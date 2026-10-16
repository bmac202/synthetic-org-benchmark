"""Gernat / Robinson trophallaxis events -> a directed interaction log.

Zenodo 5582780 (concept 10.5281/zenodo.5582779), CC-BY-NC-4.0, and the five
trial archives on beemonitoring.igb.illinois.edu.

Why this dataset matters more than its size suggests: it records DIRECTION.
`interactions.csv` carries a donor and a recipient for every food-sharing event,
so it is a directed communication log of exactly the shape our structure-recovery
instrument already consumes -- a list of {"sender", "recipient", "mtype"} records.

That makes it the sharpest available test of the central feasibility claim. The
instrument was written against synthetic organizations with a known reporting
structure. Here it meets a real biological communication trace it has never seen,
produced by a process with no designer and no reporting lines at all. Whatever
structure it recovers is structure the colony actually has.

Read the output the right way. Recovering a clean hierarchy would be a red flag,
not a success: bees have none. The interesting quantities are the centralization
score (expected LOW, near the flat-design end of our synthetic range) and whether
the emergent hubs are stable individuals or churn -- which is the biological
version of "does informal structure persist without formal authority".
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .common import (circadian_notes, find_files, infer_time_unit, normalize,
                     pick_column, pick_columns, plan_bins, quantize, stream_rows,
                     to_float)

BEE_CANDIDATES = {
    "trial": ["trial", "colony", "trial_id", "colony_id"],
    "id":    ["id", "bee", "bee_id", "tag", "tag_id"],
    "caste": ["caste", "class", "type", "role"],
}

# What counts as a queen. Matched against the normalized caste value, exactly --
# no substring test, because "queenless" and "queenright" are ordinary words in
# this literature and both contain "queen". If a deposit uses a token that is not
# here, the loader says which levels it saw and marks nobody, rather than
# deciding on its own what a caste value means.
QUEEN_TOKENS = {"queen", "q", "gyne", "queens"}


CANDIDATES = {
    "trial":     ["trial", "colony", "trial_id", "colony_id"],
    "id1":       ["id1", "bee1", "partner1", "partner_1", "donor", "from", "source"],
    "id2":       ["id2", "bee2", "partner2", "partner_2", "recipient", "to", "target"],
    "direction": ["direction", "dir", "donor_recipient"],
    "time":      ["timestamp", "time", "start", "interaction_start", "t"],
}


def read_castes(raw_dir: Path) -> tuple[dict[tuple[str, str], str], dict]:
    """Read `bees.csv` for caste, and say plainly when there is nothing to read.

    Caste is not a task -- it never varies within an individual, so scoring it as
    one makes division of labour maximal by construction, and that is settled
    elsewhere in the README. It is read for the opposite purpose: to mark the
    three queens so that any structural result can be recomputed without them.

    A queen in a trophallaxis network is fed continuously by her retinue. She is
    a hub by caste. If she is left in and unlabelled, "this colony has stable
    central individuals" may be a restatement of "this colony has a queen", and
    the deposit itself contained the information needed to tell the difference.
    """
    report: dict = dict(file=None, levels=None, n_bees=0, queen_token=None)
    files = [f for f in find_files(raw_dir, ["bees*.csv", "*bees*.csv"])]
    if not files:
        report["why"] = ("no bees.csv under this directory, so caste is unknown "
                         "and no individual can be marked")
        return {}, report

    path = files[0]
    head = next(iter(stream_rows(path, limit=1)), None)
    if head is None:
        report["why"] = f"{path.name} is empty"
        return {}, report
    resolved = pick_columns(list(head.keys()), BEE_CANDIDATES,
                            optional=("trial", "caste"))
    c_id = resolved["id"]
    c_tr, c_caste = resolved.get("trial"), resolved.get("caste")
    report["file"] = path.name
    if c_caste is None:
        report["why"] = (f"{path.name} has no caste column "
                         f"(header: {list(head.keys())})")
        return {}, report

    castes: dict[tuple[str, str], str] = {}
    levels = Counter()
    for row in stream_rows(path):
        bid = str(row[c_id]).strip()
        if not bid:
            continue
        tr = str(row[c_tr]).strip() if c_tr else ""
        val = str(row[c_caste]).strip()
        castes[(tr, bid)] = val
        levels[val] += 1
    report["n_bees"] = len(castes)
    report["levels"] = dict(levels)
    hits = sorted({v for v in levels if normalize(v) in QUEEN_TOKENS})
    report["queen_token"] = hits[0] if len(hits) == 1 else (hits or None)
    if not hits:
        # Refusing to guess is the point. A substring rule would match
        # "queenless"; a "smallest level wins" rule would invent a queen in any
        # unbalanced column. Both would produce a mark nobody chose.
        report["why"] = (
            f"none of the caste levels {sorted(levels)} is a recognised queen "
            f"token {sorted(QUEEN_TOKENS)}. Nobody has been marked. Add the real "
            f"token to QUEEN_TOKENS in loaders/gernat.py if one of these is it.")
    return castes, report


def load(raw_dir: Path, trial: str | None = None, max_rows: int | None = None,
         n_bins: int = 24, bin_hours: float | None = None):
    """Return (log, meta) where log is a list of {"sender","recipient","mtype","tbin"}.

    `tbin` is an integer time bin. `measure.py` ignores extra keys, so the log is
    still a drop-in for the existing instruments; the bin exists so hub stability
    can be measured over time -- whether the same individuals stay central, which
    is the question that distinguishes an emergent structure from a transient one.

    `n_bins` is a COUNT, not a width. An earlier version of this docstring said
    24 bins were "roughly hourly for a day-long trial", which is true only for a
    day-long trial and quietly false for every other length; a five-day record
    gets five-hour bins from the same flag. Pass `bin_hours` to fix the width
    instead, and read `meta["bin_hours"]` to find out what a bin actually was.
    """
    files = find_files(raw_dir, ["interactions*.csv", "*interaction*.csv", "*.csv"])
    files = [f for f in files if "bees" not in f.name.lower() and "trials" not in f.name.lower()]
    if not files:
        raise SystemExit(f"no interaction table found under {raw_dir}")
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    path = files[0]
    print(f"  reading {path.name}")

    head = next(iter(stream_rows(path, limit=1)), None)
    if head is None:
        raise SystemExit(f"{path} is empty")
    header = list(head.keys())

    # Resolved together. Two collisions are reachable here and both are severe.
    # A header naming its clock `trial_timestamp` binds BOTH `trial` and `time`
    # to it -- and `trial` is the colony, so every interaction would be filed
    # under a colony id that is really a timestamp, giving one colony per instant
    # and destroying colony identity without a single error. A header using
    # `partner_1`/`partner` style names can cross-match id1 and id2, which turns
    # every contact into a self-loop.
    resolved = pick_columns(header, CANDIDATES,
                            optional=("direction", "trial", "time"))
    c1, c2 = resolved["id1"], resolved["id2"]
    c_dir = resolved.get("direction")
    c_trial = resolved.get("trial")
    c_time = resolved.get("time")
    print(f"  columns -> id1={c1} id2={c2} direction={c_dir} trial={c_trial} time={c_time}")
    if c_dir is None:
        print("  NOTE: no direction column found; treating every event as symmetric")
        print("        (both orderings emitted). Centralization stays valid; the")
        print("        recovered 'reporting' edges become mutual and should be read")
        print("        as strong-tie edges, not as direction of flow.")

    log: list[dict] = []
    trials = Counter()
    times: list[float] = []
    times_by_trial: dict[str, list[float]] = defaultdict(list)
    dir_levels = Counter()
    n_undecodable = 0
    for row in stream_rows(path, limit=max_rows):
        tr = ""
        if c_trial:
            tr = str(row[c_trial]).strip()
            trials[tr] += 1
            if trial is not None and tr != str(trial):
                continue
        a, b = str(row[c1]).strip(), str(row[c2]).strip()
        if not a or not b or a == b:
            continue
        # Namespace the node key by trial. bees.csv in this deposit is keyed on
        # (trial, id), which is what you write when `id` alone is not a key. If
        # ids restart per trial and we pool them, bee 7 of trial 1 and bee 7 of
        # trial 2 become one node carrying both their edges -- and the bees that
        # come out most central are simply the ids that occur in the most trials.
        # Namespacing costs nothing when ids ARE globally unique, and prevents a
        # silent merge when they are not. Pass --trial to analyse one colony.
        if tr:
            a, b = f"{tr}:{a}", f"{tr}:{b}"
        tv = None
        if c_time:
            tv = to_float(row[c_time])
            if tv is not None:
                times.append(tv)
                times_by_trial[tr].append(tv)
        if c_dir:
            d = str(row[c_dir]).strip()
            dir_levels[d] += 1
            if d.lower() in {">", "1", "id1", "a", "forward"}:
                log.append({"sender": a, "recipient": b, "mtype": "report",
                            "_t": tv, "_tr": tr})
            elif d.lower() in {"<", "-1", "id2", "b", "backward"}:
                log.append({"sender": b, "recipient": a, "mtype": "report",
                            "_t": tv, "_tr": tr})
            else:                                   # unresolved -> symmetric
                n_undecodable += 1
                log.append({"sender": a, "recipient": b, "mtype": "report",
                            "_t": tv, "_tr": tr})
                log.append({"sender": b, "recipient": a, "mtype": "report",
                            "_t": tv, "_tr": tr})
        else:
            log.append({"sender": a, "recipient": b, "mtype": "report",
                        "_t": tv, "_tr": tr})
            log.append({"sender": b, "recipient": a, "mtype": "report",
                        "_t": tv, "_tr": tr})

    # An empty log is a failure, not a result, and it must not be written. Asked
    # for --trial q against a file whose trials are 2016-01/02/03, an earlier
    # version filtered every row away, wrote a valid-looking canonical
    # interaction_log.csv holding nothing, and exited 0. Downstream that file does
    # not read as "the run failed"; it reads as a colony in which no bee ever fed
    # another. Naming the trials that ARE present turns a silent write into a
    # one-line fix.
    if not log:
        if trial is not None and trials and str(trial) not in trials:
            raise SystemExit(
                f"--trial {trial!r} matches no row. The {len(trials)} trial(s) in "
                f"{path.name} are: " + ", ".join(f"{t!r} ({n:,} rows)"
                                                 for t, n in sorted(trials.items()))
                + "\nNothing was written.")
        raise SystemExit(
            f"no usable interactions found in {path.name}"
            + (f" for --trial {trial!r}" if trial is not None else "")
            + ". Nothing was written.")

    # A direction column we cannot decode is worse than no direction column, because
    # the fallback produces a symmetric log while the metadata still says directed.
    # Direction is the entire reason this deposit is worth using, so say so loudly
    # and record the truth in meta rather than the intention.
    decoded = bool(c_dir) and n_undecodable == 0
    if c_dir and n_undecodable:
        share = 100 * n_undecodable / max(1, sum(dir_levels.values()))
        print(f"  WARNING: {n_undecodable:,} rows ({share:.1f}%) carry a direction value")
        print(f"           this loader does not recognise: "
              f"{sorted(d for d in dir_levels if d.lower() not in {'>', '1', 'id1', 'a', 'forward', '<', '-1', 'id2', 'b', 'backward'})[:6]}")
        print("           Those events were emitted in BOTH directions, so the log is")
        print("           partly undirected. meta['directed'] is set False. Add the real")
        print("           tokens to loaders/gernat.py before reading anything as flow.")

    # Raw times -> integer bins, computed WITHIN trial. The timestamps here are
    # absolute, and trials ran at different times, so a single global min-to-max
    # binning gives each trial its own block of bins. "Do the same individuals
    # stay central across bins" then answers "do different colonies appear in
    # different bins", which is not a question anyone asked. Binning per trial
    # makes bin k mean "the k-th slice of this colony's own record" in every trial.
    unit = dict(unit=None, per_hour=None, span_hours=None, why="no timestamps found")
    span_by_trial_h: dict[str, float] = {}
    bins_by_trial: dict[str, int] = {}
    bin_h: float | None = None
    notes: list[str] = []

    if times:
        span = {tr: (min(ts), max(ts)) for tr, ts in times_by_trial.items()}

        # What unit are these timestamps in? Inferred PER TRIAL and then required
        # to agree. A single min-to-max across all trials is not a duration
        # anybody observed -- the trials ran on different real dates -- so using
        # it to sanity-check a unit would test the gap between experiments rather
        # than the length of one. Disagreement between trials means the column is
        # not what we think it is, and that is reported, not averaged over.
        per = {tr: infer_time_unit(lo, hi) for tr, (lo, hi) in span.items()}
        units = {u["unit"] for u in per.values()}
        if len(units) == 1 and None not in units:
            one = next(iter(per.values()))
            unit = dict(unit=one["unit"], per_hour=one["per_hour"], span_hours=None,
                        why=f"all {len(per)} trial(s) agree: {one['why']}")
            span_by_trial_h = {tr: (hi - lo) / one["per_hour"]
                               for tr, (lo, hi) in span.items()}
        else:
            detail = "; ".join(f"{tr or '(single)'}: {u['why']}"
                               for tr, u in sorted(per.items()))
            unit = dict(unit=None, per_hour=None, span_hours=None,
                        why=f"trials do not agree on a time unit -- {detail}")
            print(f"  NOTE: {unit['why']}")
            print("        Bins are still computed, but as equal fractions of each")
            print("        trial's record. They have no width in hours.")

        if bin_hours is not None:
            if not span_by_trial_h:
                raise SystemExit(
                    "--bin-hours needs the timestamps to be identifiable as clock "
                    "time, and they are not (see the note above). Use --bins.")
            bin_h = float(bin_hours)
            for tr, sh in span_by_trial_h.items():
                n_tr, _, nn = plan_bins(sh, bin_hours=bin_h)
                bins_by_trial[tr] = n_tr
                notes.extend(nn)
            # Bins are the same WIDTH everywhere, so trials of different lengths
            # get different counts. That is the trade being made: bin k now means
            # the same duration in every trial, which is what makes bin k
            # comparable across them.
            n_bins = max(bins_by_trial.values())
        else:
            bins_by_trial = {tr: n_bins for tr in span}
            widths = sorted(sh / n_bins for sh in span_by_trial_h.values())
            if widths:
                bin_h = widths[len(widths) // 2]
                if len(widths) > 1 and widths[-1] > 1.05 * widths[0]:
                    # A fixed COUNT over records of different lengths gives bins
                    # of different widths. Bin 3 is then three hours in one trial
                    # and five in another, and "the same individuals are central
                    # in bin 3 of every trial" compares unlike things.
                    print(f"  WARNING: --bins {n_bins} gives bins of "
                          f"{widths[0]:.2f} h to {widths[-1]:.2f} h across trials, "
                          "because the trials are not the same length. Bin k is a "
                          "different duration in each. Pass --bin-hours to fix the "
                          "width and let the count vary instead.")
                    bin_h = None
                for nn in (circadian_notes(sh, sh / n_bins)
                           for sh in span_by_trial_h.values()):
                    notes.extend(nn)

        for n in dict.fromkeys(notes):          # dedupe, keep order
            print(f"  NOTE: {n}")

        # Hoisted out of the loop deliberately. Written inline as
        # `span.get(tr, (min(times), max(times)))` the default is built on EVERY
        # iteration, because Python evaluates a `.get` default eagerly whether or
        # not the key is present -- so an O(n) scan runs once per message and the
        # loop is quietly O(n^2). On the fixtures here, a few thousand rows, that
        # is invisible. On the real 11 MB interactions table it is hours, at 100%
        # CPU, with flat memory and no output: a bug that looks exactly like a big
        # file. The fallback itself is nearly dead code -- it only fires for a
        # message whose trial is absent from `span` -- which is why the cost sat
        # in a branch that almost never runs.
        global_span = (min(times), max(times))
        for m in log:
            tv, tr = m.pop("_t", None), m.pop("_tr", "")
            lo, hi = span.get(tr, global_span)
            nb = bins_by_trial.get(tr, n_bins)
            m["tbin"] = quantize(tv, lo, hi, nb) if tv is not None else 0
    else:
        for m in log:
            m.pop("_t", None)
            m.pop("_tr", None)
            m["tbin"] = 0

    nodes = {m["sender"] for m in log} | {m["recipient"] for m in log}

    # Caste, joined on the SAME node key the log uses. Building the key any other
    # way is how a mark lands on nobody while every downstream number still
    # computes -- which reads as "the queens made no difference" and is instead
    # "the queens were never found".
    castes, caste_report = read_castes(raw_dir)
    queens: dict[str, str] = {}
    for (tr, bid), val in castes.items():
        if normalize(val) not in QUEEN_TOKENS:
            continue
        if trial is not None and tr and tr != str(trial):
            continue
        queens[f"{tr}:{bid}" if (c_trial and tr) else bid] = "queen"
    matched = sorted(set(queens) & nodes)
    if queens and not matched:
        print(f"  WARNING: {len(queens)} queen(s) named in {caste_report['file']}, "
              "and none of them matches a node in the interaction log.")
        print(f"           log keys look like {sorted(nodes)[:2]}, "
              f"queen keys like {sorted(queens)[:2]}.")
        print("           The id spaces disagree. Nothing below may be read as")
        print("           'the queens made no difference'.")
    elif matched:
        print(f"  {len(matched)} queen(s) marked: {matched}. They are NOT dropped; "
              "netstats reports the structure with and without them.")
    elif caste_report.get("why"):
        print(f"  NOTE: {caste_report['why']}")

    meta = dict(
        source="Gernat et al., Zenodo 10.5281/zenodo.5582779, CC-BY-NC-4.0",
        citation="Gernat, T., Jagla, T., Jones, B. M., Middendorf, M., & Robinson, G. E. (2023). Scientific Reports, 13, 1541.",
        file=path.name,
        trial=trial,
        trials_available=dict(trials) if trials else None,
        n_messages=len(log),
        n_individuals=len(nodes),
        n_timebins=n_bins if times else 1,
        directed=decoded,
        direction_levels=dict(dir_levels) or None,
        n_undecodable_direction=n_undecodable,
        node_key="trial:id" if c_trial else "id",
        # What one bin IS. None means the timestamps could not be identified as
        # clock time, or the bins are different widths in different trials -- in
        # both cases a bin has no single width in hours and saying so is the
        # only honest answer.
        bin_hours=round(bin_h, 3) if bin_h else None,
        bins_per_day=(round(24.0 / bin_h, 3) if bin_h else None),
        bins_by_trial=dict(bins_by_trial) or None,
        span_hours_by_trial={tr: round(h, 2) for tr, h in span_by_trial_h.items()} or None,
        time_unit_inferred=unit["unit"],
        time_unit_reason=unit["why"],
        # Pass this to netstats.structure_report(special=...). Caste is NOT a
        # task -- it never varies within an individual -- so it appears here only
        # as a mark on individuals who are hubs by biology rather than by
        # organisation.
        special_nodes=queens or None,
        n_queens_marked=len(matched),
        caste_source=caste_report,
        circadian_notes=list(dict.fromkeys(notes)) or None,
        binned_within_trial=bool(times_by_trial) and len(times_by_trial) > 1,
        time_span=[min(times), max(times)] if times else None,
        time_span_by_trial={tr: [min(ts), max(ts)]
                            for tr, ts in times_by_trial.items()} or None,
        interpretation=("Trophallaxis is food sharing, not reporting. 'mtype' is set to "
                        "'report' only so the existing instrument accepts the log unchanged. "
                        "A LOW centralization score is the biologically expected result."),
    )
    return log, meta


def write_log(log: list[dict], meta: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "interaction_log.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sender", "recipient", "mtype", "tbin"])
        for m in log:
            w.writerow([m["sender"], m["recipient"], m["mtype"], m.get("tbin", 0)])
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    return path


def read_log(out_dir: Path) -> tuple[list[dict], dict]:
    log = [{"sender": r["sender"], "recipient": r["recipient"], "mtype": r["mtype"],
            "tbin": int(r.get("tbin") or 0)}
           for r in stream_rows(out_dir / "interaction_log.csv")]
    mp = out_dir / "meta.json"
    return log, (json.loads(mp.read_text()) if mp.exists() else {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--trial", default=None, help="restrict to one colony/trial")
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--bins", type=int, default=24,
                    help="number of equal time bins (a COUNT, not a width)")
    ap.add_argument("--bin-hours", type=float, default=None,
                    help="bin WIDTH in hours; overrides --bins. Use a divisor of "
                         "24 (1,2,3,4,6,8,12) so bins fold onto clock time")
    a = ap.parse_args()

    log, meta = load(Path(a.raw), a.trial, a.max_rows, a.bins, a.bin_hours)
    write_log(log, meta, Path(a.out))
    print(f"\n  individuals : {meta['n_individuals']}")
    print(f"  messages    : {meta['n_messages']}  (directed={meta['directed']})")
    print(f"  bins        : {meta['n_timebins']} of {meta['bin_hours']} h "
          f"(time unit: {meta['time_unit_inferred']})")
    if meta.get("trials_available"):
        print(f"  trials      : {meta['trials_available']}")
    print(f"\n  written: {Path(a.out) / 'interaction_log.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
