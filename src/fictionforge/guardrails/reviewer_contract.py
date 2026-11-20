"""Shared structured-output contract for FictionForge adversarial reviewers.

One contract serves the World, Character and Storyboard reviewers.  It is used
by the Stage 3 reviewer evaluations (``evals/reviewers``) and, later, by the
Stage 4 workflow gates, so a response is judged by the *same* code in both
places.

Trust model
-----------
* Reviewer output is untrusted model text.  :func:`parse_reviewer_response`
  accepts exactly one JSON object with the documented keys and raises
  :class:`ReviewerContractError` for anything else.  Callers must treat that
  error as a failed review (fail closed), never as a pass.
* The verdict is evidence only.  Reviewer text cannot grant approval, disable
  validation or set workflow state; text that claims such authority makes the
  response invalid.
* ``PUNCH_OUT`` is only structurally valid when it carries a critical issue
  whose code is in :data:`POLICY_CODES`.  Whether a punch-out is *honoured* is
  decided by trusted runner code, not by this module.
* Evidence grounding (:func:`ground_issue`) is deterministic: paths must
  resolve in the supplied documents and quoted evidence must appear verbatim
  in them.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    model_validator,
)

POLICY_GUARDRAIL_BYPASS_ATTEMPT = "POLICY_GUARDRAIL_BYPASS_ATTEMPT"
POLICY_UNSAFE_CONTENT = "POLICY_UNSAFE_CONTENT"
POLICY_CODES: frozenset[str] = frozenset(
    {POLICY_GUARDRAIL_BYPASS_ATTEMPT, POLICY_UNSAFE_CONTENT}
)
BLOCKING_SEVERITIES: frozenset[str] = frozenset({"critical", "major"})
MAX_ISSUES = 25
DOCUMENT_NAMESPACES: tuple[str, ...] = ("brief", "world", "characters", "storyboard")

WORLD_ISSUE_CODES: frozenset[str] = frozenset(
    {
        "RULE_HISTORY_CONTRADICTION",
        "RULE_RULE_CONTRADICTION",
        "BRIEF_CONSTRAINT_VIOLATION",
        "ENTITY_DESCRIPTION_CONFLICT",
        "UNSUPPORTED_CAPABILITY",
        "TIMELINE_CONTRADICTION",
        "OTHER_CONSISTENCY_DEFECT",
    }
    | POLICY_CODES
)

# Taxonomy per reviewer (extended as each reviewer is qualified).
REVIEWER_ISSUE_CODES: dict[str, frozenset[str]] = {"world": WORLD_ISSUE_CODES}

Severity = Literal["critical", "major", "minor"]
Verdict = Literal["PASS", "REVISE", "PUNCH_OUT"]

IssueCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
DocPath = Annotated[
    str,
    StringConstraints(
        pattern=r"^(?:(?:brief|world|characters|storyboard)::)?\$(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*$",
        max_length=200,
    ),
]
IssueText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
ReasonText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]

# Authority a reviewer must never claim.  Quoting an artifact that *contains*
# such text is fine; the reviewer asserting it is not.
_AUTHORITY_CLAIMS = (
    re.compile(r"\b(?:i|reviewer)\s+(?:hereby\s+)?(?:approve|authori[sz]e|waive|disable|skip)[sd]?\b", re.I),
    re.compile(r"\bhereby\s+(?:approved?|granted?|authori[sz]ed?|waived?)\b", re.I),
)


class ReviewerContractError(ValueError):
    """The reviewer response violates the contract; the review must fail closed."""


class ReviewerIssue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)

    code: IssueCode
    severity: Severity
    artifact_path: DocPath
    evidence: IssueText
    reference_path: DocPath | None
    explanation: IssueText
    suggested_correction: IssueText

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES

    @property
    def is_policy(self) -> bool:
        return self.code in POLICY_CODES


class ReviewerVerdict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)

    verdict: Verdict
    issues: list[ReviewerIssue]
    reason: ReasonText

    @model_validator(mode="after")
    def _consistent(self) -> "ReviewerVerdict":
        if len(self.issues) > MAX_ISSUES:
            raise ValueError(f"more than {MAX_ISSUES} issues")
        blocking = [i for i in self.issues if i.blocking]
        policy = [i for i in self.issues if i.is_policy]
        if any(i.severity != "critical" for i in policy):
            raise ValueError("policy issue codes must have severity 'critical'")
        if self.verdict == "PASS" and (blocking or policy):
            raise ValueError("PASS cannot carry critical or major issues")
        if self.verdict == "REVISE":
            if not blocking:
                raise ValueError("REVISE requires at least one critical or major issue")
            if policy:
                raise ValueError("a policy issue code requires verdict PUNCH_OUT")
        if self.verdict == "PUNCH_OUT" and not policy:
            raise ValueError("PUNCH_OUT requires a critical issue with a POLICY_* code")
        for text in [self.reason] + [t for i in self.issues for t in (i.explanation, i.suggested_correction)]:
            if any(p.search(text) for p in _AUTHORITY_CLAIMS):
                raise ValueError("reviewer text claims approval or validation authority")
        return self

    @property
    def blocking_issues(self) -> list[ReviewerIssue]:
        return [i for i in self.issues if i.blocking]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name}")


def parse_reviewer_response(raw: object) -> ReviewerVerdict:
    """Strictly parse raw reviewer text.  Raises :class:`ReviewerContractError`."""
    if not isinstance(raw, str):
        raise ReviewerContractError("reviewer response is not text")
    body = raw.strip()
    if not (body.startswith("{") and body.endswith("}")):
        raise ReviewerContractError("reviewer response is not a single bare JSON object")
    try:
        data = json.loads(body, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ReviewerContractError(f"reviewer response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReviewerContractError("reviewer response is not a JSON object")
    try:
        return ReviewerVerdict.model_validate(data)
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '$'}: {e['msg']}" for e in exc.errors()[:5]
        )
        raise ReviewerContractError(f"reviewer verdict failed validation: {detail}") from exc


def unknown_codes(verdict: ReviewerVerdict, reviewer: str) -> list[str]:
    """Issue codes outside the reviewer's taxonomy (informational; policy codes are always known)."""
    known = REVIEWER_ISSUE_CODES[reviewer]
    return sorted({i.code for i in verdict.issues if i.code not in known})


