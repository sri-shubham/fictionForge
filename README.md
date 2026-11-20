# FictionForge

FictionForge is a deterministic, validator-backed story-planning workflow. A
story brief goes in; three LLM-backed steps run in sequence, each producing a
JSON artifact that is validated in Python before it is handed to the next step:

1. **world_generation** — builds the world (locations, factions, events)
2. **character_design** — builds the cast against that world
3. **storyboard_building** — builds the storyboard against world and characters

Retries and punch-outs are controlled entirely by code, never by the LLM.
Guardrail validators live in `src/fictionforge/guardrails/validators.py`;
punch-out handling (the human-approval path) lives in
`src/fictionforge/guardrails/punch_out.py`. The runner is
`src/fictionforge/runner.py`; runtime config (provider, model, retry limits)
is `config/workflow.yaml`.

## Running the workflow

```bash
python runner.py --brief examples/story_brief.json
```

Useful flags: `--output-dir` (default `runs/`), `--config`, `--provider`
(`devin` or `ollama`), `--model`, `--resume RUN_ID`, `--decisions`,
`--decide approve|deny --run-id RUN_ID --punch-out ID --approver NAME`, and
`--approved-by NAME`. Resuming a punched-out run requires a signed decision
recorded via `--decide` (`--approved-by` is only a consistency check on the
decision's attested approver); see `docs/workflow.md` §5.

## Adversarial review guardrails

Independent reviewer agents sit at every handoff boundary. They are
workflow-level guardrail components using the Stage 3-selected prompts
(`prompts/reviewers/{world,characters,storyboard}.md` — world v7, characters
v4, storyboard v10; byte-identical to the prompts hashed in
`evidence/stage3/reviewers/*/prompt_hashes.json`), a different evaluation
perspective from the generators, and their own model settings
(`review.model` in `config/workflow.yaml`, default `swe-2-medium`, with
per-gate overrides in `review.models`: characters and storyboard run
`deepseek-v4-1-flash-1017-high`). Reviewers never modify artifacts. Code: `src/fictionforge/guardrails/review.py` (reviewer client,
acceptance policy, evaluation) and `src/fictionforge/guardrails/handoff.py`
(gate keeper and handoff hook); the verdict contract is the shared
`fictionforge.guardrails.reviewer_contract` module — the same code the
Stage 3 reviewer evaluations judged.

```text
Generate -> deterministic validation -> adversarial reviewer -> handoff gate -> next step
 (world)                                                         world.approved
 (characters)                                                    characters.approved
 (storyboard)                                                    storyboard.approved  (final acceptance)
```

Review is enabled by `review.enabled: true` in `config/workflow.yaml`
(`WorkflowConfig.review_enabled` defaults to `False` only so that library users
and the pre-existing offline tests that script exact generator call sequences
are unaffected). `--no-review` disables the gates for a run (reviewers do not
run, no approvals are written, nothing is reviewed — it is an explicit
operator choice, always printed and recorded in `summary.json`).

**Reviewers are NOT fully Stage 3 qualified.** All three met the development
targets but failed the false-positive hard gate on the holdout (holdout case
pass 80/80/70%; 100% critical detection, 0% false negatives; holdout FP rate
20/20/40%). They are integrated anyway because a false positive costs a
producing-step retry, not an unsafe handoff — see `evidence/stage4/README.md`.

### Review modes

`review.mode` is `enforced` (default) or `shadow`; `--review-mode` overrides
the config. In **enforced** mode reviewer verdicts gate handoffs as described
below. In **shadow** mode the reviewer still runs and everything is recorded
(prompt hash, verdict, findings, latency, token usage), a shadow-signed
approval is written (`gate_decision` `SHADOW_HANDOFF_PERMITTED`), and each
gate record notes the `enforced_equivalent_decision` — but reviewer verdicts
and errors never block. Deterministic pieces still block in shadow mode:
schema/reference validators, integrity/tamper/upstream-approval halts, and
blocking deterministic injection-scan findings. **Shadow results are not
proof of enforced adversarial guardrails** — the summary and every audit
event say so. A shadow approval never verifies under an enforced keeper and
vice versa.

### Reviewer verdict (untrusted model output)

```json
{"verdict": "PASS|REVISE|PUNCH_OUT", "issues": [], "reason": "..."}
```

Each issue has `code`, `severity` (`critical|major|minor`), `artifact_path`
(e.g. `$.history[0].description`, optionally `brief::`/`world::`/`characters::`
prefixed), `evidence` (a verbatim quote), `reference_path` (or `null`),
`explanation`, `suggested_correction`. Parsing is strict: exactly one bare
JSON object (code fences rejected), no unknown or duplicate keys, `PASS`
cannot carry critical/major issues, `REVISE` needs at least one, `PUNCH_OUT`
requires a critical `POLICY_*` issue, and text claiming approval authority is
rejected. Anything else is a malformed response and can never be a pass — a
contract-invalid or empty response consumes one bounded re-ask from
`review.max_attempts` (fresh nonce); if every attempt is invalid the reviewer
fails closed as `REVIEWER_INVALID_RESPONSE`.

### Hook sequence (per gate, all enforced by runner code)

1. Verify artifact and input hashes and the upstream approvals (`<gate>.approved`).
2. Re-run the existing deterministic validators (blocks in both modes).
3. Deterministic scan for reviewer-directed injection text, then call the reviewer
   (bounded by `review.max_attempts`; re-asked for timeouts, provider errors, and
   contract-invalid/empty responses).
4. Parse the reviewer response on the shared contract; ground every issue's
   paths and evidence against the documents.
5. Apply the acceptance policy (`decide()`): PUNCH_OUT is honoured only when a
   critical `POLICY_*` issue's evidence is grounded *and* deterministically
   corroborated (injection scan hit or punch-out language in the quote).
6. Write the gate record `gates/<gate>_review.json` (+ `gates/history/<gate>_attempt_N.json`)
   including `review_mode`, `prompt_version`, grounding flags, repeated-finding
   tracking, false-positive candidates and (when supplied) label comparisons.
7. Only on a passing decision, trusted runner code writes the HMAC-signed
   `gates/<gate>.approved` binding the artifact hash, input hashes, validation
   result hash, review record hash and the enforcement mode. The runner then
   re-verifies that approval before accepting the handoff.

The HMAC key is held in memory (or taken from `FICTIONFORGE_GATE_KEY`, hex) and is never
written to disk, so a model-written approval file has no authority. Each gate evaluation
first deletes any existing sentinel. Downstream steps and the final acceptance gate
re-verify all three sentinels (with their input hashes) before running or completing.

REVISE retries consume the same `max_attempts_per_step` budget as validation
retries — there is no separate reviewer retry budget and no infinite loop.
Every regenerated artifact goes through the whole loop again: fresh
validation, fresh reviewer call (fresh nonce), fresh gate decision; verdicts
and approvals are never cached or reused.

### Workflow branches

| Condition | Gate decision | Runner outcome |
|---|---|---|
| Deterministic validation fails | `RETRY` / `FAILED_RETRIES_EXHAUSTED` | Retry producing agent with validator feedback (bounded by `max_attempts_per_step`) |
| Reviewer `PASS`, no blocking findings | `APPROVED` (enforced) / `SHADOW_HANDOFF_PERMITTED` (shadow) | Artifact saved, sentinel written, next step runs |
| Reviewer `REVISE` (or deterministic injection finding overriding `PASS`) | `RETRY` | Producing agent retried with the reviewer's structured issues as data; same attempt budget |
| `REVISE` on the last attempt | `FAILED_RETRIES_EXHAUSTED` (`REVIEW_RETRIES_EXHAUSTED`) | `failed_automated`; downstream never runs |
| Reviewer timeout / provider error after `review.max_attempts`, or invalid response after the bounded re-ask | `FAILED_REVIEWER` (`REVIEWER_TIMEOUT`, `REVIEWER_PROVIDER_ERROR`, `REVIEWER_INVALID_RESPONSE`) | `failed_automated` (fail closed); generator is not re-run |
| Reviewer `PUNCH_OUT` confirmed by trusted policy logic (critical `POLICY_*` issue, grounded evidence, plus deterministic corroboration for `POLICY_GUARDRAIL_BYPASS_ATTEMPT`) | `HALT_PUNCH_OUT` | `punch_out_required` (exit code 2), human review |
| Reviewer `PUNCH_OUT` that cannot be confirmed (ungrounded or uncorroborated) | downgraded to `REVISE` | Treated as `REVISE` (never PASS, never an unearned escalation) |
| Artifact or input hash changed, or approval changed after review | `HALT_ARTIFACT_TAMPERED` | `punch_out_required`; failure recorded |
| Approval sentinel missing, unsigned or forged | `HALT_GATE_APPROVAL_INVALID` | `punch_out_required`; downstream generator not called |
| Approval cannot be written | `FAILED_REVIEWER` (`GATE_WRITE_FAILED`) | `failed_automated` |

`--resume` re-verifies upstream approvals; when they cannot be verified in the new
process it re-runs the validators and reviewer for the upstream artifact and only
continues if that is approved.

### What is and is not deterministic

Only the enforcement logic (parsing, policy, hashing, signing, retries, state
transitions) is deterministic. The reviewers' semantic judgement is an LLM output and
is not; its quality is measured, not assumed:

```bash
.venv/bin/python scripts/reviewer_stage3.py verify --agent world   # frozen Stage 3 eval check
.venv/bin/python scripts/stage4_review_gate.py --gate world \
    --fixture evals/reviewers/fixtures/world/holdout/WR-H01_frostmarch_clean.json \
    --mode shadow                                            # real reviewer, single gate
.venv/bin/python scripts/run_review_rejection_demo.py        # real reviewer rejection path, evidence/stage4/demo_runs/
.venv/bin/python scripts/stage4_summarize.py runs/<run_id>   # offline run summary
```

New CLI flags: `--review-mode {shadow,enforced}` and `--reference-labels PATH`
(JSON object `gate -> PASS|REVISE|PUNCH_OUT`, compared against reviewer
verdicts in each gate record). `scripts/run_review_evals.py` was retired when
the legacy review contract was removed; Stage 3 reviewer evaluation lives in
`scripts/reviewer_stage3.py`.

## Tests

```bash
.venv/bin/python -m pytest
```

## Workflow evals

```bash
python scripts/run_workflow_evals.py --splits all
```

The eval harness calls a live LLM provider and must be run manually. The
final 12-case evaluation (`workflow-v1.1.0`) was executed on 2026-11-18;
results are recorded in `evidence/success_rate.json`,
`evidence/audit_trail.jsonl`, `evidence/punch_out.md`, and
`evidence/iterations/workflow.md`. The superseded 8-case pre-enforcement
baseline is preserved under `evidence/archive/20261118T081130Z/`.

## Validating and packaging the submission

```bash
python scripts/validate_submission.py   # structural checks R1-R7, exit 1 on failure
python scripts/package_submission.py    # builds ../fictionforge_stage4_submission.zip + .sha256
```

The packager refuses to produce a ZIP unless validation passes.

## Evidence

All measured evidence lives in `evidence/` (success rate, audit trail,
iteration logs, punch-out record). These files record real runs and must not
be edited by hand.
