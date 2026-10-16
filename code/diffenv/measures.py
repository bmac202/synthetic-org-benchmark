"""The differentiation protocol — one code path for every substrate.

This is the protocol RESTART.md describes for the ants (Alciatore) and the humans (InVS),
written down as code so the synthetic organizations are scored by the same function and so
the ant and human numbers can be re-run from it later. (The August script that produced the
ant and human numbers was never committed; this module is the repair.)

Input is a *long table*: rows of (org, window, agent, value). Nothing here knows what an
"org" is — a colony, a workplace-day series, or a synthetic run — which is the point.

Steps, exactly as recorded on 13 August:
  1. standardize within org × window across the agents present;
  2. repeatability  R = var(agent means) / (var(agent means) + mean within-agent variance);
  3. null: permute agent labels within each org × window, 200 draws; report the observed
     value against the null median and 95th percentile — never report R without it;
  4. split-half: rank correlation between each agent's mean in the first and second half of
     its windows, with the same null.

Plus the two measures the spec adds for division of labour rather than differentiation:
  * specialization — per agent-window entropy over item types worked, against a null that
    shuffles types among work actions within org × window (holds fixed how much each agent
    works and how common each type is; asks only whether agents work *narrower* sets);
  * favoured-type repeatability — R applied to each type's share of an agent's work, averaged
    over types; asks whether *which* type an agent favours is stable across windows;
  * partner consistency — Jaccard overlap of an agent's message partners in consecutive
    windows, against random partner sets of the same sizes.

House rules honoured: every statistic is returned with its null; a window in which all
agents tie is counted and reported (`degenerate_windows`), not silently zeroed.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

Row = Tuple[str, int, str, float]          # org, window, agent, value
N_DRAWS = 200


# --------------------------------------------------------------------------- core
def _group(table: Iterable[Row]) -> Dict[Tuple[str, int], Dict[str, float]]:
    g: Dict[Tuple[str, int], Dict[str, float]] = defaultdict(dict)
    for org, w, a, v in table:
        g[(org, w)][a] = float(v)
    return g


def standardize(table: Iterable[Row]) -> Tuple[List[Row], int]:
    """z-score within org × window. Returns (rows, number of degenerate windows)."""
    out: List[Row] = []
    degenerate = 0
    for (org, w), d in _group(table).items():
        vals = np.array(list(d.values()), dtype=float)
        if len(vals) < 2:
            degenerate += 1
            continue
        sd = vals.std(ddof=1)
        if sd == 0:
            degenerate += 1
            for a in d:
                out.append((org, w, a, 0.0))
            continue
        mu = vals.mean()
        for a, v in d.items():
            out.append((org, w, a, (v - mu) / sd))
    return out, degenerate


DDOF = 1   # project convention: sample variances. The 13 August ant/human numbers used
           # population variances (numpy's default); pass ddof=0 to reproduce them exactly.


def repeatability(z: Iterable[Row], ddof: int = DDOF) -> float:
    series: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for org, w, a, v in z:
        series[(org, a)].append(v)
    means, withins = [], []
    for s in series.values():
        if len(s) < 2:
            continue
        arr = np.array(s)
        means.append(arr.mean())
        withins.append(arr.var(ddof=ddof))
    if len(means) < 2:
        return float("nan")
    vb = float(np.var(means, ddof=ddof))
    vw = float(np.mean(withins))
    return vb / (vb + vw) if (vb + vw) > 0 else float("nan")


def _spearman(x: List[float], y: List[float]) -> float:
    if len(x) < 3:
        return float("nan")
    rx = np.argsort(np.argsort(x)); ry = np.argsort(np.argsort(y))
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def split_half(z: Iterable[Row]) -> float:
    by_org_win: Dict[str, set] = defaultdict(set)
    series: Dict[Tuple[str, str], Dict[int, float]] = defaultdict(dict)
    for org, w, a, v in z:
        by_org_win[org].add(w); series[(org, a)][w] = v
    firsts, seconds = [], []
    for (org, a), d in series.items():
        wins = sorted(by_org_win[org]); half = len(wins) // 2
        f = [d[w] for w in wins[:half] if w in d]; s = [d[w] for w in wins[half:] if w in d]
        if f and s:
            firsts.append(float(np.mean(f))); seconds.append(float(np.mean(s)))
    return _spearman(firsts, seconds)


def permute_labels(table: List[Row], rng: random.Random) -> List[Row]:
    """Shuffle values among agents within each org × window — destroys identity, keeps
    every value and every window's distribution."""
    out: List[Row] = []
    for (org, w), d in _group(table).items():
        agents = list(d.keys()); vals = list(d.values()); rng.shuffle(vals)
        out.extend((org, w, a, v) for a, v in zip(agents, vals))
    return out


