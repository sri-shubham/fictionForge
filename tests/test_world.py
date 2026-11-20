"""Tests for world-generation contracts (models) and exported JSON schemas."""

from __future__ import annotations

import json

import jsonschema
import pytest
from pydantic import ValidationError

from conftest import SCHEMAS_DIR, WORLDS_DIR, load_json
from fictionforge.models import (
    Location,
    StoryBrief,
    World,
)
from fictionforge.schema_export import brief_schema, world_schema

MINIMAL_BRIEF = {
    "premise": "A detective solves crimes in a city built inside a giant tree.",
    "genre": "mystery",
    "tone": "noir",
}


# ---------------------------------------------------------------------------
# StoryBrief model
# ---------------------------------------------------------------------------


def test_valid_brief_parses(brief_data):
    brief = StoryBrief.model_validate(brief_data)
    assert brief.location_count == 4
    assert "forbid:gunpowder" in brief.constraints


def test_minimal_brief_parses():
    brief = StoryBrief.model_validate(MINIMAL_BRIEF)
    assert brief.title is None
    assert brief.constraints == []
    assert brief.location_count is None


@pytest.mark.parametrize(
    "patch",
    [
        pytest.param({"premise": None}, id="missing_premise"),
        pytest.param({"genre": None}, id="missing_genre"),
        pytest.param({"tone": None}, id="missing_tone"),
        pytest.param({"premise": ""}, id="empty_premise"),
        pytest.param({"premise": "   "}, id="whitespace_premise"),
        pytest.param({"location_count": 0}, id="location_count_0"),
        pytest.param({"location_count": -1}, id="location_count_neg"),
        pytest.param({"location_count": 51}, id="location_count_51"),
        pytest.param({"location_count": "3"}, id="location_count_str"),
        pytest.param({"location_count": 2.5}, id="location_count_float"),
        pytest.param({"location_count": True}, id="location_count_bool"),
        pytest.param({"constraints": "no-cannons"}, id="constraints_not_list"),
        pytest.param({"unexpected": 1}, id="extra_field"),
        pytest.param({"title": "t" * 121}, id="title_too_long"),
    ],
)
def test_invalid_briefs_rejected(patch):
    data = dict(MINIMAL_BRIEF)
    for key, value in patch.items():
        if value is None and key in ("premise", "genre", "tone"):
            data.pop(key)
        else:
            data[key] = value
    with pytest.raises(ValidationError):
        StoryBrief.model_validate(data)


@pytest.mark.parametrize("location_count", [1, 50])
def test_brief_location_count_boundaries(location_count):
    brief = StoryBrief.model_validate({**MINIMAL_BRIEF, "location_count": location_count})
    assert brief.location_count == location_count


def test_brief_premise_max_length():
    StoryBrief.model_validate({**MINIMAL_BRIEF, "premise": "p" * 4000})
    with pytest.raises(ValidationError):
        StoryBrief.model_validate({**MINIMAL_BRIEF, "premise": "p" * 4001})


# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------


def test_valid_world_parses(world_data):
    world = World.model_validate(world_data)
    assert world.world_id == "wld_aetheria"
    assert len(world.locations) == 4


def _minimal_location(i: int) -> dict:
    return {"id": f"loc_{i:02d}", "name": f"Place {i}", "description": "d"}


def _minimal_rule(i: int) -> dict:
    return {"id": f"rul_{i:02d}", "statement": "s"}


def _world_with(locations: int, rules: int = 1) -> dict:
    return {
        "world_id": "wld_test",
        "name": "Testworld",
        "description": "A test world.",
        "locations": [_minimal_location(i) for i in range(locations)],
        "rules": [_minimal_rule(i) for i in range(rules)],
    }


@pytest.mark.parametrize("count", [1, 25])
def test_world_location_boundaries_ok(count):
    World.model_validate(_world_with(count))


@pytest.mark.parametrize("count", [0, 26])
def test_world_location_boundaries_fail(count):
    with pytest.raises(ValidationError):
        World.model_validate(_world_with(count))


@pytest.mark.parametrize("count", [1, 25])
def test_world_rule_boundaries_ok(count):
    World.model_validate(_world_with(1, rules=count))


@pytest.mark.parametrize("count", [0, 26])
def test_world_rule_boundaries_fail(count):
    with pytest.raises(ValidationError):
        World.model_validate(_world_with(1, rules=count))


@pytest.mark.parametrize("body_len", [48, 49])
def test_location_id_length_boundary(body_len):
    loc = {"id": "loc_" + "a" * body_len, "name": "n", "description": "d"}
    if body_len <= 48:
        Location.model_validate(loc)
    else:
        with pytest.raises(ValidationError):
            Location.model_validate(loc)


def test_location_id_uppercase_fails():
    with pytest.raises(ValidationError):
        Location.model_validate(
            {"id": "loc_ABC", "name": "n", "description": "d"}
        )


# ---------------------------------------------------------------------------
# Exported JSON schemas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,schema_fn",
    [
        ("brief.schema.json", brief_schema),
        ("world.schema.json", world_schema),
    ],
)
def test_schema_files_match_generated(filename, schema_fn):
    on_disk = load_json(SCHEMAS_DIR / filename)
    assert on_disk == schema_fn()
    expected = json.dumps(schema_fn(), indent=2, sort_keys=True) + "\n"
    assert (SCHEMAS_DIR / filename).read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("filename", ["brief.schema.json", "world.schema.json"])
def test_schema_files_are_valid_draft202012(filename):
    schema = load_json(SCHEMAS_DIR / filename)
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "schema_file,data_file",
    [
        ("brief.schema.json", "story_brief.json"),
    ],
)
def test_brief_fixture_validates_against_on_disk_schema(schema_file, data_file):
    schema = load_json(SCHEMAS_DIR / schema_file)
    data = load_json(WORLDS_DIR.parent / data_file)
    jsonschema.Draft202012Validator(schema).validate(data)


def test_world_fixture_validates_against_on_disk_schema(world_data):
    schema = load_json(SCHEMAS_DIR / "world.schema.json")
    jsonschema.Draft202012Validator(schema).validate(world_data)


def test_world_round_trip(world_data):
    world = World.model_validate(world_data)
    assert world.model_dump(mode="json") == world_data


def test_brief_round_trip(brief_data):
    brief = StoryBrief.model_validate(brief_data)
    assert brief.model_dump(mode="json") == brief_data
