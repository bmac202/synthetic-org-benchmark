"""Measurement instruments for REAL colony data.

`bench.py` already has instruments, but they were written against synthetic
organizations and they hard-code N, K and the demand schedule as module globals.
Real data breaks all three assumptions: the number of individuals is whatever
the tracking rig resolved, the number of tasks is whatever the ethogram or the
zone definition produced, and there is no known demand curve to match against.

This module is the real-data counterpart. Three things it does that the
synthetic version does not have to:

1.  **It corrects the mutual-information bias.** Normalized MI between individual
    and task is upward-biased whenever the agent x task table is sparse -- and
    with 4,000 bees and 4 zones over 400 bins it is very sparse. A colony of
    randomly behaving individuals will still score a positive DoL. So every DoL
    number here is reported alongside a permutation null: shuffle each
    individual's task sequence, recompute, repeat. The corrected value is
    raw minus null, and if that is near zero the "division of labour" is an
    artifact of sample size, not a property of the colony. Reporting an
    uncorrected DoL from sparse tracking data is the single easiest way to
    publish a result that does not replicate.

2.  **It gives confidence intervals.** Bootstrap over individuals, not over
    observations, because individuals are the sampling unit and observations
    within an individual are not independent.

3.  **It measures flexibility without a known demand schedule.** For real data
    we cannot score allocation against demand, because demand is unobserved.
    Instead we measure what actually happened around a shock: how much the
    task distribution moved, how many individuals changed their modal task, and
    how long the colony took to return to a stable allocation. That is a weaker
    claim than the synthetic bench makes, and it is the honest one.

Pure standard library. No numpy, no pandas -- these have to run on a laptop
with whatever Python is already installed.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict


# --------------------------------------------------------------- basic tables
def contingency(events) -> tuple[list[list[int]], int, int]:
    """agent x task counts. Returns (C, n_agents, n_tasks)."""
    n_a = max((a for a, _, _ in events), default=-1) + 1
    n_k = max((k for _, k, _ in events), default=-1) + 1
    C = [[0] * n_k for _ in range(n_a)]
    for a, k, _t in events:
        C[a][k] += 1
    return C, n_a, n_k


def _entropy(ps) -> float:
    return -sum(p * math.log(p) for p in ps if p > 0)


def nmi(C: list[list[int]]) -> float:
    """Normalized mutual information I(agent; task) / H(task).

    Normalizing by H(task) rather than by sqrt(H(a)H(k)) keeps this on the same
    scale as bench.dol_and_spec, so synthetic and real numbers are comparable.
    """
    tot = sum(sum(r) for r in C)
    if tot == 0:
        return 0.0
    n_k = len(C[0]) if C else 0
    pk = [sum(C[i][k] for i in range(len(C))) / tot for k in range(n_k)]
    pi = [sum(r) / tot for r in C]
    mi = 0.0
    for i, row in enumerate(C):
        if pi[i] <= 0:
            continue
        for k, c in enumerate(row):
            if c:
                pik = c / tot
                mi += pik * math.log(pik / (pi[i] * pk[k]))
    Hk = _entropy(pk)
    return max(0.0, min(1.0, mi / Hk)) if Hk > 0 else 0.0


def specialization(C: list[list[int]]) -> tuple[float, list[float]]:
    """Mean per-individual specialization, 1 - H(task|agent)/log K."""
    n_k = len(C[0]) if C else 0
    if n_k < 2:
        return 0.0, []
    logK = math.log(n_k)
    per = []
    for row in C:
        s = sum(row)
        if s == 0:
            continue
        per.append(1 - _entropy([c / s for c in row]) / logK)
    return (sum(per) / len(per) if per else 0.0), per


# ------------------------------------------------------- bias & uncertainty
def null_nmi(events, n_perm: int = 50, seed: int = 0) -> tuple[float, float]:
    """Permutation null for NMI: mean and sd under 'no individual identity'.

    Task labels are reshuffled across the whole event list, preserving both the
    number of observations per individual and the overall task frequencies but
    destroying the agent-task association. Whatever NMI survives that shuffle is
    the finite-sample floor.
    """
    rng = random.Random(seed)
    agents = [a for a, _, _ in events]
    tasks = [k for _, k, _ in events]
    vals = []
    for _ in range(n_perm):
        rng.shuffle(tasks)
        C, _, _ = contingency(list(zip(agents, tasks, agents)))
        vals.append(nmi(C))
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1))
    return m, sd


def bootstrap_ci(events, stat, n_boot: int = 200, seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI, resampling INDIVIDUALS with replacement.

    Resampling individual observations would treat repeated sightings of the
    same bee as independent evidence and give absurdly tight intervals.
    """
    rng = random.Random(seed)
    by_agent: dict[int, list] = defaultdict(list)
    for e in events:
        by_agent[e[0]].append(e)
    ids = list(by_agent)
    if len(ids) < 4:
        return (float("nan"), float("nan"))
    out = []
    for _ in range(n_boot):
        sample = []
        for new_id, old in enumerate(rng.choices(ids, k=len(ids))):
            for (_a, k, t) in by_agent[old]:
                sample.append((new_id, k, t))
        try:
            out.append(stat(sample))
        except Exception:
            continue
    if not out:
        return (float("nan"), float("nan"))
    out.sort()
    lo = out[int(alpha / 2 * len(out))]
    hi = out[min(len(out) - 1, int((1 - alpha / 2) * len(out)))]
    return lo, hi


