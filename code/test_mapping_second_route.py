#!/usr/bin/env python3
"""Fixtures for mersch_mapping_second_route.py, in both polarities.

A check that only ever passes is decoration. Each fixture below is a deposit-
shaped directory built to make the checker return a specific answer, including
the answers we do not want to see, so that a green run on the real deposit means
something.

  good        mapping recoverable, decline profiles discriminate, offsets exact
  disagree    containment and decline shape point at different columns
  flat        all six colonies decline identically -- unique winner, zero margin
  drift       offset moves because an ant never in behavior.csv leaves the roster
  relabel     offset moves because an ant goes `NA` and is then labelled again
  absent      offset moves because a labelled ant is not on the matrix roster
  nested      deposit sits one directory down, as the Dryad archive extracts
  twocopies   a stale behavior.csv beside a fresh one -- must refuse, not pick
  missing     no behavior.csv at all -- must say where it looked

`nested`, `twocopies` and `missing` were added on 31 July after the first real
run died with "no behavior.csv under ...". The first four fixtures all built the
deposit flat at the root, so none of them could see that the finder was wrong. A
fixture set that only ever builds the shape the code expects is a fixture set
that tests the code against itself.

`relabel` and `absent` were added the same day, for a worse reason. `drift` built
ordinary attrition -- a surplus ant, never in behavior.csv, dropping off the
roster -- and the checker printed "some ant is unlabelled in one period and
labelled in a later one", which is a different mechanism and false for this
fixture. The fixture passed, because it asserted only that drift was reported and
never what was said about it. Three mechanisms move the offset; there are now
three fixtures, one per mechanism, and each asserts that the OTHER two are not
claimed. An explanation is killed by a fixture, not by an argument, and this one
needed killing.

Exit codes: 0 pass, 1 the check ran and did not pass or could not be completed,
2 reserved for "you called this wrong" (no argument). A caller scripting this
needs "it failed" and "you held it wrong" separable.

Run:  python3 test_mapping_second_route.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLONIES = ["4", "18", "21", "29", "58", "78"]
COL_OF = {"4": 1, "18": 2, "21": 3, "29": 4, "58": 5, "78": 6}
DAYS_OF_PERIOD = {0: [1, 6], 1: [12, 17], 2: [22, 27], 3: [32, 41]}


def build(root: Path, profiles: dict, surplus: dict, matrix_profiles=None,
          subdir: str = ""):
    """profiles[colony] = [n1,n2,n3,n4] labelled ants per period (nested).

    matrix_profiles, if given, overrides the roster sizes written into the
    matrices, which is how the `disagree` fixture is made: membership still
    satisfies containment, but the decline shape points elsewhere.

    subdir puts the whole deposit one level down, which is how the real Dryad
    archive extracts and is what broke the first real run.
    """
    shutil.rmtree(root, ignore_errors=True)
    top, root = root, (root / subdir if subdir else root)
    root.mkdir(parents=True)
    assert top.exists()
    base = 1000
    ids_of, rows = {}, []
    for c in COLONIES:
        n = profiles[c][0]
        ids_of[c] = list(range(base, base + n))
        base += n + surplus[c]
        for i, tag in enumerate(ids_of[c]):
            # An ant present in the first k periods and gone after: the literal
            # NA is what the real file carries and what the checker must read.
            k = sum(1 for p in range(4) if i < profiles[c][p])
            labs = [("N" if (i % 3) else "F") if p < k else "NA" for p in range(4)]
            rows.append([str(tag), c] + labs)
    hdr = "tag_id,colony,group_period1,group_period2,group_period3,group_period4"
    # CR-only line endings, as the real deposit has.
    (root / "behavior.csv").write_bytes(
        ("\r".join([hdr] + [",".join(r) for r in rows]) + "\r").encode())

    for c in COLONIES:
        col = COL_OF[c]
        surp = [f"S{col}_{j}" for j in range(surplus[c])]
        prof = (matrix_profiles or profiles)[c]
        for p in range(4):
            keep = ["Ant%d" % t for t in ids_of[c][:prof[p]]] + surp
            for d in DAYS_OF_PERIOD[p]:
                n = len(keep)
                lines = [",".join(keep)]
                for i in range(n):
                    lines.append(",".join("0" if i == j else "1"
                                          for j in range(n)))
                (root / f"network_col{col}_day{d}.txt").write_text(
                    "\n".join(lines) + "\n")


def drop_from_matrix(path: Path, token: str | None = None):
    """Remove one ant from a matrix file, header and body together.

    Dropping the header token alone would leave the body one row too long, which
    read_matrix refuses outright -- so the fixture would test the matrix reader's
    error path instead of the mechanism it is trying to build.
    """
    lines = path.read_text().strip().split("\n")
    ids = lines[0].split(",")
    ids.pop(len(ids) - 1 if token is None else ids.index(token))
    n = len(ids)
    path.write_text("\n".join([",".join(ids)] + [
        ",".join("0" if i == j else "1" for j in range(n))
        for i in range(n)]) + "\n")


def set_labels(root: Path, colony: str, nth: int, labels: list) -> str:
    """Rewrite one ant's four period labels in behavior.csv. Returns its tag id."""
    p = root / "behavior.csv"
    rows = p.read_bytes().decode().strip("\r").split("\r")
    hdr, body = rows[0], [r.split(",") for r in rows[1:]]
    row = body[[i for i, r in enumerate(body) if r[1] == colony][nth]]
    row[2:6] = labels
    p.write_bytes(("\r".join([hdr] + [",".join(r) for r in body]) + "\r").encode())
    return row[0]


