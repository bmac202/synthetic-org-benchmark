"""What Gini of strength would this many interactions among this many
individuals produce by chance?

WHY THIS EXISTS
---------------
The cross-system Gini comparison looked like the one measure that survived every
objection: no thinning, no matched density, no ceiling, no null. Six ant colonies
came in at 0.2037 to 0.2720 and three bee colonies at 0.2363 to 0.2733, and the
temptation was to read the overlap as "inequality of interaction effort is the
same in both systems".

That reading assumes Gini has the same zero point on both sides. It does not.
Gini of strength is not 0 for a random allocation of interactions -- it is 0 only
in the limit of infinitely many events per individual. With few events per
individual, chance alone concentrates counts and Gini rises. The bee bins have
roughly 1000 individuals sharing a few thousand food-sharing events; the ant days
have roughly 130 individuals sharing tens of thousands of antennal contacts. The
bee side therefore starts from a HIGHER chance baseline, and an equal observed
Gini on the two sides means the ants are further above their own baseline than
the bees are above theirs.

This is the same trap as the Freeman/ceiling ratio, in a new costume: a statistic
that looks scale-free because it is bounded in [0, 1], but whose behaviour under
no signal at all depends on n and on the event count. The fix is the same. Report
the observed value against ITS OWN null, and compare the excesses rather than
the raw values.

THE NULL
--------
Hold the roster (n) and the total number of interaction events (E) fixed, and
throw every event at a uniformly chosen pair of individuals. This destroys both
who-talks-to-whom and how-much, which is what we want: the question is what
inequality arises from counting alone.

A second, tighter null is available and deliberately NOT the default -- events
redistributed only over the pairs that were actually observed, which holds the
topology fixed and asks whether effort is concentrated beyond what the contact
structure forces. Both are meaningful; they answer different questions, and
`--null topology` selects the second. The default answers the question that
motivated this file, which is whether a Gini of 0.25 is a lot.

SAMPLING
--------
Simulating E events one at a time is O(E) per replicate and E runs to tens of
thousands per colony-day, so the direct simulation is too slow to run inside the
main script. Under the uniform null a node's strength is Binomial(2E, 1/n): each
event contributes one endpoint to each of two distinct nodes, so there are 2E
endpoint slots and each lands on a given node with probability 1/n. The marginals
are exactly binomial and the correlation between two nodes' counts is -1/(n-1),
which is under 1% for every n here, so sampling the nodes independently is a very
good approximation and is what `sample_strengths` does.

The "two distinct nodes" constraint means a node cannot receive both endpoints of
one event, which suppresses the upper tail very slightly relative to independent
sampling. `selftest()` measures that gap against a direct event-by-event
simulation rather than asserting it is small, because a correction nobody has
measured is a guess.

Binomial(2E, 1/n) is drawn by normal approximation when the mean is large enough
for it (lam >= 30, where the approximation's error on Gini is far below the
between-replicate spread) and by Knuth's Poisson method otherwise. Poisson rather
than exact binomial is itself an approximation, valid because p = 1/n is small;
its error also shows up in `selftest()`.
"""

from __future__ import annotations

import math
import random
import statistics as st


def gini(xs) -> float:
    """Mean absolute difference over twice the mean. 0 = everyone equal."""
    v = sorted(float(x) for x in xs)
    n = len(v)
    if n < 2:
        return 0.0
    total = sum(v)
    if total <= 0:
        return 0.0
    cum = sum((2 * i - n + 1) * x for i, x in enumerate(v))
    return cum / (n * total)


def _poisson(lam: float, rng: random.Random) -> int:
    """Knuth. O(lam), so only used for small lam."""
    ell = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= ell:
            return k
        k += 1


def sample_strengths(n: int, events: int, rng: random.Random) -> list:
    """One draw of the n node strengths under the uniform-pair null."""
    lam = 2.0 * events / n if n else 0.0
    if lam <= 0:
        return [0] * n
    if lam >= 30:
        sd = math.sqrt(lam * (1.0 - 1.0 / n))
        return [max(0, int(round(rng.gauss(lam, sd)))) for _ in range(n)]
    return [_poisson(lam, rng) for _ in range(n)]


