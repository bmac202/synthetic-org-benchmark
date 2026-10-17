"""Known-answer test of the emergence audit (added 16 Oct 2026, after Evaluation 2).

Does the audit tell apart differentiation whose source we know by construction?  Six
rule-based conditions run in the same environment, under the same private visibility and with
the same scoring as the LLM runs; only the agents' decision rule changes.

  none           one response-threshold rule, all thresholds equal and fixed     nothing to find
  prescribed     the same rule, each agent's thresholds assigned (low on one
                 type) and fixed                                                  prescribed
  generated      the same rule, thresholds start equal and are learned: doing a
                 task type lowers the threshold for it (Theraulaz et al. 1998)    interaction-generated
  generated,     the same, with every agent's thresholds reset to the common
   history wiped  start at round 50                                              generated, then erased
  label bias     identical agents who send tells to the colleague they see
                 labelled "A1" with probability 0.6                              design-induced
  label bias,    the same agents with per-viewer shuffled labels as in the LLM reruns
   labels shuffled (policies.alias_square)                                        artifact largely removed
  label bias,    the same agents, labels shuffled so that every agent is exactly one
   balanced       colleague's "A1"                                                artifact removed

Audit read-outs, per condition over N seeds:
  Detect      R and its shuffled baseline for task type (favoured-type R), hub (tells
              received) and work given opportunity; count of seeds above the 95th percentile.
  Stress-test the label-shuffle rerun of the label-bias condition.
  Attribute   three signatures that need no access to the agents' internals:
              growth     task-type R in rounds 1-50 vs 51-100;
              continuity share of agents whose most-worked type is the same in rounds 1-50
                         and 51-100, against a null permuting second-half favourites;
              same agent across runs  how often an agent's favourite type (or hub rank) recurs
                         across seeds; chance for task type is 1/4.

    python3 -m diffenv.ground_truth --seeds 10 --out diffenv_results/ground_truth_2026-10-16
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import random
from collections import Counter, defaultdict
from typing import Dict, List

import numpy as np

from .env import OpenQueueEnv, TYPE_NAMES, Action, Observation, default_config
from .measures import _spearman, differentiation, specialization, tables_from_log, score_run
from .policies import alias_balanced, alias_square


class ThresholdPolicy:
    """One decision rule for the none / prescribed / generated conditions, so that they differ
    only in where an agent's thresholds come from (Theraulaz, Bonabeau & Deneubourg 1998).
    P(work a known item of type t) = 1 / (1 + theta_t^2); an item the agent does not take is
    passed on to a random colleague.
      mode="equal"     every threshold fixed at theta0 for every agent       (no source)
      mode="assigned"  agent i fixed low on one type, high on the rest      (prescribed)
      mode="learned"   all start at theta0; working t lowers theta_t by xi and raises the
                       others by phi                                         (generated)
    wipe_at: round at which every learned threshold is reset to theta0."""
    name = "rule-threshold"

    def __init__(self, seed: int, agents: List[str], n_types: int = 4, mode: str = "learned",
                 theta0: float = 1.0, xi: float = 0.3, phi: float = 0.1, lo: float = 0.2,
                 hi: float = 3.0, wipe_at: int = None, isolate: bool = False):
        self.rng = random.Random(seed * 7919 + 5)
        self.types = list(TYPE_NAMES[:n_types])
        self.mode, self.theta0, self.xi, self.phi, self.lo, self.hi = mode, theta0, xi, phi, lo, hi
        if mode in ("assigned", "assigned_random"):
            idx = list(range(len(agents)))
            if mode == "assigned_random":      # which agent gets which specialty: redrawn every run
                random.Random(seed * 7919 + 23).shuffle(idx)
            self.theta = {a: {t: (lo if t == self.types[idx[i] % n_types] else hi) for t in self.types}
                          for i, a in enumerate(agents)}
        else:
            self.theta = {a: {t: theta0 for t in self.types} for a in agents}
        self.start = {a: dict(th) for a, th in self.theta.items()}   # what a history wipe restores
        self.wipe_at, self.wiped = wipe_at, False
        self.isolate = isolate      # True: never tell anyone (no coupling between agents)

    def decide(self, obs: Observation) -> Action:
        if self.wipe_at is not None and obs.round >= self.wipe_at and not self.wiped:
            for a in self.theta:              # erase learned history; assigned thresholds stay
                self.theta[a] = dict(self.start[a])
            self.wiped = True
        th = self.theta[obs.agent]
        items = list(obs.known_items)
        self.rng.shuffle(items)
        for item_id, ty, _ in items:
            if self.rng.random() < 1.0 / (1.0 + th[ty] ** 2):
                if self.mode == "learned":
                    for t in self.types:
                        th[t] = min(self.hi, max(self.lo, th[t] - self.xi if t == ty else th[t] + self.phi))
                return Action("work", item=item_id)
        pool = obs.known_items + obs.worked_items
        if pool and obs.others and not self.isolate:
            item = self.rng.choice(pool)[0]
            return Action("tell", item=item, to=self.rng.choice(obs.others))
        return Action("pass")


class LabelBiasPolicy:
    """Identical, random agents (as C0) who send a tell to the colleague they see labelled "A1"
    with probability `bias`.  With `alias`, each viewer sees colleagues under its own labels."""
    name = "rule-label-bias"

    def __init__(self, seed: int, agents: List[str], bias: float = 0.6, alias: str = None):
        """alias=None: fixed names. alias="square": the Latin-square labels used in the LLM reruns
        (policies.alias_square). alias="balanced": policies.alias_balanced, the shuffle the LLM
        runs use with --alias-balanced; every agent carries every colleague label exactly once."""
        self.rng = random.Random(seed * 7919 + 6)
        self.bias = bias
        if alias == "square":
            self.view = alias_square(agents, seed)
        elif alias == "balanced":
            self.view = alias_balanced(agents, seed)
        else:
            self.view = {v: {x: x for x in agents} for v in agents}

    def decide(self, obs: Observation) -> Action:
        if obs.known_items and self.rng.random() < 0.5:
            return Action("work", item=self.rng.choice(obs.known_items)[0])
        pool = obs.known_items + obs.worked_items
        if pool and obs.others:
            item = self.rng.choice(pool)[0]
            seen_a1 = [o for o in obs.others if self.view[obs.agent][o] == "A1"]
            to = seen_a1[0] if seen_a1 and self.rng.random() < self.bias else self.rng.choice(obs.others)
            return Action("tell", item=item, to=to)
        return Action("pass")


CONDITIONS = {
    "none": ("No source (equal fixed thresholds)", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="equal")),
    "prescribed": ("Prescribed (assigned thresholds)", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="assigned")),
    "generated": ("Generated (thresholds learned from own history)", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="learned")),
    "generated_wiped": ("Generated, history wiped at round 50", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="learned", wipe_at=50)),
    "generated_isolated": ("Generated, agents never communicate", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="learned", isolate=True)),
    "prescribed_random": ("Prescribed, specialties reassigned at random each run", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="assigned_random")),
    "prescribed_random_wiped": ("Prescribed, reassigned at random, history wiped at round 50", lambda s, ag, nt: ThresholdPolicy(s, ag, nt, mode="assigned_random", wipe_at=50)),
    "label": ("Design-induced (prefers label “A1”)", lambda s, ag, nt: LabelBiasPolicy(s, ag)),
    "label_shuffled": ("Design-induced, labels shuffled (Latin square, as in the LLM reruns)", lambda s, ag, nt: LabelBiasPolicy(s, ag, alias="square")),
    "label_balanced": ("Design-induced, labels shuffled (balanced)", lambda s, ag, nt: LabelBiasPolicy(s, ag, alias="balanced")),
}


def _r(table, seed, draws):
    r = differentiation(table, seed=seed, n_draws=draws)["R"]
    return {"observed": float(r["observed"]), "null_p95": float(r["null_p95"])}


def _fav_r(type_counts, n_types, seed, draws):
    f = specialization(type_counts, n_types, seed=seed, n_draws=draws)["favoured_type_R"]
    return {"observed": float(f.get("observed", float("nan"))), "null_p95": float(f.get("null_p95", float("nan")))}


def _continuity(halves, agents, seed, draws=1000):
    """Continuity across the midpoint: share of agents whose most-worked type is the same in
    rounds 1-50 and 51-100, against a null that permutes agents' second-half favourites."""
    both = [a for a in agents if halves[(a, 0)] and halves[(a, 1)]]
    f1 = [max(halves[(a, 0)], key=halves[(a, 0)].get) for a in both]
    f2 = [max(halves[(a, 1)], key=halves[(a, 1)].get) for a in both]
    obs = float(np.mean([x == y for x, y in zip(f1, f2)])) if both else float("nan")
    rng = random.Random(seed * 101 + 7)
    null = []
    for _ in range(draws):
        g = f2[:]; rng.shuffle(g)
        null.append(np.mean([x == y for x, y in zip(f1, g)]))
    return {"observed": obs, "null_p95": float(np.percentile(null, 95)), "n_agents": len(both),
            "fav_first": f1, "fav_second": f2}


