"""Ollama-backed LLM client using only the standard library."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from fictionforge.llm.base import LLMClient, LLMError, LLMResponse


class OllamaClient(LLMClient):
    """Call an Ollama server over the chat completion endpoint.

    The client forces JSON output, tracks token counts when the server
    reports them, and never invents a fallback response.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        default_timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_timeout = default_timeout

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
        """Send a chat request and parse the JSON output."""
        chosen = model or self.model
        body: dict[str, Any] = {
            "model": chosen,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens

        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        deadline = timeout if timeout is not None else self.default_timeout
        last_err: BaseException | None = None

        for attempt in range(retries + 1):
            t0 = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=deadline) as response:
                    raw = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_err = exc
                if attempt < retries and exc.code >= 500:
                    self._backoff(attempt)
                    continue
                raise LLMError(
                    f"Ollama HTTP {exc.code}: {exc.reason} for model {chosen!r}"
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = exc
                if attempt < retries:
                    self._backoff(attempt)
                    continue
                raise LLMError(
                    f"Ollama request failed for model {chosen!r}: {exc}"
                ) from exc

            latency = time.monotonic() - t0
            try:
                content = raw["message"]["content"]
            except (KeyError, TypeError) as exc:
                raise LLMError(
                    "Ollama response missing 'message.content'"
                ) from exc

            prompt_tokens = raw.get("prompt_eval_count")
            completion_tokens = raw.get("eval_count")
            token_usage: dict[str, int] | None = None
            if prompt_tokens is not None or completion_tokens is not None:
                token_usage = {
                    "prompt_tokens": prompt_tokens or 0,
                    "completion_tokens": completion_tokens or 0,
                    "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
                }

            return LLMResponse(
                content=content,
                token_usage=token_usage,
                latency_s=round(latency, 3),
                metadata={
                    "model": raw.get("model"),
                    "created_at": raw.get("created_at"),
                    "done": raw.get("done"),
                },
            )

        # Defensive: should have raised inside the loop.
        raise LLMError(f"Ollama request failed after retries: {last_err}")

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(2 ** attempt, 8))


__all__ = ["OllamaClient"]
