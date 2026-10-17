#!/usr/bin/env python3
"""A second, independent route to the Mersch colony mapping.

WHY THIS EXISTS
---------------
`4->col1, 18->col2, 21->col3, 29->col4, 58->col5, 78->col6` is currently derived
by set containment on tag ids: each behaviour colony's ants appear in exactly one
matrix column, with the runner-up column missing at least 26 of them. That is a
strong inference. It is also a single inference from a single feature, and if it
is wrong then every colony-level number in this project is a relabelling that no
downstream check could catch. The email to Mersch asks her to confirm it. This
file is what we do if she does not reply.

THE SECOND ROUTE
----------------
`behavior.csv` carries `group_period1..4`, with the literal string `NA` where an
ant has no label in that period. If `NA` marks an ant that is no longer in the
colony, then the per-period count of labelled ants is a four-number decline
profile computed entirely from a text column in the behaviour table.

The matrices carry their own four-number decline profile, computed entirely from
matrix headers -- the roster is exactly constant within each period and steps only
at period boundaries.

These two profiles rest on disjoint evidence. One is a missingness pattern in a
CSV column; the other is roster cardinality in a set of matrix files. Neither
uses tag-id membership, which is the only thing the containment argument uses. So
if each behaviour colony's profile picks out exactly one matrix column, the
mapping is confirmed by a route that shares no assumption with the first.

WHAT WOULD MAKE THIS UNINFORMATIVE, AND IS THEREFORE CHECKED
------------------------------------------------------------
A unique match proves nothing if the six profiles are too similar to each other:
if every colony roughly halves over the recording, every colony matches every
column and "unique best" is an artefact of rounding. So this reports the MARGIN --
how far the winner beats the runner-up -- and treats a unique match with a margin
at or near zero as a failure. A check that cannot fail is not a check.

The comparison is on the *shape* of the decline, not on absolute size, because
the matrices are known to carry a few individuals the behaviour table does not.
The score is the spread of the per-period offset `matrix - behaviour`: zero
spread means the two profiles decline in lockstep and differ by a constant. A
non-constant offset is reported separately, because it is a finding about the
deposit rather than about the mapping.

CORRECTION, 31 July, on what a non-constant offset means
--------------------------------------------------------
This file used to say, in the paragraph above and again in the note it printed:
"a non-constant offset ... would mean `NA` is not simply attrition -- an ant
could be unlabelled in period 3 and labelled again in period 4". That named one
mechanism out of three and tested none of them, and on the real deposit it is
the wrong one: five of six colonies drift, and the ants responsible are surplus
matrix ants that never appear in `behavior.csv` at all, so they cannot regain a
label they never had. The offset is set algebra and it decomposes exactly:

    offset[k] = |M_k| - |L_k| = never[k] + na_here[k] - missing[k]

with `M_k` the matrix roster in period k, `L_k` the ants carrying a real label
in period k, and

    never[k]    on the roster, absent from behavior.csv entirely
    na_here[k]  in behavior.csv, but `NA` in this period
    missing[k]  labelled in this period, not on the roster

Any of the three can move the offset, and they mean different things: the first
is ordinary attrition among unlabelled individuals, the second includes but is
not limited to relabelling, the third is an ant the matrices lost. So the file
now prints the decomposition and names whichever component actually moved, and
counts relabellings directly -- ants with a real label following an `NA` -- rather
than inferring them. A note contradicted by the number printed beside it is worse
than no note at all, and this one was.

Run:  python3 mersch_mapping_second_route.py data/raw/mersch_keller_2013
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loaders.common import MISSING, stream_rows          # noqa: E402
from loaders.mersch_net import matrix_files, read_matrix  # noqa: E402
from loaders import mersch_map                            # noqa: E402
import re                                                 # noqa: E402

NET_RE = re.compile(r"network_col(\d+)_day(\d+)", re.I)

# Same boundaries as mersch_centralization.PERIOD_OF_DAY. Duplicated rather than
# imported so this file does not depend on the instrument it is meant to check.
def period_of_day(d: int) -> int:
    return 0 if d <= 11 else 1 if d <= 21 else 2 if d <= 31 else 3


def _is_shadow(p: Path) -> bool:
    return p.name.startswith("._") or "__MACOSX" in p.parts


def find_behavior(raw_dir: Path) -> Path:
    """Locate behavior.csv anywhere under the deposit root.

    CORRECTION, 31 July. This used to be `raw_dir / "behavior.csv"` and failed on
    the real deposit with "no behavior.csv under ...", because the Dryad archive
    extracts into a subdirectory. `mersch_map` has always used rglob here; this
    file did not, so the two disagreed about where the deposit is -- and a
    checker that cannot find the file it checks is worse than no checker,
    because "not found" and "found and fine" are one keystroke apart in a log.

    Two candidates are refused rather than resolved by picking the first. If a
    re-fetch has left an old copy alongside a new one, the two behaviour tables
    may differ, and silently reading whichever sorts first is how a stale file
    ends up underwriting a mapping.
    """
    hits = [p for p in raw_dir.rglob("behavior.csv") if not _is_shadow(p)]
    if not hits:
        seen = sorted({p.parent.relative_to(raw_dir).as_posix() or "."
                       for p in raw_dir.rglob("*.csv") if not _is_shadow(p)})
        raise SystemExit(
            f"no behavior.csv under {raw_dir}\n"
            f"  searched recursively, ignoring ._ shadows.\n"
            f"  directories that do contain a .csv: {', '.join(seen) or 'none'}")
    if len(hits) > 1:
        listed = "\n".join(f"    {p}" for p in sorted(hits))
        raise SystemExit(
            f"{len(hits)} behavior.csv files under {raw_dir}:\n{listed}\n"
            f"  Refusing to choose. Point this at the one you mean, or remove "
            f"the stale copy.")
    return hits[0]


def behaviour_profiles(raw_dir: Path) -> tuple[dict, dict, list]:
    """Per colony: labelled-ant counts per period, and the id sets behind them.

    The counts are what the decline profile is scored on. The sets are what the
    offset decomposition needs, and they are the whole reason this function grew:
    a count can tell you the matrix carries three more ants than the behaviour
    table does, and nothing whatever about which three or why.

    Returns (counts, detail, notes) where detail[colony] carries
      "labelled"  four sets of tag ids with a real label in that period
      "all"       every tag id the behaviour table gives this colony
      "relabel"   ids carrying a real label in some period after an `NA`
      "patterns"  census of the four-period labelled/`NA` pattern, per ant
    """
    path = find_behavior(raw_dir)
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    labelled: dict[str, list[set]] = defaultdict(
        lambda: [set(), set(), set(), set()])
    allids: dict[str, set] = defaultdict(set)
    relabel: dict[str, set] = defaultdict(set)
    patterns: dict[str, dict[tuple, int]] = defaultdict(lambda: defaultdict(int))
    rows = untagged = 0
    notes = []
    seen_cols = set()
    for r in stream_rows(path):
        rows += 1
        colony = (r.get("colony") or r.get("Colony") or "").strip()
        if not colony:
            continue
        seen_cols.add(colony)
        tag = mersch_map.tag_int(r.get("tag_id") or r.get("tag") or "")
        if tag is None:
            untagged += 1
        else:
            allids[colony].add(tag)
        has = [False, False, False, False]
        for k in range(4):
            for key in (f"group_period{k + 1}", f"group period{k + 1}",
                        f"groupperiod{k + 1}"):
                if key in r:
                    v = (r[key] or "").strip()
                    has[k] = v.lower() not in MISSING
                    break
        patterns[colony][tuple(has)] += 1
        for k in range(4):
            if has[k]:
                counts[colony][k] += 1
                if tag is not None:
                    labelled[colony][k].add(tag)
        # A real label following a gap. This is the mechanism the drift note used
        # to assert without ever measuring it; measuring it costs one comparison.
        if tag is not None and any(has[j] and not all(has[:j]) for j in range(4)):
            relabel[colony].add(tag)
    notes.append(f"behaviour table: {path}")
    notes.append(f"behavior.csv: {rows} rows, {len(seen_cols)} colony labels "
                 f"{sorted(seen_cols, key=lambda x: int(x) if x.isdigit() else 0)}")
    if untagged:
        # Counts would still be right and the decomposition silently would not,
        # because it works on ids. Better to say so than to let the identity
        # check below fail with no explanation attached.
        notes.append(f"  !! {untagged} row(s) have no readable tag_id. They are "
                     f"counted in the profiles and invisible to the decomposition.")
    detail = {c: {"labelled": labelled[c], "all": allids[c], "relabel": relabel[c],
                  "patterns": dict(patterns[c])} for c in counts}
    return dict(counts), detail, notes


def matrix_profiles(raw_dir: Path) -> tuple[dict, dict, list]:
    """Per matrix column, the roster size in each period, plus a constancy check.

    Returns (profiles, rosters, notes); rosters[col][k] is the set of normalized
    tag ids on that roster, or None where no matrix covers the period.
    """
    per: dict[str, dict[int, set]] = defaultdict(lambda: defaultdict(set))
    ids_per: dict[str, dict[int, set]] = defaultdict(dict)
    notes = []
    files = matrix_files(raw_dir)
    if not files:
        raise SystemExit(f"no network_col*_day*.txt under {raw_dir}")
    collisions = []
    for p in sorted(files):
        m = NET_RE.search(p.name)
        if not m:
            continue
        col, day = "col" + m.group(1), int(m.group(2))
        ids, _ = read_matrix(p)
        ints = {t for t in (mersch_map.tag_int(x) for x in ids) if t is not None}
        if len(ints) != len(ids):
            collisions.append((p.name, len(ids), len(ints)))
        k = period_of_day(day)
        per[col][k].add(len(ids))
        if len(ints) >= len(ids_per[col].get(k, ())):
            ids_per[col][k] = ints
    if collisions:
        # Two header tokens normalizing to one integer would shrink the roster
        # set below the count the score uses, and the identity check would then
        # fire with no visible cause. Name it where it happens.
        notes.append("  !! header tokens do not normalize one-to-one: "
                     + "; ".join(f"{n} {a} tokens -> {b} ids"
                                 for n, a, b in collisions[:5]))
    out, rosters = {}, {}
    for col in sorted(per):
        prof, wobble = [], []
        for k in range(4):
            sizes = per[col].get(k) or set()
            if not sizes:
                prof.append(None)
                continue
            prof.append(max(sizes))
            if len(sizes) > 1:
                wobble.append((k + 1, sorted(sizes)))
        out[col] = prof
        rosters[col] = [ids_per[col].get(k) for k in range(4)]
        if wobble:
            # The roster being exactly constant within a period is an observed
            # property, not a definition. If it ever stops holding, the profile
            # below is a maximum standing in for a range and the match is weaker
            # than it looks -- so say it here rather than let it pass silently.
            notes.append(f"  !! {col} roster is NOT constant within period(s): "
                         + "; ".join(f"p{k}={s}" for k, s in wobble))
    return out, rosters, notes


def spread(offsets: list[int]) -> int:
    return max(offsets) - min(offsets)


def label_shape(detail: dict) -> list[str]:
    """Census the four-period label patterns, and say what shape they have.

    This is a fact about the whole deposit that the mapping does not need and
    everything downstream does. If every ant's pattern is a run of labels
    followed by a run of `NA` -- a prefix -- then `NA` means "gone" and the four
    columns are a survival series, so a roster can only shrink. If any ant is
    labelled after a gap, `NA` means "not scored this period" instead, and any
    code treating the label columns as a monotone roster is wrong in a way no
    downstream check would catch.

    Printed unconditionally rather than only when the offset drifts, because
    "the property holds" and "nobody looked" are the two readings of silence,
    and only one of them is worth anything.
    """
    census: dict[tuple, int] = defaultdict(int)
    for d in detail.values():
        for pat, n in d["patterns"].items():
            census[pat] += n
    tot = sum(census.values())
    out = ["\nlabel patterns in behavior.csv (T = a real label, . = `NA`)"]
    for pat, n in sorted(census.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f"  {''.join('T' if x else '.' for x in pat)}   {n:>5} "
                   f"of {tot} ants")
    # True sorts above False, so a prefix pattern is one already in sorted order.
    bad = [p for p in census if list(p) != sorted(p, reverse=True)]
    gaps = sum(n for p, n in census.items() if p in set(bad))
    first = sum(n for p, n in census.items() if p and p[0])
    never = census.get((False, False, False, False), 0)
    out.append(f"  {first} of {tot} ants carry a label in period 1; {never} carry "
               f"none in any period.")
    if bad:
        out.append(f"  !! {gaps} of {tot} ants are labelled again after an `NA`, in "
                   f"{len(bad)} distinct pattern(s). `NA` does NOT mean 'gone' in "
                   f"this deposit -- it means 'not scored this period' at least "
                   f"sometimes, so the per-period label columns are not a survival "
                   f"series and a roster built from them can grow.")
    else:
        out.append(f"  Every pattern is a run of labels followed by a run of `NA`: "
                   f"no ant, in any colony, is labelled after a gap. `NA` is pure "
                   f"attrition deposit-wide, so the four columns are a survival "
                   f"series and any roster read off them can only shrink.")
    return out


def decompose(labelled: list[set], allids: set, roster: list[set]) -> list[tuple]:
    """Split `matrix - behaviour` into its three components, period by period.

        offset[k] = |M_k| - |L_k| = never[k] + na_here[k] - missing[k]

    never    on the roster, absent from behavior.csv entirely -- an animal the
             behaviour table never scored, so its departure is plain attrition
    na_here  in behavior.csv, `NA` in this period -- which is attrition too
             unless the ant is labelled again later, hence `relabel`
    missing  a labelled ant the matrix roster does not carry, which is the one
             direction the old note did not consider at all

    The identity is set algebra and cannot fail on consistent inputs. It is
    checked anyway, because what it actually catches is the decomposition being
    computed against a different roster than the score was -- and that failure
    would otherwise print a tidy table of numbers that do not describe the
    mapping decision they sit underneath.
    """
    rows = []
    for k in range(4):
        M = roster[k] or set()
        L = labelled[k]
        rows.append((len(M), len(L), len(M - allids), len((M & allids) - L),
                     len(L - M)))
    return rows


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    raw = Path(sys.argv[1])

    beh, detail, bnotes = behaviour_profiles(raw)
    mats, rosters, mnotes = matrix_profiles(raw)
    for n in bnotes + mnotes:
        print(n)

    print("\nbehaviour table, labelled ants per period")
    for c in sorted(beh, key=lambda x: int(x) if x.isdigit() else 0):
        print(f"  colony {c:>3}   " + " ".join(f"{v:>5}" for v in beh[c]))
    for ln in label_shape(detail):
        print(ln)
    print("\nmatrix headers, roster per period")
    for c in sorted(mats):
        print(f"  {c:>9}   " + " ".join(f"{('-' if v is None else v):>5}"
                                        for v in mats[c]))

    incomplete = [c for c, v in mats.items() if any(x is None for x in v)]
    if incomplete:
        print(f"\n  !! no matrices in some period for: {', '.join(incomplete)}. "
              f"Those columns cannot be scored and are excluded below.")

    print("\nmatching each behaviour colony to a matrix column by decline shape")
    print("  score = spread of (matrix - behaviour) across the four periods; 0 is exact\n")
    print(f"  {'colony':>7} {'best':>7} {'score':>6} {'runner-up':>10} {'score':>6} "
          f"{'margin':>7}  offsets of the winner")
    derived, weak, drifting = {}, [], []
    for c in sorted(beh, key=lambda x: int(x) if x.isdigit() else 0):
        scored = []
        for col, prof in mats.items():
            if any(x is None for x in prof):
                continue
            offs = [prof[k] - beh[c][k] for k in range(4)]
            scored.append((spread(offs), col, offs))
        scored.sort()
        if len(scored) < 2:
            print(f"  {c:>7}  too few scoreable columns to compare")
            continue
        (s1, col1, offs1), (s2, col2, _) = scored[0], scored[1]
        margin = s2 - s1
        derived[c] = col1
        # Two independent conditions, kept apart so a failure names itself.
        # A tie means the profiles do not discriminate; a non-constant offset
        # means the shapes do not actually line up even for the winner.
        if margin <= 0:
            weak.append((c, col1, col2, s1, s2))
        if s1 != 0:
            drifting.append((c, col1, offs1))
        print(f"  {c:>7} {col1:>7} {s1:>6} {col2:>10} {s2:>6} {margin:>7}  {offs1}")

    print("\nagainst the containment mapping")
    try:
        containment = mersch_map.resolve(raw, strict=True)["mapping"]
    except Exception as exc:                                  # noqa: BLE001
        print(f"  containment mapping unavailable: {exc}")
        return 1
    tied = {c for c, _, _, _, _ in weak}
    agree = 0
    for c in sorted(derived, key=lambda x: int(x) if x.isdigit() else 0):
        want = containment.get(c) or containment.get(int(c) if c.isdigit() else c)
        ok = (want == derived[c])
        agree += ok and c not in tied
        verdict = ("no margin, does not count" if c in tied
                   else "agree" if ok else "DISAGREE")
        print(f"  colony {c:>3}: containment says {want}, decline shape says "
              f"{derived[c]}   {verdict}")

    print()
    # ORDER MATTERS HERE, and getting it wrong was caught by the `flat` fixture.
    # A colony whose best and runner-up tie has no winner -- the one printed is
    # whichever the sort happened to put first -- so its agreement or
    # disagreement with containment is not evidence in either direction.
    # Reporting DISAGREE for such a colony says "one of the two routes is wrong"
    # when the truth is "this route cannot see anything here", which sends the
    # reader to look for a bug in the mapping that does not exist. So the tied
    # colonies are removed from the disagreement count and reported on their own
    # terms first.
    tied = {c for c, _, _, _, _ in weak}
    real_dis = [c for c in derived
                if c not in tied and containment.get(c) != derived[c]]
    if weak:
        for c, a, b, s1, s2 in weak:
            print(f"  colony {c}: {a} and {b} both score {s1} and {s2} -- the "
                  f"decline profiles do not distinguish them, so this route has "
                  f"no power for this colony and neither its agreement nor its "
                  f"disagreement above counts.")
        print("  A unique best match with no margin is a coin landing on its edge.")
    if real_dis:
        print(f"  {len(real_dis)} colon{'y' if len(real_dis) == 1 else 'ies'} "
              f"({', '.join(real_dis)}) DISAGREE with a positive margin. The "
              f"mapping is not confirmed and nothing colony-level should be quoted "
              f"until this is resolved -- one of the two routes is wrong and this "
              f"file does not say which.")
        return 1
    if weak:
        return 1
    if drifting:
        broken = False
        for c, col, offs in drifting:
            d = detail.get(c, {"labelled": [set()] * 4, "all": set(),
                               "relabel": set()})
            rows = decompose(d["labelled"], d["all"], rosters.get(col, [None] * 4))
            print(f"  colony {c} -> {col}: offsets {offs} are not constant. The "
                  f"shapes agree well enough to win; where the difference comes "
                  f"from, period by period:")
            print(f"      {'period':>6} {'|matrix|':>9} {'|labelled|':>11} "
                  f"{'offset':>7} {'never in':>9} {'NA in':>7} {'labelled,':>10}")
            print(f"      {'':>6} {'':>9} {'':>11} {'':>7} {'behav.csv':>9} "
                  f"{'period':>7} {'not in M':>10}")
            for k, (m, l, never, na, miss) in enumerate(rows):
                bad = (m - l != never + na - miss) or (m - l != offs[k])
                broken = broken or bad
                print(f"      {k + 1:>6} {m:>9} {l:>11} {m - l:>7} {never:>9} "
                      f"{na:>7} {miss:>10}{'  !!' if bad else ''}")
            if broken:
                print(f"      !! the decomposition does not reproduce the offsets "
                      f"the score was computed from. The table above describes "
                      f"some other pair of sets, and nothing in it may be quoted.")
                continue
            moved = [f"{name} {[r[i] for r in rows]}"
                     for name, i in (("never in behavior.csv", 2),
                                     ("`NA` in this period", 3),
                                     ("labelled but off the matrix", 4))
                     if len({r[i] for r in rows}) > 1]
            print("      what moves: " + ("; ".join(moved) if moved else
                  "!! nothing in the decomposition, yet the offset moves"))
            rel = d["relabel"]
            if rel:
                shown = sorted(rel)[:8]
                print(f"      {len(rel)} ant(s) in colony {c} carry a real label "
                      f"after an `NA` ({shown}{' ...' if len(rel) > 8 else ''}), so "
                      f"`NA` is not pure attrition here and per-period task labels "
                      f"cannot be read as a monotone roster.")
            else:
                print(f"      0 ants in colony {c} carry a real label after an "
                      f"`NA`. `NA` is pure attrition, and the drift is not "
                      f"relabelling -- whatever moved above did so for another "
                      f"reason.")
        if broken:
            return 1
        print("  Mapping agrees on both routes; the offset drift is a separate "
              "finding, not a mapping failure. What it is a finding ABOUT is "
              "whichever component moved above -- read that, not this line.")
        return 0
    print(f"  All {agree} colonies agree, every winner is exact, and every margin "
          f"is positive.\n  The mapping is confirmed by a route that does not use "
          f"tag-id membership. It remains\n  an inference -- two inferences that "
          f"agree -- and Mersch's confirmation is still worth\n  having, but "
          f"nothing is blocked on it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
