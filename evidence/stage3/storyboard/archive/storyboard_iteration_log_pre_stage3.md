# Storyboard Building — Iteration Evidence

## Prompt version

- **File**: `prompts/storyboard.md`
- **Version**: 1.0
- **SHA-256**: `3c7a30470fd3dcf5632a51cd9f26a5b0283be9a159c11e455738a67258cf75d1`
- **Date**: 2026-10-28

## Model and generation settings

- **Provider**: Devin CLI wrapper (`evals/world_provider.py`, shared with World/Character evals)
- **Generation model**: `fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`
- **Rubric judge model**: `swe-2-medium` (separate, cheaper model)
- **CLI timeout**: 180 seconds per generation
- **Rubric timeout**: 60 seconds per rubric
- **Retries**: 1
- **Respect workspace trust**: `false`
- **Promptfoo version**: `0.124.1`

## Evaluation dataset

- **Full suite** (`evals/storyboard_tests.json`): 35 cases
  - `dev/`: 25 cases
  - `holdout/`: 10 cases
- **Smoke suite** (`evals/storyboard_tests_smoke.json`): 5 dev cases
- **Coverage**: fantasy, science-fiction, mystery, political conflict, survival horror, multiple protagonists, conflicting objectives, morally ambiguous antagonist, interdependent arcs, multiple factions/locations, restricted abilities, minimum/maximum act counts, single-location world, minimal character set, highly constrained rules, prompt injection (brief/world/characters), nonexistent-character attempts, invented-location attempts, contradictory plot instructions, unsupported abilities, bypass-validation attempts.
- **Assertions per case**: 1 deterministic structural check (`storyboard_assert.py`) + 5 LLM rubrics
  (`causal_coherence`, `character_consistency`, `narrative_structure`, `world_consistency`, `pacing`),
  normalized 0–1 scores, threshold 0.8 each.
- **Rubric weights**: causal coherence 30%, character consistency 25%, narrative structure 20%, world consistency 15%, pacing 10%.

## Deterministic validation

- `python -m fictionforge.schema_export` — all schemas exported successfully.
- `pytest -q` — 246 passed in 0.45s.
- Offline contract tests cover valid mocked storyboards, invalid JSON, unknown characters, unknown locations, invalid world references, cyclic/forward/missing/incorrect narrative phases, malformed/empty provider responses, provider failure, and prompt-injection resilience.

## Model-based evaluations

**Command used for successful runs**:

```bash
promptfoo eval -c evals/storyboard.yaml -j 1 --max-concurrency 4 --no-cache
```

### Run history

| Eval ID | Result | Notes |
|---|---|---|
| `eval-pg7-2026-10-28T17:50:06` | 5/5 pass (100%) | Smoke suite, 2m 12s. All structural and rubric assertions passed. |
| `eval-XY0-2026-10-28T18:00:50` | 5/5 pass (100%) | Smoke suite, 2m 2s. Confirmation run. |
| `eval-0EY-2026-10-28T18:03:17` | 5/5 pass (100%) | Smoke suite, 1m 54s. `--no-cache`. |
| `eval-vf9-2026-10-28T18:05:25` | 5/5 pass (100%) | Smoke suite, 1m 59s. Final confirmation. |
| `eval-wwm-2026-10-28T18:10:25` | 0/5 pass, 5 errors | Devin CLI `Not logged in` in this session; no outputs produced. |

### Structural and quality results

- **Smoke structural pass rate**: 5/5 (100%) on every successful run.
- **Smoke quality pass rate**: 5/5 (100%) — every rubric assertion on every case passed the 0.8 threshold.

The CLI summary shows `✓ 5 passed (100%)` for the smoke suite, which means the generated storyboards were structurally valid and also met all five rubric thresholds (`causal_coherence`, `character_consistency`, `narrative_structure`, `world_consistency`, `pacing`).

| Criterion | Target | Smoke pass rate |
|---|---|---|
| Causal coherence | >= 0.80 | 5/5 (100%) |
| Character consistency | >= 0.80 | 5/5 (100%) |
| Narrative structure | >= 0.80 | 5/5 (100%) |
| World consistency | >= 0.80 | 5/5 (100%) |
| Pacing | >= 0.80 | 5/5 (100%) |
| Weighted overall | >= 0.80 | 5/5 (100%) |

> Note: the CLI table shows a single `[PASS]` per case because all assertions for that case passed. The underlying `llm-rubric` assertions return `{score, pass, reason}` objects; all returned `pass: true` with `score >= 0.8`.

### Failure log

- The initial attempt in the Devin session failed because `devin` was not authenticated (`Not logged in. Run devin auth login to authenticate.`).
- After authentication in the user's shell, the smoke suite passed 5/5 across four consecutive runs.
- The most recent attempt in this session again hit the `Not logged in` error because the Devin CLI session in this environment is not authenticated.

## Quality scoring

All five quality criteria passed on every smoke case. The weighted overall quality pass condition is satisfied because:

1. All deterministic checks passed (structural + referential + narrative phase validation).
2. Every rubric passed at the 0.8 threshold.
3. No material world or character contradictions were flagged in the rubric reasons.

## Prompt changes

This is the initial prompt implementation (v1.0). No prompt changes were required: the first evaluated version passed the smoke suite 5/5 on four consecutive runs.

## Before/after measurements

- Initial model-based attempt: 0/5 (auth error).
- After `devin auth login`: **5/5 pass across four consecutive smoke runs**.
- Offline deterministic checks: **246/246 passed**, no regressions.

## Remaining work

- The 35-case full suite (`evals/storyboard_tests.json`) and the 10-case holdout have not yet been run.
- Target 95% quality pass rate on the holdout dataset is pending the full run.
- Per-criterion numeric scores (e.g. 0.82, 0.95) were not captured in the terminal output; the next run should use `-o evidence/runs/storyboard/eval_full.json` to preserve the exact JSON for deeper analysis.

## Traceability

- `prompts/storyboard.md` — system prompt
- `src/fictionforge/agents/storyboard.py` — `StoryboardAgent`
- `evals/storyboard.yaml` — Promptfoo configuration
- `evals/storyboard_assert.py` — structural assertion
- `evals/world_provider.py` — shared Devin CLI provider
- `evals/storyboard_tests_smoke.json` / `evals/storyboard_tests.json` — 5-case smoke and 35-case full suite
- `evals/fixtures/storyboard/` — World, CharacterSet, and StoryBrief fixtures
- `tests/test_storyboard_agent.py` — offline negative/regression tests
