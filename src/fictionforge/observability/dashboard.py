"""Dashboard aggregation and rendering for FictionForge workflow runs.

Reads a run's append-only ``audit.jsonl`` and produces:

* a per-invocation cost/session table (generator steps, reviewer calls and
  every retry attempt, each with its Devin session ID, token usage, cost and
  cost source), and
* run totals: actual ACU cost, actual/estimated USD, unpriced invocations,
  cost per completed workflow, pricing snapshots used and reconciliation
  status.

Rendering is a single self-contained HTML file — no server, no external
assets.  Unavailable values are rendered as ``—`` and are *never* shown as
zero.  Original audit events are never rewritten; post-hoc session and cost
data arrive through ``session_discovered`` / ``cost_reconciliation`` events
which this module overlays onto the invocation rows.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

_STEP_LABELS = {
    "world_generation": "World Generation",
    "character_design": "Character Design",
    "storyboard_building": "Storyboard Building",
}

# Steps whose step_complete events represent LLM invocations.  Deterministic
# stages (load_brief, gate plumbing, …) also emit step_complete but have no
# invocation_id; they are pipeline bookkeeping, not model calls.
_LLM_STEPS = set(_STEP_LABELS)

# Final artifact file each LLM step persists in the run directory.
_ARTIFACT_FILES = {
    "world_generation": "world.json",
    "character_design": "characters.json",
    "storyboard_building": "storyboard.json",
}

_REVIEWER_LABELS = {
    "world_reviewer": "World Reviewer",
    "character_reviewer": "Character Reviewer",
    "storyboard_reviewer": "Storyboard Reviewer",
}

# Cost statuses considered resolved (vs. still unpriced).
_PRICED_STATUSES = {"actual", "estimated"}


def load_audit_events(run_dir: Path) -> list[dict[str, Any]]:
    """Load ``audit.jsonl`` for a run; returns [] when absent."""
    path = Path(run_dir) / "audit.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _step_label(step: str | None) -> str:
    if step is None:
        return "—"
    if step in _STEP_LABELS:
        return _STEP_LABELS[step]
    return step.replace("_", " ").title()


def _reviewer_label(reviewer_id: str | None, step: str | None) -> str:
    if reviewer_id and reviewer_id in _REVIEWER_LABELS:
        return _REVIEWER_LABELS[reviewer_id]
    base = _step_label(step).removesuffix(" Generation").removesuffix(
        " Design"
    ).removesuffix(" Building")
    return f"{base} Reviewer"


def _row_from_event(ev: dict[str, Any], *, kind: str) -> dict[str, Any]:
    cost = ev.get("cost_details") or {}
    usage = ev.get("token_usage") or {}
    if kind == "review":
        label = _reviewer_label(ev.get("reviewer_id"), ev.get("step"))
    else:
        label = _step_label(ev.get("step"))
    return {
        "label": label,
        "kind": kind,
        "step": ev.get("step"),
        "gate": ev.get("gate"),
        "reviewer_id": ev.get("reviewer_id"),
        "attempt": ev.get("attempt"),
        "invocation_id": ev.get("invocation_id"),
        "provider": ev.get("provider"),
        "devin_session_id": ev.get("devin_session_id"),
        "session_type": ev.get("session_type"),
        "session_id_status": ev.get("session_id_status"),
        "session_id_reason": ev.get("session_id_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "latency_s": ev.get("latency") if kind == "generation" else ev.get(
            "duration_s", ev.get("latency_s")
        ),
        "billed_acus": cost.get("billed_acus"),
        "actual_usd": cost.get("actual_usd"),
        "estimated_usd": cost.get("estimated_usd"),
        "cost_status": cost.get("status"),
        "cost_source": cost.get("source"),
        "pricing_snapshot_id": cost.get("pricing_snapshot_id"),
        "verdict": ev.get("verdict"),
        "failure_code": ev.get("failure_code"),
        "retry_decision": ev.get("retry_decision"),
        "ok": ev.get("ok") if kind == "review" else None,
        # Per-step input/output
        "prompt_hash": None,  # filled from the step_start event
        "input_artifact_hashes": None,
        "output_artifact_hash": ev.get("output_artifact_hash")
        or ev.get("artifact_sha256"),
        "artifact_name": _ARTIFACT_FILES.get(ev.get("step")),
        "validation_results": ev.get("validation_results"),
        "findings": ev.get("findings"),
        "event_ts": ev.get("timestamp"),
        "started_ts": None,  # step_start timestamp, for execution ordering
        # Prompt/output preview filled from session_exports/<inv>.io.json
        "io_file": None,
        "prompt_preview": None,
        "output_preview": None,
    }


def build_run_view(run_dir: Path) -> dict[str, Any]:
    """Aggregate one run directory into a dashboard view dict."""
    run_dir = Path(run_dir)
    events = load_audit_events(run_dir)

    rows: list[dict[str, Any]] = []
    row_by_invocation: dict[str, dict[str, Any]] = {}
    step_starts: dict[str, dict[str, Any]] = {}
    # (step, attempt) -> pending review row created by review_start, to be
    # filled in by the matching reviewer_call event when the review returns.
    pending_reviews: dict[tuple[Any, Any], dict[str, Any]] = {}
    # In-flight pipeline position: (step, attempt) -> {"idx", "in_review"}
    open_steps: dict[tuple[Any, Any], dict[str, Any]] = {}
    run_id: str | None = None
    workflow_status: str | None = None
    discovered: dict[str, dict[str, Any]] = {}
    reconciliations: list[dict[str, Any]] = []

    for idx, ev in enumerate(events):
        etype = ev.get("event_type")
        run_id = run_id or ev.get("run_id")
        if ev.get("workflow_status"):
            workflow_status = ev["workflow_status"]
        if etype == "step_start":
            open_steps[(ev.get("step"), ev.get("attempt"))] = {
                "idx": idx,
                "in_review": False,
            }
            if ev.get("invocation_id"):
                ev["_idx"] = idx
                step_starts[ev["invocation_id"]] = ev
        elif etype == "step_complete":
            open_steps.pop((ev.get("step"), ev.get("attempt")), None)
            # Skip deterministic non-LLM stages (load_brief etc.): they log
            # step_start/step_complete but carry no invocation_id and are not
            # model calls.  Pre-tracking LLM-step events (no invocation_id)
            # are still shown for backward compatibility.
            if ev.get("invocation_id") is None and ev.get("step") not in _LLM_STEPS:
                continue
            row = _row_from_event(ev, kind="generation")
            start = step_starts.get(row["invocation_id"] or "")
            # Execution order: the step ran from step_start even though its
            # step_complete lands after the gate review in the audit file.
            row["sort_key"] = start.get("_idx", idx) if start else idx
            if start:
                row["started_ts"] = start.get("timestamp")
                row["prompt_hash"] = start.get("prompt_hash")
                row["input_artifact_hashes"] = start.get(
                    "input_artifact_hashes"
                )
            rows.append(row)
            if row["invocation_id"]:
                row_by_invocation[row["invocation_id"]] = row
        elif etype == "review_start":
            key = (ev.get("step"), ev.get("attempt"))
            open_step = open_steps.get(key)
            if open_step is not None:
                open_step["in_review"] = True
            # Placeholder row so the review is visible while it runs; the
            # matching reviewer_call fills it in place.
            row = _row_from_event(ev, kind="review")
            row["pending"] = True
            row["sort_key"] = idx
            row["started_ts"] = ev.get("timestamp")
            if ev.get("artifact_sha256"):
                row["input_artifact_hashes"] = {
                    row["artifact_name"] or "artifact": ev["artifact_sha256"]
                }
            pending_reviews[key] = row
            rows.append(row)
        elif etype == "reviewer_call":
            open_step = open_steps.get((ev.get("step"), ev.get("attempt")))
            if open_step is not None:
                open_step["in_review"] = True
            row = _row_from_event(ev, kind="review")
            row["prompt_hash"] = ev.get("reviewer_prompt_sha256")
            if ev.get("artifact_sha256"):
                row["input_artifact_hashes"] = {
                    row["artifact_name"] or "artifact": ev["artifact_sha256"]
                }
            # Merge into the review_start placeholder when present: the row
            # keeps the position where the review actually began.
            pending = pending_reviews.pop(
                (ev.get("step"), ev.get("attempt")), None
            )
            if pending is not None:
                sort_key = pending["sort_key"]
                started = pending.get("started_ts")
                pending.update(row)
                pending["sort_key"] = sort_key
                pending["started_ts"] = started
                pending["pending"] = False
                row = pending
            else:
                row["started_ts"] = ev.get("timestamp")
                row["sort_key"] = idx
                row["pending"] = False
                rows.append(row)
            if row["invocation_id"]:
                row_by_invocation[row["invocation_id"]] = row
        elif etype == "session_discovered":
            if ev.get("invocation_id"):
                discovered[ev["invocation_id"]] = ev
        elif etype == "cost_reconciliation":
            reconciliations.append(ev)

    # Current pipeline position for live views: the most recently opened
    # step that has not completed, with its phase.
    current: dict[str, Any] | None = None
    if open_steps:
        (step, attempt), info = max(
            open_steps.items(), key=lambda kv: kv[1]["idx"]
        )
        current = {
            "step": step,
            "label": _step_label(step),
            "attempt": attempt,
            "phase": "reviewing" if info["in_review"] else "generating",
        }

    # Actual execution order: generation rows sort by their step_start,
    # reviewer rows by their reviewer_call event.
    rows.sort(key=lambda r: r.get("sort_key", 0))

    # Per-invocation prompt/output previews from <inv>.io.json siblings.
    exports_dir = run_dir / "session_exports"
    for row in rows:
        inv_id = row.get("invocation_id")
        if not inv_id:
            continue
        io_path = exports_dir / f"{inv_id}.io.json"
        if not io_path.exists():
            continue
        try:
            io_data = json.loads(io_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        row["io_file"] = f"session_exports/{inv_id}.io.json"
        prompt = io_data.get("prompt") or ""
        output = io_data.get("output") or ""
        row["prompt_preview"] = prompt[:400] or None
        row["output_preview"] = output[:400] or None

    # Overlay post-hoc session IDs (append-only discovery events).
    for inv_id, disc in discovered.items():
        row = row_by_invocation.get(inv_id)
        if row is not None:
            if disc.get("devin_session_id"):
                row["devin_session_id"] = disc["devin_session_id"]
            if disc.get("session_type"):
                row["session_type"] = disc["session_type"]
            row["session_id_status"] = disc.get(
                "session_id_status", row["session_id_status"]
            )
            if disc.get("session_id_reason"):
                row["session_id_reason"] = disc["session_id_reason"]

    # Overlay reconciliation outcomes (latest event wins, file order).
    for rec in reconciliations:
        inv_id = rec.get("invocation_id")
        row = row_by_invocation.get(inv_id) if inv_id else None
        cost = rec.get("cost_details") or {}
        if row is not None and rec.get("status") == "reconciled":
            for key in (
                "billed_acus",
                "actual_usd",
                "estimated_usd",
                "pricing_snapshot_id",
            ):
                if cost.get(key) is not None:
                    row[key] = cost[key]
            if cost.get("status"):
                row["cost_status"] = cost["status"]
            row["cost_source"] = (
                cost.get("source") or rec.get("reconciliation_source")
            )

    invocations = [r for r in rows if r["invocation_id"]]
    priced = [r for r in invocations if r["cost_status"] in _PRICED_STATUSES]
    unpriced = [r for r in invocations if r["cost_status"] not in _PRICED_STATUSES]

    acu_vals = [r["billed_acus"] for r in rows if r["billed_acus"] is not None]
    usd_actual = [r["actual_usd"] for r in rows if r["actual_usd"] is not None]
    usd_est = [r["estimated_usd"] for r in rows if r["estimated_usd"] is not None]
    snapshots = sorted(
        {r["pricing_snapshot_id"] for r in rows if r["pricing_snapshot_id"]}
    )
    status_counts: dict[str, int] = {}
    for r in invocations:
        st = r["cost_status"] or "unavailable"
        status_counts[st] = status_counts.get(st, 0) + 1

    total_acus = sum(acu_vals) if acu_vals else None
    totals = {
        "invocations": len(invocations),
        "priced_invocations": len(priced),
        "unpriced_invocations": len(unpriced),
        "total_billed_acus": total_acus,
        "total_actual_usd": sum(usd_actual) if usd_actual else None,
        "total_estimated_usd": sum(usd_est) if usd_est else None,
        "cost_per_workflow_acus": (
            total_acus if workflow_status == "completed" else None
        ),
        "pricing_snapshot_ids": snapshots,
        "cost_status_counts": status_counts,
    }
    return {
        "run_id": run_id or run_dir.name,
        "run_dir": str(run_dir),
        "workflow_status": workflow_status,
        "current": current,
        "rows": rows,
        "by_step": aggregate_steps(rows),
        "totals": totals,
        "reconciliation_events": len(reconciliations),
    }


def aggregate_steps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group invocation rows by step label into per-step cost metrics.

    ``billed_acus`` is ``None`` when no row reported ACUs (never zero for
    missing data).
    """
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rows:
        label = r["label"]
        if label not in grouped:
            grouped[label] = {
                "label": label,
                "kind": r["kind"],
                "invocations": 0,
                "billed_acus": None,
                "unpriced_invocations": 0,
            }
            order.append(label)
        g = grouped[label]
        g["invocations"] += 1
        if r["billed_acus"] is not None:
            g["billed_acus"] = (g["billed_acus"] or 0.0) + r["billed_acus"]
        if r["invocation_id"] and r["cost_status"] not in _PRICED_STATUSES:
            g["unpriced_invocations"] += 1
    return [grouped[label] for label in order]


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: -apple-system, 'SF Mono', Menlo, monospace; margin: 2rem;
       color: #1a1a1a; background: #fafafa; }
