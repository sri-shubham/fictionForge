"""Stage 3 Promptfoo provider for Storyboard Building: world_provider behaviour plus raw-output capture.

Generation and grading calls go through the same Devin CLI client and the same
JSON extraction as ``world_provider.py``. The only addition is that the
unmodified model text is returned in ``metadata["raw_output"]`` so the
``format_discipline`` assertion can check "JSON only" against what the model
actually said, not against the extracted JSON.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
for p in (str(REPO_ROOT / "src"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fictionforge.llm.devin import DevinCliClient, LLMError
from world_provider import _extract_json


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    config = options.get("config", {})
    client = DevinCliClient(
        model=config.get("model", "swe"),
        cli_timeout=config.get("devin_timeout", 180.0),
        respect_workspace_trust=config.get("respect_workspace_trust", False),
    )
    kwargs = {k: config[k] for k in ("temperature", "retries") if k in config}
    try:
        response = client.complete(prompt, **kwargs)
    except LLMError as exc:
        return {"error": str(exc), "output": f"{exc}"}

    raw = response.content
    extracted = _extract_json(raw)
    return {
        "output": extracted if extracted is not None else raw,
        "metadata": {
            "raw_output": raw,
            "latency_s": response.latency_s,
            "token_usage": response.token_usage,
        },
    }
