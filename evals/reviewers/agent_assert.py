"""Promptfoo assertions for agent-specific gates (see agent_gates.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent_gates import GATES  # noqa: E402
from reviewer_scoring import load_fixture  # noqa: E402


def _raw(output: Any, context: dict[str, Any]) -> Any:
    resp = (context or {}).get("providerResponse") or {}
    return ((resp.get("metadata") or {}).get("raw_output")) or output


def _gate(agent: str, name: str, output: Any, context: dict[str, Any]) -> dict[str, Any]:
    r = GATES[agent][name](load_fixture(context["vars"]["CASE_FILE"]), _raw(output, context))
    return {"pass": bool(r["pass"]), "score": 1.0 if r["pass"] else 0.0, "reason": r["reason"]}


def blocking_citation(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    return _gate("characters", "blocking_citation", output, context)
