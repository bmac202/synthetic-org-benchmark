"""Agent policies for the differentiation environment.

Every policy implements `decide(obs) -> Action`. The environment never knows which one it is
talking to, so the four substrate conditions run on identical code.

  C0   RulePolicy            exchangeable stochastic rule — the floor
  C0+  RuleSpecialistPolicy  rule-based agents with fixed, *different* propensities — a
                             rule-based positive control: proves the measure can see
                             structure before any LLM is involved
  C1   LLMPolicy(variant="exchangeable")   identical prompt, no roles, no names, no personas
  C2   LLMPolicy(variant="role")           each agent told which item type it specializes in
  C3   LLMPolicy(variant="persona")        distinct dispositions, no functional roles
  C4/C5 are environment factors (competence, exit), not policies; see env.py.

A note on C0 and why it is stochastic. The 13 August spec said "work the first known item,
tell a random agent". Taken literally that policy works every single round for every agent,
so activity is identical across agents and its within-window standard deviation is zero;
standardization is then undefined and R is 0/0. The measure would correctly report "nothing
to measure", but that is not a floor, it is a degenerate case (kept as a fixture in
test_measures.py). The floor has to be agents whose *behaviour varies* while their
*identities do not matter*: each round an agent flips a fair coin between working a random
known item and telling a random other agent about a random known item. Any differentiation
the measure then reports is manufactured by the measure.
"""
from __future__ import annotations

import os
import random
import re
import time
from typing import Dict, List, Tuple

from .env import Action, Observation, TYPE_NAMES


# --------------------------------------------------------------------------- rule-based
class RulePolicy:
    name = "C0-rule-exchangeable"

    def __init__(self, seed: int, p_work: float = 0.5):
        self.rng = random.Random(seed * 7919 + 1)
        self.p_work = p_work

    def decide(self, obs: Observation) -> Action:
        if obs.known_items and self.rng.random() < self.p_work:
            item = self.rng.choice(obs.known_items)[0]
            return Action("work", item=item)
        pool = obs.known_items + obs.worked_items      # an agent can tell about anything it knows
        if pool and obs.others:
            item = self.rng.choice(pool)[0]
            return Action("tell", item=item, to=self.rng.choice(obs.others))
        return Action("pass")


class RuleDeterministicPolicy:
    """The literal 13 August rule. Degenerate on activity; kept for the fixture."""
    name = "C0-rule-deterministic"

    def __init__(self, seed: int):
        self.rng = random.Random(seed * 7919 + 2)

    def decide(self, obs: Observation) -> Action:
        if obs.known_items:
            return Action("work", item=obs.known_items[0][0])
        if obs.others:
            return Action("pass")
        return Action("pass")


class RuleSpecialistPolicy:
    """Rule-based positive control. Agent i has a fixed favourite type and a fixed work
    propensity that differ across agents. If the measure cannot see *this*, it is broken."""
    name = "C0+-rule-specialist"

    def __init__(self, seed: int, agents: List[str], n_types: int = 4):
        self.rng = random.Random(seed * 7919 + 3)
        types = list(TYPE_NAMES[:n_types])
        self.fav: Dict[str, str] = {a: types[i % n_types] for i, a in enumerate(agents)}
        n = len(agents)
        # propensities spread evenly on [0.2, 0.9]
        self.p_work: Dict[str, float] = {a: 0.2 + 0.7 * i / max(1, n - 1) for i, a in enumerate(agents)}

    def decide(self, obs: Observation) -> Action:
        a = obs.agent
        if obs.known_items and self.rng.random() < self.p_work[a]:
            favs = [k for k in obs.known_items if k[1] == self.fav[a]]
            pool = favs if favs and self.rng.random() < 0.85 else obs.known_items
            return Action("work", item=self.rng.choice(pool)[0])
        pool = obs.known_items + obs.worked_items
        if pool and obs.others:
            item = self.rng.choice(pool)[0]
            return Action("tell", item=item, to=self.rng.choice(obs.others))
        return Action("pass")


