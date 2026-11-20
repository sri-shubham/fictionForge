"""Session-level consumption retrieval for FictionForge cost accounting.

Sources, strongest first:

1. ``atif_export`` — the per-invocation ATIF export captured by
   :class:`~fictionforge.llm.devin.DevinCliClient`.  Each ``complete()``
   call creates its own headless Devin session, so the export's committed
   ACU cost and per-step model/token data are authoritative *for that
   invocation*.
2. ``devin_sessions_db`` — the local CLI session store
   (``~/.local/share/devin/cli/sessions.db``), opened read-only.  It reports
   session-lifetime ``total_acu_cost`` / ``total_credit_cost`` keyed by the
   real local session ID.  Scope is the whole session lifetime: a resumed
   session accumulates across invocations, so totals are labelled
   ``session_lifetime`` and never silently attributed to one call.
3. Cloud/REST consumption endpoints — not implemented here: they require
   credentials that are not configured, and local CLI session IDs are not
   valid Cloud session IDs.

ACUs and USD are kept as separate units.  ACUs are never converted into
USD; ``actual_usd`` stays ``None`` unless a source reports dollars
directly.  ``estimated_usd`` is only produced by the pricing-snapshot path
(Phase 3), never guessed here.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = (
    Path.home() / ".local" / "share" / "devin" / "cli" / "sessions.db"
)


@dataclass
class SessionConsumption:
    """Consumption reported for one Devin session/invocation."""

    session_id: str | None
    session_type: str | None
    source: str | None  # "atif_export" | "devin_sessions_db"
    scope: str | None  # "invocation" | "session_lifetime"
    status: str  # "actual" | "unavailable"
    billed_acus: float | None = None
    credit_cost: float | None = None
    component_usage: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "source": self.source,
            "scope": self.scope,
            "status": self.status,
            "billed_acus": self.billed_acus,
            "credit_cost": self.credit_cost,
            "component_usage": self.component_usage,
            "reason": self.reason,
        }


def _unavailable(
    session_id: str | None,
    session_type: str | None,
    source: str | None,
    reason: str,
) -> SessionConsumption:
    return SessionConsumption(
        session_id=session_id,
        session_type=session_type,
        source=source,
        scope=None,
        status="unavailable",
        reason=reason,
    )


def consumption_from_parsed(
    parsed: dict[str, Any],
    *,
    session_type: str | None = None,
) -> SessionConsumption:
    """Build a consumption record from a parsed ATIF export.

    ``parsed`` is the output of
    :meth:`fictionforge.llm.devin.DevinCliClient.parse_atif_data` (or
    ``_parse_atif_export``).
    """
    session_id = parsed.get("session_id")
    acus = parsed.get("billed_acus")
    return SessionConsumption(
        session_id=session_id,
        session_type=session_type,
        source="atif_export",
        scope="invocation",
        status="actual" if acus is not None else "unavailable",
        billed_acus=acus,
        component_usage=list(parsed.get("component_usage") or []),
        reason=None if acus is not None else "export_missing_acu_cost",
    )


def consumption_from_export(
    export_path: Path,
    *,
    session_type: str | None = None,
) -> SessionConsumption:
    """Parse a persisted ATIF export file into a consumption record."""
    from fictionforge.llm.devin import DevinCliClient

    parsed = DevinCliClient._parse_atif_export(Path(export_path))
    if parsed.get("status") != "ok" and parsed.get("session_id") is None:
        return _unavailable(
            None, session_type, "atif_export",
            parsed.get("reason") or "export_unparseable",
        )
    return consumption_from_parsed(parsed, session_type=session_type)


def sessions_db_path() -> Path:
    """Path to the local CLI session store (env-overridable for tests)."""
    root = os.environ.get("DEVIN_CLI_DATA_DIR")
    if root:
        return Path(root) / "sessions.db"
    return DEFAULT_DB_PATH


def consumption_from_sessions_db(
    session_id: str,
    db_path: Path | None = None,
) -> SessionConsumption:
    """Read session-lifetime ACU/credit totals from the local CLI store.

    Read-only (``mode=ro``), bounded timeout, never fabricates a row.
    """
    db = Path(db_path) if db_path is not None else sessions_db_path()
    if not db.exists():
        return _unavailable(
            session_id, "local_cli", "devin_sessions_db", "sessions_db_missing"
        )
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
        try:
            row = conn.execute(
                "SELECT metadata, model, backend_type FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return _unavailable(
            session_id, "local_cli", "devin_sessions_db", "sessions_db_unreadable"
        )
    if row is None:
        return _unavailable(
            session_id, "local_cli", "devin_sessions_db", "session_not_found"
        )
    try:
        meta = json.loads(row[0] or "{}")
    except (json.JSONDecodeError, TypeError):
        return _unavailable(
            session_id, "local_cli", "devin_sessions_db", "metadata_unparseable"
        )
    acus = meta.get("total_acu_cost")
    credit = meta.get("total_credit_cost")
    if acus is None and credit is None:
        return _unavailable(
            session_id, "local_cli", "devin_sessions_db",
            "consumption_not_reported",
        )
    return SessionConsumption(
        session_id=session_id,
        session_type="local_cli",
        source="devin_sessions_db",
        scope="session_lifetime",
        status="actual",
        billed_acus=acus,
        credit_cost=credit,
    )


def collect_consumption(
    *,
    session_id: str | None = None,
    session_type: str | None = None,
    export_path: Path | None = None,
    db_path: Path | None = None,
) -> SessionConsumption:
    """Return consumption from the strongest available source.

    The per-invocation export is tried first (invocation scope); the
    session DB is the fallback and is labelled ``session_lifetime`` scope.
    """
    if export_path is not None:
        c = consumption_from_export(export_path, session_type=session_type)
        if c.status == "actual":
            return c
    if session_id:
        c = consumption_from_sessions_db(session_id, db_path=db_path)
        if c.status == "actual":
            return c
        return c
    return _unavailable(
        session_id, session_type, None, "no_consumption_source"
    )


def cost_details(
    consumption: SessionConsumption,
    *,
    pricing_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Build the audit ``cost_details`` block for a consumption record."""
    if consumption.status == "actual":
        status = "actual"
    elif consumption.reason in ("no_consumption_source", "session_not_found"):
        status = "unavailable"
    else:
        # Delayed reporting is possible; reconciliation may resolve later.
        status = "pending_reconciliation"
    return {
        "actual_usd": None,
        "estimated_usd": None,
        "billed_acus": consumption.billed_acus,
        "status": status,
        "source": consumption.source,
        "pricing_snapshot_id": pricing_snapshot_id,
    }


