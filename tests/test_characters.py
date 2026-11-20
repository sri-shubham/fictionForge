"""Tests for the Character Design contracts and deterministic guardrails."""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest
from pydantic import ValidationError

from conftest import EXAMPLES_DIR, SCHEMAS_DIR, load_json
from fictionforge.guardrails.validators import (
    ErrorCode,
    ValidationIssue,
    validate_characters,
)
from fictionforge.models import (
    Character,
    CharacterSet,
    MAX_CHARACTERS,
    MAX_RELATIONSHIPS,
    World,
)
from fictionforge.schema_export import character_schema

CHARACTERS_DIR = EXAMPLES_DIR / "characters"
INVALID_CHARACTERS_DIR = CHARACTERS_DIR / "invalid"


def codes_and_paths(issues):
    return [(i.code, i.path) for i in issues]


@pytest.fixture(scope="session")
def character_data() -> dict:
    return load_json(CHARACTERS_DIR / "valid_characters.json")


@pytest.fixture(scope="session")
def aetheria(world_data) -> World:
    return World.model_validate(world_data)


# ---------------------------------------------------------------------------
# Model and happy-path tests
# ---------------------------------------------------------------------------


def test_valid_character_set_parses(character_data):
    cs = CharacterSet.model_validate(character_data)
    assert cs.world_id == "wld_aetheria"
    assert any(c.role == "protagonist" for c in cs.characters)


def test_valid_character_set_round_trip(character_data):
    cs = CharacterSet.model_validate(character_data)
    assert cs.model_dump(mode="json") == character_data


def test_valid_characters_fixture_is_clean(character_data, aetheria):
    assert validate_characters(character_data, aetheria) == []


# ---------------------------------------------------------------------------
# Invalid fixture files
# ---------------------------------------------------------------------------

EXPECTED = {
    "duplicate_character_id.json": (ErrorCode.DUPLICATE_ID, "$.characters[1].id"),
    "unknown_location.json": (ErrorCode.UNKNOWN_LOCATION_REF, "$.characters[0].home_location_id"),
    "unknown_faction.json": (ErrorCode.UNKNOWN_FACTION_REF, "$.characters[0].faction_id"),
    "unknown_character_ref.json": (
        ErrorCode.UNKNOWN_CHARACTER_REF,
        "$.relationships[0].source_character_id",
    ),
    "missing_protagonist.json": (ErrorCode.MISSING_PROTAGONIST, "$.characters"),
    "invalid_world_id.json": (ErrorCode.WORLD_ID_MISMATCH, "$.world_id"),
    "duplicate_relationship.json": (ErrorCode.DUPLICATE_RELATIONSHIP, "$.relationships[1]"),
}


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_invalid_character_fixtures(filename, aetheria):
    data = load_json(INVALID_CHARACTERS_DIR / filename)
    expected_code, expected_path = EXPECTED[filename]
    issues = validate_characters(data, aetheria)
    assert (expected_code, expected_path) in codes_and_paths(issues)
    # Deterministic across calls
    assert codes_and_paths(validate_characters(data, aetheria)) == codes_and_paths(issues)


def test_expectation_table_covers_all_character_fixture_files():
    files = {p.name for p in INVALID_CHARACTERS_DIR.glob("*.json")}
    assert files == set(EXPECTED)


# ---------------------------------------------------------------------------
# Structural edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, [], "x", 3])
def test_non_dict_inputs(bad, aetheria):
    issues = validate_characters(bad, aetheria)
    assert codes_and_paths(issues) == [(ErrorCode.SCHEMA_VIOLATION, "$")]


def test_empty_dict_reports_required_fields(aetheria):
    issues = validate_characters({}, aetheria)
    paths = {i.path for i in issues if i.code == ErrorCode.MISSING_REQUIRED_FIELD}
    assert {"$.world_id", "$.characters"} <= paths


