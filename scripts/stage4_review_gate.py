"""Stage 4 single-gate, single-shot adversarial review for manual evaluation.

Runs the REAL ``AdversarialReviewer`` + ``HandoffHook`` against one artifact
(and its upstream context documents) without driving a full workflow.  The
hook uses ``require_upstream_approval=False`` and a temporary in-memory
GateKeeper, so this never mints a durable approval — it is a shadow
measurement harness, not a handoff.

Typical use (calls a live model; run manually, never in tests)::

    .venv/bin/python scripts/stage4_review_gate.py \
        --gate world \
        --fixture evals/reviewers/fixtures/world/holdout/WR-H01_frostmarch_clean.json \
        --mode shadow

The deterministic validators for the artifact and every supplied upstream
document run first; if any fail the reviewer is never called and the result
is ``deterministic_validation_failed``.

Tests must call :func:`run_gate_review` with a MockClient only.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from fictionforge.config import WorkflowConfig  # noqa: E402
from fictionforge.guardrails.handoff import GateKeeper, HandoffHook  # noqa: E402
from fictionforge.guardrails.review import (  # noqa: E402
    SELECTED_PROMPT_VERSIONS,
    AdversarialReviewer,
    REVIEW_MODES,
    artifact_sha256,
    default_reviewer_configs,
)
from fictionforge.guardrails.validators import (  # noqa: E402
    validate_brief,
    validate_characters,
    validate_storyboard,
    validate_world,
)
from fictionforge.models import (  # noqa: E402
    CharacterSet,
    StoryBrief,
    Storyboard,
    World,
)
from fictionforge.observability.audit import AuditLogger  # noqa: E402
from fictionforge.runner import Artifact, _canonical_json, _sha256  # noqa: E402

GATE_TO_STEP = {
    "world": "world_generation",
    "characters": "character_design",
    "storyboard": "storyboard_building",
}
_STEP_TO_GATE = {v: k for k, v in GATE_TO_STEP.items()}

GATE_ARTIFACT_DOC = {
    "world": "world",
    "characters": "characters",
    "storyboard": "storyboard",
}

SHADOW_LABEL = (
    "SHADOW MODE: reviewer verdicts were advisory and did not gate handoffs; "
    "this run is not evidence of enforced adversarial guardrails."
)


def _artifact(doc: str, data: dict[str, Any]) -> Artifact:
    canonical = _canonical_json(data)
    return Artifact(
        step_id=GATE_TO_STEP.get(doc, "load_brief"),
        artifact_type=doc,
        canonical_json=canonical,
        sha256=_sha256(canonical),
        prompt_version="",
        validation_result={"status": "passed", "issues": []},
        model_class=dict,
    )


def _validate_documents(
    gate: str, documents: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Run deterministic validators for the artifact and upstream docs."""
    models: dict[str, Any] = {}
    out: dict[str, dict[str, Any]] = {}

    def record(name, issues):
        out[name] = {
            "status": "failed" if issues else "passed",
            "issue_codes": [str(i.code) for i in issues],
            "issues": [i.to_dict() for i in issues],
        }

    if "brief" in documents:
        issues = validate_brief(documents["brief"])
        record("brief", issues)
        if not issues:
            models["brief"] = StoryBrief.model_validate(documents["brief"])
    if "world" in documents:
        issues = validate_world(documents["world"], models.get("brief"))
        record("world", issues)
        if not issues:
            models["world"] = World.model_validate(documents["world"])
    def try_record(name, fn):
        try:
            record(name, fn())
        except Exception as exc:  # missing/invalid upstream model
            out[name] = {
                "status": "failed",
                "issue_codes": ["VALIDATION_ERROR"],
                "issues": [{"code": "VALIDATION_ERROR", "message": str(exc)}],
            }

    if "characters" in documents:
        try_record(
            "characters",
            lambda: validate_characters(
                documents["characters"], models.get("world"), models.get("brief")
            ),
        )
        if out["characters"]["status"] == "passed":
            models["characters"] = CharacterSet.model_validate(
                documents["characters"]
            )
    if "storyboard" in documents:
        try_record(
            "storyboard",
            lambda: validate_storyboard(
                documents["storyboard"],
                models.get("world"),
                models.get("characters"),
                models.get("brief"),
            ),
        )
        if out["storyboard"]["status"] == "passed":
            models["storyboard"] = Storyboard.model_validate(
                documents["storyboard"]
            )
    return out, models


