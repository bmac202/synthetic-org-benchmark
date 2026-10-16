#!/usr/bin/env python3
"""
Unpack, inventory and tidy the replication package for
  Kimbrough, E. O., Smith, V. L., & Wilson, B. J. (2008). Historical Property Rights,
  Sociality, and the Emergence of Impersonal Exchange in Long-Distance Trade.
  American Economic Review 98(3), 1009-1039. openICPSR project 113239, V1.
  https://www.openicpsr.org/openicpsr/project/113239/version/V1/view
  License (LICENSE.txt in the package): CC BY 4.0 for data, BSD-3 for code.

Usage (Terminal)
    cd ~/OS_Special_Issue
    python3 get_kimbrough_data.py ~/Downloads/113239-V1.zip   # unpack + tidy + mirror
    python3 get_kimbrough_data.py --tidy-only                  # re-tidy existing raw/

Package layout (from Readme.pdf)
  Build8-PR, Build8-NPR   history-building sessions, 8 people (one session 6), two goods
                          (Red, Blue); Consumption / Production / Profit per day, plus a
                          chat log of chat and item movements.
  PRH, NPRH               main sessions, 12 people in three villages, goods G1/G2/G3
                          ("G1 is the first good in the village name"); Production has G1,
                          G2; logs per village chat room (home1-3) and the two merchant
                          rooms (travelTop; travelBottom is in REVERSE order, re-sorted here).
  Days 7, 14, 21, 28, 35 are rest days with no production (all zeros).

Outputs in data/kimbrough_2008/tidy/
  panel_long.csv     treatment, session, table (production/consumption/profit), day,
                     person, good, value
  production.csv     one row per person-day: produced per good, total, share of the
                     person's first good, rest_day flag  (the specialization variable)
  persons.csv        treatment, session, person, gender, total earnings (USD), village
                     (PRH/NPRH, inferred from which home room the person acts in),
                     goods the person harvested (field->house moves in the logs)
  events.csv         every log line: room, order, day, subperiod (A/B), kind
                     (chat / harvest / transfer / take / own_move / no_production /
                     period_marker / other), group, actor (who acted), person (who
                     received), counterpart (whose goods), quantity, good, route, text.
                     "take" = an actor moved goods out of someone else's field or house
                     (possible only without property rights, Build8-NPR).
  checks.txt         integrity checks
"""
import argparse
import csv
import datetime
import hashlib
import json
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

CITATION = ("Kimbrough, E. O., Smith, V. L., & Wilson, B. J. (2008). Historical Property "
            "Rights, Sociality, and the Emergence of Impersonal Exchange in Long-Distance "
            "Trade. American Economic Review, 98(3), 1009-1039. openICPSR 113239 V1.")
URL = "https://www.openicpsr.org/openicpsr/project/113239/version/V1/view"
TREATMENTS = ("Build8-PR", "Build8-NPR", "PRH", "NPRH")


