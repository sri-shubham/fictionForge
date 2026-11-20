"""Deterministic validation guardrails for world-generation artifacts.

Two-stage validation with stable, machine-readable error codes:

- Stage 1 (structural): the payload is checked against the JSON schema
  generated from the pydantic models (Draft 2020-12), then additionally
  through ``Model.model_validate`` to catch constraints JSON schema cannot
  express (e.g. whitespace-only strings).
- Stage 2 (semantic): identifier uniqueness and referential integrity
  (location / faction / character references), plus story-brief constraint
  enforcement for worlds.

All functions are pure and deterministic: no LLM, no I/O, and they never
raise for malformed input -- problems are reported as ``ValidationIssue``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Iterable

import jsonschema
from pydantic import BaseModel, ValidationError

from fictionforge.models import CharacterSet, Storyboard, StoryBrief, World
from fictionforge.schema_export import (
    brief_schema,
    character_schema,
    storyboard_schema,
    world_schema,
)


class ErrorCode(StrEnum):
    """Stable machine-readable validation error codes."""

    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    COUNT_BELOW_MIN = "COUNT_BELOW_MIN"
    COUNT_ABOVE_MAX = "COUNT_ABOVE_MAX"
    DUPLICATE_ID = "DUPLICATE_ID"
    UNKNOWN_LOCATION_REF = "UNKNOWN_LOCATION_REF"
    UNKNOWN_FACTION_REF = "UNKNOWN_FACTION_REF"
    BRIEF_CONSTRAINT_MALFORMED = "BRIEF_CONSTRAINT_MALFORMED"
    BRIEF_LOCATION_COUNT_MISMATCH = "BRIEF_LOCATION_COUNT_MISMATCH"
    BRIEF_LOCATIONS_BELOW_MIN = "BRIEF_LOCATIONS_BELOW_MIN"
    BRIEF_LOCATIONS_ABOVE_MAX = "BRIEF_LOCATIONS_ABOVE_MAX"
    BRIEF_FORBIDDEN_TERM = "BRIEF_FORBIDDEN_TERM"
    BRIEF_REQUIRED_TERM_MISSING = "BRIEF_REQUIRED_TERM_MISSING"
    # Character-design specific
    UNKNOWN_CHARACTER_REF = "UNKNOWN_CHARACTER_REF"
    WORLD_ID_MISMATCH = "WORLD_ID_MISMATCH"
    SELF_RELATIONSHIP = "SELF_RELATIONSHIP"
    DUPLICATE_RELATIONSHIP = "DUPLICATE_RELATIONSHIP"
    MISSING_PROTAGONIST = "MISSING_PROTAGONIST"
    # Storyboard-specific
    UNKNOWN_SCENE_REF = "UNKNOWN_SCENE_REF"
    SELF_DEPENDENCY = "SELF_DEPENDENCY"
    CYCLIC_DEPENDENCY = "CYCLIC_DEPENDENCY"
    FORWARD_DEPENDENCY = "FORWARD_DEPENDENCY"
    MISSING_NARRATIVE_PHASE = "MISSING_NARRATIVE_PHASE"
    NARRATIVE_PHASE_ORDER = "NARRATIVE_PHASE_ORDER"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single deterministic validation finding."""

    code: ErrorCode
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": str(self.code), "path": self.path, "message": self.message}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_path(loc: Iterable[object]) -> str:
    """Render a jsonschema/pydantic location tuple as a ``$``-path."""
    path = "$"
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _sorted(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return sorted(issues, key=lambda i: (i.path, str(i.code)))


@lru_cache(maxsize=1)
def _brief_validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(brief_schema())


@lru_cache(maxsize=1)
def _world_validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(world_schema())


@lru_cache(maxsize=1)
def _character_validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(character_schema())


@lru_cache(maxsize=1)
def _storyboard_validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(storyboard_schema())


def _structural_issues(
    data: object,
    validator: jsonschema.Draft202012Validator,
    model: type[BaseModel],
) -> list[ValidationIssue]:
    """Stage 1: JSON-schema + pydantic structural validation."""
    if not isinstance(data, dict):
        return [
            ValidationIssue(
                ErrorCode.SCHEMA_VIOLATION,
                "$",
                f"expected a JSON object, got {type(data).__name__}",
            )
        ]

    issues: list[ValidationIssue] = []
    reported_paths: set[str] = set()

    for error in validator.iter_errors(data):
        path = _json_path(error.absolute_path)
        if error.validator == "required":
            missing = sorted(set(error.validator_value) - set(error.instance)) or ["?"]
            for field in missing:
                issues.append(
                    ValidationIssue(
                        ErrorCode.MISSING_REQUIRED_FIELD,
                        f"{path}.{field}",
                        f"missing required field {field!r}",
                    )
                )
                reported_paths.add(f"{path}.{field}")
            continue
        if error.validator == "minItems":
            code = ErrorCode.COUNT_BELOW_MIN
            message = error.message
        elif error.validator == "maxItems":
            code = ErrorCode.COUNT_ABOVE_MAX
            message = error.message
        else:
            code = ErrorCode.SCHEMA_VIOLATION
            message = error.message
        issues.append(ValidationIssue(code, path, message))
        reported_paths.add(path)

    try:
        model.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            path = _json_path(err["loc"])
            if path in reported_paths:
                continue
            issues.append(
                ValidationIssue(ErrorCode.SCHEMA_VIOLATION, path, err["msg"])
            )
            reported_paths.add(path)

    return issues


# ---------------------------------------------------------------------------
# Stage 2: semantic checks on a structurally valid world
# ---------------------------------------------------------------------------


def _check_ref_list(
    ref_ids: list[str],
    known: set[str],
    base_path: str,
    unknown_code: ErrorCode,
    issues: list[ValidationIssue],
) -> None:
    seen: set[str] = set()
    for j, ref in enumerate(ref_ids):
        path = f"{base_path}[{j}]"
        if ref in seen:
            issues.append(
                ValidationIssue(
                    ErrorCode.DUPLICATE_ID, path, f"duplicate id {ref!r} in list"
                )
            )
        elif ref not in known:
            issues.append(
                ValidationIssue(
                    unknown_code, path, f"unknown reference {ref!r}"
                )
            )
        seen.add(ref)


def _semantic_issues(world: World) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    seen_ids: set[str] = set()

    def register(entity_id: str, path: str) -> None:
        if entity_id in seen_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.DUPLICATE_ID, path, f"duplicate id {entity_id!r}"
                )
            )
        seen_ids.add(entity_id)

    register(world.world_id, "$.world_id")
    collections = (
        ("locations", world.locations),
        ("factions", world.factions),
        ("rules", world.rules),
        ("history", world.history),
        ("conflicts", world.conflicts),
    )
    for name, items in collections:
        for i, item in enumerate(items):
            register(item.id, f"$.{name}[{i}].id")

    location_ids = {loc.id for loc in world.locations}
    faction_ids = {fac.id for fac in world.factions}

    for i, faction in enumerate(world.factions):
        _check_ref_list(
            faction.location_ids,
            location_ids,
            f"$.factions[{i}].location_ids",
            ErrorCode.UNKNOWN_LOCATION_REF,
            issues,
        )
    for i, event in enumerate(world.history):
        _check_ref_list(
            event.location_ids,
            location_ids,
            f"$.history[{i}].location_ids",
            ErrorCode.UNKNOWN_LOCATION_REF,
            issues,
        )
    for i, conflict in enumerate(world.conflicts):
        _check_ref_list(
            conflict.faction_ids,
            faction_ids,
            f"$.conflicts[{i}].faction_ids",
            ErrorCode.UNKNOWN_FACTION_REF,
            issues,
        )

    return issues


