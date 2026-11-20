# FictionForge — Stage 4 Workflow Definition

This document is the standalone definition of the FictionForge Stage 4
workflow.  Everything described here is implemented in the repository; where a
documented requirement is *not* implemented, it is marked **[GAP]** in §10
instead of being described as working.

All paths are repository-relative.

---

## 1. Workflow identity

| Property | Value |
|---|---|
| Workflow name | `fictionforge_story_planning` (declared in `manifest.yaml`) |
| Purpose | Turn a machine-checkable story brief into a validated world, character set, and storyboard through three sequential LLM steps, each guarded by deterministic validation, an adversarial reviewer, and a signed handoff gate. |
| Input | A `StoryBrief` JSON file (`src/fictionforge/models.py::StoryBrief`; example: `examples/story_brief.json`). |
| Final output | A validated run directory `runs/<run_id>/` containing `brief.json`, `world.json`, `characters.json`, `storyboard.json`, `gates/` (review records + signed approvals), `audit.jsonl`, and `summary.json`. |
| Entry point | `runner.py` (thin shim) → `src/fictionforge/runner.py::main()` → `WorkflowRunner`. |
| Configuration | `config/workflow.yaml` (production policy), `evals/workflow.yaml` (workflow evaluation harness config). |
| Workflow-level guardrails | `src/fictionforge/guardrails/validators.py`, `guardrails/review.py`, `guardrails/handoff.py`, `guardrails/punch_out.py`, `guardrails/reviewer_contract.py`. |
| Observability | `src/fictionforge/observability/audit.py` (append-only `audit.jsonl`), `observability/metrics.py`, `observability/consumption.py` + `observability/pricing.py` (ACU cost attribution with labelled `estimated_usd`). |

### The six agents

Three **judged generation steps** (evaluated end-to-end in Stage 3) and three
**adversarial review components** (workflow-level guardrails, also evaluated in
Stage 3 under `evals/reviewers/`).  The reviewers are visible, executable, and
their prompts/evaluations/iteration evidence are part of the submission; they
are *not* hidden inside the generator prompts.

| # | Agent | Role | Prompt | Model (per `config/workflow.yaml`) |
|---|---|---|---|---|
| 1 | World Generation (`world_generation`) | Produces the `World` artifact from the brief. | `prompts/world.md` | `gpt-6-luna-medium` |
| 2 | Character Design (`character_design`) | Produces the `CharacterSet` artifact against the approved world. | `prompts/characters.md` | `gpt-6-luna-medium` |
| 3 | Storyboard Building (`storyboard_building`) | Produces the `Storyboard` artifact against the approved world + characters. | `prompts/storyboard.md` | `gpt-6-luna-medium` |
| 4 | World Reviewer (`world_reviewer`, gate `world`) | Adversarially reviews the candidate `World`; verdict `PASS/REVISE/PUNCH_OUT`. | `prompts/reviewers/world.md` (v7) | `swe-2-medium` |
| 5 | Character Reviewer (`character_reviewer`, gate `characters`) | Adversarially reviews the candidate `CharacterSet` against brief + world. | `prompts/reviewers/characters.md` (v4) | `deepseek-v4-1-flash-1017-high` |
| 6 | Storyboard Reviewer (`storyboard_reviewer`, gate `storyboard`) | Adversarially reviews the candidate `Storyboard` against brief + world + characters. | `prompts/reviewers/storyboard.md` (v10) | `deepseek-v4-1-flash-1017-high` |

Reviewer prompt versions are pinned in
`src/fictionforge/guardrails/review.py::SELECTED_PROMPT_VERSIONS`
(`{"world": "v7", "characters": "v4", "storyboard": "v10"}`), byte-identical to
the prompts hashed in `evidence/stage3/reviewers/*/prompt_hashes.json`.
Reviewer models are deliberately different from the generation model
(`review.model`, `review.models` per-gate overrides).

### Success and failure conditions

| Outcome | `WorkflowStatus` | Exit code | Meaning |
|---|---|---|---|
| Success | `completed` | 0 | All three artifacts validated, reviewed, and approved; final acceptance gate verified all three signed approvals binding the current artifacts and their input hashes. |
| Automated failure | `failed_automated` | 1 | A step exhausted its attempt budget, hit a non-retryable error, or a reviewer/gate component failed closed. Downstream steps never ran. |
| Human escalation | `punch_out_required` | 2 | A policy-reserved condition requires an authorized human decision before the run may continue (see §5). |
| Human denial | `human_denied` | — (terminal) | A signed `deny` decision was recorded; the run is terminal and cannot be resumed. |
| Input/config failure | `failed_automated` | 3 | `WorkflowInputError`: missing/invalid brief, missing run summary, invalid config, unapproved punch-out resume, non-resumable step. |

---

## 2. Workflow graph

The Mermaid graph below mirrors the production execution order in
`WorkflowRunner.run()` and `HandoffHook.run()`.  Rectangles are LLM calls;
rounded boxes are deterministic trusted code; diamonds are decisions.
`load_brief` is deterministic preprocessing — **not** a judged agent.

