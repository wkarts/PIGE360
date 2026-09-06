from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.shared.domain.ids import iso_now


AGENT_STALE_AFTER_SECONDS = 180
JOB_LEASE_SECONDS = 300
CAPABILITY_BY_OPERATION = {
    "backup": "backup.execute",
    "restore": "restore.execute",
    "deploy": "deploy.execute",
}


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def future_timestamp(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def generate_agent_token() -> str:
    return "pige360_agent_" + secrets.token_urlsafe(48)


def agent_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def capabilities_from_row(row: dict[str, Any]) -> list[str]:
    try:
        value = json.loads(str(row.get("capabilities_json") or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    allowed = set(CAPABILITY_BY_OPERATION.values())
    return sorted({str(item) for item in value if str(item) in allowed})


def agent_view(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    last_seen = parse_timestamp(row.get("last_seen_at"))
    if row.get("state") == "revoked":
        connectivity = "revoked"
    elif last_seen is None:
        connectivity = "registered"
    elif (now - last_seen).total_seconds() > AGENT_STALE_AFTER_SECONDS:
        connectivity = "stale"
    else:
        connectivity = "online"
    return {
        "id": row["id"],
        "name": row["name"],
        "agent_type": row["agent_type"],
        "capabilities": capabilities_from_row(row),
        "software_version": row.get("software_version"),
        "state": row["state"],
        "connectivity": connectivity,
        "last_seen_at": row.get("last_seen_at"),
        "revoked_at": row.get("revoked_at"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": int(row["version"]),
        "stale_after_seconds": AGENT_STALE_AFTER_SECONDS,
    }


def canonical_job_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def job_view(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    lease = parse_timestamp(row.get("lease_expires_at"))
    lease_expired = bool(row.get("state") in {"claimed", "running"} and lease and lease <= now)
    return {
        "id": row["id"],
        "operation_type": row["operation_type"],
        "resource_scope": row["resource_scope"],
        "tenant_id": row.get("tenant_id"),
        "required_capability": row["required_capability"],
        "deployment_target": row.get("deployment_target"),
        "image_mode": row.get("image_mode"),
        "release_version": row.get("release_version"),
        "backup_reference": row.get("backup_reference"),
        "state": row["state"],
        "reason": row["reason"],
        "requested_by": row["requested_by"],
        "assigned_agent_id": row.get("assigned_agent_id"),
        "attempts": int(row["attempts"]),
        "result_code": row.get("result_code"),
        "evidence_reference": row.get("evidence_reference"),
        "evidence_sha256": row.get("evidence_sha256"),
        "failure_code": row.get("failure_code"),
        "correlation_id": row["correlation_id"],
        "claimed_at": row.get("claimed_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "lease_expires_at": row.get("lease_expires_at"),
        "lease_expired": lease_expired,
        "attention_required": lease_expired,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": int(row["version"]),
    }


def audit_agent_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Representação segura para audit/outbox; nunca inclui hash/token."""

    return {
        "id": row["id"],
        "name": row["name"],
        "agent_type": row["agent_type"],
        "capabilities": capabilities_from_row(row),
        "state": row["state"],
        "version": int(row["version"]),
    }


def now_iso() -> str:
    return iso_now()
