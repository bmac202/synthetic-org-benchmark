"""Cost safeguards and the call journal.

Budget      — hard caps on real API calls and estimated spend. Checked *before* every call;
              raises BudgetExceeded rather than making the call. Defaults are small; a large
              run needs `full_run=True` (the `--full-run` flag) or it refuses to start.
CallJournal — append-only JSONL of completed calls keyed by (specimen, round, agent). A policy
              consults it before calling, so a restarted run replays what it already has and
              only makes the missing calls. A call that fails is never written, so it cannot
              create a duplicate; a call that succeeded is never made again.

Prices are USD per million tokens, entered 29 September 2026 from the providers' price
pages as remembered — treat as estimates and reconcile against the dashboards.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

PRICES_PER_M: Dict[str, Tuple[float, float]] = {   # (input, output)
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "mock-scripted": (0.0, 0.0),
}
UNKNOWN_PRICE = (5.00, 25.00)      # pessimistic default for a model not in the table

DEV_MAX_CALLS = 25
DEV_MAX_COST_USD = 1.00


class BudgetExceeded(RuntimeError):
    pass


def price_for(model: str) -> Tuple[float, float]:
    if model in PRICES_PER_M:
        return PRICES_PER_M[model]
    for k, v in PRICES_PER_M.items():          # prefix match for dated snapshots
        if model.startswith(k):
            return v
    return UNKNOWN_PRICE


def cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    pi, po = price_for(model)
    return (in_tok * pi + out_tok * po) / 1e6


@dataclass
class Budget:
    max_calls: int = DEV_MAX_CALLS
    max_cost_usd: float = DEV_MAX_COST_USD
    full_run: bool = False
    calls: int = 0
    cost: float = 0.0
    by_model: Dict[str, dict] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls, **over) -> "Budget":
        b = cls(max_calls=int(os.environ.get("MAX_API_CALLS", DEV_MAX_CALLS)),
                max_cost_usd=float(os.environ.get("MAX_COST_USD", DEV_MAX_COST_USD)),
                full_run=os.environ.get("FULL_RUN", "") == "1")
        for k, v in over.items():
            if v is not None:
                setattr(b, k, v)
        return b

    def refuse_if_large(self, planned_calls: int) -> None:
        """Called once before a run starts, with the number of calls the run will make."""
        remaining = self.max_calls - self.calls
        if planned_calls > remaining:
            raise BudgetExceeded(
                f"run would make up to {planned_calls} calls but only {remaining} remain under "
                f"MAX_API_CALLS={self.max_calls}; raise --max-calls (and pass --full-run) to allow it")
        if planned_calls > DEV_MAX_CALLS and not self.full_run:
            raise BudgetExceeded(
                f"run would make up to {planned_calls} calls (> {DEV_MAX_CALLS}); pass --full-run to confirm")

    def charge_before(self) -> None:
        with self._lock:
            if self.calls + 1 > self.max_calls:
                raise BudgetExceeded(f"MAX_API_CALLS={self.max_calls} reached")
            if self.cost >= self.max_cost_usd:
                raise BudgetExceeded(f"MAX_COST_USD={self.max_cost_usd:.2f} reached (spent ~{self.cost:.4f})")

    def charge_after(self, model: str, in_tok: int, out_tok: int, latency_s: float) -> float:
        c = cost_usd(model, in_tok, out_tok)
        with self._lock:
            self.calls += 1; self.cost += c
            m = self.by_model.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_s": 0.0})
            m["calls"] += 1; m["input_tokens"] += in_tok; m["output_tokens"] += out_tok
            m["cost_usd"] += c; m["latency_s"] += latency_s
        return c

    def report(self) -> dict:
        return {"calls": self.calls, "cost_usd": round(self.cost, 6), "max_calls": self.max_calls,
                "max_cost_usd": self.max_cost_usd, "full_run": self.full_run,
                "by_model": {k: {**v, "cost_usd": round(v["cost_usd"], 6), "latency_s": round(v["latency_s"], 2)}
                             for k, v in self.by_model.items()}}


class CallJournal:
    """Append-only JSONL. One line per *completed* call: key, reply, usage."""

    def __init__(self, path: Optional[str]):
        self.path = path
        self.entries: Dict[str, dict] = {}
        if path and os.path.isfile(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue          # a torn last line from a crash mid-write is ignored
                    self.entries[e["key"]] = e

    @staticmethod
    def key(spec_id: str, rnd: int, agent: str) -> str:
        return f"{spec_id}|{rnd}|{agent}"

    def get(self, key: str) -> Optional[dict]:
        return self.entries.get(key)

    def put(self, key: str, reply: str, usage: dict) -> None:
        if key in self.entries:
            return                          # never a duplicate
        e = {"key": key, "reply": reply, "usage": usage, "t": time.time()}
        self.entries[key] = e
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(e) + "\n"); f.flush(); os.fsync(f.fileno())

    def __len__(self):
        return len(self.entries)
