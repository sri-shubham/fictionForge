# v5 diagnostic holdout and v6 pre-registration

## v5 diagnostic holdout

`results/v5_holdout_diag.json` (`eval-R9c-2026-11-13T08:26:11`): 9/10,
structural 9/10. `08_forbidden_dragon` now passes (v4 era-forbid fix
confirmed). New sole failure `09_required_chosen_one`: dangling reference
`fac_resolvers` in two conflicts' `faction_ids` (the faction was emitted as
`fac_the_resolvers`), i.e. the model re-derived an id from the name instead of
copying it. internal_consistency 4.667 for the same reason.

## Iteration 5: v5 -> v6 (id reference copying)

Hypothesis: the `09` failure is a prompt under-specification of reference
integrity, not a quality problem. Change (one clause in rule 2): wherever
`location_ids` / `faction_ids` reference an entity, copy its `id` string exactly
as emitted; do not re-derive it from the name. Diff:
`diffs/v5_to_v6.diff`.
v6 sha256 `539ecd6a3dc9c81899fd5bdefb5d02a8b1ebcf99eaeb3fd9c59faa316312a84f`.
