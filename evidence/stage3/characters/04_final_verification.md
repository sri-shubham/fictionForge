# Final verification of v3 (full dev re-run + single holdout run)

Prompt v3 (`prompts/characters.md`, byte-identical to `prompts/v3.md`), sha256 `2a0b8426a9b57cbd23a736a248612ddd6e93b9bbe9010b621abd3d88d495d4f1`.
Frozen config verified before and after both runs (config sha256 `115ac28c…`; dev `ea62cfbf…`; holdout `166b2055…`); every
summary records the same three hashes. Same generator (`fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`), grader (`swe-2-medium`),
`--jobs 3`, `--no-cache`. 0 provider errors and 0 grader errors in both runs.

Development and holdout are reported separately and are not pooled.

| Criterion | v3 dev (selection run) | v3 dev (final re-run) | v3 holdout (once) |
|---|---|---|---|
| Cases | 20 | 20 | 10 |
| structural_validity | 20/20 | 20/20 | 10/10 |
| format_discipline | 20/20 | 20/20 | 10/10 |
| injection_resistance | 1/1 | 1/1 | not applicable (dev case 14 only) |
| motivation_clarity (mean) | 20/20 (5.00) | 20/20 (5.00) | 10/10 (5.00) |
| world_consistency (mean) | 20/20 (4.95) | **19/20** (4.70) | 10/10 (4.70) |
| character_differentiation (mean) | 20/20 (5.00) | 20/20 (4.85) | 10/10 (5.00) |
| conflict_potential (mean) | 20/20 (5.00) | 20/20 (5.00) | 10/10 (5.00) |
| character_development (mean) | 20/20 (4.95) | 20/20 (4.95) | 10/10 (4.80) |
| **overall quality pass** | 20/20 (100%) | **19/20 (95%)** | **10/10 (100%)** |

Files: `results/v3_dev.json`, `results/final_dev.json`, `results/final_holdout.json` (each with `.summary.json`), `results/compare_all.md`,
`measurements.json`. The holdout was run once; no holdout result was used for any prompt decision.

## Final dev re-run failure
`05_adventure_jungle_ruins` fails `world_consistency` (score 3): Tobias "burns the key pages", which contradicts `rul_no_fire_aloft`
(open flame forbidden outside shielded forge-pits). This is a genuine world-rule violation, one of the priority failure types, and it
did not occur in the selection run on the same case (score 5). The prompt says "respect the world ... use world rules" but gives no
instruction to check abilities and actions against each rule. No prompt change was made after seeing it: a third revision would be
a different prompt than the one the holdout was run on. It is recorded as the known remaining weakness.

The holdout shows the same kind of tension at score 4: `05_adventure_western` ("hold the brake on the burning footplate" implies open flame
aloft) and `01_scifi_space_station` (premise elements "seventh ring" and "elevators" imported into the World).

## Judge and generation variability, limitations
- **Run-to-run variability is real and is the main caveat.** v3 on the same 20 dev cases scored 20/20 in one run and 19/20 in another.
  Of 100 case/criterion rubric scores, 9 changed between those runs (1 up, 8 down), and one case flipped pass/fail. Mean
  `world_consistency` moved 4.95 -> 4.70 and `character_differentiation` 5.00 -> 4.85. Each run varies both generation (new samples; the CLI
  exposes no temperature or seed) and judging, and they cannot be separated from these files.
  The honest summary of v3 on dev is therefore "19/20 to 20/20 across two runs", not "100%".
- The same noise bounds earlier comparisons: v1 90%, v2 95%, v3 100% are single runs of 20 cases, so the one-case steps between versions
  are within the observed run-to-run variation. What the data does support is narrower: the specific measured failures
  (v1 "no pivotal event" arcs in 2 cases; v2 omitted `home_location_id` in 1 case) did not recur in either v3 run, and load-bearing
  coverage rose from 75.9% to 92.0%.
- Holdout is 10 cases; 10/10 has a wide uncertainty interval (a 95% lower bound near 69%), so it shows no collapse on unseen briefs, not a precise rate.
- Single judge model (`swe-2-medium`), no second judge or human spot-check; judge text is the only evidence for rubric scores.
- Rubrics sit near the ceiling (four of five at mean >= 4.7 in every run); the set discriminates weakly between good prompts. No calibration pilot was run before freezing.
- Prompt and `character_development` rubric are aligned by design, so that criterion is not independent evidence of better characters.
- All 30 fixtures share one World (Aetheria), including briefs for other genres, so world-consistency results are for that one World only.
- Load-bearing coverage is an analytical mapping, not an ablation test.

## Other checks
`.venv/bin/pytest -q`: 272 passed (with v3 installed as `prompts/characters.md`). `scripts/characters_stage3.py verify`: no drift.
`scripts/validate_submission.py`: PASS. World Generation files and other agents were not modified.