```mermaid
flowchart TD
    START([Start: --brief PATH]) --> LOAD[[load_brief: parse JSON + validate_brief - deterministic, no model]]
    LOAD -->|valid| B_ART[[brief.json artifact: sha256 + saved]]
    LOAD -->|missing file / bad JSON| INERR[WorkflowInputError]
    LOAD -->|INVALID_STORY_BRIEF| FAIL3[failed_automated, exit 3]
    INERR --> FAIL3

    B_ART --> WGEN{{world_generation LLM call}}
    WGEN --> WPO{Punch-out phrase scan<br/>deterministic}
    WPO -->|bypass language| PO1[punch_out_required, exit 2<br/>GUARDRAIL_BYPASS_ATTEMPT]
    WPO -->|clean| WPARSE{Valid JSON?}
    WPARSE -->|no: INVALID_JSON| WRETRY1{retryable + attempts left?}
    WPARSE -->|yes| WVAL[[validate_world - deterministic]]
    WVAL -->|issues, all retryable| WRETRY1
    WVAL -->|issues, non-retryable or final attempt| WEXH[FAILED_RETRIES_EXHAUSTED<br/>failed_automated, exit 1]
    WVAL -->|clean| WGATE[[world handoff gate - HandoffHook]]

    WRETRY1 -->|attempts < 3| WGEN
    WRETRY1 -->|budget exhausted| WEXH
    WGEN -.->|MODEL_TIMEOUT / retryable provider error| WRETRY1
    WGEN -.->|PROVIDER_CONFIGURATION_ERROR| FAIL1W[failed_automated, exit 1]

    subgraph WG[world gate - deterministic order]
        WG1[[verify artifact + input hashes + upstream approvals]] --> WG2[[re-run validate_world]]
        WG2 -->|fails| WG_RETRY{retryable + attempts left?}
        WG2 -->|ok| WG3[[injection scan + world_reviewer LLM call]]
        WG3 --> WG4[[ground issues + trusted policy decide]]
        WG4 --> WG5[[write gate record world_review.json]]
        WG5 --> WG6{decision}
    end
    WGATE --> WG

    WG_RETRY -->|yes: RETRY| WGEN
    WG_RETRY -->|no: FAILED_RETRIES_EXHAUSTED| WEXH
    WG6 -->|PASS: APPROVED| WG7[[write signed world.approved - HMAC]]
    WG7 --> WG8[[runner re-verifies approval]]
    WG8 -->|verified| CGEN
    WG8 -->|verify fails| PO2[punch_out_required<br/>ARTIFACT_TAMPERED / GATE_APPROVAL_INVALID]
    WG6 -->|REVISE: RETRY| WGEN
    WG6 -->|REVISE on final attempt| WEXH
    WG6 -->|reviewer error: FAILED_REVIEWER| FAIL1W
    WG6 -->|confirmed PUNCH_OUT: HALT_PUNCH_OUT| PO3[punch_out_required, exit 2]
    WG6 -->|unconfirmed PUNCH_OUT<br/>downgraded to REVISE| WRETRY1
    WG6 -->|tamper: HALT_ARTIFACT_TAMPERED| PO2

    CGEN{{character_design LLM call}} -.->|same failure branches as world| CBR[JSON/timeout/validation/retry branches identical in shape]
    CGEN --> CGATE[[characters handoff gate - identical hook, gate characters]]
    CGATE -->|APPROVED + re-verified| SGEN
    CGATE -->|RETRY| CGEN
    CGATE -->|FAILED_REVIEWER / exhausted| FAIL1C[failed_automated, exit 1]
    CGATE -->|HALT_*| PO4[punch_out_required, exit 2]

    SGEN{{storyboard_building LLM call}} --> SGATE[[storyboard handoff gate - identical hook, gate storyboard]]
    SGATE -->|APPROVED + re-verified| FINAL[[final acceptance gate: verify_approval for world + characters + storyboard with input hashes]]
    SGATE -->|RETRY| SGEN
    SGATE -->|FAILED_REVIEWER / exhausted| FAIL1S[failed_automated, exit 1]
    SGATE -->|HALT_*| PO5[punch_out_required, exit 2]

    FINAL -->|all three verified| DONE([completed, exit 0<br/>world.json + characters.json + storyboard.json + summary.json])
    FINAL -->|any approval invalid| PO6[punch_out_required, exit 2]

    PO1 & PO3 & PO4 & PO5 & PO6 --> HUMAN{Signed human decision<br/>--decide approve|deny}
    HUMAN -->|approve + valid signed decision<br/>--resume RUN| RESUME[[resume: verify decision signature + context, reload artifacts, re-verify / re-review upstream approvals, continue from failed step]]
    HUMAN -->|deny recorded| DENY[human_denied<br/>terminal, exit 3 on resume attempt]
    HUMAN -->|no / invalid decision| DENY2[PUNCH_OUT_NOT_APPROVED<br/>run stays halted, exit 3]
    RESUME --> WGEN
```

Notes on fidelity to the implementation:

* The reviewer **always** runs inside its gate once deterministic validation
  passes (enforced and shadow mode).  Only the *consequences* differ by mode:
  in `shadow` the verdict is advisory (`SHADOW_HANDOFF_PERMITTED`) while
  deterministic checks still block.
* All retry kinds — validator issues, `REVIEW_REVISE`, invalid JSON, retryable
  provider errors — share one counter: `max_attempts_per_step` (default 3).
  Reviewer-call attempts are bounded separately by `review.max_attempts`
  (default 2).
* `StepStatus.RETRYING` exists in the enum but is never assigned; a step ends
  only as `passed` or `failed`.  Attempts are recorded `passed`/`failed`.

---

