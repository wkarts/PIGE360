from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.shared.domain.ids import uuid7


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    detail: str
    status: int = 400
    title: str = "Regra de negócio não atendida"
    errors: list[dict[str, str]] | None = None


def problem(error: DomainError, correlation_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"https://errors.pige360.local/{error.code.lower().replace('_', '-')}",
        "title": error.title,
        "status": error.status,
        "code": error.code,
        "detail": error.detail,
        "correlation_id": correlation_id or uuid7(),
    }
    if error.errors:
        body["errors"] = error.errors
    return body


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    return JSONResponse(problem(exc, correlation_id), status_code=exc.status)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None) or uuid7()
    # Não expõe detalhes internos ou segredos.
    body = problem(DomainError(
        code="INTERNAL_ERROR",
        detail="Ocorreu um erro interno. Use o identificador de correlação no suporte.",
        status=500,
        title="Erro interno",
    ), correlation_id)
    return JSONResponse(body, status_code=500)