def run_condition(cond: str, seed: int, draws: int) -> dict:
    cfg = default_config(visibility="private")
    env = OpenQueueEnv(cfg, seed)
    policy = CONDITIONS[cond][1](seed, env.agents, cfg.n_types)
    outcome = env.run(policy)
    nW = cfg.rounds // cfg.window
    tabs = tables_from_log(env.log, env.agents, nW, cfg.window, opportunity=env.opportunity)
    tc = tabs["_type_counts"]
    received = defaultdict(int)
    for m in env.log:
        if m["mtype"] == "tell":
            received[(m["recipient"], m["window"])] += 1
    hub_tab = [("r", w, a, received[(a, w)]) for w in range(nW) for a in env.agents]
    half = nW // 2
    first = {k: v for k, v in tc.items() if k[1] < half}
    second = {k: v for k, v in tc.items() if k[1] >= half}
    halves = defaultdict(lambda: defaultdict(int))
    for (a, w), c in tc.items():
        for ty, k in c.items():
            halves[(a, 0 if w < half else 1)][ty] += k
    tot = defaultdict(Counter)
    for (a, w), c in tc.items():
        tot[a].update(c)
    fav_type = {a: (tot[a].most_common(1)[0][0] if tot[a] else None) for a in env.agents}
    rec_total = Counter(m["recipient"] for m in env.log if m["mtype"] == "tell")
    return {
        "condition": cond, "seed": seed, "completed": outcome["completed"],
        "task_type": _fav_r(tc, cfg.n_types, seed, draws),
        "hub": _r(hub_tab, seed, draws),
        "work_given_opportunity": _r(tabs["activity_given_opportunity"], seed, draws),
        "task_type_first_half": _fav_r(first, cfg.n_types, seed, draws),
        "task_type_second_half": _fav_r(second, cfg.n_types, seed, draws),
        "same_favourite_both_halves": float(np.mean([
            (max(halves[(a, 0)], key=halves[(a, 0)].get) == max(halves[(a, 1)], key=halves[(a, 1)].get))
            if halves[(a, 0)] and halves[(a, 1)] else np.nan for a in env.agents])),
        "continuity": _continuity(halves, env.agents, seed),
        "favourite_type": fav_type,
        "mean_opportunity": float(np.mean(list(env.opportunity.values()))) if env.opportunity else float("nan"),
        "received_by_agent": [rec_total[a] for a in env.agents],
        "agents": env.agents,
    }


