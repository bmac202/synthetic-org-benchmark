# Structure-provenance report

Source: `examples/example_log.csv`  
Runs: 3; label-permutation baseline: 95th percentile of 200 draws per run and dimension.

## Is there structure? Persistence against each run's own baseline

Each cell is observed persistence / baseline; **bold** = above baseline.

| run | individual | functional | relational | structural | top receiver |
|---|---|---|---|---|---|
| fixed_names_seed0 | 0.12 / 0.19 | 0.13 / 0.18 | 0.36 / 0.39 | **0.38** / 0.18 | A1 |
| fixed_names_seed1 | 0.10 / 0.18 | 0.04 / 0.19 | 0.36 / 0.37 | **0.44** / 0.19 | A4 |
| fixed_names_seed2 | 0.10 / 0.19 | 0.11 / 0.19 | 0.33 / 0.35 | **0.35** / 0.19 | A1 |

## Across runs

| dimension | runs above baseline | median [bootstrap 95% CI] | median baseline |
|---|---|---|---|
| individual | 0 of 3 (chance ≈ 0.2) | 0.10 [0.10, 0.12] | 0.19 |
| functional | 0 of 3 (chance ≈ 0.2) | 0.11 [0.04, 0.13] | 0.19 |
| relational | 0 of 3 (chance ≈ 0.2) | 0.36 [0.33, 0.36] | 0.37 |
| structural | 3 of 3 (chance ≈ 0.2) | 0.38 [0.35, 0.44] | 0.19 |

## Signatures (diagnostic, not decisive)

- Same member is top receiver in 2 of 3 runs (member A1); mean cross-run rank correlation of interactions received +0.75. Recurrence of the same member across independent runs points to prescribed or label-induced structure when member identities are comparable across runs.

## Is it robust, and where did it come from?

One condition's logs establish persistent differentiation, not its source. Run this report on logs from matched conditions (shuffled or balanced labels, wiped histories, cut communication, reassigned roles) and compare the counts and medians above; the technical appendix gives the contrasts and decision rules.

