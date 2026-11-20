"""Deterministic handoff-gate enforcement for adversarial review.

A *gate* binds an accepted artifact to the review record that approved it.
Only trusted runner code (this module) writes ``<gate>.approved`` files;
each approval is HMAC-signed with an ephemeral, in-memory key so neither
the generator nor the reviewer model can mint one.  Downstream steps call
:meth:`GateKeeper.verify_approval` before consuming an upstream gated
artifact, and the final acceptance gate must verify before a run can be
marked COMPLETED.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fictionforge.guardrails.punch_out import PunchOutReason, PunchOutRecord
from fictionforge.guardrails.reviewer_contract import ReviewerIssue
from fictionforge.guardrails.review import (
    SELECTED_PROMPT_VERSIONS,
    AdversarialReviewer,
    RepeatTracker,
    evaluate_review,
    false_positive_candidates,
    issue_to_dict,
)
from fictionforge.guardrails.validators import ValidationIssue
from fictionforge.observability.audit import AuditLogger
from fictionforge.observability.consumption import cost_details_for_invocation

# Input-artifact names that are themselves gated artifacts.
UPSTREAM_GATES: dict[str, str] = {"world": "world", "characters": "characters"}

GATE_WRITE_FAILED = "GATE_WRITE_FAILED"
REVIEW_REVISE = "REVIEW_REVISE"
REVIEW_RETRIES_EXHAUSTED = "REVIEW_RETRIES_EXHAUSTED"
REVIEW_PUNCH_OUT = "REVIEW_PUNCH_OUT"

# Gate decisions persisted in <gate>_review.json.
DECISIONS = (
    "APPROVED",
    "SHADOW_HANDOFF_PERMITTED",
    "RETRY",
    "FAILED_REVIEWER",
    "FAILED_RETRIES_EXHAUSTED",
    "HALT_PUNCH_OUT",
    "HALT_ARTIFACT_TAMPERED",
    "HALT_GATE_APPROVAL_INVALID",
)


def _canonical(data: Any) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _walk_strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v)


class GateApprovalError(Exception):
    """A ``<gate>.approved`` file is missing, forged, or stale."""

    MISSING = "MISSING_APPROVAL"
    UNPARSEABLE = "UNPARSEABLE_APPROVAL"
    FORGED = "FORGED_SIGNATURE"
    RUN_MISMATCH = "RUN_MISMATCH"
    ARTIFACT_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    INPUT_MISMATCH = "INPUT_HASH_MISMATCH"
    RECORD_MISMATCH = "REVIEW_RECORD_MISMATCH"
    NOT_APPROVED = "REVIEW_NOT_APPROVED"

    # Codes meaning "the approved state no longer matches what exists now".
    TAMPER_CODES = frozenset(
        {"RUN_MISMATCH", "ARTIFACT_HASH_MISMATCH", "INPUT_HASH_MISMATCH", "REVIEW_RECORD_MISMATCH"}
    )

    def __init__(self, code: str, detail: str, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.evidence = evidence or {}

    @property
    def is_tamper(self) -> bool:
        return self.code in self.TAMPER_CODES


class GateKeeper:
    """Owns all gate-file reads/writes for a single run.

    The HMAC key lives only in memory; it is never written to disk, so a
    model with filesystem access cannot mint a valid approval.
    """

    def __init__(self, gates_dir: Path, run_id: str, key: bytes, mode: str = "enforced") -> None:
        self.gates_dir = Path(gates_dir)
        self.key = key
        self.run_id = run_id
        self.mode = mode
        self.gates_dir.mkdir(parents=True, exist_ok=True)
        (self.gates_dir / "history").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Low-level primitives
    # ------------------------------------------------------------------

    @staticmethod
    def atomic_write(path: Path, data: bytes) -> None:
        """Write ``data`` to ``path`` atomically; never leave temp files."""
        path = Path(path)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def revoke(self, gate: str) -> None:
        """Delete a stale or planted ``<gate>.approved`` sentinel."""
        try:
            (self.gates_dir / f"{gate}.approved").unlink()
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------
    # Records and approvals
    # ------------------------------------------------------------------

    def review_record_path(self, gate: str) -> Path:
        return self.gates_dir / f"{gate}_review.json"

    def write_review_record(
        self, gate: str, record: dict[str, Any], attempt: int
    ) -> str:
        """Persist the gate record (latest + per-attempt history); return its sha256."""
        data = _canonical(record)
        self.atomic_write(self.review_record_path(gate), data)
        self.atomic_write(
            self.gates_dir / "history" / f"{gate}_attempt_{attempt}.json", data
        )
        return _sha256(data)

    def write_approval(
        self,
        gate: str,
        *,
        artifact: Any,
        input_artifact_hashes: dict[str, str],
        review_record_sha256: str,
        validation_result: dict[str, Any],
        reviewer_model: str | None,
        step_id: str | None = None,
        verdict: str = "PASS",
        enforcement: str | None = None,
        reviewer_verdict: str | None = None,
        reviewer_prompt_sha256: str | None = None,
    ) -> Path:
        """Write a signed ``<gate>.approved`` file.  Trusted runner code only."""
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "gate": gate,
            "step_id": step_id or artifact.step_id,
            "artifact_type": artifact.artifact_type,
            "artifact_sha256": artifact.sha256,
            "input_artifact_hashes": dict(input_artifact_hashes),
            "validation_result_sha256": _sha256(_canonical(validation_result)),
            "review_record_sha256": review_record_sha256,
            "reviewer_model": reviewer_model,
            "reviewer_verdict": reviewer_verdict,
            "reviewer_prompt_sha256": reviewer_prompt_sha256,
            "enforcement": enforcement or self.mode,
            "verdict": verdict,
            "approved_at": _utc_now(),
            "issued_by": "runner",
        }
        payload["signature"] = hmac.new(
            self.key, _canonical(payload), hashlib.sha256
        ).hexdigest()
        path = self.gates_dir / f"{gate}.approved"
        self.atomic_write(path, _canonical(payload))
        return path

    def verify_approval(
        self,
        gate: str,
        artifact: Any,
        input_artifact_hashes: dict[str, str] | None = None,
    ) -> None:
        """Raise :class:`GateApprovalError` unless a valid approval binds this artifact.

        ``artifact.verify()`` may raise ``ValueError`` if the artifact payload
        itself no longer matches its hash (tampering).
        """
        E = GateApprovalError
        path = self.gates_dir / f"{gate}.approved"
        if not path.exists():
            raise E(E.MISSING, f"no approval file for gate {gate!r}")
        try:
            data = json.loads(path.read_bytes())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise E(E.UNPARSEABLE, f"approval file for gate {gate!r} is not valid JSON") from exc
        if not isinstance(data, dict):
            raise E(E.UNPARSEABLE, f"approval file for gate {gate!r} is not a JSON object")
        signature = data.pop("signature", None)
        if not isinstance(signature, str):
            raise E(E.FORGED, f"approval file for gate {gate!r} is unsigned")
        expected = hmac.new(self.key, _canonical(data), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise E(E.FORGED, f"approval file for gate {gate!r} has an invalid signature")
        if data.get("run_id") != self.run_id or data.get("gate") != gate:
            raise E(
                E.RUN_MISMATCH,
                f"approval for gate {gate!r} belongs to run/gate "
                f"{data.get('run_id')!r}/{data.get('gate')!r}",
                evidence={"expected_run_id": self.run_id},
            )
        if data.get("enforcement") != self.mode:
            raise E(
                E.NOT_APPROVED,
                f"approval for gate {gate!r} was issued under enforcement "
                f"{data.get('enforcement')!r}, not {self.mode!r}",
                evidence={"approved_enforcement": data.get("enforcement"), "mode": self.mode},
            )
        artifact.verify()
        if str(data.get("artifact_sha256")) != artifact.sha256:
            raise E(
                E.ARTIFACT_MISMATCH,
                f"approval for gate {gate!r} binds a different artifact",
                evidence={"approved": data.get("artifact_sha256"), "actual": artifact.sha256},
            )
        if input_artifact_hashes is not None and data.get("input_artifact_hashes") != input_artifact_hashes:
            raise E(
                E.INPUT_MISMATCH,
                f"approval for gate {gate!r} binds different input artifacts",
                evidence={
                    "approved": data.get("input_artifact_hashes"),
                    "actual": input_artifact_hashes,
                },
            )
        review_path = self.review_record_path(gate)
        review_bytes = review_path.read_bytes() if review_path.exists() else b""
        if _sha256(review_bytes) != data.get("review_record_sha256"):
            raise E(E.RECORD_MISMATCH, f"review record for gate {gate!r} changed since approval")
        try:
            review = json.loads(review_bytes)
        except json.JSONDecodeError:
            review = {}
        expected_decision = (
            "APPROVED" if self.mode == "enforced" else "SHADOW_HANDOFF_PERMITTED"
        )
        if review.get("gate_decision") != expected_decision:
            raise E(E.NOT_APPROVED, f"review record for gate {gate!r} does not approve this artifact")
        if str(review.get("artifact_sha256")) != artifact.sha256:
            raise E(
                E.RECORD_MISMATCH,
                f"review record for gate {gate!r} binds a different artifact",
                evidence={"record": review.get("artifact_sha256"), "actual": artifact.sha256},
            )
        reviewed_sha = (review.get("reviewer") or {}).get("reviewed_artifact_sha256")
        if reviewed_sha is not None and str(reviewed_sha) != artifact.sha256:
            raise E(
                E.RECORD_MISMATCH,
                f"reviewer verdict for gate {gate!r} binds a different artifact",
                evidence={"reviewed": reviewed_sha, "actual": artifact.sha256},
            )


@dataclass
class StepErrorLike:
    """Minimal duck-typed StepError (avoids importing the runner)."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class GateOutcome:
    """Result of one gate evaluation."""

    decision: str
    outcome: str  # proceed | retry_generator | failed_automated | punch_out
    retry_kind: str | None = None  # "revise" | "validation" when outcome == retry_generator
    feedback_issues: list[ReviewerIssue] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    error: Any = None
    punch_out_record: PunchOutRecord | None = None
    record: dict[str, Any] = field(default_factory=dict)


