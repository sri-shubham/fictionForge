# v1 baseline result (Red) and v2 pre-registration (written before any v2 run)

Run: `results/v1_dev.json` (+ `.summary.json`), eval `eval-I8Q-2026-11-02T08:45:20`, prompt v1 sha256
`0a0350405f01bf43dbacfe865d5feabec780243aaf5265130dff8f05e16c4d1b`, frozen config verified, `--jobs 3`,
0 provider errors, 0 grader errors. No calibration pilot was run.

| Criterion | v1 dev (20 cases) |
|---|---|
| structural_validity | 20/20 |
| format_discipline | 20/20 |
| injection_resistance | 1/1 |
| motivation_clarity | 20/20, mean 4.95 |
| world_consistency | 20/20, mean 4.90 |
| character_differentiation | 20/20, mean 4.95 |
| conflict_potential | 20/20, mean 5.00 |
| character_development | **18/20**, mean 4.70 |
| **overall quality pass** | **18/20 (90%)** |

## Measured failures (Red)
Both failing cases fail `character_development` with score 3, and the judge gives the same reason in each:
a main character's arc "names a start and end state but no pivotal event or choice"
(`13_conflicting_count_and_max`: Mira; `17_mystery_country_house`: Odalys).
The same weakness appears in two passing cases scored 4 (`06_historical_inspired_rome`, `08_constrained_exact_3`:
"implied but not explicitly named pivotal events"). So 4 of 20 cases show it; it is the only criterion with a failure.

Other sub-threshold-adjacent scores (all passed, single cases, not targeted): invented named span "the Weaver's Reach"
(`01`, world_consistency 4); a three-generation wind-debt straining the "repaid within a season" rule (`15`, 4);
stock-adjective-only personality traits (`04`, differentiation 4); an ideological motivation (`16`, motivation 4).

## Hypothesis H1 (v1 -> v2)
The v1 `arc` instruction only asks for "a non-empty summary of how the character develops", and rule 9 asks for a
"plausible" arc. Neither requires a concrete pivotal event, so the generator sometimes writes only a start and end state.
Making the arc's required content explicit (starting state, one pivotal event or choice drawn from the external conflict,
a relationship or a World element, end state, addressing the flaw/internal conflict, for every character) will remove the
"no pivotal event" failures and raise `character_development` pass rate above 18/20 without lowering other criteria.

Change: one bullet in the output contract (`diffs/v1_to_v2.diff`); v2 sha256
`5b961ef3746e4af67365c403c8f93d328734dbf27cd66294d60f2aa4c65474b8`. Nothing else differs.

## Pre-registered risks / caveats
- Arc text gets longer: could breach `LongText` 4000 chars (would show as structural_validity) or crowd other fields.
- The prompt now states what the `character_development` rubric checks. This is deliberate (the rubric encodes the desired
  behaviour) but the gain is on a rubric the prompt is aligned to; it is not independent evidence of better stories.
- With 20 cases and a judge that moves +/-1 between runs (World's evidence showed the same), a one-case difference is
  not significant. The claim will be limited to: failures of the specific kind "no pivotal event" disappear or not.
- Load-bearing coverage of v2 is 23/30 = 76.7% (`matrices/load_bearing_v2.*`); redundancy is not addressed until v3.

## Next
Run: `.venv/bin/python scripts/characters_stage3.py run v2 dev --jobs 3`
