#!/usr/bin/env bash
# 3 consecutive holdout_v2 runs per reviewer under deepseek-v4-1-flash-1017-high.
# Usage: bash scripts/run_dsv4_reviewer_holdout_v2_x3.sh
set -u
export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_PYTHON=.venv/bin/python
F="--no-cache --no-share"; J="-j 3"; M="split=holdout_v2"

for i in 1 2 3; do
  echo "===== RUN $i ====="
  promptfoo eval -c evals/reviewers/world_holdout_v2_dsv4.yaml      --prompts evidence/stage3/reviewers/world/prompts/v6.md      --filter-metadata $M $F $J --description wr_v6_dsv4_holdout_v2_r$i      -o evidence/stage3/reviewers/world/results/v6_dsv4_holdout_v2_r$i.json
  promptfoo eval -c evals/reviewers/characters_holdout_v2_dsv4.yaml --prompts evidence/stage3/reviewers/characters/prompts/v3.md --filter-metadata $M $F $J --description cr_v3_dsv4_holdout_v2_r$i -o evidence/stage3/reviewers/characters/results/v3_dsv4_holdout_v2_r$i.json
  promptfoo eval -c evals/reviewers/storyboard_holdout_v2_dsv4.yaml --prompts evidence/stage3/reviewers/storyboard/prompts/v9.md --filter-metadata $M $F $J --description sr_v9_dsv4_holdout_v2_r$i -o evidence/stage3/reviewers/storyboard/results/v9_dsv4_holdout_v2_r$i.json
done
echo "Done: evidence/stage3/reviewers/*/results/*_dsv4_holdout_v2_r{1,2,3}.json"
