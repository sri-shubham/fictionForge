"""Data contracts for the FictionForge world-generation stage.

Defines the input contract (``StoryBrief``) and output contract (``World``)
for the World Generation agent. All entity identifiers are prefixed,
machine-checkable strings so downstream agents can cross-reference them
deterministically.

Machine-readable story-brief constraints
----------------------------------------
``StoryBrief.constraints`` entries are free text by default. An entry that
starts with a known directive prefix (``key:value``) is machine-readable and
is enforced by :mod:`fictionforge.guardrails.validators`:

- ``forbid:<text>``        -- ``<text>`` must not appear in any world
  name/description/statement field (case-insensitive substring).
- ``require:<text>``       -- ``<text>`` must appear in at least one world
  name/description/statement field.
- ``min_locations:<int>``  -- the world must contain at least ``<int>`` locations.
- ``max_locations:<int>``  -- the world must contain at most ``<int>`` locations.

Any other entry is treated as an unenforceable free-text restriction.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# ---------------------------------------------------------------------------
# Shared scalar types
# ---------------------------------------------------------------------------

_MAX_ID_BODY = 48

# Collection bounds (single source of truth; JSON schema derives from these).
MIN_LOCATIONS = 1
MAX_LOCATIONS = 25
MAX_FACTIONS = 15
MIN_RULES = 1
MAX_RULES = 25
MAX_HISTORY_EVENTS = 40
MAX_CONFLICTS = 15
MAX_LOCATION_REFS = 25
MAX_FACTION_REFS = 15
MIN_LOCATION_COUNT = 1
MAX_LOCATION_COUNT = 50
MAX_CONSTRAINTS = 50

# Character/relationship bounds
MIN_CHARACTERS = 1
MAX_CHARACTERS = 20
MIN_RELATIONSHIPS = 0
MAX_RELATIONSHIPS = 100
MAX_ABILITIES = 10
MAX_TRAITS = 20


def _entity_id(prefix: str) -> Any:
    """Build a constrained identifier type with a mandatory ``prefix_``."""
    return Annotated[
        str,
        StringConstraints(pattern=rf"^{prefix}_[a-z0-9_]{{1,{_MAX_ID_BODY}}}$"),
    ]


WorldId = _entity_id("wld")
LocationId = _entity_id("loc")
FactionId = _entity_id("fac")
RuleId = _entity_id("rul")
EventId = _entity_id("evt")
ConflictId = _entity_id("cnf")
CharacterId = _entity_id("chr")
RelationshipId = _entity_id("rel")

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
MediumText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class FictionForgeModel(BaseModel):
    """Base model: strict types, no undeclared fields, trimmed strings."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Story brief (World Generation input)
# ---------------------------------------------------------------------------

ConstraintText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class StoryBrief(FictionForgeModel):
    """Commissioning brief describing the desired world."""

    title: ShortText | None = Field(
        default=None, description="Optional working title for the story."
    )
    premise: LongText = Field(
        description="Required, non-empty summary of the story premise."
    )
    genre: ShortText = Field(description="Primary genre of the story.")
    tone: ShortText = Field(description="Desired narrative tone.")
    target_audience: ShortText | None = Field(
        default=None, description="Optional intended audience."
    )
    constraints: list[ConstraintText] = Field(
        default_factory=list,
        max_length=MAX_CONSTRAINTS,
        description=(
            "Explicit world restrictions. Entries beginning with a known "
            "directive prefix (forbid:, require:, min_locations:, "
            "max_locations:) are machine-readable and enforced by guardrails."
        ),
    )
    location_count: int | None = Field(
        default=None,
        ge=MIN_LOCATION_COUNT,
        le=MAX_LOCATION_COUNT,
        description="Optional exact number of locations the world must define.",
    )


# ---------------------------------------------------------------------------
# World artifact (World Generation output)
# ---------------------------------------------------------------------------

RuleCategory = Literal["physics", "metaphysics", "social", "technology", "other"]


class Location(FictionForgeModel):
    """A distinct place in the world."""

    id: LocationId
    name: ShortText
    description: MediumText


