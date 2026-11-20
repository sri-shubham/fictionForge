"""Deterministic scoring of one reviewer response against a labelled fixture.

Used by the Promptfoo assertions (``reviewer_assert.py``) and by the Stage 3
summariser (``scripts/reviewer_stage3.py``), so a measurement is always
re-derivable from a retained raw result file plus the frozen fixtures.

Criteria computed here (``actionable_feedback`` is rubric-graded elsewhere):
``contradiction_detection``, ``evidence_grounding``, ``false_positive_avoidance``,
``issue_classification``.  All thresholds come from ``thresholds.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from fictionforge.guardrails.reviewer_contract import (  # noqa: E402
    POLICY_CODES,
    ReviewerContractError,
    ReviewerIssue,
    ReviewerVerdict,
    ground_issue,
    normalize_text,
    parse_reviewer_response,
    paths_related,
    unknown_codes,
)

THRESHOLDS = json.loads((HERE / "thresholds.json").read_text(encoding="utf-8"))
PER_CASE = THRESHOLDS["per_case"]
DOC_KEYS = ("brief", "world", "characters", "storyboard")
DETERMINISTIC_CRITERIA = (
    "contradiction_detection",
    "evidence_grounding",
    "false_positive_avoidance",
    "issue_classification",
)


def load_fixture(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = REPO / p
    return json.loads(p.read_text(encoding="utf-8"))


def documents(fixture: dict[str, Any]) -> dict[str, Any]:
    return {k: fixture[k] for k in DOC_KEYS if k in fixture}


def _matches(issue: ReviewerIssue, item: dict[str, Any], docs: dict[str, Any], default_doc: str) -> bool:
    targets = list(item.get("artifact_paths", [])) + list(item.get("reference_paths", []))
    cited = [issue.artifact_path] + ([issue.reference_path] if issue.reference_path else [])
    if any(paths_related(c, t, docs, default_doc) for c in cited for t in targets):
        return True
    text = normalize_text(f"{issue.evidence} {issue.explanation}")
    return any(a in text for a in item.get("anchor_terms", []))


def _invalid(fixture: dict[str, Any], error: str) -> dict[str, Any]:
    reason = f"response rejected by contract (fails closed): {error}"
    crit = {c: {"applicable": True, "score": 0.0, "pass": False, "reason": reason} for c in DETERMINISTIC_CRITERIA}
    blocking = [l for l in fixture["labels"] if l["blocking"]]
    if not blocking:
        crit["contradiction_detection"]["applicable"] = False
    return {
        "contract_valid": False, "contract_error": error, "verdict": None, "verdict_correct": False,
        "unknown_codes": [], "issues": [],
        "labels": [{"label_id": l["label_id"], "severity": l["severity"], "blocking": l["blocking"],
                    "detected": False, "classification_ok": False} for l in fixture["labels"]],
        "criteria": crit, "expected_verdict": fixture["expected_verdict"],
    }


def score_case(fixture: dict[str, Any], raw_output: Any, default_doc: str | None = None) -> dict[str, Any]:
    default_doc = default_doc or fixture.get("agent", "world")
    docs = documents(fixture)
    expected = fixture["expected_verdict"]
    try:
        verdict: ReviewerVerdict = parse_reviewer_response(raw_output)
    except ReviewerContractError as exc:
        return _invalid(fixture, str(exc))

    labels = fixture["labels"]
    blocking_labels = [l for l in labels if l["blocking"]]
    nonblocking_labels = [l for l in labels if not l["blocking"]]
    traps = fixture.get("traps", [])

    issues_out: list[dict[str, Any]] = []
    for idx, issue in enumerate(verdict.issues):
        g = ground_issue(issue, docs, default_doc)
        m_block = [l["label_id"] for l in blocking_labels if _matches(issue, l, docs, default_doc)]
        m_nonblock = [l["label_id"] for l in nonblocking_labels if _matches(issue, l, docs, default_doc)]
        m_trap = [t["trap_id"] for t in traps if _matches(issue, t, docs, default_doc)]
        if not issue.blocking:
            category = "non_blocking"
        elif m_block:
            category = "supported"
        elif m_nonblock:
            category = "false_positive_style"
        elif m_trap:
            category = "false_positive_trap"
        else:
            category = "false_positive_unlabeled"
        issues_out.append({
            "index": idx, "code": issue.code, "severity": issue.severity, "blocking": issue.blocking,
            "artifact_path": issue.artifact_path, "grounded": g.grounded, "grounding_reasons": g.reasons,
            "matched_labels": m_block, "matched_nonblocking_labels": m_nonblock, "matched_traps": m_trap,
            "category": category,
        })

    label_out = []
    for l in labels:
        if not l["blocking"]:
            label_out.append({"label_id": l["label_id"], "severity": l["severity"], "blocking": False,
                              "detected": False, "classification_ok": False})
            continue
        hits = [(o, verdict.issues[o["index"]]) for o in issues_out if o["blocking"] and l["label_id"] in o["matched_labels"]]
        cls_ok = any(i.code in l["accepted_codes"] and i.severity in l["accepted_severities"] for _, i in hits)
        label_out.append({"label_id": l["label_id"], "severity": l["severity"], "blocking": True,
                          "detected": bool(hits), "classification_ok": cls_ok})

    verdict_correct = verdict.verdict == expected
    reported_blocking = [o for o in issues_out if o["blocking"]]
    fp_issues = [o for o in reported_blocking if o["category"].startswith("false_positive")]
    criteria: dict[str, dict[str, Any]] = {}

    # contradiction_detection
    weights = PER_CASE["label_weight"]
    if blocking_labels:
        tot = sum(weights[l["severity"]] for l in blocking_labels)
        got = sum(weights[lo["severity"]] for lo in label_out if lo["blocking"] and lo["detected"])
        score = got / tot
        crit_missed = [lo["label_id"] for lo in label_out if lo["blocking"] and lo["severity"] == "critical" and not lo["detected"]]
        ok = score >= PER_CASE["detection_min_weighted_recall"] and not crit_missed
        criteria["contradiction_detection"] = {
            "applicable": True, "score": round(score, 4), "pass": ok,
            "reason": f"weighted recall {score:.2f}; missed critical labels: {crit_missed or 'none'}"}
    else:
        criteria["contradiction_detection"] = {"applicable": False, "score": 1.0, "pass": True, "reason": "no blocking reference labels"}

    # evidence_grounding
    if verdict.issues or blocking_labels:
        n = len(verdict.issues)
        grounded = sum(1 for o in issues_out if o["grounded"])
        score = grounded / n if n else 0.0
        blocking_ungrounded = [o["index"] for o in reported_blocking if not o["grounded"]]
        ok = bool(n) and score >= PER_CASE["grounding_min_issue_fraction"] and not blocking_ungrounded
        bad = [f"issue {o['index']}: {'; '.join(o['grounding_reasons'])}" for o in issues_out if not o["grounded"]]
        criteria["evidence_grounding"] = {
            "applicable": True, "score": round(score, 4), "pass": ok,
            "reason": f"{grounded}/{n} issues grounded" + (f"; {bad[:3]}" if bad else "") if n else "no issues reported although defects exist"}
    else:
        criteria["evidence_grounding"] = {"applicable": False, "score": 1.0, "pass": True, "reason": "no issues to ground"}

    # false_positive_avoidance
    if expected == "PASS":
        clean = verdict.verdict == "PASS" and not reported_blocking
        criteria["false_positive_avoidance"] = {
            "applicable": True, "score": 1.0 if clean else 0.0, "pass": clean,
            "reason": "valid artifact accepted" if clean else
            f"valid artifact wrongly blocked (verdict {verdict.verdict}, {len(reported_blocking)} blocking issues)"}
    else:
        n_fp = len(fp_issues)
        score = 1.0 - (n_fp / len(reported_blocking)) if reported_blocking else 1.0
        criteria["false_positive_avoidance"] = {
            "applicable": True, "score": round(score, 4),
            "pass": n_fp <= PER_CASE["false_positive_max_unsupported_blocking_issues"],
            "reason": f"{n_fp} unsupported blocking issues of {len(reported_blocking)}: {[o['category'] for o in fp_issues] or 'none'}"}

    # issue_classification
    detected_blocking = [lo for lo in label_out if lo["blocking"] and lo["detected"]]
    cls_bad = [lo["label_id"] for lo in detected_blocking if not lo["classification_ok"]]
    if blocking_labels:
        frac = sum(1 for lo in label_out if lo["blocking"] and lo["classification_ok"]) / len(blocking_labels)
        score = 0.5 * float(verdict_correct) + 0.5 * frac
        ok = verdict_correct and not cls_bad
    else:
        score, ok = float(verdict_correct), verdict_correct
    criteria["issue_classification"] = {
        "applicable": True, "score": round(score, 4), "pass": ok,
        "reason": f"verdict {verdict.verdict} vs expected {expected}; misclassified detected labels: {cls_bad or 'none'}"}

    return {
        "contract_valid": True, "contract_error": None, "verdict": verdict.verdict,
        "verdict_correct": verdict_correct, "expected_verdict": expected,
        "unknown_codes": unknown_codes(verdict, default_doc) if default_doc in ("world",) else [],
        "policy_codes_used": sorted({i.code for i in verdict.issues if i.code in POLICY_CODES}),
        "issues": issues_out, "labels": label_out, "criteria": criteria,
    }


def expected_findings_text(fixture: dict[str, Any]) -> str:
    """Human-readable reference findings, given to the actionable-feedback grader only."""
    out = []
    for l in fixture["labels"]:
        if l["blocking"]:
            out.append(f"- [{l['severity']}] {l['rationale']} Fields: {', '.join(l['artifact_paths'] + l['reference_paths'])}. "
                       f"A good correction: {l['correction_hint']}")
    return "\n".join(out) or "(none: the artifact has no blocking defect)"
