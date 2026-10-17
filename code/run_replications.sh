#!/bin/bash
# Replications requested by Evaluation 2 (16 Oct 2026): bring the A1 comparison and the
# specialization contrast to 10 runs per cell. Three lanes run in parallel; each run resumes
# from its journal if interrupted (rerun this script). About $10.40 and 2-3 hours in total.
# Usage, from this folder:   bash run_replications.sh
set -u
cd "$(dirname "$0")"
R=diffenv_results/replications_2026-10-17
mkdir -p "$R/logs"
COMMON="--visibility private --full-run --out $R/specimens --journal-dir $R/journal"

lane_gpt_a1() {
  python3 -m diffenv.run --condition c1 --backend openai --model gpt-4.1-mini \
    --seeds 3 4 5 6 7 8 9 --max-calls 6300 --max-cost 2.00 $COMMON
  python3 -m diffenv.run --condition c1 --alias --backend openai --model gpt-4.1-mini \
    --seeds 3 4 5 6 7 8 9 --max-calls 6300 --max-cost 2.00 $COMMON
}
lane_gpt_roles() {
  python3 -m diffenv.run --condition c2 --backend openai --model gpt-4.1-mini \
    --seeds 2 3 4 5 6 7 8 9 --max-calls 7200 --max-cost 2.00 $COMMON
}
lane_haiku() {
  python3 -m diffenv.run --condition c1 --alias --backend anthropic --model claude-haiku-4-5 \
    --seeds 3 4 5 6 7 8 9 --max-calls 6300 --max-cost 4.00 $COMMON
  python3 -m diffenv.run --condition c2 --backend anthropic --model claude-haiku-4-5 \
    --seeds 2 3 4 5 6 7 8 9 --max-calls 7200 --max-cost 5.00 $COMMON
}

echo "Starting three lanes at $(date). Logs in $R/logs. Leave this window open."
caffeinate -i bash -c "$(declare -f lane_gpt_a1); COMMON='$COMMON'; lane_gpt_a1" > "$R/logs/gpt_a1.log" 2>&1 &
caffeinate -i bash -c "$(declare -f lane_gpt_roles); COMMON='$COMMON'; lane_gpt_roles" > "$R/logs/gpt_roles.log" 2>&1 &
caffeinate -i bash -c "$(declare -f lane_haiku); COMMON='$COMMON'; lane_haiku" > "$R/logs/haiku.log" 2>&1 &
wait
echo "All lanes finished at $(date)."
grep -h "STOPPED\|Error\|Traceback" "$R"/logs/*.log && echo "Some lane reported a problem: see the logs." || echo "No errors reported."
