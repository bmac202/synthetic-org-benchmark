"""Score the ant and human deposits with the same protocol as the synthetic runs.

    python3 -m diffenv.run_substrates --ants IndividualBehavioursData.xlsx \
        --invs2013 tij_InVS.dat workplace_InVS_metadata.txt \
        --invs2015 workplace_InVS15_tij.dat.gz workplace_InVS15_metadata.txt --out results/substrates

Writes one JSON with both conventions (ddof=1, the project default, and ddof=0, which
reproduces the 13 August numbers exactly) and a markdown table. Sample rules, recovered on
30 September by matching August's counts: ant colonies observed in >= 4 windows (154 naive
ants in 22 colonies); people present on >= 4 days (87 in 2013, 204 in 2015).
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

from .measures import differentiation
from .substrates import ant_interaction_tables, ant_tables, invs_tables

AUGUST = {"ants": {"activity": (0.512, 0.660), "isolation": (0.560, 0.665), "speed": (0.548, 0.695)},
          "InVS2013": (0.370, 0.498), "InVS2015": (0.312, 0.457)}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--ants"); p.add_argument("--ant-networks"); p.add_argument("--invs2013", nargs=2); p.add_argument("--invs2015", nargs=2)
    p.add_argument("--min-windows", type=int, default=4); p.add_argument("--min-days", type=int, default=4)
    p.add_argument("--draws", type=int, default=200); p.add_argument("--out", default="results/substrates")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    out = {"sample_rules": {"ant_min_windows_per_colony": a.min_windows, "human_min_days_per_person": a.min_days}}
    lines = ["| substrate | construct | n agents | windows | R (ddof=1) | null p95 | split-half | R (ddof=0) | August R | August split-half |", "|---|---|---|---|---|---|---|---|---|---|"]
    if a.ants:
        t = ant_tables(a.ants); wpc = defaultdict(set)
        for org, w, ag, v in t["activity"]:
            wpc[org].add(w)
        out["ants_meta"] = t["_meta"]; out["ants"] = {}
        for k in ("activity", "isolation", "speed"):
            tab = [r for r in t[k] if len(wpc[r[0]]) >= a.min_windows]
            d1 = differentiation(tab, seed=0, n_draws=a.draws, ddof=1); d0 = differentiation(tab, seed=0, n_draws=a.draws, ddof=0)
            out["ants"][k] = {"ddof1": d1, "ddof0": d0}
            au = AUGUST["ants"][k]
            lines.append(f"| clonal ants, naive | {k} | {d1['n_agents']} | {len({w for _, w, _, _ in tab})} | {d1['R']['observed']:.3f} | {d1['R']['null_p95']:.3f} | {d1['split_half']['observed']:+.3f} | {d0['R']['observed']:.3f} | {au[0]:.3f} | {au[1]:+.3f} |")
    if a.ant_networks:
        t = ant_interaction_tables(a.ant_networks); wpc = defaultdict(set)
        for org, w, ag, v in t["interaction"]:
            wpc[org].add(w)
        out["ant_networks_meta"] = t["_meta"]; out.setdefault("ants", {})
        for k, label in (("interaction", "interaction, all nestmates (s within 1 mm)"),
                         ("interaction_naive", "interaction, naive nestmates only")):
            tab = [r for r in t[k] if len(wpc[r[0]]) >= a.min_windows]
            d1 = differentiation(tab, seed=0, n_draws=a.draws, ddof=1); d0 = differentiation(tab, seed=0, n_draws=a.draws, ddof=0)
            out["ants"][k] = {"ddof1": d1, "ddof0": d0}
            lines.append(f"| clonal ants, naive | {label} | {d1['n_agents']} | {len({w for _, w, _, _ in tab})} | {d1['R']['observed']:.3f} | {d1['R']['null_p95']:.3f} | {d1['split_half']['observed']:+.3f} | {d0['R']['observed']:.3f} | — | — |")
    for key, paths in (("InVS2013", a.invs2013), ("InVS2015", a.invs2015)):
        if not paths:
            continue
        h = invs_tables(paths[0], paths[1], org=key, min_days=a.min_days)
        d1 = differentiation(h["interaction"], seed=0, n_draws=a.draws, ddof=1); d0 = differentiation(h["interaction"], seed=0, n_draws=a.draws, ddof=0)
        out[key] = {"meta": h["_meta"], "ddof1": d1, "ddof0": d0}
        au = AUGUST[key]
        lines.append(f"| {key} office | contact slices/day | {d1['n_agents']} | {d1['n_windows']} | {d1['R']['observed']:.3f} | {d1['R']['null_p95']:.3f} | {d1['split_half']['observed']:+.3f} | {d0['R']['observed']:.3f} | {au[0]:.3f} | {au[1]:+.3f} |")
    lines.append("")
    lines.append("ddof=1: sample variances, the project convention (also used for every synthetic run). "
                 "ddof=0: population variances, which reproduces the 13 August numbers exactly. "
                 "Nulls: label permutation within org × window, 200 draws. Magnitudes are not yet "
                 "comparable across substrates (constructs, bins and pools differ) — see RESTART.md.")
    with open(os.path.join(a.out, "substrates.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(os.path.join(a.out, "substrates.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
