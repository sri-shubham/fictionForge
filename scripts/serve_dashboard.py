"""Live FictionForge dashboard server.

Watches a runs directory and serves a dynamic HTML dashboard — run list and
per-run detail pages update in the browser as ``audit.jsonl`` is appended to
(no manual rebuild).  Stdlib only, no model calls::

    .venv/bin/python scripts/serve_dashboard.py runs --port 8787
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fictionforge.observability.live import serve  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs_root", type=Path, help="Directory of run dirs.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--poll", type=float, default=1.0,
                    help="Audit-file poll interval (seconds).")
    args = ap.parse_args()
    serve(args.runs_root, host=args.host, port=args.port, poll_s=args.poll)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
