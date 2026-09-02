from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, require_roles

router = APIRouter(tags=["platform-observability"])


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _query_loki(query: str, *, start_ns: int, end_ns: int, limit: int) -> dict[str, Any]:
    base = os.getenv("LOKI_INTERNAL_URL", "http://pige360-loki:3100").rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DomainError("LOKI_URL_INVALID", "LOKI_INTERNAL_URL inválida.", 503)
    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
            "direction": "backward",
        }
    )
    request = urllib.request.Request(
        f"{base}/loki/api/v1/query_range?{params}",
        headers={"Accept": "application/json", "User-Agent": "PIGE360-ControlPlane/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise DomainError("LOKI_UNAVAILABLE", "O serviço central de logs não respondeu.", 503) from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise DomainError("LOKI_QUERY_FAILED", "Loki não confirmou a consulta.", 503)
    return payload


def _flatten(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    result = ((payload.get("data") or {}).get("result") or []) if isinstance(payload.get("data"), dict) else []
    records: list[dict[str, Any]] = []
    for stream in result:
        labels = stream.get("stream") if isinstance(stream, dict) else {}
        values = stream.get("values") if isinstance(stream, dict) else []
        for value in values or []:
            if not isinstance(value, list) or len(value) != 2:
                continue
            ts, line = value
            parsed_line: Any = None
            try:
                parsed_line = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                parsed_line = None
            records.append(
                {
                    "timestamp_ns": str(ts),
                    "labels": labels or {},
                    "event": parsed_line if isinstance(parsed_line, dict) else None,
                    "message": None if isinstance(parsed_line, dict) else str(line),
                }
            )
    records.sort(key=lambda item: int(item["timestamp_ns"]), reverse=True)
    return records[:limit]


@router.get("/platform/logs", operation_id="query_platform_logs")
def query_logs(
    request: Request,
    tenant_id: str | None = None,
    tenant_code: str | None = None,
    correlation_id: str | None = Query(default=None, max_length=100),
    service: str | None = Query(default=None, max_length=100),
    plane: str | None = Query(default=None, pattern=r"^(platform|tenant)$"),
    level: str | None = Query(default=None, max_length=30),
    minutes: int = Query(default=60, ge=1, le=10080),
    limit: int = Query(default=200, ge=1, le=1000),
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    if tenant_id:
        tenant = request.state.store.fetch_one("SELECT id,code FROM platform_tenants WHERE id=?", (tenant_id,))
        if not tenant:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        tenant_code = tenant_code or str(tenant["code"])

    matchers = ['platform="pige360"']
    if tenant_id:
        matchers.append(f"tenant_id={_quoted(tenant_id)}")
    if tenant_code:
        matchers.append(f"tenant_code={_quoted(tenant_code)}")
    if service:
        matchers.append(f"service={_quoted(service)}")
    if plane:
        matchers.append(f"plane={_quoted(plane)}")
    query = "{" + ",".join(matchers) + "}"
    pipeline: list[str] = []
    if correlation_id or level:
        pipeline.append("| json")
    if correlation_id:
        pipeline.append(f"| correlation_id={_quoted(correlation_id)}")
    if level:
        pipeline.append(f"| level={_quoted(level.lower())}")
    if pipeline:
        query += " " + " ".join(pipeline)

    now_ns = time.time_ns()
    start_ns = now_ns - minutes * 60 * 1_000_000_000
    injected = getattr(request.app.state, "loki_query", None)
    payload = injected(query, start_ns, now_ns, limit) if injected else _query_loki(query, start_ns=start_ns, end_ns=now_ns, limit=limit)
    return {
        "items": _flatten(payload, limit),
        "query": query,
        "window_minutes": minutes,
        "limit": limit,
        "generated_at_ns": str(now_ns),
    }
