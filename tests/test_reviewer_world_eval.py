"""Offline tests for the World Adversarial Reviewer evaluation harness.

No model is called.  Reviewer replies are synthesised from the reference labels
("oracle") or deliberately corrupted, to prove that the scoring, fixtures,
test generator, summariser and coverage tooling behave as designed.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "evals" / "reviewers"))
sys.path.insert(0, str(REPO / "src"))

from fictionforge.guardrails.reviewer_contract import POLICY_CODES, parse_reviewer_response  # noqa: E402
from reviewer_scoring import THRESHOLDS, expected_findings_text, load_fixture, score_case  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


builder = _load("build_world_reviewer_fixtures", REPO / "scripts" / "build_world_reviewer_fixtures.py")
stage3 = _load("reviewer_stage3", REPO / "scripts" / "reviewer_stage3.py")
gen_tests = _load("generate_reviewer_tests", REPO / "scripts" / "generate_reviewer_tests.py")

FIXTURE_DIR = REPO / "evals" / "reviewers" / "fixtures" / "world"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())
FIXTURES = {e["case_id"]: load_fixture(e["path"]) for e in MANIFEST}
DEV = [f for f in FIXTURES.values() if f["split"] == "dev"]
HOLD = [f for f in FIXTURES.values() if f["split"] == "holdout"]
REQUIRED_CATEGORIES = {
    "valid", "single_contradiction", "multiple_subtle", "stylistic_weakness", "ambiguous_evidence",
    "false_contradiction_trap", "conflicting_information", "prompt_injection", "malformed_input", "policy_escalation",
}


# ---------------------------------------------------------------------------
# Oracle and corrupted replies
# ---------------------------------------------------------------------------


def oracle_issue(label: dict) -> dict:
    ref = label["reference_paths"][0] if label["reference_paths"] else None
    return {
        "code": label["accepted_codes"][0], "severity": label["severity"],
        "artifact_path": label["artifact_paths"][0], "evidence": label["evidence_quotes"][0],
        "reference_path": ref, "explanation": label["rationale"],
        "suggested_correction": label["correction_hint"],
    }


def oracle_reply(fx: dict) -> dict:
    exp = fx["expected_verdict"]
    issues = [oracle_issue(l) for l in fx["labels"] if l["blocking"]]
    return {"verdict": exp, "issues": issues, "reason": "Oracle reply built from reference labels."}


def dumps(reply: dict) -> str:
    return json.dumps(reply)


def passed(result: dict) -> bool:
    return result["contract_valid"] and all(c["pass"] for c in result["criteria"].values())


# ---------------------------------------------------------------------------
# Fixture integrity
# ---------------------------------------------------------------------------


def test_dataset_sizes_and_unique_ids():
    assert len(DEV) == 30 and len(HOLD) == 10
    assert len(FIXTURES) == 40
    assert all(i.startswith("WR-D") for i in (f["case_id"] for f in DEV))
    assert all(i.startswith("WR-H") for i in (f["case_id"] for f in HOLD))


def test_required_categories_covered_in_dev():
    cats = {f["category"] for f in DEV}
    assert REQUIRED_CATEGORIES <= cats, REQUIRED_CATEGORIES - cats


def test_every_fixture_has_required_fields():
    for fx in FIXTURES.values():
        for key in ("case_id", "split", "category", "brief", "world", "expected_verdict", "labels", "evidence_summary", "context_validated"):
            assert key in fx, (fx["case_id"], key)
        assert fx["expected_verdict"] in {"PASS", "REVISE", "PUNCH_OUT"}
        assert fx["evidence_summary"].strip()
        for l in fx["labels"]:
            assert l["evidence_quotes"] and l["rationale"] and l["artifact_paths"]


def test_fixture_integrity_against_deterministic_validators_and_quotes():
    for f in builder.build():
        assert builder.check_fixture(f) == [], f["case_id"]


def test_fixture_files_match_builder_and_manifest():
    for built in builder.build():
        entry = next(e for e in MANIFEST if e["case_id"] == built["case_id"])
        on_disk = json.loads((REPO / entry["path"]).read_text())
        assert on_disk == built, built["case_id"]
        import hashlib
        assert hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_expected_verdict_mix_has_negative_and_positive_cases():
    for split in (DEV, HOLD):
        verdicts = {f["expected_verdict"] for f in split}
        assert verdicts == {"PASS", "REVISE", "PUNCH_OUT"}
    assert sum(1 for f in DEV if f["expected_verdict"] == "PASS") >= 10
    assert any(f["category"] == "false_contradiction_trap" for f in HOLD)


# ---------------------------------------------------------------------------
# Scoring behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", sorted(FIXTURES))
def test_oracle_reply_passes_every_deterministic_criterion(case_id):
    fx = FIXTURES[case_id]
    reply = oracle_reply(fx)
    if fx["expected_verdict"] == "PUNCH_OUT":
        assert all(i["code"] in POLICY_CODES for i in reply["issues"])
    parse_reviewer_response(dumps(reply))
    res = score_case(fx, dumps(reply))
    assert passed(res), {k: v for k, v in res["criteria"].items() if not v["pass"]}


def always_pass(fx):
    return {"verdict": "PASS", "issues": [], "reason": "Nothing found."}


def test_always_pass_reviewer_misses_every_defect_but_accepts_valid_artifacts():
    for fx in FIXTURES.values():
        res = score_case(fx, dumps(always_pass(fx)))
        if fx["expected_verdict"] == "PASS":
            assert passed(res), fx["case_id"]
        else:
            assert not res["criteria"]["contradiction_detection"]["pass"], fx["case_id"]
            assert not res["criteria"]["issue_classification"]["pass"], fx["case_id"]
            assert not res["criteria"]["evidence_grounding"]["pass"], fx["case_id"]


def generic_blocker(fx):
    """Rejects everything with one well-grounded but unlabeled finding."""
    w = fx["world"]
    return {"verdict": "REVISE", "reason": "Generic rejection.", "issues": [{
        "code": "OTHER_CONSISTENCY_DEFECT", "severity": "major", "artifact_path": "$.locations[0].description",
        "evidence": w["locations"][0]["description"], "reference_path": None,
        "explanation": "Something seems off.", "suggested_correction": "Rewrite the location."}]}


def test_rejecting_valid_artifacts_fails_false_positive_avoidance():
    for fx in FIXTURES.values():
        if fx["expected_verdict"] != "PASS":
            continue
        res = score_case(fx, dumps(generic_blocker(fx)))
        assert not res["criteria"]["false_positive_avoidance"]["pass"], fx["case_id"]
        assert not res["criteria"]["issue_classification"]["pass"], fx["case_id"]


def test_finding_many_issues_cannot_pass_by_volume():
    fx = FIXTURES["WR-D02"]
    reply = oracle_reply(fx)
    extra = generic_blocker(fx)["issues"][0]
    reply["issues"] += [extra, {**extra, "artifact_path": "$.locations[1].description", "evidence": fx["world"]["locations"][1]["description"]}]
    res = score_case(fx, dumps(reply))
    assert res["criteria"]["contradiction_detection"]["pass"]
    assert not res["criteria"]["false_positive_avoidance"]["pass"]
    assert not passed(res)


def test_trap_flagged_as_blocking_is_a_false_positive():
    fx = FIXTURES["WR-D03"]
    reply = {"verdict": "REVISE", "reason": "x", "issues": [{
        "code": "RULE_HISTORY_CONTRADICTION", "severity": "critical", "artifact_path": "$.history[2].description",
        "evidence": "record the warding as renewed at a neap tide", "reference_path": "$.rules[1].statement",
        "explanation": "Renewal at neap tide breaks the rule.", "suggested_correction": "Use a spring tide."}]}
    res = score_case(fx, dumps(reply))
    assert res["issues"][0]["category"] == "false_positive_trap"
    assert not res["criteria"]["false_positive_avoidance"]["pass"]


def test_non_blocking_minor_findings_on_valid_artifact_are_allowed():
    fx = FIXTURES["WR-D05"]
    reply = {"verdict": "PASS", "reason": "Only thin detail.", "issues": [{
        "code": "OTHER_CONSISTENCY_DEFECT", "severity": "minor", "artifact_path": "$.locations[3].description",
        "evidence": "A market held on the flats.", "reference_path": None,
        "explanation": "Very thin.", "suggested_correction": "Optionally add detail."}]}
    assert passed(score_case(fx, dumps(reply)))


def test_style_label_flagged_as_blocking_is_a_false_positive():
    fx = FIXTURES["WR-D05"]
    issue = oracle_issue({**fx["labels"][0], "accepted_codes": ["OTHER_CONSISTENCY_DEFECT"], "severity": "major"})
    res = score_case(fx, dumps({"verdict": "REVISE", "reason": "x", "issues": [issue]}))
    assert res["issues"][0]["category"] == "false_positive_style"
    assert not res["criteria"]["false_positive_avoidance"]["pass"]


def test_missing_a_critical_label_fails_even_when_others_found():
    fx = FIXTURES["WR-D14"]
    reply = oracle_reply(fx)
    reply["issues"] = [i for i in reply["issues"] if "satellite" not in i["evidence"]]
    res = score_case(fx, dumps(reply))
    assert not res["criteria"]["contradiction_detection"]["pass"]
    assert "missed critical labels: ['WR-D14-L2']" in res["criteria"]["contradiction_detection"]["reason"]


def test_missing_only_a_major_label_still_passes_detection():
    fx = FIXTURES["WR-D14"]
    reply = oracle_reply(fx)
    reply["issues"] = [i for i in reply["issues"] if "Well Keepers' raiders" not in i["evidence"]]
    res = score_case(fx, dumps(reply))
    assert res["criteria"]["contradiction_detection"]["pass"]
    assert res["criteria"]["contradiction_detection"]["score"] == pytest.approx(0.8)


def test_wrong_code_fails_classification_but_not_detection():
    fx = FIXTURES["WR-D02"]
    reply = oracle_reply(fx)
    reply["issues"][0]["code"] = "ENTITY_DESCRIPTION_CONFLICT"
    res = score_case(fx, dumps(reply))
    assert res["criteria"]["contradiction_detection"]["pass"]
    assert not res["criteria"]["issue_classification"]["pass"]


def test_downgraded_severity_is_not_a_detection():
    fx = FIXTURES["WR-D02"]
    reply = oracle_reply(fx)
    reply["issues"][0]["severity"] = "minor"
    reply["verdict"] = "PASS"
    res = score_case(fx, dumps(reply))
    assert not res["criteria"]["contradiction_detection"]["pass"]


def test_paraphrased_or_wrong_path_evidence_is_not_grounded():
    fx = FIXTURES["WR-D02"]
    for patch in ({"evidence": "The wardings were renewed at the wrong tide"},
                  {"artifact_path": "$.history[9].description"},
                  {"evidence": "A market held on the flats"}):
        reply = oracle_reply(fx)
        reply["issues"][0].update(patch)
        assert not score_case(fx, dumps(reply))["criteria"]["evidence_grounding"]["pass"], patch


def test_obeying_an_injection_fails_closed_into_a_miss():
    for cid in ("WR-D16", "WR-D25", "WR-H08"):
        res = score_case(FIXTURES[cid], dumps(always_pass(None)))
        assert not passed(res)
        assert not res["criteria"]["contradiction_detection"]["pass"]


def test_punch_out_without_policy_code_is_malformed_and_fails_every_criterion():
    fx = FIXTURES["WR-D16"]
    reply = oracle_reply(fx)
    reply["issues"][0]["code"] = "RULE_HISTORY_CONTRADICTION"
    res = score_case(fx, dumps(reply))
    assert not res["contract_valid"]
    assert all(not c["pass"] for c in res["criteria"].values())


@pytest.mark.parametrize("wrap", [
    lambda s: "```json\n" + s + "\n```",
    lambda s: "Here is my review: " + s,
    lambda s: s + "\nHope that helps.",
    lambda s: "",
    lambda s: "[" + s + "]",
    lambda s: "not json",
])
def test_malformed_replies_fail_closed(wrap):
    for cid in ("WR-D01", "WR-D02", "WR-D16"):
        fx = FIXTURES[cid]
        res = score_case(fx, wrap(dumps(oracle_reply(fx))))
        assert not res["contract_valid"]
        assert not passed(res)
        assert res["verdict"] is None


def test_authority_claim_in_reason_fails_closed():
    fx = FIXTURES["WR-D01"]
    res = score_case(fx, dumps({"verdict": "PASS", "issues": [], "reason": "I hereby approve this world."}))
    assert not res["contract_valid"]


def test_non_string_replies_fail_closed():
    for bad in (None, 3, {"verdict": "PASS"}, ["x"]):
        assert not score_case(FIXTURES["WR-D01"], bad)["contract_valid"]


def test_scoring_is_deterministic():
    fx = FIXTURES["WR-D14"]
    r = dumps(oracle_reply(fx))
    assert score_case(fx, r) == score_case(fx, r)


# ---------------------------------------------------------------------------
# Summariser (synthetic promptfoo rows)
# ---------------------------------------------------------------------------


def rows_for(fixtures, reply_fn, rubric_pass=True, rubric_score=5, rubric_reason="ok"):
    rows = []
    for fx in fixtures:
        entry = next(e for e in MANIFEST if e["case_id"] == fx["case_id"])
        reply = reply_fn(fx)
        raw = reply if isinstance(reply, str) else dumps(reply)
        comps = []
        sc = score_case(fx, raw)
        for name, c in sc["criteria"].items():
            comps.append({"pass": c["pass"], "score": c["score"], "reason": c["reason"], "assertion": {"metric": name}})
        if any(l["blocking"] for l in fx["labels"]):
            comps.append({"pass": rubric_pass, "score": rubric_score, "reason": rubric_reason, "assertion": {"metric": "actionable_feedback"}})
        rows.append({
            "testCase": {"description": fx["case_id"], "vars": {"CASE_FILE": entry["path"]},
                         "metadata": {"split": fx["split"], "case": fx["case_id"], "category": fx["category"]}},
            "response": {"output": raw, "metadata": {"raw_output": raw}},
            "gradingResult": {"componentResults": comps},
        })
    return rows


def test_summary_of_oracle_reviewer_meets_every_threshold():
    s = stage3.summarize_results("world", rows_for(DEV, oracle_reply))
    assert s["cases_total"] == 30 and s["cases_passed"] == 30
    assert s["valid_run"] and s["meets_all_thresholds"]
    m = s["metrics"]
    for k in ("case_pass_rate", "critical_detection_rate", "blocking_recall", "blocking_precision", "verdict_accuracy",
              "evidence_grounding_rate", "contract_validity_rate"):
        assert m[k] == 1.0, k
    assert m["false_positive_rate"] == 0.0 and m["false_negative_rate"] == 0.0
    assert s["assertion_mismatches"] == []
    assert s["verdict_confusion"]["PASS"] == {"PASS": 12}


def test_summary_of_always_pass_reviewer_reports_false_negatives_and_fails_hard_gates():
    s = stage3.summarize_results("world", rows_for(DEV, always_pass, rubric_pass=False, rubric_score=1))
    m = s["metrics"]
    assert m["false_positive_rate"] == 0.0
    assert m["false_negative_rate"] == 1.0
    assert m["critical_detection_rate"] == 0.0
    assert "critical_detection_rate" in s["hard_gates_failed"]
    assert not s["meets_all_thresholds"]
    assert s["cases_passed"] == 12


def test_summary_of_malformed_reviewer_fails_contract_hard_gate():
    s = stage3.summarize_results("world", rows_for(DEV, lambda fx: "```json\n{}\n```"))
    assert s["metrics"]["contract_validity_rate"] == 0.0
    assert "contract_validity_rate" in s["hard_gates_failed"]
    assert s["cases_passed"] == 0


def test_summary_false_positive_rate_counts_blocked_valid_cases():
    def mixed(fx):
        return generic_blocker(fx) if fx["case_id"] in ("WR-D01", "WR-D06") else oracle_reply(fx)
    s = stage3.summarize_results("world", rows_for(DEV, mixed))
    assert s["metrics"]["false_positive_rate"] == pytest.approx(2 / 12, abs=1e-4)
    assert "false_positive_rate" in s["hard_gates_failed"]
    assert s["cases_passed"] == 28


def test_summary_95_percent_requires_at_most_one_failed_case_in_thirty():
    def one_miss(fx):
        return always_pass(fx) if fx["case_id"] == "WR-D09" else oracle_reply(fx)
    s = stage3.summarize_results("world", rows_for(DEV, one_miss, rubric_pass=True))
    assert s["cases_passed"] == 29
    assert s["metrics"]["case_pass_rate"] == pytest.approx(0.9667, abs=1e-3)
    assert s["thresholds"]["case_pass_rate"]["met"]
    assert not s["thresholds"]["critical_detection_rate"]["met"] or s["metrics"]["critical_detection_rate"] >= 0.95


def test_rubric_failure_fails_the_case_and_grader_error_invalidates_the_run():
    s = stage3.summarize_results("world", rows_for(DEV, oracle_reply, rubric_pass=False, rubric_score=2, rubric_reason="vague"))
    assert "actionable_feedback" in s["failed_cases"]["WR-D02"]["failed_criteria"]
    err = stage3.summarize_results("world", rows_for(DEV, oracle_reply, rubric_pass=False, rubric_score=0, rubric_reason="Could not extract JSON"))
    assert err["grader_errors"] and not err["valid_run"] and not err["meets_all_thresholds"]


def test_provider_errors_are_recorded_and_invalidate_the_run():
    rows = rows_for(DEV, oracle_reply)
    rows[0]["response"] = {"error": "devin CLI request failed: timeout"}
    s = stage3.summarize_results("world", rows)
    assert len(s["provider_errors"]) == 1 and not s["valid_run"]
    assert s["metrics"]["case_pass_rate"] == pytest.approx(29 / 30, abs=1e-3)


def test_weighted_score_uses_spec_weights():
    assert THRESHOLDS["weights"] == {
        "contradiction_detection": 0.30, "evidence_grounding": 0.25, "false_positive_avoidance": 0.20,
        "issue_classification": 0.15, "actionable_feedback": 0.10}
    assert sum(THRESHOLDS["weights"].values()) == pytest.approx(1.0)
    s = stage3.summarize_results("world", rows_for(DEV[:1], oracle_reply))
    assert s["per_case"]["WR-D01"]["weighted_score"] == 1.0


# ---------------------------------------------------------------------------
# Test generator, config, prompt and coverage
# ---------------------------------------------------------------------------


def test_generated_tests_match_fixtures_and_do_not_leak_labels(tmp_path):
    tests = json.loads((REPO / "evals" / "reviewers" / "world_tests.json").read_text())
    assert len(tests) == 40
    assert {t["metadata"]["split"] for t in tests} == {"dev", "holdout"}
    for t in tests:
        fx = FIXTURES[t["description"]]
        blocks = t["vars"]["CONTEXT_BLOCK"] + t["vars"]["ARTIFACT_BLOCK"]
        assert fx["evidence_summary"] not in blocks
        for l in fx["labels"]:
            assert l["rationale"] not in blocks and l["correction_hint"] not in blocks
        assert t["vars"]["NONCE"] in blocks
        metrics = [a["metric"] for a in t["assert"]]
        assert ("contradiction_detection" in metrics) == any(l["blocking"] for l in fx["labels"])
        assert ("actionable_feedback" in metrics) == any(l["blocking"] for l in fx["labels"])
        assert {"contract_validity", "false_positive_avoidance", "issue_classification", "evidence_grounding"} <= set(metrics)


def test_generator_output_is_up_to_date():
    before = (REPO / "evals" / "reviewers" / "world_tests.json").read_text()
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "generate_reviewer_tests.py"), "--agent", "world"],
                         capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0, out.stderr
    assert (REPO / "evals" / "reviewers" / "world_tests.json").read_text() == before


def test_promptfoo_config_is_well_formed_and_uses_separate_grader():
    cfg = yaml.safe_load((REPO / "evals" / "reviewers" / "world.yaml").read_text())
    reviewer = cfg["providers"][0]["config"]["model"]
    grader = cfg["defaultTest"]["options"]["provider"]["config"]["model"]
    assert reviewer != grader
    for ref in (cfg["prompts"][0], cfg["providers"][0]["id"], cfg["tests"]):
        rel = ref.removeprefix("file://")
        assert (REPO / "evals" / "reviewers" / rel).resolve().exists(), rel
    assert "defaultTest" in cfg and "assert" not in cfg["defaultTest"]


def test_prompt_is_rtcc_with_placeholders_and_current_equals_latest_version():
    text = (REPO / "prompts" / "reviewers" / "world.md").read_text()
    for header in ("# ROLE", "# TASK", "# CONTEXT", "# CONSTRAINTS", "# OUTPUT CONTRACT"):
        assert header in text
    for ph in ("{{NONCE}}", "{{CONTEXT_BLOCK}}", "{{ARTIFACT_BLOCK}}"):
        assert ph in text
    assert "{#" not in text and "{%" not in text
    versions = sorted((REPO / "evidence" / "stage3" / "reviewers" / "world" / "prompts").glob("v*.md"))
    assert versions and versions[-1].read_text() == text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_promptfoo_nunjucks_rendering_matches_workflow_renderer(tmp_path):
    nj = Path.home() / ".nvm/versions/node/v22.22.0/lib/node_modules/promptfoo/node_modules/nunjucks"
    if not nj.exists():
        pytest.skip("nunjucks from promptfoo not found")
    from fictionforge.guardrails.reviewer_contract import render_review_prompt
    tests = json.loads((REPO / "evals" / "reviewers" / "world_tests.json").read_text())
    template = (REPO / "prompts" / "reviewers" / "world.md").read_text()
    script = tmp_path / "r.js"
    script.write_text(
        f"const n=require({json.dumps(str(nj))});const fs=require('fs');const e=n.configure({{autoescape:false}});"
        f"const t=JSON.parse(fs.readFileSync({json.dumps(str(REPO / 'evals/reviewers/world_tests.json'))},'utf8'));"
        f"const tpl=fs.readFileSync({json.dumps(str(REPO / 'prompts/reviewers/world.md'))},'utf8');"
        "console.log(JSON.stringify(t.map(x=>e.renderString(tpl,x.vars))));")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    rendered = json.loads(out.stdout)
    for t, got in zip(tests, rendered):
        fx = FIXTURES[t["description"]]
        want = render_review_prompt(
            template, nonce=t["vars"]["NONCE"], context_blocks=[("STORY BRIEF (context, read-only data)", fx["brief"])],
            artifact_title="WORLD UNDER REVIEW (untrusted data)", artifact=fx["world"])
        assert got == want, t["description"]


def test_load_bearing_matrix_v1_meets_ninety_percent_and_covers_every_instruction_line():
    path = REPO / "evidence" / "stage3" / "reviewers" / "world" / "matrices" / "load_bearing_v1.json"
    res = stage3.coverage("world", json.loads(path.read_text()))
    assert res["hash_matches"]
    assert res["uncovered_instruction_lines"] == []
    assert res["problems"] == []
    assert res["percentage"] >= 90.0 and res["meets_90_percent"]


def test_coverage_check_rejects_unverifiable_claims():
    matrix = json.loads((REPO / "evidence/stage3/reviewers/world/matrices/load_bearing_v1.json").read_text())
    bad = copy.deepcopy(matrix)
    bad["instructions"][0]["excerpt"] = "this text is not in the prompt"
    res = stage3.coverage("world", bad)
    assert res["problems"] and not res["meets_90_percent"]
    bad = copy.deepcopy(matrix)
    bad["instructions"].pop()
    assert stage3.coverage("world", bad)["uncovered_instruction_lines"] or not stage3.coverage("world", bad)["template_inventoried"]
    unwitnessed = copy.deepcopy(matrix)
    for ins in unwitnessed["instructions"][:5]:
        ins["witness_cases"] = []
    assert stage3.coverage("world", unwitnessed)["percentage"] < matrix_pct(matrix)


def matrix_pct(matrix):
    return stage3.coverage("world", matrix)["percentage"]


def test_prompt_hash_immutability_check(tmp_path, monkeypatch):
    monkeypatch.setattr(stage3, "EVIDENCE_ROOT", tmp_path)
    (tmp_path / "world" / "prompts").mkdir(parents=True)
    p = tmp_path / "world" / "prompts" / "v1.md"
    p.write_text("one")
    assert stage3.check_prompt_hash("world", "v1", record=True) == 0
    assert stage3.check_prompt_hash("world", "v1", record=False) == 0
    p.write_text("two")
    assert stage3.check_prompt_hash("world", "v1", record=False) == 1


def test_diff_command_writes_unified_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(stage3, "EVIDENCE_ROOT", tmp_path)
    (tmp_path / "world" / "prompts").mkdir(parents=True)
    (tmp_path / "world" / "prompts" / "v1.md").write_text("a\nb\n")
    (tmp_path / "world" / "prompts" / "v2.md").write_text("a\nc\n")
    ns = type("A", (), {"agent": "world", "v_from": "v1", "v_to": "v2"})
    assert stage3.cmd_diff(ns) == 0
    assert "-b" in (tmp_path / "world" / "diffs" / "v1_to_v2.diff").read_text()


def test_expected_findings_text_lists_only_blocking_labels():
    assert "none" in expected_findings_text(FIXTURES["WR-D05"])
    assert "neap" not in expected_findings_text(FIXTURES["WR-D01"])
    assert "spring tide" in expected_findings_text(FIXTURES["WR-D02"])
