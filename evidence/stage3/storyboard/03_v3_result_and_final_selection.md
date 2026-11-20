# v3 result and final selection (dev evidence only; holdout not yet run)

## Which v3 run is "v3", and the re-run disclosure

As with v1, the first `run v3 dev` (`eval-Dan-2026-11-02T13:56:07`, 20 min 28 s) finished its evaluation (21 passed, 3 failed, **1 error**: `25_coming_of_age` hit the 600000 ms Python-worker timeout; Promptfoo also logged "Python worker crashed (1/3), restarting") and the script was interrupted during the summary step (the `promptfoo --version` subprocess hung). Its raw output file was removed by hand and the command re-run. I recovered the first run from Promptfoo's local database with `promptfoo export eval` (no model call) and kept it as `results/v3_dev_attempt1_recovered.json` (+ `.summary.json`). The re-run (`eval-tuD-2026-11-02T14:29:50`, 10 min 56 s, 0 provider errors, 0 grader errors) is designated `results/v3_dev.json`, again on completeness grounds.

This choice favours v3: the designated run scored 24/25 and the discarded-then-recovered attempt scored 21/24 scored (84.0% strict). Both runs are the same prompt (sha256 `933cbbc6…`), config and models; neither is an iteration. All claims below are stated for both. The later final dev re-run of v3 (`results/final_dev.json`) is a third, independent sample of v3 on the same cases.

## Results, 25 dev cases

| Criterion | v1 baseline | v2 | v3 (`eval-tuD`) | v3 attempt 1 (24 scored + 1 provider error) |
|---|---|---|---|---|
| structural_validity / schema_validity | 16/25 | 23/25 | **24/25** | 23/24 |
| referential_integrity (evaluable) | 16/16 | 23/23 | 24/24 (1 n/e) | 23/23 (1 n/e) |
| dependency_validity (evaluable) | 16/16 | 23/23 | 24/24 (1 n/e) | 23/23 (1 n/e) |
| narrative_phase_correctness (evaluable) | 16/16 | 23/23 | 24/24 (1 n/e) | 23/23 (1 n/e) |
| format_discipline | 24/25 | 24/25 | 24/25 | 23/24 |
| causal_coherence (mean) | 23/25 (4.48) | 25/25 (4.76) | 25/25 (4.64) | 23/24 (4.67) |
| character_consistency (mean) | 24/25 (4.80) | 24/25 (4.88) | **25/25 (5.00)** | 22/24 (4.79) |
| narrative_structure (mean) | 25/25 (4.92) | 25/25 (4.76) | 25/25 (4.88) | 23/24 (4.83) |
| world_consistency (mean) | 25/25 (5.00) | 25/25 (4.92) | 25/25 (4.96) | 24/24 (4.92) |
| pacing (mean) | 25/25 (4.96) | 25/25 (5.00) | 25/25 (5.00) | 23/24 (4.83) |
| **overall quality pass** | 14/25 (56.0%) | 22/25 (88.0%) | **24/25 (96.0%)** | 21/24 (87.5%); strict 21/25 = 84.0% |
| weighted score mean | 0.9548 | 0.9676 | 0.9724 | 0.9571 |
| load-bearing instructions | 27/32 (84.4%) | 29/34 (85.3%) | 30/30 (100%) | same prompt |

Case-level, v2 -> v3 (`results/cases_v2_v3.json`, designated run): 3 improved (03, 05, 21), **1 regressed (13)**, 21 unchanged pass, 0 unchanged fail.

## H2 result: supported on its target
- `03_mystery_investigation` `character_consistency`: 2 (v2; 3 in v1 attempt 1; 2 in v1 baseline) -> **5 in both v3 runs**. In the v3 output the antagonist Kael is alive and active in setup (`scn_kael_claims_case`), rising action (`scn_kael_pressure`), climax and resolution; the premise's murdered toll-master is now an unnamed victim. This is the pre-registered prediction, met in 2 of 2 runs. It is also the single case the hypothesis was built from, so it is weak evidence about generalisation; the aligned rubric item (e) is the same behaviour the prompt now asks for.
- Not supported as a general claim: in attempt 1, `character_consistency` failed in two other cases. `05_survival_horror` scored 2 on a truncated storyboard (the output was malformed JSON; the extractor kept only the setup, so the grader judged an incomplete story), and `06_multiple_protagonists` scored 3 because Kael's Ledger-mastery (trading arrangements) was stretched to find a weak point in a physical load, an ability overreach the H2 sentence does not address. The designated v3 run scored 5 on every case. `character_consistency` therefore ranges 22/24 to 25/25 across the two v3 runs.

