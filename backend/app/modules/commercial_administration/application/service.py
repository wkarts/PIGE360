from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.shared.presentation.errors import DomainError


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_object(raw: object | None) -> dict[str, Any]:
    if raw in (None, ""):
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError) as exc:
        raise DomainError(
            "COMMERCIAL_DATA_INVALID",
            "A configuração comercial persistida é inválida.",
            503,
        ) from exc
    if not isinstance(parsed, dict):
        raise DomainError(
            "COMMERCIAL_DATA_INVALID",
            "A configuração comercial persistida é inválida.",
            503,
        )
    return parsed


def begin_idempotent(
    conn: Any,
    *,
    scope: str,
    key: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """Reserva uma chave na mesma transação da mutação ou reproduz o resultado.

    A linha desaparece com o rollback da transação. Assim, uma falha de negócio não
    deixa uma chave órfã que bloquearia a correção do pedido.
    """

    now = datetime.now(UTC)
    conn.execute("DELETE FROM commercial_idempotency_records WHERE expires_at<?", (now.isoformat(),))
    fingerprint = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    inserted = conn.execute(
        """INSERT OR IGNORE INTO commercial_idempotency_records(
               scope,idempotency_key,request_hash,response_json,created_at,expires_at
           ) VALUES(?,?,?,?,?,?)""",
        (
            scope,
            key,
            fingerprint,
            None,
            now.isoformat(),
            (now + timedelta(days=30)).isoformat(),
        ),
    ).rowcount
    current = conn.execute(
        """SELECT request_hash,response_json FROM commercial_idempotency_records
           WHERE scope=? AND idempotency_key=?""",
        (scope, key),
    ).fetchone()
    if not current:
        raise DomainError(
            "IDEMPOTENCY_RECORD_CONFLICT",
            "A chave de idempotência não pôde ser reservada.",
            409,
        )
    if current["request_hash"] != fingerprint:
        raise DomainError(
            "IDEMPOTENCY_KEY_REUSED",
            "A chave de idempotência já foi usada com outro conteúdo.",
            409,
        )
    if inserted == 1:
        return None, fingerprint
    if not current["response_json"]:
        raise DomainError(
            "IDEMPOTENCY_REQUEST_IN_PROGRESS",
            "Uma solicitação com esta chave ainda está em processamento.",
            409,
        )
    try:
        replay = json.loads(str(current["response_json"]))
    except json.JSONDecodeError as exc:
        raise DomainError(
            "IDEMPOTENCY_RECORD_INVALID",
            "O registro de idempotência não pôde ser reproduzido.",
            503,
        ) from exc
    if not isinstance(replay, dict):
        raise DomainError(
            "IDEMPOTENCY_RECORD_INVALID",
            "O registro de idempotência não pôde ser reproduzido.",
            503,
        )
    return replay, fingerprint


def finish_idempotent(
    conn: Any,
    *,
    scope: str,
    key: str,
    fingerprint: str,
    result: dict[str, Any],
) -> None:
    changed = conn.execute(
        """UPDATE commercial_idempotency_records SET response_json=?
           WHERE scope=? AND idempotency_key=? AND request_hash=? AND response_json IS NULL""",
        (canonical_json(result), scope, key, fingerprint),
    ).rowcount
    if changed != 1:
        raise DomainError(
            "IDEMPOTENCY_RECORD_CONFLICT",
            "A solicitação idempotente entrou em conflito com outro processamento.",
            409,
        )


def plan_entitlements(
    *,
    subscription: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    usage: dict[str, int],
) -> dict[str, Any]:
    if not subscription or not plan:
        return {
            "enabled": False,
            "reason": "subscription_not_configured",
            "features": {},
            "limits": {},
            "usage": usage,
            "remaining": {},
        }
    enabled = subscription["status"] in {"active", "trialing"} and plan["status"] in {
        "active",
        "inactive",
    }
    features = json_object(plan.get("features_json"))
    limits = json_object(plan.get("limits_json"))
    remaining: dict[str, int | None] = {}
    for name, raw_limit in limits.items():
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
            continue
        remaining[name] = max(0, raw_limit - int(usage.get(name, 0)))
    return {
        "enabled": enabled,
        "reason": "subscription_active" if enabled else f"subscription_{subscription['status']}",
        "features": features if enabled else {},
        "limits": limits if enabled else {},
        "usage": usage,
        "remaining": remaining if enabled else {},
    }