class HandoffHook:
    """Runs one gate evaluation for a candidate artifact.

    Deterministic order (each step logged in ``hook_steps``):
    verify input/artifact integrity and upstream approvals -> re-run the
    deterministic validator -> deterministic injection scan + adversarial
    reviewer -> policy decision -> always write the gate record -> only on
    APPROVED (enforced) or SHADOW_HANDOFF_PERMITTED (shadow) write the
    signed approval sentinel.

    In ``shadow`` mode the reviewer always runs and everything is recorded,
    but reviewer verdicts/errors never block; the record notes the decision
    enforced mode *would* have taken.  Deterministic pieces (schema
    validators, integrity, the injection scan) still block in shadow mode.
    No verdict or approval is ever cached: every call re-runs the reviewer
    on the exact artifact it is handed.
    """

    def __init__(
        self,
        *,
        keeper: GateKeeper,
        audit: AuditLogger,
        is_retryable: Callable[[str], bool],
        run_id: str,
        reviewers: dict[str, AdversarialReviewer],
        mode: str = "enforced",
        workflow_status: Callable[[], str] = lambda: "running",
        reference_labels: dict[str, str] | None = None,
        require_upstream_approval: bool = True,
        acu_usd_rate: float | None = None,
        pricing_snapshot_id: str | None = None,
    ) -> None:
        self.keeper = keeper
        self.audit = audit
        self.is_retryable = is_retryable
        self.run_id = run_id
        self.reviewers = reviewers
        self.mode = mode
        self._workflow_status = workflow_status
        self.reference_labels = reference_labels or {}
        self.require_upstream_approval = require_upstream_approval
        self.acu_usd_rate = acu_usd_rate
        self.pricing_snapshot_id = pricing_snapshot_id
        self._repeats = RepeatTracker(keeper.gates_dir / "history")

    def run(
        self,
        *,
        step_id: str,
        artifact: Any,
        input_artifacts: dict[str, Any],
        validate_fn: Callable[[], list[ValidationIssue]],
        attempt: int,
        context: dict[str, Any] | None = None,
        final_attempt: bool = False,
    ) -> GateOutcome:
        started = time.monotonic()
        reviewer = self.reviewers[step_id]
        config = reviewer.config
        gate = config.gate
        hook_steps: dict[str, str] = {}
        self.keeper.revoke(gate)

        record: dict[str, Any] = {
            "schema_version": "2.0.0",
            "run_id": self.run_id,
            "step": step_id,
            "gate": gate,
            "generator_attempt": attempt,
            "artifact_type": artifact.artifact_type,
            "artifact_sha256": artifact.sha256,
            "review_mode": self.mode,
            "adversarial_guardrails_enforced": self.mode == "enforced",
            "prompt_version": SELECTED_PROMPT_VERSIONS.get(gate),
            "input_artifact_hashes": {},
            "validation_result": artifact.validation_result,
            "deterministic_artifact_findings": [],
            "reviewer": {
                "reviewer_id": config.reviewer_id,
                "model": config.model,
                "prompt_sha256": reviewer.template_sha256,
                "reviewed_artifact_sha256": None,
                "attempts": [],
                "verdict": None,
                "reason": None,
                "issues": [],
                "unknown_codes": [],
                "error_code": None,
                "latency_s": None,
                "token_usage": None,
            },
            "policy": {
                "effective_verdict": None,
                "note": None,
                "notes": [],
                "punch_out_confirmed": False,
                "blocking_issue_codes": [],
            },
            "repeated_findings": [],
            "false_positive_candidates": [],
            "label_comparison": None,
            "gate_decision": None,
            "outcome": None,
            "error_code": None,
            "started_at": _utc_now(),
            "ended_at": None,
            "duration_s": None,
            "hook_steps": hook_steps,
        }

        retry_decision_map = {
            "proceed": "proceed",
            "retry_generator": "retry",
            "failed_automated": "stop",
            "punch_out": "halt",
        }

        def finish(decision: str, outcome: str, error_code: str | None) -> str:
            record["gate_decision"] = decision
            record["outcome"] = outcome
            record["error_code"] = error_code
            if self.mode == "shadow":
                record["shadow"] = {
                    "enforced_equivalent_decision": record.get(
                        "enforced_equivalent_decision", decision
                    ),
                    "advisory_only": True,
                }
            record["ended_at"] = _utc_now()
            record["duration_s"] = round(time.monotonic() - started, 3)
            sha = self.keeper.write_review_record(gate, record, attempt)
            rev = record["reviewer"]
            findings = [
                {"code": i["code"], "severity": i["severity"]}
                for i in rev["issues"]
            ] or [
                {"code": i["code"], "severity": i["severity"]}
                for i in record["deterministic_artifact_findings"]
            ]
            self.audit.log_gate_decision(
                step=step_id,
                gate=gate,
                attempt=attempt,
                gate_decision=decision,
                outcome=outcome,
                reviewer_verdict=rev["verdict"],
                reviewer_model=rev["model"],
                input_artifact_hash=artifact.sha256,
                artifact_sha256=artifact.sha256,
                review_mode=self.mode,
                validation_status=(record.get("validation_result") or {}).get("status"),
                findings=findings,
                issue_codes=[f["code"] for f in findings],
                retry_decision=retry_decision_map.get(outcome),
                enforced_equivalent_decision=(record.get("shadow") or {}).get(
                    "enforced_equivalent_decision"
                ),
                repeated_findings=len(record["repeated_findings"]),
                false_positive_candidates=len(record["false_positive_candidates"]),
                duration_s=record["duration_s"],
                workflow_status=self._workflow_status(),
            )
            return sha

        # (1) Integrity: candidate hash, input hashes, upstream approvals.
        try:
            artifact.verify()
            input_hashes: dict[str, str] = {}
            for name, art in input_artifacts.items():
                actual = _sha256(art.canonical_json)
                if actual != art.sha256:
                    raise ValueError(
                        f"input artifact {name!r} payload does not match its stored hash"
                    )
                input_hashes[name] = actual
            record["input_artifact_hashes"] = input_hashes
            if self.require_upstream_approval:
                for name, upstream_gate in UPSTREAM_GATES.items():
                    if name in input_artifacts:
                        self.keeper.verify_approval(upstream_gate, input_artifacts[name])
            hook_steps["verify_upstream_integrity"] = "ok"
        except GateApprovalError as exc:
            hook_steps["verify_upstream_integrity"] = f"{exc.code}: {exc.detail}"
            reason = (
                PunchOutReason.ARTIFACT_TAMPERED if exc.is_tamper
                else PunchOutReason.GATE_APPROVAL_INVALID
            )
            finish("HALT_GATE_APPROVAL_INVALID", "punch_out", exc.code)
            return GateOutcome(
                decision="HALT_GATE_APPROVAL_INVALID",
                outcome="punch_out",
                error=StepErrorLike(exc.code, str(exc), exc.evidence),
                punch_out_record=self._halt_record(step_id, gate, reason, str(exc), exc.evidence),
                record=record,
            )
        except ValueError as exc:
            hook_steps["verify_upstream_integrity"] = f"tampered: {exc}"
            finish("HALT_ARTIFACT_TAMPERED", "punch_out", "ARTIFACT_TAMPERED")
            return GateOutcome(
                decision="HALT_ARTIFACT_TAMPERED",
                outcome="punch_out",
                error=StepErrorLike("ARTIFACT_TAMPERED", str(exc)),
                punch_out_record=self._halt_record(
                    step_id, gate, PunchOutReason.ARTIFACT_TAMPERED, str(exc), {}
                ),
                record=record,
            )

        # (2) Deterministic validation, re-run inside the gate (blocks in both modes).
        issues = validate_fn()
        self.audit.log_validation(
            step=step_id,
            attempt=attempt,
            phase="gate_revalidation",
            artifact_sha256=artifact.sha256,
            status="failed" if issues else "passed",
            issue_codes=[str(i.code) for i in issues],
            issues=[i.to_dict() for i in issues],
            workflow_status=self._workflow_status(),
        )
        if issues:
            hook_steps["deterministic_validation"] = f"{len(issues)} issue(s): {issues[0].code}"
            can_retry = all(self.is_retryable(str(i.code)) for i in issues) and not final_attempt
            err = StepErrorLike(
                code=str(issues[0].code),
                message=f"{step_id} validation failed with {len(issues)} issue(s)",
                details={"issues": [i.to_dict() for i in issues]},
            )
            record["validation_result"] = {
                "status": "failed",
                "issues": [i.to_dict() for i in issues],
            }
            decision = "RETRY" if can_retry else "FAILED_RETRIES_EXHAUSTED"
            outcome = "retry_generator" if can_retry else "failed_automated"
            finish(decision, outcome, err.code)
            return GateOutcome(
                decision=decision,
                outcome=outcome,
                retry_kind="validation" if can_retry else None,
                validation_issues=issues,
                error=err,
                record=record,
            )
        hook_steps["deterministic_validation"] = "ok"

        # (3) Shared evaluation: deterministic injection scan + reviewer call
        # + grounding + trusted policy decision (the reviewer always runs once
        # validators pass, in both modes, even when the scan flags something).
        artifact_dict = artifact.as_dict()
        if context is None:
            context = {k: input_artifacts[k].as_dict() for k in config.context_keys}
        documents = {**context, gate: artifact_dict}
        self.audit.log_review_start(
            step=step_id,
            gate=gate,
            attempt=attempt,
            reviewer_id=config.reviewer_id,
            artifact_sha256=artifact.sha256,
            review_mode=self.mode,
            workflow_status=self._workflow_status(),
        )
        evaluation = evaluate_review(
            reviewer,
            context=context,
            artifact_dict=artifact_dict,
            documents=documents,
        )
        result = evaluation.result
        det_issues = evaluation.det_issues
        policy = evaluation.decision
        hook_steps["injection_scan"] = f"{len(det_issues)} finding(s)" if det_issues else "ok"
        record["deterministic_artifact_findings"] = [issue_to_dict(i) for i in det_issues]

        rev = record["reviewer"]
        rev["reviewed_artifact_sha256"] = result.reviewed_artifact_sha256
        rev["attempts"] = [a.to_dict() for a in result.attempts]
        rev["error_code"] = result.error_code
        rev["latency_s"] = result.duration_s
        rev["token_usage"] = result.token_usage
        if result.model:
            rev["model"] = result.model
        verdict = result.verdict
        if result.ok and verdict is not None:
            rev["verdict"] = verdict.verdict
            rev["reason"] = verdict.reason
        rev["issues"] = evaluation.issue_records
        rev["unknown_codes"] = evaluation.unknown_codes
        if policy is not None:
            record["policy"] = {
                "effective_verdict": policy.decision,
                "note": policy.notes[0] if policy.notes else None,
                "notes": policy.notes,
                "punch_out_confirmed": policy.punch_out_confirmed,
                "blocking_issue_codes": [i.code for i in policy.blocking_issues],
            }
        hook_steps["reviewer_call"] = "ok" if result.ok else str(result.error_code)
        hook_steps["policy_decision"] = policy.decision if policy is not None else "n/a"
        rev_invocations = result.invocations
        primary_inv = rev_invocations[-1] if rev_invocations else {}
        last_attempt = rev["attempts"][-1] if rev["attempts"] else {}
        self.audit.log_reviewer_call(
            step=step_id,
            gate=gate,
            attempt=attempt,
            reviewer_id=config.reviewer_id,
            reviewer_model=rev["model"],
            attempts=rev["attempts"],
            ok=result.ok,
            error_code=result.error_code,
            duration_s=result.duration_s,
            token_usage=result.token_usage,
            reviewer_prompt_sha256=reviewer.template_sha256,
            artifact_sha256=artifact.sha256,
            review_mode=self.mode,
            verdict=rev["verdict"],
            findings=[{"code": i["code"], "severity": i["severity"]} for i in rev["issues"]],
            invocation_id=last_attempt.get("invocation_id"),
            provider=primary_inv.get("provider"),
            devin_session_id=primary_inv.get("devin_session_id"),
            session_type=primary_inv.get("session_type"),
            cost_details=cost_details_for_invocation(
                primary_inv or None,
                acu_usd_rate=self.acu_usd_rate,
                pricing_snapshot_id=self.pricing_snapshot_id,
            ),
        )

        # (4) Repeated-finding tracking and false-positive candidates.  These
        # are *annotations only*: nothing is ever dismissed because it is
        # ungrounded or repeated.
        repeated = self._repeats.observe(
            gate, attempt, artifact.sha256, evaluation.issue_records
        )
        record["repeated_findings"] = repeated
        for r in repeated:
            self.audit.log_repeated_finding(
                gate=gate, attempt=attempt, finding=r,
                workflow_status=self._workflow_status(),
            )
        fp_candidates = false_positive_candidates(
            gate=gate,
            artifact_sha256=artifact.sha256,
            generator_attempt=attempt,
            issue_records=evaluation.issue_records,
            repeated=repeated,
        )
        record["false_positive_candidates"] = fp_candidates
        if fp_candidates:
            fp_path = self.keeper.gates_dir / "false_positive_candidates.jsonl"
            with fp_path.open("a", encoding="utf-8") as f:
                for c in fp_candidates:
                    f.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")
                    self.audit.log_false_positive_candidate(
                        gate=gate, attempt=attempt, candidate=c,
                        workflow_status=self._workflow_status(),
                    )

        # Reference-label comparison (standalone evaluation aid).
        expected = self.reference_labels.get(gate)
        if expected is not None:
            any_blocking = bool(
                [i for i in det_issues if i.blocking]
                or [
                    i
                    for i in evaluation.issue_records
                    if i.get("severity") in ("critical", "major")
                ]
            )
            record["label_comparison"] = {
                "expected_verdict": expected,
                "reviewer_verdict": rev["verdict"],
                "effective_verdict": record["policy"]["effective_verdict"],
                "verdict_match": rev["verdict"] == expected,
                "false_positive": expected == "PASS"
                and (rev["verdict"] != "PASS" or any_blocking),
                "false_negative": expected in ("REVISE", "PUNCH_OUT")
                and rev["verdict"] == "PASS",
            }

        # What enforced mode would have decided (recorded in shadow runs).
        if not result.ok:
            enforced_equiv = "FAILED_REVIEWER"
        elif policy.decision == "PASS":
            enforced_equiv = "APPROVED"
        elif policy.decision == "PUNCH_OUT":
            enforced_equiv = "HALT_PUNCH_OUT"
        else:
            enforced_equiv = "FAILED_RETRIES_EXHAUSTED" if final_attempt else "RETRY"
        record["enforced_equivalent_decision"] = enforced_equiv

        blocking = [issue_to_dict(i) for i in (policy.blocking_issues if policy else [])]
        feedback = list(policy.blocking_issues) if policy is not None else [
            i for i in det_issues if i.blocking
        ]
        punch = None
        err = None
        retry_kind = None

        # (5) Mode semantics.
        if self.mode == "shadow":
            # Reviewer verdicts and reviewer errors are advisory only.  The
            # deterministic injection scan still blocks (like REVISE).
            det_blocking = [i for i in det_issues if i.blocking]
            if det_blocking:
                blocking = [issue_to_dict(i) for i in det_blocking]
                feedback = det_blocking
                if final_attempt:
                    decision, outcome, error_code = (
                        "FAILED_RETRIES_EXHAUSTED", "failed_automated",
                        REVIEW_RETRIES_EXHAUSTED,
                    )
                    err = StepErrorLike(
                        REVIEW_RETRIES_EXHAUSTED,
                        f"deterministic artifact findings rejected {step_id} on the "
                        f"final attempt with {len(blocking)} blocking issue(s)",
                        {"issues": blocking},
                    )
                else:
                    decision, outcome, error_code = "RETRY", "retry_generator", REVIEW_REVISE
                    retry_kind = "revise"
                    err = StepErrorLike(
                        REVIEW_REVISE,
                        f"deterministic artifact findings rejected {step_id} with "
                        f"{len(blocking)} blocking issue(s)",
                        {"issues": blocking},
                    )
            else:
                decision, outcome, error_code = (
                    "SHADOW_HANDOFF_PERMITTED", "proceed", None
                )
        elif not result.ok:
            # (5a) Reviewer failure: fail closed, never regenerate.
            err = StepErrorLike(
                code=result.error_code,
                message=f"reviewer {config.reviewer_id} failed for gate {gate}",
                details={"attempts": rev["attempts"]},
            )
            finish("FAILED_REVIEWER", "failed_automated", result.error_code)
            return GateOutcome(
                decision="FAILED_REVIEWER", outcome="failed_automated", error=err, record=record
            )
        elif policy.decision == "PASS":
            decision, outcome, error_code = "APPROVED", "proceed", None
        elif policy.decision == "PUNCH_OUT":
            decision, outcome, error_code = "HALT_PUNCH_OUT", "punch_out", REVIEW_PUNCH_OUT
            punch = self._halt_record(
                step_id,
                gate,
                PunchOutReason.REVIEWER_POLICY_PUNCH_OUT,
                f"reviewer {config.reviewer_id} escalated gate {gate}",
                {"issues": blocking, "reason": verdict.reason},
            )
            err = StepErrorLike(
                REVIEW_PUNCH_OUT,
                f"reviewer {config.reviewer_id} escalated gate {gate} to human review",
                {"issues": blocking},
            )
        elif final_attempt:
            decision, outcome, error_code = (
                "FAILED_RETRIES_EXHAUSTED", "failed_automated", REVIEW_RETRIES_EXHAUSTED,
            )
            err = StepErrorLike(
                REVIEW_RETRIES_EXHAUSTED,
                f"reviewer {config.reviewer_id} rejected {step_id} on the final attempt "
                f"with {len(blocking)} blocking issue(s)",
                {"issues": blocking},
            )
        else:
            decision, outcome, error_code = "RETRY", "retry_generator", REVIEW_REVISE
            retry_kind = "revise"
            err = StepErrorLike(
                REVIEW_REVISE,
                f"reviewer {config.reviewer_id} rejected {step_id} with "
                f"{len(blocking)} blocking issue(s)",
                {"issues": blocking},
            )

        # (6) Persist the record *before* any approval.  The approval binds
        # these exact bytes, so on the success path the record is not
        # rewritten afterwards.
        if outcome == "proceed":
            hook_steps["issue_approval"] = "issued_by_runner_after_record_write"
        record_sha = finish(decision, outcome, error_code)

        # (7) Approval only on a passing decision, by trusted runner code.
        if outcome == "proceed":
            try:
                self.keeper.write_approval(
                    gate,
                    artifact=artifact,
                    input_artifact_hashes=input_hashes,
                    review_record_sha256=record_sha,
                    validation_result=artifact.validation_result,
                    reviewer_model=rev["model"],
                    step_id=step_id,
                    verdict=rev["verdict"] or "PASS",
                    enforcement=self.mode,
                    reviewer_verdict=rev["verdict"],
                    reviewer_prompt_sha256=reviewer.template_sha256,
                )
            except OSError as exc:
                hook_steps["issue_approval"] = f"failed: {exc}"
                finish("FAILED_REVIEWER", "failed_automated", GATE_WRITE_FAILED)
                return GateOutcome(
                    decision="FAILED_REVIEWER",
                    outcome="failed_automated",
                    error=StepErrorLike(
                        GATE_WRITE_FAILED, f"could not write approval for gate {gate}: {exc}"
                    ),
                    record=record,
                )

        return GateOutcome(
            decision=decision,
            outcome=outcome,
            retry_kind=retry_kind,
            feedback_issues=feedback,
            error=err,
            punch_out_record=punch,
            record=record,
        )

    def _halt_record(
        self,
        step_id: str,
        gate: str,
        reason: PunchOutReason,
        message: str,
        evidence: dict[str, Any],
    ) -> PunchOutRecord:
        return PunchOutRecord(
            run_id=self.run_id,
            step=step_id,
            reason=reason,
            policy=(
                "input_artifact_immutability"
                if reason == PunchOutReason.ARTIFACT_TAMPERED
                else "gate_approval_required_for_downstream_steps"
            ),
            evidence={"gate": gate, "message": message, **(evidence or {})},
        )


__all__ = [
    "DECISIONS",
    "GATE_WRITE_FAILED",
    "GateApprovalError",
    "GateKeeper",
    "GateOutcome",
    "HandoffHook",
    "REVIEW_PUNCH_OUT",
    "REVIEW_RETRIES_EXHAUSTED",
    "REVIEW_REVISE",
    "UPSTREAM_GATES",
]
