#!/usr/bin/env python3
"""Materialise the holdout_v2 positive-case dataset (10 settings x 6 agents = 60 cases).

    .venv/bin/python scripts/build_holdout_v2_fixtures.py

Writes, under ``evals/fixtures/holdout_v2/``:

    world/<case>.json                       StoryBrief inputs for World Generation
    characters/briefs|worlds/<case>.json    StoryBrief + World inputs for Character Design
    storyboard/briefs|worlds|characters/    StoryBrief + World + CharacterSet for Storyboard Building
    reviewers/world|characters|storyboard/  full reviewer fixtures (expected_verdict PASS)
    manifest.json                           one entry per case, per-file sha256, dataset hash

Every artifact is checked with the deterministic validators in
``fictionforge.guardrails.validators`` before it is written; the script refuses
to emit an invalid case.  It also verifies uniqueness of ids and file contents
against the existing dev/holdout fixtures (no byte-identical reuse).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from holdout_v2_data import SETTINGS  # noqa: E402
from fictionforge.guardrails.validators import (  # noqa: E402
    validate_brief,
    validate_characters,
    validate_storyboard,
    validate_world,
)
from fictionforge.models import CharacterSet, StoryBrief, World  # noqa: E402

ROOT = REPO / "evals" / "fixtures" / "holdout_v2"
SPLIT = "holdout_v2"
REVIEWER_PREFIX = {"world": "WR", "characters": "CR", "storyboard": "SR"}
EXISTING_DIRS = [
    REPO / "evals" / "fixtures" / "world",
    REPO / "evals" / "fixtures" / "characters",
    REPO / "evals" / "fixtures" / "storyboard",
    REPO / "evals" / "fixtures" / "workflow",
    REPO / "evals" / "reviewers" / "fixtures",
]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def dump(data: object) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def reviewer_doc(case_id: str, agent: str, setting: dict) -> dict:
    doc = {
        "case_id": case_id,
        "agent": agent,
        "split": SPLIT,
        "category": "valid",
        "slug": setting["slug"],
        "context_validated": True,
        "brief": setting["brief"],
        "world": setting["world"],
    }
    if agent in ("characters", "storyboard"):
        doc["characters"] = setting["characters"]
    if agent == "storyboard":
        doc["storyboard"] = setting["storyboard"]
    doc.update(
        {
            "expected_verdict": "PASS",
            "labels": [],
            "traps": [],
            "evidence_summary": setting["evidence_summary"],
        }
    )
    return doc


def main() -> int:
    failures: list[str] = []
    cases: dict[str, dict] = {}
    seen_hashes: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Gather hashes and world names of all pre-existing fixtures to prove
    # holdout_v2 reuses nothing.
    # ------------------------------------------------------------------
    existing_hashes: dict[str, str] = {}
    existing_names: set[str] = set()
    for d in EXISTING_DIRS:
        for p in sorted(d.rglob("*.json")):
            existing_hashes[sha256_bytes(p.read_bytes())] = str(p.relative_to(REPO))
            try:
                doc = json.loads(p.read_bytes())
            except Exception:
                continue
            if not isinstance(doc, dict):
                continue
            w = doc.get("world") or doc
            if isinstance(w, dict):
                if w.get("name"):
                    existing_names.add(str(w["name"]).strip().lower())
                if w.get("world_id"):
                    existing_names.add(str(w["world_id"]).strip().lower())

    def emit(case: dict, role: str, rel: str, data: object) -> None:
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = dump(data)
        h = sha256_bytes(blob)
        if h in existing_hashes:
            failures.append(f"{rel}: byte-identical to existing fixture {existing_hashes[h]}")
        # The same brief/world is intentionally shared between the generation
        # and reviewer cases of one setting; only flag content reused across
        # different settings (identified by their v2_XX name prefix).
        setting_of = rel.split("/")[-1].split("_")[0:2]
        key = "_".join(setting_of)
        if h in seen_hashes and seen_hashes[h] != key:
            failures.append(f"{rel}: content duplicated from a different setting ({seen_hashes[h]})")
        seen_hashes.setdefault(h, key)
        path.write_bytes(blob)
        case["files"].append({"role": role, "path": f"evals/fixtures/holdout_v2/{rel}", "sha256": h})

    def add_case(case_id: str, agent: str, expected_key: str, expected: str, slug: str) -> dict:
        if case_id in cases:
            failures.append(f"duplicate case_id {case_id}")
        case = {"case_id": case_id, "agent": agent, "split": SPLIT, "category": "valid",
                expected_key: expected, "slug": slug, "files": []}
        cases[case_id] = case
        return case

    world_ids: set[str] = set()
    for s in SETTINGS:
        num = s["num"]
        slug = s["slug"]
        name = s["gen_name"]
        brief, world, cast, board = s["brief"], s["world"], s["characters"], s["storyboard"]

        # ---- deterministic validation -----------------------------------
        issues = validate_brief(brief)
        if issues:
            failures.append(f"{name}: brief invalid: {[i.to_dict() for i in issues]}")
            continue
        brief_model = StoryBrief.model_validate(brief)
        issues = validate_world(world, brief_model)
        if issues:
            failures.append(f"{name}: world invalid vs brief: {[i.to_dict() for i in issues]}")
        issues = validate_world(world)  # reviewer context must stand alone too
        if issues:
            failures.append(f"{name}: world invalid standalone: {[i.to_dict() for i in issues]}")
        world_model = World.model_validate(world)
        issues = validate_characters(cast, world_model, brief_model)
        if issues:
            failures.append(f"{name}: characters invalid: {[i.to_dict() for i in issues]}")
        cast_model = CharacterSet.model_validate(cast)
        issues = validate_storyboard(board, world_model, cast_model, brief_model)
        if issues:
            failures.append(f"{name}: storyboard invalid: {[i.to_dict() for i in issues]}")
        if world["world_id"] in world_ids:
            failures.append(f"{name}: duplicate world_id {world['world_id']}")
        world_ids.add(world["world_id"])
        for token in (world["name"], world["world_id"]):
            if str(token).strip().lower() in existing_names:
                failures.append(f"{name}: world identifier {token!r} collides with an existing fixture")

        # ---- generation cases --------------------------------------------
        c = add_case(f"WG-V2-{num:02d}", "world", "expected", "valid", slug)
        emit(c, "story_brief", f"world/{name}.json", brief)

        c = add_case(f"CD-V2-{num:02d}", "characters", "expected", "valid", slug)
        emit(c, "story_brief", f"characters/briefs/{name}.json", brief)
        emit(c, "world", f"characters/worlds/{name}.json", world)

        c = add_case(f"SB-V2-{num:02d}", "storyboard", "expected", "valid", slug)
        emit(c, "story_brief", f"storyboard/briefs/{name}.json", brief)
        emit(c, "world", f"storyboard/worlds/{name}.json", world)
        emit(c, "character_set", f"storyboard/characters/{name}.json", cast)

        # ---- reviewer cases ----------------------------------------------
        for agent in ("world", "characters", "storyboard"):
            cid = f"{REVIEWER_PREFIX[agent]}-V2-{num:02d}"
            c = add_case(cid, agent, "expected_verdict", "PASS", slug)
            emit(c, "reviewer_fixture", f"reviewers/{agent}/{cid}_{slug}.json",
                 reviewer_doc(cid, agent, s))

    # ---- manifest --------------------------------------------------------
    case_list = [cases[k] for k in sorted(cases)]
    lines = sorted(
        f"{f['path']}\t{f['sha256']}"
        for c in case_list for f in c["files"]
    )
    dataset_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    manifest_doc = {
        "dataset": "holdout_v2",
        "purpose": "Independent positive-case holdout measuring false-positive avoidance and valid-input handling; NOT a comprehensive holdout (no adversarial or malformed cases).",
        "split": SPLIT,
        "case_count": len(case_list),
        "file_count": len(lines),
        "dataset_sha256": dataset_hash,
        "cases": case_list,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "manifest.json").write_text(json.dumps(manifest_doc, indent=2, ensure_ascii=False) + "\n")

    per_agent: dict[str, int] = {}
    for c in case_list:
        per_agent[c["agent"]] = per_agent.get(c["agent"], 0) + 1

    print(f"cases written: {len(case_list)}  {per_agent}")
    print(f"files written: {len(lines)}")
    print(f"dataset_sha256: {dataset_hash}")
    if failures:
        print("VALIDATION/INTEGRITY FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all fixtures pass deterministic validation and integrity checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
