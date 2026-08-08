from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from app.shared.domain.ids import iso_now
from app.shared.presentation.errors import DomainError


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_idempotent(conn: sqlite3.Connection, scope: str, key: str, request: Any) -> tuple[int, Any] | None:
    row = conn.execute(
        "SELECT request_hash,response_json,status_code FROM idempotency_keys WHERE scope=? AND idempotency_key=?",
        (scope, key),
    ).fetchone()
    if not row:
        return None
    if row["request_hash"] != canonical_hash(request):
        raise DomainError("IDEMPOTENCY_CONFLICT", "A mesma chave foi reutilizada com conteúdo diferente.", 409)
    return int(row["status_code"]), json.loads(row["response_json"])


def save_idempotent(conn: sqlite3.Connection, scope: str, key: str, request: Any, status: int, response: Any) -> None:
    conn.execute(
        "INSERT INTO idempotency_keys(scope,idempotency_key,request_hash,response_json,status_code,created_at) VALUES(?,?,?,?,?,?)",
        (scope, key, canonical_hash(request), json.dumps(response, ensure_ascii=False, sort_keys=True), status, iso_now()),
    )
