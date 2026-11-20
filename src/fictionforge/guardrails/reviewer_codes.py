"""Issue-code taxonomies for the Character and Storyboard adversarial reviewers.

Kept separate from ``reviewer_contract`` so the World reviewer's frozen
evaluation (which hashes the contract module) is unaffected.  Policy codes are
shared; everything else is reviewer specific.  ``unknown_codes`` in the
contract is informational: unknown (but well-formed) codes are never policy
codes and never grant any authority.
"""

from __future__ import annotations

from fictionforge.guardrails.reviewer_contract import POLICY_CODES

CHARACTER_ISSUE_CODES: frozenset[str] = frozenset(
    {
        "WORLD_RULE_CONTRADICTION",
        "UNSUPPORTED_ABILITY",
        "BACKGROUND_HISTORY_CONTRADICTION",
        "MOTIVATION_INCONSISTENCY",
        "RELATIONSHIP_CONTRADICTION",
        "CHARACTER_WORLD_MISMATCH",
        "BRIEF_CONSTRAINT_VIOLATION",
        "OTHER_CONSISTENCY_DEFECT",
    }
    | POLICY_CODES
)

# Codes whose supporting evidence must live in the world or the brief
# (as opposed to elsewhere in the cast).
CHARACTER_WORLD_EVIDENCE_CODES: frozenset[str] = frozenset(
    {
        "WORLD_RULE_CONTRADICTION",
        "UNSUPPORTED_ABILITY",
        "BACKGROUND_HISTORY_CONTRADICTION",
        "BRIEF_CONSTRAINT_VIOLATION",
    }
)

ISSUE_CODES_BY_REVIEWER: dict[str, frozenset[str]] = {"characters": CHARACTER_ISSUE_CODES}

__all__ = ["CHARACTER_ISSUE_CODES", "CHARACTER_WORLD_EVIDENCE_CODES", "ISSUE_CODES_BY_REVIEWER"]
