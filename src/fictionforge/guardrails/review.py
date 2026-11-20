"""Adversarial review guardrail components for FictionForge.

Reviewers are *workflow-level guardrail components*, not Stage 3 judged
steps.  Each reviewer is an independent LLM call (own prompt, own
evaluation perspective, own model setting) that critiques an already
schema-valid artifact and returns a structured verdict on the shared
contract in :mod:`fictionforge.guardrails.reviewer_contract`.

Trust model
-----------
* Reviewer output is **untrusted model output**.  It is parsed strictly by
  :func:`parse_reviewer_response` (single bare JSON object, no unknown
  keys, no duplicate keys, internally consistent); anything else raises
  :class:`ReviewerContractError` and the review fails closed.
* The reviewer verdict is only *evidence*.  Every state transition (accept,
  retry, fail, punch out) is decided by :func:`decide` and the runner.
* Only the enforcement logic is deterministic; the semantic judgement of
  the reviewer LLM is not, and is measured separately (Stage 3 reviewer
  evaluations under ``evals/reviewers``).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fictionforge.guardrails import punch_out
from fictionforge.guardrails.reviewer_codes import CHARACTER_ISSUE_CODES
from fictionforge.guardrails.reviewer_contract import (
    BLOCKING_SEVERITIES,
    POLICY_CODES,
    POLICY_GUARDRAIL_BYPASS_ATTEMPT,
    WORLD_ISSUE_CODES,
    DocPath,
    ReviewerContractError,
    ReviewerIssue,
    ReviewerVerdict,
    ground_issue,
    normalize_text,
    parse_reviewer_response,
    render_review_prompt,
)
from fictionforge.guardrails.storyboard_codes import STORYBOARD_ISSUE_CODES
from fictionforge.llm.base import LLMClient

REPO_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Error codes and constants
# ---------------------------------------------------------------------------

REVIEWER_INVALID_RESPONSE = "REVIEWER_INVALID_RESPONSE"
REVIEWER_TIMEOUT = "REVIEWER_TIMEOUT"
REVIEWER_PROVIDER_ERROR = "REVIEWER_PROVIDER_ERROR"
ARTIFACT_REVIEW_INJECTION = "ARTIFACT_REVIEW_INJECTION"

REVIEW_MODES = ("shadow", "enforced")

# Stage 3-selected reviewer prompt versions (see
# evidence/stage3/reviewers/<agent>/prompt_hashes.json).
SELECTED_PROMPT_VERSIONS = {"world": "v7", "characters": "v4", "storyboard": "v10"}

ISSUE_TAXONOMY: dict[str, frozenset[str]] = {
    "world": WORLD_ISSUE_CODES,
    "characters": CHARACTER_ISSUE_CODES,
    "storyboard": STORYBOARD_ISSUE_CODES,
}

_DOC_PATH_RE = re.compile(DocPath.__metadata__[0].pattern)


def issue_to_dict(issue: ReviewerIssue) -> dict[str, Any]:
    return issue.model_dump(mode="json")


def _canonical_json(data: Any) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def artifact_sha256(artifact: dict[str, Any]) -> str:
    """sha256 of the canonical JSON of an artifact dict (same as ``Artifact.sha256``)."""
    return hashlib.sha256(_canonical_json(artifact)).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic pre-review scan of the artifact
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules?)", re.I),
    re.compile(r"disregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)", re.I),
    re.compile(r"\b(?:system|reviewer|assistant|grader)\s+(?:note|message|instruction|override)s?\b", re.I),
    re.compile(r"(?:return|respond\s+with|output|answer|set)\s+(?:the\s+)?(?:verdict|result)?\s*[:=]?\s*[\"']?PASS\b", re.I),
    re.compile(r"\byou\s+are\s+(?:now\s+)?(?:the\s+|an?\s+)?(?:reviewer|judge|grader)\b", re.I),
    re.compile(r"mark\s+(?:this|it)\s+(?:as\s+)?(?:approved|passed|pass)\b", re.I),
    re.compile(r"\b(?:write|create|touch)\s+\S*\.approved\b", re.I),
    re.compile(r"\byou\s+are\s+no\s+longer\b", re.I),
    re.compile(r"\bignore\s+the\s+(?:schema|rules?|validat\w+|guardrails?)\b", re.I),
)


def _walk_strings(node: Any, path: str = "$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")


def scan_artifact_for_review_injection(artifact: dict[str, Any]) -> list[ReviewerIssue]:
    """Deterministically flag reviewer-directed control text inside an artifact.

    Artifact text is data.  Text that addresses the reviewer or tries to
    dictate a verdict is itself a blocking defect, independent of whatever the
    reviewer LLM concludes.
    """
    issues: list[ReviewerIssue] = []
    for path, value in _walk_strings(artifact):
        for pat in _INJECTION_PATTERNS:
            m = pat.search(value)
            if not m:
                continue
            issues.append(
                ReviewerIssue(
                    code=ARTIFACT_REVIEW_INJECTION,
                    severity="critical",
                    artifact_path=path if _DOC_PATH_RE.fullmatch(path) else "$",
                    evidence=value[max(0, m.start() - 40) : m.end() + 40].strip()[:1500],
                    reference_path=None,
                    explanation="Artifact text contains instructions aimed at the reviewer or the approval process.",
                    suggested_correction="Remove the embedded instruction; artifact fields must contain only story content.",
                )
            )
            break
    return issues


# ---------------------------------------------------------------------------
# Deterministic acceptance policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewDecision:
    """Trusted decision derived from a reviewer verdict + deterministic findings."""

    decision: str  # "PASS" | "REVISE" | "PUNCH_OUT" (effective, trusted)
    reviewer_verdict: str
    blocking_issues: list[ReviewerIssue]
    punch_out_confirmed: bool
    notes: list[str] = field(default_factory=list)


def _punch_out_confirmed(
    verdict: ReviewerVerdict,
    documents: dict[str, Any],
    default_doc: str,
) -> tuple[bool, str | None]:
    """Trusted confirmation of a reviewer PUNCH_OUT.

    A PUNCH_OUT is honoured only when a critical issue carries a code in
    :data:`POLICY_CODES` whose evidence survives :func:`ground_issue` *and* that
    is deterministically corroborated: the deterministic injection scan
    flags *some* supplied document, or the quoted evidence itself contains
    punch-out language.  Reviewer text alone can never escalate a run to a
    human; without corroboration the PUNCH_OUT is downgraded to REVISE.
    """
    policy_issues = [
        i for i in verdict.issues if i.severity == "critical" and i.code in POLICY_CODES
    ]
    if not policy_issues:
        return False, "no critical issue with a POLICY_* code"
    saw_ungrounded = False
    for issue in policy_issues:
        grounding = ground_issue(issue, documents, default_doc)
        if not grounding.grounded:
            saw_ungrounded = True
            continue
        corroborated = any(
            scan_artifact_for_review_injection(doc)
            for doc in documents.values()
            if isinstance(doc, dict)
        ) or bool(punch_out.scan_output_for_punch_outs(issue.evidence))
        if not corroborated:
            saw_ungrounded = True
            continue
        return True, None
    note = (
        "policy issue evidence failed deterministic grounding/corroboration"
        if saw_ungrounded
        else "no critical issue with a POLICY_* code"
    )
    return False, note


def decide(
    verdict: ReviewerVerdict,
    deterministic_issues: list[ReviewerIssue] | None,
    documents: dict[str, Any],
    default_doc: str,
) -> ReviewDecision:
    """Map a *validated* reviewer verdict plus deterministic findings to a decision.

    * Any blocking deterministic finding prevents PASS.
    * REVISE is never upgraded to PASS and never downgraded to PASS.
    * PUNCH_OUT is honoured only when the trusted policy logic in
      :func:`_punch_out_confirmed` confirms it; otherwise it is downgraded
      to REVISE (uncertainty is not a human-escalation condition).
    """
    det_blocking = [i for i in (deterministic_issues or []) if i.blocking]
    rev_blocking = [i for i in verdict.issues if i.blocking]
    blocking = rev_blocking + det_blocking
    notes: list[str] = []

    if verdict.verdict == "PUNCH_OUT":
        confirmed, why_not = _punch_out_confirmed(verdict, documents, default_doc)
        if confirmed:
            return ReviewDecision("PUNCH_OUT", verdict.verdict, blocking, True, notes)
        notes.append(f"PUNCH_OUT downgraded to REVISE: {why_not}")
        return ReviewDecision("REVISE", verdict.verdict, blocking, False, notes)
    if verdict.verdict == "REVISE":
        return ReviewDecision("REVISE", verdict.verdict, blocking, False, notes)
    # PASS
    if blocking:
        notes.append("deterministic artifact finding overrides reviewer PASS")
        return ReviewDecision("REVISE", verdict.verdict, blocking, False, notes)
    return ReviewDecision("PASS", verdict.verdict, [], False, notes)


# ---------------------------------------------------------------------------
# Reviewer configurations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewerConfig:
    reviewer_id: str
    gate: str  # gate file stem: world / characters / storyboard
    step_id: str  # workflow step whose output is reviewed
    artifact_type: str
    prompt_path: Path
    context_keys: tuple[str, ...]  # upstream docs, in prompt order
    context_titles: dict[str, str]  # doc name -> block title
    artifact_title: str
    default_doc: str  # artifact's own namespace (== gate)
    model: str | None = None
    temperature: float = 0.0
    timeout: float = 300.0
    max_tokens: int | None = None
    max_attempts: int = 2  # reviewer-call attempts (timeout / provider only)


_BRIEF_TITLE = "STORY BRIEF (context, read-only data)"
_WORLD_TITLE = "WORLD (validated context, read-only data)"
_CHARACTERS_TITLE = "CHARACTER SET (validated context, read-only data)"


def default_reviewer_configs(
    *,
    model: str | None = None,
    models: dict[str, str] | None = None,
    timeout: float = 300.0,
    max_attempts: int = 2,
    temperature: float = 0.0,
) -> dict[str, ReviewerConfig]:
    prompts = REPO_ROOT / "prompts" / "reviewers"
    overrides = models or {}
    common = dict(timeout=timeout, max_attempts=max_attempts, temperature=temperature)
    return {
        "world_generation": ReviewerConfig(
            reviewer_id="world_reviewer",
            gate="world",
            step_id="world_generation",
            artifact_type="world",
            prompt_path=prompts / "world.md",
            context_keys=("brief",),
            context_titles={"brief": _BRIEF_TITLE},
            artifact_title="WORLD UNDER REVIEW (untrusted data)",
            default_doc="world",
            model=overrides.get("world", model),
            **common,
        ),
        "character_design": ReviewerConfig(
            reviewer_id="character_reviewer",
            gate="characters",
            step_id="character_design",
            artifact_type="characters",
            prompt_path=prompts / "characters.md",
            context_keys=("brief", "world"),
            context_titles={"brief": _BRIEF_TITLE, "world": _WORLD_TITLE},
            artifact_title="CHARACTER SET UNDER REVIEW (untrusted data)",
            default_doc="characters",
            model=overrides.get("characters", model),
            **common,
        ),
        "storyboard_building": ReviewerConfig(
            reviewer_id="storyboard_reviewer",
            gate="storyboard",
            step_id="storyboard_building",
            artifact_type="storyboard",
            prompt_path=prompts / "storyboard.md",
            context_keys=("brief", "world", "characters"),
            context_titles={
                "brief": _BRIEF_TITLE,
                "world": _WORLD_TITLE,
                "characters": _CHARACTERS_TITLE,
            },
            artifact_title="STORYBOARD UNDER REVIEW (untrusted data)",
            default_doc="storyboard",
            model=overrides.get("storyboard", model),
            **common,
        ),
    }


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------


@dataclass
class ReviewAttempt:
    attempt: int
    status: str  # "ok" or an error code
    latency_s: float
    raw_response_sha256: str | None = None
    error: str | None = None
    token_usage: dict[str, int] | None = None
    invocation_id: str | None = None
    invocations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "status": self.status,
            "latency_s": self.latency_s,
            "raw_response_sha256": self.raw_response_sha256,
            "error": self.error,
            "token_usage": self.token_usage,
            "invocation_id": self.invocation_id,
            "invocations": self.invocations,
        }


@dataclass
class ReviewResult:
    """Outcome of invoking a reviewer (never raises for reviewer failures)."""

    reviewer_id: str
    model: str | None
    prompt_sha256: str
    reviewed_artifact_sha256: str
    verdict: ReviewerVerdict | None
    error_code: str | None
    attempts: list[ReviewAttempt] = field(default_factory=list)
    raw_response: str | None = None
    duration_s: float = 0.0
    token_usage: dict[str, int] | None = None

    @property
    def ok(self) -> bool:
        return self.verdict is not None

    @property
    def invocations(self) -> list[dict[str, Any]]:
        """All CLI invocation records across reviewer attempts."""
        return [inv for a in self.attempts for inv in a.invocations]


def _classify(exc: BaseException) -> str:
    msg = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in msg or "timed out" in msg:
        return REVIEWER_TIMEOUT
    return REVIEWER_PROVIDER_ERROR


def _sum_token_usage(attempts: list[ReviewAttempt]) -> dict[str, int] | None:
    total: dict[str, int] = {}
    seen = False
    for a in attempts:
        if not a.token_usage:
            continue
        for k, v in a.token_usage.items():
            if isinstance(v, int):
                total[k] = total.get(k, 0) + v
                seen = True
    return total if seen else None


class AdversarialReviewer:
    """Independent reviewer built on the shared :class:`LLMClient` abstraction."""

    def __init__(self, client: LLMClient, config: ReviewerConfig) -> None:
        self.client = client
        self.config = config
        self._template = config.prompt_path.read_text(encoding="utf-8")
        self.template_sha256 = hashlib.sha256(self._template.encode("utf-8")).hexdigest()

    @property
    def prompt_version(self) -> str:
        return SELECTED_PROMPT_VERSIONS.get(self.config.gate, "unknown")

    def build_prompt(
        self,
        *,
        context: dict[str, Any],
        artifact: dict[str, Any],
        nonce: str | None = None,
    ) -> str:
        if nonce is None:
            nonce = secrets.token_hex(8)
        blocks = [
            (self.config.context_titles[k], context[k]) for k in self.config.context_keys
        ]
        return render_review_prompt(
            self._template,
            nonce=nonce,
            context_blocks=blocks,
            artifact_title=self.config.artifact_title,
            artifact=artifact,
        )

    def review(self, *, context: dict[str, Any], artifact: dict[str, Any]) -> ReviewResult:
        """Run the reviewer with bounded retries; fail closed on any problem.

        Retries happen after ``REVIEWER_TIMEOUT`` / ``REVIEWER_PROVIDER_ERROR``
        and after a contract-invalid or empty response: a stochastic slip gets a
        fresh-nonce re-ask; if every attempt is invalid the result still fails
        closed as ``REVIEWER_INVALID_RESPONSE``.
        A fresh prompt (fresh nonce) is built for every attempt.
        """
        cfg = self.config
        started = time.monotonic()
        result = ReviewResult(
            reviewer_id=cfg.reviewer_id,
            model=cfg.model,
            prompt_sha256=self.template_sha256,
            reviewed_artifact_sha256=artifact_sha256(artifact),
            verdict=None,
            error_code=None,
        )
        for attempt in range(1, max(1, cfg.max_attempts) + 1):
            prompt = self.build_prompt(context=context, artifact=artifact)
            invocation_id = f"inv-{secrets.token_hex(6)}"
            t0 = time.monotonic()
            try:
                response = self.client.complete(
                    prompt,
                    model=cfg.model,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens,
                    timeout=cfg.timeout,
                    retries=0,
                    invocation_id=invocation_id,
                )
            except Exception as exc:  # provider/timeout errors never pass
                code = _classify(exc)
                result.attempts.append(
                    ReviewAttempt(
                        attempt, code, round(time.monotonic() - t0, 3),
                        error=str(exc)[:500],
                        invocation_id=invocation_id,
                        invocations=list(getattr(exc, "invocations", None) or []),
                    )
                )
                result.error_code = code
                continue  # only retryable reviewer failures reach this point
            latency = round(time.monotonic() - t0, 3)
            raw = response.content if isinstance(response.content, str) else ""
            result.raw_response = raw
            if response.metadata and response.metadata.get("model"):
                result.model = response.metadata["model"]
            raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            usage = response.token_usage
            invs = list((response.metadata or {}).get("invocations") or [])
            try:
                result.verdict = parse_reviewer_response(raw)
            except ReviewerContractError as exc:
                result.attempts.append(
                    ReviewAttempt(
                        attempt, REVIEWER_INVALID_RESPONSE, latency, raw_hash,
                        str(exc)[:500], usage,
                        invocation_id=invocation_id, invocations=invs,
                    )
                )
                result.error_code = REVIEWER_INVALID_RESPONSE
                continue  # stochastic contract slips get a fresh-nonce re-ask
            if not raw.strip():
                result.attempts.append(
                    ReviewAttempt(
                        attempt, REVIEWER_INVALID_RESPONSE, latency, raw_hash,
                        "empty reviewer response", usage,
                        invocation_id=invocation_id, invocations=invs,
                    )
                )
                result.error_code = REVIEWER_INVALID_RESPONSE
                continue
            result.attempts.append(ReviewAttempt(
                attempt, "ok", latency, raw_hash, token_usage=usage,
                invocation_id=invocation_id, invocations=invs,
            ))
            result.error_code = None
            break
        result.duration_s = round(time.monotonic() - started, 3)
        result.token_usage = _sum_token_usage(result.attempts)
        return result


# ---------------------------------------------------------------------------
# Shared evaluation (workflow hook + standalone gate script)
# ---------------------------------------------------------------------------


@dataclass
class ReviewEvaluation:
    """Everything trusted code computed about one reviewed artifact."""

    result: ReviewResult
    det_issues: list[ReviewerIssue]
    decision: ReviewDecision | None  # None when the reviewer call failed
    issue_records: list[dict[str, Any]]
    unknown_codes: list[str]


def evaluate_review(
    reviewer: AdversarialReviewer,
    *,
    context: dict[str, Any],
    artifact_dict: dict[str, Any],
    documents: dict[str, Any],
) -> ReviewEvaluation:
    """Run the deterministic scan + reviewer + grounding + policy decision.

    Never raises for reviewer failures.  A ``reviewed_artifact_sha256``
    mismatch is impossible for a correct reviewer; treat it as a
    provider-level failure and fail closed.
    """
    det_issues = scan_artifact_for_review_injection(artifact_dict)
    result = reviewer.review(context=context, artifact=artifact_dict)
    if result.reviewed_artifact_sha256 != artifact_sha256(artifact_dict):
        result.verdict = None
        result.error_code = REVIEWER_PROVIDER_ERROR

    issue_records: list[dict[str, Any]] = []
    unknown: list[str] = []
    decision: ReviewDecision | None = None
    if result.ok and result.verdict is not None:
        taxonomy = ISSUE_TAXONOMY.get(reviewer.config.gate, frozenset())
        for issue in result.verdict.issues:
            grounding = ground_issue(issue, documents, reviewer.config.default_doc)
            in_tax = issue.code in taxonomy
            if not in_tax:
                unknown.append(issue.code)
            issue_records.append(
                {
                    **issue_to_dict(issue),
                    "grounded": grounding.grounded,
                    "grounding_reasons": grounding.reasons,
                    "in_taxonomy": in_tax,
                }
            )
        unknown = sorted(set(unknown))
        decision = decide(result.verdict, det_issues, documents, reviewer.config.default_doc)
    return ReviewEvaluation(result, det_issues, decision, issue_records, unknown)


# ---------------------------------------------------------------------------
# False-positive candidates and repeated-finding tracking
# ---------------------------------------------------------------------------


def false_positive_candidates(
    *,
    gate: str,
    artifact_sha256: str,
    generator_attempt: int,
    issue_records: list[dict[str, Any]],
    repeated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tag blocking findings that are *candidates* for false-positive analysis.

    Findings are never dismissed: every candidate stays blocking; the record
    only marks it for human analysis.
    """
    repeated_by_index = {r["issue_index"]: r for r in repeated}
    out: list[dict[str, Any]] = []
    for idx, rec in enumerate(issue_records):
        if rec.get("severity") not in BLOCKING_SEVERITIES:
            continue
        reasons: list[str] = []
        if not rec.get("grounded", True):
            reasons.append("ungrounded_evidence")
        if not rec.get("in_taxonomy", True):
            reasons.append("outside_taxonomy")
        rep = repeated_by_index.get(idx)
        if rep is not None:
            reasons.append(f"repeated_after_regeneration:{rep['match']}")
        if not reasons:
            continue
        out.append(
            {
                "gate": gate,
                "artifact_sha256": artifact_sha256,
                "generator_attempt": generator_attempt,
                "issue_index": idx,
                "code": rec.get("code"),
                "severity": rec.get("severity"),
                "artifact_path": rec.get("artifact_path"),
                "reasons": reasons,
                "status": "unreviewed",
                "needs_human_analysis": True,
            }
        )
    return out


