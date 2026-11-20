"""Provider-agnostic LLM client interface."""

from __future__ import annotations

import abc
import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class LLMResponse:
    """A completed model response with optional telemetry."""

    content: str
    token_usage: dict[str, int] | None = None
    latency_s: float | None = None
    metadata: dict[str, Any] | None = None


class LLMError(Exception):
    """Raised when the model cannot return a genuine response.

    ``invocations`` carries per-execution telemetry records (session IDs,
    export paths, exit status) captured by CLI-backed providers before the
    failure, so audit trails can attribute failed calls to real sessions.
    """

    def __init__(
        self,
        message: str,
        *,
        invocations: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.invocations = invocations


class LLMClient(abc.ABC):
    """Abstract, testable LLM client."""

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float | None = None,
        retries: int = 0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call the model and return a structured response.

        Implementations must never silently fabricate output. Any
        failure (timeout, malformed response, network error) raises
        :class:`LLMError`.
        """


__all__ = ["LLMClient", "LLMError", "LLMResponse"]