# --------------------------------------------------------------------------- LLM-backed
SYSTEM_EXCHANGEABLE = (
    "You are one member of a small team of {n} people working through a shared queue of "
    "items. Nobody is in charge and nobody has a role. Each item has a type ({types}) and is "
    "finished only after two different people have worked on it. Items disappear if nobody "
    "finishes them within a few rounds. You only ever see a few of the open items; other "
    "people can tell you about items you cannot see, and you can tell them. The team's goal "
    "is to finish as many items as possible. There is no individual credit.\n\n"
    "Each round you take exactly ONE action:\n"
    "  work <item id>            — work on an item you know about (you can work each item once)\n"
    "  tell <person> <item id>   — tell one person about an item you know about\n"
    "  pass                      — do nothing this round\n"
    "{exit_line}"
    "Reply with the action only, as one line and nothing else — no reasoning, no explanation. "
    "Valid replies look exactly like: work 12   or   tell A4 12   or   pass"
)

EXIT_LINE = ("  leave                     — leave the team permanently; you take no further part\n")

ROLE_ADDENDUM = ("\n\nYour specialty is items of type {fav}. Prioritise working on {fav} items and "
                 "tell others about items of the other types.")

PERSONAS = [
    "You are cautious: you prefer to be sure before acting and dislike wasted effort.",
    "You are proactive: you like to get things moving and act quickly.",
    "You are sociable: you enjoy keeping others informed and coordinating.",
    "You are independent: you prefer to get on with work yourself.",
    "You are conscientious: you like finishing what is started and keeping the queue tidy.",
    "You are easy-going: you take things as they come and do not push.",
    "You are curious: you like variety and trying different kinds of item.",
    "You are helpful: you look for what others might need and pass it on.",
    "You are focused: you pick a thing and stick with it.",
]
PERSONA_ADDENDUM = "\n\nA note on how you tend to behave. {persona}"


def alias_square(agents: List[str], seed: int) -> Dict[str, Dict[str, str]]:
    """Per-viewer names, balanced as a Latin square.  square[viewer][agent] = the label under
    which `viewer` sees `agent` (square[v][v] is the viewer's own name).

    Why: on gpt-4.1-mini the label "A1" received most tells and "A8" fewest in six runs out of
    six — a name preference that scores as individual differentiation.  Here every agent carries
    every label exactly once across viewers, and every viewer sees nine distinct labels, so a
    preference for a label can no longer pile up on one agent.  Labels are stable for the whole
    run (a viewer's "A1" is always the same colleague), so genuine partner relationships can
    still form.  The same nine labels are used, so the prompt text is otherwise unchanged.
    Construction: label index = (a[x] + a[v]) mod n with `a` a seeded permutation; for odd n the
    diagonal (own names) is also a permutation, so own names are all distinct.
    """
    n = len(agents)
    rng = random.Random(seed * 7919 + 17)
    a = list(range(n)); rng.shuffle(a)
    sym = list(agents); rng.shuffle(sym)
    return {v: {x: sym[(a[i] + a[j]) % n] for i, x in enumerate(agents)} for j, v in enumerate(agents)}


_NAME_RE = re.compile(r"\bA\d+\b")


def alias_observation(obs: Observation, view: Dict[str, str]) -> Observation:
    """The same observation with every agent name replaced by this viewer's label for it."""
    sub = lambda text: _NAME_RE.sub(lambda m: view.get(m.group(0), m.group(0)), text)
    return Observation(agent=view[obs.agent], round=obs.round, window=obs.window,
                       known_items=obs.known_items, worked_items=obs.worked_items,
                       already_worked=obs.already_worked,
                       inbox=[(view[f], i, ty) for f, i, ty in obs.inbox],
                       others=[view[o] for o in obs.others],
                       history=[sub(h) for h in obs.history])


