"""End-to-end self test on fabricated data. Run this BEFORE downloading anything.

It writes small fake raw files in each dataset's expected shape, pushes them
through every loader, and runs every instrument on the result. Two minutes of
reassurance in exchange for not discovering a broken loader after an 11 GB
download.

It also checks that the instruments behave correctly on data whose answer we
already know: a colony of specialists must score a corrected DoL well above the
permutation null, and a colony of identical random agents must score at or near
zero. An instrument that cannot tell those two apart is not measuring anything.

    python3 selftest.py

Exit code 0 means the pipeline is sound. It does NOT mean the column names match
the real deposits -- that is what inspect_data.py is for.
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from pathlib import Path

import instruments
import netstats
from loaders import beesbook, common, dornhaus, gernat, illinois, mersch, mersch_net
from loaders.common import write_events

FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAIL
    print(f"  [{'ok' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAIL += 1


def _write(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


# ------------------------------------------------------------------ fixtures
def fake_beesbook(root: Path, rng) -> Path:
    """40 bees, each with a preferred quadrant, drifting over time."""
    d = root / "data" / "raw" / "beesbook_2018"
    rows = []
    for bee in range(40):
        pref = bee % 4
        for t in range(0, 4000, 5):
            q = pref if rng.random() < 0.85 else rng.randrange(4)
            x = rng.uniform(0, 50) + 50 * (q % 2)
            y = rng.uniform(0, 50) + 50 * (q // 2)
            rows.append([f"b{bee}", round(x, 2), round(y, 2), t])
    _write(d / "detections.csv", ["bee_id", "x_pos", "y_pos", "timestamp"], rows)
    return d


def fake_gernat(root: Path, rng) -> Path:
    """60 bees; 6 of them are hubs that receive far more than chance."""
    d = root / "data" / "raw" / "gernat_trophallaxis"
    hubs = [f"a{i}" for i in range(6)]
    rows = []
    for t in range(6000):
        a = f"a{rng.randrange(60)}"
        b = rng.choice(hubs) if rng.random() < 0.4 else f"a{rng.randrange(60)}"
        rows.append(["T1", a, b, ">", t])
    _write(d / "interactions.csv",
           ["trial", "id1", "id2", "direction", "timestamp"], rows)
    return d


def fake_gernat_three_trials(root: Path, rng) -> Path:
    """The deposit's real shape, built to be hostile in the three ways it can be.

    The real Gernat deposit is three tables that have to be joined, and the join
    is where individually-correct files produce something that is not:

      1.  ids RESTART in every trial, so pooling merges different bees;
      2.  the clocks are DISJOINT -- trial 2 begins long after trial 1 ends --
          so one global min-to-max binning gives each trial its own block of bins;
      3.  and bee 0 of trial 1 is planted as a hub in trial 1 only, so a merge
          across trials is visible as a hub that should not be one.

    The single-trial `fake_gernat` above cannot catch any of these; every check it
    passes, it passes for a file with one trial and one clock.
    """
    d = root / "data" / "raw" / "gernat_three_trials"
    inter, bees, trials = [], [], []
    base = 0.0
    for tr in ("t1", "t2", "t3"):
        span = 10_000.0
        trials.append([tr, base, base + span])
        hubs = {"b0", "b1"} if tr == "t1" else {"b40", "b41"}
        for i in range(60):
            bid = f"b{i}"
            # a third of each trial's bees die partway through, and must then
            # stop appearing -- the cross-file check depends on this holding.
            dies = rng.random() < 0.33
            death = base + rng.uniform(0.3, 0.9) * span if dies else ""
            bees.append([tr, bid, rng.choice(["nurse", "forager"]), death])
        dead = {r[1]: r[3] for r in bees if r[0] == tr and r[3] != ""}
        for _ in range(4000):
            t = base + rng.uniform(0, span)
            x = f"b{rng.randrange(60)}"
            y = rng.choice(sorted(hubs)) if rng.random() < 0.45 else f"b{rng.randrange(60)}"
            if x == y or any(d != "" and t > d for d in (dead.get(x, ""), dead.get(y, ""))):
                continue
            inter.append([tr, round(t, 1), x, y, "AtoB"])
        base += span * 2          # a gap, so the trials' ranges cannot overlap
    _write(d / "interactions.csv",
           ["trial", "timestamp", "id1", "id2", "direction"], inter)
    _write(d / "bees.csv", ["trial", "id", "caste", "time_of_death"], bees)
    _write(d / "trials.csv", ["trial", "begin", "end"], trials)
    return d


def fake_gernat_censored(root: Path, rng, overshoot: str = "constant") -> Path:
    """The opposite polarity, and the fixture that would have caught a real bug.

    `fake_gernat_three_trials` gives all three trials the SAME 60 ids, which makes
    "ids present in more than one trial" and "ids present in every trial" the same
    set. The validator's first version computed the second and captioned it as the
    first, and that fixture agreed with it perfectly -- on the real deposit the two
    differ by a factor of five (179 vs 891). A fixture that cannot separate two
    quantities cannot notice when a check confuses them, so the id ranges here are
    staggered instead:

        t1  b0 .. b39     t2  b20 .. b59     t3  b50 .. b79

    30 ids occur in two trials; NONE occurs in all three. The old computation
    returns the empty set and reports PASS -- a clean bill of health on a file
    where 37% of the id space is reused. The verdict itself flips, not just the
    number under it.

    Everything else here is set to the opposite polarity of the other fixture, so
    that any check which has quietly become a constant disagrees across the pair:
    one shared clock rather than disjoint ones, direction tokens the loader knows
    rather than ones it does not, and -- the point of the third fix -- a
    `time_of_death` stamped at the trial's declared end for EVERY bee, which is
    right-censoring wearing the costume of observed mortality.
    """
    d = root / "data" / "raw" / f"gernat_censored_{overshoot}"
    inter, bees, trials = [], [], []
    span = 10_000.0
    # The real deposit stamps every survivor at exactly `end + 1`, one single
    # value, which makes the censoring indicator a biconditional rather than a
    # tolerance. That is a materially better position to be in than "80% of these
    # are probably censored", so the validator says so -- and a claim that strong
    # needs the other polarity tested too. Under `overshoot="scatter"` the stamps
    # take several different values, no rule separates censoring from measurement
    # error, and the validator must NOT offer an exact indicator.
    def survivor_stamp() -> float:
        return span + (1 if overshoot == "constant" else rng.randrange(1, 6))
    ranges = {"t1": range(0, 40), "t2": range(20, 60), "t3": range(50, 80)}
    for tr, rng_ids in ranges.items():
        trials.append([tr, 0.0, span])          # one shared clock, deliberately
        ids = [f"b{i}" for i in rng_ids]
        # Most bees "die" exactly when observation stops. No colony does this.
        # A minority get a death time INSIDE the window, so that the corroboration
        # check has something to run on -- but it is drawn independently of when
        # the bee actually stops appearing. That is the failure the check exists
        # for: a value in the right range, in the right units, correlated with
        # nothing. It passes every check that looks at the column alone, and only
        # the comparison against the interaction record can see it.
        stops: dict[str, float] = {}
        for bid in ids:
            if rng.random() < 0.3:
                stops[bid] = rng.uniform(0.10, 0.40) * span      # vanishes early
                bees.append([tr, bid, "worker",
                             round(rng.uniform(0.50, 0.95) * span, 1)])  # unrelated
            else:
                bees.append([tr, bid, "worker", survivor_stamp()])
        for _ in range(3000):
            x, y = rng.choice(ids), rng.choice(ids)
            if x == y:
                continue
            t = rng.uniform(0, span * 0.99)
            if any(t > stops[b] for b in (x, y) if b in stops):
                continue                 # never appears after it vanishes
            inter.append([tr, round(t, 1), x, y, rng.choice([">", "<"])])
    _write(d / "interactions.csv",
           ["trial", "timestamp", "id1", "id2", "direction"], inter)
    _write(d / "bees.csv", ["trial", "id", "caste", "time_of_death"], bees)
    _write(d / "trials.csv", ["trial", "begin", "end"], trials)
    return d


MERSCH_BEHAVIOR_HEADER = [
    "colony", "tag_id", "body_size", "age(days)", "nb_foraging_events",
    "group_period1", "group_period2", "group_period3", "group_period4",
    "visits_to_brood", "visits_to_nest_entrance", "visits_to_rubbishpile",
    "nb_interaction_nurses", "nb_interaction_cleaners",
    "nb_interaction_foragers", "nb_interaction_queen",
]
"""The real `behavior.csv` header, copied verbatim from the deposit.

The fixture this replaced invented a `colony_groups.csv` with columns
`ant, group, day, colony` -- a file that does not exist in the deposit, in a
layout the deposit does not use. It passed, every time, and proved nothing:
a fixture built from what you ASSUMED the file looks like can only ever confirm
the assumption. The four `group_period*` columns and the two roles that both
match them are the entire bug, and no fixture without them can see it.
"""


def _write_cr(path: Path, header, rows) -> None:
    """Write with CR-only line endings, the way this deposit actually ships.

    `behavior.csv` is classic-Mac terminated: no LF anywhere. `wc -l` reports 0
    lines and `head` prints the file as one smear, which is a shell problem and
    not a data problem -- `csv.DictReader`, `sniff_delimiter` and `stream_rows`
    were each run against a hand-built CR-only file and all three parse it. The
    fixture uses CR so that a future change which breaks that is caught here
    rather than on the real file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",".join(str(h) for h in header) + "\r"
    body += "".join(",".join(str(x) for x in r) + "\r" for r in rows)
    path.write_text(body)


def _mersch_sequence(rng, shape: str) -> list[str]:
    """Four period labels for one ant."""
    if shape == "broken":
        # Reverse polyethism, and absences written as NA. Both must be caught:
        # the flow test has a published direction to disagree with, and a naive
        # distinct-value count would read the NAs as task changes.
        seq, cur = [], rng.choice("FFC")
        for _ in range(4):
            seq.append(cur)
            if rng.random() < 0.45:
                cur = {"F": "C", "C": "N", "N": "N"}[cur]
        if rng.random() < 0.35:                      # an ant that stops appearing
            k = rng.randrange(1, 4)
            seq = seq[:k] + ["NA"] * (4 - k)
        if rng.random() < 0.04:
            seq[rng.randrange(4)] = "X"              # a level nobody documented
        return seq
    seq, cur = [], rng.choice("NNNC")
    for _ in range(4):
        seq.append(cur)
        if rng.random() < 0.42:
            cur = {"N": "C", "C": "F", "F": "F"}[cur]
    return seq


def fake_gernat_queen(root: Path, rng, name: str, caste: str = "queen",
                      retinue: float = 0.5, donates: bool = False,
                      id_space: str = "match") -> Path:
    """One trial with one animal named in `bees.csv`, in four polarities.

    `retinue` is the share of trophallaxis events whose recipient is that animal.
    At 0.5 she is fed by a retinue and is a hub by caste. Both polarities must be
    reported, and only one of them should raise its voice -- a guard that fires
    either way is not reading the data, it is reciting.

    `donates` exists because the first version of this fixture was wrong in a way
    worth keeping written down. To make an ORDINARY queen I only lowered
    `retinue`, and left her unable to donate -- so she was still the one bee in
    sixty-one who never appeared as a sender, which made her degree half of
    everyone else's and her removal the most disruptive of all 61. She was not
    ordinary; she was unusual in the other direction. An ordinary individual has
    to be ordinary in every respect the measure can see.

    `caste="queenless"` is the substring trap. `id_space="mismatch"` writes the
    bee table under an id the interaction log never uses, which is the failure
    that computes cleanly: the mark lands on nobody, and every number below it is
    then correct about an empty set.
    """
    d = root / "data" / "raw" / f"gernat_queen_{name}"
    workers = [f"w{i}" for i in range(60)]
    q = "q0"
    senders = workers + [q] if donates else workers
    inter, bees = [], []
    bees.append(["t1", ("Q_UNSEEN" if id_space == "mismatch" else q), caste, ""])
    for w in workers:
        bees.append(["t1", w, "worker", ""])
    for _ in range(6000):
        t = round(rng.uniform(0, 10_000.0), 1)
        x = rng.choice(senders)
        y = q if rng.random() < retinue else rng.choice(workers)
        if x == y:
            continue
        inter.append(["t1", t, x, y, "AtoB"])
    _write(d / "interactions.csv",
           ["trial", "timestamp", "id1", "id2", "direction"], inter)
    _write(d / "bees.csv", ["trial", "id", "caste", "time_of_death"], bees)
    return d


def fake_mersch(root: Path, rng, shape: str = "real") -> Path:
    """The Mersch deposit's real shape, in three polarities.

    `shape="real"`  mirrors the deposit: wide period columns, CR line endings,
                    tag ids reused across colonies, one heatmap without a header,
                    a `__MACOSX` shadow, a decoy table whose `group` column is a
                    single static assignment. Every structural CHECK must fire.
    `shape="clean"` the same colony stored the way we wish it were: long format
                    with a separate day column, ids unique across colonies, every
                    heatmap headed, no shadows. The same checks must go quiet.
    `shape="broken"`the failures the "real" file happens not to have: NA labels
                    in the period columns, a backwards N<-C<-F flow, an
                    asymmetric matrix and one that is short by a row.

    Three, not two, because "real" is not the negative case for everything. It
    has no missing labels and its flow runs the published way, so on its own it
    cannot tell a missingness check that fires correctly from one wired to stay
    silent. A check that can only fire one way is not a check.
    """
    d = root / "data" / "raw" / f"mersch_{shape}" / "tracking_data" / "tracking_data"
    colonies = ["1", "2", "3"]
    n_ants = 60
    days = list(range(1, 8))

    rows, per_colony = [], {}
    for ci, col in enumerate(colonies):
        # "real": tag ids restart in every colony, so Ant7 is four different
        # animals. "clean": ids are globally unique, so pooling is harmless.
        ids = ([str(i) for i in range(n_ants)] if shape != "clean"
               else [str(ci * 1000 + i) for i in range(n_ants)])
        per_colony[col] = ids
        for i in ids:
            seq = _mersch_sequence(rng, shape)
            # One queen per colony in the shapes that model the deposit, because
            # the deposit has six. "clean" has none, so the queen checks have a
            # negative polarity and cannot be wired to fire. In "broken" the queen
            # is labelled Q once and N afterwards -- a caste relabel that a
            # distinct-value count scores as a change of task, which is the whole
            # reason queens are handled rather than tolerated.
            if i == ids[0] and shape == "real":
                seq = ["Q", "Q", "Q", "Q"]
            elif i == ids[0] and shape == "broken":
                seq = ["Q", "N", "N", "N"]
            rows.append([col, i, round(rng.uniform(120, 190), 3), 330, 0] + seq +
                        [round(rng.uniform(0, 300), 3), round(rng.random(), 4),
                         rng.randrange(6), 0, 0, 0, 0])

    if shape == "clean":
        # Long: one row per (ant, day), one `group` column, an explicit `day`.
        long_rows = []
        for r in rows:
            col, ant, seq = r[0], r[1], r[5:9]
            for k, g in enumerate(seq):
                long_rows.append([col, ant, g, k + 1, r[3]])
        # `age(days)` is here on purpose. Without it the `age` role has nothing
        # to bind to and fuzzy-matches `day` instead -- "day" is a substring of
        # the normalized "agedays" -- so the negative fixture reported a
        # collision of its own and could not have shown the check going quiet.
        # That is a real latent bug in the candidate lists, not a fixture
        # artefact: a file with `age_days` and no `day` binds the TIME index to
        # an AGE. The collision guard is what turns it from silent into loud.
        _write(d / "behavior.csv",
               ["colony", "tag_id", "group", "day", "age(days)"], long_rows)
    else:
        _write_cr(d / "behavior.csv", MERSCH_BEHAVIOR_HEADER, rows)

    # The decoy. Its `group` is ONE static assignment -- equal to period 1 -- and
    # the old loader's "smallest table with a task-like column" rule preferred it.
    _write(d / "observed_expected_interaction_frequencies.csv",
           ["colony", "tag_ID", "group", "obs_interaction_nurses",
            "exp_random_nurses"],
           [[r[0], r[1], r[5], round(rng.random(), 3), round(rng.random(), 3)]
            for r in rows])
    _write(d / "information_spread.txt", ["colony", "day", "reached"],
           [[c, dy, round(rng.random(), 3)] for c in colonies for dy in days])

    # Square, symmetric, zero-diagonal matrices; the node set shrinks with the
    # day in the shapes that model a real colony.
    for col in colonies:
        for day in days:
            keep = per_colony[col] if shape == "clean" else \
                per_colony[col][:n_ants - (day - 1)]
            ids = [f"Ant{i}" for i in keep]
            n = len(ids)
            M = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(i + 1, n):
                    M[i][j] = M[j][i] = round(rng.random(), 4)
            if shape == "broken" and day == 2:
                M[0][1] = round(M[1][0] + 0.5, 4)          # not symmetric
            lines = [",".join(ids)]
            lines += [",".join(f"{x:.4f}" for x in row) for row in M]
            if shape == "broken" and day == 3:
                lines = lines[:-1]                          # short by one row
            (d / f"network_col{col}_day{day}.txt").write_text("\n".join(lines) + "\n")

    # 17 heatmaps with a header and, in the "real" shape, one without -- the file
    # that is ALMOST like its siblings, whose first observation a loader eats.
    for k in range(6):
        name = d / f"heatmap_col{k // 2 + 1}_{'foragers' if k % 2 else 'nurses'}.txt"
        body = "\n".join(f"{rng.randrange(50)},{rng.randrange(50)},{rng.randrange(9)}"
                         for _ in range(5))
        headless = (shape == "real" and k == 0)
        name.write_text(body + "\n" if headless
                        else "x_coor,y_coor,nb_visits\n" + body + "\n")

    if shape == "real":
        mac = d.parents[1] / "__MACOSX" / "tracking_data" / "tracking_data"
        mac.mkdir(parents=True, exist_ok=True)
        (mac / "._behavior.csv").write_bytes(b"\x00\x05\x16\x07\xff\xfe\x00\x00")
    return d.parents[1]