def null_gini(n: int, events: int, reps: int = 40, seed: int = 0) -> dict:
    """Median and spread of Gini(strength) under the uniform-pair null.

    `events` is the total number of interaction EVENTS, i.e. the sum of edge
    weights -- not the number of edges. Passing the edge count instead is the
    easy mistake here and it makes the null look much more unequal than it is,
    because it shrinks the event count by the mean weight.
    """
    if n < 2 or events <= 0:
        return dict(n=n, events=events, median=None, lo=None, hi=None, reps=0)
    rng = random.Random(seed)
    vals = sorted(gini(sample_strengths(n, events, rng)) for _ in range(reps))
    return dict(n=n, events=events, reps=reps,
                median=round(st.median(vals), 4),
                lo=round(vals[0], 4), hi=round(vals[-1], 4))


def null_gini_on_edges(n: int, edges, reps: int = 40, seed: int = 0) -> dict:
    """Topology-preserving null: keep the observed pairs, reshuffle the weight.

    Answers a different question from `null_gini` -- given who contacted whom,
    is effort concentrated beyond what that contact structure forces? Events are
    dealt uniformly over the observed edges, so a node with many partners still
    accumulates more strength than a node with few.
    """
    if n < 2 or not edges:
        return dict(n=n, median=None, lo=None, hi=None, reps=0)
    events = int(round(sum(w for _, _, w in edges)))
    if events <= 0:
        return dict(n=n, median=None, lo=None, hi=None, reps=0)
    pairs = [(a, b) for a, b, _ in edges]
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        stg = {}
        for a, b, _w in edges:
            stg.setdefault(a, 0)
            stg.setdefault(b, 0)
        for _ in range(events):
            a, b = pairs[rng.randrange(len(pairs))]
            stg[a] += 1
            stg[b] += 1
        # Isolates carry a strength of 0 and must be counted: dropping them
        # would compare a null computed on the connected nodes against an
        # observed value computed on the whole roster.
        vals.append(gini(list(stg.values()) + [0] * (n - len(stg))))
    vals.sort()
    return dict(n=n, events=events, reps=reps,
                median=round(st.median(vals), 4),
                lo=round(vals[0], 4), hi=round(vals[-1], 4))


def _binomial(n: int, p: float, rng: random.Random) -> int:
    """Exact for small n, normal approximation for large. Used for thinning."""
    if n <= 0 or p <= 0:
        return 0
    if p >= 1:
        return n
    if n <= 40:
        return sum(1 for _ in range(n) if rng.random() < p)
    mu = n * p
    sd = math.sqrt(n * p * (1 - p))
    return min(n, max(0, int(round(rng.gauss(mu, sd)))))


def events_per_individual(n: int, edges) -> float:
    """2E/n. Each event touches two individuals, so this is the mean strength.

    This is the quantity that decides how much of an observed Gini is counting
    noise, and it is a property of the RECORDING, not of the animals: it depends
    on what behaviour was scored and for how long. Two systems with the same
    true inequality but different values of this number produce different Ginis.
    """
    if n < 1:
        return 0.0
    return 2.0 * sum(w for _, _, w in edges) / n


