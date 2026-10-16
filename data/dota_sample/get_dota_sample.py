#!/usr/bin/env python3
"""
Download and profile the 3 GB OpenDota match sample, to decide whether the full 2011-2016
dump (156 GB) is worth pulling for the DOTA2 field benchmark (Ching, Forti & Rawley 2024).

Source: OpenDota data dump (CC BY-SA 4.0), sample hosted for opendotadump-tools:
  https://storage.googleapis.com/dota-match-dumps/matches_small.csv
  Format: one row per match; `pgroup` is JSON {slot: {account_id, hero_id, player_slot}}.
  account_id 4294967295 = player with a private profile (anonymous).

Usage (Terminal; the download needs your own network, ~3 GB, resumable):
    cd ~/OS_Special_Issue
    python3 data/dota_sample/get_dota_sample.py          # download (if needed) + profile
    python3 data/dota_sample/get_dota_sample.py --min-matches 20

Where things go
  raw CSV:  /Volumes/OWC Express 1M2/BeeOrg/data/raw/opendota_sample/matches_small.csv
            (or data/dota_sample/raw/ if the drive is not mounted)
  outputs:  data/dota_sample/out/  (mirrored to BeeOrg/data/processed/opendota_sample/)
    profile.txt           what the sample is: matches, dates, modes, anonymity, repeat players
    accounts.csv          every public account: matches, first/last date, distinct heroes,
                          carry / support / both / neither picks
    player_matches.csv    one row per (public account, match) for accounts with at least
                          --min-matches matches: start_time, hero, role class, team, win, mode
Pass 1 counts accounts; pass 2 writes rows for the repeat players only. Hero roles come from
hero_roles.csv (OpenDota dotaconstants, current labels; heroes were rebalanced over 2011-2016).
"""
import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

URL = "https://storage.googleapis.com/dota-match-dumps/matches_small.csv"
ANON = 4294967295
HERE = Path(__file__).resolve().parent
DRIVE = Path("/Volumes/OWC Express 1M2/BeeOrg")
csv.field_size_limit(sys.maxsize)
LOBBY = {0: "public", 1: "practice", 2: "tournament", 5: "team", 6: "solo queue",
         7: "ranked", 8: "1v1 mid", -1: "invalid"}


def day(ts):
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%d")


def download(dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL}\n  -> {dest}  (resumable; re-run if interrupted)")
    r = subprocess.run(["curl", "-L", "--fail", "-C", "-", "-o", str(dest), URL])
    if r.returncode not in (0, 33):          # 33: server ignored range on a finished file
        sys.exit(f"curl failed (exit {r.returncode}); re-run to resume")


