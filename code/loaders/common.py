"""Shared helpers for turning published tracking data into one canonical format.

Canonical event format
----------------------
Every loader emits the same thing: a list of `(agent_id, task_id, timestep)`
triples, where `agent_id` and `task_id` are small non-negative integers and
`timestep` is a dense integer starting at 0. That is exactly what
`bench.colony_from_events()` already consumes, so a real colony and a
mechanistic model become interchangeable inputs to the same instruments.

Two things this module is deliberately careful about.

1.  **Column discovery.** None of these deposits publish a schema, and several
    were released without a README. Rather than hard-code column names that may
    be wrong, `pick_column` matches against a list of plausible names and, on
    failure, raises with the actual header printed. Guessing silently is how you
    end up analysing the wrong variable for a week.

2.  **Time binning.** Raw records run at 3 fps for months. `colony_from_events`
    allocates a row per timestep, so raw frame numbers would exhaust memory and
    would in any case be far finer than the behavioural process. `quantize`
    reduces time to a chosen number of bins and records the mapping.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Iterator, Sequence


# ------------------------------------------------------------------ discovery
def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


MIN_FUZZY = 3
"""Shortest name either side of a fuzzy comparison.

The real Charbonneau & Dornhaus header contains columns literally named `i` and
`a` (proportions of time inactive and active). A naive substring match binds
`time` -> `i` and `task` -> `a`, because "i" is a substring of "time" and "a" is
a substring of "task". Both are floats between 0 and 1, so the loader completes
without error and produces an entire analysis of the wrong variable. Anything
shorter than this never participates in fuzzy matching; it must match exactly.
"""


def pick_column(header: Sequence[str], candidates: Sequence[str], what: str,
                required: bool = True, override: str | None = None) -> str | None:
    """Find the column whose name best matches one of `candidates`.

    Resolution order, most trustworthy first:

    1.  `override` -- what the user passed on the command line. If they named a
        column that is not in the file, that is an error, not a cue to guess.
    2.  Exact match (after normalization) in candidate order, so the *first*
        candidate wins. Candidate order is therefore meaningful: put the column
        you actually want first.
    3.  Fuzzy substring match, but only between names of at least MIN_FUZZY
        characters, and the longest overlap wins rather than whichever header
        happened to be encountered first.

    Guessing silently is how you analyse the wrong variable for a week.
    """
    norm = {normalize(h): h for h in header}

    if override:
        if normalize(override) in norm:
            return norm[normalize(override)]
        raise KeyError(
            f"you asked for column {override!r} for {what!r}, but the file does "
            f"not have it.\n  header is: {list(header)}"
        )

    for c in candidates:                       # exact, normalized, in order
        if normalize(c) in norm:
            return norm[normalize(c)]

    best, best_score = None, 0
    for c in candidates:
        nc = normalize(c)
        if len(nc) < MIN_FUZZY:
            continue
        for nh, orig in norm.items():
            if len(nh) < MIN_FUZZY:
                continue
            if nc in nh or nh in nc:
                score = min(len(nc), len(nh))  # length of the shared part
                if score > best_score:
                    best, best_score = orig, score
    if best is not None:
        return best

    if required:
        raise KeyError(
            f"could not find a column for {what!r}.\n"
            f"  tried: {list(candidates)}\n"
            f"  header is: {list(header)}\n"
            f"  -> open code/loaders/ and add the right name to the candidate list"
        )
    return None


class ColumnCollision(KeyError):
    """Two variable roles resolved to the same column."""


class ColumnMap(dict):
    """A role -> column mapping that also remembers which aliases were allowed.

    A plain dict would carry the resolution but not the fact that two roles are
    deliberately sharing a column. That fact belongs in the output metadata, so
    it is here rather than in a comment somebody has to go and find.
    """

    aliases: list[dict]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.aliases = []


def pick_columns(header: Sequence[str], spec: dict[str, Sequence[str]],
                 optional: Sequence[str] = (),
                 overrides: dict[str, str] | None = None,
                 allow_alias: Sequence[tuple[Sequence[str], str]] = ()) -> ColumnMap:
    """Resolve several roles at once, and REFUSE when two land on one column.

    `pick_column` is right about one variable at a time and cannot see the bug
    that matters most. On the real Mersch header it resolves

        task -> group_period1        ("group" fuzzy-matches "groupperiod1")
        day  -> group_period1        ("period" fuzzy-matches it too)

    and returns both answers happily, because neither call knows the other
    happened. Nothing raises. The loader completes. But the day index is now a
    *function of* the task label -- every nurse assigned one day, every cleaner
    another -- so task is perfectly determined by time, mutual information is
    maximal by construction, the division-of-labour score sits at ceiling, kappa
    is 1.0 and the switch fraction is structurally 0. Every one of those numbers
    looks like a finding.

    Two roles exist because two distinct quantities are needed. One column cannot
    be both. So a collision is always a bug and never a coincidence, and the only
    safe response is to stop and make somebody name the columns explicitly --
    which is what `overrides` is for. Guessing silently is how you analyse the
    wrong variable for a week; guessing the SAME thing twice is how you analyse
    the wrong variable and get a clean result.

    ------------------------------------------------------------------ aliases

    "Always a bug" was written from one deposit and is too strong by exactly one
    case. Charbonneau & Dornhaus has a `Trial` column holding `pre`, `post1`,
    `post2`. That single column really is both the phase label AND the time
    index, because the time index here IS the ordinal rank of the phase. The
    loader knowingly uses it as both, and has always been right to.

    So a collision is a bug unless somebody has said in advance that it is not.
    `allow_alias` takes (roles, reason) pairs, the reason is mandatory and is
    carried into the output metadata, and an alias that is declared but does not
    fire is reported too -- because a declaration that has quietly stopped
    applying is a stale permission, and stale permissions are how a guard decays
    into a comment. Anything undeclared still raises.

    The distinction that matters: an alias is a claim that one column legitimately
    answers two questions. It is NOT a way to silence a collision you do not
    understand. If you cannot write the reason, you have found a bug.
    """
    overrides = overrides or {}
    out = ColumnMap()
    for role, cands in spec.items():
        col = pick_column(header, cands, role, required=role not in optional,
                          override=overrides.get(role))
        if col is not None:
            out[role] = col

    allowed: dict[frozenset, str] = {}
    for roles, why in allow_alias:
        if not str(why).strip():
            raise ValueError(
                f"allow_alias for {sorted(roles)} has no reason. The reason is "
                "the whole mechanism: it is what distinguishes a column that "
                "genuinely answers two questions from a collision somebody "
                "wanted to stop seeing.")
        allowed[frozenset(roles)] = why

    by_col: dict[str, list[str]] = defaultdict(list)
    for role, col in out.items():
        by_col[col].append(role)

    clashes = {}
    for c, rs in by_col.items():
        if len(rs) < 2:
            continue
        key = frozenset(rs)
        if key in allowed:
            out.aliases.append(dict(roles=sorted(rs), column=c,
                                    reason=allowed[key], fired=True))
        else:
            clashes[c] = sorted(rs)

    fired = {frozenset(a["roles"]) for a in out.aliases}
    for key, why in allowed.items():
        if key not in fired:
            out.aliases.append(dict(roles=sorted(key), column=None, reason=why,
                                    fired=False,
                                    note="declared but did not fire on this header; "
                                         "these roles resolved to different columns, "
                                         "so the permission was not needed here"))

    if clashes:
        lines = "\n".join(f"    {' and '.join(rs)} both resolved to {c!r}"
                          for c, rs in sorted(clashes.items()))
        raise ColumnCollision(
            "two variable roles resolved to the same column, and nobody declared "
            "that they may share one:\n" + lines +
            f"\n  header is: {list(header)}\n"
            "  -> name the columns explicitly (e.g. --task-col / --day-col), or "
            "fix the candidate lists in this loader, or -- if one column really "
            "does answer both questions -- declare it in this loader's "
            "allow_alias with the reason why.\n"
            "     Proceeding would make one quantity stand in for another and "
            "produce a complete run with plausible numbers about the wrong thing."
        )
    return out


# --------------------------------------------------- categorical time columns
PHASE_HINTS = (
    ("pre", -100), ("before", -100), ("baseline", -100), ("control", -90),
    ("during", 0), ("shock", 0), ("removal", 0), ("treat", 0),
    ("post", 100), ("after", 100), ("recovery", 110),
)


def phase_rank(label: str) -> tuple[int, float, str]:
    """Sort key for a phase-like label such as pre / post1 / post2.

    Several deposits record time as an ordered categorical rather than a number.
    Sorting those strings alphabetically puts "post1" before "pre", which silently
    reverses the experiment. This ranks by phase word first, then by any trailing
    digits, then alphabetically as a last resort.
    """
    s = normalize(label)
    base = 0
    for word, rank in PHASE_HINTS:
        if s.startswith(word):
            base = rank
            break
    else:
        for word, rank in PHASE_HINTS:
            if word in s:
                base = rank
                break
    digits = re.findall(r"\d+", s)
    return (base, float(digits[0]) if digits else 0.0, s)


def ordered_map(labels: Iterable[str]) -> dict[str, int]:
    """Map categorical time labels onto dense integers in experimental order."""
    uniq = sorted({str(x) for x in labels if str(x).strip() != ""}, key=phase_rank)
    return {lab: i for i, lab in enumerate(uniq)}


def is_post(label: str) -> bool:
    """True if this label names a period after the manipulation."""
    return phase_rank(label)[0] > 0


def sniff_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    for d in ("\t", ";", "|", ","):
        if d in first:
            return d
    return ","


def stream_rows(path: Path, limit: int | None = None) -> Iterator[dict]:
    """Stream a delimited file as dicts without loading it into memory."""
    delim = sniff_delimiter(path)
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            yield row


def find_files(root: Path, patterns: Sequence[str]) -> list[Path]:
    hits: list[Path] = []
    for pat in patterns:
        hits.extend(sorted(p for p in root.rglob(pat) if p.is_file()))
    seen, out = set(), []
    for p in hits:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ------------------------------------------------------------- missing values
MISSING = {"", "na", "n/a", "nan", "none", "null", "-", ".", "?", "#n/a"}
"""Strings that mean "no value" rather than being a value.

