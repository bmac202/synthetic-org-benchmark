"""The col1..col6 <-> 4/18/21/29/58/78 correspondence for Mersch 2013, and the
check that re-establishes it from the deposit instead of trusting this file.

WHY THIS MODULE EXISTS
----------------------
The Dryad deposit (10.5061/dryad.8d8h7) names its colonies twice and never says
the two names are the same thing. `behavior.csv` -- the only file carrying task
labels -- has a `colony` column reading 4, 18, 21, 29, 58, 78. The 246 network
matrices are named `network_col{1..6}_day{M}.txt`. The README lists both and
connects neither, the paper reports colony sizes only as the range "122 to 192
per colony" with no per-colony counts anywhere in the main text, the 27-page
supplement, or the twelve supplementary figures, and no metadata file in the
deposit states the correspondence.

This matters more here than it would elsewhere, because tag ids are reused
across colonies -- 218 of the 222 distinct ids occur in more than one colony.
A wrong pairing therefore does not fail. It silently relabels the animals: ant
"74" exists in several colonies and joining the wrong pair hands one ant's
network position to a different ant's task label, at a scale that looks like
data rather than like an error. Every downstream structure-x-task result rests
on this one correspondence being right.

HOW IT WAS ESTABLISHED
----------------------
Not by size matching. Six colony sizes against six node counts is six numbers
against six numbers, and a size match is evidence only when the counts are
distinct and the winner is unique -- here the two count vectors differ by a
constant offset in rank order (+3, +3, +3, +3, +3, +2), which produces a
plausible-looking ranking for a reason that has nothing to do with identity.
That ranking turned out to be correct, but it could not have been claimed.

It was established by set containment on the ant ids themselves. Strip the
`Ant` prefix from the matrix header tokens and the two files speak the same
integers. For each behavioural colony, ask which matrix column contains ALL of
its ants. On the real deposit exactly one column does, for each of the six, and
each column is claimed exactly once -- a perfect matching with no contest. The
runner-up in every case leaves between 26 and 49 of that colony's ants outside
the matrix, so the margin is not marginal.

The surplus runs the other way and is small and named: two or three ids per
colony (599, 614, 621, 647, 650, 663, 665, 673, 929, 954 across the deposit,
seventeen nodes in total) appear in the tracking networks and not in
behavior.csv. These are tracked ants with no task label. They are why the
matrix node counts sit a little above the behavioural censuses, and they must
be dropped or marked in any structure-x-task analysis -- not silently carried,
because an unlabelled node in a task cross-tab becomes a fifth task.

WHY THE MAP BELOW IS NOT THE AUTHORITY
--------------------------------------
A hardcoded correspondence is a claim about a directory, and directories get
re-fetched, re-extracted and re-organized. `resolve()` recomputes the matching
from whatever files are actually present and compares the result to `EXPECTED`.
If they ever disagree, that is either a different deposit or a bug, and both
deserve an exception rather than a result. The constant is documentation and a
tripwire; the deposit is the authority.

Caveat that travels with any census computed here. The paper states 122 to 192
workers per colony. The behavioural censuses are 99, 110, 128, 149, 157, 162
(each including one queen, so 98 to 161 workers) and the matrix node counts are
102, 113, 131, 152, 160, 164. TWO of the six fall below the 122 floor on either
count -- an earlier version of this note said four, which was simply miscounted
and was repeated into two other files before anyone checked it.

The shape of the mismatch matters more than the count. It is not a floor
problem, it is a shift: the largest colony here has 161 workers against a
published ceiling of 192, and nothing in the deposit comes near the top of the
band. Both ends sit low. The SI's edge-filtering account cannot explain it --
that account predicts matrices SMALLER than the behavioural census, and here
they are consistently three larger -- and the filtering explanation is now dead
on independent grounds, because the density and isolate measurements show these
are the raw networks. So the discrepancy stands unexplained with its best
candidate eliminated. Do not report a Mersch colony size as the colony's size
without that attached.

WHAT THIS DOES NOT ESTABLISH
----------------------------
Which real colony any of these is. The mapping says that the ants in
`network_col1_*` are the ants in behavior.csv's colony 4; it says nothing about
whether that is the colony the paper calls colony 1 in figures S11 and S12, and
nothing about which colony any published per-colony statistic refers to. Those
are three vocabularies, and only two of them have now been connected.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# behaviour-table colony label -> matrix filename label.
# Established by set containment (see the module docstring); re-derived and
# cross-checked by resolve() on every load rather than trusted.
EXPECTED: dict[str, str] = {
    "4": "col1",
    "18": "col2",
    "21": "col3",
    "29": "col4",
    "58": "col5",
    "78": "col6",
}

# The margin the containment test showed on the deposit as fetched: the
# second-best column for each colony left this many of its ants unmatched.
# Recorded so a future run that comes back with a margin of 2 is visibly not
# the same evidence, even though it would still produce a "unique" answer.
OBSERVED_MIN_RUNNER_UP_MISSES = 26

NET_RE = re.compile(r"network_col(\d+)_day(\d+)", re.I)


class MappingError(RuntimeError):
    """The correspondence could not be re-established, or disagreed with EXPECTED."""


def tag_int(token: str) -> int | None:
    """`Ant4` -> 4, `74` -> 74, junk -> None.

    The two files render the same ant differently: matrix headers carry an
    `Ant` prefix, behavior.csv does not. The first attempt at this comparison
    matched the strings as printed, found a Jaccard overlap of exactly 0.0 for
    all 36 pairs, and that zero was a property of the comparison rather than of
    the deposit. Normalizing to the integer is the whole fix, and it belongs in
    one function so no caller re-invents a partial version of it.
    """
    digits = "".join(ch for ch in token if ch.isdigit())
    return int(digits) if digits else None


def _read_header_ids(path: Path) -> set[int]:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    line = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")[0]
    out = set()
    for tok in line.split(","):
        v = tag_int(tok)
        if v is not None:
            out.add(v)
    return out


def _is_shadow(p: Path) -> bool:
    return p.name.startswith("._") or "__MACOSX" in p.parts


def matrix_ids(raw_dir: Path) -> dict[str, set[int]]:
    """{'col1': {ids seen on any day}, ...} from the matrix headers."""
    out: dict[str, set[int]] = {}
    for p in raw_dir.rglob("network_col*_day*.txt"):
        if _is_shadow(p):
            continue
        m = NET_RE.search(p.name)
        if not m:
            continue
        out.setdefault("col" + m.group(1), set()).update(_read_header_ids(p))
    return out


def behavior_ids(raw_dir: Path) -> dict[str, set[int]]:
    """{'4': {tag ids}, ...} from behavior.csv.

    behavior.csv has CR-only line endings. `newline=None` puts Python in
    universal-newline mode, which is what makes this readable at all -- anything
    that splits on "\\n" reads all 805 rows as a single line.
    """
    hits = [p for p in raw_dir.rglob("behavior.csv") if not _is_shadow(p)]
    if not hits:
        raise MappingError(f"no behavior.csv under {raw_dir}")
    out: dict[str, set[int]] = {}
    with hits[0].open(newline=None) as fh:
        for row in csv.DictReader(fh):
            v = tag_int(row.get("tag_id", ""))
            if v is not None:
                out.setdefault(str(row["colony"]).strip(), set()).add(v)
    return out


def resolve(raw_dir: Path, strict: bool = True) -> dict:
    """Re-derive the colony correspondence from the files. Returns a report dict.

    The test is containment, not overlap: the right matrix column for a colony
    is the one holding ALL of that colony's ants. Overlap alone cannot decide it
    because the reused ids guarantee every pair overlaps somewhere.

    Raises MappingError under `strict` when the matching is not unique, is not
    total, or disagrees with EXPECTED -- because a partly-resolved mapping is
    not a weaker version of a resolved one, it is a relabelling machine.
    """
    B = behavior_ids(raw_dir)
    M = matrix_ids(raw_dir)
    if not M:
        raise MappingError(f"no network_col*_day*.txt under {raw_dir}")

    rows, derived = [], {}
    for c in sorted(B, key=lambda x: int(x)):
        scored = []
        for m in sorted(M):
            missing = len(B[c] - M[m])          # behavioural ants absent from matrix
            scored.append((missing, len(M[m] - B[c]), m))
        scored.sort()
        best_missing, surplus, best = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else None
        rows.append({
            "colony": c,
            "matrix": best,
            "n_behavior": len(B[c]),
            "n_matrix": len(M[best]),
            "behavior_ants_absent_from_matrix": best_missing,
            "matrix_ids_absent_from_behavior": sorted(M[best] - B[c]),
            "runner_up_misses": runner_up,
        })
        if best_missing == 0:
            derived[c] = best

    problems = []
    complete = len(derived) == len(B)
    if not complete:
        bad = [r["colony"] for r in rows if r["behavior_ants_absent_from_matrix"]]
        problems.append(
            f"no matrix contains every ant of colon{'y' if len(bad)==1 else 'ies'} "
            f"{', '.join(bad)}. Containment is the whole test; without it the "
            f"pairing is a size guess.")
    if len(set(derived.values())) != len(derived):
        dupes = [m for m in set(derived.values())
                 if list(derived.values()).count(m) > 1]
        problems.append(
            f"matrix column(s) {dupes} claimed by more than one colony, so the "
            f"matching is not one-to-one and at least one colony is misassigned.")
    thin = [r for r in rows if r["runner_up_misses"] is not None
            and r["runner_up_misses"] < 5]
    if thin:
        problems.append(
            "the second-best column is within 5 ants for "
            + ", ".join(f"colony {r['colony']}" for r in thin)
            + " -- unique, but not by a margin that distinguishes identity from "
              "coincidence.")
    # Compare only where both speak about the same colony. A fixture or a subset
    # of the deposit legitimately has fewer colonies; a DISAGREEMENT about a
    # colony both know is the thing worth stopping for.
    clash = {c: (derived[c], EXPECTED[c]) for c in derived
             if c in EXPECTED and derived[c] != EXPECTED[c]}
    if clash:
        problems.append(
            f"derived mapping disagrees with the recorded EXPECTED for "
            f"{ {c: f'derived {a} vs expected {b}' for c, (a, b) in clash.items()} }. "
            f"One of them is wrong and neither should be used until it is known "
            f"which.")

    unlabelled = {r["colony"]: r["matrix_ids_absent_from_behavior"] for r in rows}
    report = {
        "mapping": dict(derived) if not problems else None,
        "method": ("set containment on integer-normalized tag ids: the matrix "
                   "column holding ALL of a colony's ants, required to be unique "
                   "and to agree with the recorded mapping"),
        "rows": rows,
        "unlabelled_nodes": {c: v for c, v in unlabelled.items() if v},
        "n_unlabelled_nodes": sum(len(v) for v in unlabelled.values()),
        "problems": problems,
    }
    if problems and strict:
        raise MappingError(
            "the Mersch colony correspondence did not re-establish:\n  - "
            + "\n  - ".join(problems)
            + "\n  A wrong pairing does not fail loudly here -- tag ids are reused "
              "across colonies, so it hands one ant's network position to another "
              "ant's task label. Nothing joining structure to task should run.")
    return report


def main() -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="re-derive the Mersch colony mapping")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--loose", action="store_true",
                    help="report problems instead of raising, for diagnosis")
    a = ap.parse_args()
    rep = resolve(Path(a.raw), strict=not a.loose)
    print(json.dumps(rep, indent=2))
    print("\n  mapping:", rep["mapping"] or "NOT ESTABLISHED")
    print(f"  unlabelled tracked ants: {rep['n_unlabelled_nodes']} "
          f"(in the networks, absent from behavior.csv)")
    for r in rep["rows"]:
        print(f"    colony {r['colony']:>2} -> {r['matrix']}  "
              f"behaviour n={r['n_behavior']:>3}  matrix n={r['n_matrix']:>3}  "
              f"misses={r['behavior_ants_absent_from_matrix']}  "
              f"runner-up misses={r['runner_up_misses']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
