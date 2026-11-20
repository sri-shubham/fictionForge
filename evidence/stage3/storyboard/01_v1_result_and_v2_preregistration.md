# v1 baseline result (Red) and v2 pre-registration (written before any v2 run)

Layout note: the evidence for this agent lives in `evidence/stage3/storyboard/`, the same layout as `evidence/stage3/characters/` and `evidence/stage3/world/`. It was first created under `evidence/iterations/storyboard/` and moved here (unchanged bytes) after the v1 runs; the raw Promptfoo files still record the original prompt path (`evidence/iterations/storyboard/prompts/v1.md`) in their embedded config. The frozen YAML's default `prompts:` path was not edited (that would break the freeze); `--prompts` overrides it for every run. The summaries were regenerated offline after the move so their path fields are correct; the raw files were not touched.

## Which run is the v1 baseline, and why there are two v1 runs

The first `run v1 dev` (`eval-Pif-2026-11-02T11:37:25`, 22 min 57 s) finished its Promptfoo evaluation (16 passed, 8 failed, **1 error**: case `25_coming_of_age` hit the 600000 ms Python-worker timeout) but the script was interrupted (Ctrl-C) while computing the summary, and its raw output file was removed by hand before the command was re-run, because the script refuses to overwrite. I recovered that evaluation from Promptfoo's local database with `promptfoo export eval` (no model call) and saved it as `results/v1_dev_attempt1_recovered.json` (+ `.summary.json`). It is a retained artifact of a real run, but it was **not** written by the `-o` flag, so its provenance is "exported from the Promptfoo DB".

The second run (`eval-LIi-2026-11-02T12:00:54`, 10 min 03 s, 0 provider errors, 0 grader errors, all 25 cases scored) is designated **the v1 baseline** (`results/v1_dev.json`). The reason is completeness: attempt 1 has an infrastructure error and no standard summary. This choice is disclosed because it is not neutral: attempt 1 scored higher (16/24 = 66.7% of scored cases) than the baseline (14/25 = 56.0%), so a lower baseline makes later improvements look larger. Both are reported everywhere; the two runs are the same prompt (sha256 `3c7a3047…`), config and models, so they are **not** two iterations, and the gap between them (about ten points of pass rate) is a direct measure of run-to-run noise that bounds every later comparison.

## v1 baseline, 25 dev cases (`results/v1_dev.json`, eval `eval-LIi-2026-11-02T12:00:54`)

Prompt v1 sha256 `3c7a30470fd3dcf5632a51cd9f26a5b0283be9a159c11e455738a67258cf75d1`; frozen config verified before and after (config sha256 `57127843…`, dev dataset `e956390f…`; full hashes in `frozen_eval_config.json`).

| Criterion | v1 dev (25) | attempt 1 (24 scored + 1 provider error) |
|---|---|---|
| structural_validity (= schema facet in practice) | **16/25** | 18/24 |
| schema_validity | 16/25 | 18/24 |
| referential_integrity | 16/16 evaluable (9 not evaluable) | 18/18 (6 n/e) |
| dependency_validity | 16/16 (9 n/e) | 18/18 (6 n/e) |
| narrative_phase_correctness | 16/16 (9 n/e) | 18/18 (6 n/e) |
| format_discipline | 24/25 | 22/24 |
| causal_coherence (mean) | 23/25 (4.48) | 23/24 (4.75) |
| character_consistency (mean) | 24/25 (4.80) | 21/24 (4.75) |
| narrative_structure (mean) | 25/25 (4.92) | 22/24 (4.71) |
| world_consistency (mean) | 25/25 (5.00) | 24/24 (5.00) |
| pacing (mean) | 25/25 (4.96) | 22/24 (4.75) |
| **overall quality pass** | **14/25 (56.0%)** | 16/24 (66.7%); strict 16/25 = 64.0% |
| weighted score mean | 0.9548 | 0.9558 |

No grader errors in either run. The only infrastructure failure in either run is the single provider timeout in attempt 1. "Not evaluable" means the validator stopped at the schema stage, so the semantic checks never ran on that output.

## Measured failures (Red)

**1. Structural failures dominate: 9 of 25 baseline cases (36%) fail `schema_validity`, and in 5 of those 9 the cause is a missing scene `title`.** Counted from the stored model outputs re-validated with the frozen validator:

| Baseline case | Violation |
|---|---|
| 02, 08, 14, 19, 24 | every scene is missing the required `title` (13, 11, 8, 12, 10 scenes) |
| 11 | extra key `act_id` on all 12 scenes |
| 12 | one scene missing `summary` |
| 18 | scenes missing `goal`, `conflict`, `character_ids` etc. (acts nested into the scene list; 28 issues) |
| 21 | `depends_on` placed on an act (extra key) |

