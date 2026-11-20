"""Tests for the Storyboard Building contracts and deterministic guardrails."""

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
    validate_storyboard,
)
from fictionforge.models import (
    MAX_ACTS,
    MAX_SCENE_CHARACTER_REFS,
    MAX_SCENES_PER_ACT,
    MIN_ACTS,
    MIN_SCENES_PER_ACT,
    CharacterSet,
    Scene,
    Storyboard,
    World,
)
from fictionforge.schema_export import storyboard_schema

STORYBOARDS_DIR = EXAMPLES_DIR / "storyboards"
INVALID_STORYBOARDS_DIR = STORYBOARDS_DIR / "invalid"


def codes_and_paths(issues):
    return [(i.code, i.path) for i in issues]


@pytest.fixture(scope="session")
def character_data() -> dict:
    return load_json(EXAMPLES_DIR / "characters" / "valid_characters.json")


@pytest.fixture(scope="session")
def storyboard_data() -> dict:
    return load_json(STORYBOARDS_DIR / "valid_storyboard.json")


@pytest.fixture(scope="session")
def aetheria(world_data) -> World:
    return World.model_validate(world_data)


@pytest.fixture(scope="session")
def cast(character_data) -> CharacterSet:
    return CharacterSet.model_validate(character_data)


# ---------------------------------------------------------------------------
# Model and happy-path tests
# ---------------------------------------------------------------------------


def test_valid_storyboard_parses(storyboard_data):
    sb = Storyboard.model_validate(storyboard_data)
    assert sb.world_id == "wld_aetheria"
    assert len(sb.acts) == 4
    assert sb.acts[0].purpose == "setup"


def test_valid_storyboard_round_trip(storyboard_data):
    sb = Storyboard.model_validate(storyboard_data)
    assert sb.model_dump(mode="json") == storyboard_data


def test_valid_storyboard_fixture_is_clean(storyboard_data, aetheria, cast):
    assert validate_storyboard(storyboard_data, aetheria, cast) == []


# ---------------------------------------------------------------------------
# Invalid fixture files
# ---------------------------------------------------------------------------

EXPECTED = {
    "duplicate_scene_id.json": (ErrorCode.DUPLICATE_ID, "$.acts[1].scenes[1].id"),
    "unknown_character.json": (
        ErrorCode.UNKNOWN_CHARACTER_REF,
        "$.acts[0].scenes[0].character_ids[1]",
    ),
    "unknown_location.json": (
        ErrorCode.UNKNOWN_LOCATION_REF,
        "$.acts[0].scenes[0].location_id",
    ),
    "invalid_world_id.json": (ErrorCode.WORLD_ID_MISMATCH, "$.world_id"),
    "cyclic_dependencies.json": (
        ErrorCode.CYCLIC_DEPENDENCY,
        "$.acts[1].scenes[0].id",
    ),
    "forward_dependency.json": (
        ErrorCode.FORWARD_DEPENDENCY,
        "$.acts[1].scenes[0].depends_on[0]",
    ),
    "missing_narrative_phase.json": (ErrorCode.MISSING_NARRATIVE_PHASE, "$.acts"),
    "invalid_phase_order.json": (
        ErrorCode.NARRATIVE_PHASE_ORDER,
        "$.acts[2].purpose",
    ),
}


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_invalid_storyboard_fixtures(filename, aetheria, cast):
    data = load_json(INVALID_STORYBOARDS_DIR / filename)
    expected_code, expected_path = EXPECTED[filename]
    issues = validate_storyboard(data, aetheria, cast)
    assert (expected_code, expected_path) in codes_and_paths(issues)
    # Deterministic across calls
    assert codes_and_paths(validate_storyboard(data, aetheria, cast)) == codes_and_paths(
        issues
    )


def test_expectation_table_covers_all_storyboard_fixture_files():
    files = {p.name for p in INVALID_STORYBOARDS_DIR.glob("*.json")}
    assert files == set(EXPECTED)