def fake_dornhaus(root: Path, rng) -> Path:
    """80 ants; after removal at day 8 a third of them change task."""
    d = root / "data" / "raw" / "charbonneau_dornhaus_2017"
    tasks = ["forage", "brood", "inactive", "nest"]
    base = {a: tasks[a % 4] for a in range(80)}
    after = dict(base)
    for a in range(0, 80, 3):
        after[a] = tasks[(a + 1) % 4]
    rows = []
    for day in range(1, 15):
        phase = "pre" if day < 8 else "post"
        table = base if day < 8 else after
        for a in range(80):
            t = table[a] if rng.random() < 0.85 else rng.choice(tasks)
            rows.append([1, f"ant{a}", t, day, "removal_high", phase])
    _write(d / "behaviour.csv",
           ["colony", "ant", "task", "day", "treatment", "phase"], rows)
    return d


# --------------------------------------------------------------------- tests
# Real published headers, copied verbatim from logs/schema_report.md. These are
# regression tests, not fixtures: each one is a header on which the column
# picker once bound, or could plausibly bind, the wrong variable *without
# raising*. A loader that fails loudly is an inconvenience; a loader that
# succeeds on column `a` when it wanted the task is a retracted paper.
REAL_HEADERS = {
    "charbonneau_dornhaus_2017":
        ["UAntID", "Colony", "Treat", "Trial", "i", "a", "ActInact", "ClustDesc"],
    "gernat_trophallaxis":
        ["trial", "timestamp", "id1", "id2", "direction"],
}


def test_real_headers() -> None:
    """The column picker must resolve the ACTUAL published headers correctly."""
    from loaders.common import ordered_map, phase_rank, pick_column

    print("\nREAL HEADERS (regression)")

    hdr = REAL_HEADERS["charbonneau_dornhaus_2017"]
    got = {k: pick_column(hdr, v, k, required=False)
           for k, v in dornhaus.CANDIDATES.items()}
    want = dict(ant="UAntID", colony="Colony", time="Trial", task="ClustDesc",
                treatment="Treat", phase="Trial")
    for key, expect in want.items():
        check(f"dornhaus header: {key} -> {expect}", got[key] == expect,
              f"got {got[key]!r}")
    check("dornhaus: nothing binds to the one-letter activity columns",
          "i" not in got.values() and "a" not in got.values(),
          f"{got}")

    hdr = REAL_HEADERS["gernat_trophallaxis"]
    ggot = {k: pick_column(hdr, v, k, required=False)
            for k, v in gernat.CANDIDATES.items()}
    check("gernat header: id1/id2/direction/time resolve",
          (ggot["id1"], ggot["id2"], ggot["direction"], ggot["time"])
          == ("id1", "id2", "direction", "timestamp"), str(ggot))
    check("gernat header: trial is the colony, not an id",
          ggot["trial"] == "trial", str(ggot))

    # ------------------------------------------------ the guard, per loader
    # Every loader now resolves its roles together. These are the headers on
    # which each one's roles actually collide -- constructed, but from name
    # styles that appear in real deposits, not from nonsense. Each entry names
    # what the silent version would have produced, because "it raises" is only
    # interesting if you know what it stopped.
    from loaders.common import ColumnCollision, pick_columns
    COLLIDING = [
        ("gernat", gernat, ["id1", "id2", "direction", "trial_timestamp"],
         ("trial", "time"),
         "trial IS the colony, so every contact would be filed under a colony id "
         "that is really a clock -- one colony per instant"),
        ("illinois", illinois, ["id1", "id2", "interval_begin_end"],
         ("begin", "end"),
         "every contact would have duration end - begin == 0, so every "
         "duration-weighted edge weighs nothing"),
        # `pos`, not `xy_pos`: with `xy_pos` the x role finds nothing at all and
        # the loader stops on a missing required column, which is a loud failure
        # and needs no guard. `pos` matches BOTH -- that is the quiet one.
        ("beesbook", beesbook, ["bee_id", "pos", "timestamp"],
         ("x", "y"),
         "every coordinate would sit on the diagonal and every zone be wrong"),
    ]
    for name, mod, bad_hdr, roles, damage in COLLIDING:
        spec = {k: v for k, v in mod.CANDIDATES.items()
                if k in getattr(mod, "USED_ROLES", mod.CANDIDATES)}
        try:
            got = pick_columns(bad_hdr, spec, optional=tuple(spec))
            raised, msg = False, str(got)
        except ColumnCollision as exc:
            raised, msg = True, str(exc)
        check(f"{name}: the colliding header is refused",
              raised and all(r in msg for r in roles),
              f"without it: {damage}")

    # And the negative polarity: the REAL headers must still resolve, or the
    # guard is just breaking four working loaders.
    for name, mod, good_hdr in [
        ("gernat", gernat, ["trial", "timestamp", "id1", "id2", "direction"]),
        ("illinois", illinois, ["id1", "id2", "begin", "end", "trial"]),
        ("beesbook", beesbook, ["bee_id", "x", "y", "timestamp", "age"]),
    ]:
        spec = {k: v for k, v in mod.CANDIDATES.items()
                if k in getattr(mod, "USED_ROLES", mod.CANDIDATES)}
        try:
            got = pick_columns(good_hdr, spec, optional=tuple(spec))
            ok, detail = len(set(got.values())) == len(got), str(dict(got))
        except ColumnCollision as exc:
            ok, detail = False, f"REFUSED a good header: {exc}"
        check(f"{name}: the real header still resolves, one column per role",
              ok, detail)

    # ------------------------------------------------- the declared exception
    # Dornhaus is the one place two roles legitimately share a column, and the
    # alias has to be recorded rather than merely tolerated.
    hdr = REAL_HEADERS["charbonneau_dornhaus_2017"]
    dgot = pick_columns(hdr, dornhaus.CANDIDATES,
                        optional=("time", "treatment", "phase", "colony"),
                        allow_alias=dornhaus.ALLOWED_ALIASES)
    fired = [a for a in dgot.aliases if a["fired"]]
    check("dornhaus: the declared time/phase alias is allowed, not raised on",
          dgot["time"] == "Trial" and dgot["phase"] == "Trial",
          f"time={dgot['time']} phase={dgot['phase']}")
    check("dornhaus: and the alias is recorded with its reason, not just tolerated",
          len(fired) == 1 and fired[0]["column"] == "Trial"
          and "no separate clock" in fired[0]["reason"],
          f"{fired}")
    # An alias must not be a blanket amnesty: a DIFFERENT collision on the same
    # loader still has to raise, or the exception has swallowed the rule.
    try:
        # `TaskGroup` matches the task list on "task" and the treatment list on
        # "group". Nothing about the declared time/phase alias covers this pair.
        pick_columns(["UAntID", "Colony", "Trial", "TaskGroup"],
                     {k: v for k, v in dornhaus.CANDIDATES.items()
                      if k in ("ant", "task", "treatment")},
                     allow_alias=dornhaus.ALLOWED_ALIASES)
        other_raised = False
    except ColumnCollision as exc:
        other_raised = "task" in str(exc) and "treatment" in str(exc)
    check("dornhaus: an UNdeclared collision still raises despite the alias",
          other_raised,
          "an exception for one pair must not become an amnesty for all of them")
    # A declared alias that does not fire is reported as such, so a permission
    # that has quietly stopped applying is visible rather than assumed live.
    clean = pick_columns(["UAntID", "Colony", "Treat", "Day", "Phase", "ClustDesc"],
                         dornhaus.CANDIDATES,
                         optional=("time", "treatment", "phase", "colony"),
                         allow_alias=dornhaus.ALLOWED_ALIASES)
    stale = [a for a in clean.aliases if not a["fired"]]
    check("a declared alias that does not fire is reported as stale, not assumed",
          clean["time"] == "Day" and clean["phase"] == "Phase" and len(stale) == 1,
          f"time={clean['time']} phase={clean['phase']} stale={len(stale)}")
    # The reason is the mechanism, so an alias without one is refused outright.
    try:
        pick_columns(hdr, dornhaus.CANDIDATES,
                     optional=("time", "treatment", "phase", "colony"),
                     allow_alias=[(("time", "phase"), "   ")])
        no_reason_raised = False
    except ValueError:
        no_reason_raised = True
    check("an alias declared without a reason is refused",
          no_reason_raised,
          "the reason is what separates a real two-role column from a silenced bug")

    # pre/post1/post2 must order as the experiment ran, not alphabetically
    m = ordered_map(["post2", "pre", "post1"])
    check("categorical time orders pre -> post1 -> post2",
          m == {"pre": 0, "post1": 1, "post2": 2}, str(m))
    check("phase_rank puts 'before' ahead of 'after'",
          phase_rank("before") < phase_rank("after"))


def test_dornhaus_real_shape(root: Path, rng) -> None:
    """Run the loader end to end on the real Dornhaus schema, not our own."""
    print("\nDORNHAUS ON THE REAL SCHEMA")
    d = root / "data" / "raw" / "dornhaus_real_shape"
    clusters = ["patroller", "inactive", "forager", "nurse"]
    rows = []
    for colony, treat in (("Jul14_11", "RemActive"), ("Jul14_12", "RemInactive")):
        for ant in range(60):
            base = clusters[ant % 4]
            for trial in ("pre", "post1", "post2"):
                # a third of ants re-sort after the removal
                c = clusters[(ant + 1) % 4] if (trial != "pre" and ant % 3 == 0) else base
                a = round(rng.uniform(0.5, 1.0) if c != "inactive" else rng.uniform(0, 0.2), 3)
                rows.append([f"{colony}_{ant}", colony, treat, trial,
                             round(1 - a, 3), a, "A" if a > 0.5 else "I", c])
    _write(d / "DryadData_Aug 8 2017.csv",
           ["UAntID", "Colony", "Treat", "Trial", "i", "a", "ActInact", "ClustDesc"],
           rows)

    ev, meta = dornhaus.load(d, min_obs=2)
    check("real schema: 120 ants recovered", meta["n_agents"] == 120,
          f"agents={meta['n_agents']}")
    check("real schema: task came from ClustDesc, not the activity float",
          meta["columns"]["task"] == "ClustDesc" and meta["n_tasks"] == 4,
          f"task col={meta['columns']['task']} n_tasks={meta['n_tasks']}")
    check("real schema: time is ordinal pre/post1/post2, not collapsed to one bin",
          meta["n_timesteps"] == 3 and meta["time_levels"] == ["pre", "post1", "post2"],
          f"timesteps={meta['n_timesteps']} levels={meta.get('time_levels')}")
    check("real schema: shock located at the first post trial",
          meta["shift_timestep"] == 1, f"shift={meta['shift_timestep']}")
    check("real schema: treatments preserved",
          set(meta["treatments"]) == {"RemActive", "RemInactive"},
          str(meta["treatments"]))

    fx = instruments.flexibility_around_shock(ev, int(meta["shift_timestep"]))
    check("real schema: flexibility sees the planted re-sorting",
          fx.get("switch_fraction") is not None and 0.2 < fx["switch_fraction"] < 0.5,
          f"switch_fraction={fx.get('switch_fraction')}")

    # the activity-proxy fallback must also run
    ev2, meta2 = dornhaus.load(d, min_obs=2, task_from="activity")
    check("activity proxy produces ordinal task levels",
          meta2["n_tasks"] >= 2 and all(t.startswith("act_")
                                        for t in meta2["task_labels"].values()),
          str(sorted(meta2["task_labels"].values())))
    check("activity proxy is labelled as a proxy in meta",
          "PROXY" in meta2["task_definition"], meta2["task_definition"][:40])


