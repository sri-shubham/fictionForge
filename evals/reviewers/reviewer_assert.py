"""Promptfoo Python assertions for the adversarial reviewer evaluations.

Each function scores one criterion for one test case.  The reviewer's *raw*
reply is judged (``providerResponse.metadata.raw_output``), so fenced or
prose-wrapped replies fail the strict contract exactly as they would in the
workflow.  The fixture holding the reference labels is located through the
``CASE_FILE`` test variable and is never shown to the reviewer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from reviewer_scoring import DETERMINISTIC_CRITERIA, load_fixture, score_case  # noqa: E402


def _raw(output: Any, context: dict[str, Any]) -> Any:
    resp = (context or {}).get("providerResponse") or {}
    return ((resp.get("metadata") or {}).get("raw_output")) or output


def _score(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    fixture = load_fixture(context["vars"]["CASE_FILE"])
    return score_case(fixture, _raw(output, context))


def _criterion(name: str, output: Any, context: dict[str, Any]) -> dict[str, Any]:
    c = _score(output, context)["criteria"][name]
    return {"pass": bool(c["pass"]), "score": float(c["score"]), "reason": c["reason"]}


def contract_validity(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    r = _score(output, context)
    ok = r["contract_valid"]
    return {"pass": ok, "score": 1.0 if ok else 0.0,
            "reason": "response accepted by the strict reviewer contract" if ok else f"fails closed: {r['contract_error']}"}


def contradiction_detection(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    return _criterion("contradiction_detection", output, context)


def evidence_grounding(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    return _criterion("evidence_grounding", output, context)


def false_positive_avoidance(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    return _criterion("false_positive_avoidance", output, context)


def issue_classification(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    return _criterion("issue_classification", output, context)


assert set(DETERMINISTIC_CRITERIA) == {
    "contradiction_detection", "evidence_grounding", "false_positive_avoidance", "issue_classification",
}