def summarize(runs: List[dict]) -> dict:
    def stat(key):
        obs = [r[key]["observed"] for r in runs]
        p95 = [r[key]["null_p95"] for r in runs]
        return {"median": float(np.nanmedian(obs)), "min": float(np.nanmin(obs)), "max": float(np.nanmax(obs)),
                "baseline_median": float(np.nanmedian(p95)),
                "above": int(sum(o > p for o, p in zip(obs, p95))), "n": len(runs)}
    same_type = [np.mean([a["favourite_type"][x] == b["favourite_type"][x] for x in a["agents"]])
                 for a, b in itertools.combinations(runs, 2)]
    hub_rank = [_spearman(a["received_by_agent"], b["received_by_agent"]) for a, b in itertools.combinations(runs, 2)]
    return {k: stat(k) for k in ("task_type", "hub", "work_given_opportunity", "task_type_first_half",
                                 "task_type_second_half", "continuity")} | {
        "same_favourite_both_halves": float(np.nanmedian([r["same_favourite_both_halves"] for r in runs])),
        "same_favourite_type_across_runs": float(np.mean(same_type)),
        "hub_rank_correlation_across_runs": float(np.mean(hub_rank)),
        "same_top_receiver_share": (Counter(r["agents"][int(np.argmax(r["received_by_agent"]))] for r in runs).most_common(1)[0][1] / len(runs)
                                    if any(sum(r["received_by_agent"]) for r in runs) else None),   # None: no tells at all
        "completed_median": float(np.median([r["completed"] for r in runs])),
        "mean_opportunity_median": float(np.median([r["mean_opportunity"] for r in runs])),
        "continuity_pooled": _pooled_continuity(runs),
    }


def _pooled_continuity(runs, draws=2000, seed=0):
    """All agents of all runs pooled: share keeping the same favourite type across the midpoint,
    against a null that permutes second-half favourites within each run."""
    pairs = [(r["continuity"]["fav_first"], r["continuity"]["fav_second"]) for r in runs]
    n = sum(len(f1) for f1, _ in pairs)
    obs = sum(sum(x == y for x, y in zip(f1, f2)) for f1, f2 in pairs) / n
    rng = random.Random(seed)
    null = []
    for _ in range(draws):
        hits = 0
        for f1, f2 in pairs:
            g = f2[:]; rng.shuffle(g)
            hits += sum(x == y for x, y in zip(f1, g))
        null.append(hits / n)
    null = np.array(null)
    return {"observed": float(obs), "null_mean": float(null.mean()), "null_p95": float(np.percentile(null, 95)),
            "p_value": float((null >= obs).mean()), "n_agents": n}


