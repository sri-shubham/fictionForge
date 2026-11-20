"""Offline tests for Devin session tracking and invocation-level audit fields.

No model calls: the ``devin`` binary is never executed.  CLI behaviour is
mocked at ``subprocess.run``; ATIF exports are fabricated files matching the
real ATIF-v1.7 schema observed on disk.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import MockClient
from fictionforge.guardrails.review import (
    AdversarialReviewer,
    default_reviewer_configs,
)
from fictionforge.llm.base import LLMError, LLMResponse
from fictionforge.llm.devin import DevinCliClient, classify_session_id
from fictionforge.observability.audit import AuditLogger
from fictionforge.runner import (
    WorkflowConfig,
    WorkflowRunner,
    WorkflowStatus,
)


@pytest.fixture
def brief_path(tmp_path, brief_data):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(brief_data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fixtures: fabricated ATIF exports + fake CLI
# ---------------------------------------------------------------------------

def _atif(
    session_id: str | None = "able-baker",
    *,
    prompt_tokens: int = 12000,
    completion_tokens: int = 2500,
    cached_tokens: int = 3000,
    model_name: str = "fusion-claude-sonnet-5-5-medium",
    metrics: bool = True,
) -> dict[str, Any]:
    """Fabricated ATIF-v1.7 export matching the real on-disk schema."""
    doc: dict[str, Any] = {
        "schema_version": "ATIF-v1.7",
        "agent": {
            "name": "devin",
            "version": "3000.12.43",
            "model_name": model_name,
            "tool_definitions": [],
            "extra": {"backend": "Windsurf", "permission_mode": "Normal"},
        },
        "steps": [],
    }
    if session_id is not None:
        doc["session_id"] = session_id
    if metrics:
        doc["final_metrics"] = {
            "total_prompt_tokens": prompt_tokens,
            "total_completion_tokens": completion_tokens,
            "total_cached_tokens": cached_tokens,
            "total_steps": 1,
        }
    return doc


def _fake_cli(
    *,
    export_docs: list[dict[str, Any] | None] | dict[str, Any] | None = None,
    returncode: int = 0,
    stdout: str = '{"ok": true}',
    stderr: str = "",
    calls: list[list[str]] | None = None,
):
    """Return a subprocess.run stand-in that writes ATIF exports.

    ``export_docs`` may be a single doc (same for every call), a list keyed by
    call index, or None (never writes an export).
    """
    state = {"n": 0}

    def fake_run(cmd, **kwargs):
        idx = state["n"]
        state["n"] += 1
        if calls is not None:
            calls.append(list(cmd))
        doc = export_docs
        if isinstance(export_docs, list):
            doc = export_docs[idx] if idx < len(export_docs) else None
        if doc is not None and "--export" in cmd:
            Path(cmd[cmd.index("--export") + 1]).write_text(json.dumps(doc))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return fake_run


def _read_audit(run_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (run_dir / "audit.jsonl").read_text().splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Session ID classification
# ---------------------------------------------------------------------------


def test_classify_session_id_local_word_pair():
    assert classify_session_id("able-baker") == "local_cli"
    assert classify_session_id("pushy-dumpling") == "local_cli"


def test_classify_session_id_cloud():
    assert classify_session_id("devin-abc123def456") == "cloud"


def test_classify_session_id_missing():
    assert classify_session_id(None) is None
    assert classify_session_id("") is None


# ---------------------------------------------------------------------------
# ATIF export parsing
# ---------------------------------------------------------------------------


def test_parse_atif_export_full(tmp_path):
    p = tmp_path / "s.atif"
    p.write_text(json.dumps(_atif("able-baker")))
    parsed = DevinCliClient._parse_atif_export(p)
    assert parsed["status"] == "ok"
    assert parsed["session_id"] == "able-baker"
    assert parsed["schema_version"] == "ATIF-v1.7"
    assert parsed["agent"]["model_name"] == "fusion-claude-sonnet-5-5-medium"
    assert parsed["token_usage"] == {
        "prompt_tokens": 12000,
        "completion_tokens": 2500,
        "total_tokens": 14500,
    }
    assert parsed["final_metrics"]["total_cached_tokens"] == 3000
    assert len(parsed["sha256"]) == 64


def test_parse_atif_export_missing_file(tmp_path):
    parsed = DevinCliClient._parse_atif_export(tmp_path / "nope.atif")
    assert parsed["status"] == "unavailable"
    assert parsed["reason"] == "export_not_written"
    assert parsed["session_id"] is None


def test_parse_atif_export_empty(tmp_path):
    p = tmp_path / "e.atif"
    p.write_bytes(b"")
    parsed = DevinCliClient._parse_atif_export(p)
    assert parsed["reason"] == "export_empty"


def test_parse_atif_export_unparseable(tmp_path):
    p = tmp_path / "bad.atif"
    p.write_text("{not json")
    parsed = DevinCliClient._parse_atif_export(p)
    assert parsed["reason"] == "export_unparseable"


def test_parse_atif_export_missing_session_id(tmp_path):
    p = tmp_path / "nos.atif"
    p.write_text(json.dumps(_atif(None)))
    parsed = DevinCliClient._parse_atif_export(p)
    assert parsed["status"] == "unavailable"
    assert parsed["reason"] == "export_missing_session_id"
    # Token metrics are still recoverable without a session ID.
    assert parsed["token_usage"]["total_tokens"] == 14500


def test_parse_atif_export_no_metrics(tmp_path):
    p = tmp_path / "nom.atif"
    p.write_text(json.dumps(_atif("able-baker", metrics=False)))
    parsed = DevinCliClient._parse_atif_export(p)
    assert parsed["status"] == "ok"
    assert parsed["session_id"] == "able-baker"
    assert parsed["token_usage"] is None


# ---------------------------------------------------------------------------
# DevinCliClient invocation records (mocked subprocess)
# ---------------------------------------------------------------------------


def test_complete_captures_session_and_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_cli(export_docs=_atif("able-baker")))
    client = DevinCliClient(model="m", export_dir=tmp_path / "exports")
    resp = client.complete("prompt", invocation_id="inv-aaa")

    inv = resp.metadata["invocation"]
    assert inv["invocation_id"] == "inv-aaa"
    assert inv["devin_session_id"] == "able-baker"
    assert inv["session_id_status"] == "captured"
    assert inv["session_type"] == "local_cli"
    assert inv["provider"] == "devin"
    assert inv["returncode"] == 0
    assert resp.token_usage["total_tokens"] == 14500
    assert len(resp.metadata["invocations"]) == 1

    # Export preserved under export_dir using the invocation ID.
    saved = tmp_path / "exports" / "inv-aaa.atif.json"
    assert saved.exists()
    assert inv["export_path"] == str(saved)
    assert inv["export_sha256"] is not None


def test_complete_generates_invocation_id(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_cli(export_docs=_atif()))
    client = DevinCliClient(model="m")
    resp = client.complete("prompt")
    inv = resp.metadata["invocation"]
    assert inv["invocation_id"].startswith("inv-")
    # Temp export is cleaned up; path not reported as persistent.
    assert inv["export_path"] is None


def test_complete_missing_session_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_cli(export_docs=_atif(None))
    )
    client = DevinCliClient(model="m")
    resp = client.complete("prompt")
    inv = resp.metadata["invocation"]
    assert inv["devin_session_id"] is None
    assert inv["session_id_status"] == "unavailable"
    assert inv["session_id_reason"] == "export_missing_session_id"
    # Usage survives even when the session ID does not.
    assert resp.token_usage["total_tokens"] == 14500


def test_complete_no_export_written(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_cli(export_docs=None))
    client = DevinCliClient(model="m")
    resp = client.complete("prompt")
    inv = resp.metadata["invocation"]
    assert inv["devin_session_id"] is None
    assert inv["session_id_reason"] == "export_not_written"
    assert resp.token_usage is None


def test_cli_failure_still_reports_session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_cli(export_docs=_atif("able-baker"), returncode=3, stderr="boom"),
    )
    client = DevinCliClient(model="m")
    with pytest.raises(LLMError) as ei:
        client.complete("prompt")
    invs = ei.value.invocations
    assert len(invs) == 1
    assert invs[0]["returncode"] == 3
    # A session created before the failure is still attributable.
    assert invs[0]["devin_session_id"] == "able-baker"
    assert invs[0]["session_id_status"] == "captured"


def test_cli_failure_no_export(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_cli(export_docs=None, returncode=2, stderr="x")
    )
    client = DevinCliClient(model="m")
    with pytest.raises(LLMError) as ei:
        client.complete("prompt")
    inv = ei.value.invocations[0]
    assert inv["devin_session_id"] is None
    assert inv["session_id_reason"] == "export_not_written"


def test_cli_timeout_invocation(tmp_path, monkeypatch):
    def _timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(subprocess, "run", _timeout)
    client = DevinCliClient(model="m")
    with pytest.raises(LLMError) as ei:
        client.complete("prompt")
    inv = ei.value.invocations[0]
    assert inv["session_id_status"] == "unavailable"
    assert inv["session_id_reason"] == "export_not_written"


def test_internal_retries_get_distinct_invocations(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    docs = [_atif("first-session"), _atif("second-session")]
    state = {"n": 0}

    def fake(cmd, **kwargs):
        idx = state["n"]
        state["n"] += 1
        calls.append(cmd)
        if "--export" in cmd:
            Path(cmd[cmd.index("--export") + 1]).write_text(json.dumps(docs[idx]))
        rc = 1 if idx == 0 else 0
        return SimpleNamespace(returncode=rc, stdout="{}", stderr="fail")

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr("fictionforge.llm.devin.time.sleep", lambda s: None)
    client = DevinCliClient(model="m")
    resp = client.complete("prompt", retries=1, invocation_id="inv-ext")

    invs = resp.metadata["invocations"]
    assert len(invs) == 2
    # First execution reuses the caller-supplied invocation ID; the internal
    # retry gets its own fresh ID and its own Devin session.
    assert invs[0]["invocation_id"] == "inv-ext"
    assert invs[0]["devin_session_id"] == "first-session"
    assert invs[1]["invocation_id"] != "inv-ext"
    assert invs[1]["devin_session_id"] == "second-session"


def test_cloud_session_id_classified(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_cli(export_docs=_atif("devin-xyz123"))
    )
    client = DevinCliClient(model="m")
    resp = client.complete("prompt")
    inv = resp.metadata["invocation"]
    assert inv["devin_session_id"] == "devin-xyz123"
    assert inv["session_type"] == "cloud"


# ---------------------------------------------------------------------------
# Audit schema
# ---------------------------------------------------------------------------


def test_audit_step_start_pending_session(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_step_start(
        step="world_generation",
        attempt=1,
        prompt_hash="h",
        generator_model="m",
        input_artifact_hashes={},
        workflow_status="running",
        invocation_id="inv-1",
        provider="devin",
        session_type="local_cli",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["invocation_id"] == "inv-1"
    assert ev["devin_session_id"] is None
    assert ev["session_id_status"] == "pending"
    assert ev["provider"] == "devin"


def test_audit_step_complete_session_fields(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_step_complete(
        step="world_generation",
        attempt=1,
        output_artifact_hash="h",
        validation_results=[],
        token_usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        cost=None,
        latency=1.0,
        retry_decision="continue",
        failure_code=None,
        workflow_status="running",
        invocation_id="inv-1",
        provider="devin",
        devin_session_id="able-baker",
        session_type="local_cli",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["invocation_id"] == "inv-1"
    assert ev["devin_session_id"] == "able-baker"
    assert ev["session_type"] == "local_cli"
    assert ev["cost"] is None
    assert ev["cost_details"] == {
        "actual_usd": None,
        "estimated_usd": None,
        "billed_acus": None,
        "status": "pending_reconciliation",
        "source": None,
        "pricing_snapshot_id": None,
    }


def test_audit_step_complete_missing_session(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_step_complete(
        step="world_generation",
        attempt=1,
        output_artifact_hash=None,
        validation_results=[],
        token_usage=None,
        cost=None,
        latency=1.0,
        retry_decision="stop",
        failure_code="MODEL_TIMEOUT",
        workflow_status="failed_automated",
        invocation_id="inv-1",
        provider="devin",
        session_id_reason="export_not_written",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["devin_session_id"] is None
    assert ev["session_id_status"] == "unavailable"
    assert ev["session_id_reason"] == "export_not_written"


def test_audit_backward_compatible_without_invocation(tmp_path):
    """Old-style events (no invocation) get no new keys."""
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_step_start(
        step="load_brief",
        attempt=1,
        prompt_hash="",
        generator_model=None,
        input_artifact_hashes={},
        workflow_status="running",
    )
    audit.log_step_complete(
        step="load_brief",
        attempt=1,
        output_artifact_hash="h",
        validation_results=[],
        token_usage=None,
        cost=None,
        latency=0.1,
        retry_decision=None,
        failure_code=None,
        workflow_status="running",
    )
    start, complete = _read_audit(tmp_path)
    for ev in (start, complete):
        assert "invocation_id" not in ev
        assert "devin_session_id" not in ev
        assert "cost_details" not in ev


def test_audit_session_discovered_event(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_session_discovered(
        invocation_id="inv-1",
        devin_session_id="able-baker",
        session_type="local_cli",
        source="atif_export",
        step="world_generation",
        attempt=1,
        agent={"model_name": "m"},
        export_sha256="abc",
        workflow_status="running",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["event_type"] == "session_discovered"
    assert ev["devin_session_id"] == "able-baker"
    assert ev["session_id_status"] == "captured"
    assert ev["source"] == "atif_export"


def test_audit_session_discovered_unavailable(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_session_discovered(
        invocation_id="inv-1",
        devin_session_id=None,
        session_type="local_cli",
        source="atif_export",
        session_id_reason="export_not_written",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["session_id_status"] == "unavailable"
    assert ev["session_id_reason"] == "export_not_written"


def test_audit_retry_decision_carries_session(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_retry_decision(
        step="world_generation",
        attempt=1,
        failure_code="INVALID_JSON",
        next_attempt=2,
        reason="invalid_json",
        workflow_status="running",
        invocation_id="inv-1",
        devin_session_id="able-baker",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["invocation_id"] == "inv-1"
    assert ev["devin_session_id"] == "able-baker"


def test_audit_reviewer_call_session_fields(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_reviewer_call(
        step="world_generation",
        gate="world",
        attempt=1,
        reviewer_id="world_reviewer",
        reviewer_model="swe-2-medium",
        attempts=[],
        ok=True,
        error_code=None,
        duration_s=1.0,
        invocation_id="inv-r1",
        provider="devin",
        devin_session_id="reviewer-session",
        session_type="local_cli",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["devin_session_id"] == "reviewer-session"
    assert ev["cost_details"]["status"] == "pending_reconciliation"


def test_audit_cost_reconciliation_event(tmp_path):
    audit = AuditLogger(tmp_path, run_id="r1")
    audit.log_cost_reconciliation(
        invocation_id="inv-1",
        devin_session_id="able-baker",
        session_type="local_cli",
        step="world_generation",
        attempt=1,
        cost_details={
            "actual_usd": None,
            "estimated_usd": None,
            "billed_acus": 0.42,
            "status": "actual",
            "source": "sessions_db",
            "pricing_snapshot_id": None,
        },
        reconciliation_source="sessions_db",
        status="reconciled",
    )
    (ev,) = _read_audit(tmp_path)
    assert ev["event_type"] == "cost_reconciliation"
    assert ev["category"] == "billing"
    assert ev["devin_session_id"] == "able-baker"
    assert ev["cost_details"]["billed_acus"] == 0.42


# ---------------------------------------------------------------------------
# Reviewer invocation attribution
# ---------------------------------------------------------------------------


class _SessionMockClient(MockClient):
    """MockClient that mimics DevinCliClient invocation metadata."""

    def __init__(self, responses, session_ids):
        super().__init__(responses)
        self._session_ids = list(session_ids)

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        resp = super().complete(prompt, **kwargs)
        sid = self._session_ids.pop(0) if self._session_ids else None
        inv = {
            "invocation_id": kwargs.get("invocation_id") or "inv-gen",
            "provider": "devin",
            "session_type": classify_session_id(sid),
            "devin_session_id": sid,
            "session_id_status": "captured" if sid else "unavailable",
            "session_id_reason": None if sid else "export_missing_session_id",
            "token_usage": resp.token_usage,
        }
        md = dict(resp.metadata or {})
        md["invocation"] = inv
        md["invocations"] = [inv]
        return LLMResponse(
            content=resp.content,
            token_usage=resp.token_usage,
            latency_s=resp.latency_s,
            metadata=md,
        )


_PASS_VERDICT = json.dumps(
    {"verdict": "PASS", "issues": [], "reason": "No critical inconsistencies found."}
)


def _world_reviewer(client) -> AdversarialReviewer:
    cfg = default_reviewer_configs(model="swe-2-medium")["world_generation"]
    return AdversarialReviewer(client, cfg)


def test_reviewer_invocation_attribution(world_data):
    client = _SessionMockClient([_PASS_VERDICT], ["able-baker"])
    reviewer = _world_reviewer(client)
    result = reviewer.review(context={"brief": {}}, artifact=world_data)

    assert result.ok
    assert len(result.attempts) == 1
    att = result.attempts[0]
    assert att.invocation_id is not None
    assert att.invocations[0]["devin_session_id"] == "able-baker"
    assert result.invocations[0]["devin_session_id"] == "able-baker"
    # The client received our internal invocation ID.
    assert client.calls[0]["kwargs"]["invocation_id"] == att.invocation_id


def test_reviewer_failure_keeps_invocation(world_data):
    class _FailingClient(MockClient):
        def complete(self, prompt, **kwargs):
            raise LLMError(
                "boom",
                invocations=[{
                    "invocation_id": kwargs.get("invocation_id"),
                    "devin_session_id": "able-baker",
                    "session_id_status": "captured",
                }],
            )

    reviewer = _world_reviewer(_FailingClient([]))
    result = reviewer.review(context={"brief": {}}, artifact=world_data)
    assert not result.ok
    assert result.attempts[0].invocations[0]["devin_session_id"] == "able-baker"


# ---------------------------------------------------------------------------
# Runner-level integration (MockClient — no real sessions)
# ---------------------------------------------------------------------------


def _json_response(data: object) -> LLMResponse:
    return LLMResponse(content=json.dumps(data, indent=2, ensure_ascii=False))


def test_workflow_invocation_ids_and_audit(
    brief_path, world_data, characters_data, storyboard_data, tmp_path
):
    client = MockClient([
        _json_response(world_data),
        _json_response(characters_data),
        _json_response(storyboard_data),
    ])
    runner = WorkflowRunner(
        client, WorkflowConfig(max_attempts_per_step=1), output_dir=tmp_path
    )
    result = runner.run(brief_path)
    assert result.status == WorkflowStatus.COMPLETED

    events = _read_audit(result.output_dir)
    starts = [e for e in events if e["event_type"] == "step_start"]
    completes = [e for e in events if e["event_type"] == "step_complete"]

    llm_steps = {"world_generation", "character_design", "storyboard_building"}
    for ev in starts:
        if ev["step"] in llm_steps:
            assert ev["invocation_id"].startswith("inv-")
            assert ev["session_id_status"] == "pending"
            assert ev["devin_session_id"] is None
        else:
            assert "invocation_id" not in ev

    for ev in completes:
        if ev["step"] in llm_steps:
            assert ev["invocation_id"].startswith("inv-")
            assert ev["devin_session_id"] is None
            assert ev["session_id_status"] == "unavailable"
            assert ev["cost_details"]["status"] == "unavailable"

    # All invocation IDs unique across the run.
    ids = [e["invocation_id"] for e in completes if "invocation_id" in e]
    assert len(ids) == len(set(ids)) == 3


def test_workflow_retry_invocations_distinct(
    brief_path, world_data, characters_data, storyboard_data, tmp_path
):
    invalid = {**world_data, "locations": []}
    client = MockClient([
        _json_response(invalid),
        _json_response(world_data),
        _json_response(characters_data),
        _json_response(storyboard_data),
    ])
    runner = WorkflowRunner(
        client, WorkflowConfig(max_attempts_per_step=3), output_dir=tmp_path
    )
    result = runner.run(brief_path)
    assert result.status == WorkflowStatus.COMPLETED

    world_step = next(
        s for s in result.steps if s.step_id == "world_generation"
    )
    assert len(world_step.attempts) == 2
    ids = {a.invocation_id for a in world_step.attempts}
    assert len(ids) == 2  # each retry is its own invocation

    events = _read_audit(result.output_dir)
    retries = [e for e in events if e["event_type"] == "retry_decision"]
    assert retries and retries[0]["invocation_id"] == world_step.attempts[0].invocation_id


# ---------------------------------------------------------------------------
# Consumption: component usage, ACU cost, redaction, sessions.db
# ---------------------------------------------------------------------------

from fictionforge.observability.consumption import (  # noqa: E402
    collect_consumption,
    consumption_from_parsed,
    consumption_from_sessions_db,
    cost_details_for_invocation,
)


def _fusion_atif(session_id="bottled-grass"):
    """ATIF doc matching the real fusion headless export schema."""
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": session_id,
        "agent": {"name": "devin", "version": "3000.12.43",
                  "model_name": "fusion-x-medium",
                  "tool_definitions": {"fn": {"type": "object"}}},
        "steps": [
            {"step_id": 1, "source": "user", "message": "hi"},
            {
                "step_id": 2, "source": "agent",
                "model_name": "fusion-x-medium",
                "message": "OK",
                "metrics": {"prompt_tokens": 4000, "completion_tokens": 10,
                            "cached_tokens": 0},
                "extra": {
                    "committed_acu_cost": 0.000053,
                    "generation_model": "claude-sonnet-5-5",
                    "sidekick_model": "claude-haiku-5-5",
                },
            },
            {
                "step_id": 3, "source": "agent",
                "model_name": "fusion-x-medium",
                "tool_calls": [{"function_name": "done", "arguments": {}}],
                "metrics": {"prompt_tokens": 4100, "completion_tokens": 20,
                            "cached_tokens": 0},
                "extra": {
                    "committed_acu_cost": 0.000021,
                    "generation_model": "claude-haiku-5-5",
                    "sidekick_model": "claude-haiku-5-5",
                },
            },
        ],
        "final_metrics": {"total_prompt_tokens": 8100,
                          "total_completion_tokens": 30,
                          "total_cached_tokens": 0,
                          "total_steps": 3},
    }


def test_parse_billed_acus_and_component_usage():
    parsed = DevinCliClient.parse_atif_data(_fusion_atif())
    assert parsed["billed_acus"] == pytest.approx(0.000074)
    assert parsed["component_usage"] == [
        {"step_id": 2, "source": "agent", "model_name": "fusion-x-medium",
         "generation_model": "claude-sonnet-5-5",
         "sidekick_model": "claude-haiku-5-5",
         "prompt_tokens": 4000, "completion_tokens": 10,
         "cached_tokens": 0, "committed_acu_cost": 0.000053},
        {"step_id": 3, "source": "agent", "model_name": "fusion-x-medium",
         "generation_model": "claude-haiku-5-5",
         "sidekick_model": "claude-haiku-5-5",
         "prompt_tokens": 4100, "completion_tokens": 20,
         "cached_tokens": 0, "committed_acu_cost": 0.000021},
    ]
    assert set(parsed["models_used"]) == {
        "fusion-x-medium", "claude-sonnet-5-5", "claude-haiku-5-5",
    }


def test_parse_acu_partial_when_some_steps_lack_cost():
    data = _fusion_atif()
    del data["steps"][1]["extra"]["committed_acu_cost"]
    parsed = DevinCliClient.parse_atif_data(data)
    assert parsed["billed_acus"] == pytest.approx(0.000021)


def test_parse_no_acu_returns_none():
    data = _fusion_atif()
    for s in data["steps"]:
        if s.get("source") == "agent":
            s["extra"].pop("committed_acu_cost", None)
    parsed = DevinCliClient.parse_atif_data(data)
    assert parsed["billed_acus"] is None


def test_redact_atif_data_strips_tool_definitions():
    data = _fusion_atif()
    red = DevinCliClient.redact_atif_data(data)
    assert "tool_definitions" not in red["agent"]
    assert red["agent"]["model_name"] == "fusion-x-medium"
    assert red["session_id"] == "bottled-grass"
    # original untouched, output deterministic
    assert "tool_definitions" in data["agent"]
    assert json.dumps(red, sort_keys=True) == json.dumps(
        DevinCliClient.redact_atif_data(data), sort_keys=True
    )


def test_persisted_export_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_cli(export_docs=_fusion_atif())
    )
    export_dir = tmp_path / "exports"
    client = DevinCliClient(export_dir=export_dir)
    resp = client.complete("hello")
    inv = resp.metadata["invocations"][0]
    assert inv["devin_session_id"] == "bottled-grass"
    assert inv["billed_acus"] == pytest.approx(0.000074)
    assert inv["export_redacted"] is True
    assert inv["raw_export_sha256"] != inv["export_sha256"]
    on_disk = json.loads(
        (export_dir / f"{inv['invocation_id']}.atif.json").read_bytes()
    )
    assert "tool_definitions" not in on_disk["agent"]
    assert "message" not in on_disk["steps"][0]
    assert on_disk["redacted"] is True
    import hashlib
    digest = hashlib.sha256(
        json.dumps(on_disk, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert digest == inv["export_sha256"]


def test_no_export_dir_skips_redaction(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_cli(export_docs=_fusion_atif())
    )
    client = DevinCliClient()  # no export_dir -> temp export only
    resp = client.complete("hi")
    inv = resp.metadata["invocations"][0]
    assert inv["export_redacted"] is False
    assert inv["raw_export_sha256"] is None
    assert inv["export_path"] is None  # temp path not recorded


def test_redaction_disabled_keeps_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", _fake_cli(export_docs=_fusion_atif())
    )
    export_dir = tmp_path / "exports"
    client = DevinCliClient(export_dir=export_dir, redact_exports=False)
    resp = client.complete("hi")
    inv = resp.metadata["invocations"][0]
    assert inv["export_redacted"] is False
    on_disk = json.loads(
        (export_dir / f"{inv['invocation_id']}.atif.json").read_bytes()
    )
    assert "tool_definitions" in on_disk["agent"]


def test_sessions_db_consumption(tmp_path):
    import sqlite3
    db = tmp_path / "sessions.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, metadata TEXT, "
        "model TEXT, backend_type TEXT)"
    )
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?)",
        ("bottled-grass",
         json.dumps({"total_acu_cost": 0.000074, "total_credit_cost": 0.0}),
         "fusion-x-medium", "cli"),
    )
    conn.commit()
    conn.close()
    c = consumption_from_sessions_db("bottled-grass", db_path=db)
    assert c.status == "actual"
    assert c.billed_acus == pytest.approx(0.000074)
    assert c.scope == "session_lifetime"
    assert c.source == "devin_sessions_db"


def test_sessions_db_missing_and_unparseable(tmp_path):
    import sqlite3
    missing = consumption_from_sessions_db("x", db_path=tmp_path / "nope.db")
    assert missing.status == "unavailable"
    assert missing.reason == "sessions_db_missing"

    db = tmp_path / "sessions.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, metadata TEXT, "
        "model TEXT, backend_type TEXT)"
    )
    conn.execute("INSERT INTO sessions VALUES ('x', 'not-json', 'm', 'b')")
    conn.commit()
    conn.close()
    c = consumption_from_sessions_db("x", db_path=db)
    assert c.status == "unavailable"
    assert c.reason == "metadata_unparseable"
    nf = consumption_from_sessions_db("ghost", db_path=db)
    assert nf.reason == "session_not_found"


def test_collect_consumption_prefers_export(tmp_path):
    export = tmp_path / "e.json"
    export.write_text(json.dumps(_fusion_atif()))
    c = collect_consumption(session_id="bottled-grass", export_path=export)
    assert c.source == "atif_export"
    assert c.scope == "invocation"
    assert c.billed_acus == pytest.approx(0.000074)


def test_consumption_from_parsed_no_cost():
    parsed = DevinCliClient.parse_atif_data(_fusion_atif())
    parsed["billed_acus"] = None
    c = consumption_from_parsed(parsed)
    assert c.status == "unavailable"
    assert c.reason == "export_missing_acu_cost"


def test_cost_details_for_invocation():
    actual = cost_details_for_invocation({"billed_acus": 0.5})
    assert actual["status"] == "actual"
    assert actual["source"] == "atif_export"
    assert actual["actual_usd"] is None  # ACUs never converted to USD

    pending = cost_details_for_invocation(
        {"devin_session_id": "able-baker", "billed_acus": None}
    )
    assert pending["status"] == "pending_reconciliation"

    unavailable = cost_details_for_invocation(None)
    assert unavailable["status"] == "unavailable"
