#!/usr/bin/env python3
"""Stage 3 evidence tooling for the World Generation agent.

    freeze                       hash the evaluation configuration + datasets
    verify                       fail if anything frozen has changed
    run VERSION SPLIT            run the frozen eval for evidence/stage3/world/prompts/VERSION.md
    summarize RAW.json           per-criterion summary of a raw Promptfoo result
    compare SUMMARY.json ...     side-by-side per-criterion table
    coverage MATRIX.json         load-bearing instruction percentage

Use the project venv: .venv/bin/python scripts/world_stage3.py ...
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EV = REPO / "evidence" / "stage3" / "world"
FROZEN = EV / "frozen_eval_config.json"
CONFIG = REPO / "evals" / "world_stage3.yaml"
FIXTURES = REPO / "evals" / "fixtures" / "world"
FROZEN_FILES = [
    "evals/world_stage3.yaml",
    "evals/world_stage3_tests.json",
    "evals/world_assert.py",
    "evals/world_stage3_assert.py",
    "evals/world_stage3_provider.py",
    "evals/world_provider.py",
    "src/fictionforge/guardrails/validators.py",
    "src/fictionforge/models.py",
    "schemas/world.schema.json",
]
RUBRIC_METRICS = {"internal_consistency", "premise_genre_alignment", "worldbuilding_depth",
                  "narrative_potential", "originality", "contradiction_handling"}
DET_METRICS = {"structural_validity", "format_discipline", "injection_resistance"}
ALL_METRICS = sorted(RUBRIC_METRICS | DET_METRICS)
GRADER_ERR = re.compile(r"could not extract json|timed out|timeout|execution failed|grading failed|error", re.I)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dataset_hashes() -> dict[str, str]:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    out = {}
    for split in ("dev", "holdout"):
        lines = sorted(f"{c['path']}\t{sha(REPO / c['path'])}\t{c['expected']}" for c in manifest if c["split"] == split)
        out[split] = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return out


def current_freeze() -> dict:
    return {"files": {f: sha(REPO / f) for f in FROZEN_FILES}, "dataset_sha256": dataset_hashes()}


def cmd_freeze(a) -> int:
    if FROZEN.exists() and not a.force:
        print(f"{FROZEN} exists; refusing to re-freeze (use --force only before any measured run).")
        return 1
    data = current_freeze()
    data["frozen_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data["config_sha256"] = data["files"]["evals/world_stage3.yaml"]
    FROZEN.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Froze {len(FROZEN_FILES)} files; wrote {FROZEN}")
    return 0


def cmd_verify(_a=None) -> int:
    if not FROZEN.exists():
        print("NOT FROZEN: run `freeze` first.")
        return 1
    frozen, now = json.loads(FROZEN.read_text()), current_freeze()
    drift = [f for f in FROZEN_FILES if frozen["files"].get(f) != now["files"][f]]
    drift += [f"dataset:{s}" for s in now["dataset_sha256"] if frozen["dataset_sha256"].get(s) != now["dataset_sha256"][s]]
    if drift:
        print("EVAL CONFIGURATION DRIFT: " + ", ".join(drift))
        return 1
    print("Frozen evaluation configuration verified (no drift).")
    return 0


def promptfoo_version() -> str:
    try:
        out = subprocess.run(["promptfoo", "--version"], capture_output=True, text=True, timeout=60).stdout
        return next((l.strip() for l in out.splitlines() if re.fullmatch(r"\d+\.\d+\.\d+", l.strip())), "unknown")
    except Exception:
        return "unknown"


def cmd_run(a) -> int:
    prompt = EV / "prompts" / f"{a.version}.md"
    if not prompt.exists():
        print(f"Missing {prompt}")
        return 1
    if not a.calibration and cmd_verify() != 0:
        return 1
    out_dir = EV / ("calibration" if a.calibration else "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    label = a.label or f"{a.version}_{a.split}"
    raw = out_dir / f"{label}.json"
    if raw.exists():
        print(f"{raw} already exists; results are never overwritten (pass --label to use another name).")
        return 1
    cmd = ["promptfoo", "eval", "-c", str(CONFIG), "--prompts", str(prompt),
           "--filter-metadata", f"split={a.split}", "--no-cache", "--no-share", "--no-progress-bar",
           "-j", str(a.jobs), "--description", label, "-o", str(raw)]
    if a.cases:
        cmd += ["--filter-pattern", a.cases]
    env = dict(os.environ, PROMPTFOO_DISABLE_TELEMETRY="1")
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.exists():
        env["PROMPTFOO_PYTHON"] = str(venv_py)
    print("Running:", " ".join(cmd), flush=True)
    rc = subprocess.run(cmd, cwd=REPO, env=env).returncode
    if not raw.exists():
        print(f"promptfoo exited {rc} without writing {raw}")
        return 1
    summarize(raw, a.version, a.split, calibration=a.calibration)
    return 0


def _component_key(c: dict) -> str | None:
    return (c.get("assertion") or {}).get("metric")


def summarize(raw_path: Path, version: str | None = None, split: str | None = None, calibration: bool = False) -> dict:
    raw_path = raw_path.resolve()
    doc = json.loads(raw_path.read_text())
    res = doc["results"]["results"]
    version = version or (re.search(r"(?:^|_)(v\d+)_", raw_path.name) or [None, None])[1]
    prompt_path = EV / "prompts" / f"{version}.md"
    cfg = None
    try:
        import yaml
        cfg = yaml.safe_load(CONFIG.read_text())
    except Exception:
        pass
    models = {}
    if cfg:
        models = {"generation": cfg["providers"][0]["config"], "grader": cfg["defaultTest"]["options"]["provider"]["config"]}
    per_case, provider_errors, grader_errors, failed = {}, [], [], []
    stats = {m: {"scored": 0, "passed": 0, "score_sum": 0.0, "n_scores": 0} for m in ALL_METRICS}
    structural_cases = {"pass": 0, "total": 0}
    quality_scored = quality_passed = 0
    split_seen = set()
    for r in res:
        meta = (r.get("testCase") or {}).get("metadata") or {}
        case = meta.get("case") or (r.get("testCase") or {}).get("description")
        split_seen.add(meta.get("split"))
        perr = (r.get("response") or {}).get("error") or (r.get("error") if r.get("failureReason") == 2 else None)
        if perr:
            provider_errors.append({"case": case, "error": str(perr)[:500]})
            continue
        comps = (r.get("gradingResult") or {}).get("componentResults") or []
        rec, bad, gerr = {}, [], False
        for c in comps:
            m = _component_key(c)
            if m not in stats:
                continue
            score, reason = c.get("score"), c.get("reason") or ""
            is_grader_err = (m in RUBRIC_METRICS and (not c.get("pass")) and (
                (score is not None and score < 1) or GRADER_ERR.search(reason) is not None and (score or 0) < 1))
            if m in DET_METRICS and "execution failed" in reason.lower():
                is_grader_err = True
            rec[m] = {"pass": bool(c.get("pass")), "score": score, "reason": reason, "grader_error": is_grader_err}
            if is_grader_err:
                grader_errors.append({"case": case, "metric": m, "reason": reason[:300]})
                gerr = True
                continue
            s = stats[m]
            s["scored"] += 1
            s["passed"] += int(bool(c.get("pass")))
            if m in RUBRIC_METRICS and score is not None:
                s["score_sum"] += score
                s["n_scores"] += 1
            if not c.get("pass"):
                bad.append({"metric": m, "score": score, "reason": reason})
            if m == "structural_validity":
                structural_cases["total"] += 1
                structural_cases["pass"] += int(bool(c.get("pass")))
        per_case[case] = rec
        if gerr and not bad:
            continue
        quality_scored += 1
        if not bad:
            quality_passed += 1
        else:
            failed.append({"case": case, "failures": bad})
    criteria = {}
    for m, s in stats.items():
        if s["scored"]:
            criteria[m] = {"scored": s["scored"], "passed": s["passed"], "pass_rate": round(s["passed"] / s["scored"], 4),
                           "mean_score": round(s["score_sum"] / s["n_scores"], 3) if s["n_scores"] else None}
    h = dataset_hashes()
    summary = {
        "label": raw_path.stem, "calibration_only": calibration, "prompt_version": version,
        "prompt_path": str(prompt_path.relative_to(REPO)) if prompt_path.exists() else None,
        "prompt_sha256": sha(prompt_path) if prompt_path.exists() else None,
        "split": sorted(x for x in split_seen if x), "raw_result_file": str(raw_path.relative_to(REPO)),
        "raw_result_sha256": sha(raw_path), "eval_id": doc.get("evalId"),
        "timestamp": (doc.get("results") or {}).get("timestamp"),
        "promptfoo_version": promptfoo_version(),
        "config_sha256": sha(CONFIG), "dataset_sha256": h,
        "summarizer_sha256": sha(Path(__file__)), "models": models,
        "cases_total": len(res), "provider_errors": provider_errors, "grader_errors": grader_errors,
        "structural_validity": {**structural_cases, "pass_rate": round(structural_cases["pass"] / structural_cases["total"], 4) if structural_cases["total"] else None},
        "criteria": criteria,
        "overall_quality": {"cases_scored": quality_scored, "cases_passed": quality_passed,
                            "pass_rate": round(quality_passed / quality_scored, 4) if quality_scored else None},
        "failed_cases": failed, "per_case": per_case,
    }
    out = raw_path.with_suffix(".summary.json")
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(render_summary(summary))
    print(f"\nWrote {out}")
    return summary


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render_summary(s: dict) -> str:
    lines = [f"## {s['label']}  (prompt {s['prompt_version']}, sha256 {str(s['prompt_sha256'])[:12]})",
             f"- cases: {s['cases_total']}, provider errors: {len(s['provider_errors'])}, grader errors: {len(s['grader_errors'])}",
             f"- overall quality pass rate: {s['overall_quality']['cases_passed']}/{s['overall_quality']['cases_scored']} = {pct(s['overall_quality']['pass_rate'])}",
             "", "| criterion | passed/scored | pass rate | mean score |", "|---|---|---|---|"]
    for m, c in s["criteria"].items():
        lines.append(f"| {m} | {c['passed']}/{c['scored']} | {pct(c['pass_rate'])} | {c['mean_score'] if c['mean_score'] is not None else '-'} |")
    if s["failed_cases"]:
        lines += ["", "Failed cases: " + ", ".join(f["case"] for f in s["failed_cases"])]
    return "\n".join(lines)


def cmd_compare(a) -> int:
    sums = [json.loads(Path(p).read_text()) for p in a.summaries]
    head = ["criterion"] + [f"{s['prompt_version']}:{'/'.join(s['split'])}" for s in sums]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    metrics = [m for m in ALL_METRICS if any(m in s["criteria"] for s in sums)]
    for m in metrics:
        cells = []
        for s in sums:
            c = s["criteria"].get(m)
            cells.append("-" if not c else f"{c['passed']}/{c['scored']} ({pct(c['pass_rate'])}), mean {c['mean_score'] if c['mean_score'] is not None else '-'}")
        rows.append(f"| {m} | " + " | ".join(cells) + " |")
    rows.append("| **overall quality pass** | " + " | ".join(
        f"{s['overall_quality']['cases_passed']}/{s['overall_quality']['cases_scored']} ({pct(s['overall_quality']['pass_rate'])})" for s in sums) + " |")
    rows.append("| provider errors | " + " | ".join(str(len(s["provider_errors"])) for s in sums) + " |")
    rows.append("| grader errors | " + " | ".join(str(len(s["grader_errors"])) for s in sums) + " |")
    text = "\n".join(rows)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")
    return 0


def cmd_combine(a) -> int:
    sums = [json.loads(Path(p).read_text()) for p in a.summaries]
    per_case, perr, gerr = {}, [], []
    for s in sums:
        tag = "+".join(s["split"])
        for c, rec in s["per_case"].items():
            assert f"{tag}/{c}" not in per_case, f"duplicate case {tag}/{c}"
            per_case[f"{tag}/{c}"] = rec
        perr += s["provider_errors"]
        gerr += s["grader_errors"]
    crit, failed, scored, passed = {}, [], 0, 0
    for case, rec in per_case.items():
        bad = [(m, v) for m, v in rec.items() if not v["grader_error"] and not v["pass"]]
        scored += 1
        passed += int(not bad)
        if bad:
            failed.append({"case": case, "failures": [{"metric": m, "score": v["score"], "reason": v["reason"]} for m, v in bad]})
        for m, v in rec.items():
            if v["grader_error"]:
                continue
            c = crit.setdefault(m, {"scored": 0, "passed": 0, "sum": 0.0, "n": 0})
            c["scored"] += 1
            c["passed"] += int(v["pass"])
            if m in RUBRIC_METRICS and v["score"] is not None:
                c["sum"] += v["score"]
                c["n"] += 1
    out = {"combined_from": [str(Path(p)) for p in a.summaries], "inputs_sha256": {p: sha(Path(p)) for p in a.summaries},
           "prompt_sha256": sorted({s["prompt_sha256"] for s in sums}),
           "cases_total": len(per_case), "provider_errors": perr, "grader_errors": gerr,
           "overall_quality": {"cases_scored": scored, "cases_passed": passed, "pass_rate": round(passed / scored, 4)},
           "criteria": {m: {"scored": c["scored"], "passed": c["passed"], "pass_rate": round(c["passed"] / c["scored"], 4),
                            "mean_score": round(c["sum"] / c["n"], 3) if c["n"] else None} for m, c in sorted(crit.items())},
           "failed_cases": failed}
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("cases_total", "overall_quality", "criteria")}, indent=1))
    return 0


def cmd_coverage(a) -> int:
    m = json.loads(Path(a.matrix).read_text())
    allowed = set(ALL_METRICS)
    rows, lb = [], 0
    for i in m["instructions"]:
        bad = set(i["criteria"]) - allowed
        if bad:
            print(f"{i['id']}: unknown criteria {bad}")
            return 1
        if i["load_bearing"] and not i["criteria"]:
            print(f"{i['id']}: marked load-bearing without a criterion")
            return 1
        lb += int(i["load_bearing"])
        rows.append(f"| {i['id']} | {i['text']} | {', '.join(i['criteria']) or '-'} | {'yes' if i['load_bearing'] else 'NO'}{(' - ' + i['note']) if i.get('note') else ''} |")
    n = len(m["instructions"])
    text = (f"Prompt {m['version']}: {lb}/{n} load-bearing = {100 * lb / n:.1f}%\n\n"
            "| # | Prompt instruction | Evaluation criteria | Load-bearing? |\n|---|---|---|---|\n" + "\n".join(rows))
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--force", action="store_true")
    sub.add_parser("verify")
    r = sub.add_parser("run")
    r.add_argument("version"); r.add_argument("split", choices=["dev", "holdout"])
    r.add_argument("--jobs", type=int, default=3); r.add_argument("--cases", help="regex on case name")
    r.add_argument("--label"); r.add_argument("--calibration", action="store_true")
    s = sub.add_parser("summarize"); s.add_argument("raw")
    c = sub.add_parser("compare"); c.add_argument("summaries", nargs="+"); c.add_argument("--out")
    cb = sub.add_parser("combine"); cb.add_argument("summaries", nargs="+"); cb.add_argument("--out", required=True)
    cv = sub.add_parser("coverage"); cv.add_argument("matrix"); cv.add_argument("--out")
    a = p.parse_args()
    if a.cmd == "freeze": return cmd_freeze(a)
    if a.cmd == "verify": return cmd_verify()
    if a.cmd == "run": return cmd_run(a)
    if a.cmd == "summarize": summarize(Path(a.raw)); return 0
    if a.cmd == "compare": return cmd_compare(a)
    if a.cmd == "combine": return cmd_combine(a)
    return cmd_coverage(a)


if __name__ == "__main__":
    sys.exit(main())
