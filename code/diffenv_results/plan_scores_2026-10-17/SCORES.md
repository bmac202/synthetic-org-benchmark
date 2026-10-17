# Confirmatory scores per ANALYSIS_PLAN_2026-10-16.md

- gpt_fixed:hub: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 10/10; median 0.36 [0.32, 0.40], range 0.26-0.50; median baseline 0.18
- gpt_fixed:task: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 0/10; median 0.11 [0.08, 0.12], range 0.04-0.13; median baseline 0.19
- gpt_latin:hub: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 2/10; median 0.15 [0.10, 0.18], range 0.07-0.22; median baseline 0.18
- gpt_latin:task: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 0/10; median 0.10 [0.07, 0.12], range 0.05-0.15; median baseline 0.19
- gpt_balanced:hub: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 0/10; median 0.08 [0.05, 0.10], range 0.01-0.11; median baseline 0.18
- gpt_balanced:task: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 0/10; median 0.09 [0.08, 0.12], range 0.06-0.18; median baseline 0.19
- gpt_assigned:hub: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 10/10; median 0.67 [0.60, 0.68], range 0.57-0.73; median baseline 0.18
- gpt_assigned:task: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 10/10; median 0.71 [0.64, 0.74], range 0.60-0.78; median baseline 0.21
- haiku_latin:hub: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 2/10; median 0.13 [0.07, 0.17], range 0.06-0.21; median baseline 0.18
- haiku_latin:task: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 0/10; median 0.10 [0.07, 0.12], range 0.05-0.13; median baseline 0.19
- haiku_assigned:hub: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 10/10; median 0.48 [0.38, 0.57], range 0.33-0.64; median baseline 0.18
- haiku_assigned:task: n=10 seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]; above baseline 10/10; median 0.63 [0.61, 0.66], range 0.59-0.70; median baseline 0.20
- haiku_fixed:hub: n=3 seeds [0, 1, 2]; above baseline 2/3; median 0.20 [0.13, 0.23], range 0.13-0.23; median baseline 0.18
- haiku_fixed:task: n=3 seeds [0, 1, 2]; above baseline 0/3; median 0.09 [0.09, 0.10], range 0.09-0.10; median baseline 0.19

Fixed names, gpt: agent A1 top receiver in 8/10 runs

- C1 hub: fixed vs Latin-square: U=100, exact two-sided p=0.00001, Holm p=0.00004
- C2 hub: fixed vs balanced: U=100, exact two-sided p=0.00001, Holm p=0.00004
- C3 task, gpt: assigned vs identical: U=100, exact two-sided p=0.00001, Holm p=0.00004
- C3 task, Haiku: assigned vs identical: U=100, exact two-sided p=0.00001, Holm p=0.00004

## Per run

