#!/usr/bin/env python3
"""Is `cleaner` the middle of an ordered sequence, and does the flow run one way?

WHAT PROMPTED THIS
------------------
`mersch_task_crosstab.py`, run on the real deposit 31 July, returned a pattern
too strong to leave at "cleaner is over-represented":

    cleaner -> forager   94  against a null of 26.1   (3.60x)
    nurse   -> cleaner   66                    39.2   (1.68x)
    forager -> cleaner   39                    21.6   (1.81x)
    cleaner -> nurse     21                    38.1   (0.55x)
    nurse   -> forager   14                    64.6   (0.22x)
    forager -> nurse      3                    47.4   (0.06x)

Two things are visible in that table and neither is what the cross-tab was built
to look for. First, the pair that almost never occurs is nurse <-> forager: 17 of
237 moves against 112 expected. Transitions are essentially confined to pairs
that include `cleaner`, which is what it looks like when three labels are not
three categories but three positions on one line, with `cleaner` in the middle.
Second, the flow is not symmetric: 174 of the 237 moves run nurse -> cleaner ->
forager and 63 run the other way. A boundary artefact -- an ant whose position
jitters across a cut in a continuous quantity -- produces the first of those and
gives no reason at all for the second.

WHAT THIS FILE MEASURES, AND WHY EACH PART CAN FAIL
---------------------------------------------------
**1. Which label is in the middle, recovered rather than assumed.** Three labels
admit three orderings, one per choice of middle, and each ordering makes a
different pair the "skip". The middle is whichever choice leaves fewest
transitions on its skip pair. This is reported with its margin over the runner-up
and it can come out any of three ways -- the answer that `cleaner` is the middle
is a finding here, not a premise, and the file is written so that it could have
said `nurse`.

**2. Whether the flow is directional.** Only once an order is recovered. "Forward"
is meaningless without one, so if the middle is not identified with a positive
margin this section refuses to print rather than defaulting to the ordering we
happen to expect.

Forward flow is scored against the same null the cross-tab uses: observed number
of changes per boundary, observed per-period label prevalences, and only the
question of which label lands on which end destroyed. That null already contains
any drift in the marginals -- if the colony's composition shifts towards foragers
over the 41 days, the null expects forward moves for that reason alone, and an
excess over it is an excess over composition change.

**3. Whether every colony says the same thing.** Six colonies. A pattern present
in one and absent in five is a colony, not a phenomenon, and pooling would hide
that. Colonies with too few moves to support a fraction are printed with their
counts and explicitly not scored.

**4. Whether the null's own marginals are doing the work.** The null draws label
prevalences over all scoreable ants, including the ones that never move. If
movers differ in composition from the population -- more cleaners among them for
some reason unrelated to ordering -- the excess would land on the pair structure.
So the MIDDLE is recomputed with prevalences taken over changers only, which is
the unfavourable choice, and both are printed.

The DIRECTION is not re-checked that way, and the first version of this file was
wrong to try. Prevalences taken over changers only cannot test a direction,
because a one-way flow is exactly what makes the movers nurse-heavy early and
forager-heavy late: that null has already absorbed the effect and can only report
it absent. It duly reported the `chain` fixture -- 24 forward moves against 4
backward, direction true by construction -- as not surviving, which is a broken
check and not a conservative one. The direction is instead checked against time
reversal: each ant's four labels reversed or not on a coin flip, which holds her
move count, her labels and her run structure fixed and destroys only which end
she started from. See `reversal_null`.

WHAT NONE OF THIS ESTABLISHES
-----------------------------
An ordered sequence with directional flow is what age polyethism looks like, and
that is the standard reading of this system. It is not what this file measures.
The deposit carries no age, so "workers mature from nursing through cleaning to
foraging" remains an interpretation laid over a direction, and it must be written
as one. What is measured is an order and a direction; the mechanism is not.

Nor does any of it rescue "the colony re-allocated 47% of its workforce". If the
moves are a one-way progression along a fixed sequence, the organizational claim
is about a maturation schedule and not about flexible re-allocation, and those
are different claims with different implications for the proposal.

EXIT CODES
----------
  0  the guard reproduced and the sections that could print, printed
  1  the guard did not reproduce, or the middle was not identified
  2  called wrong
"""
from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path

from mersch_task_crosstab import (EXPECT_CHANGED, EXPECT_COMPLETE,
                                  expected_pairs, find_behavior, partition,
                                  read_sequences, transitions)

