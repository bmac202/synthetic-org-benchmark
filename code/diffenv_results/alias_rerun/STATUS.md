# Randomized-name rerun — status 2026-09-30 17:29:45

6 of 6 planned runs complete. Spent so far: $0.80.

## Progress

| run | state | items done (of 600) | work / tell / pass | agents left |
|---|---|---|---|---|
| c1+private+alias-openai-gpt-4.1-mini-seed0 | complete 2026-09-30 09:37:38 | 158 | 607 / 230 / 63 | 0 |
| c1+private+alias-openai-gpt-4.1-mini-seed1 | complete 2026-09-30 09:46:49 | 158 | 610 / 238 / 52 | 0 |
| c1+private+alias-openai-gpt-4.1-mini-seed2 | complete 2026-09-30 09:56:40 | 161 | 621 / 232 / 47 | 0 |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed0 | complete 2026-09-30 10:07:41 | 173 | 588 / 257 / 55 | 0 |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed1 | complete 2026-09-30 10:16:59 | 163 | 599 / 243 / 58 | 0 |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed2 | complete 2026-09-30 10:26:28 | 176 | 589 / 260 / 51 | 0 |

## Repeatability, observed (null 95th percentile)

| run | names | work|opp | interaction | received | sent|opp |
|---|---|---|---|---|---|
| c1+private-openai-gpt-4.1-mini-seed0 | fixed | 0.12 (0.19) | 0.20 **above** (0.19) | 0.38 **above** (0.18) | 0.32 **above** (0.17) |
| c1+private-openai-gpt-4.1-mini-seed1 | fixed | 0.10 (0.18) | 0.37 **above** (0.18) | 0.44 **above** (0.19) | 0.26 **above** (0.18) |
| c1+private-openai-gpt-4.1-mini-seed2 | fixed | 0.10 (0.19) | 0.16 (0.18) | 0.35 **above** (0.19) | 0.29 **above** (0.19) |
| c1+exit+private-openai-gpt-4.1-mini-seed0 | fixed | 0.20 **above** (0.19) | 0.39 **above** (0.19) | 0.43 **above** (0.18) | 0.25 **above** (0.21) |
| c1+exit+private-openai-gpt-4.1-mini-seed1 | fixed | 0.19 **above** (0.17) | 0.33 **above** (0.18) | 0.65 **above** (0.19) | 0.25 **above** (0.19) |
| c1+exit+private-openai-gpt-4.1-mini-seed2 | fixed | 0.20 **above** (0.19) | 0.20 **above** (0.18) | 0.34 **above** (0.18) | 0.24 **above** (0.16) |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed0 | randomized | 0.13 (0.20) | 0.10 (0.20) | 0.12 (0.19) | 0.16 (0.19) |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed1 | randomized | 0.04 (0.19) | 0.05 (0.19) | 0.04 (0.19) | 0.05 (0.21) |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed2 | randomized | 0.13 (0.18) | 0.16 (0.19) | 0.18 **above** (0.18) | 0.18 (0.19) |
| c1+private+alias-openai-gpt-4.1-mini-seed0 | randomized | 0.12 (0.18) | 0.15 (0.19) | 0.22 **above** (0.19) | 0.14 (0.19) |
| c1+private+alias-openai-gpt-4.1-mini-seed1 | randomized | 0.06 (0.19) | 0.08 (0.19) | 0.07 (0.20) | 0.06 (0.18) |
| c1+private+alias-openai-gpt-4.1-mini-seed2 | randomized | 0.04 (0.19) | 0.15 (0.18) | 0.07 (0.19) | 0.07 (0.18) |

## Label check

`named` = tells in which the model wrote each label A0..A8 (its name preference). `received` = tells each real agent A0..A8 actually received.

| run | named, by label | received, by real agent | max / min received |
|---|---|---|---|
| c1+private-openai-gpt-4.1-mini-seed0 | [25, 49, 26, 30, 37, 19, 21, 23, 9] | [22, 48, 26, 30, 37, 19, 20, 22, 9] | 48 / 9 |
| c1+private-openai-gpt-4.1-mini-seed1 | [25, 39, 16, 32, 48, 14, 20, 23, 8] | [24, 39, 14, 31, 48, 14, 20, 23, 7] | 48 / 7 |
| c1+private-openai-gpt-4.1-mini-seed2 | [31, 47, 23, 23, 31, 21, 31, 20, 8] | [31, 45, 22, 23, 31, 21, 31, 20, 7] | 45 / 7 |
| c1+exit+private-openai-gpt-4.1-mini-seed0 | [29, 62, 32, 30, 41, 24, 16, 20, 6] | [29, 61, 32, 30, 41, 24, 15, 19, 6] | 61 / 6 |
| c1+exit+private-openai-gpt-4.1-mini-seed1 | [26, 70, 24, 37, 40, 24, 15, 25, 4] | [24, 68, 23, 35, 40, 24, 15, 23, 3] | 68 / 3 |
| c1+exit+private-openai-gpt-4.1-mini-seed2 | [27, 55, 32, 29, 40, 18, 22, 31, 11] | [25, 54, 28, 27, 39, 18, 22, 30, 11] | 54 / 11 |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed0 | [30, 51, 25, 40, 42, 27, 17, 21, 9] | [28, 17, 29, 38, 25, 28, 27, 28, 37] | 38 / 17 |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed1 | [23, 44, 22, 30, 47, 28, 20, 25, 9] | [29, 22, 23, 24, 29, 30, 29, 26, 31] | 31 / 22 |
| c1+exit+private+alias-openai-gpt-4.1-mini-seed2 | [28, 64, 31, 28, 42, 22, 21, 20, 7] | [32, 18, 30, 25, 36, 42, 33, 14, 30] | 42 / 14 |
| c1+private+alias-openai-gpt-4.1-mini-seed0 | [26, 39, 20, 29, 45, 25, 17, 27, 6] | [20, 16, 25, 35, 36, 17, 27, 23, 31] | 36 / 16 |
| c1+private+alias-openai-gpt-4.1-mini-seed1 | [24, 46, 24, 25, 39, 21, 23, 30, 10] | [37, 24, 29, 25, 27, 21, 23, 22, 30] | 37 / 21 |
| c1+private+alias-openai-gpt-4.1-mini-seed2 | [27, 47, 24, 23, 44, 31, 24, 12, 3] | [24, 24, 28, 24, 27, 26, 37, 20, 22] | 37 / 20 |

## Does the same agent come out on top in every run?

- fixed names, received by agent: mean cross-run rank correlation +0.72 (min +0.50, 15 pairs)
- randomized names, received by real agent: mean cross-run rank correlation +0.15 (min -0.27, 15 pairs)
- randomized names, named by label: mean cross-run rank correlation +0.75 (min +0.43, 15 pairs)

## Reading so far

Runs above their null, randomized names: work|opp 0/6, interaction 0/6, received 2/6, sent|opp 0/6.
Fixed names, for comparison: work|opp 3/6, interaction 5/6, received 6/6, sent|opp 6/6.
With 200 permutation draws, about 1 run in 20 exceeds its null by chance on any one measure.
