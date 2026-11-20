"""Explicit human-escalation guardrails for the FictionForge workflow.

A punch-out is a condition that requires authorized human intervention.
The module exposes detection helpers and a structured exception/record so
that the deterministic runner can halt immediately and produce auditable
evidence.

It also implements the local authorization boundary for resuming a halted
run: every punch-out persists a pending decision under ``punch_outs/`` in
the run directory, and only an HMAC-signed decision file created by the
``--decide`` CLI (bound to the run, the punch-out ID and the artifact
context) authorizes a resume.  Security halts such as artifact tampering
are never human-approvable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class PunchOutReason(StrEnum):
    """Standardized reasons for escalating a workflow to human review."""

    POLICY_EXCEPTION_REQUESTED = "policy_exception_requested"
    UNSAFE_OPERATION = "unsafe_operation"
    GUARDRAIL_BYPASS_ATTEMPT = "guardrail_bypass_attempt"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    ARTIFACT_TAMPERED = "artifact_tampered"
    GATE_APPROVAL_INVALID = "gate_approval_invalid"
    REVIEWER_POLICY_PUNCH_OUT = "reviewer_policy_punch_out"
    UNKNOWN = "unknown"


# Phrases in raw model output that indicate an attempt to override workflow
# control.  Detection is case-insensitive and ignores surrounding punctuation.
_PUNCH_OUT_PHRASES: frozenset[str] = frozenset(
    {
        "skip_validation",
        "bypass validation",
        "bypass the validator",
        "bypass guardrails",
        "ignore the rules",
        "ignore validation",
        "self-approve",
        "self approve",
        "i approve this output",
        "this output is approved",
        "you may approve",
        "approve this and continue",
        "override the validator",
        "do not validate",
        "disable validation",
        "ignore the schema",
        "exempt from",
        "policy exception",
        "human approval required",
        "require human approval",
    }
)


def _punch_out_phrases() -> frozenset[str]:
    """Return the mutable-controlled detection phrase set (for testing)."""
    return _PUNCH_OUT_PHRASES


def utc_now() -> str:
    """ISO-8601 UTC timestamp for audit records."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PunchOutRecord:
    """Immutable record of a human-escalation event."""

    run_id: str
    step: str
    reason: PunchOutReason
    policy: str
    evidence: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)
    approved: bool = False
    approved_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step": self.step,
            "reason": str(self.reason),
            "policy": self.policy,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "approved": self.approved,
            "approved_by": self.approved_by,
        }


class PunchOutError(Exception):
    """Raised when the workflow must stop and await human review."""

    def __init__(
        self,
        message: str,
        record: PunchOutRecord | None = None,
    ) -> None:
        super().__init__(message)
        self.record = record


def scan_output_for_punch_outs(text: str) -> list[dict[str, Any]]:
    """Scan raw model output for phrases that attempt to bypass guardrails.

    Returns a list of match records.  An empty list means no punch-out
    language was detected.
    """
    if not text:
        return []

    lowered = text.lower()
    found: list[dict[str, Any]] = []
    for phrase in _punch_out_phrases():
        if phrase in lowered:
            found.append({"phrase": phrase, "context": _context(lowered, phrase)})
    return found


def _context(text: str, phrase: str) -> str:
    """Return a short snippet around a matched phrase."""
    pos = text.find(phrase)
    if pos < 0:
        return ""
    start = max(0, pos - 40)
    end = min(len(text), pos + len(phrase) + 40)
    return text[start:end]


def check_output_for_punch_outs(
    text: str,
    *,
    run_id: str = "",
    step: str = "",
) -> None:
    """Raise ``PunchOutError`` if the model output attempts to bypass controls.

    The runner must never make control-flow decisions based on untrusted
    LLM instructions, so any control-override language is escalated.
    """
    matches = scan_output_for_punch_outs(text)
    if not matches:
        return

    record = PunchOutRecord(
        run_id=run_id,
        step=step,
        reason=PunchOutReason.GUARDRAIL_BYPASS_ATTEMPT,
        policy="llm_output_must_not_override_workflow_controls",
        evidence={
            "matched_phrases": [m["phrase"] for m in matches],
            "contexts": [m["context"] for m in matches],
            "occurrence_count": len(matches),
        },
    )
    raise PunchOutError(
        f"Guardrail bypass language detected in {step} output ({len(matches)} match(es))",
        record=record,
    )


