"""Check our reading of the Charbonneau/Sasaki/Dornhaus CSV against the paper.

WHY THIS FILE EXISTS
--------------------
The Dryad deposit doi:10.5061/dryad.77110 is a single CSV with no README, no
data dictionary and no column legend. Its header is:

    UAntID, Colony, Treat, Trial, i, a, ActInact, ClustDesc

Every statement about what those columns mean is currently an inference. An
inference that happens to be wrong does not announce itself: the loader runs,
the instruments run, and the numbers look fine. That is exactly the failure the
rest of this pipeline is built to prevent, and it is not prevented by writing a
codebook that asserts the same inference in prose.

So this script does something stronger than documenting the guess. It
recomputes, from the CSV alone, quantities the PAPER reports independently --
how many colonies, how many per treatment, how big each behavioural group is,
how many observation blocks. If our reading of the columns is right, those
numbers must come out equal to the published ones. If they do not, we have
learned that either we are misreading a column or the deposit is not the table
the paper describes, and either way we need to know before anything is written.

Matching an independently published number is evidence. Prose is not.

    python3 validate_dornhaus.py --raw "/Volumes/<drive>/BeeOrg/data/raw/charbonneau_dornhaus_2017"

HOW TO USE THE RESULT
---------------------
PASS   the CSV reproduces the paper. That column reading is confirmed.
CHECK  it does not. Read the note; do not proceed on that column.
?      no target recorded yet -- the value is printed for you to compare by eye.

The targets in PAPER below were transcribed from the PLOS ONE article by an
automated reader. Where the first run of this script proved a target wrong, it
has been replaced and the reason recorded. A target marked verified=False that
"passes" proves nothing on its own -- it may only mean our guess and the
transcription are wrong in the same direction. Open the PDF, confirm, set
verified=True.
"""
from __future__ import annotations

import argparse
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from loaders.common import (find_files, is_missing, normalize, ordered_map,
                            stream_rows, to_float)

CITATION = ("Charbonneau, D., Sasaki, T., & Dornhaus, A. (2017). Who needs 'lazy' "
            "workers? PLoS ONE 12(9): e0184074. Data: doi:10.5061/dryad.77110")

# ---------------------------------------------------------------- paper targets
# value=None means "no target yet, just print what the data says".
# tol, where present, makes the comparison approximate -- used for percentages,
# which the paper rounds to one decimal and which we recompute from a slightly
# different denominator.
ARTICLE_URL = "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0184074"

# `quote` holds the article's own words, read back off the open-access HTML on
# 31 July 2026. A quote settles ONE thing -- that we transcribed the number
# correctly -- and nothing else. It does not make the number right, it does not
# make it commensurable with ours, and it is not the human read that
# verified=True is reserved for. Keeping the two apart is the whole point: the
# first run of this file confused "our transcription is wrong" with "the paper
# and the data disagree", and got the diagnosis exactly backwards. See
# NOTE_ON_TARGETS.
PAPER = {
    "n_removal_colonies": dict(value=20, verified=False,
                               quote="We collected 20 colonies of Temnothorax "
                                     "rugatulus ants",
                               note="20 colonies received a removal treatment. The "
                                    "first run found 22 Colony values, of which 2 are "
                                    "NoRem -- so this is now compared against the "
                                    "removal colonies only, and the match is what "
                                    "identifies NoRem as sitting outside the "
                                    "published design."),
    "n_workers":         dict(value=1307, verified=False,
                              quote="(1307 workers total, colony size mean = 65.35, "
                                    "median = 56, s.d. = 33.01)",
                              note="1,307 workers AT COLLECTION -- which is not the "
                                   "denominator of the percentages below. See "
                                   "NOTE_ON_TARGETS."),
    "n_blocks":          dict(value=3,    verified=False,
                              quote="filmed over 3 consecutive days before removals "
                                    "..., at one week post-removals, and at two weeks "
                                    "post-removal (total of 9 videos per colony)",
                              note="pre-removal, 1 week post, 2 weeks post. 'Block' is "
                                   "our word, not the paper's -- the article never uses "
                                   "it. What is published is three observation periods, "
                                   "which is what Trial's three levels should carry."),
    "colonies_active":   dict(value=5,    verified=False,
                              quote="removal of the 20% most active workers (5 colonies)",
                              note="removal of the 20% most active workers"),
    "colonies_inactive": dict(value=9,    verified=False,
                              quote="removal of the 20% most inactive workers (9 colonies)",
                              note="removal of the 20% most inactive workers"),
    "colonies_random":   dict(value=6,    verified=False,
                              quote="removal of 20% randomly selected workers (6 colonies)",
                              note="removal of 20% chosen at random. 5 + 9 + 6 = 20, "
                                   "which is the one internal consistency the paper's "
                                   "own numbers do satisfy."),
    # The percentages and the counts beside them are BOTH published, verbatim, in
    # one sentence. The counts sum to 1,482 -- a population the article never
    # names and never reconciles against its own 1,307. So the percentages are
    # kept as targets not because the counts were mis-transcribed (they were not)
    # but because a percentage survives a change of denominator and a count does
    # not, and we do not know which population is meant.
    "pct_inactives":     dict(value=40.8, verified=False, tol=3.0,
                              quote="(1) Inactives (605 workers- 40.8%)",
                              note="% of clustered ants in the Inactives group; "
                                   "paper's denominator is 1,482, ours is 1,049"),
    "pct_foragers":      dict(value=9.8,  verified=False, tol=3.0,
                              quote="(2) Foragers (145 workers- 9.8%)",
                              note="% Foragers"),
    "pct_nurses":        dict(value=16.8, verified=False, tol=3.0,
                              quote="(3) Nurses (249 workers- 16.8%)",
                              note="% Nurses"),
    "pct_walkers":       dict(value=32.6, verified=False, tol=3.0,
                              quote="(4) Walkers (483 workers- 32.6%)",
                              note="% Walkers; the paper says Walkers were called "
                                   "'patrollers' in earlier work"),
}

