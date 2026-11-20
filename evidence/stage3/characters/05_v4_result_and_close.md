# Stage 4 refinement - Characters prompt: v4 result and close-out (v3 retained)

v4 = v3 + one clause extending the world-rule bullet: character actions may not
violate world rules (drafted after `04_ghost_ship`-class findings where cast
behaviour contradicted `rul_*` statements, e.g. open flame under
`rul_no_fire_aloft`).

## v4 result

`v4_dev`: **19/20** (`04_ghost_ship`, weak faction/location linkage — the known
residual class, not the rule-violation class the clause targets). The
rule-violation mechanism did not recur in this run, but the base rate is too
low at n=20 to verify a fix.

## Selection decision: v3 retained

| | v3 (selected) | v4 |
|---|---|---|
| dev | 20/20 (v3_dev), 19/20 (final_dev) | 19/20 |
| holdout | 10/10 (run once) | not run |

v4 did not measurably improve on v3's record; v3 is retained and remains
installed as `prompts/characters.md` (sha256 `2a0b8426…`). v4 stays on disk as a
hardening candidate for the world-rule-violation class.

## Remaining limitations

- World-rule-violating character actions appear at low base rate (~1/40
  outputs); the v4 clause is unverified, not rejected.
- Residual weak-linkage failures (`04_ghost_ship` class) appear under both
  versions at noise frequency.
- Holdout remains diagnostic; a fresh independent set is required for
  certification.