def render_observation(obs: Observation) -> str:
    lines = [f"Round {obs.round + 1}. You are {obs.agent}. Other people: {', '.join(obs.others) or 'none'}."]
    if obs.inbox:
        lines.append("Messages received: " + "; ".join(f"{f} told you about item {i} ({ty})" for f, i, ty in obs.inbox))
    if obs.known_items:
        lines.append("Open items you know about and could work (id, type, people who have worked it so far):")
        for i, ty, w in obs.known_items:
            lines.append(f"  item {i}, {ty}, {w} of 2 done")
    else:
        lines.append("You know of no open items you could work.")
    if obs.worked_items:
        lines.append("Open items you have already worked (you cannot work them again; they still need a second person, and you can tell someone about them):")
        for i, ty, w in obs.worked_items:
            lines.append(f"  item {i}, {ty}, {w} of 2 done")
    if obs.history:
        lines.append("Your recent actions: " + "; ".join(obs.history))
    lines.append("Your action (one line, e.g. 'work 12', 'tell A4 12' or 'pass'; no explanation):")
    return "\n".join(lines)


_ACTION_RE = re.compile(r"^\s*(work|tell|pass|leave)\b\s*(.*)$", re.I)


def parse_action(text: str, obs: Observation) -> Action:
    """Turn the model's one line into an Action. Anything unparseable is a pass, and the
    caller records that it was unparseable so the rate can be reported."""
    # accept the first line, anywhere in the reply, that starts with an action word: a short
    # preamble does not cost the agent its move, but a mention inside a sentence does not count
    m = None
    for line in text.strip().splitlines():
        line = line.strip().lstrip("*-•> ").strip("`").strip()
        m = _ACTION_RE.match(line)
        if m:
            break
    if not m:
        return Action("pass")
    kind, rest = m.group(1).lower(), m.group(2)
    nums = re.findall(r"\d+", rest)
    if kind == "work":
        return Action("work", item=int(nums[0])) if nums else Action("pass")
    if kind == "tell":
        who = re.search(r"\bA\d+\b", rest, re.I)
        if who and nums:
            # the first number that is not part of the agent name
            item_nums = re.findall(r"\d+", re.sub(r"\bA\d+\b", "", rest, flags=re.I))
            if item_nums:
                return Action("tell", item=int(item_nums[0]), to=who.group(0).upper())
        return Action("pass")
    if kind == "leave":
        return Action("leave")
    return Action("pass")


class Backend:
    """One call per decision. `complete` returns (text, usage) where usage is
    {"input_tokens": int, "output_tokens": int}. Subclasses wrap a provider; MockBackend
    needs no network. Retries are bounded (MAX_RETRIES) with exponential backoff, and
    errors that will not fix themselves (authentication, bad request) are not retried."""
    provider = "none"
    model = "none"
    MAX_RETRIES = 4
    BASE_DELAY = 2.0

    def complete(self, system: str, user: str, temperature: float, seed: int) -> Tuple[str, dict]:
        raise NotImplementedError

    def _retry(self, fn):
        delay = self.BASE_DELAY
        last = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return fn()
            except Exception as e:
                last = e
                if not self._retryable(e) or attempt == self.MAX_RETRIES - 1:
                    raise
                time.sleep(delay); delay = min(delay * 2, 30)
        raise last  # pragma: no cover

    @staticmethod
    def _retryable(e: Exception) -> bool:
        name = type(e).__name__
        status = getattr(e, "status_code", None)
        if name in ("AuthenticationError", "PermissionDeniedError", "BadRequestError", "NotFoundError"):
            return False
        if status is not None and 400 <= int(status) < 500 and int(status) != 429:
            return False
        return True