class RepeatTracker:
    """Tracks blocking findings that survive regeneration, per gate.

    Fingerprints: ``exact`` = (code, artifact_path, normalize_text(evidence));
    ``location`` = (code, artifact_path).  Prior generator attempts are
    lazily loaded from ``<history_dir>/<gate>_attempt_N.json`` on first use
    so resumed runs still detect repeats.
    """

    def __init__(self, history_dir: Path | None = None) -> None:
        self._history_dir = Path(history_dir) if history_dir else None
        # gate -> fingerprint -> {"first_seen_attempt": int, "times_seen": int,
        #                         "artifact_sha256": str}
        self._exact: dict[str, dict[tuple, dict[str, Any]]] = {}
        self._loc: dict[str, dict[tuple, dict[str, Any]]] = {}
        self._loaded: set[str] = set()

    def _load_history(self, gate: str) -> None:
        if gate in self._loaded:
            return
        self._loaded.add(gate)
        if self._history_dir is None or not self._history_dir.is_dir():
            return
        for path in sorted(self._history_dir.glob(f"{gate}_attempt_*.json")):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            attempt = int(rec.get("generator_attempt") or 0)
            sha = rec.get("artifact_sha256")
            issues = (rec.get("reviewer") or {}).get("issues") or []
            blocking = [
                i for i in issues if i.get("severity") in BLOCKING_SEVERITIES
            ]
            self._record(gate, attempt, sha, blocking)

    def _record(
        self, gate: str, attempt: int, sha: str | None, issues: list[dict[str, Any]]
    ) -> None:
        exact = self._exact.setdefault(gate, {})
        loc = self._loc.setdefault(gate, {})
        for i in issues:
            e_fp = (i.get("code"), i.get("artifact_path"), normalize_text(str(i.get("evidence") or "")))
            l_fp = (i.get("code"), i.get("artifact_path"))
            for store, fp in ((exact, e_fp), (loc, l_fp)):
                entry = store.get(fp)
                if entry is None:
                    store[fp] = {
                        "first_seen_attempt": attempt,
                        "times_seen": 1,
                        "artifact_sha256": sha,
                    }
                elif entry["first_seen_attempt"] != attempt:
                    entry["times_seen"] += 1

    def observe(
        self,
        gate: str,
        attempt: int,
        artifact_sha256: str | None,
        issues: list[Any],
    ) -> list[dict[str, Any]]:
        """Return repeated-finding records, then record ``issues`` for this attempt.

        ``issues`` may be dicts (issue records) or :class:`ReviewerIssue`s.
        """
        self._load_history(gate)
        dicts = [
            i if isinstance(i, dict) else issue_to_dict(i) for i in issues
        ]
        blocking = [i for i in dicts if i.get("severity") in BLOCKING_SEVERITIES]
        out: list[dict[str, Any]] = []
        exact = self._exact.setdefault(gate, {})
        loc = self._loc.setdefault(gate, {})
        for idx, i in enumerate(dicts):
            if i.get("severity") not in BLOCKING_SEVERITIES:
                continue
            e_fp = (i.get("code"), i.get("artifact_path"), normalize_text(str(i.get("evidence") or "")))
            l_fp = (i.get("code"), i.get("artifact_path"))
            match = None
            entry = None
            if e_fp in exact and exact[e_fp]["first_seen_attempt"] != attempt:
                match, entry = "exact", exact[e_fp]
            elif l_fp in loc and loc[l_fp]["first_seen_attempt"] != attempt:
                match, entry = "same_location", loc[l_fp]
            if match is not None:
                out.append(
                    {
                        "issue_index": idx,
                        "code": i.get("code"),
                        "artifact_path": i.get("artifact_path"),
                        "match": match,
                        "first_seen_attempt": entry["first_seen_attempt"],
                        "times_seen": entry["times_seen"] + 1,
                        "artifact_sha256_changed": entry["artifact_sha256"] != artifact_sha256,
                    }
                )
        self._record(gate, attempt, artifact_sha256, blocking)
        return out


__all__ = [
    "ARTIFACT_REVIEW_INJECTION",
    "AdversarialReviewer",
    "BLOCKING_SEVERITIES",
    "ISSUE_TAXONOMY",
    "POLICY_CODES",
    "REVIEWER_INVALID_RESPONSE",
    "REVIEWER_PROVIDER_ERROR",
    "REVIEWER_TIMEOUT",
    "REVIEW_MODES",
    "RepeatTracker",
    "ReviewAttempt",
    "ReviewDecision",
    "ReviewEvaluation",
    "ReviewResult",
    "ReviewerConfig",
    "SELECTED_PROMPT_VERSIONS",
    "artifact_sha256",
    "decide",
    "default_reviewer_configs",
    "evaluate_review",
    "false_positive_candidates",
    "issue_to_dict",
    "scan_artifact_for_review_injection",
]
