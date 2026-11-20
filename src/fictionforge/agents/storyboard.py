"""Storyboard Building agent."""

from __future__ import annotations

import json
from typing import Any

from fictionforge.agents.base import REPO_ROOT, Agent, AgentError
from fictionforge.guardrails.validators import validate_storyboard
from fictionforge.llm.base import LLMClient
from fictionforge.models import CharacterSet, StoryBrief, Storyboard, World


class StoryboardBuildingError(AgentError):
    """The model returned output that does not satisfy the Storyboard contract."""

    def __init__(
        self,
        message: str,
        validation_issues: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.validation_issues = validation_issues or []


class StoryboardAgent(Agent):
    """Generate a structured :class:`Storyboard` from a :class:`StoryBrief`, :class:`World`, and :class:`CharacterSet`."""

    prompt_path = REPO_ROOT / "prompts" / "storyboard.md"
    BRIEF_PLACEHOLDER = "{{STORY_BRIEF_JSON}}"
    WORLD_PLACEHOLDER = "{{WORLD_JSON}}"
    CHARACTER_PLACEHOLDER = "{{CHARACTER_SET_JSON}}"

    def __init__(self, client: LLMClient, **kwargs: Any) -> None:
        super().__init__(client, **kwargs)

    def run(
        self,
        brief: StoryBrief,
        world: World,
        characters: CharacterSet,
    ) -> tuple[Storyboard, dict[str, Any]]:
        brief_json = json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False)
        world_json = json.dumps(world.model_dump(mode="json"), indent=2, ensure_ascii=False)
        character_json = json.dumps(
            characters.model_dump(mode="json"), indent=2, ensure_ascii=False
        )

        prompt = self._template.replace(self.BRIEF_PLACEHOLDER, brief_json)
        prompt = prompt.replace(self.WORLD_PLACEHOLDER, world_json)
        prompt = prompt.replace(self.CHARACTER_PLACEHOLDER, character_json)

        try:
            response = self._call_llm(prompt)
        except Exception as exc:
            raise StoryboardBuildingError(f"Storyboard building failed: {exc}") from exc

        text = self._extract_json(response.content)
        try:
            data = self._parse_json(text)
        except AgentError as exc:
            raise StoryboardBuildingError(f"Model output is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise StoryboardBuildingError(
                f"Expected a JSON object, got {type(data).__name__}"
            )

        issues = validate_storyboard(data, world, characters, brief)
        if issues:
            raise StoryboardBuildingError(
                f"Generated storyboard failed validation with {len(issues)} issue(s)",
                [issue.to_dict() for issue in issues],
            )

        storyboard = Storyboard.model_validate(data)
        metadata = {
            "latency_s": response.latency_s,
            "token_usage": response.token_usage,
            "raw_metadata": response.metadata,
        }
        return storyboard, metadata


__all__ = ["StoryboardAgent", "StoryboardBuildingError"]
