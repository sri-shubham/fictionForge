# Iteration 1: RED and pre-registered change (written before v2 was run)

## Baseline v1 (measured, `results/v1_dev.json`, `results/v1_dev.summary.json`)

Prompt sha256 `496778aae1067dc1316f92ecd18466dfc5ba1f8c544b76cde787ce920a167d83`; 20 dev cases; 0 provider errors, 0 grader errors.

| Criterion | passed/scored | mean |
|---|---|---|
| structural_validity | 18/20 (90.0%) | - |
| format_discipline | 18/18 | - |
| injection_resistance | 1/1 | - |
| internal_consistency | 18/18 | 4.72 |
| premise_genre_alignment | 18/18 | 5.00 |
| worldbuilding_depth | 18/18 | 4.94 |
| narrative_potential | 18/18 | 4.94 |
| originality | 17/18 (94.4%) | 4.44 |
| contradiction_handling | 2/2 | 4.00 |
| **overall quality pass (all applicable criteria)** | **17/20 (85.0%)** | |

Failed cases: `04_horror_ghost_ship` (structural), `18_horror_cabin` (structural), `17_mystery_country_house` (originality 3).

## Observed failing cases (RED)

Both structural failures are schema key errors, not constraint errors. Output key sets found in the saved raw results:

| Case | Object | Keys the model emitted | Schema requires |
|---|---|---|---|
| 04_horror_ghost_ship | every `history[]` and `conflicts[]` item | `title` instead of `name` (18 validation issues) | `name` |
| 18_horror_cabin | every `rules[]` item | extra `name` next to `statement` (12 validation issues) | `id`, `statement`, `category` only |

All other 18 cases produced correct keys. Location/faction objects were correct in all cases.

## Hypothesis H1

The v1 prompt says "The schema is the source of truth" but contains neither the schema nor the per-entity key lists
(audit gap M1). Field names are only implied by the bullets, and the model sometimes fills in a plausible but wrong key
(`title` for a name, `name` on a rule) because the schema (`additionalProperties: false`) is not visible to it.
Giving the exact keys per object should remove this failure class.

## Exact change (v1 -> v2; diff in `diffs/v1_to_v2.diff`; v2 sha256 `8f12971b9805daca34a0b8bcce519d2204fffdab36cae7ed28f9bc7a5b280d1b`)

1. New bullet: top-level keys, exactly the 8 world keys.
2. Each entity bullet now lists its exact keys. Rules additionally state "a rule has no `name` and no `description`"; history marks `era` as omittable.
Nothing else was changed (no deletions, no wording changes elsewhere), so any effect is attributable to the field lists.

## Expected impact (prediction, before running)

- `structural_validity`: 18/20 -> 20/20 (both failing cases fixed).
- Overall quality pass: 17/20 -> 18/20 (case 17 originality is not targeted and is expected to stay as is or vary with judge/model noise).
- No expected change in the 5 LLM rubrics beyond noise (the change does not touch content guidance).
- Risk: the stricter key list could make output terse or key-obsessed; watch `worldbuilding_depth` and `originality` means for regression.
- The change adds 6 instructions, all supporting `structural_validity`.

## Support/refute rule (fixed in advance)

Supported if the 2 targeted failure patterns (wrong key on history/conflicts/rules) are absent in the v2 dev run and
`structural_validity` does not fall below 18/20. Otherwise refuted. Note that one run per case is a single sample from a stochastic model.
