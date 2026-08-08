from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from app.shared.presentation.errors import DomainError


def row_or_404(
    request: Request,
    sql: str,
    params: tuple[Any, ...],
    code: str,
    message: str,
) -> dict[str, Any]:
    row = request.state.store.fetch_one(sql, params)
    if not row:
        raise DomainError(code, message, 404)
    return row


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def bool_int(value: bool) -> int:
    return 1 if value else 0
