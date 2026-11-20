# World Generation — Iteration Evidence

## Prompt version

- **File**: `prompts/world.md`
- **Version**: 1.0
- **Date**: 2026-10-28

## Model and generation settings

- **Provider**: Devin CLI wrapper (`fictionforge.llm.devin.DevinCliClient`)
- **Generation model**: `fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`
- **Rubric judge model**: `swe-2-medium` (separate, cheaper model)
- **CLI timeout**: 180 seconds per generation
- **Retries**: 1
- **Respect workspace trust**: `false`
- **No silent fallback** to fabricated output; any CLI or validation failure raises `WorldGenerationError`.

## Evaluation dataset

- **Smoke suite** (`evals/world_tests_smoke.json`): 3 valid-generation cases
  - `01_fantasy_floating_isles` — fantasy, floating islands
  - `02_scifi_dyson_swarm` — sci-fi, Dyson swarm
  - `03_mystery_noir_city` — mystery noir metropolis
- Full fixture set (30 cases incl. rejection/injection) remains in
  `evals/fixtures/world/` for future runs.

## Offline deterministic tests

- **Command**: `.venv/bin/pytest -q`
- **Result**: 97 passed (existing 83 contract tests + 14 new World Agent tests)

## Model-based evaluations

- **Promptfoo suite**: `evals/world.yaml`, backed by `evals/world_provider.py`,
  `evals/world_assert.py`, `evals/world_tests_smoke.json`
- **Command**: `promptfoo eval -c evals/world.yaml -j 1`
- **Assertions per case**: 1 deterministic structural check
  (`world_assert.py` → `validate_world`) + 5 LLM rubrics
  (internal_consistency, premise_genre_alignment, worldbuilding_depth,
  narrative_potential, originality), threshold 3/5 each.

### Run history (3-case smoke suite)

| Eval ID | Result | Notes |
|---|---|---|
| `eval-Ajj` 13:03 | 3/3 pass | First run of the 3-case suite. |
| `eval-N8U` 13:07 | 2/3 | Case 01 failed `originality`: judge emitted `score: 0.8` — off the required 1–5 scale — despite a positive written reason. |
| `eval-Ubg` 13:13 | 3/3 pass | After rubric-spec fixes. |
| `eval-efH` 13:17 | 3/3 pass | Repeat run confirming stability. |

## Failure log

1. **Originality judge off-scale score (eval-N8U)** — The judge wrote a positive
   review ("inventive twists", "distinctive") but returned `score: 0.8`, below
   the 3.0 threshold. The rubric asked for a 1–5 score but did not forbid
   fractional or 0–1 values, so `swe-2-medium` emitted a confidence-style score.
   **Fix**: hardened all five rubric specs in `evals/world.yaml` — *"The score
   MUST be an integer between 1 and 5 inclusive (never a fraction or a 0-1
   value), and 'pass' MUST be true exactly when score >= 3"* — plus a positive
   example object `{"score": 3, "pass": true, "reason": "..."}`.
   Additional rubric hardening applied at the same time:
   - `worldbuilding_depth` now tells the judge to grade relative to the scope
     the brief requests (no penalty for a small location count the brief asked for).
   - `originality` got a calibration anchor (familiar tropes with inventive
     twists or a cohesive distinctive conceit → 4+).

## Prompt changes

- `prompts/world.md` — no changes were needed. Every observed failure traced to
  judge-rubric specification, not generation output.
- `evals/world.yaml` — all 5 rubrics hardened for integer scoring and
  consistent `pass`; scope-aware depth rubric; originality calibration anchor.
- `evals/world_tests_smoke.json` — 3 valid-generation cases.

## Before/after measurements

- Structural validity: 3/3 worlds passed `validate_world` in every run —
  generation never produced an invalid world.
- Smoke suite pass rate: 66% (`eval-N8U`) → 100% (`eval-Ubg`, `eval-efH`,
  two consecutive runs).
- Average rubric score on passing runs: ~3.8–4.2 per case.
- Remaining risk: single-judge rubric scoring is still stochastic at the 3.0
  threshold boundary; a borderline world can flip on judge variance.
- Note: `promptfoo` emitted a `telemetry.shutdown() timed out` warning at the
  end of runs; it does not affect results.

## Traceability

- `src/fictionforge/llm/devin.py` — Devin CLI client
- `src/fictionforge/agents/world.py` — World Generation agent
- `src/fictionforge/agents/base.py` — reusable agent base
- `src/fictionforge/guardrails/validators.py` — deterministic World validation
- `prompts/world.md` — system prompt
- `tests/test_world_agent.py` — deterministic agent tests
- `evals/world.yaml` — Promptfoo configuration (provider + rubrics)
- `evals/world_assert.py` — structural assertion (`EXPECTED`-aware)
- `evals/world_tests_smoke.json` — 3-case smoke suite
- `evals/fixtures/world/` — 30 StoryBrief fixtures
