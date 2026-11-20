# v2 result (Green) and v3 pre-registration (written before any v3 run)

Run: `results/v2_dev.json` (+ `.summary.json`), eval `eval-sq5-2026-11-02T13:11:55`, prompt v2 sha256
`86dce38f37e2c339dab22b7c713d6d97f0b3f7605669f513dcf0fd7460b105e1`, frozen config verified before and after, `--jobs 3`,
0 provider errors, 0 grader errors. Same 25 dev cases, models and graders as v1. Per-case movement: `results/cases_v1_v2.json`.

| Criterion | v1 baseline (`eval-LIi`) | v1 attempt 1 (24 scored) | v2 |
|---|---|---|---|
| structural_validity / schema_validity | 16/25 | 18/24 | **23/25** |
| referential_integrity (evaluable) | 16/16 | 18/18 | 23/23 (2 n/e) |
| dependency_validity (evaluable) | 16/16 | 18/18 | 23/23 (2 n/e) |
| narrative_phase_correctness (evaluable) | 16/16 | 18/18 | 23/23 (2 n/e) |
| format_discipline | 24/25 | 22/24 | 24/25 |
| causal_coherence (mean) | 23/25 (4.48) | 23/24 (4.75) | 25/25 (4.76) |
| character_consistency (mean) | 24/25 (4.80) | 21/24 (4.75) | 24/25 (4.88) |
| narrative_structure (mean) | 25/25 (4.92) | 22/24 (4.71) | 25/25 (4.76) |
| world_consistency (mean) | 25/25 (5.00) | 24/24 (5.00) | 25/25 (4.92) |
| pacing (mean) | 25/25 (4.96) | 22/24 (4.75) | 25/25 (5.00) |
| **overall quality pass** | 14/25 (56.0%) | 16/24 (66.7%; strict 64.0%) | **22/25 (88.0%)** |
| weighted score mean | 0.9548 | 0.9558 | 0.9676 |
| load-bearing instructions | 27/32 (84.4%) | same prompt | 29/34 (85.3%) |

Case-level change v1 baseline -> v2: 9 improved (02, 08, 11, 12, 14, 18, 19, 20, 24), **1 regressed (05)**, 13 unchanged pass, 2 unchanged fail (03, 21).

## H1 result: supported on its target, with noise caveats
- Missing scene `title`: 5/25 -> **0/25** (v1 baseline: 02, 08, 14, 19, 24; every one of these now has titles and passes the schema). Attempt 1 had 5/24 as well. Scene-level extra keys (`act_id`), act-level `depends_on`, the missing `summary` and the nested-acts case (11, 21 act-level, 12, 18) also did not recur. Schema failures: 9 -> 2 of 25.
- This is the pre-registered success condition (missing-`title` failures essentially disappear), and `schema_validity` 23/25 meets the pre-registered floor of at least 22/25 (overall quality pass is 22/25). The baseline-to-v2 pass-rate gain (+32 points) is much larger than the attempt-1 -> baseline gap (about 10 points), but against attempt 1 (66.7%) the gain is +21 points; both are reported.

## Regressions, remaining failures, and things not attributable to the edit
1. `05_survival_horror` regressed: the model returned **malformed JSON** (`Expecting ',' delimiter: line 1 column 1192`), failing `structural_validity`, `schema_validity` and `format_discipline`. It passed schema in v1. A single syntax slip, not a contract problem. Not addressed by any prompt change here; the prompt has no instruction that could plausibly prevent a JSON syntax slip. (v1 also had `format_discipline` failures in 24, and in 11 and 23 of attempt 1; those outputs parsed after extraction, so they are not the same defect.)
2. `21_invented_location` still fails (it failed in all three earlier runs, each time for a different reason): v2 added a top-level extra key `theme_note`. v2's exact key lists cover acts and scenes but not the root object, and rule 10 ("do not include any fields not in the schema") did not prevent it. Root-level extras also occurred in attempt 1 (`world_id_check`, case 22). Counting the three baseline-family runs and v2, root-or-act-level extra keys appear in 3 outputs.
3. `03_mystery_investigation` still fails `character_consistency` (score 2): in v2 chr_kael (the antagonist) is "a corpse from scn_body_on_bridge and an unnamed 'Cartel figure' is the killer instead", so Kael never pursues his goal, his arc is never shown, and the Veya-Kael rivalry goes unused. This case failed `character_consistency` in all three runs of v1/v1-attempt-1/v2 (scores 2, 3, 2). The brief says "a toll-master is found murdered"; Kael is the cast's toll-master antagonist.
4. Rubric means moved in both directions with no link to the edit: `narrative_structure` 4.92 -> 4.76 (five cases 5 -> 4, one 4 -> 5), `world_consistency` 5.00 -> 4.92, `causal_coherence` 4.48 -> 4.76 (the two score-3 cases 14 and 20 became 5; in v1, case 14 had a `depends_on` entry naming a non-existent scene id and case 20 had positional dependencies). I do not attribute the `causal_coherence` rise to the v2 edit, which says nothing about causality; the attempt-1 mean was already 4.75.

