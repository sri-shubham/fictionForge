# Stage 4 refinement - Storyboard prompt: v3 -> v4 pre-registration (written before any v4 run)

Continuation of the stage-3 refinement (docs 00-04) under the same frozen eval config (`scripts/storyboard_stage3.py verify`: no drift), same 25 dev / 10 holdout cases, same generation and grader models. Baseline is v3 (`prompts/storyboard.md`, byte-identical to `prompts/v3.md`): dev 24/25, 21/24 scored, 22/25 across three runs (pooled 67/74 scored, 90.5%); holdout 10/10 (run once, not used for any decision).

## Observed failures targeted (all deterministic, all recurring)
1. **Malformed JSON after the first scene/act.** `05_survival_horror` failed this way in v2, v3 attempt 1 and the v3 final dev re-run (3 of the 4 v2/v3 runs including it); `13_maximum_supported_acts` in v3 `v3_dev`. One failing output trips `structural_validity`, `schema_validity`/`narrative_phase_correctness` (missing phases after extraction) and `format_discipline` together. Documented in `03_v3_result_and_final_selection.md` ("extra closing brace right after the first scene object") and `04_final_verification.md`.
2. **Bad `depends_on` references.** `15_minimal_character_set` (final dev re-run): `depends_on` names a nonexistent scene `scn_dome_alarm`, the first genuine dependency-reference violation in any run (0 of 34 evaluable v1, 0 of 70 evaluable v2/v3 outputs before it). `22_contradictory_plot` `causal_coherence` 3: a false dependency (`scn_hollow_ambush` -> `scn_emberroost_cables`), the same false-dependency defect seen in v1 (cases 14, 20) and v3 attempt 1 (case 20).

## Hypothesis H3
(a) The prompt gives no instruction about bracket balance. The v3 doc already hypothesised that the explicit key list correlates with a mis-closed first scene object. Adding one sentence to rule 10 that states exactly how scene objects, `scenes` arrays and act objects are closed, and forbids an extra closing brace/bracket after a scene, will stop the malformed-JSON failures.
(b) The v3 refactor deleted two dependency sentences ("Only use it for direct, earlier dependencies"; "Keep the dependency graph acyclic and forward-free") as restatements of the `depends_on` bullet. The remaining rule 8 only says what a dependency should be, not that its value must be an id that was already emitted, nor what to do when no direct cause exists. Adding "copy the id exactly from an already-emitted earlier scene; never invent or re-derive one from a title; omit `depends_on` rather than link to a neighbouring scene" will remove nonexistent-reference and false-dependency failures.

## Change (two clauses, `diffs/v3_to_v4.diff`)
- Rule 8 extended by two sentences (id copied from an earlier emitted scene; omit `depends_on` when no direct cause exists).
- Rule 10 extended by two sentences (close each scene object with exactly one `}`; close an act's `scenes` array with `]` then the act with `}`; never emit an extra closing brace or bracket after a scene).
- Nothing else changes. v4 file: `prompts/v4.md`, sha256 `e33be8ff30ebc9aaf72158de950f555466680fcc8910d1e6d3c505de35d57803`. Diff sha256 `aa77939f7f858e880c2beaf856de0357a156ae2bbd74d185ea78a87291a4a4bb`.
- The live `prompts/storyboard.md` stays v3 until v4 is selected.

Two clauses go in one revision. They target different deterministic facets (a: JSON syntax -> `structural_validity`/`format_discipline`; b: dependency references -> `dependency_validity`/`referential_integrity`/`causal_coherence`), so effects are attributed by facet. Any movement on rubric criteria cannot be assigned to one clause.

## Run plan
Two independent v4 dev runs (`v4_dev`, `v4_dev_repeat1`), `--jobs 3`, no cache, because v3 dev swung 84-96% between identical runs and one run cannot show a fix. The holdout is not run in this iteration and stays untouched for certification; no holdout result is used to decide anything here.

## Pre-registered predictions and falsifiers
- Supported (a): no malformed-JSON output (JSON "Extra data"/delimiter error) in either v4 dev run, including `05_survival_horror` and `13_maximum_supported_acts`; `structural_validity` >= 24/25 in both runs.
- Supported (b): no nonexistent-reference `depends_on` (`referential_integrity`, `dependency_validity` 100% of evaluable cases) in either run, and no `causal_coherence` score <= 3 attributed to a false dependency.
- Overall: pooled pass across the two v4 runs >= v3's pooled 90.5%; each run reported separately, not pooled with v3 runs.
- Falsified if malformed JSON recurs in either run (the sentence did not help), or a nonexistent-id dependency appears.
- Risks: (1) "omit `depends_on` rather than link a neighbour" may cut dependencies and lower `causal_coherence` or `narrative_structure`; (2) the rule 8 additions partly reverse the v3 refactor's deletions, so a rise in dependency strictness is expected, not a regression; (3) an explicit bracket instruction may do nothing for a model slip that is not a reasoning error; (4) a longer prompt adds a small instruction-count change (load-bearing coverage not recomputed for v4; the new sentences map to `structural_validity`/`format_discipline` and `dependency_validity`/`referential_integrity`).
- Noise: between identical v3 runs 17 of 125 rubric scores changed and 4 crossed the pass threshold; one-to-three-case movements in the headline pass rate are not evidence. Conclusions rest on the deterministic facets above.
- Aligned-to-design caveat: the added sentences state what the deterministic validators check, so a gain on those facets verifies the instruction closes the gap, not that stories are better.

## Next (model calls)
```bash
.venv/bin/python scripts/storyboard_stage3.py run v4 dev --jobs 3
.venv/bin/python scripts/storyboard_stage3.py run v4 dev --label v4_dev_repeat1 --jobs 3
```
