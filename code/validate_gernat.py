"""Check our reading of the Gernat trophallaxis deposit before anything runs on it.

WHY THIS FILE EXISTS
--------------------
Same reason as `validate_dornhaus.py`, but the failure modes are different and,
here, worse. The Dornhaus deposit is one table of 2,346 rows; a misreading shows
up as a number that disagrees with the paper. This deposit is three tables that
have to be joined --

    interactions.csv   trial, timestamp, id1, id2, direction      367,614 rows
    bees.csv           trial, id, caste, time_of_death              2,777 rows
    trials.csv         trial, begin, end                                3 rows

-- and a join is the place where two files that are each individually correct
produce something that is not. None of the five checks below can fail loudly on
their own. Each of them, if wrong, yields a complete run with plausible numbers.

  1.  **Are bee ids unique across trials, or reused?** `bees.csv` is keyed on
      (trial, id), which is what you write when `id` alone is not a key. If ids
      restart in each trial and the loader pools them, bee 7 of trial 1 and bee 7
      of trial 2 become one node with both their edges. Centralization is then
      computed over chimeras, and the most "central" individuals are simply the
      ids that occur in the most trials. This is the same question `UAntID`
      raised for Dornhaus, where the answer happened to be reassuring.

  2.  **Do the trials share a clock?** If the timestamp is absolute and the
      trials ran in different weeks, a single min-to-max binning puts each trial
      in its own corner of the axis. "Hub stability across time bins" then
      compares colonies, not moments, and the answer looks like total turnover.
      `trials.csv` carries begin and end per trial precisely so this can be done
      per trial instead.

  3.  **What are the actual values in `direction`?** The loader decodes a set of
      conventions (`>`, `1`, `id1`, `forward`, ...) and falls back to emitting
      the event symmetrically when it does not recognise one. If the real file
      uses a convention outside that set, EVERY event takes the fallback, the
      direction information is silently discarded, and the run still reports
      `directed=True`. Direction is the entire reason this deposit is worth
      using, so a fallback that quietly disables it is the costliest bug here.

  4.  **Does the interaction record respect `time_of_death`?** This is a real
      cross-file test rather than a plausibility check: no bee should appear in
      an interaction after it died. If that holds, the two files share a clock
      and an id space, and both of the above are confirmed at once. If it fails,
      the join is wrong somewhere and we do not yet know where.

  5.  **Is `time_of_death` a death, or the end of the observation window?** I
      wrote the paragraph that used to sit here before running the script, and it
      said that because this deposit records death, absence decomposes into died
      / left / not seen, and that this makes it the better dataset for anything
      about attrition. Then the run reported a death time for 2,777 of 2,777
      bees. Colonies do not lose every member, so a universally-present death
      time is far more likely to be right-censoring: the trial ended, and the
      last row written for each animal is the closing stamp. The column looks
      identical either way and licenses completely different claims, so it is now
      a check rather than a premise -- the death times are compared against each
      trial's declared `end`, and a pile-up at the boundary is censoring.

      Note what this does to check 4. Under censoring, "no bee interacts after
      its death time" is close to an arithmetic identity: nothing inside the
      record can fall after the end of the record. It stops being evidence that
      the death times are real, and the PASS line says so.

    python3 validate_gernat.py --raw "/Volumes/<drive>/BeeOrg/data/raw/gernat_trophallaxis"

HOW TO USE THE RESULT
---------------------
PASS   the reading is confirmed by the data itself.
CHECK  it is not. Read the note; do not run the loader on that assumption.
?      reported for your eye; no target to compare against.
"""
from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from pathlib import Path

from loaders.common import find_files, is_missing, normalize, stream_rows, to_float

CITATION = ("Gernat, T., Jagla, T., Jones, B. M., Middendorf, M., & Robinson, G. E. "
            "(2023). Scientific Reports, 13, 1541. Data: Zenodo 10.5281/zenodo.5582779")

