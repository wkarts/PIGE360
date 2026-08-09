from __future__ import annotations

import time
from urllib.parse import parse_qs

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.shared.domain.ids import uuid7
from app.shared.presentation.errors import DomainError, problem


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        correlation_id = request.headers.get("X-Correlation-ID") or uuid7()
        request.state.correlation_id = correlation_id
        host = request.headers.get("host", "").split(":", 1)[0]
        try:
            resolution = request.app.state.data_router.resolve_host(host)
        except DomainError as exc:
            return JSONResponse(problem(exc, correlation_id), status_code=exc.status)
        # X-Tenant-ID nunca é seletor válido. `tenant_id` em query é permitido
        # somente no Control Plane autenticado, como filtro administrativo de
        # rotas /platform/*; no Tenant Plane a resolução continua exclusivamente
        # vinculada ao hostname.
        has_query_tenant = "tenant_id" in parse_qs(request.url.query)
        platform_filter = resolution.plane == "platform" and request.url.path.startswith("/api/v1/platform/")
        if request.headers.get("X-Tenant-ID") or (has_query_tenant and not platform_filter):
            error = DomainError("PUBLIC_TENANT_SELECTOR_FORBIDDEN", "O tenant é resolvido exclusivamente pelo hostname.", 400)
            return JSONResponse(problem(error, correlation_id), status_code=400)
        request.state.host_resolution = resolution
        request.state.store = (
            request.app.state.data_router.control
            if resolution.plane == "platform"
            else request.app.state.data_router.tenant_store(resolution.tenant_id)
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter()-started)*1000:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
