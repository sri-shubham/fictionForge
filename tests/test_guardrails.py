"""Tests for the deterministic world/brief validation guardrails."""

from __future__ import annotations

import copy

import pytest

from conftest import INVALID_WORLDS_DIR, load_json
from fictionforge.guardrails.validators import (
    ErrorCode,
    ValidationIssue,
    validate_brief,
    validate_world,
)
from fictionforge.models import StoryBrief


def codes_and_paths(issues):
    return [(i.code, i.path) for i in issues]


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_valid_brief_clean(brief_data):
    assert validate_brief(brief_data) == []


def test_valid_world_clean(world_data):
    assert validate_world(world_data) == []


def test_valid_world_clean_with_brief(world_data, brief):
    assert validate_world(world_data, brief) == []


# ---------------------------------------------------------------------------
# Invalid fixture files (parametrized expectation table)
# ---------------------------------------------------------------------------

EXPECTED = {
    "missing_required_field.json": (ErrorCode.MISSING_REQUIRED_FIELD, "$.name"),
    "empty_locations.json": (ErrorCode.COUNT_BELOW_MIN, "$.locations"),
    "too_many_locations.json": (ErrorCode.COUNT_ABOVE_MAX, "$.locations"),
    "duplicate_location_id.json": (ErrorCode.DUPLICATE_ID, "$.locations[1].id"),
    "duplicate_cross_type_id.json": (
        ErrorCode.DUPLICATE_ID,
        "$.factions[0].location_ids[2]",
    ),
    "unknown_faction_location.json": (
        ErrorCode.UNKNOWN_LOCATION_REF,
        "$.factions[0].location_ids[0]",
    ),
    "unknown_event_location.json": (
        ErrorCode.UNKNOWN_LOCATION_REF,
        "$.history[0].location_ids[0]",
    ),
    "unknown_conflict_faction.json": (
        ErrorCode.UNKNOWN_FACTION_REF,
        "$.conflicts[0].faction_ids[0]",
    ),
    "bad_id_format.json": (ErrorCode.SCHEMA_VIOLATION, "$.locations[0].id"),
    "extra_field.json": (ErrorCode.SCHEMA_VIOLATION, "$"),
    "whitespace_only_name.json": (ErrorCode.SCHEMA_VIOLATION, "$.name"),
    "wrong_type.json": (ErrorCode.SCHEMA_VIOLATION, "$.locations"),
}


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_invalid_world_fixtures(filename):
    data = load_json(INVALID_WORLDS_DIR / filename)
    expected_code, expected_path = EXPECTED[filename]
    issues = validate_world(data)
    assert (expected_code, expected_path) in codes_and_paths(issues)
    # Deterministic across calls
    assert codes_and_paths(validate_world(data)) == codes_and_paths(issues)


def test_expectation_table_covers_all_fixture_files():
    files = {p.name for p in INVALID_WORLDS_DIR.glob("*.json")}
    assert files == set(EXPECTED)


# ---------------------------------------------------------------------------
# Stage 1 structural edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, [], "x", 3])
def test_non_dict_inputs(bad):
    issues = validate_world(bad)
    assert codes_and_paths(issues) == [(ErrorCode.SCHEMA_VIOLATION, "$")]
    issues = validate_brief(bad)
    assert codes_and_paths(issues) == [(ErrorCode.SCHEMA_VIOLATION, "$")]


def test_empty_dict_reports_each_required_field():
    issues = validate_world({})
    paths = {i.path for i in issues if i.code == ErrorCode.MISSING_REQUIRED_FIELD}
    assert {"$.world_id", "$.name", "$.description", "$.locations", "$.rules"} <= paths


def test_empty_brief_reports_required_fields():
    issues = validate_brief({})
    paths = {i.path for i in issues if i.code == ErrorCode.MISSING_REQUIRED_FIELD}
    assert {"$.premise", "$.genre", "$.tone"} <= paths


# ---------------------------------------------------------------------------
# Boundary counts through the guardrails
# ---------------------------------------------------------------------------


def _boundary_world(n_locations: int, n_rules: int = 1) -> dict:
    return {
        "world_id": "wld_bound",
        "name": "Boundary",
        "description": "Boundary test world.",
        "locations": [
            {"id": f"loc_{i:02d}", "name": f"Place {i}", "description": "d"}
            for i in range(n_locations)
        ],
        "rules": [{"id": f"rul_{i:02d}", "statement": "s"} for i in range(n_rules)],
        "factions": [
            {
                "id": "fac_all",
                "name": "Everyone",
                "description": "Present everywhere.",
                "location_ids": [f"loc_{i:02d}" for i in range(min(n_locations, 25))],
            }
        ],
    }


def test_25_locations_passes_guardrails():
    assert validate_world(_boundary_world(25)) == []


def test_26_locations_count_above_max():
    issues = validate_world(_boundary_world(26))
    assert (ErrorCode.COUNT_ABOVE_MAX, "$.locations") in codes_and_paths(issues)


