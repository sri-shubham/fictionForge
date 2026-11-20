#!/usr/bin/env python3
"""Generate evals/reviewers/<agent>_tests.json from the labelled fixtures.

    .venv/bin/python scripts/generate_reviewer_tests.py --agent world

The reviewer prompt template (``{{NONCE}}``, ``{{CONTEXT_BLOCK}}``, ``{{ARTIFACT_BLOCK}}``)
is filled by Promptfoo from these variables; the blocks are built with the same
``render_block`` the workflow gates use.  The reviewer receives only the
brief/upstream context and the artifact.
Reference labels stay in the fixture file (``CASE_FILE``) and reach only the
deterministic assertions and the actionable-feedback grader.  The delimiter
nonce is derived from the case id so prompts are reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "evals" / "reviewers"))

from fictionforge.guardrails.reviewer_contract import render_block  # noqa: E402
from reviewer_scoring import expected_findings_text, load_fixture  # noqa: E402

# Block titles and context documents per reviewer (shared by evaluations and, later, workflow gates).
AGENTS = {
    "world": {
        "context": [("brief", "STORY BRIEF (context, read-only data)")],
        "artifact": ("world", "WORLD UNDER REVIEW (untrusted data)"),
        "gates": [],
        "gate_module": None,
    },
    "characters": {
        "context": [("brief", "STORY BRIEF (context, read-only data)"),
                    ("world", "WORLD (validated context, read-only data)")],
        "artifact": ("characters", "CHARACTER SET UNDER REVIEW (untrusted data)"),
        "gates": ["blocking_citation"],
        "gate_module": "agent_assert",
    },
    "storyboard": {
        "context": [("brief", "STORY BRIEF (context, read-only data)"),
                    ("world", "WORLD (validated context, read-only data)"),
                    ("characters", "CHARACTER SET (validated context, read-only data)")],
        "artifact": ("storyboard", "STORYBOARD UNDER REVIEW (untrusted data)"),
        "gates": ["blocking_citation"],
        "gate_module": "storyboard_assert",
    },
}

ACTIONABLE_RUBRIC = """You are grading the ACTIONABILITY of an adversarial reviewer's feedback on a generated artifact. The text you are given is the reviewer's JSON reply. Judge only the critical and major issues in its "issues" list.

Known defects in this artifact (reference, written by the dataset author):
{{EXPECTED_FINDINGS}}

Artifact context (for checking that a correction really resolves the problem):
{{CONTEXT_JSON}}

Check each critical/major issue:
(a) "suggested_correction" names the specific field, entity or passage to change.
(b) It is one concrete change, not a vague instruction such as "improve consistency".
(c) Applying it would resolve the stated problem without breaking the brief or the rules.
(d) It does not rewrite the whole artifact and does not claim any approval authority.
(e) "explanation" states why the passage is a defect.

Scoring (integer 1-5):
5 = (a)-(e) hold for every critical/major issue.
4 = (a)-(c) hold for every critical/major issue; (d) or (e) is weak for at most one.
3 = at least one critical/major issue has a vague or only partly effective correction.
2 = most corrections are vague or do not resolve the problem.
1 = no critical/major issue is reported, or the corrections are missing, wrong or harmful.
The score MUST be an integer 1-5 (never a fraction or 0-1 value); "pass" MUST be true exactly when score >= 4.
Return JSON only: {"reason": "one short clause per check a-e", "score": 4, "pass": true}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(AGENTS))
    args = ap.parse_args()
    spec = AGENTS[args.agent]
    manifest = json.loads((REPO / "evals" / "reviewers" / "fixtures" / args.agent / "manifest.json").read_text())
    tests = []
    for entry in manifest:
        fx = load_fixture(entry["path"])
        nonce = hashlib.sha256(fx["case_id"].encode()).hexdigest()[:16]
        art_key, art_title = spec["artifact"]
        context_block = "\n\n".join(render_block(title, fx[key], nonce) for key, title in spec["context"])
        artifact_block = render_block(art_title, fx[art_key], nonce)
        has_blocking = any(l["blocking"] for l in fx["labels"])
        asserts = [{"type": "python", "value": f"file://reviewer_assert.py:{n}", "metric": n}
                   for n in ("contract_validity", "false_positive_avoidance", "issue_classification", "evidence_grounding")]
        if has_blocking:
            asserts.insert(1, {"type": "python", "value": "file://reviewer_assert.py:contradiction_detection",
                               "metric": "contradiction_detection"})
            asserts.append({"type": "llm-rubric", "threshold": 4, "metric": "actionable_feedback", "value": ACTIONABLE_RUBRIC})
        for gate in spec["gates"]:
            asserts.append({"type": "python", "value": f"file://{spec['gate_module']}.py:{gate}", "metric": gate})
        context_json = json.dumps({k: fx[k] for k in ("brief", "world", "characters", "storyboard") if k in fx},
                                  ensure_ascii=False, sort_keys=True)
        tests.append({
            "description": fx["case_id"],
            "vars": {
                "CASE_FILE": entry["path"],
                "NONCE": nonce,
                "CONTEXT_BLOCK": context_block,
                "ARTIFACT_BLOCK": artifact_block,
                "EXPECTED_FINDINGS": expected_findings_text(fx),
                "CONTEXT_JSON": context_json,
            },
            "metadata": {"split": fx["split"], "case": fx["case_id"], "expected": fx["expected_verdict"],
                         "category": fx["category"]},
            "assert": asserts,
        })
    out = REPO / "evals" / "reviewers" / f"{args.agent}_tests.json"
    out.write_text(json.dumps(tests, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(tests)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
