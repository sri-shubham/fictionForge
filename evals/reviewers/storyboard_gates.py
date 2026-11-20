"""Storyboard-specific deterministic gate (see agent_gates.py for the pattern).

``blocking_citation``: every critical/major non-policy issue must (1) be located
inside the storyboard (``$.acts[i].scenes[j]...``), which identifies the scene,
and (2) cite a resolving ``reference_path``; for rule, motivation and brief codes
that reference must point into the world/brief, the cast, or the brief
respectively (the supporting evidence). Cause-and-effect, continuity, setup and
state-change findings may cite an earlier scene or any other document.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))

from agent_gates import _resolved_doc  # noqa: E402
from fictionforge.guardrails.reviewer_contract import (  # noqa: E402
    ReviewerContractError,
    parse_reviewer_response,
    resolve_path,
    split_path,
)
from fictionforge.guardrails.storyboard_codes import STORYBOARD_EVIDENCE_DOCS  # noqa: E402


def storyboard_blocking_citation(fixture: dict[str, Any], raw: Any) -> dict[str, Any]:
    try:
        verdict = parse_reviewer_response(raw)
    except ReviewerContractError as exc:
        return {"applicable": True, "pass": False, "reason": f"response rejected by contract: {exc}"}
    docs = {k: fixture[k] for k in ("brief", "world", "characters", "storyboard") if k in fixture}
    problems: list[str] = []
    checked = 0
    for idx, issue in enumerate(verdict.issues):
        if not issue.blocking or issue.is_policy:
            continue
        checked += 1
        art_doc, art_tokens = split_path(issue.artifact_path, "storyboard")
        if art_doc != "storyboard" or not art_tokens or art_tokens[0] != "acts":
            problems.append(f"issue {idx}: artifact_path {issue.artifact_path} is not inside the storyboard")
            continue
        if not resolve_path(docs, issue.artifact_path, "storyboard")[0]:
            problems.append(f"issue {idx}: artifact_path does not resolve")
            continue
        if issue.reference_path is None:
            problems.append(f"issue {idx}: blocking issue has no reference_path")
            continue
        ref_doc = _resolved_doc(docs, issue.reference_path, "storyboard")
        if ref_doc is None:
            problems.append(f"issue {idx}: reference_path {issue.reference_path} does not resolve")
            continue
        allowed = STORYBOARD_EVIDENCE_DOCS.get(issue.code)
        if allowed is not None and ref_doc not in allowed:
            problems.append(f"issue {idx}: {issue.code} must cite {sorted(allowed)} evidence, cited {ref_doc}")
    if not checked:
        return {"applicable": False, "pass": True, "reason": "no blocking non-policy issues"}
    return {"applicable": True, "pass": not problems,
            "reason": f"{checked} blocking issues checked" + (f"; {problems[:3]}" if problems else "; all cite the scene and supporting evidence")}


GATES: dict[str, dict[str, Callable[[dict[str, Any], Any], dict[str, Any]]]] = {
    "storyboard": {"blocking_citation": storyboard_blocking_citation},
}