# ---------------------------------------------------------------------------
# Story-brief constraints
# ---------------------------------------------------------------------------

_DIRECTIVE_PREFIXES = ("forbid", "require", "min_locations", "max_locations")


@dataclass(frozen=True, slots=True)
class _Directive:
    kind: str
    value: object
    index: int


def parse_constraints(
    constraints: list[str],
) -> tuple[list[_Directive], list[ValidationIssue]]:
    """Parse machine-readable ``key:value`` constraints.

    Returns the parsed directives plus one ``BRIEF_CONSTRAINT_MALFORMED``
    issue per malformed known-prefix entry. Unrecognised entries are
    ignored (free text).
    """
    directives: list[_Directive] = []
    issues: list[ValidationIssue] = []

    def malformed(index: int, reason: str) -> None:
        issues.append(
            ValidationIssue(
                ErrorCode.BRIEF_CONSTRAINT_MALFORMED,
                f"$.constraints[{index}]",
                reason,
            )
        )

    for i, entry in enumerate(constraints):
        key, sep, payload = entry.partition(":")
        kind = key.strip().lower()
        if not sep or kind not in _DIRECTIVE_PREFIXES:
            continue
        payload = payload.strip()
        if kind in ("forbid", "require"):
            if not payload:
                malformed(i, f"directive {kind!r} requires non-empty text")
            else:
                directives.append(_Directive(kind, payload, i))
        else:
            try:
                value = int(payload)
            except ValueError:
                malformed(i, f"directive {kind!r} requires an integer, got {payload!r}")
                continue
            if value < 1:
                malformed(i, f"directive {kind!r} requires an integer >= 1, got {value}")
            else:
                directives.append(_Directive(kind, value, i))

    mins = [d for d in directives if d.kind == "min_locations"]
    maxs = [d for d in directives if d.kind == "max_locations"]
    if mins and maxs and min(d.value for d in mins) > max(d.value for d in maxs):
        issues.append(
            ValidationIssue(
                ErrorCode.BRIEF_CONSTRAINT_MALFORMED,
                f"$.constraints[{maxs[-1].index}]",
                "min_locations exceeds max_locations",
            )
        )

    return directives, issues


