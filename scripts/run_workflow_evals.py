"""End-to-end workflow evaluation harness for FictionForge.

Executes the production `WorkflowRunner` against a versioned dataset of
StoryBrief fixtures, validates every generated artifact, and writes the
machine-readable evidence required for Stage 4 certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import textwrap
import tomllib
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fictionforge.config import WorkflowConfig
from fictionforge.guardrails.validators import (
    validate_characters,
    validate_storyboard,
    validate_world,
)
from fictionforge.llm.base import LLMClient, LLMError, LLMResponse
from fictionforge.llm.devin import DevinCliClient
from fictionforge.llm.ollama import OllamaClient
from fictionforge.models import CharacterSet, StoryBrief, Storyboard, World
from fictionforge.guardrails.punch_out import PunchOutReason, PunchOutRecord
from fictionforge.runner import (
    StepAttempt,
    StepError,
    StepResult,
    StepStatus,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)

DEFAULT_WORKFLOW_CONFIG = REPO_ROOT / "config" / "workflow.yaml"
EVAL_CONFIG = REPO_ROOT / "evals" / "workflow.yaml"
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures" / "workflow"
EVIDENCE_DIR = REPO_ROOT / "evidence"
RUNS_DIR = REPO_ROOT / "runs"
PROMPT_FILES = {
    "world_generation": REPO_ROOT / "prompts" / "world.md",
    "character_design": REPO_ROOT / "prompts" / "characters.md",
    "storyboard_building": REPO_ROOT / "prompts" / "storyboard.md",
}
REVIEWER_PROMPT_FILES = {
    "world": REPO_ROOT / "prompts" / "reviewers" / "world.md",
    "characters": REPO_ROOT / "prompts" / "reviewers" / "characters.md",
    "storyboard": REPO_ROOT / "prompts" / "reviewers" / "storyboard.md",
}

# Canonical step order used to prove a punch-out halted downstream work.
STEP_ORDER = [
    "load_brief",
    "world_generation",
    "character_design",
    "storyboard_building",
]
LLM_STEPS = ["world_generation", "character_design", "storyboard_building"]
GATE_NAMES = ["world", "characters", "storyboard"]

# Evidence files the harness rewrites on every run; preserved per invocation
# under evidence/archive/<utc-timestamp>/ before being regenerated.
PRESERVED_EVIDENCE_FILES = [
    "success_rate.json",
    "audit_trail.jsonl",
    "punch_out_tests.json",
    "punch_out.md",
    "iterations/workflow.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    return yaml.safe_load(raw) or {}


class PlaybackClient(LLMClient):
    """Deterministic client that returns a fixed sequence of raw responses.

    Used for adversarial and edge-case fixtures so the production runner and
    guardrails are exercised without depending on model sampling.
    """

    def __init__(self, responses: list[str | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.calls.append({"prompt": prompt[:200], "kwargs": kwargs})
        if not self.responses:
            raise LLMError("PlaybackClient ran out of responses")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return LLMResponse(content=str(item))


class NoOpClient(LLMClient):
    """Client that should never be called; for invalid-input fixtures."""

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        raise LLMError("NoOpClient was invoked unexpectedly")


@dataclass
class EvaluatedCase:
    case_id: str
    split: str
    category: str
    expected: str
    run_id: str
    result: Any
    quality: dict[str, Any]
    grading: dict[str, Any]
    duration_s: float
    brief_path: Path
    fixture_hash: str


def _create_client(wf_cfg: WorkflowConfig, case: dict[str, Any]) -> LLMClient:
    if case.get("playback"):
        return PlaybackClient(case["playback"]["responses"])
    if case["expected"] == "punch_out":
        return PlaybackClient([])
    if case["expected"] == "rejected":
        return NoOpClient()
    if wf_cfg.provider == "devin":
        return DevinCliClient(model=wf_cfg.model or "swe", cli_timeout=wf_cfg.timeout)
    if wf_cfg.provider == "ollama":
        return OllamaClient(
            model=wf_cfg.model or "llama3.1", default_timeout=wf_cfg.timeout
        )
    raise ValueError(f"Unknown provider: {wf_cfg.provider!r}")


def _discover_fixtures(splits: list[str] | None = None) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        case["_fixture_path"] = path
        if splits is None or case.get("split") in splits:
            fixtures.append(case)
    fixtures.sort(key=lambda c: c["case_id"])
    return fixtures


def _fixture_payload(case: dict[str, Any]) -> dict[str, Any]:
    """The fixture record without harness-internal bookkeeping keys."""
    return {k: v for k, v in case.items() if not k.startswith("_")}


def _dataset_version_and_hash(cases: list[EvaluatedCase]) -> tuple[str, str]:
    """Version from evals/workflow.yaml; hash binds the evaluated fixture files.

    The dataset hash is sha256 over the canonical list of
    ``{"case_id": ..., "sha256": <fixture file sha256>}`` pairs, sorted by
    case id, so it is reproducible directly from the fixture files on disk.
    """
    version = _load_yaml(EVAL_CONFIG).get("dataset", {}).get("version", "unknown")
    canonical = _canonical_json(
        [
            {"case_id": c.case_id, "sha256": c.fixture_hash}
            for c in sorted(cases, key=lambda c: c.case_id)
        ]
    )
    return version, _sha256_text(canonical)


def _compute_prompt_hashes() -> dict[str, str]:
    return {
        step_id: _sha256_file(path) for step_id, path in PROMPT_FILES.items()
    }


def _compute_reviewer_prompt_hashes() -> dict[str, str]:
    return {
        gate: _sha256_file(path) for gate, path in REVIEWER_PROMPT_FILES.items()
    }


def _runner_version() -> str:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pyproject = tomllib.loads(pyproject_text)
    return pyproject.get("project", {}).get("version", "unknown")


def _save_brief(case: dict[str, Any], eval_dir: Path) -> Path:
    brief_path = eval_dir / "briefs" / f"{case['case_id']}.json"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        _canonical_json(case["brief"]) + "\n", encoding="utf-8"
    )
    return brief_path


def _grade_completed(result: Any) -> dict[str, Any]:
    """Re-validate a completed workflow's artifacts for quality scoring."""
    world_issues = []
    character_issues = []
    storyboard_issues = []

    if result.world is not None:
        world_issues = validate_world(result.world.model_dump(mode="json"), result.brief)
    if result.world is not None and result.characters is not None:
        character_issues = validate_characters(
            result.characters.model_dump(mode="json"), result.world, result.brief
        )
    if (
        result.world is not None
        and result.characters is not None
        and result.storyboard is not None
    ):
        storyboard_issues = validate_storyboard(
            result.storyboard.model_dump(mode="json"),
            result.world,
            result.characters,
            result.brief,
        )

    return {
        "world_valid": not world_issues,
        "characters_valid": not character_issues,
        "storyboard_valid": not storyboard_issues,
        "world_issues": [i.to_dict() for i in world_issues],
        "character_issues": [i.to_dict() for i in character_issues],
        "storyboard_issues": [i.to_dict() for i in storyboard_issues],
    }


def _review_enabled_for(result: Any) -> bool:
    """Whether adversarial review was enabled for this run."""
    review = result.review or {}
    if "enabled" in review:
        return bool(review["enabled"])
    # Older runs have no review block; gate decisions imply enforcement.
    return bool(result.gate_decisions)


def _gates_approved(result: Any) -> bool | None:
    """All three gates APPROVED?  None when review was not enabled."""
    if not _review_enabled_for(result):
        return None
    decisions = dict(result.gate_decisions or {})
    review = result.review or {}
    for gate, decision in (review.get("gates") or {}).items():
        decisions.setdefault(gate, decision)
    return all(decisions.get(g) == "APPROVED" for g in GATE_NAMES)


