"""Shared fixtures and loaders for the world-generation test suite."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from fictionforge.llm.base import LLMResponse

# Binaries that would reach a live model or the network.  Tests must never
# call them; a MockClient is the only allowed "model".
# ``node`` is deliberately not blocked: it is a script runtime (an existing
# offline test uses it to render nunjucks) and cannot reach a model on its
# own -- the socket guard below already blocks any network egress.
_BLOCKED_ARGV0 = {"devin", "ollama", "claude", "promptfoo", "npx"}


@pytest.fixture(autouse=True)
def _no_live_model_or_network(monkeypatch):
    """Fail loudly if any test tries a real model call or network access."""

    def _blocked_connect(*args, **kwargs):
        raise RuntimeError(
            "network access is not allowed in tests (socket.socket.connect)"
        )

    def _blocked_call(fn_name):
        def _check(argv, *args, **kwargs):
            import os

            argv0 = argv[0] if isinstance(argv, (list, tuple)) else argv
            base = os.path.basename(str(argv0))
            if base in _BLOCKED_ARGV0:
                raise RuntimeError(
                    f"test attempted to invoke a live-model binary: {base!r}"
                )
            return _ORIG[fn_name](argv, *args, **kwargs)

        return _check

    _ORIG = {"run": subprocess.run, "Popen": subprocess.Popen}
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(subprocess, "run", _blocked_call("run"))
    monkeypatch.setattr(subprocess, "Popen", _blocked_call("Popen"))
    yield

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
SCHEMAS_DIR = REPO_ROOT / "schemas"
WORLDS_DIR = EXAMPLES_DIR / "worlds"
INVALID_WORLDS_DIR = WORLDS_DIR / "invalid"
CHARACTERS_DIR = EXAMPLES_DIR / "characters"
STORYBOARDS_DIR = EXAMPLES_DIR / "storyboards"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def brief_data() -> dict:
    return load_json(EXAMPLES_DIR / "story_brief.json")


@pytest.fixture(scope="session")
def world_data() -> dict:
    return load_json(WORLDS_DIR / "valid_world.json")


@pytest.fixture(scope="session")
def brief(brief_data):
    from fictionforge.models import StoryBrief

    return StoryBrief.model_validate(brief_data)


@pytest.fixture(scope="session")
def invalid_world_files() -> list[Path]:
    return sorted(INVALID_WORLDS_DIR.glob("*.json"))


@pytest.fixture(scope="session")
def characters_data() -> dict:
    return load_json(CHARACTERS_DIR / "valid_characters.json")


@pytest.fixture(scope="session")
def storyboard_data() -> dict:
    return load_json(STORYBOARDS_DIR / "valid_storyboard.json")


class MockClient:
    """Test-only LLM client that returns a canned sequence of responses."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        if not self.responses:
            raise RuntimeError("MockClient ran out of responses")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(content=str(item))


@pytest.fixture
def mock_client():
    def _make(responses: list[Any] | None = None):
        return MockClient(responses or [])
    return _make