def _brief_self_issues(brief: StoryBrief, directives: list[_Directive]) -> list[ValidationIssue]:
    """Cross-check the brief's own ``location_count`` against its bounds."""
    issues: list[ValidationIssue] = []
    if brief.location_count is None:
        return issues
    for d in directives:
        if d.kind == "min_locations" and brief.location_count < d.value:
            issues.append(
                ValidationIssue(
                    ErrorCode.BRIEF_CONSTRAINT_MALFORMED,
                    "$.location_count",
                    f"location_count {brief.location_count} is below min_locations {d.value}",
                )
            )
        if d.kind == "max_locations" and brief.location_count > d.value:
            issues.append(
                ValidationIssue(
                    ErrorCode.BRIEF_CONSTRAINT_MALFORMED,
                    "$.location_count",
                    f"location_count {brief.location_count} is above max_locations {d.value}",
                )
            )
    return issues


def _world_text_fields(world: World) -> list[tuple[str, str]]:
    """All free-text fields scanned by forbid/require directives."""
    fields: list[tuple[str, str]] = [
        ("$.name", world.name),
        ("$.description", world.description),
    ]
    for i, loc in enumerate(world.locations):
        fields.append((f"$.locations[{i}].name", loc.name))
        fields.append((f"$.locations[{i}].description", loc.description))
    for i, fac in enumerate(world.factions):
        fields.append((f"$.factions[{i}].name", fac.name))
        fields.append((f"$.factions[{i}].description", fac.description))
    for i, rule in enumerate(world.rules):
        fields.append((f"$.rules[{i}].statement", rule.statement))
    for i, ev in enumerate(world.history):
        fields.append((f"$.history[{i}].name", ev.name))
        fields.append((f"$.history[{i}].description", ev.description))
        if ev.era is not None:
            fields.append((f"$.history[{i}].era", ev.era))
    for i, con in enumerate(world.conflicts):
        fields.append((f"$.conflicts[{i}].name", con.name))
        fields.append((f"$.conflicts[{i}].description", con.description))
    return fields


