#!/usr/bin/env python3
"""Generate the holdout_v2 Promptfoo test files and eval configs.

    .venv/bin/python scripts/generate_holdout_v2_evals.py

Outputs (all NEW files; nothing frozen is touched):

    evals/holdout_v2/world_tests.json
    evals/holdout_v2/characters_tests.json
    evals/holdout_v2/storyboard_tests.json
    evals/reviewers/holdout_v2_{world,characters,storyboard}_tests.json
    evals/{world,characters,storyboard}_holdout_v2.yaml
    evals/reviewers/{world,characters,storyboard}_holdout_v2.yaml

The yaml configs are byte-for-byte copies of the frozen Stage 3 configs except
for the ``description`` and the ``tests:`` path, so prompts, rubrics, providers
and thresholds are preserved.  Run them manually with ``--prompts`` and
``--filter-metadata split=holdout_v2`` exactly like the frozen suites.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "evals" / "reviewers"))
sys.path.insert(0, str(REPO / "scripts"))

from holdout_v2_data import SETTINGS  # noqa: E402
from fictionforge.guardrails.reviewer_contract import render_block  # noqa: E402
from reviewer_scoring import expected_findings_text, load_fixture  # noqa: E402

SPLIT = "holdout_v2"
FIX = "evals/fixtures/holdout_v2"
OUT = REPO / "evals" / "holdout_v2"

AGENT_VARS = {
    "world": ["STORY_BRIEF_JSON"],
    "characters": ["STORY_BRIEF_JSON", "WORLD_JSON"],
    "storyboard": ["STORY_BRIEF_JSON", "WORLD_JSON", "CHARACTER_SET_JSON"],
}

REVIEWER_SPEC = {
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

BASE = "evals/fixtures/holdout_v2"


def gen_tests() -> None:
    """Generation-agent test files, same shape as the frozen *_stage3_tests.json."""
    for agent in ("world", "characters", "storyboard"):
        tests = []
        for s in SETTINGS:
            name = s["gen_name"]
            if agent == "world":
                var_files = {"STORY_BRIEF_JSON": f"{BASE}/world/{name}.json"}
            elif agent == "characters":
                var_files = {"STORY_BRIEF_JSON": f"{BASE}/characters/briefs/{name}.json",
                             "WORLD_JSON": f"{BASE}/characters/worlds/{name}.json"}
            else:
                var_files = {"STORY_BRIEF_JSON": f"{BASE}/storyboard/briefs/{name}.json",
                             "WORLD_JSON": f"{BASE}/storyboard/worlds/{name}.json",
                             "CHARACTER_SET_JSON": f"{BASE}/storyboard/characters/{name}.json"}
            tests.append({
                "description": name,
                "vars": {**{k: f"file://{v.removeprefix('evals/')}" for k, v in var_files.items()},
                         "EXPECTED": "valid"},
                "metadata": {"split": SPLIT, "case": name, "expected": "valid"},
            })
        path = OUT / f"{agent}_tests.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({len(tests)} cases)")


def reviewer_tests() -> None:
    """Reviewer test files, same shape as scripts/generate_reviewer_tests.py."""
    for agent, spec in REVIEWER_SPEC.items():
        tests = []
        prefix = {"world": "WR", "characters": "CR", "storyboard": "SR"}[agent]
        for s in SETTINGS:
            cid = f"{prefix}-V2-{s['num']:02d}"
            path_str = f"{BASE}/reviewers/{agent}/{cid}_{s['slug']}.json"
            fx = load_fixture(path_str)
            nonce = hashlib.sha256(cid.encode()).hexdigest()[:16]
            art_key, art_title = spec["artifact"]
            context_block = "\n\n".join(
                render_block(title, fx[key], nonce) for key, title in spec["context"])
            artifact_block = render_block(art_title, fx[art_key], nonce)
            asserts = [{"type": "python", "value": f"file://reviewer_assert.py:{n}", "metric": n}
                       for n in ("contract_validity", "false_positive_avoidance",
                                 "issue_classification", "evidence_grounding")]
            if any(l["blocking"] for l in fx["labels"]):  # never true for positive cases
                raise SystemExit(f"{cid}: positive holdout_v2 fixture must not have blocking labels")
            for gate in spec["gates"]:
                asserts.append({"type": "python",
                                "value": f"file://{spec['gate_module']}.py:{gate}", "metric": gate})
            context_json = json.dumps(
                {k: fx[k] for k in ("brief", "world", "characters", "storyboard") if k in fx},
                ensure_ascii=False, sort_keys=True)
            tests.append({
                "description": cid,
                "vars": {
                    "CASE_FILE": path_str,
                    "NONCE": nonce,
                    "CONTEXT_BLOCK": context_block,
                    "ARTIFACT_BLOCK": artifact_block,
                    "EXPECTED_FINDINGS": expected_findings_text(fx),
                    "CONTEXT_JSON": context_json,
                },
                "metadata": {"split": fx["split"], "case": cid,
                             "expected": fx["expected_verdict"], "category": fx["category"]},
                "assert": asserts,
            })
        path = REPO / "evals" / "reviewers" / f"holdout_v2_{agent}_tests.json"
        path.write_text(json.dumps(tests, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({len(tests)} cases)")


def yaml_configs() -> None:
    """Copy each frozen config, changing only description and the tests path."""
    copies = [
        ("evals/world_stage3.yaml", "evals/world_holdout_v2.yaml",
         "Storyboard", "World Generation",
         "tests: file://world_stage3_tests.json", "tests: file://holdout_v2/world_tests.json"),
        ("evals/characters_stage3.yaml", "evals/characters_holdout_v2.yaml",
         None, "Character Design",
         "tests: file://characters_stage3_tests.json", "tests: file://holdout_v2/characters_tests.json"),
        ("evals/storyboard_stage3.yaml", "evals/storyboard_holdout_v2.yaml",
         None, "Storyboard Building",
         "tests: file://storyboard_stage3_tests.json", "tests: file://holdout_v2/storyboard_tests.json"),
        ("evals/reviewers/world.yaml", "evals/reviewers/world_holdout_v2.yaml",
         None, "World Adversarial Reviewer",
         "tests: file://world_tests.json", "tests: file://holdout_v2_world_tests.json"),
        ("evals/reviewers/characters.yaml", "evals/reviewers/characters_holdout_v2.yaml",
         None, "Character Adversarial Reviewer",
         "tests: file://characters_tests.json", "tests: file://holdout_v2_characters_tests.json"),
        ("evals/reviewers/storyboard.yaml", "evals/reviewers/storyboard_holdout_v2.yaml",
         None, "Storyboard Adversarial Reviewer",
         "tests: file://storyboard_tests.json", "tests: file://holdout_v2_storyboard_tests.json"),
    ]
    for src, dst, _unused, label, old_tests, new_tests in copies:
        text = (REPO / src).read_text(encoding="utf-8")
        assert text.count(old_tests) == 1, f"{src}: expected exactly one {old_tests!r}"
        text = text.replace(old_tests, new_tests)
        desc_line = next(l for l in text.splitlines() if l.startswith("description:"))
        text = text.replace(
            desc_line,
            f"description: {label} Stage 3 holdout_v2 evaluation (positive cases only)")
        (REPO / dst).write_text(text, encoding="utf-8")
        print(f"wrote {dst}")


def main() -> int:
    gen_tests()
    reviewer_tests()
    yaml_configs()
    print("holdout_v2 eval files generated; nothing frozen was modified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
