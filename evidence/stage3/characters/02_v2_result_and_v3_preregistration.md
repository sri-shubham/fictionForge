# v2 result (Green) and v3 pre-registration (written before any v3 run)

Run: `results/v2_dev.json` (+ `.summary.json`), eval `eval-V2z-2026-11-02T08:57:35`, prompt v2 sha256
`5b961ef3746e4af67365c403c8f93d328734dbf27cd66294d60f2aa4c65474b8`, frozen config verified, `--jobs 3`,
0 provider errors, 0 grader errors. Same 20 dev cases, models and graders as v1.

| Criterion | v1 | v2 |
|---|---|---|
| structural_validity | 20/20 | **19/20** |
| format_discipline | 20/20 | 20/20 |
| injection_resistance | 1/1 | 1/1 |
| motivation_clarity (mean) | 20/20 (4.95) | 20/20 (5.00) |
| world_consistency (mean) | 20/20 (4.90) | 20/20 (4.85) |
| character_differentiation (mean) | 20/20 (4.95) | 20/20 (4.95) |
| conflict_potential (mean) | 20/20 (5.00) | 20/20 (5.00) |
| character_development (mean) | 18/20 (4.70) | **20/20 (4.95)** |
| **overall quality pass** | 18/20 (90%) | 19/20 (95%) |
| load-bearing instructions | 22/29 (75.9%) | 23/30 (76.7%) |

## H1 result
Supported on its target: both v1 failures now score 5 on `character_development` (`13`: 3 -> 5, `17`: 3 -> 5) and the two
score-4 cases with the same weakness moved to 5 (`06`) or stayed 4 for a different reason (`08`: arcs now have pivotal events,
the judge notes endings resolve too cleanly). The "no pivotal event" failure did not recur in any v2 case.

## Regression / not an improvement
- `17_mystery_country_house` now fails `structural_validity`: **all five characters omit `home_location_id` and `faction_id`**
  ("missing required field 'home_location_id'", 5 issues). Its improved `character_development` score is therefore on an output that
  would be rejected by the validator. Net overall pass 18 -> 19 only because case 13 now passes; case 17 still fails.
- Mean `world_consistency` fell 4.90 -> 4.85 (four cases dropped 5 -> 4 for loosely linked faction membership, one rose 4 -> 5) and
  `character_differentiation` shows one 5 -> 4 and one 4 -> 5. These are single-case, +/-1 moves in both directions and are
  treated as judge noise, not as an effect of the edit.
- Whether the `home_location_id` omission was caused by the v2 edit is **unknown**: it is one case, v1 did not show it on the same
  brief, and the arc edit has no obvious link to location fields. I do not claim causation. One plausible mechanism visible in the
  prompt itself: the brief requires a `manor` and the World has none, rule "Respect the world" forbids inventing places, and the prompt
  never says `home_location_id` is required (it says "faction_id is optional" but not the contrary), so the model dropped both fields.

## Hypothesis H2 (v2 -> v3) and Refactor
H2: the contract does not say `home_location_id` is required and gives no way out when the brief asks for a place the World lacks.
Stating that every character must have one and to use the closest World location rather than omit it/invent one will remove the
omission failure (target: `17` passes `structural_validity`) without hurting `world_consistency`.

Refactor in the same revision (load-bearing coverage was 76.7%, target >= 90%, "no redundant instructions"). Removed six
instructions identified in `matrices/load_bearing_v2.json` as restating others: the "Return the JSON object and nothing else" closer
(restates JSON-only), the root-keys sentence (restates "top-level, never nested" and "no fields not in the schema"), rule 2
cross-references (restates the id constraints in the contract), rule 5 (protagonist restated; unmeasured genre/tone/audience clause),
rule 9 "Believable arcs" (now fully covered by the v2 `arc` bullet). Rules renumbered 1-6.
Result by construction: 23/25 = 92.0% load-bearing (`matrices/load_bearing_v3.*`); the two remaining non-load-bearing items
(`relationship_type` examples, optional `personality_traits`) are kept and honestly counted as not load-bearing.

Diff: `diffs/v2_to_v3.diff`; v3 sha256 `2a0b8426a9b57cbd23a736a248612ddd6e93b9bbe9010b621abd3d88d495d4f1`.

## Pre-registered risks
- H2 and the refactor are in one revision, so they are not separately attributable.
- Removing the cross-reference rule and the root-keys sentence reverses protections added in the pre-Stage-3 1.0 -> 1.1 fixes
  (dangling relationship refs, nested `relationships`). If `structural_validity` falls below v2's 19/20, the refactor is rejected
  or partially reverted and that will be reported.
- Removing the closing "nothing else" line could reduce `format_discipline` (20/20 so far).
- Removing the genre/tone/audience clause is not covered by any frozen criterion, so a "no regression" result cannot speak to it.
- A one-case difference is within noise; claims will be limited accordingly.

## Next
Run: `.venv/bin/python scripts/characters_stage3.py run v3 dev --jobs 3`