def null_distribution(table: List[Row], stat, n_draws: int = N_DRAWS, seed: int = 0) -> np.ndarray:
    rng = random.Random(seed)
    draws = []
    for _ in range(n_draws):
        z, _ = standardize(permute_labels(table, rng))
        draws.append(stat(z))
    return np.array(draws, dtype=float)


def summarize(observed: float, null: np.ndarray) -> dict:
    null = null[~np.isnan(null)]
    if len(null) == 0 or math.isnan(observed):
        return {"observed": observed, "null_median": float("nan"), "null_p95": float("nan"),
                "p_value": float("nan"), "n_null": int(len(null))}
    return {"observed": float(observed), "null_median": float(np.median(null)),
            "null_p95": float(np.percentile(null, 95)),
            "p_value": float(np.mean(null >= observed)), "n_null": int(len(null))}


def differentiation(table: List[Row], seed: int = 0, n_draws: int = N_DRAWS, ddof: int = DDOF) -> dict:
    """The full protocol on one long table: R and split-half, each with its null."""
    z, degenerate = standardize(table)
    n_windows = len({(o, w) for o, w, _, _ in table})
    rstat = (lambda zz: repeatability(zz, ddof=ddof))
    out = {
        "n_rows": len(table), "n_windows": n_windows, "degenerate_windows": degenerate,
        "n_agents": len({(o, a) for o, _, a, _ in table}), "ddof": ddof,
        "R": summarize(repeatability(z, ddof=ddof), null_distribution(table, rstat, n_draws, seed)),
        "split_half": summarize(split_half(z), null_distribution(table, split_half, n_draws, seed + 1)),
    }
    return out


# --------------------------------------------------------------------------- from a log
def tables_from_log(log: List[dict], agents: List[str], n_windows: int, window: int,
                    present_until: Optional[Dict[str, int]] = None, org: str = "run",
                    opportunity: Optional[Dict[Tuple[str, int], int]] = None) -> Dict[str, List[Row]]:
    """Derive the three constructs (activity, interaction, isolation) per agent per window,
    plus the raw type counts per agent-window used by the specialization measures.

    present_until[a] = last round in which agent a was present (for the exit factor);
    agent-windows after that are dropped rather than scored as zero."""
    def present(a, w):
        if not present_until or a not in present_until:
            return True
        return w * window <= present_until[a]   # window starts while agent still present

    act = defaultdict(int); inter = defaultdict(int); talk_rounds = defaultdict(set)
    types = defaultdict(lambda: defaultdict(int)); partners = defaultdict(set)
    for m in log:
        w = m["window"]; a = m["sender"]
        if m["mtype"] == "work":
            act[(a, w)] += 1
            types[(a, w)][m["payload"]["type"]] += 1
        elif m["mtype"] == "tell":
            b = m["recipient"]
            inter[(a, w)] += 1; inter[(b, w)] += 1
            talk_rounds[(a, w)].add(m["round"]); talk_rounds[(b, w)].add(m["round"])
            partners[(a, w)].add(b); partners[(b, w)].add(a)
    tabs = {"activity": [], "interaction": [], "isolation": [], "activity_given_opportunity": []}
    type_counts: Dict[Tuple[str, int], Dict[str, int]] = {}
    partner_sets: Dict[Tuple[str, int], set] = {}
    for w in range(n_windows):
        for a in agents:
            if not present(a, w):
                continue
            tabs["activity"].append((org, w, a, act[(a, w)]))
            tabs["interaction"].append((org, w, a, inter[(a, w)]))
            tabs["isolation"].append((org, w, a, window - len(talk_rounds[(a, w)])))
            if opportunity is not None:
                # rounds in this window in which the agent had at least one item it could work;
                # under private visibility this separates disposition from luck of arrival
                opp_rounds = sum(1 for r in range(w * window, (w + 1) * window) if opportunity.get((a, r), 0) > 0)
                if opp_rounds > 0:
                    tabs["activity_given_opportunity"].append((org, w, a, act[(a, w)] / opp_rounds))
            type_counts[(a, w)] = dict(types[(a, w)])
            partner_sets[(a, w)] = set(partners[(a, w)])
    tabs["_type_counts"] = type_counts        # not a long table; consumed by specialization()
    tabs["_partner_sets"] = partner_sets
    return tabs


# --------------------------------------------------------------------------- specialization
def _norm_entropy(counts: Dict[str, int], n_types: int) -> float:
    n = sum(counts.values())
    if n == 0 or n_types < 2:
        return float("nan")
    ps = [c / n for c in counts.values() if c > 0]
    h = -sum(p * math.log(p) for p in ps)
    return h / math.log(n_types)