def raise_punch_out(
    run_id: str,
    step: str,
    reason: PunchOutReason,
    policy: str,
    evidence: dict[str, Any],
) -> None:
    """Convenience helper: raise a fully formed ``PunchOutError``."""
    record = PunchOutRecord(
        run_id=run_id,
        step=step,
        reason=reason,
        policy=policy,
        evidence=evidence,
    )
    raise PunchOutError(f"Punch-out required in {step}: {reason.value}", record=record)


# ---------------------------------------------------------------------------
# Human-decision authorization (local, signed decision files)
# ---------------------------------------------------------------------------
#
# Every punch-out persists a pending decision under ``punch_outs/`` in the
# run directory.  A resume is authorized only by a signed decision file
# created through ``runner.py --decide``.  The decision is HMAC-signed with
# a local key (``FICTIONFORGE_APPROVAL_KEY`` or ``config/approval_signing
# .key``) and bound to the run ID, the punch-out ID and the artifact
# context hash.  Security halts (artifact tampering, invalid gate
# approvals, unclassified reasons) are never human-approvable: they
# indicate corrupted trusted state and a fresh run is required.

#: Punch-out reasons a human may approve for resume.
APPROVABLE_REASONS: frozenset[PunchOutReason] = frozenset(
    {
        PunchOutReason.POLICY_EXCEPTION_REQUESTED,
        PunchOutReason.UNSAFE_OPERATION,
        PunchOutReason.GUARDRAIL_BYPASS_ATTEMPT,
        PunchOutReason.HUMAN_APPROVAL_REQUIRED,
        PunchOutReason.REVIEWER_POLICY_PUNCH_OUT,
    }
)

PUNCH_OUT_DIR = "punch_outs"
DEFAULT_KEY_FILE = "config/approval_signing.key"
KEY_ENV_VAR = "FICTIONFORGE_APPROVAL_KEY"

#: Run-directory artifact files whose hashes bind a pending decision to the
#: trusted state it was issued against.
ARTIFACT_FILES = ("brief.json", "world.json", "characters.json", "storyboard.json")


def is_approvable(reason: PunchOutReason | str) -> bool:
    """Return True when a human may approve resuming after ``reason``."""
    try:
        return PunchOutReason(str(reason)) in APPROVABLE_REASONS
    except ValueError:
        return False


def _canonical(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def artifact_context_hash(run_dir: Path | str) -> str:
    """Hash the artifact files currently present in a run directory.

    Binds a pending decision to the trusted artifacts it was issued
    against; modifying any of them invalidates a previously recorded
    approval.
    """
    run_dir = Path(run_dir)
    hashes = {
        name: _sha256((run_dir / name).read_bytes())
        for name in ARTIFACT_FILES
        if (run_dir / name).is_file()
    }
    return _sha256(_canonical(hashes))


def load_approval_key(key_file: Path | str | None = None) -> bytes:
    """Load the local decision-signing key.

    Resolution order: ``FICTIONFORGE_APPROVAL_KEY`` (hex), an explicit
    ``key_file``, then the default ``config/approval_signing.key`` (created
    on first use, mode 0600).  Possession of this key is the local
    authorization boundary; it is never written to logs or run artifacts.
    """
    env_key = os.environ.get(KEY_ENV_VAR)
    if env_key:
        return bytes.fromhex(env_key.strip())
    path = Path(key_file) if key_file else Path(DEFAULT_KEY_FILE)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
    return bytes.fromhex(path.read_text(encoding="utf-8").strip())


def pending_path(run_dir: Path | str, punch_out_id: str) -> Path:
    return Path(run_dir) / PUNCH_OUT_DIR / f"{punch_out_id}.pending.json"


def decision_path(run_dir: Path | str, punch_out_id: str) -> Path:
    return Path(run_dir) / PUNCH_OUT_DIR / f"{punch_out_id}.decision.json"


def write_pending_decision(run_dir: Path | str, record: PunchOutRecord) -> str:
    """Persist a pending human decision for a punch-out; return its ID."""
    run_dir = Path(run_dir)
    out_dir = run_dir / PUNCH_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(out_dir.glob("*.pending.json"))) + 1
    punch_out_id = f"po-{record.run_id}-{seq:02d}"
    pending = {
        "punch_out_id": punch_out_id,
        "run_id": record.run_id,
        "step": record.step,
        "reason": str(record.reason),
        "policy": record.policy,
        "evidence": record.evidence,
        "context_hash": artifact_context_hash(run_dir),
        "approvable": is_approvable(record.reason),
        "status": "pending",
        "created_at": utc_now(),
    }
    _atomic_write(pending_path(run_dir, punch_out_id), _canonical(pending))
    return punch_out_id


