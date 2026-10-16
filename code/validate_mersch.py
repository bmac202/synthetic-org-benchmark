"""Check our reading of the Mersch / Keller ant deposit before anything runs on it.

Dryad doi:10.5061/dryad.8d8h7, companion to Mersch, Crespi & Keller (2013),
*Science* 340, 1090-1093. CC0.

WHY THIS FILE EXISTS
--------------------
`validate_dornhaus.py` guards one table. `validate_gernat.py` guards a join
across three. This deposit is worse than either, for a reason that has nothing
to do with its size: it is the only one of the three that carries **explicit
per-individual task labels**, which is exactly the variable every division-of-
labour number in the proposal is computed from. If we read that column wrong,
nothing downstream complains -- the numbers come out, they are in range, and
they are about something else.

We already know one such misreading is live, because it was found by running the
real header through the loader's own column matcher instead of trusting it:

      behavior.csv  ->  task = group_period1
      behavior.csv  ->  day  = group_period1

Both roles bind to the same column. `"group"` fuzzy-matches `group_period1`, and
so does `"period"` in the day-candidate list, because `normalize()` strips the
underscore and digits are not stripped, leaving `groupperiod1` -- a string that
contains both. `MIN_FUZZY = 3` is short enough to let `"period"` through. The
consequence is not a crash. The day index becomes a **function of** the task
label: every nurse gets one day, every cleaner another. Task is then perfectly
determined by time, mutual information is maximal by construction, the division-
of-labour score sits at ceiling, kappa is 1.0, and the switch fraction is
structurally 0 -- computed from a file whose four timepoints were collapsed to
one, three of them never read at all.

So the first and most general check here is not about ants:

  0.  **Do two variable roles resolve to the same column?** If they do, that is
      always a bug and never a coincidence. Two roles exist because two distinct
      quantities are needed; one column cannot be both. The right behaviour for
      `pick_column`'s callers is to refuse, not to proceed. This check runs the
      loader's candidate lists over the real header and reports every collision.

The rest are specific to this deposit.

  1.  **Wide, not long.** Task is stored as `group_period1 .. group_period4` --
      four columns, one per assessment period, not one column plus a time index.
      Any matcher that resolves "task" to a single column silently discards
      three quarters of the temporal variation, which is the entire quantity we
      came here for. The file has to be *melted*, and the validator says how many
      periods it found rather than assuming four.

  2.  **Is a group change a change, or an absence?** This check was written
      against a claim of 596 of 805 ants (74%), and that claim is what it caught.
      807 cells across the four period columns are blank, and a blank is a
      distinct "value" to any count of distinct values: an ant present in periods
      1-2 and gone by 3 has two of them and changed nothing. Over the 392 ants
      labelled in **every** period the figure is 183, or 47%. The check reports
      both numbers side by side and names the gap as attrition, because the
      difference between them is the difference between "Mersch is our
      flexibility calibration set" and "the label is effectively static". Only
      the second number may be quoted, and only with its denominator -- 392 of
      805 is not a random half of the colony.

  3.  **Does the flow run N -> C -> F?** Age polyethism is the published result:
      ants move nurse -> cleaner -> forager and rarely back. That gives us a real
      target rather than a plausibility check. If the transition matrix is roughly
      symmetric, either the periods are not in chronological order or the labels
      are not what we think they are. Either way we would find out here rather
      than in a specialization score.

  4.  **Is `tag_id` a key?** Ant57 appears in colonies 2, 3, 5 and 6. Pooling
      across colonies without namespacing merges four animals into one node
      carrying all their edges, and the individuals that come out most central
      are simply the ids reused in the most colonies. Same failure as bee ids
      across trials in the Gernat deposit; here it is known to bite.

  5.  **Are the 246 network files what the README says they are?** The README
      asserts "the network is represented as a square matrix, but only column
      names are given (row names are symmetrical)". That is a promise about a
      file we can test: ids unique, rows == cols, `M == M^T`, zero diagonal. An
      assertion in prose and an assertion in code look the same in a paper and
      are not the same thing at all.

  6.  **Do the matrices and the behaviour table describe the same ants?** Joined
      both ways. An ant in a matrix with no row in `behavior.csv` has no task
      label and vanishes from every DoL number; an ant in `behavior.csv` absent
      from a matrix is an isolate, not a missing row, and belongs in per-capita
      denominators and in the node set a centralization measure is built over.

  7.  **Does the node set shrink across days?** 41 days of a real colony is 41
      days of mortality. If day 41 has fewer ants than day 1, every quantity
      computed per colony-day is computed over a changing denominator, and any
      trend across days is partly a trend in who is left.

  8.  **Which period does `observed_expected_interaction_frequencies.csv` use?**
      It carries a single static `group` column. If that column matches
      `group_period_p` for exactly one p, we have identified which assessment it
      was built from -- and can then say honestly whether its expected-frequency
      baselines apply to the whole record or to one quarter of it.

  9.  **Headers that are not there.** One of the 18 heatmap files
      (`heatmap_col1_foragers.txt`) starts with `0,0,0` where its 17 siblings
      start with `x_coor,y_coor,nb_visits`. Read with an assumed header, its first
      data row is eaten and becomes the column names. A file that is *almost* like
      its siblings is more dangerous than one that is obviously different.

 10.  **Line endings.** `behavior.csv` is CR-only -- classic Mac, no LF anywhere,
      which is why `wc -l` reports 0 lines and why `head` prints the whole file as
      one smear. This was checked rather than assumed: `csv.DictReader`,
      `sniff_delimiter` and `stream_rows` were all run against a hand-built
      CR-only file and all three parse it correctly. The report below states the
      terminator per file so that the next person does not have to re-derive it
      from a confusing `head`.

    python3 validate_mersch.py --raw "/Volumes/<drive>/BeeOrg/data/raw/mersch_keller_2013"

HOW TO USE THE RESULT
---------------------
PASS   the reading is confirmed by the data itself.
CHECK  it is not. Read the note; do not run the loader on that assumption.
?      reported for your eye; no target to compare against.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

from loaders.common import (find_files, is_missing, normalize, pick_column,
                            stream_rows, to_float)

CITATION = ("Mersch, D. P., Crespi, A., & Keller, L. (2013). Tracking individuals "
            "shows spatial fidelity is a key regulator of ant social organization. "
            "Science, 340, 1090-1093. Data: Dryad 10.5061/dryad.8d8h7 (CC0)")

# The candidate lists a loader for this deposit would plausibly carry, copied
# rather than imported -- the same reasoning as KNOWN_DIRECTION_TOKENS in
# validate_gernat.py. Importing the live set would make this check agree with the
# loader by construction, including in the case where both are wrong, which is
# precisely the case that was true when this file was written.
#
# `age` is kept here although the current loader no longer resolves it, because
# it exposes a second collision of the same family: `age_days` normalizes to
# `agedays`, which CONTAINS `day`, so on a header with an age column and no day
# column the time index binds to an age. Nothing raises, and every temporal
# quantity is then computed over how old the ants are. The role is cheap to keep
# and the collision is the point.
LOADER_CANDIDATES = {
    "ant":    ["ant", "ant_id", "id", "tag", "individual", "worker"],
    "colony": ["colony", "colony_id", "col", "replicate"],
    "day":    ["day", "date", "time", "period", "day_idx"],
    "group":  ["group", "task", "caste", "role", "functional_group",
               "community", "cluster", "label"],
    "age":    ["age", "age_days"],
}

TASK_NAMES = {"n": "nurse", "c": "cleaner", "f": "forager", "q": "queen"}

# The published progression. Nurse -> cleaner -> forager, by age; the reverse is
# rare. Used as a direction to test against, not as a filter.
POLYETHISM_ORDER = ["N", "C", "F"]

RESULTS: list[tuple[str, str, str]] = []


def assertion(label: str, ok: bool, detail: str = "", ok_detail: str = "") -> None:
    """Record a check. `detail` explains the failure; `ok_detail` the success."""
    RESULTS.append(("PASS", label, ok_detail) if ok else ("CHECK", label, detail))


def note(label: str, detail: str = "") -> None:
    RESULTS.append(("?", label, detail))


# --------------------------------------------------------------- file finding
def is_apple_double(p: Path) -> bool:
    """True for the metadata shadows a macOS zip leaves behind.

    Unzipping this deposit produces a `__MACOSX/` tree containing `._name.csv`
    for every real `name.csv`. They are AppleDouble resource forks: binary, a few
    hundred bytes, and named exactly like the file they shadow. `find_files` with
    a `*.csv` glob returns them, `stream_rows` opens them with errors="replace"
    and yields garbage rows rather than raising, and a loader that picks "the
    largest CSV" or "the first CSV" can end up reading one. `cut` on them reports
    `Illegal byte sequence`, which is how they were noticed.
    """
    return p.name.startswith("._") or "__MACOSX" in p.parts


def clean_files(root: Path, patterns: list[str]) -> list[Path]:
    return [p for p in find_files(root, patterns) if not is_apple_double(p)]


def table(root: Path, *names: str) -> Path | None:
    """Find one of the deposit's tables by name, case-insensitively."""
    wanted = {normalize(n) for n in names}
    for f in clean_files(root, ["*.csv", "*.tsv", "*.txt"]):
        if normalize(f.stem) in wanted:
            return f
    return None


