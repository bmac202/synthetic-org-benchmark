"""Run one or more conditions and write specimens.

    python3 -m diffenv.run --condition c0 --seeds 0 1 2
    python3 -m diffenv.run --condition c0plus --seeds 0 1 2
    python3 -m diffenv.run --condition c1 --backend anthropic --model claude-haiku-4-5 --seeds 0 1 2
    python3 -m diffenv.run --condition c2 --backend openai --model gpt-4o-mini --seeds 0
    python3 -m diffenv.run --condition c1 --backend mock --seeds 0          # offline pipeline check
    ... --competence   (C4 factor)      ... --exit   (C5 factor)

A specimen is one JSON file per run: configuration, complete log, derived measures with
their nulls, outcome, and for LLM runs the model name, every system prompt, temperature,
seed and every raw reply. It is the shareable unit and the thing the repository publishes.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import Dict, List

from .budget import Budget, BudgetExceeded, CallJournal
from .env import OpenQueueEnv, default_config, TYPE_NAMES
from .keys import describe as describe_keys, load_keys
from .measures import score_run
from .policies import (AnthropicBackend, LLMPolicy, MockBackend, OpenAIBackend, RulePolicy,
                       RuleDeterministicPolicy, RuleSpecialistPolicy)

CONDITIONS = {
    "c0": "rule-based exchangeable (floor)",
    "c0det": "rule-based deterministic (degenerate fixture)",
    "c0plus": "rule-based specialists with fixed propensities (rule-based positive control)",
    "c1": "LLM, identical prompt, no roles (the finding)",
    "c2": "LLM, role-prompted (positive control)",
    "c3": "LLM, persona-prompted, no roles",
}


def competence_table(agents: List[str], seed: int, n_types: int) -> Dict[str, Dict[str, float]]:
    """C4: each agent is good at one type (p=0.95) and poor at the others (p=0.35).
    Which type is drawn at random per agent, so nothing in the prompt reveals it."""
    rng = random.Random(seed * 31 + 11)
    types = list(TYPE_NAMES[:n_types])
    out = {}
    for a in agents:
        good = rng.choice(types)
        out[a] = {ty: (0.95 if ty == good else 0.35) for ty in types}
    return out


def spec_id_for(cond, backend, model, seed, competence, exit_allowed, visibility="sampled", alias=False):
    factors = []
    if competence: factors.append("competence")
    if exit_allowed: factors.append("exit")
    if visibility == "private": factors.append("private")
    if alias == "balanced": factors.append("aliasbal")
    elif alias: factors.append("alias")
    return f"{cond}" + ("+" + "+".join(factors) if factors else "") + \
           (f"-{backend}-{model}" if cond in ("c1", "c2", "c3") else "") + f"-seed{seed}", factors


def make_policy(cond: str, env: OpenQueueEnv, seed: int, backend: str, model: str, temperature: float,
                budget=None, journal=None, spec_id: str = "", alias: bool = False):
    agents = env.agents
    if cond == "c0":
        return RulePolicy(seed)
    if cond == "c0det":
        return RuleDeterministicPolicy(seed)
    if cond == "c0plus":
        return RuleSpecialistPolicy(seed, agents, env.cfg.n_types)
    variant = {"c1": "exchangeable", "c2": "role", "c3": "persona"}[cond]
    if backend == "mock":
        be = MockBackend(seed)
    elif backend == "anthropic":
        be = AnthropicBackend(model)
    elif backend == "openai":
        be = OpenAIBackend(model)
    else:
        raise SystemExit(f"unknown backend {backend}")
    return LLMPolicy(be, agents, variant=variant, temperature=temperature, seed=seed,
                     n_types=env.cfg.n_types, exit_allowed=env.cfg.exit_allowed,
                     budget=budget, journal=journal, spec_id=spec_id, alias=alias)


def usage_this_run(policy: LLMPolicy) -> dict:
    """Tokens and cost for the real calls this run made (replayed journal entries excluded)."""
    from .budget import cost_usd
    api = [r for r in policy.raw if r.get("source") == "api"]
    it = sum(r["usage"].get("input_tokens", 0) for r in api)
    ot = sum(r["usage"].get("output_tokens", 0) for r in api)
    return {"provider": policy.backend.provider, "model": policy.backend.model, "calls": len(api),
            "replayed": policy.replayed, "input_tokens": it, "output_tokens": ot,
            "cost_usd": round(cost_usd(policy.backend.model, it, ot), 6),
            "mean_latency_s": round(sum(r["usage"].get("latency_s", 0) for r in api) / len(api), 3) if api else None}


def run_one(cond: str, seed: int, backend: str = "mock", model: str = "", temperature: float = 1.0,
            competence: bool = False, exit_allowed: bool = False, n_draws: int = 200,
            out_dir: str = "specimens", verbose: bool = True, budget: Budget = None,
            journal_dir: str = None, **cfg_over) -> dict:
    cfg = default_config(exit_allowed=exit_allowed, **cfg_over)
    env = OpenQueueEnv(cfg, seed)
    if competence:
        cfg["competence"] = competence_table(env.agents, seed, cfg.n_types)
    is_llm = cond in ("c1", "c2", "c3")
    alias = (cfg.get("alias") or False) if is_llm else False   # False, True (Latin square) or "balanced"
    spec_id, factors = spec_id_for(cond, backend, model, seed, competence, exit_allowed, cfg.get("visibility", "sampled"), alias)
    if budget is None:
        budget = Budget.from_env()
    journal = None
    if is_llm:
        if backend != "mock":
            load_keys()
        jpath = os.path.join(journal_dir, spec_id.replace("/", "_") + ".jsonl") if journal_dir else None
        journal = CallJournal(jpath)
        planned = cfg.n_agents * cfg.rounds - len(journal)
        if backend != "mock":
            budget.refuse_if_large(planned)
    policy = make_policy(cond, env, seed, backend, model, temperature, budget, journal, spec_id, alias=alias)
    t0 = time.time()
    outcome = env.run(policy)
    elapsed = time.time() - t0
    present_until = None
    if exit_allowed:
        left = {m["sender"]: m["round"] for m in env.log if m["mtype"] == "leave"}
        present_until = {a: left.get(a, cfg.rounds) for a in env.agents}
    n_windows = cfg.rounds // cfg.window
    measures = score_run(env.log, env.agents, n_windows, cfg.window, cfg.n_types,
                         present_until=present_until, seed=seed, n_draws=n_draws,
                         opportunity=env.opportunity)
    spec = {
        "specimen_id": spec_id, "condition": cond, "condition_desc": CONDITIONS[cond],
        "factors": factors, "seed": seed, "config": dict(cfg), "agents": env.agents,
        "provider": (policy.backend.provider if isinstance(policy, LLMPolicy) else None),
        "model": (policy.backend.model if isinstance(policy, LLMPolicy) else None),
        "usage_this_run": usage_this_run(policy) if isinstance(policy, LLMPolicy) else None,
        "budget_cumulative": budget.report() if isinstance(policy, LLMPolicy) else None,
        "policy": getattr(policy, "name", type(policy).__name__),
        "llm": policy.prompt_record() if isinstance(policy, LLMPolicy) else None,
        "outcome": outcome, "derived_measures": measures, "elapsed_s": round(elapsed, 2),
        "log": env.log,
        "opportunity": {f"{a}|{r}": v for (a, r), v in env.opportunity.items()},
        "raw_replies": policy.raw if isinstance(policy, LLMPolicy) else None,
        "written": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, spec_id.replace("/", "_") + ".json")
    with open(path, "w") as f:
        json.dump(spec, f, indent=1, default=str)
    if verbose:
        print(summary_line(spec))
    return spec


def _fmt(m):
    if m is None or "observed" not in m:
        return "   n/a"
    o = m["observed"]
    return f"{o:6.3f} (null {m.get('null_median', float('nan')):.3f}/{m.get('null_p95', float('nan')):.3f})"


def summary_line(spec: dict) -> str:
    d = spec["derived_measures"]
    llm = spec.get("llm") or {}
    parts = [
        f"{spec['specimen_id']:<40}",
        f"R_act {_fmt(d['activity']['R'])}",
        f"R_int {_fmt(d['interaction']['R'])}",
        f"R_iso {_fmt(d['isolation']['R'])}",
        f"R_act|opp {_fmt(d.get('activity_given_opportunity', {}).get('R'))}",
        f"entropy {_fmt(d['specialization']['entropy'])}",
        f"favR {_fmt(d['specialization']['favoured_type_R'])}",
        f"jac {_fmt(d['partner_consistency'])}",
        f"done {spec['outcome']['completed']}/{spec['outcome']['items_arrived']}",
        f"degen {d['activity']['degenerate_windows']}",
    ]
    if llm:
        parts.append(f"unparse {llm['unparseable']}/{llm['calls']}")
    return " | ".join(parts)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--condition", required=True, choices=list(CONDITIONS))
    p.add_argument("--seeds", type=int, nargs="+", default=[0])
    p.add_argument("--backend", default="mock", choices=["mock", "anthropic", "openai"])
    p.add_argument("--model", default="")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--competence", action="store_true")
    p.add_argument("--exit", dest="exit_allowed", action="store_true")
    p.add_argument("--visibility", default="sampled", choices=["sampled", "private"], help="sampled: agents sample m open items per round; private: each item is revealed to one agent only")
    p.add_argument("--no-shuffle", dest="shuffle_view", action="store_false", help="present known items sorted by id (the pre-30-Sept behaviour; list-position bias)")
    p.add_argument("--alias", action="store_true", help="show each agent its colleagues under per-viewer labels balanced as a Latin square (removes name-preference bias; LLM conditions only)")
    p.add_argument("--alias-balanced", action="store_true", help="per-viewer labels in which every agent carries every colleague label exactly once (own name A0 for all); fixes the Latin-square residual. Implies --alias")
    p.add_argument("--draws", type=int, default=200)
    p.add_argument("--out", default="specimens")
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--agents", type=int, default=9)
    p.add_argument("--window", type=int, default=10)
    p.add_argument("--max-calls", type=int, default=None, help="hard cap on real API calls this invocation (default MAX_API_CALLS env or 25)")
    p.add_argument("--max-cost", type=float, default=None, help="hard cap on estimated USD this invocation (default MAX_COST_USD env or 1.00)")
    p.add_argument("--full-run", action="store_true", help="required for any run planning more calls than --max-calls")
    p.add_argument("--journal-dir", default="results/journal", help="where completed calls are journaled for resume")
    a = p.parse_args(argv)
    budget = Budget.from_env(max_calls=a.max_calls, max_cost_usd=a.max_cost, full_run=a.full_run or None)
    print("keys:", describe_keys() if a.backend != "mock" else "not needed", "| budget:", budget.report())
    try:
        for s in a.seeds:
            run_one(a.condition, s, a.backend, a.model, a.temperature, a.competence, a.exit_allowed,
                    a.draws, a.out, budget=budget, journal_dir=a.journal_dir,
                    rounds=a.rounds, n_agents=a.agents, window=a.window,
                    visibility=a.visibility, shuffle_view=a.shuffle_view, alias=("balanced" if a.alias_balanced else a.alias))
    except BudgetExceeded as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        print("budget at exit:", json.dumps(budget.report()))


if __name__ == "__main__":
    main()
