"""Offline dashboard builder for FictionForge workflow runs.

Reads only files on disk (``audit.jsonl`` per run) and renders a static,
self-contained HTML dashboard — no model calls, no server, no external
assets::

    .venv/bin/python scripts/build_dashboard.py runs --out dashboard/
    .venv/bin/python scripts/build_dashboard.py runs/<run_id> --out run.html

With a runs root, writes ``index.html`` plus one detail page per run.
With a single run directory (or ``--single``), writes one detail page.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fictionforge.observability.dashboard import (  # noqa: E402
    build_dashboard,
    build_run_view,
    render_run_html,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "path",
        type=Path,
        help="Runs root (dir of run dirs) or a single run directory.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory (runs root) or .html file (single run).",
    )
    ap.add_argument(
        "--single",
        action="store_true",
        help="Treat PATH as one run directory even if it lacks audit.jsonl "
        "siblings.",
    )
    args = ap.parse_args()

    if args.single or (args.path / "audit.jsonl").exists():
        view = build_run_view(args.path)
        out = args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_run_html(view), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    written = build_dashboard(args.path, args.out)
    for p in written:
        print(f"wrote {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