## Hypothesis H2 (v2 -> v3) and Refactor

H2 (second, distinct from H1): the prompt tells the model to keep characters consistent but never requires the cast's main characters to *be present and acting*. When a brief's premise implies removing or replacing a main character (a murdered toll-master who is also the antagonist), the generator follows the premise and sidelines the character, producing the measured `character_consistency` failure on `03` in every run so far. Requiring every protagonist and antagonist to appear before and in the climax, to pursue their `goal` with their `flaw`/`internal_conflict` causing a complication, and forbidding killing, vanishing or stand-in replacement before the climax (premise roles such as victim or witness go to supporting characters or unnamed background figures) will make case 03 reach `character_consistency` >= 4 without lowering the other four rubrics beyond noise. The sentence list mirrors check (e) of the `character_consistency` rubric on purpose; it is the rubric's own definition of the desired behaviour, so the gain is on a criterion the prompt is aligned to, not independent evidence of better stories.

Change 1 (behaviour): one sentence group appended to rule 5 (`diffs/v2_to_v3.diff`). Nothing else changes behaviour.

Change 2 (Refactor, no intended behaviour change): remove the five restatements identified in the load-bearing matrices, none of which maps to a criterion on its own:
- closing line "Return the JSON object and nothing else." (restates the task-section "Return JSON only" instruction),
- "Each scene should have a clear goal, conflict, and outcome." in rule 4 (restates the output-contract line "Every scene must have a clear goal, conflict, and outcome."),
- "Do not introduce events, characters, or locations that have no basis in the provided inputs." in rule 7 (restates rule 2 and the location/character id bullets),
- "Only use it for direct, earlier dependencies." and "Keep the dependency graph acyclic and forward-free." in rule 8 (restate the `depends_on` bullet).

v3 sha256 `933cbbc632ef772a680bb0d9e4035b052369b00908e5288c8e5778cb09c45611`; diff sha256 `0f99773a59b1dc523a63d616fc67310a9202d7db6e6e1b98779aef89bbe234a1`. Load-bearing coverage v3: 30/30 = 100% (`matrices/load_bearing_v3.*`), v2 29/34 = 85.3%.

Because one run carries both a behaviour change and a refactor, any movement in this run cannot be assigned to H2 versus the deletions with certainty. I accept that to keep to two iterations; the deletions are chosen to be pure restatements, and the checks below separate their likely effects (dependency/schema/format facets) from H2's (character_consistency).

## Pre-registered predictions and falsifiers
- Supported if `03_mystery_investigation` `character_consistency` >= 4 and no new case drops below 4 on `character_consistency`.
- Refactor judged safe if `format_discipline`, `dependency_validity`, `referential_integrity` and the forward/cycle facets show no new violation, and `schema_validity` does not fall below v2's 23/25 by more than one case.
- Not claimed regardless of result: the 05 malformed JSON and the root-level `theme_note` extra key (21) are not targeted. They may recur; the final report lists them as remaining weaknesses if they do.
- Risk: requiring main characters in climax plus a pursuit scene may lengthen outputs and raise JSON-syntax failures (as in 05) or hurt `pacing`/`narrative_structure` on the minimum-act cases (12, 14, 15).
- Noise: the baseline-to-attempt-1 gap (about ten points) bounds what a one-to-three-case movement in overall pass rate can mean. The v3 conclusion will rest on the case-03 criterion and the facet checks, not on the headline pass rate.

## Next (user runs; model calls)
```bash
.venv/bin/python scripts/storyboard_stage3.py run v3 dev --jobs 3
```
