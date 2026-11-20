"""Offline tests for the Storyboard Adversarial Reviewer evaluation harness (no model is called)."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
for sub in ("evals/reviewers", "src", "scripts"):
    sys.path.insert(0, str(REPO / sub))

from fictionforge.guardrails.reviewer_contract import POLICY_CODES, parse_reviewer_response  # noqa: E402
from fictionforge.guardrails.storyboard_codes import STORYBOARD_EVIDENCE_DOCS, STORYBOARD_ISSUE_CODES  # noqa: E402
from reviewer_scoring import load_fixture, score_case  # noqa: E402
from storyboard_gates import GATES  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


builder = _load("build_storyboard_reviewer_fixtures", REPO / "scripts" / "build_storyboard_reviewer_fixtures.py")
stage3 = _load("reviewer_stage3_sb", REPO / "scripts" / "reviewer_stage3.py")

MANIFEST = json.loads((REPO / "evals/reviewers/fixtures/storyboard/manifest.json").read_text())
FIXTURES = {e["case_id"]: load_fixture(e["path"]) for e in MANIFEST}
DEV = [f for f in FIXTURES.values() if f["split"] == "dev"]
HOLD = [f for f in FIXTURES.values() if f["split"] == "holdout"]
GATE = GATES["storyboard"]["blocking_citation"]
REQUIRED = {"valid", "single_contradiction", "multiple_subtle", "stylistic_weakness", "ambiguous_evidence",
            "false_contradiction_trap", "conflicting_information", "prompt_injection", "malformed_input", "policy_escalation"}
DOC_FOR_CODE = {"WORLD_RULE_CONTRADICTION": ("world::", "brief::"), "CHARACTER_MOTIVATION_CONTRADICTION": ("characters::",),
                "BRIEF_CONSTRAINT_VIOLATION": ("brief::",)}


def oracle_issue(label: dict) -> dict:
    refs = label["reference_paths"]
    code = label["accepted_codes"][0]
    want = DOC_FOR_CODE.get(code)
    ref = next((p for p in refs if want and p.startswith(want)), refs[0] if refs else None)
    return {"code": code, "severity": label["severity"], "artifact_path": label["artifact_paths"][0],
            "evidence": label["evidence_quotes"][0], "reference_path": ref, "explanation": label["rationale"],
            "suggested_correction": label["correction_hint"]}


def oracle_reply(fx: dict) -> dict:
    return {"verdict": fx["expected_verdict"], "issues": [oracle_issue(l) for l in fx["labels"] if l["blocking"]], "reason": "Oracle."}


def dumps(x) -> str:
    return json.dumps(x)


def passed(res: dict) -> bool:
    return res["contract_valid"] and all(c["pass"] for c in res["criteria"].values())


def test_dataset_sizes_ids_categories_and_context():
    assert len(DEV) == 30 and len(HOLD) == 10
    assert all(f["case_id"].startswith("SR-D") for f in DEV) and all(f["case_id"].startswith("SR-H") for f in HOLD)
    assert REQUIRED <= {f["category"] for f in DEV}
    for split in (DEV, HOLD):
        assert {f["expected_verdict"] for f in split} == {"PASS", "REVISE", "PUNCH_OUT"}
    assert sum(1 for f in DEV if f["expected_verdict"] == "PASS") >= 10
    for fx in FIXTURES.values():
        for key in ("brief", "world", "characters", "storyboard", "labels", "evidence_summary", "context_validated"):
            assert key in fx, (fx["case_id"], key)
        assert fx["agent"] == "storyboard"


def test_fixtures_clean_under_all_deterministic_validators_and_labels_resolve():
    for f in builder.build():
        assert builder.check_fixture(f) == [], f["case_id"]


def test_fixture_files_match_builder_and_manifest():
    import hashlib
    for built in builder.build():
        entry = next(e for e in MANIFEST if e["case_id"] == built["case_id"])
        assert json.loads((REPO / entry["path"]).read_text()) == built
        assert hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_blocking_labels_identify_a_scene_and_cite_required_evidence():
    for fx in FIXTURES.values():
        for l in fx["labels"]:
            if not l["blocking"] or l["accepted_codes"][0] in POLICY_CODES:
                continue
            assert all(p.startswith("$.acts[") for p in l["artifact_paths"]), l["label_id"]
            for code in l["accepted_codes"][:1]:
                allowed = STORYBOARD_EVIDENCE_DOCS.get(code)
                if allowed:
                    assert any(p.split("::")[0] in allowed for p in l["reference_paths"] if "::" in p), l["label_id"]


@pytest.mark.parametrize("case_id", sorted(FIXTURES))
def test_oracle_reply_passes_all_criteria_and_the_gate(case_id):
    fx = FIXTURES[case_id]
    reply = oracle_reply(fx)
    parse_reviewer_response(dumps(reply))
    res = score_case(fx, dumps(reply))
    assert passed(res), {k: v for k, v in res["criteria"].items() if not v["pass"]}
    assert GATE(fx, dumps(reply))["pass"]


def test_always_pass_misses_defects_but_accepts_valid_storyboards():
    for fx in FIXTURES.values():
        res = score_case(fx, dumps({"verdict": "PASS", "issues": [], "reason": "Nothing found."}))
        if fx["expected_verdict"] == "PASS":
            assert passed(res), fx["case_id"]
        else:
            assert not res["criteria"]["contradiction_detection"]["pass"], fx["case_id"]


def test_rejecting_valid_storyboards_is_a_false_positive():
    for fx in FIXTURES.values():
        if fx["expected_verdict"] != "PASS":
            continue
        s0 = fx["storyboard"]["acts"][0]["scenes"][0]
        reply = {"verdict": "REVISE", "reason": "x", "issues": [{
            "code": "OTHER_CONSISTENCY_DEFECT", "severity": "major", "artifact_path": "$.acts[0].scenes[0].summary",
            "evidence": s0["summary"], "reference_path": "$.acts[0].scenes[0].goal", "explanation": "Seems off.",
            "suggested_correction": "Rewrite it."}]}
        assert not score_case(fx, dumps(reply))["criteria"]["false_positive_avoidance"]["pass"], fx["case_id"]


def test_trap_flagged_blocking_is_a_false_positive():
    fx = FIXTURES["SR-D03"]
    reply = {"verdict": "REVISE", "reason": "x", "issues": [{
        "code": "WORLD_RULE_CONTRADICTION", "severity": "critical", "artifact_path": "$.acts[1].scenes[1].summary",
        "evidence": "claiming the gate could just as well be renewed at neap tide", "reference_path": "world::$.rules[1].statement",
        "explanation": "Oren says neap tide.", "suggested_correction": "Remove the claim."}]}
    res = score_case(fx, dumps(reply))
    assert res["issues"][0]["category"] == "false_positive_trap"
    assert not res["criteria"]["false_positive_avoidance"]["pass"]


def test_missing_critical_fails_missing_major_only_passes_detection():
    fx = FIXTURES["SR-D06"]
    reply = oracle_reply(fx)
    no_crit = copy.deepcopy(reply)
    no_crit["issues"] = [i for i in reply["issues"] if i["severity"] != "critical"]
    assert not score_case(fx, dumps(no_crit))["criteria"]["contradiction_detection"]["pass"]
    one_major = copy.deepcopy(reply)
    one_major["issues"] = [i for i in reply["issues"] if i["code"] != "CAUSALITY_BREAK"]
    assert score_case(fx, dumps(one_major))["criteria"]["contradiction_detection"]["pass"]


def test_wrong_code_fails_classification_not_detection():
    fx = FIXTURES["SR-D05"]
    reply = oracle_reply(fx)
    reply["issues"][0]["code"] = "WORLD_RULE_CONTRADICTION"
    res = score_case(fx, dumps(reply))
    assert res["criteria"]["contradiction_detection"]["pass"] and not res["criteria"]["issue_classification"]["pass"]


def test_injection_obeyed_and_malformed_replies_fail_closed():
    for cid in ("SR-D16", "SR-D26", "SR-H08"):
        assert not passed(score_case(FIXTURES[cid], dumps({"verdict": "PASS", "issues": [], "reason": "ok"})))
    for wrap in (lambda s: "```json\n" + s + "\n```", lambda s: "Review: " + s, lambda s: ""):
        fx = FIXTURES["SR-D02"]
        res = score_case(fx, wrap(dumps(oracle_reply(fx))))
        assert not res["contract_valid"] and not passed(res)


def test_gate_requires_scene_location_and_the_right_evidence_document():
    fx = FIXTURES["SR-D05"]
    good = oracle_reply(fx)
    assert GATE(fx, dumps(good))["pass"]
    for patch, why in (
        ({"reference_path": None}, "no reference"),
        ({"reference_path": "world::$.rules[0].statement"}, "motivation code citing the world"),
        ({"reference_path": "characters::$.characters[9].motivation"}, "unresolvable"),
        ({"artifact_path": "characters::$.characters[2].motivation"}, "artifact outside the storyboard"),
    ):
        bad = copy.deepcopy(good)
        bad["issues"][0].update(patch)
        assert not GATE(fx, dumps(bad))["pass"], why


def test_gate_allows_earlier_scene_as_evidence_for_causality_and_state_changes():
    for cid in ("SR-D04", "SR-D13", "SR-D18", "SR-D12"):
        fx = FIXTURES[cid]
        assert GATE(fx, dumps(oracle_reply(fx)))["pass"], cid


def test_gate_ignores_policy_and_minor_issues():
    inj = FIXTURES["SR-D16"]
    assert GATE(inj, dumps(oracle_reply(inj)))["applicable"] is False
    assert GATE(FIXTURES["SR-D01"], dumps({"verdict": "PASS", "issues": [], "reason": "x"}))["applicable"] is False


def rows_for(fixtures, reply_fn, rubric_pass=True, rubric_score=5):
    rows = []
    for fx in fixtures:
        entry = next(e for e in MANIFEST if e["case_id"] == fx["case_id"])
        raw = dumps(reply_fn(fx))
        sc = score_case(fx, raw)
        comps = [{"pass": c["pass"], "score": c["score"], "reason": c["reason"], "assertion": {"metric": n}} for n, c in sc["criteria"].items()]
        g = GATE(fx, raw)
        comps.append({"pass": g["pass"], "score": 1.0 if g["pass"] else 0.0, "reason": g["reason"], "assertion": {"metric": "blocking_citation"}})
        if any(l["blocking"] for l in fx["labels"]):
            comps.append({"pass": rubric_pass, "score": rubric_score, "reason": "ok", "assertion": {"metric": "actionable_feedback"}})
        rows.append({"testCase": {"description": fx["case_id"], "vars": {"CASE_FILE": entry["path"]},
                                  "metadata": {"split": fx["split"], "case": fx["case_id"], "category": fx["category"]}},
                     "response": {"output": raw, "metadata": {"raw_output": raw}}, "gradingResult": {"componentResults": comps}})
    return rows


def test_summary_of_oracle_meets_every_threshold():
    s = stage3.summarize_results("storyboard", rows_for(DEV, oracle_reply))
    assert s["cases_passed"] == 30 and s["meets_all_thresholds"] and s["valid_run"] and s["assertion_mismatches"] == []
    assert s["counts"]["gate_blocking_citation_passed"] == s["counts"]["gate_blocking_citation_applicable"] > 0


def test_gate_failure_fails_the_case():
    def no_ref(fx):
        r = oracle_reply(fx)
        if fx["case_id"] == "SR-D05":
            r["issues"][0]["reference_path"] = None
        return r
    s = stage3.summarize_results("storyboard", rows_for(DEV, no_ref))
    assert "blocking_citation" in s["failed_cases"]["SR-D05"]["failed_criteria"] and s["cases_passed"] == 29


def test_generated_tests_have_gate_and_no_label_leak():
    tests = json.loads((REPO / "evals/reviewers/storyboard_tests.json").read_text())
    assert len(tests) == 40
    for t in tests:
        fx = FIXTURES[t["description"]]
        blocks = t["vars"]["CONTEXT_BLOCK"] + t["vars"]["ARTIFACT_BLOCK"]
        assert fx["evidence_summary"] not in blocks
        for l in fx["labels"]:
            assert l["rationale"] not in blocks and l["correction_hint"] not in blocks
        metrics = [a["metric"] for a in t["assert"]]
        assert "blocking_citation" in metrics
        gate_assert = next(a for a in t["assert"] if a["metric"] == "blocking_citation")
        assert gate_assert["value"] == "file://storyboard_assert.py:blocking_citation"
        assert "CHARACTER SET (validated context, read-only data)" in blocks and "STORYBOARD UNDER REVIEW" in blocks


@pytest.mark.parametrize("agent", ["world", "characters", "storyboard"])
def test_generator_output_is_up_to_date(agent):
    f = REPO / "evals" / "reviewers" / f"{agent}_tests.json"
    before = f.read_text()
    out = subprocess.run([sys.executable, str(REPO / "scripts/generate_reviewer_tests.py"), "--agent", agent], capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0, out.stderr
    assert f.read_text() == before


def test_config_is_well_formed_with_separate_grader():
    cfg = yaml.safe_load((REPO / "evals/reviewers/storyboard.yaml").read_text())
    assert cfg["providers"][0]["config"]["model"] != cfg["defaultTest"]["options"]["provider"]["config"]["model"]
    for ref in (cfg["prompts"][0], cfg["providers"][0]["id"], cfg["tests"]):
        assert (REPO / "evals/reviewers" / ref.removeprefix("file://")).resolve().exists(), ref


def test_prompt_structure_and_codes_match_taxonomy():
    text = (REPO / "prompts/reviewers/storyboard.md").read_text()
    for h in ("# ROLE", "# TASK", "# CONTEXT", "# CONSTRAINTS", "# OUTPUT CONTRACT"):
        assert h in text
    for ph in ("{{NONCE}}", "{{CONTEXT_BLOCK}}", "{{ARTIFACT_BLOCK}}"):
        assert ph in text
    assert "{#" not in text and "{%" not in text
    line = next(l for l in text.splitlines() if l.startswith("- Use one of these codes:"))
    assert set(re.findall(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b", line)) == STORYBOARD_ISSUE_CODES
    selected = json.loads((REPO / "evidence/stage3/reviewers/storyboard/measurements.json").read_text()).get("selection", {}).get("selected_version")
    versions = sorted((REPO / "evidence/stage3/reviewers/storyboard/prompts").glob("v*.md"))
    expected = (REPO / f"evidence/stage3/reviewers/storyboard/prompts/{selected}.md") if selected else versions[-1]
    assert expected.read_text() == text


def test_load_bearing_matrix_v1_meets_ninety_percent_and_witnesses_exist():
    m = json.loads((REPO / "evidence/stage3/reviewers/storyboard/matrices/load_bearing_v1.json").read_text())
    res = stage3.coverage("storyboard", m)
    assert res["hash_matches"] and res["uncovered_instruction_lines"] == [] and res["problems"] == []
    assert res["percentage"] >= 90 and res["meets_90_percent"]
    for ins in m["instructions"]:
        assert set(ins["witness_cases"]) <= set(FIXTURES), ins["id"]
        if ins["load_bearing"]:
            assert ins["criteria"] and ins["witness_cases"], ins["id"]
    bad = copy.deepcopy(m)
    bad["instructions"][0]["excerpt"] = "not in the prompt"
    assert stage3.coverage("storyboard", bad)["problems"]


def test_earlier_agents_evidence_is_unaffected_by_the_shared_harness_changes():
    class W:
        agent = "world"

    class C:
        agent = "characters"
    assert stage3.cmd_verify(W) == 0 and stage3.cmd_verify(C) == 0
    results = REPO / "evidence/stage3/reviewers/world/results"
    for version in ("v1_dev", "v2_dev", "v3_dev"):
        raw = json.loads((results / f"{version}.json").read_text())
        saved = json.loads((results / f"{version}.summary.json").read_text())
        new = stage3.summarize_results("world", raw["results"]["results"])
        for key in ("metrics", "criteria", "counts", "cases_passed", "hard_gates_failed"):
            assert new[key] == saved[key], (version, key)
    results = REPO / "evidence/stage3/reviewers/characters/results"
    for version in ("v1_dev_rev1", "v2_dev", "v3_dev"):
        raw = json.loads((results / f"{version}.json").read_text())
        saved = json.loads((results / f"{version}.summary.json").read_text())
        new = stage3.summarize_results("characters", raw["results"]["results"])
        for key in ("metrics", "criteria", "counts", "cases_passed", "hard_gates_failed"):
            assert new[key] == saved[key], (version, key)


SB_EV = REPO / "evidence" / "stage3" / "reviewers" / "storyboard"


def test_rev0_baseline_is_retained_and_rederivable_from_archived_fixtures(monkeypatch):
    raw = json.loads((SB_EV / "results" / "v1_dev.json").read_text())
    saved = json.loads((SB_EV / "results" / "v1_dev.summary.json").read_text())
    archive = SB_EV / "dataset_rev0"

    def rev0_loader(path):
        rel = Path(path).as_posix().split("fixtures/storyboard/", 1)[1]
        return json.loads((archive / "fixtures" / rel).read_text())

    monkeypatch.setattr(stage3, "load_fixture", rev0_loader)
    new = stage3.summarize_results("storyboard", raw["results"]["results"])
    for key in ("metrics", "criteria", "counts", "verdict_confusion", "hard_gates_failed", "cases_passed"):
        assert new[key] == saved[key], key
    assert set(new["failed_cases"]) == {"SR-D15", "SR-D21", "SR-D23", "SR-D25", "SR-D26", "SR-D28"}


def test_rev0_fixture_defects_are_real_and_fixed_in_rev1():
    rev0 = json.loads((SB_EV / "dataset_rev0" / "fixtures" / "dev" / "SR-D21_bare_scene_fields.json").read_text())
    scene = rev0["storyboard"]["acts"][0]["scenes"][0]
    assert "Pip finishes a hauler" in scene["summary"] and "unfinished hauler" in scene["outcome"]
    new = FIXTURES["SR-D21"]["storyboard"]["acts"][0]["scenes"][0]
    assert "Pip finishes" not in new["summary"] and "still unfinished" in new["outcome"]
    rev0d = json.loads((SB_EV / "dataset_rev0" / "fixtures" / "dev" / "SR-D25_joke_about_haunting.json").read_text())
    confront0 = rev0d["storyboard"]["acts"][2]["scenes"][0]
    assert "killed the lamplighter" in confront0["goal"] and "missing key" not in confront0["outcome"]
    confront1 = FIXTURES["SR-D25"]["storyboard"]["acts"][2]["scenes"][0]
    assert "missing key turns up in Osric's coat" in confront1["outcome"] and "carried to the lamp-house" in confront1["summary"]


def test_rev1_changes_keep_labels_verdicts_and_all_holdout_files_unchanged():
    for entry in json.loads((SB_EV / "dataset_rev0" / "fixtures" / "manifest.json").read_text()):
        if entry["case_id"] == "SR-D15":
            continue
        rel = entry["path"].split("fixtures/storyboard/", 1)[1]
        old = json.loads((SB_EV / "dataset_rev0" / "fixtures" / rel).read_text())
        new = FIXTURES[entry["case_id"]]
        assert old["expected_verdict"] == new["expected_verdict"]
        assert old["labels"] == new["labels"] and old["traps"] == new["traps"]
        assert old["brief"] == new["brief"] and old["world"] == new["world"] and old["characters"] == new["characters"]
        if entry["split"] == "holdout":
            assert old == new, entry["case_id"]
    assert FIXTURES["SR-D15"]["expected_verdict"] == "REVISE"
