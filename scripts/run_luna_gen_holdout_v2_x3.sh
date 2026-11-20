#!/usr/bin/env bash
# 3 consecutive holdout_v2 runs per generation agent under gpt-6-luna-medium.
# Usage: bash scripts/run_luna_gen_holdout_v2_x3.sh
set -u
export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_PYTHON=.venv/bin/python
F="--no-cache --no-share"; J="-j 3"; M="split=holdout_v2"

for i in 1 2 3; do
  echo "===== RUN $i ====="
  promptfoo eval -c evals/world_holdout_v2_luna.yaml      --prompts evidence/stage3/world/prompts/v6.md      --filter-metadata $M $F $J --description world_v6_luna_holdout_v2_r$i      -o evidence/stage3/world/results/v6_luna_holdout_v2_r$i.json
  promptfoo eval -c evals/characters_holdout_v2_luna.yaml --prompts evidence/stage3/characters/prompts/v3.md --filter-metadata $M $F $J --description characters_v3_luna_holdout_v2_r$i -o evidence/stage3/characters/results/v3_luna_holdout_v2_r$i.json
  promptfoo eval -c evals/storyboard_holdout_v2_luna.yaml --prompts evidence/stage3/storyboard/prompts/v3.md --filter-metadata $M $F $J --description storyboard_v3_luna_holdout_v2_r$i -o evidence/stage3/storyboard/results/v3_luna_holdout_v2_r$i.json
done
echo "Done: evidence/stage3/{world,characters,storyboard}/results/*_luna_holdout_v2_r{1,2,3}.json"
