"""Promptfoo structural assertion for World Generation output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fictionforge.guardrails.validators import validate_world
from fictionforge.models import StoryBrief


def get_assert(output: str, context: dict[str, Any]) -> dict[str, Any]:
    """Return pass/fail for the generated world against the StoryBrief."""
    expected = context["vars"].get("EXPECTED", "valid")

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        if expected == "rejection":
            return {
                "pass": True,
                "score": 1.0,
                "reason": "Non-JSON output for a contradictory brief",
            }
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Output is not valid JSON: {exc}",
        }

    brief_json = context["vars"].get("STORY_BRIEF_JSON", "{}")
    try:
        brief_data = json.loads(brief_json)
        brief = StoryBrief.model_validate(brief_data)
    except Exception as exc:
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Could not parse the StoryBrief: {exc}",
        }

    issues = validate_world(data, brief)
    if issues:
        if expected == "rejection":
            return {
                "pass": True,
                "score": 1.0,
                "reason": f"Contradictory brief correctly rejected ({len(issues)} issue(s))",
            }
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"World validation failed with {len(issues)} issue(s): {issues[0].message}",
        }

    if expected == "rejection":
        return {
            "pass": False,
            "score": 0.0,
            "reason": "A contradictory brief unexpectedly produced a valid world",
        }

    return {"pass": True, "score": 1.0, "reason": "World is structurally valid"}