# What the loader in loaders/gernat.py will recognise. Kept here deliberately as
# a copy rather than imported: the point of the check is to notice when the two
# drift apart, and importing the live set would make the check agree with the
# loader by construction even when both are wrong.
KNOWN_DIRECTION_TOKENS = {">", "1", "id1", "a", "forward",
                          "<", "-1", "id2", "b", "backward"}

RESULTS: list[tuple[str, str, str]] = []


def assertion(label: str, ok: bool, detail: str = "", ok_detail: str = "") -> None:
    """Record a check. `detail` explains the failure; `ok_detail` the success.

    The first version of this took one `detail` and printed it either way, which
    produced lines like

        [PASS ] every event falls inside its trial's declared window
                 [] have events outside the begin/end in trials.csv, so either the
                 two files use different clocks or the trial labels do not line up

    -- a PASS whose body is a warning about a failure that did not happen, and in
    one case an empty list rendered as `[]`. Somebody reading a verdict block full
    of those learns that the prose under a result is noise, and then does not read
    the prose under the CHECK either. A check that trains people to skip its own
    output has cost more than it bought, so the two cases now carry separate text.
    """
    RESULTS.append(("PASS", label, ok_detail) if ok else ("CHECK", label, detail))


def note(label: str, detail: str = "") -> None:
    RESULTS.append(("?", label, detail))


def _sortkey(v: str):
    """Order ids numerically where they are numbers, lexically otherwise.

    The canonical-ordering test asks whether id1 always sorts before id2. On string
    ids that question is well posed; on numeric ids stored as text, plain string
    comparison puts '10' before '9' and the test reports a scatter of violations
    that are artefacts of the comparison rather than facts about the file.
    """
    f = to_float(v)
    return (0, f, "") if f is not None else (1, 0.0, v)