def matches(path: Path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                pg = json.loads(row["pgroup"]) if row.get("pgroup") else {}
            except json.JSONDecodeError:
                pg = None
            yield row, pg


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, help="use an already downloaded sample")
    ap.add_argument("--min-matches", type=int, default=10)
    ap.add_argument("--max-rows", type=int, default=0, help="stop after N matches (testing)")
    ap.add_argument("--drive", type=Path, default=DRIVE)
    a = ap.parse_args()

    raw_dir = (a.drive / "data" / "raw" / "opendota_sample") if a.drive.is_dir() \
        else HERE / "raw"
    src = a.csv or raw_dir / "matches_small.csv"
    if not a.csv:
        download(src)
    out = HERE / "out"
    out.mkdir(exist_ok=True)

    roles = {}
    with open(HERE / "hero_roles.csv", newline="") as f:
        for r in csv.DictReader(f):
            roles[int(r["hero_id"])] = r["role_class"]

    # ---------------- pass 1: profile + per-account counts
    n = bad = 0
    t_min, t_max = None, None
    lobby, mode, humans, slots_anon, slots = Counter(), Counter(), Counter(), 0, 0
    days = Counter()
    acc = defaultdict(lambda: [0, None, None, 0, Counter()])  # n, first, last, hero bitmask, roles
    for row, pg in matches(src):
        n += 1
        if a.max_rows and n > a.max_rows:
            n -= 1
            break
        if pg is None:
            bad += 1
            continue
        t = int(row["start_time"] or 0)
        t_min = t if t_min is None else min(t_min, t)
        t_max = t if t_max is None else max(t_max, t)
        days[day(t)] += 1
        lobby[row.get("lobby_type", "")] += 1
        mode[row.get("game_mode", "")] += 1
        humans[row.get("human_players", "")] += 1
        for p in pg.values():
            slots += 1
            aid = int(p.get("account_id") or ANON)
            if aid == ANON:
                slots_anon += 1
                continue
            s = acc[aid]
            s[0] += 1
            s[1] = t if s[1] is None else min(s[1], t)
            s[2] = t if s[2] is None else max(s[2], t)
            h = int(p.get("hero_id") or 0)
            s[3] |= 1 << h
            s[4][roles.get(h, "unknown")] += 1
        if n % 500000 == 0:
            print(f"  pass 1: {n:,} matches", flush=True)

    with open(out / "accounts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "matches", "first_day", "last_day", "span_days",
                    "distinct_heroes", "carry", "support", "both", "neither", "unknown"])
        for aid, (k, t0, t1, hs, rc) in acc.items():
            w.writerow([aid, k, day(t0), day(t1), round((t1 - t0) / 86400, 1), bin(hs).count("1"),
                        rc["carry"], rc["support"], rc["both"], rc["neither"], rc["unknown"]])

    counts = Counter(s[0] for s in acc.values())
    def at_least(k):
        return sum(v for m, v in counts.items() if m >= k)
    keep = {aid for aid, s in acc.items() if s[0] >= a.min_matches}

    # ---------------- pass 2: rows for repeat players
    rows = 0
    with open(out / "player_matches.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "match_id", "start_time", "day", "hero_id", "role_class",
                    "player_slot", "team", "win", "lobby_type", "game_mode", "duration",
                    "public_teammates"])
        i = 0
        for row, pg in matches(src):
            i += 1
            if a.max_rows and i > a.max_rows:
                break
            if not pg:
                continue
            ps = [(int(p.get("account_id") or ANON), p) for p in pg.values()]
            hit = [(aid, p) for aid, p in ps if aid in keep]
            if not hit:
                continue
            rad_win = row.get("radiant_win", "") in ("t", "true", "True", "1")
            for aid, p in hit:
                slot = int(p.get("player_slot") or 0)
                team = "radiant" if slot < 128 else "dire"
                mates = sum(1 for b, q in ps if b != ANON and b != aid and
                            (int(q.get("player_slot") or 0) < 128) == (slot < 128))
                h = int(p.get("hero_id") or 0)
                w.writerow([aid, row["match_id"], row["start_time"], day(row["start_time"]),
                            h, roles.get(h, "unknown"), slot, team,
                            int(rad_win == (team == "radiant")), row.get("lobby_type", ""),
                            row.get("game_mode", ""), row.get("duration", ""), mates])
                rows += 1

    # ---------------- profile
    span = (t_max - t_min) / 86400 if t_min else 0
    L = [f"OpenDota sample profile — {dt.date.today()}  source: {src}",
         f"matches: {n:,}  (unparseable pgroup: {bad:,})",
         f"dates (UTC): {day(t_min)} to {day(t_max)}  = {span:.1f} days; "
         f"distinct days with matches: {len(days)}",
         f"busiest days: {days.most_common(5)}",
         f"lobby types: " + ", ".join(f"{LOBBY.get(int(k), k) if k.lstrip('-').isdigit() else k}"
                                      f" {v:,}" for k, v in lobby.most_common(8)),
         f"game modes (code: count): {dict(mode.most_common(8))}",
         f"human players per match: {dict(humans.most_common(5))}",
         f"player slots: {slots:,}; anonymous {slots_anon / max(slots, 1):.1%}",
         f"public accounts: {len(acc):,}",
         "accounts with at least k matches: " + ", ".join(
             f">={k}: {at_least(k):,}" for k in (2, 5, 10, 20, 50, 100)),
         f"player_matches.csv: {rows:,} rows for {len(keep):,} accounts with "
         f">= {a.min_matches} matches",
         "VERDICT GUIDE: the full dump is worth it if repeat players are many here OR the",
         "sample covers only a short window (then the full 5 years multiplies repeats)."]
    (out / "profile.txt").write_text("\n".join(L) + "\n")
    print("\n" + "\n".join(L))

    if a.drive.is_dir():
        d = a.drive / "data" / "processed" / "opendota_sample"
        shutil.copytree(out, d, dirs_exist_ok=True)
        shutil.copy2(HERE / "hero_roles.csv", d / "hero_roles.csv")
        print(f"\nMirrored outputs to {d}")


if __name__ == "__main__":
    main()
