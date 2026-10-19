# Functional (favored-type) baseline: pre-specified vs aggregate null

Pre-specified threshold: mean over task types of each type's 95th-percentile null. Aggregate-null threshold:
95th percentile of the null distribution of the mean statistic itself (one joint label permutation per
window applied to all types; 200 draws). The pre-specified analysis is unchanged.

## LLM runs (plan-specified cells)

| Cell | Runs | Median R | Pre-specified threshold (median) | Above | Aggregate-null threshold (median) | Above |
|---|---|---|---|---|---|---|
| gpt_fixed | 10 | 0.11 | 0.19 | 0/10 | 0.15 | 0/10 |
| gpt_latin | 10 | 0.10 | 0.19 | 0/10 | 0.14 | 1/10 |
| gpt_balanced | 10 | 0.09 | 0.19 | 0/10 | 0.15 | 1/10 |
| gpt_assigned | 10 | 0.71 | 0.21 | 10/10 | 0.16 | 10/10 |
| haiku_latin | 10 | 0.10 | 0.19 | 0/10 | 0.15 | 0/10 |
| haiku_assigned | 10 | 0.63 | 0.19 | 10/10 | 0.15 | 10/10 |
| haiku_fixed | 3 | 0.09 | 0.19 | 0/3 | 0.15 | 0/3 |

## Known-answer test (rule-based agents, seeds 0-19)

| Cell | Runs | Median R | Pre-specified threshold (median) | Above | Aggregate-null threshold (median) | Above |
|---|---|---|---|---|---|---|
| none | 20 | 0.09 | 0.19 | 0/20 | 0.15 | 1/20 |
| prescribed | 20 | 0.49 | 0.20 | 20/20 | 0.16 | 20/20 |
| generated | 20 | 0.35 | 0.19 | 20/20 | 0.15 | 20/20 |
| generated_wiped | 20 | 0.19 | 0.19 | 8/20 | 0.15 | 15/20 |
| generated_isolated | 20 | 0.25 | 0.19 | 18/20 | 0.15 | 20/20 |
| prescribed_random | 20 | 0.55 | 0.19 | 20/20 | 0.16 | 20/20 |
| prescribed_random_wiped | 20 | 0.55 | 0.19 | 20/20 | 0.16 | 20/20 |
| label | 20 | 0.09 | 0.19 | 0/20 | 0.15 | 0/20 |
| label_shuffled | 20 | 0.09 | 0.19 | 0/20 | 0.15 | 0/20 |
| label_balanced | 20 | 0.10 | 0.19 | 1/20 | 0.15 | 1/20 |

Check: largest difference between the stored observed statistic and its recomputation: 0.00e+00.
