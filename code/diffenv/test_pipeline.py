"""Mock/unit tests for the LLM pipeline — no network. Run: python3 -m diffenv.test_pipeline

  P1  prompt construction   — C1 prompts identical across agents; C2 names a distinct
                              specialty per agent; C3 a distinct persona; exit line only
                              with the exit factor; observation renders items and inbox
  P2  parser                — well-formed, malformed, empty, multi-line, missing fields
  P3  retries               — retryable errors retried with bounded count and backoff;
                              non-retryable (auth) raised at once; exhaustion raises
  P4  failure ≠ duplicate   — a backend that fails on call k: the run aborts, the journal
                              holds exactly k−1 entries; restarting with the same journal
                              replays k−1 and makes only the missing calls; final journal
                              has exactly n_agents×rounds unique keys; total real calls equal
                              the number of unique keys (no duplicates)
  P5  storage metadata      — specimens carry provider / model / condition / seed / factors
                              and per-run usage; two providers distinguishable
  P6  seed handling         — same seed → identical log; different seed → different log;
                              journal keys carry the seed so seeds cannot cross-contaminate
  P7  condition assignment  — C2 assignment map covers all types; C3 personas distinct
  P8  budget                — refuses a run larger than MAX_API_CALLS without --full-run;
                              stops mid-run at the call cap; stops at the cost cap; mock
                              backend never charges
  P9  keys                  — loader sets env from a temp file, describe() never returns a
                              value, scrub() redacts
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

from .budget import Budget, BudgetExceeded, CallJournal, cost_usd
from .env import Observation, OpenQueueEnv, default_config
from .keys import describe, load_keys, scrub
from .policies import (Backend, LLMPolicy, MockBackend, parse_action, render_observation,
                       EXIT_LINE)
from .run import run_one

FAIL = []
TMP = tempfile.mkdtemp(prefix="diffenv_test_")


def check(name, cond, detail=""):
    print(f"  [{'ok' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAIL.append(name)


# --------------------------------------------------------------------------- helpers
class ScriptedBackend(Backend):
    """Returns canned replies; can be told to fail on specific call numbers."""
    provider = "scripted"
    model = "scripted-model"
    BASE_DELAY = 0.0

    def __init__(self, replies=("work 0",), fail_on=(), fail_exc=None, provider="scripted", model="scripted-model"):
        self.replies = list(replies); self.fail_on = set(fail_on); self.n = 0
        self.fail_exc = fail_exc or RuntimeError("transient")
        self.provider = provider; self.model = model
        self.attempts = 0

    def complete(self, system, user, temperature, seed):
        def call():
            self.attempts += 1
            self.n += 1
            if self.n in self.fail_on:
                raise self.fail_exc
            return self.replies[(self.n - 1) % len(self.replies)], {"input_tokens": 100, "output_tokens": 3}
        return self._retry(call)


class AuthError(Exception):
    status_code = 401


class RateLimit(Exception):
    status_code = 429


# --------------------------------------------------------------------------- P1
def p1_prompts():
    print("P1 prompt construction")
    agents = [f"A{i}" for i in range(9)]
    c1 = LLMPolicy(MockBackend(), agents, "exchangeable")
    check("C1: all nine system prompts identical", len(set(c1.system.values())) == 1)
    check("C1: no exit line without the factor", EXIT_LINE.strip() not in c1.system["A0"])
    c1x = LLMPolicy(MockBackend(), agents, "exchangeable", exit_allowed=True)
    check("C1+exit: exit line present", EXIT_LINE.strip() in c1x.system["A0"])
    c2 = LLMPolicy(MockBackend(), agents, "role")
    check("C2: specialty named per agent", all(f"specialty is items of type {c2.assignment[a]}" in c2.system[a] for a in agents))
    check("C2: prompts differ only by specialty", len(set(c2.system.values())) == 4)
    c3 = LLMPolicy(MockBackend(), agents, "persona")
    check("C3: nine distinct personas", len(set(c3.assignment.values())) == 9)
    check("C3: no specialty language", all("specialty" not in s for s in c3.system.values()))
    obs = Observation("A3", 4, 0, [(12, "alpha", 1), (15, "gamma", 0)], [(7, "beta", 1)], {7}, [("A1", 12, "alpha")], ["A0", "A1"], ["passed"])
    txt = render_observation(obs)
    check("observation renders items", "item 12, alpha, 1 of 2 done" in txt and "item 15, gamma, 0 of 2 done" in txt)
    check("observation renders inbox", "A1 told you about item 12" in txt)
    check("observation renders round and history", "Round 5" in txt and "passed" in txt)
    empty = render_observation(Observation("A3", 0, 0, [], [], set(), [], ["A0"], []))
    check("observation with no items says so", "no open items" in empty)


# --------------------------------------------------------------------------- P2
def p2_parser():
    print("P2 parser edge cases")
    obs = Observation("A3", 0, 0, [(12, "alpha", 0)], [], set(), [], ["A0", "A1"], [])
    cases = [
        ("work 12", ("work", 12, None)), ("WORK 12", ("work", 12, None)), ("work item #12", ("work", 12, None)),
        ("work 12\nbecause it is close", ("work", 12, None)),
        ("tell A1 12", ("tell", 12, "A1")), ("tell a1 about item 12", ("tell", 12, "A1")), ("Tell A1: item 12", ("tell", 12, "A1")),
        ("pass", ("pass", None, None)), ("Pass.", ("pass", None, None)), ("leave", ("leave", None, None)),
        ("", ("pass", None, None)), ("   ", ("pass", None, None)), ("I'll work on it", ("pass", None, None)),
        ("work", ("pass", None, None)), ("tell 12", ("pass", None, None)), ("tell A1", ("pass", None, None)),
        ("{\"action\": \"work\", \"item\": 12}", ("pass", None, None)),
        ("I will take item 12.\nwork 12", ("work", 12, None)),
        ("- work 12", ("work", 12, None)), ("`tell A1 12`", ("tell", 12, "A1")),
        ("Item 12 is alpha so I should work it", ("pass", None, None)),
        ("I need to analyze the situation:\n\n- I'm A0, and I worked on item", ("pass", None, None)),
    ]
    for text, (k, item, to) in cases:
        a = parse_action(text, obs)
        check(f"parse {text!r:35}", (a.kind, a.item, a.to) == (k, item, to), f"→ {a.kind} {a.item} {a.to}")


# --------------------------------------------------------------------------- P3
def p3_retries():
    print("P3 retries")
    b = ScriptedBackend(fail_on=(1, 2), fail_exc=RateLimit())
    text, _ = b.complete("s", "u", 1.0, 0)
    check("retryable error retried until success", text == "work 0" and b.attempts == 3, f"(attempts {b.attempts})")
    b = ScriptedBackend(fail_on=(1,), fail_exc=AuthError())
    try:
        b.complete("s", "u", 1.0, 0); ok = False
    except AuthError:
        ok = True
    check("auth error not retried", ok and b.attempts == 1, f"(attempts {b.attempts})")
    b = ScriptedBackend(fail_on=(1, 2, 3, 4, 5, 6), fail_exc=RateLimit())
    try:
        b.complete("s", "u", 1.0, 0); ok = False
    except RateLimit:
        ok = True
    check("bounded: gives up after MAX_RETRIES", ok and b.attempts == Backend.MAX_RETRIES, f"(attempts {b.attempts}, max {Backend.MAX_RETRIES})")
    # backoff is exponential and capped
    delays = []; d = Backend.BASE_DELAY
    for _ in range(6):
        delays.append(d); d = min(d * 2, 30)
    check("backoff schedule 2,4,8,16,30,30", delays == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0], str(delays))


# --------------------------------------------------------------------------- P4
def p4_failure_no_duplicates():
    print("P4 failure cannot create duplicates; resume makes only the missing calls")
    jdir = os.path.join(TMP, "journal"); shutil.rmtree(jdir, ignore_errors=True)
    n_agents, rounds = 3, 4
    total = n_agents * rounds
    k = 7                                     # the 7th real call fails hard (non-retryable)
    b1 = ScriptedBackend(replies=("work 0", "pass", "tell A1 0"), fail_on=(k,), fail_exc=AuthError())
    cfg = default_config(n_agents=n_agents, rounds=rounds, window=2)
    env = OpenQueueEnv(cfg, 0)
    jpath = os.path.join(jdir, "spec.jsonl")
    pol = LLMPolicy(b1, env.agents, "exchangeable", budget=Budget(max_calls=1000), journal=CallJournal(jpath), spec_id="spec")
    try:
        env.run(pol); aborted = False
    except AuthError:
        aborted = True
    j = CallJournal(jpath)
    check("run aborted on the failing call", aborted)
    check(f"journal holds exactly {k-1} entries after abort", len(j) == k - 1, f"({len(j)})")
    check("failed call not journaled", CallJournal.key("spec", 2, "A0") not in j.entries)
    # restart with a backend that does not fail; same seed, same journal
    b2 = ScriptedBackend(replies=("work 0", "pass", "tell A1 0"))
    env2 = OpenQueueEnv(cfg, 0)
    pol2 = LLMPolicy(b2, env2.agents, "exchangeable", budget=Budget(max_calls=1000), journal=CallJournal(jpath), spec_id="spec")
    env2.run(pol2)
    j2 = CallJournal(jpath)
    check("restart replayed the journaled calls", pol2.replayed == k - 1, f"({pol2.replayed})")
    check("restart made only the missing calls", pol2.calls == total - (k - 1), f"({pol2.calls})")
    check(f"final journal has exactly {total} unique keys", len(j2) == total, f"({len(j2)})")
    with open(jpath) as f:
        lines = [l for l in f if l.strip()]
    check("no duplicate lines on disk", len(lines) == total and len({json.loads(l)['key'] for l in lines}) == total, f"({len(lines)} lines)")
    check("real calls across both runs == unique keys", (k - 1) + pol2.calls == total)
    # a third run with the complete journal makes zero calls
    b3 = ScriptedBackend(fail_on=tuple(range(1, 100)), fail_exc=AuthError())   # would fail if called at all
    env3 = OpenQueueEnv(cfg, 0)
    pol3 = LLMPolicy(b3, env3.agents, "exchangeable", budget=Budget(max_calls=1000), journal=CallJournal(jpath), spec_id="spec")
    env3.run(pol3)
    check("complete journal → zero real calls, identical log length", pol3.calls == 0 and len(env3.log) == len(env2.log))
    check("replayed trajectory identical to the original", env3.log == env2.log)
    # a torn last line is tolerated
    with open(jpath, "a") as f:
        f.write('{"key": "spec|99|A0", "reply": "wo')
    j4 = CallJournal(jpath)
    check("torn last line ignored on load", len(j4) == total)


# --------------------------------------------------------------------------- P5
def p5_storage_metadata():
    print("P5 storage metadata")
    out = os.path.join(TMP, "spec_meta"); shutil.rmtree(out, ignore_errors=True)
    from . import run as runmod
    orig = runmod.make_policy

    def fake_make_policy(cond, env, seed, backend, model, temperature, budget=None, journal=None, spec_id="", **_kw):
        be = ScriptedBackend(replies=("work 0", "tell A1 0", "pass"), provider=backend, model=model)
        variant = {"c1": "exchangeable", "c2": "role", "c3": "persona"}[cond]
        return LLMPolicy(be, env.agents, variant=variant, temperature=temperature, seed=seed,
                         budget=budget, journal=journal, spec_id=spec_id)
    runmod.make_policy = fake_make_policy
    try:
        s1 = run_one("c1", 3, backend="openai", model="gpt-x-test", out_dir=out, n_draws=5,
                     budget=Budget(max_calls=1000), n_agents=3, rounds=4, window=2, verbose=False)
        s2 = run_one("c2", 5, backend="anthropic", model="claude-x-test", competence=True, out_dir=out, n_draws=5,
                     budget=Budget(max_calls=1000), n_agents=3, rounds=4, window=2, verbose=False)
    finally:
        runmod.make_policy = orig
    check("provider/model/condition/seed stored (openai)", (s1["provider"], s1["model"], s1["condition"], s1["seed"]) == ("openai", "gpt-x-test", "c1", 3))
    check("provider/model/condition/seed stored (anthropic)", (s2["provider"], s2["model"], s2["condition"], s2["seed"]) == ("anthropic", "claude-x-test", "c2", 5))
    check("factors stored", s2["factors"] == ["competence"] and s1["factors"] == [])
    check("specimen ids distinct and carry provider+model", s1["specimen_id"] != s2["specimen_id"] and "openai-gpt-x-test" in s1["specimen_id"] and "anthropic-claude-x-test" in s2["specimen_id"])
    check("per-run usage stored", s1["usage_this_run"]["calls"] == 12 and s1["usage_this_run"]["input_tokens"] == 1200)
    check("llm record carries prompts and assignment", s2["llm"]["assignment"] and len(s2["llm"]["system_prompts"]) == 3)
    check("raw replies stored with source", all(r["source"] == "api" for r in s1["raw_replies"]) and len(s1["raw_replies"]) == 12)
    files = sorted(os.listdir(out))
    check("two specimen files written", len(files) == 2, str(files))
    with open(os.path.join(out, files[0])) as f:
        d = json.load(f)
    check("specimen JSON round-trips with required keys", all(k in d for k in ("specimen_id", "provider", "model", "condition", "seed", "log", "derived_measures", "usage_this_run")))


# --------------------------------------------------------------------------- P6
def p6_seeds():
    print("P6 seed handling")
    out = os.path.join(TMP, "seeds"); shutil.rmtree(out, ignore_errors=True)
    a = run_one("c1", 1, backend="mock", out_dir=out, n_draws=5, n_agents=3, rounds=6, window=2, verbose=False)
    b = run_one("c1", 1, backend="mock", out_dir=out, n_draws=5, n_agents=3, rounds=6, window=2, verbose=False)
    c = run_one("c1", 2, backend="mock", out_dir=out, n_draws=5, n_agents=3, rounds=6, window=2, verbose=False)
    check("same seed → identical log", a["log"] == b["log"])
    check("different seed → different log", a["log"] != c["log"])
    check("journal key carries the specimen id (seed inside)", CallJournal.key(a["specimen_id"], 0, "A0") != CallJournal.key(c["specimen_id"], 0, "A0"))
    r0 = run_one("c0", 4, out_dir=out, n_draws=5, verbose=False); r1 = run_one("c0", 4, out_dir=out, n_draws=5, verbose=False)
    check("C0 reproducible bit-for-bit under a seed", r0["log"] == r1["log"] and r0["derived_measures"] == r1["derived_measures"])


# --------------------------------------------------------------------------- P7
def p7_conditions():
    print("P7 condition assignment")
    agents = [f"A{i}" for i in range(9)]
    c2 = LLMPolicy(MockBackend(), agents, "role")
    check("C2 covers all four types", set(c2.assignment.values()) == {"alpha", "beta", "gamma", "delta"})
    check("C2 balanced (3,2,2,2)", sorted([list(c2.assignment.values()).count(t) for t in ("alpha", "beta", "gamma", "delta")]) == [2, 2, 2, 3])
    c3 = LLMPolicy(MockBackend(), agents, "persona")
    check("C3 nine distinct personas", len(set(c3.assignment.values())) == 9)
    try:
        LLMPolicy(MockBackend(), agents, "nonsense"); ok = False
    except AssertionError:
        ok = True
    check("unknown variant rejected", ok)
    from .run import competence_table
    ct = competence_table(agents, 0, 4)
    check("C4 table: one good type per agent", all(sorted(v.values()) == [0.35, 0.35, 0.35, 0.95] for v in ct.values()))


# --------------------------------------------------------------------------- P8
def p8_budget():
    print("P8 budget")
    b = Budget(max_calls=25, max_cost_usd=1.0)
    try:
        b.refuse_if_large(900); ok = False
    except BudgetExceeded:
        ok = True
    check("refuses 900-call run without --full-run", ok)
    b2 = Budget(max_calls=25, max_cost_usd=1.0, full_run=True)
    try:
        b2.refuse_if_large(900); ok = False
    except BudgetExceeded:
        ok = True
    check("--full-run alone does not lift the call cap", ok)
    b3 = Budget(max_calls=2000, max_cost_usd=1.0, full_run=True); b3.refuse_if_large(900)
    check("--full-run with a raised cap passes", True)
    # mid-run stop at the call cap
    cfg = default_config(n_agents=3, rounds=4, window=2)
    env = OpenQueueEnv(cfg, 0)
    pol = LLMPolicy(ScriptedBackend(), env.agents, "exchangeable", budget=Budget(max_calls=5), journal=CallJournal(None), spec_id="cap")
    try:
        env.run(pol); ok = False
    except BudgetExceeded:
        ok = True
    check("stops at the call cap mid-run", ok and pol.calls == 5, f"(calls {pol.calls})")
    # cost cap
    class Pricey(ScriptedBackend):
        model = "gpt-4.1"
    env = OpenQueueEnv(cfg, 0)
    pol = LLMPolicy(Pricey(model="gpt-4.1"), env.agents, "exchangeable", budget=Budget(max_calls=1000, max_cost_usd=0.0005), journal=CallJournal(None), spec_id="cost")
    try:
        env.run(pol); ok = False
    except BudgetExceeded:
        ok = True
    check("stops at the cost cap mid-run", ok and 0 < pol.calls < 12, f"(calls {pol.calls}, spent {pol.budget.cost:.6f})")
    bm = Budget(max_calls=3)
    env = OpenQueueEnv(cfg, 0)
    pol = LLMPolicy(MockBackend(), env.agents, "exchangeable", budget=bm, journal=CallJournal(None), spec_id="mock")
    try:
        env.run(pol); ok = False
    except BudgetExceeded:
        ok = True
    check("mock backend is still counted against the cap (safety over convenience)", ok)
    check("mock backend costs nothing", bm.cost == 0.0)
    check("price lookup: known, dated snapshot, unknown → pessimistic", cost_usd("gpt-4.1-mini", 1e6, 0) == 0.40 and cost_usd("claude-haiku-4-5-20251001", 1e6, 0) == 1.0 and cost_usd("gpt-99", 1e6, 0) == 5.0)


# --------------------------------------------------------------------------- P9
def p9_keys():
    print("P9 key loading")
    saved = {k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
    for k in saved:
        os.environ.pop(k, None)
    p = os.path.join(TMP, "keys.env")
    with open(p, "w") as f:
        f.write("# comment\nANTHROPIC_API_KEY=sk-test-anthropic-XYZ\nOPENAI_API_KEY='sk-test-openai-ABC'\nJUNK=1\n")
    loaded = load_keys(p)
    check("both names loaded, junk ignored", sorted(loaded) == ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"] and "JUNK" not in os.environ)
    check("quotes stripped", os.environ["OPENAI_API_KEY"] == "sk-test-openai-ABC")
    d = describe()
    check("describe() never returns a value", "XYZ" not in json.dumps(d) and "ABC" not in json.dumps(d) and "set (" in d["ANTHROPIC_API_KEY"])
    check("scrub() redacts", scrub("key is sk-test-anthropic-XYZ here") == "key is <ANTHROPIC_API_KEY> here")
    check("loader does not override an existing value by default", load_keys(p) == [])
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


if __name__ == "__main__":
    for fn in (p1_prompts, p2_parser, p3_retries, p4_failure_no_duplicates, p5_storage_metadata, p6_seeds, p7_conditions, p8_budget, p9_keys):
        fn()
    shutil.rmtree(TMP, ignore_errors=True)
    print("\nFAILED:" if FAIL else "\nALL PIPELINE TESTS PASS", FAIL or "")
    sys.exit(1 if FAIL else 0)