def _brief_world_issues(world: World, brief: StoryBrief) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    directives, malformed = parse_constraints(brief.constraints)
    issues.extend(malformed)

    count = len(world.locations)
    if brief.location_count is not None and brief.location_count != count:
        issues.append(
            ValidationIssue(
                ErrorCode.BRIEF_LOCATION_COUNT_MISMATCH,
                "$.locations",
                f"brief requires location_count {brief.location_count}, world has {count}",
            )
        )
    for d in directives:
        if d.kind == "min_locations" and count < d.value:
            issues.append(
                ValidationIssue(
                    ErrorCode.BRIEF_LOCATIONS_BELOW_MIN,
                    "$.locations",
                    f"world has {count} locations, below minimum {d.value}",
                )
            )
        elif d.kind == "max_locations" and count > d.value:
            issues.append(
                ValidationIssue(
                    ErrorCode.BRIEF_LOCATIONS_ABOVE_MAX,
                    "$.locations",
                    f"world has {count} locations, above maximum {d.value}",
                )
            )

    text_fields = _world_text_fields(world)
    for d in directives:
        term = str(d.value).lower()
        if d.kind == "forbid":
            for path, text in text_fields:
                if term in text.lower():
                    issues.append(
                        ValidationIssue(
                            ErrorCode.BRIEF_FORBIDDEN_TERM,
                            path,
                            f"field contains forbidden term {d.value!r}",
                        )
                    )
        elif d.kind == "require":
            if not any(term in text.lower() for _, text in text_fields):
                issues.append(
                    ValidationIssue(
                        ErrorCode.BRIEF_REQUIRED_TERM_MISSING,
                        "$",
                        f"required term {d.value!r} not found in any text field",
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# Stage 2: semantic checks on a structurally valid CharacterSet
# ---------------------------------------------------------------------------


def _character_semantic_issues(character_set: CharacterSet, world: World) -> list[ValidationIssue]:
    """Referential integrity, uniqueness, and protagonist checks.

    Note on ability validation: the World model does not currently expose
    machine-readable restrictions (e.g. ``forbid:supernatural`` or
    ``restrict:technology`` directives are not parsed into a semantic rule set).
    Therefore, supernatural/technological ability categories are accepted here.
    Qualitative or schema-evolution checks should handle those in the future.
    """
    issues: list[ValidationIssue] = []

    if character_set.world_id != world.world_id:
        issues.append(
            ValidationIssue(
                ErrorCode.WORLD_ID_MISMATCH,
                "$.world_id",
                (
                    f"character set references world {character_set.world_id!r}, "
                    f"expected {world.world_id!r}"
                ),
            )
        )

    location_ids = {loc.id for loc in world.locations}
    faction_ids = {fac.id for fac in world.factions}
    character_ids: set[str] = set()
    protagonist_found = False

    for i, c in enumerate(character_set.characters):
        if c.id in character_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.DUPLICATE_ID,
                    f"$.characters[{i}].id",
                    f"duplicate id {c.id!r}",
                )
            )
        character_ids.add(c.id)

        if c.home_location_id not in location_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.UNKNOWN_LOCATION_REF,
                    f"$.characters[{i}].home_location_id",
                    f"unknown location {c.home_location_id!r}",
                )
            )

        if c.faction_id is not None and c.faction_id not in faction_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.UNKNOWN_FACTION_REF,
                    f"$.characters[{i}].faction_id",
                    f"unknown faction {c.faction_id!r}",
                )
            )

        if c.role == "protagonist":
            protagonist_found = True

    if not protagonist_found:
        issues.append(
            ValidationIssue(
                ErrorCode.MISSING_PROTAGONIST,
                "$.characters",
                "at least one protagonist is required",
            )
        )

    seen_rel_ids: set[str] = set()
    seen_rel_keys: set[tuple[str, str, str]] = set()

    for i, r in enumerate(character_set.relationships):
        if r.id in seen_rel_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.DUPLICATE_ID,
                    f"$.relationships[{i}].id",
                    f"duplicate id {r.id!r}",
                )
            )
        seen_rel_ids.add(r.id)

        if r.source_character_id not in character_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.UNKNOWN_CHARACTER_REF,
                    f"$.relationships[{i}].source_character_id",
                    f"unknown character {r.source_character_id!r}",
                )
            )

        if r.target_character_id not in character_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.UNKNOWN_CHARACTER_REF,
                    f"$.relationships[{i}].target_character_id",
                    f"unknown character {r.target_character_id!r}",
                )
            )

        if r.source_character_id == r.target_character_id:
            issues.append(
                ValidationIssue(
                    ErrorCode.SELF_RELATIONSHIP,
                    f"$.relationships[{i}]",
                    "self-referential relationships are not supported",
                )
            )

        rel_key = (r.source_character_id, r.target_character_id, r.relationship_type)
        if rel_key in seen_rel_keys:
            issues.append(
                ValidationIssue(
                    ErrorCode.DUPLICATE_RELATIONSHIP,
                    f"$.relationships[{i}]",
                    "duplicate directed relationship of the same type",
                )
            )
        seen_rel_keys.add(rel_key)

    return issues


# ---------------------------------------------------------------------------
# Stage 2: semantic checks on a structurally valid Storyboard
# ---------------------------------------------------------------------------

_REQUIRED_PHASES = ("setup", "rising_action", "climax", "resolution")
_PHASE_ORDER = {phase: i for i, phase in enumerate(_REQUIRED_PHASES)}


