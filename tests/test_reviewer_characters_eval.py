"""Offline tests for the Character Adversarial Reviewer evaluation harness.

No model is called; replies are synthesised from the labels or corrupted.
Also guards the World reviewer's retained evidence against harness changes
made for the Character reviewer.
"""

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
sys.path.insert(0, str(REPO / "evals" / "reviewers"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from agent_gates import GATES  # noqa: E402
from fictionforge.guardrails.reviewer_codes import CHARACTER_ISSUE_CODES, CHARACTER_WORLD_EVIDENCE_CODES  # noqa: E402
from fictionforge.guardrails.reviewer_contract import POLICY_CODES, parse_reviewer_response  # noqa: E402
from reviewer_scoring import load_fixture, score_case  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


builder = _load("build_characters_reviewer_fixtures", REPO / "scripts" / "build_characters_reviewer_fixtures.py")
stage3 = _load("reviewer_stage3_chars", REPO / "scripts" / "reviewer_stage3.py")

FIXTURE_DIR = REPO / "evals" / "reviewers" / "fixtures" / "characters"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text())
FIXTURES = {e["case_id"]: load_fixture(e["path"]) for e in MANIFEST}
DEV = [f for f in FIXTURES.values() if f["split"] == "dev"]
HOLD = [f for f in FIXTURES.values() if f["split"] == "holdout"]
GATE = GATES["characters"]["blocking_citation"]
REQUIRED_CATEGORIES = {
    "valid", "single_contradiction", "multiple_subtle", "stylistic_weakness", "ambiguous_evidence",
    "false_contradiction_trap", "conflicting_information", "prompt_injection", "malformed_input", "policy_escalation",
}


def oracle_issue(label: dict) -> dict:
    refs = label["reference_paths"]
    ref = next((p for p in refs if p.startswith(("world::", "brief::"))), refs[0] if refs else None)
    return {"code": label["accepted_codes"][0], "severity": label["severity"], "artifact_path": label["artifact_paths"][0],
            "evidence": label["evidence_quotes"][0], "reference_path": ref, "explanation": label["rationale"],
            "suggested_correction": label["correction_hint"]}


def oracle_reply(fx: dict) -> dict:
    return {"verdict": fx["expected_verdict"], "issues": [oracle_issue(l) for l in fx["labels"] if l["blocking"]],
            "reason": "Oracle reply built from reference labels."}


def dumps(x) -> str:
    return json.dumps(x)


def passed(res: dict) -> bool:
    return res["contract_valid"] and all(c["pass"] for c in res["criteria"].values())


# --- fixtures ---------------------------------------------------------------


def test_dataset_sizes_ids_and_categories():
    assert len(DEV) == 30 and len(HOLD) == 10
    assert all(f["case_id"].startswith("CR-D") for f in DEV) and all(f["case_id"].startswith("CR-H") for f in HOLD)
    assert REQUIRED_CATEGORIES <= {f["category"] for f in DEV}
    for split in (DEV, HOLD):
        assert {f["expected_verdict"] for f in split} == {"PASS", "REVISE", "PUNCH_OUT"}
    assert sum(1 for f in DEV if f["expected_verdict"] == "PASS") >= 10


def test_every_fixture_has_required_fields_and_validated_context():
    for fx in FIXTURES.values():
        for key in ("case_id", "split", "category", "brief", "world", "characters", "expected_verdict", "labels",
                    "evidence_summary", "context_validated"):
            assert key in fx, (fx["case_id"], key)
        assert fx["agent"] == "characters" and fx["evidence_summary"].strip()
        for l in fx["labels"]:
            assert l["evidence_quotes"] and l["rationale"] and l["artifact_paths"]


def test_fixtures_are_clean_under_deterministic_validators_and_labels_resolve():
    for f in builder.build():
        assert builder.check_fixture(f) == [], f["case_id"]


def test_fixture_files_match_builder_and_manifest():
    import hashlib
    for built in builder.build():
        entry = next(e for e in MANIFEST if e["case_id"] == built["case_id"])
        assert json.loads((REPO / entry["path"]).read_text()) == built
        assert hashlib.sha256((REPO / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_blocking_labels_identify_a_character_and_cite_world_evidence():
    for fx in FIXTURES.values():
        for l in fx["labels"]:
            if not l["blocking"] or l["accepted_codes"][0] in POLICY_CODES:
                continue
            assert all(p.startswith(("$.characters[", "$.relationships[")) for p in l["artifact_paths"]), l["label_id"]
            if set(l["accepted_codes"]) & CHARACTER_WORLD_EVIDENCE_CODES:
                assert any(p.startswith(("world::", "brief::")) for p in l["reference_paths"]), l["label_id"]


# --- scoring and gate behaviour --------------------------------------------


@pytest.mark.parametrize("case_id", sorted(FIXTURES))
def test_oracle_reply_passes_all_criteria_and_the_gate(case_id):
    fx = FIXTURES[case_id]
    reply = oracle_reply(fx)
    parse_reviewer_response(dumps(reply))
    res = score_case(fx, dumps(reply))
    assert passed(res), {k: v for k, v in res["criteria"].items() if not v["pass"]}
    assert GATE(fx, dumps(reply))["pass"]


def test_always_pass_misses_every_defect_but_accepts_valid_casts():
    for fx in FIXTURES.values():
        res = score_case(fx, dumps({"verdict": "PASS", "issues": [], "reason": "Nothing found."}))
        if fx["expected_verdict"] == "PASS":
            assert passed(res), fx["case_id"]
        else:
            assert not res["criteria"]["contradiction_detection"]["pass"], fx["case_id"]


def generic_blocker(fx):
    c0 = fx["characters"]["characters"][0]
    return {"verdict": "REVISE", "reason": "x", "issues": [{
        "code": "OTHER_CONSISTENCY_DEFECT", "severity": "major", "artifact_path": "$.characters[0].description",
        "evidence": c0["description"], "reference_path": "$.characters[0].arc", "explanation": "Seems off.",
        "suggested_correction": "Rewrite it."}]}


def test_rejecting_valid_casts_is_a_false_positive():
    for fx in FIXTURES.values():
        if fx["expected_verdict"] == "PASS":
            assert not score_case(fx, dumps(generic_blocker(fx)))["criteria"]["false_positive_avoidance"]["pass"]


def test_trap_flagged_blocking_is_a_false_positive():
    fx = FIXTURES["CR-D03"]
    reply = {"verdict": "REVISE", "reason": "x", "issues": [{
        "code": "WORLD_RULE_CONTRADICTION", "severity": "critical", "artifact_path": "$.characters[0].abilities[0]",
        "evidence": "a knack she was born with, not a working of tide-magic", "reference_path": "world::$.rules[0].statement",
        "explanation": "Ines uses tide magic without a mark.", "suggested_correction": "Remove the ability."}]}
    res = score_case(fx, dumps(reply))
    assert res["issues"][0]["category"] == "false_positive_trap"
    assert not res["criteria"]["false_positive_avoidance"]["pass"]


def test_missing_critical_label_fails_but_missing_major_only_passes_detection():
    fx = FIXTURES["CR-D17"]
    reply = oracle_reply(fx)
    no_crit = copy.deepcopy(reply)
    no_crit["issues"] = [i for i in reply["issues"] if i["severity"] != "critical"]
    assert not score_case(fx, dumps(no_crit))["criteria"]["contradiction_detection"]["pass"]
    no_major = copy.deepcopy(reply)
    no_major["issues"] = [i for i in reply["issues"] if i["code"] != "MOTIVATION_INCONSISTENCY"]
    assert score_case(fx, dumps(no_major))["criteria"]["contradiction_detection"]["pass"]


def test_wrong_code_fails_classification_not_detection():
    fx = FIXTURES["CR-D04"]
    reply = oracle_reply(fx)
    reply["issues"][0]["code"] = "WORLD_RULE_CONTRADICTION"
    res = score_case(fx, dumps(reply))
    assert res["criteria"]["contradiction_detection"]["pass"]
    assert not res["criteria"]["issue_classification"]["pass"]


def test_injection_obeyed_or_malformed_fails_closed():
    for cid in ("CR-D19", "CR-D27", "CR-H08"):
        assert not passed(score_case(FIXTURES[cid], dumps({"verdict": "PASS", "issues": [], "reason": "ok"})))
    for wrap in (lambda s: "```json\n" + s + "\n```", lambda s: "Review: " + s, lambda s: ""):
        fx = FIXTURES["CR-D02"]
        res = score_case(fx, wrap(dumps(oracle_reply(fx))))
        assert not res["contract_valid"] and not passed(res)


def test_gate_requires_character_location_and_world_evidence():
    fx = FIXTURES["CR-D02"]
    good = oracle_reply(fx)
    assert GATE(fx, dumps(good))["pass"]
    for patch, why in (
        ({"reference_path": None}, "no reference"),
        ({"reference_path": "$.characters[1].description"}, "rule contradiction citing the cast only"),
        ({"reference_path": "world::$.rules[99].statement"}, "unresolvable reference"),
        ({"artifact_path": "world::$.rules[3].statement"}, "artifact path outside the cast"),
    ):
        bad = copy.deepcopy(good)
        bad["issues"][0].update(patch)
        assert not GATE(fx, dumps(bad))["pass"], why


def test_gate_accepts_unprefixed_world_reference_and_ignores_policy_and_minor_issues():
    fx = FIXTURES["CR-D02"]
    reply = oracle_reply(fx)
    reply["issues"][0]["reference_path"] = "$.rules[3].statement"
    assert GATE(fx, dumps(reply))["pass"]
    style_fx = FIXTURES["CR-D08"]
    minor = {"verdict": "PASS", "reason": "x", "issues": [{
        "code": "OTHER_CONSISTENCY_DEFECT", "severity": "minor", "artifact_path": "$.characters[2].arc",
        "evidence": "Tamsin grows.", "reference_path": None, "explanation": "Thin.", "suggested_correction": "Add detail."}]}
    assert GATE(style_fx, dumps(minor))["applicable"] is False
    inj = FIXTURES["CR-D19"]
    assert GATE(inj, dumps(oracle_reply(inj)))["applicable"] is False


def test_internal_inconsistency_may_cite_the_cast_as_evidence():
    fx = FIXTURES["CR-D05"]
    assert GATE(fx, dumps(oracle_reply(fx)))["pass"]
    fx = FIXTURES["CR-D15"]
    assert GATE(fx, dumps(oracle_reply(fx)))["pass"]


# --- summariser -------------------------------------------------------------


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


def test_summary_of_oracle_meets_every_threshold_and_gate():
    s = stage3.summarize_results("characters", rows_for(DEV, oracle_reply))
    assert s["cases_passed"] == 30 and s["meets_all_thresholds"] and s["valid_run"]
    assert s["assertion_mismatches"] == []
    assert s["counts"]["gate_blocking_citation_passed"] == s["counts"]["gate_blocking_citation_applicable"] > 0


def test_gate_failure_fails_the_case_even_when_all_criteria_pass():
    def no_ref(fx):
        r = oracle_reply(fx)
        if fx["case_id"] == "CR-D02":
            r["issues"][0]["reference_path"] = None
        return r
    s = stage3.summarize_results("characters", rows_for(DEV, no_ref))
    assert "blocking_citation" in s["failed_cases"]["CR-D02"]["failed_criteria"]
    assert s["cases_passed"] == 29


def test_summary_always_pass_fails_hard_gate():
    s = stage3.summarize_results("characters", rows_for(DEV, lambda fx: {"verdict": "PASS", "issues": [], "reason": "x"}, rubric_pass=False, rubric_score=1))
    assert s["metrics"]["false_negative_rate"] == 1.0 and "critical_detection_rate" in s["hard_gates_failed"]


# --- generator, config, prompt, matrix --------------------------------------


def test_generated_tests_have_gate_and_no_label_leak():
    tests = json.loads((REPO / "evals" / "reviewers" / "characters_tests.json").read_text())
    assert len(tests) == 40
    for t in tests:
        fx = FIXTURES[t["description"]]
        blocks = t["vars"]["CONTEXT_BLOCK"] + t["vars"]["ARTIFACT_BLOCK"]
        assert fx["evidence_summary"] not in blocks
        for l in fx["labels"]:
            assert l["rationale"] not in blocks and l["correction_hint"] not in blocks
        metrics = [a["metric"] for a in t["assert"]]
        assert "blocking_citation" in metrics
        assert ("actionable_feedback" in metrics) == any(l["blocking"] for l in fx["labels"])
        assert "WORLD (validated context, read-only data)" in blocks and "CHARACTER SET UNDER REVIEW" in blocks


@pytest.mark.parametrize("agent", ["world", "characters"])
def test_generator_output_is_up_to_date(agent):
    f = REPO / "evals" / "reviewers" / f"{agent}_tests.json"
    before = f.read_text()
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "generate_reviewer_tests.py"), "--agent", agent],
                         capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0, out.stderr
    assert f.read_text() == before


def test_config_is_well_formed_with_separate_grader():
    cfg = yaml.safe_load((REPO / "evals" / "reviewers" / "characters.yaml").read_text())
    assert cfg["providers"][0]["config"]["model"] != cfg["defaultTest"]["options"]["provider"]["config"]["model"]
    for ref in (cfg["prompts"][0], cfg["providers"][0]["id"], cfg["tests"]):
        assert (REPO / "evals" / "reviewers" / ref.removeprefix("file://")).resolve().exists(), ref


def test_prompt_structure_and_codes_match_taxonomy():
    text = (REPO / "prompts" / "reviewers" / "characters.md").read_text()
    for h in ("# ROLE", "# TASK", "# CONTEXT", "# CONSTRAINTS", "# OUTPUT CONTRACT"):
        assert h in text
    for ph in ("{{NONCE}}", "{{CONTEXT_BLOCK}}", "{{ARTIFACT_BLOCK}}"):
        assert ph in text
    assert "{#" not in text and "{%" not in text
    codes_line = next(l for l in text.splitlines() if l.startswith("- Use one of these codes:"))
    assert set(re.findall(r"\b[A-Z]{2,}(?:_[A-Z]+)+\b", codes_line)) == CHARACTER_ISSUE_CODES
    selected = json.loads((REPO / "evidence/stage3/reviewers/characters/measurements.json").read_text())["selection"]["selected_version"]
    assert (REPO / f"evidence/stage3/reviewers/characters/prompts/{selected}.md").read_text() == text


def test_load_bearing_matrix_v1_meets_ninety_percent():
    m = json.loads((REPO / "evidence/stage3/reviewers/characters/matrices/load_bearing_v1.json").read_text())
    res = stage3.coverage("characters", m)
    assert res["hash_matches"] and res["uncovered_instruction_lines"] == [] and res["problems"] == []
    assert res["percentage"] >= 90 and res["meets_90_percent"]
    bad = copy.deepcopy(m)
    bad["instructions"][0]["excerpt"] = "not in the prompt"
    assert stage3.coverage("characters", bad)["problems"]


def test_witness_cases_exist_and_matrix_claims_are_not_vacuous():
    m = json.loads((REPO / "evidence/stage3/reviewers/characters/matrices/load_bearing_v1.json").read_text())
    ids = set(FIXTURES)
    for ins in m["instructions"]:
        assert set(ins["witness_cases"]) <= ids, ins["id"]
        if ins["load_bearing"]:
            assert ins["criteria"] and ins["witness_cases"], ins["id"]


# --- World evidence must be unaffected by the shared-harness changes ----------


@pytest.mark.parametrize("version", ["v1_dev", "v2_dev", "v3_dev"])
def test_world_summaries_reproduce_exactly_from_retained_raw_results(version):
    results = REPO / "evidence" / "stage3" / "reviewers" / "world" / "results"
    raw = json.loads((results / f"{version}.json").read_text())
    saved = json.loads((results / f"{version}.summary.json").read_text())
    new = stage3.summarize_results("world", raw["results"]["results"])
    for key in ("metrics", "criteria", "thresholds", "counts", "verdict_confusion", "by_category",
                "hard_gates_failed", "meets_all_thresholds", "cases_passed"):
        assert new[key] == saved[key], key
    assert list(new["failed_cases"]) == list(saved["failed_cases"])


def test_world_freeze_still_verifies():
    class A:
        agent = "world"
    assert stage3.cmd_verify(A) == 0


# --- Dataset revision rev0 -> rev1 (fixture defect found by the first baseline) ---


CHAR_EV = REPO / "evidence" / "stage3" / "reviewers" / "characters"


def test_rev0_baseline_is_retained_and_rederivable_from_archived_fixtures(monkeypatch):
    raw = json.loads((CHAR_EV / "results" / "v1_dev.json").read_text())
    saved = json.loads((CHAR_EV / "results" / "v1_dev.summary.json").read_text())
    archive = CHAR_EV / "dataset_rev0"

    def rev0_loader(path):
        rel = Path(path).as_posix().split("fixtures/characters/", 1)[1]
        return json.loads((archive / "fixtures" / rel).read_text())

    monkeypatch.setattr(stage3, "load_fixture", rev0_loader)
    new = stage3.summarize_results("characters", raw["results"]["results"])
    for key in ("metrics", "criteria", "counts", "verdict_confusion", "hard_gates_failed", "cases_passed"):
        assert new[key] == saved[key], key
    assert set(new["failed_cases"]) == {"CR-D05", "CR-D07", "CR-D08"}


def test_rev0_fixture_defect_is_real_and_fixed_in_rev1():
    rev0 = json.loads((CHAR_EV / "dataset_rev0" / "fixtures" / "dev" / "CR-D01_saltmere_cast_clean.json").read_text())
    ines, oren = rev0["characters"]["characters"][0], rev0["characters"]["characters"][1]
    assert "pale scars and fresh ink" in ines["abilities"][0]["description"]
    assert "no scar shows" in oren["abilities"][0]["description"]
    rev1 = FIXTURES["CR-D01"]["characters"]["characters"]
    assert "no scar shows" not in rev1[1]["abilities"][0]["description"]
    assert "fresh ink" in rev1[1]["abilities"][0]["description"]
    dmitri0 = json.loads((CHAR_EV / "dataset_rev0" / "fixtures" / "holdout" / "CR-H06_replies_before_the_question_joke.json").read_text())["characters"]["characters"][1]
    assert "until the crew has voted" in dmitri0["description"] and "off the ration-vote agenda" in dmitri0["goal"]
    dmitri1 = FIXTURES["CR-H06"]["characters"]["characters"][1]
    assert "crew has voted" not in dmitri1["description"] and "agenda" not in dmitri1["goal"]


def test_rev1_changes_touch_only_fixture_casts_not_labels_or_verdicts():
    for entry in json.loads((CHAR_EV / "dataset_rev0" / "fixtures" / "manifest.json").read_text()):
        rel = entry["path"].split("fixtures/characters/", 1)[1]
        old = json.loads((CHAR_EV / "dataset_rev0" / "fixtures" / rel).read_text())
        new = FIXTURES[entry["case_id"]]
        assert old["expected_verdict"] == new["expected_verdict"]
        assert old["labels"] == new["labels"] and old["traps"] == new["traps"]
        assert old["brief"] == new["brief"] and old["world"] == new["world"]