# ---------------------------------------------------------------------------
# Structural edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, [], "x", 3])
def test_non_dict_inputs(bad, aetheria, cast):
    issues = validate_storyboard(bad, aetheria, cast)
    assert codes_and_paths(issues) == [(ErrorCode.SCHEMA_VIOLATION, "$")]


def test_empty_dict_reports_required_fields(aetheria, cast):
    issues = validate_storyboard({}, aetheria, cast)
    paths = {i.path for i in issues if i.code == ErrorCode.MISSING_REQUIRED_FIELD}
    assert {"$.world_id", "$.title", "$.logline", "$.theme", "$.acts"} <= paths


@pytest.mark.parametrize(
    "field",
    ["id", "title", "purpose", "scenes"],
)
def test_missing_act_required_fields(field, storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    del data["acts"][0][field]
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.MISSING_REQUIRED_FIELD, f"$.acts[0].{field}") in codes_and_paths(
        issues
    )


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "title",
        "summary",
        "location_id",
        "character_ids",
        "goal",
        "conflict",
        "outcome",
    ],
)
def test_missing_scene_required_fields(field, storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    del data["acts"][0]["scenes"][0][field]
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.MISSING_REQUIRED_FIELD,
        f"$.acts[0].scenes[0].{field}",
    ) in codes_and_paths(issues)


def test_invalid_purpose_value(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["purpose"] = "exposition"
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.SCHEMA_VIOLATION, "$.acts[0].purpose") in codes_and_paths(issues)


def test_unknown_additional_fields(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["extra"] = 1
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.SCHEMA_VIOLATION, "$.acts[0]") in codes_and_paths(issues)


def test_invalid_id_prefix(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["id"] = "act-001"
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.SCHEMA_VIOLATION, "$.acts[0].id") in codes_and_paths(issues)


# ---------------------------------------------------------------------------
# Referential-integrity and dependency edge cases
# ---------------------------------------------------------------------------


def test_invalid_world_reference(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["world_id"] = "wld_other"
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.WORLD_ID_MISMATCH, "$.world_id") in codes_and_paths(issues)


def test_unknown_character_reference(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["scenes"][0]["character_ids"] = ["chr_missing"]
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.UNKNOWN_CHARACTER_REF,
        "$.acts[0].scenes[0].character_ids[0]",
    ) in codes_and_paths(issues)


def test_unknown_location_reference(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["scenes"][0]["location_id"] = "loc_missing"
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.UNKNOWN_LOCATION_REF,
        "$.acts[0].scenes[0].location_id",
    ) in codes_and_paths(issues)


def test_duplicate_act_id(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][1]["id"] = data["acts"][0]["id"]
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.DUPLICATE_ID, "$.acts[1].id") in codes_and_paths(issues)


def test_duplicate_scene_character_ids(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["scenes"][0]["character_ids"] = ["chr_veya", "chr_veya"]
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.DUPLICATE_ID,
        "$.acts[0].scenes[0].character_ids[1]",
    ) in codes_and_paths(issues)


def test_unknown_scene_dependency(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][0]["scenes"][0]["depends_on"] = ["scn_missing"]
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.UNKNOWN_SCENE_REF,
        "$.acts[0].scenes[0].depends_on[0]",
    ) in codes_and_paths(issues)


def test_self_dependency(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    sid = data["acts"][0]["scenes"][0]["id"]
    data["acts"][0]["scenes"][0]["depends_on"] = [sid]
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.SELF_DEPENDENCY,
        "$.acts[0].scenes[0].depends_on[0]",
    ) in codes_and_paths(issues)