def _storyboard_semantic_issues(
    storyboard: Storyboard,
    world: World,
    characters: CharacterSet,
) -> list[ValidationIssue]:
    """Referential integrity, uniqueness, dependency, and narrative phase checks."""
    issues: list[ValidationIssue] = []

    if storyboard.world_id != world.world_id:
        issues.append(
            ValidationIssue(
                ErrorCode.WORLD_ID_MISMATCH,
                "$.world_id",
                (
                    f"storyboard references world {storyboard.world_id!r}, "
                    f"expected {world.world_id!r}"
                ),
            )
        )

    # Act ID uniqueness
    seen_act_ids: set[str] = set()
    for i, act in enumerate(storyboard.acts):
        if act.id in seen_act_ids:
            issues.append(
                ValidationIssue(
                    ErrorCode.DUPLICATE_ID,
                    f"$.acts[{i}].id",
                    f"duplicate act id {act.id!r}",
                )
            )
        seen_act_ids.add(act.id)

    # Scene ID uniqueness and linear positions (first occurrence wins)
    seen_scene_ids: set[str] = set()
    duplicate_scene_ids: set[str] = set()
    scene_positions: dict[str, tuple[int, int, int]] = {}
    linear = 0
    for i, act in enumerate(storyboard.acts):
        for j, scene in enumerate(act.scenes):
            if scene.id in seen_scene_ids:
                duplicate_scene_ids.add(scene.id)
                issues.append(
                    ValidationIssue(
                        ErrorCode.DUPLICATE_ID,
                        f"$.acts[{i}].scenes[{j}].id",
                        f"duplicate scene id {scene.id!r}",
                    )
                )
            else:
                scene_positions[scene.id] = (i, j, linear)
            seen_scene_ids.add(scene.id)
            linear += 1

    location_ids = {loc.id for loc in world.locations}
    character_ids = {c.id for c in characters.characters}

    # Build the full dependency graph (known, non-self edges) for cycle detection
    graph: dict[str, list[str]] = {sid: [] for sid in seen_scene_ids}

    for i, act in enumerate(storyboard.acts):
        for j, scene in enumerate(act.scenes):
            if scene.id in duplicate_scene_ids:
                continue

            scene_path = f"$.acts[{i}].scenes[{j}]"

            # Location reference
            if scene.location_id not in location_ids:
                issues.append(
                    ValidationIssue(
                        ErrorCode.UNKNOWN_LOCATION_REF,
                        f"{scene_path}.location_id",
                        f"unknown location {scene.location_id!r}",
                    )
                )

            # Character references, including duplicates within a scene
            seen_chars: set[str] = set()
            for k, char_id in enumerate(scene.character_ids):
                char_path = f"{scene_path}.character_ids[{k}]"
                if char_id in seen_chars:
                    issues.append(
                        ValidationIssue(
                            ErrorCode.DUPLICATE_ID,
                            char_path,
                            f"duplicate character id {char_id!r} in scene",
                        )
                    )
                elif char_id not in character_ids:
                    issues.append(
                        ValidationIssue(
                            ErrorCode.UNKNOWN_CHARACTER_REF,
                            char_path,
                            f"unknown character {char_id!r}",
                        )
                    )
                seen_chars.add(char_id)

            # Scene dependencies: self, unknown, forward, and graph edges
            current_pos = scene_positions[scene.id][2]
            for k, dep in enumerate(scene.depends_on):
                dep_path = f"{scene_path}.depends_on[{k}]"
                if dep == scene.id:
                    issues.append(
                        ValidationIssue(
                            ErrorCode.SELF_DEPENDENCY,
                            dep_path,
                            f"scene {scene.id!r} depends on itself",
                        )
                    )
                    continue
                if dep not in seen_scene_ids:
                    issues.append(
                        ValidationIssue(
                            ErrorCode.UNKNOWN_SCENE_REF,
                            dep_path,
                            f"unknown scene {dep!r}",
                        )
                    )
                    continue
                # Record edge even if forward, so cycles can be detected.
                graph[scene.id].append(dep)
                dep_pos = scene_positions[dep][2]
                if dep_pos >= current_pos:
                    issues.append(
                        ValidationIssue(
                            ErrorCode.FORWARD_DEPENDENCY,
                            dep_path,
                            f"dependency {dep!r} must reference an earlier scene",
                        )
                    )

    # Cycle detection over the full dependency graph (Kosaraju's SCCs)
    scene_order = list(scene_positions.keys())

    visited: set[str] = set()
    finish: list[str] = []
    for start in scene_order:
        if start in visited:
            continue
        stack = [(start, 0)]
        while stack:
            node, idx = stack[-1]
            if node not in visited:
                visited.add(node)
            if idx < len(graph[node]):
                child = graph[node][idx]
                stack[-1] = (node, idx + 1)
                if child not in visited:
                    stack.append((child, 0))
            else:
                finish.append(node)
                stack.pop()

    transpose: dict[str, list[str]] = {sid: [] for sid in graph}
    for sid, deps in graph.items():
        for dep in deps:
            transpose[dep].append(sid)

    assigned: set[str] = set()
    cyclic: set[str] = set()
    for start in reversed(finish):
        if start in assigned:
            continue
        component: list[str] = []
        stack = [start]
        while stack:
            node = stack.pop()
            if node in assigned:
                continue
            assigned.add(node)
            component.append(node)
            for child in transpose[node]:
                if child not in assigned:
                    stack.append(child)
        if len(component) > 1:
            cyclic.update(component)
    for i, act in enumerate(storyboard.acts):
        for j, scene in enumerate(act.scenes):
            if scene.id in cyclic:
                issues.append(
                    ValidationIssue(
                        ErrorCode.CYCLIC_DEPENDENCY,
                        f"$.acts[{i}].scenes[{j}].id",
                        f"scene {scene.id!r} is part of a dependency cycle",
                    )
                )

    # Narrative phase progression: all required phases, in non-decreasing order
    phases = [act.purpose for act in storyboard.acts]
    present = set(phases)
    missing = set(_REQUIRED_PHASES) - present
    if missing:
        issues.append(
            ValidationIssue(
                ErrorCode.MISSING_NARRATIVE_PHASE,
                "$.acts",
                f"missing narrative phase(s): {sorted(missing)}",
            )
        )

    prev = -1
    for i, phase in enumerate(phases):
        order = _PHASE_ORDER.get(phase, -1)
        if order < prev:
            issues.append(
                ValidationIssue(
                    ErrorCode.NARRATIVE_PHASE_ORDER,
                    f"$.acts[{i}].purpose",
                    f"narrative phase {phase!r} is out of order",
                )
            )
            break
        prev = order

    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_brief(data: object) -> list[ValidationIssue]:
    """Validate a story-brief payload; returns sorted issues (empty = valid)."""
    issues = _structural_issues(data, _brief_validator(), StoryBrief)
    if issues:
        return _sorted(issues)
    brief = StoryBrief.model_validate(data)
    directives, malformed = parse_constraints(brief.constraints)
    issues.extend(malformed)
    issues.extend(_brief_self_issues(brief, directives))
    return _sorted(issues)


