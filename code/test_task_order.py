#!/usr/bin/env python3
"""Fixtures for mersch_task_order.py, in both polarities.

The claim this file protects is that `cleaner` was recovered as the middle of an
ordering rather than assumed into it. That claim is only worth anything if the
instrument can return the other two answers, so two of the fixtures below make a
different label the middle and make no middle identifiable at all.

  chain       ordered, one-way   -> cleaner in the middle, flow directional
  nurse_mid   ordered, one-way   -> NURSE in the middle. The instrument is not
                                    wired to the answer we expect.
  symmetric   ordered, two-way   -> cleaner in the middle, flow NOT directional
  tie         no ordering        -> no unique middle, direction refused, rc 1
  split       two colonies disagreeing about the middle -> counted, not pooled
  wobble      a colony whose majority is two moves -> "no direction", no arrow
  against     a colony genuinely running the other way -> named with !!
  mismatch    guard: wrong expected counts -> nothing printed at all

`chain` and `symmetric` are the important pair. They have the same ordering and
differ only in whether the moves run one way, which is exactly the distinction
between "these three labels are cuts through one continuous quantity" and "these
ants progress along a sequence". An instrument that called both of them
directional would be measuring the ordering twice and the direction never.

They are also the pair that carries the reversal null's polarity. `chain` has 24
forward moves against 4 backward, so the direction is true by construction and a
sensitivity that reports it as not surviving is broken rather than conservative;
`symmetric` has it false by construction. The first version of the sensitivity
re-drew label prevalences over changers only and failed `chain` -- a directional
flow is exactly what makes the movers nurse-heavy early, so that null had already
absorbed the effect. Both needles are asserted here in both polarities, because a
reversal null that answered "survives" to everything would satisfy `chain` alone.

Run:  python3 test_task_order.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from test_task_crosstab import build

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []


def run(root: Path, changed: int, complete: int):
    r = subprocess.run(
        [sys.executable, str(HERE / "mersch_task_order.py"), "--raw", str(root),
         "--expect-changed", str(changed), "--expect-complete", str(complete)],
        capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def expect(name, root, changed, complete, want_rc, needles, absent=()):
    rc, out = run(root, changed, complete)
    missing = [n for n in needles if n not in out]
    present = [n for n in absent if n in out]
    if rc == want_rc and not missing and not present:
        print(f"  PASS  {name}")
        return
    FAILS.append(name)
    print(f"  FAIL  {name}: rc={rc} want={want_rc}")
    for n in missing:
        print(f"        expected in output, absent: {n!r}")
    for n in present:
        print(f"        expected absent, present:  {n!r}")
    print("\n".join("        | " + ln for ln in out.splitlines()[-35:]))


class Gen:
    """Row builder that keeps tag ids unique across colonies as it goes."""

    def __init__(self):
        self.rows, self.n = [], 0

    def add(self, colony: str, labels, times: int = 1):
        for _ in range(times):
            self.n += 1
            self.rows.append((colony, f"Ant{self.n}", *labels))
        return self


def chain_colony(g: Gen, col: str, fwd: int, bwd: int, stable: int = 12):
    """`fwd` moves along nurse -> cleaner -> forager, `bwd` the other way.

    Every changer makes exactly one move, so the move counts are the arguments.
    Stable ants exist to give the null a population whose composition is not
    itself made of movers.
    """
    for k in range(fwd):
        g.add(col, ["N", "N", "N", "C"] if k % 2 == 0 else ["C", "C", "C", "F"])
    for k in range(bwd):
        g.add(col, ["F", "F", "F", "C"] if k % 2 == 0 else ["C", "C", "C", "N"])
    g.add(col, ["N", "N", "N", "N"], stable // 3)
    g.add(col, ["C", "C", "C", "C"], stable // 3)
    g.add(col, ["F", "F", "F", "F"], stable - 2 * (stable // 3))


def nurse_mid_colony(g: Gen, col: str, n: int, stable: int = 12):
    """Moves run cleaner -> nurse -> forager, so `cleaner <-> forager` is empty."""
    for k in range(n):
        g.add(col, ["C", "C", "C", "N"] if k % 2 == 0 else ["N", "N", "N", "F"])
    g.add(col, ["N", "N", "N", "N"], stable // 3)
    g.add(col, ["C", "C", "C", "C"], stable // 3)
    g.add(col, ["F", "F", "F", "F"], stable - 2 * (stable // 3))


def counts(g: Gen):
    complete = len(g.rows)
    changed = sum(1 for r in g.rows if len(set(r[2:6])) > 1)
    return changed, complete


def main() -> int:
    tmp = Path("/tmp/fx_order")
    print("mersch_task_order fixtures\n")

    g = Gen()
    chain_colony(g, "1", fwd=24, bwd=4, stable=30)
    build(tmp / "chain", g.rows)
    expect("chain: cleaner recovered as the middle, flow one-way",
           tmp / "chain", *counts(g), 0,
           ["cleaner is the middle",
            "Order recovered from the data: nurse -- cleaner -- forager",
            "the flow is directional beyond what the shift in composition",
            # The reversal null in its live polarity. This fixture has 24
            # forward moves against 4 backward -- direction is true by
            # construction -- so a sensitivity that reports it as not
            # surviving is broken, not conservative. The first version of the
            # sensitivity did exactly that, which is why this needle is here
            # and not left to the real deposit to discover.
            "the direction survives time reversal"],
           absent=["the flow is not directional",
                   "no unique minimum",
                   "the direction does not survive time reversal"])

    g = Gen()
    nurse_mid_colony(g, "1", n=24, stable=30)
    build(tmp / "nurse_mid", g.rows)
    expect("nurse_mid: the instrument can answer something other than cleaner",
           tmp / "nurse_mid", *counts(g), 0,
           ["nurse is the middle",
            "Order recovered from the data: cleaner -- nurse -- forager"],
           absent=["cleaner is the middle"])

    # Same ordering as `chain`, moves balanced. If this reported a direction the
    # instrument would be reading the ordering and calling it a direction.
    g = Gen()
    chain_colony(g, "1", fwd=14, bwd=14, stable=30)
    build(tmp / "symmetric", g.rows)
    expect("symmetric: same order, two-way flow, direction NOT claimed",
           tmp / "symmetric", *counts(g), 0,
           ["cleaner is the middle", "the flow is not directional beyond",
            # The other polarity of the same needle. Without this pair, a
            # reversal null that returned "survives" on every input would pass
            # the `chain` assertion above and carry no information.
            "the direction does not survive time reversal"],
           absent=["the flow is directional beyond",
                   "the direction survives time reversal"])

    # Every pair equally travelled: there is no line to lay the labels on, and
    # "forward" is then a choice rather than a measurement.
    g = Gen()
    for k in range(8):
        g.add("1", ["N", "N", "N", "C"])
        g.add("1", ["C", "C", "C", "F"])
        g.add("1", ["N", "N", "N", "F"])
    g.add("1", ["N", "N", "N", "N"], 10)
    g.add("1", ["C", "C", "C", "C"], 10)
    g.add("1", ["F", "F", "F", "F"], 10)
    build(tmp / "tie", g.rows)
    expect("tie: no unique middle, direction refused rather than defaulted",
           tmp / "tie", *counts(g), 1,
           ["no unique minimum", "Direction not scored"],
           absent=["WHICH WAY THE FLOW RUNS"])

    # One colony ordered on cleaner, one on nurse. Pooling would average them
    # into a single confident answer that neither colony supports.
    g = Gen()
    chain_colony(g, "1", fwd=24, bwd=4, stable=30)
    nurse_mid_colony(g, "2", n=26, stable=30)
    build(tmp / "split", g.rows)
    expect("split: a colony disagreeing about the middle is counted, not hidden",
           tmp / "split", *counts(g), 0,
           ["PER COLONY", "1 do not"])

    # A strong colony and a wobbling one. Colony 2's majority is two moves out
    # of twenty-two, which is what coin flips give; before 31 July the table
    # re-oriented each colony to its own majority and printed an arrow for it,
    # so a row like colony 2's was typographically indistinguishable from a row
    # like colony 1's. The real deposit produced exactly this (col29, 12 against
    # 10), which is how the defect was found. Both verdicts are asserted,
    # because a table that called everything directional would satisfy the first
    # assertion on its own.
    g = Gen()
    chain_colony(g, "1", fwd=24, bwd=4, stable=30)
    chain_colony(g, "2", fwd=12, bwd=10, stable=30)
    build(tmp / "wobble", g.rows)
    expect("wobble: a two-move majority is reported as no direction, not an arrow",
           tmp / "wobble", *counts(g), 0,
           ["one-way, with the pooled axis",
            "no direction; the net is the size coin flips give",
            "1 run one way along the pooled axis, 1 show no direction, "
            "0 run the other way"],
           absent=["AGAINST the pooled axis"])

    # The opposite polarity of that last needle, and the reason the pooled axis
    # is used at all. Colony 2 here really does run the other way, strongly. If
    # each colony were re-oriented to its own majority this would print an arrow
    # like everyone else's and the disagreement would be invisible.
    g = Gen()
    chain_colony(g, "1", fwd=30, bwd=4, stable=30)
    chain_colony(g, "2", fwd=3, bwd=24, stable=30)
    build(tmp / "against", g.rows)
    expect("against: a colony running the other way is named, not absorbed",
           tmp / "against", *counts(g), 0,
           ["AGAINST the pooled axis",
            "1 run one way along the pooled axis, 0 show no direction, "
            "1 run the other way"])

    expect("mismatch: a failed guard prints nothing about ordering",
           tmp / "split", 999, 999, 1,
           ["does not reproduce the expected counts"],
           absent=["WHICH LABEL IS IN THE MIDDLE", "PER COLONY"])

    print()
    if FAILS:
        print(f"{len(FAILS)} fixture(s) failed: {', '.join(FAILS)}")
        return 1
    print("all fixtures pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