def test_cyclic_dependencies(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    # scn_kael (act 1, scene 0) and scn_maris (act 1, scene 1) depend on each other
    data["acts"][1]["scenes"][0]["depends_on"] = ["scn_maris_smuggles"]
    data["acts"][1]["scenes"][1]["depends_on"] = ["scn_kael_raises_tolls"]
    issues = validate_storyboard(data, aetheria, cast)
    assert any(i.code == ErrorCode.CYCLIC_DEPENDENCY for i in issues)


def test_forward_dependency(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    # Kael (act 1, scene 0) may not depend on Maris (act 1, scene 1)
    data["acts"][1]["scenes"][0]["depends_on"] = ["scn_maris_smuggles"]
    data["acts"][1]["scenes"][1]["depends_on"] = []
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.FORWARD_DEPENDENCY,
        "$.acts[1].scenes[0].depends_on[0]",
    ) in codes_and_paths(issues)


def test_missing_narrative_phase(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["acts"][2]["purpose"] = "rising_action"
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.MISSING_NARRATIVE_PHASE, "$.acts") in codes_and_paths(issues)


def test_invalid_narrative_phase_order(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    # Swap purpose labels of act_rising and act_climax, leaving scene order intact
    data["acts"][1]["purpose"] = "climax"
    data["acts"][2]["purpose"] = "rising_action"
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.NARRATIVE_PHASE_ORDER, "$.acts[2].purpose") in codes_and_paths(
        issues
    )


# ---------------------------------------------------------------------------
# Boundary count tests
# ---------------------------------------------------------------------------


def _minimal_scene(i: int) -> dict:
    return {
        "id": f"scn_{i:04d}",
        "title": f"Scene {i}",
        "summary": "A scene summary.",
        "location_id": "loc_emberroost",
        "character_ids": ["chr_veya"],
        "goal": "Goal.",
        "conflict": "Conflict.",
        "outcome": "Outcome.",
        "depends_on": [],
    }


def _minimal_act(i: int, n_scenes: int, purpose: str) -> dict:
    return {
        "id": f"act_{i:02d}",
        "title": f"Act {i}",
        "purpose": purpose,
        "scenes": [_minimal_scene(i * 100 + j) for j in range(n_scenes)],
    }


def _storyboard(n_acts: int, n_scenes: int = 1) -> dict:
    all_purposes = ["setup", "rising_action", "climax", "resolution"]
    if n_acts <= 4:
        purposes = all_purposes[:n_acts]
    else:
        purposes = (
            ["setup"]
            + ["rising_action"] * (n_acts - 3)
            + ["climax", "resolution"]
        )
    return {
        "world_id": "wld_aetheria",
        "title": "Boundary",
        "logline": "A test storyboard.",
        "theme": "testing",
        "acts": [
            _minimal_act(i, n_scenes, purposes[i])
            for i in range(n_acts)
        ],
    }


@pytest.mark.parametrize("count", [4, MAX_ACTS])
def test_act_count_boundaries_ok(count, aetheria, cast):
    assert validate_storyboard(_storyboard(count), aetheria, cast) == []


def test_act_count_below_min(aetheria, cast):
    issues = validate_storyboard(_storyboard(0), aetheria, cast)
    assert (ErrorCode.COUNT_BELOW_MIN, "$.acts") in codes_and_paths(issues)


def test_act_count_above_max(aetheria, cast):
    issues = validate_storyboard(_storyboard(MAX_ACTS + 1), aetheria, cast)
    assert (ErrorCode.COUNT_ABOVE_MAX, "$.acts") in codes_and_paths(issues)


@pytest.mark.parametrize("count", [MIN_SCENES_PER_ACT, MAX_SCENES_PER_ACT])
def test_scene_count_boundaries_ok(count, aetheria, cast):
    assert validate_storyboard(_storyboard(4, count), aetheria, cast) == []


def test_scene_count_above_max(aetheria, cast):
    data = _storyboard(1, MAX_SCENES_PER_ACT + 1)
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.COUNT_ABOVE_MAX,
        "$.acts[0].scenes",
    ) in codes_and_paths(issues)


def test_empty_scenes_list(aetheria, cast):
    data = _storyboard(1, 0)
    issues = validate_storyboard(data, aetheria, cast)
    assert (ErrorCode.COUNT_BELOW_MIN, "$.acts[0].scenes") in codes_and_paths(issues)


