# Stage 4 manual commands (live models — run these yourself)

**None of these commands were run by the implementer.** Every command below
calls a real model through the Devin CLI provider and produces real evidence.
Run them from the repo root (`fictionforge/`). Output paths are noted per
command; summarize afterwards with `scripts/stage4_summarize.py`.

## 1. World reviewer — shadow gate (live model)

```bash
.venv/bin/python scripts/stage4_review_gate.py \
    --gate world \
    --fixture evals/reviewers/fixtures/world/holdout/WR-H01_frostmarch_clean.json \
    --mode shadow \
    --out-dir evidence/stage4/shadow_runs
```

Other holdout fixtures: `evals/reviewers/fixtures/world/holdout/WR-H0*.json`
(e.g. `WR-H04_molecular_assemblers_make_water.json` for an expected REVISE).

## 2. Characters reviewer — shadow gate (live model)

```bash
.venv/bin/python scripts/stage4_review_gate.py \
    --gate characters \
    --fixture evals/reviewers/fixtures/characters/holdout/CR-H01_frostmarch_cast_clean.json \
    --mode shadow \
    --out-dir evidence/stage4/shadow_runs
```

## 3. Storyboard reviewer — shadow gate (live model)

```bash
.venv/bin/python scripts/stage4_review_gate.py \
    --gate storyboard \
    --fixture evals/reviewers/fixtures/storyboard/holdout/SR-H01_rime_crown_storyboard_clean.json \
    --mode shadow \
    --out-dir evidence/stage4/shadow_runs
```

Each run prints the full result (verdict, grounded issues, policy decision,
enforced-equivalent decision, latency, token usage, label comparison) and
writes it under `evidence/stage4/shadow_runs/`.

## 4. Full workflow — enforced reviewers (live models, 6 calls)

```bash
.venv/bin/python runner.py \
    --brief examples/story_brief.json \
    --review-mode enforced \
    --output-dir runs_stage4
```

Full workflow in **shadow** mode with reference labels (advisory verdicts
plus per-gate label comparisons; approvals are shadow-signed):

```bash
.venv/bin/python runner.py \
    --brief examples/story_brief.json \
    --review-mode shadow \
    --reference-labels labels.json \
    --output-dir runs_stage4_shadow
```

where `labels.json` is e.g. `{"world": "PASS", "characters": "PASS",
"storyboard": "PASS"}`. Outputs land in `runs_stage4*/<run_id>/`
(`audit.jsonl`, `gates/`, `summary.json`).

## 5. Rejection + retry demo (live reviewer, scripted generator)

```bash
.venv/bin/python scripts/run_review_rejection_demo.py \
    --scenarios B_reject_then_fix \
    --out-dir evidence/stage4/demo_runs
```

Scenario B: the generator returns a flawed (but validator-clean) world, the
real reviewer rejects it, the retry prompt carries the structured reviewer
feedback, and the scripted generator then returns the clean world.

## 6. Reviewer-triggered failure / punch-out demo (live reviewer)

```bash
.venv/bin/python scripts/run_review_rejection_demo.py \
    --scenarios A_reject_exhausted C_punch_out \
    --out-dir evidence/stage4/demo_runs
```

* `A_reject_exhausted`: same flawed world every attempt -> REVISE ->
  `REVIEW_RETRIES_EXHAUSTED`, no `world.approved`, no downstream calls.
* `C_punch_out`: a validator-clean world carrying reviewer-directed control
  text -> deterministic injection scan flags it; a real reviewer may return
  a confirmed `POLICY_GUARDRAIL_BYPASS_ATTEMPT` PUNCH_OUT (`HALT_PUNCH_OUT`,
  exit 2). Either way no approval is minted.

Aggregate results are written to `evidence/stage4/demo_runs/rejection_demo.json`.

## Summarize afterwards (offline)

```bash
.venv/bin/python scripts/stage4_summarize.py runs_stage4/* runs_stage4_shadow/* \
    --out evidence/stage4/summary.json
```

Shadow runs are labelled in the output: they are not proof of enforced
adversarial guardrails.