# ----------------------------------------------------------------- helpers
def md5(p, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def safe_extract(zip_path: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            t = (dest / m.filename).resolve()
            if root not in t.parents and t != root:
                sys.exit(f"unsafe path in zip, stopping: {m.filename}")
        z.extractall(dest)


def text(p: Path):
    return p.read_bytes().decode("latin-1").replace("\r", "")


def session_of(name: str):
    m = re.search(r"(\d+)\.\w+$", name)
    return int(m.group(1)) if m else None


CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, escapechar="\\")
        w.writeheader()
        for r in rows:
            w.writerow({k: CTRL.sub(" ", v) if isinstance(v, str) else v
                        for k, v in r.items()})


# ----------------------------------------------------------------- tables
def parse_table(p: Path):
    """Day x person(-good) table -> (long rows, trailing person rows)."""
    lines = [l for l in text(p).split("\n") if l.strip()]
    hi = next(i for i, l in enumerate(lines) if l.lower().startswith("period"))
    d = ";" if ";" in lines[hi] else "\t"
    hdr = [h.strip() for h in lines[hi].split(d)]
    cols = []
    for h in hdr[1:]:
        m = re.fullmatch(r"(?:(\w+)\s+)?Person (\d+)", h)
        cols.append((m.group(1) or "", int(m.group(2))) if m else None)
    long, tail, in_tail = [], [], False
    for l in lines[hi + 1:]:
        f = [x.strip() for x in l.split(d)]
        if re.fullmatch(r"\d+", f[0]) and not in_tail:
            day = int(f[0])
            for c, v in zip(cols, f[1:]):
                if c and v != "":
                    long.append(dict(day=day, person=c[1], good=c[0], value=float(v)))
        elif f[0].lower().startswith(("person", "player")):
            in_tail = True
        elif in_tail and f[0]:
            tail.append(f)
    return long, tail


# ----------------------------------------------------------------- logs
def strip_rtf(s: str):
    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252"), s)
    s = re.sub(r"\\par[d]?\b", "\n", s)
    s = re.sub(r"\{\\\*[^{}]*\}", "", s)
    s = re.sub(r"\{\\fonttbl[^{}]*(\{[^{}]*\}[^{}]*)*\}", "", s)
    s = re.sub(r"\{\\colortbl[^{}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", s)
    return s.replace("{", "").replace("}", "")


PERIOD = re.compile(r"\*+\s*Period\s+(\d+)-([AB])\s*\*+")
CHAT = re.compile(r"^(?:\\?([AB])\\)?\[Group (\d+)\]<Person (\d+)>:\s?(.*)$")
# PRH/NPRH: "[Person 1 received 5 Red from person 1(field->house)]", "... from person 4]"
RECV = re.compile(r"^\[Person (\d+) received (\d+) (\w+) from person (\d+)\s*(?:\(([^)]*)\))?\]")
# Build8-NPR: "[Person 1 moved 5 Red from person 2's house to person 1's house]"
MOVE_LOC = re.compile(r"^\[Person (\d+) moved (\d+) (\w+) from person (\d+)'s (\w+) "
                      r"to person (\d+)'s (\w+)\]", re.I)
# Build8-PR: "[Person 1 moved 22 red and 1 blue to person 2]", "[... moved 5 blue to person 8]"
MOVE_TO = re.compile(r"^\[Person (\d+) moved (.+?) to person (\d+)\]", re.I)
QTY = re.compile(r"(\d+) (\w+)")


def parse_log(p: Path, reverse: bool):
    lines = [l.strip() for l in strip_rtf(text(p)).replace("\x00", "").split("\n")]
    lines = [l for l in lines if l and l not in ("Courier New;", ";;;")]
    if reverse:
        # the bottom merchant room scrolled up: whole file is newest-first
        lines = lines[::-1]
    out, day, sub = [], None, None
    for i, l in enumerate(lines):
        base = dict(order=i, day=day, subperiod=sub, kind="other", group="", actor="",
                    person="", counterpart="", quantity="", good="", route="", text=l)
        r = dict(base)
        if m := PERIOD.search(l):
            day, sub = int(m.group(1)), m.group(2)
            r.update(day=day, subperiod=sub, kind="period_marker")
        elif "No Production" in l:
            r["kind"] = "no_production"
        elif m := CHAT.match(l):
            r.update(kind="chat", group=int(m.group(2)), actor=int(m.group(3)),
                     person=int(m.group(3)), text=m.group(4), subperiod=m.group(1) or sub)
        elif m := RECV.match(l):
            to, q, g, frm, route = m.groups()
            route = route or ""
            harvest = "field" in route.lower() and to == frm
            r.update(kind="harvest" if harvest else "transfer", actor=int(frm),
                     person=int(to), counterpart=int(frm), quantity=int(q),
                     good=g.capitalize(), route=route)
        elif m := MOVE_LOC.match(l):
            act, q, g, src, sloc, dst, dloc = m.groups()
            act, src, dst = int(act), int(src), int(dst)
            if src == dst == act and sloc.lower() == "field" and dloc.lower() == "house":
                kind = "harvest"
            elif src == dst:
                kind = "own_move"                       # e.g. house -> own field
            elif act != src:
                kind = "take"                           # actor removes another's goods
            else:
                kind = "transfer"
            r.update(kind=kind, actor=act, person=dst, counterpart=src, quantity=int(q),
                     good=g.capitalize(), route=f"{sloc.lower()}->{dloc.lower()}")
        elif m := MOVE_TO.match(l):
            act, what, to = m.groups()
            parts = QTY.findall(what)
            if parts:
                for q, g in parts:                     # one row per good moved
                    out.append(dict(base, kind="transfer", actor=int(act), person=int(to),
                                    counterpart=int(act), quantity=int(q),
                                    good=g.capitalize(), route="moved"))
                continue
        out.append(r)
    return out


# ----------------------------------------------------------------- tidy
def tidy(raw: Path, tidy_dir: Path):
    tidy_dir.mkdir(parents=True, exist_ok=True)
    panel, persons, events, checks = [], {}, [], []
    for tr in TREATMENTS:
        for p in sorted((raw / tr).glob("*.txt")):
            kind = p.name.split("-")[0].lower()
            s = session_of(p.name)
            long, tail = parse_table(p)
            for r in long:
                panel.append(dict(treatment=tr, session=s, table=kind, **r))
            if kind == "profit":
                ids = sorted({r["person"] for r in long})
                ok = len(tail) == len(ids)   # gender/earnings are listed in person order
                for k in ids:
                    f = tail[k - 1] if ok else ["", ""]
                    g = f[0].lower()[:1]
                    pay = f[1].replace("$", "").strip() if len(f) > 1 else ""
                    persons[(tr, s, k)] = dict(
                        treatment=tr, session=s, person=k, gender=g if g in "mf" else "",
                        gender_raw=f[0], earnings_usd=pay,
                        note="" if ok else f"earnings list has {len(tail)} rows for "
                                           f"{len(ids)} people; not assigned")
        for p in sorted((raw / tr).glob("*.rtf")):
            room = re.sub(r"-+.*$", "", p.name).lower()       # chat / home1 / travelTop ...
            s = session_of(p.name)
            for r in parse_log(p, reverse=room == "travelbottom"):
                events.append(dict(treatment=tr, session=s, room=room, **r))

    # production per person-day
    prod = defaultdict(dict)
    for r in panel:
        if r["table"] == "production":
            prod[(r["treatment"], r["session"], r["day"], r["person"])][r["good"]] = r["value"]
    prows = []
    for (tr, s, d, k), g in sorted(prod.items()):
        goods = sorted(g)                                  # ['Blue','Red'] or ['G1','G2']
        first = "Red" if "Red" in g else "G1"
        tot = sum(g.values())
        prows.append(dict(treatment=tr, session=s, day=d, person=k,
                          good_a=first, produced_a=g.get(first, 0),
                          good_b=[x for x in goods if x != first][0],
                          produced_b=sum(v for x, v in g.items() if x != first),
                          total=tot, share_a=round(g.get(first, 0) / tot, 4) if tot else "",
                          rest_day=int(tot == 0 and d % 7 == 0)))

    # village and harvested goods per person, from the logs
    home, harvested = defaultdict(Counter), defaultdict(Counter)
    for e in events:
        key = (e["treatment"], e["session"], e["person"])
        if e["person"] == "":
            continue
        if e["room"].startswith("home") and e["kind"] in ("chat", "harvest"):
            home[key][e["room"]] += 1
        if e["kind"] == "harvest" and e["counterpart"] == e["person"]:
            harvested[key][e["good"]] += e["quantity"]
    for key, row in persons.items():
        h = home.get(key)
        row["village"] = h.most_common(1)[0][0].replace("home", "") if h else ""
        row["village_share"] = round(h.most_common(1)[0][1] / sum(h.values()), 3) if h else ""
        hv = harvested.get(key, Counter())
        row["harvested_goods"] = "/".join(f"{g}:{q}" for g, q in hv.most_common())

    write_csv(tidy_dir / "panel_long.csv", panel,
              ["treatment", "session", "table", "day", "person", "good", "value"])
    write_csv(tidy_dir / "production.csv", prows,
              ["treatment", "session", "day", "person", "good_a", "produced_a", "good_b",
               "produced_b", "total", "share_a", "rest_day"])
    write_csv(tidy_dir / "persons.csv", sorted(persons.values(),
              key=lambda r: (r["treatment"], r["session"], r["person"])),
              ["treatment", "session", "person", "gender", "gender_raw", "earnings_usd",
               "village", "village_share", "harvested_goods", "note"])
    write_csv(tidy_dir / "events.csv", events,
              ["treatment", "session", "room", "order", "day", "subperiod", "kind", "group",
               "actor", "person", "counterpart", "quantity", "good", "route", "text"])

    # checks
    sess = sorted({(r["treatment"], r["session"]) for r in prows})
    checks.append(f"sessions: {len(sess)}")
    for tr, s in sess:
        rows = [r for r in prows if (r["treatment"], r["session"]) == (tr, s)]
        np_ = len({r["person"] for r in rows})
        days = sorted({r["day"] for r in rows})
        rest = sorted({r["day"] for r in rows if r["total"] == 0}
                      - {r["day"] for r in rows if r["total"] > 0})
        npers = sum(1 for k in persons if k[:2] == (tr, s))
        ev = Counter(e["kind"] for e in events if (e["treatment"], e["session"]) == (tr, s))
        vill = Counter(persons[k]["village"] for k in persons if k[:2] == (tr, s))
        checks.append(f"{tr:<11} s{s}: persons={np_} (profit tail {npers}) days={len(days)} "
                      f"rest_days={rest} events chat={ev['chat']} harvest={ev['harvest']} "
                      f"transfer={ev['transfer']} take={ev['take']} own_move={ev['own_move']} "
                      f"other={ev['other']}"
                      + (f" villages={dict(sorted(vill.items()))}" if tr in ("PRH", "NPRH") else ""))
    other = Counter(e["text"][:40] for e in events if e["kind"] == "other")
    checks.append("unclassified log lines (most common): " + repr(other.most_common(8)))
    (tidy_dir / "checks.txt").write_text("\n".join(checks) + "\n")
    print("\n".join(checks))
    print(f"\nWrote {tidy_dir}: panel_long ({len(panel):,}), production ({len(prows):,}), "
          f"persons ({len(persons)}), events ({len(events):,})")
    return [panel, prows, persons, events]


# ----------------------------------------------------------------- drive
def mirror(out: Path, drive: Path):
    if not drive.is_dir():
        print(f"\nOWC drive not mounted ({drive}); skipped the drive copy.")
        return
    d_raw = drive / "data" / "raw" / "kimbrough_2008"
    d_pro = drive / "data" / "processed" / "kimbrough_2008"
    shutil.copytree(out / "raw", d_raw, dirs_exist_ok=True)
    if (out / "inventory.csv").exists():
        shutil.copy2(out / "inventory.csv", d_raw / "inventory.csv")
    shutil.copytree(out / "tidy", d_pro, dirs_exist_ok=True)   # overwrite in place
    files = [p for p in (out / "tidy").iterdir() if p.is_file()]
    bad = [p.name for p in files if md5(p) != md5(d_pro / p.name)]
    if bad:
        sys.exit(f"drive copy mismatch: {bad}")
    mf = drive / "MANIFEST.json"
    if mf.exists():
        m = json.loads(mf.read_text())
        m["entries"] = {k: v for k, v in m["entries"].items()
                        if not k.startswith("kimbrough_2008/processed/")}
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for p in files:
            m["entries"][f"kimbrough_2008/processed/{p.name}"] = dict(
                dataset="kimbrough_2008", file=p.name, url=URL,
                local_path=str(d_pro / p.name), bytes=p.stat().st_size, md5=md5(p),
                complete=True, citation=CITATION, license="CC BY 4.0 (data)",
                why="Tidy tables built by get_kimbrough_data.py from raw/kimbrough_2008.",
                fetched=now)
        mf.write_text(json.dumps(m, indent=2))
    print(f"Mirrored tidy/ to {d_pro} (md5-checked)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip", nargs="?", type=Path)
    ap.add_argument("--tidy-only", action="store_true")
    ap.add_argument("--project", type=Path, default=Path.home() / "OS_Special_Issue")
    ap.add_argument("--drive", type=Path, default=Path("/Volumes/OWC Express 1M2/BeeOrg"))
    a = ap.parse_args()
    out = a.project / "data" / "kimbrough_2008"
    raw = out / "raw"

    if not a.tidy_only:
        if not a.zip or not a.zip.expanduser().is_file():
            sys.exit("give the downloaded zip, or use --tidy-only")
        if raw.exists() and any(raw.iterdir()):
            sys.exit(f"{raw} already holds the package; use --tidy-only")
        safe_extract(a.zip.expanduser(), raw)
        inv = [dict(path=str(p.relative_to(raw)), bytes=p.stat().st_size, md5=md5(p))
               for p in sorted(raw.rglob("*")) if p.is_file() and p.name != ".DS_Store"]
        write_csv(out / "inventory.csv", inv, ["path", "bytes", "md5"])
        print(f"Unpacked {len(inv)} files into {raw}")
    if not raw.is_dir():
        sys.exit(f"no package at {raw}")
    (out / ".gitignore").write_text("raw/\n")
    tidy(raw, out / "tidy")
    mirror(out, a.drive)


if __name__ == "__main__":
    main()