def dol_report(events, n_perm: int = 50, n_boot: int = 200, seed: int = 0) -> dict:
    """The headline division-of-labour number, with its caveats attached."""
    C, n_a, n_k = contingency(events)
    raw = nmi(C)
    null_m, null_sd = null_nmi(events, n_perm, seed)
    lo, hi = bootstrap_ci(events, lambda ev: nmi(contingency(ev)[0]), n_boot, seed)
    spec, per = specialization(C)
    spec_lo, spec_hi = bootstrap_ci(
        events, lambda ev: specialization(contingency(ev)[0])[0], n_boot, seed)
    corrected = max(0.0, raw - null_m)
    z = (raw - null_m) / null_sd if null_sd > 0 else float("inf")
    return dict(
        n_agents=n_a, n_tasks=n_k, n_events=len(events),
        dol_raw=round(raw, 4),
        dol_null_mean=round(null_m, 4),
        dol_null_sd=round(null_sd, 5),
        dol_corrected=round(corrected, 4),
        dol_z_vs_null=round(z, 2) if math.isfinite(z) else None,
        dol_ci95=[round(lo, 4), round(hi, 4)] if math.isfinite(lo) else None,
        spec_mean=round(spec, 4),
        spec_ci95=[round(spec_lo, 4), round(spec_hi, 4)] if math.isfinite(spec_lo) else None,
        spec_sd=round(_sd(per), 4),
        verdict=_verdict(corrected, z),
    )


def _sd(xs) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _verdict(corrected: float, z: float) -> str:
    if not math.isfinite(z) or z < 3:
        return ("NOT distinguishable from chance. The raw DoL is explained by the "
                "sparsity of the table, not by the colony. Do not report the raw number.")
    if corrected < 0.05:
        return "significant but very small: individuals barely differ in what they do."
    if corrected < 0.20:
        return "modest division of labour."
    return "strong division of labour."


# --------------------------------------------------------------- role stability
def modal_task_by_window(events, n_windows: int = 4) -> list[dict[int, int]]:
    """Each individual's modal task in each of n_windows equal time slices."""
    tmax = max((t for _, _, t in events), default=0)
    span = (tmax + 1) / n_windows
    acc: list[dict[int, Counter]] = [defaultdict(Counter) for _ in range(n_windows)]
    for a, k, t in events:
        w = min(n_windows - 1, int(t / span)) if span > 0 else 0
        acc[w][a][k] += 1
    return [{a: c.most_common(1)[0][0] for a, c in w.items()} for w in acc]


def role_stability(events, n_windows: int = 4) -> dict:
    """Do individuals keep the same task over time, or churn?

    This is the biological version of the organizational question 'does informal
    role structure persist without anyone assigning it'. It is reported as the
    fraction of individuals whose modal task is unchanged between consecutive
    windows, against the chance level implied by the task frequencies.
    """
    wins = modal_task_by_window(events, n_windows)
    agreements, ns = [], []
    for w1, w2 in zip(wins, wins[1:]):
        shared = set(w1) & set(w2)
        if not shared:
            continue
        agreements.append(sum(w1[a] == w2[a] for a in shared) / len(shared))
        ns.append(len(shared))
    C, _, n_k = contingency(events)
    tot = sum(sum(r) for r in C)
    pk = [sum(C[i][k] for i in range(len(C))) / tot for k in range(n_k)] if tot else []
    chance = sum(p * p for p in pk)
    obs = sum(agreements) / len(agreements) if agreements else float("nan")
    kappa = (obs - chance) / (1 - chance) if chance < 1 and math.isfinite(obs) else float("nan")
    return dict(
        n_windows=n_windows,
        window_agreement=[round(a, 4) for a in agreements],
        agreement_mean=round(obs, 4) if math.isfinite(obs) else None,
        chance_agreement=round(chance, 4),
        kappa=round(kappa, 4) if math.isfinite(kappa) else None,
        n_shared_individuals=ns,
        note=("kappa near 0 means individuals are re-sorting between windows; near 1 "
              "means roles are sticky. Read alongside the temporal_caveat in meta.json: "
              "if the dataset only re-assessed task labels 3 times, this is measuring "
              "label persistence, not behavioural persistence."),
    )