def gini_at_intensity(n: int, edges, target_epi: float,
                      reps: int = 9, seed: int = 0):
    """Gini(strength) after thinning events down to `target_epi` per individual.

    WHY THIS RATHER THAN A CORRECTION
    ---------------------------------
    The obvious fix for a scale-dependent baseline is to subtract it -- report
    observed minus null. Measured against a known truth across the n and event
    counts this project actually spans, that is the WORST of the options tried:
    subtraction over-corrects, because Gini combines true inequality and
    counting noise sub-additively rather than linearly. Quadrature
    (sqrt(obs^2 - null^2)) is much better on lognormal and gamma propensities
    and much worse on heavy-tailed and two-class ones, so choosing it means
    betting on the shape of a distribution nobody has measured.

    Thinning assumes nothing about shape. It performs the SAME operation the
    matched-density comparison performs on edges, one level down on events: put
    both sides at the same sampling intensity and run the plain statistic on
    both. The residual bias is not zero, but it is nearly the same on both
    sides, and for a comparison that is what matters.

    Like every thinning, it cannot ADD events, so the target must be at or below
    the sparser side's own intensity or the operation is a no-op on that side --
    the exact defect that made an earlier matched-density run meaningless.
    Callers must pass the minimum across both systems and check `thinned`.
    """
    n = int(n)
    if n < 2 or not edges:
        return dict(median=None, thinned=False, target_epi=target_epi)
    have = events_per_individual(n, edges)
    if have <= 0:
        return dict(median=None, thinned=False, target_epi=target_epi)
    if target_epi >= have:
        # A no-op, reported as one. Returning the untouched value silently is how
        # a table comes to say both sides were matched when only one of them was.
        return dict(median=None, thinned=False, target_epi=target_epi,
                    have_epi=round(have, 2))
    p = target_epi / have
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        stg = {}
        for a, b, w in edges:
            stg.setdefault(a, 0)
            stg.setdefault(b, 0)
            k = _binomial(int(round(w)), p, rng)
            if k:
                stg[a] += k
                stg[b] += k
        # Isolates and any node whose every event was thinned away still count:
        # they are part of the roster and dropping them raises Gini.
        vals.append(gini(list(stg.values()) + [0] * (n - len(stg))))
    vals.sort()
    return dict(median=round(st.median(vals), 4), thinned=True,
                target_epi=round(target_epi, 2), have_epi=round(have, 2),
                lo=round(vals[0], 4), hi=round(vals[-1], 4), reps=reps)


def _quantile_propensities(shape: str, n: int) -> list:
    """A propensity vector whose Gini is (near enough) independent of n.

    This is the fix for a confounded first attempt at this test. Drawing a fresh
    random propensity vector at each n meant the measured spread mixed two
    things: the scale artifact we are trying to size, and ordinary sampling
    variation in the propensity draw itself. Evaluating the distribution's
    inverse CDF on a deterministic grid removes the second entirely, so any
    difference between scales is the artifact and nothing else.
    """
    us = [(i + 0.5) / n for i in range(n)]
    if shape == "lognormal":
        nd = st.NormalDist()
        return [math.exp(0.6 * nd.inv_cdf(u)) for u in us]
    if shape == "pareto1.8":
        return [(1.0 - u) ** (-1.0 / 1.8) for u in us]
    if shape == "twoclass":
        return [5.0 if u > 0.8 else 1.0 for u in us]
    raise ValueError(shape)


def _simulate(prop, events: int, rng: random.Random) -> dict:
    """Throw `events` at pairs drawn proportional to propensity. -> {(a,b): w}."""
    n = len(prop)
    cum, run = [], 0.0
    for p in prop:
        run += p
        cum.append(run)
    total = run

    def pick() -> int:
        x = rng.random() * total
        lo, hi = 0, n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo

    w = {}
    for _ in range(events):
        a = pick()
        b = pick()
        while b == a:
            b = pick()
        k = (a, b) if a < b else (b, a)
        w[k] = w.get(k, 0) + 1
    return w


