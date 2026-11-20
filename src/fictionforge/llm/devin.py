"""Devin CLI wrapper for model invocation.

Session-aware cost accounting: every CLI execution produces an *invocation
record* carrying a unique internal ``invocation_id``, the Devin session ID
recovered from the ATIF ``--export`` payload (never scraped from stdout),
token metrics, exit status and timing.  Invocation records are surfaced on
``LLMResponse.metadata["invocations"]`` and, on failure, on
``LLMError.invocations`` so the audit trail can attribute every model call —
including provider failures and retries — to a real Devin session.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fictionforge.llm.base import LLMClient, LLMError, LLMResponse


def _new_invocation_id() -> str:
    return f"inv-{uuid.uuid4().hex[:12]}"


def classify_session_id(session_id: str | None) -> str | None:
    """Classify a Devin session ID as ``local_cli`` or ``cloud``.

    Local CLI sessions use human-readable word-pair IDs (e.g.
    ``pushy-dumpling``); Devin Cloud sessions use ``devin-*`` IDs.  A local
    CLI session ID must never be treated as a Cloud session ID.
    """
    if not session_id:
        return None
    if session_id.startswith("devin-"):
        return "cloud"
    return "local_cli"


class DevinCliClient(LLMClient):
    """Invoke a model through the local ``devin`` CLI.

    This is useful when the evaluation must route through Devin's
    own model access, credentialing, and workspace controls rather
    than a raw HTTP API. The client never fabricates responses.

    When the CLI is called with ``--export``, it writes an ATIF
    conversation export containing ``session_id``, ``agent.model_name``
    and ``final_metrics`` with token counts.  The client parses those
    fields and exposes them in ``LLMResponse.token_usage`` and the
    invocation records in ``LLMResponse.metadata``.

    When ``export_dir`` is set, each ATIF export is preserved at
    ``<export_dir>/<invocation_id>.atif.json`` instead of a deleted temp
    file, so session metadata survives for later cost reconciliation.
    """

    provider = "devin"
    session_type = "local_cli"

    def __init__(
        self,
        *,
        model: str = "swe",
        cli_timeout: float = 180.0,
        respect_workspace_trust: bool = False,
        export_dir: Path | str | None = None,
        redact_exports: bool = True,
    ) -> None:
        self.model = model
        self.cli_timeout = cli_timeout
        self.respect_workspace_trust = respect_workspace_trust
        self.export_dir = Path(export_dir) if export_dir is not None else None
        self.redact_exports = redact_exports
        self._devin = shutil.which("devin") or "devin"

    # ------------------------------------------------------------------
    # ATIF export parsing
    # ------------------------------------------------------------------

    @staticmethod
    def parse_atif_data(data: dict[str, Any]) -> dict[str, Any]:
        """Extract session/usage/consumption fields from a parsed ATIF doc."""
        result: dict[str, Any] = {
            "session_id": None,
            "schema_version": data.get("schema_version"),
            "agent": data.get("agent") if isinstance(data.get("agent"), dict) else None,
            "final_metrics": None,
            "token_usage": None,
            "component_usage": [],
            "models_used": [],
            "billed_acus": None,
        }
        session_id = data.get("session_id")
        if isinstance(session_id, str) and session_id:
            result["session_id"] = session_id

        metrics = data.get("final_metrics")
        if isinstance(metrics, dict):
            result["final_metrics"] = metrics
            prompt = metrics.get("total_prompt_tokens")
            completion = metrics.get("total_completion_tokens")
            if prompt is not None or completion is not None:
                prompt = prompt or 0
                completion = completion or 0
                result["token_usage"] = {
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "total_tokens": prompt + completion,
                }

        # Per-step component accounting: each agent step records the model
        # that actually served it (relevant for Fusion main/sidekick splits),
        # its token metrics, and its committed ACU cost — real per-component
        # data, so no model split is ever invented.
        components: list[dict[str, Any]] = []
        models: set[str] = set()
        total_acu = 0.0
        saw_acu = False
        for step in data.get("steps") or []:
            if not isinstance(step, dict):
                continue
            extra = step.get("extra") or {}
            step_metrics = step.get("metrics") or {}
            model_name = step.get("model_name") or extra.get("generation_model")
            acu = extra.get("committed_acu_cost")
            if model_name is None and acu is None and not step_metrics:
                continue
            components.append(
                {
                    "step_id": step.get("step_id"),
                    "source": step.get("source"),
                    "model_name": model_name,
                    "generation_model": extra.get("generation_model"),
                    "sidekick_model": extra.get("sidekick_model"),
                    "prompt_tokens": step_metrics.get("prompt_tokens"),
                    "completion_tokens": step_metrics.get("completion_tokens"),
                    "cached_tokens": step_metrics.get("cached_tokens"),
                    "committed_acu_cost": acu,
                }
            )
            if model_name:
                models.add(model_name)
            gen = extra.get("generation_model")
            if gen:
                models.add(gen)
            if isinstance(acu, (int, float)):
                total_acu += acu
                saw_acu = True
        result["component_usage"] = components
        result["models_used"] = sorted(models)
        if saw_acu:
            result["billed_acus"] = total_acu
        return result

    @staticmethod
    def _parse_atif_export(export_path: Path) -> dict[str, Any]:
        """Parse a Devin ATIF export into structured session metadata.

        Returns a dict with ``status`` (``"ok"`` or ``"unavailable"``),
        ``reason`` (when unavailable), plus the fields produced by
        :meth:`parse_atif_data` and the file ``sha256``.
        """
        try:
            raw = export_path.read_bytes()
        except OSError:
            return {
                "status": "unavailable",
                "reason": "export_not_written",
                "session_id": None,
            }
        if not raw.strip():
            return {
                "status": "unavailable",
                "reason": "export_empty",
                "session_id": None,
            }
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {
                "status": "unavailable",
                "reason": "export_unparseable",
                "session_id": None,
            }
        if not isinstance(data, dict):
            return {
                "status": "unavailable",
                "reason": "export_unparseable",
                "session_id": None,
            }

        result = DevinCliClient.parse_atif_data(data)
        result["sha256"] = hashlib.sha256(raw).hexdigest()
        if result["session_id"] is None:
            result["status"] = "unavailable"
            result["reason"] = "export_missing_session_id"
        else:
            result["status"] = "ok"
            result["reason"] = None
        return result

    @staticmethod
    def redact_atif_data(data: dict[str, Any]) -> dict[str, Any]:
        """Return a redacted ATIF doc safe to persist outside the ZIP.

        Drops ``agent.tool_definitions`` (large, content-free for accounting)
        and replaces step ``message``/``tool_calls`` content with hashes so
        prompts and model output are never persisted unredacted.  Session,
        model, token and cost fields are preserved verbatim.
        """
        out = dict(data)
        agent = dict(out.get("agent") or {})
        tools = agent.pop("tool_definitions", None)
        if tools is not None:
            agent["tool_definition_count"] = (
                len(tools) if isinstance(tools, list) else None
            )
        out["agent"] = agent
        steps = []
        for step in out.get("steps") or []:
            if not isinstance(step, dict):
                continue
            s = dict(step)
            msg = s.pop("message", None)
            if msg is not None:
                raw = json.dumps(msg, ensure_ascii=False, sort_keys=True)
                s["message_sha256"] = hashlib.sha256(
                    raw.encode("utf-8")
                ).hexdigest()
            calls = s.pop("tool_calls", None)
            if calls is not None:
                s["tool_call_count"] = (
                    len(calls) if isinstance(calls, list) else None
                )
            steps.append(s)
        out["steps"] = steps
        out["redacted"] = True
        return out

    # ------------------------------------------------------------------
    # Invocation bookkeeping
    # ------------------------------------------------------------------

    def _export_path_for(self, invocation_id: str) -> tuple[Path, bool]:
        """Return (path, persistent) for this invocation's ATIF export."""
        if self.export_dir is not None:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            return self.export_dir / f"{invocation_id}.atif.json", True
        # Path only — do not pre-create, so "export_not_written" is
        # distinguishable from an empty export.
        return (
            Path(tempfile.gettempdir()) / f"ff-export-{invocation_id}.atif",
            False,
        )

    def _new_invocation(
        self,
        invocation_id: str,
        cli_index: int,
        model: str,
        export_path: Path,
        persistent: bool,
    ) -> dict[str, Any]:
        return {
            "invocation_id": invocation_id,
            "cli_invocation_index": cli_index,
            "provider": self.provider,
            "model": model,
            "session_type": self.session_type,
            "devin_session_id": None,
            "session_id_status": "pending",
            "session_id_reason": None,
            "export_path": str(export_path) if persistent else None,
            "export_sha256": None,
            "export_schema_version": None,
            "agent": None,
            "returncode": None,
            "duration_s": None,
            "token_usage": None,
            "final_metrics": None,
            "billed_acus": None,
            "component_usage": None,
            "models_used": None,
            "export_redacted": False,
            "raw_export_sha256": None,
            "io_path": None,
            "error": None,
        }

    @staticmethod
    def _redact_export_file(export_path: Path) -> str | None:
        """Rewrite an ATIF export in place, redacted.  Returns new sha256."""
        try:
            data = json.loads(export_path.read_bytes())
        except Exception:
            return None
        redacted = json.dumps(
            DevinCliClient.redact_atif_data(data),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        try:
            export_path.write_bytes(redacted)
        except OSError:
            return None
        return hashlib.sha256(redacted).hexdigest()

    @staticmethod
    def _record_export(invocation: dict[str, Any], parsed: dict[str, Any]) -> None:
        invocation["export_sha256"] = parsed.get("sha256")
        invocation["export_schema_version"] = parsed.get("schema_version")
        invocation["agent"] = parsed.get("agent")
        invocation["final_metrics"] = parsed.get("final_metrics")
        invocation["token_usage"] = parsed.get("token_usage")
        invocation["billed_acus"] = parsed.get("billed_acus")
        invocation["component_usage"] = parsed.get("component_usage")
        invocation["models_used"] = parsed.get("models_used")
        session_id = parsed.get("session_id")
        if session_id:
            invocation["devin_session_id"] = session_id
            invocation["session_type"] = classify_session_id(session_id)
            invocation["session_id_status"] = "captured"
            invocation["session_id_reason"] = None
        else:
            invocation["session_id_status"] = "unavailable"
            invocation["session_id_reason"] = parsed.get("reason")

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float | None = None,
        retries: int = 0,
        invocation_id: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        chosen = model or self.model
        deadline = timeout if timeout is not None else self.cli_timeout
        last_err: BaseException | None = None
        invocations: list[dict[str, Any]] = []

        for attempt in range(retries + 1):
            t0 = time.monotonic()
            inv_id = (
                invocation_id
                if attempt == 0 and invocation_id
                else _new_invocation_id()
            )
            export_path: Path | None = None
            persistent = False
            prompt_path: str | None = None
            invocation: dict[str, Any] | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False
                ) as f:
                    f.write(prompt)
                    prompt_path = f.name

                export_path, persistent = self._export_path_for(inv_id)
                invocation = self._new_invocation(
                    inv_id, attempt, chosen, export_path, persistent
                )
                invocations.append(invocation)

                cmd = [
                    self._devin,
                    "--model",
                    chosen,
                    "--prompt-file",
                    prompt_path,
                    "-p",
                    "--export",
                    str(export_path),
                ]
                if not self.respect_workspace_trust:
                    cmd.extend(["--respect-workspace-trust", "false"])

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=deadline,
                )

                invocation["duration_s"] = round(time.monotonic() - t0, 3)
                invocation["returncode"] = proc.returncode
                self._record_export(invocation, self._parse_atif_export(export_path))
                if persistent and self.redact_exports:
                    red_sha = self._redact_export_file(export_path)
                    if red_sha:
                        invocation["raw_export_sha256"] = invocation[
                            "export_sha256"
                        ]
                        invocation["export_sha256"] = red_sha
                        invocation["export_redacted"] = True

                if proc.returncode != 0:
                    invocation["error"] = proc.stderr.strip()[:1000]
                    raise LLMError(
                        f"devin CLI exited {proc.returncode}: {proc.stderr.strip()}",
                        invocations=invocations,
                    )

                content = proc.stdout
                if not content:
                    invocation["error"] = "empty_output"
                    raise LLMError(
                        "devin CLI returned empty output",
                        invocations=invocations,
                    )

                if persistent and self.export_dir is not None:
                    io_path = self.export_dir / f"{inv_id}.io.json"
                    try:
                        io_path.write_text(
                            json.dumps(
                                {
                                    "invocation_id": inv_id,
                                    "model": chosen,
                                    "prompt": prompt,
                                    "output": content,
                                },
                                ensure_ascii=False,
                                indent=2,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                        invocation["io_path"] = str(io_path)
                    except OSError:
                        pass

                return LLMResponse(
                    content=content,
                    token_usage=invocation["token_usage"],
                    latency_s=invocation["duration_s"],
                    metadata={
                        "model": chosen,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "export_path": invocation["export_path"],
                        "invocation": invocation,
                        "invocations": invocations,
                    },
                )

            except (subprocess.TimeoutExpired, FileNotFoundError, LLMError) as exc:
                if invocation is not None and invocation["duration_s"] is None:
                    invocation["duration_s"] = round(time.monotonic() - t0, 3)
                    if invocation["error"] is None:
                        invocation["error"] = type(exc).__name__
                if (
                    invocation is not None
                    and invocation["session_id_status"] == "pending"
                ):
                    # A partially written export may still carry a session ID.
                    self._record_export(
                        invocation, self._parse_atif_export(export_path)
                    )
                    if invocation["session_id_status"] == "pending":
                        invocation["session_id_status"] = "unavailable"
                    if invocation["session_id_reason"] is None:
                        invocation["session_id_reason"] = (
                            "cli_timeout"
                            if isinstance(exc, subprocess.TimeoutExpired)
                            else "cli_failed_before_export"
                        )
                last_err = exc
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                if isinstance(exc, LLMError):
                    raise
                raise LLMError(
                    f"devin CLI request failed: {exc}", invocations=invocations
                ) from exc
            finally:
                if prompt_path:
                    try:
                        os.unlink(prompt_path)
                    except OSError:
                        pass
                if export_path is not None and not persistent:
                    try:
                        os.unlink(export_path)
                    except OSError:
                        pass

        raise LLMError(
            f"devin CLI request failed after retries: {last_err}",
            invocations=invocations,
        )


__all__ = ["DevinCliClient", "classify_session_id"]
