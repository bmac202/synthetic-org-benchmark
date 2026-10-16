"""First look at Mersch structure x task, now that the colony mapping holds.

Four questions, in the order they gate each other.

0. ARE THESE MATRICES EVEN UNDIRECTED?  Density here is edges over n(n-1)/2,
   counted on the upper triangle, which is right only if M[i][j] == M[j][i].
   Nothing in the deposit says so. The check is two comparisons per cell and it
   runs first, because if the answer is no then the density figure that decides
   question 1 is measuring half a directed graph and every number after it
   inherits the error.

1. ARE THESE MATRICES RAW OR FILTERED?  This gates everything else. The SI says
   the published networks were thinned from a raw daily density of 72 +/- 5.3%
   down to 24.6 +/- 5.8% by dropping the lowest-weight edges, and that 17-48
   workers became isolated and were dropped from the plots. Removing the weakest
   edges is precisely the operation that manufactures degree inequality, so a
   centralization computed on a filtered matrix is not comparable to one
   computed on a raw matrix. If the density here reads ~72% these are raw and
   the comparison to the Gernat bench is available; if it reads ~25% they are
   filtered and any centralization is partly a measure of the filter. Either
   answer is useful. Not knowing is what stops the work.

2. HOW COMPLETE IS THE JOIN?  Per colony: how many network nodes carry a task
   label, how many labelled ants never appear in the network, and how many
   nodes are the unlabelled tracked ants. Reported before anything is computed
   on the joined data, because a coverage figure discovered afterwards tends to
   arrive as a footnote rather than as a denominator.

3. DOES CONTACT DIFFER BY TASK GROUP?  Mean partner count per ant by group,
   per period. This is descriptive and deliberately weak: it is a first look,
   not a test, and it inherits every caveat above.

PERIOD BOUNDS: NO LONGER AN ASSUMPTION
--------------------------------------
behavior.csv stores four task assessments as group_period1..4 and does not say
which days belong to which period, so this was carried for a while as an
inference from the SI's stability rule ("8 out of 11 days, or 7 out of 10
days"). It is not an inference. The SI states it: the clustering was run over
"the 11 first experimental days and also in all three subsequent 10-day
periods", and the fig. S5 caption independently says "the first 11-day period".
Days 1-11, 12-21, 22-31, 32-41 is therefore what the authors did, not what we
guessed they did. Recorded here because a caveat that outlives its uncertainty
is worse than no caveat -- it teaches the reader to skip the ones that matter.

WHAT IS STILL AN ASSUMPTION
---------------------------
That the deposit's day numbering starts where the paper's experimental day 1
starts. If the files were numbered from a setup day, every period boundary
shifts by one and the group means blur across them. The density, symmetry and
coverage figures do not depend on it.

Queens are reported separately throughout. A queen is a hub by caste, not by
organization, and pooling her into a worker mean answers a different question
than the one being asked.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from loaders import mersch_map
from loaders.mersch_net import matrix_files, read_matrix, NET_RE

PERIOD_OF_DAY = {d: (0 if d <= 11 else 1 if d <= 21 else 2 if d <= 31 else 3)
                 for d in range(1, 42)}
PERIOD_BOUNDS = ("days 1-11, 12-21, 22-31, 32-41 -- STATED in the SI, not inferred: "
                 "'the 11 first experimental days and also in all three subsequent "
                 "10-day periods', corroborated by the fig. S5 caption's 'the first "
                 "11-day period'")

# Which group is which cluster, from the fig. S5 caption: "nurses (cluster 1
# outlined in blue), foragers (cluster 2 outlined in orange) and cleaners
# (remaining ants grouped in clusters 3 outlined in green)."
#
# So CLEANER is the residual class -- the bucket for ants that did not sit in
# cluster 1 or cluster 2 on 70% of days. It is not a task observed in the ants;
# it is what is left over after two clusters are named. Any statement of the
# form "cleaners are X" is therefore a statement about the ants the clustering
# could not place, and the direction of the bias is knowable in advance: an ant
# that contacts both clusters broadly is exactly an ant that fails a stability
# threshold. Read every cleaner row below with that in hand.
RESIDUAL_GROUP = "cleaner"
TASK = {"n": "nurse", "c": "cleaner", "f": "forager", "q": "queen"}


def read_labels(raw_dir: Path) -> dict[str, dict[int, str]]:
    """{'4:74': {period: task}}. `NA` is missing, not a fifth task."""
    hits = [p for p in raw_dir.rglob("behavior.csv")
            if not p.name.startswith("._") and "__MACOSX" not in p.parts]
    out: dict[str, dict[int, str]] = {}
    with hits[0].open(newline=None) as fh:          # CR-only line endings
        for row in csv.DictReader(fh):
            key = f"{str(row['colony']).strip()}:{mersch_map.tag_int(row['tag_id'])}"
            per = {}
            for p in range(4):
                v = str(row.get(f"group_period{p+1}", "")).strip().lower()
                # "na" is the literal string in this file. Counting it as a value
                # is what turned attrition into 596 "group changes"; the ant did
                # not switch task, it stopped being observed.
                if v and v not in {"na", "nan", ""}:
                    per[p] = TASK.get(v, v)
            out[key] = per
    return out


def analyse(raw_dir: Path) -> dict:
    mapping = mersch_map.resolve(raw_dir, strict=True)["mapping"]
    labels = read_labels(raw_dir)
    files = matrix_files(raw_dir)

    by_col: dict[str, dict[int, Path]] = defaultdict(dict)
    for p in files:
        m = NET_RE.search(p.name)
        if m:
            by_col["col" + m.group(1)][int(m.group(2))] = p

    out = {"colony_map": mapping,
           "period_bounds_assumed": PERIOD_BOUNDS,
           "colonies": [], "unreadable": []}

    for beh in sorted(mapping, key=int):
        col = mapping[beh]
        days = sorted(by_col[col])
        dens, iso = [], []
        asym_cells = 0        # M[i][j] != M[j][i] -- see the symmetry note below
        asym_days = 0
        diag_nonzero = 0
        deg_sum: dict[str, list[int]] = defaultdict(list)   # node -> per-day degree
        deg_by_period: dict[int, dict[str, list[float]]] = {p: defaultdict(list)
                                                            for p in range(4)}
        nodes_seen: set[str] = set()

        for day in days:
            try:
                ids, M = read_matrix(by_col[col][day])
            except ValueError as exc:
                out["unreadable"].append(str(exc))
                continue
            n = len(ids)
            keys = [f"{beh}:{mersch_map.tag_int(i)}" for i in ids]
            nodes_seen.update(keys)
            deg = [0] * n
            edges = 0
            day_asym = 0
            for i in range(n):
                if M[i][i]:
                    diag_nonzero += 1
                for j in range(i + 1, n):
                    w = M[i][j]
                    if w != M[j][i]:
                        day_asym += 1
                    # Counting the upper triangle only is correct if and only if
                    # the matrix is symmetric, which nothing in the deposit
                    # states. day_asym measures it instead of assuming it: if it
                    # is ever non-zero these are directed contacts and every
                    # density and degree below is computed on the wrong object.
                    if w is not None and w > 0:
                        edges += 1
                        deg[i] += 1
                        deg[j] += 1
            asym_cells += day_asym
            asym_days += 1 if day_asym else 0
            possible = n * (n - 1) / 2
            dens.append(edges / possible if possible else 0.0)
            iso.append(sum(1 for d in deg if d == 0))
            per = PERIOD_OF_DAY.get(day)
            for k, d in zip(keys, deg):
                deg_sum[k].append(d)
                lab = labels.get(k, {}).get(per)
                if lab is not None and per is not None:
                    # Degree normalized by (n-1): a partner COUNT is not
                    # comparable across days whose colony size differs, and this
                    # colony's n moves across the 41 days.
                    deg_by_period[per][lab].append(d / (n - 1) if n > 1 else 0.0)

        labelled_here = {k for k in labels if k.startswith(beh + ":")}
        unlabelled_nodes = sorted(nodes_seen - labelled_here)
        never_seen = sorted(labelled_here - nodes_seen)
        queens = [k for k in labelled_here
                  if "queen" in set(labels.get(k, {}).values())]

        groups = {}
        for p in range(4):
            groups[p] = {g: {"n_ant_days": len(v),
                             "mean_normalized_degree": round(st.mean(v), 4),
                             "sd": round(st.pstdev(v), 4) if len(v) > 1 else None}
                         for g, v in sorted(deg_by_period[p].items())}

        out["colonies"].append({
            "behavior_colony": beh,
            "matrix": col,
            "n_days": len(days),
            "n_nodes_union": len(nodes_seen),
            "n_labelled_in_behavior_csv": len(labelled_here),
            "n_nodes_with_task_label": len(nodes_seen & labelled_here),
            "n_nodes_without_task_label": len(unlabelled_nodes),
            "unlabelled_nodes": unlabelled_nodes,
            "n_labelled_ants_never_in_network": len(never_seen),
            "queens": queens,
            "density_mean": round(st.mean(dens), 4) if dens else None,
            "density_sd": round(st.pstdev(dens), 4) if len(dens) > 1 else None,
            "density_min_max": [round(min(dens), 4), round(max(dens), 4)] if dens else None,
            "isolates_per_day_mean": round(st.mean(iso), 2) if iso else None,
            "isolates_per_day_max": max(iso) if iso else None,
            "asymmetric_cells": asym_cells,
            "days_with_any_asymmetry": asym_days,
            "nonzero_diagonal_cells": diag_nonzero,
            "normalized_degree_by_group_and_period": groups,
        })

    tot_asym = sum(c["asymmetric_cells"] for c in out["colonies"])
    tot_diag = sum(c["nonzero_diagonal_cells"] for c in out["colonies"])
    # Two separate facts, and an earlier version of this code reported them as
    # one. Asymmetry would invalidate every figure below, because counting the
    # upper triangle would then be counting half a directed graph. A non-zero
    # diagonal invalidates nothing here: the loops above run j > i, so the
    # diagonal is never read into an edge, a degree or an isolate count. Joining
    # them with "and" produced an alarm that said the matrices were directed
    # when they were perfectly symmetric. A check that cries wolf is worse than
    # no check, because the next real alarm gets read at the same discount.
    sym = ("every matrix is symmetric (0 cells with M[i][j] != M[j][i]), which "
           "matches the deposit README -- 'only column names are given (row "
           "names are symmetrical)'. An undirected reading is correct and each "
           "contact is counted once."
           if tot_asym == 0 else
           f"{tot_asym} cells have M[i][j] != M[j][i]. These are NOT undirected "
           f"matrices, so every density, degree and isolate figure below is "
           f"computed on the wrong object and none should be used until the "
           f"direction convention is established.")
    diag = ("" if tot_diag == 0 else
            f" Separately, {tot_diag} diagonal cells are non-zero -- an ant "
            f"recorded in contact with itself. This is a blemish worth knowing "
            f"about, but it changes nothing in this report: the diagonal is "
            f"never read, so no figure here moves if those cells are zeroed.")
    out["symmetry_verdict"] = sym + diag

    # A second, independent signature of the same question. The SI says edge
    # filtering left "17-48 workers" isolated per day. Isolate count and density
    # can disagree -- density is an average over all pairs, isolation is a
    # property of the worst-connected individuals -- so agreement between them
    # is worth more than either alone.
    iso_max = max((c["isolates_per_day_max"] or 0) for c in out["colonies"]) \
        if out["colonies"] else 0
    out["isolate_crosscheck"] = (
        f"maximum isolates on any single day, any colony: {iso_max}. The SI says "
        f"edge filtering left 17-48 workers isolated. "
        + ("Nothing here is close to that floor, which is a second and "
           "independent sign that these are the unfiltered networks -- it is "
           "computed from the worst-connected individuals rather than from the "
           "average pair, so it can fail while density passes."
           if iso_max < 17 else
           "This is in the range the SI attributes to filtering, which "
           "CONTRADICTS a raw reading and outranks the density figure: "
           "isolation is the direct signature of the operation, density is a "
           "downstream average."))

    d = [c["density_mean"] for c in out["colonies"] if c["density_mean"] is not None]
    if d:
        m = st.mean(d)
        out["density_verdict"] = (
            f"mean daily density {m:.1%} across colonies. The SI reports 72 +/- 5.3% "
            f"for the RAW networks and 24.6 +/- 5.8% after the lowest-weight edges "
            f"were dropped. "
            + ("This matches the raw figure: the deposit ships unfiltered networks, "
               "and a centralization computed here is comparable to one computed on "
               "another raw deposit."
               if m > 0.60 else
               "This matches the FILTERED figure: the deposit ships the thinned "
               "networks. Dropping the weakest edges manufactures degree "
               "inequality, so a centralization computed here is not comparable to "
               "a raw-network centralization and must not be placed beside the "
               "Gernat bench without that stated."
               if m < 0.40 else
               "This matches NEITHER stated figure, so what these files are is not "
               "established by density and no centralization should be reported "
               "until it is."))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()
    rep = analyse(Path(a.raw))

    print("\n  colony map:", rep["colony_map"])
    print("  period bounds:", rep["period_bounds_assumed"])
    if rep["unreadable"]:
        print(f"  {len(rep['unreadable'])} matrices unreadable:")
        for m in rep["unreadable"][:5]:
            print("   ", m)
    print("\n  DENSITY AND JOIN COVERAGE")
    print(f"  {'col':>4} {'days':>5} {'nodes':>6} {'labelled':>9} {'unlab':>6} "
          f"{'never-seen':>11} {'density':>16} {'isolates/day':>13}")
    for c in rep["colonies"]:
        print(f"  {c['behavior_colony']:>4} {c['n_days']:>5} {c['n_nodes_union']:>6} "
              f"{c['n_nodes_with_task_label']:>9} {c['n_nodes_without_task_label']:>6} "
              f"{c['n_labelled_ants_never_in_network']:>11} "
              f"{c['density_mean']:>8.4f} +/-{c['density_sd']:<5.4f} "
              f"{c['isolates_per_day_mean']:>13.1f}")
    print("\n  SYMMETRY: " + rep["symmetry_verdict"])
    print("\n  " + rep["density_verdict"])
    print("\n  ISOLATE CROSS-CHECK: " + rep["isolate_crosscheck"])

    print("\n  NORMALIZED DEGREE BY GROUP (share of possible partners contacted)")
    print("  descriptive only -- inherits the density verdict above.")
    print(f"  '{RESIDUAL_GROUP}' is the RESIDUAL class (SI fig. S5: nurses = cluster 1,")
    print("  foragers = cluster 2, cleaners = the remaining ants). It is what the")
    print("  clustering could not place on 70% of days, so a high contact figure for")
    print("  it is partly the definition and not only the animal.")
    for c in rep["colonies"]:
        print(f"  colony {c['behavior_colony']} ({c['matrix']}):")
        for p in range(4):
            g = c["normalized_degree_by_group_and_period"].get(p, {})
            if not g:
                continue
            cells = "  ".join(
                f"{k}={v['mean_normalized_degree']:.3f}(n={v['n_ant_days']})"
                for k, v in g.items())
            print(f"    period {p+1}: {cells}")

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rep, indent=2))
        print(f"\n  written: {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
