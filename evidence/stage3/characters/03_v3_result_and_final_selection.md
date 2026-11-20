# v3 result (Refactor) and final-prompt selection (dev data only; written before any holdout run)

Artifacts: `results/v3_dev.json` / `.summary.json`, `results/compare_v1_v2_v3_dev.md`, `diffs/v2_to_v3.diff`.
Run: eval `eval-ycs-2026-11-02T09:12:19`, prompt v3 sha256 `2a0b8426a9b57cbd23a736a248612ddd6e93b9bbe9010b621abd3d88d495d4f1`,
frozen config verified, `--jobs 3` (same as v1 and v2), same 20 dev cases, generator and grader. 0 provider errors, 0 grader errors.

| Criterion | v1 | v2 | v3 |
|---|---|---|---|
| structural_validity | 20/20 | 19/20 | 20/20 |
| format_discipline | 20/20 | 20/20 | 20/20 |
| injection_resistance | 1/1 | 1/1 | 1/1 |
| motivation_clarity (mean) | 20/20 (4.95) | 20/20 (5.00) | 20/20 (5.00) |
| world_consistency (mean) | 20/20 (4.90) | 20/20 (4.85) | 20/20 (4.95) |
| character_differentiation (mean) | 20/20 (4.95) | 20/20 (4.95) | 20/20 (5.00) |
| conflict_potential (mean) | 20/20 (5.00) | 20/20 (5.00) | 20/20 (5.00) |
| character_development (mean) | 18/20 (4.70) | 20/20 (4.95) | 20/20 (4.95) |
| **overall quality pass** | 18/20 (90%) | 19/20 (95%) | **20/20 (100%)** |
| load-bearing instructions | 22/29 (75.9%) | 23/30 (76.7%) | 23/25 (92.0%) |

## H2 supported (on the one case that showed the failure)
`17_mystery_country_house` now passes `structural_validity`: all four characters have a `home_location_id` and `faction_id`
(Silverspine, Mistral Docks, The Hollow, Emberroost). Across all 20 v3 outputs, no character is missing `home_location_id`.
This is one failing case in v2, so the claim is limited to "the observed omission did not recur"; it is not evidence that the
omission rate fell from a measured base rate.

## Refactor accepted
Removing six redundant instructions (A3, B16, C2, C5a, C5b, C9) did not lower `structural_validity` (20/20) or
`format_discipline` (20/20), and no dangling-reference or nested-`relationships` failure appeared. Instruction count 30 -> 25;
load-bearing coverage rose from 76.7% to 92.0%, above the 90% target. H2 and the refactor are in the same revision and are not
separately attributable (stated in advance). The removed genre/tone/audience clause (C5b) is not scored by any frozen criterion,
so the run cannot show whether it mattered.

## Not an improvement / limitations (honest reading)
- The dev set is nearly saturated. v1 was already 90%; four of five rubrics are at mean >= 4.9 in every version. The only
  measured quality failures anywhere were the two `character_development` cases (v1) and one structural failure (v2).
- Per-case rubric scores moved on 13 case/criterion pairs across v1-v3 in both directions. Between v2 and v3: 4 up, 1 down
  (`07_minimal_input` character_development 5 -> 4: "all arcs are positive growth"). One-point moves on single cases are the judge's
  noise floor and are not evidence of change. Differences in means (e.g. 4.85 -> 4.95 world_consistency) are not claimed as improvement.
- v3's 20/20 vs v2's 19/20 is a one-case difference. It is not statistically meaningful; what is claimed is only the specific fixes
  above (no pivotal-event arcs: v1 -> v2, 2 cases; omitted `home_location_id`: v2 -> v3, 1 case) plus the coverage change.
- The prompt now states what the `character_development` rubric checks, so that gain is aligned-to-rubric, not independent evidence
  of better characters.
- Residual weaknesses visible in v3 judge text: `06_historical_inspired_rome` Bridge Wardens membership for an ex-senator is loosely
  linked (score 4 in v2 and v3); arcs in `07_minimal_input` are all positive growth. No instruction targets either.
- A single judge model (`swe-2-medium`) scored everything; no second judge was used.

## Selection
Selected final prompt: **v3** (`prompts/characters.md`, byte-identical to `evidence/stage3/characters/prompts/v3.md`), chosen on dev results
only: highest overall quality pass (20/20), no structural failures, and the only version above 90% load-bearing coverage.
`pytest -q` passes (272 tests) with it installed. The holdout has not been run at this point.

## Remaining steps
```
.venv/bin/python scripts/characters_stage3.py run v3 dev --label final_dev --jobs 3        # full dev suite, fresh run (judge/generation variability)
.venv/bin/python scripts/characters_stage3.py run v3 holdout --label final_holdout --jobs 3 # untouched holdout, once
```
