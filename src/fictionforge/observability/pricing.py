"""Immutable pricing snapshots (Phase 3 provenance for estimated costs).

A snapshot records a conversion/billing rate *as configured or observed*,
with full provenance: who supplied it, when, and a content hash so the same
rate always resolves to the same snapshot ID.  Snapshots live under
``data/pricing/snapshots/`` and are never mutated after creation — a new rate
produces a new snapshot ID, so historical ``estimated_usd`` values always
point back at the exact rate that produced them.

Estimated USD is only ever produced here from a configured/verified rate;
nothing fabricates prices.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SNAPSHOTS_DIR = Path("data/pricing/snapshots")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_for_acu_rate(
    rate: float,
    *,
    provider: str = "devin",
    model: str | None = None,
    source: str = "config/workflow.yaml#cost.acu_usd_rate",
    snapshots_dir: Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Persist (if needed) and return ``(snapshot_id, snapshot)`` for a rate.

    The snapshot ID is a content hash — identical rate+provenance always
    resolves to the same immutable snapshot file.
    """
    content = {
        "snapshot_type": "acu_to_usd_rate",
        "provider": provider,
        "model": model,
        "currency": "USD",
        "billing_unit": "ACU",
        "rates": {"acu_to_usd": rate},
        "source": source,
        "verification_status": "configured",
        "effective_date": None,
        "observed_at": _utc_now(),
    }
    # ID covers rate+identity only, not the timestamp — same rate => same ID.
    id_material = json.dumps(
        {k: v for k, v in content.items() if k != "observed_at"},
        sort_keys=True,
    )
    snapshot_id = "acu-usd-" + hashlib.sha256(
        id_material.encode("utf-8")
    ).hexdigest()[:16]
    content["snapshot_id"] = snapshot_id
    content["source_response_hash"] = hashlib.sha256(
        json.dumps(content["rates"], sort_keys=True).encode("utf-8")
    ).hexdigest()

    out_dir = Path(snapshots_dir) if snapshots_dir else SNAPSHOTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{snapshot_id}.json"
    if not path.exists():
        path.write_text(
            json.dumps(content, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return snapshot_id, content


def estimate_usd(
    billed_acus: float | None, acu_usd_rate: float | None
) -> float | None:
    """ACU → USD via a configured rate; ``None`` when either side is missing."""
    if billed_acus is None or acu_usd_rate is None:
        return None
    return round(billed_acus * acu_usd_rate, 8)


__all__ = ["SNAPSHOTS_DIR", "estimate_usd", "snapshot_for_acu_rate"]