def table_prefix(root: Path, prefix: str) -> Path | None:
    """Find a table whose normalized stem STARTS with `prefix`.

    `observed_expected_interaction_frequencies.csv` is long enough that nobody
    types it twice the same way, and the published name has varied between the
    README and the file itself.
    """
    npfx = normalize(prefix)
    for f in clean_files(root, ["*.csv", "*.tsv"]):
        if normalize(f.stem).startswith(npfx):
            return f
    return None


def line_terminator(path: Path) -> str:
    """Report which line ending a file actually uses, from its bytes."""
    chunk = path.open("rb").read(65536)
    crlf = chunk.count(b"\r\n")
    cr = chunk.count(b"\r") - crlf
    lf = chunk.count(b"\n") - crlf
    if cr and not lf and not crlf:
        return "CR (classic Mac)"
    if crlf and not cr and not lf:
        return "CRLF"
    if lf and not cr and not crlf:
        return "LF"
    return f"MIXED (cr={cr} lf={lf} crlf={crlf})"


def read_lines(path: Path) -> list[str]:
    """All non-empty lines, whatever the terminator.

    `splitlines()` splits on CR, LF and CRLF alike, which is the whole reason it
    is used here instead of iterating the file object: `behavior.csv` and the
    network matrices do not agree on a terminator, and the difference must not
    reach the caller.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    return [ln for ln in text.splitlines() if ln.strip()]


# ------------------------------------------------------- check 0: double-bind
def check_column_binding(name: str, header: list[str]) -> dict[str, str]:
    """Resolve every loader role against a real header and refuse on collision."""
    bound: dict[str, str] = {}
    for role, cands in LOADER_CANDIDATES.items():
        try:
            col = pick_column(header, cands, role, required=False)
        except KeyError:
            col = None
        if col is not None:
            bound[role] = col

    by_col: dict[str, list[str]] = defaultdict(list)
    for role, col in bound.items():
        by_col[col].append(role)
    clashes = {c: rs for c, rs in by_col.items() if len(rs) > 1}

    print(f"\nCOLUMN BINDING  ({name})")
    print("-" * 92)
    for role in LOADER_CANDIDATES:
        col = bound.get(role)
        flag = "  <-- COLLISION" if col and len(by_col[col]) > 1 else ""
        print(f"  {role:8} -> {col if col else '-- not found --':<40}{flag}")

    assertion(
        f"no two variable roles bind to the same column in {name}",
        not clashes,
        "; ".join(f"{' and '.join(sorted(rs))} both resolve to {c!r}"
                  for c, rs in sorted(clashes.items()))
        + ". Two roles exist because two distinct quantities are needed, so one "
          "column cannot be both -- this is always a bug and never a coincidence. "
          "Where the colliding roles are the task label and the time index the "
          "damage is specific and invisible: task becomes a function of time, "
          "mutual information is maximal by construction, the division-of-labour "
          "score sits at ceiling and the switch fraction is structurally zero. "
          "pick_column's callers must refuse rather than proceed",
        f"each of the {len(bound)} resolved roles took a different column, so no "
        f"quantity is standing in for another")
    return bound


# ------------------------------------------------------------ period handling
PERIOD_RE = re.compile(r"^group[_ ]?period[_ ]?(\d+)$", re.I)


def period_columns(header: list[str]) -> list[tuple[int, str]]:
    """Every `group_periodN` column, in N order."""
    out = []
    for h in header:
        m = PERIOD_RE.match(str(h).strip())
        if m:
            out.append((int(m.group(1)), h))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="data/raw/mersch_keller_2013")
    ap.add_argument("--max-matrices", type=int, default=None,
                    help="cap the number of network matrices parsed (quick look only)")
    ap.add_argument("--colony-map", default=None,
                    help="matrix colony -> behavior.csv colony, e.g. "
                         "'1=4,2=18,3=21,4=29,5=58,6=78'. Only supply this once "
                         "the correspondence is CONFIRMED; it decides which ants "
                         "are which")
    a = ap.parse_args()
    root = Path(a.raw).expanduser()

    colony_map = {}
    if a.colony_map:
        for pair in a.colony_map.split(","):
            if "=" not in pair:
                raise SystemExit(f"--colony-map entry {pair!r} is not net=behav")
            k, v = pair.split("=", 1)
            colony_map[k.strip()] = v.strip()

    print(f"source : {CITATION}\n")

    behav = table(root, "behavior", "behaviour")
    obsexp = table_prefix(root, "observed_expected")
    spread = table(root, "information_spread")
    nets = sorted(p for p in clean_files(root, ["network_col*_day*.txt"]))
    heats = sorted(p for p in clean_files(root, ["heatmap_*.txt"]))
    shadows = [p for p in find_files(root, ["*.csv", "*.txt"]) if is_apple_double(p)]

    for label, p in (("behavior", behav), ("observed/expected", obsexp),
                     ("information_spread", spread)):
        print(f"  {label:20} {p.relative_to(root) if p else '-- NOT FOUND --'}")
    print(f"  {'network matrices':20} {len(nets)} files")
    print(f"  {'heatmaps':20} {len(heats)} files")

    if shadows:
        note("macOS AppleDouble shadows excluded",
             f"{len(shadows)} files under __MACOSX/ or named ._* were skipped. They "
             f"are binary resource forks named exactly like the real files, so a "
             f"loader that picks 'the first CSV' or 'the largest CSV' can read one "
             f"and get garbage rather than an error -- stream_rows opens with "
             f"errors='replace' and will not raise. Any find_files call in a Mersch "
             f"loader must filter them")

    if behav is None:
        raise SystemExit(f"\nno behavior table under {root}")

    # -------------------------------------------------------- line terminators
    print("\nLINE TERMINATORS")
    print("-" * 92)
    sample = [p for p in (behav, obsexp, spread) if p] + nets[:1] + heats[:1]
    for p in sample:
        print(f"  {p.name:52} {line_terminator(p)}")
    print("  (all three readers -- csv.DictReader, sniff_delimiter, stream_rows --")
    print("   were run against a hand-built CR-only file and parse it correctly.")
    print("   `wc -l` and `head` do not; that is a shell problem, not a data problem.)")

    # ------------------------------------------------------------ behavior.csv
    rows = list(stream_rows(behav))
    header = list(rows[0].keys()) if rows else []
    print(f"\nbehavior.csv : {len(rows):,} rows x {len(header)} columns")

    bound = check_column_binding("behavior.csv", header)

    periods = period_columns(header)
    assertion(
        "the task label is stored long, one column plus a time index",
        len(periods) <= 1,
        f"it is stored WIDE: {len(periods)} columns "
        f"({', '.join(c for _, c in periods)}), one per assessment period. A "
        f"matcher that resolves 'task' to a single column reads period "
        f"{periods[0][0] if periods else '?'} and discards the other "
        f"{len(periods) - 1} -- which is to say it discards the entire temporal "
        f"variation in the variable this deposit was chosen for. The file has to "
        f"be melted into (ant, period, group) before anything reads it",
        "one task column, so no melt is needed")

    if not periods:
        print("\nno group_period* columns found; nothing further to check on labels")
    else:
        run_label_checks(rows, header, periods)

    # ----------------------------------------------------- tag_id across colonies
    ccol = pick_column(header, ["colony", "colony_id", "col"], "colony", required=False)
    acol = pick_column(header, ["tag_id", "tagid", "ant_id", "ant", "tag"], "ant",
                       required=False)
    if ccol and acol:
        check_id_reuse(rows, ccol, acol)

    # ------------------------------------------------------------- the matrices
    net_nodes = check_matrices(nets, a.max_matrices)

    if ccol and acol and net_nodes:
        check_matrix_behavior_join(rows, ccol, acol, net_nodes, colony_map)
        check_attrition(net_nodes)

    # ------------------------------------------------------- observed/expected
    if obsexp is not None and periods and ccol and acol:
        check_obsexp_period(obsexp, rows, ccol, acol, periods)

    # ---------------------------------------------------------------- heatmaps
    if heats:
        check_heatmaps(heats)

    # ----------------------------------------------------------------- verdict
    print("\nVERDICT")
    print("=" * 92)
    order = {"CHECK": 0, "?": 1, "PASS": 2}
    for status, label, detail in sorted(RESULTS, key=lambda r: order.get(r[0], 9)):
        print(f"  [{status:5}] {label}")
        if detail:
            print(f"           {detail}")

    n_check = sum(1 for s, _, _ in RESULTS if s == "CHECK")
    print(f"\n{n_check} disagreement(s).")
    if n_check:
        print("Each CHECK above is a way this deposit can produce a complete run with\n"
              "plausible numbers that are about the wrong thing. Fix the loader, or\n"
              "scope the claim in writing, before anything from here is used.")
    return 0


# --------------------------------------------------------------- label checks
def run_label_checks(rows: list[dict], header: list[str],
                     periods: list[tuple[int, str]]) -> None:
    """Levels, missingness, change fraction, and the direction of the flow."""
    cols = [c for _, c in periods]

    # ---- levels and missingness, per period
    print(f"\nTASK LABELS BY PERIOD  ({len(periods)} periods)")
    print("-" * 92)
    print(f"  {'period':10} {'n':>6}  {'missing':>8}  levels")
    all_levels: Counter = Counter()
    missing_by_period: dict[str, int] = {}
    for n, c in periods:
        vals = [str(r.get(c, "")).strip() for r in rows]
        miss = sum(1 for v in vals if is_missing(v))
        present = Counter(v for v in vals if not is_missing(v))
        all_levels.update(present)
        missing_by_period[c] = miss
        lv = ", ".join(f"{k}:{n_}" for k, n_ in sorted(present.items()))
        print(f"  {c:10} {len(vals):>6}  {miss:>8}  {lv}")

    total_missing = sum(missing_by_period.values())
    unexpected = sorted(k for k in all_levels if k.lower() not in TASK_NAMES)
    assertion(
        "every task label is one of the four documented castes",
        not unexpected,
        f"levels outside {sorted(TASK_NAMES)}: {unexpected[:8]}. Each of those is a "
        f"category the loader will happily carry into a task distribution, and a "
        f"stray level with a handful of members moves a specialization score "
        f"without ever looking like an error",
        # .get, not [], for the same reason as shape_detail above: this string is
        # built even when the check fails, and it fails precisely when a level has
        # no entry in TASK_NAMES.
        f"levels are exactly {sorted(all_levels)} = "
        f"{', '.join(TASK_NAMES.get(k.lower(), k) for k in sorted(all_levels))}")

    # ---- the number that gates everything: is a change a change?
    complete, partial = [], []
    for r in rows:
        seq = [str(r.get(c, "")).strip() for c in cols]
        (partial if any(is_missing(v) for v in seq) else complete).append(seq)

    naive_changed = sum(1 for r in rows
                        if len({str(r.get(c, "")).strip() for c in cols}) > 1)
    comp_changed = sum(1 for seq in complete if len(set(seq)) > 1)

    print(f"\n  ants with a label in all {len(cols)} periods : {len(complete):>6,}")
    print(f"  ants missing at least one label        : {len(partial):>6,}")
    print(f"  naive distinct-value count changed     : {naive_changed:>6,} "
          f"({100 * naive_changed / max(1, len(rows)):.1f}% of all rows)")
    print(f"  changed among COMPLETE ants only       : {comp_changed:>6,} "
          f"({100 * comp_changed / max(1, len(complete)):.1f}% of complete)")

    if total_missing == 0:
        note("the change fraction survives the missingness test",
             f"there are no missing labels anywhere in the {len(cols)} period "
             f"columns, so 'more than one distinct value' cannot be picking up an "
             f"ant that was simply absent for a period. {comp_changed:,} of "
             f"{len(rows):,} ants ({100 * comp_changed / max(1, len(rows)):.1f}%) "
             f"change group, and the number means what it says: this deposit is a "
             f"calibration set for task re-allocation, not a static labelling")
    else:
        assertion(
            "the change fraction is not an artefact of missing labels",
            abs(naive_changed - comp_changed) <= 0.02 * max(1, len(rows)),
            f"{total_missing:,} cells across the period columns are missing, and "
            f"the change count moves from {naive_changed:,} (counting the missing "
            f"token as a level) to {comp_changed:,} over the {len(complete):,} ants "
            f"labelled in every period. The gap is attrition being read as "
            f"flexibility: an ant present in periods 1-2 and gone by 3 has two "
            f"distinct 'values' and changed nothing. Only the second number may be "
            f"quoted, and it must be quoted with its denominator",
            f"{total_missing:,} cells are missing but the two counts agree to "
            f"within 2% ({naive_changed:,} vs {comp_changed:,}), so the change "
            f"fraction is about task and not about presence")

    # ---- direction of flow
    trans: Counter = Counter()
    for seq in complete:
        for x, y in zip(seq, seq[1:]):
            trans[(x.upper(), y.upper())] += 1

    levels = sorted({k for pair in trans for k in pair})
    if levels:
        print("\n  TRANSITIONS between consecutive periods (complete ants only)")
        print("  " + "-" * 88)
        print("      from \\ to " + "".join(f"{l:>10}" for l in levels))
        for f in levels:
            line = "".join(f"{trans.get((f, t), 0):>10,}" for t in levels)
            print(f"      {f:>9} {line}")

    rank = {c: i for i, c in enumerate(POLYETHISM_ORDER)}
    fwd = sum(n for (f, t), n in trans.items()
              if f in rank and t in rank and rank[t] > rank[f])
    bwd = sum(n for (f, t), n in trans.items()
              if f in rank and t in rank and rank[t] < rank[f])
    if fwd + bwd:
        assertion(
            "task changes run forward along nurse -> cleaner -> forager",
            fwd > 2 * bwd,
            f"{fwd:,} forward against {bwd:,} backward transitions among "
            f"{'/'.join(POLYETHISM_ORDER)}. Age polyethism is the published result "
            f"for this colony, so a roughly symmetric flow means one of our "
            f"premises is wrong -- most likely that group_period1..N are in "
            f"chronological order, or that N/C/F mean what we take them to mean. "
            f"Both are assumptions about the file, not findings from it, and "
            f"neither can be carried into a re-allocation claim until this "
            f"resolves",
            f"{fwd:,} forward against {bwd:,} backward "
            f"({fwd / max(1, fwd + bwd):.0%} forward). The flow reproduces age "
            f"polyethism, which independently confirms that the period columns are "
            f"in chronological order and that N/C/F carry their documented "
            f"meanings -- neither of which we had evidence for before")

    # ---- queens
    qcount = sum(1 for r in rows
                 if any(str(r.get(c, "")).strip().upper() == "Q" for c in cols))
    if qcount:
        q_stable = sum(1 for r in rows
                       if all(str(r.get(c, "")).strip().upper() == "Q" for c in cols))
        note("queens are structurally special nodes",
             f"{qcount} ant(s) carry the Q label in at least one period, "
             f"{q_stable} in every period. A queen is not a worker with a different "
             f"task: she is a different kind of node, and leaving her in a "
             f"centralization score guarantees a hub that says nothing about "
             f"emergent structure. Report her separately or exclude her, but say "
             f"which")


# ----------------------------------------------------------------- id reuse
def check_id_reuse(rows: list[dict], ccol: str, acol: str) -> None:
    """Is tag_id a key on its own, or only (colony, tag_id)?"""
    # A Counter over memberships, not a pairwise set intersection. With 6 colonies
    # the pairwise version is 15 comparisons and answers "do these two overlap";
    # the Counter answers "in how many colonies does this id occur", which is the
    # question, and costs one pass.
    colonies_per_id: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        colonies_per_id[str(r[acol]).strip()].add(str(r[ccol]).strip())
    reused = {i: c for i, c in colonies_per_id.items() if len(c) > 1}
    worst = sorted(reused.items(), key=lambda kv: -len(kv[1]))[:4]

    assertion(
        f"{acol} identifies an ant on its own",
        not reused,
        f"{len(reused):,} of {len(colonies_per_id):,} ids occur in more than one "
        f"colony (e.g. " + "; ".join(f"{i} in {sorted(c)}" for i, c in worst) +
        f"). Pooling without namespacing merges those animals into one node "
        f"carrying all their edges, and the individuals that come out most central "
        f"are then simply the ids reused in the most colonies. The node key must be "
        f"{ccol}:{acol}, which costs nothing when ids ARE unique and prevents a "
        f"silent merge when they are not",
        f"all {len(colonies_per_id):,} ids occur in exactly one colony, so pooling "
        f"is safe -- but namespace anyway, because this is a property of the file "
        f"and not of the format")


# ----------------------------------------------------------------- matrices
NET_RE = re.compile(r"network_col(\d+)_day(\d+)", re.I)


def check_matrices(nets: list[Path], cap: int | None) -> dict[tuple[str, int], list[str]]:
    """Square, symmetric, zero-diagonal, unique ids -- the README's claim, tested."""
    if not nets:
        return {}

    parsed = nets if cap is None else nets[:cap]
    if cap is not None and len(nets) > cap:
        print(f"\n  NOTE: parsing {cap} of {len(nets)} matrices (--max-matrices). "
              f"The remaining {len(nets) - cap} were NOT checked.")

    nodes: dict[tuple[str, int], list[str]] = {}
    bad_shape, bad_sym, bad_diag, dup_ids, off_by_one = [], [], [], [], []
    max_asym = 0.0
    grid: dict[str, set[int]] = defaultdict(set)

    print(f"\nNETWORK MATRICES  ({len(parsed)} parsed)")
    print("-" * 92)
    for p in parsed:
        m = NET_RE.search(p.name)
        if not m:
            continue
        col, day = m.group(1), int(m.group(2))
        grid[col].add(day)

        lines = read_lines(p)
        if not lines:
            bad_shape.append((p.name, 0, 0))
            continue
        ids = [x.strip().strip('"') for x in lines[0].split(",")]
        body = [ln.split(",") for ln in lines[1:]]

        if len(ids) != len(set(ids)):
            dup_ids.append(p.name)
        if len(body) == len(ids) - 1:
            # The signature of a header row that is really a data row, or of a
            # data row eaten as a header. Called out separately from a general
            # shape failure because the fix is different.
            off_by_one.append(p.name)
        if len(body) != len(ids) or any(len(r) != len(ids) for r in body):
            bad_shape.append((p.name, len(ids), len(body)))
            continue

        M = [[to_float(x) for x in r] for r in body]
        n = len(ids)
        asym = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                x, y = M[i][j], M[j][i]
                if x is None or y is None:
                    continue
                asym = max(asym, abs(x - y))
        if asym > 1e-9:
            bad_sym.append((p.name, asym))
        max_asym = max(max_asym, asym)
        if any(M[i][i] not in (0, 0.0, None) for i in range(n)):
            bad_diag.append(p.name)
        nodes[(col, day)] = ids

    sizes = {c: (len(grid[c]), min(grid[c]), max(grid[c])) for c in sorted(grid)}
    for c, (n_days, lo, hi) in sizes.items():
        gaps = sorted(set(range(lo, hi + 1)) - grid[c])
        print(f"  colony {c:3}  {n_days:>3} days  {lo}..{hi}"
              + (f"   MISSING {gaps[:8]}" if gaps else "   contiguous"))

    n_expected = sum(len(v) for v in grid.values())
    assertion(
        "the matrix grid is complete: one file per colony per day",
        all(len(set(range(min(d), max(d) + 1)) - d) == 0 for d in grid.values()),
        "at least one colony is missing days inside its own range (listed above). "
        "A gap is not a colony that stopped: it is a day whose network is absent, "
        "and any across-day trend computed by position rather than by day number "
        "will slide past it",
        f"{n_expected} files = {len(grid)} colonies x contiguous day runs, with no "
        f"interior gaps")

    # Both details are built before the call rather than inline, because an
    # f-string argument is evaluated whether or not the branch that uses it is
    # taken: `max(a for _, a in bad_sym)` raises on the empty sequence, i.e. the
    # failure message crashes exactly when there is no failure. A check that only
    # runs when it fails is not a check.
    shape_detail = (
        f"{len(bad_shape)} file(s) are not: " +
        "; ".join(f"{n} ({c} ids, {r} rows)" for n, c, r in bad_shape[:4]) +
        (f" -- of which {len(off_by_one)} are short by exactly one row, the "
         f"signature of a data row eaten as a header or a header that is really "
         f"data" if off_by_one else "")) if bad_shape else ""
    assertion(
        "every matrix is square with the ids its header declares",
        not bad_shape, shape_detail,
        f"all {len(nodes)} matrices have as many rows as header ids, and every row "
        f"has that many fields")

    sym_detail = (
        f"{len(bad_sym)} matrix(es) are not symmetric; the largest off-diagonal "
        f"disagreement is {max(a for _, a in bad_sym):.6g} in "
        f"{max(bad_sym, key=lambda t: t[1])[0]}. The README says row names may be "
        f"taken from the columns because the matrix is symmetric. If it is not, "
        f"then row i is not ant i, every edge is attached to the wrong pair, and "
        f"the network is not the colony's") if bad_sym else ""
    assertion(
        "the README's 'row names are symmetrical' holds as M == M^T",
        not bad_sym, sym_detail,
        f"every one of the {len(nodes)} matrices satisfies M == M^T exactly "
        f"(largest deviation {max_asym:.3g}), so reading row names off the column "
        f"header is safe and the graph is honestly undirected")

    if bad_diag:
        note("non-zero diagonal", f"{len(bad_diag)} matrix(es) carry a self-loop on "
             f"at least one ant, e.g. {bad_diag[:3]}. Self-interaction is not a "
             f"thing an ant does; it inflates degree by a constant that differs "
             f"per individual")
    if dup_ids:
        note("duplicate ids in a matrix header",
             f"{len(dup_ids)} file(s), e.g. {dup_ids[:3]}. Two columns for one ant "
             f"means the ant's edges are split across them and its degree is wrong "
             f"in both")
    return nodes


