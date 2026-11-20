"""Promptfoo assertions for the Storyboard reviewer's agent-specific gate."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from reviewer_scoring import load_fixture  # noqa: E402
from storyboard_gates import GATES  # noqa: E402


def _raw(output: Any, context: dict[str, Any]) -> Any:
    resp = (context or {}).get("providerResponse") or {}
    return ((resp.get("metadata") or {}).get("raw_output")) or output


def blocking_citation(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    r = GATES["storyboard"]["blocking_citation"](load_fixture(context["vars"]["CASE_FILE"]), _raw(output, context))
    return {"pass": bool(r["pass"]), "score": 1.0 if r["pass"] else 0.0, "reason": r["reason"]}