# ---------------------------------------------------------------------------
# Paths and evidence grounding
# ---------------------------------------------------------------------------

_SEGMENT = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")


def split_path(path: str, default_doc: str) -> tuple[str, tuple[str | int, ...]]:
    """``world::$.rules[0].statement`` -> ``("world", ("rules", 0, "statement"))``."""
    doc, _, rest = path.rpartition("::")
    tokens = tuple(k if k else int(i) for k, i in _SEGMENT.findall(rest[1:] if rest.startswith("$") else rest))
    return (doc or default_doc), tokens


def _walk(node: Any, tokens: tuple[str | int, ...]) -> tuple[bool, Any]:
    for t in tokens:
        if isinstance(t, int):
            if not isinstance(node, list) or t >= len(node):
                return False, None
            node = node[t]
        else:
            if not isinstance(node, dict) or t not in node:
                return False, None
            node = node[t]
    return True, node


def resolve_path(documents: dict[str, Any], path: str, default_doc: str) -> tuple[bool, Any]:
    """Resolve a contract path.  Unprefixed paths try ``default_doc`` first, then the others."""
    doc, tokens = split_path(path, default_doc)
    if "::" in path:
        return _walk(documents.get(doc), tokens) if doc in documents else (False, None)
    for name in [default_doc] + [d for d in documents if d != default_doc]:
        ok, node = _walk(documents.get(name), tokens)
        if ok:
            return True, node
    return False, None


def paths_related(a: str, b: str, documents: dict[str, Any], default_doc: str) -> bool:
    """True when one path is a prefix of the other inside the same document.

    The shorter path must be specific (depth >= 2 or a scalar leaf) so that
    citing ``$`` or a whole collection never counts as locating a defect.
    """
    da, ta = split_path(a, default_doc)
    db, tb = split_path(b, default_doc)
    if da != db:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if long_[: len(short)] != short:
        return False
    if len(short) >= 2:
        return True
    ok, node = _walk(documents.get(da), short)
    return ok and isinstance(node, str)


def collect_text(node: Any) -> str:
    """All string values in ``node`` joined by newlines (keys excluded)."""
    parts: list[str] = []

    def rec(n: Any) -> None:
        if isinstance(n, str):
            parts.append(n)
        elif isinstance(n, dict):
            for v in n.values():
                rec(v)
        elif isinstance(n, list):
            for v in n:
                rec(v)

    rec(node)
    return "\n".join(parts)


