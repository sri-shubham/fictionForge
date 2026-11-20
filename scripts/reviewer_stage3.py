#!/usr/bin/env python3
"""Stage 3 evidence tooling for the adversarial reviewers (world / characters / storyboard).

    freeze   --agent A                      hash the frozen evaluation configuration + datasets
    verify   --agent A                      fail if anything frozen has changed
    run      --agent A VERSION SPLIT        run promptfoo (CALLS MODELS: run it yourself)
    summarize --agent A RAW.json            re-score a retained raw result and update measurements.json
    compare  --agent A SUMMARY.json ...     side-by-side metric table
    diff     --agent A V_FROM V_TO          write diffs/V_FROM_to_V_TO.diff
    coverage --agent A MATRIX.json          load-bearing instruction percentage + inventory checks
    offline-check --agent A                 validate everything that can be validated without a model

Only ``run`` can invoke a model (through promptfoo).  Every other command is offline and derives
its numbers from retained raw result files, the frozen fixtures and ``thresholds.json``.
Use the project venv: .venv/bin/python scripts/reviewer_stage3.py ...
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "evals" / "reviewers"))

from agent_gates import GATES as _CHAR_GATES  # noqa: E402
from storyboard_gates import GATES as _SB_GATES  # noqa: E402

GATES = {**_CHAR_GATES, **_SB_GATES}
from reviewer_scoring import DETERMINISTIC_CRITERIA, THRESHOLDS, load_fixture, score_case  # noqa: E402

EVAL_DIR = REPO / "evals" / "reviewers"
EVIDENCE_ROOT = REPO / "evidence" / "stage3" / "reviewers"
ALL_CRITERIA = list(THRESHOLDS["weights"])
GRADER_ERR = re.compile(r"could not extract json|timed out|timeout|execution failed|grading failed|error", re.I)
COMMON_FROZEN = [
    "evals/reviewers/reviewer_assert.py",
    "evals/reviewers/reviewer_scoring.py",
    "evals/reviewers/thresholds.json",
    "evals/world_stage3_provider.py",
    "evals/world_provider.py",
    "src/fictionforge/guardrails/reviewer_contract.py",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ev_dir(agent: str) -> Path:
    return EVIDENCE_ROOT / agent


AGENT_EXTRA_FROZEN = {
    "characters": ["evals/reviewers/agent_assert.py", "evals/reviewers/agent_gates.py",
                   "src/fictionforge/guardrails/reviewer_codes.py"],
    "storyboard": ["evals/reviewers/storyboard_assert.py", "evals/reviewers/storyboard_gates.py",
                   "evals/reviewers/agent_gates.py", "src/fictionforge/guardrails/storyboard_codes.py"],
}


def frozen_files(agent: str) -> list[str]:
    return ([f"evals/reviewers/{agent}.yaml", f"evals/reviewers/{agent}_tests.json"] + COMMON_FROZEN
            + AGENT_EXTRA_FROZEN.get(agent, []))


def dataset_hashes(agent: str) -> dict[str, str]:
    manifest = json.loads((EVAL_DIR / "fixtures" / agent / "manifest.json").read_text())
    out = {}
    for split in ("dev", "holdout"):
        lines = sorted(f"{c['path']}\t{sha(REPO / c['path'])}\t{c['expected_verdict']}" for c in manifest if c["split"] == split)
        out[split] = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return out


def current_freeze(agent: str) -> dict[str, Any]:
    return {"files": {f: sha(REPO / f) for f in frozen_files(agent)}, "dataset_sha256": dataset_hashes(agent)}


def cmd_freeze(a) -> int:
    path = ev_dir(a.agent) / "frozen_eval_config.json"
    if path.exists() and not a.force:
        print(f"{path} exists; refusing to re-freeze (use --force only before any measured run).")
        return 1
    data = current_freeze(a.agent)
    data["frozen_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Froze {len(data['files'])} files and both datasets; wrote {path}")
    return 0


def cmd_verify(a) -> int:
    path = ev_dir(a.agent) / "frozen_eval_config.json"
    if not path.exists():
        print("NOT FROZEN: run `freeze` first.")
        return 1
    frozen, now = json.loads(path.read_text()), current_freeze(a.agent)
    drift = [f for f in now["files"] if frozen["files"].get(f) != now["files"][f]]
    drift += [f"dataset:{s}" for s in now["dataset_sha256"] if frozen["dataset_sha256"].get(s) != now["dataset_sha256"][s]]
    if drift:
        print("EVAL CONFIGURATION DRIFT: " + ", ".join(drift))
        return 1
    print("Frozen evaluation configuration verified (no drift).")
    return 0


# ---------------------------------------------------------------------------
# Prompt versions
# ---------------------------------------------------------------------------


def prompt_path(agent: str, version: str) -> Path:
    return ev_dir(agent) / "prompts" / f"{version}.md"


def check_prompt_hash(agent: str, version: str, record: bool) -> int:
    """Prompt versions are immutable once evaluated: hash recorded on first run, verified afterwards."""
    p = prompt_path(agent, version)
    if not p.exists():
        print(f"Missing {p}")
        return 1
    hashes_file = ev_dir(agent) / "prompt_hashes.json"
    hashes = json.loads(hashes_file.read_text()) if hashes_file.exists() else {}
    h = sha(p)
    if version in hashes and hashes[version] != h:
        print(f"PROMPT CHANGED AFTER EVALUATION: {version} was {hashes[version][:12]}, is now {h[:12]}. "
              f"Create a new version instead of editing {p}.")
        return 1
    if record and version not in hashes:
        hashes[version] = h
        hashes_file.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    return 0


def promptfoo_version() -> str:
    try:
        out = subprocess.run(["promptfoo", "--version"], capture_output=True, text=True, timeout=60).stdout
        return next((l.strip() for l in out.splitlines() if re.fullmatch(r"\d+\.\d+\.\d+", l.strip())), "unknown")
    except Exception:
        return "unknown"


def result_name(version: str, split: str) -> str:
    return "final_holdout" if split == "holdout" else f"{version}_{split}"


def cmd_run(a) -> int:
    if cmd_verify(a) != 0 or check_prompt_hash(a.agent, a.version, record=not a.dry_run) != 0:
        return 1
    raw = ev_dir(a.agent) / "results" / f"{a.label or result_name(a.version, a.split)}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    if raw.exists():
        print(f"{raw} already exists; results are never overwritten.")
        return 1
    cmd = ["promptfoo", "eval", "-c", str(EVAL_DIR / f"{a.agent}.yaml"), "--prompts", str(prompt_path(a.agent, a.version)),
           "--filter-metadata", f"split={a.split}", "--no-cache", "--no-share", "--no-progress-bar",
           "-j", str(a.jobs), "--description", raw.stem, "-o", str(raw)]
    env = dict(os.environ, PROMPTFOO_DISABLE_TELEMETRY="1")
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.exists():
        env["PROMPTFOO_PYTHON"] = str(venv_py)
    if a.dry_run:
        print("DRY RUN (no model is called). Command that would run:\n" + " ".join(cmd))
        return 0
    print("Running:", " ".join(cmd), flush=True)
    rc = subprocess.run(cmd, cwd=REPO, env=env).returncode
    if not raw.exists():
        print(f"promptfoo exited {rc} without writing {raw}")
        return 1
    summarize(a.agent, raw, a.version, a.split)
    return 0


# ---------------------------------------------------------------------------
# Summarising (offline; derived from the raw result + fixtures)
# ---------------------------------------------------------------------------


def _provider_error(r: dict[str, Any]) -> str | None:
    resp = r.get("response") or {}
    err = resp.get("error") or (r.get("error") if r.get("failureReason") == 2 else None)
    return str(err)[:500] if err else None


def _raw_reply(r: dict[str, Any]) -> Any:
    resp = r.get("response") or {}
    return ((resp.get("metadata") or {}).get("raw_output")) or resp.get("output")


def summarize_results(agent: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure function: promptfoo result rows -> metrics (used by tests with synthetic rows)."""
    suite = THRESHOLDS["suite"]
    per_case: dict[str, Any] = {}
    provider_errors, grader_errors = [], []
    crit = {c: {"applicable": 0, "passed": 0, "score_sum": 0.0} for c in ALL_CRITERIA}
    cat_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"cases": 0, "passed": 0})
    confusion: dict[str, Counter] = defaultdict(Counter)
    m = Counter()
    weighted_scores, mismatches = [], []

    for r in results:
        meta = (r.get("testCase") or {}).get("metadata") or {}
        case = meta.get("case") or (r.get("testCase") or {}).get("description")
        perr = _provider_error(r)
        if perr:
            provider_errors.append({"case": case, "error": perr})
            continue
        fixture = load_fixture(r["testCase"]["vars"]["CASE_FILE"])
        sc = score_case(fixture, _raw_reply(r))
        comps = {(c.get("assertion") or {}).get("metric"): c for c in ((r.get("gradingResult") or {}).get("componentResults") or [])}
        rubric = comps.get("actionable_feedback")
        has_blocking = any(l["blocking"] for l in fixture["labels"])
        rub_info, grader_error = None, False
        if has_blocking:
            if rubric is None:
                grader_error = True
                grader_errors.append({"case": case, "metric": "actionable_feedback", "reason": "assertion result missing"})
            else:
                score, reason = rubric.get("score"), rubric.get("reason") or ""
                if not rubric.get("pass") and ((score is not None and score < 1) or GRADER_ERR.search(reason)) and (score or 0) < 1:
                    grader_error = True
                    grader_errors.append({"case": case, "metric": "actionable_feedback", "reason": reason[:300]})
                else:
                    rub_info = {"pass": bool(rubric.get("pass")), "score": score, "reason": reason}
        # sanity: promptfoo's own deterministic component results must agree with the re-score
        for name in DETERMINISTIC_CRITERIA:
            c = comps.get(name)
            if c is not None and bool(c.get("pass")) != bool(sc["criteria"][name]["pass"]):
                mismatches.append({"case": case, "metric": name})

        applicable = {n: sc["criteria"][n] for n in DETERMINISTIC_CRITERIA if sc["criteria"][n]["applicable"]}
        failed = [n for n, c in applicable.items() if not c["pass"]]
        gate_results = {}
        for gname, gfn in GATES.get(fixture.get("agent", agent), {}).items():
            g = gfn(fixture, _raw_reply(r))
            gate_results[gname] = g
            gc = comps.get(gname)
            if gc is not None and bool(gc.get("pass")) != bool(g["pass"]):
                mismatches.append({"case": case, "metric": gname})
            m[f"gate_{gname}_applicable"] += int(g["applicable"])
            m[f"gate_{gname}_passed"] += int(g["applicable"] and g["pass"])
            if not g["pass"]:
                failed.append(gname)
        if not sc["contract_valid"]:
            failed = ["contract_validity"] + failed
        if rub_info is not None and not rub_info["pass"]:
            failed.append("actionable_feedback")
        passed = not failed and not grader_error

        for n, c in applicable.items():
            crit[n]["applicable"] += 1
            crit[n]["passed"] += int(c["pass"])
            crit[n]["score_sum"] += c["score"]
        w_num = w_den = 0.0
        for n, c in applicable.items():
            w = THRESHOLDS["weights"][n]
            w_num += w * c["score"]
            w_den += w
        if rub_info is not None:
            crit["actionable_feedback"]["applicable"] += 1
            crit["actionable_feedback"]["passed"] += int(rub_info["pass"])
            crit["actionable_feedback"]["score_sum"] += (rub_info["score"] or 0) / 5.0
            w_num += THRESHOLDS["weights"]["actionable_feedback"] * (rub_info["score"] or 0) / 5.0
            w_den += THRESHOLDS["weights"]["actionable_feedback"]
        weighted = w_num / w_den if w_den else 0.0
        if not grader_error:
            weighted_scores.append(weighted)

        expected = fixture["expected_verdict"]
        confusion[expected][sc["verdict"] or "INVALID"] += 1
        m["cases"] += 1
        m["contract_valid"] += int(sc["contract_valid"])
        m["verdict_correct"] += int(sc["verdict_correct"])
        if expected == "PASS":
            m["pass_cases"] += 1
            m["pass_cases_blocked"] += int(not applicable["false_positive_avoidance"]["pass"] or sc["verdict"] != "PASS")
        else:
            m["nonpass_cases"] += 1
            m["nonpass_cases_missed"] += int(sc["verdict"] == "PASS")
        for lo in sc["labels"]:
            if lo["blocking"]:
                m["blocking_labels"] += 1
                m["blocking_detected"] += int(lo["detected"])
                if lo["severity"] == "critical":
                    m["critical_labels"] += 1
                    m["critical_detected"] += int(lo["detected"])
        for io in sc["issues"]:
            m["issues"] += 1
            m["issues_grounded"] += int(io["grounded"])
            if io["blocking"]:
                m["blocking_reported"] += 1
                m["blocking_supported"] += int(io["category"] == "supported")
        cat = meta.get("category") or fixture["category"]
        cat_stats[cat]["cases"] += 1
        cat_stats[cat]["passed"] += int(passed)
        per_case[case] = {
            "category": cat, "expected_verdict": expected, "verdict": sc["verdict"], "case_pass": passed,
            "grader_error": grader_error, "failed_criteria": failed, "weighted_score": round(weighted, 4),
            "criteria": {n: {"pass": c["pass"], "score": c["score"], "reason": c["reason"]} for n, c in applicable.items()},
            "actionable_feedback": rub_info, "gates": gate_results,
            "missed_labels": [lo["label_id"] for lo in sc["labels"] if lo["blocking"] and not lo["detected"]],
            "misclassified_labels": [lo["label_id"] for lo in sc["labels"] if lo["blocking"] and lo["detected"] and not lo["classification_ok"]],
            "unsupported_blocking_issues": [
                {"index": io["index"], "code": io["code"], "severity": io["severity"], "artifact_path": io["artifact_path"],
                 "category": io["category"], "matched_traps": io["matched_traps"]}
                for io in sc["issues"] if io["blocking"] and io["category"].startswith("false_positive")],
            "ungrounded_issues": [{"index": io["index"], "reasons": io["grounding_reasons"]} for io in sc["issues"] if not io["grounded"]],
            "unknown_codes": sc.get("unknown_codes", []), "contract_error": sc["contract_error"],
        }

    def rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    cases_total = len(results)
    n_passed = sum(1 for c in per_case.values() if c["case_pass"])
    metrics = {
        "critical_detection_rate": rate(m["critical_detected"], m["critical_labels"]),
        "blocking_recall": rate(m["blocking_detected"], m["blocking_labels"]),
        "blocking_precision": rate(m["blocking_supported"], m["blocking_reported"]),
        "false_positive_rate": rate(m["pass_cases_blocked"], m["pass_cases"]),
        "false_negative_rate": rate(m["nonpass_cases_missed"], m["nonpass_cases"]),
        "verdict_accuracy": rate(m["verdict_correct"], m["cases"]),
        "evidence_grounding_rate": rate(m["issues_grounded"], m["issues"]),
        "contract_validity_rate": rate(m["contract_valid"], cases_total),
        "weighted_score": round(sum(weighted_scores) / len(weighted_scores), 4) if weighted_scores else None,
        "case_pass_rate": rate(n_passed, cases_total),
    }
    comparators = {
        "case_pass_rate": ("min", suite["case_pass_rate_min"]), "critical_detection_rate": ("min", suite["critical_detection_rate_min"]),
        "false_positive_rate": ("max", suite["false_positive_rate_max"]), "blocking_precision": ("min", suite["blocking_precision_min"]),
        "blocking_recall": ("min", suite["blocking_recall_min"]), "verdict_accuracy": ("min", suite["verdict_accuracy_min"]),
        "evidence_grounding_rate": ("min", suite["evidence_grounding_rate_min"]), "weighted_score": ("min", suite["weighted_score_min"]),
        "contract_validity_rate": ("min", suite["contract_validity_rate_min"]),
    }
    threshold_report = {}
    for k, (kind, limit) in comparators.items():
        v = metrics[k]
        ok = v is not None and (v >= limit if kind == "min" else v <= limit)
        threshold_report[k] = {"value": v, "threshold": limit, "kind": kind, "met": ok, "hard_gate": k in THRESHOLDS["hard_gates"]}
    criteria = {n: {"applicable_cases": s["applicable"], "passed": s["passed"], "pass_rate": rate(s["passed"], s["applicable"]),
                    "mean_score": round(s["score_sum"] / s["applicable"], 4) if s["applicable"] else None}
                for n, s in crit.items() if s["applicable"]}
    valid_run = not provider_errors and not grader_errors
    return {
        "cases_total": cases_total, "cases_passed": n_passed, "provider_errors": provider_errors, "grader_errors": grader_errors,
        "valid_run": valid_run, "assertion_mismatches": mismatches,
        "metrics": metrics, "criteria": criteria, "thresholds": threshold_report,
        "hard_gates_failed": [k for k, t in threshold_report.items() if t["hard_gate"] and not t["met"]],
        "meets_all_thresholds": valid_run and all(t["met"] for t in threshold_report.values()),
        "counts": dict(m), "verdict_confusion": {k: dict(v) for k, v in confusion.items()},
        "by_category": {k: {**v, "pass_rate": rate(v["passed"], v["cases"])} for k, v in sorted(cat_stats.items())},
        "failed_cases": {k: v for k, v in per_case.items() if not v["case_pass"]}, "per_case": per_case,
    }