def validate_world(data: object, brief: StoryBrief | None = None) -> list[ValidationIssue]:
    """Validate a world payload, optionally against a parsed ``StoryBrief``."""
    issues = _structural_issues(data, _world_validator(), World)
    if issues:
        return _sorted(issues)
    world = World.model_validate(data)
    issues.extend(_semantic_issues(world))
    if brief is not None:
        issues.extend(_brief_world_issues(world, brief))
    return _sorted(issues)


def validate_characters(
    data: object,
    world: World,
    brief: StoryBrief | None = None,
) -> list[ValidationIssue]:
    """Validate a CharacterSet payload against a parsed ``World``.

    The optional ``brief`` is accepted for API symmetry but is not used; the
    CharacterSet is checked against the supplied World contract only.
    """
    issues = _structural_issues(data, _character_validator(), CharacterSet)
    if issues:
        return _sorted(issues)
    character_set = CharacterSet.model_validate(data)
    issues.extend(_character_semantic_issues(character_set, world))
    return _sorted(issues)


def validate_storyboard(
    data: object,
    world: World,
    characters: CharacterSet,
    brief: StoryBrief | None = None,
) -> list[ValidationIssue]:
    """Validate a Storyboard payload against a parsed ``World`` and ``CharacterSet``.

    The optional ``brief`` is accepted for API symmetry; the storyboard is
    checked against the supplied World and CharacterSet contracts only.
    """
    issues = _structural_issues(data, _storyboard_validator(), Storyboard)
    if issues:
        return _sorted(issues)
    storyboard = Storyboard.model_validate(data)
    issues.extend(_storyboard_semantic_issues(storyboard, world, characters))
    return _sorted(issues)


__all__ = [
    "ErrorCode",
    "ValidationIssue",
    "parse_constraints",
    "validate_brief",
    "validate_characters",
    "validate_storyboard",
    "validate_world",
]