NOTE_ON_TARGETS = """
WHAT THE FIRST RUN SETTLED, AND WHAT IT DID NOT

A CORRECTION FIRST. An earlier version of this note said, in these words: "The
transcribed absolute group sizes (605/145/249/483, sum 1,482) are wrong. No set
of ants in the deposit has those sizes... the absolute numbers were an artefact
of automated extraction." That is false and it was checked on 31 July 2026
against the open-access article itself. The sentence is published verbatim:
"Workers were clustered into 4 distinct task groups: (1) Inactives (605 workers-
40.8%), (2) Foragers (145 workers- 9.8%), (3) Nurses (249 workers- 16.8%), and
(4) Walkers (483 workers- 32.6%)". Our transcription was faithful. The
disagreement is between the paper and the deposit, not between the paper and our
reading of it -- and blaming the extraction let us stop looking at the real
problem, which is a full third of it.

Settled, now, by reading the article:

  * The four task-group counts sum to 1,482. The article's own collection total
    is 1,307. The article never names a population of 1,482 and never reconciles
    the two, and it does not say whether workers eclosed or were newly marked
    during the three weeks. That 1,482 is the percentages' denominator is not an
    inference from the sum; all four reproduce from it to the published decimal
    -- 605/1482 = 40.82, 145/1482 = 9.78, 249/1482 = 16.80, 483/1482 = 32.59 --
    and none of them reproduces from 1,307. So the percentages are percentages OF
    1,482, and 1,307 is a count of something else. They cannot both describe the
    sample.

  * The groups do not overlap, and that is settled from inside the paper rather
    than from the deposit. The four percentages sum to exactly 100.0 and each
    reproduces from 1,482. Both only hold if the four counts partition 1,482; an
    ant counted in two groups would raise all four percentages of the distinct
    headcount together and their sum above 100. The deposit agrees -- ClustDesc
    is one label per ant, zero ants carry two -- but that is a property of the
    1,049 we hold, not of the 1,482 the paper clustered, so it corroborates and
    does not settle. Consequence: 1,482 minus 1,307 is a difference of
    POPULATION, not of counting rule, and "the clustering covers more ants than
    the collection" stays the assumption to put to the authors.

  * Which is why the percentages are kept as targets and the counts are not: a
    proportion survives a change of denominator and a headcount does not. Our
    1,049 clustered ants give proportions within ~2.5 points of the published
    ones, and that agreement is about COMPOSITION only. It is not evidence that
    we have the same ants. tol=3.0 exists to absorb rounding, and it must not be
    read as absorbing a 1,482-versus-1,049 difference in population -- it does
    not, and nothing here does.

  * 22 Colony values, 2 of them NoRem, leaves exactly the 20 removal colonies the
    methods describe. NoRem is therefore not a miscount; it is a group outside the
    published design. Still unresolved (see the email draft).

  * Three observation periods -- "3 consecutive days before removals ..., at one
    week post-removals, and at two weeks post-removal (total of 9 videos per
    colony)", each video 5 minutes. The word "block" appears nowhere in the
    article; it is ours. Trial's three levels are the published design.

Not settled:

  * The worker total. The paper says 1,307; the file has 1,299 distinct UAntIDs
    and 1,049 of them carry a behavioural group. Neither matches, and the paper's
    other total, 1,482, matches neither either. 1,049 is exactly the number of
    pre-block rows, which the script now tests directly. The residual 8-ant gap
    between 1,299 and 1,307 is small enough to be an exclusion rule we have not
    reconstructed and large enough that we should not claim to have reproduced
    the sample. Given 1,482, we should not claim the paper reproduces itself
    either -- and that is a sentence for the authors, not for the proposal.

Still owed: a human opening the PDF. Every target now carries the article's own
words in a `quote` field, so that read is a minute's work rather than a hunt.
Quoting is not verifying: it settles that we copied correctly and nothing more.
"""

# What we currently BELIEVE each column is. Every line here is a claim that the
# checks below are trying to falsify.
CLAIMS = [
    ("UAntID",   "unique worker identifier; unique across colonies, not within"),
    ("Colony",   "colony identifier; 20 removal colonies plus NoRem"),
    ("Treat",    "removal treatment applied to the COLONY, so constant within a colony"),
    ("Trial",    "observation block: pre / post1 / post2, an ORDERED categorical"),
    ("i",        "proportion of observed time inactive, in [0,1], per ant per block"),
    ("a",        "proportion of observed time on active tasks, in [0,1]; NOT 1 - i, "
                 "because undifferentiated walking is in neither"),
    ("ActInact", "coarse two-level active/inactive flag; present on a minority of rows"),
    ("ClustDesc", "behavioural group from cluster analysis of PRE-REMOVAL data, "
                  "therefore CONSTANT per ant across blocks, and MISSING for ants "
                  "first seen after the removal"),
]

