"""Fixtures for the differentiation protocol. Run: python3 -m diffenv.test_measures

Each fixture is built so the right answer is known before the measure sees it. A measure
that fails here is not run on anything real. Fixtures:

  F1  exchangeable noise         — R must sit inside its null (no identity → no repeatability)
  F2  known ICC                  — agents with fixed offsets + noise; R must track the
                                   analytic intraclass correlation within tolerance
  F3  relabel                    — F2's table with labels shuffled within every window; R must
                                   collapse into the null (the relabel guard from the ant work)
  F4  degenerate                 — all agents tie in every window; must report degenerate
                                   windows and R = nan, not a number
  F5  specialists (env, C0+)     — rule-based agents with fixed favourite types and fixed
                                   propensities: R far above null, entropy below null,
                                   favoured-type R above null
  F6  exchangeable (env, C0)     — over many seeds, share of R above the null 95th percentile
                                   must be about 5%, and it must not drift with seed
  F7  parse                      — the LLM action parser on well-formed and malformed replies
"""
from __future__ import annotations

import random
import sys

import numpy as np

from .env import Observation, OpenQueueEnv, default_config
from .measures import differentiation, permute_labels, score_run
from .policies import RuleDeterministicPolicy, RulePolicy, RuleSpecialistPolicy, parse_action

FAIL = []


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAIL.append(name)


def synthetic_table(n_agents=9, n_windows=10, sd_between=0.0, sd_within=1.0, seed=0, org="fx"):
    rng = np.random.default_rng(seed)
    offs = rng.normal(0, sd_between, n_agents)
    rows = []
    for w in range(n_windows):
        for i in range(n_agents):
            rows.append((org, w, f"A{i}", float(offs[i] + rng.normal(0, sd_within))))
    return rows


def f1_exchangeable():
    print("F1 exchangeable noise")
    hits = 0; n = 40
    for s in range(n):
        r = differentiation(synthetic_table(sd_between=0.0, seed=s), seed=s, n_draws=100)["R"]
        hits += r["observed"] > r["null_p95"]
    check("share above null p95 near 5%", hits / n <= 0.15, f"({hits}/{n})")


def f2_known_icc():
    print("F2 known ICC")
    for sb, tol in ((1.0, 0.12), (2.0, 0.12)):
        # pool many agents so the estimate is tight: 60 agents, 10 windows
        r = differentiation(synthetic_table(n_agents=60, sd_between=sb, seed=1), seed=1, n_draws=50)["R"]
        # standardization within window rescales both components by the same factor, so the
        # expected R is the plain ICC sb²/(sb²+1)
        expect = sb ** 2 / (sb ** 2 + 1)
        check(f"R tracks ICC at sd_between={sb}", abs(r["observed"] - expect) < tol,
              f"(R={r['observed']:.3f}, expect {expect:.3f}, null p95 {r['null_p95']:.3f})")
        check(f"R above null at sd_between={sb}", r["observed"] > r["null_p95"])


def f3_relabel():
    print("F3 relabel")
    tab = synthetic_table(n_agents=9, sd_between=2.0, seed=2)
    r0 = differentiation(tab, seed=2, n_draws=100)["R"]
    shuffled = permute_labels(tab, random.Random(99))
    r1 = differentiation(shuffled, seed=2, n_draws=100)["R"]
    check("structured table is above null", r0["observed"] > r0["null_p95"], f"(R={r0['observed']:.3f})")
    check("relabelled table collapses into null", r1["observed"] <= r1["null_p95"],
          f"(R={r1['observed']:.3f}, null p95 {r1['null_p95']:.3f})")