def _boot_ci(diffs, draws=10000, seed=0):
    rng = np.random.default_rng(seed)
    d = np.array(diffs, dtype=float)
    boots = rng.choice(d, size=(draws, len(d)), replace=True).mean(axis=1)
    return {"mean_difference": float(d.mean()), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))], "n_runs": len(d)}


def contrasts(runs: Dict[str, List[dict]]) -> dict:
    """Run-level comparisons with 95% bootstrap intervals over runs (runs, not agents, are the
    independent units). Wipe contrasts are paired by seed: both arms share every round before 50."""
    def cont(r): return r["continuity"]["observed"]
    def task(r): return r["task_type"]["observed"]
    out = {}
    pairs = [("generated", "generated_wiped", cont, "continuity: no wipe minus wipe (paired by seed)"),
             ("prescribed_random", "prescribed_random_wiped", cont, "continuity, prescribed at random: no wipe minus wipe (paired by seed)")]
    for a, b, f, label in pairs:
        if a in runs and b in runs:
            out[label] = _boot_ci([f(x) - f(y) for x, y in zip(runs[a], runs[b])])
    if "generated" in runs and "generated_isolated" in runs:
        a = [task(r) for r in runs["generated"]]; b = [task(r) for r in runs["generated_isolated"]]
        rng = np.random.default_rng(1)
        boots = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(10000)]
        out["task-type R: communication minus no communication (unpaired)"] = {
            "mean_difference": float(np.mean(a) - np.mean(b)),
            "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))], "n_runs": [len(a), len(b)]}
    return out


def table_md(summ: Dict[str, dict]) -> str:
    def c(s):
        if s["median"] != s["median"]:      # nan: measure undefined (e.g. no tells when agents never communicate)
            return "—"
        return f"{s['median']:.2f} ({s['baseline_median']:.2f}) {s['above']}/{s['n']}"
    L = ["| condition | task type | hub | work given opportunity | task type within rounds 1-50 / 51-100 | continuity across the midpoint | same favourite type across runs (chance 0.25) | same top receiver across runs |",
         "|---|---|---|---|---|---|---|---|"]
    for k, s in summ.items():
        L.append(f"| {CONDITIONS[k][0]} | {c(s['task_type'])} | {c(s['hub'])} | {c(s['work_given_opportunity'])} | "
                 f"{c(s['task_type_first_half'])} / {c(s['task_type_second_half'])} | {s['continuity_pooled']['observed']:.2f} (chance {s['continuity_pooled']['null_mean']:.2f}, p95 {s['continuity_pooled']['null_p95']:.2f}) | "
                 f"{s['same_favourite_type_across_runs']:.2f} | " + (f"{round(s['same_top_receiver_share'] * s['task_type']['n'])}/{s['task_type']['n']}" if s['same_top_receiver_share'] is not None else "—") + " |")
    L.append("")
    L.append("Cells: median R (median shuffled baseline, 95th percentile) and seeds above it / seeds. "
             "Same top receiver: the largest number of seeds in which one and the same agent received the most tells.")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--draws", type=int, default=200)
    p.add_argument("--out", default="results/ground_truth")
    p.add_argument("--rebuild", action="store_true", help="re-summarize ground_truth.json in --out without re-running")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    runs, summ = {}, {}
    if a.rebuild:          # re-summarize saved runs without re-simulating
        runs = json.load(open(os.path.join(a.out, "ground_truth.json")))["runs"]
    for cond in CONDITIONS:
        if not a.rebuild:
            runs[cond] = [run_condition(cond, s, a.draws) for s in range(a.seeds)]
        summ[cond] = summarize(runs[cond])
        print(cond, json.dumps({k: (v.get("median", v.get("observed")) if isinstance(v, dict) else v) for k, v in summ[cond].items()}))
    con = contrasts(runs)
    json.dump({"summary": summ, "contrasts": con, "runs": runs}, open(os.path.join(a.out, "ground_truth.json"), "w"), indent=1, default=str)
    md = "# Known-answer test of the emergence audit\n\n" + table_md(summ) + "\n"
    md += "\n## Contrasts (95% bootstrap intervals over runs)\n\n" + "\n".join(
        f"- {k}: {v['mean_difference']:+.2f} [{v['ci95'][0]:+.2f}, {v['ci95'][1]:+.2f}]" for k, v in con.items()) + "\n"
    md += "\nMean items an agent could work per round (median over runs): " + ", ".join(
        f"{CONDITIONS[k][0]} {s['mean_opportunity_median']:.2f}" for k, s in summ.items()) + "\n"
    open(os.path.join(a.out, "ground_truth.md"), "w").write(md)
    print(md)


if __name__ == "__main__":
    main()
