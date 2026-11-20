# v6 result and pending items

## Iteration 5 result (v6)

Dev result (`eval-5if-2026-11-13T08:38:56`, `results/v6_dev.json`):
20/20, structural 20/20, originality mean 4.944, internal_consistency 4.833,
no regression versus v5.

Diagnostic holdout (`eval-4fv-2026-11-13T08:45:05`,
`results/v6_holdout_diag.json`, label `v6_holdout_diag`): 9/10, structural
9/10, all other criteria 100%. `09_required_chosen_one` now passes (the id
copying fix held). Sole failure `06_historical_napoleonic`
(`forbid:gunpowder`): the model wrote "it has no gunpowder" in the world
`description` (negating the forbidden term still contains it as a substring);
`rul_no_gunpowder_weapons` is an id, which the validator does not scan, so only
the description tripped it. This is a new failure mode (mentioning a forbidden
term in order to negate it), not a regression of the earlier fixes.

Decision: v6 result accepted by the user as acceptable (9/10 holdout, 20/20
dev). No further prompt change made for the `06` negation failure. Holdout is
diagnostic only (already examined across several prompt versions).

## Pending

- v6 dev repeat (stability of the 20/20).
- Fresh untouched holdout still required for certification.
- Known residual risk: negated mentions of a `forbid:` term (`06`) are not
  addressed by the prompt.

## Post-hoc housekeeping (2026-11-13)

- `prompts/versions/` was removed from the repository. The prompt files now live only at `evidence/stage3/world/prompts/v1.md` through `v6.md` (byte-identical copies, sha256 unchanged).
- The World eval default prompt path in `evals/world_stage3.yaml` is now `evidence/stage3/world/prompts/v1.md`. `--prompts` still overrides it on every run. The yaml sha changed from `2dceef84b26d436bc5eeec1bcdfa4d849a3bb71fcd5932db23a957d870f861c5` to `b72716ddd7e4603f107d445f4762ff3cd68c0166f4b6e05975a17c7599411e6a`; the amendment is recorded in `amendments` in `frozen_eval_config.json`. No other frozen file or dataset changed, and `world_stage3.py verify` passes.
- `world_stage3.py run` and `summarize` now read `evidence/stage3/world/prompts/vN.md`, and the default run label is `vN_split`.
- Summaries produced before this date record the old `config_sha256` (`2dceef84...`) and `prompt_path: prompts/versions/world_vN.md`. Raw results are unchanged, and their `prompt_sha256` values still match the new prompt files.