def test_illinois(root: Path, rng) -> None:
    """The five portal trials: undirected contacts, ms epochs, tab-delimited."""
    print("\nILLINOIS PORTAL (5 independent colonies)")
    d = root / "data" / "raw" / "illinois_portal"
    d.mkdir(parents=True, exist_ok=True)
    t0 = 1_500_000_000_000                      # a plausible ms epoch
    hubs = {n: [f"t{n}_h{i}" for i in range(5)] for n in (1, 2)}
    for n in (1, 2):
        lines = ["trial\tid1\tid2\tbegin\tend"]
        for k in range(4000):
            a = f"t{n}_b{rng.randrange(80)}"
            b = rng.choice(hubs[n]) if rng.random() < 0.45 else f"t{n}_b{rng.randrange(80)}"
            begin = t0 + k * 20_000             # 20 s apart -> ~22 h span
            lines.append(f"{n}\t{a}\t{b}\t{begin}\t{begin + rng.randrange(500, 9000)}")
        (d / f"trial{n}.txt").write_text("\n".join(lines) + "\n")

    found = illinois.trial_files(d)
    check("found both trial files", len(found) == 2, str([p.name for p in found]))

    log, meta = illinois.load_one(d / "trial1.txt", n_bins=12)
    check("illinois: tab-delimited header parsed", meta["n_individuals"] > 50,
          f"individuals={meta['n_individuals']}")
    check("illinois: every contact emitted both ways (undirected)",
          meta["n_messages"] == 2 * meta["n_contacts"] and meta["directed"] is False,
          f"{meta['n_messages']} msgs / {meta['n_contacts']} contacts")
    check("illinois: ms epochs became real time bins, not one bin",
          len({m["tbin"] for m in log}) == 12, f"{len({m['tbin'] for m in log})} bins")
    check("illinois: span reported in hours, not milliseconds",
          meta["span_hours"] is not None and 20 < meta["span_hours"] < 25,
          f"span={meta['span_hours']} h")

    rep = netstats.structure_report(log, k=5, n_perm=15)
    top = {n for n, _ in rep["top_hubs"][:5]}
    check("illinois: planted hubs recovered in trial1",
          len(top & set(hubs[1])) >= 4, f"recovered {sorted(top)}")
    check("illinois: trial2 hubs do NOT leak into trial1",
          not (top & set(hubs[2])), f"recovered {sorted(top)}")


def test_time_bins(root: Path) -> None:
    """A bin count is not a bin width, and a contact is not an instant.

    Two defects live here and neither raises anything. `--bins 24` over a
    five-day record gives five-hour bins, not hourly ones, and five hours
    straddles the daily activity cycle -- so "the same bees are central across
    bins" is partly a statement about when bees are awake. And an interval
    binned on its start is systematically assigned early. Both are silent, so
    both need a test that would notice.
    """
    print("\nTIME BINS: what a bin IS, and where an interval goes")
    H = 3_600_000                                   # ms per hour
    t0 = 1_500_000_000_000                          # a plausible ms epoch

    # --- unit inference, in every unit and in both polarities -----------------
    for name, per_s in (("s", 1), ("ms", 1_000), ("us", 1_000_000)):
        lo = int(1.5e9 * per_s)
        got = common.infer_time_unit(lo, lo + 120 * 3600 * per_s)
        check(f"time unit: a 120 h record in {name} is read as {name}",
              got["unit"] == name and abs(got["span_hours"] - 120) < 1e-6,
              f"{got}")

    # The magnitude test alone would call this milliseconds. The span test
    # refutes it: no trial in any of these deposits is three seconds long. Two
    # tests that disagree must produce `unknown`, not the more confident of them.
    refuted = common.infer_time_unit(t0, t0 + 3_000)
    check("time unit: an implausible span refutes the magnitude reading",
          refuted["unit"] is None and "disagree" in refuted["why"], f"{refuted}")

    relative = common.infer_time_unit(0.0, 80_000.0)
    check("time unit: relative times and frame counters are refused, not guessed",
          relative["unit"] is None and "epoch" in relative["why"], f"{relative}")

    # Negative polarity: the guard must not be wired to say None to everything.
    ok = common.infer_time_unit(t0, t0 + 120 * H)
    check("time unit: a real ms record is NOT refused",
          ok["unit"] == "ms" and ok["per_hour"] == 3_600_000.0, f"{ok}")

    # --- plan_bins: the five-hour bin, which is the actual defect -------------
    n, w, notes = common.plan_bins(120.0, n_bins=24)
    check("bins: 24 bins over a 5-day record are 5 h each, and it is said so",
          n == 24 and abs(w - 5.0) < 1e-9, f"n={n} width={w}")
    # Exactly one complaint: 5 h does not divide the day, but it is under the
    # width limit, so the second note must NOT fire. A guard that raises every
    # objection it owns every time carries no information.
    check("bins: a 5 h bin is flagged as not dividing the day, and only that",
          len(notes) == 1 and "does not divide 24" in notes[0], f"{notes}")

    n4, w4, notes4 = common.plan_bins(120.0, bin_hours=4)
    check("bins: a 4 h width over 120 h gives 30 bins and no complaint",
          n4 == 30 and w4 == 4.0 and notes4 == [], f"n={n4} w={w4} {notes4}")

    # Negative polarity on the circadian rule: 6 h divides 24 and is not over
    # the width limit, so a guard that fires on everything fails here.
    check("bins: a 6 h width is accepted silently",
          common.plan_bins(120.0, bin_hours=6)[2] == [],
          f"{common.plan_bins(120.0, bin_hours=6)[2]}")
    check("bins: 7 h neither divides the day nor stays under the width limit",
          len(common.plan_bins(120.0, bin_hours=7)[2]) == 2,
          f"{common.plan_bins(120.0, bin_hours=7)[2]}")

    # A width beats a count when both are given: a width is comparable across
    # records of different lengths and a count is not.
    check("bins: --bin-hours overrides --bins",
          common.plan_bins(120.0, n_bins=24, bin_hours=2)[0] == 60,
          f"{common.plan_bins(120.0, n_bins=24, bin_hours=2)}")

    # Under about a day there is no second day to fold bins onto, so the
    # circadian term is not separable at any width. Different note, not silence.
    check("bins: a sub-day record says the confound cannot be folded out",
          any("no second day" in x for x in common.plan_bins(22.0, n_bins=12)[2]),
          f"{common.plan_bins(22.0, n_bins=12)[2]}")

    try:
        common.plan_bins(None, bin_hours=4)
        refused = False
    except SystemExit as exc:
        refused = "could not be identified" in str(exc)
    check("bins: a width in hours is refused when the unit is unknown", refused,
          "otherwise '4 hours' would be 4 frame-counts wearing an hour's name")

    # --- the interval, in the loader ----------------------------------------
    d = root / "data" / "raw" / "illinois_interval"
    d.mkdir(parents=True, exist_ok=True)
    rows = ["trial\tid1\tid2\tbegin\tend"]
    for k in range(60):                              # every 2 h, 1 s each
        b = t0 + k * 2 * H
        rows.append(f"1\tb{k % 12}\tb{(k * 5 + 3) % 12}\t{b}\t{b + 1000}")
    # begins 1 min before the bin 0/1 edge at 5 h, ends 1 min after it. Binned
    # on its start it is in bin 0; binned on its midpoint -- which is exactly
    # the edge -- it is in bin 1.
    rows.append(f"1\tS1\tS2\t{t0 + 5 * H - 60_000}\t{t0 + 5 * H + 60_000}")
    # end before begin: not a short contact, a row we do not understand.
    rows.append(f"1\tR1\tR2\t{t0 + 10 * H}\t{t0 + 10 * H - 5_000}")
    # the last contact STARTS at 119 h and ENDS at 120 h. The record is 120 h
    # long; a window that closes on the last begin would call it 119.
    rows.append(f"1\tZ1\tZ2\t{t0 + 119 * H}\t{t0 + 120 * H}")
    (d / "trial1.txt").write_text("\n".join(rows) + "\n")

    log, meta = illinois.load_one(d / "trial1.txt", n_bins=24)
    check("illinois: the window closes on the last end, not the last begin",
          abs(meta["span_hours"] - 120.0) < 0.01,
          f"span={meta['span_hours']} h -- 119 means the final contact was cut short")
    check("illinois: the ms epoch is identified and a bin gets a width in hours",
          meta["time_unit_inferred"] == "ms" and meta["bin_hours"] == 5.0
          and meta["bins_per_day"] == 4.8,
          f"unit={meta['time_unit_inferred']} bin={meta['bin_hours']} h")
    check("illinois: the 5 h bin carries its circadian warning into meta.json",
          meta["circadian_notes"]
          and any("does not divide 24" in x for x in meta["circadian_notes"]),
          f"{meta['circadian_notes']}")

    by_pair = {(m["sender"], m["recipient"]): m["tbin"] for m in log}
    check("illinois: the boundary-crossing contact is binned on its midpoint",
          by_pair[("S1", "S2")] == 1,
          f"tbin={by_pair[('S1', 'S2')]} -- 0 means it was binned on its start")
    check("illinois: and the crossing is counted, so the choice is auditable",
          meta["contacts_crossing_bin_edge"] == 1,
          f"{meta['contacts_crossing_bin_edge']} crossings of {meta['n_contacts']}")
    check("illinois: a row whose end precedes its begin is counted and set aside",
          meta["rows_with_end_before_begin"] == 1
          and by_pair[("R1", "R2")] == 2,
          f"reversed={meta['rows_with_end_before_begin']} "
          f"tbin={by_pair[('R1', 'R2')]}")
    check("illinois: the longest contact is reported, not just the median",
          meta["max_duration_s"] == 3600.0 and meta["median_duration_s"] == 1.0,
          f"max={meta['max_duration_s']} s median={meta['median_duration_s']} s -- "
          "a contact as long as a bin has an almost arbitrary bin")

    # Negative polarity on the crossing counter: the same file at a width where
    # nothing crosses must report zero, not a number the counter is fond of.
    # 6 h also divides 24 and is not over the width limit, so a clean run here
    # shows the circadian notes are not simply always on.
    _, six = illinois.load_one(d / "trial1.txt", bin_hours=6)
    check("illinois: at 6 h bins nothing crosses an edge, and it says 0",
          six["contacts_crossing_bin_edge"] == 0 and six["n_timebins"] == 20
          and six["bin_hours"] == 6.0 and six["circadian_notes"] is None,
          f"crossings={six['contacts_crossing_bin_edge']} "
          f"bins={six['n_timebins']} notes={six['circadian_notes']}")

    # A whole-day bin is the one width where the circadian phase problem cannot
    # arise -- and it still earns the width warning, because a day-wide bin has
    # averaged the day away before anything is measured. Both are true at once.
    _, day = illinois.load_one(d / "trial1.txt", bin_hours=24)
    check("illinois: a day-wide bin divides the day and is still flagged as wide",
          day["n_timebins"] == 5 and day["bins_per_day"] == 1.0
          and len(day["circadian_notes"]) == 1
          and "activity peak" in day["circadian_notes"][0],
          f"{day['circadian_notes']}")

    # --- gernat: a fixed COUNT over trials of different lengths ---------------
    # This is the version of the same defect that only appears with replicates.
    # Gernat bins within trial, so `--bins 24` gives 2 h bins in a two-day trial
    # and 5 h bins in a five-day one. "The same bees are central in bin 3 of
    # every trial" then compares a two-hour window with a five-hour one, and
    # nothing in the old output said the widths differed.
    g = root / "data" / "raw" / "gernat_bins"
    g.mkdir(parents=True, exist_ok=True)
    grows = ["trial,id1,id2,direction,timestamp"]
    for k in range(40):                                     # trial 1: ~48 h
        grows.append(f"1,a{k % 8},a{(k * 3 + 1) % 8},>,{t0 + int(k * 48 * H / 40)}")
    for k in range(40):                                     # trial 2: ~120 h,
        grows.append(f"2,c{k % 8},c{(k * 3 + 1) % 8},>,"    # a month later
                     f"{t0 + 30 * 24 * H + int(k * 120 * H / 40)}")
    (g / "interactions.csv").write_text("\n".join(grows) + "\n")

    _, gm = gernat.load(g, n_bins=24)
    check("gernat: the time unit is agreed across trials, not pooled across them",
          gm["time_unit_inferred"] == "ms"
          and set(gm["span_hours_by_trial"]) == {"1", "2"}
          and gm["span_hours_by_trial"]["2"] > 2 * gm["span_hours_by_trial"]["1"],
          f"{gm['span_hours_by_trial']} -- a single min-to-max across trials "
          "would have measured the month between the experiments")
    check("gernat: a fixed bin COUNT over unequal trials reports no single width",
          gm["bin_hours"] is None and gm["bins_by_trial"] == {"1": 24, "2": 24},
          f"bin_hours={gm['bin_hours']} -- any number here would be wrong for "
          "at least one trial")

    _, gh = gernat.load(g, n_bins=24, bin_hours=4)
    check("gernat: a fixed WIDTH makes bin k the same duration in every trial",
          gh["bin_hours"] == 4.0 and gh["bins_by_trial"] == {"1": 12, "2": 30}
          and gh["n_timebins"] == 30 and gh["circadian_notes"] is None,
          f"{gh['bins_by_trial']} -- the count varies instead, which is the trade")


def test_degeneracy_guard() -> None:
    """A static per-individual task label must be refused, not scored.

    This is the Charbonneau & Dornhaus case: `ClustDesc` is assigned once per
    ant from the pooled record, so no ant ever changes label. Every instrument
    still returns a number, and every number is an arithmetic restatement of the
    labelling -- DoL 1.0, kappa 1.0, switch_fraction 0.0. The test asserts both
    halves: that the pathology really does produce those values, and that
    run_real_bench refuses to report them.
    """
    import run_real_bench

    print("\nDEGENERACY GUARD")

    # one fixed task per individual, 6 timesteps: the pathological case
    static = [(a, a % 4, t) for t in range(6) for a in range(40)]
    varies, n_ind = run_real_bench.task_variation(static)
    check("static labels detected as zero within-individual variation",
          varies == 0.0 and n_ind == 40, f"varies={varies} n={n_ind}")

    # ...and confirm the instruments really would have been fooled
    rep = instruments.dol_report(static, n_perm=10, n_boot=20)
    st = instruments.role_stability(static, n_windows=3)
    check("the trap is real: static labels score DoL 1.0 and kappa 1.0",
          rep["dol_raw"] > 0.99 and (st["kappa"] or 0) > 0.99,
          f"dol_raw={rep['dol_raw']} kappa={st['kappa']}")
    # And -- the reason the guard has to exist at all -- the permutation null
    # does NOT rescue us here. It shuffles labels across individuals, so it has
    # a low mean, the corrected value stays high, and the verdict reads "strong
    # division of labour" for a colony where nothing was ever observed to vary.
    check("the permutation null does NOT catch static labelling",
          rep["dol_corrected"] > 0.5 and "strong" in rep["verdict"].lower(),
          f"corrected={rep['dol_corrected']} verdict={rep['verdict'][:40]!r} "
          "-- this is why the guard runs BEFORE the instruments")

    # a colony where a third of individuals re-sort must NOT be withheld
    moving = [(a, (a % 4) if (t < 3 or a % 3) else (a + 1) % 4, t)
              for t in range(6) for a in range(40)]
    mvaries, _ = run_real_bench.task_variation(moving)
    check("a colony that re-sorts is not flagged degenerate", mvaries > 0.2,
          f"varies={mvaries}")


