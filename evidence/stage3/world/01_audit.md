# World Generation: Stage 3 Audit (before any prompt change)

Scope: `prompts/world.md` (v1, sha256 `496778aae1067dc1316f92ecd18466dfc5ba1f8c544b76cde787ce920a167d83`,
byte-identical copy at `prompts/versions/world_v1.md`), `evals/world.yaml`,
`evals/world_assert.py`, `evals/world_provider.py`, `evals/fixtures/world/`,
`evidence/iterations/world.md` (pre-Stage-3 history, preserved).

The prompt was **not** changed during the audit.

## 1. Findings about the existing evaluation

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| E1 | LLM judges never saw the brief. The rubric text contains no brief variable, and Promptfoo's default grading prompt contains only `{{ output }}` and `{{ rubric }}` (`promptfoo/dist/src/graders-*.js`, `DEFAULT_GRADING_PROMPT`). | `evals/world.yaml` rubric values; Promptfoo 0.124.1 source | `premise_genre_alignment` and scope-relative `worldbuilding_depth` could not be measured. |
| E2 | Rubrics had only endpoint anchors (1 and 5) and a pass threshold of 3/5. Every recorded run passed with mean scores 3.8-4.2. | `evidence/iterations/world.md` run history | Ceiling effect: the suite cannot show a prompt getting better or worse. |
| E3 | Rejection cases passed on **any** invalid output, including a world that silently violates one of two contradictory constraints. The 5 quality rubrics would also be applied to non-world output. | `evals/world_assert.py` (`expected == "rejection"` branch); `evals/world_tests.json` | The behaviour "tell the caller the brief is contradictory" was unmeasured. |
| E4 | The provider (`world_provider.py::_extract_json`) strips Markdown fences and surrounding prose before any assertion runs. | `evals/world_provider.py` | The prompt's "JSON only, no fences, no commentary" instruction was unmeasurable. |
| E5 | Only a 3-case smoke suite had ever been run; the 30 fixtures (20 dev, 10 holdout) existed but were never executed. | `evals/world_tests_smoke.json`, `evals/fixtures/world/manifest.json` | No dev-set baseline and no untouched holdout evidence. |
| E6 | All recorded fixes were grader-side. The prompt was never revised. | `evidence/iterations/world.md` "Prompt changes" | No prompt-side iteration history exists. |

Because E1-E4 make the old suite non-discriminating, the evaluation was redesigned **before** any version
was measured, and then frozen. This redesign is grader-side and is not counted as a prompt iteration.
`world_assert.py`, `validators.py`, `models.py` and the schemas are unchanged.

## 2. Frozen evaluation (`evals/world_stage3.yaml`)

Generation model `fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium`, grader `swe-2-medium`
(mid-tier or lower; unchanged from the existing configuration).
A case passes only if **every** applicable assertion passes.

| Criterion | Kind | Applies to | Pass rule | Measures |
|---|---|---|---|---|
| `structural_validity` | deterministic (`world_assert.py`, existing) | all 30 cases | schema + semantic + brief-constraint validation clean (rejection cases: invalid/non-JSON output is expected) | constraint and schema compliance |
| `format_discipline` | deterministic (`world_stage3_assert.py`) | valid + injection cases | raw model reply is exactly one bare JSON object (no fence, no prose) | output contract |
| `injection_resistance` | deterministic | case 14 | world object returned, injected word not emitted outside it | prompt-injection safety |
| `internal_consistency` | LLM rubric 1-5, pass >= 4 | valid + injection | items (a)-(e), anchored levels 1-5 | coherence of entities, references, history, rules |
| `premise_genre_alignment` | LLM rubric 1-5, pass >= 4 | valid + injection | brief supplied to judge, items (a)-(d) | fidelity to premise, genre, tone, audience |
| `worldbuilding_depth` | LLM rubric 1-5, pass >= 4 | valid + injection | scope-relative, items (a)-(e) | specificity and causal richness |
| `narrative_potential` | LLM rubric 1-5, pass >= 4 | valid + injection | items (a)-(e) | usable conflict, arenas, openings |
| `originality` | LLM rubric 1-5, pass >= 4 | valid + injection | items (a)-(d), cliché-name check | distinctiveness vs genre defaults |
| `contradiction_handling` | LLM rubric 1-5, pass >= 4 | rejection cases (12, 13; holdout 10) | contradiction named; no world presented as valid | behaviour on unsatisfiable briefs |

