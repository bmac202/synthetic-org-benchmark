"""Score the confirmatory comparisons exactly as fixed in ANALYSIS_PLAN_2026-10-16.md.

    python3 score_plan.py        # from code/; makes no API calls

Primary outcomes, each against the run's own 95th-percentile label-permutation baseline
(200 draws, seed 0, unchanged scoring code):
  hub persistence       track_alias.score(...)["received"]
  task-type persistence derived_measures["specialization"]["favoured_type_R"] (measures.specialization)
Writes diffenv_results/plan_scores_2026-10-17/{scores.json, SCORES.md}.
"""
import ast, glob, itertools, json, os, random
from collections import Counter
import numpy as np
from diffenv.track_alias import score as hub_score

R = "diffenv_results"
OUT = os.path.join(R, "plan_scores_2026-10-17"); os.makedirs(OUT, exist_ok=True)
G, H = "openai-gpt-4.1-mini", "anthropic-claude-haiku-4-5"

def files(pattern_by_dir):
    out = []
    for d, pat in pattern_by_dir:
        out += glob.glob(os.path.join(R, d, "specimens", pat))
    return sorted(set(out), key=lambda p: int(p.split("seed")[-1].split(".")[0]))

CELLS = {
    "gpt_fixed":    files([("final", f"c1+private-{G}-seed*.json"), ("replications_2026-10-17", f"c1+private-{G}-seed*.json")]),
    "gpt_latin":    files([("alias_rerun", f"c1+private+alias-{G}-seed*.json"), ("replications_2026-10-17", f"c1+private+alias-{G}-seed*.json")]),
    "gpt_balanced": files([("balanced_2026-10-17", f"c1+private+aliasbal-{G}-seed*.json")]),
    "gpt_assigned": files([("final", f"c2+private-{G}-seed*.json"), ("gaps_2026-10-16", f"c2+private-{G}-seed*.json"), ("replications_2026-10-17", f"c2+private-{G}-seed*.json")]),
    "haiku_latin":  files([("gaps_2026-10-16", f"c1+private+alias-{H}-seed*.json"), ("replications_2026-10-17", f"c1+private+alias-{H}-seed*.json")]),
    "haiku_assigned": files([("final", f"c2+private-{H}-seed*.json"), ("gaps_2026-10-16", f"c2+private-{H}-seed*.json"), ("replications_2026-10-17", f"c2+private-{H}-seed*.json")]),
    "haiku_fixed":  files([("final", f"c1+private-{H}-seed*.json")]),   # exploratory, not in the plan
}

def run_scores(p):
    d = json.load(open(p)); h = hub_score(p)
    fav = d["derived_measures"]["specialization"]["favoured_type_R"]
    rec = h["received_by_agent"]; ag = h["agents"]
    top = ag[int(np.argmax(rec))]
    o = {"file": os.path.relpath(p, R), "seed": d["seed"],
         "hub": h["received"], "task": (fav["observed"], fav["null_p95"]),
         "top_receiver": top, "top_share": max(rec) / max(1, sum(rec)),
         "completed": d["outcome"]["completed"], "cost": h["cost"],
         "other": {k: h[k] for k in ("work|opp", "interaction", "sent|opp")}}
    # favoured label: for each sender, the label (as that sender sees it) of the agent it told most
    al = (d.get("llm") or {}).get("alias")
    if al:
        al = ast.literal_eval(al) if isinstance(al, str) else al
        fav_lab = []
        for a in ag:
            c = Counter(m["recipient"] for m in d["log"] if m["mtype"] == "tell" and m["sender"] == a)
            if c:
                fav_lab.append(al[a][c.most_common(1)[0][0]])
        o["favoured_labels"] = dict(Counter(fav_lab))
    return o

def above(x): return x[0] > x[1]

def boot_ci(v, n=10000, seed=1):
    rng = np.random.default_rng(seed); v = np.asarray(v)
    meds = np.median(rng.choice(v, size=(n, len(v)), replace=True), axis=1)
    return float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))

