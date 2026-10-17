"""Fixtures for per-viewer labels (`--alias`).  python3 -m diffenv.test_alias

1. The label square is Latin: each viewer sees nine distinct labels, each agent carries each
   label exactly once across viewers, and own names are all distinct.
2. A backend with a pure name preference (always tells "A1" when it can) manufactures a hub
   without aliasing and cannot with it.
3. Under aliasing the log holds real agents: the label in each raw reply, translated through
   the sender's view, is the logged recipient.
"""
import re
from collections import Counter

from .budget import Budget
from .env import OpenQueueEnv, default_config
from .policies import alias_balanced, Backend, LLMPolicy, alias_square


class NamePreferenceBackend(Backend):
    provider = "mock"; model = "mock-name-preference"

    def complete(self, system, user, temperature, seed):
        items = re.findall(r"item (\d+), (\w+), (\d) of 2 done", user)
        others = re.search(r"Other people: ([^.\n]+)", user).group(1)
        usage = {"input_tokens": 1, "output_tokens": 1}
        if not items:
            return "pass", usage
        rnd = int(re.search(r"Round (\d+)", user).group(1))
        if rnd % 2 == 0 and "A1" in [o.strip() for o in others.split(",")]:
            return f"tell A1 {items[0][0]}", usage
        workable = re.findall(r"item (\d+), (\w+), (\d) of 2 done", user.split("already worked")[0])
        return (f"work {workable[0][0]}" if workable and "You know of no open" not in user else "pass"), usage


def run(alias, seed=0):
    cfg = default_config(visibility="private", alias=alias)
    env = OpenQueueEnv(cfg, seed)
    pol = LLMPolicy(NamePreferenceBackend(), env.agents, seed=seed, alias=alias, budget=Budget(max_calls=1000))
    env.run(pol)
    return env, pol


def main():
    agents = [f"A{i}" for i in range(9)]
    for seed in range(20):
        sq = alias_square(agents, seed)
        for v in agents:
            assert sorted(sq[v].values()) == sorted(agents), "a viewer must see nine distinct labels"
        for x in agents:
            assert sorted(sq[v][x] for v in agents) == sorted(agents), "an agent must carry each label once"
        assert sorted(sq[v][v] for v in agents) == sorted(agents), "own names must be distinct"
    print("1. label square is Latin with distinct own names (20 seeds)")

    env, _ = run(alias=False)
    rec = Counter(m["recipient"] for m in env.log if m["mtype"] == "tell")
    share_plain = rec["A1"] / sum(rec.values())
    env, pol = run(alias=True)
    rec = Counter(m["recipient"] for m in env.log if m["mtype"] == "tell")
    top_alias = max(rec.values()) / sum(rec.values())
    print(f"2. name-preference backend: without aliasing A1 receives {share_plain:.0%} of tells; "
          f"with aliasing the most-told agent receives {top_alias:.0%} (8 of 9 agents receive)")
    assert share_plain == 1.0 and top_alias <= 0.2 and len(rec) == 8

    tells = [m for m in env.log if m["mtype"] == "tell"]
    raw = {(r["round"], r["agent"]): r["reply"] for r in pol.raw}
    for m in tells:
        label = re.search(r"\bA\d+\b", raw[(m["round"], m["sender"])]).group(0)
        assert pol.unalias[m["sender"]][label] == m["recipient"] != m["sender"]
    print(f"3. {len(tells)} logged tells all match the translated reply")

    # 4. balanced labels (16 Oct 2026): own name A0 for every viewer, every agent carries each
    #    colleague label once, so a pure "A1" preference spreads over all nine agents.
    for seed in range(20):
        sq = alias_balanced(agents, seed)
        assert all(sq[v][v] == "A0" for v in agents)
        for x in agents:
            assert sorted(sq[v][x] for v in agents if v != x) == [f"A{k}" for k in range(1, 9)]
    env, pol = run(alias="balanced")
    rec = Counter(m["recipient"] for m in env.log if m["mtype"] == "tell")
    top_bal = max(rec.values()) / sum(rec.values())
    print(f"4. balanced labels: all {len(rec)} agents receive tells; the most-told receives {top_bal:.0%}")
    assert len(rec) == 9 and top_bal <= 0.2
    tells = [m for m in env.log if m["mtype"] == "tell"]
    raw = {(r["round"], r["agent"]): r["reply"] for r in pol.raw}
    for m in tells:
        label = re.search(r"\bA\d+\b", raw[(m["round"], m["sender"])]).group(0)
        assert pol.unalias[m["sender"]][label] == m["recipient"] != m["sender"]
    print("ALIAS FIXTURES PASS")


if __name__ == "__main__":
    main()
