"""Live dashboard server for FictionForge runs — stdlib only.

Serves a dynamic page over ``http.server`` that watches a runs directory and
pushes updates to the browser via Server-Sent Events (SSE).  No external
dependencies, no websockets, no model calls.

Routes:

* ``GET /``                    — runs index (live, SSE-driven)
* ``GET /run/<run_id>``        — run detail page (live, SSE-driven)
* ``GET /api/runs``            — JSON summaries for all runs
* ``GET /api/run/<run_id>``    — JSON: ``{view, state, age_s, last_activity_at}``
* ``GET /api/stream``          — SSE: run list changes
* ``GET /api/stream/run/<id>`` — SSE: one run's audit file changes
* ``GET /run/<id>/file/<name>``— read-only file serve from a run directory

Change detection is file mtime/size polling — ``audit.jsonl`` is append-only,
so a changed fingerprint means new events to re-aggregate.  A run is
considered *running* while its latest ``workflow_status`` is ``running``
(or absent); a quiet-but-running file is flagged ``stalled`` so a wedged
workflow is visible instead of silently green.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fictionforge.observability.dashboard import build_run_view

TERMINAL_STATUSES = {"completed", "failed_automated", "punch_out_required"}
STALL_AFTER_S = 60.0
DEFAULT_POLL_S = 1.0
KEEPALIVE_S = 15.0


def run_state(workflow_status: str | None, age_s: float) -> str:
    """Classify a run: ``running`` | ``stalled`` | terminal status."""
    if workflow_status in TERMINAL_STATUSES:
        return workflow_status
    if workflow_status == "running" and age_s > STALL_AFTER_S:
        return "stalled"
    return "running" if workflow_status in (None, "running") else workflow_status


def audit_fingerprint(run_dir: Path) -> tuple[int, int] | None:
    """(mtime_ns, size) of a run's audit file — None when absent."""
    try:
        st = (Path(run_dir) / "audit.jsonl").stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def run_summary(run_dir: Path, now: float | None = None) -> dict[str, Any]:
    """Lightweight per-run summary for the index (full view on detail)."""
    run_dir = Path(run_dir)
    fp = audit_fingerprint(run_dir)
    now = time.time() if now is None else now
    last_at = fp[0] / 1e9 if fp else None
    age_s = max(0.0, now - last_at) if last_at else 0.0
    view = build_run_view(run_dir)
    t = view["totals"]
    return {
        "run_id": view["run_id"],
        "workflow_status": view["workflow_status"],
        "state": run_state(view["workflow_status"], age_s),
        "current": view.get("current"),
        "age_s": round(age_s, 1),
        "last_activity_at": last_at,
        "invocations": t["invocations"],
        "unpriced_invocations": t["unpriced_invocations"],
        "total_billed_acus": t["total_billed_acus"],
        "total_actual_usd": t["total_actual_usd"],
        "total_estimated_usd": t["total_estimated_usd"],
    }


def run_live(run_dir: Path, now: float | None = None) -> dict[str, Any]:
    """Full run view plus live state, for the detail page/API."""
    run_dir = Path(run_dir)
    fp = audit_fingerprint(run_dir)
    now = time.time() if now is None else now
    last_at = fp[0] / 1e9 if fp else None
    age_s = max(0.0, now - last_at) if last_at else 0.0
    view = build_run_view(run_dir)
    return {
        "view": view,
        "state": run_state(view["workflow_status"], age_s),
        "age_s": round(age_s, 1),
        "last_activity_at": last_at,
    }


def scan_runs(runs_root: Path, now: float | None = None) -> list[dict[str, Any]]:
    """Summaries for every run dir with an ``audit.jsonl``.

    Running/stalled runs first, then most-recently-active.
    """
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        return []
    out = []
    for d in runs_root.iterdir():
        if d.is_dir() and (d / "audit.jsonl").exists():
            out.append(run_summary(d, now=now))
    # Most recent activity first (running runs are naturally on top).
    out.sort(key=lambda s: s["last_activity_at"] or 0.0, reverse=True)
    return out


# ---------------------------------------------------------------------------
# HTML shells — JS fetches JSON + subscribes to SSE
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: -apple-system, 'SF Mono', Menlo, monospace; margin: 2rem;
       color: #1a1a1a; background: #fafafa; }