## Refactor check (pre-registered conditions)
- `referential_integrity`, `dependency_validity` and `narrative_phase_correctness` showed no violation in any evaluable v3 output in either run; no forward, cyclic or unknown-reference dependency appeared after the dependency instructions were removed.
- `schema_validity` 24/25 and 23/24, within one case of v2's 23/25. No new extra-key failures (the root-level `theme_note` of v2 case 21 did not recur in either v3 run).
- `format_discipline`: one failure per run, always the malformed-JSON case below, never prose or fences. Removing "Return the JSON object and nothing else." caused no measurable prose output (0 of 49 v3 outputs with prose).
- Conclusion: the deletions are consistent with pure restatements; the 100% load-bearing figure rests on that analytic mapping, not on an ablation.

## Regression and remaining weakness: malformed JSON after the first scene
All three schema failures since v2 that are not extra-key errors are the same defect. The raw output has an extra closing brace right after the first scene object:
- v2 `05_survival_horror`: `…decides to go there herself."}},{"id":"scn_ledger_in_the_still"…`
- v3 attempt 1 `05_survival_horror`: `…despite the stillness."}},{"id":"scn_toll_in_the_calm"…`
- v3 `13_maximum_supported_acts`: `…rather than share them."}},{"id":"scn_kael_raises_tolls"…`

`json.loads` fails at char ~1190-1249 in each. This is the only structural failure in v3 (24/25 and 23/24), and it is the reason `13_maximum_supported_acts` regressed in the designated run (the case passed in v2 and in v3 attempt 1). Frequency: 0 of 49 v1 outputs (25 + 24) versus 3 of 74 v2/v3 outputs (25 + 25 + 24; the provider-error case has no output), a difference too small to call significant (one-sided Fisher exact p = 0.21), so I do not claim v2's contract edit caused it; it is a hypothesis that the explicit "optionally `depends_on`" key list correlates with a mis-closed first scene. It is not fixed in v3 and I made no third revision: the task asks for two measured revisions and the iteration budget is spent.

Other v3 observations (single cases, not attributed): `20_nonexistent_character` attempt 1 `causal_coherence` 3 (false `depends_on`), the same defect that failed this case in v1 baseline; `causal_coherence` mean fell 4.76 -> 4.64 (five cases 5 -> 4, two 4 -> 5).

## Final selection
v3 is selected as the final prompt on development evidence only: it is the only version with character_consistency 25/25 on the designated run, has the best dev pass rate (96.0%; 87.5% in the other run vs v2's single 88.0%), its refactor produced no facet regressions, and it has no redundant instructions left. v3 is not clearly better than v2 on the weaker v3 run, so the dev gain over v2 is within observed run-to-run variation (about ten points between the two v1 runs, 8-12 between the two v3 runs). Selection did not use any holdout result.

`prompts/storyboard.md` is replaced with v3 (byte-identical to `prompts/v3.md`, sha256 `933cbbc632ef772a680bb0d9e4035b052369b00908e5288c8e5778cb09c45611`) so the pipeline agent loads the selected prompt. It is not a frozen file; the evaluations load the evidence copy through `--prompts`.

## Next (user runs; model calls). Run the dev suite first, then the holdout once.
```bash
.venv/bin/python scripts/storyboard_stage3.py run v3 dev --jobs 3 --label final_dev
.venv/bin/python scripts/storyboard_stage3.py run v3 holdout --jobs 3 --label final_holdout
```
If the summary step hangs on `promptfoo --version`, interrupt it and tell me; I will regenerate the summary offline from the raw file (do not delete or re-run: the raw file is the evidence, and a holdout run is counted once).
