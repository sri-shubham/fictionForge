"""Export JSON Schemas for the FictionForge world-generation contracts.

Generates Draft 2020-12 JSON schemas from the pydantic models so that
non-Python consumers (and the guardrail validators) can validate payloads
without importing the models.

Usage::

    python -m fictionforge.schema_export [output_dir]

Writes ``brief.schema.json``, ``characters.schema.json``,
``storyboard.schema.json``, and ``world.schema.json``
(default: ``schemas/`` at the repository root).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fictionforge.models import CharacterSet, Storyboard, StoryBrief, World

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"


def brief_schema() -> dict:
    """JSON Schema (validation mode) for :class:`StoryBrief`."""
    return StoryBrief.model_json_schema(mode="validation")


def world_schema() -> dict:
    """JSON Schema (validation mode) for :class:`World`."""
    return World.model_json_schema(mode="validation")


def character_schema() -> dict:
    """JSON Schema (validation mode) for :class:`CharacterSet`."""
    return CharacterSet.model_json_schema(mode="validation")


def storyboard_schema() -> dict:
    """JSON Schema (validation mode) for :class:`Storyboard`."""
    return Storyboard.model_json_schema(mode="validation")


def _serialize(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_schemas(directory: Path) -> tuple[Path, Path, Path, Path]:
    """Write all schema files into ``directory``; returns their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    brief_path = directory / "brief.schema.json"
    world_path = directory / "world.schema.json"
    character_path = directory / "characters.schema.json"
    storyboard_path = directory / "storyboard.schema.json"
    brief_path.write_text(_serialize(brief_schema()), encoding="utf-8")
    world_path.write_text(_serialize(world_schema()), encoding="utf-8")
    character_path.write_text(_serialize(character_schema()), encoding="utf-8")
    storyboard_path.write_text(_serialize(storyboard_schema()), encoding="utf-8")
    return brief_path, world_path, character_path, storyboard_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    directory = Path(args[0]) if args else DEFAULT_SCHEMA_DIR
    for path in write_schemas(directory):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
