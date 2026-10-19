# LLM runs made in Stage 1 but not reported

Stage 1 made 90 LLM runs. The 81 reported in the proposal and technical appendix are in
`code/diffenv_results/`. The nine below were made but are not part of any reported result;
they are archived here unchanged so that every run is disclosed. All used gpt-4.1-mini.

| File | Date (UTC) | Calls | Cost (USD) | Purpose | Why not reported |
|---|---|---|---|---|---|
| `tiny__c1-openai-gpt-4.1-mini-seed0.json` | 2026-09-29 14:54 | 3 | 0.0004 | API connectivity and logging check | Smoke test, 3 calls |
| `pilot__c2-openai-gpt-4.1-mini-seed0.json` | 2026-09-29 14:57 | 45 | 0.0079 | Pilot of the specialty prompt and reply parser | 5-round pilot under the original visibility setting, before the reported design was fixed |
| `pilot__c1-openai-gpt-4.1-mini-seed0.json` | 2026-09-29 15:00 | 45 | 0.0073 | Pilot of the identical-agent prompt and reply parser | Same |
| `pilot2__c1-openai-gpt-4.1-mini-seed1.json` | 2026-09-29 15:11 | 45 | 0.0071 | Comparison of visibility settings: sampled | 5-round pilot; led to the private-visibility design used in every reported run |
| `pilot2__c1+private-openai-gpt-4.1-mini-seed1.json` | 2026-09-29 15:12 | 45 | 0.0061 | Comparison of visibility settings: private | Same |
| `pilot3__c1+private-openai-gpt-4.1-mini-seed3.json` | 2026-09-29 15:21 | 45 | 0.0069 | Final check of the private-visibility run before full runs | 5-round pilot |
| `c1+exit+private+alias-openai-gpt-4.1-mini-seed0.json` | 2026-09-30 10:07 | 900 | 0.1615 | Full run: identical agents with an exit option, Latin-square labels | Superseded condition: the exit option is reported only with fixed names (appendix A6), and the Latin-square shuffle was replaced by the balanced shuffle |
| `c1+exit+private+alias-openai-gpt-4.1-mini-seed1.json` | 2026-09-30 10:16 | 900 | 0.1618 | Same | Same |
| `c1+exit+private+alias-openai-gpt-4.1-mini-seed2.json` | 2026-09-30 10:26 | 900 | 0.1619 | Same | Same |

Total: 9 runs, $0.52. With the 81 reported runs ($22.06), Stage 1's LLM runs cost $22.58 as recorded.