def test_empty_character_list(aetheria):
    issues = validate_characters({"world_id": "wld_aetheria", "characters": []}, aetheria)
    assert (ErrorCode.COUNT_BELOW_MIN, "$.characters") in codes_and_paths(issues)


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "name",
        "role",
        "description",
        "motivation",
        "goal",
        "flaw",
        "internal_conflict",
        "external_conflict",
        "home_location_id",
        "arc",
    ],
)
def test_missing_character_required_fields(field, character_data, aetheria):
    data = copy.deepcopy(character_data)
    del data["characters"][0][field]
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.MISSING_REQUIRED_FIELD, f"$.characters[0].{field}") in codes_and_paths(
        issues
    )


def test_invalid_character_role(character_data, aetheria):
    data = copy.deepcopy(character_data)
    data["characters"][0]["role"] = "hero"
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.SCHEMA_VIOLATION, "$.characters[0].role") in codes_and_paths(issues)


@pytest.mark.parametrize(
    "abilities",
    [
        pytest.param(["not an object"], id="string_ability"),
        pytest.param([{"description": "missing name"}], id="missing_ability_name"),
        pytest.param(
            [{"name": "x", "description": "y", "extra": 1}], id="extra_ability_field"
        ),
    ],
)
def test_malformed_ability_objects(abilities, character_data, aetheria):
    data = copy.deepcopy(character_data)
    data["characters"][0]["abilities"] = abilities
    issues = validate_characters(data, aetheria)
    assert any(
        i.code in (ErrorCode.SCHEMA_VIOLATION, ErrorCode.MISSING_REQUIRED_FIELD)
        for i in issues
    )


@pytest.mark.parametrize(
    "patch,expected_path",
    [
        ({"characters": [{"extra": 1}]}, "$.characters[0]"),
        ({"extra": 1}, "$"),
    ],
)
def test_unknown_additional_fields(patch, expected_path, character_data, aetheria):
    data = copy.deepcopy(character_data)
    if "characters" in patch:
        # Replace first character with a minimal-but-extra payload
        data["characters"][0] = {
            "id": "chr_test",
            "name": "Test",
            "role": "protagonist",
            "description": "A test.",
            "motivation": "Test.",
            "goal": "Test.",
            "flaw": "Test.",
            "internal_conflict": "Test.",
            "external_conflict": "Test.",
            "home_location_id": "loc_emberroost",
            "arc": "Grows.",
            "extra": 1,
        }
    else:
        data.update(patch)
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.SCHEMA_VIOLATION, expected_path) in codes_and_paths(issues)


# ---------------------------------------------------------------------------
# Relationship edge cases
# ---------------------------------------------------------------------------


def test_duplicate_relationship_id(character_data, aetheria):
    data = copy.deepcopy(character_data)
    data["relationships"][1]["id"] = data["relationships"][0]["id"]
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.DUPLICATE_ID, "$.relationships[1].id") in codes_and_paths(issues)


def test_self_referential_relationship(character_data, aetheria):
    data = copy.deepcopy(character_data)
    data["relationships"].append(
        {
            "id": "rel_self",
            "source_character_id": "chr_veya",
            "target_character_id": "chr_veya",
            "relationship_type": "rival",
            "description": "Veya battles herself.",
        }
    )
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.SELF_RELATIONSHIP, "$.relationships[2]") in codes_and_paths(issues)


def test_unknown_relationship_target(character_data, aetheria):
    data = copy.deepcopy(character_data)
    data["relationships"][0]["target_character_id"] = "chr_missing"
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.UNKNOWN_CHARACTER_REF, "$.relationships[0].target_character_id") in codes_and_paths(
        issues
    )


# ---------------------------------------------------------------------------
# Boundary count tests
# ---------------------------------------------------------------------------


def _minimal_character(i: int, role: str = "supporting") -> dict:
    return {
        "id": f"chr_{i:04d}",
        "name": f"Character {i}",
        "role": role,
        "description": "A minimal character.",
        "personality_traits": ["brave"],
        "motivation": "To survive.",
        "goal": "Survive.",
        "flaw": "Cautious.",
        "internal_conflict": "Fear.",
        "external_conflict": "Danger.",
        "home_location_id": "loc_emberroost",
        "faction_id": None,
        "abilities": [],
        "arc": "Grows.",
    }


