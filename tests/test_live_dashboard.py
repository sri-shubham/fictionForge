"""Offline tests for the live dashboard server logic.

Pure functions only — conftest blocks sockets, so the HTTP/SSE layer is
exercised through its non-socket parts (summaries, fingerprints, pages).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from fictionforge.observability.live import (
    STALL_AFTER_S,
    audit_fingerprint,
    index_page,
    run_page,
    run_state,
    run_summary,
    scan_runs,
)


def _write_audit(run_dir: Path, events: list[dict]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "audit.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return run_dir


def _step_complete(run_id="r1", **kw):
    ev = {
        "event_type": "step_complete",
        "run_id": run_id,
        "step": "world_generation",
        "attempt": 1,
        "workflow_status": "running",
        "latency": 1.0,
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5,
                        "total_tokens": 15},
        "invocation_id": "inv-1",
        "provider": "devin",
        "devin_session_id": "able-baker",
        "cost_details": {"billed_acus": 0.02, "status": "actual",
                         "source": "atif_export"},
    }
    ev.update(kw)
    return ev


# ---------------------------------------------------------------------------
# State classification
# ---------------------------------------------------------------------------

def test_run_state_terminal():
    assert run_state("completed", 5) == "completed"
    assert run_state("failed_automated", 0) == "failed_automated"
    assert run_state("punch_out_required", 999) == "punch_out_required"


def test_run_state_running_and_stalled():
    assert run_state("running", 1) == "running"
    assert run_state("running", STALL_AFTER_S + 1) == "stalled"
    assert run_state(None, 1) == "running"


# ---------------------------------------------------------------------------
# Summaries + scanning
# ---------------------------------------------------------------------------

def test_run_summary_fields(tmp_path):
    run = _write_audit(tmp_path / "r1", [_step_complete()])
    s = run_summary(run, now=time.time())
    assert s["run_id"] == "r1"
    assert s["workflow_status"] == "running"
    assert s["state"] == "running"
    assert s["invocations"] == 1
    assert s["total_billed_acus"] == pytest.approx(0.02)
    assert s["total_actual_usd"] is None
    json.dumps(s)  # must be JSON-serializable for SSE/API


def test_scan_runs_orders_live_first(tmp_path):
    now = time.time()
    _write_audit(tmp_path / "old_done", [
        _step_complete(run_id="old_done", workflow_status="completed"),
        {"event_type": "workflow_complete", "workflow_status": "completed"},
    ])
    _write_audit(tmp_path / "live_run", [_step_complete(run_id="live_run")])
    (tmp_path / "empty").mkdir()  # no audit.jsonl -> skipped
    runs = scan_runs(tmp_path, now=now)
    ids = [r["run_id"] for r in runs]
    assert ids[0] == "live_run"
    assert runs[0]["state"] == "running"
    assert runs[1]["state"] == "completed"
    assert len(runs) == 2


def test_audit_fingerprint_detects_appends(tmp_path):
    run = _write_audit(tmp_path / "r1", [_step_complete()])
    fp1 = audit_fingerprint(run)
    assert fp1 is not None
    with (run / "audit.jsonl").open("a") as f:
        f.write(json.dumps(_step_complete(attempt=2)) + "\n")
    fp2 = audit_fingerprint(run)
    assert fp2 != fp1
    assert audit_fingerprint(tmp_path / "no-audit") is None


def test_scan_runs_missing_root(tmp_path):
    assert scan_runs(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# HTML shells
# ---------------------------------------------------------------------------

def test_index_page_is_live():
    page = index_page()
    assert "EventSource('/api/stream')" in page


def test_run_page_streams_run_view():
    page = run_page("abc123")
    assert "'/api/stream/run/' + encodeURIComponent" in page
    assert "fetch('/api/run/' + encodeURIComponent" in page
    assert "navigator.clipboard" in page  # copy buttons wired in JS
    assert '"abc123"' in page