def check_attrition(nodes: dict[tuple[str, int], list[str]]) -> None:
    """Does the node set shrink across days, and is it nested?"""
    by_colony: dict[str, dict[int, set[str]]] = defaultdict(dict)
    for (col, day), ids in nodes.items():
        by_colony[col][day] = set(ids)

    print("\nNODE SET ACROSS DAYS")
    print("-" * 92)
    print(f"  {'colony':8} {'day1':>6} {'last':>6} {'lost':>6} {'gained':>7}  nested?")
    any_gain, shrink = 0, 0
    for col in sorted(by_colony):
        days = sorted(by_colony[col])
        first, last = by_colony[col][days[0]], by_colony[col][days[-1]]
        lost, gained = len(first - last), len(last - first)
        nested = all(by_colony[col][b] <= by_colony[col][a]
                     for a, b in zip(days, days[1:]))
        any_gain += gained
        shrink += 1 if len(last) < len(first) else 0
        print(f"  {col:8} {len(first):>6} {len(last):>6} {lost:>6} {gained:>7}"
              f"  {'yes' if nested else 'NO'}")

    if shrink:
        note("the colony shrinks across the record",
             f"{shrink} of {len(by_colony)} colonies end with fewer ants than they "
             f"start with. Anything computed per colony-day has a moving "
             f"denominator, so a trend across days is partly a trend in who is "
             f"left. Per-capita quantities need the day's own node count, not the "
             f"colony's maximum, and a survival-style analysis is the honest way "
             f"to state a change over the 41 days")
    if any_gain:
        note("ants appear after day 1",
             f"{any_gain} ant-days involve an id present at the end that was absent "
             f"at the start. Either new ants were tagged mid-record or an ant can "
             f"drop out of a day's matrix and return, and those license different "
             f"readings of an absence. Absence is not death here unless it is "
             f"terminal")


