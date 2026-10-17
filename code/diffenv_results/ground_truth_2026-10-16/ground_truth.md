# Known-answer test of the emergence audit

| condition | task type | hub | work given opportunity | task type, rounds 1-50 / 51-100 | same favourite in both halves (chance 0.25) | same favourite type across runs (chance 0.25) | same top receiver across runs |
|---|---|---|---|---|---|---|---|
| No source (equal fixed thresholds) | 0.09 (0.19) 0/20 | 0.08 (0.19) 2/20 | 0.10 (0.18) 1/20 | 0.18 / 0.17 | 0.22 | 0.26 | 4/20 |
| Prescribed (assigned thresholds) | 0.49 (0.20) 20/20 | 0.09 (0.19) 0/20 | 0.10 (0.18) 2/20 | 0.57 / 0.50 | 1.00 | 1.00 | 4/20 |
| Generated (thresholds learned from own history) | 0.35 (0.19) 20/20 | 0.10 (0.19) 0/20 | 0.10 (0.19) 0/20 | 0.36 / 0.45 | 0.44 | 0.23 | 4/20 |
| Generated, history wiped at round 50 | 0.19 (0.19) 8/20 | 0.09 (0.19) 0/20 | 0.07 (0.19) 1/20 | 0.36 / 0.39 | 0.22 | 0.25 | 5/20 |
| Design-induced (prefers label “A1”) | 0.09 (0.19) 0/20 | 0.97 (0.19) 20/20 | 0.09 (0.18) 1/20 | 0.18 / 0.18 | 0.22 | 0.26 | 20/20 |
| Design-induced, labels shuffled (Latin square, as in the LLM reruns) | 0.09 (0.19) 0/20 | 0.32 (0.19) 20/20 | 0.06 (0.19) 0/20 | 0.18 / 0.16 | 0.22 | 0.25 | 4/20 |
| Design-induced, labels shuffled (balanced) | 0.10 (0.19) 0/20 | 0.09 (0.19) 1/20 | 0.07 (0.18) 1/20 | 0.20 / 0.18 | 0.28 | 0.24 | 4/20 |

Cells: median R (median shuffled baseline, 95th percentile) and seeds above it / seeds. Same top receiver: the largest number of seeds in which one and the same agent received the most tells.
