"""The differentiation environment: an open queue with partial visibility.

Built 29 September 2026 from `spec_differentiation_environment.md` (13 August).

Why this exists. In the earlier aggregation prototype (orglib-poc) every agent does exactly
one thing along a channel the injected structure names. Differentiation cannot arise, so the
dependent variable does not exist. Here nobody assigns anything: agents choose how much to
act, what to work on and whom to talk to. Whether they come to differ is the measurement.

Rules, in one paragraph. `N` agents, no roles, no reporting lines, no individual score. Each
round a batch of `K` items arrives, each with one of `n_types` types. An item completes when
two *distinct* agents have worked it; it expires `W` rounds after arrival if not complete.
Each agent privately sees a random sample of `m` open items plus any item another agent has
told it about. Each round every agent takes exactly one action: `work(item)`, `tell(agent,
item)` or `pass`. Payoff is collective — items completed — and nobody sees it during the run.

Optional factors (both off by default, both added in September 2026):
  * competence   — per-agent, per-type success probability for `work`; a failed `work` is
                   logged but does not count toward completion.  (condition C4)
  * exit         — a permanent `leave` action; the agent takes no further part. (condition C5)

Logging. Every action is one row in the schema orglib-poc already uses,
`{t, sender, recipient, mtype, payload}`, so the structural instruments in
`orglib/measure.py` run unchanged. For `work`, `pass` and `leave` the recipient is the agent
itself. `payload` carries the item id and type, and for `work` whether it succeeded.

Decisions within a round are simultaneous: all agents see the same state, then all actions
apply. If two agents work the same item in the same round it completes that round.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

TYPE_NAMES = ("alpha", "beta", "gamma", "delta")


@dataclass
class Item:
    id: int
    type: str
    arrived: int                     # round of arrival
    workers: Set[str] = field(default_factory=set)
    completed_at: Optional[int] = None
    expired_at: Optional[int] = None

    @property
    def open(self) -> bool:
        return self.completed_at is None and self.expired_at is None


@dataclass
class Observation:
    """What one agent sees when it decides. This — and only this — is what a policy gets."""
    agent: str
    round: int
    window: int
    known_items: List[Tuple[int, str, int]]   # (item id, type, workers so far) for items it may work
    worked_items: List[Tuple[int, str, int]]  # open items it has already worked: cannot work again, can tell
    already_worked: Set[int]                  # items this agent has already worked (cannot work twice)
    inbox: List[Tuple[str, int, str]]         # (from, item id, type) told this round
    others: List[str]                         # other agents still present
    history: List[str]                        # this agent's own recent actions, as short strings


@dataclass
class Action:
    kind: str                                 # work | tell | pass | leave
    item: Optional[int] = None
    to: Optional[str] = None


class Config(dict):
    """Plain dict with attribute access, so a specimen can serialize it directly."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


def default_config(**over) -> Config:
    c = Config(
        n_agents=9,          # matches the Alciatore colony size
        rounds=100,          # ten windows of ten rounds
        window=10,
        k_items=6,
        n_types=4,
        m_sample=3,
        w_expiry=5,
        history_len=5,       # how many of its own past actions an agent is shown
        competence=None,     # None, or {agent: {type: p_success}}
        exit_allowed=False,
        shuffle_view=True,   # present an agent's known items in random order (removes list-position bias)
        alias=False,         # LLM runs only: per-viewer colleague labels (see policies.alias_square)
        visibility="sampled",  # "sampled": each agent samples m open items per round;
                               # "private": each arriving item is revealed to exactly one agent,
                               #            so a second worker can only come via `tell`
    )
    c.update(over)
    return c