class Faction(FictionForgeModel):
    """A group or power bloc, optionally tied to locations."""

    id: FactionId
    name: ShortText
    description: MediumText
    location_ids: list[LocationId] = Field(
        default_factory=list,
        max_length=MAX_LOCATION_REFS,
        description="Identifiers of locations this faction is associated with.",
    )


class WorldRule(FictionForgeModel):
    """An invariant rule or restriction of the world."""

    id: RuleId
    statement: MediumText = Field(
        description="The rule expressed as a single declarative statement."
    )
    category: RuleCategory = Field(default="other")


class HistoricalEvent(FictionForgeModel):
    """A notable event in the world's past."""

    id: EventId
    name: ShortText
    description: MediumText
    era: ShortText | None = Field(default=None)
    location_ids: list[LocationId] = Field(
        default_factory=list,
        max_length=MAX_LOCATION_REFS,
        description="Identifiers of locations where the event took place.",
    )


class Conflict(FictionForgeModel):
    """An active source of tension in the world."""

    id: ConflictId
    name: ShortText
    description: MediumText
    faction_ids: list[FactionId] = Field(
        default_factory=list,
        max_length=MAX_FACTION_REFS,
        description="Identifiers of factions involved in the conflict.",
    )


class World(FictionForgeModel):
    """Structured world artifact produced by the World Generation agent."""

    world_id: WorldId
    name: ShortText
    description: LongText
    locations: list[Location] = Field(min_length=MIN_LOCATIONS, max_length=MAX_LOCATIONS)
    factions: list[Faction] = Field(default_factory=list, max_length=MAX_FACTIONS)
    rules: list[WorldRule] = Field(min_length=MIN_RULES, max_length=MAX_RULES)
    history: list[HistoricalEvent] = Field(default_factory=list, max_length=MAX_HISTORY_EVENTS)
    conflicts: list[Conflict] = Field(default_factory=list, max_length=MAX_CONFLICTS)


# ---------------------------------------------------------------------------
# Character artifact (Character Design output)
# ---------------------------------------------------------------------------

CharacterRole = Literal["protagonist", "antagonist", "supporting"]

AbilityCategory = Literal[
    "physical", "mental", "social", "supernatural", "technological", "other"
]


class CharacterAbility(FictionForgeModel):
    """A structured capability, skill, or power belonging to a character."""

    name: ShortText = Field(description="Name of the ability.")
    description: MediumText = Field(description="What the ability allows.")
    category: AbilityCategory = Field(
        default="other",
        description="Machine-readable ability category for downstream guardrails.",
    )


class Character(FictionForgeModel):
    """A story character with role, motivation, conflicts, and development arc."""

    id: CharacterId = Field(description="Unique identifier; chr_ prefix.")
    name: ShortText = Field(description="Non-empty character name.")
    role: CharacterRole = Field(
        description="Narrative role: protagonist, antagonist, or supporting."
    )
    description: LongText = Field(
        description="Character background, identity, and look."
    )
    personality_traits: list[ShortText] = Field(
        default_factory=list,
        max_length=MAX_TRAITS,
        description="Traits that define personality.",
    )
    motivation: MediumText = Field(description="Primary driving motivation.")
    goal: MediumText = Field(description="Concrete objective.")
    flaw: MediumText = Field(description="Internal weakness.")
    internal_conflict: MediumText = Field(description="Personal struggle.")
    external_conflict: MediumText = Field(description="External opposition.")
    home_location_id: LocationId = Field(
        description="Home or primary location; must exist in the referenced world."
    )
    faction_id: FactionId | None = Field(
        default=None,
        description="Optional faction; must exist in the referenced world.",
    )
    abilities: list[CharacterAbility] = Field(
        default_factory=list,
        max_length=MAX_ABILITIES,
        description="Structured abilities or skills.",
    )
    arc: LongText = Field(description="Character development arc summary.")


class CharacterRelationship(FictionForgeModel):
    """A directed relationship between two characters."""

    id: RelationshipId = Field(description="Unique identifier; rel_ prefix.")
    source_character_id: CharacterId = Field(description="Subject of the relationship.")
    target_character_id: CharacterId = Field(description="Object of the relationship.")
    relationship_type: ShortText = Field(
        description="Type such as friend, enemy, ally, rival, mentor."
    )
    description: MediumText = Field(description="Nature of the relationship.")
    conflict: MediumText | None = Field(
        default=None,
        description="Optional source of tension in the relationship.",
    )