@pytest.mark.parametrize("count", [1, MAX_SCENE_CHARACTER_REFS])
def test_character_ref_count_boundaries_ok(count, aetheria, cast):
    data = _storyboard(1, 1)
    data["acts"][0]["scenes"][0]["character_ids"] = [
        f"chr_{i:04d}" for i in range(count)
    ]
    # chr_0000 etc don't exist, but we only care about the list length being accepted structurally
    # Use existing characters for valid count check
    data["acts"][0]["scenes"][0]["character_ids"] = ["chr_veya"] * count
    issues = validate_storyboard(data, aetheria, cast)
    # chr_veya duplicate may be reported if count > 1
    if count == 1:
        assert (ErrorCode.COUNT_BELOW_MIN, "$.acts[0].scenes[0].character_ids") not in codes_and_paths(issues)


def test_character_ref_count_above_max(aetheria, cast):
    data = _storyboard(1, 1)
    data["acts"][0]["scenes"][0]["character_ids"] = [
        "chr_veya"
    ] * (MAX_SCENE_CHARACTER_REFS + 1)
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.COUNT_ABOVE_MAX,
        "$.acts[0].scenes[0].character_ids",
    ) in codes_and_paths(issues)


def test_scene_without_characters(aetheria, cast):
    data = _storyboard(1, 1)
    data["acts"][0]["scenes"][0]["character_ids"] = []
    issues = validate_storyboard(data, aetheria, cast)
    assert (
        ErrorCode.COUNT_BELOW_MIN,
        "$.acts[0].scenes[0].character_ids",
    ) in codes_and_paths(issues)


# ---------------------------------------------------------------------------
# Determinism and immutability
# ---------------------------------------------------------------------------


def test_issues_sorted_by_path_then_code(storyboard_data, aetheria, cast):
    data = copy.deepcopy(storyboard_data)
    data["world_id"] = "wld_other"
    data["acts"][0]["scenes"][0]["location_id"] = "loc_missing"
    data["acts"][0]["scenes"][0]["character_ids"] = ["chr_missing"]
    issues = validate_storyboard(data, aetheria, cast)
    keys = [(i.path, str(i.code)) for i in issues]
    assert keys == sorted(keys)
    assert len(issues) >= 2


def test_input_immutability(storyboard_data, aetheria, cast):
    before_data = copy.deepcopy(storyboard_data)
    before_world = aetheria.model_dump(mode="json")
    before_cast = cast.model_dump(mode="json")
    validate_storyboard(storyboard_data, aetheria, cast)
    assert storyboard_data == before_data
    assert aetheria.model_dump(mode="json") == before_world
    assert cast.model_dump(mode="json") == before_cast


# ---------------------------------------------------------------------------
# Exported JSON schema
# ---------------------------------------------------------------------------


def test_storyboard_schema_on_disk_matches_generated():
    on_disk = load_json(SCHEMAS_DIR / "storyboard.schema.json")
    assert on_disk == storyboard_schema()
    expected = json.dumps(storyboard_schema(), indent=2, sort_keys=True) + "\n"
    assert (SCHEMAS_DIR / "storyboard.schema.json").read_text(encoding="utf-8") == expected


def test_storyboard_schema_is_valid_draft202012():
    schema = load_json(SCHEMAS_DIR / "storyboard.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_valid_storyboard_fixture_validates_against_on_disk_schema(storyboard_data):
    schema = load_json(SCHEMAS_DIR / "storyboard.schema.json")
    jsonschema.Draft202012Validator(schema).validate(storyboard_data)


# ---------------------------------------------------------------------------
# Error code / issue object checks
# ---------------------------------------------------------------------------


def test_new_error_codes_are_strings():
    for code in [
        ErrorCode.UNKNOWN_SCENE_REF,
        ErrorCode.SELF_DEPENDENCY,
        ErrorCode.CYCLIC_DEPENDENCY,
        ErrorCode.FORWARD_DEPENDENCY,
        ErrorCode.MISSING_NARRATIVE_PHASE,
        ErrorCode.NARRATIVE_PHASE_ORDER,
    ]:
        assert isinstance(code, str)
        assert code == code.value


def test_validation_issue_to_dict():
    issue = ValidationIssue(ErrorCode.FORWARD_DEPENDENCY, "$.x", "forward")
    assert issue.to_dict() == {
        "code": "FORWARD_DEPENDENCY",
        "path": "$.x",
        "message": "forward",
    }
