#!/usr/bin/env bash
# Preset wrapper for diffenv final runs. Usage: ./run.sh --condition c1 --seeds 0
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export MAX_COST_USD="${MAX_COST_USD:-1.0}"
exec python3 -m diffenv.run \
  --backend openai --model gpt-4.1-mini \
  --visibility private --draws 200 \
  --out diffenv_results/final/specimens \
  --journal-dir diffenv_results/final/journal \
  --max-calls 900 --full-run "$@"