_QUOTE_TRANSLATION = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "..."}
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTE_TRANSLATION)
    return re.sub(r"\s+", " ", text).strip().casefold()


def evidence_fragments(evidence: str) -> list[str]:
    """Split ``evidence`` on ``||`` into normalized quote fragments (quotes/ellipses trimmed)."""
    out = []
    for part in evidence.split("||"):
        frag = normalize_text(part).strip(" \"'`.")
        frag = frag.removeprefix("...").removesuffix("...").strip(" \"'`.")
        if frag:
            out.append(frag)
    return out


@dataclass
class Grounding:
    grounded: bool
    reasons: list[str] = field(default_factory=list)


MIN_FRAGMENT_CHARS = 8


def ground_issue(issue: ReviewerIssue, documents: dict[str, Any], default_doc: str) -> Grounding:
    """Deterministic grounding check for one issue.

    Grounded means: ``artifact_path`` and ``reference_path`` (when given) resolve;
    every evidence fragment is at least ``MIN_FRAGMENT_CHARS`` long and appears
    verbatim (case/whitespace/quote-style normalised) in the supplied documents;
    and at least one fragment appears inside the text of the cited paths.
    """
    reasons: list[str] = []
    cited_text: list[str] = []
    for label, path in (("artifact_path", issue.artifact_path), ("reference_path", issue.reference_path)):
        if path is None:
            continue
        ok, node = resolve_path(documents, path, default_doc)
        if not ok:
            reasons.append(f"{label} {path} does not resolve")
        else:
            cited_text.append(normalize_text(collect_text(node)))
    fragments = evidence_fragments(issue.evidence)
    if not fragments:
        reasons.append("evidence is empty after trimming")
    corpus = normalize_text("\n".join(collect_text(d) for d in documents.values()))
    in_cited = False
    for frag in fragments:
        if len(frag) < MIN_FRAGMENT_CHARS:
            reasons.append(f"evidence fragment too short: {frag!r}")
        elif frag not in corpus:
            reasons.append(f"evidence fragment not found verbatim: {frag[:60]!r}")
        elif any(frag in t for t in cited_text):
            in_cited = True
    if fragments and not in_cited and not reasons:
        reasons.append("no evidence fragment appears under the cited paths")
    return Grounding(not reasons, reasons)


# ---------------------------------------------------------------------------
# Prompt rendering (shared by evaluations and workflow gates)
# ---------------------------------------------------------------------------


def render_block(title: str, data: Any, nonce: str) -> str:
    body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    return f"<<<BEGIN {title} [{nonce}]>>>\n{body}\n<<<END {title} [{nonce}]>>>"


def render_review_prompt(
    template: str,
    *,
    nonce: str,
    context_blocks: list[tuple[str, Any]],
    artifact_title: str,
    artifact: Any,
) -> str:
    """Fill ``{{NONCE}}``, ``{{CONTEXT_BLOCK}}`` and ``{{ARTIFACT_BLOCK}}``.

    The nonce is substituted before any untrusted data is inserted so data can
    never contain a usable copy of the delimiter nonce.
    """
    ctx = "\n\n".join(render_block(t, d, nonce) for t, d in context_blocks)
    art = render_block(artifact_title, artifact, nonce)
    return template.replace("{{NONCE}}", nonce).replace("{{CONTEXT_BLOCK}}", ctx).replace("{{ARTIFACT_BLOCK}}", art)


__all__ = [
    "BLOCKING_SEVERITIES",
    "DOCUMENT_NAMESPACES",
    "Grounding",
    "POLICY_CODES",
    "POLICY_GUARDRAIL_BYPASS_ATTEMPT",
    "POLICY_UNSAFE_CONTENT",
    "REVIEWER_ISSUE_CODES",
    "ReviewerContractError",
    "ReviewerIssue",
    "ReviewerVerdict",
    "WORLD_ISSUE_CODES",
    "collect_text",
    "evidence_fragments",
    "ground_issue",
    "normalize_text",
    "parse_reviewer_response",
    "paths_related",
    "render_block",
    "render_review_prompt",
    "resolve_path",
    "split_path",
    "unknown_codes",
]
