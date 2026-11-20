"""Stage 3 deterministic assertions for Storyboard Building (additive to storyboard_assert.py).

Each function reports one facet of the existing deterministic validator so the evidence can state
JSON/schema validity, referential integrity, scene-dependency validity and narrative-phase
correctness separately. No rule here differs from ``fictionforge.guardrails.validators``.

When the output is not parseable or violates the schema, the validator stops before its semantic
checks. The three semantic facets then cannot be evaluated; they fail with a reason that starts
with ``NOT_EVALUABLE`` so the summariser can report them separately from genuine violations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fictionforge.guardrails.validators import ErrorCode, validate_storyboard
from fictionforge.models import CharacterSet, World

SCHEMA_CODES = {
    ErrorCode.SCHEMA_VIOLATION,
    ErrorCode.MISSING_REQUIRED_FIELD,
    ErrorCode.COUNT_BELOW_MIN,
    ErrorCode.COUNT_ABOVE_MAX,
}
REFERENTIAL_CODES = {
    ErrorCode.WORLD_ID_MISMATCH,
    ErrorCode.UNKNOWN_LOCATION_REF,
    ErrorCode.UNKNOWN_CHARACTER_REF,
    ErrorCode.DUPLICATE_ID,
}
DEPENDENCY_CODES = {
    ErrorCode.UNKNOWN_SCENE_REF,
    ErrorCode.SELF_DEPENDENCY,
    ErrorCode.FORWARD_DEPENDENCY,
    ErrorCode.CYCLIC_DEPENDENCY,
}
PHASE_CODES = {ErrorCode.MISSING_NARRATIVE_PHASE, ErrorCode.NARRATIVE_PHASE_ORDER}


def _result(ok: bool, reason: str) -> dict[str, Any]:
    return {"pass": ok, "score": 1.0 if ok else 0.0, "reason": reason}


def _validate(output: str, context: dict[str, Any]):
    """Return (issues, error). ``issues`` is None when validation could not run."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        return None, f"Output is not valid JSON: {exc}"
    v = context["vars"]
    try:
        world = World.model_validate(json.loads(v["WORLD_JSON"]))
        characters = CharacterSet.model_validate(json.loads(v["CHARACTER_SET_JSON"]))
    except Exception as exc:
        return None, f"Could not parse World/CharacterSet fixtures: {exc}"
    return validate_storyboard(data, world, characters), None


def _facet(output: str, context: dict[str, Any], codes: set, label: str) -> dict[str, Any]:
    issues, err = _validate(output, context)
    if issues is None:
        return _result(False, f"NOT_EVALUABLE: {err}")
    if any(i.code in SCHEMA_CODES for i in issues):
        return _result(False, "NOT_EVALUABLE: schema violations stopped semantic validation")
    hits = [i for i in issues if i.code in codes]
    if hits:
        return _result(False, f"{len(hits)} {label} issue(s): {hits[0].message}")
    return _result(True, f"No {label} issues")


def schema_validity(output: str, context: dict[str, Any]) -> dict[str, Any]:
    issues, err = _validate(output, context)
    if issues is None:
        return _result(False, err)
    hits = [i for i in issues if i.code in SCHEMA_CODES]
    if hits:
        return _result(False, f"{len(hits)} schema issue(s): {hits[0].message} at {hits[0].path}")
    return _result(True, "Output parses and satisfies the Storyboard schema")


def referential_integrity(output: str, context: dict[str, Any]) -> dict[str, Any]:
    return _facet(output, context, REFERENTIAL_CODES, "referential-integrity")


def dependency_validity(output: str, context: dict[str, Any]) -> dict[str, Any]:
    return _facet(output, context, DEPENDENCY_CODES, "scene-dependency")


def narrative_phase_correctness(output: str, context: dict[str, Any]) -> dict[str, Any]:
    return _facet(output, context, PHASE_CODES, "narrative-phase")


def format_discipline(output: str, context: dict[str, Any]) -> dict[str, Any]:
    """Pass iff the model's raw reply is exactly one JSON object (no fences, no prose)."""
    resp = (context or {}).get("providerResponse") or {}
    raw = ((resp.get("metadata") or {}).get("raw_output")) or output
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _result(False, "Raw reply is not a single bare JSON object (fence, prose or malformed JSON)")
    if not isinstance(parsed, dict):
        return _result(False, "Raw reply is JSON but not an object")
    return _result(True, "Reply is a single bare JSON object")
