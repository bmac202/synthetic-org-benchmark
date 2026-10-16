#!/usr/bin/env python3
"""Fixtures for mersch_task_crosstab.py, in both polarities.

The cross-tab's job is to say whether the group changes run through `cleaner`.
The way it fails silently is by describing the wrong population -- so the guard
that compares its own reproduction of `changed of complete` against the expected
pair is the first thing tested, in both directions, and everything else is only
worth testing once that works.

  reproduce    counts match the expectation -> the split prints
  mismatch     counts do not match -> the split must NOT print
  no_c         every change is nurse <-> forager -> "not over-represented"
  via_c        cleaner is rare but on every change -> "more than the null puts there"
  dropped      a queen, an incomplete ant and an unlabelled row are all excluded

`no_c` and `via_c` are a pair on purpose. A verdict line that fires on every real
input carries no information, and the only way to know which of the two branches
a green run took is to have an input that reaches each. `via_c` in particular
keeps `cleaner` RARE while putting it on every change, because the confounder
this whole file exists to rule out is "cleaner is common, so cleaner is on
everything" -- a fixture where cleaner is both common and on every change would
pass whether or not the null is doing its job.

`dropped` exists because three separate exclusions feed one denominator, and a
denominator that is right for the wrong reason is a denominator that will move
the next time someone touches it. The queen there is labelled Q once and N three
times: kept, she is a changer, and she would sit inside the headline count as an
ant that changed job when what changed was how a caste got recorded.

Exit codes: 0 pass, 1 a fixture failed. The script under test uses 0/1/2 as
documented in its own docstring.

Run:  python3 test_task_crosstab.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []

HDR = "colony,tag_id,group_period1,group_period2,group_period3,group_period4"


def build(root: Path, rows: list[tuple]) -> Path:
    """Write a deposit-shaped behavior.csv, one directory down, CR-delimited.

    Both details are deliberate. The Dryad archive extracts into a subdirectory,
    and a fixture built flat at the root cannot catch a finder that only looks
    there. And behavior.csv really does use bare CR line endings -- a fixture
    written with "\\n" would let a reader that splits on newlines pass here and
    read the whole real file as a single row.
    """
    d = root / "tracking_data"
    d.mkdir(parents=True, exist_ok=True)
    body = [",".join(str(x) for x in r) for r in rows]
    (d / "behavior.csv").write_bytes(
        ("\r".join([HDR] + body) + "\r").encode())
    return root


def run(root: Path, changed: int, complete: int):
    r = subprocess.run(
        [sys.executable, str(HERE / "mersch_task_crosstab.py"),
         "--raw", str(root), "--expect-changed", str(changed),
         "--expect-complete", str(complete)],
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
    print("\n".join("        | " + ln for ln in out.splitlines()[-30:]))


# Six complete ants, no cleaner anywhere, three of them changing.
NO_C = [
    ("1", "Ant1", "N", "N", "N", "N"),
    ("1", "Ant2", "F", "F", "F", "F"),
    ("1", "Ant3", "N", "N", "N", "F"),
    ("1", "Ant4", "F", "F", "N", "N"),
    ("1", "Ant5", "N", "F", "F", "F"),
    ("1", "Ant6", "N", "N", "N", "N"),
]

# Eleven complete ants. Cleaner appears on 1 of 11 labels in period 1 and 2 of
# 11 in period 4 -- rare -- yet is on the end of every one of the three changes.
VIA_C = [
    ("1", f"Ant{i}", "N", "N", "N", "N") for i in range(1, 5)
] + [
    ("1", f"Ant{i}", "F", "F", "F", "F") for i in range(5, 9)
] + [
    ("1", "Ant9",  "N", "N", "N", "C"),
    ("1", "Ant10", "F", "F", "F", "C"),
    ("1", "Ant11", "C", "C", "C", "N"),
]

# NO_C plus three ants that must not reach the denominator.
DROPPED = NO_C + [
    ("1", "Ant7", "Q", "N", "N", "N"),      # caste relabel, not a job change
    ("1", "Ant8", "N", "NA", "N", "N"),     # not labelled in every period
    ("1", "Ant9", "NA", "NA", "NA", "NA"),  # no label at all
]


def main() -> int:
    tmp = Path("/tmp/fx_crosstab")
    print("mersch_task_crosstab fixtures\n")

    build(tmp / "no_c", NO_C)
    expect("reproduce: matching expectation lets the split print",
           tmp / "no_c", 3, 6, 0,
           ["-> agrees", "WHAT THE CHANGES ARE"],
           absent=["the split is NOT printed",
                   "does not reproduce the expected counts"])

    # Same file, wrong expectation. The counts the file computes have not
    # changed; what has changed is whether they are the ones the headline
    # describes, and that is the only thing this branch is allowed to care about.
    expect("mismatch: wrong expectation suppresses the split entirely",
           tmp / "no_c", 4, 6, 1,
           ["does not reproduce the expected counts",
            "the split is NOT printed"],
           absent=["WHAT THE CHANGES ARE", "with a cleaner on one end"])

    expect("no_c: nurse <-> forager only, cleaner not over-represented",
           tmp / "no_c", 3, 6, 0,
           ["with a cleaner on one end : 0 of 3",
            "nurse <-> forager directly: 3 of 3",
            "changers never labelled cleaner in any period: 3 of 3",
            "is not over-represented against the null"],
           absent=["more changes than the null puts there"])

    build(tmp / "via_c", VIA_C)
    expect("via_c: rare cleaner on every change beats its own prevalence",
           tmp / "via_c", 3, 11, 0,
           ["with a cleaner on one end : 3 of 3",
            "nurse <-> forager directly: 0 of 3",
            "changers never labelled cleaner in any period: 0 of 3",
            "more changes than the null puts there"],
           absent=["is not over-represented against the null"])

    build(tmp / "dropped", DROPPED)
    expect("dropped: queen, incomplete and unlabelled stay out of the denominator",
           tmp / "dropped", 3, 6, 0,
           ["-> agrees",
            "ants ever labelled queen, dropped                 : 1",
            "1 of them carry a worker label in another period",
            "1 row(s) carry no label in any period"])

    print()
    if FAILS:
        print(f"{len(FAILS)} fixture(s) failed: {', '.join(FAILS)}")
        return 1
    print("all fixtures pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
