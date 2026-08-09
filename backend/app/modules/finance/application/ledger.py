from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from app.shared.domain.money import CENT, money, money_str
from app.shared.domain.ids import uuid7
from app.shared.presentation.errors import DomainError

def month_add(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    days = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    return date(year, month, min(value.day, days[month - 1]))


def installment_total_due(row: dict[str, Any]) -> Decimal:
    return (
        money(row["original_amount"])
        + money(row["penalty_amount"])
        + money(row["interest_amount"])
        - money(row["discount_amount"])
    )


def apply_payment_allocations(
    conn: Any,
    *,
    tenant_id: str,
    payment_id: str,
    allocations: Iterable[tuple[str, Decimal]],
    now: str,
) -> list[dict[str, str]]:
    applied: list[dict[str, str]] = []
    for installment_id, raw_amount in allocations:
        row = conn.execute(
            "SELECT * FROM installments WHERE id=? AND tenant_id=?",
            (installment_id, tenant_id),
        ).fetchone()
        if not row:
            raise DomainError("INSTALLMENT_NOT_FOUND", "Parcela não localizada.", 404)

        total_due = installment_total_due(row)
        already_paid = money(row["paid_amount"])
        balance = total_due - already_paid
        amount = money(raw_amount)
        if amount <= Decimal("0"):
            raise DomainError("INVALID_ALLOCATION_AMOUNT", "Valor de rateio inválido.", 422)
        if amount > balance:
            raise DomainError(
                "ALLOCATION_EXCEEDS_BALANCE",
                "Rateio excede o saldo da parcela.",
                409,
            )

        paid = already_paid + amount
        state = "paid" if paid >= total_due else "partial"
        allocation_id = uuid7()
        conn.execute(
            "INSERT INTO payment_allocations(id,tenant_id,payment_id,installment_id,amount,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (allocation_id, tenant_id, payment_id, installment_id, money_str(amount), now),
        )
        conn.execute(
            "UPDATE installments SET paid_amount=?,state=?,updated_at=? WHERE id=?",
            (money_str(paid), state, now, installment_id),
        )
        applied.append(
            {
                "id": allocation_id,
                "installment_id": installment_id,
                "amount": money_str(amount),
                "state": state,
            }
        )
    return applied
