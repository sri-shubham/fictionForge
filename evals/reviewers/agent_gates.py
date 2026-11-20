"""Agent-specific deterministic gates (added on top of the shared criteria).

A gate is a pass/fail check derived from the strictly parsed verdict.  It is
re-derivable offline from a retained raw reply, like the shared criteria, and
is an *additional* pass condition for the case; it carries no weight.

``characters``: ``blocking_citation`` - every critical/major non-policy issue
must (1) be located inside the character set (``$.characters[i]...`` or
``$.relationships[j]...``), which identifies the relevant character, and
(2) cite a resolving ``reference_path``; for codes in
``CHARACTER_WORLD_EVIDENCE_CODES`` that reference must point into the world or
the brief (the supporting world evidence).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from fictionforge.guardrails.reviewer_codes import CHARACTER_WORLD_EVIDENCE_CODES  # noqa: E402
from fictionforge.guardrails.reviewer_contract import (  # noqa: E402
    ReviewerContractError,
    parse_reviewer_response,
    resolve_path,
    split_path,
)


def _resolved_doc(documents: dict[str, Any], path: str, default_doc: str) -> str | None:
    """Name of the document a path resolves in (prefixed paths: the prefix; unprefixed: default first)."""
    doc, tokens = split_path(path, default_doc)
    if "::" in path:
        return doc if resolve_path(documents, path, default_doc)[0] else None
    for name in [default_doc] + [d for d in documents if d != default_doc]:
        probe = f"{name}::" + path
        if resolve_path(documents, probe, default_doc)[0]:
            return name
    return None


def characters_blocking_citation(fixture: dict[str, Any], raw: Any) -> dict[str, Any]:
    try:
        verdict = parse_reviewer_response(raw)
    except ReviewerContractError as exc:
        return {"applicable": True, "pass": False, "reason": f"response rejected by contract: {exc}"}
    docs = {k: fixture[k] for k in ("brief", "world", "characters") if k in fixture}
    problems: list[str] = []
    checked = 0
    for idx, issue in enumerate(verdict.issues):
        if not issue.blocking or issue.is_policy:
            continue
        checked += 1
        art_doc, art_tokens = split_path(issue.artifact_path, "characters")
        if art_doc != "characters" or not art_tokens or art_tokens[0] not in ("characters", "relationships"):
            problems.append(f"issue {idx}: artifact_path {issue.artifact_path} is not inside the character set")
            continue
        if not resolve_path(docs, issue.artifact_path, "characters")[0]:
            problems.append(f"issue {idx}: artifact_path does not resolve")
            continue
        if issue.reference_path is None:
            problems.append(f"issue {idx}: blocking issue has no reference_path")
            continue
        ref_doc = _resolved_doc(docs, issue.reference_path, "characters")
        if ref_doc is None:
            problems.append(f"issue {idx}: reference_path {issue.reference_path} does not resolve")
        elif issue.code in CHARACTER_WORLD_EVIDENCE_CODES and ref_doc not in ("world", "brief"):
            problems.append(f"issue {idx}: {issue.code} must cite world or brief evidence, cited {ref_doc}")
    if not checked:
        return {"applicable": False, "pass": True, "reason": "no blocking non-policy issues"}
    return {"applicable": True, "pass": not problems,
            "reason": f"{checked} blocking issues checked" + (f"; {problems[:3]}" if problems else "; all cite the character and supporting evidence")}


GATES: dict[str, dict[str, Callable[[dict[str, Any], Any], dict[str, Any]]]] = {
    "characters": {"blocking_citation": characters_blocking_citation},
}