def _downstream_halted(result: Any) -> bool:
    """True when no step after the punched step recorded any attempt."""
    if not result.punch_out_records:
        return False
    record = result.punch_out_records[0]
    if record.step not in STEP_ORDER:
        return False
    boundary = STEP_ORDER.index(record.step)
    for s in result.steps:
        if s.step_id not in STEP_ORDER:
            continue
        if STEP_ORDER.index(s.step_id) > boundary and s.attempts:
            return False
    return True


def _failure_class(result: Any) -> str | None:
    """Terminal-failure classification distinguishing review rejections
    (bounded REVISE loops) from provider and reviewer-infrastructure
    failures, brief rejections and policy/security halts."""
    if result.status == WorkflowStatus.COMPLETED:
        return None
    if result.status == WorkflowStatus.PUNCH_OUT_REQUIRED:
        return "policy_punch_out"
    if result.status == WorkflowStatus.HUMAN_DENIED:
        return "human_denied"
    code = result.failure_code or ""
    if code == "EVAL_HARNESS_ERROR":
        return "harness_error"
    if result.exit_code == 3 or code in {
        "INVALID_STORY_BRIEF",
        "INVALID_CONFIG",
        "MISSING_BRIEF_FILE",
        "BRIEF_CONSTRAINT_MALFORMED",
    }:
        return "brief_rejection"
    if code in {"REVIEW_REVISE", "REVIEW_RETRIES_EXHAUSTED"}:
        return "review_rejection"
    if code.startswith("REVIEWER_") or code == "FAILED_REVIEWER":
        return "reviewer_infrastructure_failure"
    if code in {
        "LLM_PROVIDER_ERROR",
        "MODEL_TIMEOUT",
        "PROVIDER_CONFIGURATION_ERROR",
    }:
        return "provider_failure"
    if code in {
        "POLICY_VIOLATION",
        "ARTIFACT_TAMPERED",
        "GATE_APPROVAL_INVALID",
        "GATE_WRITE_FAILED",
        "PUNCH_OUT",
        "REVIEW_PUNCH_OUT",
    }:
        return "policy_or_security_halt"
    if code == "UNEXPECTED_ERROR":
        return "unexpected_error"
    # Validator codes and INVALID_JSON land here.
    return "validation_failure"


