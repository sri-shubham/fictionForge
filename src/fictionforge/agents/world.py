"""World Generation agent."""

from __future__ import annotations

import json
from typing import Any

from fictionforge.agents.base import REPO_ROOT, Agent, AgentError
from fictionforge.guardrails.validators import validate_world
from fictionforge.llm.base import LLMClient
from fictionforge.models import StoryBrief, World


class WorldGenerationError(AgentError):
    """The model returned output that does not satisfy the World contract."""

    def __init__(
        self,
        message: str,
        validation_issues: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.validation_issues = validation_issues or []


class WorldAgent(Agent):
    """Generate a structured :class:`World` from a :class:`StoryBrief`."""

    prompt_path = REPO_ROOT / "prompts" / "world.md"
    BRIEF_PLACEHOLDER = "{{STORY_BRIEF_JSON}}"

    def __init__(self, client: LLMClient, **kwargs: Any) -> None:
        super().__init__(client, **kwargs)

    def run(self, brief: StoryBrief) -> tuple[World, dict[str, Any]]:
        brief_json = json.dumps(brief.model_dump(mode="json"), indent=2, ensure_ascii=False)
        prompt = self._render(self.BRIEF_PLACEHOLDER, brief_json)

        try:
            response = self._call_llm(prompt)
        except Exception as exc:
            raise WorldGenerationError(f"World generation failed: {exc}") from exc

        text = self._extract_json(response.content)
        try:
            data = self._parse_json(text)
        except AgentError as exc:
            raise WorldGenerationError(f"Model output is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise WorldGenerationError(
                f"Expected a JSON object, got {type(data).__name__}"
            )

        issues = validate_world(data, brief)
        if issues:
            raise WorldGenerationError(
                f"Generated world failed validation with {len(issues)} issue(s)",
                [issue.to_dict() for issue in issues],
            )

        world = World.model_validate(data)
        metadata = {
            "latency_s": response.latency_s,
            "token_usage": response.token_usage,
            "raw_metadata": response.metadata,
        }
        return world, metadata


__all__ = ["WorldAgent", "WorldGenerationError"]