class CharacterSet(FictionForgeModel):
    """Complete set of characters and their relationships for a given world."""

    world_id: WorldId = Field(description="References the source world.")
    characters: list[Character] = Field(
        min_length=MIN_CHARACTERS,
        max_length=MAX_CHARACTERS,
        description="Characters who inhabit the world.",
    )
    relationships: list[CharacterRelationship] = Field(
        default_factory=list,
        max_length=MAX_RELATIONSHIPS,
        description="Directed relationships between characters.",
    )


# ---------------------------------------------------------------------------
# Storyboard artifact (Storyboard Building output)
# ---------------------------------------------------------------------------

NarrativePhase = Literal["setup", "rising_action", "climax", "resolution"]

ActId = _entity_id("act")
SceneId = _entity_id("scn")

# Storyboard bounds (single source of truth; JSON schema derives from these).
MIN_ACTS = 1
MAX_ACTS = 10
MIN_SCENES_PER_ACT = 1
MAX_SCENES_PER_ACT = 25
MIN_SCENE_CHARACTER_REFS = 1
MAX_SCENE_CHARACTER_REFS = 10
MAX_SCENE_DEPENDENCIES = 10


class Scene(FictionForgeModel):
    """A single narrative beat within an act."""

    id: SceneId
    title: ShortText
    summary: MediumText
    location_id: LocationId
    character_ids: list[CharacterId] = Field(
        min_length=MIN_SCENE_CHARACTER_REFS,
        max_length=MAX_SCENE_CHARACTER_REFS,
        description="Participating characters; at least one required.",
    )
    goal: MediumText
    conflict: MediumText
    outcome: MediumText
    depends_on: list[SceneId] = Field(
        default_factory=list,
        max_length=MAX_SCENE_DEPENDENCIES,
        description="Preceding scene IDs this scene depends on.",
    )


class Act(FictionForgeModel):
    """A major division of the storyboard with a narrative purpose."""

    id: ActId
    title: ShortText
    purpose: NarrativePhase = Field(description="Narrative purpose of the act.")
    scenes: list[Scene] = Field(
        min_length=MIN_SCENES_PER_ACT,
        max_length=MAX_SCENES_PER_ACT,
        description="Ordered scenes that make up the act.",
    )


class Storyboard(FictionForgeModel):
    """Complete narrative outline for the story-writing workflow."""

    world_id: WorldId = Field(description="References the source world.")
    title: ShortText
    logline: MediumText
    theme: ShortText
    acts: list[Act] = Field(
        min_length=MIN_ACTS,
        max_length=MAX_ACTS,
        description="Ordered acts that make up the story.",
    )


__all__ = [
    "AbilityCategory",
    "Act",
    "ActId",
    "Character",
    "CharacterAbility",
    "CharacterId",
    "CharacterRelationship",
    "CharacterRole",
    "CharacterSet",
    "Conflict",
    "ConflictId",
    "ConstraintText",
    "EventId",
    "Faction",
    "FactionId",
    "FictionForgeModel",
    "HistoricalEvent",
    "Location",
    "LocationId",
    "LongText",
    "MAX_ABILITIES",
    "MAX_ACTS",
    "MAX_CHARACTERS",
    "MAX_RELATIONSHIPS",
    "MAX_SCENE_CHARACTER_REFS",
    "MAX_SCENE_DEPENDENCIES",
    "MAX_SCENES_PER_ACT",
    "MAX_TRAITS",
    "MediumText",
    "MIN_ACTS",
    "MIN_CHARACTERS",
    "MIN_RELATIONSHIPS",
    "MIN_SCENE_CHARACTER_REFS",
    "MIN_SCENES_PER_ACT",
    "NarrativePhase",
    "RelationshipId",
    "RuleCategory",
    "RuleId",
    "Scene",
    "SceneId",
    "ShortText",
    "StoryBrief",
    "Storyboard",
    "World",
    "WorldId",
    "WorldRule",
]
