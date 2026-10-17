#!/bin/bash
# Comparison C2 of ANALYSIS_PLAN_2026-10-16.md: the "A1" artifact under the corrected,
# balanced label shuffle. gpt-4.1-mini, identical agents, seeds 0-9 in two parallel lanes.
# About $1.60 and 45 minutes. Each run resumes from its journal if interrupted.
# Usage, from this folder:   bash run_balanced.sh
set -u
cd "$(dirname "$0")"
R=diffenv_results/balanced_2026-10-17
mkdir -p "$R/logs"
COMMON="--condition c1 --visibility private --alias-balanced --backend openai --model gpt-4.1-mini --full-run --max-calls 4500 --max-cost 1.00 --out $R/specimens --journal-dir $R/journal"
echo "Starting two lanes at $(date). Logs in $R/logs. Leave this window open."
caffeinate -i python3 -m diffenv.run $COMMON --seeds 0 1 2 3 4 > "$R/logs/lane1.log" 2>&1 &
caffeinate -i python3 -m diffenv.run $COMMON --seeds 5 6 7 8 9 > "$R/logs/lane2.log" 2>&1 &
wait
echo "Both lanes finished at $(date)."
grep -h "STOPPED\|Error\|Traceback" "$R"/logs/*.log && echo "A lane reported a problem: see the logs." || echo "No errors reported."