def summarize(agent: str, raw_path: Path, version: str | None = None, split: str | None = None) -> dict[str, Any]:
    raw_path = raw_path.resolve()
    doc = json.loads(raw_path.read_text())
    rows = doc["results"]["results"]
    splits = sorted({((r.get("testCase") or {}).get("metadata") or {}).get("split") for r in rows} - {None})
    version = version or (re.match(r"(v\d+)_", raw_path.name) or [None, None])[1]
    pfile = prompt_path(agent, version) if version else None
    body = summarize_results(agent, rows)
    summary = {
        "agent": agent, "label": raw_path.stem, "prompt_version": version,
        "prompt_path": str(pfile.relative_to(REPO)) if pfile and pfile.exists() else None,
        "prompt_sha256": sha(pfile) if pfile and pfile.exists() else None,
        "split": splits, "raw_result_file": str(raw_path.relative_to(REPO)), "raw_result_sha256": sha(raw_path),
        "eval_id": doc.get("evalId"), "timestamp": (doc.get("results") or {}).get("timestamp"),
        "promptfoo_version": promptfoo_version(),
        "config_sha256": sha(EVAL_DIR / f"{agent}.yaml"), "dataset_sha256": dataset_hashes(agent),
        "summarizer_sha256": sha(Path(__file__)), "scoring_sha256": sha(EVAL_DIR / "reviewer_scoring.py"),
        "thresholds_sha256": sha(EVAL_DIR / "thresholds.json"),
        "models": (doc.get("config") or {}).get("providers"), **body,
    }
    out = raw_path.with_suffix(".summary.json")
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(render_summary(summary))
    print(f"\nWrote {out}")
    update_measurements(agent, summary)
    return summary


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render_summary(s: dict[str, Any]) -> str:
    lines = [f"## {s['label']}  (prompt {s['prompt_version']}, sha256 {str(s['prompt_sha256'])[:12]})",
             f"- cases: {s['cases_total']}, passed: {s['cases_passed']}, provider errors: {len(s['provider_errors'])}, grader errors: {len(s['grader_errors'])}, valid run: {s['valid_run']}",
             "", "| metric | value | threshold | met |", "|---|---|---|---|"]
    for k, t in s["thresholds"].items():
        op = ">=" if t["kind"] == "min" else "<="
        lines.append(f"| {k}{' (HARD GATE)' if t['hard_gate'] else ''} | {pct(t['value'])} | {op} {pct(t['threshold'])} | {'yes' if t['met'] else 'NO'} |")
    lines += ["", "| criterion | applicable | pass rate | mean score |", "|---|---|---|---|"]
    for n, c in s["criteria"].items():
        lines.append(f"| {n} | {c['applicable_cases']} | {pct(c['pass_rate'])} | {c['mean_score']} |")
    lines += ["", f"- meets all thresholds: {s['meets_all_thresholds']}; hard gates failed: {s['hard_gates_failed'] or 'none'}"]
    if s["failed_cases"]:
        lines.append("- failed cases: " + ", ".join(f"{k} ({'/'.join(v['failed_criteria'])})" for k, v in s["failed_cases"].items()))
    return "\n".join(lines)