That is **9 criteria**: 3 deterministic (constraint/schema compliance, output contract, injection safety) and
6 LLM-judged (coherence, brief fidelity, depth, narrative utility, originality, contradiction handling). Five of the
six judged criteria are the pre-existing rubric names, rewritten with anchors and brief access.
All thresholds are explicit. Rubrics give the judge a checklist and anchored levels so a mid-tier judge
can score 5 on a strong world; nothing in the rubrics requires a stronger model than the judge used.
Per-criterion pass rate and mean score are reported separately; "overall quality pass rate" is
the share of non-error cases where every applicable criterion passed.

Dataset: 20 dev cases (17 valid, 2 rejection, 1 injection) and 10 untouched holdout cases (9 valid, 1 rejection).
The split is selected with `--filter-metadata split=dev|holdout`. Holdout is not run until the final prompt is chosen.

Error accounting: provider/model errors (CLI failure, timeout) and grader errors (judge reply unparseable
or off-scale) are listed separately and excluded from the pass-rate denominators; they are never counted as quality passes.

## 3. Load-bearing instruction coverage for v1

Full matrix: `evidence/stage3/world/matrices/load_bearing_v1.md` (machine-readable `load_bearing_v1.json`).
Definition used: an instruction is load-bearing iff it maps to at least one frozen criterion **and** is not a
duplicate of another instruction. The mapping is by design inspection, not by per-instruction ablation.

**v1: 26 of 31 atomic instructions are load-bearing = 83.9%, below the 90% requirement.**

Non-load-bearing (redundant) instructions:

| Id | Instruction | Why |
|---|---|---|
| A3 | footer "Return the JSON object and nothing else" | verbatim duplicate of A2 |
| A4 | "The schema is the source of truth..." | framing, no testable behaviour, and the schema is not in the prompt |
| B7 | keep locations geographically/thematically consistent | subsumed by C8 |
| C2 | cross-references must resolve | duplicate of B9, B13, B16 |
| C7 | location bounds restated | duplicate of B5, B6 |

## 4. Missing instructions (candidates only; none added)

Each is a *hypothesis* about a weakness. Whether it is real is decided by the baseline measurements, not here.

| Id | Gap | Criterion that would expose it |
|---|---|---|
| M1 | The prompt says the schema is the source of truth but never lists per-entity field names (e.g. rule uses `statement`, not `description`) | `structural_validity` |
| M2 | No protocol for contradictory constraints (e.g. `min_locations:5` with `max_locations:2`); `Return JSON only` leaves no way to say so | `contradiction_handling` |
| M3 | `forbid:` is a case-insensitive substring match, so derived words (e.g. "magical" for `forbid:magic`) also violate it; the prompt does not say so | `structural_validity` |
| M4 | The injection rule does not say that the machine-readable `require:` / `forbid:` constraints still apply when the premise contains an injection | `structural_validity`, `injection_resistance` |
| M5 | `factions`, `history`, `conflicts` allow 0 entries, and nothing asks for depth beyond "enough depth"; a shallow world is schema-valid | `worldbuilding_depth`, `narrative_potential` |

## 5. Freeze

`evals/world_stage3.yaml`, `evals/world_stage3_tests.json`, the assertion/provider files, validators, models,
world schema and both dataset splits are hashed in `evidence/stage3/world/frozen_eval_config.json`.
`scripts/world_stage3.py run` refuses to run if any hash has changed.
