"""Score DOTA2, the Takata LLM community and the KSW lab economies with the same protocol.

    cd ~/OS_Special_Issue/code
    python3 -m diffenv.run_external --out diffenv_results/external_2026-10-06

Reads ../data/dota_sample/out/player_matches.csv, ../data/takata/tidy/, and
../data/kimbrough_2008/tidy/production.csv. Writes external.json and external.md.
The output folder is gitignored because it reports results on the Takata data, which we
promised to send to the authors before circulating.
"""
from __future__ import annotations

import argparse
import json
import os

from .external import dota_quarters, dota_tables, ksw_tables, takata_tables
from .measures import differentiation

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def line(label, construct, d):
    return (f"| {label} | {construct} | {d['n_agents']} | {d['n_windows']} | "
            f"{d['R']['observed']:.3f} | {d['R']['null_p95']:.3f} | "
            f"{d['split_half']['observed']:+.3f} | {d['split_half']['null_p95']:+.3f} |")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="diffenv_results/external_2026-10-06")
    p.add_argument("--draws", type=int, default=200)
    p.add_argument("--skip", nargs="*", default=[])
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, ".gitignore"), "w") as f:
        f.write("*\n")
    res, lines = {}, [
        "| population | construct | n agents | windows (org x window) | R | R null p95 | split-half | split-half null p95 |",
        "|---|---|---|---|---|---|---|---|"]

    def score(label, construct, tab, key):
        d = differentiation(tab, seed=0, n_draws=a.draws)
        res[key] = d
        lines.append(line(label, construct, d))
        print(lines[-1], flush=True)

    if "dota" not in a.skip:
        pm = os.path.join(ROOT, "data", "dota_sample", "out", "player_matches.csv")
        t = dota_tables(pm); res["dota_meta"] = t["_meta"]
        score("DOTA2 players (blocks of 5 picks)", "carry share", t["carry_share"], "dota_blocks")
        t = dota_tables(pm, block=10, min_blocks=4)
        score("DOTA2 players (blocks of 10 picks)", "carry share", t["carry_share"], "dota_blocks10")
        t = dota_quarters(pm); res["dota_quarters_meta"] = t["_meta"]
        score("DOTA2 players (calendar quarters)", "carry share", t["carry_share"], "dota_quarters")

    if "takata" not in a.skip:
        tidy = os.path.join(ROOT, "data", "takata", "tidy")
        t = takata_tables(tidy, ranges=[5])
        main_run = {k: [r for r in v if r[0] == "r05:t01"] for k, v in t.items() if k != "_meta"}
        for k in ("move_rate", "move_rate_ok", "contacts", "msg_len", "mem_len"):
            score("Takata main run (range 5, trial 01)", k, main_run[k], f"takata_main:{k}")
        for rng in (0, 5, 10, 15, 20, 25):
            t = takata_tables(tidy, ranges=[rng])
            for k in ("move_rate", "move_rate_ok", "contacts", "msg_len", "mem_len"):
                if rng == 25 and k == "contacts":
                    continue           # everyone hears everyone: no variance by design
                score(f"Takata range {rng} (10 trials)", k, t[k], f"takata_r{rng:02d}:{k}")

    if "ksw" not in a.skip:
        t = ksw_tables(os.path.join(ROOT, "data", "kimbrough_2008", "tidy", "production.csv"))
        for tr in t["_meta"]["treatments"] + ["all"]:
            score(f"KSW 2008 lab ({tr})", "share of first good", t[f"share_first_good:{tr}"],
                  f"ksw:{tr}")

    lines += ["", "Protocol: measures.differentiation (ddof=1), values standardized within org x "
              "window, nulls permute agent labels within org x window (200 draws). DOTA2: one org, "
              "windows are per-player blocks of picks. Takata: org = trial, windows = 10 steps. "
              "KSW: org = session, window = production day; comparative advantage is induced by design."]
    with open(os.path.join(a.out, "external.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    with open(os.path.join(a.out, "external.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