def update_measurements(agent: str, summary: dict[str, Any]) -> None:
    path = ev_dir(agent) / "measurements.json"
    data = json.loads(path.read_text()) if path.exists() else {"agent": agent, "runs": {}}
    key = summary["label"]
    data["runs"][key] = {
        "status": "RUN" if summary["valid_run"] else "RUN_INVALID",
        "prompt_version": summary["prompt_version"], "prompt_sha256": summary["prompt_sha256"],
        "raw_result_file": summary["raw_result_file"], "raw_result_sha256": summary["raw_result_sha256"],
        "summary_file": str(Path(summary["raw_result_file"]).with_suffix(".summary.json")),
        "eval_id": summary["eval_id"], "timestamp": summary["timestamp"],
        "cases_total": summary["cases_total"], "cases_passed": summary["cases_passed"],
        "metrics": summary["metrics"], "criteria": summary["criteria"],
        "meets_all_thresholds": summary["meets_all_thresholds"], "hard_gates_failed": summary["hard_gates_failed"],
        "provider_errors": len(summary["provider_errors"]), "grader_errors": len(summary["grader_errors"]),
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


def cmd_compare(a) -> int:
    sums = [json.loads(Path(p).read_text()) for p in a.summaries]
    metric_keys = ["case_pass_rate", "critical_detection_rate", "blocking_recall", "blocking_precision", "false_positive_rate",
                   "false_negative_rate", "verdict_accuracy", "evidence_grounding_rate", "contract_validity_rate", "weighted_score"]
    print("| metric | " + " | ".join(f"{s['label']} ({s['prompt_version']})" for s in sums) + " |")
    print("|---|" + "---|" * len(sums))
    for k in metric_keys:
        print(f"| {k} | " + " | ".join(pct(s["metrics"].get(k)) for s in sums) + " |")
    for n in ALL_CRITERIA:
        print(f"| criterion pass: {n} | " + " | ".join(pct((s['criteria'].get(n) or {}).get('pass_rate')) for s in sums) + " |")
    return 0


def cmd_diff(a) -> int:
    p1, p2 = prompt_path(a.agent, a.v_from), prompt_path(a.agent, a.v_to)
    out = ev_dir(a.agent) / "diffs" / f"{a.v_from}_to_{a.v_to}.diff"
    out.parent.mkdir(parents=True, exist_ok=True)
    diff = "".join(difflib.unified_diff(p1.read_text().splitlines(True), p2.read_text().splitlines(True),
                                        f"{a.v_from}.md", f"{a.v_to}.md"))
    out.write_text(diff)
    print(f"wrote {out} ({len(diff.splitlines())} lines)")
    return 0


# ---------------------------------------------------------------------------
# Load-bearing coverage
# ---------------------------------------------------------------------------


def instruction_lines(prompt: str) -> list[str]:
    """Instruction-bearing lines: skips headers, blanks, placeholders and the JSON template block."""
    out, in_template = [], False
    for raw in prompt.splitlines():
        line = raw.strip()
        if in_template:
            in_template = raw.rstrip() != "}"
            continue
        if raw.rstrip() == "{":
            in_template = True
            continue
        if not line or line.startswith("#") or line in ("{{CONTEXT_BLOCK}}", "{{ARTIFACT_BLOCK}}"):
            continue
        out.append(line)
    return out


def coverage(agent: str, matrix: dict[str, Any]) -> dict[str, Any]:
    prompt = (REPO / matrix["prompt_path"]).read_text()
    manifest = {c["case_id"] for c in json.loads((EVAL_DIR / "fixtures" / agent / "manifest.json").read_text())}
    problems, rows = [], []
    for ins in matrix["instructions"]:
        probs = []
        if ins["excerpt"] not in prompt:
            probs.append("excerpt not found verbatim in prompt")
        known = ALL_CRITERIA + ["contract_validity"] + [g for gs in GATES.values() for g in gs]
        bad_crit = [c for c in ins["criteria"] if c not in known]
        if bad_crit:
            probs.append(f"unknown criteria {bad_crit}")
        missing = [w for w in ins["witness_cases"] if w not in manifest]
        if missing:
            probs.append(f"unknown witness cases {missing}")
        lb = bool(ins["criteria"]) and bool(ins["witness_cases"]) and not probs and ins["load_bearing"]
        if ins["load_bearing"] and probs:
            problems.append(f"{ins['id']}: claimed load-bearing but {probs}")
        rows.append({**ins, "verified_load_bearing": lb})
    uncovered = [l for l in instruction_lines(prompt) if not any(i["excerpt"] in l for i in matrix["instructions"])]
    template_ok = any('"verdict": "PASS" | "REVISE" | "PUNCH_OUT"' in i["excerpt"] for i in matrix["instructions"])
    n_lb = sum(r["verified_load_bearing"] for r in rows)
    return {
        "prompt_sha256": sha(REPO / matrix["prompt_path"]), "matrix_prompt_sha256": matrix["prompt_sha256"],
        "hash_matches": sha(REPO / matrix["prompt_path"]) == matrix["prompt_sha256"],
        "instructions": len(rows), "load_bearing": n_lb,
        "percentage": round(100 * n_lb / len(rows), 1) if rows else 0.0,
        "uncovered_instruction_lines": uncovered, "template_inventoried": template_ok, "problems": problems,
        "meets_90_percent": bool(rows) and 100 * n_lb / len(rows) >= 90 and not uncovered and template_ok and not problems,
    }


def cmd_coverage(a) -> int:
    matrix = json.loads(Path(a.matrix).read_text())
    res = coverage(a.agent, matrix)
    print(json.dumps({k: v for k, v in res.items()}, indent=2))
    return 0 if res["meets_90_percent"] and res["hash_matches"] else 1


def cmd_offline_check(a) -> int:
    rc = 0
    rc |= cmd_verify(a) if (ev_dir(a.agent) / "frozen_eval_config.json").exists() else 0
    for v in ("v1", "v2", "v3"):
        if prompt_path(a.agent, v).exists():
            rc |= check_prompt_hash(a.agent, v, record=False)
    for m in sorted((ev_dir(a.agent) / "matrices").glob("load_bearing_*.json")):
        res = coverage(a.agent, json.loads(m.read_text()))
        print(f"{m.name}: {res['load_bearing']}/{res['instructions']} = {res['percentage']}% (hash ok: {res['hash_matches']}, uncovered lines: {len(res['uncovered_instruction_lines'])})")
        rc |= 0 if res["meets_90_percent"] else 1
    mfile = ev_dir(a.agent) / "measurements.json"
    if mfile.exists():
        for k, run in json.loads(mfile.read_text()).get("runs", {}).items():
            if str(run.get("status", "")).startswith("RUN"):
                f = REPO / run["raw_result_file"]
                ok = f.exists() and sha(f) == run["raw_result_sha256"]
                print(f"{k}: raw result {'present, hash ok' if ok else 'MISSING OR CHANGED'}")
                rc |= 0 if ok else 1
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("freeze", "verify", "offline-check"):
        sp = sub.add_parser(name)
        sp.add_argument("--agent", required=True)
        if name == "freeze":
            sp.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--agent", required=True)
    r.add_argument("version")
    r.add_argument("split", choices=["dev", "holdout"])
    r.add_argument("--jobs", type=int, default=2)
    r.add_argument("--label", help="result file stem, e.g. v3_dev_repeat1 (default: <version>_<split>, or final_holdout)")
    r.add_argument("--dry-run", action="store_true", help="print the promptfoo command without running it")
    s = sub.add_parser("summarize")
    s.add_argument("--agent", required=True)
    s.add_argument("raw")
    c = sub.add_parser("compare")
    c.add_argument("--agent", required=True)
    c.add_argument("summaries", nargs="+")
    d = sub.add_parser("diff")
    d.add_argument("--agent", required=True)
    d.add_argument("v_from")
    d.add_argument("v_to")
    cv = sub.add_parser("coverage")
    cv.add_argument("--agent", required=True)
    cv.add_argument("matrix")
    a = p.parse_args()
    return {"freeze": cmd_freeze, "verify": cmd_verify, "run": cmd_run, "compare": cmd_compare, "diff": cmd_diff,
            "coverage": cmd_coverage, "offline-check": cmd_offline_check,
            "summarize": lambda x: (summarize(x.agent, Path(x.raw)), 0)[1]}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
