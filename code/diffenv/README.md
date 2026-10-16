# diffenv — the differentiation environment

Built 29 September 2026 from `spec_differentiation_environment.md` (13 August), extended with
two factors added in September 2026. Standard
library plus numpy; the LLM backends need `anthropic` / `openai` and an API key.

**The question it answers.** Do initially exchangeable agents — same model, same prompt,
different only in what they happen to see — come to differ persistently in how much they do,
whom they talk to, and what they work on? That is the dependent variable the ant and human
legs already have numbers for (R = 0.51 clonal ants; 0.37 / 0.31 office workers) and the
synthetic leg did not.

## Layout

```
env.py           the open queue with partial visibility; logs {t, round, window, sender,
                 recipient, mtype, payload} — orglib-poc's schema plus round/window
policies.py      C0 rule (exchangeable), C0+ rule specialists, LLMPolicy (C1/C2/C3),
                 backends (anthropic, openai, mock), the one-line action parser
measures.py      the differentiation protocol as one function for every substrate:
                 standardize within org×window → R, split-half, label-permutation null
                 (200 draws) → plus entropy vs type-shuffle null, favoured-type R,
                 partner Jaccard vs random sets
run.py           CLI; writes one specimen JSON per run
report.py        aggregates specimens into a markdown table
test_measures.py seven fixtures; run before anything else
```

## Conditions and factors

| id | what | role |
|---|---|---|
| C0 | rule agents, coin-flip between work and tell | floor — must sit at the null |
| C0+ | rule agents with fixed, different propensities and favourite types | rule-based positive control — proves the measure can see structure |
| C1 | LLM agents, identical prompt, no roles, names or personas | the finding |
| C2 | LLM agents, each told a specialty type | LLM positive control |
| C3 | LLM agents, distinct dispositions, no functional roles | does injected variance persist? (Big-Five persona prompts) |
| `--competence` (C4) | each agent succeeds at one type with p=.95, others p=.35; not told which | skill-based division of labour as a positive control |
| `--exit` (C5) | a permanent `leave` action | exit as a manipulable factor |

## Credentials and cost safeguards (added 29 September, evening)

- Keys are read from `keys.env` (project root) by `keys.py` into the process environment
  only. They are never printed, logged, or copied; `keys.env` is git-ignored at the root and
  in `code/`. `keys.describe()` reports only whether each name is set.
- `MAX_API_CALLS` (default 25) and `MAX_COST_USD` (default 1.00) are hard caps checked before
  every call. Any run planning more than 25 calls refuses to start unless `--full-run` is
  passed *and* `--max-calls` covers it. Retries are bounded (4 attempts, 2/4/8/16 s backoff,
  capped at 30 s); authentication and bad-request errors are not retried.
- Every completed call is journaled (`--journal-dir`, JSONL, keyed by specimen/round/agent).
  A failed call journals nothing, so it cannot create a duplicate; a restarted run replays
  the journal and makes only the missing calls, reproducing the identical trajectory.
- Each specimen records provider, model (as the API reported it), condition, seed, factors,
  per-run tokens and estimated cost, and whether `temperature` was actually applied.
  Anthropic has deprecated `temperature` on Opus 4.7+, Sonnet 5 and Fable 5; Haiku 4.5 and
  Sonnet 4.5 still accept it (sent in the raw body). This is worth a sentence in the paper:
  one of the researcher's variance levers no longer exists on frontier models.
- `api.openai.com` is unreachable from the Cowork cloud workspace and from the VM linked to
  the author's computer (network policy). The OpenAI backend is written and mock-tested but has never
  made a real call.

## Run

```
python3 -m diffenv.test_measures                                     # measurement fixtures first
python3 -m diffenv.test_pipeline                                    # then the mock pipeline tests
python3 -m diffenv.run --condition c0     --seeds 0 1 2
python3 -m diffenv.run --condition c0plus --seeds 0 1 2
python3 -m diffenv.run --condition c2 --backend anthropic --model claude-haiku-4-5 --seeds 0 1 2
python3 -m diffenv.run --condition c1 --backend anthropic --model claude-haiku-4-5 --seeds 0 1 2
python3 -m diffenv.run --condition c1 --backend openai    --model gpt-4o-mini       --seeds 0 1 2
python3 -m diffenv.report results/specimens
```

Set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in the environment. One run is
9 agents × 100 rounds = 900 short calls.

## What the floor showed (29 September)