class MockBackend(Backend):
    """Scripted stand-in so the whole prompt→parse→act pipeline can be exercised offline.
    Behaves like a mildly specialised agent if the system prompt names a specialty, else
    like the exchangeable rule. Not evidence about anything."""
    provider = "mock"
    model = "mock-scripted"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def complete(self, system, user, temperature, seed):
        fav = re.search(r"specialty is items of type (\w+)", system)
        items = re.findall(r"item (\d+), (\w+), (\d) of 2 done", user.split("already worked")[0])
        others = re.search(r"Other people: ([^.\n]+)", user)
        others = [o.strip() for o in others.group(1).split(",")] if others and "none" not in others.group(1) else []
        usage = {"input_tokens": len(system) // 4 + len(user) // 4, "output_tokens": 4}
        if not items:
            return "pass", usage
        if fav:
            favs = [i for i in items if i[1] == fav.group(1)]
            if favs and self.rng.random() < 0.8:
                return f"work {self.rng.choice(favs)[0]}", usage
            if others and self.rng.random() < 0.7:
                nonfav = [i for i in items if i[1] != fav.group(1)] or items
                return f"tell {self.rng.choice(others)} {self.rng.choice(nonfav)[0]}", usage
        if self.rng.random() < 0.5:
            return f"work {self.rng.choice(items)[0]}", usage
        if others:
            return f"tell {self.rng.choice(others)} {self.rng.choice(items)[0]}", usage
        return "pass", usage


class AnthropicBackend(Backend):
    provider = "anthropic"

    def __init__(self, model: str):
        import anthropic  # noqa
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set; load keys.env first")
        self.client = anthropic.Anthropic(max_retries=0)   # we do our own bounded retries
        self.model = model

    # Anthropic SDK >= 1.x removed `temperature` from the typed signature, and the API rejects
    # it for Opus 4.7+, Sonnet 5 and Fable 5 ('"temperature" is deprecated for this model').
    # Older models (Haiku 4.5, Sonnet 4.5, the 4.6 family) still accept it in the raw body.
    # We send it via extra_body; if the model rejects it we retry once without it and record
    # `temperature_applied: False` so the specimen says which sampling regime it was run under.
    temperature_applied = True

    def complete(self, system, user, temperature, seed):
        def call():
            kw = dict(model=self.model, max_tokens=40, system=system,
                      messages=[{"role": "user", "content": user}])
            if self.temperature_applied:
                kw["extra_body"] = {"temperature": temperature}
            try:
                r = self.client.messages.create(**kw)
            except Exception as e:
                msg = str(e)
                if self.temperature_applied and "temperature" in msg and ("deprecated" in msg or "not supported" in msg):
                    self.temperature_applied = False
                    r = self.client.messages.create(**{k: v for k, v in kw.items() if k != "extra_body"})
                else:
                    raise
            text = ""
            for block in (r.content or []):
                if getattr(block, "type", "") == "text":
                    text += block.text
            u = getattr(r, "usage", None)
            usage = {"input_tokens": int(getattr(u, "input_tokens", 0) or 0),
                     "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
                     "model": getattr(r, "model", self.model), "stop_reason": getattr(r, "stop_reason", None),
                     "temperature_applied": self.temperature_applied}
            return text, usage
        return self._retry(call)


class OpenAIBackend(Backend):
    provider = "openai"

    def __init__(self, model: str):
        from openai import OpenAI  # noqa
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY not set; load keys.env first")
        self.client = OpenAI(max_retries=0)
        self.model = model

    temperature_applied = True   # gpt-5-family models reject non-default temperature; we fall back once

    def complete(self, system, user, temperature, seed):
        def call():
            kw = dict(model=self.model, max_completion_tokens=40,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            if self.temperature_applied:
                kw["temperature"] = temperature
            try:
                r = self.client.chat.completions.create(**kw)
            except Exception as e:
                msg = str(e)
                if self.temperature_applied and "temperature" in msg and ("unsupported" in msg.lower() or "not supported" in msg.lower() or "does not support" in msg.lower()):
                    self.temperature_applied = False
                    r = self.client.chat.completions.create(**{k: v for k, v in kw.items() if k != "temperature"})
                else:
                    raise
            choice = r.choices[0] if r.choices else None
            text = (choice.message.content or "") if choice and choice.message else ""
            u = getattr(r, "usage", None)
            usage = {"input_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
                     "output_tokens": int(getattr(u, "completion_tokens", 0) or 0),
                     "model": getattr(r, "model", self.model),
                     "stop_reason": getattr(choice, "finish_reason", None) if choice else None,
                     "temperature_applied": self.temperature_applied}
            return text, usage
        return self._retry(call)


class LLMPolicy:
    """One model call per agent per round. `variant` selects C1/C2/C3.

    Every call goes: journal lookup → budget check → provider call (bounded retries) →
    budget charge → journal write. A failed call is charged nothing and journals nothing, so
    a restart with the same journal makes exactly the calls that are missing and no others.
    """

    def __init__(self, backend: Backend, agents: List[str], variant: str = "exchangeable",
                 temperature: float = 1.0, seed: int = 0, n_types: int = 4, exit_allowed: bool = False,
                 budget=None, journal=None, spec_id: str = "unspecified", alias: bool = False):
        assert variant in ("exchangeable", "role", "persona")
        self.alias = alias_square(agents, seed) if alias else None
        self.unalias = ({v: {lab: x for x, lab in view.items()} for v, view in self.alias.items()}
                        if alias else None)
        from .budget import Budget, CallJournal
        self.backend = backend
        self.variant = variant
        self.temperature = temperature
        self.seed = seed
        self.agents = agents
        self.budget = budget if budget is not None else Budget()
        self.journal = journal if journal is not None else CallJournal(None)
        self.spec_id = spec_id
        types = list(TYPE_NAMES[:n_types])
        base = SYSTEM_EXCHANGEABLE.format(n=len(agents), types=", ".join(types),
                                          exit_line=EXIT_LINE if exit_allowed else "")
        self.system: Dict[str, str] = {}
        self.assignment: Dict[str, str] = {}
        for i, a in enumerate(agents):
            s = base
            if variant == "role":
                fav = types[i % n_types]
                self.assignment[a] = fav
                s += ROLE_ADDENDUM.format(fav=fav)
            elif variant == "persona":
                p = PERSONAS[i % len(PERSONAS)]
                self.assignment[a] = p
                s += PERSONA_ADDENDUM.format(persona=p)
            self.system[a] = s
        self.name = {"exchangeable": "C1-llm-exchangeable", "role": "C2-llm-role",
                     "persona": "C3-llm-persona"}[variant]
        self.calls = 0            # real provider calls made by this object
        self.replayed = 0         # decisions answered from the journal
        self.unparseable = 0
        self.raw: List[dict] = []      # every reply (real or replayed), for the specimen

    def decide(self, obs: Observation) -> Action:
        from .budget import CallJournal
        key = CallJournal.key(self.spec_id, obs.round, obs.agent)
        shown = alias_observation(obs, self.alias[obs.agent]) if self.alias else obs
        user = render_observation(shown)
        cached = self.journal.get(key)
        if cached is not None:
            text, usage, source = cached["reply"], cached.get("usage", {}), "journal"
            self.replayed += 1
        else:
            self.budget.charge_before()
            t0 = time.time()
            text, usage = self.backend.complete(self.system[obs.agent], user, self.temperature, self.seed)
            latency = time.time() - t0
            self.budget.charge_after(self.backend.model, usage.get("input_tokens", 0), usage.get("output_tokens", 0), latency)
            usage = {**usage, "latency_s": round(latency, 3)}
            self.journal.put(key, text, usage)
            self.calls += 1
            source = "api"
        act = parse_action(text, shown)
        if self.alias and act.kind == "tell":
            # the model named a label; translate back to the real agent (unknown label -> pass)
            real = self.unalias[obs.agent].get(act.to)
            act = Action("tell", item=act.item, to=real) if real else Action("pass")
        if act.kind == "pass" and not re.match(r"^\s*pass\b", text.strip(), re.I):
            self.unparseable += 1
        self.raw.append({"round": obs.round, "agent": obs.agent, "reply": text.strip()[:200],
                         "source": source, "usage": usage})
        return act

    def prompt_record(self) -> dict:
        return {"variant": self.variant, "temperature": self.temperature,
                "provider": self.backend.provider, "model": self.backend.model,
                "system_prompts": self.system, "assignment": self.assignment,
                "alias": self.alias,   # None, or {viewer: {agent: label shown to that viewer}}
                "calls": self.calls, "replayed": self.replayed, "unparseable": self.unparseable,
                "journal": self.journal.path}
