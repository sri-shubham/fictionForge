"""Metrics and summary calculation for FictionForge workflow runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkflowMetrics:
    """Aggregated metrics for a single workflow run."""

    status: str
    completed: bool
    total_attempts: int
    retry_counts: dict[str, int]
    per_step_latency_s: dict[str, float]
    total_duration_s: float
    token_usage: dict[str, int] | None
    model_cost_usd: float | None
    validation_failure_counts: dict[str, int]
    punch_out_events: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "completed": self.completed,
            "total_attempts": self.total_attempts,
            "retry_counts": self.retry_counts,
            "per_step_latency_s": self.per_step_latency_s,
            "total_duration_s": self.total_duration_s,
            "token_usage": self.token_usage,
            "model_cost_usd": self.model_cost_usd,
            "validation_failure_counts": self.validation_failure_counts,
            "punch_out_events": self.punch_out_events,
        }


def _sum_tokens(attempts: list[Any]) -> dict[str, int] | None:
    """Sum token usage across attempts, distinguishing unavailable from zero.

    A field is ``None`` only when no attempt reported it.  If at least one
    value is reported, the field is the numeric sum (possibly zero).
    """
    prompt_total: int | None = None
    completion_total: int | None = None
    total_total: int | None = None

    for attempt in attempts:
        usage = getattr(attempt, "token_usage", None) or {}
        if not isinstance(usage, dict):
            continue
        if usage.get("prompt_tokens") is not None:
            prompt_total = (prompt_total or 0) + usage["prompt_tokens"]
        if usage.get("completion_tokens") is not None:
            completion_total = (completion_total or 0) + usage["completion_tokens"]
        if usage.get("total_tokens") is not None:
            total_total = (total_total or 0) + usage["total_tokens"]

    return {
        "prompt_tokens": prompt_total,
        "completion_tokens": completion_total,
        "total_tokens": total_total,
    }


class MetricsCalculator:
    """Build a ``WorkflowMetrics`` object from a completed ``WorkflowResult``."""

    @staticmethod
    def calculate(result: Any) -> WorkflowMetrics:
        steps = getattr(result, "steps", [])
        status = getattr(result, "status", "")
        if hasattr(status, "value"):
            status = status.value

        total_attempts = 0
        retry_counts: dict[str, int] = {}
        per_step_latency_s: dict[str, float] = {}
        validation_failure_counts: dict[str, int] = {}

        all_attempts: list[Any] = []

        for step in steps:
            step_id = getattr(step, "step_id", "unknown")
            attempts = getattr(step, "attempts", [])
            total_attempts += len(attempts)
            retry_counts[step_id] = max(0, len(attempts) - 1)
            all_attempts.extend(attempts)

            step_latency = sum(
                getattr(a, "latency_s", 0.0) or 0.0 for a in attempts
            )
            per_step_latency_s[step_id] = round(step_latency, 3)

            failed = sum(
                1 for a in attempts if getattr(a, "status", "") != "passed"
            )
            validation_failure_counts[step_id] = failed

        started = getattr(result, "started_at", 0.0) or 0.0
        ended = getattr(result, "ended_at", 0.0) or 0.0
        total_duration = round(ended - started, 3) if ended >= started else 0.0

        token_usage = _sum_tokens(all_attempts)
        # If every token field is None, represent unavailability as a null dict
        if all(v is None for v in token_usage.values()):
            token_usage = None

        punch_outs = getattr(result, "punch_out_records", None) or []

        return WorkflowMetrics(
            status=status,
            completed=status == "completed",
            total_attempts=total_attempts,
            retry_counts=retry_counts,
            per_step_latency_s=per_step_latency_s,
            total_duration_s=total_duration,
            token_usage=token_usage,
            model_cost_usd=None,
            validation_failure_counts=validation_failure_counts,
            punch_out_events=len(punch_outs),
        )


__all__ = ["MetricsCalculator", "WorkflowMetrics"]