h1 { font-size: 1.3rem; } h2 { font-size: 1rem; margin-top: 1.5rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #ddd; }
th { background: #efefef; font-weight: 600; }
tr.review td { background: #f4f6fb; }
.sid { font-family: Menlo, monospace; font-size: 0.8rem; }
.copy { border: 1px solid #bbb; background: #fff; border-radius: 3px;
        cursor: pointer; font-size: 0.7rem; padding: 1px 6px; margin-left: 6px; }
.na { color: #999; } .actual { color: #0a6; } .pending { color: #c80; }
.unavailable { color: #a33; }
.meta { color: #555; font-size: 0.85rem; }
.totals td { background: #fff; }
details.io { font-size: 0.75rem; }
details.io summary { cursor: pointer; color: #06c; }
details.io div { padding: 4px 0; white-space: pre-wrap; line-height: 1.5; }
details.io code { font-size: 0.7rem; }
"""


def _fmt_num(v: Any, unit: str = "", digits: int = 6) -> str:
    if v is None:
        return '<span class="na">—</span>'
    if isinstance(v, float):
        text = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    else:
        text = f"{v:,}"
    return f"{text}{unit}"


def _fmt_dur(v: Any) -> str:
    if v is None:
        return '<span class="na">—</span>'
    v = float(v)
    if v >= 60:
        return f"{int(v // 60)}m {v % 60:.0f}s"
    return f"{v:.1f}s"


def _fmt_tokens(row: dict[str, Any]) -> str:
    if row["total_tokens"] is None and row["prompt_tokens"] is None:
        return '<span class="na">—</span>'
    total = row["total_tokens"]
    p = row["prompt_tokens"]
    c = row["completion_tokens"]
    if total is None:
        total = (p or 0) + (c or 0)
    return (
        f'{total:,} <span class="na">({(p or 0):,} in / '
        f"{(c or 0):,} out)</span>"
    )


def _status_html(status: str | None) -> str:
    if not status:
        return '<span class="na">—</span>'
    cls = {
        "actual": "actual",
        "estimated": "actual",
        "pending_reconciliation": "pending",
    }.get(status, "unavailable")
    return f'<span class="{cls}">{html.escape(status)}</span>'


def _session_cell(row: dict[str, Any]) -> str:
    sid = row["devin_session_id"]
    if not sid:
        reason = row.get("session_id_reason") or "unavailable"
        return f'<span class="na">—</span> <span class="na">({html.escape(str(reason))})</span>'
    esc = html.escape(sid)
    return (
        f'<span class="sid">{esc}</span>'
        f'<button class="copy" data-sid="{esc}">copy</button>'
    )


def _short_hash(h: Any) -> str:
    return f"{h[:12]}…" if isinstance(h, str) and len(h) > 12 else str(h)


def _io_cell(row: dict[str, Any], run_id: str) -> str:
    """Collapsible per-step input/output details."""
    lines: list[str] = []
    inputs = row.get("input_artifact_hashes") or {}
    if inputs:
        lines.append(
            "in:  "
            + ", ".join(
                f"{k} <code>{html.escape(_short_hash(v))}</code>"
                for k, v in inputs.items()
            )
        )
    if row.get("prompt_hash"):
        lines.append(
            f"prompt sha: <code>{html.escape(_short_hash(row['prompt_hash']))}</code>"
        )
    if row.get("prompt_preview"):
        lines.append(
            f"prompt: <code>{html.escape(row['prompt_preview'][:300])}</code>"
        )
    if row.get("output_preview"):
        lines.append(
            f"output: <code>{html.escape(row['output_preview'][:300])}</code>"
        )
    if row.get("io_file"):
        lines.append(
            f'<a href="/run/{html.escape(run_id)}/file/{html.escape(row["io_file"])}">'
            "full prompt+output</a>"
        )
    out = row.get("output_artifact_hash")
    name = row.get("artifact_name")
    if out or name:
        link = (
            f' <a href="/run/{html.escape(run_id)}/file/{html.escape(name)}">view</a>'
            if name
            else ""
        )
        lines.append(
            f"out: {html.escape(name or 'artifact')} "
            f"<code>{html.escape(_short_hash(out))}</code>{link}"
        )
    vr = row.get("validation_results")
    if vr:
        failed = sum(
            1
            for v in vr
            if isinstance(v, dict)
            and (v.get("status") == "failed" or v.get("passed") is False)
        )
        lines.append(
            f"validation: {len(vr)} checks, {failed} failed"
        )
    if row.get("verdict"):
        findings = row.get("findings") or []
        codes = ", ".join(
            f.get("code", "?") for f in findings if isinstance(f, dict)
        )
        suffix = f" · findings: {html.escape(codes)}" if codes else ""
        lines.append(f"verdict: {html.escape(str(row['verdict']))}{suffix}")
    if not lines:
        return '<span class="na">—</span>'
    return (
        '<details class="io"><summary>i/o</summary><div>'
        + "<br>".join(lines)
        + "</div></details>"
    )


def render_run_html(view: dict[str, Any]) -> str:
    """Render one run view as a self-contained workflow detail page."""
    rows_html = []
    for r in view["rows"]:
        cls = ' class="review"' if r["kind"] == "review" else ""
        attempt = r["attempt"] if r["attempt"] is not None else "—"
        rows_html.append(
            f"<tr{cls}>"
            f"<td>{html.escape(r['label'])}</td>"
            f"<td>{attempt}</td>"
            f"<td>{_session_cell(r)}</td>"
            f"<td>{_fmt_tokens(r)}</td>"
            f"<td>{'<span class=\"pending\">reviewing…</span>' if r.get('pending') else _fmt_dur(r['latency_s'])}</td>"
            f"<td>{_fmt_num(r['billed_acus'], ' ACU')}</td>"
            f"<td>{_fmt_num(r['actual_usd'], ' USD', 4)}</td>"
            f"<td>{_fmt_num(r['estimated_usd'], ' USD', 4)}</td>"
            f"<td>{_status_html(r['cost_status'])}</td>"
            f"<td>{html.escape(str(r['cost_source'] or '—'))}</td>"
            f"<td>{_io_cell(r, view['run_id'])}</td>"
            "</tr>"
        )
    t = view["totals"]
    snaps = ", ".join(t["pricing_snapshot_ids"]) or "—"
    counts = ", ".join(
        f"{k}: {v}" for k, v in sorted(t["cost_status_counts"].items())
    ) or "—"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>FictionForge run {html.escape(view['run_id'])}</title>
<style>{_CSS}</style></head><body>
<h1>FictionForge run <code>{html.escape(view['run_id'])}</code></h1>
<p class="meta">status: {html.escape(str(view['workflow_status'] or '—'))}
 · dir: <code>{html.escape(view['run_dir'])}</code></p>

<h2>Invocations</h2>
<table><thead><tr>
<th>Step</th><th>Attempt</th><th>Devin Session</th><th>Tokens</th><th>Time</th>
<th>ACU</th><th>Actual USD</th><th>Est. USD</th><th>Cost Status</th><th>Source</th><th>I/O</th>
</tr></thead><tbody>
{''.join(rows_html) or '<tr><td colspan="11" class="na">no invocation events</td></tr>'}
</tbody></table>

<h2>Totals</h2>
<table class="totals"><tbody>
<tr><th>Total actual cost (ACU)</th><td>{_fmt_num(t['total_billed_acus'], ' ACU')}</td></tr>
<tr><th>Total actual cost (USD)</th><td>{_fmt_num(t['total_actual_usd'], ' USD', 4)}</td></tr>
<tr><th>Total estimated cost (USD)</th><td>{_fmt_num(t['total_estimated_usd'], ' USD', 4)}</td></tr>
<tr><th>Cost per completed workflow (ACU)</th><td>{_fmt_num(t['cost_per_workflow_acus'], ' ACU')}</td></tr>
<tr><th>Invocations</th><td>{t['invocations']}</td></tr>
<tr><th>Unpriced invocations</th><td>{t['unpriced_invocations']}</td></tr>
<tr><th>Pricing snapshots used</th><td>{html.escape(snaps)}</td></tr>
<tr><th>Reconciliation status</th><td>{html.escape(counts)}</td></tr>
</tbody></table>

<script>
document.querySelectorAll('button.copy').forEach(function(b) {{
  b.addEventListener('click', function() {{
    navigator.clipboard.writeText(b.getAttribute('data-sid'));
    b.textContent = 'copied'; setTimeout(function() {{ b.textContent = 'copy'; }}, 1200);
  }});
}});
</script>
</body></html>
"""


def render_index_html(views: list[dict[str, Any]]) -> str:
    """Render a runs index linking to each detail page."""
    rows = []
    for v in views:
        t = v["totals"]
        rows.append(
            "<tr>"
            f'<td><a href="{html.escape(v["run_id"])}.html"><code>{html.escape(v["run_id"])}</code></a></td>'
            f"<td>{html.escape(str(v['workflow_status'] or '—'))}</td>"
            f"<td>{t['invocations']}</td>"
            f"<td>{_fmt_num(t['total_billed_acus'], ' ACU')}</td>"
            f"<td>{_fmt_num(t['total_actual_usd'], ' USD', 4)}</td>"
            f"<td>{t['unpriced_invocations']}</td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>FictionForge runs</title>
<style>{_CSS}</style></head><body>
<h1>FictionForge runs</h1>
<table><thead><tr>
<th>Run</th><th>Status</th><th>Invocations</th><th>Total ACU</th>
<th>Total USD</th><th>Unpriced</th>
</tr></thead><tbody>
{''.join(rows) or '<tr><td colspan="6" class="na">no runs</td></tr>'}
</tbody></table>
</body></html>
"""


def build_dashboard(runs_root: Path, out_dir: Path) -> list[Path]:
    """Render ``index.html`` + one detail page per run under ``out_dir``."""
    runs_root = Path(runs_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    views = [
        build_run_view(d)
        for d in sorted(runs_root.iterdir())
        if d.is_dir() and (d / "audit.jsonl").exists()
    ]
    written = [out_dir / "index.html"]
    for v in views:
        page = out_dir / f"{v['run_id']}.html"
        page.write_text(render_run_html(v), encoding="utf-8")
        written.append(page)
    written[0].write_text(render_index_html(views), encoding="utf-8")
    return written


__all__ = [
    "aggregate_steps",
    "build_dashboard",
    "build_run_view",
    "load_audit_events",
    "render_index_html",
    "render_run_html",
]