def test_missing_values(root: Path, rng) -> None:
    """`NA` is a string, and the validator that catches it must itself be tested.

    Two failures live here, and neither raises.

    The first is treating the literal two-character string `NA` as a behavioural
    category. In the real deposit 250 ants carry `ClustDesc='NA'` -- ants first
    seen after the removal, whom the pre-removal cluster analysis never
    classified. Counted as a value, they become a fifth group that does not
    exist, and every task distribution, division-of-labour number and switch
    count is computed over it.

    The second is subtler: `validate_dornhaus.py` is what stands between us and
    the first failure, and nothing was testing the validator. A guard that has
    silently stopped guarding is worse than no guard, because we would go on
    trusting it. So this builds a fixture with the real header and known planted
    structure, runs the validator over it, and asserts that the checks fire the
    way they are supposed to.
    """
    import io
    import sys
    from contextlib import redirect_stdout

    import validate_dornhaus as vd

    print("\nMISSING VALUES AND THE VALIDATOR")

    check("'NA' reads as missing, 'nurse' does not",
          common.is_missing("NA") and common.is_missing(" na ")
          and common.is_missing("") and not common.is_missing("nurse"),
          "case- and whitespace-insensitive")

    # A fixture shaped like the real deposit: 20 removal colonies plus 2 NoRem,
    # ants first seen post-removal carry ClustDesc='NA', and ActInact is absent
    # on most rows.
    d = root / "data" / "raw" / "dornhaus_missing"
    clusters = ["inactive"] * 41 + ["patroller"] * 33 + ["nurse"] * 17 + ["forager"] * 9
    treats = ["RemActive"] * 5 + ["RemLazy"] * 9 + ["RemRandom"] * 6 + ["NoRem"] * 2
    rows, ant = [], 0
    for ci, treat in enumerate(treats):
        for k in range(50):
            ant += 1
            pre = k < 40                       # the other 10 arrive after the shock
            # drawn, not assigned by `ant % len(clusters)`: a modular assignment
            # interacts with the pre/post split above and can make a whole group
            # (foragers, in the first draft of this fixture) fall entirely among
            # the post-only ants, so the group never appears at all.
            cl = rng.choice(clusters) if pre else "NA"
            # Planted attrition, and deliberately more of it than the 20% the
            # design removes: that is the realistic case and it is the one that
            # must trip the "absence is not removal" check. NoRem colonies lose
            # only the background rate, which is the signature the validator
            # looks for.
            survives = rng.random() >= (0.10 if treat == "NoRem" else 0.35)
            if pre:
                blocks = ("pre", "post1", "post2") if survives else ("pre",)
            else:
                blocks = ("post1", "post2")
            for trial in blocks:
                i = round(rng.uniform(0, 0.9), 3)
                a = round(rng.uniform(0, 1 - i), 3)   # deliberately i + a < 1
                rows.append([f"A{ant}", f"C{ci + 1}", treat, trial, i, a,
                             "NA" if rng.random() < 0.58 else rng.choice(["A", "I"]),
                             cl])
    _write(d / "DryadData_Aug 8 2017.csv",
           ["UAntID", "Colony", "Treat", "Trial", "i", "a", "ActInact", "ClustDesc"],
           rows)

    # --- the loader must drop the NA rows rather than invent a group ----------
    ev, meta = dornhaus.load(d, min_obs=2)
    labels = set(meta["task_labels"].values())
    check("loader does not admit 'NA' as a fifth behavioural group",
          not any(common.is_missing(t) for t in labels) and len(labels) == 4,
          f"tasks={sorted(labels)}")
    # Derive the expectation from the fixture rather than asserting a constant:
    # the loader keeps ants that are classified AND appear in at least two
    # blocks. Note what that second condition costs -- it removes precisely the
    # ants that disappeared after the removal, which is a non-random subset. Any
    # flexibility number computed downstream describes the survivors, and the
    # ants most affected by the shock are the ones least likely to be in it.
    seen = Counter(r[0] for r in rows)
    expect = len({r[0] for r in rows
                  if not common.is_missing(r[7]) and seen[r[0]] >= 2})
    check("loader keeps classified ants seen in at least two blocks",
          meta["n_agents"] == expect,
          f"agents={meta['n_agents']}, fixture implies {expect} of 1100 "
          "(--min-obs 2 drops the ants that vanished after the shock)")

    # --- and the validator must reach the right verdicts on known structure ---
    def status_for(path: Path):
        """Run the validator over `path`, return a fragment -> status lookup."""
        vd.RESULTS.clear()
        argv = sys.argv[:]
        sys.argv = ["validate_dornhaus.py", "--raw", str(path)]
        try:
            with redirect_stdout(io.StringIO()):
                vd.main()
        finally:
            sys.argv = argv
        res = {label: st for st, label, _ in vd.RESULTS}

        def status(fragment: str) -> str | None:
            for label, st in res.items():
                if fragment in label:
                    return st
            return None
        return status

    # --- the right file must be chosen even beside a much bigger wrong one ----
    # This is the failure the first real run hit: a raw root holding several
    # deposits, and a `find_csv` that picked the largest file. It opened a
    # 367,614-row interactions table from another study, printed the Dornhaus
    # citation over it, and was caught only by the header check at the end.
    # Selection is by header now, so a decoy twenty times the size must lose.
    decoy = [[f"t{r % 3}", r, f"b{r % 40}", f"b{(r * 7) % 40}", "AtoB"]
             for r in range(len(rows) * 20)]
    _write(d / "interactions.csv",
           ["trial", "timestamp", "id1", "id2", "direction"], decoy)
    chosen = vd.find_csv(d)
    check("validator picks the file by header, not by size",
          chosen.name != "interactions.csv",
          f"chose {chosen.name} with a decoy {len(decoy):,} rows vs "
          f"{len(rows):,} in the real table")

    status = status_for(d)

    check("validator confirms the 20 removal colonies once NoRem is set aside",
          status("removal treatment") == "PASS", str(status("removal treatment")))
    # NB the fragment has to be "UNRESOLVED: NoRem", not "NoRem" -- the colony
    # count label also mentions NoRem, and matching that one instead would make
    # this test pass while the group went unflagged.
    check("validator flags NoRem as unresolved rather than absorbing it",
          status("UNRESOLVED: NoRem") == "CHECK", str(status("UNRESOLVED: NoRem")))
    check("validator proves ClustDesc is present iff the ant was there pre-removal",
          status("EXACTLY having been present") == "PASS",
          str(status("EXACTLY having been present")))
    check("validator refuses 'NA' as a group label",
          status("every ClustDesc label") == "PASS",
          "'NA' must be excluded before this check, or it fails as an unexpected label")
    check("validator detects that i + a does NOT sum to 1",
          status("i + a sums to 1") == "CHECK",
          "a third undifferentiated category is unaccounted for, so `a` is not 1 - i")
    check("validator reports whether --task-from activity is viable at all",
          status("task-from activity") is not None,
          "an ant needs a parseable `a` in >=2 blocks to show any within-ant change")
    check("validator refuses to equate disappearing with having been removed",
          status("NOT the same as being removed") == "CHECK",
          "planted 35% loss against a 20% removal, so absence confounds removal "
          "with death and non-observation and the check must trip")
    check("validator notices NoRem colonies lose fewer ants, and calls it a hint",
          status("HINT ONLY: NoRem") == "PASS",
          "planted 10% loss in NoRem vs 35% elsewhere -- suggestive of a genuine "
          "control, but n=2 colonies, so it must never be reported as evidence")
    # In this fixture ActInact was drawn independently of i and a, so the honest
    # answer is "not recoverable" and "no threshold works". Asserting only this
    # direction would be weak -- a check hard-wired to say "not recoverable"
    # would pass it -- so the second fixture below plants the opposite.
    check("validator says an independently drawn ActInact is not recoverable",
          status("recoverable from i and a") == "CHECK",
          str(status("recoverable from i and a")))
    check("validator finds no threshold on i or a for an independent ActInact",
          status("no threshold on i or a") == "PASS",
          str(status("no threshold on i or a")))
    check("validator clears missingness that really is unrelated to activity",
          status("missingness is unrelated") == "PASS",
          "the flag was dropped at a fixed rate here, independent of `a`")

    # --- the opposite polarity: structure planted, and it must be found -------
    # Three properties are planted at once, each the mirror of a check that
    # passed above. If any check has quietly become a constant, it fires the
    # same way on both fixtures and one of these fails.
    d2 = root / "data" / "raw" / "dornhaus_derived"
    # 1000 pre-removal ants across the 20 removal colonies, in exactly the
    # published proportions, so excluding NoRem should land on the targets.
    pool = (["inactive"] * 408 + ["patroller"] * 326
            + ["nurse"] * 168 + ["forager"] * 98)
    rng.shuffle(pool)
    rows2, ant, k = [], 0, 0
    for ci, treat in enumerate(treats):
        for _ in range(50):
            ant += 1
            if treat == "NoRem":
                cl = "inactive"      # 2 skewed colonies, pulling every share off
            else:
                cl = pool[k]
                k += 1
            for trial in ("pre", "post1", "post2"):
                i = round(rng.uniform(0, 0.9), 3)
                a = round(rng.uniform(0, 1 - i), 3)
                # 2. the flag is present only for the more active ants, so
                #    missingness is informative rather than a coding convention.
                # 3. and where present it is exactly `a > i`, i.e. derivable.
                flag = ("A" if a > i else "I") if a > 0.30 else "NA"
                rows2.append([f"B{ant}", f"C{ci + 1}", treat, trial, i, a, flag, cl])
    _write(d2 / "DryadData_Aug 8 2017.csv",
           ["UAntID", "Colony", "Treat", "Trial", "i", "a", "ActInact", "ClustDesc"],
           rows2)

    status2 = status_for(d2)
    check("validator recovers a derivable ActInact",
          status2("recoverable from i and a") == "PASS",
          str(status2("recoverable from i and a")))
    check("validator's threshold search finds the cut when one exists",
          status2("no threshold on i or a") == "CHECK",
          "the planted rule IS a threshold on a - i, so the check must trip")
    check("validator catches missingness that tracks activity",
          status2("missingness is unrelated") == "CHECK",
          "the flag was dropped whenever a <= 0.30, so flagged rows are the "
          "active ones and any ActInact-defined subset is biased")
    check("validator confirms when excluding NoRem does close the gap",
          status2("excluding NoRem explains") == "PASS",
          "the 20 removal colonies carry the published shares exactly and the "
          "2 NoRem colonies are all-inactive, so dropping them must move every "
          "group towards its target")


def test_loaders(root: Path, rng) -> dict:
    events_by = {}
    print("\nLOADERS")

    d = fake_beesbook(root, rng)
    ev, meta = beesbook.load(d, n_zones=4, n_bins=50, min_obs=5)
    check("beesbook", meta["n_agents"] == 40 and meta["n_tasks"] == 4,
          f"agents={meta['n_agents']} tasks={meta['n_tasks']} events={meta['n_events']}")
    write_events(ev, meta, root / "data" / "processed" / "beesbook_2018")
    events_by["beesbook_2018"] = (ev, meta)

    d = fake_mersch(root, rng, "real")
    ev, meta = mersch.load(d, min_obs=1)
    # 177, not 180: the fixture has one queen per colony and the default drops
    # them. Queen is a caste, not a task -- left in, three ants are perfectly
    # specialized and never switch, which raises the division-of-labour score for
    # a reason that has nothing to do with the division of labour.
    check("mersch", meta["n_agents"] == 177 and meta["n_tasks"] == 3,
          f"agents={meta['n_agents']} tasks={sorted(meta['task_labels'].values())}")
    check("mersch preferred behavior.csv over the static-group decoy",
          meta["file"] == "behavior.csv", meta["file"])
    # The whole point of the rewrite. Four wide period columns must become four
    # timesteps, not one column read and three discarded.
    check("mersch melted the wide period columns instead of picking one",
          meta["layout"] == "wide (melted)" and meta["n_timesteps"] == 4,
          f"layout={meta['layout']!r} timesteps={meta['n_timesteps']}")
    # Ids restart in every colony in this fixture, so 180 agents can only come
    # out of a namespaced key; an un-namespaced one collapses to 60.
    check("mersch namespaced the ant id on its colony",
          meta["node_key"] == "colony:ant" and meta["n_agents"] == 177,
          f"key={meta['node_key']!r} agents={meta['n_agents']}")
    check("mersch reports the group-change fraction it was chosen for",
          0.4 < meta["share_changed_group"] < 0.95,
          f"{meta['n_ants_changed_group']}/{meta['n_ants_complete']} = "
          f"{meta['share_changed_group']:.1%}")

    # ---- queens: a caste, not a task -------------------------------------
    ev_q, meta_q = mersch.load(d, min_obs=1, queens="keep")
    check("queens are excluded by default and countable",
          meta["queens"] == "exclude" and meta["n_queens"] == 3,
          f"policy={meta['queens']!r} n_queens={meta['n_queens']}")
    check("keeping them puts all 180 ants and a fourth level back",
          meta_q["n_agents"] == 180 and meta_q["n_tasks"] == 4
          and "queen" in meta_q["task_labels"].values(),
          f"agents={meta_q['n_agents']} tasks={sorted(meta_q['task_labels'].values())}"
          " -- the exclusion must be a policy, not a hard-wired filter")
    ev_o, meta_o = mersch.load(d, min_obs=1, queens="only")
    check("'only' isolates them, so 'report separately' is a run and not a footnote",
          meta_o["n_agents"] == 3 and set(meta_o["task_labels"].values()) == {"queen"},
          f"agents={meta_o['n_agents']} tasks={sorted(meta_o['task_labels'].values())}")
    check("the change count is reported both with and without them",
          meta["n_ants_complete_incl_queens"] == meta["n_ants_complete"] + 3,
          f"{meta['n_ants_complete']} without vs "
          f"{meta['n_ants_complete_incl_queens']} with -- if only one number is "
          f"published, nobody can see what the policy did")
    # The queen labelled Q once and N afterwards. A distinct-value count scores
    # her as having changed group; a caste relabel is not task re-allocation, so
    # she must be named rather than absorbed into the switch fraction.
    db = fake_mersch(root, rng, "broken")
    _ev_b, meta_b = mersch.load(db, min_obs=1, queens="keep")
    check("a Q-then-worker relabel is reported, not counted as re-allocation",
          bool(meta_b.get("queen_mixed_warning")) and len(meta_b["queen_mixed_label"]) == 3,
          f"mixed={meta_b.get('queen_mixed_label')}")

    # The same colony stored long must give the same agents, and must NOT claim
    # a melt. A loader that only works on one layout is a loader that will be
    # pointed at the other one by somebody in a hurry.
    dl = fake_mersch(root, rng, "clean")
    ev_l, meta_l = mersch.load(dl, min_obs=1)
    check("mersch reads the long layout too, without melting",
          meta_l["layout"] == "long" and meta_l["n_agents"] == 180
          and meta_l["n_timesteps"] == 4,
          f"layout={meta_l['layout']!r} agents={meta_l['n_agents']} "
          f"timesteps={meta_l['n_timesteps']}")
    check("a colony with no queens does not manufacture a queen warning",
          meta_l["n_queens"] == 0 and not meta_l.get("queen_mixed_warning"),
          f"n_queens={meta_l['n_queens']} -- without this the queen checks could "
          f"be wired to fire on anything")
    write_events(ev, meta, root / "data" / "processed" / "mersch_keller_2013")
    events_by["mersch_keller_2013"] = (ev, meta)

    d = fake_dornhaus(root, rng)
    ev, meta = dornhaus.load(d, min_obs=3)
    check("dornhaus", meta["n_agents"] == 80, f"agents={meta['n_agents']}")
    # Days run 1..14 and the manipulation is on day 8, so the shock is the 8th
    # bin -- dense timestep 7. The loader used to report the raw day number, 8,
    # which put the pre/post boundary one day late in every flexibility number.
    check("dornhaus found the shock from the phase column",
          meta["shift_timestep"] == 7,
          f"shift={meta['shift_timestep']} (dense index of day 8)")
    check("dornhaus sees within-individual task change",
          meta["task_varies_within_agent"] > 0.2,
          f"varies={meta['task_varies_within_agent']}")
    write_events(ev, meta, root / "data" / "processed" / "charbonneau_dornhaus_2017")
    events_by["charbonneau_dornhaus_2017"] = (ev, meta)

    d = fake_gernat(root, rng)
    log, lmeta = gernat.load(d, n_bins=12)
    check("gernat", lmeta["n_individuals"] == 60 and lmeta["directed"],
          f"n={lmeta['n_individuals']} msgs={lmeta['n_messages']}")
    out = root / "data" / "processed" / "gernat_trophallaxis"
    gernat.write_log(log, lmeta, out)
    back, _ = gernat.read_log(out)
    check("gernat round-trips through CSV", len(back) == len(log))
    check("gernat wrote time bins", len({m["tbin"] for m in back}) > 1,
          f"{len({m['tbin'] for m in back})} bins")
    return events_by