Over 40 seeds of C0: mean R 0.093 / 0.097 / 0.093 (activity / interaction / isolation)
against null medians 0.095 / 0.095 / 0.094; 1 / 3 / 1 of 40 above the null 95th percentile.
The measure does not manufacture differentiation. C0+ over 3 seeds: R activity 0.70–0.78,
favoured-type R 0.73–0.81, entropy 0.46–0.50 against null ~0.72. The measure sees structure
when it is there. The competence factor on C0 alone: 0/12 seeds beyond the null on either
measure, so whatever appears under C4 is agents responding to their own history.

## Deviations from the 13 August spec, and why

- **C0 is stochastic.** The literal rule ("work the first known item") makes every agent
  equally active every window; there is nothing to standardize and R is undefined. Fixture F4
  keeps that case and checks it is reported as degenerate rather than as a number.
- **`round` and `window` are logged on every row** in addition to `t`, so the window
  boundary is a fact of the log rather than something reconstructed from it.
- **Specialization entropy counts work *attempts*, not successes.** Under the competence
  factor the choice is the dependent variable; success is the environment's reply to it.

## Pilots, 29 September evening — 295 Haiku 4.5 calls (≈ $0.13) and 228 gpt-4.1-mini calls (≈ $0.04)

All pilots are 9 agents × 5 rounds, one seed, unless noted. Nothing has run at full length.

**Sampled visibility (the 13 August design), both models, three seeds:** 45 of 45 actions
`work`, zero `tell`s, activity identical across agents every round (degenerate, R undefined).
Herding onto the same items survives randomizing item order, so it is not list-position bias;
it looks like a rational focal point (everyone tries to finish the item showing "1 of 2 done").
Reading: when communication is unnecessary, identical agents produce identical behaviour and
never communicate. Kept as the boundary case.

**Private visibility (each item revealed to one agent; a second worker only via `tell`), both
models, after the rendering fixes below:** Haiku 28 work / 8 tell / 9 pass, gpt-4.1-mini
26 / 7 / 12; 5 of 30 done on each; tells spread over 4–7 recipients; on gpt, 5 of 7 tells were
about an item the sender had half-finished and the recipient completed all 5. Reading: when a
colleague's knowledge is necessary and the move is visible, identical agents begin to
coordinate. Whether *particular* agents become the tellers over ten windows — the DV — needs
the full 100 rounds. **Design settled: private visibility, shuffled view, opportunity-
conditioned activity.**

**C2 (role-prompted) on both models:** agents worked their assigned type in 31/33 (Haiku) and
25/29 (gpt) work actions; gpt also routed off-type items to the right specialist. The measure
sees structure when a prompt injects it.

### Three instrument artifacts caught by the pilots — appendix material

1. **Item order.** Known items were listed sorted by id; both models took the first-listed
   item. Now shuffled per observation (seeded). Herding survived the fix, so it is real.
2. **Recipient order.** The first name in "Other people:" received 7 of 8 tells on Haiku and
   5 of 14 on gpt, producing an "emergent hub" with interaction R = 0.51 above the null.
   Shuffling the names removed it entirely (R at the null). Structure manufactured by the
   prompt, caught by the calibration logic; before/after specimens in `diffenv_results/`.
3. **Exposure.** Under private visibility an agent that receives no item can only pass, so
   raw activity R (0.35–0.40) reported luck of arrival as individuality. Added
   `activity_given_opportunity` (work per round with something workable): floor 0.08, rule
   specialists 0.74, and on the gpt private pilot 0.09 against a raw 0.35. Quote the
   conditioned measure under private visibility, never the raw one.

Also fixed: worked items were hidden from the agent's own view, so the key private-mode move
(tell someone about the item you half-finished) was never presented as available; both models
passed instead. And the C0 floor's apparent 0.02 excess was a mean compared to a median of a
right-skewed statistic — against the null's mean the gap is 0.007 (pure-noise tables: 0.099
vs 0.100). The 100-seed floor under both visibilities: 6–9 of 100 above the null 95th
percentile (5 expected).

**Costs.** Steady-state prompt ≈ 450–500 input tokens, 6–7 output. Per 900-call run:
≈ $0.50 Haiku 4.5, ≈ $0.20 gpt-4.1-mini, ≈ $1.50 Sonnet 4.5.

## Full-length results, 29–30 September — 13 Haiku 4.5 runs (11,700 calls, ≈ $5.78) and 11–13 gpt-4.1-mini runs (≈ $2.20)

