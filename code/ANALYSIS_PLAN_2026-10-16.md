# Analysis plan for the confirmatory comparisons

Written 16 October 2026, 22:25 UTC. The replication runs (`code/run_replications.sh`) started
at about 22:13 UTC. By then only journal line counts (calls completed) had been read; no
outcome, specimen or score of a new run had been looked at. The balanced-shuffle runs
(`code/run_balanced.sh`) had not started.

Everything in Stage 1 before this date is **exploratory**: the measures, controls and artifact
checks were developed while looking at results. This plan fixes the analysis for the
comparisons that follow it. The scoring code is unchanged from 30 September:
`track_alias.tables` for the hub measure and `measures.specialization` for task type, with 200
label permutations per baseline.

## Primary outcomes

- **Hub persistence**: repeatability R of tells received per agent per 10-round window,
  against the run's own 95th-percentile label-permutation baseline.
- **Task-type persistence**: favoured-type R (`measures.specialization`), against the run's own
  95th-percentile baseline.

A run counts as "above baseline" if its R exceeds that percentile. Under the null, about 5% of
runs exceed it. With 10 runs per cell, 2 or fewer above baseline is treated as consistent with
chance (binomial P(X ≥ 3 | n = 10, p = 0.05) ≈ 0.012). 8 or more above baseline is treated as
a reliable effect.

## Comparisons

**C1. The "A1" artifact, original protocol.** gpt-4.1-mini, identical agents (C1, private
visibility). Fixed names, seeds 0–9, against the Latin-square shuffle (`--alias`), seeds 0–9.
- The artifact replicates if at least 8 of 10 fixed-name runs are above baseline on hub
  persistence and the agent named "A1" is the top receiver in at least 8 of 10.
- The shuffle removes it if at most 2 of 10 shuffled runs are above baseline. With 3 or more,
  we report a residual effect, which the known-answer test leads us to expect from this shuffle.

**C2. The "A1" artifact, corrected protocol.** The same 10 fixed-name runs, against the
balanced shuffle (`--alias-balanced`), seeds 0–9. Same rules as C1.

**C3. Coordination without a division of labor.** For each model separately (gpt-4.1-mini and
Claude Haiku 4.5): identical agents with the Latin-square shuffle (seeds 0–9) against agents
told a specialty (C2, seeds 0–9).
- The contrast holds if at least 8 of 10 specialty runs and at most 2 of 10 identical-agent runs
  are above baseline on task-type persistence.
- Any other pattern is reported as found. Identical-agent runs that do specialize will be
  examined, not discarded.

## Secondary and multiplicity

For each comparison we also report medians, ranges and a two-sided Mann–Whitney test on R,
with Holm correction across the four tests (C1, C2, C3 for gpt, C3 for Haiku). All other
diagnostics are reported as counts above baseline against the 5% expected by chance, and are
labelled exploratory.

## Known-answer test

`diffenv/ground_truth.py` with seeds 0–19 and the parameters in that file (xi = 0.3, phi = 0.1,
reset at round 50). It is a methods check, not a hypothesis test; it is reported in full.

## Deviations

Any departure from this plan, including runs that fail and are repeated, is reported with the
results.
