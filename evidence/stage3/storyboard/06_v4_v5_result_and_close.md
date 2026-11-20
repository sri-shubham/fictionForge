# Stage 4 refinement - Storyboard prompt: v4/v5 results and close-out (v3 retained)

## v4 result

Two dev runs as pre-registered in `05_v4_preregistration.md`:
`v4_dev` and `v4_dev_repeat1`, both **23/25**, valid runs.

Deterministic facets (the pre-registered predictions):

- (a) Malformed JSON / extra `}` after the first scene: **did not recur** in
  either run (~50 outputs clean vs 3/74 under v2/v3). Prediction supported.
- (b) Nonexistent `depends_on` reference: **did not recur**. Prediction supported.
- Overall: 23/25 x2 (92%) vs v3 pooled 90.5% — within the documented
  one-to-three-case noise band; not evidence of improvement.

New failure class observed: truncated/stopped-early boards on edge-case briefs —
`16_highly_constrained` and `20_nonexistent_character` emitted setup-only acts,
and `16`/`21_invented_location` added a `"_note"` extra root key annotating the
abbreviation (violating the no-extra-keys rule it sits next to).

## v5 iteration and result

v5 = v4 + one completeness rule ("Deliver the complete storyboard ... all four
required purposes ... never stop after the setup, leave a phase out, or add
placeholder, note or commentary fields"), targeting the truncation/`_note` class.

- `v5_dev`: **23/25**. The `_note` keys and setup-only truncation did not recur;
  failures were `05_survival_horror` (soft-rubric miss on an otherwise
  well-formed board — the extra-`}` mechanism did **not** return) and
  `07_*` (a scene violating `rul_no_fire_aloft`).
- `v5_holdout_diag`: **9/10** (`10_conflicting_count_min`). Diagnostic only —
  the holdout was previously examined; not a fresh certification set.

## Selection decision: v3 retained

| | v3 (selected) | v4 | v5 |
|---|---|---|---|
| dev (pooled) | 67/74 scored, 90.5% | 23/25, 23/25 | 23/25 |
| holdout | 10/10 (run once) | not run | 9/10 diag |

v4 and v5 plausibly eliminated the extra-`}` mechanism (0 recurrences in ~35
outputs vs 3/74 before) and the truncation/`_note` class, but neither measurably
outperformed v3 on the retained record; per protocol the stronger measured
version is retained. v4/v5 remain on disk
(`evidence/stage3/storyboard/prompts/v4.md`, `v5.md`) as contract-hardening
candidates if a fresh holdout or more dev runs ever shows the difference is real.

`prompts/storyboard.md` remains byte-identical to `prompts/v3.md`
(sha256 `933cbbc6…`).

## Remaining limitations

- Dev case-pass sits in an 88–96% band across identical v3 runs vs the 95%
  target; a one-case gap at n=25, not statistically resolvable at this size.
- The v4/v5 contract fixes are unverified at this sample size for the
  low-base-rate classes they target; documented as candidates, not selected.
- World-rule violations in generated scenes (`rul_no_fire_aloft` class) keep
  appearing across agents; no prompt clause has been verified to prevent them.
- Holdout remains diagnostic; a fresh independent set is required for
  certification.
