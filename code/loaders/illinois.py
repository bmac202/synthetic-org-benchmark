"""Robinson-lab bee-monitoring portal, trial1-5 -> five independent interaction logs.

beemonitoring.igb.illinois.edu, companion data to Gernat et al. (2018) PNAS
115(7), 1433-1438. Five separate colonies, each in its own `trialN.txt`,
~60 MB in total.

THE REAL SCHEMA
---------------
    trial, id1, id2, begin, end

  trial       colony/trial identifier, constant within a file
  id1, id2    the two bees. There is NO direction column: this is a record of
              *contact*, not of flow.
  begin, end  millisecond epochs bounding the contact.

Two consequences follow from the missing direction column, and both matter for
how the output is read.

First, every contact is emitted in both orderings, so the graph is symmetric.
Centralization remains meaningful -- it is a statement about how unevenly
contact concentrates -- but a recovered "reporting edge" here is a strong tie,
not a direction of influence. The gernat loader says the same thing about its
unresolved rows; it is restated because this whole dataset is in that case.

Second, and more usefully: these are five independent colonies measured the same
way. The single most fragile claim in a study like ours is that a network result
from one colony is a property of colonies rather than of that colony. Five
replicates is the cheapest available answer, and it costs one loader. If
centralization is low and hubs are stable in all five, that is a finding; if it
holds in two of five, we have learned something more important than the result
we wanted.

Duration is kept in the metadata rather than used as an edge weight. A contact
lasting ten seconds is not ten times the tie that a one-second contact is, and
weighting by it silently changes what centralization means. It is used for one
thing only: a contact is an interval, so the loader bins it on its midpoint and
reports how many contacts cross a bin boundary. That number is what tells you
whether the choice of endpoint mattered, and it belongs in the output rather
than in an assumption.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .common import (find_files, infer_time_unit, pick_column, pick_columns,
                     plan_bins, quantize, stream_rows, to_float)
from .gernat import write_log

CANDIDATES = {
    "trial": ["trial", "colony", "trial_id", "colony_id"],
    "id1":   ["id1", "bee1", "partner1", "partner_1", "from", "source"],
    "id2":   ["id2", "bee2", "partner2", "partner_2", "to", "target"],
    "begin": ["begin", "start", "start_time", "timestamp", "time"],
    "end":   ["end", "stop", "end_time", "finish"],
}

MS_PER_HOUR = 3_600_000


def trial_files(raw_dir: Path) -> list[Path]:
    files = find_files(raw_dir, ["trial*.txt", "trial*.csv", "trial*.tsv"])
    return [f for f in files
            if f.name not in {"SOURCE.txt", "REQUEST.txt", "RESOLVED.json"}]


def load_one(path: Path, n_bins: int = 24, max_rows: int | None = None,
             bin_hours: float | None = None):
    """Return (log, meta) for a single trial file.

    A contact here is an interval, not an instant. `begin` and `end` bound it,
    and the loader has to decide which single moment the contact belongs to
    before it can be put in a time bin. It uses the MIDPOINT, and then counts how
    many contacts would have landed in a different bin had the start been used
    instead. That count is the whole justification: if it is a handful out of a
    million the choice is immaterial and the number says so, and if it is large
    the binning is too fine for contacts this long and the number says that too.
    Either way it is in the metadata rather than in somebody's head.

    The observation window runs to the last `end`, not the last `begin`. A
    contact still in progress when the last one starts is inside the record, and
    a window that stops at the last start understates the span it covers.
    """
    head = next(iter(stream_rows(path, limit=1)), None)
    if head is None:
        raise SystemExit(f"{path} is empty")
    header = list(head.keys())

    # Resolved together. `begin` and `end` are the dangerous pair: a column named
    # something like `interval_begin_end` matches both candidate lists, and then
    # every contact has duration end - begin == 0. Nothing raises, the file reads,
    # and every duration-weighted edge silently weighs nothing -- which is exactly
    # the quantity this loader exists to compute.
    resolved = pick_columns(header, CANDIDATES,
                            optional=("begin", "end", "trial"))
    c1, c2 = resolved["id1"], resolved["id2"]
    c_begin = resolved.get("begin")
    c_end = resolved.get("end")
    c_trial = resolved.get("trial")
    print(f"  {path.name}: id1={c1} id2={c2} begin={c_begin} end={c_end} trial={c_trial}")

    pairs: list[tuple[str, str, float | None, float | None]] = []
    trials = Counter()
    begins: list[float] = []
    ends: list[float] = []
    durations: list[float] = []
    skipped_self = 0
    n_reversed = 0

    for row in stream_rows(path, limit=max_rows):
        a, b = str(row[c1]).strip(), str(row[c2]).strip()
        if not a or not b:
            continue
        if a == b:
            skipped_self += 1
            continue
        if c_trial:
            trials[str(row[c_trial]).strip()] += 1
        tv = to_float(row[c_begin]) if c_begin else None
        ev = to_float(row[c_end]) if c_end else None
        if tv is not None:
            begins.append(tv)
        # An `end` before its `begin` is not a short contact, it is a row this
        # loader does not understand. Counted and then ignored for duration, so
        # it cannot quietly enter the distribution as a negative number.
        if tv is not None and ev is not None:
            if ev >= tv:
                ends.append(ev)
                durations.append(ev - tv)
            else:
                n_reversed += 1
                ev = None
        elif ev is not None:
            ends.append(ev)
        pairs.append((a, b, tv, ev))

    if not pairs:
        raise SystemExit(f"read 0 usable contacts from {path.name}")

    # The window closes at the last END. See the docstring.
    t_lo = min(begins) if begins else 0.0
    t_hi = max(ends + begins) if (ends or begins) else 0.0
    have_time = bool(begins)

    unit = infer_time_unit(t_lo, t_hi) if have_time else dict(
        unit=None, per_hour=None, span_hours=None, why="no timestamps")
    # These files are documented as millisecond epochs, so the inference has a
    # known right answer here and disagreeing with it is worth printing rather
    # than silently preferring one of the two.
    span_h = unit["span_hours"]
    if have_time and unit["unit"] is None:
        span_h = (t_hi - t_lo) / MS_PER_HOUR
        print(f"  NOTE: {unit['why']}")
        print("        Falling back to the documented millisecond epoch for the "
              f"span ({span_h:.2f} h). Check this before quoting bin widths.")
    elif have_time and unit["unit"] != "ms":
        print(f"  WARNING: timestamps look like {unit['unit']}, not the "
              "milliseconds this deposit documents. One of the two is wrong.")

    n_bins, bin_h, notes = plan_bins(span_h, n_bins=n_bins, bin_hours=bin_hours)
    for n in notes:
        print(f"  NOTE: {n}")

    log: list[dict] = []
    n_straddle = 0
    for a, b, tv, ev in pairs:
        if not have_time or tv is None:
            tb = 0
        else:
            mid = tv if ev is None else (tv + ev) / 2.0
            tb = quantize(mid, t_lo, t_hi, n_bins)
            if ev is not None and quantize(tv, t_lo, t_hi, n_bins) != \
                    quantize(ev, t_lo, t_hi, n_bins):
                n_straddle += 1
        # undirected contact -> both orderings, so degree is contact count
        log.append({"sender": a, "recipient": b, "mtype": "report", "tbin": tb})
        log.append({"sender": b, "recipient": a, "mtype": "report", "tbin": tb})

    if durations and n_straddle:
        print(f"  NOTE: {n_straddle:,} of {len(pairs):,} contacts "
              f"({100 * n_straddle / len(pairs):.2f}%) cross a bin boundary, so "
              "which end of the interval you bin on changes their bin.")

    nodes = {m["sender"] for m in log} | {m["recipient"] for m in log}
    d_sorted = sorted(durations)
    meta = dict(
        source="Robinson lab bee-monitoring portal (beemonitoring.igb.illinois.edu)",
        citation="Gernat, T., et al. (2018). PNAS, 115(7), 1433-1438.",
        file=path.name,
        trial=(sorted(trials)[0] if len(trials) == 1 else (dict(trials) or None)),
        n_contacts=len(pairs),
        n_messages=len(log),
        n_individuals=len(nodes),
        n_timebins=n_bins if have_time else 1,
        directed=False,
        self_contacts_dropped=skipped_self,
        time_span_ms=[t_lo, t_hi] if have_time else None,
        span_hours=round(span_h, 2) if span_h else None,
        # What one bin IS. Without this, "24 bins" is a number nobody can turn
        # into a duration, and every across-bin claim is uninterpretable.
        bin_hours=round(bin_h, 3) if bin_h else None,
        bins_per_day=(round(24.0 / bin_h, 3) if bin_h else None),
        time_unit_inferred=unit["unit"],
        time_unit_reason=unit["why"],
        circadian_notes=notes or None,
        binned_on="midpoint of begin..end",
        contacts_crossing_bin_edge=n_straddle,
        window_closes_on="max(end)",
        rows_with_end_before_begin=n_reversed,
        median_duration_s=(round(d_sorted[len(d_sorted) // 2] / 1000.0, 2)
                           if d_sorted else None),
        p90_duration_s=(round(d_sorted[int(0.9 * (len(d_sorted) - 1))] / 1000.0, 2)
                        if d_sorted else None),
        # The max is the one that matters for binning: a contact comparable in
        # length to a bin is a contact whose bin assignment is close to arbitrary.
        max_duration_s=(round(d_sorted[-1] / 1000.0, 2) if d_sorted else None),
        interpretation=("Undirected contact log: no direction column exists, so every "
                        "contact is emitted both ways. Centralization measures how "
                        "unevenly contact concentrates; a recovered edge is a strong "
                        "tie, NOT a direction of influence. Durations are reported but "
                        "deliberately not used as edge weights."),
    )
    return log, meta


def load_all(raw_dir: Path, n_bins: int = 24, max_rows: int | None = None,
             bin_hours: float | None = None):
    files = trial_files(raw_dir)
    if not files:
        raise SystemExit(
            f"no trial files under {raw_dir}.\n"
            "  expected trial1.txt .. trial5.txt from the Illinois portal; run\n"
            "  python3 fetch_data.py --tier core first."
        )
    out = {}
    for p in files:
        out[p.stem] = load_one(p, n_bins=n_bins, max_rows=max_rows,
                               bin_hours=bin_hours)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True,
                    help="a subdirectory is written per trial, so all five stay separate")
    ap.add_argument("--trial", default=None, help="only this file stem, e.g. trial3")
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--bins", type=int, default=24,
                    help="number of equal time bins (a COUNT, not a width: over a "
                         "5-day trial 24 bins are 5 h each)")
    ap.add_argument("--bin-hours", type=float, default=None,
                    help="bin WIDTH in hours; overrides --bins. Use a divisor of "
                         "24 (1,2,3,4,6,8,12) so bins fold onto clock time and the "
                         "daily activity cycle can be averaged out")
    a = ap.parse_args()

    raw, out_root = Path(a.raw), Path(a.out)
    files = trial_files(raw)
    if a.trial:
        files = [f for f in files if f.stem == a.trial]
        if not files:
            raise SystemExit(f"no file with stem {a.trial!r} under {raw}")

    summary = {}
    for p in files:
        log, meta = load_one(p, n_bins=a.bins, max_rows=a.max_rows,
                             bin_hours=a.bin_hours)
        dest = out_root / p.stem
        write_log(log, meta, dest)
        summary[p.stem] = dict(individuals=meta["n_individuals"],
                               contacts=meta["n_contacts"],
                               span_hours=meta["span_hours"],
                               bin_hours=meta["bin_hours"])
        print(f"    -> {meta['n_individuals']} bees, {meta['n_contacts']:,} contacts, "
              f"{meta['span_hours']} h in {meta['n_timebins']} bins of "
              f"{meta['bin_hours']} h  ->  {dest / 'interaction_log.csv'}")

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "trials_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n  {len(summary)} trial(s) written under {out_root}")
    print("  These are independent colonies. Run the structure report on each and")
    print("  compare: a result that holds in one of five is not a result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