def specialization(type_counts: Dict[Tuple[str, int], Dict[str, int]], n_types: int,
                   min_work: int = 2, seed: int = 0, n_draws: int = N_DRAWS, org: str = "run") -> dict:
    """Within-window narrowness (entropy) against a type-shuffle null, and favoured-type
    repeatability (R on each type's share, averaged) against the label-permutation null."""
    rng = random.Random(seed)
    # entropy, observed
    def mean_entropy(tc):
        hs = [_norm_entropy(c, n_types) for c in tc.values() if sum(c.values()) >= min_work]
        return float(np.mean(hs)) if hs else float("nan")
    obs_h = mean_entropy(type_counts)
    # null: shuffle the type labels among all work actions within each window
    by_win = defaultdict(list)
    for (a, w), c in type_counts.items():
        for ty, k in c.items():
            by_win[w].extend([(a, ty)] * k)
    null_h = []
    for _ in range(n_draws):
        tc = defaultdict(lambda: defaultdict(int))
        for w, acts in by_win.items():
            tys = [ty for _, ty in acts]; rng.shuffle(tys)
            for (a, _), ty in zip(acts, tys):
                tc[(a, w)][ty] += 1
        null_h.append(mean_entropy(tc))
    ent = summarize(obs_h, np.array(null_h))
    ent["p_value"] = float(np.mean(np.array(null_h) <= obs_h)) if not math.isnan(obs_h) else float("nan")  # lower = more specialized
    ent["direction"] = "lower is more specialized; p = share of null draws at or below observed"
    # favoured-type repeatability: R on each type's share
    all_types = sorted({ty for c in type_counts.values() for ty in c})
    shares = {ty: [] for ty in all_types}
    for (a, w), c in type_counts.items():
        n = sum(c.values())
        if n < min_work:
            continue
        for ty in all_types:
            shares[ty].append((org, w, a, c.get(ty, 0) / n))
    per_type = {}
    for ty, tab in shares.items():
        if len({a for _, _, a, _ in tab}) >= 3 and len({w for _, w, _, _ in tab}) >= 2:
            per_type[ty] = differentiation(tab, seed=seed, n_draws=n_draws)["R"]
    if per_type:
        fav = {"observed": float(np.nanmean([v["observed"] for v in per_type.values()])),
               "null_median": float(np.nanmean([v["null_median"] for v in per_type.values()])),
               "null_p95": float(np.nanmean([v["null_p95"] for v in per_type.values()])),
               "per_type": per_type}
    else:
        fav = {"observed": float("nan"), "note": "too few agent-windows with >= min_work work actions"}
    return {"entropy": ent, "favoured_type_R": fav, "min_work": min_work}


# --------------------------------------------------------------------------- partners
def partner_consistency(partner_sets: Dict[Tuple[str, int], set], agents: List[str], n_windows: int,
                        seed: int = 0, n_draws: int = N_DRAWS) -> dict:
    """Mean Jaccard of consecutive-window partner sets, against random sets of the same sizes."""
    rng = random.Random(seed)
    pairs = []
    for a in agents:
        for w in range(n_windows - 1):
            s1 = partner_sets.get((a, w)); s2 = partner_sets.get((a, w + 1))
            if s1 is None or s2 is None or not s1 or not s2:
                continue
            pairs.append((a, s1, s2))
    if not pairs:
        return {"observed": float("nan"), "note": "no agent had partners in consecutive windows"}
    def jac(x, y):
        return len(x & y) / len(x | y)
    obs = float(np.mean([jac(s1, s2) for _, s1, s2 in pairs]))
    others = {a: [o for o in agents if o != a] for a in agents}
    null = []
    for _ in range(n_draws):
        vals = []
        for a, s1, s2 in pairs:
            r1 = set(rng.sample(others[a], len(s1))); r2 = set(rng.sample(others[a], len(s2)))
            vals.append(jac(r1, r2))
        null.append(float(np.mean(vals)))
    out = summarize(obs, np.array(null)); out["n_pairs"] = len(pairs)
    return out


# --------------------------------------------------------------------------- one call
def score_run(log: List[dict], agents: List[str], n_windows: int, window: int, n_types: int,
              present_until: Optional[Dict[str, int]] = None, seed: int = 0, n_draws: int = N_DRAWS,
              opportunity: Optional[Dict[Tuple[str, int], int]] = None) -> dict:
    tabs = tables_from_log(log, agents, n_windows, window, present_until, opportunity=opportunity)
    out = {k: differentiation(tabs[k], seed=seed, n_draws=n_draws) for k in ("activity", "interaction", "isolation")}
    if tabs["activity_given_opportunity"]:
        out["activity_given_opportunity"] = differentiation(tabs["activity_given_opportunity"], seed=seed, n_draws=n_draws)
    out["specialization"] = specialization(tabs["_type_counts"], n_types, seed=seed, n_draws=n_draws)
    out["partner_consistency"] = partner_consistency(tabs["_partner_sets"], agents, n_windows, seed=seed, n_draws=n_draws)
    return out