def _assess_case(result: Any, case: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    status = result.status.value
    expected = case["expected"]
    gates_approved = _gates_approved(result)
    downstream_halted = _downstream_halted(result)
    assessment: dict[str, Any] = {
        "end_to_end_success": False,
        "first_attempt_success": False,
        "retry_recovery": False,
        "expected": expected,
        "actual_status": status,
        "exit_code": result.exit_code,
        "failure_code": result.failure_code,
        "failure_reason": result.failure_reason,
        "failure_class": _failure_class(result),
        "gates_approved": gates_approved,
        "downstream_halted": downstream_halted,
        "storyboard_reviewer_approved": (
            (result.gate_decisions or {}).get("storyboard") == "APPROVED"
            if _review_enabled_for(result)
            else None
        ),
        "pass": False,
        "notes": [],
    }

    # End-to-end success: completed, all artifacts post-hoc valid, and —
    # when review is enabled — every gate APPROVED.
    if result.status == WorkflowStatus.COMPLETED:
        artifacts_valid = (
            quality["world_valid"]
            and quality["characters_valid"]
            and quality["storyboard_valid"]
        )
        assessment["end_to_end_success"] = artifacts_valid and (
            gates_approved in (True, None)
        )
        if not artifacts_valid:
            assessment["notes"].append("Runner reported completed but post-hoc validation failed.")
        if _review_enabled_for(result) and not gates_approved:
            assessment["notes"].append(
                "Run completed without all three gates APPROVED."
            )

    # First-attempt vs retry-recovery
    if assessment["end_to_end_success"]:
        step_attempts = [len(s.attempts) for s in result.steps]
        assessment["first_attempt_success"] = all(a == 1 for a in step_attempts)
        assessment["retry_recovery"] = any(a > 1 for a in step_attempts)

    # Pass/fail against expectation
    if expected == "completed":
        assessment["pass"] = bool(assessment["end_to_end_success"])
        if not assessment["pass"]:
            assessment["notes"].append(
                f"Expected completed but got {status} ({result.failure_code})."
            )
    elif expected == "rejected":
        no_model_steps = all(
            s.step_id == "load_brief" for s in result.steps
        )
        assessment["pass"] = bool(
            result.status == WorkflowStatus.FAILED_AUTOMATED
            and result.exit_code == 3
            and no_model_steps
        )
        if not assessment["pass"]:
            assessment["notes"].append("Expected deterministic brief rejection.")
        elif not no_model_steps:
            assessment["notes"].append("Rejected brief still started a model step.")
    elif expected == "punch_out":
        assessment["pass"] = bool(
            result.status == WorkflowStatus.PUNCH_OUT_REQUIRED
            and result.punch_out_records
            and downstream_halted
        )
        if result.status == WorkflowStatus.PUNCH_OUT_REQUIRED and not downstream_halted:
            assessment["notes"].append(
                "Punched out but downstream steps still executed."
            )
        if not assessment["pass"]:
            assessment["notes"].append("Expected punch-out escalation.")

    return assessment


def _load_model_maybe(path: Path, model: type) -> Any | None:
    if not path.exists():
        return None
    try:
        return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _replay_existing_run(
    case: dict[str, Any],
    run_id: str,
) -> EvaluatedCase:
    """Use an already-executed run directory as the result for a fixture.

    This lets the harness generate evidence from real workflow executions
    without re-invoking the model (e.g. when the provider is managed
    outside the harness).
    """
    run_dir = RUNS_DIR / run_id
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    steps: list[StepResult] = []
    for raw in summary.get("steps", []):
        attempts: list[StepAttempt] = []
        n = raw.get("attempts", 1) or 1
        status = StepStatus(raw["status"])
        for i in range(1, n + 1):
            if status == StepStatus.PASSED:
                attempt_status = "passed" if i == n else "failed"
            else:
                attempt_status = "failed"
            attempts.append(
                StepAttempt(
                    attempt_number=i,
                    status=attempt_status,
                    prompt_hash="",
                    model=None,
                    input_hashes={},
                    output_hash=None,
                    token_usage=None,
                    latency_s=0.0,
                    error=None,
                )
            )
        error = None
        if raw.get("error"):
            e = raw["error"]
            error = StepError(
                code=e.get("code", ""),
                message=e.get("message", ""),
                details=e.get("details", {}),
            )
        steps.append(
            StepResult(
                step_id=raw["step_id"],
                status=status,
                attempts=attempts,
                error=error,
            )
        )

    punch_out_records = [
        PunchOutRecord(
            run_id=r.get("run_id", run_id),
            step=r["step"],
            reason=PunchOutReason(r["reason"]),
            policy=r["policy"],
            evidence=r["evidence"],
            timestamp=r.get("timestamp") or _utc_now(),
            approved=r.get("approved", False),
            approved_by=r.get("approved_by"),
        )
        for r in summary.get("punch_out_records", [])
    ]

    brief = _load_model_maybe(run_dir / "brief.json", StoryBrief)
    world = _load_model_maybe(run_dir / "world.json", World)
    characters = _load_model_maybe(run_dir / "characters.json", CharacterSet)
    storyboard = _load_model_maybe(run_dir / "storyboard.json", Storyboard)

    result = WorkflowResult(
        run_id=run_id,
        status=WorkflowStatus(summary["status"]),
        steps=steps,
        brief=brief,
        world=world,
        characters=characters,
        storyboard=storyboard,
        output_dir=run_dir,
        started_at=summary.get("started_at", 0.0),
        ended_at=summary.get("ended_at", 0.0),
        exit_code=summary.get("exit_code", 0),
        failure_reason=summary.get("failure_reason"),
        failure_code=summary.get("failure_code"),
        punch_out_records=punch_out_records,
        gate_decisions=dict(summary.get("gates") or {}),
        review=summary.get("review"),
    )
    duration = round(result.ended_at - result.started_at, 3) if result.ended_at >= result.started_at else 0.0
    quality = _grade_completed(result)
    grading = _assess_case(result, case, quality)
    fixture_hash = _fixture_file_hash(case)

    return EvaluatedCase(
        case_id=case["case_id"],
        split=case["split"],
        category=case["category"],
        expected=case["expected"],
        run_id=run_id,
        result=result,
        quality=quality,
        grading=grading,
        duration_s=duration,
        brief_path=run_dir / "brief.json",
        fixture_hash=fixture_hash,
    )


def _run_case(
    case: dict[str, Any],
    wf_cfg: WorkflowConfig,
    eval_dir: Path,
) -> EvaluatedCase:
    existing = case.get("existing_run_id")
    if existing:
        return _replay_existing_run(case, existing)

    brief_path = _save_brief(case, eval_dir)
    client = _create_client(wf_cfg, case)
    run_id = uuid.uuid4().hex[:16]
    runner = WorkflowRunner(
        client=client,
        config=wf_cfg,
        output_dir=RUNS_DIR,
        run_id=run_id,
    )
    started = _utc_now()
    result = runner.run(brief_path)
    ended = _utc_now()
    duration = round(result.ended_at - result.started_at, 3) if result.ended_at else 0.0

    quality: dict[str, Any] = _grade_completed(result)
    grading = _assess_case(result, case, quality)
    fixture_hash = _fixture_file_hash(case)

    return EvaluatedCase(
        case_id=case["case_id"],
        split=case["split"],
        category=case["category"],
        expected=case["expected"],
        run_id=run_id,
        result=result,
        quality=quality,
        grading=grading,
        duration_s=duration,
        brief_path=brief_path,
        fixture_hash=fixture_hash,
    )


def _fixture_file_hash(case: dict[str, Any]) -> str:
    """SHA-256 of the fixture file on disk; empty when unavailable."""
    path = case.get("_fixture_path")
    if isinstance(path, Path) and path.exists():
        return _sha256_file(path)
    return _sha256_text(_canonical_json(_fixture_payload(case)))


def _audit_events_for_run(run_id: str) -> list[dict[str, Any]] | None:
    """Parsed audit.jsonl events for a run; None when the file is absent."""
    path = RUNS_DIR / run_id / "audit.jsonl"
    if not path.exists():
        return None
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _usage_total(usage: dict[str, Any] | None) -> int | None:
    """Total tokens for one invocation — never double-counts the
    prompt/completion components against the reported total."""
    if not usage:
        return None
    total = usage.get("total_tokens")
    if isinstance(total, (int, float)):
        return int(total)
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if prompt is None and completion is None:
        return None
    return int(prompt or 0) + int(completion or 0)


def _aggregate_run_audit(run_id: str) -> dict[str, Any]:
    """Token, cost, invocation and coverage aggregates for one run's audit log.

    All values come from recorded audit events only; nothing is estimated.
    """
    empty = {
        "audit_present": False,
        "generation_tokens": {s: None for s in LLM_STEPS},
        "reviewer_tokens": {g: None for g in GATE_NAMES},
        "total_tokens": 0,
        "model_invocations": 0,
        "generation_invocations": 0,
        "reviewer_invocations": 0,
        "reviewer_reasks": 0,
        "invocations_missing_tokens": 0,
        "billed_acus": 0.0,
        "estimated_usd": 0.0,
        "actual_usd": 0.0,
        "acus_per_step": {s: 0.0 for s in LLM_STEPS},
        "acus_per_gate": {g: 0.0 for g in GATE_NAMES},
        "invocations_with_cost": 0,
        "invocations_missing_cost": 0,
        "cost_statuses": {},
        "cost_sources": {},
        "retry_decisions": 0,
        "event_counts": {},
        "step_completes": [],
        "gate_decisions": [],
        "reviewer_calls": [],
        "punch_out_events": 0,
    }
    events = _audit_events_for_run(run_id)
    if events is None:
        return empty

    agg = dict(empty)
    agg["audit_present"] = True
    agg["generation_tokens"] = {s: 0 for s in LLM_STEPS}
    agg["reviewer_tokens"] = {g: 0 for g in GATE_NAMES}
    cost_statuses: Counter[str] = Counter()
    cost_sources: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    step_completes: list[tuple[str, int]] = []
    gate_decisions: list[dict[str, Any]] = []
    reviewer_calls: list[dict[str, Any]] = []

    for e in events:
        et = e.get("event_type")
        event_counts[et] += 1
        if et == "step_complete":
            step = e.get("step")
            step_completes.append((step, e.get("attempt")))
            if step in LLM_STEPS:
                agg["model_invocations"] += 1
                agg["generation_invocations"] += 1
                total = _usage_total(e.get("token_usage"))
                if total is None:
                    agg["invocations_missing_tokens"] += 1
                else:
                    agg["generation_tokens"][step] += total
                    agg["total_tokens"] += total
                cd = e.get("cost_details")
                if isinstance(cd, dict):
                    status = cd.get("status") or "unavailable"
                    cost_statuses[status] += 1
                    if cd.get("source"):
                        cost_sources[cd["source"]] += 1
                    acus = cd.get("billed_acus")
                    if isinstance(acus, (int, float)):
                        agg["billed_acus"] += acus
                        agg["acus_per_step"][step] += acus
                        agg["invocations_with_cost"] += 1
                    else:
                        agg["invocations_missing_cost"] += 1
                    est = cd.get("estimated_usd")
                    if isinstance(est, (int, float)):
                        agg["estimated_usd"] += est
                    act = cd.get("actual_usd")
                    if isinstance(act, (int, float)):
                        agg["actual_usd"] += act
                else:
                    agg["invocations_missing_cost"] += 1
        elif et == "reviewer_call":
            attempts = e.get("reviewer_attempts") or []
            n_calls = len(attempts) if attempts else 1
            agg["model_invocations"] += n_calls
            agg["reviewer_invocations"] += n_calls
            agg["reviewer_reasks"] += max(0, n_calls - 1)
            reviewer_calls.append(e)
            gate = e.get("gate")
            total = _usage_total(e.get("token_usage"))
            if total is None:
                agg["invocations_missing_tokens"] += 1
            else:
                if gate in agg["reviewer_tokens"]:
                    agg["reviewer_tokens"][gate] += total
                agg["total_tokens"] += total
            cd = e.get("cost_details")
            if isinstance(cd, dict):
                status = cd.get("status") or "unavailable"
                cost_statuses[status] += 1
                if cd.get("source"):
                    cost_sources[cd["source"]] += 1
                acus = cd.get("billed_acus")
                if isinstance(acus, (int, float)):
                    agg["billed_acus"] += acus
                    if gate in agg["acus_per_gate"]:
                        agg["acus_per_gate"][gate] += acus
                    agg["invocations_with_cost"] += 1
                else:
                    agg["invocations_missing_cost"] += 1
                est = cd.get("estimated_usd")
                if isinstance(est, (int, float)):
                    agg["estimated_usd"] += est
                act = cd.get("actual_usd")
                if isinstance(act, (int, float)):
                    agg["actual_usd"] += act
            else:
                agg["invocations_missing_cost"] += 1
        elif et == "retry_decision":
            agg["retry_decisions"] += 1
        elif et == "gate_decision":
            gate_decisions.append(e)
        elif et == "punch_out":
            agg["punch_out_events"] += 1

    agg["cost_statuses"] = dict(cost_statuses)
    agg["cost_sources"] = dict(cost_sources)
    agg["event_counts"] = dict(event_counts)
    agg["step_completes"] = step_completes
    agg["gate_decisions"] = gate_decisions
    agg["reviewer_calls"] = reviewer_calls
    return agg


def _collect_audit_trail(cases: list[EvaluatedCase], dataset_version: str) -> None:
    audit_path = EVIDENCE_DIR / "audit_trail.jsonl"
    with audit_path.open("w", encoding="utf-8") as out:
        for ev in cases:
            run_audit = RUNS_DIR / ev.run_id / "audit.jsonl"
            if not run_audit.exists():
                continue
            for line in run_audit.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event["eval_case_id"] = ev.case_id
                event["eval_split"] = ev.split
                event["dataset_version"] = dataset_version
                out.write(_canonical_json(event) + "\n")


def _build_punch_out_evidence(cases: list[EvaluatedCase]) -> tuple[list[dict], str]:
    records: list[dict[str, Any]] = []
    lines: list[str] = [
        "# Punch-Out Evidence",
        "",
        "This report records every human-escalation scenario encountered during the ",
        "end-to-end workflow evaluation.  All punch-outs are raised by deterministic ",
        "code in `src/fictionforge/guardrails/punch_out.py` and caught in the runner ",
        "before any downstream step executes.",
        "",
    ]

    for ev in cases:
        if ev.expected != "punch_out" and not ev.result.punch_out_records:
            continue
        record = ev.result.punch_out_records[0] if ev.result.punch_out_records else None
        audit_ref = f"runs/{ev.run_id}/audit.jsonl"
        audit_event = None
        run_audit = RUNS_DIR / ev.run_id / "audit.jsonl"
        if run_audit.exists():
            for line in run_audit.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("event_type") == "punch_out":
                    audit_event = event
                    break

        passed = bool(
            ev.grading["pass"]
            and ev.result.status == WorkflowStatus.PUNCH_OUT_REQUIRED
        )
        details = {
            "test_id": f"punch_out_{ev.case_id}",
            "case_id": ev.case_id,
            "split": ev.split,
            "triggering_condition": ev.category,
            "expected_behavior": "Workflow halts with PUNCH_OUT_REQUIRED; no downstream execution.",
            "actual_behavior": ev.result.failure_reason or ev.result.status.value,
            "workflow_status": ev.result.status.value,
            "downstream_halted": ev.grading.get("downstream_halted"),
            "run_id": ev.run_id,
            "audit_event_reference": audit_ref,
            "audit_event": audit_event,
            "punch_out_record": record.to_dict() if record else None,
            "passed": passed,
        }
        records.append(details)

        lines.extend(
            [
                f"## {details['test_id']}",
                "",
                f"- **Case ID:** {ev.case_id}",
                f"- **Run ID:** {ev.run_id}",
                f"- **Trigger:** {details['triggering_condition']}",
                f"- **Expected:** {details['expected_behavior']}",
                f"- **Actual:** {details['actual_behavior']}",
                f"- **Workflow status:** {details['workflow_status']}",
                f"- **Audit trail:** `{audit_ref}`",
                f"- **Result:** {'PASS' if passed else 'FAIL'}",
                "",
            ]
        )

    if not records:
        lines.append("No punch-out events were recorded in this evaluation run.")

    return records, "\n".join(lines)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _audit_check(ev: EvaluatedCase, agg: dict[str, Any]) -> dict[str, Any]:
    """Per-case audit completeness: every recorded step attempt has a
    step_complete event, every approving gate decision has a matching
    reviewer call, every reviewer call produced a gate decision, and every
    punch-out record has a punch_out audit event."""
    check = {
        "audit_present": agg["audit_present"],
        "missing_step_complete": [],
        "approved_gates_missing_reviewer_call": [],
        "reviewer_calls_missing_gate_decision": [],
        "punch_out_events_missing": len(ev.result.punch_out_records),
        "complete": None,
    }
    if not agg["audit_present"]:
        return check
    expected = {
        (s.step_id, a.attempt_number)
        for s in ev.result.steps
        for a in s.attempts
        if s.step_id in STEP_ORDER
    }
    have = {(step, att) for step, att in agg["step_completes"]}
    check["missing_step_complete"] = sorted(expected - have)
    rev_keys = {(e.get("gate"), e.get("attempt")) for e in agg["reviewer_calls"]}
    dec_keys = {(e.get("gate"), e.get("attempt")) for e in agg["gate_decisions"]}
    check["approved_gates_missing_reviewer_call"] = [
        {"gate": gd.get("gate"), "attempt": gd.get("attempt")}
        for gd in agg["gate_decisions"]
        if gd.get("gate_decision") in ("APPROVED", "SHADOW_HANDOFF_PERMITTED")
        and (gd.get("gate"), gd.get("attempt")) not in rev_keys
    ]
    check["reviewer_calls_missing_gate_decision"] = [
        {"gate": rc.get("gate"), "attempt": rc.get("attempt")}
        for rc in agg["reviewer_calls"]
        if (rc.get("gate"), rc.get("attempt")) not in dec_keys
    ]
    check["punch_out_events_missing"] = max(
        0, len(ev.result.punch_out_records) - agg["punch_out_events"]
    )
    check["complete"] = (
        not check["missing_step_complete"]
        and not check["approved_gates_missing_reviewer_call"]
        and not check["reviewer_calls_missing_gate_decision"]
        and check["punch_out_events_missing"] == 0
    )
    return check


def _code_to_failure_class(code: str | None) -> str:
    """Map a step-attempt error code onto the same classes as _failure_class."""
    if not code:
        return "unknown"
    if code in {"REVIEW_REVISE", "REVIEW_RETRIES_EXHAUSTED"}:
        return "review_rejection"
    if code.startswith("REVIEWER_") or code == "FAILED_REVIEWER":
        return "reviewer_infrastructure_failure"
    if code in {"LLM_PROVIDER_ERROR", "MODEL_TIMEOUT", "PROVIDER_CONFIGURATION_ERROR"}:
        return "provider_failure"
    if code in {
        "POLICY_VIOLATION", "ARTIFACT_TAMPERED", "GATE_APPROVAL_INVALID",
        "GATE_WRITE_FAILED", "PUNCH_OUT", "REVIEW_PUNCH_OUT",
    }:
        return "policy_or_security_halt"
    if code in {
        "INVALID_STORY_BRIEF", "INVALID_CONFIG", "MISSING_BRIEF_FILE",
        "BRIEF_CONSTRAINT_MALFORMED",
    }:
        return "brief_rejection"
    return "validation_failure"


def _build_success_rate_report(
    cases: list[EvaluatedCase],
    dataset_version: str,
    dataset_hash: str,
    wf_cfg: WorkflowConfig,
    prompt_hashes: dict[str, str],
    reviewer_prompt_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    eligible = [c for c in cases if c.expected == "completed"]
    completed = [c for c in eligible if c.grading["end_to_end_success"]]
    first_pass = [c for c in completed if c.grading["first_attempt_success"]]
    recovered = [c for c in completed if c.grading["retry_recovery"]]
    failed_auto = [c for c in eligible if not c.grading["end_to_end_success"]]
    expected_punch = [c for c in cases if c.expected == "punch_out"]
    expected_rejected = [c for c in cases if c.expected == "rejected"]
    observed_punch = [
        c for c in cases if c.result.status == WorkflowStatus.PUNCH_OUT_REQUIRED
    ]
    unexpected_punch = [c for c in observed_punch if c.expected != "punch_out"]
    observed_rejected = [
        c
        for c in cases
        if c.result.status == WorkflowStatus.FAILED_AUTOMATED
        and c.result.exit_code == 3
    ]
    passed_cases = [c for c in cases if c.grading["pass"]]
    # B: storyboard completion — fully validated, reviewer-approved storyboard.
    storyboard_completed = [
        c
        for c in eligible
        if c.result.status == WorkflowStatus.COMPLETED
        and c.quality["storyboard_valid"]
        and c.grading["storyboard_reviewer_approved"] in (True, None)
    ]
    # C: policy enforcement — expected punch-outs that halted correctly.
    policy_enforced = [c for c in expected_punch if c.grading["pass"]]
    harness_errors = [c for c in cases if c.run_id == "error"]

    # Audit-derived aggregates, deduplicated by run id (a replayed run must
    # not count its tokens/cost once per referencing case).
    run_aggs: dict[str, dict[str, Any]] = {}
    audit_checks: dict[str, dict[str, Any]] = {}
    for c in cases:
        if c.run_id not in run_aggs:
            run_aggs[c.run_id] = _aggregate_run_audit(c.run_id)
        audit_checks[c.case_id] = _audit_check(c, run_aggs[c.run_id])

    runs_missing_audit = [
        c.case_id for c in cases if not run_aggs[c.run_id]["audit_present"]
    ]
    runs_audit_incomplete = [
        c.case_id
        for c in cases
        if audit_checks[c.case_id]["complete"] is False
    ]

    # Per-agent attempt/failure counts, classified by failure kind.
    step_stats: dict[str, dict[str, Any]] = {
        s: {"attempts": 0, "failures": 0, "by_class": Counter()}
        for s in STEP_ORDER
    }
    for c in cases:
        for s in c.result.steps:
            if s.step_id not in step_stats:
                step_stats[s.step_id] = {"attempts": 0, "failures": 0, "by_class": Counter()}
            step_stats[s.step_id]["attempts"] += len(s.attempts)
            for a in s.attempts:
                if a.status != "passed":
                    step_stats[s.step_id]["failures"] += 1
                    cls = _code_to_failure_class(a.error.code if a.error else None)
                    step_stats[s.step_id]["by_class"][cls] += 1

    per_agent_failure = {
        step: {
            "attempts": stats["attempts"],
            "failures": stats["failures"],
            "failure_rate": round(stats["failures"] / stats["attempts"], 4)
            if stats["attempts"]
            else 0.0,
            "by_failure_class": dict(stats["by_class"]),
        }
        for step, stats in step_stats.items()
    }

    # Quality pass counts
    quality_pass = {
        "world_valid": sum(1 for c in completed if c.quality["world_valid"]),
        "characters_valid": sum(
            1 for c in completed if c.quality["characters_valid"]
        ),
        "storyboard_valid": sum(
            1 for c in completed if c.quality["storyboard_valid"]
        ),
    }

    # Token / cost / invocation totals from run audit logs (deduplicated).
    gen_tokens: dict[str, int] = {s: 0 for s in LLM_STEPS}
    rev_tokens: dict[str, int] = {g: 0 for g in GATE_NAMES}
    acus_step: dict[str, float] = {s: 0.0 for s in LLM_STEPS}
    acus_gate: dict[str, float] = {g: 0.0 for g in GATE_NAMES}
    total_tokens = 0
    tokens_recorded = False
    invocations = 0
    gen_invocations = 0
    rev_invocations = 0
    reviewer_reasks = 0
    missing_tokens = 0
    billed_acus = 0.0
    estimated_usd = 0.0
    actual_usd = 0.0
    inv_with_cost = 0
    inv_missing_cost = 0
    retry_decisions = 0
    cost_statuses: Counter[str] = Counter()
    cost_sources: Counter[str] = Counter()
    for agg in run_aggs.values():
        if not agg["audit_present"]:
            continue
        invocations += agg["model_invocations"]
        gen_invocations += agg["generation_invocations"]
        rev_invocations += agg["reviewer_invocations"]
        reviewer_reasks += agg["reviewer_reasks"]
        missing_tokens += agg["invocations_missing_tokens"]
        billed_acus += agg["billed_acus"]
        estimated_usd += agg["estimated_usd"]
        actual_usd += agg["actual_usd"]
        inv_with_cost += agg["invocations_with_cost"]
        inv_missing_cost += agg["invocations_missing_cost"]
        retry_decisions += agg["retry_decisions"]
        cost_statuses.update(agg["cost_statuses"])
        cost_sources.update(agg["cost_sources"])
        for s in LLM_STEPS:
            v = agg["generation_tokens"].get(s) or 0
            gen_tokens[s] += v
            acus_step[s] += agg["acus_per_step"].get(s) or 0.0
        for g in GATE_NAMES:
            v = agg["reviewer_tokens"].get(g) or 0
            rev_tokens[g] += v
            acus_gate[g] += agg["acus_per_gate"].get(g) or 0.0
        if agg["total_tokens"]:
            tokens_recorded = True
            total_tokens += agg["total_tokens"]

    # Duration statistics for eligible cases
    durations = [c.duration_s for c in eligible]
    retries = [
        sum(max(0, len(s.attempts) - 1) for s in c.result.steps) for c in eligible
    ]
    failure_class_counts = Counter(
        c.grading["failure_class"] for c in cases if c.grading["failure_class"]
    )

    report = {
        "report_type": "workflow_success_rate",
        "generated_at": _utc_now(),
        "dataset": {
            "version": dataset_version,
            "sha256": dataset_hash,
            "total_cases": len(cases),
            "eligible_completion_cases": len(eligible),
            "expected_completed_cases": len(eligible),
            "expected_punch_out_cases": len(expected_punch),
            "expected_rejected_cases": len(expected_rejected),
            "development_cases": sum(1 for c in cases if c.split == "dev"),
            "holdout_cases": sum(1 for c in cases if c.split == "holdout"),
            "adversarial_cases": sum(
                1 for c in cases if "punch_out" in c.category or c.category.startswith("adversarial")
            ),
            "invalid_cases": len(expected_rejected),
            "cases_by_category": dict(Counter(c.category for c in cases)),
            "harness_error_cases": [c.case_id for c in harness_errors],
        },
        "runner": {
            "version": _runner_version(),
            "config_path": DEFAULT_WORKFLOW_CONFIG.relative_to(REPO_ROOT).as_posix(),
            "provider": wf_cfg.provider,
            "model": wf_cfg.model,
            "max_attempts_per_step": wf_cfg.max_attempts_per_step,
            "temperature": wf_cfg.temperature,
            "prompt_hashes": prompt_hashes,
            "review_enabled": wf_cfg.review_enabled,
            "review_mode": wf_cfg.review_mode,
            "review_model": wf_cfg.review_model,
            "review_models": wf_cfg.review_models,
            "review_max_attempts": wf_cfg.review_max_attempts,
            "reviewer_prompt_hashes": reviewer_prompt_hashes or {},
        },
        "summary": {
            # A — every case's actual terminal outcome vs declared expectation
            "expected_outcome_success_rate": round(
                len(passed_cases) / len(cases), 4
            )
            if cases
            else None,
            "expected_outcome_passed": len(passed_cases),
            "expected_outcome_total": len(cases),
            # B — validated, reviewer-approved storyboard over eligible cases
            "storyboard_completion_rate": round(
                len(storyboard_completed) / len(eligible), 4
            )
            if eligible
            else None,
            "storyboard_completed": len(storyboard_completed),
            "storyboard_eligible": len(eligible),
            # C — expected punch-outs that halted downstream correctly
            "policy_enforcement_rate": round(
                len(policy_enforced) / len(expected_punch), 4
            )
            if expected_punch
            else None,
            "policy_enforced": len(policy_enforced),
            "policy_expected": len(expected_punch),
            # Outcome populations (expected vs observed kept distinct)
            "completed_workflows": len(completed),
            "failed_automated_workflows": len(failed_auto),
            "punch_outs": len(observed_punch),
            "punch_outs_expected": len(expected_punch),
            "punch_outs_observed": len(observed_punch),
            "punch_outs_unexpected": len(unexpected_punch),
            "unexpected_punch_out_cases": [c.case_id for c in unexpected_punch],
            "rejected_briefs": len(expected_rejected),
            "rejected_briefs_expected": len(expected_rejected),
            "rejected_briefs_observed": len(observed_rejected),
            "end_to_end_success_rate": round(len(completed) / len(eligible), 4)
            if eligible
            else None,
            "first_pass_success_rate": round(len(first_pass) / len(eligible), 4)
            if eligible
            else None,
            "retry_recovery_rate": round(len(recovered) / len(completed), 4)
            if completed
            else 0.0,
            # Schema compliance: explicit validated booleans, never all() over
            # a mixed bool/issue-list mapping (the historical bug zeroed this).
            "schema_compliance_rate": round(
                sum(
                    1
                    for c in completed
                    if c.quality["world_valid"]
                    and c.quality["characters_valid"]
                    and c.quality["storyboard_valid"]
                )
                / len(eligible),
                4,
            )
            if eligible
            else None,
            "cross_artifact_consistency_rate": round(
                sum(
                    1
                    for c in completed
                    if c.quality["characters_valid"] and c.quality["storyboard_valid"]
                )
                / len(eligible),
                4,
            )
            if eligible
            else None,
            "final_storyboard_quality_pass_rate": round(
                quality_pass["storyboard_valid"] / len(eligible), 4
            )
            if eligible
            else None,
            "average_execution_duration_s": _average(durations),
            "p95_execution_duration_s": round(_percentile(durations, 0.95), 3),
            "average_retries_per_workflow": _average([float(r) for r in retries]),
            "total_retry_decisions": retry_decisions,
            "reviewer_reask_total": reviewer_reasks,
            "punch_out_frequency": round(len(observed_punch) / len(cases), 4)
            if cases
            else 0.0,
            # Invocation, token and cost accounting (audit-derived)
            "total_model_invocations": invocations,
            "generation_invocations": gen_invocations,
            "reviewer_invocations": rev_invocations,
            "invocations_missing_token_usage": missing_tokens,
            "total_model_tokens": total_tokens if tokens_recorded else None,
            "generation_tokens": gen_tokens,
            "reviewer_tokens": rev_tokens,
            "total_billed_acus": round(billed_acus, 8) if billed_acus else 0.0,
            "billed_acus_per_step": {k: round(v, 8) for k, v in acus_step.items()},
            "billed_acus_per_gate": {k: round(v, 8) for k, v in acus_gate.items()},
            "invocations_with_cost": inv_with_cost,
            "invocations_missing_cost": inv_missing_cost,
            "cost_statuses": dict(cost_statuses),
            "cost_sources": dict(cost_sources),
            "total_estimated_usd": round(estimated_usd, 8) if estimated_usd else None,
            "total_actual_usd": round(actual_usd, 8) if actual_usd else None,
            "total_model_cost_usd": None,
            "cost_note": (
                "actual_usd is never reported by the provider. billed_acus come "
                "from per-invocation ATIF exports (status=actual); "
                "total_estimated_usd is the labelled acu_usd_rate conversion "
                "(config cost.acu_usd_rate), not billing data."
            ),
            # Audit completeness across evaluated runs
            "runs_with_audit": len(cases) - len(runs_missing_audit),
            "runs_missing_audit": runs_missing_audit,
            "runs_audit_incomplete": runs_audit_incomplete,
            "audit_completeness_rate": round(
                sum(
                    1
                    for c in cases
                    if audit_checks[c.case_id]["complete"] is True
                )
                / len(cases),
                4,
            )
            if cases
            else None,
        },
        "per_agent_failure_breakdown": per_agent_failure,
        "failure_class_breakdown": dict(failure_class_counts),
        "token_consumption_per_agent": {
            **{s: {"total_tokens": gen_tokens[s] or None} for s in LLM_STEPS},
            **{
                f"reviewer:{g}": {"total_tokens": rev_tokens[g] or None}
                for g in GATE_NAMES
            },
        },
        "excluded_runs": [
            {
                "case_id": c.case_id,
                "run_id": c.run_id,
                "reason": "harness_error" if c.run_id == "error" else "audit_missing",
            }
            for c in cases
            if c.run_id == "error" or not run_aggs[c.run_id]["audit_present"]
        ],
        "audit_checks_per_case": audit_checks,
        "failed_cases": [
            {
                "case_id": c.case_id,
                "split": c.split,
                "expected": c.expected,
                "actual_status": c.result.status.value,
                "failure_class": c.grading["failure_class"],
                "failure_code": c.result.failure_code,
                "failure_reason": c.result.failure_reason,
                "run_id": c.run_id,
            }
            for c in cases
            if not c.grading["pass"]
        ],
        "per_case_results": [
            {
                "case_id": c.case_id,
                "split": c.split,
                "category": c.category,
                "expected": c.expected,
                "run_id": c.run_id,
                "status": c.result.status.value,
                "exit_code": c.result.exit_code,
                "pass": bool(c.grading["pass"]),
                "end_to_end_success": c.grading["end_to_end_success"],
                "first_attempt_success": c.grading["first_attempt_success"],
                "retry_recovery": c.grading["retry_recovery"],
                "failure_class": c.grading["failure_class"],
                "gates_approved": c.grading["gates_approved"],
                "downstream_halted": c.grading["downstream_halted"],
                "storyboard_reviewer_approved": c.grading["storyboard_reviewer_approved"],
                "duration_s": c.duration_s,
                "fixture_hash": c.fixture_hash,
                "world_valid": c.quality["world_valid"],
                "characters_valid": c.quality["characters_valid"],
                "storyboard_valid": c.quality["storyboard_valid"],
                "failure_code": c.result.failure_code,
                "failure_reason": c.result.failure_reason,
                "punch_out_step": (
                    c.result.punch_out_records[0].step
                    if c.result.punch_out_records
                    else None
                ),
                "gate_decisions": dict(c.result.gate_decisions or {}),
                "model_invocations": run_aggs[c.run_id]["model_invocations"],
                "total_tokens": run_aggs[c.run_id]["total_tokens"] or None,
                "billed_acus": round(run_aggs[c.run_id]["billed_acus"], 8)
                if run_aggs[c.run_id]["billed_acus"]
                else None,
                "estimated_usd": round(run_aggs[c.run_id]["estimated_usd"], 8)
                if run_aggs[c.run_id]["estimated_usd"]
                else None,
                "audit_complete": audit_checks[c.case_id]["complete"],
            }
            for c in cases
        ],
    }
    return report


def _build_iteration_section(report: dict[str, Any]) -> str:
    """One dated, appendable section for evidence/iterations/workflow.md."""
    s = report["summary"]
    lines = [
        f"## Automated harness report — {report['generated_at']}",
        "",
        "### Run configuration",
        "",
        f"- **Dataset version:** {report['dataset']['version']}",
        f"- **Dataset SHA-256:** {report['dataset']['sha256']}",
        f"- **Runner version:** {report['runner']['version']}",
        f"- **Provider:** {report['runner']['provider']}",
        f"- **Model:** {report['runner']['model']}",
        f"- **Review:** enabled={report['runner'].get('review_enabled')} "
        f"mode={report['runner'].get('review_mode')} "
        f"model={report['runner'].get('review_model')} "
        f"models={report['runner'].get('review_models')}",
        f"- **Max attempts per step:** {report['runner']['max_attempts_per_step']}",
        "- **Prompt hashes:**",
    ]
    for step, h in report["runner"]["prompt_hashes"].items():
        lines.append(f"  - `{step}`: `{h}`")
    for gate, h in (report["runner"].get("reviewer_prompt_hashes") or {}).items():
        lines.append(f"  - `reviewer:{gate}`: `{h}`")
    lines.extend(
        [
            "",
            "### Headline metrics",
            "",
            f"- **Expected-outcome success rate:** {s['expected_outcome_success_rate']} "
            f"({s['expected_outcome_passed']}/{s['expected_outcome_total']})",
            f"- **Storyboard completion rate:** {s['storyboard_completion_rate']} "
            f"({s['storyboard_completed']}/{s['storyboard_eligible']})",
            f"- **Policy enforcement rate:** {s['policy_enforcement_rate']} "
            f"({s['policy_enforced']}/{s['policy_expected']})",
            f"- **End-to-end success rate:** {s['end_to_end_success_rate']}",
            f"- **First-pass success rate:** {s['first_pass_success_rate']}",
            f"- **Schema compliance rate:** {s['schema_compliance_rate']}",
            f"- **Final storyboard quality pass rate:** {s['final_storyboard_quality_pass_rate']}",
            f"- **Punch-outs observed/expected/unexpected:** "
            f"{s['punch_outs_observed']}/{s['punch_outs_expected']}/{s['punch_outs_unexpected']}",
            f"- **Model invocations:** {s['total_model_invocations']} "
            f"(generation {s['generation_invocations']}, reviewer {s['reviewer_invocations']})",
            f"- **Total model tokens:** {s['total_model_tokens']}",
            f"- **Total billed ACUs:** {s['total_billed_acus']}",
            f"- **Total estimated USD:** {s['total_estimated_usd']}",
            f"- **Average duration:** {s['average_execution_duration_s']} s",
            f"- **P95 duration:** {s['p95_execution_duration_s']} s",
            f"- **Average retries per workflow:** {s['average_retries_per_workflow']}",
            f"- **Audit completeness rate:** {s['audit_completeness_rate']}",
            "",
            "### Per-agent failure breakdown",
            "",
            "| Agent | Attempts | Failures | Failure rate | By class |",
            "|-------|----------|----------|--------------|----------|",
        ]
    )
    for step, stats in report["per_agent_failure_breakdown"].items():
        lines.append(
            f"| {step} | {stats['attempts']} | {stats['failures']} | "
            f"{stats['failure_rate']} | {stats.get('by_failure_class') or {}} |"
        )
    lines.extend(["", "### Failure analysis", ""])
    failed = report["failed_cases"]
    if failed:
        for f in failed:
            lines.append(
                f"- `{f['case_id']}` ({f['split']}): expected `{f['expected']}`, "
                f"got `{f['actual_status']}` [{f.get('failure_class')}] — "
                f"{f['failure_code']}: {f['failure_reason']}"
            )
    else:
        lines.append("No failed cases in this evaluation run.")
    if report.get("excluded_runs"):
        lines.extend(["", "### Excluded runs", ""])
        for x in report["excluded_runs"]:
            lines.append(f"- `{x['case_id']}` run `{x['run_id']}`: {x['reason']}")
    return "\n".join(lines)


def _archive_existing_evidence() -> Path | None:
    """Move the evidence files this harness regenerates into a timestamped
    archive before rewriting them; returns the archive dir (or None)."""
    existing = [
        rel for rel in PRESERVED_EVIDENCE_FILES if (EVIDENCE_DIR / rel).exists()
    ]
    if not existing:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = EVIDENCE_DIR / "archive" / stamp
    for rel in existing:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EVIDENCE_DIR / rel, target)
    return dest


def _write_evidence(cases: list[EvaluatedCase], wf_cfg: WorkflowConfig) -> dict[str, Any]:
    archive_dir = _archive_existing_evidence()
    dataset_version, dataset_hash = _dataset_version_and_hash(cases)
    prompt_hashes = _compute_prompt_hashes()
    reviewer_prompt_hashes = _compute_reviewer_prompt_hashes()

    report = _build_success_rate_report(
        cases,
        dataset_version,
        dataset_hash,
        wf_cfg,
        prompt_hashes,
        reviewer_prompt_hashes,
    )
    if archive_dir is not None:
        report["archived_previous_evidence"] = str(
            archive_dir.relative_to(REPO_ROOT)
            if archive_dir.is_relative_to(REPO_ROOT)
            else archive_dir
        )
    (EVIDENCE_DIR / "success_rate.json").write_text(
        _canonical_json(report) + "\n", encoding="utf-8"
    )

    _collect_audit_trail(cases, dataset_version)

    punch_records, punch_md = _build_punch_out_evidence(cases)
    (EVIDENCE_DIR / "punch_out_tests.json").write_text(
        _canonical_json(punch_records) + "\n", encoding="utf-8"
    )
    (EVIDENCE_DIR / "punch_out.md").write_text(punch_md + "\n", encoding="utf-8")

    # The iteration log is cumulative: append this run's section instead of
    # replacing the manually maintained history (the pre-write copy is also
    # preserved in the archive).
    iterations_path = EVIDENCE_DIR / "iterations" / "workflow.md"
    section = _build_iteration_section(report)
    if iterations_path.exists():
        prior = iterations_path.read_text(encoding="utf-8")
        iterations_path.write_text(prior.rstrip() + "\n\n" + section + "\n", encoding="utf-8")
    else:
        iterations_path.write_text(
            "# Workflow Evaluation Iterations\n\n" + section + "\n",
            encoding="utf-8",
        )

    return report


def _print_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("\n=== FictionForge End-to-End Workflow Evaluation ===")
    print(f"Dataset version:   {report['dataset']['version']}")
    print(f"Total cases:       {report['dataset']['total_cases']}")
    print(f"Eligible:          {report['dataset']['eligible_completion_cases']}")
    print(f"Expected-outcome:  {s['expected_outcome_success_rate']} "
          f"({s['expected_outcome_passed']}/{s['expected_outcome_total']})")
    print(f"Storyboard rate:   {s['storyboard_completion_rate']} "
          f"({s['storyboard_completed']}/{s['storyboard_eligible']})")
    print(f"Policy enforce:    {s['policy_enforcement_rate']} "
          f"({s['policy_enforced']}/{s['policy_expected']})")
    print(f"Completed:         {s['completed_workflows']}")
    print(f"Success rate:      {s['end_to_end_success_rate']}")
    print(f"First-pass rate:   {s['first_pass_success_rate']}")
    print(f"Schema compliance: {s['schema_compliance_rate']}")
    print(f"Punch-outs:        {s['punch_outs_observed']} observed "
          f"({s['punch_outs_unexpected']} unexpected)")
    print(f"Invocations:       {s['total_model_invocations']} "
          f"(gen {s['generation_invocations']} + rev {s['reviewer_invocations']})")
    print(f"Tokens:            {s['total_model_tokens']}")
    print(f"Billed ACUs:       {s['total_billed_acus']}  est. USD: {s['total_estimated_usd']}")
    print(f"Avg duration:      {s['average_execution_duration_s']} s")
    print(f"P95 duration:      {s['p95_execution_duration_s']} s")
    print(f"Avg retries:       {s['average_retries_per_workflow']}")
    print(f"Audit completeness:{s['audit_completeness_rate']}")
    if report["failed_cases"]:
        print("\nFailed cases:")
        for f in report["failed_cases"]:
            print(f"  - {f['case_id']}: {f['actual_status']} "
                  f"[{f.get('failure_class')}] ({f['failure_code']})")
    else:
        print("\nAll expected outcomes were observed.")
    if report.get("archived_previous_evidence"):
        print(f"\nPrevious evidence archived to {report['archived_previous_evidence']}")
    print("\nEvidence written to:")
    for name in (
        "evidence/success_rate.json",
        "evidence/punch_out_tests.json",
        "evidence/punch_out.md",
        "evidence/audit_trail.jsonl",
        "evidence/iterations/workflow.md",
    ):
        print(f"  - {name}")


def _print_run_plan(fixtures: list[dict[str, Any]], wf_cfg: WorkflowConfig) -> None:
    """Dry-run pre-flight report: what a live run would do, with no calls."""
    eval_cfg = _load_yaml(EVAL_CONFIG)
    version = eval_cfg.get("dataset", {}).get("version", "unknown")
    live = [c for c in fixtures if not c.get("playback") and c["expected"] == "completed"]
    playback = [c for c in fixtures if c.get("playback")]
    inert = [
        c
        for c in fixtures
        if not c.get("playback") and c["expected"] != "completed"
    ]
    gen_steps = len(LLM_STEPS)
    # Minimum: every eligible case runs 3 generation + 3 reviewer calls.
    min_calls = len(live) * (gen_steps + gen_steps)
    # Worst case: every step exhausts max_attempts and every reviewer call
    # exhausts its re-ask budget for every generation attempt.
    max_per_case = gen_steps * wf_cfg.max_attempts_per_step + gen_steps * (
        wf_cfg.max_attempts_per_step * max(1, wf_cfg.review_max_attempts)
    )
    max_calls = len(live) * max_per_case

    print("=== Workflow evaluation run plan (dry run — nothing executed) ===")
    print(f"Dataset version:   {version}")
    print(f"Cases selected:    {len(fixtures)}")
    for c in fixtures:
        kind = (
            "playback" if c.get("playback")
            else "live" if c["expected"] == "completed"
            else "deterministic"
        )
        print(
            f"  {c['case_id']}  split={c['split']}  expected={c['expected']}  "
            f"category={c['category']}  source={kind}"
        )
    print()
    print(f"Provider:          {wf_cfg.provider}")
    print(f"Generation model:  {wf_cfg.model}")
    print(f"Review:            enabled={wf_cfg.review_enabled} "
          f"mode={wf_cfg.review_mode} max_attempts={wf_cfg.review_max_attempts}")
    print(f"Reviewer models:   default={wf_cfg.review_model} "
          f"overrides={wf_cfg.review_models}")
    print(f"Step retry budget: {wf_cfg.max_attempts_per_step} attempts/step "
          f"(shared across validation, JSON, provider and reviewer retries)")
    print(f"ACU->USD rate:     {wf_cfg.acu_usd_rate} (estimated_usd only)")
    print()
    print("Generation prompt hashes:")
    for step, h in _compute_prompt_hashes().items():
        print(f"  {step}: {h}")
    print("Reviewer prompt hashes:")
    for gate, h in _compute_reviewer_prompt_hashes().items():
        print(f"  {gate}: {h}")
    print()
    print(f"Live-model cases:  {len(live)} "
          f"(playback: {len(playback)}, deterministic/no-model: {len(inert)})")
    print(f"Expected model invocations: min {min_calls} "
          f"(3 generation + 3 reviewer per eligible case), "
          f"worst-case bound {max_calls} with exhausted retry budgets")
    print()
    print("Outputs:")
    print(f"  runs:            {RUNS_DIR}/<run_id>/ (new dir per case; existing runs preserved)")
    print(f"  evidence:        {EVIDENCE_DIR}/success_rate.json, audit_trail.jsonl,")
    print(f"                   punch_out_tests.json, punch_out.md,")
    print(f"                   iterations/workflow.md (appended, not replaced)")
    print(f"  prior evidence:  preserved under {EVIDENCE_DIR}/archive/<utc>/ before rewrite")


def main(argv: list[str] | None = None) -> int:
    global EVIDENCE_DIR, RUNS_DIR
    parser = argparse.ArgumentParser(
        prog="run_workflow_evals.py",
        description="Run the FictionForge Stage 4 end-to-end workflow evaluation harness.",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        default=None,
        help="Which fixture splits to run (e.g. 'dev', 'holdout', 'all').",
    )
    parser.add_argument(
        "--case-ids",
        nargs="+",
        default=None,
        help="Run only the specified case IDs.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_WORKFLOW_CONFIG),
        help="Path to the workflow configuration YAML (default: config/workflow.yaml).",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["devin", "ollama"],
        help="Override the configured LLM provider for eligible completion cases.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the configured model identifier.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help="Override the number of retries per step.",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(EVIDENCE_DIR),
        help="Where to write evaluation evidence (default: evidence/).",
    )
    parser.add_argument(
        "--runs-dir",
        default=str(RUNS_DIR),
        help="Base directory for per-run outputs (default: runs/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the run plan (cases, config, expected invocations, output "
        "locations) without executing anything or writing evidence.",
    )
    args = parser.parse_args(argv)

    # Resolve global paths from CLI
    EVIDENCE_DIR = Path(args.evidence_dir)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "iterations").mkdir(exist_ok=True)
    RUNS_DIR = Path(args.runs_dir)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    wf_cfg = WorkflowConfig.from_yaml(args.config)
    eval_cfg = _load_yaml(EVAL_CONFIG)
    if args.provider:
        wf_cfg.provider = args.provider
    if args.model:
        wf_cfg.model = args.model
    if args.max_attempts is not None:
        wf_cfg.max_attempts_per_step = args.max_attempts

    # Use model from eval config if not otherwise set
    if not wf_cfg.model:
        wf_cfg.model = eval_cfg.get("runner", {}).get("model")

    # Determine splits
    splits = args.splits
    if splits and splits == ["all"]:
        splits = None

    fixtures = _discover_fixtures(splits)
    if args.case_ids:
        fixtures = [c for c in fixtures if c["case_id"] in args.case_ids]
    if not fixtures:
        print("No fixtures matched the requested filters.", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_run_plan(fixtures, wf_cfg)
        return 0

    eval_dir = EVIDENCE_DIR / "workflow_eval_runs"
    eval_dir.mkdir(parents=True, exist_ok=True)

    cases: list[EvaluatedCase] = []
    print(f"Running {len(fixtures)} workflow evaluation case(s)...")
    for case in fixtures:
        print(f"  {case['case_id']} ({case['split']}, expected={case['expected']}) ...", end=" ", flush=True)
        try:
            ev = _run_case(case, wf_cfg, eval_dir)
            print(ev.result.status.value)
        except Exception as exc:
            print(f"ERROR: {exc}")
            # Record a synthetic failure so the report still includes the case.
            synthetic = WorkflowResult(
                run_id="error",
                status=WorkflowStatus.FAILED_AUTOMATED,
                steps=[],
                brief=None,
                world=None,
                characters=None,
                storyboard=None,
                output_dir=eval_dir,
                started_at=0.0,
                ended_at=0.0,
                exit_code=1,
                failure_reason=str(exc),
                failure_code="EVAL_HARNESS_ERROR",
            )
            ev = EvaluatedCase(
                case_id=case["case_id"],
                split=case["split"],
                category=case["category"],
                expected=case["expected"],
                run_id="error",
                result=synthetic,
                quality={
                    "world_valid": False,
                    "characters_valid": False,
                    "storyboard_valid": False,
                    "world_issues": [],
                    "character_issues": [],
                    "storyboard_issues": [],
                },
                grading={
                    "end_to_end_success": False,
                    "first_attempt_success": False,
                    "retry_recovery": False,
                    "expected": case["expected"],
                    "actual_status": "failed_automated",
                    "exit_code": 1,
                    "failure_code": "EVAL_HARNESS_ERROR",
                    "failure_reason": str(exc),
                    "failure_class": "harness_error",
                    "gates_approved": None,
                    "downstream_halted": False,
                    "storyboard_reviewer_approved": None,
                    "pass": False,
                    "notes": ["Harness raised an exception"],
                },
                duration_s=0.0,
                brief_path=Path(""),
                fixture_hash=_fixture_file_hash(case),
            )
        cases.append(ev)

    report = _write_evidence(cases, wf_cfg)
    _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
