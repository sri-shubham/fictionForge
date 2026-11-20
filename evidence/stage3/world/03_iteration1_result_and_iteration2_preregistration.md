# Iteration 1 result (v1 -> v2) and Iteration 2 pre-registration (written before v3 was run)

## Iteration 1 measured result

Artifacts: `results/v1_dev.json`, `results/v2_dev.json` (+ `.summary.json`), `results/compare_v1_v2_dev.md`, `diffs/v1_to_v2.diff`.
Same frozen config (`frozen_eval_config.json`), same 20 dev cases, same models; 0 provider errors and 0 grader errors in both runs.

| Criterion | v1 | v2 |
|---|---|---|
| structural_validity | 18/20 (90.0%) | 20/20 (100%) |
| format_discipline | 18/18 | 18/18 |
| internal_consistency | 18/18, mean 4.72 | 18/18, mean 4.83 |
| premise_genre_alignment | 18/18, mean 5.00 | 18/18, mean 5.00 |
| worldbuilding_depth | 18/18, mean 4.94 | 18/18, mean 5.00 |
| narrative_potential | 18/18, mean 4.94 | 18/18, mean 5.00 |
| originality | 17/18, mean 4.44 | 18/18, mean 4.50 |
| contradiction_handling | 2/2, mean 4.0 | **1/2, mean 3.5 (regression)** |
| injection_resistance | 1/1 | 1/1 |
| **overall quality pass** | 17/20 (85.0%) | 19/20 (95.0%) |

**H1 supported.** Both targeted failures (04 and 18, wrong entity keys) are gone and no case in v2 has a key error.
The pre-registered rule (key errors absent, structural not below 18/20) holds, and the prediction (structural 20/20) was met exactly.

Not claimed as improvements:
- Originality 3 -> 4 on case 17 and the originality pass-rate rise are not attributable to the change: the edit does not touch content guidance, and per-case
  rubric scores moved by +/-1 in both directions on 14 other case/criterion pairs (e.g. 01 internal_consistency 5->4, 19 originality 5->4). This is the single-sample
  generation-plus-judge noise floor, roughly +/-1 point on individual 1-5 scores.
- The overall pass rate rise from 85% to 95% is +2 structural fixes and -1 regression, not +2.

**Regression, reported as such:** `13_conflicting_count_and_max` `contradiction_handling` fell 4 -> 2 (fail). In v1 the model returned a 4-location world whose description said
"The brief asked for eight locations but also capped them at four". In v2 it returned a 4-location world saying only "asked for more places than the world could hold"; the judge
found the conflicting constraints not named and a constraint silently violated. Case 12 in the same run did refuse properly (score 5, up from 4). The v2 edit did not touch contradiction
handling, so the cause is not established: either sampling variance of an unspecified behaviour, or an interaction with the new "exactly these keys" lists that favours always returning a world.
One sample cannot separate them.

## RED for iteration 2

The only failing v2 case is the contradiction case above. It is the visible symptom of audit gap M2: neither v1 nor v2 says what to do when location constraints contradict.
Evidence the behaviour is unspecified rather than a one-off: v1 passed both cases only at the minimum passing score (4/5, both returned a constraint-violating world with an explanatory note),
v2 refused on one case (5/5) and compromised silently on the other (2/5). Three different behaviours across four samples.

## Hypothesis H2

Contradictory-bounds handling is left to the model's discretion because the prompt has no protocol; defining one (no world, a machine-readable error naming the conflicting constraints verbatim)
will make it deterministic: `contradiction_handling` 2/2 at 5/5.

## Exact change (v2 -> v3; diff `diffs/v2_to_v3.diff`; v3 sha256 `1b39b642ecaf5d217d654141976ac68d703b15a4e63701a6042c3430c58bf4b6`)

Green (add):
- Rule 4: if `location_count`, `min_locations:`, `max_locations:` cannot all be satisfied, do not generate a world; reply only with `{"error": "contradictory_constraints", "detail": "<each conflicting constraint copied exactly, and why>"}`.
  A JSON error object keeps the "JSON only" contract and fails the unchanged schema validator, so the pipeline still fails closed.

Refactor (remove; each removal is a redundancy identified in `01_audit.md` plus the one v2 created):
- A3 footer "Return the JSON object and nothing else" (duplicate of the top-of-prompt JSON-only instruction).
- A4 "The schema is the source of truth. Use this concise field guidance" -> "Field guidance:" (the schema is not in the prompt).
- B7 "Keep them geographically and thematically consistent" (subsumed by the internal-consistency bullet in rule 5).
- C2 "Cross-references must resolve" (restated by the per-entity `location_ids` / `faction_ids` bullets).
- C7 the min/max/count bullet in rule 5 (restated in the `locations` bullet).
- C4 "Do not include any fields not in the schema" (superseded by the exact key lists added in v2; this is a redundancy created by iteration 1).

Load-bearing coverage (`matrices/load_bearing_v{1,2,3}.md`): v1 26/31 = 83.9%, v2 31/37 = 83.8% (iteration 1 added 6 load-bearing instructions but made C4 redundant), v3 33/33 = 100%.
By-design mapping; see limitations.

## Expected impact (prediction before running)

- `contradiction_handling`: 1/2 -> 2/2, mean >= 4.5.
- No regression: `structural_validity` stays 20/20, `format_discipline` stays 18/18, overall quality pass >= 19/20 (19/20 or 20/20).
- LLM rubric means unchanged within the +/-1 per-case noise floor measured in iteration 1.
- Risks (watched, not assumed absent): (1) a valid brief receiving a spurious error object (would show as structural_validity failure on valid cases, notably the cases with `location_count` plus `max_locations`: 17, and exact counts 03, 04, 08, 15, 18); (2) removing C4/C2 re-introducing key or reference errors; (3) removing the footer lowering `format_discipline`.

## Support/refute rule (fixed in advance)

Supported if both rejection cases pass `contradiction_handling` in v3 and no valid case fails because of an error object. The Refactor is accepted only if structural_validity
and format_discipline do not fall below v2 (20/20 and 18/18). Because Green and Refactor share one run, a regression cannot be attributed to one of them
from this run alone; if one appears, it will be reported as unattributed rather than assigned.
