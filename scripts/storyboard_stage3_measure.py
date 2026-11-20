#!/usr/bin/env python3
"""Aggregate retained Storyboard Building Stage 3 results into evidence/stage3/storyboard/measurements.json
and results/compare_v1_v2_v3_dev.md (+ compare_all.md).

Reads only retained files (summaries, matrices, diffs, frozen config); makes no model calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EV = REPO / "evidence" / "stage3" / "storyboard"
RES = EV / "results"
RUBRICS = ["causal_coherence", "character_consistency", "narrative_structure", "world_consistency", "pacing"]
WEIGHTS = {"causal_coherence": 0.30, "character_consistency": 0.25, "narrative_structure": 0.20,
           "world_consistency": 0.15, "pacing": 0.10}
FACETS = ["structural_validity", "schema_validity", "referential_integrity", "dependency_validity",
          "narrative_phase_correctness", "format_discipline"]
DEV = {"v1": "v1_dev", "v2": "v2_dev", "v3": "v3_dev"}
EXTRA_RUNS = ["v1_dev_attempt1_recovered", "v3_dev_attempt1_recovered", "final_dev", "final_holdout"]
LEGACY = {
    "eval-njD-2026-10-28T17:46:35": {"file": "evidence/runs/storyboard/eval_smoke.json", "outcome": "5 provider errors (Not logged in); no measurements"},
    "eval-wwm-2026-10-28T18:10:25": {"file": "evidence/runs/storyboard/eval_smoke_pass.json", "outcome": "5 provider errors (Not logged in); no measurements"},
    "eval-pg7-2026-10-28T17:50:06": {"file": None, "outcome": "cited in the pre-Stage-3 log as 5/5; NO result file retained; unverifiable; not used"},
    "eval-XY0-2026-10-28T18:00:50": {"file": None, "outcome": "cited in the pre-Stage-3 log as 5/5; NO result file retained; unverifiable; not used"},
    "eval-0EY-2026-10-28T18:03:17": {"file": None, "outcome": "cited in the pre-Stage-3 log as 5/5; NO result file retained; unverifiable; not used"},
    "eval-vf9-2026-10-28T18:05:25": {"file": None, "outcome": "cited in the pre-Stage-3 log as 5/5; NO result file retained; unverifiable; not used"},
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def load(label: str) -> dict:
    return json.loads((RES / f"{label}.summary.json").read_text())


def block(s: dict, summary_file: Path) -> dict:
    return {
        "eval_id": s["eval_id"], "timestamp": s["timestamp"], "split": s["split"],
        "prompt_version": s["prompt_version"], "prompt_sha256": s["prompt_sha256"],
        "raw_result_file": s["raw_result_file"], "raw_result_sha256": s["raw_result_sha256"],
        "summary_file": rel(summary_file), "config_sha256": s["config_sha256"], "dataset_sha256": s["dataset_sha256"],
        "cases_attempted": s["cases_attempted"],
        "provider_errors": len(s["provider_errors"]), "grader_errors": len(s["grader_errors"]),
        "criteria": s["criteria"], "overall_quality": s["overall_quality"], "weighted_score": s["weighted_score"],
        "failed_cases": [{"case": f["case"], "failures": [{"metric": x["metric"], "score": x["score"]} for x in f["failures"]]}
                         for f in s["failed_cases"]],
        "provider_error_cases": [p["case"] for p in s["provider_errors"]],
    }


def frac(c):
    return "-" if not c else f"{c['passed']}/{c['scored']} ({100 * c['pass_rate']:.1f}%)"


def cell(c, mean=True):
    if not c:
        return "-"
    t = frac(c)
    return t + (f", mean {c['mean_score']:.2f}" if mean and c.get("mean_score") is not None else "")


def delta(a, b, mean):
    if not a or not b:
        return "-"
    if mean:
        return f"{b['mean_score'] - a['mean_score']:+.2f} mean; {100 * (b['pass_rate'] - a['pass_rate']):+.1f} pp"
    return f"{100 * (b['pass_rate'] - a['pass_rate']):+.1f} pp"


def case_passed(rec: dict):
    if "provider_error" in rec:
        return None
    vals = [v for k, v in rec.items() if not k.startswith("_") and not v["grader_error"] and not v["not_evaluable"]]
    return all(v["pass"] for v in vals)


def comparison_table(sums: dict, lb: dict) -> str:
    v1, v2, v3 = sums["v1"], sums["v2"], sums["v3"]
    cols = ["Metric", "v1", "v2", "v3", "v2 - v1", "v3 - v2", "v3 - v1"]
    rows = []

    def add(name, f, mean=False):
        cells = [f(s) for s in (v1, v2, v3)]
        cs = [s["criteria"].get(name) if name in FACETS + RUBRICS else None for s in (v1, v2, v3)]
        if name in FACETS + RUBRICS:
            d = [delta(cs[0], cs[1], mean), delta(cs[1], cs[2], mean), delta(cs[0], cs[2], mean)]
        else:
            d = ["", "", ""]
        rows.append([name] + cells + d)

    rows.append(["Development cases attempted"] + [str(s["cases_attempted"]) for s in (v1, v2, v3)] + ["", "", ""])
    add("structural_validity", lambda s: cell(s["criteria"]["structural_validity"], False))
    for m in ("schema_validity", "referential_integrity", "dependency_validity", "narrative_phase_correctness", "format_discipline"):
        c = [s["criteria"].get(m) for s in (v1, v2, v3)]
        rows.append([f"&nbsp;&nbsp;{m}" + (" (evaluable only)" if m in ("referential_integrity", "dependency_validity", "narrative_phase_correctness") else "")]
                    + [cell(x, False) + (f", {x['not_evaluable']} n/e" if x and x["not_evaluable"] else "") for x in c]
                    + [delta(c[0], c[1], False), delta(c[1], c[2], False), delta(c[0], c[2], False)])
    for m, label in (("causal_coherence", "Causal coherence (30%)"), ("character_consistency", "Character consistency (25%)"),
                     ("narrative_structure", "Narrative structure (20%)"), ("world_consistency", "World consistency (15%)"),
                     ("pacing", "Pacing (10%)")):
        c = [s["criteria"][m] for s in (v1, v2, v3)]
        rows.append([label] + [cell(x) for x in c] + [delta(c[0], c[1], True), delta(c[1], c[2], True), delta(c[0], c[2], True)])
    q = [s["overall_quality"] for s in (v1, v2, v3)]
    rows.append(["**Overall quality pass rate**"] + [f"{x['cases_passed']}/{x['cases_scored']} ({100 * x['pass_rate']:.1f}%)" for x in q]
                + [f"{100 * (q[1]['pass_rate'] - q[0]['pass_rate']):+.1f} pp", f"{100 * (q[2]['pass_rate'] - q[1]['pass_rate']):+.1f} pp",
                   f"{100 * (q[2]['pass_rate'] - q[0]['pass_rate']):+.1f} pp"])
    w = [s["weighted_score"]["mean"] for s in (v1, v2, v3)]
    rows.append(["Weighted rubric score (mean, weights 30/25/20/15/10)"] + [f"{x:.4f}" for x in w] + [f"{w[1] - w[0]:+.4f}", f"{w[2] - w[1]:+.4f}", f"{w[2] - w[0]:+.4f}"])
    rows.append(["Load-bearing coverage"] + [f"{lb[v]['load_bearing']}/{lb[v]['instructions']} ({lb[v]['load_bearing_pct']}%)" for v in ("v1", "v2", "v3")]
                + [f"{lb['v2']['load_bearing_pct'] - lb['v1']['load_bearing_pct']:+.1f} pp", f"{lb['v3']['load_bearing_pct'] - lb['v2']['load_bearing_pct']:+.1f} pp",
                   f"{lb['v3']['load_bearing_pct'] - lb['v1']['load_bearing_pct']:+.1f} pp"])
    rows.append(["Provider/grader errors"] + [f"{len(s['provider_errors'])} provider / {len(s['grader_errors'])} grader" for s in (v1, v2, v3)] + ["", "", ""])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] + ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def all_runs_table(labels: list[str]) -> str:
    sums = {l: load(l) for l in labels}
    head = ["criterion"] + labels
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for m in FACETS + RUBRICS:
        rows.append(f"| {m} | " + " | ".join(cell(s["criteria"].get(m)) for s in sums.values()) + " |")
    rows.append("| **overall quality pass** | " + " | ".join(
        f"{s['overall_quality']['cases_passed']}/{s['overall_quality']['cases_scored']} ({100 * s['overall_quality']['pass_rate']:.1f}%); strict {100 * s['overall_quality']['pass_rate_strict_of_attempted']:.1f}%"
        for s in sums.values()) + " |")
    rows.append("| weighted score mean | " + " | ".join(str(s["weighted_score"]["mean"]) for s in sums.values()) + " |")
    rows.append("| cases attempted | " + " | ".join(str(s["cases_attempted"]) for s in sums.values()) + " |")
    rows.append("| provider / grader errors | " + " | ".join(f"{len(s['provider_errors'])} / {len(s['grader_errors'])}" for s in sums.values()) + " |")
    return "\n".join(rows)


def main() -> None:
    frozen = json.loads((EV / "frozen_eval_config.json").read_text())
    versions, sums = {}, {}
    for v, label in DEV.items():
        prompt = EV / "prompts" / f"{v}.md"
        matrix = json.loads((EV / "matrices" / f"load_bearing_{v}.json").read_text())
        n = len(matrix["instructions"])
        lb = sum(i["load_bearing"] for i in matrix["instructions"])
        sums[v] = load(label)
        versions[v] = {
            "prompt_file": rel(prompt), "prompt_sha256": sha(prompt),
            "instructions": n, "load_bearing": lb, "load_bearing_pct": round(100 * lb / n, 1),
            "matrix_file": rel(EV / "matrices" / f"load_bearing_{v}.json"),
            "dev": block(sums[v], RES / f"{label}.summary.json"),
        }
    diffs = {k: {"file": rel(EV / "diffs" / f"{k}.diff"), "sha256": sha(EV / "diffs" / f"{k}.diff")} for k in ("v1_to_v2", "v2_to_v3")}
    extra, registry = {}, {}
    for label in EXTRA_RUNS:
        extra[label] = block(load(label), RES / f"{label}.summary.json")
    for label in list(DEV.values()) + EXTRA_RUNS:
        raw = RES / f"{label}.json"
        s = load(label)
        registry[s["eval_id"]] = {"label": label, "raw_result_file": rel(raw), "raw_result_sha256": sha(raw), "exists": raw.exists(),
                                  "prompt_version": s["prompt_version"], "split": s["split"],
                                  "role": {"v1_dev": "v1 baseline", "v2_dev": "v2 dev", "v3_dev": "v3 dev (designated)",
                                           "v1_dev_attempt1_recovered": "first run of unchanged v1 (recovered from Promptfoo DB)",
                                           "v3_dev_attempt1_recovered": "first run of unchanged v3 (recovered from Promptfoo DB)",
                                           "final_dev": "final dev re-run of v3", "final_holdout": "final holdout, run once"}[label]}
    legacy = {k: dict(v, exists=bool(v["file"] and (REPO / v["file"]).exists())) for k, v in LEGACY.items()}

    flips = {}
    for case in sums["v1"]["per_case"]:
        for m in RUBRICS:
            sc = [sums[v]["per_case"][case][m]["score"] for v in ("v1", "v2", "v3")]
            if len(set(sc)) > 1:
                flips[f"{case}/{m}"] = sc
    moves = {}
    for a, b in (("v1", "v2"), ("v2", "v3"), ("v1", "v3")):
        buckets = {"improved": [], "regressed": [], "unchanged_pass": [], "unchanged_fail": []}
        for case in sums[a]["per_case"]:
            pa, pb = case_passed(sums[a]["per_case"][case]), case_passed(sums[b]["per_case"][case])
            key = "unchanged_pass" if pa and pb else "unchanged_fail" if not pa and not pb else "improved" if pb else "regressed"
            buckets[key].append(case)
        moves[f"{a}_to_{b}"] = buckets
    table = comparison_table(sums, versions)
    (RES / "compare_v1_v2_v3_dev.md").write_text(table + "\n")
    (RES / "compare_all.md").write_text(all_runs_table(list(DEV.values()) + EXTRA_RUNS) + "\n")
    out = {
        "agent": "storyboard_building",
        "frozen_config_file": rel(EV / "frozen_eval_config.json"),
        "frozen_config_sha256": sha(EV / "frozen_eval_config.json"),
        "frozen_files": frozen["files"], "dataset_sha256": frozen["dataset_sha256"],
        "models": {"generation": "fusion-claude-sonnet-5-5-medium-sidekick-claude-haiku-5-5-medium", "grader": "swe-2-medium"},
        "rubric_weights": WEIGHTS,
        "versions": versions, "diffs": diffs,
        "additional_runs": extra,
        "evaluation_run_registry": registry,
        "pre_stage3_run_ids_cited_in_old_log": legacy,
        "case_level_moves_dev": moves,
        "per_case_rubric_score_changes_v1_v2_v3": flips,
        "comparison_table_file": rel(RES / "compare_v1_v2_v3_dev.md"),
        "comparison_table_markdown": table,
        "selected_prompt": "v3",
        "notes": "All numbers are copied from retained .summary.json files; v1/v2/v3 columns are the designated dev runs. "
                 "Per-case changes list [v1, v2, v3] rubric scores where they differ. Load-bearing coverage is an analytic mapping, not an ablation.",
    }
    (EV / "measurements.json").write_text(json.dumps(out, indent=2) + "\n")
    missing = [k for k, v in registry.items() if not v["exists"]]
    print(f"wrote {EV / 'measurements.json'}; missing referenced results: {missing or 'none'}")
    print(table)


if __name__ == "__main__":
    main()
