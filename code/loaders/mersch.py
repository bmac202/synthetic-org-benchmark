"""Mersch, Crespi & Keller (2013) ants -> canonical events.

Dryad 10.5061/dryad.8d8h7, CC0. Six *Camponotus fellah* colonies, 41 days of
tracking, 805 tagged workers described in `behavior.csv`.

This is the only public deposit in our set with EXPLICIT per-individual task
labels (nurse / cleaner / forager / queen), which makes it the calibration set:
the division-of-labour instrument can be scored against labels a biologist
assigned rather than against a proxy we invented.

WHAT THIS FILE USED TO SAY, AND WHY IT WAS WRONG
------------------------------------------------
The previous version of this docstring said the labels were re-assessed "only
three times across the 41 days", that the temporal resolution of task was
therefore 10 days, and -- on that basis -- that "flexibility has to come from
Charbonneau & Dornhaus, where there is an actual manipulation". None of that
survived contact with the file.

`behavior.csv` carries `group_period1 .. group_period4`: **four** assessments,
not three, stored WIDE -- one column per period rather than one column plus a
time index.

So the conclusion inverts. Mersch is not a static labelling to be used for
specialization only; it is a re-allocation record, and the proposal's claims
about task re-allocation have a dataset behind them here as well as in
Charbonneau & Dornhaus. What Mersch does not have is a *manipulation* -- the
re-allocation is whatever the colony did, not a response to something done to
it. That is the caveat worth carrying, and it is a different caveat entirely.

AND WHAT THIS FILE SAID NEXT, WHICH WAS ALSO WRONG
--------------------------------------------------
The paragraph above used to continue: "**596 of the 805 ants (74%) hold more
than one distinct label across those four periods**, with no missing cells
anywhere in them". The first number came from a one-line count over the four
columns; the claim about missing cells came from nowhere -- it was assumed,
because the count looked clean.

807 cells across those columns are blank. A blank is a distinct "value" to any
count of distinct values, so an ant present in periods 1-2 and gone by 3 has two
of them and changed nothing: that is attrition being read as flexibility, which
is precisely the error `validate_mersch.py` exists to catch, committed in the
number the validator was written to check. Restricted to the 392 ants labelled
in **every** period, **183 change group -- 47%, not 74%**.

Two things follow for anything quoting this. The figure is 183/392 and the
denominator travels with it, because those 392 are the ants scoreable across the
whole record and are not a random half of the colony -- the same survivorship
shape as Dornhaus's 669. And the flexibility conclusion survives: 47% is still a
colony that re-allocates, so the paragraph above stands, at half the strength it
was first written with.

The counting in `load()` was right all along -- `complete` has always required a
label in every period -- which is the only reason the fix is confined to prose.

THE BUG THIS REWRITE FIXES
--------------------------
The wide layout is not a formatting inconvenience. Run the real header through
the old candidate lists and both of these come back:

    task -> group_period1        day -> group_period1

`"group"` fuzzy-matches `groupperiod1`, and so does `"period"` in the day list.
Neither `pick_column` call can see the other, so nothing raises: the loader
completes, having read one period of four and made the day index a function of
the task label. Task is then perfectly determined by time, mutual information is
maximal by construction, and the division-of-labour score comes out at ceiling
from three quarters of the data never being read at all.

Two fixes, both here. The roles are resolved together through
`common.pick_columns`, which refuses on a collision rather than proceeding; and
the wide period columns are *melted* into one observation per (ant, period) so
that the four assessments become four timesteps instead of three discarded
columns.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from . import mersch_map
from .common import (EventBuilder, find_files, pick_column, pick_columns,
                     report, stream_rows, write_events)

# Roles resolved TOGETHER, so a collision is caught. `day` is deliberately kept
# in the long-format spec even though the wide path does not use it: the point of
# the collision guard is that it fires on a header where these two overlap.
CANDIDATES = {
    "ant":    ["tag_id", "ant_id", "ant", "individual", "worker", "tag", "id"],
    "colony": ["colony", "colony_id", "col", "replicate"],
    "day":    ["day", "date", "day_idx", "time", "period"],
    "group":  ["group", "task", "caste", "role", "functional_group",
               "community", "cluster", "label"],
}
TASK_NAMES = {"n": "nurse", "c": "cleaner", "f": "forager", "q": "queen"}

QUEEN = "queen"
"""`queen` is a caste, not a task, and mixing the two costs in both directions.

