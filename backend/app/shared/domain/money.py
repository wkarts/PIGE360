from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.shared.presentation.errors import DomainError

CENT = Decimal("0.01")


def money(value: Any, field: str = "valor") -> Decimal:
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DomainError("INVALID_AMOUNT", f"{field} inválido.", 422) from exc


def money_str(value: Any) -> str:
    return format(money(value), ".2f")