## 3. Handoff contracts

Artifacts are immutable `Artifact` records (`src/fictionforge/runner.py`):
`step_id`, `artifact_type`, `canonical_json` (sorted-key compact JSON),
`sha256`, `prompt_version`, `validation_result`, `model_class`.
`Artifact.verify()` re-hashes the payload before every use.

| Boundary | Input | Output | Deterministic validation | Reviewer | Gate |
|---|---|---|---|---|---|
| Brief → World | `StoryBrief` (validated at `load_brief`) | `World` | `validate_brief`, then `validate_world(data, brief)` | `world_reviewer` (context: brief) | `world` |
| World → Characters | approved `World` + `StoryBrief` | `CharacterSet` | `validate_characters(data, world, brief)` | `character_reviewer` (context: brief, world) | `characters` |
| Characters → Storyboard | approved `World` + `CharacterSet` + `StoryBrief` | `Storyboard` | `validate_storyboard(data, world, characters, brief)` | `storyboard_reviewer` (context: brief, world, characters) | `storyboard` |
| Storyboard → Output | all three approved artifacts | run directory | final `verify_approval` on all three gates **with** `input_artifact_hashes` | — | final acceptance gate |

### Contract mechanics

* **Artifact identity.** Every artifact is canonical JSON hashed with
  SHA-256.  Downstream steps re-hash their declared inputs before each attempt
  (`input_artifact_immutability` policy); a mismatch raises
  `PunchOutError(ARTIFACT_TAMPERED)`.
* **Schema validation.** `jsonschema` Draft-2020-12 validators generated from
  the Pydantic models plus referential/semantic checks in
  `guardrails/validators.py`: prefixed entity IDs (`wld_/loc_/fac_/rul_/evt_/
  cnf_/chr_/rel_/act_/scn_`), referential integrity (locations, factions,
  characters, scenes), uniqueness, brief-constraint directives
  (`forbid:`, `require:`, `min_locations:`, `max_locations:`, `location_count`),
  `world_id` matching, protagonist presence, relationship sanity, narrative
  phase coverage/order, and acyclic backward-only scene dependencies.
* **Reviewer verdict validation.** Reviewer output is untrusted:
  `parse_reviewer_response` accepts exactly one bare JSON object (no fences,
  no unknown/duplicate keys), enforces verdict/issue consistency (`PASS`
  cannot carry critical/major issues; `REVISE` requires ≥1; `PUNCH_OUT`
  requires a critical `POLICY_*` issue), and rejects text claiming approval
  authority.  Every issue is then *grounded* against the actual documents
  (`ground_issue`) and tagged with taxonomy membership
  (`ISSUE_TAXONOMY`); ungrounded/unknown findings stay blocking and are logged
  as `false_positive_candidates` — never silently dismissed.
* **HMAC-bound gate approval.** On a passing decision, trusted code
  (`GateKeeper.write_approval`, "runner" only) writes
  `gates/<gate>.approved`, an HMAC-SHA256-signed payload binding `run_id`,
  `gate`, `artifact_sha256`, `input_artifact_hashes`,
  `validation_result_sha256`, `review_record_sha256`, `reviewer_model`,
  `reviewer_verdict`, `reviewer_prompt_sha256`, `enforcement`, `verdict`, and
  `issued_by: "runner"`.  The key lives only in memory (or in the
  `FICTIONFORGE_GATE_KEY` env var, hex); it is never written to disk, so model
  output cannot mint an approval.
