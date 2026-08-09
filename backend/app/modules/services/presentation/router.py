from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.finance.application.ledger import CENT, money, money_str, month_add
from app.modules.operations.common import FINANCE_ROLES, dumps, require, row_or_404, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["services"])


class ServiceInput(BaseModel):
    code: str
    name: str
    description: str | None = None
    price: Decimal = Field(ge=0)
    recurrence: str | None = None
    nbs: str | None = None
    lc116_code: str | None = None
    municipal_code: str | None = None
    cnae: str | None = None
    fiscal_profile: dict[str, Any] = Field(default_factory=dict)


class ServiceOrderItemInput(BaseModel):
    service_id: str
    quantity: Decimal = Field(gt=0)


class ServiceOrderInput(BaseModel):
    enrollment_id: str | None = None
    responsible_guardian_id: str | None = None
    competence: str | None = None
    items: list[ServiceOrderItemInput] = Field(min_length=1)
    installment_count: int = Field(default=1, ge=1, le=120)
    first_due_date: date | None = None


@router.get("/services", operation_id="list_services_relational")
def list_services(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FINANCE_ROLES | {"secretary"})
    return {
        "items": request.state.store.fetch_all(
            "SELECT * FROM services WHERE tenant_id=? ORDER BY name",
            (tenant(user),),
        )
    }


@router.post("/services", status_code=201, operation_id="create_service_relational")
def create_service(
    data: ServiceInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    service_id = uuid7()
    now = iso_now()
    price = money(data.price)
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO services(id,tenant_id,code,name,description,price,recurrence,nbs,lc116_code,"
            "municipal_code,cnae,fiscal_profile_json,state,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                service_id,
                tenant_id,
                data.code,
                data.name,
                data.description,
                money_str(price),
                data.recurrence,
                data.nbs,
                data.lc116_code,
                data.municipal_code,
                data.cnae,
                dumps(data.fiscal_profile),
                "active",
                now,
                now,
            ),
        )
        result = {
            "id": service_id,
            "code": data.code,
            "name": data.name,
            "price": money_str(price),
            "state": "active",
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="service",
            aggregate_id=service_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.get("/service-orders", operation_id="list_service_orders")
def list_service_orders(
    request: Request,
    state: str | None = None,
    enrollment_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES | {"secretary"})
    tenant_id = tenant(user)
    sql = "SELECT * FROM service_orders WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if state:
        sql += " AND state=?"
        params.append(state)
    if enrollment_id:
        sql += " AND enrollment_id=?"
        params.append(enrollment_id)
    sql += " ORDER BY created_at DESC"
    orders = request.state.store.fetch_all(sql, params)
    for order in orders:
        order["items"] = request.state.store.fetch_all(
            "SELECT soi.*,s.code,s.name FROM service_order_items soi "
            "JOIN services s ON s.id=soi.service_id "
            "WHERE soi.service_order_id=? ORDER BY soi.created_at,soi.id",
            (order["id"],),
        )
    return {"items": orders}


@router.post("/service-orders", status_code=201, operation_id="create_service_order")
def create_service_order(
    data: ServiceOrderInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES | {"secretary"})
    tenant_id = tenant(user)
    now = iso_now()

    if data.enrollment_id:
        row_or_404(
            request,
            "SELECT id FROM enrollments WHERE id=? AND tenant_id=?",
            (data.enrollment_id, tenant_id),
            "ENROLLMENT_NOT_FOUND",
            "Matrícula não localizada.",
        )

    items: list[tuple[ServiceOrderItemInput, Decimal, Decimal]] = []
    total = Decimal("0")
    for item in data.items:
        service = row_or_404(
            request,
            "SELECT * FROM services WHERE id=? AND tenant_id=? AND state='active'",
            (item.service_id, tenant_id),
            "SERVICE_NOT_FOUND",
            "Serviço não localizado.",
        )
        unit_price = money(service["price"])
        line_total = (unit_price * item.quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        total += line_total
        items.append((item, unit_price, line_total))

    order_id = uuid7()
    financial_contract_id = uuid7()
    description = f"Pedido de serviços {order_id[-8:]}"
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO financial_contracts(id,tenant_id,enrollment_id,responsible_guardian_id,"
            "description,total_amount,currency,competence_rule,state,version,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                financial_contract_id,
                tenant_id,
                data.enrollment_id,
                data.responsible_guardian_id,
                description,
                money_str(total),
                "BRL",
                "billing",
                "active",
                1,
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO service_orders(id,tenant_id,enrollment_id,responsible_guardian_id,competence,"
            "state,total_amount,financial_contract_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                order_id,
                tenant_id,
                data.enrollment_id,
                data.responsible_guardian_id,
                data.competence,
                "confirmed",
                money_str(total),
                financial_contract_id,
                now,
                now,
            ),
        )
        for item, unit_price, line_total in items:
            conn.execute(
                "INSERT INTO service_order_items(id,tenant_id,service_order_id,service_id,quantity,"
                "unit_price,total_amount,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    order_id,
                    item.service_id,
                    str(item.quantity),
                    money_str(unit_price),
                    money_str(line_total),
                    now,
                ),
            )

        count = data.installment_count
        first_due_date = data.first_due_date or date.today()
        base = (total / Decimal(count)).quantize(CENT, rounding=ROUND_HALF_UP)
        installments = [base] * count
        installments[-1] = (total - sum(installments[:-1], Decimal("0"))).quantize(CENT)
        for sequence, amount in enumerate(installments, 1):
            due = month_add(first_due_date, sequence - 1)
            conn.execute(
                "INSERT INTO installments(id,tenant_id,financial_contract_id,sequence,competence,due_date,"
                "original_amount,discount_amount,penalty_amount,interest_amount,paid_amount,state,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    financial_contract_id,
                    sequence,
                    due.strftime("%Y-%m"),
                    str(due),
                    money_str(amount),
                    "0.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "open",
                    now,
                    now,
                ),
            )

        result = {
            "id": order_id,
            "state": "confirmed",
            "total_amount": money_str(total),
            "financial_contract_id": financial_contract_id,
            "installments": count,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="confirm",
            aggregate_type="service_order",
            aggregate_id=order_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="ServiceOrderConfirmed",
            aggregate_type="service_order",
            aggregate_id=order_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result
