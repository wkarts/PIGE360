from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.shared.presentation.errors import DomainError


DEFAULT_TENANT_QUOTAS: dict[str, int] = {
    "max_users": 500,
    "max_students": 5_000,
    "storage_bytes": 107_374_182_400,
    "api_requests_per_minute": 6_000,
    "max_integrations": 20,
    "max_concurrent_builds": 2,
    "max_custom_domains": 10,
}


# Contrato exposto pelo Control Plane. Somente marque uma quota como
# ``enforced`` quando todos os pontos canônicos de criação/execução conhecidos
# passam pelo mesmo gate. Storage permanece deliberadamente informativo até
# existir um ledger transacional que reconcilie LocalObjectStorage e S3/MinIO.
TENANT_QUOTA_ENFORCEMENT: dict[str, dict[str, str]] = {
    "max_users": {"status": "enforced", "scope": "active_tenant_users"},
    "max_students": {"status": "enforced", "scope": "active_students"},
    "storage_bytes": {
        "status": "not_enforced",
        "scope": "configured_advisory_limit",
        "reason_code": "STORAGE_USAGE_LEDGER_UNAVAILABLE",
    },
    "api_requests_per_minute": {"status": "enforced", "scope": "tenant_http_requests"},
    "max_integrations": {"status": "enforced", "scope": "non_archived_integration_connections"},
    "max_concurrent_builds": {"status": "enforced", "scope": "queued_or_building_build_requests"},
    "max_custom_domains": {"status": "enforced", "scope": "enabled_custom_domains"},
}


def configured_tenant_quotas(raw: object) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def effective_tenant_quotas(raw: object) -> dict[str, Any]:
    return {**DEFAULT_TENANT_QUOTAS, **configured_tenant_quotas(raw)}


def quota_limit_from_raw(raw: object, quota: str) -> int:
    """Interpreta um limite conhecido sem transformar corrupção em ilimitado."""
    if quota not in DEFAULT_TENANT_QUOTAS:
        raise ValueError(f"Quota desconhecida: {quota}")
    value = effective_tenant_quotas(raw)[quota]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainError(
            "TENANT_QUOTAS_INVALID",
            f"A quota '{quota}' persistida para o tenant é inválida.",
            503,
        )
    return value


def tenant_quota_limit(control_store: Any, tenant_id: str, quota: str) -> int:
    """Lê do Control Plane um limite conhecido e validado."""

    row = control_store.fetch_one(
        "SELECT quotas_json FROM platform_tenants WHERE id=?",
        (tenant_id,),
    )
    if not row:
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    return quota_limit_from_raw(row.get("quotas_json"), quota)


def consume_tenant_api_request(
    control_store: Any,
    tenant_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, int | str]:
    """Consome uma unidade da quota HTTP do tenant em bucket UTC de um minuto.

    O contador fica no Control DB e o lock transacional nomeado torna o limite
    comum a todas as instâncias que compartilham esse banco. Requisições que já
    atingiram o limite não incrementam o contador.
    """

    current = (now or datetime.now(UTC)).astimezone(UTC)
    bucket = current.replace(second=0, microsecond=0)
    bucket_key = bucket.isoformat()
    reset_at = bucket + timedelta(minutes=1)
    retry_after = max(1, int((reset_at - current).total_seconds() + 0.999))

    with control_store.transaction() as conn:
        control_store.transaction_lock(conn, f"tenant-api-rate:{tenant_id}:{bucket_key}")
        tenant = conn.execute(
            "SELECT quotas_json FROM platform_tenants WHERE id=?",
            (tenant_id,),
        ).fetchone()
        if not tenant:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        limit = quota_limit_from_raw(tenant["quotas_json"], "api_requests_per_minute")
        row = conn.execute(
            "SELECT request_count FROM tenant_api_rate_buckets WHERE tenant_id=? AND bucket_start=?",
            (tenant_id, bucket_key),
        ).fetchone()
        used = int(row["request_count"] if row else 0)
        if used >= limit:
            raise DomainError(
                "TENANT_API_RATE_LIMIT_EXCEEDED",
                f"A quota de requisições do tenant ({limit} por minuto) foi atingida.",
                429,
                "Limite de requisições atingido",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_at.timestamp())),
                },
            )
        if row:
            conn.execute(
                "UPDATE tenant_api_rate_buckets SET request_count=request_count+1,updated_at=? "
                "WHERE tenant_id=? AND bucket_start=?",
                (current.isoformat(), tenant_id, bucket_key),
            )
        else:
            conn.execute(
                "INSERT INTO tenant_api_rate_buckets(tenant_id,bucket_start,request_count,updated_at) "
                "VALUES(?,?,?,?)",
                (tenant_id, bucket_key, 1, current.isoformat()),
            )
        # Um bucket por tenant é suficiente para a decisão atual e impede
        # crescimento indefinido sem depender de um scheduler externo.
        conn.execute(
            "DELETE FROM tenant_api_rate_buckets WHERE tenant_id=? AND bucket_start<?",
            (tenant_id, bucket_key),
        )
        used += 1

    return {
        "limit": limit,
        "remaining": max(0, limit - used),
        "reset": int(reset_at.timestamp()),
        "bucket_start": bucket_key,
    }
