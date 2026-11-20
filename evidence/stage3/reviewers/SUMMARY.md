# Stage 3 adversarial reviewers - consolidated results

Generated from the retained `*.summary.json` files; every figure re-derives from the raw Promptfoo results with `scripts/reviewer_stage3.py summarize`. Nothing here is hand-entered.

| Reviewer | Selected | Dev run 1 | Dev repeat | Holdout (10 cases) | Holdout critical detection | Holdout FP rate | Holdout FN rate | Hard gate failed on holdout |
|---|---|---|---|---|---|---|---|---|
| world | v3 | 29/30 (96.7%) | 29/30 (96.7%) | 8/10 (80.0%) | 100.0% | 20.0% | 0.0% | false_positive_rate |
| characters | v1 | 29/30 (96.7%) | 30/30 (100.0%) | 8/10 (80.0%) | 100.0% | 20.0% | 0.0% | false_positive_rate |
| storyboard | v3 | 30/30 (100.0%) | 29/30 (96.7%) | 7/10 (70.0%) | 100.0% | 40.0% | 0.0% | false_positive_rate |

Reading:
- The 95% overall case-pass target was met on the development set for all three reviewers (both runs) and **not met on the holdout for any of them** (80%, 80%, 70%).
- Holdout critical-issue detection was 100% and the false-negative rate 0% for all three: no planted defect or injection was missed.
- All three failed the false-positive hard gate on the holdout (valid artifacts sent back for revision). In the workflow a false positive costs a producing-step retry, not an unsafe handoff.
- Of the 7 holdout failures, 3 are reviewer errors (severity under-call, short evidence fragment, misquoted brief) and 4 look like fixture weaknesses on re-reading (one introduced by my own dataset correction); this audit is post-hoc and no reported number or fixture was changed because of it. See each reviewer's iteration log, sections 6 and 8.
- Retained history includes the superseded rev0 dataset runs for Characters and Storyboard (`dataset_rev0/`) and every failed or regressed prompt version.

Logs: `evidence/iterations/reviewers/{world,characters,storyboard}.md`.

## Stage 4 update (2026-11-13)

Iteration continued on the holdout false-positive classes. Current installed selections (`prompts/reviewers/`):

| Reviewer | Installed | Dev (latest valid runs) | Diagnostic holdout | Hard gates on holdout |
|---|---|---|---|---|
| world | v6 | 29/30 (96.7%) | 10/10 | all met |
| characters | v3 | 29/30 (96.7%) | 10/10 | all met |
| storyboard | v9 | 28/30 (93.3%), 28/30 | 10/10 | all met |

Reading:
- The false-positive hard gate now passes on the diagnostic holdout for all three reviewers; storyboard v9 is the first version to meet **all** thresholds on a holdout run (10/10).
- Storyboard reviewer dev case-pass is 93.3% vs the 95% target — residual misses are one perennially flaky fixture (SR-D06) and single-observation borderline FPs; detection metrics are 100%.
- **Caveat:** all holdouts are diagnostic (the same frozen 10 cases examined across iterations). A fresh independent holdout with pre-fixed reference labels is still required for certification.
- Full iteration history, rejected versions and mechanism notes: `evidence/iterations/reviewers/storyboard.md` section 10, `evidence/iterations/reviewers/characters.md` section 10, `evidence/iterations/reviewers/world.md` sections 10–14.
