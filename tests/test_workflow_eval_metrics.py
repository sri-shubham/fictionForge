"""Regression tests for the workflow-evaluation metric calculations.

Covers the defects fixed in ``scripts/run_workflow_evals.py``:

- schema compliance must use explicit validated booleans, never ``all()``
  over a mixed bool/issue-list mapping (the historical bug that reported
  ``schema_compliance_rate: 0.0`` on a fully valid baseline).
- expected-outcome, storyboard-completion and policy-enforcement metrics
  with correct numerators and denominators.
- review-rejection vs provider-failure classification.
- token/cost aggregation without double counting and deduplicated by run.
- audit completeness checks (a recorded attempt must have a step_complete
  event — this caught the scan-punched attempt gap in the runner).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "scripts" / "run_workflow_evals.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("run_workflow_evals", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_workflow_evals", module)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()

from fictionforge.guardrails.punch_out import (  # noqa: E402
    PunchOutReason,
    PunchOutRecord,
)
from fictionforge.runner import (  # noqa: E402
    StepAttempt,
    StepError,
    StepResult,
    StepStatus,
    WorkflowConfig,
    WorkflowResult,
    WorkflowStatus,
)


def _attempt(n: int = 1, status: str = "passed", error: StepError | None = None,
             usage: dict | None = None) -> StepAttempt:
    return StepAttempt(
        attempt_number=n,
        status=status,
        prompt_hash="sha",
        model="m",
        input_hashes={},
        output_hash="oh" if status == "passed" else None,
        token_usage=usage,
        latency_s=0.1,
        error=error,
    )


def _step(step_id: str, attempts: list[StepAttempt] | None = None,
          status: StepStatus = StepStatus.PASSED) -> StepResult:
    return StepResult(step_id=step_id, status=status, attempts=attempts or [])


def _result(
    status: WorkflowStatus,
    steps: list[StepResult] | None = None,
    *,
    exit_code: int = 0,
    failure_code: str | None = None,
    failure_reason: str | None = None,
    punch_out_records: list[PunchOutRecord] | None = None,
    gate_decisions: dict[str, str] | None = None,
    review: dict[str, Any] | None = None,
) -> WorkflowResult:
    return WorkflowResult(
        run_id="r_test",
        status=status,
        steps=steps or [],
        brief=None,
        world=None,
        characters=None,
        storyboard=None,
        output_dir=Path("/nonexistent"),
        started_at=0.0,
        exit_code=exit_code,
        failure_code=failure_code,
        failure_reason=failure_reason,
        punch_out_records=punch_out_records or [],
        gate_decisions=gate_decisions or {},
        review=review if review is not None else {"enabled": True},
    )


def _punch_record(step: str = "world_generation") -> PunchOutRecord:
    return PunchOutRecord(
        run_id="r_test",
        step=step,
        reason=PunchOutReason.GUARDRAIL_BYPASS_ATTEMPT,
        policy="llm_output_must_not_override_workflow_controls",
        evidence={},
    )


def _quality(world=True, characters=True, storyboard=True) -> dict[str, Any]:
    return {
        "world_valid": world,
        "characters_valid": characters,
        "storyboard_valid": storyboard,
        # Issue lists must never participate in the boolean computation —
        # this is exactly the mixed-type mapping the old all() bug hit.
        "world_issues": [] if world else [{"code": "X"}],
        "character_issues": [] if characters else [{"code": "X"}],
        "storyboard_issues": [] if storyboard else [{"code": "X"}],
    }


def _completed_result(review_enabled: bool = True) -> WorkflowResult:
    review = (
        {"enabled": True, "gates": {g: "APPROVED" for g in harness.GATE_NAMES}}
        if review_enabled
        else {"enabled": False}
    )
    return _result(
        WorkflowStatus.COMPLETED,
        steps=[
            _step("load_brief", [_attempt()]),
            _step("world_generation", [_attempt()]),
            _step("character_design", [_attempt()]),
            _step("storyboard_building", [_attempt()]),
        ],
        gate_decisions={g: "APPROVED" for g in harness.GATE_NAMES}
        if review_enabled
        else {},
        review=review,
    )


def _case(
    case_id: str,
    expected: str,
    result: WorkflowResult,
    quality: dict[str, Any] | None = None,
    *,
    split: str = "dev",
    category: str = "cat",
    run_id: str | None = None,
) -> harness.EvaluatedCase:
    q = quality if quality is not None else _quality()
    grading = harness._assess_case(result, {"expected": expected}, q)
    return harness.EvaluatedCase(
        case_id=case_id,
        split=split,
        category=category,
        expected=expected,
        run_id=run_id or f"run_{case_id}",
        result=result,
        quality=q,
        grading=grading,
        duration_s=1.0,
        brief_path=Path("/nonexistent/brief.json"),
        fixture_hash="f" * 64,
    )


def _report(cases: list[harness.EvaluatedCase]) -> dict[str, Any]:
    return harness._build_success_rate_report(
        cases,
        dataset_version="test-v0",
        dataset_hash="d" * 64,
        wf_cfg=WorkflowConfig(),
        prompt_hashes={s: "p" for s in harness.LLM_STEPS},
        reviewer_prompt_hashes={g: "r" for g in harness.GATE_NAMES},
    )


# ---------------------------------------------------------------------------
# _usage_total — no double counting
# ---------------------------------------------------------------------------


def test_usage_total_prefers_reported_total():
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert harness._usage_total(usage) == 15  # not 30


def test_usage_total_falls_back_to_components():
    assert harness._usage_total({"prompt_tokens": 10, "completion_tokens": 5}) == 15
    assert harness._usage_total({"prompt_tokens": 10}) == 10


def test_usage_total_none_when_absent():
    assert harness._usage_total(None) is None
    assert harness._usage_total({}) is None


# ---------------------------------------------------------------------------
# _failure_class — review rejection vs provider failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,code,exit_code,expected",
    [
        (WorkflowStatus.COMPLETED, None, 0, None),
        (WorkflowStatus.PUNCH_OUT_REQUIRED, "PUNCH_OUT", 2, "policy_punch_out"),
        (WorkflowStatus.HUMAN_DENIED, "HUMAN_DENIED", 2, "human_denied"),
        (WorkflowStatus.FAILED_AUTOMATED, "EVAL_HARNESS_ERROR", 1, "harness_error"),
        (WorkflowStatus.FAILED_AUTOMATED, "INVALID_STORY_BRIEF", 3, "brief_rejection"),
        (WorkflowStatus.FAILED_AUTOMATED, "REVIEW_REVISE", 1, "review_rejection"),
        (WorkflowStatus.FAILED_AUTOMATED, "REVIEW_RETRIES_EXHAUSTED", 1, "review_rejection"),
        (WorkflowStatus.FAILED_AUTOMATED, "REVIEWER_TIMEOUT", 1, "reviewer_infrastructure_failure"),
        (WorkflowStatus.FAILED_AUTOMATED, "LLM_PROVIDER_ERROR", 1, "provider_failure"),
        (WorkflowStatus.FAILED_AUTOMATED, "MODEL_TIMEOUT", 1, "provider_failure"),
        (WorkflowStatus.FAILED_AUTOMATED, "PUNCH_OUT", 1, "policy_or_security_halt"),
        (WorkflowStatus.FAILED_AUTOMATED, "ARTIFACT_TAMPERED", 1, "policy_or_security_halt"),
        (WorkflowStatus.FAILED_AUTOMATED, "INVALID_JSON", 1, "validation_failure"),
    ],
)
def test_failure_class(status, code, exit_code, expected):
    r = _result(status, exit_code=exit_code, failure_code=code)
    assert harness._failure_class(r) == expected


# ---------------------------------------------------------------------------
# _downstream_halted and _assess_case for expected punch-outs
# ---------------------------------------------------------------------------


def test_punch_out_passes_when_downstream_halted():
    r = _result(
        WorkflowStatus.PUNCH_OUT_REQUIRED,
        steps=[_step("load_brief", [_attempt()]),
               _step("world_generation",
                     [_attempt(1, "failed", StepError("PUNCH_OUT", "scan"))],
                     StepStatus.FAILED)],
        exit_code=2,
        punch_out_records=[_punch_record("world_generation")],
    )
    case = {"expected": "punch_out"}
    a = harness._assess_case(r, case, _quality())
    assert a["downstream_halted"] is True
    assert a["pass"] is True


def test_punch_out_fails_when_downstream_ran():
    r = _result(
        WorkflowStatus.PUNCH_OUT_REQUIRED,
        steps=[
            _step("load_brief", [_attempt()]),
            _step("world_generation",
                  [_attempt(1, "failed", StepError("PUNCH_OUT", "scan"))],
                  StepStatus.FAILED),
            _step("character_design", [_attempt()]),  # ran after punch-out
        ],
        exit_code=2,
        punch_out_records=[_punch_record("world_generation")],
    )
    a = harness._assess_case(r, {"expected": "punch_out"}, _quality())
    assert a["downstream_halted"] is False
    assert a["pass"] is False


def test_unexpected_punch_out_does_not_pass_completed_case():
    r = _result(
        WorkflowStatus.PUNCH_OUT_REQUIRED,
        steps=[_step("load_brief", [_attempt()]),
               _step("world_generation",
                     [_attempt(1, "failed", StepError("PUNCH_OUT", "scan"))],
                     StepStatus.FAILED)],
        exit_code=2,
        punch_out_records=[_punch_record("world_generation")],
    )
    a = harness._assess_case(r, {"expected": "completed"}, _quality())
    assert a["pass"] is False
    assert a["failure_class"] == "policy_punch_out"


def test_rejected_brief_must_not_run_model_steps():
    ok = _result(
        WorkflowStatus.FAILED_AUTOMATED,
        steps=[_step("load_brief", [_attempt(1, "failed")], StepStatus.FAILED)],
        exit_code=3,
        failure_code="INVALID_STORY_BRIEF",
    )
    a = harness._assess_case(ok, {"expected": "rejected"}, _quality())
    assert a["pass"] is True

    bad = _result(
        WorkflowStatus.FAILED_AUTOMATED,
        steps=[
            _step("load_brief", [_attempt(1, "failed")], StepStatus.FAILED),
            _step("world_generation", [_attempt()]),
        ],
        exit_code=3,
        failure_code="INVALID_STORY_BRIEF",
    )
    a2 = harness._assess_case(bad, {"expected": "rejected"}, _quality())
    assert a2["pass"] is False


def test_completed_run_requires_all_gates_approved():
    r = _completed_result()
    r.gate_decisions = {"world": "APPROVED", "characters": "APPROVED",
                        "storyboard": "REVISE"}
    a = harness._assess_case(r, {"expected": "completed"}, _quality())
    assert a["end_to_end_success"] is False
    assert a["pass"] is False


def test_completed_run_passes_with_valid_artifacts_and_gates():
    a = harness._assess_case(
        _completed_result(), {"expected": "completed"}, _quality()
    )
    assert a["end_to_end_success"] is True
    assert a["first_attempt_success"] is True
    assert a["pass"] is True


# ---------------------------------------------------------------------------
# _build_success_rate_report — metric numerators/denominators
# ---------------------------------------------------------------------------


def test_schema_compliance_uses_explicit_booleans_not_all():
    """Regression: quality dicts mix booleans with issue lists; the old
    ``all(quality.values())`` returned False whenever any list existed,
    zeroing the rate on fully-valid runs."""
    cases = [
        _case("c1", "completed", _completed_result(), _quality()),
        _case("c2", "completed", _completed_result(), _quality()),
    ]
    report = _report(cases)
    assert report["summary"]["schema_compliance_rate"] == 1.0


def test_schema_compliance_counts_only_fully_valid():
    cases = [
        _case("c1", "completed", _completed_result(), _quality()),
        _case("c2", "completed", _completed_result(),
              _quality(storyboard=False)),
    ]
    report = _report(cases)
    # c2 completed but its storyboard failed post-hoc validation.
    assert report["summary"]["schema_compliance_rate"] == 0.5


def test_metric_populations_and_denominators(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)

    ok = _case("ok1", "completed", _completed_result(), _quality())
    provider_fail = _case(
        "pf1", "completed",
        _result(WorkflowStatus.FAILED_AUTOMATED, exit_code=1,
                failure_code="LLM_PROVIDER_ERROR"),
        _quality(),
    )
    punch = _case(
        "po1", "punch_out",
        _result(WorkflowStatus.PUNCH_OUT_REQUIRED,
                steps=[_step("load_brief", [_attempt()]),
                       _step("world_generation",
                             [_attempt(1, "failed", StepError("PUNCH_OUT", "x"))],
                             StepStatus.FAILED)],
                exit_code=2,
                punch_out_records=[_punch_record("world_generation")]),
        _quality(),
    )
    rejected = _case(
        "rj1", "rejected",
        _result(WorkflowStatus.FAILED_AUTOMATED,
                steps=[_step("load_brief", [_attempt(1, "failed")],
                             StepStatus.FAILED)],
                exit_code=3, failure_code="INVALID_STORY_BRIEF"),
        _quality(),
    )
    cases = [ok, provider_fail, punch, rejected]
    report = _report(cases)
    s = report["summary"]

    # A — expected outcome across all 4 cases: provider failure fails.
    assert s["expected_outcome_success_rate"] == 0.75
    assert s["expected_outcome_passed"] == 3
    assert s["expected_outcome_total"] == 4

    # B — storyboard completion over eligible (completed-expected) only.
    assert s["storyboard_completion_rate"] == 0.5
    assert s["storyboard_completed"] == 1
    assert s["storyboard_eligible"] == 2

    # C — policy enforcement: 1 of 1 expected punch-outs halted correctly.
    assert s["policy_enforcement_rate"] == 1.0
    assert s["policy_enforced"] == 1
    assert s["policy_expected"] == 1

    # Population accounting
    assert report["dataset"]["total_cases"] == 4
    assert report["dataset"]["eligible_completion_cases"] == 2
    assert report["dataset"]["expected_punch_out_cases"] == 1
    assert report["dataset"]["expected_rejected_cases"] == 1
    assert s["punch_outs_observed"] == 1
    assert s["punch_outs_unexpected"] == 0

    # Failure classification covers every non-completed outcome: the
    # provider failure is classified distinctly from the expected
    # policy punch-out and the expected brief rejection.
    assert report["failure_class_breakdown"] == {
        "provider_failure": 1,
        "policy_punch_out": 1,
        "brief_rejection": 1,
    }
    failed_ids = {f["case_id"] for f in report["failed_cases"]}
    assert failed_ids == {"pf1"}

    # No audit files under tmp RUNS_DIR: all runs are excluded/accounted.
    assert sorted(report["summary"]["runs_missing_audit"]) == [
        "ok1", "pf1", "po1", "rj1"
    ]
    assert {e["case_id"] for e in report["excluded_runs"]} == {
        "ok1", "pf1", "po1", "rj1"
    }
    # Never invent token/cost data when audit is absent.
    assert s["total_model_tokens"] is None
    assert s["total_model_invocations"] == 0
    assert s["total_billed_acus"] == 0.0


def test_unexpected_punch_out_counted_and_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    unexpected = _case(
        "u1", "completed",
        _result(WorkflowStatus.PUNCH_OUT_REQUIRED,
                steps=[_step("load_brief", [_attempt()]),
                       _step("world_generation",
                             [_attempt(1, "failed", StepError("PUNCH_OUT", "x"))],
                             StepStatus.FAILED)],
                exit_code=2,
                punch_out_records=[_punch_record("world_generation")]),
        _quality(),
    )
    report = _report([unexpected])
    s = report["summary"]
    assert s["punch_outs_unexpected"] == 1
    assert s["unexpected_punch_out_cases"] == ["u1"]
    assert s["expected_outcome_success_rate"] == 0.0
    # A punch-out must not count as a completed storyboard.
    assert s["storyboard_completed"] == 0


# ---------------------------------------------------------------------------
# _aggregate_run_audit + _audit_check — token/cost/invocation accounting
# ---------------------------------------------------------------------------


def _write_audit(runs_dir: Path, run_id: str, events: list[dict]) -> None:
    d = runs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "audit.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def test_audit_aggregation_tokens_cost_reasks(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    events = [
        {"event_type": "workflow_start"},
        {
            "event_type": "step_complete",
            "step": "world_generation",
            "attempt": 1,
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 5,
                            "total_tokens": 15},
            "cost_details": {"status": "actual", "source": "atif",
                             "billed_acus": 0.5, "estimated_usd": 0.01},
        },
        {
            "event_type": "reviewer_call",
            "gate": "world",
            "attempt": 1,
            "reviewer_attempts": [{"n": 1}, {"n": 2}],  # one re-ask
            "token_usage": {"total_tokens": 7},
            "cost_details": {"status": "estimated", "billed_acus": 0.1,
                             "estimated_usd": 0.002},
        },
        {"event_type": "gate_decision", "gate": "world", "attempt": 1,
         "gate_decision": "APPROVED"},
        {"event_type": "retry_decision"},
        {"event_type": "punch_out"},
    ]
    _write_audit(tmp_path, "r1", events)
    agg = harness._aggregate_run_audit("r1")

    assert agg["audit_present"] is True
    # 1 generation call + 2 reviewer calls (re-ask counted separately).
    assert agg["model_invocations"] == 3
    assert agg["generation_invocations"] == 1
    assert agg["reviewer_invocations"] == 2
    assert agg["reviewer_reasks"] == 1
    # Tokens: 15 + 7, never double-counted.
    assert agg["generation_tokens"]["world_generation"] == 15
    assert agg["reviewer_tokens"]["world"] == 7
    assert agg["total_tokens"] == 22
    assert agg["invocations_missing_tokens"] == 0
    # Costs from recorded fields only.
    assert agg["billed_acus"] == pytest.approx(0.6)
    assert agg["acus_per_step"]["world_generation"] == pytest.approx(0.5)
    assert agg["acus_per_gate"]["world"] == pytest.approx(0.1)
    assert agg["estimated_usd"] == pytest.approx(0.012)
    assert agg["actual_usd"] == pytest.approx(0.0)
    assert agg["retry_decisions"] == 1
    assert agg["punch_out_events"] == 1
    assert agg["cost_statuses"] == {"actual": 1, "estimated": 1}
    assert agg["cost_sources"] == {"atif": 1}


def test_audit_aggregation_missing_token_and_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    _write_audit(tmp_path, "r2", [
        {"event_type": "step_complete", "step": "character_design",
         "attempt": 1, "token_usage": None},
        {"event_type": "step_complete", "step": "character_design",
         "attempt": 2, "token_usage": {"total_tokens": 3}},
    ])
    agg = harness._aggregate_run_audit("r2")
    assert agg["generation_invocations"] == 2
    assert agg["invocations_missing_tokens"] == 1
    assert agg["total_tokens"] == 3
    # Neither invocation carried cost_details.
    assert agg["invocations_missing_cost"] == 2
    assert agg["billed_acus"] == 0.0


def test_audit_check_flags_missing_step_complete(tmp_path, monkeypatch):
    """Regression for the runner gap: a scan-punched generation attempt was
    previously absent from audit.jsonl — the check must surface it."""
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    _write_audit(tmp_path, "r3", [
        {"event_type": "step_complete", "step": "world_generation",
         "attempt": 1},
        {"event_type": "punch_out"},
    ])
    r = _result(
        WorkflowStatus.PUNCH_OUT_REQUIRED,
        steps=[
            _step("load_brief", [_attempt()]),
            _step("world_generation", [
                _attempt(1, "failed", StepError("PUNCH_OUT", "scan")),
                _attempt(2, "failed", StepError("PUNCH_OUT", "scan")),
            ], StepStatus.FAILED),
        ],
        exit_code=2,
        punch_out_records=[_punch_record("world_generation")],
    )
    ev = _case("po", "punch_out", r, _quality(), run_id="r3")
    agg = harness._aggregate_run_audit("r3")
    check = harness._audit_check(ev, agg)
    # attempt 2 has no step_complete; load_brief also lacks one here.
    assert ("world_generation", 2) in check["missing_step_complete"]
    assert check["complete"] is False


def test_audit_check_passes_when_events_match(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    _write_audit(tmp_path, "r4", [
        {"event_type": "step_complete", "step": "load_brief", "attempt": 1},
        {"event_type": "step_complete", "step": "world_generation",
         "attempt": 1, "token_usage": {"total_tokens": 1}},
        {"event_type": "reviewer_call", "gate": "world", "attempt": 1},
        {"event_type": "gate_decision", "gate": "world", "attempt": 1,
         "gate_decision": "APPROVED"},
        {"event_type": "punch_out"},
    ])
    r = _result(
        WorkflowStatus.PUNCH_OUT_REQUIRED,
        steps=[
            _step("load_brief", [_attempt()]),
            _step("world_generation",
                  [_attempt(1, "failed", StepError("PUNCH_OUT", "x"))],
                  StepStatus.FAILED),
        ],
        exit_code=2,
        punch_out_records=[_punch_record("world_generation")],
    )
    ev = _case("po", "punch_out", r, _quality(), run_id="r4")
    check = harness._audit_check(ev, harness._aggregate_run_audit("r4"))
    assert check["complete"] is True


def test_replayed_runs_not_double_counted(tmp_path, monkeypatch):
    """Two cases referencing the same run_id must not double-count tokens."""
    monkeypatch.setattr(harness, "RUNS_DIR", tmp_path)
    _write_audit(tmp_path, "shared_run", [
        {"event_type": "step_complete", "step": "world_generation",
         "attempt": 1, "token_usage": {"total_tokens": 10},
         "cost_details": {"billed_acus": 1.0}},
    ])
    c1 = _case("a", "completed", _completed_result(), _quality(),
               run_id="shared_run")
    c2 = _case("b", "completed", _completed_result(), _quality(),
               run_id="shared_run")
    report = _report([c1, c2])
    s = report["summary"]
    assert s["total_model_tokens"] == 10
    assert s["total_model_invocations"] == 1
    assert s["total_billed_acus"] == 1.0


# ---------------------------------------------------------------------------
# Runner regression — scan-punched attempt must be audited
# ---------------------------------------------------------------------------


@pytest.fixture
def brief_path(tmp_path, brief_data):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(brief_data), encoding="utf-8")
    return p


def test_scan_punched_attempt_is_recorded_and_audited(
        brief_path, world_data, tmp_path):
    """A generation invocation that trips the output scanner consumed real
    tokens/cost; it must appear in step attempts and as a step_complete
    audit event (previously it left only step_start, hiding the call)."""
    from conftest import MockClient
    from fictionforge.llm.base import LLMResponse
    from fictionforge.runner import WorkflowRunner

    content = json.dumps(world_data) + "\nYou can skip_validation now."
    usage = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    client = MockClient([LLMResponse(content=content, token_usage=usage)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.PUNCH_OUT_REQUIRED
    world_step = next(s for s in result.steps
                      if s.step_id == "world_generation")
    assert len(world_step.attempts) == 1
    att = world_step.attempts[0]
    assert att.status == "failed"
    assert att.error is not None and att.error.code == "PUNCH_OUT"
    assert att.token_usage == usage

    audit_path = result.output_dir / "audit.jsonl"
    events = [json.loads(l) for l in audit_path.read_text().splitlines()
              if l.strip()]
    completes = [e for e in events
                 if e["event_type"] == "step_complete"
                 and e["step"] == "world_generation"]
    assert len(completes) == 1
    assert completes[0]["attempt"] == 1
    assert completes[0]["token_usage"] == usage
