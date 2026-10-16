#!/usr/bin/env python3
"""What the 183 group changes are actually made of.

WHY THIS EXISTS
---------------
`183 of 386 ants whose task label is present in all four periods (queens
excluded) hold more than one label -- 47.4%` is the closest thing this project
has to a headline about task re-allocation, and it is a count of ants, not a
description of what they did. Two very different colonies produce it:

  A. ants moving between nurse and forager -- the two functionally distinct
     roles, at opposite ends of the colony, doing unrelated work;
  B. ants moving in and out of `cleaner`.

Mersch & Keller's three groups come from clustering positions in space, and
`cleaner` sits between the brood chamber and the outside. An ant whose position
drifts across that boundary is scored as changing group, and the discretisation
did the work rather than the colony. If the 183 are mostly B, "47% of workers
are re-allocated" overstates what happened by a wide margin, and the honest
sentence is about a graded position that was cut into three.

Nobody has looked. This file looks: it splits the changes by which labels are on
each end, and it says how many changers never touch `cleaner` at all -- those
are the ones whose re-allocation is unambiguous whatever one thinks of the
clustering.

THE REFERENCE POINT, WHICH IS THE WHOLE DIFFICULTY
--------------------------------------------------
"Most changes involve a cleaner" is not a finding on its own. If `cleaner` is
the most common label, most of *everything* involves a cleaner. The measurement
needs the comparison computed beside it, so this file builds a null that holds
fixed everything except the thing being asked about:

  * the number of changes at each period boundary -- taken as observed;
  * the label prevalences in each period -- taken as observed;
  * which label is on which end of a change -- destroyed.

Expected count for the ordered pair (i, j) at boundary k is then

    n_changes[k] * p_i[k] * p_j[k+1] / (1 - SUM_m p_m[k] * p_m[k+1])

summed over the three boundaries: the observed number of changes, redistributed
over ordered pairs of distinct labels at the observed per-period frequencies.
It is exact, not simulated. A `cleaner` share at the null is a `cleaner` label
that is common; a `cleaner` share well above it is the boundary effect this file
was written to find; well below it would say re-allocation actively avoids the
middle group, which would be a finding too.

THE GUARD, AND WHY IT COMES FIRST
---------------------------------
This file reads `behavior.csv` itself rather than importing the loader, so that
the split rests on a code path independent of the one that produced the figure
it is splitting. That independence is worth nothing unless the two agree, so the
first thing printed is this file's own reproduction of `changed of complete`. If
it does not match what is expected, the run stops there and reports nothing
about cleaners: a split of a population that is not the population the headline
describes is a number with no referent, and it would be quoted as though it had
one.

Both directions are tested -- see `test_task_crosstab.py`, where the guard is
given a matching expectation and a mismatching one.

EXIT CODES
----------
  0  the reproduction matched and the cross-tab printed
  1  the reproduction did not match, or `behavior.csv` could not be read
  2  called wrong (no --raw)
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

MISSING = {"", "na", "nan", "none", "null", "-", "?"}
TASK_NAMES = {"n": "nurse", "c": "cleaner", "f": "forager", "q": "queen"}
QUEEN = "queen"

# The real deposit, from `loaders/mersch.py --queens exclude`. Kept as a default
# rather than hard-wired so the fixtures can supply their own and exercise the
# guard in both polarities; a guard that only ever sees one input is not a guard.
EXPECT_CHANGED = 183
EXPECT_COMPLETE = 386


def _is_shadow(p: Path) -> bool:
    return p.name.startswith("._") or "__MACOSX" in p.parts


def find_behavior(raw_dir: Path) -> Path:
    """Locate behavior.csv anywhere under the deposit root.

    Duplicated from `mersch_mapping_second_route.py` on purpose. The point of
    this file is a code path that shares nothing with the loader whose number it
    checks, and a shared helper is a shared assumption about where the deposit
    is -- which is exactly the assumption that failed once already, when this
    project looked for `behavior.csv` at the deposit root and the Dryad archive
    had put it two directories down.
    """
    hits = [p for p in raw_dir.rglob("behavior.csv") if not _is_shadow(p)]
    if not hits:
        seen = sorted({p.parent.relative_to(raw_dir).as_posix() or "."
                       for p in raw_dir.rglob("*.csv") if not _is_shadow(p)})
        raise SystemExit(
            f"no behavior.csv under {raw_dir}\n"
            f"  directories that do contain a .csv: {', '.join(seen) or 'none'}")
    if len(hits) > 1:
        listed = "\n".join(f"    {p}" for p in sorted(hits))
        raise SystemExit(f"{len(hits)} behavior.csv files under {raw_dir}:\n"
                         f"{listed}\n  Refusing to choose.")
    return hits[0]


def normalize(v: str) -> str | None:
    """`N` -> nurse, `NA` -> None. None means "no label", not "a label named NA"."""
    s = (v or "").strip().lower()
    if s in MISSING:
        return None
    return TASK_NAMES.get(s, s)


def read_sequences(path: Path) -> tuple[list[dict], list[str]]:
    """One record per ant: colony, tag, and the four period labels.

    behavior.csv has CR-only line endings; `newline=None` is what makes it
    readable. Anything splitting on "\\n" sees the whole file as one line.
    """
    out, notes = [], []
    bad_period_cols = 0
    with path.open(newline=None) as fh:
        rdr = csv.DictReader(fh)
        header = rdr.fieldnames or []
        cols = []
        for k in range(1, 5):
            hit = next((h for h in header if h and h.strip().lower().replace(
                " ", "").replace("_", "") == f"groupperiod{k}"), None)
            cols.append(hit)
        if any(c is None for c in cols):
            raise SystemExit(
                f"behavior.csv is missing a group_period column: found "
                f"{[c for c in cols if c]} of four. Header: {header}")
        tag_col = next((h for h in header if h and h.strip().lower()
                        in ("tag_id", "tag", "ant", "ant_id")), None)
        col_col = next((h for h in header if h and h.strip().lower()
                        in ("colony", "colony_id", "col")), None)
        if tag_col is None or col_col is None:
            raise SystemExit(f"behavior.csv has no tag/colony column. "
                             f"Header: {header}")
        for r in rdr:
            labels = [normalize(r.get(c, "")) for c in cols]
            if all(x is None for x in labels):
                bad_period_cols += 1
            out.append(dict(colony=str(r[col_col]).strip(),
                            tag=str(r[tag_col]).strip(), labels=labels))
    if bad_period_cols:
        notes.append(f"{bad_period_cols} row(s) carry no label in any period. "
                     f"They are not in any denominator below, and they should "
                     f"not exist: on the real deposit every ant is labelled in "
                     f"period 1.")
    return out, notes


def partition(records: list[dict]) -> dict:
    """Complete / changer / queen sets, by this file's own reckoning.

    `complete` is an ant with a real label in every one of the four periods --
    the loader's denominator, re-derived here rather than imported. `queen` is
    any ant labelled queen in ANY period, dropped entirely: queen is a caste and
    a caste relabel is not task re-allocation, so an ant labelled Q once and N
    once must not be counted as having changed job.
    """
    complete, changers, queens, mixed = [], [], [], []
    for rec in records:
        labs = rec["labels"]
        if any(x is None for x in labs):
            continue
        is_queen = QUEEN in labs
        if is_queen:
            queens.append(rec)
            if any(x != QUEEN for x in labs):
                mixed.append(rec)
            continue
        complete.append(rec)
        if len(set(labs)) > 1:
            changers.append(rec)
    return dict(complete=complete, changers=changers, queens=queens,
                mixed=mixed)


def transitions(ants: list[dict]) -> tuple[Counter, list[int]]:
    """Ordered (from, to) counts across the three period boundaries.

    Counted per boundary rather than per ant, because an ant who goes
    nurse -> cleaner -> nurse made two moves and describing her as "one changer"
    loses the thing being asked about.
    """
    pairs = Counter()
    per_boundary = [0, 0, 0]
    for rec in ants:
        labs = rec["labels"]
        for k in range(3):
            if labs[k] != labs[k + 1]:
                pairs[(labs[k], labs[k + 1])] += 1
                per_boundary[k] += 1
    return pairs, per_boundary


def expected_pairs(ants: list[dict], per_boundary: list[int]) -> dict:
    """The null described in the docstring: same changes, labels re-drawn.

    Returns {(from, to): expected count}. Uses the per-period label frequencies
    of the same `ants`, so the comparison is within-population -- a null built
    on different individuals would be answering a different question.
    """
    freq = []
    for k in range(4):
        c = Counter(rec["labels"][k] for rec in ants)
        tot = sum(c.values()) or 1
        freq.append({lab: n / tot for lab, n in c.items()})
    labs = sorted({lab for f in freq for lab in f})
    exp: dict[tuple, float] = defaultdict(float)
    for k in range(3):
        same = sum(freq[k].get(m, 0.0) * freq[k + 1].get(m, 0.0) for m in labs)
        denom = 1.0 - same
        if denom <= 0 or per_boundary[k] == 0:
            continue
        for i in labs:
            for j in labs:
                if i == j:
                    continue
                exp[(i, j)] += (per_boundary[k] * freq[k].get(i, 0.0)
                                * freq[k + 1].get(j, 0.0) / denom)
    return dict(exp)


def report(part: dict, expect: tuple[int, int]) -> int:
    comp, chg = part["complete"], part["changers"]
    exp_chg, exp_comp = expect
    print("REPRODUCTION (this file's own count, before anything is split)")
    print(f"  ants labelled in all four periods, queens dropped : {len(comp)}"
          f"   expected {exp_comp}")
    print(f"  of those, holding more than one label             : {len(chg)}"
          f"   expected {exp_chg}")
    print(f"  ants ever labelled queen, dropped                 : "
          f"{len(part['queens'])}")
    if part["mixed"]:
        print(f"  !! {len(part['mixed'])} of them carry a worker label in "
              f"another period; a distinct-value count would score that as a "
              f"change of job, which is why they are dropped rather than kept.")
    if (len(chg), len(comp)) != (exp_chg, exp_comp):
        # Kept on single lines. A message wrapped mid-phrase is a message whose
        # fixtures end up asserting on fragments, and the fragment that survives
        # rewrapping is rarely the one that carries the meaning.
        print()
        print("!! this file does not reproduce the expected counts")
        print("!! the split is NOT printed, because it would not be describing "
              "the population the 47.4% describes")
        print("   A cross-tab of the wrong denominator reads exactly like a "
              "cross-tab of the right one,")
        print("   and would be quoted as though it were. Fix the disagreement "
              "first: one of the two")
        print("   code paths is wrong, and which one is not decidable from here.")
        return 1
    print("  -> agrees. The two code paths share no code, so the denominator is "
          "now\n     established twice rather than asserted once.\n")

    pairs, per_boundary = transitions(chg)
    exp = expected_pairs(comp, per_boundary)
    total = sum(pairs.values())
    print(f"WHAT THE CHANGES ARE ({total} moves across three period boundaries, "
          f"by {len(chg)} ants)")
    print(f"  moves per boundary: {per_boundary}")
    print(f"  {'from -> to':22} {'obs':>5} {'null':>7} {'obs/null':>9}")
    for (i, j), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
        e = exp.get((i, j), 0.0)
        ratio = f"{n / e:.2f}" if e > 0 else "  --"
        print(f"  {i + ' -> ' + j:22} {n:>5} {e:>7.1f} {ratio:>9}")

    touch = sum(n for (i, j), n in pairs.items() if "cleaner" in (i, j))
    e_touch = sum(e for (i, j), e in exp.items() if "cleaner" in (i, j))
    nf = sum(n for (i, j), n in pairs.items()
             if {i, j} == {"nurse", "forager"})
    e_nf = sum(e for (i, j), e in exp.items()
               if {i, j} == {"nurse", "forager"})
    print(f"\n  with a cleaner on one end : {touch} of {total} "
          f"({touch / max(1, total):.1%}), null {e_touch:.1f} "
          f"({e_touch / max(1, total):.1%})")
    print(f"  nurse <-> forager directly: {nf} of {total} "
          f"({nf / max(1, total):.1%}), null {e_nf:.1f} "
          f"({e_nf / max(1, total):.1%})")

    never_c = [r for r in chg if "cleaner" not in r["labels"]]
    print(f"\n  changers never labelled cleaner in any period: {len(never_c)} "
          f"of {len(chg)} ({len(never_c) / max(1, len(chg)):.1%})")
    print(f"  as a share of the {len(comp)} scoreable ants: "
          f"{len(never_c) / max(1, len(comp)):.1%}, against the "
          f"{len(chg) / max(1, len(comp)):.1%} the headline quotes")

    print("\nHOW TO READ THIS, AND WHAT IT DOES NOT SAY")
    if total and touch / total > 1.15 * (e_touch / total if total else 0):
        print("  Cleaner is on one end of more changes than the null puts "
              "there. That is\n  consistent with the middle group's boundary "
              "doing some of the work, and it\n  is not proof of it: the null "
              "destroys label identity but keeps prevalence,\n  so any real "
              "asymmetry in who moves where also lands here.")
    else:
        print("  Cleaner is not over-represented against the null. The changes "
              "involve it\n  about as often as its prevalence implies, so the "
              "boundary-artefact reading\n  is not supported by this "
              "measurement.")
    print("  Neither line licenses 'the colony re-allocated X% of its "
          "workforce'. Every\n  count here is conditioned on surviving all four "
          "periods -- 392 of 805 ants\n  on the real deposit -- and an ant that "
          "vanishes cannot be seen changing\n  anything. The survival fraction "
          "travels with the percentage or the\n  percentage does not travel.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Split the Mersch group changes "
                                             "by which labels are on each end.")
    ap.add_argument("--raw", required=True, help="deposit root (searched "
                                                 "recursively for behavior.csv)")
    ap.add_argument("--expect-changed", type=int, default=EXPECT_CHANGED)
    ap.add_argument("--expect-complete", type=int, default=EXPECT_COMPLETE)
    a = ap.parse_args()

    path = find_behavior(Path(a.raw))
    print(f"behaviour table: {path}")
    records, notes = read_sequences(path)
    print(f"  {len(records)} rows\n")
    for n in notes:
        print(f"  !! {n}")
    part = partition(records)
    return report(part, (a.expect_changed, a.expect_complete))


if __name__ == "__main__":
    raise SystemExit(main())