# The reader, the partition and the null are imported rather than re-implemented.
# The independence that mattered was from `loaders/mersch.py`, and the cross-tab
# already established it by reproducing 183 of 386 from `behavior.csv` on a code
# path the loader does not touch. A second private copy of the same CSV reader
# would not add a second inference, it would add a second thing to keep in step.

MIN_MOVES = 20
"""Below this a per-colony fraction is printed as counts only.

Not a significance threshold and not presented as one. It is the point below
which a percentage misleads more than it informs: 4 of 5 moves reads as 80% and
is four moves.
"""


def skip_counts(pairs: Counter, labels: list[str]) -> dict[str, int]:
    """For each candidate middle, how many moves skip it.

    With labels {a, b, c}, choosing `b` as the middle makes a <-> c the skip
    pair. Counting the skip is the whole test: a genuine ordering shows up as
    one pair being far rarer than the other two, in both directions.
    """
    out = {}
    for mid in labels:
        ends = [x for x in labels if x != mid]
        out[mid] = sum(n for (i, j), n in pairs.items()
                       if {i, j} == set(ends))
    return out


def direction(pairs: Counter, order: list[str]) -> tuple[int, int]:
    """(forward, backward) along `order`, counting a skip as one step forward."""
    pos = {lab: k for k, lab in enumerate(order)}
    fwd = sum(n for (i, j), n in pairs.items() if pos[j] > pos[i])
    bwd = sum(n for (i, j), n in pairs.items() if pos[j] < pos[i])
    return fwd, bwd


def label_set(ants: list[dict]) -> list[str]:
    return sorted({lab for r in ants for lab in r["labels"]})


REVERSAL_DRAWS = 4000
REVERSAL_SEED = 20260731


def reversal_null(changers: list[dict], order: list[str],
                  draws: int = REVERSAL_DRAWS,
                  seed: int = REVERSAL_SEED) -> list[int]:
    """Imbalance under time reversal: each ant's sequence reversed or not, coin-flip.

    WHY THIS NULL AND NOT THE OTHER ONE, recorded because the other one shipped
    first and was wrong. The sensitivity originally re-drew the label
    prevalences over changers only, on the reasoning that movers might differ in
    composition from the population. That is a fair check on WHICH LABELS the
    moves involve. It is worthless as a check on DIRECTION, and worse than
    worthless: a directional flow is what makes the movers nurse-heavy early and
    forager-heavy late, so a null built on the movers' own per-period
    prevalences has already absorbed the effect and can only ever report it as
    absent. On the `chain` fixture -- built with 24 forward moves against 4
    backward, direction present by construction -- it duly reported the
    direction as not surviving. A check that fails on a fixture where the
    property is true by construction is not conservative, it is broken.

    What direction actually needs is a null that destroys the arrow of time and
    changes nothing else. Reversing an ant's four labels does exactly that: the
    number of moves she makes, the labels she holds, and the run structure of
    her record are all identical in the reversed sequence, and only which end
    she started from is gone. Flip each ant independently and the imbalance is a
    random-sign sum of the same per-ant displacements, centred on zero, with the
    right spread for this many ants making this many moves.

    Returns the absolute imbalance from each draw.
    """
    rng = random.Random(seed)
    pos = {lab: k for k, lab in enumerate(order)}
    # Each ant's net displacement and its reverse are fixed; only the sign is
    # drawn. Precomputing them makes the draws cheap and makes it obvious that
    # nothing else varies between them.
    nets = []
    for rec in changers:
        labs = rec["labels"]
        net = sum((1 if pos[labs[k + 1]] > pos[labs[k]] else -1)
                  for k in range(3) if labs[k] != labs[k + 1])
        nets.append(net)
    out = []
    for _ in range(draws):
        tot = 0
        for net in nets:
            tot += net if rng.random() < 0.5 else -net
        out.append(abs(tot))
    return out


