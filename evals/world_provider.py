"""Promptfoo provider that invokes the Devin CLI for world generation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Make the local source tree importable from this provider file.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fictionforge.llm.devin import DevinCliClient, LLMError


def _extract_json(text: str) -> str | None:
    """Pull the first valid JSON object/array out of a possibly noisy response."""
    text = text.strip()

    # 1. Markdown code fence (json or no language).
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # 2. First bare JSON object/array using a simple nesting walk.
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start == -1:
        return None

    stack: list[str] = []
    in_string = False
    escape = False
    for j, ch in enumerate(text[start:]):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
            if not stack:
                return text[start : start + j + 1]
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
            if not stack:
                return text[start : start + j + 1]

    return None


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Generate a world by passing the prompt to the Devin CLI."""
    config = options.get("config", {})

    # `timeout` in this config is the promptfoo Python-worker timeout (ms).
    # `devin_timeout` is the per-CLI-call timeout in seconds.
    client = DevinCliClient(
        model=config.get("model", "swe"),
        cli_timeout=config.get("devin_timeout", 180.0),
        respect_workspace_trust=config.get("respect_workspace_trust", False),
    )

    kwargs = {
        k: config[k]
        for k in ("temperature", "retries")
        if k in config
    }

    try:
        response = client.complete(prompt, **kwargs)
    except LLMError as exc:
        return {"error": str(exc), "output": f"{exc}"}

    raw = response.content
    extracted = _extract_json(raw)
    output = extracted if extracted is not None else raw
    return {"output": output}