def test_instruments(events_by: dict) -> None:
    print("\nINSTRUMENTS")

    ev, meta = events_by["mersch_keller_2013"]
    rep = instruments.dol_report(ev, n_perm=20, n_boot=40)
    check("specialists score above the null",
          rep["dol_corrected"] > 0.10 and (rep["dol_z_vs_null"] or 0) > 3,
          f"raw={rep['dol_raw']} null={rep['dol_null_mean']} "
          f"corr={rep['dol_corrected']} z={rep['dol_z_vs_null']}")
    check("bootstrap CI is finite and brackets the raw value",
          rep["dol_ci95"] is not None and rep["dol_ci95"][0] <= rep["dol_raw"] <= rep["dol_ci95"][1],
          str(rep["dol_ci95"]))

    # a colony with no structure at all: identical agents choosing at random
    rng = random.Random(7)
    noise = [(a, rng.randrange(4), t) for t in range(60) for a in range(100)]
    nrep = instruments.dol_report(noise, n_perm=20, n_boot=40)
    check("random agents are NOT called specialized",
          nrep["dol_corrected"] < 0.02,
          f"raw={nrep['dol_raw']} null={nrep['dol_null_mean']} corr={nrep['dol_corrected']}")
    check("random agents get the 'not distinguishable' verdict",
          nrep["dol_corrected"] < 0.02, nrep["verdict"][:48])
    check("the raw number would have been misleading",
          nrep["dol_raw"] > nrep["dol_corrected"],
          f"raw {nrep['dol_raw']} vs corrected {nrep['dol_corrected']} "
          "-- this gap IS the bias the correction removes")

    # Role stability gets its own two fixtures rather than borrowing the Mersch
    # events. It used to run on `ev`, and that worked only while the Mersch
    # fixture happened to plant 90%-stable roles. It no longer does: in the real
    # deposit 183 of the 392 fully-labelled ants (47%) change group across the
    # four periods, so the fixture models a colony that RE-ALLOCATES -- not at
    # the 74% first claimed here, which counted blank cells as a level, but
    # enough that a kappa near 1 on this fixture would
    # now be the bug rather than the pass. Borrowing one fixture for two
    # properties means a change in either silently redefines the other test.
    srng = random.Random(5)
    stable = [(a, a % 4 if srng.random() < 0.95 else srng.randrange(4), t)
              for t in range(60) for a in range(100)]
    st = instruments.role_stability(stable, n_windows=4)
    check("stable roles give high kappa", (st["kappa"] or 0) > 0.5, f"kappa={st['kappa']}")
    nst = instruments.role_stability(noise, n_windows=4)
    check("random roles give kappa near zero", abs(nst["kappa"] or 1) < 0.15,
          f"kappa={nst['kappa']}")
    # And the middle case, which is the one this project actually cares about:
    # a colony that is neither rigid nor random must land between them. If the
    # Mersch events scored like the stable fixture, the melt would have collapsed
    # the four periods back into one and every ant would look constant by
    # construction -- exactly the failure the wide-format bug produced.
    mst = instruments.role_stability(ev, n_windows=4)
    check("a re-allocating colony lands between rigid and random",
          (nst["kappa"] or 0) + 0.1 < (mst["kappa"] or 0) < (st["kappa"] or 1),
          f"mersch kappa={mst['kappa']} vs stable {st['kappa']} and random {nst['kappa']}")

    ev, meta = events_by["charbonneau_dornhaus_2017"]
    fx = instruments.flexibility_around_shock(ev, int(meta["shift_timestep"]))
    check("flexibility runs on the shock dataset", "error" not in fx, str(fx.get("error", "")))
    check("about a third of individuals switched task",
          fx["switch_fraction"] is not None and 0.15 < fx["switch_fraction"] < 0.55,
          f"switch_fraction={fx['switch_fraction']} response_tvd={fx['response_tvd']}")

    lg = instruments.to_bench_log(ev)
    check("events convert back to a bench-shaped log",
          len(lg) == meta["n_timesteps"] and len(lg[0]) == meta["n_agents"],
          f"{len(lg)} x {len(lg[0])}")


def test_gernat_join(root: Path, rng) -> None:
    """Three tables joined is where correct files make an incorrect result.

    Each failure here runs to completion and returns plausible numbers. Reused
    ids give you chimeric bees whose centrality is an artefact of how many trials
    their id appears in. A global time binning over disjoint trial clocks turns
    "are hubs stable over time" into "do different colonies occupy different
    bins". An unrecognised direction token silently converts a directed food-flow
    log into an undirected one while the metadata still claims direction.
    """
    import io
    import sys
    from contextlib import redirect_stdout

    import validate_gernat as vg

    print("\nGERNAT: THREE TABLES, ONE JOIN")

    def run(path: Path) -> dict[str, tuple[str, str]]:
        """Run the validator over a fixture and return {label: (status, detail)}."""
        vg.RESULTS.clear()
        argv = sys.argv[:]
        sys.argv = ["validate_gernat.py", "--raw", str(path)]
        try:
            with redirect_stdout(io.StringIO()):
                vg.main()
        finally:
            sys.argv = argv
        return {label: (st, detail) for st, label, detail in vg.RESULTS}

    def find(res: dict, fragment: str) -> tuple[str, str]:
        for label, pair in res.items():
            if fragment in label:
                return pair
        return ("", "")

    d = fake_gernat_three_trials(root, rng)
    res = run(d)

    def status(fragment: str) -> str | None:
        return find(res, fragment)[0] or None

    check("validator catches ids reused across trials",
          status("unique across trials") == "CHECK",
          "ids restart at b0 in every trial, so pooling merges different bees")
    check("validator catches disjoint trial clocks",
          status("share one clock") == "CHECK",
          "the trials are separated by a gap, so one global binning would give "
          "each trial its own block of bins")
    check("validator catches a direction token the loader cannot decode",
          status("every direction value") == "CHECK",
          "'AtoB' is not in the recognised set, and the fallback would emit every "
          "event symmetrically while still reporting directed=True")
    check("validator confirms the cross-file clock and id space",
          status("after its recorded time_of_death") == "PASS",
          "the fixture never lets a bee interact after it dies, so this must pass; "
          "if it fails the join is wrong and neither file can be trusted against "
          "the other")
    check("validator reports caste as a static attribute, not a task",
          status("static per-individual attribute") is not None,
          "a caste that never varies makes DoL maximal by construction")

    # --- and the loader must not commit the errors the validator described ---
    with redirect_stdout(io.StringIO()):
        log, meta = gernat.load(d, n_bins=12)
    check("loader namespaces node ids by trial",
          meta["node_key"] == "trial:id"
          and all(":" in m["sender"] for m in log),
          f"node_key={meta['node_key']} -- without this, b0 of t1 and b0 of t3 "
          f"are one node with both their edges")
    check("loader does not claim direction it could not decode",
          meta["directed"] is False and meta["n_undecodable_direction"] > 0,
          f"directed={meta['directed']}, undecodable={meta['n_undecodable_direction']}")
    # The real test of per-trial binning: every trial must span the FULL bin
    # range. Under global binning each trial would occupy its own narrow block.
    bins_by_trial = defaultdict(set)
    for m in log:
        bins_by_trial[m["sender"].split(":")[0]].add(m["tbin"])
    check("loader bins time within trial, not across trials",
          all(len(v) == 12 for v in bins_by_trial.values()),
          {k: len(v) for k, v in bins_by_trial.items()})

    # Deaths in this fixture fall in the middle of the window, so the censoring
    # check must NOT fire. Without this half, a censoring check hard-wired to
    # CHECK would look correct on the censored fixture below.
    st, detail = find(res, "observed death, not censoring")
    check("validator does not cry censoring when deaths are spread through the trial",
          st == "PASS",
          "deaths are drawn uniformly across the middle of each window here")
    check("a PASS carries pass prose, not the failure warning",
          st == "PASS" and "censoring stamp" not in detail and detail != "",
          f"detail printed under the PASS was: {detail[:90]!r}")

    st, detail = find(res, "corroborated by the interaction record")
    check("validator confirms death times that DO track when the bee vanished",
          st == "PASS",
          f"in this fixture a bee's interactions are truncated at its death, so the "
          f"lag must come out far below the shuffled null. detail: {detail[:110]!r}")

    # ---- the other polarity: staggered ids, one clock, and censored deaths ----
    res2 = run(fake_gernat_censored(root, rng, "constant"))

    st, detail = find(res2, "unique across trials")
    check("validator counts ids in >=2 trials, not ids in ALL trials",
          st == "CHECK" and "30 of 80" in detail,
          f"t1/t2 share 20 ids and t2/t3 share 10, and NO id is in all three. "
          f"An all-trials intersection reports 0 here and PASSes. detail: {detail[:120]!r}")

    st, detail = find(res2, "observed death, not censoring")
    check("validator catches a time_of_death that is really trial-end censoring",
          st == "CHECK",
          "every bee in this fixture 'dies' at the declared end of its trial, which "
          "is an end-of-observation stamp, not mortality -- and the real deposit "
          "carries one for 2,777 of 2,777 bees")

    st, _ = find(res2, "after its recorded time_of_death")
    check("the cross-file death test is reported as near-vacuous under censoring",
          st == "PASS" and "vacuous" in find(res2, "after its recorded")[1],
          "no event can fall after the end of the record, so this PASS is arithmetic "
          "rather than evidence, and must say so")

    st, detail = find(res2, "corroborated by the interaction record")
    check("validator catches death times that do not track when the bee vanished",
          st == "CHECK",
          "a third of these bees stop appearing early and are given a death time "
          "drawn independently of that. The value is in the right range and the "
          "right units and correlated with nothing; only the comparison against "
          f"the interaction record can see it. detail: {detail[:110]!r}")

    st, detail = find(res2, "share one clock")
    check("validator confirms a shared clock when the trials do overlap",
          st == "PASS" and "do not overlap" not in detail,
          f"all three trials run over the same window here; detail: {detail[:90]!r}")

    st, detail = find(res2, "every direction value")
    check("validator confirms decodable direction tokens",
          st == "PASS" and "does not recognise" not in detail,
          f"'>' and '<' are both in the recognised set; detail: {detail[:90]!r}")

    # ---- and the polarity WITHIN the censoring finding ----
    # "80% of this column is censoring" is a warning. "censored == (t == end + 1)"
    # is a usable fact -- it turns the deposit into a survival table that can be
    # decoded exactly. The validator claims the second whenever every overshoot is
    # the same constant, and that is a strong enough claim that it needs the case
    # where it is FALSE tested too. Otherwise a note hard-wired to fire would look
    # correct here and would quietly bless a column with no rule behind it.
    st, detail = find(res2, "censoring stamp is a single constant")
    check("validator spots an exactly decodable censoring sentinel",
          st == "?" and "end + 1s" in detail,
          f"every survivor here is stamped at exactly end + 1, so the indicator is "
          f"a biconditional and not a tolerance. detail: {detail[:120]!r}")

    res3 = run(fake_gernat_censored(root, rng, "scatter"))
    st_c, _ = find(res3, "censoring stamp is a single constant")
    st_s, detail = find(res3, "overshoot takes several different values")
    check("validator does not offer an exact indicator when the overshoot scatters",
          st_c == "" and st_s == "?",
          f"survivors here are stamped at end + 1..5, so no rule separates censoring "
          f"from measurement error and the exact-indicator note must stay silent. "
          f"constant-note status={st_c!r}, scatter-note detail: {detail[:100]!r}")
    check("the censoring CHECK still fires when the overshoot scatters",
          find(res3, "observed death, not censoring")[0] == "CHECK",
          "the pile-up at the boundary is what makes it censoring; whether the "
          "sentinel is decodable is a separate question and must not suppress it")