gpt_fixed seed0: hub 0.38/0.18 task 0.13/0.18 top A1 (0.21) done 145 cost 0.16 work|opp 0.12/0.19 interaction 0.20/0.19 sent|opp 0.32/0.17
gpt_fixed seed1: hub 0.44/0.19 task 0.04/0.19 top A4 (0.22) done 162 cost 0.16 work|opp 0.10/0.18 interaction 0.37/0.18 sent|opp 0.26/0.18
gpt_fixed seed2: hub 0.35/0.19 task 0.11/0.19 top A1 (0.19) done 151 cost 0.16 work|opp 0.10/0.19 interaction 0.16/0.18 sent|opp 0.29/0.19
gpt_fixed seed3: hub 0.32/0.18 task 0.12/0.18 top A1 (0.19) done 152 cost 0.16 work|opp 0.20/0.17 interaction 0.18/0.20 sent|opp 0.30/0.18
gpt_fixed seed4: hub 0.26/0.18 task 0.08/0.19 top A4 (0.17) done 161 cost 0.16 work|opp 0.12/0.19 interaction 0.17/0.19 sent|opp 0.20/0.18
gpt_fixed seed5: hub 0.36/0.18 task 0.13/0.19 top A1 (0.18) done 156 cost 0.16 work|opp 0.15/0.18 interaction 0.21/0.17 sent|opp 0.11/0.21
gpt_fixed seed6: hub 0.50/0.19 task 0.08/0.19 top A1 (0.24) done 156 cost 0.16 work|opp 0.19/0.19 interaction 0.34/0.20 sent|opp 0.24/0.19
gpt_fixed seed7: hub 0.37/0.18 task 0.10/0.19 top A1 (0.18) done 160 cost 0.16 work|opp 0.18/0.18 interaction 0.22/0.19 sent|opp 0.15/0.19
gpt_fixed seed8: hub 0.28/0.19 task 0.10/0.18 top A1 (0.21) done 157 cost 0.16 work|opp 0.04/0.20 interaction 0.21/0.21 sent|opp 0.21/0.19
gpt_fixed seed9: hub 0.36/0.19 task 0.12/0.19 top A1 (0.23) done 157 cost 0.16 work|opp 0.13/0.20 interaction 0.18/0.18 sent|opp 0.12/0.19
gpt_latin seed0: hub 0.22/0.19 task 0.15/0.19 top A4 (0.16) done 158 cost 0.00 work|opp 0.12/0.18 interaction 0.15/0.19 sent|opp 0.14/0.19 favlab {'A1': 3, 'A5': 1, 'A4': 4, 'A7': 1}
gpt_latin seed1: hub 0.07/0.20 task 0.12/0.19 top A0 (0.16) done 158 cost 0.16 work|opp 0.06/0.19 interaction 0.08/0.19 sent|opp 0.06/0.18 favlab {'A1': 3, 'A4': 4, 'A7': 1, 'A3': 1}
gpt_latin seed2: hub 0.07/0.19 task 0.05/0.19 top A6 (0.16) done 161 cost 0.16 work|opp 0.04/0.19 interaction 0.15/0.18 sent|opp 0.07/0.18 favlab {'A4': 3, 'A6': 1, 'A1': 1, 'A5': 3, 'A0': 1}
gpt_latin seed3: hub 0.11/0.19 task 0.11/0.18 top A1 (0.17) done 168 cost 0.16 work|opp 0.07/0.21 interaction 0.17/0.18 sent|opp 0.11/0.19 favlab {'A1': 5, 'A0': 1, 'A7': 1, 'A2': 1, 'A5': 1}
gpt_latin seed4: hub 0.20/0.18 task 0.08/0.20 top A1 (0.17) done 166 cost 0.16 work|opp 0.18/0.19 interaction 0.11/0.19 sent|opp 0.06/0.19 favlab {'A4': 3, 'A1': 3, 'A3': 1, 'A2': 1, 'A6': 1}
gpt_latin seed5: hub 0.17/0.18 task 0.13/0.19 top A0 (0.18) done 158 cost 0.16 work|opp 0.10/0.20 interaction 0.12/0.20 sent|opp 0.06/0.18 favlab {'A1': 2, 'A4': 2, 'A7': 2, 'A6': 1, 'A3': 2}
gpt_latin seed6: hub 0.15/0.18 task 0.08/0.19 top A8 (0.20) done 150 cost 0.16 work|opp 0.11/0.18 interaction 0.09/0.18 sent|opp 0.09/0.18 favlab {'A2': 1, 'A0': 2, 'A4': 2, 'A1': 2, 'A3': 2}
gpt_latin seed7: hub 0.18/0.19 task 0.05/0.18 top A2 (0.16) done 160 cost 0.16 work|opp 0.19/0.19 interaction 0.09/0.18 sent|opp 0.18/0.19 favlab {'A0': 3, 'A1': 3, 'A2': 1, 'A4': 1, 'A3': 1}
gpt_latin seed8: hub 0.15/0.18 task 0.09/0.19 top A5 (0.16) done 152 cost 0.16 work|opp 0.11/0.19 interaction 0.05/0.18 sent|opp 0.10/0.19 favlab {'A1': 3, 'A2': 1, 'A0': 2, 'A7': 1, 'A5': 1, 'A6': 1}
gpt_latin seed9: hub 0.12/0.18 task 0.10/0.19 top A8 (0.17) done 155 cost 0.16 work|opp 0.09/0.17 interaction 0.18/0.19 sent|opp 0.03/0.18 favlab {'A4': 4, 'A2': 1, 'A5': 2, 'A1': 2}
gpt_balanced seed0: hub 0.11/0.18 task 0.18/0.18 top A3 (0.14) done 150 cost 0.16 work|opp 0.14/0.18 interaction 0.06/0.19 sent|opp 0.14/0.21 favlab {'A1': 9}
gpt_balanced seed1: hub 0.05/0.18 task 0.11/0.19 top A7 (0.13) done 166 cost 0.16 work|opp 0.11/0.20 interaction 0.07/0.18 sent|opp 0.08/0.19 favlab {'A1': 9}
gpt_balanced seed2: hub 0.06/0.19 task 0.09/0.19 top A7 (0.13) done 164 cost 0.16 work|opp 0.07/0.18 interaction 0.04/0.19 sent|opp 0.12/0.20 favlab {'A1': 9}
gpt_balanced seed3: hub 0.01/0.19 task 0.08/0.18 top A7 (0.12) done 161 cost 0.16 work|opp 0.04/0.20 interaction 0.05/0.19 sent|opp 0.11/0.19 favlab {'A1': 9}
gpt_balanced seed4: hub 0.08/0.18 task 0.07/0.18 top A2 (0.13) done 148 cost 0.16 work|opp 0.21/0.18 interaction 0.08/0.21 sent|opp 0.07/0.18 favlab {'A1': 8, 'A4': 1}
gpt_balanced seed5: hub 0.10/0.18 task 0.10/0.19 top A6 (0.14) done 170 cost 0.16 work|opp 0.18/0.21 interaction 0.06/0.18 sent|opp 0.09/0.19 favlab {'A1': 9}
gpt_balanced seed6: hub 0.05/0.18 task 0.13/0.18 top A5 (0.14) done 152 cost 0.16 work|opp 0.04/0.19 interaction 0.10/0.18 sent|opp 0.05/0.20 favlab {'A1': 9}
gpt_balanced seed7: hub 0.10/0.19 task 0.09/0.19 top A3 (0.16) done 167 cost 0.16 work|opp 0.11/0.20 interaction 0.09/0.19 sent|opp 0.13/0.22 favlab {'A1': 9}
gpt_balanced seed8: hub 0.09/0.18 task 0.12/0.19 top A0 (0.15) done 158 cost 0.16 work|opp 0.11/0.19 interaction 0.15/0.19 sent|opp 0.03/0.18 favlab {'A1': 9}
gpt_balanced seed9: hub 0.07/0.19 task 0.06/0.19 top A7 (0.13) done 161 cost 0.16 work|opp 0.04/0.19 interaction 0.04/0.18 sent|opp 0.07/0.20 favlab {'A1': 8, 'A3': 1}
gpt_assigned seed0: hub 0.61/0.18 task 0.76/0.22 top A1 (0.20) done 43 cost 0.17 work|opp 0.24/0.18 interaction 0.45/0.20 sent|opp 0.36/0.19
gpt_assigned seed1: hub 0.69/0.19 task 0.60/0.22 top A1 (0.19) done 49 cost 0.17 work|opp 0.07/0.19 interaction 0.46/0.18 sent|opp 0.11/0.19
gpt_assigned seed2: hub 0.68/0.17 task 0.70/0.20 top A1 (0.20) done 49 cost 0.17 work|opp 0.18/0.18 interaction 0.41/0.18 sent|opp 0.23/0.19
gpt_assigned seed3: hub 0.58/0.17 task 0.78/0.22 top A1 (0.19) done 45 cost 0.17 work|opp 0.31/0.18 interaction 0.33/0.17 sent|opp 0.22/0.18
gpt_assigned seed4: hub 0.67/0.18 task 0.71/0.22 top A1 (0.20) done 39 cost 0.17 work|opp 0.28/0.21 interaction 0.35/0.19 sent|opp 0.30/0.20
gpt_assigned seed5: hub 0.66/0.18 task 0.71/0.20 top A1 (0.19) done 51 cost 0.17 work|opp 0.16/0.19 interaction 0.43/0.18 sent|opp 0.26/0.21
gpt_assigned seed6: hub 0.67/0.18 task 0.72/0.21 top A1 (0.21) done 54 cost 0.17 work|opp 0.24/0.18 interaction 0.42/0.19 sent|opp 0.30/0.19
gpt_assigned seed7: hub 0.57/0.18 task 0.64/0.22 top A1 (0.17) done 46 cost 0.17 work|opp 0.16/0.19 interaction 0.28/0.17 sent|opp 0.18/0.19
gpt_assigned seed8: hub 0.73/0.18 task 0.63/0.21 top A1 (0.21) done 50 cost 0.17 work|opp 0.17/0.18 interaction 0.41/0.17 sent|opp 0.24/0.19
gpt_assigned seed9: hub 0.63/0.18 task 0.74/0.20 top A1 (0.21) done 55 cost 0.17 work|opp 0.19/0.19 interaction 0.43/0.19 sent|opp 0.36/0.19
haiku_latin seed0: hub 0.15/0.19 task 0.10/0.18 top A8 (0.14) done 120 cost 0.43 work|opp 0.07/0.17 interaction 0.20/0.17 sent|opp 0.06/0.18 favlab {'A3': 1, 'A2': 1, 'A6': 2, 'A4': 1, 'A5': 1, 'A8': 2, 'A7': 1}
haiku_latin seed1: hub 0.20/0.18 task 0.13/0.19 top A5 (0.16) done 115 cost 0.43 work|opp 0.10/0.19 interaction 0.12/0.19 sent|opp 0.05/0.18 favlab {'A1': 2, 'A2': 1, 'A7': 2, 'A5': 2, 'A3': 1, 'A4': 1}
haiku_latin seed2: hub 0.07/0.18 task 0.12/0.19 top A2 (0.14) done 126 cost 0.43 work|opp 0.11/0.19 interaction 0.10/0.19 sent|opp 0.21/0.18 favlab {'A1': 1, 'A2': 2, 'A3': 2, 'A7': 1, 'A5': 2, 'A0': 1}
haiku_latin seed3: hub 0.21/0.19 task 0.09/0.20 top A0 (0.17) done 113 cost 0.43 work|opp 0.07/0.17 interaction 0.15/0.19 sent|opp 0.12/0.18 favlab {'A7': 1, 'A3': 1, 'A0': 3, 'A1': 1, 'A5': 1, 'A4': 2}
haiku_latin seed4: hub 0.06/0.20 task 0.10/0.19 top A0 (0.16) done 116 cost 0.43 work|opp 0.09/0.17 interaction 0.12/0.20 sent|opp 0.16/0.21 favlab {'A1': 4, 'A7': 1, 'A0': 2, 'A2': 1, 'A5': 1}
haiku_latin seed5: hub 0.11/0.18 task 0.08/0.19 top A2 (0.14) done 121 cost 0.43 work|opp 0.14/0.19 interaction 0.06/0.19 sent|opp 0.12/0.18 favlab {'A7': 2, 'A2': 1, 'A1': 1, 'A5': 2, 'A8': 1, 'A0': 1, 'A4': 1}
haiku_latin seed6: hub 0.10/0.20 task 0.05/0.19 top A4 (0.15) done 122 cost 0.43 work|opp 0.08/0.19 interaction 0.10/0.19 sent|opp 0.12/0.19 favlab {'A2': 1, 'A3': 3, 'A4': 1, 'A6': 1, 'A0': 1, 'A8': 1, 'A1': 1}
haiku_latin seed7: hub 0.06/0.18 task 0.05/0.19 top A2 (0.14) done 116 cost 0.43 work|opp 0.07/0.19 interaction 0.06/0.19 sent|opp 0.13/0.19 favlab {'A2': 3, 'A0': 1, 'A4': 2, 'A1': 3}
haiku_latin seed8: hub 0.16/0.20 task 0.12/0.19 top A0 (0.15) done 112 cost 0.43 work|opp 0.12/0.21 interaction 0.16/0.19 sent|opp 0.19/0.19 favlab {'A3': 1, 'A1': 1, 'A5': 1, 'A4': 3, 'A6': 2, 'A0': 1}
haiku_latin seed9: hub 0.14/0.18 task 0.10/0.19 top A4 (0.18) done 119 cost 0.43 work|opp 0.08/0.17 interaction 0.18/0.17 sent|opp 0.13/0.17 favlab {'A0': 2, 'A6': 1, 'A3': 1, 'A5': 1, 'A2': 1, 'A4': 1, 'A1': 2}
haiku_assigned seed0: hub 0.37/0.17 task 0.61/0.18 top A1 (0.19) done 88 cost 0.47 work|opp 0.17/0.18 interaction 0.27/0.18 sent|opp 0.15/0.18
haiku_assigned seed1: hub 0.54/0.17 task 0.63/0.19 top A1 (0.22) done 84 cost 0.48 work|opp 0.17/0.19 interaction 0.46/0.17 sent|opp 0.14/0.18
haiku_assigned seed2: hub 0.45/0.18 task 0.67/0.20 top A1 (0.19) done 75 cost 0.48 work|opp 0.09/0.19 interaction 0.36/0.18 sent|opp 0.11/0.17
haiku_assigned seed3: hub 0.39/0.17 task 0.64/0.19 top A1 (0.17) done 84 cost 0.47 work|opp 0.10/0.19 interaction 0.39/0.17 sent|opp 0.07/0.19
haiku_assigned seed4: hub 0.51/0.19 task 0.59/0.20 top A4 (0.17) done 86 cost 0.47 work|opp 0.25/0.19 interaction 0.41/0.18 sent|opp 0.27/0.20
haiku_assigned seed5: hub 0.58/0.17 task 0.60/0.19 top A1 (0.23) done 76 cost 0.48 work|opp 0.12/0.20 interaction 0.52/0.19 sent|opp 0.21/0.18
haiku_assigned seed6: hub 0.39/0.19 task 0.66/0.20 top A1 (0.20) done 80 cost 0.48 work|opp 0.10/0.17 interaction 0.43/0.18 sent|opp 0.12/0.19
haiku_assigned seed7: hub 0.64/0.19 task 0.70/0.19 top A1 (0.23) done 79 cost 0.48 work|opp 0.13/0.20 interaction 0.52/0.19 sent|opp 0.18/0.20
haiku_assigned seed8: hub 0.33/0.20 task 0.62/0.20 top A1 (0.19) done 77 cost 0.47 work|opp 0.08/0.22 interaction 0.25/0.20 sent|opp 0.11/0.21
haiku_assigned seed9: hub 0.57/0.18 task 0.64/0.20 top A1 (0.21) done 85 cost 0.48 work|opp 0.06/0.19 interaction 0.55/0.19 sent|opp 0.08/0.18
haiku_fixed seed0: hub 0.20/0.17 task 0.09/0.19 top A1 (0.16) done 122 cost 0.43 work|opp 0.04/0.19 interaction 0.16/0.20 sent|opp 0.14/0.20
haiku_fixed seed1: hub 0.13/0.18 task 0.09/0.19 top A0 (0.17) done 100 cost 0.43 work|opp 0.08/0.18 interaction 0.07/0.18 sent|opp 0.10/0.18
haiku_fixed seed2: hub 0.23/0.18 task 0.10/0.19 top A1 (0.19) done 121 cost 0.43 work|opp 0.07/0.20 interaction 0.15/0.17 sent|opp 0.10/0.19
