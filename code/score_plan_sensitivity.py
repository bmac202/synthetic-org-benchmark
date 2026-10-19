"""Sensitivity analyses for ANALYSIS_PLAN_2026-10-16.md (added 17 Oct 2026).

1. Post-plan runs only: drops every run made before the plan was written
   (gpt fixed/Latin seeds 0-2, Haiku Latin seeds 0-2, specialty seeds 0-1).
2. Paired by seed: exact Wilcoxon signed-rank on the same seeds across conditions
   (the environment is seeded identically; behavior then diverges).
Reads diffenv_results/plan_scores_2026-10-17/scores.json; writes SENSITIVITY.md beside it.
"""
import itertools, json, os
import numpy as np
from score_plan import mann_whitney_exact, holm

D = "diffenv_results/plan_scores_2026-10-17"
S = json.load(open(os.path.join(D, "scores.json")))["runs"]
PRE = {"gpt_fixed": {0, 1, 2}, "gpt_latin": {0, 1, 2}, "haiku_latin": {0, 1, 2},
       "gpt_assigned": {0, 1}, "haiku_assigned": {0, 1}, "gpt_balanced": set()}
COMP = [("C1 hub: fixed vs Latin-square", "gpt_fixed", "gpt_latin", "hub"),
        ("C2 hub: fixed vs balanced", "gpt_fixed", "gpt_balanced", "hub"),
        ("C3 task, gpt: assigned vs identical", "gpt_assigned", "gpt_latin", "task"),
        ("C3 task, Haiku: assigned vs identical", "haiku_assigned", "haiku_latin", "task")]

def wilcoxon_exact(d):
    d = np.asarray([x for x in d if x != 0]); n = len(d)
    r = np.abs(d).argsort().argsort() + 1.0
    obs = r[d > 0].sum(); mu = n * (n + 1) / 4; dev = abs(obs - mu); cnt = 0
    for signs in itertools.product((0, 1), repeat=n):
        cnt += abs(sum(rk for rk, s in zip(r, signs) if s) - mu) >= dev - 1e-9
    return float(obs), cnt / 2 ** n, n

L = ["# Sensitivity analyses", "", "## 1. Post-plan runs only", ""]
ps, rows = [], []
for name, a, b, m in COMP:
    A = [r for r in S[a] if r["seed"] not in PRE[a]]; B = [r for r in S[b] if r["seed"] not in PRE[b]]
    U, p = mann_whitney_exact([r[m][0] for r in A], [r[m][0] for r in B])
    ka = sum(r[m][0] > r[m][1] for r in A); kb = sum(r[m][0] > r[m][1] for r in B)
    rows.append((name, len(A), ka, np.median([r[m][0] for r in A]), len(B), kb, np.median([r[m][0] for r in B]), U)); ps.append(p)
for (name, na, ka, ma, nb, kb, mb, U), p, ph in zip(rows, ps, holm(ps)):
    L.append(f"- {name}: {ka}/{na} above (median {ma:.2f}) vs {kb}/{nb} above (median {mb:.2f}); U={U:.0f}, exact p={p:.5f}, Holm p={ph:.5f}")
extra = sum(r["top_receiver"] == "A1" for r in S["gpt_fixed"] if r["seed"] not in PRE["gpt_fixed"])
L.append(f"- Post-plan fixed-name gpt runs with 'A1' as top receiver: {extra}/{len([r for r in S['gpt_fixed'] if r['seed'] not in PRE['gpt_fixed']])}")
L += ["", "## 2. Paired by seed (exact Wilcoxon signed-rank, all 10 seeds)", ""]
ps, rows = [], []
for name, a, b, m in COMP:
    A = {r["seed"]: r[m][0] for r in S[a]}; B = {r["seed"]: r[m][0] for r in S[b]}
    seeds = sorted(set(A) & set(B)); W, p, n = wilcoxon_exact([A[s] - B[s] for s in seeds])
    pos = sum(A[s] > B[s] for s in seeds); rows.append((name, n, pos, W)); ps.append(p)
for (name, n, pos, W), p, ph in zip(rows, ps, holm(ps)):
    L.append(f"- {name}: first condition higher in {pos}/{n} seed pairs; W+={W:.0f}, exact p={p:.5f}, Holm p={ph:.5f}")
open(os.path.join(D, "SENSITIVITY.md"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