h1 { font-size: 1.3rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #ddd; }
th { background: #efefef; font-weight: 600; }
tr.review td { background: #f4f6fb; }
.sid { font-family: Menlo, monospace; font-size: 0.8rem; }
.copy { border: 1px solid #bbb; background: #fff; border-radius: 3px;
        cursor: pointer; font-size: 0.7rem; padding: 1px 6px; margin-left: 6px; }
.na { color: #999; }
.state-running { color: #06c; font-weight: 600; }
.state-stalled { color: #c80; font-weight: 600; }
.state-completed { color: #0a6; }
.state-failed_automated, .state-punch_out_required { color: #a33; }
.actual { color: #0a6; } .pending { color: #c80; } .unavailable { color: #a33; }
.meta { color: #555; font-size: 0.85rem; }
details.io { font-size: 0.75rem; }
details.io summary { cursor: pointer; color: #06c; }
details.io div { padding: 4px 0; white-space: pre-wrap; line-height: 1.5; }
details.io code { font-size: 0.7rem; }
#conn { font-size: 0.75rem; color: #888; }
.dot { display:inline-block; width:8px; height:8px; border-radius:4px;
       background:#ccc; margin-right:5px; }
.dot.live { background:#0a6; } .dot.dead { background:#a33; }
"""

_JS_COMMON = """
function fmtNum(v, unit, digits) {
  if (v === null || v === undefined) return '<span class="na">—</span>';
  if (typeof v === 'number' && !Number.isInteger(v))
    return v.toFixed(digits || 6).replace(/0+$/, '').replace(/\\.$/, '') + unit;
  return Number(v).toLocaleString() + unit;
}
function fmtDur(v) {
  if (v === null || v === undefined) return '<span class="na">—</span>';
  v = Number(v);
  if (v >= 60) return Math.floor(v / 60) + 'm ' + Math.round(v % 60) + 's';
  return v.toFixed(1) + 's';
}
function fmtTokens(r) {
  if (r.total_tokens === null && r.prompt_tokens === null)
    return '<span class="na">—</span>';
  const t = r.total_tokens !== null ? r.total_tokens :
    (r.prompt_tokens || 0) + (r.completion_tokens || 0);
  return t.toLocaleString() + ' <span class="na">(' +
    (r.prompt_tokens || 0).toLocaleString() + ' in / ' +
    (r.completion_tokens || 0).toLocaleString() + ' out)</span>';
}
function statusHtml(s) {
  if (!s) return '<span class="na">—</span>';
  const cls = {actual: 'actual', estimated: 'actual',
               pending_reconciliation: 'pending'}[s] || 'unavailable';
  return '<span class="' + cls + '">' + s + '</span>';
}
function esc(s) { const d = document.createElement('div');
  d.textContent = s; return d.innerHTML; }
function wireCopy(root) {
  root.querySelectorAll('button.copy').forEach(function(b) {
    b.onclick = function() {
      navigator.clipboard.writeText(b.getAttribute('data-sid'));
      b.textContent = 'copied';
      setTimeout(function() { b.textContent = 'copy'; }, 1200);
    };
  });
}
function setConn(live) {
  const d = document.getElementById('dot');
  if (d) d.className = 'dot ' + (live ? 'live' : 'dead');
}
function shortHash(h) {
  return (typeof h === 'string' && h.length > 12) ? h.slice(0, 12) + '…' : h;
}
function fmtAge(ageS, lastAt) {
  // Readable "x ago" with exact datetime on hover.
  const d = Math.floor(ageS / 86400);
  let txt;
  if (d >= 30) txt = Math.floor(d / 30.44) + 'mo ago';
  else if (d >= 1) txt = d + 'd ago';
  else if (ageS >= 3600) txt = Math.floor(ageS / 3600) + 'h ago';
  else if (ageS >= 60) txt = Math.floor(ageS / 60) + 'm ago';
  else txt = Math.round(ageS) + 's ago';
  const exact = lastAt ? new Date(lastAt * 1000).toLocaleString() : 'never';
  return '<span title="' + exact + '">' + txt + '</span>';
}
function ioCell(r, runId) {
  const lines = [];
  const ins = r.input_artifact_hashes || {};
  const inParts = Object.entries(ins).map(function(kv) {
    return kv[0] + ' <code>' + esc(shortHash(kv[1])) + '</code>';
  });
  if (inParts.length) lines.push('in:  ' + inParts.join(', '));
  if (r.prompt_hash)
    lines.push('prompt sha: <code>' + esc(shortHash(r.prompt_hash)) + '</code>');
  if (r.prompt_preview)
    lines.push('prompt: <code>' + esc(r.prompt_preview.slice(0, 300)) + '</code>');
  if (r.output_preview)
    lines.push('output: <code>' + esc(r.output_preview.slice(0, 300)) + '</code>');
  if (r.io_file)
    lines.push('<a href="/run/' + encodeURIComponent(runId) + '/file/' +
      r.io_file.split('/').map(encodeURIComponent).join('/') +
      '">full prompt+output</a>');
  if (r.output_artifact_hash || r.artifact_name) {
    const link = r.artifact_name
      ? ' <a href="/run/' + encodeURIComponent(runId) + '/file/' +
        encodeURIComponent(r.artifact_name) + '">view</a>' : '';
    lines.push('out: ' + esc(r.artifact_name || 'artifact') + ' <code>' +
      esc(shortHash(r.output_artifact_hash)) + '</code>' + link);
  }
  const vr = r.validation_results;
  if (vr && vr.length) {
    const failed = vr.filter(function(v) {
      return v.status === 'failed' || v.passed === false;
    }).length;
    lines.push('validation: ' + vr.length + ' checks, ' + failed + ' failed');
  }
  if (r.verdict) {
    const codes = (r.findings || []).map(function(f) { return f.code; })
      .filter(Boolean).join(', ');
    lines.push('verdict: ' + esc(r.verdict) +
      (codes ? ' · findings: ' + esc(codes) : ''));
  }
  if (!lines.length) return '<span class="na">—</span>';
  return '<details class="io"><summary>i/o</summary><div>' +
    lines.join('<br>') + '</div></details>';
}
"""

_INDEX_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>FictionForge live runs</title>
<style>__CSS__</style></head><body>
<h1>FictionForge live runs <span id="conn"><span class="dot" id="dot"></span>live</span></h1>
<table><thead><tr>
<th>Run</th><th>State</th><th>Current step</th><th>Last activity</th>
<th>Invocations</th><th>Total ACU</th><th>Est. USD</th><th>Unpriced</th>
</tr></thead><tbody id="rows"></tbody></table>
<div class="meta" style="margin-top:0.6rem">
<button class="copy" id="prev">&larr; prev</button>
<span id="pageinfo" style="margin:0 8px"></span>
<button class="copy" id="next">next &rarr;</button>
</div>
<script>
__JS__
function currentCell(s) {
  const c = s.current;
  if (!c || s.state === 'completed' || s.state === 'failed_automated' ||
      s.state === 'punch_out_required')
    return '<span class="na">—</span>';
  return esc(c.label) + ' <span class="na">attempt ' + (c.attempt || 1) +
    ' · ' + esc(c.phase) + '</span>';
}
var allRuns = [], page = 0, PAGE_SIZE = 10;
function draw() {
  const pages = Math.max(1, Math.ceil(allRuns.length / PAGE_SIZE));
  if (page >= pages) page = pages - 1;
  const slice = allRuns.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  document.getElementById('pageinfo').textContent =
    'page ' + (page + 1) + ' of ' + pages + ' (' + allRuns.length + ' runs)';
  render(slice);
}
document.getElementById('prev').onclick = function() {
  if (page > 0) { page--; draw(); } };
document.getElementById('next').onclick = function() {
  if ((page + 1) * PAGE_SIZE < allRuns.length) { page++; draw(); } };
function render(runs) {
  document.getElementById('rows').innerHTML = runs.map(function(s) {
    return '<tr><td><a href="/run/' + encodeURIComponent(s.run_id) +
      '"><code>' + esc(s.run_id) + '</code></a></td>' +
      '<td class="state-' + esc(s.state) + '">' + esc(s.state) + '</td>' +
      '<td>' + currentCell(s) + '</td>' +
      '<td>' + fmtAge(s.age_s, s.last_activity_at) + '</td>' +
      '<td>' + s.invocations + '</td>' +
      '<td>' + fmtNum(s.total_billed_acus, ' ACU') + '</td>' +
      '<td>' + fmtNum(s.total_estimated_usd, ' USD', 4) + '</td>' +
      '<td>' + s.unpriced_invocations + '</td></tr>';
  }).join('') || '<tr><td colspan="8" class="na">no runs</td></tr>';
}
var es = new EventSource('/api/stream');
es.onopen = function() { setConn(true); };
es.onerror = function() { setConn(false); };
es.onmessage = function(e) {
  allRuns = JSON.parse(e.data).runs; draw();
};
</script></body></html>
"""

_RUN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>run __RUN_ID__</title>
<style>__CSS__</style></head><body>
<h1>Run <code>__RUN_ID__</code> <span id="conn"><span class="dot" id="dot"></span>live</span></h1>
<p class="meta">state: <span id="rstate">—</span>
 · last activity: <span id="rage">—</span>
 · dir: <code id="rdir">—</code></p>
<table><thead><tr>
<th>Step</th><th>Attempt</th><th>Devin Session</th><th>Tokens</th><th>Time</th>
<th>ACU</th><th>Actual USD</th><th>Est. USD</th><th>Cost Status</th><th>Source</th><th>I/O</th>
</tr></thead><tbody id="rows"></tbody></table>
<h2 style="font-size:1rem;margin-top:1.5rem">Totals</h2>
<table><tbody id="totals"></tbody></table>
<script>
__JS__
function sessionCell(r) {
  if (!r.devin_session_id) {
    const why = r.session_id_reason || 'unavailable';
    return '<span class="na">—</span> <span class="na">(' + esc(why) + ')</span>';
  }
  return '<span class="sid">' + esc(r.devin_session_id) + '</span>' +
    '<button class="copy" data-sid="' + esc(r.devin_session_id) + '">copy</button>';
}
function render(p) {
  var v = p.view;
  var st = document.getElementById('rstate');
  st.textContent = p.state || v.workflow_status || '—';
  st.className = 'state-' + (p.state || '');
  document.getElementById('rage').innerHTML =
    p.last_activity_at ? fmtAge(p.age_s, p.last_activity_at) : '—';
  document.getElementById('rdir').textContent = v.run_dir;
  document.getElementById('rows').innerHTML = v.rows.map(function(r) {
    return '<tr' + (r.kind === 'review' ? ' class="review"' : '') + '>' +
      '<td>' + esc(r.label) + '</td>' +
      '<td>' + (r.attempt === null ? '—' : r.attempt) + '</td>' +
      '<td>' + sessionCell(r) + '</td>' +
      '<td>' + fmtTokens(r) + '</td>' +
      '<td>' + (r.pending
        ? '<span class="pending">reviewing…</span>'
        : fmtDur(r.latency_s)) + '</td>' +
      '<td>' + fmtNum(r.billed_acus, ' ACU') + '</td>' +
      '<td>' + fmtNum(r.actual_usd, ' USD', 4) + '</td>' +
      '<td>' + fmtNum(r.estimated_usd, ' USD', 4) + '</td>' +
      '<td>' + statusHtml(r.cost_status) + '</td>' +
      '<td>' + esc(r.cost_source || '—') + '</td>' +
      '<td>' + ioCell(r, v.run_id) + '</td></tr>';
  }).join('') || '<tr><td colspan="11" class="na">no invocation events</td></tr>';
  var t = v.totals;
  document.getElementById('totals').innerHTML =
    '<tr><th>Total actual (ACU)</th><td>' + fmtNum(t.total_billed_acus, ' ACU') + '</td></tr>' +
    '<tr><th>Total actual (USD)</th><td>' + fmtNum(t.total_actual_usd, ' USD', 4) + '</td></tr>' +
    '<tr><th>Total est. (USD)</th><td>' + fmtNum(t.total_estimated_usd, ' USD', 4) + '</td></tr>' +
    '<tr><th>Cost/workflow (ACU)</th><td>' + fmtNum(t.cost_per_workflow_acus, ' ACU') + '</td></tr>' +
    '<tr><th>Invocations</th><td>' + t.invocations + '</td></tr>' +
    '<tr><th>Unpriced</th><td>' + t.unpriced_invocations + '</td></tr>' +
    '<tr><th>Reconciliation</th><td>' + esc(
      Object.entries(t.cost_status_counts || {})
        .map(function(kv) { return kv[0] + ': ' + kv[1]; }).join(', ') || '—'
    ) + '</td></tr>';
  wireCopy(document);
}
fetch('/api/run/' + encodeURIComponent(__RUN_ID_JSON__))
  .then(function(r) { return r.json(); }).then(render);
var es = new EventSource('/api/stream/run/' + encodeURIComponent(__RUN_ID_JSON__));
es.onopen = function() { setConn(true); };
es.onerror = function() { setConn(false); };
es.onmessage = function(e) { render(JSON.parse(e.data)); };
</script></body></html>
"""


def index_page() -> str:
    return _INDEX_HTML.replace("__CSS__", _CSS).replace("__JS__", _JS_COMMON)


def run_page(run_id: str) -> str:
    return (
        _RUN_HTML.replace("__CSS__", _CSS)
        .replace("__JS__", _JS_COMMON)
        .replace("__RUN_ID_JSON__", json.dumps(run_id))
        .replace("__RUN_ID__", run_id)
    )


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> bool:
    """Write one SSE frame; returns False when the client is gone."""
    try:
        handler.wfile.write(
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode(
                "utf-8"
            )
        )
        handler.wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def _sse_open(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


def make_handler(runs_root: Path, poll_s: float = DEFAULT_POLL_S):
    runs_root = Path(runs_root)

    class Handler(BaseHTTPRequestHandler):
        server_version = "FictionForgeLive/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
            pass

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, text: str, status: int = 200) -> None:
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream_runs(self) -> None:
            _sse_open(self)
            fingerprints: dict[str, Any] = {}
            last_keepalive = time.monotonic()
            while True:
                live_ids = {
                    d.name
                    for d in runs_root.iterdir()
                    if d.is_dir() and (d / "audit.jsonl").exists()
                } if runs_root.is_dir() else set()
                current = {
                    rid: audit_fingerprint(runs_root / rid) for rid in live_ids
                }
                if current != fingerprints:
                    fingerprints = current
                    if not _sse(self, {"type": "runs", "runs": scan_runs(runs_root)}):
                        return
                    last_keepalive = time.monotonic()
                elif time.monotonic() - last_keepalive > KEEPALIVE_S:
                    if not _sse(self, {"type": "keepalive"}):
                        return
                    last_keepalive = time.monotonic()
                time.sleep(poll_s)

        def _stream_run(self, run_id: str) -> None:
            _sse_open(self)
            run_dir = runs_root / run_id
            fp: Any = object()  # always differ on first pass
            last_keepalive = time.monotonic()
            while True:
                cur = audit_fingerprint(run_dir)
                if cur != fp:
                    fp = cur
                    if not _sse(
                        self, {"type": "run", **run_live(run_dir)}
                    ):
                        return
                    last_keepalive = time.monotonic()
                elif time.monotonic() - last_keepalive > KEEPALIVE_S:
                    if not _sse(self, {"type": "keepalive"}):
                        return
                    last_keepalive = time.monotonic()
                time.sleep(poll_s)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/":
                self._html(index_page())
            elif path == "/api/runs":
                self._json({"runs": scan_runs(runs_root)})
            elif path.startswith("/api/run/"):
                run_id = path.removeprefix("/api/run/")
                if not (runs_root / run_id / "audit.jsonl").exists():
                    self._json({"error": "unknown run"}, status=404)
                    return
                self._json(run_live(runs_root / run_id))
            elif path == "/api/stream":
                self._stream_runs()
            elif path.startswith("/api/stream/run/"):
                self._stream_run(path.removeprefix("/api/stream/run/"))
            elif "/file/" in path:
                # Read-only artifact/file serve: /run/<id>/file/<relpath>
                run_id, name = path.split("/file/", 1)
                run_id = run_id.removeprefix("/run/")
                if ".." in name.split("/") or not name:
                    self._html("<h1>bad path</h1>", status=400)
                    return
                run_dir = (runs_root / run_id).resolve()
                target = (run_dir / name).resolve()
                if not str(target).startswith(str(run_dir) + "/") or not target.is_file():
                    self._html("<h1>not found</h1>", status=404)
                    return
                body = target.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/json" if name.endswith(".json") else "text/plain",
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path.startswith("/run/"):
                run_id = path.removeprefix("/run/")
                if not (runs_root / run_id / "audit.jsonl").exists():
                    self._html("<h1>unknown run</h1>", status=404)
                    return
                self._html(run_page(run_id))
            else:
                self._html("<h1>not found</h1>", status=404)

    return Handler


class _QuietHTTPServer(ThreadingHTTPServer):
    """Swallow expected client-disconnect errors (SSE reconnects)."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, OSError)):
            return
        super().handle_error(request, client_address)


def serve(
    runs_root: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
    poll_s: float = DEFAULT_POLL_S,
) -> ThreadingHTTPServer:
    """Start the live dashboard server (blocking on the calling thread)."""
    handler = make_handler(Path(runs_root), poll_s=poll_s)
    httpd = _QuietHTTPServer((host, port), handler)
    print(f"FictionForge live dashboard: http://{host}:{port}/  (runs: {runs_root})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd


def serve_in_thread(
    runs_root: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    poll_s: float = DEFAULT_POLL_S,
) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    """Start on a background thread; returns (server, thread, bound_port)."""
    handler = make_handler(Path(runs_root), poll_s=poll_s)
    httpd = _QuietHTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, httpd.server_address[1]


__all__ = [
    "audit_fingerprint",
    "build_run_view",
    "index_page",
    "make_handler",
    "run_live",
    "run_page",
    "run_state",
    "run_summary",
    "scan_runs",
    "serve",
    "serve_in_thread",
]
