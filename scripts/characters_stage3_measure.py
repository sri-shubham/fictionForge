#!/usr/bin/env python3
"""Aggregate retained Character Design Stage 3 results into evidence/stage3/characters/measurements.json.

Reads only retained files (summaries, matrices, diffs, frozen config); makes no model calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EV = REPO / "evidence" / "stage3" / "characters"
RUBRICS = ["motivation_clarity", "world_consistency", "character_differentiation", "conflict_potential", "character_development"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def result_block(summary_path: Path) -> dict:
    s = json.loads(summary_path.read_text())
    return {
        "eval_id": s["eval_id"], "timestamp": s["timestamp"], "split": s["split"],
        "prompt_version": s["prompt_version"], "prompt_sha256": s["prompt_sha256"],
        "raw_result_file": s["raw_result_file"], "raw_result_sha256": s["raw_result_sha256"],
        "summary_file": rel(summary_path), "config_sha256": s["config_sha256"], "dataset_sha256": s["dataset_sha256"],
        "cases_total": s["cases_total"], "provider_errors": len(s["provider_errors"]), "grader_errors": len(s["grader_errors"]),
        "structural_validity": s["structural_validity"],
        "criteria": s["criteria"], "overall_quality": s["overall_quality"],
        "failed_cases": [{"case": f["case"], "failures": [{"metric": x["metric"], "score": x["score"]} for x in f["failures"]]} for f in s["failed_cases"]],
    }


def main() -> None:
    frozen = json.loads((EV / "frozen_eval_config.json").read_text())
    versions = {}
    for v in ("v1", "v2", "v3"):
        prompt = EV / "prompts" / f"{v}.md"
        matrix = json.loads((EV / "matrices" / f"load_bearing_{v}.json").read_text())
        n = len(matrix["instructions"])
        lb = sum(i["load_bearing"] for i in matrix["instructions"])
        dev = EV / "results" / f"{v}_dev.summary.json"
        versions[v] = {
            "prompt_file": rel(prompt), "prompt_sha256": sha(prompt),
            "instructions": n, "load_bearing": lb, "load_bearing_pct": round(100 * lb / n, 1),
            "matrix_file": rel(EV / "matrices" / f"load_bearing_{v}.json"),
            "dev": result_block(dev) if dev.exists() else None,
        }
    diffs = {k: {"file": rel(EV / "diffs" / f"{k}.diff"), "sha256": sha(EV / "diffs" / f"{k}.diff")} for k in ("v1_to_v2", "v2_to_v3")}
    extra = {}
    for label in ("final_dev", "final_holdout"):
        p = EV / "results" / f"{label}.summary.json"
        extra[label] = result_block(p) if p.exists() else None
    flips = {}
    sums = {v: json.loads((EV / "results" / f"{v}_dev.summary.json").read_text()) for v in versions if versions[v]["dev"]}
    if len(sums) == 3:
        for case in sums["v1"]["per_case"]:
            for m in RUBRICS:
                sc = [sums[v]["per_case"][case][m]["score"] for v in ("v1", "v2", "v3")]
                if len(set(sc)) > 1:
                    flips[f"{case}/{m}"] = sc
    out = {
        "agent": "character_design",
        "frozen_config_file": rel(EV / "frozen_eval_config.json"),
        "frozen_config_sha256": sha(EV / "frozen_eval_config.json"),
        "frozen_files": frozen["files"], "dataset_sha256": frozen["dataset_sha256"],
        "models": {"generation": "fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium", "grader": "swe-2-medium"},
        "versions": versions, "diffs": diffs,
        "per_case_rubric_score_changes_v1_v2_v3": flips,
        "final_dev": extra["final_dev"], "final_holdout": extra["final_holdout"],
        "selected_prompt": "v3",
        "notes": "All numbers are copied from retained .summary.json files; per-case changes list [v1, v2, v3] rubric scores where they differ.",
    }
    (EV / "measurements.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {EV / 'measurements.json'}; final_dev={'yes' if extra['final_dev'] else 'pending'}, final_holdout={'yes' if extra['final_holdout'] else 'pending'}")


if __name__ == "__main__":
    main()