Final environment: private visibility, shuffled view, 9 agents, 100 rounds in 10 windows,
K=6, four types, W=5. Tables: `diffenv_results/final/summary_both_models_2026-09-30.md`.
Under private visibility quote **R activity given opportunity**, never raw R activity (which
reads arrival luck as individuality — gpt C1 raw 0.23 above the null in 3/3 seeds, conditioned
0.10 below it in 3/3).

| condition | what was injected | Haiku 4.5 | gpt-4.1-mini | reading |
|---|---|---|---|---|
| C0 rule, exchangeable | nothing | R|opp 0.13 (null p95 0.18), 0/3 | — | floor holds |
| C0+ rule, fixed propensities | differences by construction | R|opp 0.80, 3/3; favoured-type R 0.34 | — | measure sees structure; type-specialization harder to see under private visibility (agents can only work what they are given) |
| **C1 identical prompt** | nothing | **R|opp 0.04 / 0.08 / 0.07** (p95 ≈ 0.18); split-half −0.60 / −0.67 / 0.00; entropy at null; favoured-type R 0.09–0.11 | **R|opp 0.12 / 0.10 / 0.10** (p95 ≈ 0.18); split-half 0.13 / 0.05 / 0.02; entropy at null | **no persistent differentiation, on either model** — C1 ≈ C0 |
| C2 role-prompted | a specialty per agent | favoured-type R 0.61 (p95 0.18); entropy 0.41 vs 0.64 | favoured-type R 0.76 (p95 0.22); entropy 0.38 vs 0.63 | positive control passes on both |
| C3 persona-prompted | a disposition, no role | R|opp 0.57 / 0.56 / 0.32, 3/3; entropy at null | R|opp 0.62 median, 3/3; R interaction 0.46, 3/3; entropy at null | injected disposition persists across all ten windows; it changes *how much*, never *what* — no division of labour by type |
| C4 competence heterogeneity, unannounced | skill differences, learnable only from own failures | R|opp at null 0/3; own-good-type share 0.22–0.28 in both halves (chance 0.25); done 34–49 | same: 0.22–0.27 both halves; done 47–50 | neither model learns its competence from feedback; skill-based division of labour does not emerge |
| C5 permanent `leave` available | an exit option | 0 leaves in 2,700 actions; otherwise ≡ C1 | 0 leaves in 900+ | the option exists and is never taken; behaviour unchanged |

**Coordination without differentiation.** C1 agents communicate (≈ 190 tells per 900 actions
on Haiku, ≈ 230 on gpt), and complete 100–122 (Haiku) and 145–162 (gpt) of 600 items — more
than role-prompted C2 agents (88 / 43, who become routers: 475 tells to 369 work on Haiku) and
twice the rule agents (≈ 57). A population of identical LLM agents coordinates well, through
communication, without any individual becoming anything in particular.

**The three-way, stated once.** Nothing injected → nothing persists (C1). A role injected →
division of labour appears (C2). A disposition injected → it persists, modestly, without
becoming division of labour (C3). The heterogeneity a synthetic organization displays is the
heterogeneity the researcher wrote into it. Against that: clonal ants R = 0.51 and office
workers R = 0.37 / 0.31 on the same statistic, with the comparability caveats in RESTART.md
(different constructs, bins and pools; the ant `interaction` recompute is still owed).

**Not quotable / caveats.** One seed for C2 per model. The ant and human numbers are from
August code that is not in the repository. Magnitude comparisons across substrates wait on the
one-construct recompute. Zero to four unparseable replies per 2,700 calls.

## The ant and human legs, re-run through the same code — 30 September

`substrates.py` loads `IndividualBehavioursData.xlsx` (Alciatore et al. 2021) and the two
SocioPatterns InVS deposits into the long table; `run_substrates.py` scores them with
`measures.differentiation()`. The 13 August script was on neither the folder nor the OWC
drive; it was recovered as a *specification* by matching its counts and numbers:

- sample rules: naive ants in colonies observed in ≥ 4 of the 9 windows (154 ants, 22
  colonies; 2 colonies with 3 windows dropped); people present on ≥ 4 of the 10 days (87 in
  2013, 204 in 2015); a person with no contact on a day is absent, not zero;
