"""Offline tests for the Stage 3 storyboard eval harness (assert facets + summariser)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STORYBOARDS_DIR = REPO_ROOT / "examples" / "storyboards"
INVALID_DIR = STORYBOARDS_DIR / "invalid"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_asserts = _load_module(
    "storyboard_stage3_assert", REPO_ROOT / "evals" / "storyboard_stage3_assert.py"
)
_stage3 = _load_module(
    "storyboard_stage3", REPO_ROOT / "scripts" / "storyboard_stage3.py"
)

FACETS = [
    "schema_validity",
    "referential_integrity",
    "dependency_validity",
    "narrative_phase_correctness",
    "format_discipline",
]


@pytest.fixture(scope="module")
def context() -> dict:
    return {
        "vars": {
            "STORY_BRIEF_JSON": (REPO_ROOT / "examples" / "story_brief.json").read_text(),
            "WORLD_JSON": (
                REPO_ROOT / "evals" / "fixtures" / "storyboard" / "worlds" / "aetheria.json"
            ).read_text(),
            "CHARACTER_SET_JSON": (
                REPO_ROOT
                / "evals"
                / "fixtures"
                / "storyboard"
                / "characters"
                / "aetheria_cast.json"
            ).read_text(),
        }
    }


def test_valid_storyboard_passes_all_facets(context):
    output = (STORYBOARDS_DIR / "valid_storyboard.json").read_text()
    for facet in FACETS:
        result = getattr(_asserts, facet)(output, context)
        assert result["pass"], f"{facet}: {result['reason']}"


@pytest.mark.parametrize(
    "filename,facet",
    [
        ("unknown_character.json", "referential_integrity"),
        ("unknown_location.json", "referential_integrity"),
        ("invalid_world_id.json", "referential_integrity"),
        ("duplicate_scene_id.json", "referential_integrity"),
        ("forward_dependency.json", "dependency_validity"),
        ("cyclic_dependencies.json", "dependency_validity"),
        ("invalid_phase_order.json", "narrative_phase_correctness"),
        ("missing_narrative_phase.json", "narrative_phase_correctness"),
    ],
)
def test_invalid_example_fails_expected_facet(context, filename, facet):
    output = (INVALID_DIR / filename).read_text()
    assert getattr(_asserts, "schema_validity")(output, context)["pass"], filename
    result = getattr(_asserts, facet)(output, context)
    assert not result["pass"], f"{filename}/{facet} unexpectedly passed"
    assert not result["reason"].startswith("NOT_EVALUABLE"), result["reason"]


def test_non_json_output_semantic_facets_not_evaluable(context):
    assert not _asserts.schema_validity("not json", context)["pass"]
    for facet in [
        "referential_integrity",
        "dependency_validity",
        "narrative_phase_correctness",
    ]:
        result = getattr(_asserts, facet)("not json", context)
        assert not result["pass"]
        assert result["reason"].startswith("NOT_EVALUABLE"), result["reason"]


def test_format_discipline_uses_raw_output_metadata(context):
    valid = (STORYBOARDS_DIR / "valid_storyboard.json").read_text()
    fenced = f"```json\n{valid}\n```"
    ctx_fenced = {
        **context,
        "providerResponse": {"metadata": {"raw_output": fenced}},
    }
    assert not _asserts.format_discipline(valid, ctx_fenced)["pass"]
    ctx_bare = {
        **context,
        "providerResponse": {"metadata": {"raw_output": valid}},
    }
    assert _asserts.format_discipline(valid, ctx_bare)["pass"]


# ---------------------------------------------------------------------------
# summarize()
# ---------------------------------------------------------------------------

DET_PASS = [
    "structural_validity",
    "schema_validity",
    "referential_integrity",
    "dependency_validity",
    "narrative_phase_correctness",
    "format_discipline",
]
RUBRICS = {
    "causal_coherence": 0.30,
    "character_consistency": 0.25,
    "narrative_structure": 0.20,
    "world_consistency": 0.15,
    "pacing": 0.10,
}


def _component(metric, passed, score, reason="ok"):
    return {
        "pass": passed,
        "score": score,
        "reason": reason,
        "assertion": {"type": "python", "metric": metric},
    }


def _row(case, components, error=None, failure_reason=0):
    row = {
        "testCase": {
            "metadata": {"split": "dev", "case": case, "expected": "valid"},
            "description": case,
        },
        "response": {"output": "{}"},
        "gradingResult": {"componentResults": components},
        "failureReason": failure_reason,
    }
    if error:
        row["response"]["error"] = error
    return row


def _passing_components(rubric_score=5):
    comps = [_component(m, True, 1) for m in DET_PASS]
    comps += [_component(m, True, rubric_score) for m in RUBRICS]
    return comps


def test_summarize(tmp_path):
    rows = []
    # (a) fully passing case
    rows.append(_row("a_pass", _passing_components()))
    # (b) rubric content failure: causal_coherence 3/5
    comps = _passing_components()
    comps[6] = _component("causal_coherence", False, 3, "weak causal links")
    rows.append(_row("b_rubric_fail", comps))
    # (c) provider error
    rows.append(
        _row("c_provider_error", [], error="rate limit exceeded", failure_reason=2)
    )
    # (d) schema failure; semantic facets not evaluable
    comps = [
        _component("structural_validity", True, 1),
        _component("schema_validity", False, 0, "schema violations"),
        _component(
            "referential_integrity", False, 0, "NOT_EVALUABLE: schema violations stopped semantic validation"
        ),
        _component(
            "dependency_validity", False, 0, "NOT_EVALUABLE: schema violations stopped semantic validation"
        ),
        _component(
            "narrative_phase_correctness", False, 0, "NOT_EVALUABLE: schema violations stopped semantic validation"
        ),
        _component("format_discipline", True, 1),
    ]
    comps += [_component(m, True, 5) for m in RUBRICS]
    rows.append(_row("d_schema_fail", comps))
    # (e) grader error on a rubric (score 0 + extraction error reason)
    comps = _passing_components()
    comps[6] = _component("causal_coherence", False, 0, "Could not extract JSON")
    rows.append(_row("e_grader_error", comps))

    raw = tmp_path / "synthetic.json"
    raw.write_text(
        json.dumps(
            {
                "evalId": "eval-x",
                "results": {"timestamp": "t", "results": rows},
            }
        )
    )

    summary = _stage3.summarize(raw, "v1", "dev")

    assert summary["prompt_sha256"] is not None
    assert summary["cases_attempted"] == 5

    # provider error accounting
    assert len(summary["provider_errors"]) == 1
    assert "provider_error" in summary["per_case"]["c_provider_error"]
    q = summary["overall_quality"]
    assert q["cases_scored"] == 3  # a, b, d; not c, not e
    assert q["cases_passed"] == 1  # only a
    assert q["pass_rate_strict_of_attempted"] == pytest.approx(1 / 5)

    # grader error registered separately, not a content failure
    assert len(summary["grader_errors"]) == 1
    assert summary["grader_errors"][0]["case"] == "e_grader_error"
    failed_cases = {f["case"] for f in summary["failed_cases"]}
    assert failed_cases == {"b_rubric_fail", "d_schema_fail"}

    # not_evaluable accounting for case d
    for m in (
        "referential_integrity",
        "dependency_validity",
        "narrative_phase_correctness",
    ):
        c = summary["criteria"][m]
        assert c["not_evaluable"] == 1
        assert c["scored"] == 3  # a, b and e (e's other metrics still score)

    # weighted scores
    assert summary["per_case"]["a_pass"]["_weighted_score"] == pytest.approx(1.0)
    expected_b = 0.30 * 3 / 5 + 0.25 + 0.20 + 0.15 + 0.10
    assert summary["per_case"]["b_rubric_fail"]["_weighted_score"] == pytest.approx(
        expected_b
    )
    # d's rubrics all pass so it is weighted too; e has a grader error -> None
    assert summary["per_case"]["d_schema_fail"]["_weighted_score"] == pytest.approx(1.0)
    assert summary["per_case"]["e_grader_error"]["_weighted_score"] is None
    assert summary["weighted_score"]["cases"] == 3
    assert summary["weighted_score"]["mean"] == pytest.approx((1.0 + expected_b + 1.0) / 3)

    # summary file written next to the raw result
    assert raw.with_suffix(".summary.json").exists()