def score(changers: list[dict], pool: list[dict], tag: str) -> dict:
    """Everything measurable about one population, against a null built on `pool`.

    `pool` is what the null's prevalences come from, and it is the knob the
    sensitivity turns: all scoreable ants (favourable) or changers only
    (unfavourable).
    """
    pairs, per_boundary = transitions(changers)
    exp = expected_pairs(pool, per_boundary)
    labels = label_set(pool)
    obs_skip = skip_counts(pairs, labels)
    exp_skip = {mid: sum(e for (i, j), e in exp.items()
                         if {i, j} == {x for x in labels if x != mid})
                for mid in labels}
    ranked = sorted(obs_skip.items(), key=lambda kv: kv[1])
    mid, best = ranked[0]
    margin = ranked[1][1] - best if len(ranked) > 1 else 0
    ends = [x for x in labels if x != mid]
    order = [ends[0], mid, ends[1]] if len(ends) == 2 else list(labels)

    # DEFECT, caught by the `chain` fixture, 31 July. The first version stopped
    # here and called this order "forward". `ends` comes out of a sorted label
    # list, so on the real vocabulary that made forward mean
    # forager -> cleaner -> nurse: the direction of the axis was being set by
    # the alphabet, which is a fact about English spelling. The fixture built a
    # colony flowing nurse -> cleaner -> forager and the file reported it as
    # flowing backwards and not directional. Both readings were wrong and the
    # second one was wrong in the safe direction, which is how it would have
    # survived a run on the real deposit without anyone noticing.
    #
    # The skip test recovers which label is in the MIDDLE. It says nothing about
    # which end is the start -- nothing can, from an unordered vocabulary. So
    # the orientation below is read off the flow and reported as a description,
    # while the thing actually scored against the null is the imbalance
    # |forward - backward|, which is identical under either orientation and so
    # cannot be inflated by having picked one.
    fwd, bwd = direction(pairs, order)
    e_fwd, e_bwd = 0.0, 0.0
    pos = {lab: k for k, lab in enumerate(order)}
    for (i, j), e in exp.items():
        if pos.get(j, 0) > pos.get(i, 0):
            e_fwd += e
        else:
            e_bwd += e
    if bwd > fwd:
        order = list(reversed(order))
        fwd, bwd = bwd, fwd
        e_fwd, e_bwd = e_bwd, e_fwd
    return dict(tag=tag, pairs=pairs, exp=exp, total=sum(pairs.values()),
                obs_skip=obs_skip, exp_skip=exp_skip, mid=mid, margin=margin,
                order=order, fwd=fwd, bwd=bwd, e_fwd=e_fwd, e_bwd=e_bwd,
                imbalance=abs(fwd - bwd), e_imbalance=abs(e_fwd - e_bwd))


def print_middle(s: dict) -> None:
    print(f"WHICH LABEL IS IN THE MIDDLE ({s['total']} moves)")
    print(f"  {'candidate middle':20} {'moves skipping it':>18} {'null':>8}")
    for mid, n in sorted(s["obs_skip"].items(), key=lambda kv: kv[1]):
        print(f"  {mid:20} {n:>18} {s['exp_skip'][mid]:>8.1f}")
    if s["margin"] <= 0:
        print(f"  !! no unique minimum. The labels do not lie on a line that "
              f"this measurement can see,")
        print(f"     and 'forward' has no meaning without one. Direction not "
              f"scored.")
        return
    print(f"  -> {s['mid']} is the middle, by {s['margin']} moves over the "
          f"runner-up.")
    print(f"     Order recovered from the data: "
          f"{' -- '.join(s['order'])}. Not assumed: each of the three labels "
          f"was offered the position.")
    print(f"     Written in the majority direction of flow. Only the middle is "
          f"recovered by this")
    print(f"     test; which end is the start is a description, and it is "
          f"scored in the next section.")


def print_direction(s: dict) -> None:
    tot = s["fwd"] + s["bwd"]
    if not tot:
        print("  no moves to score")
        return
    print(f"\nWHICH WAY THE FLOW RUNS")
    print(f"  Orientation is read off the flow, not assumed: the majority "
          f"direction is called")
    print(f"  the forward one. The skip test recovers the middle label and "
          f"cannot recover which")
    print(f"  end is the start, so what is scored below is the imbalance, "
          f"which is the same")
    print(f"  number whichever way round the axis is written.")
    print(f"  along {' -> '.join(s['order'])}")
    print(f"    with the flow : {s['fwd']:>4} of {tot} ({s['fwd'] / tot:.1%}), "
          f"null {s['e_fwd']:.1f}")
    print(f"    against it    : {s['bwd']:>4} of {tot} ({s['bwd'] / tot:.1%}), "
          f"null {s['e_bwd']:.1f}")
    print(f"    imbalance     : {s['imbalance']:>4} of {tot} "
          f"({s['imbalance'] / tot:.1%}), null {s['e_imbalance']:.1f} "
          f"({s['e_imbalance'] / tot:.1%})")
    if s["imbalance"] > max(1.15 * s["e_imbalance"], 0.10 * tot):
        print("  -> the flow is directional beyond what the shift in "
              "composition accounts for.")
        print("     A cut through a continuous quantity produces the ordering "
              "above but gives no")
        print("     reason for this: jitter across a boundary goes both ways.")
    else:
        print("  -> the flow is not directional beyond the null. The ordering "
              "above is then")
        print("     consistent with a boundary being crossed in both "
              "directions, which is what a")
        print("     discretised continuous position looks like.")


