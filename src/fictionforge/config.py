"""Workflow and provider configuration for FictionForge."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fictionforge.guardrails.validators import ErrorCode


def _default_retryable() -> list[str]:
    """Validator error codes that may be transient and therefore retried.

    Provider-level codes are also included because the same list is used to
    classify non-validation failures (JSON parse, timeout, etc.).
    """
    validator_codes = [
        # Structural / reference errors that a resampled generation may fix
        ErrorCode.SCHEMA_VIOLATION,
        ErrorCode.MISSING_REQUIRED_FIELD,
        ErrorCode.COUNT_BELOW_MIN,
        ErrorCode.COUNT_ABOVE_MAX,
        ErrorCode.DUPLICATE_ID,
        ErrorCode.UNKNOWN_LOCATION_REF,
        ErrorCode.UNKNOWN_FACTION_REF,
        ErrorCode.UNKNOWN_CHARACTER_REF,
        ErrorCode.UNKNOWN_SCENE_REF,
        ErrorCode.SELF_RELATIONSHIP,
        ErrorCode.DUPLICATE_RELATIONSHIP,
        ErrorCode.MISSING_PROTAGONIST,
        ErrorCode.SELF_DEPENDENCY,
        ErrorCode.FORWARD_DEPENDENCY,
        ErrorCode.CYCLIC_DEPENDENCY,
        ErrorCode.MISSING_NARRATIVE_PHASE,
        ErrorCode.NARRATIVE_PHASE_ORDER,
        # Brief-driven constraint violations that a better generation may fix
        ErrorCode.BRIEF_LOCATION_COUNT_MISMATCH,
        ErrorCode.BRIEF_LOCATIONS_BELOW_MIN,
        ErrorCode.BRIEF_LOCATIONS_ABOVE_MAX,
        ErrorCode.BRIEF_FORBIDDEN_TERM,
        ErrorCode.BRIEF_REQUIRED_TERM_MISSING,
        ErrorCode.WORLD_ID_MISMATCH,
    ]
    operational_codes = ["INVALID_JSON", "MODEL_TIMEOUT", "REVIEW_REVISE"]
    return [str(c) for c in validator_codes] + operational_codes


def _default_non_retryable() -> list[str]:
    """Codes that indicate an unrecoverable failure or human escalation."""
    return [
        ErrorCode.BRIEF_CONSTRAINT_MALFORMED,
        "POLICY_VIOLATION",
        "PROVIDER_CONFIGURATION_ERROR",
        "ARTIFACT_TAMPERED",
        "PUNCH_OUT",
        "REVIEWER_TIMEOUT",
        "REVIEWER_PROVIDER_ERROR",
        "REVIEWER_INVALID_RESPONSE",
        "REVIEW_RETRIES_EXHAUSTED",
        "REVIEW_PUNCH_OUT",
        "GATE_APPROVAL_INVALID",
        "GATE_WRITE_FAILED",
    ]


@dataclass
class WorkflowConfig:
    """Deterministic workflow policy."""

    max_attempts_per_step: int = 3
    stop_on_failure: bool = True
    retryable_errors: list[str] = field(default_factory=_default_retryable)
    non_retryable_errors: list[str] = field(default_factory=_default_non_retryable)
    output_dir: str = "runs"
    provider: str = "devin"
    model: str | None = None
    timeout: float = 120.0
    temperature: float = 0.7
    max_tokens: int | None = None
    review_enabled: bool = False
    review_mode: str = "enforced"
    review_model: str | None = None
    review_models: dict[str, str] | None = None
    review_timeout: float = 300.0
    review_max_attempts: int = 2
    review_temperature: float = 0.0
    # Configured ACU→USD conversion rate (org billing rate).  Used only to
    # produce labelled estimated_usd — never treated as actual billing.
    acu_usd_rate: float | None = None
    # Local authorization boundary for human punch-out decisions: approver
    # identities allowed to sign approve/deny decisions, and the HMAC key
    # file used to sign them (FICTIONFORGE_APPROVAL_KEY env var overrides).
    human_approvers: list[str] = field(default_factory=list)
    approval_key_file: str | None = None

    def __post_init__(self) -> None:
        from fictionforge.guardrails.review import REVIEW_MODES

        if self.review_mode not in REVIEW_MODES:
            raise ValueError(
                f"review_mode must be one of {REVIEW_MODES}, got {self.review_mode!r}"
            )
        if self.review_models is not None:
            from fictionforge.guardrails.review import default_reviewer_configs

            valid = {c.gate for c in default_reviewer_configs().values()}
            bad = set(self.review_models) - valid
            if bad:
                raise ValueError(
                    f"review_models keys must be gate names {sorted(valid)}, "
                    f"got {sorted(bad)}"
                )

    @classmethod
    def from_yaml(cls, path: Path | str) -> "WorkflowConfig":
        raw = Path(path).read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(raw) or {}
        wf = data.get("workflow", {})
        review = wf.get("review", {}) or {}
        cost = wf.get("cost", {}) or {}
        approvals = wf.get("human_approvals", {}) or {}
        return cls(
            max_attempts_per_step=wf.get("max_attempts_per_step", 3),
            stop_on_failure=wf.get("stop_on_failure", True),
            retryable_errors=wf.get("retryable_errors", _default_retryable()),
            non_retryable_errors=wf.get("non_retryable_errors", _default_non_retryable()),
            output_dir=wf.get("output_dir", "runs"),
            provider=wf.get("provider", "devin"),
            model=wf.get("model"),
            timeout=float(wf.get("timeout", 120.0)),
            temperature=float(wf.get("temperature", 0.7)),
            max_tokens=wf.get("max_tokens"),
            review_enabled=bool(review.get("enabled", False)),
            review_mode=str(review.get("mode", "enforced")),
            review_model=review.get("model"),
            review_models=(
                dict(review["models"]) if review.get("models") else None
            ),
            review_timeout=float(review.get("timeout", 300.0)),
            review_max_attempts=int(review.get("max_attempts", 2)),
            review_temperature=float(review.get("temperature", 0.0)),
            acu_usd_rate=(
                float(cost["acu_usd_rate"])
                if cost.get("acu_usd_rate") is not None
                else None
            ),
            human_approvers=[str(a) for a in approvals.get("approvers", [])],
            approval_key_file=approvals.get("key_file"),
        )

    @classmethod
    def default(cls) -> "WorkflowConfig":
        return cls(
            retryable_errors=_default_retryable(),
            non_retryable_errors=_default_non_retryable(),
        )

    def is_retryable(self, code: str) -> bool:
        """Fail-closed: a code is retryable only if explicitly listed."""
        if code in self.non_retryable_errors:
            return False
        return code in self.retryable_errors


__all__ = ["WorkflowConfig"]
