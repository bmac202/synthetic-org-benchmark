"""Charbonneau & Dornhaus worker-removal experiment -> canonical events + a shock time.

Dryad 10.5061/dryad.77110. Temnothorax rugatulus. Per-individual activity and
task before and after the removal of either the most active or the least active
workers, followed for roughly two weeks.

This is the single most important small dataset in the project. Every other open
deposit is observational: you can measure how specialized a colony is, but not
what happens when the workforce is disrupted. Here there is a real manipulation
with a real before and after, at the individual level. It is the only place we
can compute FLEXIBILITY -- re-allocation after a shock -- against biological
ground truth rather than against a simulated demand schedule.

THE REAL SCHEMA
---------------
`DryadData_Aug 8 2017.csv`, comma-delimited, ~156 KB:

    UAntID, Colony, Treat, Trial, i, a, ActInact, ClustDesc
    Jul14_11_dddo, Jul14_11, RemActive, post2, 1, 0, I, patroller

  UAntID    unique ant id, already namespaced by colony
  Colony    colony id
  Treat     RemActive / RemInactive / control -- which workers were removed
  Trial     pre / post1 / post2   <- this is TIME, and it is categorical
  i, a      proportion of scans inactive / active. Floats in [0, 1].
  ActInact  modal state that trial, "I" or "A"
  ClustDesc behavioural cluster: patroller, inactive, forager, ...

Note `i` and `a`. A substring-matching column picker binds "time" -> `i` and
"task" -> `a`, because "i" is inside "time" and "a" is inside "task". The loader
then runs to completion, collapses every event onto timestep 0, and uses a float
as a categorical task label. It produces numbers. They are meaningless. That is
why `pick_column` now refuses to fuzzy-match names shorter than three characters
and why the candidate lists below lead with the literal published names.

Time here is an ordered categorical, not a number, so the loader maps
pre/post1/post2 onto 0/1/2 through `common.ordered_map` rather than `float()`.

The file is tiny, so run this loader first. If the pipeline is wrong, you find
out in seconds rather than after an 11 GB download.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from .common import (EventBuilder, find_files, is_missing, is_post, normalize,
                     ordered_map, pick_column, pick_columns, report, stream_rows,
                     to_float, write_events)

# The literal published names come FIRST in every list. pick_column resolves
# exact matches in candidate order, so leading with the real name means the
# generic fallbacks can never outvote it.
CANDIDATES = {
    "ant":       ["UAntID", "ant_id", "antid", "ant", "individual", "worker",
                  "tag", "bee", "id"],
    "colony":    ["Colony", "colony_id", "col", "nest", "replicate"],
    "time":      ["Trial", "trial", "time", "day", "date", "observation",
                  "period", "scan", "week"],
    # ClustDesc is the behavioural cluster and is what we want. ActInact is a
    # two-level active/inactive flag -- a legitimate fallback, but a much
    # coarser one, so it sits behind ClustDesc rather than in front of it.
    "task":      ["ClustDesc", "clust_desc", "cluster", "task", "behavior",
                  "behaviour", "role", "state", "category", "ActInact"],
    "treatment": ["Treat", "treatment", "group", "condition", "removal",
                  "manipulation"],
    "phase":     ["Trial", "phase", "prepost", "pre_post", "stage",
                  "before_after", "period"],
}

# The one legitimate two-role column in this repo, and the reason the collision
# guard needed an exception at all.
#
# `Trial` in this deposit holds `pre`, `post1`, `post2`. It is the phase label,
# and it is also the time index -- because time here IS the ordinal rank of the
# phase. There is no separate clock. Both roles resolve to it, and both are
# right: `ordered_map` turns the same strings into 0/1/2 for binning, and
# `is_post` reads them as the manipulation marker to locate the shock.
#
# What makes this safe rather than a silent double-binding is the direction of
# the dependency. In the Mersch bug, task became a function of time, so task was
# perfectly predicted by time and every dependence measure went to ceiling by
# construction. Here the two roles that share a column are time and phase, and
# NOTHING measured is a function of either -- the task column is separate and
# untouched. Sharing a column between two describers of the same axis costs
# nothing; sharing one between a describer and the thing being described is what
# manufactures a finding.
#
# The check that keeps this honest: if a future file has a real clock AND a
# separate phase column, this alias does not fire, and `pick_columns` says so.
ALLOWED_ALIASES = [
    (("time", "phase"),
     "in this deposit `Trial` holds pre/post1/post2, which is simultaneously the "
     "phase label and the ordinal time index; there is no separate clock, and the "
     "task column is independent of both, so nothing measured becomes a function "
     "of its own time index"),
]

# Activity proportions, used only by --task-from activity. These are looked up
# by exact name: they are one character long and must never be fuzzy-matched.
ACTIVE_NAMES = ["a", "active", "prop_active", "propactive"]
INACTIVE_NAMES = ["i", "inactive", "prop_inactive", "propinactive"]


def _exact(header, names):
    norm = {normalize(h): h for h in header}
    for n in names:
        if normalize(n) in norm:
            return norm[normalize(n)]
    return None


def _activity_label(value: float) -> str:
    """Bin an activity proportion into a coarse ordinal task proxy."""
    if value < 0.10:
        return "act_none"
    if value < 0.34:
        return "act_low"
    if value < 0.67:
        return "act_mid"
    return "act_high"


def load(raw_dir: Path, min_obs: int = 2, task_from: str = "cluster",
         cols: dict | None = None):
    """Convert the deposit to canonical events.

    task_from : "cluster"  use the behavioural cluster column (the default and
                           the only one that measures task allocation)
                "activity" derive a coarse task from the active-time proportion.
                           A PROXY. Use only if the cluster label turns out to be
                           a static per-ant attribute, in which case switching is
                           structurally impossible and flexibility is undefined.
    cols      : optional {"ant": ..., "task": ...} overrides from --col-*.
    """
    cols = cols or {}
    files = find_files(raw_dir, ["*.csv", "*.txt", "*.tsv", "*.xlsx"])
    files = [f for f in files
             if f.name not in {"SOURCE.txt", "REQUEST.txt", "RESOLVED.json"}]
    delimited = [f for f in files if f.suffix.lower() != ".xlsx"]
    if not delimited:
        raise SystemExit(
            f"no delimited files under {raw_dir}.\n"
            f"  found: {[f.name for f in files[:10]]}\n"
            "  If the deposit is .xlsx, convert it first:\n"
            "     pip3 install openpyxl && python3 -c \"import openpyxl,csv,sys;"
            "wb=openpyxl.load_workbook(sys.argv[1]);ws=wb.active;"
            "w=csv.writer(open(sys.argv[2],'w'));[w.writerow(r) for r in ws.values]\" in.xlsx out.csv"
        )

    # pick the table that has both an individual and a task-like column
    best, best_score = None, -1
    for p in delimited:
        head = next(iter(stream_rows(p, limit=1)), None)
        if not head:
            continue
        hdr = list(head.keys())
        score = 0
        for keyname in ("ant", "task", "time", "treatment"):
            if pick_column(hdr, CANDIDATES[keyname], keyname, required=False):
                score += 1
        if score > best_score:
            best, best_score = p, score
    if best is None or best_score < 2:
        raise SystemExit(
            "could not identify a per-individual table.\n"
            f"  files: {[p.name for p in delimited[:15]]}\n"
            "  run inspect_data.py --dataset charbonneau_dornhaus_2017 and extend CANDIDATES."
        )
    path = best
    print(f"  reading {path.name}")

    head = next(iter(stream_rows(path, limit=1)))
    header = list(head.keys())
    # Resolved TOGETHER rather than in six independent calls. Six sequential
    # pick_column calls cannot see one another, which is precisely how `task` and
    # `day` both bound silently to `group_period1` in the Mersch loader.
    resolved = pick_columns(header, CANDIDATES,
                            optional=("time", "treatment", "phase", "colony"),
                            overrides={k: v for k, v in cols.items() if v},
                            allow_alias=ALLOWED_ALIASES)
    c_ant = resolved["ant"]
    c_task = resolved["task"]
    c_time = resolved.get("time")
    c_trt = resolved.get("treatment")
    c_phase = resolved.get("phase")
    c_col = resolved.get("colony")
    for a in resolved.aliases:
        if a["fired"]:
            print(f"  NOTE: {' and '.join(a['roles'])} share column "
                  f"{a['column']!r} -- {a['reason']}")
    c_active = _exact(header, ACTIVE_NAMES)
    c_inactive = _exact(header, INACTIVE_NAMES)

    if task_from == "activity":
        if not c_active:
            raise SystemExit(
                "--task-from activity needs an active-proportion column and this "
                f"file has none.\n  header is: {header}"
            )
        c_task = c_active

    print(f"  columns -> ant={c_ant} task={c_task} time={c_time} "
          f"treatment={c_trt} phase={c_phase} colony={c_col}")
    if c_active or c_inactive:
        print(f"  (activity columns present: active={c_active} inactive={c_inactive})")

    # ---------------------------------------------------------- read the file
    # 156 KB. Read it once into memory so we can decide whether the time column
    # is numeric or categorical before committing to an interpretation.
    rows = []
    n_missing_task = 0
    for row in stream_rows(path):
        raw_task = str(row[c_task]).strip()
        # `NA` is a literal string here, not an empty cell. 250 ants carry it in
        # ClustDesc -- ants first seen after the removal, whom the pre-removal
        # cluster analysis never classified. Kept as a value it would become a
        # fifth behavioural group with 250 members that does not exist.
        if is_missing(raw_task):
            n_missing_task += 1
            continue
        if task_from == "activity":
            av = to_float(raw_task)
            if av is None:
                continue
            task = _activity_label(av)
        else:
            task = raw_task.lower()
        rows.append((
            str(row[c_col]).strip() if c_col else "1",
            str(row[c_ant]).strip(),
            task,
            str(row[c_time]).strip() if c_time else "0",
            str(row[c_trt]).strip() if c_trt else "",
            str(row[c_phase]).strip() if c_phase else "",
        ))
    if n_missing_task:
        pct = n_missing_task / (n_missing_task + len(rows))
        print(f"  dropped {n_missing_task} rows ({pct:.1%}) with a missing "
              f"{c_task}. Those rows still exist in the file; they are not usable "
              f"as a task and are NOT a category.")
        if pct > 0.5:
            print(f"  NOTE: that is most of the file. Whatever is measured from "
                  f"{c_task} describes the minority of rows that carry one, and "
                  f"the reason the rest are missing has to be understood before "
                  f"any number is quoted. Run validate_dornhaus.py.")
    if not rows:
        raise SystemExit(f"read 0 usable rows from {path.name} -- check --col-task")

    # ------------------------------------------------- numeric or ordinal time
    raw_times = [r[3] for r in rows]
    numeric = all(to_float(t) is not None for t in raw_times)
    if numeric:
        time_map = None
        time_kind = "numeric"

        def tbin_of(label: str) -> int:
            return int(to_float(label))
    else:
        time_map = ordered_map(raw_times)
        time_kind = "ordinal categorical"

        def tbin_of(label: str) -> int:
            return time_map[label]
        print(f"  time column is categorical; ordered as "
              f"{[k for k, _ in sorted(time_map.items(), key=lambda kv: kv[1])]}")

    eb = EventBuilder()
    treatments, tasks, phases = Counter(), Counter(), Counter()
    phase_at_time: dict[int, Counter] = {}
    task_by_agent: dict[str, set] = defaultdict(set)

    for col, ant, task, traw, trt, ph in rows:
        tbin = tbin_of(traw)
        agent = f"{col}:{ant}"
        eb.add(agent, task, tbin)
        tasks[task] += 1
        task_by_agent[agent].add(task)
        if trt:
            treatments[trt] += 1
        if ph:
            phases[ph.lower()] += 1
            phase_at_time.setdefault(tbin, Counter())[ph.lower()] += 1

    events, meta = eb.build(min_obs_per_agent=min_obs)

    # ------------------------------------------------------- locate the shock
    # Computed in RAW bin units, then mapped through the builder's dense index.
    # Skipping that mapping silently misplaces the shock by however many bins
    # were empty before it -- with days numbered from 1, that is off by one.
    raw_shift = None
    if phase_at_time:
        for t in sorted(phase_at_time):
            if is_post(phase_at_time[t].most_common(1)[0][0]):
                raw_shift = t
                break
    if raw_shift is not None:
        shift = eb.bin_index.get(raw_shift, raw_shift)
        shift_note = ("shock time taken from the dataset's own phase column "
                      f"({c_phase}), first post-manipulation level.")
    elif eb.bin_index:
        shift = len(eb.bin_index) // 2
        shift_note = ("no explicit pre/post column found; shock time set to the midpoint "
                      "of the observation window. CHECK THIS against the paper before "
                      "reporting any flexibility number.")
    else:
        shift, shift_note = None, "no time bins"

    # --------------------------------------------- can flexibility exist here?
    # If every ant carries one task label for the whole experiment, the label is
    # a static attribute rather than a behavioural state, switch_fraction is
    # structurally zero, and the flexibility measure is measuring nothing.
    multi = sum(1 for a, s in task_by_agent.items() if len(s) > 1)
    varies = round(multi / max(1, len(task_by_agent)), 4)
    if varies == 0.0:
        print("\n  WARNING: no ant ever changes task label in this file.")
        print(f"           '{c_task}' is a static per-individual attribute here, so")
        print("           switch_fraction is structurally 0 and flexibility is undefined.")
        print("           Re-run with --task-from activity to use the activity proportions")
        print("           as a task proxy, and label the result a proxy when reporting it.")

    meta.update(
        source="Charbonneau & Dornhaus, Dryad 10.5061/dryad.77110",
        citation="Charbonneau, D., & Dornhaus, A. (2017). Behavioral Ecology and Sociobiology.",
        file=path.name,
        columns=dict(ant=c_ant, task=c_task, time=c_time, treatment=c_trt,
                     phase=c_phase, colony=c_col),
        column_aliases=resolved.aliases or None,
        task_source=task_from,
        task_counts=dict(tasks),
        treatments=dict(treatments) or None,
        phases=dict(phases) or None,
        time_kind=time_kind,
        time_levels=(None if time_map is None else
                     [k for k, _ in sorted(time_map.items(), key=lambda kv: kv[1])]),
        shift_timestep=shift,
        shift_note=shift_note,
        task_varies_within_agent=varies,
        task_definition=("behavioural cluster as coded by the authors"
                         if task_from == "cluster" else
                         "PROXY: active-time proportion binned into four ordinal levels"),
        design="worker removal (most-active vs least-active) with pre/post observation",
    )
    return events, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-obs", type=int, default=2,
                    help="drop ants seen in fewer than this many time bins. "
                         "The real file has only 3 (pre/post1/post2), so 2 keeps "
                         "any ant present on both sides of the shock.")
    ap.add_argument("--task-from", choices=["cluster", "activity"], default="cluster",
                    help="'cluster' uses the behavioural cluster column; "
                         "'activity' derives a coarse proxy from the active-time "
                         "proportion. Only use the proxy if the cluster label is static.")
    for name in ("ant", "task", "time", "treatment", "phase", "colony"):
        ap.add_argument(f"--col-{name}", default=None,
                        help=f"force the {name} column instead of auto-detecting")
    a = ap.parse_args()

    cols = {n: getattr(a, f"col_{n}")
            for n in ("ant", "task", "time", "treatment", "phase", "colony")}
    events, meta = load(Path(a.raw), a.min_obs, task_from=a.task_from, cols=cols)
    write_events(events, meta, Path(a.out))
    report("charbonneau_dornhaus_2017", meta)
    print(f"\n  treatments   : {meta.get('treatments')}")
    print(f"  time         : {meta.get('time_kind')}  {meta.get('time_levels') or ''}")
    print(f"  shock at t   : {meta.get('shift_timestep')}  ({meta.get('shift_note')})")
    print(f"  task varies  : {meta.get('task_varies_within_agent')} of individuals "
          "change label at least once")
    print(f"  written: {Path(a.out) / 'events.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
