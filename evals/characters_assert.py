"""Promptfoo structural assertion for Character Design output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fictionforge.guardrails.validators import validate_characters
from fictionforge.models import StoryBrief, World


def get_assert(output: str, context: dict[str, Any]) -> dict[str, Any]:
    """Return pass/fail for the generated character set against the World."""
    expected = context["vars"].get("EXPECTED", "valid")

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        if expected == "rejection":
            return {
                "pass": True,
                "score": 1.0,
                "reason": "Non-JSON output for an adversarial or contradictory case",
            }
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Output is not valid JSON: {exc}",
        }

    brief_json = context["vars"].get("STORY_BRIEF_JSON", "{}")
    world_json = context["vars"].get("WORLD_JSON", "{}")
    try:
        brief = StoryBrief.model_validate(json.loads(brief_json))
        world = World.model_validate(json.loads(world_json))
    except Exception as exc:
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Could not parse the StoryBrief or World: {exc}",
        }

    issues = validate_characters(data, world, brief)
    if issues:
        if expected == "rejection":
            return {
                "pass": True,
                "score": 1.0,
                "reason": f"Adversarial case correctly rejected ({len(issues)} issue(s))",
            }
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"Character set validation failed with {len(issues)} issue(s): {issues[0].message}",
        }

    if expected == "rejection":
        return {
            "pass": False,
            "score": 0.0,
            "reason": "An adversarial or contradictory case unexpectedly produced a valid character set",
        }

    return {
        "pass": True,
        "score": 1.0,
        "reason": "Character set is structurally and referentially valid",
    }