def run_gate_review(
    client,
    *,
    gate: str,
    documents: dict[str, Any],
    mode: str = "shadow",
    model: str | None = None,
    timeout: float = 300.0,
    max_attempts: int = 2,
    expected_verdict: str | None = None,
) -> dict[str, Any]:
    """One-shot gate review.  ``client`` is the reviewer client (MockClient in tests).

    ``documents`` maps doc names (brief/world/characters/storyboard) to
    validated-or-candidate JSON dicts; the artifact under review is
    ``documents[gate]``.
    """
    if gate not in GATE_TO_STEP:
        raise ValueError(f"unknown gate {gate!r}")
    if mode not in REVIEW_MODES:
        raise ValueError(f"mode must be one of {REVIEW_MODES}")
    step_id = GATE_TO_STEP[gate]
    artifact_doc = documents[gate]
    sha = artifact_sha256(artifact_doc)

    result: dict[str, Any] = {
        "standalone": True,
        "upstream_approval_verified": False,
        "gate": gate,
        "step": step_id,
        "mode": mode,
        "shadow": mode == "shadow",
        "label": SHADOW_LABEL if mode == "shadow" else "ENFORCED MODE",
        "artifact_sha256": sha,
        "prompt_version": SELECTED_PROMPT_VERSIONS.get(gate),
        "validation": {},
        "deterministic_artifact_findings": [],
        "verdict": None,
        "issues": [],
        "decision": None,
        "enforced_equivalent_decision": None,
        "latency_s": None,
        "token_usage": None,
        "false_positive_candidates": [],
        "label_comparison": None,
    }

    cfg = default_reviewer_configs(
        model=model, timeout=timeout, max_attempts=max_attempts
    )[step_id]

    # Deterministic validators for the artifact AND its upstream docs first.
    needed = {gate, *cfg.context_keys}
    validation, models = _validate_documents(
        gate, {k: v for k, v in documents.items() if k in needed}
    )
    result["validation"] = validation
    if any(v["status"] == "failed" for v in validation.values()):
        result["decision"] = "deterministic_validation_failed"
        return result

    validators = {
        "world": lambda: validate_world(artifact_doc, models.get("brief")),
        "characters": lambda: validate_characters(
            artifact_doc, models.get("world"), models.get("brief")
        ),
        "storyboard": lambda: validate_storyboard(
            artifact_doc,
            models.get("world"),
            models.get("characters"),
            models.get("brief"),
        ),
    }

    reviewer = AdversarialReviewer(client, cfg)
    result["reviewer_prompt_sha256"] = reviewer.template_sha256
    result["reviewer_model"] = model

    context = {k: documents[k] for k in cfg.context_keys}
    docs = {**context, gate: artifact_doc}
    artifact = _artifact(gate, artifact_doc)
    input_artifacts = {k: _artifact(k, documents[k]) for k in cfg.context_keys}

    wf_config = WorkflowConfig.default()
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        keeper = GateKeeper(
            Path(tmp) / "gates", "standalone", secrets.token_bytes(32), mode=mode
        )
        audit = AuditLogger(Path(tmp), run_id="standalone")
        hook = HandoffHook(
            keeper=keeper,
            audit=audit,
            is_retryable=wf_config.is_retryable,
            run_id="standalone",
            reviewers={step_id: reviewer},
            mode=mode,
            reference_labels={gate: expected_verdict} if expected_verdict else None,
            require_upstream_approval=False,
        )
        outcome = hook.run(
            step_id=step_id,
            artifact=artifact,
            input_artifacts=input_artifacts,
            validate_fn=validators[gate],
            attempt=1,
            context=context,
            final_attempt=True,
        )
    result["latency_s"] = round(time.monotonic() - started, 3)

    rec = outcome.record
    rev = rec.get("reviewer", {})
    result["deterministic_artifact_findings"] = rec.get(
        "deterministic_artifact_findings", []
    )
    result["verdict"] = rev.get("verdict")
    result["issues"] = rev.get("issues", [])
    result["decision"] = rec.get("gate_decision")
    result["enforced_equivalent_decision"] = (rec.get("shadow") or {}).get(
        "enforced_equivalent_decision"
    ) or rec.get("enforced_equivalent_decision")
    result["token_usage"] = rev.get("token_usage")
    result["reviewer_attempts"] = rev.get("attempts", [])
    result["reviewer_error_code"] = rev.get("error_code")
    result["policy"] = rec.get("policy")
    result["false_positive_candidates"] = rec.get("false_positive_candidates", [])
    result["repeated_findings"] = rec.get("repeated_findings", [])
    result["label_comparison"] = rec.get("label_comparison")
    result["reviewer_model"] = rev.get("model") or model
    return result


def _load_documents(args) -> tuple[dict[str, Any], str | None]:
    expected = None
    if args.fixture:
        fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        documents = {
            k: fixture[k]
            for k in ("brief", "world", "characters", "storyboard")
            if k in fixture
        }
        expected = fixture.get("expected_verdict")
    else:
        defaults = {
            "brief": "examples/story_brief.json",
            "world": "examples/worlds/valid_world.json",
            "characters": "examples/characters/valid_characters.json",
            "storyboard": "examples/storyboards/valid_storyboard.json",
        }
        documents = {}
        for name, default in defaults.items():
            path = getattr(args, name) or (REPO_ROOT / default)
            p = Path(path)
            if p.exists():
                documents[name] = json.loads(p.read_text(encoding="utf-8"))
    return documents, expected


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--gate", required=True, choices=sorted(GATE_TO_STEP))
    ap.add_argument("--fixture", default=None,
                    help="Stage 3 fixture JSON (keys brief/world/characters/"
                         "storyboard/expected_verdict); read-only.")
    for name in ("brief", "world", "characters", "storyboard"):
        ap.add_argument(f"--{name}", default=None,
                        help=f"Path to the {name} JSON doc (default: examples/).")
    ap.add_argument("--mode", default="shadow", choices=list(REVIEW_MODES))
    ap.add_argument("--model", default="swe-2-medium")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--expected-verdict", default=None,
                    choices=["PASS", "REVISE", "PUNCH_OUT"])
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "evidence" / "stage4" / "shadow_runs"))
    args = ap.parse_args()

    documents, expected = _load_documents(args)
    expected = args.expected_verdict or expected

    from fictionforge.llm.devin import DevinCliClient

    client = DevinCliClient(model=args.model, cli_timeout=args.timeout)
    result = run_gate_review(
        client,
        gate=args.gate,
        documents=documents,
        mode=args.mode,
        model=args.model,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        expected_verdict=expected,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{args.gate}_{args.mode}_{int(time.time())}.json"
    (out_dir / name).write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {out_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
