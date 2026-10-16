"""Structure instruments for a real interaction log.

Mirrors `orglib/measure.py` so the numbers are directly comparable to the
synthetic organizations, and adds the two things a real biological trace needs
that a designed org does not.

1.  **A null model for centralization.** In a designed hierarchy, a high Freeman
    centralization means a hierarchy. In a real colony it might just mean that
    some bees are more active than others. So centralization is reported against
    a degree-preserving rewiring null: if the observed value sits inside the null
    band, the apparent centralization is a by-product of the activity
    distribution, not evidence of structure.

2.  **Hub stability.** A single top-in-degree list is nearly meaningless on its
    own -- somebody always ranks first. The question that matters for the
    organizational analogy is whether the SAME individuals stay central across
    time. Stable hubs without any assignment mechanism is exactly the
    "role differentiation without role assignment" claim, and it is measurable
    here as rank overlap between time windows against a chance baseline.

3.  **A population that moves.** Every Mersch colony ends the record smaller than
    it started. Pooling 41 days into one graph makes `n` the union of everyone who
    ever lived, and a dead ant is a zero-degree node that adds a full `dmax` to
    the centralization numerator -- so attrition raises the pooled score with no
    individual becoming more central. `node_census` exposes the per-bin count and
    `centralization_by_bin` computes the score on the animals actually present.
    The same correction applies to the hub-stability chance baseline, which draws
    from the living and not from the union.

4.  **Self-interaction.** `degree_centralization` always skipped `a == b`;
    `emergent_hubs` did not, so a non-zero matrix diagonal -- present in 15 of the
    246 Mersch matrices -- could promote an ant into the top-k on the strength of
    interacting with itself. Both now agree, and the count is reported rather than
    silently absorbed.

Read the results the right way. Bees have no reporting lines. Recovering a
crisp hierarchy would mean the instrument is hallucinating structure, which is
a finding about the instrument. The expected result is LOW centralization with
STABLE hubs, and that combination -- decentralized yet differentiated -- is
precisely the regime the organizational literature finds hardest to design.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict


# ------------------------------------------------------------------- basics
def comm_graph(log, mtypes=("report",)) -> dict:
    w = defaultdict(int)
    for m in log:
        if m["mtype"] in mtypes:
            w[(m["sender"], m["recipient"])] += 1
    return w


def degree_centralization(log) -> float:
    """Freeman degree centralization, 0 (flat) to ~1 (star). Same as measure.py."""
    deg = defaultdict(set)
    nodes = set()
    for m in log:
        a, b = m["sender"], m["recipient"]
        nodes.add(a)
        nodes.add(b)
        if a != b:
            deg[a].add(b)
            deg[b].add(a)
    n = len(nodes)
    if n < 3:
        return 0.0
    degrees = {x: len(deg[x]) for x in nodes}
    dmax = max(degrees.values())
    num = sum(dmax - d for d in degrees.values())
    denom = (n - 1) * (n - 2)
    return num / denom if denom else 0.0


def count_self_loops(log) -> int:
    return sum(1 for m in log if m["sender"] == m["recipient"])


def emergent_hubs(log, k=None, drop_self: bool = True):
    """Rank individuals by in-degree, ignoring self-interaction by default.

    `degree_centralization` has always skipped `a == b`, because a self-loop adds
    nothing to a neighbour set. This function did not, and that asymmetry is the
    bug: 15 of the 246 Mersch matrices carry a non-zero diagonal, so a handful of
    ants arrived here with an extra in-degree that no other ant received. It does
    not cancel out -- it differs per individual, which is precisely what a ranking
    is sensitive to. An ant can be promoted into the top-k, and thereby into the
    persistent-hub set, on the strength of interacting with itself.

    `drop_self=False` restores the old behaviour for anyone who wants it; nothing
    in this repo asks for it, and `structure_report` reports the count either way
    so the decision is never invisible.
    """
    indeg = Counter()
    for m in log:
        if m["mtype"] != "report":
            continue
        if drop_self and m["sender"] == m["recipient"]:
            continue
        indeg[m["recipient"]] += 1
    ranked = indeg.most_common()
    return ranked if k is None else ranked[:k]


# --------------------------------------------------------------- null model
def _edge_list(log):
    return [(m["sender"], m["recipient"]) for m in log]


def centralization_null(log, n_perm: int = 30, seed: int = 0) -> tuple[float, float]:
    """Shuffle recipients while preserving each node's out-activity.

    This keeps the fact that some individuals interact far more than others and
    destroys only WHO they interact with. It is the right null for the question
    'is this network centralized beyond what activity heterogeneity implies'.
    """
    rng = random.Random(seed)
    edges = _edge_list(log)
    if len(edges) < 10:
        return float("nan"), float("nan")
    senders = [a for a, _ in edges]
    recips = [b for _, b in edges]
    vals = []
    for _ in range(n_perm):
        rng.shuffle(recips)
        fake = [{"sender": a, "recipient": b, "mtype": "report"}
                for a, b in zip(senders, recips) if a != b]
        vals.append(degree_centralization(fake))
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1))
    return m, sd


# ------------------------------------------------------------ hub stability
def hub_stability(log, k: int = 10) -> dict:
    """Jaccard overlap of the top-k in-degree set between consecutive time bins."""
    bins: dict[int, list] = defaultdict(list)
    for m in log:
        bins[int(m.get("tbin", 0))].append(m)
    keys = sorted(bins)
    if len(keys) < 2:
        return dict(error="log has a single time bin; re-run the loader with --bins")
    tops = []
    for t in keys:
        tops.append({n for n, _ in emergent_hubs(bins[t], k)})
    overlaps = []
    for s1, s2 in zip(tops, tops[1:]):
        union = s1 | s2
        overlaps.append(len(s1 & s2) / len(union) if union else 0.0)
    nodes = {m["sender"] for m in log} | {m["recipient"] for m in log}
    # Chance Jaccard for two independent k-subsets of n nodes. `n` is the mean
    # number of individuals present per bin, NOT the union across all bins. Two
    # top-k lists are drawn from the animals alive at the time, and in a colony
    # that loses a third of its workers the union is much larger than the pool
    # either draw came from. Using the union deflates the chance baseline, which
    # makes hub persistence look more impressive than it is -- and hub persistence
    # is the finding this file exists to support, so it is exactly the number that
    # must not be flattered.
    per_bin = [len({m["sender"] for m in bins[t]} | {m["recipient"] for m in bins[t]})
               for t in keys]
    n = sum(per_bin) / len(per_bin) if per_bin else len(nodes)
    chance = (k * k / n) / (2 * k - k * k / n) if n > k else 1.0
    persistent = Counter()
    for s in tops:
        for x in s:
            persistent[x] += 1
    core = [x for x, c in persistent.items() if c >= 0.8 * len(tops)]
    return dict(
        k=k, n_bins=len(keys), n_nodes=len(nodes), n_nodes_per_bin_mean=round(n, 1),
        jaccard_consecutive=[round(o, 4) for o in overlaps],
        jaccard_mean=round(sum(overlaps) / len(overlaps), 4),
        jaccard_chance=round(chance, 4),
        persistent_hub_count=len(core),
        persistent_hubs=sorted(core)[:20],
        note=("persistent hubs are individuals in the top-k for at least 80% of time "
              "bins. If that count is well above chance, the colony has stable "
              "central individuals that nobody appointed."),
    )


# --------------------------------------------------------- moving population
def node_census(log) -> dict:
    """How many individuals are actually present in each time bin.

    Every one of the six Mersch colonies ends the record with fewer ants than it
    starts with. That makes the population an independent variable, not a
    constant, and two things downstream care.

    Freeman centralization divides by (n-1)(n-2), where n is the number of nodes
    in the graph. Pool 41 days into one graph and n is the UNION -- every ant that
    ever lived, including the ones that are dead by the end. A dead ant is a
    zero-degree node, and each one contributes a full `dmax` to the numerator
    sum(dmax - d). So attrition raises the pooled centralization on its own,
    without any individual becoming more central than any other. The colony looks
    like it is centralizing as it dies.

    Anything per-capita has the same problem in reverse: a rate computed against
    the starting n falls as the colony shrinks, whether or not the behaviour did.
    """
    bins: dict[int, set] = defaultdict(set)
    for m in log:
        t = int(m.get("tbin", 0))
        bins[t].add(m["sender"])
        bins[t].add(m["recipient"])
    keys = sorted(bins)
    sizes = [len(bins[t]) for t in keys]
    union = set().union(*bins.values()) if bins else set()
    out = dict(
        n_bins=len(keys),
        # A LIST of {tbin, n}, not a dict keyed by bin. `structure_report` is
        # serialized to JSON by run_real_bench, and JSON keys are strings: a
        # bin-keyed dict comes back ordered "0", "1", "10", "2", so the first and
        # last entries -- the two the shrinkage figure is computed from -- are
        # silently the wrong bins. A list carries its order through.
        n_by_bin=[{"tbin": t, "n": len(bins[t])} for t in keys],
        n_union=len(union),
        n_first=sizes[0] if sizes else 0,
        n_last=sizes[-1] if sizes else 0,
    )
    if sizes and sizes[0]:
        out["shrinkage"] = round((sizes[0] - sizes[-1]) / sizes[0], 4)
    return out


def centralization_by_bin(log) -> dict:
    """Centralization computed within each bin, on the nodes present in that bin.

    This is the number to quote when the population moves. The pooled figure
    answers a question about the union of everyone who ever lived; this one
    answers it about the colony as it stood on a given day.
    """
    bins: dict[int, list] = defaultdict(list)
    for m in log:
        bins[int(m.get("tbin", 0))].append(m)
    keys = sorted(bins)
    vals = [degree_centralization(bins[t]) for t in keys]
    if not vals:
        return dict(n_bins=0)
    mean = sum(vals) / len(vals)
    return dict(
        n_bins=len(keys),
        by_bin=[round(v, 4) for v in vals],
        mean=round(mean, 4),
        first=round(vals[0], 4),
        last=round(vals[-1], 4),
    )


def special_nodes_report(log, special: dict, k: int = 10, n_perm: int = 30,
                         seed: int = 0) -> dict:
    """What does the network look like without the individuals we already knew were special?

    Gernat's `bees.csv` marks 3 queens among 2,777 bees. A queen in a
    trophallaxis network is fed continuously by her retinue, so she is a hub by
    caste, not by anything the colony organised. Leave her in and "this colony
    has stable central individuals" can be a restatement of "this colony has a
    queen" -- the same shape as every other finding-by-construction this repo
    keeps catching, except that here the confound has a name in the deposit and
    could have been checked from the start.

    The answer is not to drop her. Dropping her silently would be its own
    unrecorded decision, and how much of the structure rests on three animals is
    a quantity worth having. So both numbers are computed and the DIFFERENCE is
    the output: if removing three of nine hundred nodes moves centralization
    materially, centralization was substantially about those three.

    Removing the node removes her incident edges too, which lowers her retinue's
    degree as well. That is the intended counterfactual -- the worker-worker
    network -- not a side effect.
    """
    marked = {n for n in special if n}
    nodes_in = {m["sender"] for m in log} | {m["recipient"] for m in log}
    present = nodes_in & marked
    out = dict(
        labels={n: special[n] for n in sorted(present)},
        n_marked=len(marked),
        n_present=len(present),
    )
    if not marked:
        return out
    if not present:
        # A join that matches nothing is the failure this whole report is
        # supposed to prevent, wearing a disguise: every number below would be
        # computed correctly on a mark that landed on nobody, and the run would
        # look like a clean negative result.
        out["join_failed"] = (
            f"{len(marked)} individual(s) were marked special, and NONE of them "
            f"appear in the log. The id spaces do not match -- check the "
            f"namespacing (trial:id vs id) before reading anything below as "
            f"'the queens made no difference'.")
        return out

    ranked = emergent_hubs(log, k=None)
    rank_of = {n: i + 1 for i, (n, _) in enumerate(ranked)}
    n_nodes = len(ranked)
    out["ranks"] = {n: dict(rank=rank_of.get(n), of=n_nodes,
                            percentile=(round(100 * (1 - (rank_of[n] - 1) / n_nodes), 1)
                                        if n in rank_of else None),
                            in_degree=dict(ranked).get(n, 0))
                    for n in sorted(present)}
    out["in_top_k"] = sorted(n for n, _ in ranked[:k] if n in present)

    without = [m for m in log
               if m["sender"] not in present and m["recipient"] not in present]
    if not without:
        out["note"] = "removing the marked individuals empties the log"
        return out

    cen_with = degree_centralization(log)
    cen_without = degree_centralization(without)
    out["centralization_with"] = round(cen_with, 4)
    out["centralization_without"] = round(cen_without, 4)
    out["delta"] = round(cen_without - cen_with, 4)
    out["messages_removed"] = len(log) - len(without)
    out["share_of_messages"] = round(len(out["labels"]) and
                                     (len(log) - len(without)) / len(log), 4)
    out["top_hubs_without"] = [(n, c) for n, c in emergent_hubs(without, k)]

    # Removing ANY node moves centralization, because it removes that node's
    # edges and shrinks the normalisation. So a delta on its own says nothing:
    # measured on a 61-node fixture where the marked bee behaves exactly like a
    # worker, removing her still moved centralization by 14% of it -- comfortably
    # past a 5% threshold, and entirely a property of the operation rather than
    # of the bee. The comparison that has any content is against removing the
    # same NUMBER of arbitrary individuals.
    rng = random.Random(seed)
    others = sorted(nodes_in - present)
    n_drop = min(len(present), len(others))
    null: list[float] = []
    for _ in range(max(0, n_perm) if others else 0):
        drop = set(rng.sample(others, n_drop))
        w = [m for m in log
             if m["sender"] not in drop and m["recipient"] not in drop]
        if w:
            null.append(degree_centralization(w) - cen_with)
    if null:
        null.sort()
        out["delta_null_median"] = round(null[len(null) // 2], 4)
        out["delta_null_range"] = [round(null[0], 4), round(null[-1], 4)]
        out["n_null_draws"] = len(null)
        unusual = not (null[0] <= (cen_without - cen_with) <= null[-1])
    else:
        out["delta_null_median"] = out["delta_null_range"] = None
        out["n_null_draws"] = 0
        unusual = True                 # nothing to compare against; do not soothe

    # The magnitude threshold is deliberately low. This is not a significance
    # test; it is a prompt to report both numbers rather than one. It has to be
    # cleared TOGETHER with the null, so that "she matters" cannot be satisfied
    # by an effect that removing anybody would have produced.
    material = bool(cen_with) and abs(out["delta"]) / max(cen_with, 1e-9) > 0.05
    if material and unusual:
        out["note"] = (
            f"removing {len(present)} of {n_nodes} individuals moves "
            f"centralization from {cen_with:.4f} to {cen_without:.4f} "
            f"({out['delta']:+.4f}), outside the range removing {n_drop} "
            f"arbitrary individuals produces ({out.get('delta_null_range')}). "
            f"They carry {out['share_of_messages']:.1%} of all messages. Quote "
            f"both figures and say which population each describes; a single "
            f"number here is a claim about the colony that is partly a claim "
            f"about its caste structure.")
    else:
        why = ("under 5% of it" if not material else
               f"inside the range removing {n_drop} arbitrary individuals "
               f"produces ({out.get('delta_null_range')}), so it is a property "
               f"of dropping nodes and not of these nodes")
        out["note"] = (
            f"removing {len(present)} of {n_nodes} individuals moves "
            f"centralization by {out['delta']:+.4f}, which is {why}. The "
            f"structure does not rest on them -- which is itself the result, and "
            f"is only sayable because it was checked.")
    return out


def partner_narrowing(log, seed: int = 0) -> dict:
    """Observed repetition against the repetition the NULL ITSELF produces.

    `events_per_unique_pair` on its own is unreadable, because the number it
    should be compared against is not 1.0. Shuffling recipients does not hand
    every event a fresh partner: with n individuals and E events some of the
    reassigned events land on a partner that individual already has, so the null
    graph has repetition of its own. How much depends on n and on how many events
    the busiest individuals have -- it is a coupon-collector quantity, not a
    constant. The null's own figure is the reference, and this function measures
    it by doing exactly what the null does, once, with the null's seed.

        narrowing = events_per_unique_pair / events_per_unique_pair_null

    narrowing == 1 means the observed partner sets are exactly as wide as a
    random re-assignment of the same event counts would make them. Above 1 means
    they are narrower, and that is what drives the z negative: the shuffle widens
    them, which raises dmax, which makes the NULL the centralized one.

    This is why the real colonies read the way they do. An
    events_per_unique_pair of 1.2 looks like almost no repetition, and against a
    reference of 1.0 it would be. But at n ~ 900 a random re-assignment produces
    about 1.04, so 1.2 is nearly twenty per cent narrower than chance, and the
    null's spread across permutations is small enough that twenty per cent is
    worth a z of -18.

    Measured across synthetics -- 900 individuals, lognormal activity, partner
    sets built to a fixed repetition factor:

        narrowing   0.96    1.91    3.74
        z          +22     -23     -20

    The sign is predicted by narrowing in every fixture except the two that
    contain a genuine hub, where the hub dominates and the z goes positive
    regardless. That is the asymmetry the z_note bands already state: the
    positive direction is a finding, the negative direction is this.
    """
    edges = _edge_list(log)
    obs = [(a, b) for a, b in edges if a != b]
    if len(obs) < 10:
        return {"events_per_unique_pair_null": None, "narrowing": None,
                "why": "fewer than 10 off-diagonal events; not estimable"}
    o_pairs = {frozenset((a, b)) for a, b in obs}
    o_epup = len(obs) / len(o_pairs)
    rng = random.Random(seed)
    recips = [b for _, b in edges]
    rng.shuffle(recips)
    fake = [(a, b) for (a, _), b in zip(edges, recips) if a != b]
    if not fake:
        return {"events_per_unique_pair_null": None, "narrowing": None,
                "why": "the shuffle left no off-diagonal events"}
    n_epup = len(fake) / len({frozenset((a, b)) for a, b in fake})
    return {"events_per_unique_pair_null": round(n_epup, 3),
            "narrowing": round(o_epup / n_epup, 3) if n_epup else None}


def structure_report(log, k: int = 10, n_perm: int = 30, seed: int = 0,
                     special: dict | None = None) -> dict:
    cen = degree_centralization(log)
    null_m, null_sd = centralization_null(log, n_perm, seed)
    z = (cen - null_m) / null_sd if null_sd and null_sd > 0 else float("nan")
    nodes = {m["sender"] for m in log} | {m["recipient"] for m in log}
    pairs = {(m["sender"], m["recipient"]) for m in log
             if m["sender"] != m["recipient"]}
    repeat = len(log) / len(pairs) if pairs else float("nan")
    census = node_census(log)
    within = centralization_by_bin(log) if census["n_bins"] > 1 else {}
    n_self = count_self_loops(log)

    out = dict(
        n_individuals=len(nodes),
        n_messages=len(log),
        centralization=round(cen, 4),
        centralization_null_mean=round(null_m, 4) if math.isfinite(null_m) else None,
        centralization_z=round(z, 2) if math.isfinite(z) else None,
        centralization_within_bin=within or None,
        unique_pairs=len(pairs),
        events_per_unique_pair=round(repeat, 2) if math.isfinite(repeat) else None,
        partner_narrowing=partner_narrowing(log, seed=seed),
        census=census,
        n_self_loops=n_self,
        top_hubs=[(n, c) for n, c in emergent_hubs(log, k)],
        stability=hub_stability(log, k),
        reference=("Synthetic range from the bench: flat designs sit near the low end, "
                   "a centralized hierarchy near the high end. A colony scoring at the "
                   "flat end is the expected -- and interesting -- result."),
    )
    # What the z actually compares, and why it is not a test for "is there a hub".
    #
    # `degree_centralization` counts DISTINCT partners. `centralization_null`
    # shuffles the recipient column. That shuffle preserves the recipient
    # MULTISET, so it does not touch a high-volume receiver at all: an individual
    # who is on the receiving end of half the colony's events still receives half
    # of them after the shuffle, now from senders drawn at random, and so still
    # touches everybody. What the shuffle rewires is everyone ELSE -- an ordinary
    # bee's events, which in life go to the same handful of nestmates over and
    # over, are scattered across the whole colony.
    #
    # Measured directly, on a 300-node hard star, hub and median degree observed
    # then in one null draw:
    #
    #     narrow partner sets  hub 299 / median 38   ->  null hub 299 / median 86
    #     wide partner sets    hub 299 / median 86   ->  null hub 299 / median 85
    #
    # The hub survives the null intact both times. The gap between hub and median
    # closes only because the median rises. So the z is not measuring the hub's
    # prominence; it is measuring how much NARROWER the ordinary individuals'
    # partner sets are than their event volume alone would imply.
    #
    # That single mechanism produces both of the ways this statistic misleads,
    # measured on synthetic networks of 300 nodes and 30,000 events:
    #
    #     partners each      5      20      60     150     299
    #     no hub at all   -7.4   -15.8    -3.6    -0.4    +0.4
    #     hard star      +201.3  +187.4   +59.7    +0.2    -0.7
    #
    # Top row: nothing whatever is centralized, and the z reads as low as -16.
    # Bottom row: a hard star, centralization 0.72, and the z reads -0.7 -- the
    # hub is in the null too, so there is nothing left to detect. A large
    # negative z is not evidence of flatness and a z near zero is not evidence of
    # no hub.
    #
    # A CORRECTION, TWICE OVER, and the reason `partner_narrowing` exists.
    #
    # The first version of this note told the reader a negative z meant "contacts
    # repeat" and pointed at events_per_unique_pair. It shipped in three releases,
    # and on the real Gernat colonies it asserted that explanation beside an
    # events_per_unique_pair of 1.2 -- a value which, by the table above, should
    # give a z near zero rather than -18.7. A note contradicted by the number
    # printed next to it is worse than no note at all.
    #
    # The second version blamed the EXPONENT relating partner count to event
    # count, on the theory that the null inflates the busiest individuals most. It
    # was written, and then killed by its own fixture before it shipped: a
    # synthetic in which every individual repeats by exactly the same factor --
    # exponent 1.0 by construction, fitted at 0.98 -- scores z of -23 at a
    # repetition of 2.0. The exponent was not the mechanism. It had merely been
    # correlated with it in the first set of synthetics, because those built
    # partner sets as a power of activity and so moved repetition and exponent
    # together.
    #
    # What was wrong in both attempts is the reference point, not the statistic.
    # events_per_unique_pair was being read against 1.0, and 1.0 is not what the
    # null produces. Shuffling recipients does not give every event a fresh
    # partner: some reassigned events land on a partner that individual already
    # has, so the null graph repeats too, by an amount that depends on n and on
    # the event counts -- a coupon-collector quantity. Uniform repetition of
    # factor r divides every degree by r, which divides centralization by r; the
    # observation is compressed by the repetition it has, the null by the
    # repetition IT has, and the z is the difference. So the question is not "do
    # contacts repeat" but "do they repeat MORE than a random re-assignment of the
    # same event counts would repeat" -- which is `partner_narrowing.narrowing`,
    # and which is why an events_per_unique_pair of 1.2 can be a large effect: at
    # n ~ 900 the null's own figure is about 1.04.
    #
    # Only the positive direction carries information. The number to quote is
    # `centralization` against the synthetic bench range.
    nr = out["partner_narrowing"].get("narrowing")
    out["null_definition"] = (
        "recipients shuffled, event counts per individual preserved. It leaves a "
        "high-volume receiver a hub in the null too, and it does NOT give every "
        "event a fresh partner -- the null graph has repetition of its own. So z "
        "asks 'are partner sets narrower than a random re-assignment of the same "
        "event counts would make them', not 'is there a hub' -- see "
        "partner_narrowing.")
    if math.isfinite(z):
        if z < -2:
            # The explanation names the RATIO, not events_per_unique_pair itself
            # and not a fitted exponent. Both of those have already been shipped
            # or drafted as the explanation here and both were wrong; the ratio is
            # the one that tracks the sign across every fixture in
            # test_null_calibration that does not contain a hub.
            n0 = out["partner_narrowing"].get("events_per_unique_pair_null")
            if nr is not None and nr > 1.05:
                why = (f"partner sets are {nr:.2f}x narrower than chance -- "
                       f"{out['events_per_unique_pair']} events per pair observed "
                       f"against {n0} for a random re-assignment of the same event "
                       f"counts, which is the reference, NOT 1.0 -- so the shuffle "
                       f"widens every partner set, raises dmax and makes the NULL "
                       f"the centralized one. A synthetic with no hub at all and a "
                       f"narrowing of 1.9 scores z of -23")
            elif nr is not None:
                why = (f"partner sets are {nr:.2f}x the width chance would give "
                       f"them, i.e. no narrower than the null's own repetition, so "
                       f"the usual explanation for a negative z does NOT apply "
                       f"here and this reading is not yet accounted for. Do not "
                       f"quote it either way until it is")
            else:
                why = ("the narrowing ratio could not be computed on this log, so "
                       "there is nothing to attribute this to yet")
            out["z_note"] = (
                f"z is {z:.1f}, i.e. BELOW the null. {why}. Read this as a "
                f"property of the null, not as 'flatter than chance', and quote "
                f"centralization={cen:.4f} against the bench range rather than "
                f"the z.")
        elif z <= 2:
            out["z_note"] = (
                f"z is {z:.1f}, indistinguishable from the null. This is NOT "
                f"evidence that there is no hub. Because the shuffle preserves "
                f"who receives how much, an individual who dominates by volume "
                f"alone dominates the null as well: a synthetic hard star with "
                f"centralization 0.72 scores z of -0.7. Read centralization "
                f"({cen:.4f}) and the top_hubs list, not the z.")
        else:
            out["z_note"] = (
                f"z is +{z:.1f}, i.e. ABOVE the null -- the one direction that "
                f"carries information here. Contact is concentrated on a few "
                f"individuals BEYOND what their event volume alone would produce, "
                f"and it has to be, because the shuffle carries a volume hub into "
                f"the null intact and still could not reach this. That is a claim "
                f"about the shape of the network, not about any named individual. "
                f"Quote it with centralization={cen:.4f}.")
    if n_self:
        out["self_loop_note"] = (
            f"{n_self} record(s) have sender == recipient. They are excluded from the "
            f"hub ranking and from degree, because a self-loop inflates one "
            f"individual's degree by an amount that differs per individual and so "
            f"re-ranks rather than cancels. Drop them in the loader if they are not "
            f"meant to be there.")
    if census.get("shrinkage", 0) > 0.05:
        out["denominator_note"] = (
            f"the population falls {census['shrinkage']:.1%} across the record "
            f"({census['n_first']} -> {census['n_last']}), and the pooled graph "
            f"carries all {census['n_union']} individuals who ever appear. Dead "
            f"nodes are zero-degree nodes, and every one of them adds a full dmax "
            f"to the centralization numerator -- so the pooled figure of "
            f"{out['centralization']} is inflated by attrition alone. Quote "
            f"centralization_within_bin (mean "
            f"{within.get('mean')}) instead, or say which you mean.")
    if special:
        out["special_nodes"] = special_nodes_report(log, special, k, n_perm, seed)
    return out