def load_pending_decisions(run_dir: Path | str) -> list[dict[str, Any]]:
    out_dir = Path(run_dir) / PUNCH_OUT_DIR
    pendings: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*.pending.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if isinstance(data, dict) and data.get("punch_out_id"):
            pendings.append(data)
    return pendings


def load_decision(run_dir: Path | str, punch_out_id: str) -> dict[str, Any] | None:
    path = decision_path(run_dir, punch_out_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def sign_decision(payload: dict[str, Any], key: bytes) -> dict[str, Any]:
    signed = dict(payload)
    signed["signature"] = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    return signed


def verify_decision_signature(signed: dict[str, Any], key: bytes) -> bool:
    signature = signed.get("signature")
    if not isinstance(signature, str):
        return False
    payload = {k: v for k, v in signed.items() if k != "signature"}
    expected = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


class DecisionError(Exception):
    """Raised when recording a human decision is not permitted."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def record_human_decision(
    *,
    run_dir: Path | str,
    punch_out_id: str,
    decision: str,
    approver: str,
    approvers: list[str] | frozenset[str],
    key: bytes,
    audit: Any | None = None,
) -> dict[str, Any]:
    """Record a signed human decision for a pending punch-out.

    Validates the pending decision, the approver allowlist and (for
    approvals) punch-out approvability, then writes an immutable signed
    ``<punch_out_id>.decision.json`` file, logs a ``human_decision`` audit
    event and updates ``summary.json`` (denials move the run to
    ``human_denied``).  Raises :class:`DecisionError` on any policy breach.
    """
    run_dir = Path(run_dir)
    if decision not in ("approve", "deny"):
        raise DecisionError(
            f"decision must be 'approve' or 'deny', got {decision!r}",
            code="INVALID_DECISION",
        )
    pending_file = pending_path(run_dir, punch_out_id)
    if not pending_file.is_file():
        raise DecisionError(
            f"no pending decision {punch_out_id!r} in {run_dir}",
            code="PENDING_DECISION_NOT_FOUND",
        )
    pending = json.loads(pending_file.read_text(encoding="utf-8"))
    if decision_path(run_dir, punch_out_id).is_file():
        raise DecisionError(
            f"punch-out {punch_out_id!r} already has a recorded decision",
            code="ALREADY_DECIDED",
        )
    if approver not in set(approvers):
        raise DecisionError(
            f"approver {approver!r} is not in the configured approvers list",
            code="APPROVER_NOT_AUTHORIZED",
        )
    reason = pending.get("reason", "")
    if decision == "approve" and not is_approvable(reason):
        raise DecisionError(
            f"punch-out reason {reason!r} is a security halt and cannot be "
            "approved by a human decision; start a new run",
            code="PUNCH_OUT_NOT_APPROVABLE",
        )

    payload = {
        "punch_out_id": punch_out_id,
        "run_id": pending["run_id"],
        "decision": decision,
        "approver": approver,
        "step": pending["step"],
        "reason": reason,
        "context_hash": pending["context_hash"],
        "decided_at": utc_now(),
    }
    signed = sign_decision(payload, key)
    _atomic_write(decision_path(run_dir, punch_out_id), _canonical(signed))

    if audit is not None:
        audit.log_human_decision(
            punch_out_id=punch_out_id,
            decision=decision,
            approver=approver,
            authorized=True,
            reason_code="OK",
            step=pending["step"],
            punch_out_reason=reason,
        )

    summary_path = run_dir / "summary.json"
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = None
        if isinstance(summary, dict):
            for rec in summary.get("punch_out_records", []):
                if rec.get("evidence", {}).get("punch_out_id") == punch_out_id:
                    rec["decision"] = decision
                    rec["decided_by"] = approver
                    rec["decided_at"] = payload["decided_at"]
                    # ``approved`` is set only by the runner after it verifies
                    # the signed decision during resume authorization.
            if decision == "deny":
                summary["status"] = "human_denied"
            _atomic_write(summary_path, _canonical(summary))
    return signed


__all__ = [
    "APPROVABLE_REASONS",
    "ARTIFACT_FILES",
    "DecisionError",
    "PunchOutError",
    "PunchOutReason",
    "PunchOutRecord",
    "artifact_context_hash",
    "check_output_for_punch_outs",
    "is_approvable",
    "load_approval_key",
    "load_decision",
    "load_pending_decisions",
    "raise_punch_out",
    "record_human_decision",
    "scan_output_for_punch_outs",
    "sign_decision",
    "verify_decision_signature",
    "write_pending_decision",
]
