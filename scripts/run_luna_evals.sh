#!/usr/bin/env bash
# All 6 agents x (dev + holdout + holdout_v2) under gpt-6-luna-medium.
# Model under test is swapped in the *_luna.yaml variants; graders unchanged.
# Usage: bash scripts/run_luna_evals.sh
set -u
export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_PYTHON=.venv/bin/python

J="-j 3"; F="--no-cache --no-share"

# ---------- Generation agents (installed: world v6, characters v3, storyboard v3) ----------
promptfoo eval -c evals/world_stage3_luna.yaml      --prompts evidence/stage3/world/prompts/v6.md      --filter-metadata split=dev        $F $J --description world_v6_luna_dev      -o evidence/stage3/world/results/v6_luna_dev.json
promptfoo eval -c evals/characters_stage3_luna.yaml --prompts evidence/stage3/characters/prompts/v3.md --filter-metadata split=dev        $F $J --description characters_v3_luna_dev -o evidence/stage3/characters/results/v3_luna_dev.json
promptfoo eval -c evals/storyboard_stage3_luna.yaml --prompts evidence/stage3/storyboard/prompts/v3.md --filter-metadata split=dev        $F $J --description storyboard_v3_luna_dev -o evidence/stage3/storyboard/results/v3_luna_dev.json

promptfoo eval -c evals/world_stage3_luna.yaml      --prompts evidence/stage3/world/prompts/v6.md      --filter-metadata split=holdout    $F $J --description world_v6_luna_holdout      -o evidence/stage3/world/results/v6_luna_holdout.json
promptfoo eval -c evals/characters_stage3_luna.yaml --prompts evidence/stage3/characters/prompts/v3.md --filter-metadata split=holdout    $F $J --description characters_v3_luna_holdout -o evidence/stage3/characters/results/v3_luna_holdout.json
promptfoo eval -c evals/storyboard_stage3_luna.yaml --prompts evidence/stage3/storyboard/prompts/v3.md --filter-metadata split=holdout    $F $J --description storyboard_v3_luna_holdout -o evidence/stage3/storyboard/results/v3_luna_holdout.json

promptfoo eval -c evals/world_holdout_v2_luna.yaml      --prompts evidence/stage3/world/prompts/v6.md      --filter-metadata split=holdout_v2 $F $J --description world_v6_luna_holdout_v2      -o evidence/stage3/world/results/v6_luna_holdout_v2.json
promptfoo eval -c evals/characters_holdout_v2_luna.yaml --prompts evidence/stage3/characters/prompts/v3.md --filter-metadata split=holdout_v2 $F $J --description characters_v3_luna_holdout_v2 -o evidence/stage3/characters/results/v3_luna_holdout_v2.json
promptfoo eval -c evals/storyboard_holdout_v2_luna.yaml --prompts evidence/stage3/storyboard/prompts/v3.md --filter-metadata split=holdout_v2 $F $J --description storyboard_v3_luna_holdout_v2 -o evidence/stage3/storyboard/results/v3_luna_holdout_v2.json

# ---------- Reviewer agents (installed: world v6, characters v3, storyboard v9) ----------
promptfoo eval -c evals/reviewers/world_luna.yaml      --prompts evidence/stage3/reviewers/world/prompts/v6.md      --filter-metadata split=dev    $F $J --description wr_v6_luna_dev -o evidence/stage3/reviewers/world/results/v6_luna_dev.json
promptfoo eval -c evals/reviewers/characters_luna.yaml --prompts evidence/stage3/reviewers/characters/prompts/v3.md --filter-metadata split=dev    $F $J --description cr_v3_luna_dev -o evidence/stage3/reviewers/characters/results/v3_luna_dev.json
promptfoo eval -c evals/reviewers/storyboard_luna.yaml --prompts evidence/stage3/reviewers/storyboard/prompts/v9.md --filter-metadata split=dev    $F $J --description sr_v9_luna_dev -o evidence/stage3/reviewers/storyboard/results/v9_luna_dev.json

promptfoo eval -c evals/reviewers/world_luna.yaml      --prompts evidence/stage3/reviewers/world/prompts/v6.md      --filter-metadata split=holdout    $F $J --description wr_v6_luna_holdout -o evidence/stage3/reviewers/world/results/v6_luna_holdout.json
promptfoo eval -c evals/reviewers/characters_luna.yaml --prompts evidence/stage3/reviewers/characters/prompts/v3.md --filter-metadata split=holdout    $F $J --description cr_v3_luna_holdout -o evidence/stage3/reviewers/characters/results/v3_luna_holdout.json
promptfoo eval -c evals/reviewers/storyboard_luna.yaml --prompts evidence/stage3/reviewers/storyboard/prompts/v9.md --filter-metadata split=holdout    $F $J --description sr_v9_luna_holdout -o evidence/stage3/reviewers/storyboard/results/v9_luna_holdout.json

promptfoo eval -c evals/reviewers/world_holdout_v2_luna.yaml      --prompts evidence/stage3/reviewers/world/prompts/v6.md      --filter-metadata split=holdout_v2 $F $J --description wr_v6_luna_holdout_v2 -o evidence/stage3/reviewers/world/results/v6_luna_holdout_v2.json
promptfoo eval -c evals/reviewers/characters_holdout_v2_luna.yaml --prompts evidence/stage3/reviewers/characters/prompts/v3.md --filter-metadata split=holdout_v2 $F $J --description cr_v3_luna_holdout_v2 -o evidence/stage3/reviewers/characters/results/v3_luna_holdout_v2.json
promptfoo eval -c evals/reviewers/storyboard_holdout_v2_luna.yaml --prompts evidence/stage3/reviewers/storyboard/prompts/v9.md --filter-metadata split=holdout_v2 $F $J --description sr_v9_luna_holdout_v2 -o evidence/stage3/reviewers/storyboard/results/v9_luna_holdout_v2.json

echo "All 18 luna runs complete. Results: evidence/stage3/**/results/*_luna_*.json"