RESULTS: list[tuple[str, str, str]] = []      # (status, label, detail)


def record(label: str, got, target_key: str | None = None, detail: str = "") -> None:
    if target_key is None or PAPER.get(target_key, {}).get("value") is None:
        RESULTS.append(("?", label, f"data says {got}. {detail}".strip()))
        return
    t = PAPER[target_key]
    tol = t.get("tol")
    # Three states, not two. "quoted" says the transcription is right; only
    # "verified" says a human has read the PDF. Collapsing them is how the first
    # run came to blame its own extraction for a disagreement the article
    # actually contains.
    mark = ("" if t["verified"]
            else "  (transcription quoted from the article; NOT human-verified)"
            if t.get("quote") else "  (target NOT human-verified, NOT quoted)")
    if tol is None:
        status = "PASS" if got == t["value"] else "CHECK"
        RESULTS.append((status, label,
                        f"data {got} vs paper {t['value']}{mark}. {detail}".strip()))
        return
    # A tolerance was applied. That deserves its own status rather than being
    # laundered into a PASS, because the tolerance is OUR choice and was set
    # after seeing the data. "Within 3.0" where the deviation is 2.3 is a
    # threshold fitted to the result. CLOSE means consistent with the published
    # figure, not reproducing it.
    dev = round(got - t["value"], 2)
    status = "CLOSE" if abs(dev) <= tol else "CHECK"
    RESULTS.append((status, label,
                    f"data {got} vs paper {t['value']}, off by {dev:+} "
                    f"(our tolerance {tol}){mark}. {detail}".strip()))


def assertion(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("PASS" if ok else "CHECK", label, detail))


def header_of(path: Path) -> list[str]:
    """First row of a delimited file, as a list of column names."""
    for row in stream_rows(path, limit=1):
        return list(row.keys())
    return []