def _character_set(n_chars: int, n_rels: int = 0) -> dict:
    data = {
        "world_id": "wld_aetheria",
        "characters": [
            _minimal_character(i, role="protagonist" if i == 0 else "supporting")
            for i in range(n_chars)
        ],
        "relationships": [],
    }
    if n_rels:
        for i in range(n_rels):
            data["relationships"].append(
                {
                    "id": f"rel_{i:04d}",
                    "source_character_id": data["characters"][0]["id"],
                    "target_character_id": data["characters"][1]["id"],
                    "relationship_type": f"type_{i}",
                    "description": "A relationship.",
                }
            )
    return data


@pytest.mark.parametrize("count", [1, MAX_CHARACTERS])
def test_character_count_boundaries_ok(count, aetheria):
    assert validate_characters(_character_set(count), aetheria) == []


@pytest.mark.parametrize("count", [0, MAX_CHARACTERS + 1])
def test_character_count_boundaries_fail(count, aetheria):
    issues = validate_characters(_character_set(count), aetheria)
    if count == 0:
        assert (ErrorCode.COUNT_BELOW_MIN, "$.characters") in codes_and_paths(issues)
    else:
        assert (ErrorCode.COUNT_ABOVE_MAX, "$.characters") in codes_and_paths(issues)


@pytest.mark.parametrize("count", [0, MAX_RELATIONSHIPS])
def test_relationship_count_boundaries_ok(count, aetheria):
    data = _character_set(2, count)
    assert validate_characters(data, aetheria) == []


def test_relationship_count_above_max(aetheria):
    data = _character_set(2, MAX_RELATIONSHIPS + 1)
    issues = validate_characters(data, aetheria)
    assert (ErrorCode.COUNT_ABOVE_MAX, "$.relationships") in codes_and_paths(issues)


# ---------------------------------------------------------------------------
# Determinism and immutability
# ---------------------------------------------------------------------------


def test_issues_sorted_by_path_then_code(aetheria):
    data = _character_set(1)
    data["world_id"] = "wld_other"
    data["characters"][0]["home_location_id"] = "loc_missing"
    issues = validate_characters(data, aetheria)
    keys = [(i.path, str(i.code)) for i in issues]
    assert keys == sorted(keys)
    assert len(issues) >= 2


def test_input_immutability(character_data, aetheria):
    before_data = copy.deepcopy(character_data)
    before_world = aetheria.model_dump(mode="json")
    validate_characters(character_data, aetheria)
    assert character_data == before_data
    assert aetheria.model_dump(mode="json") == before_world


# ---------------------------------------------------------------------------
# Exported JSON schema
# ---------------------------------------------------------------------------


def test_character_schema_on_disk_matches_generated():
    on_disk = load_json(SCHEMAS_DIR / "characters.schema.json")
    assert on_disk == character_schema()
    expected = json.dumps(character_schema(), indent=2, sort_keys=True) + "\n"
    assert (SCHEMAS_DIR / "characters.schema.json").read_text(encoding="utf-8") == expected


def test_character_schema_is_valid_draft202012():
    schema = load_json(SCHEMAS_DIR / "characters.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_valid_character_fixture_validates_against_on_disk_schema(character_data):
    schema = load_json(SCHEMAS_DIR / "characters.schema.json")
    jsonschema.Draft202012Validator(schema).validate(character_data)


# ---------------------------------------------------------------------------
# Error code / issue object checks
# ---------------------------------------------------------------------------


def test_new_error_codes_are_strings():
    for code in [
        ErrorCode.UNKNOWN_CHARACTER_REF,
        ErrorCode.WORLD_ID_MISMATCH,
        ErrorCode.SELF_RELATIONSHIP,
        ErrorCode.DUPLICATE_RELATIONSHIP,
        ErrorCode.MISSING_PROTAGONIST,
    ]:
        assert isinstance(code, str)
        assert code == code.value


def test_validation_issue_to_dict():
    issue = ValidationIssue(ErrorCode.MISSING_PROTAGONIST, "$.characters", "no hero")
    assert issue.to_dict() == {
        "code": "MISSING_PROTAGONIST",
        "path": "$.characters",
        "message": "no hero",
    }