# ------------------------------------------------------------------ flexibility
def allocation_by_timestep(events, n_tasks: int | None = None) -> dict[int, list[float]]:
    if n_tasks is None:
        n_tasks = max((k for _, k, _ in events), default=-1) + 1
    counts: dict[int, list[int]] = defaultdict(lambda: [0] * n_tasks)
    for _a, k, t in events:
        counts[t][k] += 1
    out = {}
    for t, c in counts.items():
        s = sum(c)
        out[t] = [x / s for x in c] if s else [0.0] * n_tasks
    return out


def _tvd(p, q) -> float:
    return 0.5 * sum(abs(a - b) for a, b in zip(p, q))


def flexibility_around_shock(events, shift: int, settle: int | None = None) -> dict:
    """What the colony actually did when the workforce was disturbed.

    Reported quantities:
      response_tvd     how far the aggregate task distribution moved, pre vs post
      switch_fraction  fraction of individuals whose modal task changed
      recovery_steps   timesteps until the post-shock allocation stops moving
                       (first t where the distribution is within `tol` of the
                       eventual post-shock mean for `hold` consecutive steps)

    None of these need a demand schedule, which is the point: with real data
    demand is unobserved, so the honest measurement is of the RESPONSE, not of
    the match to an assumed optimum.
    """
    n_tasks = max((k for _, k, _ in events), default=-1) + 1
    alloc = allocation_by_timestep(events, n_tasks)
    times = sorted(alloc)
    if not times or shift is None:
        return dict(error="no timesteps or no shift point supplied")
    pre_t = [t for t in times if t < shift]
    post_t = [t for t in times if t >= shift]
    if not pre_t or not post_t:
        return dict(error=f"shift={shift} leaves one side empty "
                          f"(pre={len(pre_t)}, post={len(post_t)})")

    def mean_alloc(ts):
        acc = [0.0] * n_tasks
        for t in ts:
            for k in range(n_tasks):
                acc[k] += alloc[t][k]
        return [x / len(ts) for x in acc]

    pre, post = mean_alloc(pre_t), mean_alloc(post_t)

    # per-individual modal task, pre vs post
    pre_m: dict[int, Counter] = defaultdict(Counter)
    post_m: dict[int, Counter] = defaultdict(Counter)
    for a, k, t in events:
        (pre_m if t < shift else post_m)[a][k] += 1
    shared = set(pre_m) & set(post_m)
    switched = sum(pre_m[a].most_common(1)[0][0] != post_m[a].most_common(1)[0][0]
                   for a in shared)

    # recovery: first post-shock t whose allocation stays close to `post`
    tol, hold = 0.10, max(3, len(post_t) // 20)
    recovery = None
    run = 0
    for t in post_t:
        if _tvd(alloc[t], post) <= tol:
            run += 1
            if run >= hold:
                recovery = t - shift - hold + 1
                break
        else:
            run = 0

    settle = settle if settle is not None else (recovery or 0)
    settled_t = [t for t in post_t if t >= shift + settle]
    return dict(
        shift_timestep=shift,
        n_pre_steps=len(pre_t), n_post_steps=len(post_t),
        alloc_pre=[round(x, 4) for x in pre],
        alloc_post=[round(x, 4) for x in post],
        response_tvd=round(_tvd(pre, post), 4),
        n_individuals_both_sides=len(shared),
        switch_fraction=round(switched / len(shared), 4) if shared else None,
        recovery_steps=recovery,
        settled_stability=round(
            1 - sum(_tvd(alloc[t], post) for t in settled_t) / len(settled_t), 4
        ) if settled_t else None,
        note=("response_tvd is 0..1: how much the aggregate allocation moved. "
              "switch_fraction is the individual-level version of the same thing. "
              "recovery_steps is None if the allocation never settles, which is "
              "itself a finding."),
    )


# ------------------------------------------------ comparability with bench.py
def to_bench_log(events) -> list[list]:
    """Same shape bench.run() produces: log[t][i] = task or None."""
    n_a = max((a for a, _, _ in events), default=-1) + 1
    tmax = max((t for _, _, t in events), default=-1)
    log = [[None] * n_a for _ in range(tmax + 1)]
    for a, k, t in events:
        log[t][a] = k
    return log


def summary_line(name: str, rep: dict) -> str:
    ci = rep.get("dol_ci95")
    ci_s = f" [{ci[0]:.2f},{ci[1]:.2f}]" if ci else ""
    return (f"{name:28} n={rep['n_agents']:>5} K={rep['n_tasks']:>2} "
            f"DoL_raw={rep['dol_raw']:.3f} null={rep['dol_null_mean']:.3f} "
            f"DoL_corr={rep['dol_corrected']:.3f}{ci_s} "
            f"spec={rep['spec_mean']:.3f}")