def test_zero_rules_count_below_min():
    issues = validate_world(_boundary_world(1, n_rules=0))
    assert (ErrorCode.COUNT_BELOW_MIN, "$.rules") in codes_and_paths(issues)


# ---------------------------------------------------------------------------
# Brief constraint parsing (validate_brief)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "constraints,expected_path",
    [
        (["min_locations:abc"], "$.constraints[0]"),
        (["max_locations:0"], "$.constraints[0]"),
        (["forbid:"], "$.constraints[0]"),
        (["require:  "], "$.constraints[0]"),
        (["min_locations:5", "max_locations:2"], "$.constraints[1]"),
        (["max_locations:6"], "$.location_count"),  # location_count=10 below
    ],
)
def test_malformed_constraints(constraints, expected_path):
    data = {
        "premise": "A voyage among drifting isles.",
        "genre": "fantasy",
        "tone": "wondrous",
        "location_count": 10,
        "constraints": constraints,
    }
    issues = validate_brief(data)
    assert (ErrorCode.BRIEF_CONSTRAINT_MALFORMED, expected_path) in codes_and_paths(
        issues
    )


def test_free_text_constraint_ignored():
    data = {
        "premise": "A voyage among drifting isles.",
        "genre": "fantasy",
        "tone": "wondrous",
        "constraints": ["Keep names lyrical.", "forbid dragons entirely"],
    }
    assert validate_brief(data) == []


# ---------------------------------------------------------------------------
# Brief constraint enforcement on worlds (validate_world with brief)
# ---------------------------------------------------------------------------


def _brief(**overrides) -> StoryBrief:
    data = {
        "premise": "A voyage among drifting isles.",
        "genre": "fantasy",
        "tone": "wondrous",
    }
    data.update(overrides)
    return StoryBrief.model_validate(data)


def test_forbidden_term_in_description(world_data):
    brief = _brief(constraints=["forbid:cartel"])
    issues = validate_world(world_data, brief)
    pairs = codes_and_paths(issues)
    assert all(c == ErrorCode.BRIEF_FORBIDDEN_TERM for c, _ in pairs)
    assert len(pairs) > 1


def test_forbidden_term_case_insensitive_in_rule(world_data):
    world = copy.deepcopy(world_data)
    world["rules"][0]["statement"] = "Gunpowder is unknown in Aetheria."
    brief = _brief(constraints=["forbid:gunpowder"])
    issues = validate_world(world, brief)
    assert (ErrorCode.BRIEF_FORBIDDEN_TERM, "$.rules[0].statement") in codes_and_paths(
        issues
    )


def test_required_term_missing(world_data):
    brief = _brief(constraints=["require:aardvark"])
    issues = validate_world(world_data, brief)
    assert (ErrorCode.BRIEF_REQUIRED_TERM_MISSING, "$") in codes_and_paths(issues)


def test_required_term_present(world_data):
    brief = _brief(constraints=["require:skybridge"])
    assert validate_world(world_data, brief) == []


def test_location_count_mismatch(world_data):
    brief = _brief(location_count=7)
    issues = validate_world(world_data, brief)
    assert (ErrorCode.BRIEF_LOCATION_COUNT_MISMATCH, "$.locations") in codes_and_paths(
        issues
    )


def test_locations_below_min(world_data):
    brief = _brief(constraints=["min_locations:5"])
    issues = validate_world(world_data, brief)
    assert (ErrorCode.BRIEF_LOCATIONS_BELOW_MIN, "$.locations") in codes_and_paths(
        issues
    )


def test_locations_above_max(world_data):
    brief = _brief(constraints=["max_locations:2"])
    issues = validate_world(world_data, brief)
    assert (ErrorCode.BRIEF_LOCATIONS_ABOVE_MAX, "$.locations") in codes_and_paths(
        issues
    )


def test_free_text_constraint_ignored_on_world(world_data):
    brief = _brief(constraints=["Everything should feel melancholy."])
    assert validate_world(world_data, brief) == []


def test_brief_none_skips_brief_checks(world_data):
    assert validate_world(world_data, None) == validate_world(world_data) == []


# ---------------------------------------------------------------------------
# Issue object / code stability
# ---------------------------------------------------------------------------


def test_error_code_values_match_names():
    for code in ErrorCode:
        assert code.value == code.name
    assert len({c.value for c in ErrorCode}) == len(ErrorCode)


def test_validation_issue_to_dict():
    issue = ValidationIssue(ErrorCode.DUPLICATE_ID, "$.x", "dup")
    assert issue.to_dict() == {
        "code": "DUPLICATE_ID",
        "path": "$.x",
        "message": "dup",
    }


def test_issues_sorted_by_path_then_code():
    world = copy.deepcopy(load_json(INVALID_WORLDS_DIR / "duplicate_location_id.json"))
    issues = validate_world(world)
    keys = [(i.path, str(i.code)) for i in issues]
    assert keys == sorted(keys)
