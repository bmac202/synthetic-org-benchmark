# Known-answer test of structure-provenance analysis

| condition | task type | hub | work given opportunity | task type within rounds 1-50 / 51-100 | continuity across the midpoint | same favourite type across runs (chance 0.25) | same top receiver across runs |
|---|---|---|---|---|---|---|---|
| No source (equal fixed thresholds) | 0.09 (0.19) 0/20 | 0.08 (0.19) 2/20 | 0.10 (0.18) 1/20 | 0.18 (0.33) 0/20 / 0.17 (0.34) 0/20 | 0.23 (chance 0.25, p95 0.31) | 0.26 | 4/20 |
| Prescribed (assigned thresholds) | 0.49 (0.20) 20/20 | 0.09 (0.19) 0/20 | 0.10 (0.18) 2/20 | 0.57 (0.35) 20/20 / 0.50 (0.35) 20/20 | 0.96 (chance 0.26, p95 0.32) | 1.00 | 4/20 |
| Generated (thresholds learned from own history) | 0.35 (0.19) 20/20 | 0.10 (0.19) 0/20 | 0.10 (0.19) 0/20 | 0.36 (0.34) 12/20 / 0.45 (0.34) 19/20 | 0.43 (chance 0.26, p95 0.31) | 0.23 | 4/20 |
| Generated, history wiped at round 50 | 0.19 (0.19) 8/20 | 0.09 (0.19) 0/20 | 0.07 (0.19) 1/20 | 0.36 (0.34) 12/20 / 0.39 (0.34) 15/20 | 0.24 (chance 0.25, p95 0.30) | 0.25 | 5/20 |
| Generated, agents never communicate | 0.25 (0.19) 18/20 | — | 0.09 (0.19) 1/20 | 0.30 (0.34) 7/20 / 0.32 (0.35) 8/20 | 0.39 (chance 0.26, p95 0.31) | 0.24 | — |
| Prescribed, specialties reassigned at random each run | 0.55 (0.19) 20/20 | 0.12 (0.19) 0/20 | 0.11 (0.18) 0/20 | 0.57 (0.35) 20/20 / 0.59 (0.35) 19/20 | 0.96 (chance 0.26, p95 0.32) | 0.24 | 4/20 |
| Prescribed, reassigned at random, history wiped at round 50 | 0.55 (0.19) 20/20 | 0.12 (0.19) 0/20 | 0.11 (0.18) 0/20 | 0.57 (0.35) 20/20 / 0.59 (0.35) 19/20 | 0.96 (chance 0.26, p95 0.32) | 0.24 | 4/20 |
| Design-induced (prefers label “A1”) | 0.09 (0.19) 0/20 | 0.97 (0.19) 20/20 | 0.09 (0.18) 1/20 | 0.18 (0.34) 0/20 / 0.18 (0.34) 0/20 | 0.23 (chance 0.24, p95 0.28) | 0.26 | 20/20 |
| Design-induced, labels shuffled (Latin square, as in the LLM reruns) | 0.09 (0.19) 0/20 | 0.32 (0.19) 20/20 | 0.06 (0.19) 0/20 | 0.18 (0.34) 0/20 / 0.16 (0.34) 0/20 | 0.18 (chance 0.24, p95 0.29) | 0.25 | 4/20 |
| Design-induced, labels shuffled (balanced) | 0.10 (0.19) 1/20 | 0.10 (0.19) 0/20 | 0.08 (0.19) 1/20 | 0.19 (0.34) 0/20 / 0.18 (0.34) 0/20 | 0.25 (chance 0.25, p95 0.30) | 0.25 | 5/20 |

Cells: median R (median shuffled baseline, 95th percentile) and seeds above it / seeds. Same top receiver: the largest number of seeds in which one and the same agent received the most tells.

## Contrasts (95% bootstrap intervals over runs)

- continuity: no wipe minus wipe (paired by seed): +0.19 [+0.10, +0.28]
- continuity, prescribed at random: no wipe minus wipe (paired by seed): +0.00 [+0.00, +0.00]
- task-type R: communication minus no communication (unpaired): +0.09 [+0.06, +0.13]

Mean items an agent could work per round (median over runs): No source (equal fixed thresholds) 2.18, Prescribed (assigned thresholds) 3.03, Generated (thresholds learned from own history) 2.36, Generated, history wiped at round 50 2.27, Generated, agents never communicate 1.78, Prescribed, specialties reassigned at random each run 3.00, Prescribed, reassigned at random, history wiped at round 50 3.00, Design-induced (prefers label “A1”) 3.10, Design-induced, labels shuffled (Latin square, as in the LLM reruns) 3.09, Design-induced, labels shuffled (balanced) 3.11