def check_matrix_behavior_join(rows: list[dict], ccol: str, acol: str,
                               nodes: dict[tuple[str, int], list[str]],
                               colony_map: dict[str, str] | None = None) -> None:
    """Join the network node sets against the behaviour table, both directions."""
    behav_ids: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        behav_ids[str(r[ccol]).strip()].add(str(r[acol]).strip())

    net_ids: dict[str, set[str]] = defaultdict(set)
    for (col, _day), ids in nodes.items():
        # An unmapped label is left as it is rather than dropped: a mapping that
        # covers only some colonies must still fail the vocabulary check below,
        # not quietly shrink the comparison to the ones it happens to cover.
        net_ids[(colony_map or {}).get(col, col)].update(ids)
    if colony_map:
        print(f"\n  colony map applied: {colony_map}")
        print("   (supplied on the command line -- this is an assertion about which")
        print("    colony is which, and every id join below depends on it)")

    # Matrix headers are written "Ant57"; behavior.csv carries "57". Compare on
    # the digits so that a formatting difference does not masquerade as a missing
    # ant -- and say so, because silently normalizing a key is itself a way to
    # join two things that should not have joined.
    def key(x: str) -> str:
        d = re.sub(r"[^0-9]", "", x)
        return d if d else normalize(x)

    behav_k = {c: {key(i) for i in v} for c, v in behav_ids.items()}
    net_k = {c: {key(i) for i in v} for c, v in net_ids.items()}
    b_labels, n_labels = set(behav_k), set(net_k)
    shared_colonies = sorted(b_labels & n_labels)

    # The two files have to label colonies from the SAME VOCABULARY before any id
    # can be joined, and "they overlap somewhere" is not that.
    #
    # This check used to fire only on an EMPTY intersection. On the real deposit
    # the intersection is not empty -- it is exactly one label, by coincidence.
    # behavior.csv names its colonies 4, 18, 21, 29, 58 and 78; the matrix
    # filenames are network_col1..col6. The only value in both sets is "4", which
    # on one side means the fourth matrix and on the other a colony that happens
    # to be CALLED 4. Those are almost certainly not the same colony, and the
    # join went on to report "57 of 102 matrix ids have no task label" about a
    # pairing nobody chose -- one colony's graph against another colony's labels.
    #
    # Same family as the double-binding bug this file was written for: a check
    # that can only fire on total mismatch waves the partial coincidence through,
    # and what comes out the other side reads like a finding.
    #
    # So refuse unless the vocabularies are equal, and print both. A mapping
    # probably does exist -- six labels on each side, and sorting the behaviour
    # labels numerically lines them up with col1..col6 -- but inferring it from
    # sort order is a guess, and a guess about which colony is which is a guess
    # about which ants are which.
    assertion(
        "the matrices and behavior.csv label colonies from the same vocabulary",
        b_labels == n_labels,
        f"they do not. Matrices use {sorted(n_labels)}; behavior.csv uses "
        f"{sorted(b_labels)}"
        + (f". The only label in both is {shared_colonies}, an overlap of "
           f"{len(shared_colonies)} of {len(n_labels)} -- a coincidence of "
           f"numbering, not a correspondence"
           if shared_colonies else ". They share nothing at all") +
        ". No id can be joined across the two until the mapping is stated "
        "explicitly. Sorting the behaviour labels numerically does line them up "
        "with col1..col6, but that is an inference from sort order, and a guess "
        "about which colony is which is a guess about which ants are which. "
        "Confirm it against the deposit's README or the authors and pass "
        f"--colony-map '{sorted(n_labels)[0] if n_labels else '1'}="
        f"{sorted(b_labels, key=lambda s: (len(s), s))[0] if b_labels else '4'},...'",
        f"both files use {sorted(b_labels)}, so a colony label means the same "
        f"thing on each side and the id joins below are between the ants of one "
        f"colony and the labels of that same colony"
        + (" (after the --colony-map you supplied)" if colony_map else ""))

    if b_labels != n_labels:
        note("the unlabelled-ant and isolate counts were NOT computed",
             "both need the colony mapping above. They are the two numbers that "
             "say whether the graph and the task labels describe the same animals "
             "-- worth getting rather than guessing")
        return

    unlabelled = sum(len(net_k[c] - behav_k[c]) for c in shared_colonies)
    isolates = sum(len(behav_k[c] - net_k[c]) for c in shared_colonies)
    n_net = sum(len(net_k[c]) for c in shared_colonies)
    n_behav = sum(len(behav_k[c]) for c in shared_colonies)

    assertion(
        "every ant in a network matrix has a task label in behavior.csv",
        unlabelled == 0,
        f"{unlabelled:,} of {n_net:,} matrix ids have no row in behavior.csv. Those "
        f"ants are in the graph and absent from every division-of-labour number, so "
        f"the structure and the labels are computed over different populations -- "
        f"and the difference is not random if the unlabelled ones are, say, the "
        f"ones that died before scoring",
        f"all {n_net:,} matrix ids across {len(shared_colonies)} colonies join onto "
        f"a behavior.csv row, so structure and task labels describe the same ants")

    if isolates:
        note("ants in behavior.csv that never appear in a matrix",
             f"{isolates:,} of {n_behav:,}. These are isolates, not missing rows. "
             f"They belong in the denominator of anything per-capita and in the "
             f"node set of any centralization measure; building the graph from the "
             f"matrices alone drops them and makes the colony look better connected "
             f"than it is")


