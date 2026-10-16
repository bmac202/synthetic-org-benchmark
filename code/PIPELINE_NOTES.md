# BeeOrg — public tracking data for *From Hives to Hierarchies*

Everything here is standard-library Python 3.9+. No pip installs, no virtualenv,
no accounts, no API keys. Seven of the datasets are CC0 or CC-BY and download
without asking anyone's permission.

The whole point of the pipeline is one sentence: **turn published insect-tracking
deposits into the same event format the bench already consumes, so a real colony
and a synthetic organization become rows in the same table.**

---

## Run it

Open Terminal, `cd` to wherever you unzipped this folder, then:

```bash
python3 selftest.py                  # 1. prove the pipeline works (no download)
python3 fetch_data.py --dry-run      # 2. confirm it found the OWC drive
python3 fetch_data.py --tier core    # 3. ~670 MB, a few minutes
python3 inspect_data.py              # 4. see what the files actually contain
```

Step 1 costs two minutes and fabricates data with a known answer, so a broken
loader shows up before an 11 GB download rather than after one.

Step 3 is deliberately the small tier. The data in it is only ~150 MB; the rest
is the `btools` source clone, which is 582 MB of tracking-software assets. Add
`--no-git` to skip it. Core includes Charbonneau & Dornhaus, which at 195 KB is
the single most useful file in the project — it is the only open deposit with a
real workforce shock. Get the pipeline working on that, then:

```bash
python3 fetch_data.py --tier main    # ~17 GB, includes BeesBook 2018
```

If the drive is not auto-detected, pass it: `--dest '/Volumes/Your Drive'`.
Re-running is always safe — completed files are skipped, interrupted ones resume.

### Reading the final tally

The summary distinguishes three things that used to be conflated:

- **complete** — the bytes are on the drive and in `MANIFEST.json`.
- **FAILED** — something went wrong; re-run to retry.
- **awaiting release** — identified, justified, located, but not public yet.
  A `REQUEST.txt` in the dataset folder says who to ask. This is neither a
  success nor a failure and is counted as neither.

After the tally the script re-checks the disk directly and warns about any
dataset folder holding nothing but the notes it wrote itself. That check does
not consult the counters, so a bug in the accounting cannot hide an empty
folder — which is exactly how the first run reported "6/6 complete" while one
dataset had not arrived at all.

---

## What lands on the drive

```
<drive>/BeeOrg/
  data/raw/<dataset>/        exactly as published, plus SOURCE.txt and RESOLVED.json
  data/interim/              scratch
  data/processed/<dataset>/  events.csv + meta.json   <- the canonical format
  code/                      a copy of this folder, so the drive is self-contained
  logs/                      schema_report.md, real_bench.json
  notes/                     yours
  MANIFEST.json              every file: URL, size, MD5, citation, licence, date
```

`MANIFEST.json` matters more than it looks. In eighteen months, when a reviewer
asks which version of a deposit produced Table 2, it is the answer.

---

## Convert to the canonical format

Each loader reads one deposit and writes `(agent_id, task_id, timestep)` triples.

```bash
D=/Volumes/<drive>/BeeOrg
python3 -m loaders.dornhaus --raw $D/data/raw/charbonneau_dornhaus_2017 \
                            --out $D/data/processed/charbonneau_dornhaus_2017
python3 -m loaders.mersch   --raw $D/data/raw/mersch_keller_2013 \
                            --out $D/data/processed/mersch_keller_2013
python3 -m loaders.gernat   --raw $D/data/raw/gernat_trophallaxis \
                            --out $D/data/processed/gernat_trophallaxis --bin-hours 4
python3 -m loaders.illinois --raw $D/data/raw/illinois_portal \
                            --out $D/data/processed/illinois_portal --bin-hours 4
python3 -m loaders.beesbook --raw $D/data/raw/beesbook_2018 \
                            --out $D/data/processed/beesbook_2018 --max-rows 2000000
```

Run BeesBook with `--max-rows 2000000` first. It is a two-pass streaming reader
over ~11 GB; the capped run finishes in under a minute and tells you whether the
column mapping is right before you commit an hour to the full pass.

`loaders.illinois` writes one subdirectory per trial, because the five files are
five independent colonies and averaging them would throw away the only
replication in the project.

Both contact loaders take `--bin-hours` as well as `--bins`. Prefer it. `--bins`
sets a *count*, so it gives different bin widths on records of different lengths
and the widths are not written down anywhere; `--bin-hours` sets the width, and a
divisor of 24 keeps the daily activity cycle separable from whatever else the
bins are being used to measure. See "Twenty-four bins is not twenty-four hours"
below for why this is not a preference.

**When a loader stops with "could not find a column for …", that is the design
working.** None of these deposits publish a schema. Rather than guess and
silently analyse the wrong variable, the loader prints the real header and asks
you to add the correct name to the `CANDIDATES` dict at the top of the file. It
is a thirty-second edit and it is the difference between a result and an
artifact.

If you already know the answer, name it directly instead of editing the file:

```bash
python3 -m loaders.dornhaus --raw ... --out ... --col-task ClustDesc --col-time Trial
```

An explicitly named column that does not exist in the file is an error, not a
cue to fall back to guessing.

### The near-miss that shaped this

The real Charbonneau & Dornhaus header is:

```
UAntID, Colony, Treat, Trial, i, a, ActInact, ClustDesc
```

`i` and `a` are the proportions of time inactive and active. The original
substring matcher bound **time → `i`** and **task → `a`**, because "i" is inside
"time" and "a" is inside "task". Nothing raised. Every event would have
collapsed onto timestep 0 with a float used as a categorical task label, and the
run would have produced a full set of plausible numbers about the wrong
variables.

Three changes came out of that. `pick_column` now resolves exact matches first
in candidate order, refuses to fuzzy-match any name shorter than three
characters, and prefers the longest overlap rather than the first hit.
`selftest.py` carries the literal published headers as regression fixtures, so
the mis-binding cannot come back silently. And the shock timestep is now mapped
through the same dense bin index as the events — it used to be reported in raw
day numbers, which put the pre/post boundary one bin late.

Two things about this deposit are worth knowing before reading any number from
it. Time is the categorical `Trial` column (`pre`, `post1`, `post2`), ordered by
the experiment rather than alphabetically — sorted as strings, `post1` comes
before `pre` and the experiment runs backwards. And there are only three time
points, so `--min-obs 2` is the default: an ant needs to appear on both sides of
the removal, and nothing stricter is achievable.

`ClustDesc` **is** a static per-ant attribute. On the real file no ant ever
changes label, which means the authors assigned the cluster once from the pooled
record rather than per trial. The loader reports `task varies : 0.0` and says so
loudly, and offers `--task-from activity`, which bins the active-time proportion
into four ordinal levels instead. That is a proxy, it is recorded as one in
`meta.json`, and it should be described as one in anything we write.

`NA` in these files is the R convention arriving as a literal two-character
string, not an empty cell. Read naively it becomes a fifth behavioural group with
250 members. `loaders/common.py` centralises the set of strings that mean *no
value*, the loader drops those rows and reports how many it dropped, and
`selftest.py` asserts that the group never reappears.

### None of these deposits ship a codebook