def test_queen_marking(root: Path, rng) -> None:
    """A queen is a hub by caste. The deposit says which bee she is; use it.

    Gernat's `bees.csv` names 3 queens among 2,777 bees, and a queen in a
    trophallaxis network is fed continuously by her retinue. If she is left in
    and unlabelled, "this colony has stable central individuals" can be a
    restatement of "this colony has a queen" -- and the information needed to
    tell those apart was in the deposit the whole time.

    So five polarities, because a mark that always fires and a mark that never
    lands are the same kind of useless:

      hub      a queen fed by a retinue -- marked, rank 1, a large delta, and a
               note that says quote both numbers;
      ordinary a queen fed like anyone else -- marked, small delta, and the note
               that says the structure does not rest on her. This is the check
               that stops the guard from being hard-wired to shout;
      mismatch the queen keyed in an id space the log never uses -- the join
               fails, and it has to SAY so, because every number computed on an
               empty mark is correct and reads as a clean negative result;
      levels   nurse/forager and no queen at all -- nobody marked, and the report
               names the levels it saw rather than electing the rarest one;
      trap     a caste level `queenless` -- NOT a queen, because the match is
               exact and both "queenless" and "queenright" contain "queen".
    """
    import io
    from contextlib import redirect_stdout

    print("\nQUEENS: A HUB BY CASTE IS NOT A HUB BY ORGANISATION")

    def run(d: Path) -> tuple[list, dict, dict, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            log, meta = gernat.load(d)
            rep = netstats.structure_report(log, k=10, n_perm=5,
                                            special=meta.get("special_nodes"))
        return log, meta, rep, buf.getvalue()

    d_hub = fake_gernat_queen(root, rng, "hub", retinue=0.5)
    _, meta, rep, said = run(d_hub)
    sp = rep.get("special_nodes", {})
    check("a queen named in bees.csv is joined onto the interaction log",
          meta.get("n_queens_marked") == 1 and sp.get("n_present") == 1,
          f"marked={meta.get('n_queens_marked')} present={sp.get('n_present')} "
          f"labels={sp.get('labels')} -- keyed trial:id on both sides")
    check("the loader says out loud that she is kept, not dropped",
          "NOT dropped" in said,
          "dropping her silently would be its own unrecorded decision")
    check("a queen fed by a retinue comes out as the top hub",
          sp.get("ranks", {}).get("t1:q0", {}).get("rank") == 1,
          f"rank={sp.get('ranks', {}).get('t1:q0', {})} -- half of all "
          f"trophallaxis in this fixture ends at her, by construction")
    check("centralization is reported with her and without her",
          sp.get("centralization_without") is not None
          and sp.get("delta", 0) < -0.02,
          f"with={sp.get('centralization_with')} "
          f"without={sp.get('centralization_without')} "
          f"delta={sp.get('delta')} share={sp.get('share_of_messages')}")
    check("and the note demands both numbers rather than one",
          "Quote both figures" in sp.get("note", ""),
          f"note: {sp.get('note', '')[:90]!r}")

    d_ord = fake_gernat_queen(root, rng, "ordinary", retinue=1 / 61,
                              donates=True)
    _, meta2, rep2, _ = run(d_ord)
    sp2 = rep2.get("special_nodes", {})
    check("a queen who is NOT preferentially fed is still marked",
          meta2.get("n_queens_marked") == 1 and sp2.get("n_present") == 1,
          "the mark is a caste, not a finding; it must not depend on the result")
    check("...and the guard stays quiet, which is the negative polarity",
          abs(sp2.get("delta", 1.0)) < 0.02
          and "does not rest on them" in sp2.get("note", ""),
          f"delta={sp2.get('delta')} share={sp2.get('share_of_messages')}. A "
          f"guard that fires in both fixtures would carry no information; this "
          f"is the run that proves it is reading the data")
    check("her delta is judged against removing one arbitrary bee, not zero",
          sp2.get("n_null_draws", 0) > 0
          and sp2["delta_null_range"][0] <= sp2["delta"] <= sp2["delta_null_range"][1],
          f"delta={sp2.get('delta')} null range={sp2.get('delta_null_range')} "
          f"median={sp2.get('delta_null_median')} over "
          f"{sp2.get('n_null_draws')} draws -- removing anybody moves "
          f"centralization, so a bare delta cannot tell you it was her")
    check("...while the retinue-fed queen falls outside that same range",
          sp.get("n_null_draws", 0) > 0
          and not (sp["delta_null_range"][0] <= sp["delta"]
                   <= sp["delta_null_range"][1])
          and "outside the range" in sp.get("note", ""),
          f"delta={sp.get('delta')} vs null range={sp.get('delta_null_range')} "
          f"-- the null has to be clearable, or it is just a way of never "
          f"reporting anything")

    d_bad = fake_gernat_queen(root, rng, "mismatch", retinue=0.5,
                              id_space="mismatch")
    _, meta3, rep3, said3 = run(d_bad)
    sp3 = rep3.get("special_nodes", {})
    check("a mark that lands on nobody is reported as a FAILED JOIN",
          bool(sp3.get("join_failed")) and sp3.get("n_present") == 0
          and meta3.get("n_queens_marked") == 0,
          f"join_failed={str(sp3.get('join_failed'))[:80]!r}")
    check("...and the loader refuses to let it read as a negative result",
          "id spaces disagree" in said3
          and "made no difference" in said3,
          "every downstream number here is computed correctly on an empty set, "
          "which is exactly why it has to be said before they are read")

    d_lev = fake_gernat_three_trials(root, rng)
    _, meta4, _, said4 = run(d_lev)
    src = meta4.get("caste_source", {})
    check("nurse/forager and no queen means nobody is marked",
          meta4.get("n_queens_marked") == 0 and meta4.get("special_nodes") is None,
          f"levels={sorted(src.get('levels') or {})}")
    check("...and it names the levels it saw instead of electing the rarest one",
          "nurse" in (src.get("why") or "") and "forager" in (src.get("why") or ""),
          f"why: {(src.get('why') or '')[:100]!r} -- a 'smallest level wins' rule "
          f"would invent a queen in any unbalanced column")

    d_trap = fake_gernat_queen(root, rng, "trap", caste="queenless", retinue=0.5)
    _, meta5, rep5, _ = run(d_trap)
    check("`queenless` is not a queen",
          meta5.get("n_queens_marked") == 0
          and "special_nodes" not in rep5,
          "the match is exact on the normalized value, not a substring test: "
          "'queenless' and 'queenright' are ordinary words in this literature "
          "and both contain 'queen'")


def fake_gernat_scale(root: Path, n_rows: int) -> Path:
    """A deposit-shaped interactions table of a given size, for timing only.

    Deliberately the real column shape and the real timestamp unit -- seconds
    since the epoch, three trials months apart, a decodable direction token --
    because a cost that only appears once trials and absolute clocks are involved
    is exactly the cost the small fixtures were blind to.
    """
    d = root / "data" / "raw" / f"gernat_scale_{n_rows}"
    rng = random.Random(3)
    base = 1_466_140_980
    rows = []
    for i in range(n_rows):
        tr = f"20{16 + i % 3}-01"
        t = base + (i % 3) * 10_000_000 + rng.randrange(0, 5 * 24 * 3600)
        a, b = rng.randrange(2000), rng.randrange(2000)
        if a != b:
            rows.append([tr, t, a, b, ">"])
    _write(d / "interactions.csv",
           ["trial", "timestamp", "id1", "id2", "direction"], rows)
    return d


def test_loader_scale(root: Path) -> None:
    """The loader must be linear in rows, and nothing else here would notice.

    This check exists because of a bug that every other test passed. The binning
    loop read `span.get(tr, (min(times), max(times)))`. Python evaluates a `.get`
    default eagerly -- always, whether or not the key is present -- so a full scan
    of every timestamp ran once per message, and the loop was O(n^2) inside a
    fallback that almost never fires.

    On a four-thousand-row fixture that is microseconds and invisible. On the
    real 11 MB interactions table it was tens of minutes at 100% CPU with flat
    memory and, because the output was piped, no printing: a defect whose
    signature is indistinguishable from "this is a big file, be patient". It was
    caught by noticing that eleven megabytes should not take four minutes, which
    is not a mechanism anyone should have to rely on twice.

    So: a real-shaped table large enough that a quadratic term dominates, and a
    ceiling loose enough that only a change of complexity can breach it.
    """
    import time

    print("\nSCALE: A COST THAT ONLY APPEARS ON THE REAL FILE")
    times = {}
    # Sized up from 25k/100k after the first run: at 0.12s the small leg was
    # mostly interpreter noise, and the ratio came out 6.2 against a ceiling of
    # 8 -- not enough headroom for a timing check to be trusted on a busy
    # machine. Bigger legs cost about a second and buy a stable denominator.
    for n in (50_000, 200_000):
        d = fake_gernat_scale(root, n)
        t0 = time.time()
        buf = io.StringIO()
        with redirect_stdout(buf):
            log, meta = gernat.load(d, bin_hours=4)
        times[n] = time.time() - t0
        check(f"{n:,} rows load and bin correctly",
              len(log) > n * 0.9 and meta.get("bin_hours") == 4.0,
              f"{len(log):,} log entries in {times[n]:.2f}s "
              f"({len(log) / max(times[n], 1e-9):,.0f} rows/s)")

    check("200,000 rows load in under 20 seconds",
          times[200_000] < 20.0,
          f"{times[200_000]:.2f}s. The quadratic version needed about 145s for a "
          f"QUARTER of these rows, so the ceiling sits an order of magnitude above "
          f"the observed cost and far below the regression -- it can only be "
          f"breached by a change of complexity, not by a slow afternoon")
    ratio = times[200_000] / max(times[50_000], 1e-9)
    check("quadrupling the rows does not multiply the time by sixteen",
          ratio < 8.0,
          f"4x rows -> {ratio:.1f}x time. Linear is ~4x, quadratic ~16x; this "
          f"names the SHAPE of the cost, which an absolute ceiling alone cannot")


def test_mersch_deposit(root: Path, rng) -> None:
    """validate_mersch.py against three plantings of the same colony.

    The one check that matters most here is not about ants at all. Two variable
    roles resolving to the same column is a bug in every dataset, forever, and it
    is invisible: nothing raises, the run completes, and the number that comes out
    is at ceiling because one quantity has silently become a function of the
    other. It was found in this loader by running the real header through the
    matcher rather than by trusting it, so the fixture carries the real header and
    the test requires both that the collision fires on it and that it stays quiet
    on a header where the roles are genuinely distinct.
    """
    import io
    from contextlib import redirect_stdout

    import validate_mersch as vm

    def run(path: Path) -> dict[str, tuple[str, str]]:
        vm.RESULTS.clear()
        argv = sys.argv[:]
        sys.argv = ["validate_mersch.py", "--raw", str(path)]
        try:
            with redirect_stdout(io.StringIO()):
                vm.main()
        finally:
            sys.argv = argv
        return {label: (st, detail) for st, label, detail in vm.RESULTS}

    def find(res: dict, fragment: str) -> tuple[str, str]:
        for label, pair in res.items():
            if fragment in label:
                return pair
        return ("", "")

    print("\nMERSCH: FOUR PERIODS, ONE COLUMN")

    real = run(fake_mersch(root, rng, "real"))
    clean = run(fake_mersch(root, rng, "clean"))
    broken = run(fake_mersch(root, rng, "broken"))

    # ---- the general invariant, both polarities
    st, detail = find(real, "no two variable roles bind to the same column")
    check("validator refuses a header where two roles take one column",
          st == "CHECK" and "group_period1" in detail,
          f"the real header binds both task and day to group_period1 and nothing "
          f"raises; that is the bug. detail: {detail[:90]!r}")
    check("the same check passes on a header where the roles are distinct",
          find(clean, "no two variable roles bind to the same column")[0] == "PASS",
          "the long layout has a real `day` column, so nothing collides -- without "
          "this the collision check could be hard-wired to fire and look right")

    # ---- and the loader itself must refuse, not just the validator
    from loaders.common import ColumnCollision, pick_columns
    raised = False
    try:
        pick_columns(MERSCH_BEHAVIOR_HEADER, mersch.CANDIDATES,
                     optional=("colony", "day"))
    except ColumnCollision:
        raised = True
    check("pick_columns refuses the collision rather than returning two answers",
          raised,
          "a validator that reports the bug while the loader proceeds anyway "
          "leaves the bug in the numbers")

    # ---- wide vs long
    check("validator names the wide layout and counts the discarded periods",
          find(real, "task label is stored long")[0] == "CHECK"
          and "4 columns" in find(real, "task label is stored long")[1],
          find(real, "task label is stored long")[1][:90])
    check("validator is quiet about layout when the file is already long",
          find(clean, "task label is stored long")[0] == "PASS")

    # ---- the missingness gate on the change fraction
    st_r, _ = find(real, "change fraction")
    st_b, det_b = find(broken, "change fraction is not an artefact")
    check("no missingness warning when the period columns are complete",
          st_r == "?",
          "with no NA anywhere, 'more than one distinct value' cannot be picking "
          "up an absence, so the change fraction may travel")
    check("validator catches attrition being read as flexibility",
          st_b == "CHECK",
          f"NAs planted for ants that stop appearing must move the change count. "
          f"detail: {det_b[:90]!r}")

    # ---- direction of the flow
    check("validator confirms N -> C -> F when the flow runs that way",
          find(real, "forward along nurse")[0] == "PASS")
    check("validator disagrees when the flow runs backwards",
          find(broken, "forward along nurse")[0] == "CHECK",
          "age polyethism is the published result, so a reversed flow means the "
          "period columns are not in chronological order or N/C/F do not mean "
          "what we take them to mean -- either way it is not a finding")
    check("validator flags a task level nobody documented",
          find(broken, "four documented castes")[0] == "CHECK",
          find(broken, "four documented castes")[1][:80])

    # ---- id reuse
    check("validator catches tag ids reused across colonies",
          find(real, "identifies an ant on its own")[0] == "CHECK")
    check("validator does not invent reuse when ids are globally unique",
          find(clean, "identifies an ant on its own")[0] == "PASS")

    # ---- the README's claim, tested
    check("validator confirms M == M^T when the matrices are symmetric",
          find(real, "row names are symmetrical")[0] == "PASS")
    check("validator catches an asymmetric matrix",
          find(broken, "row names are symmetrical")[0] == "CHECK",
          "if the matrix is not symmetric then row i is not ant i and every edge "
          "is attached to the wrong pair")
    check("validator catches a matrix short by exactly one row",
          find(broken, "square with the ids its header")[0] == "CHECK"
          and "short by exactly one row" in find(broken, "square with the ids its header")[1],
          find(broken, "square with the ids its header")[1][:100])

    # ---- the file that is almost like its siblings
    check("validator catches the one heatmap without a header",
          find(real, "every heatmap file carries the same header")[0] == "CHECK")
    check("validator is quiet when every heatmap is headed",
          find(clean, "every heatmap file carries the same header")[0] == "PASS")

    # ---- the colony vocabularies, which decide which ants are which
    #
    # The real deposit names its colonies 4, 18, 21, 29, 58 and 78 in
    # behavior.csv and col1..col6 in the matrix filenames. The intersection is
    # not empty -- it is exactly {"4"}, by coincidence -- so a guard that only
    # fires on a TOTAL mismatch let it through and reported "57 of 102 matrix ids
    # have no task label" about the fourth matrix paired with a colony that
    # happens to be called 4. That is one colony's graph against another colony's
    # labels, and it reads exactly like a finding.
    #
    # So this fixture reproduces the coincidence rather than a clean mismatch:
    # colony 1 keeps its name and 2 and 3 are renamed out of the behaviour
    # vocabulary, leaving an overlap of one.
    import shutil as _sh
    src = fake_mersch(root, rng, "real")
    shifted = root / "data" / "raw" / "mersch_shifted"
    if shifted.exists():
        _sh.rmtree(shifted)
    _sh.copytree(src, shifted)
    for p in list(shifted.rglob("network_col*_day*.txt")):
        n = p.name.replace("col2_", "col9_").replace("col3_", "col8_")
        if n != p.name:
            p.rename(p.with_name(n))
    shifted_res = run(shifted)

    st, detail = find(shifted_res, "label colonies from the same vocabulary")
    check("validator refuses a join when the colony vocabularies differ",
          st == "CHECK" and "coincidence of numbering" in detail,
          f"an overlap of one label out of three is not a correspondence. "
          f"detail: {detail[:100]!r}")
    check("and does not report an unlabelled-ant count it cannot compute",
          find(shifted_res, "every ant in a network matrix has a task label")[0] == "",
          "the number was the bug -- suppressing it is the fix, not softening it")
    check("it says out loud that those two counts were withheld",
          find(shifted_res, "were NOT computed")[0] == "?",
          "a missing check is invisible; a withheld one is a to-do")
    check("the same check passes when both files use one vocabulary",
          find(real, "label colonies from the same vocabulary")[0] == "PASS",
          "without this the vocabulary guard could be hard-wired to fire")
    check("with the vocabularies aligned the join runs and finds no orphans",
          find(real, "every ant in a network matrix has a task label")[0] == "PASS",
          find(real, "every ant in a network matrix has a task label")[1][:80])

    # ---- housekeeping that a loader can trip over
    check("validator excludes the __MACOSX resource forks",
          find(real, "AppleDouble")[0] == "?")
    check("validator identifies which period the static group column came from",
          "reproduces group_period1 exactly" in find(real, "built on one assessment")[1],
          find(real, "built on one assessment")[1][:90])


def test_nested_archives(root: Path) -> None:
    """A zip inside a zip: does the fetcher actually get to the data?

    This is the check that would have caught the Mersch bundle. The Dryad
    download is a zip whose useful contents are themselves a `tracking_data.zip`,
    and the old one-level `unzip` left that second archive sitting on disk. The
    folder was not empty, so the disk check passed; the download succeeded, so
    the counter said complete; and the only way to find out was to point a loader
    at it days later. A test that only asserts the outer zip opened would repeat
    exactly that mistake, so the assertion here is about the file at the BOTTOM.
    """
    print("\nNESTED ARCHIVES")
    import zipfile
    import fetch_data

    d = root / "archives"
    (d / "build" / "tracking").mkdir(parents=True, exist_ok=True)
    (d / "build" / "tracking" / "positions.csv").write_text("ant,x,y\n1,0,0\n")
    inner = d / "build" / "tracking_data.zip"
    with zipfile.ZipFile(inner, "w") as z:
        z.write(d / "build" / "tracking" / "positions.csv", "tracking/positions.csv")
    (d / "build" / "readme.txt").write_text("outer\n")
    outer = d / "dryad_bundle.zip"
    with zipfile.ZipFile(outer, "w") as z:
        z.write(inner, "tracking_data.zip")
        z.write(d / "build" / "readme.txt", "readme.txt")

    out = d / "out"
    out.mkdir()
    done = fetch_data.unzip(outer, out)
    check("outer archive expanded", (out / "readme.txt").exists())
    check("nested archive expanded too", (out / "tracking" / "positions.csv").exists(),
          "one level of recursion is the whole difference between "
          "'downloaded' and 'readable'")
    check("both archives reported as expanded", len(done) == 2,
          f"{[p.name for p in done]}")

    # Re-run. The outer marker now exists, and the naive early-return on that
    # marker is precisely how a resumed run inherits the original bug: the outer
    # zip having been expanded once says nothing about the inner one.
    (out / "tracking" / "positions.csv").unlink()
    fetch_data.unzipped_marker(out / "tracking_data.zip").unlink()
    done2 = fetch_data.unzip(outer, out)
    check("a re-run still descends past an already-expanded outer zip",
          (out / "tracking" / "positions.csv").exists(),
          f"visited {[p.name for p in done2]}")

    # And the reverse polarity: with nothing expanded, the packed-archive scan
    # must SEE the archive. A warning that cannot fire is not a warning.
    fresh = d / "fresh"
    fresh.mkdir()
    shutil.copy2(outer, fresh / "dryad_bundle.zip")
    found = fetch_data.archives_under(fresh)
    check("packed archives are visible to the disk-level scan",
          [p.name for p in found] == ["dryad_bundle.zip"]
          and not fetch_data.unzipped_marker(found[0]).exists(),
          f"{[p.name for p in found]}")

    # AppleDouble shadows are named exactly like the real files. `is_zipfile`
    # already rejects them, but the name filter has to hold independently: the
    # scan reports what is UNEXPANDED, and a garbage entry there sends someone
    # looking for a bug in a file that was never real.
    macos = fresh / "__MACOSX"
    macos.mkdir()
    shutil.copy2(outer, macos / "._dryad_bundle.zip")
    check("the scan ignores __MACOSX resource forks",
          [p.name for p in fetch_data.archives_under(fresh)] == ["dryad_bundle.zip"],
          f"{[p.name for p in fetch_data.archives_under(fresh)]}")

    # Path traversal. The old guard compared strings, so a sibling directory
    # whose name merely starts with the destination's passed it.
    check("a sibling path that shares a name prefix is not 'inside'",
          not fetch_data._within(Path("/data/raw/mersch_evil"), Path("/data/raw/mersch")),
          "string prefix != path prefix")
    check("a genuine child still is",
          fetch_data._within(Path("/data/raw/mersch/behavior.csv"), Path("/data/raw/mersch")))

    evil = d / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escaped.txt", "no")
    raised = False
    try:
        fetch_data.unzip(evil, out)
    except RuntimeError:
        raised = True
    check("traversal member refused", raised and not (d / "escaped.txt").exists())


def test_netstats(root: Path) -> None:
    print("\nSTRUCTURE")
    log, _ = gernat.read_log(root / "data" / "processed" / "gernat_trophallaxis")
    rep = netstats.structure_report(log, k=6, n_perm=15)
    check("centralization computed", 0.0 <= rep["centralization"] <= 1.0,
          f"cen={rep['centralization']} null={rep['centralization_null_mean']} "
          f"z={rep['centralization_z']}")
    st = rep["stability"]
    check("planted hubs are recovered as persistent",
          st.get("persistent_hub_count", 0) >= 4,
          f"{st.get('persistent_hub_count')} persistent, "
          f"jaccard={st.get('jaccard_mean')} vs chance {st.get('jaccard_chance')}")
    # Node ids arrive namespaced as "trial:id" -- deliberately, so that a bee id
    # reused in another trial cannot be merged with this one. Strip the prefix
    # here rather than dropping the namespacing, which is the thing being tested
    # two sections up.
    top = {n.split(":")[-1] for n, _ in rep["top_hubs"][:6]}
    planted = {f"a{i}" for i in range(6)}
    check("top hubs are the planted ones", len(top & planted) >= 5,
          f"recovered {sorted(top)}")

    # ---- self-interaction must not buy a ranking --------------------------
    # Two nodes with identical real degree; one of them also talks to itself, a
    # lot. `degree_centralization` has always ignored `a == b`; `emergent_hubs`
    # did not, and 15 of the 246 Mersch matrices carry a non-zero diagonal. The
    # asymmetry is the bug: the inflation differs per individual, so it re-ranks
    # rather than cancelling.
    base = [{"sender": f"n{i}", "recipient": "quiet", "mtype": "report", "tbin": 0}
            for i in range(5)]
    base += [{"sender": f"n{i}", "recipient": "loud", "mtype": "report", "tbin": 0}
             for i in range(5)]
    selfy = base + [{"sender": "loud", "recipient": "loud", "mtype": "report",
                     "tbin": 0} for _ in range(50)]
    ranked = dict(netstats.emergent_hubs(selfy))
    check("a self-loop does not inflate in-degree",
          ranked["loud"] == ranked["quiet"] == 5,
          f"loud={ranked['loud']} quiet={ranked['quiet']} -- 50 self-records must "
          f"buy nothing")
    ranked_old = dict(netstats.emergent_hubs(selfy, drop_self=False))
    check("and the old behaviour is still reachable, so the fix is a choice",
          ranked_old["loud"] == 55,
          f"loud={ranked_old['loud']} with drop_self=False -- a check that can "
          f"only fire one way is not a check")
    rep_s = netstats.structure_report(selfy, k=3, n_perm=5)
    check("the self-loops are counted and said out loud, not silently absorbed",
          rep_s["n_self_loops"] == 50 and bool(rep_s.get("self_loop_note")),
          f"n_self_loops={rep_s['n_self_loops']}")
    rep_c = netstats.structure_report(base, k=3, n_perm=5)
    check("a clean log reports no self-loops and no note",
          rep_c["n_self_loops"] == 0 and not rep_c.get("self_loop_note"),
          "the negative polarity")

    # ---- a population that shrinks ---------------------------------------
    # Ten individuals on a star in bin 0; by bin 3 six of them are dead. Pool the
    # bins and the dead are zero-degree nodes, each adding a full dmax to the
    # centralization numerator -- so the pooled score rises on attrition alone.
    shrink = []
    for t, alive in enumerate([10, 9, 7, 4]):
        for i in range(1, alive):
            shrink.append({"sender": f"a{i}", "recipient": "hub",
                           "mtype": "report", "tbin": t})
            shrink.append({"sender": "hub", "recipient": f"a{i}",
                           "mtype": "report", "tbin": t})
    rep_sh = netstats.structure_report(shrink, k=3, n_perm=5)
    cen_sh = rep_sh["census"]
    check("the per-bin census is recorded, so the denominator is available",
          cen_sh["n_first"] == 10 and cen_sh["n_last"] == 4
          and cen_sh["n_union"] == 10,
          f"first={cen_sh['n_first']} last={cen_sh['n_last']} "
          f"union={cen_sh['n_union']}")
    check("shrinkage past 5% raises the moving-denominator note",
          bool(rep_sh.get("denominator_note")) and cen_sh["shrinkage"] == 0.6,
          f"shrinkage={cen_sh['shrinkage']}")
    check("centralization is also computed within bins, on the ants alive then",
          rep_sh["centralization_within_bin"]["n_bins"] == 4,
          f"by_bin={rep_sh['centralization_within_bin']['by_bin']}")
    # A stable population must NOT raise it, or the note means nothing.
    stable = []
    for t in range(4):
        for i in range(1, 10):
            stable.append({"sender": f"a{i}", "recipient": "hub",
                           "mtype": "report", "tbin": t})
            stable.append({"sender": "hub", "recipient": f"a{i}",
                           "mtype": "report", "tbin": t})
    rep_st = netstats.structure_report(stable, k=3, n_perm=5)
    check("a stable population raises no such note",
          not rep_st.get("denominator_note") and rep_st["census"]["shrinkage"] == 0.0,
          f"shrinkage={rep_st['census']['shrinkage']}")
    # The chance baseline draws from the living, not from the union. With the
    # union it is smaller, which flatters hub persistence -- the very finding
    # this module exists to support.
    check("the hub-stability chance baseline uses the living, not the union",
          rep_sh["stability"]["n_nodes_per_bin_mean"] < rep_sh["stability"]["n_nodes"],
          f"per-bin mean {rep_sh['stability']['n_nodes_per_bin_mean']} vs union "
          f"{rep_sh['stability']['n_nodes']}")

    # The census has to survive being written to disk. run_real_bench serializes
    # structure_report to JSON, and JSON has no integer keys: a bin-keyed dict
    # returns with keys "0","1","10","11","2", which sort lexicographically. The
    # fixture must therefore run past bin 9 -- with four bins the bug cannot show
    # itself, and a check that cannot fail is not a check. Under the old dict the
    # last entry after a round-trip is bin 9 (n=11), not bin 11 (n=9).
    long_run = []
    for t, alive in enumerate(range(20, 8, -1)):        # 12 bins, 20 -> 9
        for i in range(1, alive):
            long_run.append({"sender": f"a{i}", "recipient": "hub",
                             "mtype": "report", "tbin": t})
            long_run.append({"sender": "hub", "recipient": f"a{i}",
                             "mtype": "report", "tbin": t})
    rep_lr = netstats.structure_report(long_run, k=3, n_perm=5)
    round_tripped = json.loads(json.dumps(rep_lr, default=str))
    by_bin = round_tripped["census"]["n_by_bin"]
    check("the per-bin census keeps its day order through JSON",
          [r["tbin"] for r in by_bin] == list(range(12))
          and by_bin[0]["n"] == 20 and by_bin[-1]["n"] == 9,
          f"first={by_bin[0]} last={by_bin[-1]} -- bin 10 must not sort before bin 2")


def test_bench_pooling() -> None:
    """Three colonies in one file must not be reported as one graph.

    `loaders.gernat` writes all three of Gernat's colonies into a single
    `interaction_log.csv`. `run_real_bench` read that file as one network, and a
    centralization over it is a statistic about a union of three graphs that
    share no edges -- it computes, it looks like a colony number, and it is not
    one. The Mersch loader has refused to pool since the beginning; the bench was
    doing it anyway, one directory over.

    The negative polarity is the one that makes this a check rather than a
    reflex: namespaces that DO interact are labels within one population, and
    splitting on them would delete real edges.
    """
    print("\nPOOLING")
    import run_real_bench as bench

    sep = [{"sender": f"{t}:b{i}", "recipient": f"{t}:b{(i + 1) % 8}",
            "mtype": "trophallaxis", "tbin": 0}
           for t in ("2016-01", "2016-02", "2016-03") for i in range(8)]
    meta = {"special_nodes": ["2016-01:b0", "2016-02:b0", "2016-03:b0"],
            "source": "fixture"}
    buf = io.StringIO()
    with redirect_stdout(buf):
        parts = bench.split_if_disconnected("gernat_trophallaxis", sep, meta)
    check("three colonies sharing no edge are split into three graphs",
          len(parts) == 3 and set(parts) == {"gernat_trophallaxis[2016-01]",
                                             "gernat_trophallaxis[2016-02]",
                                             "gernat_trophallaxis[2016-03]"},
          f"{sorted(parts)}")
    check("and each part keeps only its own edges",
          all(len(p) == 8 for p, _ in parts.values()),
          f"{[len(p) for p, _ in parts.values()]} of {len(sep)} records")
    check("the queen mark is split with the log, not carried whole into each part",
          all(m["special_nodes"] == [f"{g}:b0"]
              for g, (_, m) in ((k[len("gernat_trophallaxis["):-1], v)
                                for k, v in parts.items())),
          "a colony's report must not be told about another colony's queen")
    check("and the split says why, rather than renaming things quietly",
          "not a colony" in
          next(iter(parts.values()))[1]["split_note"],
          next(iter(parts.values()))[1]["split_note"][:88])

    # Negative polarity: one edge across the namespaces and they are not separate
    # graphs any more. One edge is enough, and that is the point -- the test is
    # connectivity, not naming.
    joined = sep + [{"sender": "2016-01:b0", "recipient": "2016-02:b0",
                     "mtype": "trophallaxis", "tbin": 0}]
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        kept = bench.split_if_disconnected("gernat_trophallaxis", joined, meta)
    check("one edge between namespaces is enough to stop the split",
          len(kept) == 1 and "gernat_trophallaxis" in kept,
          f"{sorted(kept)} -- namespaces that interact are labels, not colonies")
    check("and that decision is announced too",
          "kept pooled" in buf2.getvalue(), buf2.getvalue().strip()[:88])

    flat = [{"sender": f"b{i}", "recipient": f"b{(i + 1) % 8}", "mtype": "t",
             "tbin": 0} for i in range(8)]
    check("a log with no namespaces at all is left exactly alone",
          bench.split_if_disconnected("mersch_net", flat, {}) == {"mersch_net":
                                                                 (flat, {})},
          "the common case must not pay for the guard")

    # ---- a section that vanishes rather than complains --------------------
    # On the real drive the Gernat loader had been pointed at
    # `data/canonical/gernat_q` while the bench globs `data/processed/`. The
    # COMMUNICATION STRUCTURE block simply did not appear, the run exited 0, and
    # the output was complete on its own terms -- which reads as "no structure to
    # report" rather than "nothing was looked at".
    stray_root = Path(tempfile.mkdtemp())
    for rel in ("data/canonical/gernat_q", "data/processed/illinois_portal/t1"):
        p = stray_root / rel
        p.mkdir(parents=True)
        (p / "interaction_log.csv").write_text("sender,recipient,mtype,tbin\na,b,t,0\n")
    strays = [str(s) for s in bench.find_stray_logs(stray_root)]
    check("an interaction log outside processed/ is found and named",
          strays == ["data/canonical/gernat_q"],
          f"{strays} -- an empty section is the worst way to report a missing input")
    check("and a log in the right place is not reported as stray",
          not any("processed" in s for s in strays),
          "the nested illinois trial dir lives under processed/ and is not a stray")
    shutil.rmtree(stray_root, ignore_errors=True)


def _exchangeable(seed: int, n_nodes: int, n_events: int, n_partners: int,
                  star: bool = False) -> list[dict]:
    """A colony in which every individual is interchangeable -- or one with a hub.

    Each individual has a fixed partner set of `n_partners` nestmates, so the
    events-per-unique-pair figure is set by `n_partners` alone: narrow partner
    sets mean the same contacts repeat. Nothing here is centralized unless `star`
    is given, in which case one individual receives half of everything.
    """
    rng = random.Random(seed)
    log = []
    for _ in range(n_events):
        s = rng.randrange(n_nodes)
        r = (0 if (star and rng.random() < 0.5)
             else (s + 1 + rng.randrange(n_partners)) % n_nodes)
        if s != r:
            log.append({"sender": f"b{s}", "recipient": f"b{r}",
                        "mtype": "trophallaxis", "tbin": 0})
    return log


def _repeaters(seed: int, n_nodes: int = 900, top_frac: float = 0.1,
               top_rep: float = 2.0, uniform_rep: float | None = None,
               scale: float = 2.0, spread: float = 1.2) -> list[dict]:
    """Lognormal activity, and repetition applied on purpose rather than by luck.

    Each individual gets `e` events and a partner set of `e / rep` nestmates,
    visited round-robin -- so its repetition factor is exactly `rep` and its
    partner count is exactly proportional to its activity. `uniform_rep` gives
    every individual the same factor; otherwise only the busiest `top_frac`
    repeat, at `top_rep`, and everybody else contacts a fresh nestmate every time.

    The uniform form is what killed the partner-scaling exponent: repetition is
    strictly proportional to activity there, so the exponent is 1.0 by
    construction, and the z is still -23. The skewed form at top_rep=2 is the one
    that reproduces the real colonies -- 1.27 events per pair against a null of
    1.03, and a z of -21.6, against Gernat's 1.23 and -18.7.
    """
    rng = random.Random(seed)
    acts = [(i, max(1, int(round(math.exp(rng.gauss(scale, spread))))))
            for i in range(n_nodes)]
    acts.sort(key=lambda t: -t[1])
    cut = int(n_nodes * top_frac)
    log = []
    for rank, (i, e) in enumerate(acts):
        rep = uniform_rep if uniform_rep is not None else (
            top_rep if rank < cut else 1.0)
        p = max(1, min(n_nodes - 1, int(round(e / rep))))
        partners = rng.sample([j for j in range(n_nodes) if j != i], p)
        for k in range(e):
            log.append({"sender": f"b{i}", "recipient": f"b{partners[k % p]}",
                        "mtype": "trophallaxis", "tbin": 0})
    return log


def test_null_calibration() -> None:
    """What the centralization z-score is actually a test of.

    The real colonies score z of -8.2, -18.7 and -14.7, which reads as "these
    colonies are significantly LESS centralized than chance" and is not what it
    means. `degree_centralization` counts distinct partners; `centralization_null`
    shuffles the recipient column. That shuffle preserves the recipient multiset,
    so an individual who receives half the colony's contacts still receives half
    of them afterwards -- the hub is carried into the null intact. What gets
    rewired is everybody else: an ordinary bee's repeated visits to the same few
    nestmates are scattered across the whole colony, and her degree goes up.

    So the z compares ordinary partner sets against a wide-open version of
    themselves. That one mechanism breaks it in both directions, and each
    direction gets a fixture below: a colony with no hub whatever scores far
    below zero, and a hard star scores zero. Neither is a check that can only
    fire one way.
    """
    print("\nWHAT THE Z IS A TEST OF")

    flat = netstats.structure_report(_exchangeable(7, 200, 12_000, 20),
                                     k=5, n_perm=8)
    check("a colony with no hub at all scores far below the null",
          flat["centralization_z"] < -4 and flat["centralization"] < 0.05,
          f"cen={flat['centralization']} z={flat['centralization_z']} at "
          f"{flat['events_per_unique_pair']} events per unique pair -- every "
          f"individual is interchangeable, so the z is reporting repetition")
    check("and it says so rather than leaving the reader to infer flatness",
          "narrower than chance" in flat.get("z_note", ""),
          flat.get("z_note", "")[:96])

    star = netstats.structure_report(_exchangeable(7, 200, 12_000, 20, star=True),
                                     k=5, n_perm=8)
    check("the same fixture with a real hub scores strongly positive",
          star["centralization_z"] > 25 and star["centralization"] > 0.6,
          f"cen={star['centralization']} z={star['centralization_z']} -- the "
          f"statistic does detect concentration, so the negative reading above "
          f"is not simply a broken measure")
    check("and the positive note is a different note, not the same one",
          "ABOVE the null" in star.get("z_note", "")
          and "narrower than chance" not in star.get("z_note", ""),
          star.get("z_note", "")[:96])

    # The second failure direction, and the one that would actually cost us a
    # finding. Widen every partner set to the whole colony and keep the hub: the
    # network is still a hard star, centralization still ~0.72, and the z falls to
    # zero -- because with nothing narrow left to widen, the shuffle reproduces
    # the observed degree sequence. Measured hub/median degree, observed then in
    # one null draw: 299/86 -> 299/85. A z near zero is not evidence of no hub.
    wide = netstats.structure_report(_exchangeable(7, 300, 30_000, 299, star=True),
                                     k=5, n_perm=8)
    check("a hard star can score a z of zero, so a null result is not a finding",
          abs(wide["centralization_z"]) < 5 and wide["centralization"] > 0.6,
          f"cen={wide['centralization']} z={wide['centralization_z']} -- one bee "
          f"receives half of everything and the z cannot see her, because the "
          f"shuffle preserves how much each individual receives")
    check("and the reader is told that, not left with an unqualified z",
          "NOT evidence that there is no hub" in wide.get("z_note", ""),
          wide.get("z_note", "")[:96])

    # events_per_unique_pair is the thing the z is confounded with, so it has to
    # move with the confound and be reported next to it.
    epup = [netstats.structure_report(_exchangeable(7, 200, 12_000, p),
                                      k=5, n_perm=3)["events_per_unique_pair"]
            for p in (5, 20, 60)]
    check("events per unique pair rises as the partner set narrows",
          epup[0] > epup[1] > epup[2] > 1.0,
          f"5/20/60 partners -> {epup} events per pair -- this is the quantity "
          f"the z tracks, which is why it is in the report next to it")
    check("the definition of the null travels with the number",
          "hub in the null too" in flat.get("null_definition", ""),
          "a statistic whose null is described somewhere else is a statistic that "
          "will be quoted without it")

    # THE REFERENCE POINT, which is the thing two shipped versions of this note
    # got wrong. events_per_unique_pair was being read against 1.0. The null does
    # not produce 1.0: reassigned events land on partners an individual already
    # has, so the null graph repeats too, by an amount set by n and the event
    # counts. On the wide-partner star it repeats 2.3 times per pair. Anything
    # that compares the observed figure to 1.0 is comparing it to a number the
    # null never reaches.
    wide_pn = wide["partner_narrowing"]
    check("the null does its own repeating, so 1.0 is not the reference",
          wide_pn["events_per_unique_pair_null"] > 2.0,
          f"a random re-assignment of these same event counts gives "
          f"{wide_pn['events_per_unique_pair_null']} events per pair, not 1.0 -- "
          f"read against 1.0 this network looks like heavy repetition and it is "
          f"exactly average")
    check("and the observed figure is reported as a ratio to it, not raw",
          abs(wide_pn["narrowing"] - 1.0) < 0.05
          and abs(wide["centralization_z"]) < 5,
          f"narrowing={wide_pn['narrowing']} at z={wide['centralization_z']} -- "
          f"partner sets exactly as wide as chance, and a z of zero to match")

    # The fixture that killed the partner-scaling exponent. Every individual
    # repeats by the same factor, so partner count is strictly proportional to
    # activity and any exponent fitted through it is 1.0. If the exponent were the
    # mechanism this would score zero. It scores -23.
    uni = netstats.structure_report(_repeaters(1, uniform_rep=2.0), k=5, n_perm=8)
    check("repetition uniform in activity still drives the z hard negative",
          uni["centralization_z"] < -12
          and uni["partner_narrowing"]["narrowing"] > 1.5,
          f"z={uni['centralization_z']} at narrowing="
          f"{uni['partner_narrowing']['narrowing']} -- partner count is exactly "
          f"proportional to activity here, so this is not the busy individuals "
          f"revisiting more than the quiet ones; it is everyone revisiting")
    check("and the note attributes it to the ratio, not to the raw repetition",
          "narrower than chance" in uni.get("z_note", "")
          and "which is the reference, NOT 1.0" in uni.get("z_note", ""),
          uni.get("z_note", "")[:120])

    # The fixture that reproduces the real colonies. Only the busiest tenth
    # revisit, at a factor of two. Gernat 2016-02 reads 1.23 events per pair at
    # z=-18.7; this reads 1.27 at -21.6. That is the reading the first note called
    # "contacts repeat" beside a figure of 1.2 -- and 1.2 IS repetition, once it
    # is read against the 1.03 the null gives rather than against 1.0.
    real = netstats.structure_report(_repeaters(1, top_rep=2.0), k=5, n_perm=8)
    rpn = real["partner_narrowing"]
    check("the Gernat reading is reproduced by a colony with no hub in it",
          real["centralization_z"] < -10 and 1.15 < real["events_per_unique_pair"] < 1.4
          and rpn["events_per_unique_pair_null"] < 1.10,
          f"epup={real['events_per_unique_pair']} against a null of "
          f"{rpn['events_per_unique_pair_null']}, narrowing={rpn['narrowing']}, "
          f"z={real['centralization_z']} -- against Gernat's 1.23 and -18.7, with "
          f"nothing centralized here at all (cen={real['centralization']:.4f})")
    check("a small raw repetition is a large narrowing, and the note says which",
          f"{rpn['narrowing']:.2f}x narrower than chance" in real.get("z_note", ""),
          f"1.27 events per pair reads as 'barely any repetition' and is "
          f"{rpn['narrowing']}x chance; the note has to print both or it invites "
          f"the reading that sank the first two versions")

    # The branch that says "not accounted for". It exists because a negative z at
    # a narrowing of 1 would mean the mechanism above is not the whole story. No
    # fixture here produces one -- eight seeds of the wide star sit at narrowing
    # 1.00 and every one of them stays inside the +/-2 band. So this check is not
    # asserting the branch fires; it is recording that it never has. If it fires
    # on real data, that reading is outside everything calibrated here.
    swept = [flat, star, wide, uni, real]
    check("no calibrated fixture lands in the not-accounted-for branch",
          not any("not yet accounted for" in r.get("z_note", "") for r in swept),
          "every negative z in this file is explained by the narrowing ratio; if "
          "a colony ever trips that branch the explanation does not cover it and "
          "the number must not be quoted until it does")


def test_mersch_networks(root: Path, rng) -> None:
    """The 246 daily matrices, read as a graph rather than validated as files."""
    print("\nMERSCH NETWORKS")
    d = fake_mersch(root, rng, "real")

    try:
        mersch_net.load(d)
        pooled_refused = False
    except SystemExit as exc:
        pooled_refused = "disconnected" in str(exc)
    check("pooling colonies into one graph is refused by default",
          pooled_refused,
          "six colonies in one graph is six components, and Freeman "
          "centralization on a disconnected union moves with the pooled node "
          "count for reasons that are not about anybody's organization")

    log, meta = mersch_net.load(d, colony="col1")
    check("one colony's matrices load as an undirected log",
          meta["n_matrices"] == 7 and not meta["directed"] and meta["n_messages"] > 0,
          f"matrices={meta['n_matrices']} messages={meta['n_messages']}")
    check("every contact is emitted both ways",
          meta["n_messages"] == 2 * meta["n_edges_undirected"],
          f"{meta['n_edges_undirected']} undirected -> {meta['n_messages']} records")
    check("nodes are namespaced on the MATRIX colony label",
          all(m["sender"].startswith("col1:") for m in log[:50]),
          f"e.g. {log[0]['sender']!r} -- col1 is not colony 1 of behavior.csv")
    check("and the loader says so rather than letting somebody assume",
          meta["joinable_to_behavior_csv"] is False and "col1..col6" in meta["join_blocker"],
          "structure is computable now; structure x task waits on the mapping")
    check("the shrinking node count is carried per day",
          meta["census"][0]["n"] > meta["census"][-1]["n"]
          and meta["population_shrinkage"] > 0,
          f"census={[c['n'] for c in meta['census']]}")
    check("and past 5% it is stated, not left in the metadata to be found",
          bool(meta.get("denominator_warning")),
          f"shrinkage={meta['population_shrinkage']}")

    # Self-loops: plant one, then check both policies see it.
    p = next(iter(sorted((d).rglob("network_col1_day1.txt"))))
    lines = p.read_text().strip().split("\n")
    body = [ln.split(",") for ln in lines[1:]]
    body[0][0] = "0.9000"
    p.write_text("\n".join([lines[0]] + [",".join(r) for r in body]) + "\n")

    log_d, meta_d = mersch_net.load(d, colony="col1", self_loops="drop")
    log_k, meta_k = mersch_net.load(d, colony="col1", self_loops="keep")
    check("a planted self-loop is counted under both policies",
          meta_d["n_self_loops"] == 1 and meta_k["n_self_loops"] == 1,
          f"drop={meta_d['n_self_loops']} keep={meta_k['n_self_loops']} -- the "
          f"count is the thing that must not disappear")
    check("dropping means it never reaches the log; keeping means it does",
          netstats.count_self_loops(log_d) == 0
          and netstats.count_self_loops(log_k) == 1,
          f"drop={netstats.count_self_loops(log_d)} "
          f"keep={netstats.count_self_loops(log_k)}")

    # A matrix short by a row is skipped loudly rather than read partially.
    db = fake_mersch(root, rng, "broken")
    _log_b, meta_b = mersch_net.load(db, colony="col1")
    check("a matrix that is not square is skipped and reported",
          meta_b["n_matrices_unreadable"] >= 1,
          f"{meta_b['n_matrices_unreadable']} unreadable of {meta_b['n_matrices']} "
          f"-- short by one row is a header eaten as data, not a smaller colony")
    check("the AppleDouble shadows are not read as matrices",
          all("__MACOSX" not in str(x) for x in mersch_net.matrix_files(d)),
          "they are binary and named exactly like the real files")

    out = root / "data" / "processed" / "mersch_networks"
    mersch_net.write_log(log, meta, out)
    # meta.json is the artefact anybody downstream actually reads, so the census
    # has to be correct AFTER serialization, not just in memory.
    on_disk = json.loads((out / "meta.json").read_text())
    days = [c["day"] for c in on_disk["census"]]
    check("the census survives the round-trip to meta.json in day order",
          days == sorted(days) and len(days) == meta["n_timebins"]
          and on_disk["census"][0]["n"] >= on_disk["census"][-1]["n"],
          f"days={days} -- a day-keyed dict would come back as strings, and "
          f"'10' sorts before '2'")


def main() -> int:
    rng = random.Random(11)
    root = Path(tempfile.mkdtemp(prefix="beeorg_selftest_"))
    print(f"scratch: {root}")
    try:
        test_real_headers()
        test_dornhaus_real_shape(root, rng)
        test_illinois(root, rng)
        test_time_bins(root)
        test_degeneracy_guard()
        test_missing_values(root, rng)
        events_by = test_loaders(root, rng)
        test_instruments(events_by)
        test_gernat_join(root, rng)
        test_queen_marking(root, rng)
        test_loader_scale(root)
        test_mersch_deposit(root, rng)
        test_nested_archives(root)
        test_netstats(root)
        test_bench_pooling()
        test_null_calibration()
        test_mersch_networks(root, rng)
    finally:
        keep = "--keep" in sys.argv
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f"\nkept scratch tree at {root}")

    print(f"\n{'ALL CHECKS PASSED' if not FAIL else str(FAIL) + ' CHECK(S) FAILED'}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
