"""Offline consistency checks between docs/workflow.md and the implementation.

These tests make the Stage 4 workflow definition falsifiable: every state,
gate decision, step id, gate name, error code and retry limit the document
claims must exist in the code it describes.  No model calls, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from fictionforge.config import WorkflowConfig
from fictionforge.guardrails.handoff import DECISIONS, UPSTREAM_GATES
from fictionforge.guardrails.punch_out import PunchOutReason
from fictionforge.guardrails.review import (
    REVIEW_MODES,
    SELECTED_PROMPT_VERSIONS,
    default_reviewer_configs,
)
from fictionforge.runner import (
    StepStatus,
    WorkflowRunner,
    WorkflowStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "workflow.md"
EVAL_YAML = REPO_ROOT / "evals" / "workflow.yaml"
WORKFLOW_YAML = REPO_ROOT / "config" / "workflow.yaml"

pytestmark = pytest.mark.skipif(
    not DOC_PATH.exists(), reason="docs/workflow.md not present"
)


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_workflow_doc_exists_and_has_required_sections(doc):
    for heading in (
        "## 1. Workflow identity",
        "## 2. Workflow graph",
        "## 3. Handoff contracts",
        "## 4. Branching logic",
        "## 5. Ordinary failures vs. human punch-outs",
        "## 6. Automated guardrail stack",
        "## 10. Gaps and limitations",
    ):
        assert heading in doc, f"missing section {heading!r}"


def test_mermaid_graph_present_and_covers_all_steps(doc):
    assert "```mermaid" in doc, "no mermaid diagram found"
    mermaid = doc.split("```mermaid", 1)[1].split("```", 1)[0]
    for step_id in (
        "load_brief",
        "world_generation",
        "character_design",
        "storyboard_building",
    ):
        assert step_id in mermaid, f"{step_id} missing from workflow graph"
    for terminal in ("completed", "failed_automated", "punch_out_required"):
        assert terminal in mermaid, f"terminal state {terminal} missing"


def test_documented_workflow_statuses_match_enum(doc):
    for status in WorkflowStatus:
        assert status.value in doc, f"undocumented WorkflowStatus {status.value}"
    # Every status value actually used by the runner must appear in the
    # success/failure condition table.
    for expected in ("completed", "failed_automated", "punch_out_required"):
        assert expected in doc


def test_documented_step_statuses_match_enum(doc):
    for status in StepStatus:
        assert status.value in doc, f"undocumented StepStatus {status.value}"


def test_all_gate_decisions_documented(doc):
    for decision in DECISIONS:
        assert decision in doc, f"gate decision {decision} not in docs"


def test_step_ids_and_gate_names_consistent(doc):
    configs = default_reviewer_configs()
    assert set(configs) == set(WorkflowRunner.PROMPTS) == set(
        WorkflowRunner.RESUMABLE_STEPS
    ), "reviewer/runner step sets diverged"
    for cfg in configs.values():
        assert cfg.gate in doc
        assert cfg.reviewer_id in doc
        assert f"prompts/reviewers/{cfg.gate}.md" in doc
    for gate in UPSTREAM_GATES.values():
        assert gate in SELECTED_PROMPT_VERSIONS
    for gate, version in SELECTED_PROMPT_VERSIONS.items():
        assert version in doc, f"selected reviewer prompt {gate}={version} undocumented"


def test_documented_error_codes_match_config(doc):
    config = WorkflowConfig.from_yaml(WORKFLOW_YAML)
    for code in config.retryable_errors + config.non_retryable_errors:
        assert code in doc, f"error code {code} configured but undocumented"


def test_documented_retry_limits_match_config(doc):
    config = WorkflowConfig.from_yaml(WORKFLOW_YAML)
    assert f"max_attempts_per_step: {config.max_attempts_per_step}" in doc or (
        f"(default {config.max_attempts_per_step})" in doc
    ), "documented attempt budget does not match config"
    # Reviewer attempt budget must also be documented.
    assert str(config.review_max_attempts) in doc


def test_documented_review_modes_and_punch_out_reasons(doc):
    for mode in REVIEW_MODES:
        assert mode in doc
    for reason in PunchOutReason:
        assert reason.value in doc, f"PunchOutReason {reason.value} undocumented"


def test_documented_models_match_config(doc):
    config = WorkflowConfig.from_yaml(WORKFLOW_YAML)
    assert config.model in doc, f"generation model {config.model} undocumented"
    assert config.review_model in doc
    for gate, model in (config.review_models or {}).items():
        assert model in doc, f"reviewer model for {gate} undocumented"


def test_workflow_yaml_criteria_complete():
    data = yaml.safe_load(EVAL_YAML.read_text(encoding="utf-8"))
    criteria = data.get("criteria")
    assert isinstance(criteria, list) and len(criteria) == 7
    required = {
        "id",
        "name",
        "purpose",
        "inputs",
        "measurement",
        "expected",
        "pass_fail",
        "evidence",
    }
    names = set()
    for c in criteria:
        assert required <= set(c), f"criterion missing fields: {c.get('id')}"
        names.add(c["name"])
        # Referenced evidence paths must be repository-relative, never absolute.
        assert not c["evidence"].startswith("/")
    assert names == {
        "end_to_end_narrative_quality",
        "handoff_correctness",
        "reviewer_gate_enforcement",
        "branching_and_retry_correctness",
        "human_escalation_correctness",
        "execution_reliability",
        "audit_completeness_and_cost_attribution",
    }


def test_workflow_yaml_existing_keys_preserved():
    """The harness contract (dataset/runner/grader/output) must remain intact."""
    data = yaml.safe_load(EVAL_YAML.read_text(encoding="utf-8"))
    assert data["dataset"]["version"] == "workflow-v1.1.0"
    assert data["runner"]["config"] == "config/workflow.yaml"
    assert data["grader"]["use_llm_rubrics"] is False
    assert data["output"]["evidence_dir"] == "evidence"
    assert data["default_splits"] == ["dev"]


def test_manifest_declares_six_agents_and_workflow_artifacts():
    manifest = yaml.safe_load(
        (REPO_ROOT / "manifest.yaml").read_text(encoding="utf-8")
    )
    steps = {s["name"] for s in manifest["workflow"]["steps"]}
    assert steps == {
        "world_generation",
        "world_review",
        "character_design",
        "characters_review",
        "storyboard_building",
        "storyboard_review",
    }
    artifacts = manifest["workflow"]["artifacts"]
    for key in ("guardrails", "punch_out", "success_rate", "audit_trail", "log"):
        assert key in artifacts


def test_docs_have_no_absolute_local_paths(doc):
    assert "/Users/" not in doc, "docs/workflow.md contains a local absolute path"
    assert "C:\\" not in doc