Attempt 1 repeats the same pattern: scene `title` missing in 07, 21, 22, 23, 24 (cases 21 and 24 fail in both runs), extra keys `purpose_note` (11) and `world_id_check` (22), and a non-object scene entry (23). Across the two runs, 10 of 15 schema failures are the missing scene `title`.

The v1 contract text lists `title` for the story and for an act but **never for a scene**, although the schema requires it (`Scene.required = id, title, summary, location_id, character_ids, goal, conflict, outcome`). The scene bullet lists only `id`; other scene keys are described in separate bullets and none says the list is complete.

**2. Content-quality failures are fewer and scattered** (the rubrics ran on every output, valid or not):
- `causal_coherence` < 4 in `14_single_location` (score 3: dependency on a non-existent id `scn_ddead_cells_alarm`) and `20_nonexistent_character` (3: several `depends_on` entries are positional, not truthful); attempt 1 `01_fantasy_adventure` (3: false dependency). Mean 4.48 is the lowest rubric mean, and 9 of the 25 baseline cases scored 4 and 2 scored 3 rather than 5 on it.
- `character_consistency` 2 in `03_mystery_investigation` (the antagonist is dead partway through and never pursues his goal; also failed in attempt 1 with 3).
- `format_discipline` fails in 24 (baseline) and 11 and 23 (attempt 1); each of these outputs is also a schema failure, i.e. malformed or non-conforming JSON.
- `narrative_phase_correctness`, `referential_integrity` and `dependency_validity` have no violation in any evaluable output (16/16 and 18/18), so there is nothing to fix there.

## Hypothesis H1 (v1 -> v2)

Cause: the output contract does not give a complete, exact key list for each object. It omits the required scene `title` and never says an object has *only* the listed keys, so the generator improvises scene shapes (drops `title`, adds `act_id`/`purpose_note`, nests acts into scenes).
Prediction: stating every scene's exact key set (with `title` required) and that acts carry only `id`, `title`, `purpose`, `scenes` will remove "missing scene title" and act/scene extra-key failures. Concretely: missing-scene-title failures 5/25 -> 0/25, and `schema_validity` pass rate 16/25 -> at least 22/25, with no loss on the five rubrics beyond one-case noise.

Change (one hunk, two bullets in the output contract; `diffs/v1_to_v2.diff`, sha256 `77135d14…`): `acts` bullet gains "exactly these keys … Nothing else goes on an act: `depends_on` and the scene keys below belong only inside a scene"; `scenes` bullet gains "Every scene object has exactly these keys: `id`, `title`, `summary`, `location_id`, `character_ids`, `goal`, `conflict`, `outcome`, and optionally `depends_on`. `title` (1-120 chars) is required on every scene." Nothing else differs. v2 sha256 `86dce38f37e2c339dab22b7c713d6d97f0b3f7605669f513dcf0fd7460b105e1`.

## Pre-registered risks and caveats
- Noise: the same v1 prompt scored 14/25 and 16/24 in two runs and the scored schema failures moved 9 -> 6, so a change of one to three cases is inside run-to-run variation. I will treat the hypothesis as supported only if missing-`title` failures essentially disappear (they were 5/25 and 5/24), not on the headline pass rate alone.
- Fixing structure exposes the rubrics to more valid storyboards; rubric scores may shift in either direction for reasons unrelated to the edit.
- The change targets structure, not story quality. The creative failures above (false dependencies, an antagonist who disappears) are deliberately left for iteration 2 if they persist in v2.
- The prompt now states a schema fact that the `schema_validity` assertion checks. The gain is on a check the prompt is aligned to by design; it is real for the pipeline (invalid storyboards are rejected) but not independent evidence of better stories.
- Load-bearing coverage of v2 is 29/34 = 85.3% and of v1 27/32 = 84.4% (`matrices/load_bearing_v*.md`); redundancy is not addressed until v3. (Correction made after the v2 result and before v3 was run: the first drafts of both matrices omitted the sentence "Only use it for direct, earlier dependencies." of rule 8, giving 27/31 = 87.1% and 29/33 = 87.9%. The sentence was added as a non-load-bearing restatement; the coverage tool checks anchors verbatim against the prompt, but cannot detect an unlisted sentence.)
- Not every schema failure is the same cause: 12's single missing `summary` and 18's nested acts are only covered by H1 in spirit (exact key lists), so they may persist.

## Next (user runs; model calls)
```bash
.venv/bin/python scripts/storyboard_stage3.py run v2 dev --jobs 3
```