`NA` is the R convention and it arrives from these deposits as the literal
two-character string. Charbonneau & Dornhaus carries 250 ants whose ClustDesc is
`NA` -- ants first seen after the removal, so the pre-removal cluster analysis
never assigned them a group. Read naively, `NA` becomes a fifth behavioural
category with 250 members, and every task distribution, every division-of-labour
number and every switch count is computed over a group that does not exist.

The same string appears in ActInact on 1,372 of 2,346 rows. Missingness at that
scale is not a nuisance to be silently dropped either: which rows are missing is
itself a finding, so `validate_dornhaus.py` reports the pattern rather than
letting the loaders quietly discard it.
"""


def is_missing(v) -> bool:
    """True if this cell means 'no value'. Case- and whitespace-insensitive."""
    return str(v).strip().lower() in MISSING


def to_float(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------- time bins
def quantize(value: float, lo: float, hi: float, n_bins: int) -> int:
    if hi <= lo:
        return 0
    b = int((value - lo) / (hi - lo) * n_bins)
    return max(0, min(n_bins - 1, b))


# A bin count is not a bin width. `quantize` divides the observed span into
# `n_bins` equal pieces, so "24 bins" means one hour only if the record happens
# to be one day long. The Illinois trials run about five days, where 24 bins are
# five hours each -- and five hours is most of a bee's active period. Every
# question these loaders exist to answer ("do the same individuals stay central
# across bins?") is asked across bins, so a bin whose width nobody has written
# down is a unit nobody can interpret.
#
# The two helpers below exist so a loader can state what one bin IS, in hours,
# or say plainly that it cannot tell. Saying it cannot tell is the point: a
# confident bin width that is wrong by a factor of a thousand is worse than none.

# unit name -> (units per second, smallest absolute epoch that could be this unit)
# The magnitude thresholds are the same instant (1973) expressed in each unit, so
# the bands are disjoint by three orders of magnitude and cannot both match.
TIME_UNITS = (
    ("us", 1_000_000.0, 1e14),
    ("ms", 1_000.0,     1e11),
    ("s",  1.0,         1e8),
)

# No colony trial in any of these deposits runs for a year, and none is over in
# under a minute. A unit guess that implies a span outside this range has been
# refuted by the data itself, whatever its magnitude suggested.
PLAUSIBLE_SPAN_S = (60.0, 400 * 24 * 3600.0)


def infer_time_unit(t_lo: float, t_hi: float) -> dict:
    """What unit are these timestamps in, and what is the span in hours?

    Returns a record with `unit`, `per_hour`, `span_hours` and `why`. `unit` is
    None when the timestamps cannot be identified -- relative times starting near
    zero, frame counters, anything whose magnitude is not an absolute epoch.

    Two independent tests have to agree. The magnitude of `t_lo` says which unit
    an absolute epoch would be in; the resulting span says whether that reading
    describes a plausible animal-tracking record. A frame counter at 3 fps that
    has been running long enough to look like an epoch in seconds will fail the
    second test, and a reading that fails either test is reported as unknown
    rather than as a number somebody will put in a table.
    """
    if t_lo is None or t_hi is None or t_hi < t_lo:
        return dict(unit=None, per_hour=None, span_hours=None,
                    why="no usable timestamps")
    for name, per_s, floor in TIME_UNITS:
        if t_lo < floor:
            continue
        span_s = (t_hi - t_lo) / per_s
        if not (PLAUSIBLE_SPAN_S[0] <= span_s <= PLAUSIBLE_SPAN_S[1]):
            return dict(
                unit=None, per_hour=None, span_hours=None,
                why=(f"magnitude says {name}, but that makes the record "
                     f"{span_s / 3600:,.3f} h long, which is not a trial. The "
                     f"two tests disagree, so the unit is reported as unknown."))
        return dict(unit=name, per_hour=per_s * 3600.0,
                    span_hours=span_s / 3600.0,
                    why=f"t_lo={t_lo:,.0f} is an absolute epoch in {name}")
    return dict(unit=None, per_hour=None, span_hours=None,
                why=(f"t_lo={t_lo:,.0f} is too small to be an absolute epoch; "
                     "these look like relative times or frame indices, so a bin "
                     "width in hours cannot be computed"))


def plan_bins(span_hours: float | None, n_bins: int | None = None,
              bin_hours: float | None = None) -> tuple[int, float | None, list[str]]:
    """Turn a bin count OR a bin width into (n_bins, bin_hours, notes).

    `bin_hours` wins when both are given, because a width is the more meaningful
    of the two: it is comparable across records of different lengths, which is
    what you need before comparing five Illinois trials with a Gernat trial.

    `notes` carries the circadian warnings. They are warnings and not errors on
    purpose -- a bin that straddles day and night is not invalid, it is a bin
    whose contents mix an activity peak with a trough, and whoever reads the
    output needs to be told which one they have.
    """
    notes: list[str] = []
    if bin_hours is not None:
        if span_hours is None:
            raise SystemExit(
                "--bin-hours needs a bin width in hours, and this file's "
                "timestamps could not be identified as clock time (see the "
                "time-unit line above). Use --bins to divide the record into a "
                "number of equal pieces instead, and read the result as "
                "fractions of the record rather than as hours.")
        if bin_hours <= 0:
            raise SystemExit("--bin-hours must be positive")
        n = max(1, int(math.ceil(span_hours / bin_hours)))
        return n, float(bin_hours), notes + circadian_notes(span_hours, bin_hours)
    n = int(n_bins or 1)
    if n < 1:
        raise SystemExit("--bins must be at least 1")
    width = (span_hours / n) if span_hours else None
    return n, width, notes + circadian_notes(span_hours, width)


def circadian_notes(span_hours: float | None, bin_hours: float | None) -> list[str]:
    """Whether the bin grid can be separated from the daily activity cycle.

    Bees are strongly diurnal, so which individuals appear central in a bin
    depends on what time of day the bin covers. That confound is not removable
    in general -- but it IS removable when the bin width divides 24 h, because
    then bin k and bin k + 24/width cover the same clock hours and can be folded
    onto each other. Time of day then becomes a factor you can average over
    instead of a term hidden inside "hub churn".

    So the rule is not that non-divisor bins are wrong. It is that divisor bins
    make the circadian term separable and non-divisor bins do not.
    """
    if span_hours is None or bin_hours is None:
        return ["bin width in hours is unknown for this file, so nothing can be "
                "said about whether bins align with the daily cycle"]
    notes: list[str] = []
    if span_hours < 30:
        notes.append(
            f"the record is {span_hours:.1f} h, under one full day plus a "
            "margin. Bins are clock-time slices of a single day, so bin-to-bin "
            "hub churn cannot be separated from the daily activity cycle: "
            "there is no second day to fold these bins onto.")
        return notes
    per_day = 24.0 / bin_hours
    if abs(per_day - round(per_day)) > 1e-9:
        notes.append(
            f"a bin is {bin_hours:.2f} h, which does not divide 24 h "
            f"({per_day:.2f} bins per day). Bin boundaries therefore drift "
            "against the solar day, bin k covers a different time of day on "
            "each day of the record, and the circadian term cannot be folded "
            "out. Pick a width from 1, 2, 3, 4, 6, 8, 12 or 24 h to make it "
            "separable.")
    if bin_hours > 6:
        notes.append(
            f"a bin is {bin_hours:.2f} h, long enough to contain both a full "
            "activity peak and a full trough. Whatever varies within it is "
            "averaged away before anything is measured.")
    return notes


# --------------------------------------------------------------- event build
class EventBuilder:
    """Accumulate (agent, task, time) observations, then emit dense integer events.

    Handles the common case where an agent is observed many times inside one
    time bin: the modal task in that bin wins, which is the standard scan-sample
    convention and keeps one row per (agent, bin).
    """

    def __init__(self) -> None:
        self._obs: dict[tuple[str, int], Counter] = defaultdict(Counter)
        self._agents: set[str] = set()
        self._tasks: set[str] = set()
        self._bins: set[int] = set()
        # filled in by build(): raw bin value -> dense timestep index. Callers
        # that computed a landmark (a shock time, say) in RAW bin units must map
        # it through this, or the landmark lands on the wrong event timestep.
        self.bin_index: dict[int, int] = {}
        self.agent_index: dict[str, int] = {}

    def add(self, agent, task, tbin: int, weight: int = 1) -> None:
        a, t = str(agent), str(task)
        self._obs[(a, int(tbin))][t] += weight
        self._agents.add(a)
        self._tasks.add(t)
        self._bins.add(int(tbin))

    def build(self, min_obs_per_agent: int = 1
              ) -> tuple[list[tuple[int, int, int]], dict]:
        agents = sorted(self._agents)
        tasks = sorted(self._tasks)
        bins = sorted(self._bins)
        a_ix = {a: i for i, a in enumerate(agents)}
        t_ix = {t: i for i, t in enumerate(tasks)}
        b_ix = {b: i for i, b in enumerate(bins)}
        self.bin_index = dict(b_ix)
        self.agent_index = dict(a_ix)

        per_agent = Counter(a for (a, _b) in self._obs)
        keep = {a for a, n in per_agent.items() if n >= min_obs_per_agent}

        events: list[tuple[int, int, int]] = []
        for (a, b), counter in self._obs.items():
            if a not in keep:
                continue
            task = counter.most_common(1)[0][0]
            events.append((a_ix[a], t_ix[task], b_ix[b]))
        events.sort(key=lambda e: (e[2], e[0]))

        meta = dict(
            n_agents=len(keep),
            n_agents_before_filter=len(agents),
            n_tasks=len(tasks),
            n_timesteps=len(bins),
            n_events=len(events),
            task_labels={t_ix[t]: t for t in tasks},
            obs_per_agent_median=_median(sorted(per_agent[a] for a in keep)) if keep else 0,
            obs_per_agent_min=min((per_agent[a] for a in keep), default=0),
            obs_per_agent_max=max((per_agent[a] for a in keep), default=0),
            density=round(len(events) / max(1, len(keep) * len(bins)), 4),
        )
        return events, meta


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


# ------------------------------------------------------------------- output
def write_events(events: Iterable[tuple[int, int, int]], meta: dict, out_dir: Path,
                 extra: dict | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "events.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["agent_id", "task_id", "timestep"])
        w.writerows(events)
    payload = dict(meta)
    if extra:
        payload.update(extra)
    (out_dir / "meta.json").write_text(json.dumps(payload, indent=2, default=str))
    return path


def read_events(out_dir: Path) -> tuple[list[tuple[int, int, int]], dict]:
    path = out_dir / "events.csv"
    events = []
    for row in stream_rows(path):
        events.append((int(row["agent_id"]), int(row["task_id"]), int(row["timestep"])))
    meta_path = out_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return events, meta


def report(name: str, meta: dict) -> None:
    print(f"\n  {name}")
    print(f"    agents      : {meta['n_agents']} (of {meta['n_agents_before_filter']} seen)")
    print(f"    tasks       : {meta['n_tasks']}  {meta.get('task_labels')}")
    print(f"    timesteps   : {meta['n_timesteps']}")
    print(f"    events      : {meta['n_events']}  (density {meta['density']})")
    print(f"    obs / agent : min {meta['obs_per_agent_min']}, "
          f"median {meta['obs_per_agent_median']}, max {meta['obs_per_agent_max']}")
    n = meta["n_agents"]
    if n < 50:
        print(f"    NOTE: {n} agents is below the ~50-150 needed for stable per-individual")
        print("          specialization estimates. Treat individual-level numbers as indicative.")
