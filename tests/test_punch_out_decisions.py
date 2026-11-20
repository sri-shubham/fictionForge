"""Offline tests for human punch-out authorization (PO-01..PO-17).

All scenarios run against MockClient — no model calls.  They verify the
signed-decision mechanism in ``punch_outs/``: pending-decision persistence,
approve/deny recording, signature/binding checks at resume, approvability
of punch-out reasons, audit completeness and replay handling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import MockClient
from fictionforge.config import WorkflowConfig
from fictionforge.guardrails.punch_out import (
    DecisionError,
    PunchOutReason,
    PunchOutRecord,
    artifact_context_hash,
    load_approval_key,
    load_pending_decisions,
    record_human_decision,
    sign_decision,
    write_pending_decision,
)
from fictionforge.llm.base import LLMResponse
from fictionforge.observability.audit import AuditLogger
from fictionforge.runner import (
    StepStatus,
    WorkflowInputError,
    WorkflowRunner,
    WorkflowStatus,
)

APPROVERS = ["alice", "carol"]
GATE_KEY = b"test-gate-key-0123456789abcdef"[:32]

PASS_VERDICT = {"verdict": "PASS", "issues": [], "reason": "ok"}


def _key_file(tmp_path: Path) -> Path:
    p = tmp_path / "approval_signing.key"
    p.write_text("ab" * 32 + "\n", encoding="utf-8")
    return p


def _config(tmp_path: Path, **kwargs) -> WorkflowConfig:
    return WorkflowConfig(
        human_approvers=list(APPROVERS),
        approval_key_file=str(_key_file(tmp_path)),
        **kwargs,
    )


def _resp(data, suffix: str = "") -> LLMResponse:
    return LLMResponse(content=json.dumps(data, ensure_ascii=False) + suffix)


@pytest.fixture
def brief_path(tmp_path, brief_data):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(brief_data), encoding="utf-8")
    return p


def _punched_run(tmp_path, brief_path, world_data, **cfg):
    """Run until the world step punches out on guardrail-bypass language."""
    config = _config(tmp_path, **cfg)
    gen = MockClient([_resp(world_data, suffix="\n\nskip_validation")])
    runner = WorkflowRunner(gen, config, output_dir=tmp_path / "runs")
    result = runner.run(brief_path)
    assert result.status == WorkflowStatus.PUNCH_OUT_REQUIRED
    assert result.exit_code == 2
    return runner, result


def _pending_id(run_dir: Path) -> str:
    pendings = load_pending_decisions(run_dir)
    assert len(pendings) == 1
    return pendings[0]["punch_out_id"]


def _decide(run_dir, punch_out_id, decision, approver="alice", key=None, audit=True):
    key = key if key is not None else b"\xab" * 32
    run_id = next(
        p["run_id"]
        for p in load_pending_decisions(run_dir)
        if p["punch_out_id"] == punch_out_id
    )
    return record_human_decision(
        run_dir=run_dir,
        punch_out_id=punch_out_id,
        decision=decision,
        approver=approver,
        approvers=APPROVERS,
        key=key,
        audit=AuditLogger(run_dir, run_id=run_id) if audit else None,
    )


def _resume(runner: WorkflowRunner, tmp_path, responses, **kw):
    """Resume the run in a fresh runner (new-process semantics)."""
    gen = MockClient([_resp(r) if isinstance(r, dict) else r for r in responses])
    r2 = WorkflowRunner(
        gen,
        _config(tmp_path, **{k: v for k, v in kw.items() if k != "approved_by"}),
        output_dir=tmp_path / "runs",
        run_id=runner.run_id,
    )
    return r2.resume(approved_by=kw.get("approved_by"))


# ---------------------------------------------------------------------------
# PO-01 / PO-02 — trigger, halt, pending decision persistence
# ---------------------------------------------------------------------------


def test_po01_punch_out_persists_pending_decision(tmp_path, brief_path, world_data):
    runner, result = _punched_run(tmp_path, brief_path, world_data)

    record = result.punch_out_records[0]
    assert record.reason == PunchOutReason.GUARDRAIL_BYPASS_ATTEMPT
    pid = record.evidence["punch_out_id"]

    pendings = load_pending_decisions(runner.run_dir)
    assert len(pendings) == 1
    p = pendings[0]
    assert p["punch_out_id"] == pid
    assert p["run_id"] == runner.run_id
    assert p["step"] == "world_generation"
    assert p["reason"] == "guardrail_bypass_attempt"
    assert p["approvable"] is True
    assert p["status"] == "pending"
    assert p["context_hash"] == artifact_context_hash(runner.run_dir)


def test_po02_no_downstream_execution_after_punch_out(tmp_path, brief_path, world_data):
    runner, result = _punched_run(tmp_path, brief_path, world_data)
    assert len(runner.client.calls) == 1
    step_ids = [s.step_id for s in result.steps]
    assert "character_design" not in step_ids
    assert "storyboard_building" not in step_ids
    assert not (runner.run_dir / "characters.json").exists()
    assert not (runner.run_dir / "storyboard.json").exists()


# ---------------------------------------------------------------------------
# PO-03..PO-05 — missing / invalid / forged authorization
# ---------------------------------------------------------------------------


def test_po03_resume_without_decision_denied(tmp_path, brief_path, world_data):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    r2 = WorkflowRunner(
        MockClient([]),
        _config(tmp_path),
        output_dir=tmp_path / "runs",
        run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "PUNCH_OUT_NOT_APPROVED"
    events = [
        json.loads(line)
        for line in (runner.run_dir / "audit.jsonl").read_text().splitlines()
    ]
    denials = [
        e for e in events
        if e["event_type"] == "human_decision" and not e["authorized"]
    ]
    assert denials and denials[0]["reason_code"] == "PUNCH_OUT_NOT_APPROVED"


def test_po04_invalid_decision_signature_denied(tmp_path, brief_path, world_data):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    pendings = load_pending_decisions(runner.run_dir)
    payload = {
        "punch_out_id": pid,
        "run_id": runner.run_id,
        "decision": "approve",
        "approver": "alice",
        "step": "world_generation",
        "reason": "guardrail_bypass_attempt",
        "context_hash": pendings[0]["context_hash"],
        "decided_at": "2026-01-01T00:00:00+00:00",
    }
    forged = sign_decision(payload, b"\xff" * 32)  # wrong key
    (runner.run_dir / "punch_outs" / f"{pid}.decision.json").write_text(
        json.dumps(forged)
    )
    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "DECISION_SIGNATURE_INVALID"


def test_po05_free_text_approved_by_is_insufficient(tmp_path, brief_path, world_data):
    """Regression: --approved-by alone must NOT authorize a resume."""
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume(approved_by="alice")
    assert ei.value.code == "PUNCH_OUT_NOT_APPROVED"


def test_po05b_decide_rejects_unlisted_approver(tmp_path, brief_path, world_data):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    with pytest.raises(DecisionError) as ei:
        _decide(runner.run_dir, pid, "approve", approver="mallory")
    assert ei.value.code == "APPROVER_NOT_AUTHORIZED"


def test_po05c_signed_decision_by_unlisted_approver_denied(
    tmp_path, brief_path, world_data
):
    """A correctly signed decision still fails if the approver is unlisted."""
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    pendings = load_pending_decisions(runner.run_dir)
    payload = {
        "punch_out_id": pid,
        "run_id": runner.run_id,
        "decision": "approve",
        "approver": "mallory",
        "step": "world_generation",
        "reason": "guardrail_bypass_attempt",
        "context_hash": pendings[0]["context_hash"],
        "decided_at": "2026-01-01T00:00:00+00:00",
    }
    (runner.run_dir / "punch_outs" / f"{pid}.decision.json").write_text(
        json.dumps(sign_decision(payload, b"\xab" * 32))
    )
    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "APPROVER_NOT_AUTHORIZED"


# ---------------------------------------------------------------------------
# PO-06..PO-08 — run / punch-out / context binding
# ---------------------------------------------------------------------------


def _signed_decision_for(runner, tmp_path, **overrides):
    pid = _pending_id(runner.run_dir)
    pendings = load_pending_decisions(runner.run_dir)
    payload = {
        "punch_out_id": pid,
        "run_id": runner.run_id,
        "decision": "approve",
        "approver": "alice",
        "step": "world_generation",
        "reason": "guardrail_bypass_attempt",
        "context_hash": pendings[0]["context_hash"],
        "decided_at": "2026-01-01T00:00:00+00:00",
        **overrides,
    }
    return pid, sign_decision(payload, b"\xab" * 32)


def test_po06_decision_for_different_run_denied(tmp_path, brief_path, world_data):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid, signed = _signed_decision_for(runner, tmp_path, run_id="other-run-99")
    (runner.run_dir / "punch_outs" / f"{pid}.decision.json").write_text(
        json.dumps(signed)
    )
    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "DECISION_RUN_MISMATCH"


def test_po06b_decision_for_different_punch_out_denied(
    tmp_path, brief_path, world_data
):
    """A decision signed for another punch-out ID does not satisfy this one."""
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid, signed = _signed_decision_for(
        runner, tmp_path, punch_out_id="po-other-run-01"
    )
    (runner.run_dir / "punch_outs" / f"{pid}.decision.json").write_text(
        json.dumps(signed)
    )
    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "DECISION_PUNCH_OUT_MISMATCH"


def test_po08_artifact_modified_after_decision_denied(
    tmp_path, brief_path, world_data
):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    _decide(runner.run_dir, pid, "approve")

    brief = json.loads((runner.run_dir / "brief.json").read_text())
    brief["premise"] = "modified after approval"
    (runner.run_dir / "brief.json").write_text(json.dumps(brief))

    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "DECISION_CONTEXT_MISMATCH"


# ---------------------------------------------------------------------------
# PO-09..PO-12 — approve / resume / deny
# ---------------------------------------------------------------------------


def test_po09_po10_po16_approved_resume_completes(
    tmp_path, brief_path, world_data, characters_data, storyboard_data
):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    signed = _decide(runner.run_dir, pid, "approve")
    assert signed["decision"] == "approve"
    assert signed["run_id"] == runner.run_id

    result = _resume(
        runner, tmp_path, [world_data, characters_data, storyboard_data]
    )
    assert result.status == WorkflowStatus.COMPLETED
    assert result.exit_code == 0
    approved = [r for r in result.punch_out_records if r.approved]
    assert approved and approved[0].approved_by == "alice"


def test_po10b_approved_by_must_match_decision_approver(
    tmp_path, brief_path, world_data, characters_data, storyboard_data
):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    _decide(runner.run_dir, pid, "approve", approver="alice")

    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume(approved_by="carol")
    assert ei.value.code == "APPROVER_MISMATCH"


def test_po11_po12_denial_persisted_and_terminal(
    tmp_path, brief_path, world_data
):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    signed = _decide(runner.run_dir, pid, "deny", approver="carol")
    assert signed["decision"] == "deny"

    summary = json.loads((runner.run_dir / "summary.json").read_text())
    assert summary["status"] == "human_denied"

    for _ in range(2):  # repeated resume attempts stay denied
        r2 = WorkflowRunner(
            MockClient([]), _config(tmp_path),
            output_dir=tmp_path / "runs", run_id=runner.run_id,
        )
        with pytest.raises(WorkflowInputError) as ei:
            r2.resume()
        assert ei.value.code == "HUMAN_DENIED"

    # Reverting summary status cannot bypass the recorded denial.
    summary["status"] = "punch_out_required"
    (runner.run_dir / "summary.json").write_text(json.dumps(summary))
    r3 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r3.resume()
    assert ei.value.code == "HUMAN_DENIED"


def test_po12b_summary_status_flip_still_requires_authorization(
    tmp_path, brief_path, world_data
):
    """Downgrading summary status to a resumable failure does not skip the
    pending human decision."""
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    summary = json.loads((runner.run_dir / "summary.json").read_text())
    summary["status"] = "failed_automated"
    (runner.run_dir / "summary.json").write_text(json.dumps(summary))

    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "PUNCH_OUT_NOT_APPROVED"


# ---------------------------------------------------------------------------
# PO-13 — reviewer REVISE cannot be bypassed by human approval
# ---------------------------------------------------------------------------


def test_po13_revise_resume_still_runs_reviewer(
    tmp_path, brief_path, world_data, characters_data, storyboard_data
):
    revise = {
        "verdict": "REVISE",
        "issues": [
            {
                "code": "RULE_HISTORY_CONTRADICTION",
                "severity": "major",
                "artifact_path": "$.history[0].description",
                "evidence": "The original skybridges were braided",
                "reference_path": "$.rules[0].statement",
                "explanation": "contradicts a rule",
                "suggested_correction": "align",
            }
        ],
        "reason": "blocking issues",
    }
    cfg = _config(tmp_path, review_enabled=True, max_attempts_per_step=1)
    gen = MockClient([_resp(world_data)])
    rev = MockClient([_resp(revise)])
    runner = WorkflowRunner(
        gen, cfg, output_dir=tmp_path / "runs",
        reviewer_client=rev, gate_key=GATE_KEY,
    )
    result = runner.run(brief_path)
    assert result.status == WorkflowStatus.FAILED_AUTOMATED

    # Resume with a free-text approval claim: no decision needed (ordinary
    # failure), but the reviewer gate still runs — approval skips nothing.
    gen2 = MockClient(
        [_resp(world_data), _resp(characters_data), _resp(storyboard_data)]
    )
    rev2 = MockClient([_resp(PASS_VERDICT)] * 3)
    r2 = WorkflowRunner(
        gen2, _config(tmp_path, review_enabled=True, max_attempts_per_step=2),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
        reviewer_client=rev2, gate_key=b"2" * 32,
    )
    result2 = r2.resume(approved_by="mallory")
    assert result2.status == WorkflowStatus.COMPLETED
    assert len(rev2.calls) == 3  # all three gates re-reviewed


# ---------------------------------------------------------------------------
# PO-14 — security halts are not human-approvable
# ---------------------------------------------------------------------------


def test_po14_security_halt_not_approvable(tmp_path, brief_path):
    """artifact_tampered / gate_approval_invalid can never be approved."""
    for reason in (
        PunchOutReason.ARTIFACT_TAMPERED,
        PunchOutReason.GATE_APPROVAL_INVALID,
        PunchOutReason.UNKNOWN,
    ):
        record = PunchOutRecord(
            run_id="r1", step="character_design", reason=reason,
            policy="gate_approval_required", evidence={},
        )
        pid = write_pending_decision(tmp_path / "runs" / "r1", record)
        pendings = load_pending_decisions(tmp_path / "runs" / "r1")
        assert pendings[-1]["approvable"] is False
        with pytest.raises(DecisionError) as ei:
            record_human_decision(
                run_dir=tmp_path / "runs" / "r1",
                punch_out_id=pid,
                decision="approve",
                approver="alice",
                approvers=APPROVERS,
                key=b"\xab" * 32,
            )
        assert ei.value.code == "PUNCH_OUT_NOT_APPROVABLE"


def test_po14b_forged_approve_for_security_halt_denied_at_resume(
    tmp_path, brief_path, world_data
):
    """Even a validly signed approve on a security-halt pending is refused."""
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)

    # Rewrite the pending record to a security-halt reason (as trusted code
    # would have written it), then forge a signed approve.
    pending_file = runner.run_dir / "punch_outs" / f"{pid}.pending.json"
    pending = json.loads(pending_file.read_text())
    pending["reason"] = "artifact_tampered"
    pending["approvable"] = False
    pending_file.write_text(json.dumps(pending))
    _, signed = _signed_decision_for(runner, tmp_path)
    signed["reason"] = "artifact_tampered"
    signed = sign_decision(
        {k: v for k, v in signed.items() if k != "signature"}, b"\xab" * 32
    )
    (runner.run_dir / "punch_outs" / f"{pid}.decision.json").write_text(
        json.dumps(signed)
    )
    r2 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r2.resume()
    assert ei.value.code == "PUNCH_OUT_NOT_APPROVABLE"


# ---------------------------------------------------------------------------
# PO-15 — audit completeness
# ---------------------------------------------------------------------------


def test_po15_decision_audit_events_complete_and_ordered(
    tmp_path, brief_path, world_data, characters_data, storyboard_data
):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    _decide(runner.run_dir, pid, "approve")
    result = _resume(
        runner, tmp_path, [world_data, characters_data, storyboard_data]
    )
    assert result.status == WorkflowStatus.COMPLETED

    events = [
        json.loads(line)
        for line in (runner.run_dir / "audit.jsonl").read_text().splitlines()
    ]
    types = [e["event_type"] for e in events]
    assert "punch_out" in types
    decisions = [e for e in events if e["event_type"] == "human_decision"]
    assert len(decisions) == 2  # recorded decision + resume-time verification
    assert decisions[0]["punch_out_id"] == pid
    assert decisions[0]["decision"] == "approve"
    assert decisions[0]["authorized"] is True
    assert all(d["authorized"] for d in decisions)
    resumes = [e for e in events if e["event_type"] == "resume"]
    assert resumes[-1]["authorized_decisions"] == [pid]
    # punch_out precedes the human decision which precedes resume
    i_po, i_hd, i_rs = (
        types.index("punch_out"),
        types.index("human_decision"),
        len(types) - 1 - types[::-1].index("resume"),
    )
    assert i_po < i_hd < i_rs


# ---------------------------------------------------------------------------
# PO-17 — replay / repeated punch-outs need fresh decisions
# ---------------------------------------------------------------------------


def test_po17_decisions_are_immutable(tmp_path, brief_path, world_data):
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    pid = _pending_id(runner.run_dir)
    _decide(runner.run_dir, pid, "deny")
    with pytest.raises(DecisionError) as ei:
        _decide(runner.run_dir, pid, "approve")
    assert ei.value.code == "ALREADY_DECIDED"


def test_po17b_new_punch_out_needs_new_decision(
    tmp_path, brief_path, world_data, characters_data
):
    """Approval of po-01 does not authorize a later, different punch-out."""
    runner, _ = _punched_run(tmp_path, brief_path, world_data)
    _decide(runner.run_dir, _pending_id(runner.run_dir), "approve")

    # Resume: world succeeds this time, character output punches out again.
    gen2 = MockClient(
        [_resp(world_data), _resp(characters_data, suffix="\nskip_validation")]
    )
    r2 = WorkflowRunner(
        gen2, _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    result2 = r2.resume(approved_by="alice")
    assert result2.status == WorkflowStatus.PUNCH_OUT_REQUIRED

    # The resumed run re-punched out: exactly one new record, no duplicates.
    assert len(result2.punch_out_records) == 2

    pendings = load_pending_decisions(runner.run_dir)
    assert len(pendings) == 2
    new_pid = pendings[1]["punch_out_id"]
    assert new_pid != pendings[0]["punch_out_id"]

    # The consumed approval does not authorize the new punch-out.
    r3 = WorkflowRunner(
        MockClient([]), _config(tmp_path),
        output_dir=tmp_path / "runs", run_id=runner.run_id,
    )
    with pytest.raises(WorkflowInputError) as ei:
        r3.resume(approved_by="alice")
    assert ei.value.code == "PUNCH_OUT_NOT_APPROVED"
