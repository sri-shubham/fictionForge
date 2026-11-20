# Stage 4 — adversarial-reviewer integration

This directory documents the Stage 4 integration of the Stage 3-selected
adversarial reviewers into the workflow's handoff gates. **The implementer
performed no live model calls** — every check was offline (pytest with
`MockClient`, static verification, hash comparison). `manual_commands.md`
contains the commands a user can run to produce live evidence; `shadow_runs/`
and `demo_runs/` are created by those commands, not by the implementation.

## What was integrated

* `src/fictionforge/guardrails/review.py` — rewritten on the **shared**
  reviewer contract (`fictionforge.guardrails.reviewer_contract`, the same
  code the Stage 3 promptfoo evaluations judged).  The legacy in-module
  contract (`ReviewIssue`/`ReviewVerdict`/`parse_review_response`/`path`
  key) was removed; see `contract_migration.md`.
* `AdversarialReviewer` calls the reviewer model with the Stage 3-selected
  prompts — `prompts/reviewers/world.md` (v3), `characters.md` (v1),
  `storyboard.md` (v3) — byte-identical to the prompt files hashed in
  `evidence/stage3/reviewers/*/prompt_hashes.json`.
* `GateKeeper`/`HandoffHook` (`guardrails/handoff.py`) run, per gate:
  integrity + upstream-approval checks → deterministic revalidation →
  deterministic injection scan → reviewer call → grounding +
  trusted policy decision → gate record → signed approval (passing
  decisions only).  The runner then re-verifies the approval itself.
* Modes: `review.mode: enforced|shadow` (`--review-mode`).  Shadow records
  the `enforced_equivalent_decision` per gate and is loudly labelled
  everywhere — **shadow results are not proof of enforced adversarial
  guardrails**.
* Audit: every event has a `category`; reviewer calls, gate decisions,
  deterministic validations, repeated findings and false-positive
  candidates are all recorded (`audit.jsonl`,
  `gates/false_positive_candidates.jsonl`).
* Scripts: `scripts/stage4_review_gate.py` (single-gate shadow review),
  `scripts/stage4_summarize.py` (offline run summaries),
  `scripts/run_review_rejection_demo.py` (live rejection/punch-out demo;
  adds scenario `C_punch_out`).  `scripts/run_review_evals.py` is a retired
  stub — the legacy contract it measured no longer exists.

## Mode semantics

| | enforced | shadow |
|---|---|---|
| Reviewer runs, everything recorded | yes | yes |
| Reviewer PASS | `APPROVED` + signed approval | `SHADOW_HANDOFF_PERMITTED` + shadow-signed approval |
| Reviewer REVISE / confirmed policy PUNCH_OUT / reviewer error | RETRY / HALT / FAILED_REVIEWER | advisory only (enforced-equivalent recorded) |
| Deterministic validators, integrity/tamper/upstream approvals | block | block (identical) |
| Deterministic injection-scan finding | block | block (treated like REVISE) |
| Approval `enforcement` field | `enforced` | `shadow` (never verifies under an enforced keeper) |

## Qualification status (from Stage 3, unchanged)

The three reviewers are integrated but **are NOT fully Stage 3 qualified**:
all three failed the false-positive hard gate on the holdout (holdout case
pass rates 80/80/70%; holdout critical-issue detection 100%; false-negative
rate 0%; holdout FP rates 20/20/40%).  See
`evidence/stage3/reviewers/SUMMARY.md`.  They are integrated anyway because
the failure mode is a wasted generator retry — never an unsafe handoff —
and deterministic guardrails (validators, injection scan, gate signatures)
do not depend on reviewer judgement.

## Design decisions worth noting

* **One contract.**  The workflow parses reviewer output with the exact
  code evaluated in Stage 3, so a Stage 3 measurement and a Stage 4 gate
  judge the same response the same way.  No parallel contract exists.
* **Fail closed.**  Contract-invalid reviewer output is never re-asked and
  never becomes a pass; reviewer timeouts/provider errors retry at most
  `review.max_attempts` times; REVISE retries share the
  `max_attempts_per_step` budget — no infinite loops.
* **Trusted confirmation of PUNCH_OUT.**  A reviewer PUNCH_OUT is honoured
  only when a critical `POLICY_*` issue's evidence passes deterministic
  grounding *and* is deterministically corroborated (the injection scan
  flags some supplied document, or the quoted evidence itself contains
  punch-out language).  Otherwise it downgrades to REVISE — never PASS,
  never an unearned human escalation; reviewer text alone cannot halt a run.
* **No verdict/approval caching.**  Every gate evaluation re-runs the
  reviewer on the exact artifact; the approval binds artifact hash, input
  hashes, review-record hash, reviewer verdict, prompt hash and
  enforcement mode, and the runner re-verifies before accepting.
* **Nothing is dismissed.**  Ungrounded, out-of-taxonomy and repeated
  findings are recorded as `false_positive_candidates` for human analysis
  but still count as blocking.
