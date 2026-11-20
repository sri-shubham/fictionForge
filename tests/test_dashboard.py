"""Offline tests for the run dashboard aggregation and HTML rendering.

Fabricated ``audit.jsonl`` files only — no model calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fictionforge.observability.dashboard import (
    build_dashboard,
    build_run_view,
    render_index_html,
    render_run_html,
)


def _write_audit(run_dir: Path, events: list[dict]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "audit.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return run_dir


def _step_complete(step="world_generation", attempt=1, **kw):
    ev = {
        "event_type": "step_complete",
        "run_id": "run-1",
        "step": step,
        "attempt": attempt,
        "workflow_status": "running",
        "latency": 2.0,
        "token_usage": {"prompt_tokens": 12000, "completion_tokens": 2500,
                        "total_tokens": 14500},
        "invocation_id": f"inv-{step}-{attempt}",
        "provider": "devin",
        "devin_session_id": "able-baker",
        "session_type": "local_cli",
        "cost_details": {
            "actual_usd": None, "estimated_usd": None,
            "billed_acus": 0.02, "status": "actual",
            "source": "atif_export", "pricing_snapshot_id": None,
        },
    }
    ev.update(kw)
    return ev


def _reviewer_call(step="world_generation", attempt=1, **kw):
    ev = {
        "event_type": "reviewer_call",
        "run_id": "run-1",
        "step": step,
        "gate": "world",
        "attempt": attempt,
        "reviewer_id": "world_reviewer",
        "workflow_status": "running",
        "duration_s": 1.0,
        "token_usage": {"prompt_tokens": 3000, "completion_tokens": 200,
                        "total_tokens": 3200},
        "invocation_id": f"inv-rev-{attempt}",
        "provider": "devin",
        "devin_session_id": "calico-tiger",
        "session_type": "local_cli",
        "verdict": "approve",
        "ok": True,
        "cost_details": {
            "actual_usd": None, "estimated_usd": None,
            "billed_acus": 0.01, "status": "actual",
            "source": "atif_export", "pricing_snapshot_id": None,
        },
    }
    ev.update(kw)
    return ev


def test_run_view_rows_labels_and_attempts(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        _step_complete(attempt=1),
        _step_complete(attempt=2, devin_session_id="delta-echo"),
        _reviewer_call(),
        _step_complete(step="character_design"),
        {"event_type": "workflow_complete", "run_id": "run-1",
         "workflow_status": "completed"},
    ])
    view = build_run_view(run)
    labels = [(r["label"], r["attempt"]) for r in view["rows"]]
    assert labels == [
        ("World Generation", 1),
        ("World Generation", 2),
        ("World Reviewer", 1),
        ("Character Design", 1),
    ]
    assert view["rows"][1]["devin_session_id"] == "delta-echo"
    assert view["workflow_status"] == "completed"


def test_run_view_totals_never_zero_for_missing(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        _step_complete(),
        _reviewer_call(cost_details=None),  # unpriced
    ])
    view = build_run_view(run)
    t = view["totals"]
    assert t["total_billed_acus"] == pytest.approx(0.02)
    assert t["total_actual_usd"] is None  # no USD data -> None, not 0
    assert t["total_estimated_usd"] is None
    assert t["unpriced_invocations"] == 1
    assert t["priced_invocations"] == 1
    assert t["cost_per_workflow_acus"] is None  # not completed


def test_session_discovered_overlays_row(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        _step_complete(devin_session_id=None,
                       cost_details=None),
        {"event_type": "session_discovered", "run_id": "run-1",
         "invocation_id": "inv-world_generation-1",
         "devin_session_id": "found-later", "session_type": "local_cli",
         "session_id_status": "captured", "source": "atif_export"},
    ])
    view = build_run_view(run)
    assert view["rows"][0]["devin_session_id"] == "found-later"
    assert view["rows"][0]["session_id_status"] == "captured"


def test_cost_reconciliation_overlays_row(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        _step_complete(
            devin_session_id="able-baker",
            cost_details={
                "actual_usd": None, "estimated_usd": None,
                "billed_acus": None, "status": "pending_reconciliation",
                "source": None, "pricing_snapshot_id": None,
            }),
        {"event_type": "cost_reconciliation", "run_id": "run-1",
         "invocation_id": "inv-world_generation-1",
         "devin_session_id": "able-baker",
         "cost_details": {"billed_acus": 0.05, "status": "actual",
                          "source": "devin_sessions_db"},
         "reconciliation_source": "devin_sessions_db",
         "status": "reconciled"},
    ])
    view = build_run_view(run)
    row = view["rows"][0]
    assert row["billed_acus"] == pytest.approx(0.05)
    assert row["cost_status"] == "actual"
    assert row["cost_source"] == "devin_sessions_db"


def test_backward_compatible_old_events(tmp_path):
    """Pre-tracking events lack invocation keys — still render, unpriced."""
    run = _write_audit(tmp_path / "r1", [
        {"event_type": "step_complete", "run_id": "old",
         "step": "world_generation", "attempt": 1,
         "token_usage": {"prompt_tokens": 5, "completion_tokens": 1,
                         "total_tokens": 6},
         "workflow_status": "completed"},
    ])
    view = build_run_view(run)
    assert len(view["rows"]) == 1
    assert view["rows"][0]["invocation_id"] is None
    assert view["totals"]["invocations"] == 0
    assert view["totals"]["total_billed_acus"] is None


def test_render_html_contains_table_copy_no_zero_costs(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        _step_complete(),
        _reviewer_call(cost_details=None),
    ])
    html_text = render_run_html(build_run_view(run))
    assert "able-baker" in html_text
    assert 'data-sid="able-baker"' in html_text
    assert "World Reviewer" in html_text
    assert "0.02" in html_text  # ACU shown
    assert ">0 USD<" not in html_text  # unavailable never renders as zero
    assert "navigator.clipboard" in html_text
    # no external assets
    assert "http://" not in html_text and "https://" not in html_text.replace(
        "DOCTYPE", ""
    )


def test_build_dashboard_writes_pages(tmp_path):
    root = tmp_path / "runs"
    _write_audit(root / "runA", [_step_complete()])
    _write_audit(root / "runB", [_reviewer_call()])
    (root / "not-a-run").mkdir()  # no audit.jsonl -> skipped
    out = tmp_path / "dash"
    written = build_dashboard(root, out)
    names = {p.name for p in written}
    assert "index.html" in names
    assert (out / "index.html").exists()
    detail_pages = [p for p in written if p.name != "index.html"]
    assert len(detail_pages) == 2
    index = (out / "index.html").read_text()
    assert "Total ACU" in index


def test_render_index_links(tmp_path):
    views = [
        {"run_id": "abc", "workflow_status": "completed",
         "totals": {"invocations": 2, "total_billed_acus": 0.03,
                    "total_actual_usd": None, "unpriced_invocations": 0}},
    ]
    page = render_index_html(views)
    assert 'href="abc.html"' in page
    assert "0.03" in page


# ---------------------------------------------------------------------------
# Execution ordering + io previews + estimated USD
# ---------------------------------------------------------------------------


def test_rows_in_actual_execution_order(tmp_path):
    """reviewer_call precedes step_complete in the file; generation ran first."""
    run = _write_audit(tmp_path / "r1", [
        {"event_type": "step_start", "run_id": "r1", "step": "world_generation",
         "attempt": 1, "invocation_id": "inv-g1", "provider": "devin",
         "prompt_hash": "ph", "input_artifact_hashes": {"brief_file": "aa"},
         "workflow_status": "running", "timestamp": "2026-01-01T00:00:00"},
        _step_complete(
            invocation_id="inv-g1",
            timestamp="2026-01-01T00:03:00"),
        _reviewer_call(timestamp="2026-01-01T00:02:00"),
        _step_complete(step="character_design", invocation_id="inv-g2",
                       timestamp="2026-01-01T00:05:00"),
        {"event_type": "step_start", "run_id": "r1",
         "step": "character_design", "attempt": 1,
         "invocation_id": "inv-g2", "provider": "devin",
         "workflow_status": "running", "timestamp": "2026-01-01T00:03:30"},
    ])
    # Reorder file so reviewer_call lands before world step_complete.
    events = (run / "audit.jsonl").read_text().splitlines()
    order = [0, 2, 1, 4, 3]
    (run / "audit.jsonl").write_text("\n".join(events[i] for i in order) + "\n")
    view = build_run_view(run)
    labels = [(r["label"], r["kind"]) for r in view["rows"]]
    assert labels[0] == ("World Generation", "generation")
    assert labels[1] == ("World Reviewer", "review")
    assert labels[2][0] == "Character Design"


def test_io_preview_loaded(tmp_path):
    run = _write_audit(tmp_path / "r1", [_step_complete()])
    exdir = run / "session_exports"
    exdir.mkdir()
    (exdir / "inv-world_generation-1.io.json").write_text(json.dumps({
        "invocation_id": "inv-world_generation-1",
        "prompt": "Write a world about cats",
        "output": '{"world_name": "Catland"}',
    }))
    view = build_run_view(run)
    row = view["rows"][0]
    assert row["io_file"].endswith(".io.json")
    assert "cats" in row["prompt_preview"]
    assert "Catland" in row["output_preview"]
    page = render_run_html(view)
    assert "full prompt+output" in page
    assert "Catland" in page


def _step_complete_with_id(inv_id, **kw):
    ev = _step_complete()
    ev["invocation_id"] = inv_id
    ev.update(kw)
    return ev


def test_cost_details_estimated_usd_with_rate():
    from fictionforge.observability.consumption import (
        cost_details_for_invocation,
    )
    d = cost_details_for_invocation(
        {"billed_acus": 0.04}, acu_usd_rate=1.25,
        pricing_snapshot_id="acu-usd-x")
    assert d["estimated_usd"] == pytest.approx(0.05)
    assert d["actual_usd"] is None
    assert d["status"] == "actual"
    assert d["pricing_snapshot_id"] == "acu-usd-x"
    # No rate -> no estimate.
    d2 = cost_details_for_invocation({"billed_acus": 0.04})
    assert d2["estimated_usd"] is None
    assert d2["pricing_snapshot_id"] is None


def test_pricing_snapshot_immutable(tmp_path):
    from fictionforge.observability.pricing import snapshot_for_acu_rate
    sid1, c1 = snapshot_for_acu_rate(1.25, model="m1", snapshots_dir=tmp_path)
    sid2, _ = snapshot_for_acu_rate(1.25, model="m1", snapshots_dir=tmp_path)
    assert sid1 == sid2  # content-hash ID is stable
    f = tmp_path / f"{sid1}.json"
    assert f.exists()
    assert c1["rates"]["acu_to_usd"] == 1.25
    assert c1["currency"] == "USD"
    sid3, _ = snapshot_for_acu_rate(1.50, model="m1", snapshots_dir=tmp_path)
    assert sid3 != sid1  # a new rate never mutates history


def test_workflow_config_acu_rate(tmp_path):
    from fictionforge.config import WorkflowConfig
    cfg = WorkflowConfig.from_yaml("config/workflow.yaml")
    assert cfg.acu_usd_rate == 1.25


# ---------------------------------------------------------------------------
# review_start: pending review rows + live phase
# ---------------------------------------------------------------------------


def _review_start(step="world_generation", attempt=1, **kw):
    ev = {
        "event_type": "review_start",
        "run_id": "run-1",
        "step": step,
        "gate": "world",
        "attempt": attempt,
        "reviewer_id": "world_reviewer",
        "artifact_sha256": "f00dcafe" * 8,
        "review_mode": "enforced",
        "workflow_status": "running",
        "timestamp": "2026-01-01T00:01:00",
    }
    ev.update(kw)
    return ev


def test_review_start_creates_pending_row(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        {"event_type": "step_start", "run_id": "r1", "step": "world_generation",
         "attempt": 1, "invocation_id": "inv-g1", "provider": "devin",
         "workflow_status": "running", "timestamp": "2026-01-01T00:00:00"},
        _review_start(),
    ])
    view = build_run_view(run)
    assert len(view["rows"]) == 1
    row = view["rows"][0]
    assert row["kind"] == "review"
    assert row["label"] == "World Reviewer"
    assert row["pending"] is True
    assert row["input_artifact_hashes"]["world.json"] == "f00dcafe" * 8
    # Current-step indicator shows the review is live, not "generating".
    assert view["current"]["phase"] == "reviewing"
    page = render_run_html(view)
    assert "reviewing…" in page


def test_reviewer_call_fills_pending_row(tmp_path):
    run = _write_audit(tmp_path / "r1", [
        {"event_type": "step_start", "run_id": "r1", "step": "world_generation",
         "attempt": 1, "invocation_id": "inv-g1", "provider": "devin",
         "workflow_status": "running", "timestamp": "2026-01-01T00:00:00"},
        _review_start(),
        _reviewer_call(timestamp="2026-01-01T00:02:00", verdict="approve"),
        _step_complete(invocation_id="inv-g1",
                       timestamp="2026-01-01T00:02:05"),
    ])
    view = build_run_view(run)
    review_rows = [r for r in view["rows"] if r["kind"] == "review"]
    assert len(review_rows) == 1  # filled in place, not duplicated
    row = review_rows[0]
    assert row["pending"] is False
    assert row["verdict"] == "approve"
    assert row["devin_session_id"] == "calico-tiger"
    assert row["billed_acus"] == pytest.approx(0.01)
    # Row order: generation first (sorted by step_start), review second
    # (sorted by review_start — not where reviewer_call lands in the file).
    assert [r["kind"] for r in view["rows"]] == ["generation", "review"]


def test_reviewer_call_without_start_appends_normally(tmp_path):
    """Old logs (no review_start) still get a normal reviewer row."""
    run = _write_audit(tmp_path / "r1", [_reviewer_call()])
    view = build_run_view(run)
    assert len(view["rows"]) == 1
    assert view["rows"][0]["pending"] is False
