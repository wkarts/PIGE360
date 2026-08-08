from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.shared.domain.ids import iso_now, uuid7


def add_audit(
    conn: sqlite3.Connection,
    *, tenant_id: str | None, actor_id: str | None, action: str,
    aggregate_type: str, aggregate_id: str | None,
    correlation_id: str, before: Any = None, after: Any = None, reason: str | None = None,
) -> str:
    audit_id = uuid7()
    conn.execute(
        """INSERT INTO audit_log(id,tenant_id,actor_id,action,aggregate_type,aggregate_id,before_json,after_json,reason,correlation_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (audit_id, tenant_id, actor_id, action, aggregate_type, aggregate_id,
         json.dumps(before, ensure_ascii=False, sort_keys=True) if before is not None else None,
         json.dumps(after, ensure_ascii=False, sort_keys=True) if after is not None else None,
         reason, correlation_id, iso_now()),
    )
    return audit_id


def add_outbox(
    conn: sqlite3.Connection,
    *, tenant_id: str | None, event_type: str, aggregate_type: str, aggregate_id: str,
    payload: Any, correlation_id: str, event_version: int = 1,
) -> str:
    event_id = uuid7()
    conn.execute(
        """INSERT INTO outbox_events(id,tenant_id,event_type,event_version,aggregate_type,aggregate_id,payload_json,correlation_id,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (event_id, tenant_id, event_type, event_version, aggregate_type, aggregate_id,
         json.dumps(payload, ensure_ascii=False, sort_keys=True), correlation_id, iso_now()),
    )
    return event_id
