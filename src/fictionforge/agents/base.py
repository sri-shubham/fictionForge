"""Base agent for LLM-driven generation."""

from __future__ import annotations

import abc
import json
import re
from pathlib import Path
from typing import Any

from fictionforge.llm.base import LLMClient, LLMError, LLMResponse


REPO_ROOT = Path(__file__).resolve().parents[3]


class AgentError(Exception):
    """Base error for agent failures."""


class Agent(abc.ABC):
    """Provider-agnostic, validator-backed agent skeleton."""

    prompt_path: Path

    def __init__(
        self,
        client: LLMClient,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._template = self.prompt_path.read_text(encoding="utf-8")

    @abc.abstractmethod
    def run(self, brief: Any) -> tuple[Any, dict[str, Any]]: ...

    def _render(self, placeholder: str, value: str) -> str:
        return self._template.replace(placeholder, value)

    def _call_llm(self, prompt: str) -> LLMResponse:
        return self.client.complete(
            prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            retries=self.max_retries,
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip Markdown fences and other wrapping noise."""
        text = text.strip()
        # Try to extract a fenced JSON block.
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fence:
            return fence.group(1).strip()
        return text

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentError(f"Model output is not valid JSON: {exc}") from exc


__all__ = ["Agent", "AgentError", "REPO_ROOT"]
