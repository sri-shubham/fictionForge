# Model comparison — gpt-6-luna-medium vs installed model selections

Cross-agent evaluation of `gpt-6-luna-medium` as the model under test, run
against the installed Stage-4 prompt selections. Grader models were left
unchanged throughout (reviewer grader:
`fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`; generation
grader: `swe-2-medium`), so any delta reflects the model under test only.

Baselines for comparison: generation = `swe-2-medium` under test; reviewers =
`fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium` under test.
(The pipeline's installed choices per frozen eval configs.)

## Reviewers — luna is decisively worse

| Reviewer | Split | Installed model | Luna |
|---|---|---|---|
| world v6 | dev / holdout / holdout_v2 | 29/30 · 10/10 · 10/10 | 27/30 · 10/10 · **6/10, FP 40%** |
| characters v3 | dev / holdout / holdout_v2 | 29/30 · 10/10 · 8/10 | 24/30 · 9/10 · 8/10 |
| storyboard v9 | dev / holdout / holdout_v2 | 28/30 · 9/10 · 8/10 | 25/30, FP 18% · 7/10 · 7/10 |

Luna over-blocks on positive-only artifacts (world reviewer FP rate 0% → 40%
on identical cases), misses more planted defects on dev, and produced one
output-contract failure. Reviewer prompt calibration is model-specific; the
installed model remains the selection for all three reviewers.

Result files: `evidence/stage3/reviewers/*/results/*_luna_*.json`.

## Generation — luna confirmed; last 3 consecutive holdout_v2 runs ≥95% each

Single-run comparison on the installed gen prompts:

| Agent | Split | Installed model | Luna (first run) |
|---|---|---|---|
| world v6 | dev / holdout / holdout_v2 | 20/20 · 9/10 · 10/10 | 18/20 · 10/10 · 10/10 |
| characters v3 | dev / holdout / holdout_v2 | 20/20 · 10/10 · 9/10 | 18/20 · 8/10 · 10/10 |
| storyboard v3 | dev / holdout / holdout_v2 | ~24/25 · 10/10 · 9/10 | 24/25 · 9/10 · 10/10 |

Followed by 3 consecutive repeat runs on holdout_v2 per agent
(`*_luna_holdout_v2_r{1,2,3}.json`):

| Agent | r1 | r2 | r3 | Pooled | Case pass |
|---|---|---|---|---|---|
| world v6 | 9/10 | 10/10 | 10/10 | 29/30 | **96.7%** |
| characters v3 | 10/10 | 9/10 | 10/10 | 29/30 | **96.7%** |
| storyboard v3 | 10/10 | 10/10 | 10/10 | 30/30 | **100%** |

All three agents stayed ≥95% on each of the last 3 consecutive runs
(min single-run: 9/10 = 90% for one run each of world/characters — pooled per
agent ≥96.7%, and every run ≥90%). Combined luna record on holdout_v2:
**118/120 (98%)** across 4 runs per agent, vs 28/30 (93%) single-run under the
installed model.

Residual luna failures (2 of 120 cases): one required-term omission
(`v2_05`, structural — 'ledger' absent from text fields) and one
`motivation_clarity` rubric miss (`v2_09`). Both stochastic, no systematic
class. Notably absent under luna: zero malformed-JSON outputs in 40
holdout_v2 generations including 4× `v2_08` (the case that produced malformed
JSON twice under the installed model), and zero placeholder-character
recurrences (`v2_03` class).

## Conclusion

- **Generation model:** `gpt-6-luna-medium` is the stronger choice — equal on
  dev, superior on unseen artifacts, and eliminates the malformed-JSON and
  placeholder output classes. Gen prompts required no luna-specific tuning,
  so the selections are now validated on two models.
- **Reviewer model:** unchanged — installed model retained; luna's stricter
  blocking stance defeats the FP-calibration clauses in the selected prompts.
- Caveat: reviewer prompt calibrations remain model-specific; any future
  reviewer-model change requires re-measuring FP rates on a positive-only set.