def reversal_p(movers: list[dict], order: list[str], obs: int) -> float:
    """Share of time-reversal draws whose imbalance reaches `obs`."""
    draws = reversal_null(movers, order)
    return sum(1 for d in draws if d >= obs) / len(draws)


def print_reversal(s: dict, changers: list[dict]) -> None:
    """The direction, against the arrow-of-time null rather than a re-drawn pool."""
    draws = reversal_null(changers, s["order"])
    obs = s["imbalance"]
    ordered = sorted(draws)
    mean = sum(ordered) / len(ordered)
    p95 = ordered[int(0.95 * (len(ordered) - 1))]
    exceed = sum(1 for d in ordered if d >= obs) / len(ordered)
    print(f"  (b) THE DIRECTION, against time reversal. Each ant's sequence is "
          f"reversed or not on")
    print(f"      a coin flip, {REVERSAL_DRAWS} times (seed {REVERSAL_SEED}). "
          f"Move counts, labels held and")
    print(f"      run structure are identical in a reversed record; only which "
          f"end she started")
    print(f"      from is destroyed. Prevalences taken over changers cannot do "
          f"this job -- a one-way")
    print(f"      flow is what makes the movers nurse-heavy early, so that null "
          f"absorbs the effect.")
    print(f"      observed imbalance {obs}; null mean {mean:.1f}, "
          f"95th percentile {p95}")
    print(f"      draws at or above the observed imbalance: {exceed:.1%} "
          f"of {REVERSAL_DRAWS}")
    if exceed <= 0.05:
        print(f"      -> the direction survives time reversal. The moves do not "
              f"just lie along an")
        print(f"         order, they run predominantly one way along it.")
    else:
        print(f"      -> the direction does not survive time reversal. Report "
              f"the ordering without")
        print(f"         a direction; an imbalance this size is what coin flips "
              f"produce here.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover the task ordering and "
                                             "test whether the flow is one-way.")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--expect-changed", type=int, default=EXPECT_CHANGED)
    ap.add_argument("--expect-complete", type=int, default=EXPECT_COMPLETE)
    a = ap.parse_args()

    path = find_behavior(Path(a.raw))
    print(f"behaviour table: {path}")
    records, notes = read_sequences(path)
    for n in notes:
        print(f"  !! {n}")
    part = partition(records)
    comp, chg = part["complete"], part["changers"]
    print(f"  scoreable ants {len(comp)} (expected {a.expect_complete}), "
          f"changers {len(chg)} (expected {a.expect_changed})")
    if (len(chg), len(comp)) != (a.expect_changed, a.expect_complete):
        print("!! this file does not reproduce the expected counts; nothing "
              "below would describe")
        print("   the population the headline describes, so nothing below is "
              "printed.")
        return 1
    print()

    main_s = score(chg, comp, "all scoreable ants")
    print_middle(main_s)
    if main_s["margin"] <= 0:
        return 1
    print_direction(main_s)

    # Two claims, two nulls, and they are not interchangeable. Re-drawing the
    # prevalences over changers is the unfavourable choice for the MIDDLE, and
    # it is a null that cannot see a DIRECTION at all -- see `reversal_null`.
    print("\nSENSITIVITY, in two parts, because the two claims fail in "
          "different ways")
    alt = score(chg, chg, "changers only")
    if alt["mid"] != main_s["mid"] or alt["margin"] <= 0:
        print(f"  (a) THE MIDDLE, with the null's prevalences over changers "
              f"only:")
        print(f"      !! the middle changes to {alt['mid']} (margin "
              f"{alt['margin']}). The ordering is a property of the null, not "
              f"of the data.")
    else:
        print(f"  (a) THE MIDDLE, with the null's prevalences over changers "
              f"only: unchanged "
              f"({alt['mid']}, margin {alt['margin']}); skip null moves "
              f"{main_s['exp_skip'][main_s['mid']]:.1f} -> "
              f"{alt['exp_skip'][alt['mid']]:.1f}")
    print_reversal(main_s, chg)

    # DEFECT, caught by the real-deposit run of 31 July and by the `wobble`
    # fixture built from it. This table used to re-orient each colony to its own
    # majority and print that as an arrow. Colony 29 came out `f -> c -> n` on a
    # 12-against-10 split -- a net of two moves out of twenty-two -- and sat in
    # the table looking exactly like the five colonies with real flows, an arrow
    # per row and nothing to separate them. It is the same shape as the failure
    # this project has already had once with col29, where a statistic that moves
    # with density was read as a period effect. A majority is not a direction.
    # So direction is now measured along the POOLED axis, so that "the other way"
    # is a thing a colony can be seen to do rather than a thing the orientation
    # code silently absorbs, and each colony's net is put to the same
    # time-reversal null as the pooled figure.
    main_order = main_s["order"]
    axis = " -> ".join(main_order)
    print("\nPER COLONY (a pattern in one colony is a colony, not a "
          "phenomenon)")
    print(f"  Direction is measured along the pooled axis {axis}, not along "
          f"each colony's own")
    print(f"  majority, and scored against the same reversal null. `net` is "
          f"with-minus-against on")
    print(f"  that axis and `p` is the share of reversal draws reaching it. A "
          f"colony whose majority")
    print(f"  is a handful of moves has no direction to report, and printing "
          f"its arrow would say")
    print(f"  otherwise.")
    by_col: dict[str, list] = {}
    for r in comp:
        by_col.setdefault(r["colony"], []).append(r)
    print(f"  {'colony':8} {'moves':>6} {'middle':>9} {'margin':>7} "
          f"{'with':>5} {'against':>8} {'net':>6} {'p':>7}  direction")
    agree = disagree = quiet = 0
    oneway = nodir = reverse = 0
    for col in sorted(by_col, key=lambda c: (len(c), c)):
        pool = by_col[col]
        movers = [r for r in pool if len(set(r["labels"])) > 1]
        s = score(movers, pool, col)
        pairs, _ = transitions(movers)
        fwd, bwd = direction(pairs, main_order)
        tot, net = fwd + bwd, fwd - bwd
        if tot < MIN_MOVES:
            quiet += 1
            print(f"  {col:8} {tot:>6} {'--':>9} {'--':>7} {fwd:>5} "
                  f"{bwd:>8} {net:>+6} {'--':>7}  not scored, fewer than "
                  f"{MIN_MOVES} moves")
            continue
        star = "" if (s["mid"] == main_s["mid"] and s["margin"] > 0) else "  !!"
        if star:
            disagree += 1
        else:
            agree += 1
        p = reversal_p(movers, main_order, abs(net))
        if p > 0.05:
            nodir += 1
            verdict = "no direction; the net is the size coin flips give"
        elif net > 0:
            oneway += 1
            verdict = "one-way, with the pooled axis"
        else:
            reverse += 1
            verdict = "one-way, AGAINST the pooled axis  !!"
        print(f"  {col:8} {tot:>6} {s['mid']:>9} {s['margin']:>7} "
              f"{fwd:>5} {bwd:>8} {net:>+6} {p:>7.3f}  {verdict}{star}")
    print(f"  {agree} colony/ies put {main_s['mid']} in the middle with a "
          f"positive margin, {disagree} do not, "
          f"{quiet} had fewer than {MIN_MOVES} moves and were not scored.")
    print(f"  On direction: {oneway} run one way along the pooled axis, "
          f"{nodir} show no direction, "
          f"{reverse} run the other way.")
    print(f"  A colony showing no direction is not a colony running backwards. "
          f"One that does run")
    print(f"  the other way is marked !! above, and would be the more "
          f"interesting result of the two.")
    if quiet:
        print(f"  The unscored ones are named above with their counts rather "
              f"than dropped: a colony")
        print(f"  that vanishes from a table reads as agreement.")

    print("\nWHAT MAY AND MAY NOT BE SAID FROM THIS")
    print("  Measured: an order over the three labels, and a direction along "
          "it.")
    print("  Not measured: why. The deposit carries no age, so 'workers mature "
          "from nursing")
    print("  through cleaning to foraging' is an interpretation laid over a "
          "direction. It is the")
    print("  standard reading of this system and it is still not what these "
          "counts establish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
