"""Offline summariser for Stage 4 adversarial-review run directories.

Reads only files on disk (``audit.jsonl``, ``gates/*.json``,
``gates/false_positive_candidates.jsonl``, ``summary.json``) — no model
calls, ever::

    .venv/bin/python scripts/stage4_summarize.py runs/<run_id> [...] [--out summary.json]

Shadow runs are explicitly labelled: they are *not* proof of enforced
adversarial guardrails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHADOW_NOTE = (
    "SHADOW MODE: reviewer verdicts were advisory and did not gate handoffs; "
    "this run is not proof of enforced adversarial guardrails."
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def summarize_run(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    events = _read_jsonl(run_dir / "audit.jsonl")
    gates_dir = run_dir / "gates"

    review_info = summary.get("review") or {}
    mode = review_info.get("mode")
    run: dict[str, Any] = {
        "run_dir": str(run_dir),
        "run_id": summary.get("run_id", run_dir.name),
        "status": summary.get("status"),
        "review_mode": mode,
        "adversarial_guardrails_enforced": review_info.get(
            "adversarial_guardrails_enforced"
        ),
        "shadow": mode == "shadow",
        "label": review_info.get("label"),
        "gates": {},
        "false_positive_candidates": [],
        "totals": {},
    }

    fp_path = gates_dir / "false_positive_candidates.jsonl"
    run["false_positive_candidates"] = _read_jsonl(fp_path)

    gate_files = sorted(gates_dir.glob("*_review.json")) if gates_dir.is_dir() else []
    latencies: list[float] = []
    n_revise = 0
    n_label_fp = 0
    n_labelled = 0
    for gf in gate_files:
        try:
            rec = json.loads(gf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rev = rec.get("reviewer") or {}
        issues = rev.get("issues") or []
        det = rec.get("deterministic_artifact_findings") or []
        if rev.get("latency_s") is not None:
            latencies.append(rev["latency_s"])
        if rec.get("gate_decision") == "RETRY":
            n_revise += 1
        lc = rec.get("label_comparison")
        if lc:
            n_labelled += 1
            if lc.get("false_positive"):
                n_label_fp += 1
        run["gates"][rec.get("gate", gf.stem)] = {
            "step": rec.get("step"),
            "generator_attempt": rec.get("generator_attempt"),
            "artifact_sha256": rec.get("artifact_sha256"),
            "review_mode": rec.get("review_mode"),
            "prompt_version": rec.get("prompt_version"),
            "verdict": rev.get("verdict"),
            "reviewer_id": rev.get("reviewer_id"),
            "model": rev.get("model"),
            "prompt_sha256": rev.get("prompt_sha256"),
            "reviewed_artifact_sha256": rev.get("reviewed_artifact_sha256"),
            "error_code": rev.get("error_code"),
            "latency_s": rev.get("latency_s"),
            "token_usage": rev.get("token_usage"),
            "findings": [
                {"code": i.get("code"), "severity": i.get("severity")}
                for i in issues
            ] + [
                {"code": i.get("code"), "severity": i.get("severity")}
                for i in det
            ],
            "gate_decision": rec.get("gate_decision"),
            "outcome": rec.get("outcome"),
            "policy": rec.get("policy"),
            "repeated_findings": rec.get("repeated_findings") or [],
            "false_positive_candidates": rec.get("false_positive_candidates")
            or [],
            "label_comparison": lc,
            "enforced_equivalent_decision": (rec.get("shadow") or {}).get(
                "enforced_equivalent_decision"
            ),
        }

    run["totals"] = {
        "gate_records": len(run["gates"]),
        "revise_retries": n_revise,
        "false_positive_candidates": len(run["false_positive_candidates"]),
        "mean_reviewer_latency_s": (
            round(sum(latencies) / len(latencies), 3) if latencies else None
        ),
        "audit_events": len(events),
        "label_false_positive_rate": (
            round(n_label_fp / n_labelled, 3) if n_labelled else None
        ),
        "labelled_gates": n_labelled,
    }
    return run


def to_markdown(runs: list[dict[str, Any]]) -> str:
    lines = ["# Stage 4 adversarial-review run summary", ""]
    for run in runs:
        lines.append(f"## Run `{run['run_id']}` — {run['status']}")
        if run["shadow"]:
            lines.append(f"> {SHADOW_NOTE}")
        lines.append("")
        lines.append(
            f"- mode: `{run['review_mode']}` enforced: "
            f"`{run['adversarial_guardrails_enforced']}`"
        )
        t = run["totals"]
        lines.append(
            f"- gates: {t['gate_records']}, REVISE retries: {t['revise_retries']}, "
            f"FP candidates: {t['false_positive_candidates']}, "
            f"mean reviewer latency: {t['mean_reviewer_latency_s']}s"
        )
        if t["label_false_positive_rate"] is not None:
            lines.append(
                f"- label FP rate: {t['label_false_positive_rate']} "
                f"({t['labelled_gates']} labelled gates)"
            )
        for gate, g in sorted(run["gates"].items()):
            codes = ", ".join(
                f"{f['code']}({f['severity']})" for f in g["findings"]
            ) or "none"
            lines.append(
                f"  - **{gate}** attempt {g['generator_attempt']}: "
                f"verdict `{g['verdict']}` decision `{g['gate_decision']}` "
                f"findings [{codes}] latency {g['latency_s']}s "
                f"tokens {g['token_usage']} hash `{str(g['artifact_sha256'])[:12]}…`"
            )
            if g["repeated_findings"]:
                lines.append(f"    - repeated findings: {g['repeated_findings']}")
            if g["false_positive_candidates"]:
                lines.append(
                    f"    - FP candidates: {g['false_positive_candidates']}"
                )
            if g["label_comparison"]:
                lines.append(f"    - label comparison: {g['label_comparison']}")
            if g["enforced_equivalent_decision"]:
                lines.append(
                    f"    - enforced-equivalent decision: "
                    f"`{g['enforced_equivalent_decision']}`"
                )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", default=None, help="Write JSON summary to PATH.")
    args = ap.parse_args()
    runs = [summarize_run(d) for d in args.run_dirs]
    print(to_markdown(runs))
    if args.out:
        Path(args.out).write_text(
            json.dumps({"runs": runs}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