class OpenQueueEnv:
    def __init__(self, config: Config, seed: int):
        self.cfg = config
        self.seed = seed
        self.rng = random.Random(seed)
        self.agents: List[str] = [f"A{i}" for i in range(config.n_agents)]
        self.present: List[str] = list(self.agents)
        self.items: Dict[int, Item] = {}
        self.known: Dict[str, Set[int]] = {a: set() for a in self.agents}
        self.told_this_round: Dict[str, List[Tuple[str, int, str]]] = {a: [] for a in self.agents}
        self.worked: Dict[str, Set[int]] = {a: set() for a in self.agents}
        self.history: Dict[str, List[str]] = {a: [] for a in self.agents}
        self.log: List[dict] = []
        self.opportunity: Dict[Tuple[str, int], int] = {}   # (agent, round) -> items it could work when it decided
        self.t = 0
        self.round = 0
        self._next_item = 0
        self.completed = 0
        self.expired = 0
        self.types = list(TYPE_NAMES[: config.n_types])

    # ------------------------------------------------------------------ helpers
    def window_of(self, rnd: int) -> int:
        return rnd // self.cfg.window

    def _emit(self, sender: str, recipient: str, mtype: str, payload) -> None:
        self.log.append({"t": self.t, "round": self.round, "window": self.window_of(self.round),
                         "sender": sender, "recipient": recipient, "mtype": mtype,
                         "payload": payload})
        self.t += 1

    def _arrive(self) -> None:
        for _ in range(self.cfg.k_items):
            it = Item(self._next_item, self.rng.choice(self.types), self.round)
            self.items[it.id] = it
            self._next_item += 1
            if self.cfg.get("visibility", "sampled") == "private" and self.present:
                self.known[self.rng.choice(self.present)].add(it.id)

    def _expire(self) -> None:
        for it in self.items.values():
            if it.open and self.round - it.arrived >= self.cfg.w_expiry:
                it.expired_at = self.round
                self.expired += 1

    def _open_items(self) -> List[Item]:
        return [it for it in self.items.values() if it.open]

    def _forget_closed(self) -> None:
        for a in self.agents:
            self.known[a] = {i for i in self.known[a] if self.items[i].open}

    # ------------------------------------------------------------------ observe
    def observe(self, agent: str) -> Observation:
        if self.cfg.get("visibility", "sampled") == "sampled":
            open_ids = [it.id for it in self._open_items()]
            sample = self.rng.sample(open_ids, min(self.cfg.m_sample, len(open_ids)))
            self.known[agent].update(sample)
        known = sorted(self.known[agent])
        if self.cfg.get("shuffle_view", True):
            self.rng.shuffle(known)
        known_items = [(i, self.items[i].type, len(self.items[i].workers)) for i in known
                       if i not in self.worked[agent]]
        worked_items = [(i, self.items[i].type, len(self.items[i].workers)) for i in known
                        if i in self.worked[agent]]
        self.opportunity[(agent, self.round)] = len(known_items)
        others = [o for o in self.present if o != agent]
        if self.cfg.get("shuffle_view", True):
            self.rng.shuffle(others)     # recipient position bias: the first-listed name attracts tells
        return Observation(
            agent=agent, round=self.round, window=self.window_of(self.round),
            known_items=known_items, worked_items=worked_items, already_worked=set(self.worked[agent]),
            inbox=list(self.told_this_round[agent]),
            others=others,
            history=list(self.history[agent][-self.cfg.history_len:]),
        )

    # ------------------------------------------------------------------ step
    def step(self, actions: Dict[str, Action]) -> None:
        """Apply one round of simultaneous actions, then advance the clock."""
        # clear inboxes; tells made this round are delivered for next round's observation
        new_inbox: Dict[str, List[Tuple[str, int, str]]] = {a: [] for a in self.agents}
        comp = self.cfg.competence
        for a in list(self.present):
            act = actions.get(a) or Action("pass")
            if act.kind == "work" and act.item is not None and act.item in self.known[a] \
                    and self.items[act.item].open and act.item not in self.worked[a]:
                it = self.items[act.item]
                ok = True
                if comp is not None:
                    ok = self.rng.random() < comp[a][it.type]
                self.worked[a].add(it.id)
                if ok:
                    it.workers.add(a)
                self._emit(a, a, "work", {"item": it.id, "type": it.type, "ok": ok})
                self.history[a].append(f"worked item {it.id} ({it.type})" + ("" if ok else " — failed"))
            elif act.kind == "tell" and act.item is not None and act.to in self.present \
                    and act.to != a and act.item in self.known[a] and self.items[act.item].open:
                it = self.items[act.item]
                self.known[act.to].add(it.id)
                new_inbox[act.to].append((a, it.id, it.type))
                self._emit(a, act.to, "tell", {"item": it.id, "type": it.type})
                self.history[a].append(f"told {act.to} about item {it.id} ({it.type})")
            elif act.kind == "leave" and self.cfg.exit_allowed:
                self.present.remove(a)
                self._emit(a, a, "leave", {})
                self.history[a].append("left the organization")
            else:
                self._emit(a, a, "pass", {})
                self.history[a].append("passed")
        # completions
        for it in self._open_items():
            if len(it.workers) >= 2:
                it.completed_at = self.round
                self.completed += 1
        self.told_this_round = new_inbox
        self.round += 1
        self._expire()
        self._forget_closed()
        if self.round < self.cfg.rounds:
            self._arrive()

    def run(self, policy, on_round=None) -> dict:
        """Drive the whole episode with one policy object deciding for every agent."""
        self._arrive()
        while self.round < self.cfg.rounds:
            obs = {a: self.observe(a) for a in self.present}
            acts = {a: policy.decide(obs[a]) for a in self.present}
            self.step(acts)
            if on_round:
                on_round(self)
        return self.outcome()

    def outcome(self) -> dict:
        n_items = len(self.items)
        return {"items_arrived": n_items, "completed": self.completed, "expired": self.expired,
                "still_open": sum(1 for it in self.items.values() if it.open),
                "completion_rate": self.completed / n_items if n_items else 0.0,
                "agents_left": [a for a in self.agents if a not in self.present]}
