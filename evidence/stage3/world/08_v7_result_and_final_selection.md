# Stage 4 refinement - World prompt: v7 result and final selection (v6 installed)

## v7 iteration and result

v7 = v6 + extension of the `forbid:` clause to cover negated mentions ("never
write the forbidden text even to say it does not exist"), drafted after the v6
holdout failure `06_historical_napoleonic` ("it has no gunpowder" in
`$.description`).

`v7_dev`: **19/20** — `16_scifi_cyberpunk` emitted an extra `name` key on all
10 rule objects (a new slip class unrelated to the negation clause). The
negated-mention mechanism did not recur, but at n=20 that is not a verification.

## Selection decision: v6 installed

| | v6 | v7 |
|---|---|---|
| dev | **20/20** | 19/20 |
| holdout diag | 9/10 | not run |

v7 scored strictly worse on its only measured run and offered no verified
benefit; v6 is selected and installed as `prompts/world.md`
(sha256 `539ecd6a3dc9c81899fd5bdefb5d02a8b1ebcf99eaeb3fd9c59faa316312a84f`).
The v7 prompt file is retained at `evidence/stage3/world/prompts/v7.md`.

## Final measured record for v6

- dev `v6_dev`: 20/20, structural 20/20, originality 4.944.
- holdout `v6_holdout_diag`: 9/10 — `08_forbidden_dragon` passes (era-copy fix
  verified), `09_required_chosen_one` passes (id-copying fix verified); sole
  failure `06_historical_napoleonic` negated-forbid substring.

## Remaining limitations

- **Negated mentions of `forbid:` terms are a known open failure mode** (the
  `06` mechanism). The drafted v7 clause is on disk unverified.
- `v6` has a single dev run; a repeat would tighten the 20/20 stability
  estimate.
- Holdout is diagnostic (previously examined); a fresh independent set is
  required for certification.