def mann_whitney_exact(x, y):
    allv = np.array(list(x) + list(y)); ranks = allv.argsort().argsort() + 1.0
    # mid-ranks for ties
    for v in set(allv):
        idx = np.where(allv == v)[0]
        if len(idx) > 1: ranks[idx] = ranks[idx].mean()
    n1 = len(x); obs = ranks[:n1].sum(); mu = n1 * (len(allv) + 1) / 2
    dev = abs(obs - mu); cnt = tot = 0
    for comb in itertools.combinations(range(len(allv)), n1):
        tot += 1; cnt += abs(ranks[list(comb)].sum() - mu) >= dev - 1e-9
    U = obs - n1 * (n1 + 1) / 2
    return float(U), cnt / tot

def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0] * len(ps); run = 0
    for k, i in enumerate(order):
        run = max(run, min(1, (len(ps) - k) * ps[i])); adj[i] = run
    return adj

S = {c: [run_scores(p) for p in fs] for c, fs in CELLS.items()}
summ = {}
for c, runs in S.items():
    for m in ("hub", "task"):
        v = [r[m][0] for r in runs]; b = [r[m][1] for r in runs]
        summ[f"{c}:{m}"] = {"n": len(runs), "seeds": [r["seed"] for r in runs], "above": sum(above(r[m]) for r in runs),
                            "median": float(np.median(v)), "min": float(min(v)), "max": float(max(v)),
                            "ci95_median": boot_ci(v), "median_baseline": float(np.median(b))}
tests = {
    "C1 hub: fixed vs Latin-square": ([r["hub"][0] for r in S["gpt_fixed"]], [r["hub"][0] for r in S["gpt_latin"]]),
    "C2 hub: fixed vs balanced": ([r["hub"][0] for r in S["gpt_fixed"]], [r["hub"][0] for r in S["gpt_balanced"]]),
    "C3 task, gpt: assigned vs identical": ([r["task"][0] for r in S["gpt_assigned"]], [r["task"][0] for r in S["gpt_latin"]]),
    "C3 task, Haiku: assigned vs identical": ([r["task"][0] for r in S["haiku_assigned"]], [r["task"][0] for r in S["haiku_latin"]]),
}
res = {k: mann_whitney_exact(*v) for k, v in tests.items()}
adj = holm([p for _, p in res.values()])
mw = {k: {"U": res[k][0], "p": res[k][1], "p_holm": a} for k, a in zip(res, adj)}
a1_top = sum(r["top_receiver"] == "A1" for r in S["gpt_fixed"])
json.dump({"runs": S, "summary": summ, "tests": mw, "fixed_A1_top": a1_top}, open(os.path.join(OUT, "scores.json"), "w"), indent=1)

L = ["# Confirmatory scores per ANALYSIS_PLAN_2026-10-16.md", ""]
for k, s in summ.items():
    L.append(f"- {k}: n={s['n']} seeds {s['seeds']}; above baseline {s['above']}/{s['n']}; median {s['median']:.2f} "
             f"[{s['ci95_median'][0]:.2f}, {s['ci95_median'][1]:.2f}], range {s['min']:.2f}-{s['max']:.2f}; median baseline {s['median_baseline']:.2f}")
L += ["", f"Fixed names, gpt: agent A1 top receiver in {a1_top}/{len(S['gpt_fixed'])} runs", ""]
for k, v in mw.items():
    L.append(f"- {k}: U={v['U']:.0f}, exact two-sided p={v['p']:.5f}, Holm p={v['p_holm']:.5f}")
L += ["", "## Per run", ""]
for c, runs in S.items():
    for r in runs:
        L.append(f"{c} seed{r['seed']}: hub {r['hub'][0]:.2f}/{r['hub'][1]:.2f} task {r['task'][0]:.2f}/{r['task'][1]:.2f} "
                 f"top {r['top_receiver']} ({r['top_share']:.2f}) done {r['completed']} cost {r['cost']:.2f} "
                 + " ".join(f"{k} {v[0]:.2f}/{v[1]:.2f}" for k, v in r["other"].items())
                 + (f" favlab {r.get('favoured_labels')}" if r.get("favoured_labels") else ""))
open(os.path.join(OUT, "SCORES.md"), "w").write("\n".join(L) + "\n")
print("\n".join(L))
