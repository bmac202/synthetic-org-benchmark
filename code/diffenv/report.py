"""Aggregate specimens into one table.   python3 -m diffenv.report results/specimens > results/summary.md

Per condition (and model, and factor set): median observed statistic across seeds, median
null 95th percentile, and how many seeds exceed it. A number is never printed without the
null next to it.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np


def load(dirpath):
    for p in sorted(glob.glob(os.path.join(dirpath, "*.json"))):
        with open(p) as f:
            yield json.load(f)


def key(spec):
    llm = spec.get("llm") or {}
    return (spec["condition"], llm.get("model", "-"), "+".join(spec.get("factors", [])) or "-")


def cell(vals, p95s, higher_is_signal=True):
    v = np.array(vals, dtype=float); q = np.array(p95s, dtype=float)
    ok = ~np.isnan(v)
    if not ok.any():
        return "n/a"
    hits = int(np.sum(v[ok] > q[ok])) if higher_is_signal else int(np.sum(v[ok] < q[ok]))
    return f"{np.nanmedian(v):.3f} vs {np.nanmedian(q):.3f} [{hits}/{ok.sum()}]"


def main(dirpath):
    groups = defaultdict(list)
    for s in load(dirpath):
        groups[key(s)].append(s)
    rows = []
    for k in sorted(groups):
        ss = groups[k]
        d = [s["derived_measures"] for s in ss]
        def pick(path, field):
            out = []
            for m in d:
                x = m
                for p in path:
                    x = x.get(p, {}) if isinstance(x, dict) else {}
                out.append(x.get(field, float("nan")) if isinstance(x, dict) else float("nan"))
            return out
        r_act = cell(pick(["activity", "R"], "observed"), pick(["activity", "R"], "null_p95"))
        r_int = cell(pick(["interaction", "R"], "observed"), pick(["interaction", "R"], "null_p95"))
        r_iso = cell(pick(["isolation", "R"], "observed"), pick(["isolation", "R"], "null_p95"))
        r_opp = cell(pick(["activity_given_opportunity", "R"], "observed"), pick(["activity_given_opportunity", "R"], "null_p95"))
        ent_obs = pick(["specialization", "entropy"], "observed"); ent_null = pick(["specialization", "entropy"], "null_median")
        ent_p = pick(["specialization", "entropy"], "p_value")
        ok = [not np.isnan(x) for x in ent_obs]
        ent = (f"{np.nanmedian(ent_obs):.3f} vs {np.nanmedian(ent_null):.3f} [{sum(1 for pp, o in zip(ent_p, ok) if o and pp < 0.05)}/{sum(ok)}]"
               if any(ok) else "n/a")
        fav = cell(pick(["specialization", "favoured_type_R"], "observed"), pick(["specialization", "favoured_type_R"], "null_p95"))
        done = np.median([s["outcome"]["completed"] for s in ss])
        unp = ""
        if ss[0].get("llm"):
            unp = f"{sum(s['llm']['unparseable'] for s in ss)}/{sum(s['llm']['calls'] for s in ss)}"
        left = np.median([len(s["outcome"]["agents_left"]) for s in ss])
        rows.append((k, len(ss), r_act, r_opp, r_int, r_iso, ent, fav, int(done), unp, left))
    print("| condition | model | factors | seeds | R activity | R activity given opportunity | R interaction | R isolation | entropy (lower = specialized) | favoured-type R | items done (of 600) | unparseable | agents left |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for (c, m, f), n, ra, ro, ri, rs, e, fv, dn, unp, left in rows:
        print(f"| {c} | {m} | {f} | {n} | {ra} | {ro} | {ri} | {rs} | {e} | {fv} | {dn} | {unp} | {left:.0f} |")
    print()
    print("Cells read: median observed vs median null threshold [seeds beyond threshold / seeds]. "
          "For R the threshold is the null 95th percentile. For entropy the second number is the null "
          "median and the bracket counts seeds whose entropy is below the null at p < 0.05 (type-shuffle null). "
          "Under private visibility quote 'R activity given opportunity', not 'R activity'.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results/specimens")