* **Downstream execution requirements.** Before a downstream LLM call starts,
  the runner verifies every gated input's approval (`UPSTREAM_GATES =
  {"world": "world", "characters": "characters"}`), and the runner
  *re-verifies* the approval the hook claims to have written before accepting
  the handoff (fail closed).  After `storyboard_building` passes, the final
  acceptance gate re-verifies all three approvals *including* input-hash
  binding — no verified approvals, no `completed`.

### Accept / reject / regenerate / escalate

| Gate condition | Decision | Effect |
|---|---|---|
| Clean artifact + reviewer `PASS`, no blocking findings | `APPROVED` (`SHADOW_HANDOFF_PERMITTED` in shadow) | Signed approval written; artifact saved; next step may run |
| Reviewer `REVISE`, or deterministic injection-scan finding, attempts left | `RETRY` (`REVIEW_REVISE`) | Generator re-run with structured issues injected as retry feedback data (attempts 2+: "## Retry feedback") |
| `REVISE`/validation failure on final attempt | `FAILED_RETRIES_EXHAUSTED` | Step failed; workflow `failed_automated` |
| Reviewer timeout/provider error after `review.max_attempts`, or all-invalid responses | `FAILED_REVIEWER` (`REVIEWER_TIMEOUT` / `REVIEWER_PROVIDER_ERROR` / `REVIEWER_INVALID_RESPONSE`) | Fail closed; generator is *not* regenerated |
| Confirmed reviewer `PUNCH_OUT` | `HALT_PUNCH_OUT` | `punch_out_required`; human decision required |
| Unconfirmed reviewer `PUNCH_OUT` | downgraded to `REVISE` | Never PASS, never an unearned escalation |
| Hash mismatch / stale or mutated review record | `HALT_ARTIFACT_TAMPERED` | `punch_out_required` |
| Missing/unsigned/forged approval | `HALT_GATE_APPROVAL_INVALID` | `punch_out_required`; downstream never called |
| Approval write fails | `FAILED_REVIEWER` (`GATE_WRITE_FAILED`) | `failed_automated` |

---

## 4. Branching logic — transition table

Actual enums: `WorkflowStatus` = `pending | running | completed |
failed_automated | punch_out_required | human_denied`; `StepStatus` = `pending |
running | passed | retrying | failed` (`retrying` is defined but unused —
transitions are internal to `_run_llm_step`).  Gate decisions: `DECISIONS` in
`guardrails/handoff.py`.

| Current state | Trigger | Guard condition | Action | Next state |
|---|---|---|---|---|
| `pending` | `run()` invoked | — | log `workflow_start`; status → `running` | `running` |
| `running` / `load_brief` | brief file missing / not JSON | — | `WorkflowInputError` (`MISSING_BRIEF_FILE`, `INVALID_STORY_BRIEF`) | `failed_automated` (exit 3) |
| `running` / `load_brief` | `validate_brief` issues | deterministic | record failed attempt, audit events | `failed_automated` (exit 3) |
| `running` / `load_brief` | brief valid | — | save `brief.json` artifact + sha256 | continue to `world_generation` |
| `running` / LLM step | input artifact hash mismatch | `sha256(canonical) != artifact.sha256` | `PunchOutError(ARTIFACT_TAMPERED)` | `punch_out_required` (exit 2) |
| `running` / LLM step | upstream gate approval missing/forged/stale | `verify_approval` raises | `PunchOutError(ARTIFACT_TAMPERED|GATE_APPROVAL_INVALID)` + `halt_<step>.json` | `punch_out_required` (exit 2) |
| `running` / LLM step | provider exception | `is_retryable(code)` and attempt < 3 | log `retry_decision`, retry same step | same step, attempt n+1 |
| `running` / LLM step | provider exception | non-retryable (`PROVIDER_CONFIGURATION_ERROR`) or final attempt | record `StepError` | `failed_automated` (exit 1 or 3) |
| `running` / LLM step | output contains bypass language | `scan_output_for_punch_outs` matches | `PunchOutError(GUARDRAIL_BYPASS_ATTEMPT)` | `punch_out_required` (exit 2) |
| `running` / LLM step | output not parseable JSON | `INVALID_JSON` retryable, attempts left | retry with no feedback block | same step, attempt n+1 |
| `running` / LLM step | validator issues | **all** issue codes retryable and attempt < 3 | retry with validator feedback appended | same step, attempt n+1 |
| `running` / LLM step | validator issues | any non-retryable code, or final attempt | step `failed` | `failed_automated` (exit 1) |
| `running` / gate | deterministic revalidation fails | all retryable and attempt < 3 | `RETRY`, kind `validation` | same step, attempt n+1 |
| `running` / gate | injection-scan or reviewer `REVISE` | attempt < `max_attempts_per_step` | `RETRY` (`REVIEW_REVISE`), reviewer issues as feedback | same step, attempt n+1 |
| `running` / gate | rejection on final attempt | — | `FAILED_RETRIES_EXHAUSTED` (`REVIEW_RETRIES_EXHAUSTED`) | `failed_automated` (exit 1) |
| `running` / gate | reviewer call fails closed | all attempts timeout/provider/invalid | `FAILED_REVIEWER` | `failed_automated` (exit 1) |
| `running` / gate | reviewer `PUNCH_OUT` | grounded critical `POLICY_*` issue **and** deterministic corroboration | `HALT_PUNCH_OUT` (`REVIEW_PUNCH_OUT`) | `punch_out_required` (exit 2) |
| `running` / gate | reviewer `PUNCH_OUT` | not confirmed | downgrade to `REVISE` | same as REVISE row |
| `running` / gate | integrity/tamper finding | — | `HALT_ARTIFACT_TAMPERED` / `HALT_GATE_APPROVAL_INVALID` | `punch_out_required` (exit 2) |
| `running` / gate | `PASS`, no blocking findings | — | gate record + signed approval + runner re-verify | next step |
| `running` / final gate | all 3 approvals verify with input hashes | `verify_approval` × 3 | — | `completed` (exit 0) |
| `running` / final gate | any approval invalid | — | `PunchOutError` + halt record | `punch_out_required` (exit 2) |
| `punch_out_required` | `--decisions --run-id` (inspect) | — | print pending + recorded decisions; no state change | unchanged |
| `punch_out_required` | `--decide approve\|deny --punch-out ID --approver NAME` | pending exists, no prior decision, approver in `human_approvals.approvers`, reason approvable (for approve) | write signed `punch_outs/<id>.decision.json` + `human_decision` audit event; deny → status `human_denied` | `punch_out_required` (approve) / `human_denied` (deny) |
| `punch_out_required` | `resume()` without a decision | pending decision file missing | `WorkflowInputError(PUNCH_OUT_NOT_APPROVED)` + `human_decision(authorized=false)` event | stays halted (exit 3) |
| `punch_out_required` | `resume()` with a decision | signature/run-id/punch-out-id/approver/context-hash all verify | mark record `approved` (verified), reload artifacts, re-verify/re-review upstream approvals once | `running` from failed step (budget cumulative) |
| `punch_out_required` | `resume()` with bad decision | signature invalid, wrong run/punch-out, unlisted approver, `--approved-by` mismatch, stale `context_hash`, or deny recorded | `WorkflowInputError` (`DECISION_*`, `APPROVER_*`, `HUMAN_DENIED`, `PUNCH_OUT_NOT_APPROVABLE`) + audit event | stays halted (exit 3) |
| `punch_out_required` (security halt) | any approval attempt | reason `artifact_tampered` / `gate_approval_invalid` / `unknown` | `PUNCH_OUT_NOT_APPROVABLE` at `--decide` and re-checked at `resume()` | terminal; requires a new run |
| `human_denied` | `resume()` | — | `WorkflowInputError(HUMAN_DENIED)` | terminal (exit 3) |
| `failed_automated` | `resume()` | failed step ∈ `RESUMABLE_STEPS`; saved artifacts present; **no unresolved pending decisions** | reload artifacts, re-verify/re-review upstream approvals once | `running` from failed step |
| `failed_automated` | `resume()` | unresolved pending decision files exist | same authorization checks as `punch_out_required` (summary-status edits cannot downgrade a halt) | `running` or stays halted |
| `failed_automated` | `resume()` | failed step `load_brief` | `WorkflowInputError(NON_RESUMABLE_STEP)` | stays failed (exit 3) |
| any | `resume()` on `completed` run | — | `WorkflowInputError(ALREADY_COMPLETED)` | — (exit 3) |

Invalid transitions are prevented structurally, not by convention:

* A step cannot start while a gated input lacks a verified approval.
* `verify_approval` binds run id, gate, artifact hash, input hashes, review
  record hash and enforcement mode — replayed, swapped, or hand-edited
  approvals fail closed.
* `resume()` can only continue from the first non-passed step and only for
  `world_generation | character_design | storyboard_building`; upstream
  artifacts must re-verify or be re-reviewed once.
* `GateKeeper.revoke` deletes any pre-existing sentinel before each gate
  evaluation, so stale approvals cannot be replayed.
* Retry decisions require **every** issue code to be in `retryable_errors`
  (`is_retryable` is fail-closed — unlisted codes are never retried).

### Configured error taxonomy (`config/workflow.yaml`)

Retryable (generation may fix the defect; shared `max_attempts_per_step`
budget — a step retries only when *every* reported code is retryable and the
attempt is not the last):

`SCHEMA_VIOLATION`, `MISSING_REQUIRED_FIELD`, `COUNT_BELOW_MIN`,
`COUNT_ABOVE_MAX`, `DUPLICATE_ID`, `UNKNOWN_LOCATION_REF`,
`UNKNOWN_FACTION_REF`, `UNKNOWN_CHARACTER_REF`, `UNKNOWN_SCENE_REF`,
`BRIEF_LOCATION_COUNT_MISMATCH`, `BRIEF_LOCATIONS_BELOW_MIN`,
`BRIEF_LOCATIONS_ABOVE_MAX`, `BRIEF_FORBIDDEN_TERM`,
`BRIEF_REQUIRED_TERM_MISSING`, `WORLD_ID_MISMATCH`, `SELF_RELATIONSHIP`,
`DUPLICATE_RELATIONSHIP`, `MISSING_PROTAGONIST`, `SELF_DEPENDENCY`,
`FORWARD_DEPENDENCY`, `CYCLIC_DEPENDENCY`, `MISSING_NARRATIVE_PHASE`,
`NARRATIVE_PHASE_ORDER`, `INVALID_JSON`, `MODEL_TIMEOUT`, `REVIEW_REVISE`.

Non-retryable (fail closed immediately):

`BRIEF_CONSTRAINT_MALFORMED`, `POLICY_VIOLATION`,
`PROVIDER_CONFIGURATION_ERROR`, `ARTIFACT_TAMPERED`, `PUNCH_OUT`,
`REVIEWER_TIMEOUT`, `REVIEWER_PROVIDER_ERROR`, `REVIEWER_INVALID_RESPONSE`,
`REVIEW_RETRIES_EXHAUSTED`, `REVIEW_PUNCH_OUT`, `GATE_APPROVAL_INVALID`,
`GATE_WRITE_FAILED`.

---

## 5. Ordinary failures vs. human punch-outs

**Ordinary failures** produce `failed_automated` (exit 1) or a config/input
exit 3.  They are the workflow doing its job; no human decision is required:

* `INVALID_JSON` — malformed model output (retryable within budget).
* Validator codes (`SCHEMA_VIOLATION`, `UNKNOWN_*_REF`, `CYCLIC_DEPENDENCY`,
  brief-constraint codes, …) — retryable only when **all** reported codes are
  in `retryable_errors`.
* Reviewer `REVISE` — bounded regeneration (shared attempt budget).
* `MODEL_TIMEOUT` / retryable `LLM_PROVIDER_ERROR` — bounded retry; exhausted →
  `failed_automated`.
* `REVIEWER_*` failures and `GATE_WRITE_FAILED` — fail closed, non-retryable.
* `REVIEW_RETRIES_EXHAUSTED` — the step's budget is spent; downstream stops.

**Human punch-outs** produce `punch_out_required` (exit 2) plus a
`PunchOutRecord` (`run_id`, `step`, `reason`, `policy`, `evidence`,
`timestamp`, `approved`, `approved_by`) logged as a `punch_out` audit event.
They are reserved conditions, not model failure modes:

| `PunchOutReason` | Trigger (trusted code) | Policy | Human-approvable? |
|---|---|---|---|
| `guardrail_bypass_attempt` | Generator output contains bypass/self-approval/`policy exception`/`human approval required` phrases (`check_output_for_punch_outs`) | `llm_output_must_not_override_workflow_controls` | **Yes** — the offending output is discarded; approval authorizes a fresh attempt |
| `reviewer_policy_punch_out` | Reviewer `PUNCH_OUT` confirmed by trusted policy (`decide` → `_punch_out_confirmed`) | `gate_approval_required_for_downstream_steps` | **Yes** |
| `artifact_tampered` | Input artifact hash mismatch; approval binding mismatch (`RUN_MISMATCH`, `ARTIFACT_HASH_MISMATCH`, `INPUT_HASH_MISMATCH`, `REVIEW_RECORD_MISMATCH`) | `input_artifact_immutability` / gate policies / `final_acceptance_gate` | **No** — security halt; integrity state is untrusted, start a new run |
| `gate_approval_invalid` | Missing, unsigned, forged, or wrong-mode approval | `gate_approval_required_for_downstream_steps` / `final_acceptance_gate` | **No** — security halt |
| `policy_exception_requested`, `unsafe_operation`, `human_approval_required` | Reserved for future policies (`raise_punch_out`); currently untriggered | — | **Yes** (by design, once triggered) |
| `unknown` | Fallback reason | — | **No** |

Approvability is enforced twice: `--decide approve` refuses non-approvable
reasons (`PUNCH_OUT_NOT_APPROVABLE`), and `resume()` re-checks the pending
record's reason so even a correctly signed approval cannot rescue a security
halt.  `is_approvable` / `APPROVABLE_REASONS` in `guardrails/punch_out.py`
is the single source of truth.

### Approval and resume mechanism

Every punch-out persists a pending decision file
`runs/<run_id>/punch_outs/<punch_out_id>.pending.json` (stable ID
`po-<run_id>-<seq>`, step, reason, evidence, and a `context_hash` binding the
artifact files present in the run directory at halt time).  A human records a
decision with:

```bash
python runner.py --decisions --run-id RUN_ID                      # inspect pending decisions
python runner.py --decide approve --run-id RUN_ID \
    --punch-out PUNCH_OUT_ID --approver stage4-operator           # or: --decide deny