def bias_table(reps: int = 2) -> int:
    """Size the scale artifact in each candidate estimator against a known truth.

    The comparison this project needs is between ~130 ants sharing hundreds of
    events each and ~1000 bees sharing tens. Those are wildly different sampling
    intensities, so before any estimator is quoted across the two it has to be
    shown to give the SAME answer on both when the true inequality is identical
    by construction. The last column is the whole point: it is the gap the
    estimator invents out of scale alone, and it has to be small next to the
    ant-vs-bee difference anyone wants to interpret.

    Returns non-zero if subtraction (excess) still looks acceptable, because the
    file's own docstrings tell the reader it is not.
    """
    scales = [("ant-like", 130, 650.0), ("bee-like", 1000, 40.0)]
    target = min(epi for _, _, epi in scales)
    print("\n  scale artifact at FIXED true inequality "
          f"(thinning target {target:.0f} events/individual)")
    print(f"  {'shape':>11} {'true':>7} {'estimator':>10} "
          f"{'ant-like':>9} {'bee-like':>9} {'GAP':>8}")
    worst = {}
    for shape in ("lognormal", "pareto1.8", "twoclass"):
        truth = gini(_quantile_propensities(shape, 1000))
        got = {}
        for label, n, epi in scales:
            prop = _quantile_propensities(shape, n)
            events = int(round(epi * n / 2))
            acc = {}
            for r in range(reps):
                rng = random.Random(1000 + r)
                w = _simulate(prop, events, rng)
                edges = [(a, b, c) for (a, b), c in w.items()]
                stg = {}
                for a, b, c in edges:
                    stg[a] = stg.get(a, 0) + c
                    stg[b] = stg.get(b, 0) + c
                raw = gini(list(stg.values()) + [0] * (n - len(stg)))
                null = null_gini(n, events, reps=15, seed=7 + r)["median"] or 0.0
                mat = gini_at_intensity(n, edges, target, reps=3, seed=r)
                acc.setdefault("raw", []).append(raw)
                acc.setdefault("excess", []).append(raw - null)
                acc.setdefault("quad", []).append(
                    math.sqrt(max(0.0, raw * raw - null * null)))
                # A no-op leaves the value at the side's own intensity, which is
                # exactly right for the sparser side -- it is already at target.
                acc.setdefault("matched", []).append(
                    mat["median"] if mat["thinned"] else raw)
            got[label] = {k: st.median(v) for k, v in acc.items()}
        for est in ("raw", "excess", "quad", "matched"):
            a = got["ant-like"][est]
            b = got["bee-like"][est]
            gap = abs(a - b)
            worst[est] = max(worst.get(est, 0.0), gap)
            print(f"  {shape:>11} {truth:>7.4f} {est:>10} "
                  f"{a:>9.4f} {b:>9.4f} {gap:>8.4f}")
    print("\n  worst-case scale gap over the three shapes:")
    for est, g in sorted(worst.items(), key=lambda kv: kv[1]):
        print(f"    {est:>10} {g:.4f}")
    best = min(worst, key=worst.get)
    print(f"\n  best worst case: {best}")
    bad = 0
    if worst["excess"] <= worst["raw"]:
        print("  <-- excess is no longer the worst option; the docstrings in "
              "this file say it is, and one of the two is now wrong")
        bad = 1
    if best != "matched":
        print(f"  <-- '{best}' beats matched intensity here, but the main "
              "script thins. Re-read before quoting either.")
        bad = 1
    return bad


def selftest() -> int:
    """Measure the sampler against direct event-by-event simulation.

    The point is not to assert the approximation is good. It is to print how
    wrong it is, at the n and event counts this project actually uses, so the
    number can be judged rather than trusted.
    """
    rng = random.Random(11)
    print("  sampler vs direct simulation (both 40 reps)")
    print(f"  {'n':>6} {'events':>9} {'lam':>7} {'direct':>9} {'sampled':>9} "
          f"{'diff':>8} {'spread':>9}")
    bad = 0
    for n, events in [(130, 46952), (130, 2000), (164, 800),
                      (1000, 4000), (1000, 40000), (605, 9000)]:
        direct = []
        for _ in range(40):
            stg = [0] * n
            for _ in range(events):
                a = rng.randrange(n)
                b = rng.randrange(n)
                while b == a:
                    b = rng.randrange(n)
                stg[a] += 1
                stg[b] += 1
            direct.append(gini(stg))
        d = st.median(direct)
        s = null_gini(n, events, reps=40, seed=3)["median"]
        # The between-replicate spread of the direct simulation is the yardstick:
        # an approximation error smaller than the noise the null already has is
        # not worth correcting.
        spread = max(direct) - min(direct)
        flag = ""
        if abs(d - s) > max(spread, 0.005):
            flag = "  <-- larger than the null's own spread"
            bad += 1
        print(f"  {n:>6} {events:>9} {2*events/n:>7.1f} {d:>9.4f} {s:>9.4f} "
              f"{s - d:>+8.4f} {spread:>9.4f}{flag}")
    # A null that is indistinguishable from 0 would make the whole exercise
    # pointless, so show that it is not.
    print("\n  the null is not negligible, which is the reason this file exists:")
    for n, events in [(130, 46952), (1000, 4000)]:
        r = null_gini(n, events, reps=40, seed=5)
        print(f"    n={n:>5} events={events:>7} -> null Gini "
              f"{r['median']:.4f} [{r['lo']:.4f},{r['hi']:.4f}]")
    bad += bias_table()
    print("\n  FAIL" if bad else "\n  OK")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(selftest())
