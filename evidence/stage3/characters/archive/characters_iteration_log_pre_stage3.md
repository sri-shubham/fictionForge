# Character Design — Iteration Evidence

## Prompt version

- **File**: `prompts/characters.md`
- **Version**: 1.0 → 1.1 (schema-compliance fixes)
- **Date**: 2026-10-28

## Model and generation settings

- **Provider**: Devin CLI wrapper (`evals/world_provider.py`, shared with World eval)
- **Generation model**: `fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`
- **Rubric judge model**: `swe-2-medium` (separate, cheaper model)
- **CLI timeout**: 180 seconds per generation
- **Retries**: 1
- **Respect workspace trust**: `false`

## Evaluation dataset

- **Smoke suite** (`evals/characters_tests_smoke.json`): 5 valid-generation cases
  (fantasy, sci-fi, mystery, horror, adventure briefs), each paired with a
  shared World fixture (`fixtures/characters/worlds/aetheria.json`)
- **Assertions per case**: 1 deterministic structural check
  (`characters_assert.py`) + 5 LLM rubrics
  (motivation_clarity, world_consistency, character_differentiation,
  conflict_potential, character_development), normalized 0–1 scores,
  threshold 0.6 each.
- Rubric weights: motivation 25%, world consistency 25%, differentiation 20%,
  conflict 20%, development 10%.

## Model-based evaluations

- **Command**: `promptfoo eval -c evals/characters.yaml -j 1`
  (later runs also `-j 1 --max-concurrency 4`)

### Run history

| Eval ID | Result | Notes |
|---|---|---|
| `eval-rTn` 14:15 | aborted | User interrupted; Python worker shutdown. |
| `eval-fWH` 14:16 | 0/5 | All cases failed `structural_validity`: `missing required field 'description'`. All 5 rubrics passed (0.8–1.0) — pure schema issue. |
| `eval-iDq` 14:32 | 4/5 | Case 0 failed: `relationships` nested inside each character object (10 additional-properties issues). Top-level array was empty. |
| `eval-ggM` 14:51 | 3/5 | Case 3: dangling relationship ref `chr_edmund_ashgrove_placeholder` (character never generated). Case 4: `chr_corvin_Draske` — uppercase letter violates `^chr_[a-z0-9_]{1,48}$`. |
| `eval-1nQ` 15:13 | 5/5 pass | After prompt fixes below. |
| `eval-T0h` 15:42 | 5/5 pass | Confirmation run. |
| `eval-n6W`/`eval-lbm`/`eval-1UG` 15:49–16:27 | aborted | User interruptions / promptfoo Python worker shutdown & EPIPE crashes — infrastructure noise, not generation failures. |
| `eval-yXA` 16:27 | 5/5 pass | `--max-concurrency 4`, 2m 7s (vs ~5m 40s serial). |
| `eval-rRW` 16:30 | 5/5 pass | |
| `eval-RiO` 16:35 | 5/5 pass | |

## Failure log

All three content-relevant failures were schema-compliance drift in the
generated JSON; rubric quality scores were strong (0.8–1.0) throughout.

1. **Missing `description` on every character (eval-fWH, 5 cases)** —
   `Character.description` is a required `LongText` in the schema, but the
   prompt's output-contract field list never mentioned it, so the model
   omitted it consistently.
   **Fix**: added a `description` bullet to the contract in
   `prompts/characters.md` ("required long-form background — identity,
   history, and look; do not omit").
2. **`relationships` nested inside characters (eval-iDq, case 0)** — the model
   emitted per-character `relationships` keys; the schema only allows a
   top-level `relationships` array on `CharacterSet`.
   **Fix**: moved `relationships` into the root-field group with explicit
   wording "**top-level** array on the root object (sibling of `characters`),
   never nested inside a character", plus a closing contract line: "Only
   `world_id`, `characters`, and `relationships` are allowed at the root."
3. **Id discipline violations (eval-ggM, cases 3–4)** — a relationship
   referenced `chr_edmund_ashgrove_placeholder` (a character never generated),
   and `chr_corvin_Draske` contained an uppercase letter violating
   `^chr_[a-z0-9_]{1,48}$`.
   **Fix**: contract now spells out the full id pattern
   (`chr_<lowercase_letters_digits_underscores>`, no uppercase/hyphens/
   `placeholder` suffixes), and rule 2 explicitly forbids referencing
   ungenerated characters.

## Prompt changes

- `prompts/characters.md` — three targeted edits (above), all in the
  output-contract / cross-reference sections. No changes to rubric text or
  model config: generation (`fusion-claude-sonnet-…-haiku-…`) and judge
  (`swe-2-medium`) were already correctly configured.
- Note the pattern: each run surfaced a *different* structural violation as
  the previous one was fixed. If id-shape errors recur, a deterministic
  repair pass (slugify ids, drop dangling refs) in the provider is the
  durable fix.

## Before/after measurements

- Structural validity: 0/5 → 4/5 → 3/5 (distinct remaining violations) →
  **5/5 across five consecutive runs** (`eval-1nQ`, `eval-T0h`, `eval-yXA`,
  `eval-rRW`, `eval-RiO`).
- Rubric scores: consistently 0.8–1.0 (threshold 0.6) in every run —
  content quality was never the bottleneck.
- Wall time: ~5m 40s serial (`-j 1`) → ~2m 20s with `--max-concurrency 4`.
- Note: `promptfoo` emitted a `telemetry.shutdown() timed out` warning and
  intermittent `Worker shutting down`/`EPIPE` crashes when runs were
  interrupted; neither affects completed-run results.

## Traceability

- `prompts/characters.md` — system prompt (iterated)
- `evals/characters.yaml` — Promptfoo configuration (provider + rubrics)
- `evals/characters_assert.py` — structural assertion
- `evals/characters_tests_smoke.json` — 5-case smoke suite
- `evals/world_provider.py` — shared Devin CLI provider
- `evals/fixtures/characters/` — brief fixtures + `worlds/aetheria.json`
- `src/fictionforge/models.py` — `Character`, `CharacterRelationship`,
  `CharacterSet` schema (`^chr_[a-z0-9_]{1,48}$` id pattern)