Six ants in the real deposit carry the Q label in at least one period. Read as a
fourth task they are six individuals who are perfectly specialized and never
switch, which drags the division-of-labour score up for a reason that has nothing
to do with how labour is divided among the workers. Worse, if an ant is labelled
Q in one period and N or F in another, the distinct-value count scores her as
having changed group -- and a caste relabel is not task re-allocation. She would
be sitting inside the 183.

So the default is to drop any ant ever labelled queen, and to say how many were
dropped and what the change figure was with and without them. Six of 805 is small
enough that the aggregate barely moves, which is the argument FOR a principled
default rather than a shrug: it costs nothing to be right, and the number that
gets quoted should not depend on whether anyone remembered.
"""

PERIOD_RE = re.compile(r"^group[_ ]?period[_ ]?(\d+)$", re.I)

SKIP_NAMES = {"SOURCE.txt", "RESOLVED.json"}


def _normalize_task(v: str) -> str:
    s = str(v).strip().lower()
    return TASK_NAMES.get(s, s or "unknown")


def period_columns(header: list[str]) -> list[tuple[int, str]]:
    """Every `group_periodN` column, in N order."""
    out = [(int(m.group(1)), h) for h in header
           if (m := PERIOD_RE.match(str(h).strip()))]
    return sorted(out)


def is_apple_double(p: Path) -> bool:
    """macOS resource-fork shadows: `__MACOSX/._behavior.csv` and friends.

    They are named exactly like the real files and are binary. `stream_rows`
    opens with errors="replace", so reading one yields garbage rows rather than
    an exception -- and "pick the smallest labelled table" is exactly the kind of
    rule that picks one.
    """
    return p.name.startswith("._") or "__MACOSX" in p.parts


def _find_behavior(raw_dir: Path) -> tuple[Path, list[Path]]:
    """Prefer `behavior.csv` by name. Fall back only with a loud note.

    The old rule was `min(labelled, key=size)` -- the smallest file with anything
    resembling a task column. That is a rule about file sizes, not about content,
    and in this deposit it silently prefers
    `observed_expected_interaction_frequencies.csv`, whose `group` column is a
    single static assignment, over `behavior.csv`, which has the four periods we
    came for. Preferring a name we can check beats preferring a number that
    happens to be small.
    """
    files = [p for p in find_files(raw_dir, ["*.csv", "*.tsv", "*.txt"])
             if not is_apple_double(p) and p.name not in SKIP_NAMES]
    if not files:
        raise SystemExit(
            f"no delimited files under {raw_dir}. The Dryad bundle may need "
            "unzipping (fetch_data.py does this automatically, including the "
            "tracking_data.zip nested inside it) -- run inspect_data.py "
            "--dataset mersch_keller_2013 and report what you see."
        )
    for p in files:
        if p.stem.lower() in {"behavior", "behaviour"}:
            return p, files

    labelled = []
    for p in files:
        head = next(iter(stream_rows(p, limit=1)), None)
        if head and pick_column(list(head.keys()), CANDIDATES["group"], "task",
                                required=False):
            labelled.append(p)
    if not labelled:
        raise SystemExit(
            "found tables but none named behavior.csv and none with a "
            "task/group/caste column.\n"
            f"  files: {[p.name for p in files[:15]]}\n"
            "  run inspect_data.py --dataset mersch_keller_2013 and add the real "
            "column name to CANDIDATES['group'] in this file."
        )
    p = min(labelled, key=lambda q: q.stat().st_size)
    print(f"  NOTE: no behavior.csv here; falling back to {p.name} because it is the")
    print("        smallest table carrying a task-like column. That is a rule about")
    print("        file size, not about content -- confirm it is the right table.")
    return p, files


def load(raw_dir: Path, colony: str | None = None, min_obs: int = 1,
         task_col: str | None = None, day_col: str | None = None,
         queens: str = "exclude"):
    """Return (events, meta) in the canonical (agent, task, timestep) format."""
    path, _files = _find_behavior(raw_dir)
    print(f"  reading {path.name}")

    head = next(iter(stream_rows(path, limit=1)), None)
    if head is None:
        raise SystemExit(f"{path} is empty")
    header = list(head.keys())

    periods = period_columns(header)
    wide = bool(periods) and task_col is None

    if wide:
        # Wide path. `day` is not resolved at all -- the period index IS the time
        # index, so there is nothing for it to bind to and no collision to have.
        cols = pick_columns(header, {k: v for k, v in CANDIDATES.items()
                                     if k in ("ant", "colony")},
                            optional=("colony",))
        c_ant, c_col = cols["ant"], cols.get("colony")
        print(f"  columns -> ant={c_ant} colony={c_col}  "
              f"task={len(periods)} period columns: {[c for _, c in periods]}")
        print(f"  melting {len(periods)} wide period columns into "
              f"{len(periods)} timesteps per ant")
    else:
        cols = pick_columns(header, CANDIDATES, optional=("colony", "day"),
                            overrides={k: v for k, v in
                                       (("group", task_col), ("day", day_col))
                                       if v})
        c_ant, c_col = cols["ant"], cols.get("colony")
        c_grp, c_day = cols["group"], cols.get("day")
        print(f"  columns -> ant={c_ant} task={c_grp} day={c_day} colony={c_col}")

    eb = EventBuilder()
    colonies, tasks, missing = Counter(), Counter(), Counter()
    day_order: dict[str, int] = {}
    n_rows = 0
    changed = complete = 0
    changed_all = complete_all = 0        # the same counts with queens left in
    queen_ids: list[str] = []
    queen_mixed: list[str] = []           # labelled queen in one period, worker in another
    n_queen_rows = 0

    for row in stream_rows(path):
        n_rows += 1
        col = str(row[c_col]).strip() if c_col else "1"
        colonies[col] += 1
        if colony is not None and col != str(colony):
            continue
        # Namespace on colony. Ant57 exists in colonies 2, 3, 5 and 6; pooling
        # without this merges four animals into one node carrying all their
        # edges, and the "most central" ants are then the ids reused most often.
        #
        # The id goes through mersch_map.tag_int so that this key is identical by
        # construction to the one mersch_net.py emits, rather than identical by
        # luck. The two files render the same ant as `74` and `Ant74`; comparing
        # them as printed returned an overlap of exactly zero on all 36 colony
        # pairs, which looked like a finding about the deposit and was a fact
        # about the comparison. One normalizer, used by both sides.
        _tag = mersch_map.tag_int(str(row[c_ant]))
        agent = f"{col}:{_tag if _tag is not None else str(row[c_ant]).strip()}"

        if wide:
            seq = [_normalize_task(row.get(c, "")) for _, c in periods]
            labelled = [t for t in seq if t not in {"", "unknown", "na", "nan"}]
            is_queen = QUEEN in labelled
            if is_queen:
                n_queen_rows += 1
                queen_ids.append(agent)
                if any(t != QUEEN for t in labelled):
                    queen_mixed.append(agent)
            # Counted before the policy is applied, so the effect of the policy on
            # the headline figure is visible rather than inferred.
            if len(labelled) == len(seq):
                complete_all += 1
                changed_all += len(set(seq)) > 1
            if is_queen and queens == "exclude":
                continue
            if not is_queen and queens == "only":
                continue
            if len(labelled) == len(seq):
                complete += 1
                changed += len(set(seq)) > 1
            for (n, c), task in zip(periods, seq):
                if task in {"", "unknown", "na", "nan"}:
                    missing[c] += 1
                    continue
                tasks[task] += 1
                eb.add(agent, task, n - 1)
        else:
            task = _normalize_task(row[c_grp])
            if task in {"", "unknown", "na", "nan"}:
                missing[c_grp] += 1
                continue
            if task == QUEEN:
                n_queen_rows += 1
                queen_ids.append(agent)
                if queens == "exclude":
                    continue
            elif queens == "only":
                continue
            tasks[task] += 1
            day = str(row[c_day]).strip() if c_day else "0"
            if day not in day_order:
                try:
                    day_order[day] = int(float(day))
                except (TypeError, ValueError):
                    day_order[day] = len(day_order)
            eb.add(agent, task, day_order[day])

    events, meta = eb.build(min_obs_per_agent=min_obs)
    meta.update(
        source="Mersch, Crespi & Keller (2013), Dryad 10.5061/dryad.8d8h7, CC0",
        citation="Mersch, D. P., Crespi, A., & Keller, L. (2013). Science, 340(6136), 1090-1093.",
        file=path.name,
        colony=colony,
        colonies_available=dict(colonies),
        task_counts=dict(tasks),
        n_source_rows=n_rows,
        layout="wide (melted)" if wide else "long",
        period_columns=[c for _, c in periods] if wide else None,
        missing_labels=dict(missing) or None,
        node_key="colony:ant",
        # events.csv carries dense integer agent_ids, which is what the
        # instrument wants and is useless to anyone trying to join task labels to
        # network position: the names are the join key and they were being
        # discarded at the door. Exported here so `{colony}:{tag}` -- the same
        # string mersch_net.py emits under --node-namespace behavior -- can be
        # looked up. Without this the resolved colony mapping buys nothing.
        agent_index=dict(eb.agent_index),
        agent_index_note=("'{colony}:{tag}' -> the agent_id used in events.csv. "
                          "Joins to mersch_net.py node keys under "
                          "--node-namespace behavior."),
        task_definition="published functional-group label (nurse / cleaner / forager)"
                        + (" -- queens EXCLUDED" if queens == "exclude" else
                           " and queen -- queens KEPT as a task level" if queens == "keep"
                           else " -- QUEENS ONLY"),
        queens=queens,
        n_queens=len(set(queen_ids)),
        queen_ids=sorted(set(queen_ids))[:20] or None,
    )
    if queen_mixed:
        meta["queen_mixed_label"] = sorted(set(queen_mixed))[:20]
        meta["queen_mixed_warning"] = (
            f"{len(set(queen_mixed))} ant(s) are labelled queen in one period and a "
            f"worker task in another. A distinct-value count scores that as a change "
            f"of group, but a caste relabel is not task re-allocation -- it is either "
            f"a labelling artefact or a different phenomenon entirely, and either way "
            f"it does not belong in the switch fraction. With --queens exclude they "
            f"are out of it.")
    if wide:
        meta["n_ants_complete"] = complete
        meta["n_ants_changed_group"] = changed
        meta["share_changed_group"] = round(changed / max(1, complete), 4)
        meta["n_ants_complete_incl_queens"] = complete_all
        meta["n_ants_changed_group_incl_queens"] = changed_all
        meta["queen_effect_on_change_share"] = round(
            changed / max(1, complete) - changed_all / max(1, complete_all), 4)
        meta["temporal_caveat"] = (
            f"Task was assessed {len(periods)} times across the 41 days, so the "
            f"temporal resolution of 'task' is about {41 // max(1, len(periods))} "
            f"days. {changed} of {complete} ants labelled in every period "
            f"({changed / max(1, complete):.0%}) hold more than one label, so this "
            f"deposit DOES measure re-allocation -- but it is re-allocation the "
            f"colony did on its own, not a response to a manipulation. For a "
            f"manipulated comparison use Charbonneau & Dornhaus.")
        meta["denominator_caveat"] = (
            f"The denominator is {complete}, not the {n_rows} rows in the file. Those "
            f"{complete} are the ants labelled in EVERY period, i.e. the ones scoreable "
            f"across the whole record -- which is not a random subset, it is the "
            f"survivors. Quote the fraction with its denominator or not at all. The "
            f"naive count over all rows treats a blank cell as a distinct label and so "
            f"reads attrition as flexibility.")
    return events, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--colony", default=None)
    ap.add_argument("--min-obs", type=int, default=1)
    ap.add_argument("--task-col", default=None,
                    help="name the task column explicitly (also forces the long path)")
    ap.add_argument("--day-col", default=None, help="name the time column explicitly")
    ap.add_argument("--queens", choices=("exclude", "keep", "only"), default="exclude",
                    help="queen is a caste, not a task. Default drops any ant ever "
                         "labelled Q; 'only' gives you the queens alone, so "
                         "'report separately' is two runs and not a footnote")
    a = ap.parse_args()

    events, meta = load(Path(a.raw), a.colony, a.min_obs, a.task_col, a.day_col,
                        a.queens)
    write_events(events, meta, Path(a.out))
    report("mersch_keller_2013", meta)
    print(f"\n  colonies available: {meta['colonies_available']}")
    print(f"  queens: {meta['n_queens']} ({meta['queens']})")
    if meta.get("queen_mixed_warning"):
        print(f"  NOTE: {meta['queen_mixed_warning']}")
    if meta.get("share_changed_group") is not None:
        print(f"  ants changing group: {meta['n_ants_changed_group']} of "
              f"{meta['n_ants_complete']} ({meta['share_changed_group']:.1%})")
        print(f"    with queens left in: {meta['n_ants_changed_group_incl_queens']} of "
              f"{meta['n_ants_complete_incl_queens']}")
    print(f"  written: {Path(a.out) / 'events.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
