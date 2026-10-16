"""Adapters that turn three external populations into the long table `measures.py` scores.

Added 6 October 2026. Same protocol, same nulls as the ants, InVS and synthetic runs.
Each adapter returns {construct: [(org, window, agent, value), ...], "_meta": {...}}.

DOTA2 (OpenDota dump, first 3 GB; data/dota_sample/out/player_matches.csv)
  Free-pick matches only (game_mode 1 All Pick, 22 Ranked All Pick; lobby 0 public, 7 ranked),
  heroes labelled carry-only or support-only. org = "dota" (one population of strangers),
  agent = account, window = consecutive block of `block` such picks in time order (block 0 =
  the player's first `block` picks in the sample), value = share of carry picks in the block.
  Players need >= `min_blocks` full blocks; only the first `max_blocks` are used, so heavy
  players do not dominate late windows. Robustness: calendar quarters (`dota_quarters`).

Takata et al. 2024 LLM community (data/takata/tidy/; private, do not redistribute)
  org = "r{range}:t{trial}", agent = agent index, window = block of `window` steps (steps 1-100).
    move_rate      share of steps the agent moved (unparseable answers count as "stay",
                   as in the simulation)
    move_rate_ok   same, over parseable answers only (window dropped if none)
    contacts       mean number of agents within message range when it spoke
    msg_len        mean characters of the raw message
    mem_len        mean characters of the memory it wrote

Kimbrough, Smith & Wilson 2008 lab economies (data/kimbrough_2008/tidy/production.csv)
  org = "{treatment}:s{session}", agent = person, window = production day (rest days dropped),
  value = share of output in the person's first good. The design induces comparative
  advantage (odd vs even subjects), so this is a positive control for designed heterogeneity.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from statistics import mean
from typing import Dict, List

Row = tuple


def dota_tables(path: str, block: int = 5, min_blocks: int = 4, max_blocks: int = 10) -> Dict[str, object]:
    picks = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["game_mode"] not in ("1", "22") or r["lobby_type"] not in ("0", "7"):
                continue
            if r["role_class"] not in ("carry", "support"):
                continue
            picks[r["account_id"]].append((int(r["start_time"]), int(r["match_id"]),
                                           1.0 if r["role_class"] == "carry" else 0.0))
    rows: List[Row] = []
    kept = 0
    for aid, ps in picks.items():
        ps.sort()
        nb = len(ps) // block
        if nb < min_blocks:
            continue
        kept += 1
        for b in range(min(nb, max_blocks)):
            chunk = ps[b * block:(b + 1) * block]
            rows.append(("dota", b, aid, mean(c for _, _, c in chunk)))
    return {"carry_share": rows,
            "_meta": {"players": kept, "block": block, "min_blocks": min_blocks,
                      "max_blocks": max_blocks, "players_any": len(picks)}}


def dota_quarters(path: str, min_picks: int = 3, min_windows: int = 4) -> Dict[str, object]:
    by = defaultdict(lambda: defaultdict(list))
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["game_mode"] not in ("1", "22") or r["lobby_type"] not in ("0", "7"):
                continue
            if r["role_class"] not in ("carry", "support"):
                continue
            y, m = int(r["day"][:4]), int(r["day"][5:7])
            q = (y - 2011) * 4 + (m - 1) // 3
            by[r["account_id"]][q].append(1.0 if r["role_class"] == "carry" else 0.0)
    rows: List[Row] = []
    kept = 0
    for aid, qs in by.items():
        good = {q: v for q, v in qs.items() if len(v) >= min_picks}
        if len(good) < min_windows:
            continue
        kept += 1
        rows.extend(("dota", q, aid, mean(v)) for q, v in good.items())
    return {"carry_share": rows, "_meta": {"players": kept, "min_picks_per_quarter": min_picks,
                                           "min_quarters": min_windows}}


def takata_tables(tidy_dir: str, window: int = 10, ranges=None) -> Dict[str, object]:
    acc = defaultdict(lambda: defaultdict(list))     # (construct) -> (org,w,agent) -> values
    with open(f"{tidy_dir}/agent_steps.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            step = int(r["step"])
            if step == 0:
                continue
            rng = int(r["range"])
            if ranges is not None and rng not in ranges:
                continue
            key = (f"r{rng:02d}:t{r['trial']}", (step - 1) // window, r["agent"])
            moved = 0.0 if r["move_parsed"] == "stay" else 1.0
            acc["move_rate"][key].append(moved)
            if r["move_parse_failed"] == "False":
                acc["move_rate_ok"][key].append(moved)
            acc["msg_len"][key].append(float(len(r["message_raw"])))
            acc["mem_len"][key].append(float(len(r["memory"])))
            acc["contacts"][key].append(0.0)          # filled from contacts.csv below
    deg = defaultdict(int)
    with open(f"{tidy_dir}/contacts.csv", newline="") as f:
        for r in csv.DictReader(f):
            rng = int(r["range"])
            if ranges is not None and rng not in ranges:
                continue
            deg[(f"r{rng:02d}:t{r['trial']}", int(r["step"]), r["sender"])] += 1
    # contacts: mean over the window's steps of the number of agents within range
    cont = defaultdict(list)
    for (org, w, a) in acc["move_rate"]:
        for s in range(w * window + 1, (w + 1) * window + 1):
            cont[(org, w, a)].append(float(deg.get((org, s, a), 0)))
    acc["contacts"] = cont
    out = {k: [(o, w, a, mean(v)) for (o, w, a), v in d.items() if v] for k, d in acc.items()}
    out["_meta"] = {"window_steps": window, "orgs": len({o for o, _, _ in acc["move_rate"]})}
    return out


def ksw_tables(production_csv: str) -> Dict[str, object]:
    by_tr = defaultdict(list)
    with open(production_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r["rest_day"] == "1" or r["share_a"] == "":
                continue
            org = f"{r['treatment']}:s{r['session']}"
            by_tr[r["treatment"]].append((org, int(r["day"]), r["person"], float(r["share_a"])))
    out = {f"share_first_good:{k}": v for k, v in by_tr.items()}
    out["share_first_good:all"] = [row for v in by_tr.values() for row in v]
    out["_meta"] = {"treatments": sorted(by_tr)}
    return out