This is worth stating plainly because it shapes everything downstream. The
Dryad deposit is **one CSV and nothing else** — no README, no data dictionary,
no column legend. The only authoritative description of what `i`, `a`,
`ActInact`, `Treat` and `ClustDesc` mean is the Methods section of the paper,
which is prose, is not machine-readable, and never names a column.

So every statement about these columns is an inference until something tests it.
Writing the inference down in a codebook does not test it; it just makes the
guess look official. `validate_dornhaus.py` tests it instead:

```bash
python3 validate_dornhaus.py --raw $D/data/raw/charbonneau_dornhaus_2017
```

It recomputes from the CSV alone quantities the paper reports independently —
colonies per treatment, size of each behavioural group, number of observation
blocks, how many workers — and prints PASS or CHECK against each. Reproducing a
published number the authors derived without us is evidence that we are reading
the column they wrote. It also asserts the structural claims: that `UAntID` is
unique across colonies (if not, every per-ant number pools different ants), that
`Treat` is constant within a colony, and that `i + a` sums to 1 (if it does not,
a third "undifferentiated" category is unaccounted for and `a` is not `1 - i`).

The paper targets at the top of that file are transcribed and **not yet
human-verified**. A PASS against an unverified target proves nothing on its own;
check the number in the PDF and set `verified=True`.

Exit code is 1 while any CHECK is outstanding, so this can gate the analysis.

### What the first run against the real file established

Confirmed, by reproducing numbers the authors derived without us: **5 RemActive,
9 RemLazy, 6 RemRandom** colonies, matching the published design exactly; three
observation blocks; `UAntID` unique across colonies; `Treat` constant within a
colony; and `ClustDesc` constant within an ant, with **zero** ants changing
cluster — so the degeneracy guard is responding to a real property of the
authors' design, not to a mistake of ours.

Three things the run settled that prose could not have:

**The 250 unlabelled ants are not data loss.** `ClustDesc` is the literal string
`NA` for 250 of the 1,299 ants. The remaining 1,049 is exactly the number of
pre-block rows, and the validator now tests the biconditional directly: an ant
carries a cluster label *if and only if* it was present before the removal. That
is the signature of a cluster analysis fitted to pre-removal data only. Those 250
are the ants that entered the record after the shock — a group worth analysing on
purpose rather than dropping.

**`a` is not `1 − i`.** The two proportions sum to 1 in only 12.5% of rows. That
is consistent with the paper's third, undifferentiated category (walking inside
the nest) belonging to neither, and it means any code that reconstructs one from
the other is wrong.

**Two of my own paper targets were fabricated by an automated reader.** The
transcribed group sizes (605/145/249/483) match no set of ants in the file and
sum to 1,482, which matches nothing either. The percentages published alongside
them (40.8/9.8/16.8/32.6) reproduce to within about two and a half points. The
targets now use the percentages and the counts are gone. This is the reason the
`verified` flag exists: a number can be published, transcribed faithfully in
form, and still be wrong.

Still open: `NoRem`, which is 2 colonies and 81 ants that the published methods
do not describe — removing them leaves exactly the 20 colonies the paper reports,
so it is a real extra group and not a miscount. And the worker total: the paper
says 1,307, the file has 1,299. Eight ants is small enough to be an exclusion
rule we have not reconstructed and large enough that we should not claim to have
reproduced the sample. Both are in the email draft to the authors.

### What the attrition and ActInact checks then overturned

**Absence is not removal.** The median removal colony loses **42%** of its
pre-removal ants by the first post block (RemLazy 41%, RemRandom 44%, RemActive
43%, each spanning roughly 25–79% across colonies) against a design that removes
20%. The excess is death, marker loss and non-observation, so the ants that
vanish are not the ants that were taken out and the treated individuals cannot be
recovered by subtraction. The removal list has to be asked for.

**`NoRem` is almost certainly not a control.** Its two colonies lose **100%** of
their pre-removal ants — every one of those 81 ants appears in the `pre` block
and never again. A colony that was watched and then left alone does not do that;
a colony that was observed once and dropped before treatment does. This reverses
what the attrition test was built to look for, and the email question changes
with it: not *is this a control?* but *these two colonies have baseline data
only — were they excluded before the manipulation?*

**`ActInact` is not redundant.** The obvious reconstruction, `A` iff `a > i`,
reproduces only **76.8%** of the 974 flagged rows, and a search over every
threshold on `a`, on `i`, and on `a − i` does no better. The column therefore
carries something the deposit does not otherwise contain, which matters because
it is absent on 58% of rows and we would otherwise have dropped it as a derived
convenience.

**And one of these checks was wrong when first written.** The missingness test
compared median `a` on flagged against unflagged rows using an *absolute*
threshold of 0.10. The real values are 0.187 and 0.092 — a doubling — and it slid
under the threshold and printed PASS. `a` has a median near 0.1, so an absolute
gap was the wrong shape for the variable; the test is now a ratio. What it should
have reported is that the flag is present preferentially for more active ants, so
any subset defined by `ActInact` is biased towards activity. `selftest.py` now
also runs the validator over a second fixture with the opposite structure planted
— a derivable flag, missingness that tracks activity, and a `NoRem` group whose
exclusion does close the gap to the published shares — so each of these checks
has to fire in both directions rather than merely being constant.

### The validator opened the wrong study

Pointed at the whole `data/raw` tree rather than one deposit's directory,
`validate_dornhaus.py` chose its input with `max(files, key=size)` — on the
reasoning that a deposit's real table is the biggest file in its own folder. With
several deposits under one root, the biggest file is whichever study happens to
be largest. It opened Gernat's 367,614-row `interactions.csv`, printed the
Charbonneau citation above it, and was stopped only by the header check at the
very end.

Stopping was the correct outcome and the guard earned its place, but it was the
last line of defence doing work that selection should never have handed it. Size
is not evidence about identity; the header is. Selection is by header now, so
pointing `--raw` at the parent of every deposit works correctly and finds the
right file wherever it sits. If nothing matches, or if two files match, the
script prints every candidate with its path and its header and exits rather than
choosing. `selftest.py` plants a decoy twenty times the size of the real table in
the same directory and asserts the real one still wins.

The reason this is in the README rather than just fixed: the failure mode was
not "the script broke". It was a heuristic that had been right every previous
time, on directories with one deposit in them, and became silently wrong the
moment the input grew a second study. That shape recurs.

### Gernat: three tables, and the join between them

The deposit turned out to be three files, not one — `interactions.csv` (367,614
rows: trial, timestamp, id1, id2, direction), `bees.csv` (2,777 rows: trial, id,
caste, time_of_death) and `trials.csv` (3 rows: trial, begin, end). A join is
where two files that are each individually correct produce something that is
not, and none of the five failure modes here can raise. Each one yields a
complete run with plausible numbers. So `validate_gernat.py` exists for the same
reason its Dornhaus counterpart does.

One thing the run settled outright: **this deposit carries no task labels.**
`caste` is 2,774 worker and 3 queen, and never varies within an individual. It
is a static attribute of the same shape as Dornhaus's `ClustDesc`, so using it as
a task would make division of labour maximal by construction and flexibility
undefined. Gernat is a structure instrument — direction, hubs, centralization —
and nothing else. Task labels have to come from Mersch, which is not in
`data/raw` yet.