def f4_degenerate():
    print("F4 degenerate")
    rows = [("fx", w, f"A{i}", 5.0) for w in range(10) for i in range(9)]
    d = differentiation(rows, n_draws=10)
    check("all windows reported degenerate", d["degenerate_windows"] == 10, f"({d['degenerate_windows']})")
    check("R is nan, not a number", np.isnan(d["R"]["observed"]))
    # and the literal 13-August rule produces this in the environment
    cfg = default_config(rounds=50)
    env = OpenQueueEnv(cfg, 0); env.run(RuleDeterministicPolicy(0))
    m = score_run(env.log, env.agents, 5, 10, 4, n_draws=10)
    check("deterministic rule: activity degenerate in the env", m["activity"]["degenerate_windows"] == 5,
          f"({m['activity']['degenerate_windows']}/5)")


def f5_specialists():
    print("F5 rule-based specialists (C0+)")
    cfg = default_config()
    env = OpenQueueEnv(cfg, 0); env.run(RuleSpecialistPolicy(0, env.agents, 4))
    m = score_run(env.log, env.agents, 10, 10, 4, seed=0, n_draws=100)
    a = m["activity"]["R"]; e = m["specialization"]["entropy"]; f = m["specialization"]["favoured_type_R"]
    check("activity R above null", a["observed"] > a["null_p95"], f"(R={a['observed']:.3f}, p95 {a['null_p95']:.3f})")
    check("entropy below null (narrower than chance)", e["observed"] < e["null_median"] and e["p_value"] < 0.05,
          f"(H={e['observed']:.3f}, null {e['null_median']:.3f}, p={e['p_value']:.3f})")
    check("favoured-type R above null", f["observed"] > f["null_p95"], f"(R={f['observed']:.3f}, p95 {f['null_p95']:.3f})")


def f6_floor_sweep(n=40):
    print(f"F6 exchangeable rule (C0) over {n} seeds")
    hits = {"activity": 0, "interaction": 0, "isolation": 0}
    obs = {k: [] for k in hits}; nulls = {k: [] for k in hits}
    ent_hits = 0
    for s in range(n):
        cfg = default_config()
        env = OpenQueueEnv(cfg, s); env.run(RulePolicy(s))
        m = score_run(env.log, env.agents, 10, 10, 4, seed=s, n_draws=100)
        for k in hits:
            r = m[k]["R"]; obs[k].append(r["observed"]); nulls[k].append(r["null_median"])
            hits[k] += r["observed"] > r["null_p95"]
        ent_hits += m["specialization"]["entropy"]["p_value"] < 0.05
    for k in hits:
        check(f"{k}: share above p95 ≈ 5%", hits[k] / n <= 0.15, f"({hits[k]}/{n}; mean obs {np.mean(obs[k]):.3f} vs mean null median {np.mean(nulls[k]):.3f})")
    check("entropy: share below null ≈ 5%", ent_hits / n <= 0.15, f"({ent_hits}/{n})")


def f7_parse():
    print("F7 action parser")
    obs = Observation("A3", 0, 0, [(12, "alpha", 0)], [], set(), [], ["A0", "A1"], [])
    check("work", parse_action("work 12", obs).kind == "work" and parse_action("work 12", obs).item == 12)
    check("Work item 12.", parse_action("Work item 12.", obs).item == 12)
    check("tell A1 12", (lambda a: a.kind == "tell" and a.to == "A1" and a.item == 12)(parse_action("tell A1 12", obs)))
    check("tell A1 about item 12", (lambda a: a.kind == "tell" and a.to == "A1" and a.item == 12)(parse_action("tell A1 about item 12", obs)))
    check("pass", parse_action("pass", obs).kind == "pass")
    check("leave", parse_action("leave", obs).kind == "leave")
    check("garbage → pass", parse_action("I think I will do nothing", obs).kind == "pass")
    check("tell without item → pass", parse_action("tell A1", obs).kind == "pass")


if __name__ == "__main__":
    for fn in (f1_exchangeable, f2_known_icc, f3_relabel, f4_degenerate, f5_specialists, f6_floor_sweep, f7_parse):
        fn()
    print("\nFAILED:" if FAIL else "\nALL FIXTURES PASS", FAIL or "")
    sys.exit(1 if FAIL else 0)