# ------------------------------------------------------- observed / expected
def check_obsexp_period(obsexp: Path, rows: list[dict], ccol: str, acol: str,
                        periods: list[tuple[int, str]]) -> None:
    """Which of the four assessments is the static `group` column?"""
    orows = list(stream_rows(obsexp))
    if not orows:
        return
    oheader = list(orows[0].keys())
    oc = pick_column(oheader, ["colony", "colony_id"], "colony", required=False)
    oa = pick_column(oheader, ["tag_id", "tagid", "tag_ID", "ant"], "ant", required=False)
    og = pick_column(oheader, ["group"], "group", required=False)
    print(f"\nobserved/expected : {len(orows):,} rows x {len(oheader)} columns "
          f"(colony={oc} ant={oa} group={og})")
    if not (oc and oa and og):
        note("could not resolve colony/ant/group in the observed-expected table",
             f"header is {oheader}")
        return

    static = {(str(r[oc]).strip(), str(r[oa]).strip()): str(r[og]).strip()
              for r in orows}
    matched = []
    print("  agreement with each period column")
    for n, c in periods:
        hit = tot = 0
        for r in rows:
            k = (str(r[ccol]).strip(), str(r[acol]).strip())
            if k not in static:
                continue
            tot += 1
            if str(r.get(c, "")).strip().upper() == static[k].upper():
                hit += 1
        share = hit / max(1, tot)
        matched.append((share, n, c, hit, tot))
        print(f"    {c:16} {hit:>6,} / {tot:<6,}  {share:6.1%}")

    best = max(matched) if matched else None
    if best and best[0] >= 0.999:
        note("the observed/expected baselines are built on one assessment",
             f"its `group` column reproduces {best[2]} exactly ({best[3]:,} of "
             f"{best[4]:,}), so the expected-frequency baselines in that file "
             f"describe period {best[1]} and not the record as a whole. Comparing "
             f"them against interaction counts pooled over all "
             f"{len(periods)} periods asks whether ants interact as period "
             f"{best[1]}'s assignment predicts, over a window in which "
             f"three quarters of the assignment changed")
    elif best:
        note("the observed/expected `group` matches no single period exactly",
             f"best agreement is {best[2]} at {best[0]:.1%}. So it is a separate "
             f"assignment -- a pooled or modal label, or a fifth assessment -- and "
             f"using it as 'the' task label mixes it with the period columns. Which "
             f"one a number came from has to be stated")


# ---------------------------------------------------------------- heatmaps
def check_heatmaps(heats: list[Path]) -> None:
    """One of these files does not have the header its 17 siblings have."""
    headed, bare = [], []
    for p in heats:
        first = read_lines(p)[:1]
        if not first:
            continue
        toks = [t.strip() for t in first[0].split(",")]
        (bare if all(to_float(t) is not None for t in toks) else headed).append(p.name)

    assertion(
        "every heatmap file carries the same header",
        not bare,
        f"{len(bare)} of {len(heats)} start with a numeric row and no column "
        f"names: {bare[:4]}. Read with an assumed header, the first data row is "
        f"consumed and becomes the column names -- so that file loses one "
        f"observation and gains three columns named after coordinates. A file that "
        f"is ALMOST like its siblings is more dangerous than one that is obviously "
        f"different, because the loader completes",
        f"all {len(heats)} begin with column names")
    if headed:
        note("heatmap header", f"{len(headed)} file(s) begin with column names; "
             f"the reader must sniff per file rather than assume")


if __name__ == "__main__":
    raise SystemExit(main())