**Are ids unique across trials?** `bees.csv` is keyed on (trial, id), which is
what you write when `id` alone is not a key. If ids restart per trial and the
loader pools them, bee 7 of trial 1 and bee 7 of trial 2 become one node holding
both their edges, and the individuals that come out most central are simply the
ids occurring in the most trials. The loader now namespaces every node as
`trial:id`, which costs nothing if ids *are* globally unique and prevents a
silent merge if they are not.

**Do the trials share a clock?** If timestamps are absolute and the trials ran
weeks apart, a single min-to-max binning gives each trial its own block of bins,
and "do the same individuals stay central across time" quietly becomes "do
different colonies appear in different bins" — which reads as total turnover.
Bins are now computed within trial, so bin *k* means the *k*-th slice of that
colony's own record in every trial.

**What is actually in `direction`?** The loader decodes a set of conventions and
falls back to emitting an event symmetrically when it meets one it does not know.
If the real file uses a token outside that set, every event takes the fallback,
direction is discarded, and the run still reports `directed=True`. Direction is
the entire reason this deposit is worth having, so an undecodable token now
prints a warning and sets `directed=False` — the metadata records what happened
rather than what was intended.

On the real file both tokens are recognised (`'<'` 202,798 and `'>'` 164,816), so
`directed=True` is honest. Two things travel with that. First, `id1` sorts before
`id2` in **100.0%** of rows: the pair columns are a canonicalised key and encode
nothing about who fed whom, which makes `direction` the single point of failure
for every directed claim from this deposit — there is no redundant encoding to
fall back on or cross-check against. Second, the split is 55.2/44.8 rather than
even. Against a canonicalised key that asymmetry is a property of detection or
annotation, not of the colony, and must not be read as food flowing one way. It
belongs in any claim about in- versus out-degree.

**And one genuine cross-file test.** No bee should appear in an interaction after
its recorded `time_of_death`. If that holds, the two files share both a clock and
an id space and the join is safe; if it fails, one of those is wrong. This is
stronger than any plausibility check because it can only pass for the right
reason.

**Retracted: `time_of_death` is mostly not death.** This section previously said
that because Gernat records death, absence decomposes into died, left and not
seen, and that this makes it the better deposit for anything about attrition —
the thing Dornhaus cannot give us. That was written before the check ran. The run
then reported a death time for 2,777 of 2,777 bees, and colonies do not lose
every member. So the column became a check against each trial's declared `end`.
It returned 2,244 bees (80.8%) whose death sits at or past the boundary, 533
(19.2%) earlier — and a **median gap of −1.0 s**.

The sign is the finding. A negative gap means the recorded death is *later* than
the declared end of observation, and the median one is later by exactly one
second. That cannot be a measurement; it is a sentinel meaning *still alive when
we stopped looking*. The first version of the check lumped "after the end"
together with "at the end" — both are censoring, so the verdict was the same —
and printed the −1.0 without noticing that the sign was the whole story. Buckets
that hide the sign of a difference hide the finding, so the overshoot got its own
line and its commonest values were printed.

Splitting it settled the question more sharply than expected. All 2,244 sit
**strictly after** the end, every one at exactly `end + 1 s` — a single constant
— and **zero** fall in the minute before it. So the indicator is not a tolerance
at all:

> `censored == (time_of_death == trial_end + 1)`

is a biconditional, exact, with nothing to judge. That turns "80% of this column
is probably censoring" — a warning you have to carry around — into "this column
is a survival pair we can decode", which is a fact you can use. Had the overshoot
taken several different values the opposite would follow: no rule separating
censoring from measurement error, and the whole column suspect. A claim that
strong needs its negative case tested, so the self-test plants both polarities and
requires the exact-indicator note to stay silent under the scattered one while
the censoring CHECK still fires.

What this deposit actually holds is a survival table with the censoring indicator
left implicit: **533 candidate events and 2,244 observations censored at trial
end.** That is a perfectly ordinary layout and it is usable — but it must be read
as (time, censored), never as a time of death, and no survival analysis may treat
those 2,244 as deaths.

**Are the 533 real?** A death time inside the window is only an observation if
the animal also stops appearing at roughly that moment. Checking that needs a
tolerance, and "within an hour" is 0.8% of a five-day trial but 36% of the
self-test fixture — the ActInact mistake in a new costume. So the scale comes
from the data instead: death times are shuffled among bees of the same trial,
which preserves every marginal and destroys only the pairing, and the real lag is
read against that null. A ratio near 1.0 means the column says nothing about when
the bee vanished.

They are real. Of the 533, **527 have interactions**; the median one stops
appearing **438 s (0.12 h)** from its recorded death, against **84,803 s
(23.56 h)** under within-trial shuffling — a ratio of **0.005**. The remaining 6
never appear in `interactions.csv` at all and cannot be corroborated either way.
So the survival table is usable as a table: 533 observed events, of which 527 are
independently confirmed by a second file, and 2,244 right-censored at trial end.

One more count that matters for denominators: **10 bees are described in
`bees.csv` but never interact** (2,767 interacting `(trial, id)` pairs against
2,777 rows). Those are isolates, not missing rows. They belong in per-capita
denominators and in the node set for centralization — dropping them because they
have no edges inflates every per-capita quantity and shrinks the graph the null
model is built on.

It follows that the cross-file test above is weaker than it first appeared. Under
censoring, "no bee interacts after its death time" is close to an arithmetic
identity: nothing inside the record can fall after the end of the record. It
still confirms the clock and the id space, which is what makes the join safe, but
it is not evidence that the death times are real, and the PASS line now says so
in as many words.

**A reporting bug in the same file, found the same way.** The id-uniqueness check
computed `set.intersection(*per)` — the ids present in *every* trial — under a
label reading "occur in more than one trial". On the real deposit that is 179
where the true figure is 891 of 1,707: a fivefold understatement of the hazard.
The verdict was right either way, which is exactly why nothing downstream would
have caught it, and why the fixture did not either. The hostile fixture gives all
three trials the same 60 ids, so "in ≥2 trials" and "in all 3 trials" are the
same set there. A fixture that cannot separate two quantities cannot notice a
check that confuses them.

**A PASS should not read like a warning.** The verdict block was printing the
failure prose under passing checks, including one line that rendered an empty
list of offending trials as `[]` inside a sentence about trials with bad
timestamps. Somebody reading a page of those learns that the text under a result
is noise — and then does not read the text under the CHECK either. Every check
now carries separate pass and fail prose.

The self-test runs two fixtures with opposite structure. The first is
deliberately hostile: three trials with ids restarting in each, clocks separated
by a gap so the ranges cannot overlap, an unrecognised direction token, planted
hubs that differ between trials, and deaths spread through the middle of each
window. The second inverts all of it — id ranges staggered so that 30 of 80 ids
occur in two trials and none in all three, one shared clock, decodable direction
tokens, most bees stamped as dying at the declared end of the trial, and a
minority who vanish early and are then given a death time drawn independently of
when they vanished — a value in the right range, in the right units, correlated
with nothing, which passes every check that reads the column on its own. Each
check must fire on one and stay quiet on the other, so a check that has quietly
become a constant disagrees with one of the two. The second fixture is also run
twice, once with every survivor stamped at `end + 1` and once with the stamps
scattered over `end + 1 … end + 5`, because the exact-indicator claim is a claim
about the shape of the overshoot and needs the shape it does *not* hold for. The
single-trial fixture that preceded both passed everything it was given, for a
file with one trial and one clock.

