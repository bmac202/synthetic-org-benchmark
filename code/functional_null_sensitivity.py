"""Sensitivity analysis for the functional (favored-type) baseline (added 19 Oct 2026).

The pre-specified functional statistic is the mean over task types of per-type repeatability R_k
(measures.specialization). Its pre-specified baseline is the mean over types of each type's own
95th-percentile null value. That is not, in general, the 95th percentile of the null distribution of
the mean statistic itself. This script computes the latter: in each draw, member labels are permuted
within each window once and the same permutation is applied to every type's share (so each
member-window keeps its whole type profile), and the mean of the per-type R is recomputed.

It leaves the pre-specified analysis untouched and reports, for every run, the observed statistic,
the pre-specified threshold and the aggregate-null threshold, and whether each is exceeded.

    python3 functional_null_sensitivity.py            # from code/; no API calls

Writes diffenv_results/plan_scores_2026-10-17/FUNCTIONAL_NULL_SENSITIVITY.md and .json.
"""
import json, os, random
from collections import defaultdict
import numpy as np
from diffenv.measures import standardize, repeatability, specialization, tables_from_log
from diffenv.env import OpenQueueEnv, default_config
from diffenv.ground_truth import CONDITIONS

N_DRAWS, MIN_WORK = 200, 2
R = "diffenv_results"; OUT = os.path.join(R, "plan_scores_2026-10-17")


def share_tables(type_counts):
    all_types = sorted({ty for c in type_counts.values() for ty in c})
    rows = {}                                   # (w, a) -> {type: share}
    for (a, w), c in type_counts.items():
        n = sum(c.values())
        if n >= MIN_WORK:
            rows[(w, a)] = {ty: c.get(ty, 0) / n for ty in all_types}
    keep = []
    for ty in all_types:
        tab = [("run", w, a, s[ty]) for (w, a), s in rows.items()]
        if len({a for _, _, a, _ in tab}) >= 3 and len({w for _, w, _, _ in tab}) >= 2:
            keep.append(ty)
    return rows, keep


def mean_r(rows, types):
    vals = []
    for ty in types:
        z, _ = standardize([("run", w, a, s[ty]) for (w, a), s in rows.items()])
        vals.append(repeatability(z))
    return float(np.nanmean(vals))


def aggregate_null(type_counts, seed=0, draws=N_DRAWS):
    rows, types = share_tables(type_counts)
    if not types:
        return float("nan"), float("nan")
    obs = mean_r(rows, types)
    by_w = defaultdict(list)
    for (w, a) in rows:
        by_w[w].append(a)
    rng = random.Random(seed)
    null = []
    for _ in range(draws):
        perm = {}
        for w, agents in by_w.items():
            src = agents[:]; rng.shuffle(src)
            for a, b in zip(agents, src):
                perm[(w, a)] = rows[(w, b)]
        null.append(mean_r(perm, types))
    return obs, float(np.percentile(null, 95))


def score(type_counts, n_types, seed=0):
    pre = specialization(type_counts, n_types, seed=seed, n_draws=N_DRAWS)["favoured_type_R"]
    obs, agg95 = aggregate_null(type_counts, seed=seed)
    return {"observed": pre.get("observed"), "prespecified_threshold": pre.get("null_p95"),
            "aggregate_threshold": agg95, "observed_check": obs}


def llm_cells():
    S = json.load(open(os.path.join(OUT, "scores.json")))["runs"]
    out = {}
    for cell, runs in S.items():
        res = []
        for r in runs:
            d = json.load(open(os.path.join(R, r["file"])))
            W = d["config"]["window"]; nW = d["config"]["rounds"] // W
            tabs = tables_from_log(d["log"], d["agents"], nW, W)
            res.append(dict(seed=r["seed"], **score(tabs["_type_counts"], d["config"]["n_types"])))
        out[cell] = res
    return out


def known_answer(seeds=range(20)):
    out = {}
    for cond in CONDITIONS:
        res = []
        for s in seeds:
            cfg = default_config(visibility="private"); env = OpenQueueEnv(cfg, s)
            env.run(CONDITIONS[cond][1](s, env.agents, cfg.n_types))
            nW = cfg.rounds // cfg.window
            tabs = tables_from_log(env.log, env.agents, nW, cfg.window, opportunity=env.opportunity)
            res.append(dict(seed=s, **score(tabs["_type_counts"], cfg.n_types, seed=s)))
        out[cond] = res
    return out


def summarize(name, res):
    n = len(res)
    a = sum(r["observed"] > r["prespecified_threshold"] for r in res)
    b = sum(r["observed"] > r["aggregate_threshold"] for r in res)
    med = lambda k: float(np.nanmedian([r[k] for r in res]))
    return (f"| {name} | {n} | {med('observed'):.2f} | {med('prespecified_threshold'):.2f} | {a}/{n} | "
            f"{med('aggregate_threshold'):.2f} | {b}/{n} |")


if __name__ == "__main__":
    llm = llm_cells(); ka = known_answer()
    head = ["| Cell | Runs | Median R | Pre-specified threshold (median) | Above | Aggregate-null threshold (median) | Above |",
            "|---|---|---|---|---|---|---|"]
    L = ["# Functional (favored-type) baseline: pre-specified vs aggregate null", "",
         "Pre-specified threshold: mean over task types of each type's 95th-percentile null. Aggregate-null threshold:",
         "95th percentile of the null distribution of the mean statistic itself (one joint label permutation per",
         "window applied to all types; 200 draws). The pre-specified analysis is unchanged.", "",
         "## LLM runs (plan-specified cells)", ""] + head
    L += [summarize(c, r) for c, r in llm.items()]
    L += ["", "## Known-answer test (rule-based agents, seeds 0-19)", ""] + head
    L += [summarize(c, r) for c, r in ka.items()]
    chk = max(abs(r["observed"] - r["observed_check"]) for rs in list(llm.values()) + list(ka.values()) for r in rs
              if r["observed"] == r["observed"])
    L += ["", f"Check: largest difference between the stored observed statistic and its recomputation: {chk:.2e}."]
    open(os.path.join(OUT, "FUNCTIONAL_NULL_SENSITIVITY.md"), "w").write("\n".join(L) + "\n")
    json.dump({"llm": llm, "known_answer": ka}, open(os.path.join(OUT, "functional_null_sensitivity.json"), "w"), indent=1)
    print("\n".join(L))
