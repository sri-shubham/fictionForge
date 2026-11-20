# v4 result and v5 pre-registration

Continuation of the stage-3 refinement (v1->v3, docs 01-04) after the reviewer
prompt work was descoped. Same frozen eval config (verified, no drift), same
20 dev / 10 holdout cases, same generation and grader models. v3 is the
baseline (dev 19/20 x2, holdout 9/10, combined 28/30).

## Iteration 3: v3 -> v4 (contract alignment)

Hypothesis (pre-registered): holdout `08_forbidden_dragon` failed
`structural_validity` because the model copied the brief's title into
`history[].era` ("Dragonless Age" contains forbidden term "dragon"). Prompt
rule 3a scopes `forbid:` to "the world's name, description, rule statements,
or entity descriptions", but `validators._world_text_fields` scans every
free-text field including all entity `name`s, `description`s, rule
`statement`s and history `era`s (substring, case-insensitive). The prompt
under-specifies the frozen contract.

Change (one clause): `forbid:`/`require:` scope rewritten to cover all
free-text fields (incl. entity names and `era`) with substring semantics
stated explicitly. Diff: `diffs/v3_to_v4.diff`.
v4 sha256 `a0b1b6ecd411b2a1bbdcd102a78e6919ee7ffb9de36eec1b61c23c5200b53c25`.

Dev result (`eval-gBf-2026-11-13T07:56:02`, `results/v4_dev.json`):
19/20, structural 20/20, sole failure `17_mystery_country_house` originality 3.
Prediction held exactly: zero dev effect (no dev case exercises an
era-position forbid), no regression. The fix is verifiable only on holdout.

## Iteration 4: v4 -> v5 (originality)

Observed failure: `originality` is the only failing criterion, three
consecutive runs (v3 dev `03`, v3 final `17`, v4 `17`), judge reason
consistent each time: the world is a competent genre default containing
nothing beyond the brief ("no real twist beyond the brief", "interchangeable
with any Christie-style manor mystery"). Rubric checks (b) twist beyond genre
default AND the brief itself, (d) non-transferable details. The prompt's only
originality instruction was "aim for original details".

Change (one bullet extended): require at least one distinctive element beyond
the brief itself that could not be dropped unchanged into another world of
the same genre. Diff: `diffs/v4_to_v5.diff`.
v5 sha256 `41b0283ffb47b6db44d019fef1d1dcdc3ccb101f7a3f355bf3eb42cf8471d4d5`.

Dev result (`eval-phy-2026-11-13T08:10:48`, `results/v5_dev.json`):
20/20 - first perfect dev run for this prompt. originality 18/18, mean 5.0
(v3: 4.50/4.56, v4: 4.44). `17` scored 5 with the judge citing the
"beyond-brief" element directly ("the Ledger of Courtesies - a guest book
requiring truthful confessions - is a distinctive twist"). internal_consistency
4.833 and narrative_potential 4.889 within the +/-0.1 noise floor; no
regression on any criterion. Hypothesis supported.

Honesty note: the v5 bullet mirrors rubric language, so the originality gain
is aligned-to-rubric, not independent evidence of more original worlds (same
disclosure as characters v3). One run only; a repeat and a diagnostic holdout
run are pending.