def find_csv(raw_dir: Path) -> Path:
    """Pick the CSV whose HEADER matches, not the biggest one.

    The first version of this took `max(files, key=size)`, on the reasoning that
    the deposit's one real table would be the largest file in its own directory.
    That holds until you point the script at a raw root holding more than one
    deposit, at which point it confidently opened a 367,614-row `interactions.csv`
    -- a different study entirely -- printed the Charbonneau citation above it,
    and only stopped because the header check downstream refused it.

    Stopping was the right outcome, but it came from the last line of defence.
    Size is not evidence about identity; the header is. So selection is now by
    header, every candidate is listed with the path that distinguishes it from
    its namesakes, and an ambiguous match is an error rather than a coin toss.
    """
    files = [f for f in find_files(raw_dir, ["*.csv", "*.tsv", "*.txt"])
             if f.name not in {"RESOLVED.json"}]
    if not files:
        raise SystemExit(f"no CSV under {raw_dir}")

    want = {normalize(c) for c, _ in CLAIMS}
    scored = []
    for f in files:
        try:
            head = header_of(f)
        except OSError as exc:                      # unreadable is not a match
            scored.append((f, [], -1, str(exc)))
            continue
        have = {normalize(h) for h in head}
        scored.append((f, head, len(want & have), ""))

    best = max(s[2] for s in scored)
    hits = [s for s in scored if s[2] == best and best == len(want)]

    if len(hits) == 1:
        return hits[0][0]

    # Either nothing matched or several things did. Both need human eyes, and
    # both are far more useful with the candidate list printed than without.
    print(f"looked under {raw_dir}")
    print(f"expected a header containing: {[c for c, _ in CLAIMS]}\n")
    for f, head, score, err in sorted(scored, key=lambda s: -s[2]):
        try:
            rel = f.relative_to(raw_dir)
        except ValueError:
            rel = f
        note = err or f"{score}/{len(want)} of the expected columns"
        print(f"  {str(rel):60} {note}")
        print(f"      header: {head}")
    if not hits:
        raise SystemExit(
            "\nNo file under this root has the Charbonneau/Dornhaus header. Point "
            "--raw at\nthe directory for that deposit, or check the download "
            "actually completed.")
    raise SystemExit(
        f"\n{len(hits)} files carry that header. Which deposit is which is now a "
        "question\nabout the directory layout, and guessing between them is exactly "
        "what this\nscript exists to prevent. Pass --raw a path that contains only one.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True, help="data/raw/charbonneau_dornhaus_2017")
    a = ap.parse_args()

    root = Path(a.raw).expanduser()
    path = find_csv(root)
    # The path, not just the name. `interactions.csv` and `antdata.csv` are both
    # plausible names for half a dozen deposits, and when several sit under one
    # raw root the bare filename does not say which study you are looking at.
    try:
        shown = path.relative_to(root)
    except ValueError:
        shown = path
    print(f"reading {shown}")
    print(f"source : {CITATION}\n")

    rows = list(stream_rows(path))
    if not rows:
        raise SystemExit("read 0 rows")
    header = list(rows[0].keys())
    print(f"header : {header}")
    print(f"rows   : {len(rows):,}\n")

    missing_cols = [c for c, _ in CLAIMS if c not in header]
    if missing_cols:
        print(f"!! the header does not contain {missing_cols}.")
        print("   This is not the file this script was written for. Stop and look.")
        return 1

    ants_all: set[str] = set()
    ants_clustered: set[str] = set()      # carry a real ClustDesc
    ants_unlabelled: set[str] = set()     # ClustDesc is the string 'NA'
    colonies: set[str] = set()
    treat_colonies = defaultdict(set)
    ant_treat = defaultdict(set)
    ant_colony = defaultdict(set)
    ant_cluster = defaultdict(set)
    cluster_ants = defaultdict(set)
    trials = Counter()
    actinact = Counter()
    ant_trials = defaultdict(set)
    ants_in_block = defaultdict(set)      # trial -> ants
    colony_block_ants = defaultdict(lambda: defaultdict(set))   # colony -> trial -> ants
    colony_treat: dict[str, str] = {}
    actinact_rows: list[tuple[str, float, float]] = []   # (flag, i, a) where present
    a_when_flag_missing: list[float] = []
    # missingness cross-tab: trial -> column -> count of missing cells
    miss = defaultdict(Counter)
    # for the activity path: how many blocks per ant carry a usable `a`
    ant_a_blocks = defaultdict(set)
    sums, i_bad, a_bad = [], 0, 0
    n_i_parsed = n_a_parsed = 0

    for r in rows:
        ant = str(r["UAntID"]).strip()
        col = str(r["Colony"]).strip()
        treat = str(r["Treat"]).strip()
        trial = str(r["Trial"]).strip()
        clust = str(r["ClustDesc"]).strip()
        ants_all.add(ant)
        colonies.add(col)
        treat_colonies[treat].add(col)
        ant_treat[ant].add(treat)
        ant_colony[ant].add(col)
        ant_trials[ant].add(trial)
        ants_in_block[trial].add(ant)
        colony_block_ants[col][trial].add(ant)
        colony_treat[col] = treat
        trials[trial] += 1
        flag = str(r["ActInact"]).strip()
        actinact[flag] += 1

        # `NA` here is a literal two-character string, not an empty cell. Treated
        # as a value it becomes a fifth behavioural group with 250 members that
        # does not exist. It is counted, and counted separately.
        for cname in ("i", "a", "ActInact", "ClustDesc"):
            if is_missing(r[cname]):
                miss[trial][cname] += 1
        if is_missing(clust):
            ants_unlabelled.add(ant)
        else:
            ants_clustered.add(ant)
            ant_cluster[ant].add(clust)
            cluster_ants[clust].add(ant)

        vi, va = to_float(r["i"]), to_float(r["a"])
        if vi is not None:
            n_i_parsed += 1
            if not (0.0 <= vi <= 1.0):
                i_bad += 1
        if va is not None:
            n_a_parsed += 1
            ant_a_blocks[ant].add(trial)
            if not (0.0 <= va <= 1.0):
                a_bad += 1
        if vi is not None and va is not None:
            sums.append(vi + va)
            if is_missing(flag):
                a_when_flag_missing.append(va)
            else:
                actinact_rows.append((flag, vi, va))

    # ------------------------------------------------------------- the checks
    removal_colonies = {c for t, cs in treat_colonies.items() if t != "NoRem"
                        for c in cs}
    record("colonies with a removal treatment (excluding NoRem)",
           len(removal_colonies), "n_removal_colonies",
           f"{len(colonies)} Colony values in total")
    record("distinct UAntID (all rows)", len(ants_all), "n_workers")
    record("distinct UAntID carrying a ClustDesc", len(ants_clustered), None,
           f"plus {len(ants_unlabelled)} whose ClustDesc is the string 'NA'")
    record("observation blocks", len(trials), "n_blocks",
           f"levels {sorted(trials)}")

    assertion("UAntID is unique across colonies (never reused)",
              all(len(v) == 1 for v in ant_colony.values()),
              f"{sum(1 for v in ant_colony.values() if len(v) > 1)} ants appear "
              "under more than one Colony -- if nonzero, UAntID is NOT a global key "
              "and every per-ant number in the pipeline is pooling different ants")
    assertion("Treat is a colony-level, not ant-level, variable",
              all(len(v) == 1 for v in ant_treat.values()),
              f"{sum(1 for v in ant_treat.values() if len(v) > 1)} ants carry more "
              "than one Treat value")
    assertion("ClustDesc is constant per ant (cluster fitted to pre-removal only)",
              all(len(v) == 1 for v in ant_cluster.values()),
              f"{sum(1 for v in ant_cluster.values() if len(v) > 1)} ants change "
              "cluster. If this PASSES, the degeneracy guard in run_real_bench.py is "
              "correct and ClustDesc must never be used as a time-varying task. "
              "Author-confirmed, Daniel Charbonneau by email received 4 August 2026: "
              "the cluster analysis was run on the pre-removal data only, to establish "
              "colony composition before the shock, and was deliberately NOT repeated "
              "afterwards -- cluster solutions are sensitive to their input settings, "
              "so the authors compared direct behavioural quantities (time spent "
              "active) across blocks instead of comparing clusterings. Read that as a "
              "warning and not a permission: it endorses the activity columns as the "
              "thing that moves over time, and it says nothing about binning them into "
              "discrete states and calling a boundary crossing a task switch")

    # ---- the decisive test of WHY 250 ants are unlabelled -------------------
    # If the cluster analysis was fitted to the pre-removal block only, then an
    # ant has a ClustDesc if and only if it was present pre-removal. This is a
    # far stronger statement than "some ants are missing a label", and it is
    # checkable from the file alone.
    pre_blocks = [t for t in trials if str(t).strip().lower().startswith("pre")]
    if pre_blocks:
        pre_ants = set().union(*(ants_in_block[t] for t in pre_blocks))
        labelled_not_pre = ants_clustered - pre_ants
        pre_not_labelled = pre_ants - ants_clustered
        assertion("having a ClustDesc is EXACTLY having been present pre-removal",
                  not labelled_not_pre and not pre_not_labelled,
                  f"{len(pre_ants)} ants in the pre block, {len(ants_clustered)} "
                  f"clustered; {len(labelled_not_pre)} labelled but absent pre-removal, "
                  f"{len(pre_not_labelled)} present pre-removal but unlabelled. "
                  "A clean match means the missing labels are not data loss -- they "
                  "identify the ants that entered the record after the shock, which "
                  "is a group we may want to analyse on purpose")

    # ---- can the activity route actually carry an analysis? -----------------
    # ClustDesc is unusable as a task because it never varies. The fallback is to
    # bin the per-block activity proportion `a`. That only works if an ant has a
    # parseable `a` in at least two blocks -- otherwise there is no within-ant
    # change to measure and we are back to a static label by another name.
    a_ge2 = sum(1 for v in ant_a_blocks.values() if len(v) >= 2)
    a_ge1 = sum(1 for v in ant_a_blocks.values() if v)
    assertion("--task-from activity is viable (enough ants have >=2 blocks with `a`)",
              a_ge2 >= 50,
              f"{a_ge1} of {len(ants_all)} ants have a parseable `a` in at least one "
              f"block; {a_ge2} have it in two or more. Only those {a_ge2} can show a "
              "within-individual change, so they are the effective sample for any "
              "specialization or flexibility number computed this way")

    assertion("i and a lie in [0,1] as proportions",
              i_bad == 0 and a_bad == 0,
              f"{i_bad} bad i of {n_i_parsed:,} parseable, {a_bad} bad a of "
              f"{n_a_parsed:,} parseable, out of {len(rows):,} rows. Note the "
              "denominator: cells that do not parse are skipped, so this says "
              "nothing about the rows that carry no number at all")
    if sums:
        near1 = sum(1 for s in sums if abs(s - 1.0) < 1e-6) / len(sums)
        assertion("i + a sums to 1 (they exhaust the time budget)",
                  near1 > 0.99,
                  f"{near1:.1%} of {len(sums):,} rows with both values sum to 1. If "
                  "well below 1, a third category ('undifferentiated' walking) is "
                  "unaccounted for and 'a' is NOT 1 - i")

    print("COLUMN-BY-COLUMN, what we currently believe")
    print("-" * 92)
    for name, claim in CLAIMS:
        print(f"  {name:10} {claim}")

    print("\nTREATMENTS  (colonies per treatment, not ants)")
    print("-" * 92)
    for t in sorted(treat_colonies, key=lambda x: -len(treat_colonies[x])):
        n_ants = len({a for a in ants_all if t in ant_treat[a]})
        print(f"  {t:12} {len(treat_colonies[t]):>3} colonies, {n_ants:>5} ants")
    mapping = {"RemActive": "colonies_active", "RemLazy": "colonies_inactive",
               "RemRandom": "colonies_random"}
    for code, key in mapping.items():
        if code in treat_colonies:
            record(f"colonies with {code}", len(treat_colonies[code]), key)

    if "NoRem" in treat_colonies:
        n = len(treat_colonies["NoRem"])
        n_ants = len({a for a in ants_all if "NoRem" in ant_treat[a]})
        # RESOLVED by the first author, received 4 August 2026. Until then this
        # check deliberately failed as UNRESOLVED; the text it carried is kept in
        # ANSWERED below so that what we did not know is still legible.
        assertion("ANSWERED by the author: NoRem is an abandoned replicate, not a control",
                  n == 2,
                  f"{n} colon{'y' if n == 1 else 'ies'}, {n_ants} ants carry "
                  "Treat='NoRem'. Daniel Charbonneau, by email: the behaviour of these "
                  "colonies was scored and validated, but the queens were accidentally "
                  "killed while the workers were being removed, so the removal was "
                  "never carried out and the replicate was unusable for the study. "
                  "Two consequences, and they point opposite ways. EXCLUDE these ants "
                  "from anything involving the removal contrast -- there is no shock in "
                  "them and they are not a control either, because a control is a "
                  "design and this is an accident. But the pre block is good data by "
                  "the author's account, collected before the queens were lost, so it "
                  "is usable as ADDITIONAL pre-removal baseline. Note what is and is "
                  "not evidence here: the file independently shows exactly this shape "
                  "(2 colonies, pre only, nothing after), which is why the answer is "
                  "credible; but that the pre block predates the queen loss is the "
                  "author's testimony and the file cannot corroborate it, because a "
                  "colony with no post block looks the same either way")

    print("\nBEHAVIOURAL GROUPS  (distinct ants per ClustDesc)")
    print("-" * 92)
    for c in sorted(cluster_ants, key=lambda x: -len(cluster_ants[x])):
        n = len(cluster_ants[c])
        print(f"  {c:14} {n:>5} ants  {n / max(1, len(ants_clustered)):>6.1%}")
    print(f"  {'TOTAL':14} {len(ants_clustered):>5}")
    print(f"  {'(no label)':14} {len(ants_unlabelled):>5} ants carry ClustDesc='NA' "
          "and are NOT a fifth group")

    gmap = {"inactive": "pct_inactives", "forager": "pct_foragers",
            "nurse": "pct_nurses", "patroller": "pct_walkers",
            "walker": "pct_walkers"}
    for label, ants in cluster_ants.items():
        key = gmap.get(label.strip().lower())
        pct = round(100 * len(ants) / max(1, len(ants_clustered)), 1)
        if key:
            record(f"group share: {label}", pct, key,
                   f"{len(ants)} of {len(ants_clustered)} clustered ants")
        else:
            record(f"group share: {label}", pct, None,
                   "no paper target -- this label was not expected")
    # The four shares miss the published percentages by +2.3, +2.2, -2.2, -2.3 --
    # two over and two under, which is a denominator difference and not sampling
    # noise. One candidate denominator is available to test: the paper may have
    # computed its percentages over the 20 experimental colonies, while we are
    # including the NoRem ants. Recompute both ways and see which moves closer.
    norem_ants = {a for a in ants_all
                  if any(colony_treat.get(c) == "NoRem" for c in ant_colony[a])}
    if norem_ants and cluster_ants:
        excl = {c: ants - norem_ants for c, ants in cluster_ants.items()}
        n_excl = sum(len(v) for v in excl.values())
        print(f"\n  the same shares with the {len(norem_ants & ants_clustered)} "
              f"clustered NoRem ants excluded (n={n_excl}):")
        moved = []
        for c in sorted(excl, key=lambda x: -len(excl[x])):
            pct = 100 * len(excl[c]) / max(1, n_excl)
            before = 100 * len(cluster_ants[c]) / max(1, len(ants_clustered))
            key = gmap.get(c.strip().lower())
            tgt = PAPER.get(key, {}).get("value") if key else None
            extra = ""
            if tgt is not None:
                extra = (f"  paper {tgt}, off by {pct - tgt:+.1f} "
                         f"(was {before - tgt:+.1f})")
                moved.append(abs(pct - tgt) < abs(before - tgt))
            print(f"    {c:14} {len(excl[c]):>5} ants  {pct:>5.1f}%{extra}")
        if moved:
            assertion("excluding NoRem explains the gap to the published shares",
                      all(moved),
                      f"{sum(moved)} of {len(moved)} groups move closer to the paper "
                      "once NoRem ants are dropped. If all four move closer, the "
                      "paper's denominator is the 20 experimental colonies and ours "
                      "should be too. If they do not, the gap is something else and "
                      "the shares remain CLOSE, not reproduced")

    expected = {"inactive", "forager", "nurse", "patroller", "walker"}
    unexpected = {c for c in cluster_ants if c.strip().lower() not in expected}
    if unexpected:
        assertion("every ClustDesc label is one the paper names", False,
                  f"unexpected labels: {sorted(unexpected)}")
    else:
        assertion("every ClustDesc label is one the paper names", True,
                  f"{sorted(cluster_ants)} -- and 'NA' is correctly excluded rather "
                  "than counted as a group")
    if any(c.strip().lower() == "patroller" for c in cluster_ants):
        assertion("NAMING: data 'patroller' IS the paper's 'Walkers' -- author-confirmed",
                  True,
                  "confirmed by Daniel Charbonneau by email, received 4 August 2026: "
                  "the group was called walkers, wanderers and patrollers at various "
                  "points and the deposit carries the older name. He adds the reason "
                  "for the final choice, and it is a caveat we should carry rather "
                  "than drop: the group's function, if it has one, is not known, and "
                  "'walker' was chosen precisely because it asserts less than "
                  "'patroller' does. So use Walkers, and do not write anything that "
                  "treats this group as performing a patrol or a monitoring task -- "
                  "the name in the deposit would be smuggling in a claim the authors "
                  "deliberately withdrew")

    print("\nOBSERVATION BLOCKS")
    print("-" * 92)
    for t, n in sorted(trials.items()):
        print(f"  {t:10} {n:>6} rows, {len(ants_in_block[t]):>5} distinct ants")
    complete = sum(1 for v in ant_trials.values() if len(v) == len(trials))
    print(f"  ants present in all {len(trials)} blocks: {complete} of {len(ants_all)} "
          f"({complete / max(1, len(ants_all)):.1%})")
    print("  Attrition is why --min-obs 2 is the loader default: requiring all three")
    print("  blocks would discard most of the colony.")

    # ---- does disappearing from the record mean having been removed? --------
    # The design removes 20% of workers per colony. It is tempting to read the
    # ants that vanish between pre and the first post block as "the removed
    # ones", which would hand us the identity of the treated individuals for
    # free. That inference is only safe if the disappearance rate is close to
    # 20%. If it is much higher, absence confounds removal with death, marker
    # loss and simply not being seen, and we cannot recover who was removed.
    order_ix = ordered_map(trials.keys())
    by_ix = {v: k for k, v in order_ix.items()}
    pre_label, first_post = by_ix.get(0), by_ix.get(1)
    if pre_label and first_post:
        print(f"\nATTRITION  ({pre_label} -> {first_post}, per colony)")
        print("-" * 92)
        rates = defaultdict(list)
        for col, blocks in colony_block_ants.items():
            pre_set = blocks.get(pre_label, set())
            if not pre_set:
                continue
            gone = pre_set - blocks.get(first_post, set())
            rates[colony_treat[col]].append(len(gone) / len(pre_set))
        print(f"  {'treatment':12} {'colonies':>9} {'median lost':>13}  range")
        for t in sorted(rates, key=lambda x: -len(rates[x])):
            rs = sorted(rates[t])
            print(f"  {t:12} {len(rs):>9} {statistics.median(rs):>12.0%}  "
                  f"[{rs[0]:.0%}, {rs[-1]:.0%}]")

        removal_rates = [r for t, rs in rates.items() if t != "NoRem" for r in rs]
        if removal_rates:
            med = statistics.median(removal_rates)
            assertion("disappearing from the record is NOT the same as being removed",
                      med <= 0.30,
                      f"the median removal colony loses {med:.0%} of its pre-removal "
                      f"ants by {first_post}, against a design that removes 20%. The "
                      "excess is death, marker loss and non-observation, so the set of "
                      "ants that vanish is NOT the set that was removed and we cannot "
                      "recover the treated individuals by subtraction. Ask the authors "
                      "for the removal list instead of inferring it")

        # ---- a hint at what NoRem is, now superseded by the answer ----------
        # This was written before the authors replied. The reasoning was: if NoRem
        # is a genuine unmanipulated control, its colonies should lose only the
        # background rate rather than a 20% step. It is kept, failing, as a record
        # of how little it was worth. The true answer -- scored, then the queens
        # accidentally killed during removal, replicate abandoned -- was not on the
        # menu of possibilities this hint was built to discriminate between, and no
        # attrition rate could have pointed at it. The email that got the answer
        # worked because it described the pattern in the file and asked what it was,
        # rather than offering the authors a choice between our two guesses.
        if "NoRem" in rates and removal_rates:
            nr = sorted(rates["NoRem"])
            nr_med = statistics.median(nr)
            assertion("SUPERSEDED: the attrition hint could not have found the answer",
                      False,
                      f"NoRem median {nr_med:.0%} (n={len(nr)}, range "
                      f"[{nr[0]:.0%}, {nr[-1]:.0%}]) vs removal median "
                      f"{statistics.median(removal_rates):.0%} (n={len(removal_rates)}). "
                      "The hint asked whether NoRem looks like a control. It is not a "
                      "control and it is not a removal group; it is a replicate that "
                      "was abandoned after the pre block, so its 'attrition' is an "
                      "artefact of the record stopping and carries no information about "
                      "the treatment at all. See the ANSWERED check above")

        first_seen = {}
        for t in sorted(trials, key=lambda x: order_ix[x]):
            for ant in ants_in_block[t]:
                first_seen.setdefault(ant, t)
        arrivals = Counter(first_seen.values())
        print("  first appearance in the record, by block:")
        for t in sorted(trials, key=lambda x: order_ix[x]):
            print(f"    {t:10} {arrivals[t]:>5} ants seen here for the first time")
        print("  Ants arriving after the shock are the colony's replacement labour.")
        print("  They carry no ClustDesc, so anything keyed on cluster silently excludes")
        print("  exactly the individuals who joined the workforce in response.")

    print("\nMISSINGNESS BY BLOCK  (cells that read as 'no value', mostly the string 'NA')")
    print("-" * 92)
    cols = ("i", "a", "ActInact", "ClustDesc")
    print(f"  {'block':10} {'rows':>7}  " + "  ".join(f"{c:>12}" for c in cols))
    for t, n in sorted(trials.items()):
        cells = "  ".join(f"{miss[t][c]:>5} ({miss[t][c] / max(1, n):>4.0%})"
                          for c in cols)
        print(f"  {t:10} {n:>7}  {cells}")
    print("  Which rows are missing is itself a finding. A column missing uniformly")
    print("  across blocks is a coding convention; one concentrated in the post blocks")
    print("  is a consequence of the manipulation and must be modelled, not dropped.")

    print("\nActInact LEVELS")
    print("-" * 92)
    for k, n in actinact.most_common():
        note = "  <- missing, not a level" if is_missing(k) else ""
        print(f"  {k!r:12} {n:>6} rows{note}")

    # ---- is ActInact just a binarisation of i and a, or new information? ----
    # It matters which. If A/I is recoverable from the numbers already in the
    # row, the column is redundant and its 58% missingness costs us nothing. If
    # it is NOT recoverable, it encodes something the deposit does not otherwise
    # give us -- and we would be discarding it without knowing what it was.
    if actinact_rows:
        agree = sum(1 for f, vi, va in actinact_rows
                    if (va > vi) == (f.strip().upper().startswith("A")))
        frac = agree / len(actinact_rows)
        assertion("ActInact is recoverable from i and a (so it is redundant)",
                  frac > 0.95,
                  f"the rule 'A iff a > i' reproduces {frac:.1%} of the "
                  f"{len(actinact_rows):,} rows that carry a flag. Above ~95% the "
                  "column is a derived convenience and dropping it loses nothing. "
                  "Below that it carries information we cannot reconstruct, and we "
                  "need to know what it is before discarding 58% of it as missing")
        # If the simple rule fails, is SOME threshold on the numbers we have
        # enough? Search over `a`, `i` and their difference. If one of them hits
        # near-perfect accuracy the column is still derived, just not by the
        # rule we guessed. If none does, ActInact is genuinely extra information.
        best = (0.0, "", 0.0)
        for label, key in (("a", lambda i_, a_: a_),
                           ("i", lambda i_, a_: -i_),
                           ("a - i", lambda i_, a_: a_ - i_)):
            vals = sorted({key(vi, va) for _f, vi, va in actinact_rows})
            for thr in vals:
                acc = sum(1 for f, vi, va in actinact_rows
                          if (key(vi, va) > thr)
                          == f.strip().upper().startswith("A")) / len(actinact_rows)
                if acc > best[0]:
                    best = (acc, label, thr)
        assertion("no threshold on i or a reproduces ActInact either",
                  best[0] <= 0.95,
                  f"the best single cut is `{best[1]} > {best[2]:.3f}` at {best[0]:.1%} "
                  "accuracy. If this is still well short of perfect, ActInact was not "
                  "computed from these two columns and encodes something the deposit "
                  "does not otherwise contain -- worth one line in the email")

        if a_when_flag_missing:
            m_flag = statistics.median(va for _f, _i, va in actinact_rows)
            m_none = statistics.median(a_when_flag_missing)
            # Compare as a RATIO, not an absolute difference. `a` has a median
            # near 0.1, so an absolute gap of 0.095 -- which is a doubling -- slid
            # under a 0.10 threshold and produced a reassuring PASS on the first
            # real run. The threshold was the wrong shape for the variable.
            ratio = m_flag / m_none if m_none else float("inf")
            assertion("ActInact missingness is unrelated to how active the ant was",
                      ratio < 1.25,
                      f"median `a` is {m_flag:.3f} on flagged rows vs {m_none:.3f} on "
                      f"unflagged ones -- a factor of {ratio:.2f}. The flag is present "
                      "preferentially for MORE active ants, so any subset defined by "
                      "ActInact is biased towards activity and cannot be treated as a "
                      "random sample of the colony")

    # ------------------------------------------------------------------ verdict
    print("\nVERDICT")
    print("=" * 92)
    order = {"CHECK": 0, "CLOSE": 1, "?": 2, "PASS": 3}
    for status, label, detail in sorted(RESULTS, key=lambda r: order[r[0]]):
        print(f"  [{status:5}] {label}")
        if detail:
            print(f"           {detail}")

    n_check = sum(1 for s, _, _ in RESULTS if s == "CHECK")
    n_close = sum(1 for s, _, _ in RESULTS if s == "CLOSE")
    n_open = sum(1 for s, _, _ in RESULTS if s == "?")
    unver = sum(1 for v in PAPER.values() if v["value"] is not None and not v["verified"])

    print(NOTE_ON_TARGETS)
    print(f"{n_check} disagreement(s), {n_close} close-but-not-equal, "
          f"{n_open} value(s) with no target yet.")
    if n_close:
        print("CLOSE is not PASS. Those lines are consistent with the published figure "
              "under a\ntolerance we chose ourselves after seeing the data. Write "
              "'consistent with', never\n'reproduces', until the denominator the paper "
              "used is known.")
    unquoted = sum(1 for v in PAPER.values()
                   if v["value"] is not None and not v["verified"]
                   and not v.get("quote"))
    if unver:
        print(f"{unver} of the paper targets have not been checked against the PDF by "
              f"a human\n({unver - unquoted} of them now carry the article's own "
              f"sentence in a `quote` field, so that\ncheck is a minute's reading; "
              f"{unquoted} carry no quote at all).\nA PASS against an unverified target "
              f"is not yet evidence -- open the paper, confirm\nthe number, and set "
              f"verified=True in PAPER at the top of this file. A quote proves\nwe "
              f"copied it correctly and proves nothing else: the article's task-group "
              f"counts\nsum to 1,482 against its own stated 1,307, and both are quoted "
              f"accurately.")
    print("\nNothing from this deposit should appear in the proposal until the CHECK "
          "lines are\nresolved or explicitly scoped out in writing.")
    return 1 if n_check else 0


if __name__ == "__main__":
    raise SystemExit(main())
