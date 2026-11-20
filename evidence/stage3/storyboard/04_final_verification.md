# Final verification of v3 (full dev re-run + single holdout run)

Prompt v3 (`prompts/storyboard.md`, byte-identical to `prompts/v3.md`), sha256 `933cbbc632ef772a680bb0d9e4035b052369b00908e5288c8e5778cb09c45611`.
Frozen config verified before and after both runs (config sha256 `5712784394fd…`; dev `e956390f…`; holdout `ef94c294…`); every summary records the
same three hashes. Same generator (`fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`), grader (`swe-2-medium`), `--jobs 3`, `--no-cache`.
0 provider errors and 0 grader errors in both runs. Development and holdout are reported separately and are not pooled.

| Criterion | v3 dev (selection run, `eval-tuD`) | v3 dev (final re-run, `eval-XMK-2026-11-02T14:51:56`) | v3 holdout (once, `eval-wv4-2026-11-02T15:02:28`) |
|---|---|---|---|
| Cases | 25 | 25 | 10 |
| structural_validity | 24/25 | **23/25** | 10/10 |
| schema_validity | 24/25 | 25/25 | 10/10 |
| referential_integrity | 24/24 (1 n/e) | 25/25 | 10/10 |
| dependency_validity | 24/24 (1 n/e) | **24/25** | 10/10 |
| narrative_phase_correctness | 24/24 (1 n/e) | **24/25** | 10/10 |
| format_discipline | 24/25 | 24/25 | 10/10 |
| causal_coherence (mean) | 25/25 (4.64) | 24/25 (4.68) | 10/10 (4.90) |
| character_consistency (mean) | 25/25 (5.00) | 24/25 (4.88) | 10/10 (5.00) |
| narrative_structure (mean) | 25/25 (4.88) | 24/25 (4.76) | 10/10 (5.00) |
| world_consistency (mean) | 25/25 (4.96) | 25/25 (4.92) | 10/10 (5.00) |
| pacing (mean) | 25/25 (5.00) | 24/25 (4.88) | 10/10 (5.00) |
| **overall quality pass** | 24/25 (96.0%) | **22/25 (88.0%)** | **10/10 (100%)** |
| weighted score mean | 0.9724 | 0.9604 | 0.9940 |

Files: `results/v3_dev.json`, `results/final_dev.json`, `results/final_holdout.json` (each with `.summary.json`), `results/compare_v1_v2_v3_dev.md`,
`results/compare_all.md`, `measurements.json`. The holdout was run once; no holdout result was used for any prompt decision, and the prompt
had been selected before the holdout existed as a result.

## Final dev re-run failures (3 cases)
- `05_survival_horror` (all of structural, narrative-phase and format fail; rubrics 2 on character_consistency, narrative_structure, pacing): the model closed the `acts` array right after the first act (`…"depends_on":["scn_docks_stranded"]}]}]},{"id":"act_rising"…`, JSON "Extra data"), so the extractor kept only the setup act and the validator reports three missing phases. Same family as the extra-closing-brace defect in `03_v3_result_and_final_selection.md`; this case has now failed that way in v2, v3 attempt 1 and the final dev re-run (3 of the 4 v2/v3 runs that include it).
- `15_minimal_character_set`: `depends_on` names a scene that does not exist (`scn_dome_alarm`). This is the first genuine dependency-reference violation in any run (0 of 34 evaluable v1 outputs; 0 of 70 evaluable v2/v3 outputs before this one; 1 of 25 here). The refactor that removed the dependency restatements (rule 8 sentences) cannot be fully cleared by this: one violation in 95 evaluable v2/v3-family outputs against none in 34 for v1 is not a significant difference, but the pre-registered check 'no new dependency violation' was not met in this run.
- `22_contradictory_plot` `causal_coherence` 3: `scn_hollow_ambush` falsely depends on `scn_emberroost_cables` (the same false-dependency defect seen in v1 case 14, 20, attempt-1 case 01).

## Judge and generation variability, and limitations
- **Run-to-run variability is the main caveat.** v3 on the same dev cases: 24/25 (96.0%), 21/24 scored (87.5%; 84.0% strict, one timeout), 22/25 (88.0%) across three runs. Pooled it is 67 of 74 scored case-runs (90.5%); only one of three runs reached the 95% target. v1 across two runs: 14/25 and 16/24. Seven of 25 cases changed pass/fail status at least once across the three v3 runs (05, 06, 13, 15, 20, 22, 25).
- Rubric-score stability (same prompt, same cases): between `v3_dev` and `final_dev`, 17 of 125 case/criterion scores changed (7 up, 10 down) and 4 crossed the pass threshold; between `v3_dev` and v3 attempt 1, 21 of 120 changed (5 crossed); between the two v1 runs 26 of 120 changed (9 crossed). Each run varies both generation (new samples; the CLI exposes no temperature or seed) and judging, and the files cannot separate them. One-to-three-case differences between versions are inside this noise; v3 over v2 (88.0%) is not distinguishable on dev from these runs, while v1 (56.0%, 66.7%) versus v2/v3 (84-96%) is well outside it.
- The honest development summary for v3 is "84% to 96% across three runs (pooled about 90%)", not "96%".
- Holdout is 10 cases; 10/10 has a Clopper-Pearson 95% lower bound near 69%, so it shows no collapse on unseen briefs, not a rate. 8 of 10 holdout cases use the same Aetheria world and cast, 2 use the minimal world; the holdout contains no prompt-injection or contradictory-plot cases, which dev does, so it does not cover those stress cases.
- Single judge model (`swe-2-medium`), no second judge and no human spot-check; judge text is the only evidence for rubric scores. The judge failed no call (0 grader errors in 7 runs).
- The rubrics sit near the ceiling (most rubric means 4.7-5.0 in every v2/v3 run); they discriminate weakly between good prompts. No calibration pilot ran before freezing. Deterministic facets, not the rubrics, drove most measured differences between versions.
- The prompt's rule 5 addition mirrors rubric item (e) of `character_consistency` by design; that gain is on a criterion the prompt is aligned to.
- Dev worlds and casts are nearly uniform (22 of 25 dev cases use Aetheria and the same three-character cast), so world/character results are for that fixture only.
- Load-bearing coverage is an analytical mapping of prompt sentences to criteria, not an ablation test; it shows design coverage, not causal contribution.

## Other checks
Tests and submission validation are recorded in `evidence/iterations/storyboard.md` section 9 after they were run.