```

`--decide` writes an immutable, HMAC-SHA256-signed `<punch_out_id>.decision.json`
binding the run ID, punch-out ID, decision, approver and context hash, logs a
`human_decision` audit event, and (for `deny`) moves `summary.json` to the
terminal `human_denied` status.  The signing key comes from
`FICTIONFORGE_APPROVAL_KEY`, the configured `human_approvals.key_file`, or the
auto-generated `config/approval_signing.key` (mode 0600, never logged or
committed).  Approvers must be in the `human_approvals.approvers` allowlist in
`config/workflow.yaml`.  Decisions are write-once (`ALREADY_DECIDED`).

`resume()` (`python runner.py --resume RUN_ID`) then:

1. Refuses `human_denied` and `completed` runs outright.
2. Verifies **every** unresolved pending decision: valid signature, matching
   run ID and punch-out ID, `approve` verdict, allowlisted approver,
   `context_hash` equal to the *current* artifact state, and an approvable
   reason.  Any failure logs a `human_decision` (`authorized: false`) event
   and raises `WorkflowInputError` (exit 3).  `--approved-by NAME` is a
   consistency check on the decision's attested approver — it is **not** an
   authorization credential; a free-text name alone cannot resume a run.
3. Marks the punch-out records `approved`/`approved_by` from the verified
   decisions (persisted on finalize), reloads saved artifacts, re-verifies
   upstream approvals (re-running validation + reviewer once when the
   ephemeral gate key changed), logs a `resume` event with
   `authorized_decisions`, and continues from the failed step with the
   remaining cumulative attempt budget.
4. Approval never skips validators, reviewers or gates — the interrupted step
   re-runs end-to-end.

Authorization checks are driven by the pending-decision files **and** the
summary status, so editing `summary.json` alone (e.g. relabelling a halt as
`failed_automated`) cannot bypass the human-decision requirement.

* **[Limitation — attested, not authenticated identity]** Approver identity
  is a string in an allowlist: authorization = possession of the local
  signing key + allowlist membership.  Anyone with write access to the key
  file (or `FICTIONFORGE_APPROVAL_KEY`) can mint a decision, and anyone with
  write access to the run directory can delete decision files (the audit
  trail would show the gap).  This is a *local* boundary suitable for a
  single-operator environment; a real deployment should replace it with a
  verified identity channel (signed approval service, hardware-backed keys).

---

## 6. Automated guardrail stack

### Layer 1 — Deterministic

* Pydantic models (`models.py`, `extra="forbid"`, strict) + exported JSON
  Schemas (`schemas/*.schema.json`) + `jsonschema` validation.
* Referential integrity and semantic checks (`validators.py`): ID formats,
  uniqueness, cross-references, brief directives, graph acyclicity,
  `world_id` matching.
* State validation: step order is fixed in `run()`; statuses and exit codes
  are code-controlled; `is_retryable` fails closed on unknown codes.
* Artifact integrity: canonical JSON + SHA-256; `Artifact.verify()` before
  every use; atomic writes for gate files.

### Layer 2 — Adversarial review

* Three independent reviewer prompts (own model settings, own nonce-tagged
  prompt rendering via `render_review_prompt`), each critiquing an already
  schema-valid artifact with read-only upstream context.
* Structured verdicts on the shared `reviewer_contract` — the same parser the
  Stage 3 reviewer evals judged.
* Evidence-backed findings: each issue must quote verbatim evidence;
  `ground_issue` verifies the quote exists under the cited path.
* Reviewer failure handling: bounded attempts (`review.max_attempts = 2`) with
  a fresh nonce per attempt covering timeouts, provider errors, and
  contract-invalid/empty responses; all-failed → `FAILED_REVIEWER`, never a
  pass.
* Reviewer semantic quality is **measured, not assumed** — see
  `evals/reviewers/`, `evidence/iterations/reviewers/`, and the known
  limitation below.

### Layer 3 — Handoff enforcement

* Gate records `gates/<gate>_review.json` + `gates/history/<gate>_attempt_N.json`
  are written before any approval; approvals bind the record's hash.
* Signed sentinels `gates/<gate>.approved` (HMAC, ephemeral key) are the only
  acceptance currency; the runner re-verifies after issue and before every
  downstream/final use.
* Reviewer decisions enforced by `decide()`: `PASS` cannot survive a blocking
  finding; `PUNCH_OUT` requires deterministic confirmation; nothing is
  dismissed — ungrounded/out-of-taxonomy/repeated findings are logged as
  `false_positive_candidates` and `repeated_findings` but still block.
* No verdict or approval caching: every regenerated artifact is revalidated,
  re-reviewed, and re-gated.

### Layer 4 — Human escalation

* Deterministic phrase scan of generator output
  (`check_output_for_punch_outs`).
* Confirmed reviewer policy punch-outs (§5).
* Tamper/forgery halts (artifact hashes, approval signatures).
* Audited resume requiring `--approved-by` (see the identity limitation, §5).

**Deterministic vs. probabilistic:** layers 1, 3 (enforcement), and the
punch-out scanners are fully deterministic trusted code.  Only the reviewer
verdicts (layer 2) are probabilistic model judgements — and they are treated
as untrusted evidence that trusted code parses, grounds, corroborates, and
can downgrade but never upgrade.

**Review modes.** `review.mode: enforced` (default) gates handoffs as above.
`shadow` runs the reviewer and records everything (including
`enforced_equivalent_decision`) but never lets a verdict block; deterministic
layers still block identically.  Shadow artifacts are loudly labelled and are
**not** evidence of enforced adversarial guardrails; a shadow approval never
verifies under an enforced keeper.  `--no-review` disables reviewers entirely
(explicit operator choice, recorded in `summary.json`).

---

## 7. Workflow-level evaluation definition

Workflow-level evaluation is defined in `evals/workflow.yaml` (consumed by
`scripts/run_workflow_evals.py`) and documented criterion-by-criterion there
under `criteria:`.  The dataset is `evals/fixtures/workflow/` (12 versioned
cases: dev/holdout × completed/rejected/punch_out expectations).  Evidence
artifacts are `evidence/success_rate.json`, `evidence/audit_trail.jsonl`,
`evidence/punch_out.md`, and `evidence/iterations/workflow.md`.

Seven criteria are defined: end-to-end narrative quality, handoff correctness,
reviewer gate enforcement, branching/retry correctness, human escalation
correctness, execution reliability, and audit completeness + cost attribution.
Each has a purpose, inputs, measurement method, expected behavior, explicit
pass/fail threshold, and evidence artifact — see `evals/workflow.yaml`.

Criteria 2–7 have deterministic offline coverage (`pytest`; see §11); criteria
1 and parts of 3 and 6 additionally require the live harness
(`scripts/run_workflow_evals.py --splits all`), which **must be run manually**
— it invokes real models.

---

## 8. Workflow-level iteration evidence

`evidence/iterations/workflow.md` records:

* The baseline architecture and config (dataset `workflow-v1.0.0`, prompt
  hashes, runner version `0.1.0`, model, attempt budget).
* The baseline measured run (8 cases: 6/6 eligible completed, end-to-end
  success rate 1.0, first-pass 0.6667, 1 expected punch-out, per-agent failure
  breakdown).
* Implementation changes made since (per-gate reviewer model split,
  contract-slip re-ask, prompt-version bookkeeping fix).
* The final measured end-to-end evaluation *with enforced reviewer
  gates* (dataset `workflow-v1.1.0`, 12 cases, recorded 2026-11-18 in
  `evidence/success_rate.json` and appended to
  `evidence/iterations/workflow.md`): expected-outcome success 12/12,
  storyboard completion 6/6, policy enforcement 5/5, 1 expected brief
  rejection.

No historical measurements were fabricated for this documentation; the
superseded 8-case baseline figures are preserved verbatim under
`evidence/archive/20261118T081130Z/` (the live `evidence/success_rate.json`
now holds the final 12-case report).

---

## 9. Reproducibility

All paths below are repository-relative; run from the repository root.

```bash
# Install (Python >= 3.12)
python -m venv .venv && .venv/bin/pip install -e '.[dev]'

# Configuration — config/workflow.yaml
#   workflow.max_attempts_per_step: 3   workflow.retryable_errors / non_retryable_errors
#   provider: devin | ollama           model: gpt-6-luna-medium
#   review.enabled: true               review.mode: enforced | shadow
#   review.model / review.models       review.max_attempts: 2
#   cost.acu_usd_rate: 1.25            output_dir: runs
#   human_approvals.approvers: [stage4-operator]
#   human_approvals.key_file (optional; FICTIONFORGE_APPROVAL_KEY hex env var overrides)

# Manual workflow execution (LIVE models — run these yourself)
python runner.py --brief examples/story_brief.json
python runner.py --brief examples/story_brief.json --review-mode shadow
python runner.py --brief examples/story_brief.json --provider ollama --model llama3.1

# Human punch-out decisions (no model calls)
python runner.py --decisions --run-id <RUN_ID>
python runner.py --decide approve --run-id <RUN_ID> --punch-out <PUNCH_OUT_ID> --approver stage4-operator
python runner.py --decide deny    --run-id <RUN_ID> --punch-out <PUNCH_OUT_ID> --approver stage4-operator

# Resume a halted run (requires a valid signed decision for PUNCH_OUT runs)
python runner.py --resume <RUN_ID> --approved-by stage4-operator

# Offline verification (no model calls)
python -m pytest -q
python scripts/validate_submission.py
python scripts/stage4_summarize.py runs/<run_id>

# Workflow-level evaluation (LIVE models — manual)
python scripts/run_workflow_evals.py --splits all
```

| Asset | Path |
|---|---|
| Per-run outputs | `runs/<run_id>/` (`brief.json`, `world.json`, `characters.json`, `storyboard.json`, `summary.json`, `attempts/`) |
| Gate records + approvals | `runs/<run_id>/gates/` (`<gate>_review.json`, `<gate>.approved`, `history/`, `halt_<step>.json`, `false_positive_candidates.jsonl`) |
| Audit trail | `runs/<run_id>/audit.jsonl`; aggregated eval trail `evidence/audit_trail.jsonl` |
| Session exports | `runs/<run_id>/session_exports/` (`inv-*.atif.json`, Devin CLI session/ACU accounting) |
| Pricing snapshots | `data/pricing/snapshots/` (immutable ACU→USD snapshots for `estimated_usd` labels) |
| Eval fixtures | `evals/fixtures/workflow/{dev,holdout}/` + `manifest.json` |

`FICTIONFORGE_GATE_KEY` (hex) optionally pins the gate HMAC key across
processes; without it an ephemeral random key is used and `resume()`
re-reviews upstream artifacts once.  `FICTIONFORGE_APPROVAL_KEY` (hex)
supplies the human-decision signing key; otherwise
`config/approval_signing.key` is auto-generated with mode 0600 (a `.key`
file — excluded from the submission package).  `config/approval_signing.key`
must not be committed.

---

## 10. Gaps and limitations

| # | Severity | Gap | Location |
|---|---|---|---|
| 1 | security | Approver identity is attested, not authenticated: authorization = possession of the local signing key + allowlist membership. A filesystem attacker can delete (not forge) decision files; the audit trail would show the gap. Suitable for a single-operator environment only. | `src/fictionforge/guardrails/punch_out.py`, `config/workflow.yaml` |
| 2 | medium | `workflow.stop_on_failure` is parsed (`config.py`) but never consulted; the runner always stops on the first failed step. Dead config option — either implement or remove. | `src/fictionforge/config.py`, `runner.py` |
| 3 | low | `StepStatus.RETRYING` is defined but never assigned; retry state exists only implicitly inside `_run_llm_step`. | `src/fictionforge/runner.py` |
| 4 | low | `resume()` marks the run `completed` without re-running the explicit final-acceptance loop used by `run()` (each gate approval is still freshly written/verified during the resumed steps; no functional hole, but the check is asymmetric). | `src/fictionforge/runner.py::resume` |
| 5 | docs (resolved) | `README.md` previously claimed an invalid reviewer response "fails closed immediately (no re-ask)"; corrected — since 2026-11-17 the code re-asks contract-invalid/empty responses once within `review.max_attempts` (fresh nonce) and the README now documents this. | `README.md` vs `guardrails/review.py::AdversarialReviewer.review` |
| 6 | certification | Reviewer classification ambiguity: the three reviewers are declared as manifest `steps` with prompts/evals/logs (not hidden under `not_judged`). If the official certification spec intends `steps` to mean judged generation steps only, this should be clarified — reviewer evidence is fully present either way and is NOT treated as unmeasured. | `manifest.yaml` |
| 7 | certification | Reviewers are integrated but NOT fully Stage-3 qualified (holdout FP hard-gate failure, 20/20/40%). Their failure mode is a wasted generator retry, not an unsafe handoff; deterministic guardrails do not depend on reviewer judgement. | `evidence/stage3/reviewers/SUMMARY.md`, `evidence/stage4/README.md` |
| 8 | resolved | Measured end-to-end evaluation under enforced reviewer gates now exists: the final 12-case `workflow-v1.1.0` run recorded 2026-11-18 (expected-outcome success 12/12; see §8). The superseded pre-enforcement 8-case baseline is preserved under `evidence/archive/20261118T081130Z/`. | `evidence/success_rate.json`, `evidence/iterations/workflow.md` |
| 9 | pending | No Stage-4 examination/feedback document exists in the repository; nothing was found to incorporate. | repo |
| 10 | config | `evidence/iterations/workflow.md` and `evidence/success_rate.json` contain an absolute machine-local config path (the absolute form of `config/workflow.yaml` on the recording machine) written by the harness. Preserved as historical evidence; active configs and all docs use repository-relative paths. | evidence files |