def cost_details_for_invocation(
    inv: dict[str, Any] | None,
    *,
    acu_usd_rate: float | None = None,
    pricing_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Build ``cost_details`` directly from a CLI invocation record.

    Actual billed ACUs from the export win; a captured session without
    cost data stays ``pending_reconciliation`` (billing can lag); no
    invocation record at all is ``unavailable``.  ``acu_usd_rate`` only ever
    produces a labelled ``estimated_usd`` — actual billing stays ``null``.
    """
    from fictionforge.observability.pricing import estimate_usd

    inv = inv or {}
    acus = inv.get("billed_acus")
    if acus is not None:
        return {
            "actual_usd": None,
            "estimated_usd": estimate_usd(acus, acu_usd_rate),
            "billed_acus": acus,
            "status": "actual",
            "source": "atif_export",
            "pricing_snapshot_id": (
                pricing_snapshot_id if acu_usd_rate is not None else None
            ),
        }
    return {
        "actual_usd": None,
        "estimated_usd": None,
        "billed_acus": None,
        "status": "pending_reconciliation" if inv else "unavailable",
        "source": None,
        "pricing_snapshot_id": None,
    }


__all__ = [
    "DEFAULT_DB_PATH",
    "SessionConsumption",
    "collect_consumption",
    "consumption_from_export",
    "consumption_from_parsed",
    "consumption_from_sessions_db",
    "cost_details",
    "cost_details_for_invocation",
    "sessions_db_path",
]
