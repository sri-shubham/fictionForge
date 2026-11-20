"""Character Design agent."""

from __future__ import annotations

import json
from typing import Any

from fictionforge.agents.base import REPO_ROOT, Agent, AgentError
from fictionforge.guardrails.validators import validate_characters
from fictionforge.llm.base import LLMClient
from fictionforge.models import CharacterSet, StoryBrief, World


class CharacterDesignError(AgentError):
    """The model returned output that does not satisfy the CharacterSet contract."""

    def __init__(
        self,
        message: str,
        validation_issues: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.validation_issues = validation_issues or []


class CharacterAgent(Agent):
    """Generate a structured :class:`CharacterSet` from a :class:`StoryBrief` and :class:`World`."""

    prompt_path = REPO_ROOT / "prompts" / "characters.md"
    BRIEF_PLACEHOLDER = "{{STORY_BRIEF_JSON}}"
    WORLD_PLACEHOLDER = "{{WORLD_JSON}}"

    def __init__(self, client: LLMClient, **kwargs: Any) -> None:
        super().__init__(client, **kwargs)

    def run(self, brief: StoryBrief, world: World) -> tuple[CharacterSet, dict[str, Any]]:
        brief_json = json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False)
        world_json = json.dumps(world.model_dump(mode="json"), indent=2, ensure_ascii=False)

        prompt = self._template.replace(self.BRIEF_PLACEHOLDER, brief_json)
        prompt = prompt.replace(self.WORLD_PLACEHOLDER, world_json)

        try:
            response = self._call_llm(prompt)
        except Exception as exc:
            raise CharacterDesignError(f"Character design failed: {exc}") from exc

        text = self._extract_json(response.content)
        try:
            data = self._parse_json(text)
        except AgentError as exc:
            raise CharacterDesignError(f"Model output is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise CharacterDesignError(
                f"Expected a JSON object, got {type(data).__name__}"
            )

        issues = validate_characters(data, world, brief)
        if issues:
            raise CharacterDesignError(
                f"Generated character set failed validation with {len(issues)} issue(s)",
                [issue.to_dict() for issue in issues],
            )

        character_set = CharacterSet.model_validate(data)
        metadata = {
            "latency_s": response.latency_s,
            "token_usage": response.token_usage,
            "raw_metadata": response.metadata,
        }
        return character_set, metadata


__all__ = ["CharacterAgent", "CharacterDesignError"]