### Mersch: four periods, one column

`behavior.csv` carries **four** task assessments per ant, not the three this
project's notes claimed, and it stores them **wide** — `group_period1 …
group_period4`, one column per period, no time index. Run the real header
through the loader's candidate lists and two variable roles come back holding
the same answer:

    task -> group_period1        day -> group_period1

`"group"` fuzzy-matches `groupperiod1`; so does `"period"` in the day list.
Neither `pick_column` call can see that the other happened, so nothing raises.
The loader completes on one period of four, and the day index is now a *function
of* the task label: task is perfectly determined by time, mutual information is
maximal by construction, division of labour comes out at ceiling, role-stability
kappa is 1.0, and the switch fraction is structurally zero. Every number is
plausible and every one of them is about the wrong thing. This is the failure
mode worth naming: not a crash, not a missing file, but a run that finishes
clean on a quantity you did not ask for.

The general invariant behind it is that **two variable roles resolving to one
column is always a bug and never a coincidence** — two roles exist because two
distinct quantities are needed, and one column cannot be both. That is now
enforced rather than documented. `loaders/common.pick_columns` resolves the
roles together and raises `ColumnCollision` instead of returning two answers,
`validate_mersch.py` reports the binding as a table with the collision flagged,
and `loaders/mersch.py` *melts* the four period columns into four timesteps so
there is nothing left for `day` to bind to. `--task-col` / `--day-col` name the
columns explicitly when the guard fires on a header we have not seen.

Building the negative fixture turned up a second collision of the same family.
`age_days` normalizes to `agedays`, which contains `day`, so on a header with an
age column and no day column **the time index binds to an age** — every temporal
quantity then computed over how old the ants are, silently. The `age` role is
kept in the validator's candidate lists precisely because that collision is the
point.

What the melt then shows is the finding: the labels move. **183 of the 392 ants
labelled in every one of the four periods (47%) hold more than one distinct
label.** That inverts what this project previously assumed. Mersch is not a
static labelling good only for specialization — it is a re-allocation record,
and it is the largest one we have. What it lacks is a *manipulation*: the
re-allocation is whatever the colony did on its own, not a response to something
done to it. Charbonneau & Dornhaus remains the manipulated comparison, but it is
now a comparison and not the only source.

That figure is the second one this file carried. The first was **596 of 805,
74%** — asserted here alongside a claim that no cells were missing anywhere in
those four columns, a claim that came from nowhere except the count having
looked clean. Run against the real deposit, `validate_mersch.py` found **807
blank cells** across the period columns. A blank is a distinct "value" to any
count of distinct values, so an ant present in periods 1–2 and gone by 3 has two
of them and changed nothing: the 74% was attrition read as flexibility. That is
precisely the failure this validator exists to catch, committed in the one
number it was written to check, and it survived here because the fixture had no
missing labels planted in it and so could only agree with the assumption.

Only 183/392 may be quoted, and only carrying its denominator. Those 392 are the
ants scoreable throughout, which is not a random half of 805 — it is the same
survivorship shape as Dornhaus's 669 and it has to travel with the number. The
validator now reports both counts side by side and names the gap between them on
the real file; on a fixture with attrition planted, it reports that absence is
being read as flexibility. Both polarities are asserted, so neither can go quiet.

The fixture has three polarities rather than two — `real`, `clean`, `broken` —
for a reason worth stating. "Real" has no missing labels and its flow runs the
published N→C→F way, so on its own it cannot distinguish a missingness check
that correctly stays silent from one wired to stay silent. It also replaced a
fixture that invented a `colony_groups.csv` with columns `ant, group, day,
colony` — a file that does not exist in the deposit, in a layout the deposit
does not use. It passed every time and proved nothing: **a fixture built from
what you assumed the file looks like can only confirm the assumption.** The
header now in `selftest.py` is copied verbatim from the deposit.

Two smaller things the deposit does that the checks now cover. Tag ids are
reused across colonies — ant 57 exists in four of the six — so nodes are keyed
`colony:ant`; pooling without that merges four animals into one node carrying
all their edges, and the "most central" ants become the ids reused most often.
And the bundle ships macOS AppleDouble shadows (`__MACOSX/`, `._*`) named
exactly like the real files. They are binary, and `stream_rows` opens with
`errors="replace"`, so reading one yields garbage rows rather than an exception
— and the old file-selection rule, "the smallest table with a task-like column",
is exactly the kind of rule that picks one. Selection now prefers the name
`behavior.csv` and falls back only with a printed note. (The CR-only line
endings, by contrast, were checked and are harmless: `csv.DictReader` and
`stream_rows` handle them. `wc -l` and `head` do not, which is why the file
looks like one line from the shell.)

### Two colony vocabularies, and a join nobody chose

`behavior.csv` names its six colonies **4, 18, 21, 29, 58, 78**. The 246 daily
matrices name theirs in the filename: **`network_col1` … `network_col6`**. Which
`col` is which colony is not stated in anything we have read, and it is not
recoverable from sort order — a guess about which colony is which is a guess
about which ants are which.

The join check was written to notice this and did not, because of how it was
written: it compared the two label sets, and bailed only when the intersection
was **empty**. The intersection is not empty. It is exactly `{"4"}`, because one
vocabulary happens to contain the numeral 4 and the other happens to have a
fourth colony. So the check passed, the join ran on that single accidental pair,
and the validator reported two confident numbers — an unlabelled-ant count and
an isolate count — about a pairing nobody had chosen. Both are **withdrawn** and
neither appears anywhere in this repo.

This is the same family as the double-binding bug the file was written for: **a
check that can only fire on total mismatch waves the partial coincidence
through**, and what comes out the other side reads like a finding rather than
like an error. The guard now requires the two vocabularies to be *equal*, always
records the assertion so a PASS exists to point at, and — this is the part that
matters — suppresses both derived counts and prints a `note` saying they were
**not computed** and why. A missing check is invisible; a withheld number is a
to-do. `--colony-map '1=4,2=18,…'` supplies the correspondence once it is
confirmed, and an unmapped label is left in place rather than dropped, so a
partial map still fails the equality check instead of quietly shrinking the
comparison to whatever it happened to cover. Getting the mapping is a question
for the deposit's own README or for the authors.

### What the real deposit confirmed

Predictions made from fixtures, then checked against the actual files: the
double-binding collision does fire on the real header; the wide layout is real;
tag ids are reused across colonies (218 of 222); exactly one of the 18 heatmaps
is headerless (`heatmap_col1_foragers.txt`); `observed_expected`'s `group`
column reproduces `group_period1` exactly, 805 of 805, so it is a copy and not a
second opinion; and four AppleDouble shadows are present. All **246 matrices are
square and satisfy M == M<sup>T</sup> exactly** (largest deviation 0), and the
6 × 41 colony-day grid is complete with no interior gaps.

One result was not predicted and is worth more than the rest: transitions run
**174 forward against 63 backward, 73% forward**, along the published nurse →
cleaner → forager sequence. Age polyethism is the strongest prior in this
literature, and recovering it here independently establishes two things the
loader had been assuming — that the period columns are in chronological order,
and that N/C/F carry their documented meanings rather than arbitrary levels.

Four things the run raised that are still open: **6 ants carry the queen label**
in at least one period and are structurally special nodes, to be excluded from
centralization or reported separately; **15 matrices carry a self-loop**, which
inflates degree for those individuals; **all 6 colonies end with fewer ants than
they start with**, so per-capita anything has a moving denominator across the 41
days; and the colony mapping above. The first three are settled in the next
section; the fourth is with the authors.

### The three that were open, and what each one was quietly doing

Three of those four are now decided in code rather than in a note. Each is a
policy with both settings reachable and both polarities tested, because a
default nobody can see is indistinguishable from an assumption.

**Queens are a caste, not a task.** Six ants carry `Q`. Left in a task series
they are perfect specialists who never switch, which pushes division-of-labour
up; and if one is `Q` in one period and `N` in another, a distinct-value count
scores her as having changed group — but a caste relabel is not task
re-allocation, and she would be sitting inside the 183. `loaders/mersch.py` now
takes `--queens {exclude,keep,only}`, defaults to `exclude`, and reports the
change count **both ways** so the effect of the policy on the headline figure is
visible rather than inferred. Six of 805 barely moves the aggregate, which is the
argument for a stated default rather than a shrug.

**Self-loops re-rank rather than cancel.** `degree_centralization` always skipped
`a == b`; `emergent_hubs` did not, and that asymmetry was the bug. Fifteen of the
246 matrices carry a non-zero diagonal, so a handful of ants arrived with an
extra in-degree no other ant received — and because the inflation differs per
individual, it does not wash out of a ranking. An ant could be promoted into the
top-k, and thence into the persistent-hub set, on the strength of interacting
with herself. Both functions now agree, `drop_self=False` still reaches the old
behaviour, and the count is reported either way.

**The denominator moves.** All six colonies shrink. Pool 41 days into one graph
and `n` becomes the union of everyone who ever lived; a dead ant is a zero-degree
node, and every one of them adds a full `dmax` to the numerator of
`sum(dmax - d)`. Attrition raises pooled centralization on its own, with no
individual becoming more central than any other — the colony appears to
centralize as it dies. `node_census` and `centralization_by_bin` now compute on
the animals actually present, and `structure_report` says which figure is which
instead of leaving the reader to pick. The same correction applies to the
hub-stability chance baseline, which drew its `n` from the union: that deflates
chance Jaccard and flatters hub persistence, and hub persistence is the finding
`netstats.py` exists to support, so it is precisely the number that must not be
flattered.

The fourth — the colony mapping — is not ours to decide and is still with the
authors. `loaders/mersch_net.py` reads the matrices into a contact log and
refuses the join rather than guessing it.

### The guard was in one loader out of five

`pick_columns` — resolve every role at once, refuse when two land on the same
column — was written for `mersch.py` because that is where the double-binding was
found. The other four loaders went on resolving their columns in independent
`pick_column` calls, which is the exact pattern that produced the bug. The guard
existed; four fifths of the code was outside it.

So the first thing was to ask whether any of them collides *now*. Only one does,
and it is not a bug — see below. But the useful question is not whether a
collision is present on today's header, it is whether one is reachable, since
these deposits get updated and we have five more to load. Probing each loader's
candidate lists against plausible header spellings found three:

`gernat` binds `trial` and `time` to a single `trial_timestamp` column. `trial`
is the **colony**. Every interaction would be filed under a colony id that is
really a clock — one colony per instant, colony identity destroyed, no error.
`illinois` binds `begin` and `end` to a single `interval_begin_end`, giving every
contact a duration of exactly zero, which is the quantity that loader exists to
compute. `beesbook` binds `x` and `y` to a column named `pos`, putting every
coordinate on the diagonal. All three read clean and finish.

All four loaders now resolve their roles together. What the conversion cost is
the more interesting part.

**The rule was too strong by exactly one case.** "Two roles on one column is
always a bug" was written from a single deposit. Charbonneau & Dornhaus has a
`Trial` column holding `pre`, `post1`, `post2`, and it genuinely is both the
phase label and the time index, because time here *is* the ordinal rank of the
phase — there is no separate clock. That loader has always used it as both and
has always been right to. Converting blindly would have broken working code in
the name of safety.

What distinguishes it from the Mersch bug is the direction of the dependency.
There, task became a function of time, so task was perfectly predicted by time
and every dependence measure hit ceiling by construction. Here the two roles
sharing a column are time and phase — two describers of the same axis — and
nothing measured is a function of either. Sharing a column between two describers
of one axis costs nothing. Sharing one between a describer and the thing being
described is what manufactures a finding.

So `pick_columns` gained `allow_alias`: declared role-pairs that may share a
column, each carrying a mandatory reason, recorded in the output metadata.
Undeclared collisions still raise. An alias declared but not firing is reported
as stale, because a permission that has quietly stopped applying is how a guard
decays into a comment. And an alias with a blank reason is refused outright — the
reason is the whole mechanism, the thing that separates a column which really
answers two questions from a collision somebody wanted to stop seeing. If you
cannot write the reason, you have found a bug.

**One loader is deliberately left partly unguarded.** `beesbook` declares `day`
and `cam` in its candidate list but reads neither. `day` and `time` do collide on
a plausible header — a lone `datetime` column matches both — so including `day`
in the guarded set would refuse a file on account of a role the loader never
reads. A guard that blocks correct work teaches people to route around it, and a
guard people route around protects nothing. `USED_ROLES` names the guarded set,
and if day-based binning is ever wired in, `day` joins it on the same commit.

### A day-keyed dict, and the sort that made it wrong instead of missing

The census these fixes depend on was first written as a dict keyed by day, which
is the obvious shape and survives every in-memory test. It is written to
`meta.json`. JSON has no integer keys, so it comes back keyed by string, and
sorted it reads `"0", "1", "10", "11", "2"`. On a 41-day record the last entry is
then day 9, not day 41.

What makes this worth a section is the failure mode. Nothing raises. The census
is present, the count is a plausible number, and the shrinkage figure computed
from the first and last entries is simply a different number than the true one —
on a 12-bin test, 45% against the correct 55%. Wrong, not missing. Both `census`
and `n_by_bin` are now lists of records, which carry their own order through
serialization, and the check that guards them runs to bin 11 on purpose: with
four bins the bug cannot express itself, and a check that cannot fail is not a
check.

### Twenty-four bins is not twenty-four hours

Both contact loaders took a `--bins` argument defaulting to 24, and `gernat.py`'s
docstring described that as "roughly hourly for a day-long trial". It is a bin
*count*, not a bin *width*: the span is divided into that many equal pieces, so
24 bins are hourly only when the record happens to be a day. The Illinois trials
run about five days, where the same flag gives five-hour bins.

Everything these loaders exist to measure is measured across bins — whether the
same individuals stay central from one bin to the next is the question that
separates a persistent structure from a transient one. A bin whose width nobody
wrote down is a unit nobody can interpret, and a five-hour bin is most of a bee's
active period. Bees are strongly diurnal, so which individuals look central in a
bin depends on what time of day the bin covers, and "hub churn" measured on such
a grid is part structure and part sunrise.

The remedy is not to ban wide bins. It is that when the bin width divides 24
hours, bin *k* and bin *k* + 24/width cover the same clock hours and can be
folded onto each other, so time of day becomes a factor you can average over
instead of a term hidden inside the result. When the width does not divide 24 the
boundaries drift against the solar day and the circadian term is not separable at
all. Both loaders now take `--bin-hours` as an alternative to `--bins`, record
`bin_hours` and `bins_per_day` in their metadata, and print a note when the grid
they were given cannot be folded. A record under about thirty hours gets a
different note: there is no second day to fold onto, so at any width the confound
stays.

Saying what a bin is in hours means knowing what unit the timestamps are in, and
none of these deposits guarantee it. `infer_time_unit` reads the magnitude of the
first timestamp to see which unit an absolute epoch would be in, then checks
whether that reading implies a plausible trial length, and reports *unknown*
unless both agree. A frame counter that has run long enough to look like an epoch
in seconds fails the second test. This matters more than it sounds: a bin width
that is wrong by a factor of a thousand is worse than no bin width, because it is
the kind of number that ends up in a table.

The replicate case is where the count-versus-width distinction stops being
cosmetic. `gernat.py` bins within trial, so a fixed count over trials of
different lengths produces bins of different widths — two hours in one colony and
five in another — and the sentence "the same individuals are central in bin 3 of
every trial" then compares a two-hour window with a five-hour one. The loader now
warns when that happens and reports `bin_hours` as null rather than picking one of
the widths, because any single number there is wrong for at least one trial. Given
`--bin-hours` instead it fixes the width and lets the count vary, which is the
trade that makes bin *k* comparable across colonies.

### A contact is an interval, and it was being filed under its start

The Illinois rows carry `begin` and `end`. The loader used `begin` as the
contact's moment and `end` only for a median duration, which quietly makes two
decisions. The observation window closed at the last *start*, so a contact still
in progress when the final one began fell outside the span — on the test fixture
that is a 120-hour record reported as 119. And every contact was assigned to the
bin containing its first instant, which for a long contact is a choice, not a
reading.

Contacts are now binned on their midpoint, the window closes on the last `end`,
and — the part that actually settles the question — the loader counts how many
contacts cross a bin boundary and puts that count in the metadata. If it is a
handful out of a million, the endpoint choice is immaterial and the number says
so; if it is large, the bins are too fine for contacts this long and the number
says that instead. The duration summary gained a maximum alongside the median,
because the maximum is the one that bears on binning: a contact as long as a bin
has a bin assignment that is close to arbitrary. Rows whose `end` precedes their
`begin` are counted separately and kept out of the duration distribution rather
than entering it as negative numbers.

### The colony has three queens, and they were sitting in the network as bees

`bees.csv` classes 2,774 of Gernat's animals as workers and 3 as queens, and
until now the loader read that file for nothing. The three went into the
interaction log as ordinary nodes. A queen in a trophallaxis network is fed
more or less continuously by her retinue, so she is a hub *by caste* — the
colony did not organise itself around her, her ovaries did. Leave her in
unlabelled and "this colony has stable central individuals," which is a
load-bearing sentence for the proposal, may be a restatement of "this colony has
a queen." The information needed to tell those apart was in the deposit from the
first download.

The answer is not to drop her. Dropping her would be its own unrecorded
decision, and how much of the structure rests on three animals out of nine
hundred is a quantity worth having. So both networks are computed and the
*difference* is the output: `netstats.special_nodes_report` reports her rank
among the hubs, centralization with and without her, the share of messages that
leave with her, and who the top hubs are once she is gone.

Two things about that report took a second pass. The first: **removing any node
moves centralization**, because it removes that node's edges and shrinks the
normalisation. The delta is therefore not evidence on its own. Measured on a
61-bee fixture where the marked bee behaved exactly like a worker, removing her
still moved centralization by 14% of its value — past the 5% threshold the note
originally used, and entirely a property of the operation rather than of the
bee. The delta is now compared against the deltas from removing the same *number*
of arbitrary individuals, and the loud note fires only when it falls outside that
range. Both notes still print both figures; what changed is which one gets to
claim the queens mattered.

The second is the join. The queen keys are built on the same `trial:id` namespace
the log uses, because a mark built any other way lands on nobody while every
number downstream still computes — centralization with and without would come out
identical, the report would read as a clean negative result, and the run would
look like it had checked something. That case now stops the run's output with a
warning naming both id spaces. And the caste levels are matched exactly, not by
substring: `queenless` and `queenright` are ordinary words in this literature and
both contain "queen". A deposit whose caste column says something else gets a
note listing the levels it saw and marks nobody, rather than electing the rarest
level and calling it a queen.

### Eleven megabytes should not take four minutes

The first run of the queen work against the real Gernat file sat at 100% CPU
with no output. The obvious readings were all wrong: not a memory problem — RSS
was flat at 81 MB — and not a big file, because `interactions.csv` is 11 MB. The
bug was one line in the binning loop:

```python
lo, hi = span.get(tr, (min(times), max(times)))       # O(n) per message
```

Python evaluates a `.get` default *eagerly*, whether or not the key is present.
So a full scan of every timestamp in the deposit ran once per message and the
loop was quadratic — inside a fallback branch that fires only for a message whose
trial is missing from `span`, which is to say almost never. Measured: 0.60 s at
5,000 rows, 2.41 s at 10,000, 9.09 s at 20,000. Time quadruples when rows double.
Extrapolated to the real table's roughly 390,000 rows, an hour or more.

Two things about this are worth keeping. The first is that every existing test
passed, and would have gone on passing forever, because the largest fixture in
the suite is four thousand rows — where the quadratic term is microseconds. A
cost that only appears at scale needs a check that runs at scale, so `selftest.py`
now builds a real-shaped 200,000-row table and asserts both an absolute ceiling
and, more usefully, that quadrupling the rows does not multiply the time by
sixteen. The ratio is the check that names the *shape* of the cost; a ceiling
alone can be breached by a busy machine and tells you nothing about why.

The second is the failure signature. Piped through `tail`, the loader printed
nothing until it exited, so a quadratic bug and a large file were externally
identical — same pinned core, same silence, same flat memory. It was caught by
arithmetic on the file size rather than by anything in the instrument. That is
not a mechanism, and it is why the check now exists.

### The bench was pooling three colonies, one directory over from the loader that refuses to

`loaders/mersch_net.py` has refused to pool colonies into one graph since the day
it was written, and `selftest.py` has a check that says so. Meanwhile
`loaders/gernat.py` writes all three of Gernat's colonies into a single
`interaction_log.csv`, namespaced `trial:id` — and `run_real_bench.py` read that
file as one network. Bees in different colonies never meet, so the pooled graph
is three components with no edge between them, and Freeman centralization over
it is a statistic about the union: it computes, it prints in the same column as
every other colony, and it is not a colony number. The per-trial figures quoted
here were obtained by hand, outside the bench, which is why the defect survived.

`split_if_disconnected` now splits such a file into one graph per namespace, and
splits the queen marks with it so no colony's report is told about another
colony's queen. It fires on **evidence, not on naming**: ids are grouped by
prefix, and the split happens only when no edge crosses a prefix. A single
crossing edge means the prefixes are labels inside one interacting population,
splitting would delete real edges, and the log is left pooled and said to be.
Both polarities are fixtures in `test_bench_pooling`, along with the case that
has to stay free — a log with no namespaces at all is returned untouched.

### The section that disappeared instead of complaining

Running the bench against the real drive printed division of labour, verdict,
role stability and flexibility — and no COMMUNICATION STRUCTURE block at all.
Exit code 0. The output was complete on its own terms, which is exactly why it
was dangerous: a missing section reads as *no structure to report*, not as
*nothing was looked at*. The cause was mundane. The Gernat loader had been run
with `--out .../data/canonical/gernat_q`; the bench globs `data/processed/`.

The bench now says so. When no logs are found it prints the glob it tried, and
`find_stray_logs` looks one level wider and names any interaction log sitting
elsewhere under the drive, with the instruction to re-run the loader with `--out`
under `data/processed/`. The negative polarity is in the fixture too: a log
correctly nested under `processed/` must not be reported as a stray, or the
message becomes noise and stops being read.

### A z-score of −14.7, and the sentence it was about to become

With the queens settled, the three colonies read out as centralization 0.2564,
0.2387 and 0.3060 against a degree-preserving null, with z of −8.2, −18.7 and
−14.7. Written up unexamined, that becomes "all three colonies are significantly
*less* centralized than chance" — a clean, quotable, publishable sentence, and
wrong.

The statistic and its null do not measure the same thing.
`degree_centralization` counts **distinct partners**. `centralization_null`
shuffles the recipient column. The shuffle preserves the recipient *multiset*,
so it never touches a high-volume receiver: a bee on the receiving end of half
the colony's trophallaxis still receives half of it afterwards, now from senders
drawn at random, and still touches everybody. What the shuffle rewires is
everyone *else* — an ordinary bee's repeated visits to the same few nestmates get
scattered across the whole colony, and her degree rises. Measured on a 300-node
hard star, hub and median degree, observed then in one null draw:

| partner sets | observed hub / median | null hub / median |
|---|---|---|
| narrow | 299 / 38 | 299 / **86** |
| wide | 299 / 86 | 299 / 85 |

The hub survives the null intact both times. The gap closes only because the
median moves. So the z is not a test of whether there is a hub; it is a test of
whether ordinary individuals' partner sets are narrower than their event volume
implies.

That one mechanism breaks the statistic in both directions. On synthetic
networks of 300 nodes and 30,000 events:

| partners each | 5 | 20 | 60 | 150 | 299 |
|---|---|---|---|---|---|
| no hub at all | −7.4 | −15.8 | −3.6 | −0.4 | +0.4 |
| hard star (cen ≈ 0.72–0.97) | +201.3 | +187.4 | +59.7 | +0.2 | −0.7 |

Top row: nothing whatever is centralized and the z reads −16, because contacts
repeat. Bottom row: one individual receives half of everything, centralization
0.72, and the z reads −0.7, because the hub is in the null too. **A large
negative z is not evidence of flatness, and a z near zero is not evidence of no
hub.** Only the positive direction carries information.

### The note that contradicted the number printed beside it

That caveat shipped, as a three-band `z_note` telling the reader a negative z
meant *contacts repeat* and pointing at `events_per_unique_pair`. Then it ran
against the real colonies and printed this:

> z is −18.7, i.e. BELOW the null. Contacts repeat …

next to `events_per_unique_pair = 1.23`. By the table above, 1.23 is the
far-right column — the one where the z should read ±0.4. The note was refuted by
the number on its own line, which is a worse failure than having no note, because
a reader who checks is now told the instrument does not understand itself.

The second attempt blamed the **exponent** relating partner count to event count:
fit log(partners) against log(events), and if busy individuals revisit more than
quiet ones the null inflates them most. It was drafted, and killed by its own
fixture before it shipped. A synthetic in which *every* individual repeats by the
same factor — partner count exactly proportional to activity, so the exponent is
1.0 by construction and fits at 0.98 — scores **z = −22.3**. The exponent was
never the mechanism; it had only been correlated with it in the first synthetics,
which built partner sets as a power of activity and so moved both together.

What was wrong both times is the **reference point**, not the statistic.
`events_per_unique_pair` was being read against 1.0, and 1.0 is not what the null
produces. Shuffling recipients does not hand every event a fresh partner: some
reassigned events land on a partner that individual already has, so the null
graph repeats too, by an amount set by *n* and the event counts. On the
wide-partner star above, the null repeats **2.32 times per pair**. Uniform
repetition of factor *r* divides every degree by *r*, and so divides
centralization by *r* — the observation is compressed by the repetition it has,
the null by the repetition *it* has, and the z is the difference between them.

So the question was never "do contacts repeat" but "do they repeat **more than a
random re-assignment of the same event counts** would repeat". That ratio is
`partner_narrowing.narrowing`, and it predicts the sign of the z in every
synthetic here that does not contain a genuine hub:

| | narrowing | z |
|---|---|---|
| no repetition beyond chance | 0.96 | +22 |
| everyone repeats ×2 | 1.92 | −22 |
| everyone repeats ×4 | 3.74 | −20 |
| hard star, partner sets wide | 1.00 | −1.8 |

And it dissolves the paradox. At *n* ≈ 900 a random re-assignment gives about
**1.03** events per pair, so Gernat's 1.23 is not "almost no repetition" — it is
**twenty per cent narrower than chance**, and the null's spread across
permutations is small enough to make twenty per cent worth a z of −18.7. A
synthetic colony with no hub in it at all, in which only the busiest tenth revisit
and only at a factor of two, reads 1.27 events per pair against a null of 1.03
and scores **z = −21.6** at centralization 0.096. That is the real colonies'
reading, produced by a network with nothing centralized in it.

Consequences, all enforced rather than remembered. `structure_report` carries
`partner_narrowing` — observed repetition, the null's own repetition, and the
ratio — so the observed figure can no longer be printed without the number it
must be read against, and the `z_note` quotes the ratio and both endpoints
inline. `null_definition` states that the shuffle leaves a volume hub intact
*and* that it does not give every event a fresh partner. `run_real_bench.py`
prints the narrowing line directly beneath the centralization line.
`test_null_calibration` in `selftest.py` now carries the fixture that killed the
exponent and the fixture that reproduces Gernat, and a check asserting that no
calibrated fixture lands in the "not accounted for" branch — so if a real colony
ever trips it, the explanation genuinely does not cover that reading.

The number to quote for the colonies is **centralization 0.2564 / 0.2387 /
0.3060** against the synthetic bench range. Not the z, and never the z with an
explanation attached that has now been wrong twice.

### Nested archives, and what "complete" was allowed to mean

The Dryad bundle expands to a `tracking_data.zip` and stops. `fetch_data.py`
unzipped one level, so the folder was not empty, the manifest said complete, and
the summary printed "2/2 datasets complete" — every one of those statements true
about *downloading* and false about *readability*. Expansion now recurses (depth
capped, self-referential archives visited once, and it descends past an outer
archive whose marker already exists, since a resumed run would otherwise inherit
the original bug), and a final disk-level scan reports any archive still packed.
That scan is separate from the empty-folder scan on purpose: an unexpanded zip
*is* payload by the emptiness test.

### Why a static label is worse than a missing one

Flexibility being undefined is the least of it. With one label per individual
for the whole record, mutual information between individual and task is the
entire entropy of the task variable, so DoL is 1.0; the modal task in every
window is the only task, so role-stability kappa is exactly 1.0. Both are
arithmetic restatements of "the label never changes", and neither raises.

The permutation null does not save us either — it shuffles labels across
individuals, so it scores low, the corrected DoL stays near 0.8, and the verdict
prints *strong division of labour* for a colony in which nothing was ever
observed to vary. `selftest.py` asserts exactly that, so the point cannot be
quietly lost.

So `run_real_bench.py` checks within-individual variation **before** running any
instrument, and a dataset with none is printed as `WITHHELD` with no numbers at
all. Attaching a caveat instead would not work: a number in a table gets quoted,
and the caveat does not travel with it.

The static label is still useful — as a covariate rather than a task. Do ants
the authors clustered as foragers respond to the removal differently from ones
clustered as inactive? That is the "who takes up the slack" question, and it is
the organizationally interesting one.

---

## Measure

```bash
python3 run_real_bench.py --root $D --synthetic
```

Four things come out, in the same measurement space as `bench.py`:

**Division of labour**, reported three ways — raw, permutation null, and the
difference. Only the difference is quotable. Normalized MI is upward-biased on
sparse individual × task tables, and with 4,000 bees over 400 time bins the
table is extremely sparse: a colony of *randomly behaving* individuals still
scores a positive raw DoL. The self-test demonstrates this on data where the
true answer is zero. Reporting an uncorrected DoL from tracking data is the
easiest way to publish something that will not replicate.

**Specialization**, with a bootstrap CI resampled over individuals rather than
over observations, because repeated sightings of one bee are not independent
evidence.

**Role stability** — does the same individual keep the same task across time
windows, against the chance level implied by the task frequencies. High
specialization with *low* stability is the more interesting organizational case:
individuals specialize at any moment while the assignment churns. That is
"same algorithm, different input, different output" in measurable form.

**Flexibility around a shock**, for Charbonneau & Dornhaus. With real data
demand is unobserved, so unlike the synthetic bench we cannot score allocation
against an optimum. What we can measure is the response: how far the aggregate
task distribution moved, how many individuals changed their modal task, and how
long the colony took to settle. An aggregate mix that barely moves while a third
of individuals switch tasks is resilience that no org chart encodes — and it is
exactly the comparison the proposal needs.

**Replication across colonies**, from the five Illinois portal trials. They are
independent colonies recorded the same way, which makes them the cheapest
available answer to the most fragile claim in a study like this one — that a
network result is a property of colonies rather than of the one colony we
looked at. `run_real_bench.py` prints the spread across trials and how many fall
below the degree-preserving null. Quote the spread. A result that holds in one
of five is not a result, and finding that out is worth more than the result we
were hoping for.

Separately, `netstats.py` runs the structure instruments on Gernat's directed
trophallaxis log. Expect **low** centralization: bees have no reporting lines,
and recovering a crisp hierarchy would be evidence that the instrument
hallucinates structure, not that the colony has any. The result worth having is
low centralization *with* stable hubs — decentralized yet differentiated, the
regime organizational design finds hardest to produce deliberately.

---

## Files

| file | what it does |
|---|---|
| `sources.py` | the dataset registry: DOIs, tiers, licences, and why each one is here |
| `fetch_data.py` | resolves Zenodo/Dryad records through their APIs and downloads, resumable and MD5-verified |
| `inspect_data.py` | prints the real columns of whatever arrived; run before writing any analysis |
| `loaders/*.py` | one converter per deposit, all emitting the same format |
| `loaders/common.py` | shared column resolution, the collision guard and its declared aliases, missing-value handling, time-unit inference and bin planning, the event builder |
| `loaders/illinois.py` | the five portal trials: undirected contact logs, one output dir per colony, contacts binned as intervals |
| `loaders/mersch_net.py` | the 246 daily matrices as one contact log per colony; refuses to pool colonies, and refuses the join to `behavior.csv` |
| `instruments.py` | bias-corrected DoL, bootstrap CIs, role stability, flexibility |
| `netstats.py` | centralization against a degree-preserving null (with the note saying what that null does and does not detect, and the narrowing ratio that says what a negative z is made of), hub stability, and the structure recomputed without the marked queens |
| `validate_dornhaus.py` | checks our column reading against the numbers the paper reports independently |
| `validate_gernat.py` | the three-table join, direction tokens, and the censored death column |
| `validate_mersch.py` | column binding, the wide period columns, the change figure and its missingness gate, and the two colony vocabularies |
| `run_real_bench.py` | runs everything on whatever converted successfully |
| `selftest.py` | fabricates data with a known answer and checks the instruments recover it |
| `bench.py` | the synthetic systems, unchanged, for the comparison rows |

## Licences

Mersch, Charbonneau & Dornhaus, Kay, Richardson and Alciatore are CC0. BeesBook
is CC-BY-4.0. Gernat's Zenodo deposit is CC-BY-NC-4.0 — fine for research, worth
noting before any commercial reuse. `btools` is AGPL-3.0. The George/Frank
repository states no licence and is not public yet (see below).
Every licence is repeated per file in `MANIFEST.json`.

## Not included

Two datasets are wanted and not obtainable today. Both are recorded rather than
quietly dropped, because a reviewer asking "why no exposure-network data?"
deserves a better answer than silence.

**Stroeymeyt et al. (2018)**, the pathogen-exposure network data, is restricted.
That one needs an email to Nathalie Stroeymeyt at Bristol.

**George, Motes-Rodrigo, Keller & Frank (2026)**, *Social and spatial affinity
drive wound care by ants*, PNAS doi:10.1073/pnas.2614400123 (preprint
10.1101/2025.10.08.681151). The paper names
`github.com/EbiAG/wound-care-interaction-networks` in its data availability
statement, and that URL is the one in `sources.py`, but GitHub currently serves
it as 404 to unauthenticated clients — which is what it does for a *private*
repository. git then falls back to asking for a username, which is the
"could not read Username for 'https://github.com'" error. **No amount of
`gh auth login` fixes this**: a personal account cannot clone a repository it
has not been granted access to. The fix is an email to Ebi Antony George or
Erik Frank at Würzburg asking them to flip the deposit public. `fetch_data.py`
now marks it `kind="pending"`, writes the request note, and counts it apart from
both the successes and the failures.

It is worth asking for. The paper's own result — wound care performed by a
*non-specialized* subset whose behaviour sits between nurse and forager, with
allocation predicted by prior spatial and social proximity to the injured in the
preceding hours — is the proposal's "role differentiation without role
assignment" claim, already demonstrated in an insect, with a clean exogenous
shock attached.