- variance convention: August used **population** variances (numpy's default). With
  `ddof=0` all five August R values reproduce to three decimals. The project convention is
  now **sample** variances (`ddof=1`, as in every synthetic run), because the population
  version's inflation depends on the number of windows, which differs across substrates.
- split-half: August's exact split was not recovered (ants +0.58 to +0.65 here vs +0.66 to
  +0.70; humans match within 0.005 under a per-person split). All variants sit far above
  their null (p95 ≈ +0.13). R, the quoted statistic, is the one that reproduces.

| substrate | construct | n | windows | **R (ddof=1)** | null p95 | R (ddof=0) = August |
|---|---|---|---|---|---|---|
| clonal ants, naive | activity | 154 | 9 | **0.481** | 0.130 | 0.512 |
| clonal ants, naive | isolation | 154 | 9 | **0.529** | 0.130 | 0.560 |
| clonal ants, naive | speed | 154 | 9 | **0.517** | 0.129 | 0.548 |
| InVS 2013 office | contact slices/day | 87 | 10 | **0.336** | 0.156 | 0.370 |
| InVS 2015 office | contact slices/day | 204 | 10 | **0.283** | 0.144 | 0.312 |

Provenance: InVS files were fetched by `fetch_data.py` on 14 August into
`BeeOrg/data/raw/sociopatterns_workplace_2013` and `_2015` on the OWC drive (RESOLVED.json
there records URLs but no digests — SocioPatterns publishes none, so adoption verified size
only). The ant workbook came from the Alciatore Dryad deposit (`BeeOrg/data/raw/alciatore_2021`).

Quote with: the magnitudes are still not comparable across substrates (activity vs contact
volume; 3–6 h windows vs days; 7 ants per colony vs 87–204 people per day). The ant
`interaction` recompute from the `Network_1mmDist6h` matrices is the remaining step.

## One construct across every substrate — `interaction`, 30 September afternoon

| substrate | interaction measure | n | pool | windows | **R** | null p95 |
|---|---|---|---|---|---|---|
| clonal ants, naive (Alciatore) | seconds within 1 mm, all nestmates | 154 | 7 | 9 × 3–6 h | **0.676** | 0.131 |
| clonal ants, naive (Alciatore) | same, naive nestmates only | 154 | 7 | 9 | **0.669** | 0.131 |
| ants with queen (Mersch) | interactions per day | 822 | ≈100 | 41 days | **0.560** | 0.042 |
| honey bees (Gernat) | trophallaxis events per day | 2,382 | ≈820 | 5 days | **0.434** | 0.176 |
| office 2013 / 2015 (InVS) | contact slices per day | 87 / 204 | 87 / 204 | 10 days | **0.336 / 0.283** | 0.156 / 0.144 |
| office, random pools of 7 | same | 87 / 204 | 7 | 10 days | 0.325 / 0.306 | 0.160 / 0.138 |
| C1 Haiku 4.5 (3 seeds) | tells sent + received per window | 9 | 9 | 10 | 0.16 / 0.07 / 0.15 | ≈ 0.19 |
| C1 gpt-4.1-mini, fixed names (3 seeds) | same | 9 | 9 | 10 | 0.20 / 0.37 / 0.16 — label artifact | ≈ 0.19 |
| C1 gpt-4.1-mini, randomized names (3 seeds) | same | 9 | 9 | 10 | **0.15 / 0.08 / 0.15** | ≈ 0.19 |

The gpt row is a label artifact, not differentiation: see RESTART.md, 30 September afternoon
(name preference for "A1"/"A4", against "A8", identical across six runs). Mersch and Gernat
rows are a first look (`diffenv_results/substrates_2026-09-30b/first_look_other_colonies.py`);
Mersch ants are not exchangeable (age, task group) and the queen is not removed. Windows
differ in length across substrates; pools do not explain the ant–human gap.

## Not yet done
- Done 30 Sept: C1 and C1+exit on gpt-4.1-mini with `--alias` — all measures at the null (see RESTART.md, `diffenv_results/alias_rerun/STATUS.md`). Still open: C2/C3 on gpt and all Haiku runs used fixed names.

- Done 16 Oct: Haiku C1 with `--alias` (seeds 0–2) and a second C2 seed per model (`diffenv_results/gaps_2026-10-16/`).
- The OpenAI leg runs from a local machine (`api.openai.com` is blocked from the cloud
  workspace); specimens land in the shared folder.
- Re-running this module on the ant (`IndividualBehavioursData.xlsx`) and InVS tables — the
  August script for those numbers was never committed; `measures.differentiation()` takes the
  same long table and is the repair. Needs the data staged.
