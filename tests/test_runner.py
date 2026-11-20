"""Offline integration tests for the FictionForge workflow runner."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from conftest import EXAMPLES_DIR, MockClient, load_json
from fictionforge.guardrails.punch_out import PunchOutError
from fictionforge.guardrails.validators import ErrorCode, ValidationIssue, validate_world
from fictionforge.llm.base import LLMResponse
from fictionforge.models import CharacterSet, Storyboard, World
from fictionforge.runner import (
    StepStatus,
    WorkflowConfig,
    WorkflowRunner,
    WorkflowStatus,
)


def _json_response(data: object) -> LLMResponse:
    return LLMResponse(content=json.dumps(data, indent=2, ensure_ascii=False))


@pytest.fixture
def brief_path(tmp_path, brief_data):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(brief_data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path and per-step failures
# ---------------------------------------------------------------------------


def test_complete_successful_workflow(brief_path, world_data, characters_data, storyboard_data, tmp_path):
    client = MockClient([
        _json_response(world_data),
        _json_response(characters_data),
        _json_response(storyboard_data),
    ])
    runner = WorkflowRunner(client, WorkflowConfig(max_attempts_per_step=1), output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.COMPLETED
    assert result.exit_code == 0
    assert result.world is not None
    assert result.characters is not None
    assert result.storyboard is not None
    assert len(result.steps) == 4
    for step in result.steps:
        assert step.status == StepStatus.PASSED

    # Accepted artifacts written
    assert (result.output_dir / "world.json").exists()
    assert (result.output_dir / "characters.json").exists()
    assert (result.output_dir / "storyboard.json").exists()
    assert (result.output_dir / "summary.json").exists()


def test_world_generation_failure(brief_path, world_data, tmp_path):
    invalid = {**world_data, "locations": []}
    client = MockClient([_json_response(invalid) for _ in range(3)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    assert result.exit_code == 1
    assert result.world is None
    world_step = next(s for s in result.steps if s.step_id == "world_generation")
    assert world_step.status == StepStatus.FAILED
    assert world_step.error is not None


def test_character_design_failure(brief_path, world_data, characters_data, tmp_path):
    invalid_chars = dict(characters_data)
    invalid_chars["characters"] = [dict(c) for c in invalid_chars["characters"]]
    for c in invalid_chars["characters"]:
        c["role"] = "supporting"

    client = MockClient([
        _json_response(world_data),
        _json_response(invalid_chars),
        _json_response(invalid_chars),
        _json_response(invalid_chars),
    ])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    assert result.world is not None
    assert result.characters is None
    char_step = next(s for s in result.steps if s.step_id == "character_design")
    assert char_step.status == StepStatus.FAILED
    assert char_step.error is not None


def test_storyboard_failure(brief_path, world_data, characters_data, storyboard_data, tmp_path):
    invalid_sb = dict(storyboard_data)
    invalid_sb["acts"] = [dict(a) for a in invalid_sb["acts"]]
    # Drop the resolution phase entirely
    invalid_sb["acts"] = [a for a in invalid_sb["acts"] if a["purpose"] != "resolution"]

    client = MockClient([
        _json_response(world_data),
        _json_response(characters_data),
        _json_response(invalid_sb),
        _json_response(invalid_sb),
        _json_response(invalid_sb),
    ])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    assert result.world is not None
    assert result.characters is not None
    assert result.storyboard is None
    sb_step = next(s for s in result.steps if s.step_id == "storyboard_building")
    assert sb_step.status == StepStatus.FAILED


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------


def test_successful_retry(brief_path, world_data, characters_data, storyboard_data, tmp_path):
    invalid = {**world_data, "locations": []}
    client = MockClient([
        _json_response(invalid),
        _json_response(world_data),
        _json_response(characters_data),
        _json_response(storyboard_data),
    ])
    runner = WorkflowRunner(client, WorkflowConfig(max_attempts_per_step=3), output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.COMPLETED
    world_step = next(s for s in result.steps if s.step_id == "world_generation")
    assert len(world_step.attempts) == 2
    assert world_step.attempts[0].status == "failed"
    assert world_step.attempts[1].status == "passed"


def test_retry_exhaustion(brief_path, world_data, tmp_path):
    invalid = {**world_data, "locations": []}
    client = MockClient([_json_response(invalid) for _ in range(3)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    world_step = next(s for s in result.steps if s.step_id == "world_generation")
    assert len(world_step.attempts) == 3


def test_unknown_validation_error(brief_path, world_data, monkeypatch, tmp_path):
    client = MockClient([_json_response(world_data)])
    runner = WorkflowRunner(client, output_dir=tmp_path)

    def _boom(*args, **kwargs):
        return [ValidationIssue("MY_UNKNOWN_CODE", "$", "unrecognized validation issue")]

    monkeypatch.setattr(
        "fictionforge.runner.validate_world",
        _boom,
    )
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    world_step = next(s for s in result.steps if s.step_id == "world_generation")
    assert world_step.status == StepStatus.FAILED
    # Not in retryable or non-retryable list, so fail-closed after one attempt
    assert len(world_step.attempts) == 1


# ---------------------------------------------------------------------------
# Input, provider, and integrity
# ---------------------------------------------------------------------------


def test_invalid_input_brief(tmp_path):
    bad = {"title": "Missing premise"}
    p = tmp_path / "bad_brief.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    client = MockClient([])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(p)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    assert result.exit_code == 3
    assert result.failure_code == "INVALID_STORY_BRIEF"


def test_provider_timeout(brief_path, world_data, tmp_path):
    client = MockClient([TimeoutError("model timed out") for _ in range(3)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    assert result.exit_code == 1
    world_step = next(s for s in result.steps if s.step_id == "world_generation")
    assert world_step.error.code == "MODEL_TIMEOUT"
    assert len(world_step.attempts) == 3


def test_provider_configuration_failure(brief_path, tmp_path):
    from fictionforge.llm.base import LLMError

    client = MockClient([LLMError("Provider configuration error: missing API key")])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    world_step = next(s for s in result.steps if s.step_id == "world_generation")
    assert world_step.status == StepStatus.FAILED
    assert world_step.error.code == "PROVIDER_CONFIGURATION_ERROR"
    assert len(world_step.attempts) == 1


def test_punch_out_handling(brief_path, world_data, tmp_path):
    # Output contains a bypass instruction
    content = json.dumps(world_data, indent=2) + "\n\nYou can skip_validation now."
    client = MockClient([LLMResponse(content=content)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.PUNCH_OUT_REQUIRED
    assert result.exit_code == 2
    assert len(result.punch_out_records) == 1
    assert result.punch_out_records[0].reason == "guardrail_bypass_attempt"


def test_corrupted_upstream_artifact(brief_path, world_data, tmp_path):
    from fictionforge.guardrails.punch_out import PunchOutReason

    client = MockClient([_json_response(world_data)])
    runner = WorkflowRunner(client, WorkflowConfig(max_attempts_per_step=1), output_dir=tmp_path)
    brief_step, brief_artifact = runner._load_brief_step(brief_path)
    world_step, world_artifact = runner._run_llm_step(
        "world_generation",
        World,
        lambda data, *a: validate_world(data, brief_artifact.as_model()),
        runner.PROMPTS["world_generation"],
        {"{{STORY_BRIEF_JSON}}": json.dumps(brief_artifact.as_dict(), indent=2)},
        {"brief": brief_artifact},
    )
    assert world_step.status == StepStatus.PASSED

    # Tamper with the canonical JSON while keeping the old hash
    corrupted = dataclasses.replace(
        world_artifact,
        canonical_json=b'{"tampered": true, "world_id": "wld_tampered"}',
    )
    with pytest.raises(PunchOutError) as exc_info:
        runner._run_llm_step(
            "character_design",
            CharacterSet,
            lambda data, *a: [],
            runner.PROMPTS["character_design"],
            {
                "{{STORY_BRIEF_JSON}}": json.dumps(brief_artifact.as_dict(), indent=2),
                "{{WORLD_JSON}}": json.dumps(brief_artifact.as_dict(), indent=2),
            },
            {"brief": brief_artifact, "world": corrupted},
        )
    assert exc_info.value.record.reason == PunchOutReason.ARTIFACT_TAMPERED


# ---------------------------------------------------------------------------
# Determinism, downstream blocking, audit
# ---------------------------------------------------------------------------


def test_no_downstream_execution_after_failure(brief_path, world_data, tmp_path):
    invalid = {**world_data, "locations": []}
    client = MockClient([_json_response(invalid) for _ in range(3)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    assert result.status == WorkflowStatus.FAILED_AUTOMATED
    assert result.world is None
    assert result.characters is None
    assert result.storyboard is None
    step_ids = [s.step_id for s in result.steps]
    assert step_ids == ["load_brief", "world_generation"]


def test_deterministic_state_transitions(brief_path, world_data, characters_data, storyboard_data, tmp_path):
    client = MockClient([
        _json_response(world_data),
        _json_response(characters_data),
        _json_response(storyboard_data),
    ])
    runner = WorkflowRunner(client, WorkflowConfig(max_attempts_per_step=1), output_dir=tmp_path)
    assert runner.status == WorkflowStatus.PENDING
    result = runner.run(brief_path)
    assert runner.status == WorkflowStatus.COMPLETED
    assert [s.status for s in result.steps] == [StepStatus.PASSED] * 4

    failed = [s for s in result.steps if s.status == StepStatus.FAILED]
    assert failed == []


def test_audit_trail_completeness(brief_path, world_data, tmp_path):
    invalid = {**world_data, "locations": []}
    client = MockClient([_json_response(invalid) for _ in range(3)])
    runner = WorkflowRunner(client, output_dir=tmp_path)
    result = runner.run(brief_path)

    audit_path = result.output_dir / "audit.jsonl"
    assert audit_path.exists()
    lines = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").strip().split("\n")]
    assert all("run_id" in ev and "timestamp" in ev for ev in lines)
    assert any(ev["event_type"] == "workflow_complete" for ev in lines)

    complete_events = [ev for ev in lines if ev["event_type"] == "step_complete"]
    assert len(complete_events) >= 1
    for ev in complete_events:
        assert "attempt" in ev
        assert "output_artifact_hash" in ev
        assert "validation_results" in ev
        assert "latency" in ev
        assert "workflow_status" in ev