def table(root: Path, *names: str) -> Path | None:
    """Find one of the deposit's tables by name, case-insensitively."""
    wanted = {normalize(n) for n in names}
    for f in find_files(root, ["*.csv", "*.tsv", "*.txt"]):
        if normalize(f.stem) in wanted:
            return f
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="data/raw/gernat_trophallaxis")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="cap interaction rows read (for a quick look; omit for the real answer)")
    a = ap.parse_args()
    root = Path(a.raw).expanduser()

    inter = table(root, "interactions")
    bees = table(root, "bees")
    trials_f = table(root, "trials")

    print(f"source : {CITATION}\n")
    for label, p in (("interactions", inter), ("bees", bees), ("trials", trials_f)):
        print(f"  {label:14} {p.relative_to(root) if p else '-- NOT FOUND --'}")
    if inter is None:
        raise SystemExit(f"\nno interactions table under {root}")

    # ------------------------------------------------------------- trials.csv
    trial_window: dict[str, tuple[float, float]] = {}
    if trials_f:
        for row in stream_rows(trials_f):
            keys = {normalize(k): k for k in row}
            tr = str(row[keys["trial"]]).strip()
            b, e = to_float(row.get(keys.get("begin", ""), "")), \
                to_float(row.get(keys.get("end", ""), ""))
            if b is not None and e is not None:
                trial_window[tr] = (b, e)
        print(f"\nTRIAL WINDOWS  (from {trials_f.name})")
        print("-" * 92)
        for tr, (b, e) in sorted(trial_window.items()):
            print(f"  {tr:10}  begin {b:>16.1f}   end {e:>16.1f}   span {e - b:>14.1f}")

    # ----------------------------------------------------------------- bees.csv
    bee_caste: dict[tuple[str, str], set[str]] = defaultdict(set)
    death: dict[tuple[str, str], float] = {}
    ids_per_trial: dict[str, set[str]] = defaultdict(set)
    caste_levels = Counter()
    n_bee_rows = 0
    censored: bool | None = None      # None = not testable (no trials.csv)
    # Death times that fall strictly inside the trial window. These are the only
    # rows in the column that could be an event rather than a censoring stamp, and
    # they are the only rows the corroboration check below has anything to say about.
    observed_death: dict[tuple[str, str], float] = {}
    if bees:
        for row in stream_rows(bees):
            keys = {normalize(k): k for k in row}
            n_bee_rows += 1
            tr = str(row[keys["trial"]]).strip()
            bid = str(row[keys["id"]]).strip()
            ids_per_trial[tr].add(bid)
            if "caste" in keys:
                c = str(row[keys["caste"]]).strip()
                caste_levels[c] += 1
                if not is_missing(c):
                    bee_caste[(tr, bid)].add(c)
            if "timeofdeath" in keys:
                d = to_float(row[keys["timeofdeath"]])
                if d is not None:
                    death[(tr, bid)] = d

        print(f"\nBEES  ({n_bee_rows:,} rows)")
        print("-" * 92)
        for tr in sorted(ids_per_trial):
            print(f"  {tr:10}  {len(ids_per_trial[tr]):>5} individuals")
        if caste_levels:
            print("\n  caste levels:")
            for c, n in caste_levels.most_common():
                flag = "  <- missing, not a level" if is_missing(c) else ""
                print(f"    {c!r:20} {n:>6} rows{flag}")

        # 1. THE ID QUESTION. If ids are reused across trials, the node key must
        #    be (trial, id) and pooling is a silent merge of different animals.
        if len(ids_per_trial) > 1:
            per = list(ids_per_trial.values())
            # Count each id's trials and take those with two or more. The first
            # version of this line was `set.intersection(*per)`, which is the ids
            # present in EVERY trial -- a strictly smaller set than the ids present
            # in more than one, and on the real deposit smaller by a factor of five:
            # it reported 179 where the true figure is 891 of 1,707, i.e. 52% of the
            # id space rather than 10%. The label said "occur in more than one trial"
            # throughout, so the number under it was answering a different question
            # from the one it was captioned with. The verdict was right either way,
            # which is precisely why nothing downstream would have caught it.
            trials_per_id = Counter(bid for s in per for bid in s)
            shared = {bid for bid, k in trials_per_id.items() if k >= 2}
            union = set(trials_per_id)
            in_all = set.intersection(*per)
            assertion(
                "bee id is unique across trials (safe to pool as one node key)",
                not shared,
                f"{len(shared):,} of {len(union):,} ids "
                f"({100 * len(shared) / max(1, len(union)):.0f}%) occur in more than "
                f"one trial; {len(in_all):,} occur in all {len(per)}. bees.csv is keyed "
                f"on (trial, id), so a shared id is almost certainly two different bees. "
                f"Every node key must therefore be 'trial:id' and no analysis may pool "
                f"individuals across trials -- otherwise the most central bees are just "
                f"the ids that recur. loaders/gernat.py namespaces by trial for this "
                f"reason; this CHECK confirms the namespacing is load-bearing, not "
                f"precautionary",
                f"no id appears in more than one of the {len(per)} trials, across "
                f"{len(union):,} ids. Pooling individuals across trials is safe on id "
                f"grounds (it may still be wrong on clock grounds -- see below)")

        # A caste that never varies is a static attribute, exactly like Dornhaus's
        # ClustDesc, and carries the same degeneracy risk if used as a task.
        varying = sum(1 for v in bee_caste.values() if len(v) > 1)
        note("caste is a static per-individual attribute" if not varying
             else "caste varies within an individual",
             f"{varying} of {len(bee_caste):,} bees carry more than one caste value. "
             f"If zero, caste is an attribute and NOT a time-varying task: using it as "
             f"one makes division-of-labour maximal by construction and flexibility "
             f"undefined, which is the failure run_real_bench.py already guards")

        # 5. THE CENSORING QUESTION. This check exists because of a claim I made
        #    before running it: that `time_of_death` decomposes absence into died /
        #    left / not seen, and therefore makes this the better deposit for
        #    anything about attrition. That claim survives only if the field records
        #    OBSERVED death. A death time present for every single bee is far more
        #    likely to be right-censoring -- the trial ended, the observation window
        #    closed, and the last row written for each animal is the closing time
        #    rather than a death. The two are indistinguishable from the column
        #    alone and completely different in what they license: observed death
        #    supports a survival analysis, censoring at trial end supports nothing
        #    beyond "the trial ended". trials.csv is what separates them, so the
        #    test is the death times against each trial's declared end.
        n_bees = sum(len(v) for v in ids_per_trial.values())
        if death:
            note("bees carrying a time_of_death value",
                 f"{len(death):,} of {n_bees:,} "
                 f"({100 * len(death) / max(1, n_bees):.1f}%). A value present for "
                 f"essentially everyone is a reason for suspicion rather than "
                 f"confidence: colonies do not lose every member, so a universal "
                 f"death time is more likely an end-of-observation stamp. The next "
                 f"check is what tells the two apart")

        if death and trial_window:
            # Three buckets, not two. The first version lumped "died after the
            # declared end" in with "died at it", on the reasoning that both are
            # censoring. The real file then reported a MEDIAN gap of -1.0 s, which
            # says the typical value is not near the end but one second past it --
            # a sentinel meaning "still alive when we stopped looking", not a
            # measurement at all. A bucket that hides the sign of the difference
            # hides exactly that, so the sign now gets its own line.
            after_end = 0     # death LATER than the declared end: impossible as an observation
            at_end = 0        # within a minute before the end
            before = 0        # comfortably inside the window: a candidate real death
            unmatched = 0     # bee in a trial trials.csv does not describe
            latest_gap: list[float] = []
            after_gaps = Counter()
            for (tr, bid), d in death.items():
                win = trial_window.get(tr)
                if win is None:
                    unmatched += 1
                    continue
                gap = win[1] - d          # seconds from death to declared end
                latest_gap.append(gap)
                if gap < 0:
                    after_end += 1
                    after_gaps[gap] += 1
                elif gap <= 60:
                    at_end += 1
                else:
                    before += 1
                    observed_death[(tr, bid)] = d
            matched = after_end + at_end + before
            if matched:
                latest_gap.sort()
                med = latest_gap[len(latest_gap) // 2]
                share = (after_end + at_end) / matched
                censored = share >= 0.25
                print(f"\n  time_of_death vs trial end  ({matched:,} bees matched to a "
                      f"trials.csv window)")
                print("-" * 92)
                print(f"    LATER than the declared end    : {after_end:>6,}  "
                      f"({100 * after_end / matched:.1f}%)  <- cannot be an observed death")
                print(f"    within 60s before the end      : {at_end:>6,}  "
                      f"({100 * at_end / matched:.1f}%)")
                print(f"    earlier than that              : {before:>6,}  "
                      f"({100 * before / matched:.1f}%)  <- candidate real deaths")
                print(f"    median (end - death)           : {med:>10.1f} s "
                      f"= {med / 3600:.1f} h")
                if after_gaps:
                    common = ", ".join(f"{-g:+.0f}s x{n:,}" for g, n in
                                       after_gaps.most_common(3))
                    print(f"    commonest overshoot values     : {common}")
                # If every overshoot is the SAME number, the sentinel is a literal
                # constant and the censoring indicator is exactly recoverable --
                # `time_of_death == end + k` iff censored, with no tolerance and no
                # judgement call. That is worth stating separately from the CHECK
                # above, because it turns "this column is 80% censoring" (a warning)
                # into "this column is a survival pair we can decode exactly" (a
                # usable fact). A scatter of different overshoots would mean the
                # opposite: no rule, and the whole column suspect.
                if len(after_gaps) == 1 and at_end == 0:
                    k = -next(iter(after_gaps))
                    note("the censoring stamp is a single constant, so the indicator "
                         "is exact",
                         f"every one of the {after_end:,} overshooting values is "
                         f"exactly end + {k:.0f}s, and nothing falls in the minute "
                         f"before the end. So censored == (time_of_death == "
                         f"trial_end + {k:.0f}) is a biconditional, not a threshold: "
                         f"the survival pair (time, censored) can be reconstructed "
                         f"from this deposit with no tolerance and no judgement call")
                elif after_gaps:
                    note("the overshoot takes several different values",
                         f"{len(after_gaps):,} distinct amounts by which a recorded "
                         f"death exceeds the end of observation. A single constant "
                         f"would be a decodable sentinel; a scatter is not, and no "
                         f"rule separates censoring from measurement error here")
                if unmatched:
                    print(f"    no matching trial window       : {unmatched:>6,}")
                # An absolute-difference threshold would repeat the ActInact mistake,
                # so the test is on the SHARE piling up at the boundary. A quarter is
                # already far more than any plausible synchronised mortality.
                assertion(
                    "time_of_death is observed death, not censoring at trial end",
                    share < 0.25,
                    f"{100 * share:.1f}% of bees carry a 'death' at or after their "
                    f"trial's declared end, {100 * after_end / max(1, after_end + at_end):.1f}% "
                    f"of those strictly after it. Bees do not die in synchrony with the "
                    f"experimenter's clock, and none can die after observation stopped, "
                    f"so for those individuals the column is a censoring stamp: they "
                    f"were alive when the trial ended. This is a survival table with "
                    f"the censoring indicator left implicit, which is a perfectly "
                    f"ordinary layout -- but it must be read as (time, censored) and "
                    f"not as a time of death. The {before:,} bees with an earlier value "
                    f"are the candidate real events, and the next check tests whether "
                    f"the interaction record corroborates them",
                    f"only {100 * share:.1f}% of death times sit at or past the trial "
                    f"boundary, so the column is recording deaths the observers saw "
                    f"rather than the end of observation")

    # --------------------------------------------------------- interactions.csv
    head = next(iter(stream_rows(inter, limit=1)), None)
    if head is None:
        raise SystemExit(f"{inter} is empty")
    keys = {normalize(k): k for k in head}
    print(f"\nINTERACTIONS  header {list(head.keys())}")
    print("-" * 92)
    need = ["trial", "id1", "id2"]
    missing = [n for n in need if n not in keys]
    if missing:
        print(f"!! expected columns {missing} are absent. This is not the file this "
              f"script was written for. Stop and look.")
        return 1

    k_tr, k1, k2 = keys["trial"], keys["id1"], keys["id2"]
    k_dir = keys.get("direction")
    k_time = keys.get("timestamp") or keys.get("time")

    dir_levels = Counter()
    per_trial_time: dict[str, list[float]] = defaultdict(list)
    seen_ids: dict[str, set[str]] = defaultdict(set)
    n_rows = self_loops = 0
    after_death = 0
    death_examples: list[str] = []
    edge_seen: set[tuple] = set()
    duplicates = 0
    ordered_pairs = 0        # rows where id1 sorts before id2
    last_seen: dict[tuple[str, str], float] = {}

    for row in stream_rows(inter, limit=a.max_rows):
        n_rows += 1
        tr = str(row[k_tr]).strip()
        x, y = str(row[k1]).strip(), str(row[k2]).strip()
        if x == y:
            self_loops += 1
        if _sortkey(x) <= _sortkey(y):
            ordered_pairs += 1
        seen_ids[tr].add(x)
        seen_ids[tr].add(y)
        if k_dir:
            dir_levels[str(row[k_dir]).strip()] += 1
        tv = to_float(row[k_time]) if k_time else None
        if tv is not None:
            per_trial_time[tr].append(tv)
            for bid in (x, y):
                if tv > last_seen.get((tr, bid), float("-inf")):
                    last_seen[(tr, bid)] = tv
                d = death.get((tr, bid))
                if d is not None and tv > d:
                    after_death += 1
                    if len(death_examples) < 3:
                        death_examples.append(f"{tr}/{bid} at {tv:.0f} vs death {d:.0f}")
        key = (tr, x, y, row[k_time] if k_time else "")
        if key in edge_seen:
            duplicates += 1
        else:
            edge_seen.add(key)

    print(f"  rows read     : {n_rows:,}"
          + ("  (CAPPED by --max-rows; every count below is partial)" if a.max_rows else ""))
    print(f"  self-loops    : {self_loops:,}")
    print(f"  exact dupes   : {duplicates:,}  (same trial, pair, timestamp)")

    # 3. THE DIRECTION QUESTION.
    if k_dir:
        print("\n  direction levels:")
        for d, n in dir_levels.most_common():
            known = "recognised" if d.lower() in KNOWN_DIRECTION_TOKENS else \
                "NOT RECOGNISED -> would be emitted symmetrically"
            print(f"    {d!r:20} {n:>8,} rows   {known}")
        unknown = sum(n for d, n in dir_levels.items()
                      if d.lower() not in KNOWN_DIRECTION_TOKENS)
        assertion(
            "every direction value is one the loader can decode",
            unknown == 0,
            f"{unknown:,} of {sum(dir_levels.values()):,} rows carry a direction token "
            f"the loader does not recognise, and its fallback emits those events in BOTH "
            f"directions. That silently converts a directed food-flow log into an "
            f"undirected one while the run still reports directed=True. Direction is the "
            f"whole reason this deposit is worth using -- add the real tokens to "
            f"loaders/gernat.py before running anything",
            f"all {sum(dir_levels.values()):,} rows use one of "
            f"{sorted(dir_levels)}, every one of which the loader decodes. The log it "
            f"produces is genuinely directed and meta['directed']=True is honest")
    else:
        note("no direction column found", "the deposit's value is its direction; check the file")

    # Is (id1, id2) a sorted key or a meaningful order? This decides what the
    # direction column is doing. If id1 sorts before id2 in essentially every row,
    # the pair columns are a canonicalised key -- they carry no direction at all,
    # and `direction` is the ONLY thing distinguishing donor from recipient. Drop
    # or mis-decode it and the log is undirected with no fallback. If instead the
    # ordering is mixed, the pair order may already encode the event and direction
    # may be a redundant re-statement, in which case the two can be cross-checked.
    share_ordered = ordered_pairs / max(1, n_rows)
    if share_ordered > 0.99 or share_ordered < 0.01:
        note("(id1, id2) is a canonicalised pair, not an ordered one",
             f"id1 sorts before id2 in {100 * share_ordered:.1f}% of rows. The column "
             f"order therefore encodes nothing about who fed whom, and `direction` is "
             f"the single point of failure for every directed claim from this deposit")
    else:
        note("(id1, id2) ordering is mixed",
             f"id1 sorts before id2 in {100 * share_ordered:.1f}% of rows, so the pair "
             f"order is not a canonical key. It may itself encode the event, which "
             f"would make `direction` checkable against it rather than trusted alone")

    if k_dir and len(dir_levels) == 2:
        (_, hi), (_, lo) = dir_levels.most_common()
        skew = hi / max(1, hi + lo)
        note("direction is not balanced 50/50",
             f"the commoner token takes {100 * skew:.1f}% of rows. With a "
             f"canonicalised pair key this is a real asymmetry in the data-collection "
             f"or detection process, not a property of the colony -- it should not be "
             f"read as 'food flows one way'. Worth carrying into any claim about "
             f"in- versus out-degree")

    # 2. THE CLOCK QUESTION.
    if per_trial_time:
        print("\n  timestamp range per trial:")
        spans = {}
        for tr in sorted(per_trial_time):
            ts = per_trial_time[tr]
            spans[tr] = (min(ts), max(ts))
            win = trial_window.get(tr)
            fit = ""
            if win:
                inside = win[0] <= min(ts) and max(ts) <= win[1]
                fit = "  within trials.csv window" if inside else \
                      "  <- OUTSIDE the window trials.csv gives"
            print(f"    {tr:10}  {min(ts):>16.1f} .. {max(ts):>16.1f}  "
                  f"({len(ts):>8,} events){fit}")

        overlapping = False
        ordered = sorted(spans.values())
        for (lo1, hi1), (lo2, _hi2) in zip(ordered, ordered[1:]):
            if lo2 <= hi1:
                overlapping = True
        assertion(
            "the trials share one clock (a single global time binning is meaningful)",
            overlapping,
            "the trials' timestamp ranges do not overlap, so the timestamp is absolute "
            "rather than time-since-start. A single min-to-max binning then gives each "
            "trial its own block of bins, and 'the same individuals stay central across "
            "bins' becomes 'different colonies appear in different bins'. Bins must be "
            "computed WITHIN trial, against that trial's own begin/end",
            "the trials' timestamp ranges overlap, so the clock is shared and a single "
            "global binning puts the same moment in the same bin for every trial")

        if trial_window:
            bad = [tr for tr, (lo, hi) in spans.items()
                   if tr in trial_window
                   and not (trial_window[tr][0] <= lo and hi <= trial_window[tr][1])]
            checked = [tr for tr in spans if tr in trial_window]
            assertion("every event falls inside its trial's declared window",
                      not bad,
                      f"{', '.join(bad)} ha{'s' if len(bad) == 1 else 've'} events "
                      f"outside the begin/end in trials.csv, so either the two files "
                      f"use different clocks or the trial labels do not line up. "
                      f"Either way the join is not yet safe",
                      f"checked all {len(checked)} trials that trials.csv describes. "
                      f"interactions.csv and trials.csv agree on both the clock and "
                      f"the trial labels")

    # 4. THE CROSS-FILE TEST.
    if death and k_time:
        assertion(
            "no bee interacts after its recorded time_of_death",
            after_death == 0,
            f"{after_death:,} interaction rows involve a bee later than its death time"
            + (f" (e.g. {'; '.join(death_examples)})" if death_examples else "")
            + ". Passing this is strong evidence that bees.csv and interactions.csv "
              "share both a clock and an id space, which is what makes the join safe. "
              "Failing it means one of those is wrong and the join must not be used",
            ("bees.csv and interactions.csv agree on both a clock and an id space, so "
             "the join is safe."
             + (" But read this result narrowly: the censoring check above says these "
                "are end-of-observation times, and no event inside the record can fall "
                "after the end of the record. The test is close to vacuous here and is "
                "NOT evidence that the death times are real."
                if censored else
                " Because the death times are not concentrated at the trial boundary, "
                "this is a substantive test rather than an arithmetic identity.")))

    # 6. DO THE NON-CENSORED DEATH TIMES CORROBORATE? The check above is close to
    #    vacuous for a bee whose "death" is the end of the record. It is not vacuous
    #    for the ones whose death falls inside the window: those individuals should
    #    also STOP APPEARING at roughly that moment. If a bee's last interaction is
    #    days before its recorded death, the death time is not tracking the record
    #    and the subset cannot be used as observed events either -- which would take
    #    the deposit from "survival table with implicit censoring" (usable) to
    #    "column of unknown provenance" (not).
    if observed_death and k_time:
        # The tolerance problem, again. "Last seen within an hour of the recorded
        # death" sounds like a reasonable bar until you notice that an hour is 0.8%
        # of a five-day trial and 36% of the ten-thousand-second self-test fixture,
        # so the same constant means two different things in the two places it runs.
        # That is the ActInact mistake in a new costume. The scale therefore comes
        # from the data: death times are shuffled AMONG the bees of the same trial,
        # which preserves every marginal and destroys only the pairing, and the real
        # lag is read against that null rather than against a number I picked.
        by_trial: dict[str, list[tuple[float, float]]] = defaultdict(list)
        never_seen = 0
        for (tr, bid), d in observed_death.items():
            ls = last_seen.get((tr, bid))
            if ls is None:
                never_seen += 1
            else:
                by_trial[tr].append((d, ls))
        real = sorted(abs(d - ls) for v in by_trial.values() for d, ls in v)
        usable = {tr: v for tr, v in by_trial.items() if len(v) >= 2}
        if real and usable:
            rnd = random.Random(20160617)
            med = lambda xs: sorted(xs)[len(xs) // 2]          # noqa: E731
            null_meds = []
            for _ in range(21):
                vals = []
                for v in usable.values():
                    ds = [d for d, _ in v]
                    rnd.shuffle(ds)
                    vals += [abs(d - ls) for d, (_, ls) in zip(ds, v)]
                null_meds.append(med(vals))
            med_real, med_null = med(real), med(null_meds)
            ratio = med_real / med_null if med_null else 1.0
            print(f"\n  death time vs last interaction  ({len(real):,} bees whose death "
                  f"falls inside the window)")
            print("-" * 92)
            print(f"    median |death - last seen|     : {med_real:>10.1f} s "
                  f"= {med_real / 3600:.2f} h")
            print(f"    same, death times shuffled     : {med_null:>10.1f} s "
                  f"= {med_null / 3600:.2f} h   (21 permutations, within trial)")
            print(f"    ratio                          : {ratio:>10.3f}"
                  f"   (1.0 = the death time says nothing about when the bee vanished)")
            if never_seen:
                print(f"    never seen interacting at all  : {never_seen:>6,}")
            assertion(
                "deaths inside the window are corroborated by the interaction record",
                ratio <= 0.25,
                f"the median bee stops appearing {med_real / 3600:.2f} h from its "
                f"recorded death, against {med_null / 3600:.2f} h when the death times "
                f"are shuffled among bees of the same trial -- a ratio of {ratio:.2f}, "
                f"where 1.0 means the column carries no information about when the "
                f"animal actually vanished. A death time that does not track the record "
                f"is not an observation of death, so this subset is not a set of usable "
                f"events either and NOTHING in this column should be read as mortality",
                f"the median bee stops appearing {med_real / 3600:.2f} h from its "
                f"recorded death, against {med_null / 3600:.2f} h under shuffling -- a "
                f"ratio of {ratio:.2f}. The death time tracks the moment the animal "
                f"leaves the record, so these {len(real):,} are usable as observed "
                f"events with the rest treated as censored at trial end. That is an "
                f"ordinary survival layout and the only safe reading of this column")

    # ids seen interacting but not described in bees.csv
    if ids_per_trial:
        unknown_ids = {tr: seen_ids[tr] - ids_per_trial.get(tr, set())
                       for tr in seen_ids}
        n_unknown = sum(len(v) for v in unknown_ids.values())
        assertion("every interacting bee is described in bees.csv",
                  n_unknown == 0,
                  f"{n_unknown:,} ids appear in interactions.csv with no row in bees.csv. "
                  f"Those individuals have no caste and no death time, so any analysis "
                  f"joining the two silently drops them -- and they are not a random "
                  f"subset if, say, they are the ones that died before scoring",
                  f"every one of the {sum(len(v) for v in seen_ids.values()):,} "
                  f"(trial, id) pairs seen interacting has a row in bees.csv, so a "
                  f"join onto caste or death time drops nobody")

        # The other direction of the same join. A bee described in bees.csv that
        # never appears in interactions.csv is a real individual with zero degree,
        # not a missing row -- and dropping it silently inflates every per-capita
        # rate and removes exactly the isolates a centralization measure needs.
        silent = sum(len(ids_per_trial[tr]) - len(seen_ids.get(tr, set()) & ids_per_trial[tr])
                     for tr in ids_per_trial)
        if silent:
            note("bees described in bees.csv that never interact",
                 f"{silent:,} of {sum(len(v) for v in ids_per_trial.values()):,}. "
                 f"These are isolates, not missing rows. They belong in the "
                 f"denominator of anything per-capita and in the node set of any "
                 f"centralization measure; building the graph from interactions.csv "
                 f"alone drops them and makes the colony look better connected than "
                 f"it is")

    # -------------------------------------------------------------- verdict
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


if __name__ == "__main__":
    raise SystemExit(main())
