from __future__ import annotations

import json
import logging
import time
from urllib.parse import parse_qs

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.shared.domain.ids import uuid7
from app.shared.presentation.errors import DomainError, problem


logger = logging.getLogger("pige360.http")


def _log_request(
    request: Request,
    *,
    correlation_id: str,
    host: str,
    status: int,
    duration_ms: float,
    plane: str | None = None,
    tenant_id: str | None = None,
    tenant_code: str | None = None,
    surface: str | None = None,
    error_code: str | None = None,
) -> None:
    level = "error" if status >= 500 else ("warning" if status >= 400 else "info")
    payload = {
        "event": "http_request",
        "level": level,
        "service": "pige360-api",
        "environment": request.app.state.settings.environment,
        "correlation_id": correlation_id,
        "request_host": host,
        "request_method": request.method,
        # Query string é deliberadamente excluída para reduzir exposição de dados.
        "request_path": request.url.path,
        "status_code": status,
        "duration_ms": round(duration_ms, 2),
        "plane": plane,
        "tenant_id": tenant_id,
        "tenant_code": tenant_code,
        "surface": surface,
    }
    if error_code:
        payload["error_code"] = error_code
    log_line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if level == "error":
        logger.error(log_line)
    elif level == "warning":
        logger.warning(log_line)
    else:
        logger.info(log_line)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        correlation_id = request.headers.get("X-Correlation-ID") or uuid7()
        request.state.correlation_id = correlation_id
        host = request.headers.get("host", "").split(":", 1)[0]
        try:
            resolution = request.app.state.data_router.resolve_host(host)
        except DomainError as exc:
            _log_request(
                request,
                correlation_id=correlation_id,
                host=host,
                status=exc.status,
                duration_ms=(time.perf_counter() - started) * 1000,
                error_code=exc.code,
            )
            return JSONResponse(problem(exc, correlation_id), status_code=exc.status)

        # X-Tenant-ID nunca é seletor válido. `tenant_id` em query é permitido
        # somente no Control Plane autenticado, como filtro administrativo de
        # rotas /platform/*; no Tenant Plane a resolução continua exclusivamente
        # vinculada ao hostname.
        has_query_tenant = "tenant_id" in parse_qs(request.url.query)
        platform_filter = resolution.plane == "platform" and request.url.path.startswith("/api/v1/platform/")
        if request.headers.get("X-Tenant-ID") or (has_query_tenant and not platform_filter):
            error = DomainError(
                "PUBLIC_TENANT_SELECTOR_FORBIDDEN",
                "O tenant é resolvido exclusivamente pelo hostname.",
                400,
            )
            _log_request(
                request,
                correlation_id=correlation_id,
                host=host,
                status=400,
                duration_ms=(time.perf_counter() - started) * 1000,
                plane=resolution.plane,
                tenant_id=resolution.tenant_id,
                tenant_code=resolution.tenant_code,
                surface=resolution.surface,
                error_code=error.code,
            )
            return JSONResponse(problem(error, correlation_id), status_code=400)

        request.state.host_resolution = resolution
        request.state.store = (
            request.app.state.data_router.control
            if resolution.plane == "platform"
            else request.app.state.data_router.tenant_store(resolution.tenant_id)
        )

        try:
            response = await call_next(request)
        except Exception:
            _log_request(
                request,
                correlation_id=correlation_id,
                host=host,
                status=500,
                duration_ms=(time.perf_counter() - started) * 1000,
                plane=resolution.plane,
                tenant_id=resolution.tenant_id,
                tenant_code=resolution.tenant_code,
                surface=resolution.surface,
                error_code="UNHANDLED_EXCEPTION",
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        _log_request(
            request,
            correlation_id=correlation_id,
            host=host,
            status=response.status_code,
            duration_ms=duration_ms,
            plane=resolution.plane,
            tenant_id=resolution.tenant_id,
            tenant_code=resolution.tenant_code,
            surface=resolution.surface,
        )
        return response
