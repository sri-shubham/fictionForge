"""Structured JSONL audit trail for FictionForge workflow runs.

The logger writes one event per attempt to ``audit.jsonl`` and keeps failed
attempt outputs in ``attempts/`` so that every decision is reproducible.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_run_id() -> str:
    return uuid.uuid4().hex[:16]


_EVENT_CATEGORIES = {
    "step_start": "generation",
    "step_complete": "generation",
    "session_discovered": "generation",
    "deterministic_validation": "deterministic_validation",
    "review_start": "adversarial_review",
    "reviewer_call": "adversarial_review",
    "false_positive_candidate": "adversarial_review",
    "repeated_finding": "adversarial_review",
    "gate_decision": "gate",
    "retry_decision": "retry",
    "punch_out": "punch_out",
    "human_decision": "punch_out",
    "workflow_start": "workflow",
    "workflow_complete": "workflow",
    "resume": "workflow",
    "cost_reconciliation": "billing",
}


def pending_cost_details(status: str = "pending_reconciliation") -> dict[str, Any]:
    """Default ``cost_details`` block for an unaudited-cost invocation."""
    return {
        "actual_usd": None,
        "estimated_usd": None,
        "billed_acus": None,
        "status": status,
        "source": None,
        "pricing_snapshot_id": None,
    }


@dataclass
class AuditConfig:
    """Where and how the audit trail is persisted."""

    run_dir: Path
    run_id: str = field(default_factory=_default_run_id)

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "attempts").mkdir(exist_ok=True)


class AuditLogger:
    """Append-only JSONL audit log for a single workflow run."""

    def __init__(self, run_dir: Path, run_id: str | None = None) -> None:
        self.run_id = run_id or _default_run_id()
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "attempts").mkdir(exist_ok=True)
        self.audit_path = self.run_dir / "audit.jsonl"

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _write(self, event: dict[str, Any]) -> dict[str, Any]:
        event.setdefault("run_id", self.run_id)
        event.setdefault("timestamp", _utc_now())
        event.setdefault(
            "category", _EVENT_CATEGORIES.get(event.get("event_type"), "workflow")
        )
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # -----------------------------------------------------------------------
    # Artifact persistence
    # -----------------------------------------------------------------------

    def save_artifact(self, name: str, data: bytes) -> Path:
        """Persist a validated artifact to the run directory."""
        path = self.run_dir / name
        path.write_bytes(data)
        return path

    def save_attempt(self, step: str, attempt: int, data: bytes) -> Path:
        """Persist a failed or intermediate attempt under ``attempts/``."""
        path = self.run_dir / "attempts" / f"{step}_attempt_{attempt}.json"
        path.write_bytes(data)
        return path

    # -----------------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------------

    def log_step_start(
        self,
        step: str,
        attempt: int,
        prompt_hash: str,
        generator_model: str | None,
        input_artifact_hashes: dict[str, str],
        workflow_status: str,
        invocation_id: str | None = None,
        provider: str | None = None,
        session_type: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_type": "step_start",
            "step": step,
            "attempt": attempt,
            "prompt_hash": prompt_hash,
            "generator_model": generator_model,
            "input_artifact_hashes": input_artifact_hashes,
            "workflow_status": workflow_status,
        }
        if invocation_id is not None:
            # The Devin session ID is only known once the CLI session is
            # created; a session_discovered event is appended later.
            event["invocation_id"] = invocation_id
            event["provider"] = provider
            event["session_type"] = session_type
            event["devin_session_id"] = None
            event["session_id_status"] = "pending"
        return self._write(event)

    def log_step_complete(
        self,
        step: str,
        attempt: int,
        output_artifact_hash: str | None,
        validation_results: list[dict[str, Any]],
        token_usage: dict[str, int] | None,
        cost: float | None,
        latency: float,
        retry_decision: str | None,
        failure_code: str | None,
        workflow_status: str,
        generator_model: str | None = None,
        invocation_id: str | None = None,
        provider: str | None = None,
        devin_session_id: str | None = None,
        session_type: str | None = None,
        session_id_reason: str | None = None,
        cost_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_type": "step_complete",
            "step": step,
            "attempt": attempt,
            "generator_model": generator_model,
            "output_artifact_hash": output_artifact_hash,
            "validation_results": validation_results,
            "token_usage": token_usage,
            "cost": cost,
            "latency": latency,
            "retry_decision": retry_decision,
            "failure_code": failure_code,
            "workflow_status": workflow_status,
        }
        if invocation_id is not None:
            event["invocation_id"] = invocation_id
            event["provider"] = provider
            event["devin_session_id"] = devin_session_id
            event["session_type"] = session_type
            if devin_session_id is None:
                event["session_id_status"] = "unavailable"
                event["session_id_reason"] = session_id_reason or "unknown"
            event["cost_details"] = cost_details or pending_cost_details()
        return self._write(event)

    def log_session_discovered(
        self,
        *,
        invocation_id: str,
        devin_session_id: str | None,
        session_type: str | None,
        source: str,
        step: str | None = None,
        attempt: int | None = None,
        agent: dict[str, Any] | None = None,
        session_id_status: str | None = None,
        session_id_reason: str | None = None,
        export_sha256: str | None = None,
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        """Append a discovery event once an invocation's session ID is known.

        Written after ``step_start``/``reviewer_call`` so historical events
        are never rewritten.
        """
        return self._write(
            {
                "event_type": "session_discovered",
                "invocation_id": invocation_id,
                "devin_session_id": devin_session_id,
                "session_type": session_type,
                "session_id_status": session_id_status
                or ("captured" if devin_session_id else "unavailable"),
                "session_id_reason": session_id_reason,
                "source": source,
                "step": step,
                "attempt": attempt,
                "agent": agent,
                "export_sha256": export_sha256,
                "workflow_status": workflow_status,
            }
        )

    def log_cost_reconciliation(
        self,
        *,
        invocation_id: str | None,
        devin_session_id: str | None,
        session_type: str | None,
        step: str | None,
        attempt: int | None,
        cost_details: dict[str, Any],
        reconciliation_source: str,
        status: str,
        reason: str | None = None,
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        """Append a cost-reconciliation outcome for a recorded invocation."""
        return self._write(
            {
                "event_type": "cost_reconciliation",
                "invocation_id": invocation_id,
                "devin_session_id": devin_session_id,
                "session_type": session_type,
                "step": step,
                "attempt": attempt,
                "cost_details": cost_details,
                "reconciliation_source": reconciliation_source,
                "status": status,
                "reason": reason,
                "workflow_status": workflow_status,
            }
        )

    def log_retry_decision(
        self,
        step: str,
        attempt: int,
        failure_code: str,
        next_attempt: int,
        reason: str,
        workflow_status: str,
        invocation_id: str | None = None,
        devin_session_id: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_type": "retry_decision",
            "step": step,
            "attempt": attempt,
            "failure_code": failure_code,
            "next_attempt": next_attempt,
            "reason": reason,
            "workflow_status": workflow_status,
        }
        if invocation_id is not None:
            event["invocation_id"] = invocation_id
            event["devin_session_id"] = devin_session_id
        return self._write(event)

    def log_punch_out(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._write({"event_type": "punch_out", "record": record})

    def log_human_decision(
        self,
        *,
        punch_out_id: str,
        decision: str | None,
        approver: str | None,
        authorized: bool,
        reason_code: str,
        step: str | None = None,
        punch_out_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a human approve/deny decision or a rejected authorization."""
        return self._write(
            {
                "event_type": "human_decision",
                "punch_out_id": punch_out_id,
                "decision": decision,
                "approver": approver,
                "authorized": authorized,
                "reason_code": reason_code,
                "step": step,
                "punch_out_reason": punch_out_reason,
                "details": details or {},
            }
        )

    def log_workflow_start(
        self,
        *,
        review_mode: str | None,
        review_enabled: bool,
        adversarial_guardrails_enforced: bool,
        reviewers: dict[str, dict[str, Any]],
        generator_model: str | None,
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "workflow_start",
                "review_mode": review_mode,
                "review_enabled": review_enabled,
                "adversarial_guardrails_enforced": adversarial_guardrails_enforced,
                "reviewers": reviewers,
                "generator_model": generator_model,
                "workflow_status": workflow_status,
            }
        )

    def log_validation(
        self,
        *,
        step: str,
        attempt: int,
        phase: str,  # "generation_output" | "gate_revalidation"
        artifact_sha256: str | None,
        status: str,  # "passed" | "failed"
        issue_codes: list[str],
        issues: list[dict[str, Any]],
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "deterministic_validation",
                "step": step,
                "attempt": attempt,
                "phase": phase,
                "artifact_sha256": artifact_sha256,
                "status": status,
                "issue_codes": issue_codes,
                "issues": issues,
                "workflow_status": workflow_status,
            }
        )

    def log_review_start(
        self,
        *,
        step: str,
        gate: str,
        attempt: int,
        reviewer_id: str,
        artifact_sha256: str | None,
        review_mode: str | None = None,
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        """Mark that a gate review is being invoked.

        Emitted immediately before the reviewer model call so live views can
        distinguish "review in progress" from generator silence.  The matching
        ``reviewer_call`` event is written when the review returns.
        """
        return self._write(
            {
                "event_type": "review_start",
                "step": step,
                "gate": gate,
                "attempt": attempt,
                "reviewer_id": reviewer_id,
                "artifact_sha256": artifact_sha256,
                "review_mode": review_mode,
                "workflow_status": workflow_status,
            }
        )

    def log_reviewer_call(
        self,
        *,
        step: str,
        gate: str,
        attempt: int,
        reviewer_id: str,
        reviewer_model: str | None,
        attempts: list[dict[str, Any]],
        ok: bool,
        error_code: str | None,
        duration_s: float,
        token_usage: dict[str, int] | None = None,
        reviewer_prompt_sha256: str | None = None,
        artifact_sha256: str | None = None,
        review_mode: str | None = None,
        verdict: str | None = None,
        findings: list[dict[str, Any]] | None = None,
        latency_s: float | None = None,
        invocation_id: str | None = None,
        provider: str | None = None,
        devin_session_id: str | None = None,
        session_type: str | None = None,
        cost_details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_type": "reviewer_call",
            "step": step,
            "gate": gate,
            "attempt": attempt,
            "reviewer_id": reviewer_id,
            "reviewer_model": reviewer_model,
            "reviewer_prompt_sha256": reviewer_prompt_sha256,
            "artifact_sha256": artifact_sha256,
            "review_mode": review_mode,
            "verdict": verdict,
            "findings": findings,
            "reviewer_attempts": attempts,
            "ok": ok,
            "error_code": error_code,
            "duration_s": duration_s,
            "latency_s": duration_s if latency_s is None else latency_s,
            "token_usage": token_usage,
        }
        if invocation_id is not None:
            event["invocation_id"] = invocation_id
            event["provider"] = provider
            event["devin_session_id"] = devin_session_id
            event["session_type"] = session_type
            if devin_session_id is None:
                event["session_id_status"] = "unavailable"
            event["cost_details"] = cost_details or pending_cost_details()
        return self._write(event)

    def log_gate_decision(
        self,
        *,
        step: str,
        gate: str,
        attempt: int,
        gate_decision: str,
        outcome: str,
        reviewer_verdict: str | None,
        reviewer_model: str | None,
        input_artifact_hash: str | None,
        issue_codes: list[str],
        duration_s: float,
        workflow_status: str,
        review_mode: str | None = None,
        artifact_sha256: str | None = None,
        validation_status: str | None = None,
        findings: list[dict[str, Any]] | None = None,
        retry_decision: str | None = None,
        enforced_equivalent_decision: str | None = None,
        repeated_findings: int = 0,
        false_positive_candidates: int = 0,
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "gate_decision",
                "step": step,
                "gate": gate,
                "attempt": attempt,
                "gate_decision": gate_decision,
                "outcome": outcome,
                "reviewer_verdict": reviewer_verdict,
                "reviewer_model": reviewer_model,
                "input_artifact_hash": input_artifact_hash,
                "artifact_sha256": artifact_sha256,
                "review_mode": review_mode,
                "validation_status": validation_status,
                "findings": findings,
                "issue_codes": issue_codes,
                "retry_decision": retry_decision,
                "enforced_equivalent_decision": enforced_equivalent_decision,
                "repeated_findings": repeated_findings,
                "false_positive_candidates": false_positive_candidates,
                "duration_s": duration_s,
                "workflow_status": workflow_status,
            }
        )

    def log_false_positive_candidate(
        self,
        *,
        gate: str,
        attempt: int,
        candidate: dict[str, Any],
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "false_positive_candidate",
                "gate": gate,
                "attempt": attempt,
                "candidate": candidate,
                "workflow_status": workflow_status,
            }
        )

    def log_repeated_finding(
        self,
        *,
        gate: str,
        attempt: int,
        finding: dict[str, Any],
        workflow_status: str | None = None,
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "repeated_finding",
                "gate": gate,
                "attempt": attempt,
                "finding": finding,
                "workflow_status": workflow_status,
            }
        )

    def log_resume(
        self,
        resumed_from_step: str,
        workflow_status: str,
        approved_by: str | None = None,
        authorized_decisions: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "resume",
                "resumed_from_step": resumed_from_step,
                "approved_by": approved_by,
                "authorized_decisions": authorized_decisions or [],
                "workflow_status": workflow_status,
            }
        )

    def log_workflow_complete(
        self,
        workflow_status: str,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        return self._write(
            {
                "event_type": "workflow_complete",
                "workflow_status": workflow_status,
                "summary": summary,
            }
        )


__all__ = ["AuditLogger", "AuditConfig", "pending_cost_details"]