def run(root: Path):
    r = subprocess.run([sys.executable,
                        str(HERE / "mersch_mapping_second_route.py"), str(root)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


DECLINE = {"4":  [40, 34, 28, 20], "18": [46, 39, 31, 21],
           "21": [52, 46, 38, 32], "29": [34, 25, 19, 12],
           "58": [58, 50, 33, 24], "78": [64, 55, 45, 35]}
SURPLUS = {"4": 3, "18": 3, "21": 3, "29": 3, "58": 3, "78": 2}

FAILS = []


def expect(name: str, root: Path, want_rc, needles, absent=()):
    rc, out = run(root)
    ok = (rc in want_rc if isinstance(want_rc, (set, tuple, list)) else rc == want_rc)
    missing = [n for n in needles if n not in out]
    present = [n for n in absent if n in out]
    if ok and not missing and not present:
        print(f"  PASS  {name}")
        return
    FAILS.append(name)
    print(f"  FAIL  {name}: rc={rc} want={want_rc}")
    for n in missing:
        print(f"        expected in output, absent: {n!r}")
    for n in present:
        print(f"        expected absent, present:  {n!r}")
    print("\n".join("        | " + ln for ln in out.splitlines()[-25:]))


def main() -> int:
    tmp = Path("/tmp/fx_map2")
    print("mersch_mapping_second_route fixtures\n")

    build(tmp / "good", DECLINE, SURPLUS)
    expect("good: agrees with containment, exact, positive margins",
           tmp / "good", 0,
           ["All 6 colonies agree", "agree",
            "`NA` is pure attrition deposit-wide"], absent=["DISAGREE", "!!"])

    # Colony 4's matrices decline on colony 18's shape. Containment is untouched
    # -- every ant of colony 4 is still in col1 -- so the two routes must part.
    mp = dict(DECLINE)
    mp["4"] = [40, 33, 25, 15]
    build(tmp / "disagree", DECLINE, SURPLUS, matrix_profiles=mp)
    expect("disagree: decline shape contradicts containment",
           tmp / "disagree", 1, ["DISAGREE", "nothing colony-level"])

    # Every colony halves in the same proportions -> the profiles cannot tell the
    # columns apart, and a unique winner is then meaningless.
    flat = {c: [40, 34, 28, 20] for c in COLONIES}
    build(tmp / "flat", flat, {c: 3 for c in COLONIES})
    expect("flat: identical profiles are reported as non-discriminating",
           tmp / "flat", 1, ["no power for this colony", "coin landing on its edge"])

    # MECHANISM A. One surplus ant -- never in behavior.csv, so it can never
    # gain or lose a label -- drops off the roster in periods 3 and 4. The offset
    # must move, and the reason must be named as attrition among never-labelled
    # ants. It must NOT be reported as relabelling: that is what this file said
    # for a month, and it is impossible here by construction.
    build(tmp / "drift", DECLINE, SURPLUS)
    for d in (22, 27, 32, 41):
        drop_from_matrix(tmp / "drift" / f"network_col1_day{d}.txt")
    expect("drift: attrition among never-labelled ants, named as such",
           tmp / "drift", 0,
           ["are not constant", "separate finding",
            "never in behavior.csv [3, 3, 2, 2]",
            "0 ants in colony 4 carry a real label after an",
            "`NA` is pure attrition deposit-wide"],
           absent=["`NA` is not pure attrition here",
                   "does not reproduce the offsets"])

    # MECHANISM B. An ant with a full record goes `NA` in period 2 and is
    # labelled again in period 3. The rosters are untouched, so the offset moves
    # for the opposite reason, and now the relabelling claim is the true one.
    # The gap sits in period 2 rather than period 3 for a dull reason worth
    # recording: in period 3 the perturbed profile ties with col3 at score 1,
    # the colony is reported as having no margin, and the fixture then tests the
    # tie path instead of the mechanism. A fixture has to reach the branch it
    # names.
    build(tmp / "relabel", DECLINE, SURPLUS)
    tag = set_labels(tmp / "relabel", "4", 0, ["N", "NA", "N", "N"])
    expect("relabel: a label after a gap is measured, not assumed",
           tmp / "relabel", 0,
           ["are not constant", "`NA` in this period [0, 1, 0, 0]",
            "carry a real label after an `NA`", f"[{tag}]",
            "`NA` is not pure attrition here",
            # The deposit-wide shape census must flip too, on the same evidence.
            # One ant with a gap is enough to make the survival-series reading
            # false, and a census that still reports it would be reassuring on
            # a deposit where it does not hold.
            "T.TT", "are labelled again after an `NA`",
            "a roster built from them can grow"],
           absent=["0 ants in colony 4 carry a real label after an",
                   "`NA` is pure attrition deposit-wide",
                   "does not reproduce the offsets"])

    # MECHANISM C. A labelled ant is missing from the matrix roster -- the one
    # direction the old note did not consider at all, and the only one that
    # pushes the offset DOWN without anything leaving the behaviour table.
    build(tmp / "absent", DECLINE, SURPLUS)
    for d in (22, 27, 32, 41):
        drop_from_matrix(tmp / "absent" / f"network_col1_day{d}.txt", "Ant1000")
    expect("absent: a labelled ant off the roster is reported as its own case",
           tmp / "absent", 0,
           ["are not constant", "labelled but off the matrix [0, 0, 1, 1]",
            "0 ants in colony 4 carry a real label after an",
            "`NA` is pure attrition deposit-wide"],
           absent=["`NA` is not pure attrition here",
                   "does not reproduce the offsets"])

    # The real deposit extracts into a subdirectory. The first real run died here
    # with "no behavior.csv under ..." because this file looked only at the root
    # while mersch_map had always used rglob.
    build(tmp / "nested", DECLINE, SURPLUS, subdir="doi_10.5061_dryad.8d8h7/data")
    expect("nested: finds the deposit one level down",
           tmp / "nested", 0, ["All 6 colonies agree"])

    # A stale copy alongside a fresh one must be refused, not silently resolved
    # by sort order -- the two tables can differ.
    build(tmp / "twocopies", DECLINE, SURPLUS)
    (tmp / "twocopies" / "old").mkdir()
    shutil.copy(tmp / "twocopies" / "behavior.csv",
                tmp / "twocopies" / "old" / "behavior.csv")
    expect("two copies: refuses to choose",
           tmp / "twocopies", 1, ["2 behavior.csv files", "Refusing to choose"])

    # And the not-found message must name where it looked, so the next person
    # does not have to read the source to find out.
    empty = tmp / "empty"
    shutil.rmtree(empty, ignore_errors=True)
    (empty / "elsewhere").mkdir(parents=True)
    (empty / "elsewhere" / "trials.csv").write_text("a,b\n1,2\n")
    # rc 1, not 2: 2 is reserved for "you called this wrong" (no argument), 1 is
    # "the check ran and did not pass or could not be completed". A caller
    # scripting this needs those separable.
    expect("missing: says where it looked and what it did find",
           empty, 1, ["no behavior.csv under", "searched recursively",
                      "elsewhere"])

    print()
    if FAILS:
        print(f"{len(FAILS)} fixture(s) failed: {', '.join(FAILS)}")
        return 1
    print("9 fixtures pass, in both polarities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
