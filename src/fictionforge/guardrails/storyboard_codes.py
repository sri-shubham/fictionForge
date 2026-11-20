"""Issue-code taxonomy for the Storyboard adversarial reviewer.

Separate from ``reviewer_contract`` and ``reviewer_codes`` so the frozen
evaluations of the World and Character reviewers (which hash those modules)
are unaffected.
"""

from __future__ import annotations

from fictionforge.guardrails.reviewer_contract import POLICY_CODES

STORYBOARD_ISSUE_CODES: frozenset[str] = frozenset(
    {
        "WORLD_RULE_CONTRADICTION",
        "CHARACTER_MOTIVATION_CONTRADICTION",
        "CAUSALITY_BREAK",
        "CONTINUITY_ERROR",
        "UNSUPPORTED_PLOT_DEVELOPMENT",
        "UNEXPLAINED_STATE_CHANGE",
        "MISSING_SETUP",
        "BRIEF_CONSTRAINT_VIOLATION",
        "OTHER_CONSISTENCY_DEFECT",
    }
    | POLICY_CODES
)

# code -> documents the reference_path must resolve in (codes not listed: any document, including the storyboard itself)
STORYBOARD_EVIDENCE_DOCS: dict[str, frozenset[str]] = {
    "WORLD_RULE_CONTRADICTION": frozenset({"world", "brief"}),
    "CHARACTER_MOTIVATION_CONTRADICTION": frozenset({"characters"}),
    "BRIEF_CONSTRAINT_VIOLATION": frozenset({"brief"}),
}

__all__ = ["STORYBOARD_EVIDENCE_DOCS", "STORYBOARD_ISSUE_CODES"]
