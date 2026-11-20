# Iteration 2 result (v2 -> v3) and final-prompt selection (dev data only; written before any holdout run)

Artifacts: `results/v3_dev.json` / `.summary.json`, `results/compare_v1_v2_v3_dev.md`, `diffs/v2_to_v3.diff`.
Same frozen config, same 20 dev cases, same generation and grader models. 0 provider errors, 0 grader errors.
Run-level setting that differs and is not a model setting: promptfoo concurrency `--jobs 4` for v3 vs `--jobs 3` for v1/v2.

| Criterion | v1 | v2 | v3 |
|---|---|---|---|
| structural_validity | 18/20 (90.0%) | 20/20 | 20/20 |
| format_discipline | 18/18 | 18/18 | 18/18 |
| injection_resistance | 1/1 | 1/1 | 1/1 |
| internal_consistency (mean) | 18/18 (4.72) | 18/18 (4.83) | 18/18 (4.89) |
| premise_genre_alignment (mean) | 18/18 (5.00) | 18/18 (5.00) | 18/18 (5.00) |
| worldbuilding_depth (mean) | 18/18 (4.94) | 18/18 (5.00) | 18/18 (5.00) |
| narrative_potential (mean) | 18/18 (4.94) | 18/18 (5.00) | 18/18 (5.00) |
| originality (mean) | 17/18 (4.44) | 18/18 (4.50) | 17/18 (4.50) |
| contradiction_handling (mean) | 2/2 (4.0) | 1/2 (3.5) | 2/2 (5.0) |
| **overall quality pass** | 17/20 (85%) | 19/20 (95%) | 19/20 (95%) |
| load-bearing instructions | 26/31 (83.9%) | 31/37 (83.8%) | 33/33 (100%) |

## H2 supported
Both contradictory briefs (12, 13) now return `{"error": "contradictory_constraints", "detail": ...}` naming each conflicting constraint verbatim; `contradiction_handling` 5/5 on both.
Case 13 went 2 -> 5. No valid case received a spurious error object (all 18 non-rejection cases passed `structural_validity` and `format_discipline`), so the pre-registered risk (1) did not occur.

## Refactor accepted
Removing six redundant instructions (A3, A4, B7, C2, C4, C7) did not lower `structural_validity` (20/20) or `format_discipline` (18/18); no key or reference errors appeared.
Instruction count 37 -> 33 while coverage by the frozen criteria rose to 100%. The contradiction rule was added in the same step, so the refactor and the green change are not separately attributable (stated in advance).

## Not an improvement / remaining weaknesses
- Overall quality pass is unchanged at 19/20: the contradiction fix is offset by a new failure, `03_mystery_noir_city` originality 3/5 ("noir defaults ... could transfer to another noir world largely unchanged").
  That case scored 4 (v1), 5 (v2), 3 (v3) with an unchanged originality instruction (C10): it is not attributable to the v3 edit. It is, however, a real remaining weakness: originality is the weakest quality criterion in all three versions
  (mean 4.44 / 4.50 / 4.50; between 7 and 9 of 18 worlds sit at exactly 4) and one case failed it in v1 (17) and in v3 (03), a different case each time.
- Per-case rubric scores moved on 10 case/criterion pairs between v2 and v3 in both directions (6 up, 4 down, excluding the contradiction case), the same +/-1 noise floor as in iteration 1.
  Differences of one point on a single case are therefore not evidence of change. Small differences in means (4.83 -> 4.89 internal consistency) are likewise within noise and are not claimed as improvement.
- Dev sample sizes are small (18 scored worlds, 2 contradiction cases); pass-rate differences of one case are not statistically meaningful. Only the structural fix (18 -> 20, deterministic, identical failure mechanism in both cases) and the contradiction fix (qualitative change in behaviour, visible in the raw output) are claimed.
- No instruction targets originality beyond one line (C10). A third iteration was not run; the task asks for two.

## Selection
Selected final prompt: **v3** (`prompts/versions/world_v3.md`, sha256 `1b39b642ecaf5d217d654141976ac68d703b15a4e63701a6042c3430c58bf4b6`), chosen on dev results only:
it ties v2 on overall quality pass (19/20), has the best contradiction handling, 100% structural validity, and the highest load-bearing coverage. v3 was installed as `prompts/world.md`; `pytest -q` passes (272 tests) with it.
The holdout set has not been run at this point.
