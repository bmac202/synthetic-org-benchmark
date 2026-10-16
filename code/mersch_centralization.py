"""Mersch degree centralization, placed beside the bench on comparable terms.

The gate this was waiting on is open. check_mersch_join.py established that the
deposit ships the RAW networks -- mean daily density 70.0% against the SI's
72 +/- 5.3% raw and 24.6 +/- 5.8% filtered, and a maximum of 3 isolates on any
colony-day against the 17-48 the SI attributes to filtering. Dropping weak edges
is the operation that manufactures degree inequality, so that verdict is what
makes a Mersch centralization comparable to one computed on another raw deposit
at all.

But "comparable" was doing too much work in that sentence, and this script exists
because of what it was hiding.

THE DENSITY CEILING
-------------------
Freeman degree centralization is sum(dmax - d_i) / ((n-1)(n-2)). On a graph whose
density is p, the mean degree is already p(n-1), and the hub can be no better than
n-1, so the numerator cannot exceed n(n-1) - 2m. At p = 0.70 that ceiling is about
0.30 -- no 70%-dense graph on any number of nodes can score higher, however
brutally centralized its wiring is. A sparser network is not competing under the
same constraint.

So the headline comparison is not a like-for-like one. If the bench figure came
from networks materially sparser than 70%, then reading "Mersch is less
centralized than the bench" off the raw numbers is reading off the densities. The
statistic would be doing what the SI's edge filter would have done: reporting a
property of how many edges survived.

Three answers, printed together, because any one of them alone is misleading:

  1. FREEMAN, as the bench computes it. Imported from netstats rather than
     reimplemented here, so the two datasets cannot drift apart definitionally.
     Quotable only with its density beside it.

  2. FREEMAN / CEILING-AT-THIS-DENSITY. What share of the inequality available
     at this edge count was realised. Read the warning below before quoting it:
     the first run showed it is not the density-free number this line originally
     claimed, and it is kept mainly to show its own limits.

WHAT FREEMAN ACTUALLY MEASURES, WHICH IS LESS THAN IT LOOKS
-----------------------------------------------------------
Expand the numerator. sum(dmax - d_i) = n*dmax - sum(d_i) = n*dmax - 2m. So

    Freeman = (n*dmax - 2m) / ((n-1)(n-2))

depends on the data through exactly three numbers: n, the edge count, and the
single largest degree. The rest of the degree distribution is not in it. Two
colonies with wildly different inequality among their ordinary workers score
identically if their busiest ant and their edge count match. Freeman is not a
measure of degree inequality; it is a measure of how far the top node sits above
the mean, and it is the standard the bench uses, so it has to be reported -- but
it should never be the only thing reported.

That has a sharp consequence for measure 2. Ratio = (n*dmax - 2m)/(n(n-1) - 2m),
which equals exactly 1 the moment dmax = n-1, whatever the other n-1 ants are
doing. At 70% density an ant that contacted every single nestmate on some day is
not rare, so the ratio saturates and stops discriminating. On the first real run
three of the six colonies hit exactly 1.0000 on their most extreme day. Worse,
across the six colonies the ratio's rank correlation with density is +0.94 --
having "corrected" for density it now tracks density almost perfectly, in the
opposite direction to raw Freeman's -0.60. It over-corrects. The saturation rate
is therefore printed beside it, and the honest comparison is measure 4.

  4. MATCHED-DENSITY FREEMAN. Thin both datasets to the SAME density by keeping
     their heaviest edges, then compute Freeman on both. No ceiling arithmetic,
     no normalisation to argue about -- the two networks are simply put on equal
     terms and the standard statistic is run on both.

     It only works when both sides can REACH the target, and against the Gernat
     log they cannot. Thinning removes edges; it cannot add them. A 4 h bee bin
     runs at 0.35% density against a Mersch day's 70%, so asking for 25% leaves
     the bee side untouched and thins only the ants -- and the first version of
     this script did exactly that, then printed "this is the pair to quote" over
     a 27%-dense graph and a 0.35%-dense one. It now reads the comparison log
     first and lowers the target to whatever the sparser side actually has. That
     exposes the real obstacle: at 0.35% density a 102-ant colony has about 18
     edges, so nearly every ant is an isolate and Freeman is measuring one node
     against an empty field. The three conditions -- equal observation window,
     achieved densities within 10%, neither side fragmented past 20% isolates --
     are checked separately and the side-by-side figure is withheld unless all
     three pass, because which one fails determines what to do next.

     The density gap between these two systems is not a measurement choice to be
     corrected away. It is structural: a bee cannot meet 2000 nestmates in a day
     and an ant in a colony of 130 can meet all of them. Aggregating the bee log
     to 24 h bins narrows it and is worth doing, but nothing will bring 2335
     individuals to 70% density, so the honest comparison across these two
     systems is probably not a Freeman pair at all.

  3. GINI OF WEIGHTED STRENGTH. The Mersch matrices are weighted and the binary
     reading throws that away: at 70% density nearly every pair has SOME contact,
     so who contacts whom is close to uninformative while how much is not. Gini
     uses the whole distribution rather than its maximum, is bounded 0-1, and on
     the first real run correlated with density at only -0.31 against Freeman's
     -0.60 and the ratio's +0.94 -- the least density-contaminated of the three.
     It is NOT comparable to a published Freeman figure. It is a different
     statistic, reported because it is the one carrying signal.

     A correction, recorded here because an earlier version of this docstring
     said the opposite: Gini is NOT scale-free either, and the raw cross-system
     comparison it licenses is narrower than it first appeared. Gini of strength
     reaches 0 only in the limit of many events per individual; with few events,
     counting noise alone concentrates strength and Gini rises. A bee bin of
     ~1000 individuals sharing a few thousand food-sharing events has a chance
     baseline several times higher than an ant day of ~130 individuals sharing
     tens of thousands of contacts. The first three-colony run produced
     Mersch 0.2037-0.2720 against bees 0.2363-0.2733 and the overlap looked like
     a result; it is not one until each side is read against its own baseline.
     `gini_null.py` computes that baseline by holding n and the event count fixed
     and throwing every event at a uniformly chosen pair.

     A SECOND correction, on top of the first, recorded for the same reason. The
     paragraph above used to end "the panel reports the EXCESS. Quote the excess,
     or quote the level with its null beside it." Do not. Subtracting the null
     over-corrects, because true inequality and counting noise combine
     sub-additively rather than linearly, and `gini_null.bias_table()` measures
     the excess as the WORST of four candidates when true inequality is held
     fixed and only the scale is varied across the ranges this project spans.
     The measured artifact in the excess is about 0.054, which is the same
     magnitude as the ant-vs-bee difference anyone would want to interpret --
     so the excess bands (Mersch 0.1835-0.2450, logs 0.1497-0.1856) must not be
     quoted, and neither must the raw pair.

     What IS quotable is the matched-intensity panel: thin events on both sides
     to the same events-per-individual, which for this data means thinning the
     ants by roughly a factor of ten down to the bees' ~39-45, then compare the
     plain Gini. This assumes nothing about distribution shape, which is what
     disqualified quadrature (sqrt(obs^2 - null^2)) -- better than matching on
     lognormal and gamma propensities, worse on heavy-tailed and two-class ones,
     so adopting it means betting on a shape nobody has measured. Matching has
     the best worst case, but it is not exact either: run `python3 gini_null.py`
     to print the residual, around 0.028 on a heavy tail, and do not read a
     separation smaller than that as a separation.

THE THRESHOLD SWEEP
-------------------
Keeping only the heaviest edges and recomputing shows directly how much of the
Freeman number is density rather than structure. The 25% row matters most: the SI
says the published networks were thinned to 24.6 +/- 5.8% density, so that row is
roughly the network the paper itself analysed, and it is also the row to use if
the bench figure turns out to come from a network of about that sparsity. If
Freeman climbs steeply across the sweep on a fixed set of ants, then the
cross-dataset comparison at face value was measuring the filter.

This is a sensitivity analysis, not a correction. These are the raw networks and
the raw row is the real one. The rest of the sweep says how far the answer would
travel if it were not.

WHAT IS NOT COMPUTED HERE
-------------------------
The centralization z-score. `centralization_null` shuffles recipients while
preserving out-activity, and against a 70%-dense graph the shuffle produces
something close to a complete graph every time, so the null lands near zero and
the z lands enormously negative. That number reads as "these colonies are
significantly less centralized than chance" and it does not mean that. It is a
statement about what the null can produce at this density. Not printed, so it
cannot be quoted.

ISOLATES, AND WHY THE ROSTER MATTERS
------------------------------------
An ant with no contacts on a given day never appears in an edge list, so a log-
derived node count silently drops it and n comes out too small -- which inflates
centralization, since the ants most missing are exactly the least connected. Here
the matrix header IS the roster, so isolates are known. They are passed to
netstats as self-events: `degree_centralization` adds both endpoints to its node
set before it checks `a != b`, so a self-event registers presence at degree zero.
The script then asserts the resulting n equals the matrix node count, which turns
a silent undercount into a crash.

A log read with --compare has no roster, so its isolates cannot be recovered and
its n is whatever interacted. That asymmetry is printed with the result rather
than left for the reader to discover.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from loaders import mersch_map
from loaders.mersch_net import matrix_files, read_matrix, NET_RE
from netstats import degree_centralization
from gini_null import null_gini, events_per_individual, gini_at_intensity

PERIOD_OF_DAY = {d: (0 if d <= 11 else 1 if d <= 21 else 2 if d <= 31 else 3)
                 for d in range(1, 42)}
KEEP_FRACTIONS = (1.00, 0.50, 0.25)


# ------------------------------------------------------------------ measures
def freeman_ceiling(n: int, m: int) -> float:
    """Largest Freeman centralization any graph with these n and m can reach.

    Two regimes. Below m = n-1 there are not enough edges to wire a full star, so
    the best hub has degree m and the ceiling is m/(n-1). Above it the hub sits at
    n-1 and every additional edge must land between two non-hubs, lifting two
    degrees and costing 2 from the numerator: (n(n-1) - 2m)/((n-1)(n-2)). The two
    agree at m = n-1, where both give exactly 1.
    """
    if n < 3:
        return 0.0
    if m <= n - 1:
        return m / (n - 1)
    return max(0.0, (n * (n - 1) - 2 * m) / ((n - 1) * (n - 2)))


def gini(xs) -> float:
    """Mean absolute difference over twice the mean. 0 = everyone equal."""
    v = sorted(float(x) for x in xs)
    n = len(v)
    if n < 2:
        return 0.0
    total = sum(v)
    if total <= 0:
        return 0.0
    # sum_i (2i - n + 1) x_i on sorted values -- the O(n) form of the double sum.
    cum = sum((2 * i - n + 1) * x for i, x in enumerate(v))
    return cum / (n * total)


def measure(nodes, edges, with_null: bool = False) -> dict:
    """edges: list of (i, j, w) with i < j, w > 0. nodes: the full roster.

    `with_null` adds the chance baseline for Gini(strength). It is off by
    default because it is only meaningful on the RAW graph -- running it on a
    thinned graph would give the null for an event count that no colony has.
    """
    n = len(nodes)
    m = len(edges)
    log = [{"sender": a, "recipient": a, "mtype": "report"} for a in nodes]
    log += [{"sender": a, "recipient": b, "mtype": "report"} for a, b, _ in edges]
    cen = degree_centralization(log)

    # If this ever fires, the roster and the log disagree and every figure in the
    # row is computed on a different n than the one reported next to it.
    seen = {x["sender"] for x in log} | {x["recipient"] for x in log}
    if len(seen) != n:
        raise AssertionError(f"node set {len(seen)} != roster {n}")

    deg = defaultdict(int)
    stg = defaultdict(float)
    for a in nodes:
        deg[a] += 0
        stg[a] += 0.0
    for a, b, w in edges:
        deg[a] += 1
        deg[b] += 1
        stg[a] += w
        stg[b] += w
    ceil_ = freeman_ceiling(n, m)
    dens = (2 * m / (n * (n - 1))) if n > 1 else 0.0
    dmax = max(deg.values()) if deg else 0
    # WHO the top node is, not just how big its degree is. Freeman sees the data
    # through dmax alone, so if the same individual holds it in every bin the
    # statistic is largely a readout of that one animal -- and if that animal is
    # the queen, it is measuring biology rather than organisation.
    dmax_node = max(deg, key=lambda a: (deg[a], str(a))) if deg else None

    # Gini(strength) is 0 only in the limit of many events per individual. With
    # few events, chance alone concentrates counts. The bee bins have ~1000
    # individuals sharing a few thousand events and the ant days ~130 sharing
    # tens of thousands, so the two sides have DIFFERENT zero points and a
    # matching raw Gini does not mean matching inequality.
    #
    # `events_per_individual` is 2E/n, the mean strength, and it is the number
    # that decides how much of an observed Gini is counting noise. It is carried
    # on every row because the matched-intensity pass needs the minimum across
    # BOTH systems before it can thin either of them.
    events = int(round(sum(w for _, _, w in edges)))
    ng = ex = None
    if with_null and n >= 2 and events > 0:
        ng = null_gini(n, events, reps=40, seed=17)["median"]
        # RETAINED IN THE JSON, NOT QUOTABLE. See the correction under measure 3
        # in the module docstring: subtracting the null over-corrects, because
        # true inequality and counting noise combine sub-additively. It is kept
        # only so that a reader who saw the earlier tables can find the number
        # and see it superseded rather than silently vanished.
        ex = round(gini(stg.values()) - ng, 4) if ng is not None else None

    return dict(n=n, m=m, density=round(dens, 4), dmax_node=dmax_node,
                events=events, gini_strength_null=ng, gini_strength_excess=ex,
                epi=round(events_per_individual(n, edges), 2),
                freeman=round(cen, 4),
                freeman_ceiling=round(ceil_, 4),
                freeman_of_ceiling=(round(cen / ceil_, 4) if ceil_ > 0 else None),
                gini_degree=round(gini(deg.values()), 4),
                gini_strength=round(gini(stg.values()), 4),
                dmax=dmax,
                # Freeman is (n*dmax - 2m)/((n-1)(n-2)), so when one individual
                # has contacted everyone the ratio to the ceiling is exactly 1
                # regardless of how the other n-1 are wired. Counting how often
                # that happens is the difference between a normalisation and a
                # constant.
                dmax_saturated=int(dmax == n - 1),
                isolates=sum(1 for a in nodes if deg[a] == 0))


def thin_to_density(nodes, edges, target: float):
    """Keep the heaviest edges until density is at or below `target`.

    The point is to remove density as an explanation before comparing two
    datasets, without any normalisation formula standing between the data and the
    statistic. Ties at the cutoff are kept together, so the achieved density can
    land above the target; it is returned rather than assumed.
    """
    n = len(nodes)
    if n < 3 or not edges:
        return list(edges)
    want = int(target * n * (n - 1) / 2)
    if want >= len(edges):
        return list(edges)
    if want < 1:
        return []
    ws = sorted((w for _, _, w in edges), reverse=True)
    cut = ws[want - 1]
    return [e for e in edges if e[2] >= cut]


def sweep(nodes, edges) -> dict:
    """Recompute after keeping only the heaviest edges.

    The cutoff is a weight, not a rank, so ties at the boundary are all kept and
    the achieved density is reported rather than the requested one. Asking for the
    top 25% and getting 31% because a third of the edges share one weight is
    information, not an error to be rounded away.
    """
    out = {}
    if not edges:
        return out
    ws = sorted((w for _, _, w in edges), reverse=True)
    for f in KEEP_FRACTIONS:
        k = max(1, int(round(f * len(ws))))
        cut = ws[k - 1]
        kept = [e for e in edges if e[2] >= cut]
        r = measure(nodes, kept)
        r["requested_keep"] = f
        r["weight_cutoff"] = cut
        out[f"{int(f * 100)}pct"] = r
    return out


# -------------------------------------------------------------------- inputs
def mersch_days(raw_dir: Path):
    """Yield (behaviour_colony, day, nodes, edges) per matrix file."""
    files = matrix_files(raw_dir)
    if not files:
        raise SystemExit(f"no network_col*_day*.txt under {raw_dir}")
    # strict=True: a mapping that does not reproduce is not a weaker mapping, it
    # is a relabelling machine, and every colony-level row below would be wrong
    # in a way no downstream check could catch.
    mapping = mersch_map.resolve(raw_dir, strict=True)["mapping"]
    col_of_matrix = {v: k for k, v in mapping.items()}
    for p in sorted(files):
        mm = NET_RE.search(p.name)
        if not mm:
            continue
        matrix_col, day = "col" + mm.group(1), int(mm.group(2))
        ids, M = read_matrix(p)
        n = len(ids)
        edges = []
        for i in range(n):
            for j in range(i + 1, n):
                w = M[i][j]
                if w is not None and w > 0:
                    edges.append((ids[i], ids[j], float(w)))
        yield col_of_matrix.get(matrix_col, matrix_col), matrix_col, day, ids, edges


def compare_bins(log_dir: Path):
    """Yield (bin, nodes, edges) from a canonical interaction_log.csv."""
    path = log_dir / "interaction_log.csv" if log_dir.is_dir() else log_dir
    per = defaultdict(lambda: defaultdict(int))
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            a, b = r["sender"], r["recipient"]
            if a == b:
                continue
            t = int(r.get("tbin") or 0)
            per[t][(a, b) if a < b else (b, a)] += 1
    for t in sorted(per):
        pairs = per[t]
        nodes = sorted({x for pr in pairs for x in pr})
        yield t, nodes, [(a, b, float(w)) for (a, b), w in pairs.items()]


# ------------------------------------------------------------------- reports
def summarise(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return dict(median=round(st.median(vals), 4),
                lo=round(min(vals), 4), hi=round(max(vals), 4), n=len(vals))


def analyse_mersch(raw_dir: Path, match_density: float = 0.25) -> dict:
    by_col = defaultdict(list)
    bins_by_col = defaultdict(list)
    for beh_col, matrix_col, day, ids, edges in mersch_days(raw_dir):
        bins_by_col[beh_col].append((day, list(ids), edges))
        r = measure(ids, edges, with_null=True)
        r.update(day=day, period=PERIOD_OF_DAY.get(day), matrix=matrix_col)
        r["sweep"] = sweep(ids, edges)
        mt = measure(ids, thin_to_density(ids, edges, match_density))
        r["matched_freeman"] = mt["freeman"]
        r["matched_density"] = mt["density"]
        r["matched_gini_strength"] = mt["gini_strength"]
        r["matched_m"] = mt["m"]
        r["matched_isolate_frac"] = round(mt["isolates"] / mt["n"], 4) if mt["n"] else None
        by_col[beh_col].append(r)

    out = {"unit": "one colony-day; days are NOT pooled, because the union of 11 "
                   "days of a 70%-dense graph is a near-complete graph and its "
                   "centralization is near zero by construction",
           "colonies": []}
    for col in sorted(by_col, key=lambda x: str(x)):
        rows = sorted(by_col[col], key=lambda r: r["day"])
        c = dict(behavior_colony=col, matrix=rows[0]["matrix"], n_days=len(rows),
                 nodes=rows[0]["n"],
                 density=summarise(rows, "density"),
                 freeman=summarise(rows, "freeman"),
                 freeman_ceiling=summarise(rows, "freeman_ceiling"),
                 freeman_of_ceiling=summarise(rows, "freeman_of_ceiling"),
                 gini_strength=summarise(rows, "gini_strength"),
                 gini_strength_null=summarise(rows, "gini_strength_null"),
                 gini_strength_excess=summarise(rows, "gini_strength_excess"),
                 events=summarise(rows, "events"),
                 epi=summarise(rows, "epi"),
                 gini_degree=summarise(rows, "gini_degree"),
                 matched_freeman=summarise(rows, "matched_freeman"),
                 matched_density=summarise(rows, "matched_density"),
                 matched_isolate_frac=summarise(rows, "matched_isolate_frac"),
                 dmax_saturated_days=sum(r["dmax_saturated"] for r in rows))
        c["by_period"] = {}
        for p in range(4):
            pr = [r for r in rows if r["period"] == p]
            if pr:
                c["by_period"][p] = dict(
                    n_days=len(pr), freeman=summarise(pr, "freeman"),
                    freeman_of_ceiling=summarise(pr, "freeman_of_ceiling"),
                    gini_strength=summarise(pr, "gini_strength"))
        c["sweep_median"] = {}
        for tag in (f"{int(f * 100)}pct" for f in KEEP_FRACTIONS):
            sr = [r["sweep"][tag] for r in rows if tag in r.get("sweep", {})]
            if sr:
                c["sweep_median"][tag] = dict(
                    density=summarise(sr, "density"), freeman=summarise(sr, "freeman"),
                    freeman_of_ceiling=summarise(sr, "freeman_of_ceiling"))
        # Not JSON-serialisable and not meant to be: stripped before writing.
        c["_bins"] = bins_by_col[col]
        out["colonies"].append(c)

    fm = [c["freeman"]["median"] for c in out["colonies"] if c["freeman"]]
    dn = [c["density"]["median"] for c in out["colonies"] if c["density"]]
    if fm and dn:
        out["headline"] = (
            f"median daily Freeman centralization {st.median(fm):.4f} "
            f"(colony medians {min(fm):.4f} to {max(fm):.4f}) at median density "
            f"{st.median(dn):.1%}. Quote the two together or not at all: at this "
            f"density the arithmetic ceiling on Freeman is about "
            f"{freeman_ceiling(150, int(round(st.median(dn) * 150 * 149 / 2))):.2f}, "
            f"so a low value here is not evidence of a flat colony until it is "
            f"read against that ceiling or against the sweep below.")
    return out


def analyse_compare(log_dir: Path, match_density: float = 0.25) -> dict:
    rows = []
    bins = []
    namespaces = set()
    for t, nodes, edges in compare_bins(log_dir):
        namespaces.update(x.split(":", 1)[0] for x in nodes if ":" in x)
        if len(nodes) < 3:
            continue
        bins.append((t, list(nodes), edges))
        r = measure(nodes, edges, with_null=True)
        mt = measure(nodes, thin_to_density(nodes, edges, match_density))
        r.update(tbin=t, matched_freeman=mt["freeman"],
                 matched_density=mt["density"],
                 matched_gini_strength=mt["gini_strength"],
                 matched_m=mt["m"],
                 matched_isolate_frac=(round(mt["isolates"] / mt["n"], 4)
                                       if mt["n"] else None))
        rows.append(r)
    if not rows:
        return {}

    # The observation window is the other half of the density problem. A Mersch
    # row is one DAY of contact; if these bins are an hour each, the comparison
    # log has had less time to accumulate edges and will look sparser and more
    # centralized for reasons that have nothing to do with either colony.
    meta = {}
    mp = (log_dir / "meta.json") if log_dir.is_dir() else log_dir.parent / "meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text())
        except (ValueError, OSError):
            meta = {}
    bh = meta.get("bin_hours")
    window = (f"each bin is {bh} h against a Mersch row of 24 h"
              + ("" if bh in (24, 24.0) else
                 " -- NOT the same observation window, so regenerate this log "
                 "with --bin-hours 24 before reading the raw densities against "
                 "each other")
              if bh else
              "bin width unknown (no bin_hours in meta.json); confirm it matches "
              "the 24 h of a Mersch row before comparing densities")

    # The gernat loader namespaces node ids as "trial:id" precisely so that bee 7
    # of one colony is not merged with bee 7 of another. That makes pooling
    # visible here: more than one prefix means this log holds several colonies in
    # one adjacency matrix, and they are disjoint components. Density is then
    # divided by roughly the number of colonies and Freeman with it, so every
    # figure below is an artefact of pooling rather than a property of any colony.
    # Cheap to detect, catastrophic to miss.
    pooled = sorted(namespaces) if len(namespaces) > 1 else None

    # Freeman depends on the data only through n, m and the single largest degree,
    # so the identity of that one individual decides the statistic. If it is the
    # same animal in every bin, "centralization" is that animal's degree wearing a
    # structural name; if that animal is the queen, it is a fact about bee biology
    # and not about how the colony organises work.
    special = meta.get("special_nodes") or {}
    tops = Counter(r["dmax_node"] for r in rows if r.get("dmax_node") is not None)
    top_node, top_bins = (tops.most_common(1)[0] if tops else (None, 0))
    hub = dict(most_frequent=top_node, bins_held=top_bins, of_bins=len(rows),
               is_special=(str(top_node) in special) if top_node is not None else None,
               special_label=special.get(str(top_node)),
               special_held_bins=sum(1 for r in rows
                                     if str(r.get("dmax_node")) in special),
               n_special_marked=len(special))

    return dict(source=str(log_dir), n_bins=len(rows), window=window,
                bin_hours=bh, pooled_trials=pooled, hub=hub, _bins=bins,
                nodes=summarise(rows, "n"),
                density=summarise(rows, "density"),
                freeman=summarise(rows, "freeman"),
                freeman_ceiling=summarise(rows, "freeman_ceiling"),
                freeman_of_ceiling=summarise(rows, "freeman_of_ceiling"),
                gini_strength=summarise(rows, "gini_strength"),
                gini_strength_null=summarise(rows, "gini_strength_null"),
                gini_strength_excess=summarise(rows, "gini_strength_excess"),
                events=summarise(rows, "events"),
                epi=summarise(rows, "epi"),
                matched_freeman=summarise(rows, "matched_freeman"),
                matched_density=summarise(rows, "matched_density"),
                matched_isolate_frac=summarise(rows, "matched_isolate_frac"),
                dmax_saturated_bins=sum(r["dmax_saturated"] for r in rows),
                roster_caveat=("n here is derived from the log, so any individual "
                               "that interacted with nobody in a bin is invisible "
                               "and n is a lower bound. The Mersch rows do not "
                               "have this problem -- the matrix header is the "
                               "roster -- so the two n's are not the same kind of "
                               "number, and the bias runs one way: dropping "
                               "isolates raises centralization."))


# The residual scale artifact left in matched intensity, measured by
# gini_null.bias_table() on the worst of the distribution shapes tried
# (heavy-tailed, pareto 1.8). Two bands that fail to overlap by less than this
# have not been shown to differ: the gap is inside what the method invents out
# of scale alone. Stating that rule in prose and not enforcing it in the code is
# how it gets forgotten at the moment it becomes inconvenient.
GINI_RESOLUTION = 0.028


def gini_verdict(a, b):
    """(state, gap) for two (lo, hi) bands. States: overlap, too close, separate."""
    if a[0] > b[1]:
        gap = a[0] - b[1]
    elif b[0] > a[1]:
        gap = b[0] - a[1]
    else:
        return "overlap", 0.0
    return ("separate" if gap > GINI_RESOLUTION else "too close"), gap


def matched_intensity(rep, reps: int = 9) -> dict:
    """Put both systems at the same events per individual, then compare plain Gini.

    WHY THIS AND NOT A CORRECTION TO THE RAW NUMBERS
    ------------------------------------------------
    Two earlier attempts at this comparison were withdrawn. The first quoted the
    raw Gini bands side by side, which assumes the two systems share a zero
    point; they do not, because Gini(strength) is inflated by counting noise and
    the ants have an order of magnitude more events per individual than the
    bees. The second subtracted each side's own null -- the excess -- and that
    is worse: `gini_null.bias_table()` measures it as the WORST of four
    candidates at fixed true inequality, because inequality and noise combine
    sub-additively so subtraction over-corrects.

    Thinning assumes nothing about the shape of the underlying distribution. It
    is the operation the matched-density comparison already performs on edges,
    one level down on events. The residual bias is not zero -- run
    `python3 gini_null.py` to see it, around 0.03 on a heavy tail -- but it is
    nearly the same on both sides, and a comparison only needs that.

    Thinning cannot ADD events, so the target is the minimum over every bin on
    both sides and the sparser side is reported as `thinned: no`. That is not a
    failure; it is the side that sets the target. What would be a failure is
    reporting a matched table in which only one side was actually matched, so
    every row carries its own flag.
    """
    groups = []
    for c in rep.get("colonies") or []:
        if c.get("_bins"):
            groups.append(("Mersch", c.get("behavior_colony"), c["_bins"]))
    for c in rep.get("compare") or []:
        if not c or not c.get("_bins"):
            continue
        # Same rule as the density target: a pooled log is refused elsewhere, so
        # it must not be allowed to set the target on its way out.
        if c.get("pooled_trials"):
            continue
        groups.append(("log", Path(c["source"]).name, c["_bins"]))
    if not groups:
        return {}

    # WHICH bin sets the target, not just what the target is. The minimum over
    # every bin on both sides is a single number chosen by a single bin, and the
    # matched-density pass already had to be fixed once for exactly this: one
    # degenerate dataset silently steering the whole table. A short bin at the
    # edge of a recording -- a day that was only partly observed -- has both a
    # small roster and a low intensity, and if it wins the min() it thins every
    # other bin in the run by a factor chosen by an accident of where the
    # recording started. So name the winner, and compare its roster against its
    # own group's typical roster.
    catalog = []
    for side, label, bins in groups:
        for key, nd, ed in bins:
            e = events_per_individual(len(nd), ed)
            if e > 0:
                catalog.append(dict(side=side, label=str(label), key=str(key),
                                    n=len(nd), epi=e))
    if not catalog:
        return {}
    setter = min(catalog, key=lambda r: r["epi"])
    target = setter["epi"]
    peer_n = st.median([r["n"] for r in catalog if r["label"] == setter["label"]])
    setter = dict(setter, epi=round(setter["epi"], 2), peer_median_n=peer_n,
                  runt=bool(peer_n and setter["n"] < 0.6 * peer_n))

    # The whole method rests on one claim: at a fixed number of events per
    # individual the chance baseline is the same regardless of how many
    # individuals there are. If that were false, matching intensity would still
    # leave the 130-ant and 1000-bee sides on different zero points and we would
    # be back where we started with a new coat of paint. It is cheap to check on
    # the actual rosters in this run rather than take it on faith, so check it.
    ns = sorted({len(nd) for _, _, bins in groups for _, nd, _ in bins})
    shared = []
    for n in (ns[0], ns[-1]):
        e = int(round(target * n / 2))
        if n >= 2 and e > 0:
            v = null_gini(n, e, reps=40, seed=23)["median"]
            if v is not None:
                shared.append((n, v))
    baseline_ok = (len(shared) < 2 or
                   abs(shared[0][1] - shared[-1][1]) <= 0.01)

    prim_rows, prim_gone = _matched_rows(groups, target, reps, drop_below=False)
    out = {"target_epi": round(target, 2), "reps": reps, "target_set_by": setter,
           "shared_null": [dict(n=n, null=v) for n, v in shared],
           "baseline_ok": baseline_ok,
           "rows": prim_rows, "vanished": prim_gone,
           "total_bins": sum(len(b) for _, _, b in groups)}

    # SENSITIVITY. The target above is one number picked by one bin. If the
    # overlap-or-separation verdict flips when that bin is replaced by a
    # different reasonable choice, the verdict belongs to the bin rather than to
    # the animals. Re-run at the sparsest GROUP's median intensity and at twice
    # the primary target. Both are higher than the primary, and thinning cannot
    # add events, so bins that cannot reach the higher target are DROPPED rather
    # than left unthinned -- leaving them in would put them at a higher noise
    # floor than everything else in the same column, which is the very confusion
    # this whole exercise exists to remove.
    by_group = {}
    for r in catalog:
        by_group.setdefault(r["label"], []).append(r["epi"])
    sparsest = min(by_group, key=lambda k: st.median(by_group[k]))
    alts = sorted({round(st.median(by_group[sparsest]), 2), round(2 * target, 2)})
    out["sensitivity"] = []
    for t in alts:
        if t <= target * 1.05:
            continue
        rows, gone = _matched_rows(groups, t, max(5, reps // 2), drop_below=True)
        if rows:
            out["sensitivity"].append(dict(target_epi=t, rows=rows,
                                           vanished=gone))
    return out


def _matched_rows(groups, target, reps, drop_below):
    """One matched-intensity table at one target.

    `drop_below` decides what happens to a bin that is already sparser than the
    target. At the primary target -- the global minimum -- exactly one bin is in
    that position and it is the definition of the target, so it keeps its plain
    Gini. At any HIGHER target, a bin below it cannot be thinned up to meet it,
    and quietly keeping its raw value would mix two noise floors in one column.
    Drop it, and report how many were dropped so a table built on half the data
    cannot pass for a table built on all of it.

    CORRECTION. An earlier version returned only `rows`, and a group whose every
    bin fell below the target produced no row at all -- so its bins were counted
    neither as kept nor as dropped, and the whole group left the comparison
    without appearing anywhere in the output. On the real deposit that hid an
    entire bee log at the highest target, and it was the log with the highest
    median, so the side that lost data was also the side whose range shrank.
    A group leaving the comparison is the single most important thing that can
    happen to a comparison, so it is now returned separately and printed by name.
    """
    rows, vanished = [], []
    for side, label, bins in groups:
        vals, thinned_bins, dropped, have = [], 0, 0, []
        for i, (_key, nd, ed) in enumerate(bins):
            n = len(nd)
            have.append(events_per_individual(n, ed))
            g = gini_at_intensity(n, ed, target, reps=reps, seed=100 + i)
            if g["thinned"]:
                thinned_bins += 1
                vals.append(g["median"])
            elif drop_below:
                dropped += 1
            else:
                # Already at or below the target: the plain Gini IS the matched
                # value, because this bin is what the target was taken from.
                stg = defaultdict(float)
                for a in nd:
                    stg[a] += 0.0
                for a, b, w in ed:
                    stg[a] += w
                    stg[b] += w
                vals.append(round(gini(stg.values()), 4))
        if not vals:
            vanished.append(dict(
                side=side, label=str(label), lost_bins=dropped or len(bins),
                have_epi_lo=round(min(have), 1) if have else None,
                have_epi_hi=round(max(have), 1) if have else None))
            continue
        rows.append(dict(
            side=side, label=str(label), n_bins=len(vals),
            thinned_bins=thinned_bins, dropped_bins=dropped,
            have_epi_lo=round(min(have), 1), have_epi_hi=round(max(have), 1),
            gini=round(st.median(vals), 4),
            lo=round(min(vals), 4), hi=round(max(vals), 4)))
    return rows, vanished


def print_matched_intensity(mi) -> None:
    if not mi or not mi.get("rows"):
        return
    t = mi["target_epi"]
    print("\n  GINI OF STRENGTH AT MATCHED SAMPLING INTENSITY")
    print(f"    every bin thinned to {t:.1f} events per individual, which is the "
          "minimum across")
    print("    both systems -- the sparsest bin sets the target and is itself "
          "left alone.")
    ts = mi.get("target_set_by")
    if ts:
        print(f"    That bin is {ts['side']}/{ts['label']} {ts['key']}, roster "
              f"{ts['n']} against a group median of {ts['peer_median_n']:.0f}.")
        if ts.get("runt"):
            print("    ITS ROSTER IS WELL BELOW ITS OWN GROUP'S, which is what a "
                  "partly-observed bin at\n    the edge of a recording looks "
                  "like. One short bin is then choosing how hard every\n    "
                  "other bin in the table gets thinned. Read the sensitivity "
                  "rows below before\n    quoting anything from this table.")
    print(f"    {'side':<8} {'group':<22} {'bins':>5} {'thinned':>8} "
          f"{'own events/ind':>16} {'Gini at target':>24}")
    for r in mi["rows"]:
        band = f"{r['gini']:.4f} [{r['lo']:.4f},{r['hi']:.4f}]"
        print(f"    {r['side']:<8} {r['label']:<22} {r['n_bins']:>5} "
              f"{r['thinned_bins']:>3}/{r['n_bins']:<4} "
              f"{r['have_epi_lo']:>7.0f}-{r['have_epi_hi']:<8.0f} {band:>24}")
    sn = mi.get("shared_null") or []
    if len(sn) >= 2:
        lo, hi = sn[0], sn[-1]
        print(f"\n    Chance baseline at this intensity: {lo['null']:.4f} for a "
              f"roster of {lo['n']}, {hi['null']:.4f} for {hi['n']}.")
        if mi.get("baseline_ok"):
            print("    Those agree, which is the assumption the method rests on "
                  "-- at fixed events per\n    individual the noise floor does "
                  "not care how many individuals there are, so both\n    sides "
                  "are now measured from the same zero. Note it is not zero: "
                  "neither absolute\n    level below is pure inequality, but "
                  "the DIFFERENCE between them is interpretable.")
        else:
            print("    THOSE DO NOT AGREE, and they are supposed to. The claim "
                  "that matching intensity\n    equalises the baseline has "
                  "failed on these rosters, so the table above is not a\n    "
                  "like-for-like comparison after all. Do not quote it; work "
                  "out why first.")

    sides = {}
    for r in mi["rows"]:
        sides.setdefault(r["side"], []).append(r["gini"])
    if len(sides) == 2:
        (sa, va), (sb, vb) = sides.items()
        a = (min(va), max(va))
        b = (min(vb), max(vb))
        state, gap = gini_verdict(a, b)
        sep = state == "separate"
        print(f"\n    {sa} group medians {a[0]:.4f} to {a[1]:.4f}; "
              f"{sb} {b[0]:.4f} to {b[1]:.4f}")
        thin = [s for s, v in ((sa, va), (sb, vb)) if len(v) < 2]
        if thin:
            # A "band" from one colony is a point, and a gap between a point and
            # a band is not evidence of anything about either population.
            print(f"    {', '.join(thin)} contributes fewer than 2 colonies, so "
                  "one side has no band at all.\n    Whatever the arrangement "
                  "below says, it is provisional until that side has\n    "
                  "several colonies to vary over.")
        if not mi.get("baseline_ok"):
            sep = False
            print("    Verdict withheld: the baseline check above failed.")
        elif sep:
            print(f"    The bands are apart by {gap:.4f}, which clears the "
                  f"{GINI_RESOLUTION:.3f} that matching itself\n    invents out "
                  "of scale on the worst distribution shape tried. That is a "
                  "real\n    difference in how unequally interaction effort is "
                  "distributed, and it survives the\n    scale objection that "
                  "killed the raw and excess versions of this comparison.")
        elif state == "too close":
            print(f"    The bands fail to overlap, but only by {gap:.4f}, and "
                  f"matching leaves a residual\n    artifact of about "
                  f"{GINI_RESOLUTION:.3f} (gini_null.bias_table(), heavy-tailed "
                  "case). A gap smaller than\n    the method's own error is not "
                  "a difference. TOO CLOSE TO CALL -- and specifically not\n    "
                  "quotable as a separation, which is the tempting misreading.")
        else:
            print("    The bands OVERLAP. Once the recording intensities are "
                  "matched there is no\n    evidence here that effort is more "
                  "unequally distributed in one system than the\n    other. "
                  "That is a result, not a failure -- the raw gap was a "
                  "property of how long\n    each colony was watched.")

    def _verdict(rows):
        s = {}
        for r in rows:
            s.setdefault(r["side"], []).append(r["gini"])
        if len(s) != 2:
            return None
        (_sa, va), (_sb, vb) = s.items()
        a, b = (min(va), max(va)), (min(vb), max(vb))
        return gini_verdict(a, b)[0], a, b, len(va), len(vb)

    sens = [s for s in (mi.get("sensitivity") or []) if _verdict(s["rows"])]
    if not sens:
        # Saying nothing here would be read as nothing to say. An untested
        # verdict and a verdict that survived testing look identical on the page
        # unless the difference is printed.
        print("\n    SENSITIVITY: none available. Every alternative target was "
              "within 5% of the\n    primary, so this run cannot tell you "
              "whether the verdict depends on which bin\n    happened to be "
              "sparsest. Treat it as untested on that axis.")
    elif not mi.get("baseline_ok"):
        print("\n    SENSITIVITY: skipped. The baseline check failed, so there "
              "is no verdict to test.")
    else:
        print("\n    SENSITIVITY -- does the verdict belong to the animals or to "
              "the one bin that set\n    the target? Re-run at higher targets, "
              "dropping bins too sparse to reach them:")
        base = _verdict(mi["rows"])
        total = mi.get("total_bins") or 0
        print(f"      {'target':>7} {'kept/dropped':>14} {'grp':>5} "
              f"{'side A':>18} {'side B':>18}  verdict")
        if base:
            v, a, b, na, nb = base
            print(f"      {mi['target_epi']:>7.1f} {'all bins':>14} "
                  f"{f'{na}v{nb}':>5} "
                  f"{a[0]:.4f}-{a[1]:.4f} {b[0]:.4f}-{b[1]:.4f}  {v}")
        flips = 0
        lost_groups, thin_sides = [], []
        for s_ in sens:
            r = _verdict(s_["rows"])
            if not r:
                continue
            v, a, b, na, nb = r
            kept = sum(x["n_bins"] for x in s_["rows"])
            gone = s_.get("vanished") or []
            # A group that lost EVERY bin returns no row, so its bins are in
            # neither sum. Counting only the per-row drops made kept+dropped fall
            # short of the total and made a vanished group invisible; add them
            # back explicitly, and reconcile against the known total so a future
            # accounting hole announces itself instead of being absorbed.
            drop = (sum(x["dropped_bins"] for x in s_["rows"])
                    + sum(x["lost_bins"] for x in gone))
            tag = "" if not total or kept + drop == total else " ?"
            for g in gone:
                lost_groups.append((s_["target_epi"], g))
            if min(na, nb) < 2:
                thin_sides.append((s_["target_epi"], na, nb))
            print(f"      {s_['target_epi']:>7.1f} {f'{kept}/{drop}{tag}':>14} "
                  f"{f'{na}v{nb}':>5} "
                  f"{a[0]:.4f}-{a[1]:.4f} {b[0]:.4f}-{b[1]:.4f}  {v}")
        for t_, g in lost_groups:
            print(f"      at {t_:.1f}, {g['side']} group {g['label']} left the "
                  f"comparison entirely: all {g['lost_bins']} of its bins\n"
                  f"        top out at {g['have_epi_hi']} events per individual, "
                  f"below the target. Its range is\n"
                  f"        not in that row.")
        for t_, na, nb in thin_sides:
            print(f"      at {t_:.1f} one side is down to {min(na, nb)} group, so "
                  f"its 'range' is a single number.\n"
                  f"        A verdict from that row is not evidence about "
                  f"either population.")
            # What matters is whether the CLAIM changes, not whether the label
            # does. "overlap" and "too close" are both "no difference shown", so
            # moving between them is not a flip and calling it one would train
            # the reader to ignore the line that matters.
            if base and (v == "separate") != (base[0] == "separate"):
                flips += 1
        if flips:
            print("\n      THE VERDICT FLIPS between targets: at one the data "
                  "supports a claim of difference\n      and at another it does "
                  "not. That makes it a statement about how hard the data was\n"
                  "      thinned rather than about either colony. Do not quote "
                  "either version.")
        elif base:
            claim = ("a difference" if base[0] == "separate"
                     else "no demonstrated difference")
            print(f"\n      Every target tried gives {claim}, so that conclusion "
                  "is not an artefact of\n      which bin happened to be "
                  "sparsest.")
            if lost_groups or thin_sides:
                # The agreement above is real but it is not agreement across the
                # same data. Rows that lost a whole group agree using less
                # evidence, and saying "every target agrees" without saying that
                # invites the reader to count them as independent confirmations.
                print("      Read that with the losses above in mind: the higher "
                      "targets agree using\n      fewer groups, not more "
                      "evidence. The primary row is the one built on "
                      "everything.")

    print("\n    Not quotable, and kept in the JSON only so the superseded "
          "numbers can be found:\n    `gini_strength_excess`. Subtracting each "
          "side's null over-corrects; it measures as\n    the worst of four "
          "candidates at fixed true inequality. See gini_null.bias_table().")


def fmt(s) -> str:
    return "     --     " if not s else f"{s['median']:.4f} [{s['lo']:.4f},{s['hi']:.4f}]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True, help="Mersch raw deposit directory")
    ap.add_argument("--compare", default=None, nargs="+", metavar="DIR",
                    help="one or more canonical loader output dirs (each holding an "
                         "interaction_log.csv) to run through the identical "
                         "measures, e.g. one Gernat trial per directory. Give all "
                         "of them: a single bee colony is one number and six ant "
                         "colonies are a range, and comparing a number to a range "
                         "is how a difference gets claimed that six more colonies "
                         "would have dissolved")
    ap.add_argument("--match-density", type=float, default=0.25,
                    help="thin both datasets to this density and re-run Freeman on "
                         "both, so the comparison is not decided by sparsity. "
                         "Default 0.25, which is also the density the SI says the "
                         "PUBLISHED Mersch networks were thinned to.")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    # Thinning can only REMOVE edges, so a target above the sparser dataset's own
    # density is a no-op on that side and the two are not matched at all. Read the
    # comparison log first, and drop the target to whatever the sparser side can
    # actually reach. An earlier version skipped this and printed a confident
    # "this is the pair to quote" over a 27%-dense graph and a 0.35%-dense one.
    target, lowered, tgt_excluded = a.match_density, None, []
    if a.compare:
        pres = [analyse_compare(Path(p), a.match_density) for p in a.compare]
        # A pooled log is REFUSED further down, so it must not be allowed to set
        # the target on its way out. Pooling divides density by roughly the
        # colony count, so a pooled log is always the sparsest log in the room
        # and would always win the min() below -- and then every colony in the
        # table is thinned to a density that no colony has, chosen by the one
        # dataset the script is about to tell you not to use. Exclude it from
        # the target and say so, rather than silently letting it steer.
        usable = []
        for p, path in zip(pres, a.compare):
            if not p or not p.get("density"):
                continue
            if p.get("pooled_trials"):
                tgt_excluded.append((path, len(p["pooled_trials"]),
                                     p["density"]["median"]))
                continue
            usable.append(p["density"]["median"])
        # The SPARSEST log sets the target, not the average of them: a target
        # above any one log's density is a no-op on that log, and then that log
        # alone is unmatched while the table says every side was thinned.
        if usable and min(usable) < target:
            lowered = (target, min(usable))
            target = min(usable)

    rep = analyse_mersch(Path(a.raw), target)
    print("\n  UNIT: " + rep["unit"])
    nd = sorted({c["n_days"] for c in rep["colonies"]})
    print(f"\n  PER COLONY, median [min,max] over the "
          f"{nd[0] if len(nd) == 1 else str(nd)} days")
    print(f"  {'col':>4} {'n':>5} {'density':>22} {'Freeman':>22} "
          f"{'Gini(strength)':>22} {'Gini(degree)':>22} {'sat':>4}")
    for c in rep["colonies"]:
        print(f"  {str(c['behavior_colony']):>4} {c['nodes']:>5} "
              f"{fmt(c['density']):>22} {fmt(c['freeman']):>22} "
              f"{fmt(c['gini_strength']):>22} {fmt(c['gini_degree']):>22} "
              f"{c['dmax_saturated_days']:>4}")
    print("  'sat' = days on which one ant contacted every nestmate. On those days")
    print("  Freeman sits exactly at its ceiling whatever the other ants did, so the")
    print("  ceiling ratio is a constant there rather than a measurement.")

    print(f"\n  MATCHED-DENSITY FREEMAN (thinned to {target:.4%})")
    if lowered:
        print(f"  target lowered from {lowered[0]:.0%}: the comparison log's own "
              f"median density is {lowered[1]:.4%}, and thinning cannot raise a "
              f"density, so {lowered[0]:.0%} would have left that side untouched.")
    for _p, _k, _d in tgt_excluded:
        print(f"  NOT used to set the target: {_p} (median density {_d:.4%}) "
              f"pools {_k} colonies, which divides its density by roughly {_k}. "
              "It would have won the minimum every time and thinned the ants to "
              "a density no colony has.")
    for c in rep["colonies"]:
        print(f"  colony {str(c['behavior_colony']):>3}: Freeman "
              f"{fmt(c['matched_freeman'])} at achieved density "
              f"{fmt(c['matched_density'])}, isolates "
              f"{fmt(c['matched_isolate_frac'])}")

    print("\n  THRESHOLD SWEEP (median over days; keep only the heaviest edges)")
    print("  the 25% row is roughly the density the SI says the PUBLISHED networks")
    print("  were thinned to, so it is the row that matches the paper's own analysis")
    print(f"  {'col':>4} {'keep':>6} {'density':>22} {'Freeman':>22} "
          f"{'Freeman/ceiling':>22}")
    for c in rep["colonies"]:
        for tag, s in c["sweep_median"].items():
            print(f"  {str(c['behavior_colony']):>4} {tag:>6} "
                  f"{fmt(s['density']):>22} {fmt(s['freeman']):>22} "
                  f"{fmt(s['freeman_of_ceiling']):>22}")

    print("\n  BY PERIOD (Freeman, median over the days in the period)")
    for c in rep["colonies"]:
        cells = "  ".join(
            f"p{p + 1}={v['freeman']['median']:.4f}"
            for p, v in sorted(c["by_period"].items()) if v.get("freeman"))
        print(f"  colony {c['behavior_colony']} ({c['matrix']}): {cells}")

    print("\n  " + rep["headline"])

    rep["compare"] = []
    for _path in (a.compare or []):
        cmp_ = analyse_compare(Path(_path), target)
        rep["compare"].append(cmp_)
        if cmp_:
            mm = [c["matched_freeman"]["median"] for c in rep["colonies"]
                  if c.get("matched_freeman")]
            print(f"\n  COMPARISON LOG: {cmp_['source']}  ({cmp_['n_bins']} bins)")
            print(f"    WINDOW: {cmp_['window']}")
            print(f"    nodes/bin        {fmt(cmp_['nodes'])}")
            print(f"    density          {fmt(cmp_['density'])}")
            print(f"    Freeman          {fmt(cmp_['freeman'])}")
            print(f"    Gini(strength)   {fmt(cmp_['gini_strength'])}")
            print(f"    saturated bins   {cmp_['dmax_saturated_bins']} of "
                  f"{cmp_['n_bins']}")
            print(f"    MATCHED Freeman  {fmt(cmp_['matched_freeman'])} at "
                  f"achieved density {fmt(cmp_['matched_density'])}")
            h = cmp_.get("hub") or {}
            if h.get("most_frequent") is not None:
                # The worry is that Freeman, which sees the data only through
                # dmax, is really reporting one marked animal. That worry is
                # only earned if a marked animal holds the maximum in MOST
                # bins. An earlier version raised it whenever the modal top
                # node happened to be marked at all -- and printed "largely a
                # readout of one animal's biology" over a node that led 1 bin
                # in 3, which is what a top node does by chance when no one
                # dominates. Scale the sentence to the fraction, and let the
                # unremarkable case read as unremarkable.
                nb = h.get("of_bins") or 0
                sb = h.get("special_held_bins") or 0
                frac = (sb / nb) if nb else 0.0
                tag = ""
                if h.get("n_special_marked") and frac >= 0.5:
                    tag = (f" -- and a marked individual holds it in {sb} of "
                           f"{nb} bins ({frac:.0%}), so Freeman here is "
                           "substantially a readout of one animal's biology. "
                           "Report it with and without.")
                elif h.get("n_special_marked") and sb:
                    tag = (f" -- a marked individual holds the maximum in {sb} "
                           f"of {nb} bins ({frac:.0%}); too few to call Freeman "
                           "a readout of that animal, but check it again if "
                           "more bins are added")
                elif h.get("n_special_marked"):
                    tag = (f" -- never one of the {h['n_special_marked']} marked "
                           "special node(s) in any bin, which is the reassuring "
                           "answer")
                print(f"    TOP NODE         {h['most_frequent']} holds the maximum "
                      f"degree in {h['bins_held']} of {h['of_bins']} bins{tag}")

            # Three conditions, reported separately rather than OR-ed into one
            # verdict, because which one fails determines what to do about it.
            fails = []
            if cmp_.get("pooled_trials"):
                pt = cmp_["pooled_trials"]
                print(f"\n    POOLED: this log holds {len(pt)} colonies in one "
                      f"matrix ({', '.join(pt)}). They are disjoint components, "
                      "so density and Freeman above are both divided by roughly "
                      f"{len(pt)} and describe no colony that exists. Regenerate "
                      "with --trial, one run per colony.")
                fails.append(f"POOLING: {len(pt)} colonies in one graph "
                             "-- rerun the loader with --trial")
            bh_ = cmp_.get("bin_hours")
            if bh_ not in (24, 24.0):
                fails.append(
                    ("WINDOW: bin width is not recorded in the log's meta.json, so "
                     "it cannot be shown to match a 24 h Mersch row"
                     if bh_ is None else
                     f"WINDOW: bins are {bh_} h, not 24 h")
                    + " -- regenerate the log with --bin-hours 24")
            ad = [c["matched_density"]["median"] for c in rep["colonies"]
                  if c.get("matched_density")]
            acmp = (cmp_["matched_density"] or {}).get("median")
            if ad and acmp:
                gap = max(abs(x - acmp) / max(x, acmp) for x in ad)
                if gap > 0.10:
                    fails.append(f"DENSITY: achieved densities still differ by up to "
                                 f"{gap:.0%} after thinning -- Mersch "
                                 f"{min(ad):.4%} to {max(ad):.4%}, log {acmp:.4%}")
            iso_m = max((c["matched_isolate_frac"]["median"] for c in rep["colonies"]
                         if c.get("matched_isolate_frac")), default=0.0)
            iso_c = ((cmp_.get("matched_isolate_frac") or {}).get("median") or 0.0)
            if max(iso_m, iso_c) > 0.20:
                fails.append(f"FRAGMENTATION: thinning to this density leaves "
                             f"{iso_m:.0%} of Mersch ants and {iso_c:.0%} of log "
                             "individuals with no edges at all, so Freeman is "
                             "measuring one node against a field of isolates")
            nm = [c["nodes"] for c in rep["colonies"]]
            nc = (cmp_["nodes"] or {}).get("median")
            if nm and nc:
                print(f"\n    SCALE: {min(nm)}-{max(nm)} individuals against "
                      f"{nc:.0f}. Freeman is normalised by (n-1)(n-2) but the "
                      "achievable density is not scale-free -- a bee cannot meet "
                      "2000 nestmates in a day -- so treat n as part of the "
                      "comparison, not as controlled for.")
            if fails or not (mm and cmp_.get("matched_freeman")):
                print("\n    NO SIDE-BY-SIDE FIGURE. These two are not yet on a "
                      "common footing:")
                for f_ in fails:
                    print(f"      - {f_}")
                print("    Do not quote a Mersch Freeman beside a log Freeman until "
                      "every line above is cleared.")
            else:
                print(f"\n    SIDE BY SIDE at {acmp:.4%} density -- "
                      f"Mersch colony medians {min(mm):.4f} to {max(mm):.4f}, "
                      f"comparison log {cmp_['matched_freeman']['median']:.4f}.")
                print("    Window, density and connectivity all check out, so this "
                      "is the pair to quote.")
            print("\n    " + cmp_["roster_caveat"])
        else:
            print(f"\n  COMPARISON LOG: nothing readable at {_path}")

    # Gini of strength needs no thinning, no matching and no ceiling, and for one
    # run this looked like the panel that survives every objection the Freeman
    # comparison keeps failing. It does not, and the reason is worth printing
    # rather than hiding: Gini has a chance baseline that DEPENDS ON SCALE. With
    # few events per individual, counting noise alone concentrates strength. The
    # bee bins have ~1000 individuals sharing a few thousand food-sharing events;
    # the ant days have ~130 sharing tens of thousands of contacts. So the two
    # sides do not share a zero point, and equal raw Gini does NOT mean equal
    # inequality -- it means the denser, better-sampled side is further above its
    # own baseline.
    #
    # CORRECTION. An earlier version of this block ended "Report the excess, and
    # show the level only beside its null", and printed an EXCESS column as the
    # one to read. That was wrong and the wrongness is measurable: see
    # gini_null.bias_table(), where subtraction is the worst of four candidates
    # at fixed true inequality, because true inequality and counting noise
    # combine sub-additively. The panel below is therefore diagnostic only -- it
    # shows WHY the raw levels cannot be paired -- and the quotable comparison is
    # the matched-intensity table that follows it.
    good = [c for c in (rep["compare"] or [])
            if c and c.get("gini_strength") and not c.get("pooled_trials")]
    if good:
        def _band(cs, key):
            v = [c[key]["median"] for c in cs
                 if c.get(key) and c[key].get("median") is not None]
            return (min(v), max(v)) if v else None

        mers = [c for c in rep["colonies"] if c.get("gini_strength")]
        print("\n  GINI OF STRENGTH ON THE RAW NETWORKS -- DIAGNOSTIC, NOT A "
              "COMPARISON")
        print(f"    {'':<8} {'colonies':>8} {'events/ind':>12} {'observed':>17} "
              f"{'chance':>17}")
        for label, cs in (("Mersch", mers), ("logs", good)):
            ob, nu = _band(cs, "gini_strength"), _band(cs, "gini_strength_null")
            evb = _band(cs, "epi")
            ev = f"{evb[0]:,.0f}-{evb[1]:,.0f}" if evb else "n/a"
            f2 = lambda b: f"{b[0]:.4f} to {b[1]:.4f}" if b else "n/a"
            print(f"    {label:<8} {len(cs):>8} {ev:>12} {f2(ob):>17} "
                  f"{f2(nu):>17}")
        nm, nc = _band(mers, "gini_strength_null"), _band(good, "gini_strength_null")
        if nm and nc:
            print(f"\n    The two chance baselines are {f2(nm)} and {f2(nc)}. They "
                  "differ because\n    events per individual differ, and that is a "
                  "property of the recording setup,\n    not of the animals. Neither "
                  "column above is a like-for-like pair, however\n    similar the two "
                  "observed ranges look. Read the matched table below instead.")
        if len(good) < 3:
            print(f"    Only {len(good)} log colony(ies). A range needs more than one "
                  "number, and the ant side has six -- run the remaining trials "
                  "before reading any overlap or gap as a result.")
        print("    Weights are interaction counts on both sides, but they count "
              "DIFFERENT behaviours -- any antennal contact for Mersch, food "
              "sharing for Gernat -- so a similar Gini means similar inequality "
              "of effort, not similar behaviour.")

    mi = matched_intensity(rep)
    rep["matched_intensity"] = mi
    print_matched_intensity(mi)

    # The per-bin graphs were carried only so both sides could be thinned against
    # one target. They are large and not serialisable; drop them before writing.
    for c in (rep.get("colonies") or []):
        c.pop("_bins", None)
    for c in (rep.get("compare") or []):
        if c:
            c.pop("_bins", None)

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"\n  written: {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
