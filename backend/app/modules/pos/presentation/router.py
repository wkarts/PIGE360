from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import SALES_ROLES, require, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["pos"])


class CashOpen(BaseModel):
    terminal_code: str
    opening_amount: Decimal = Field(default=Decimal("0"), ge=0)


class CashClose(BaseModel):
    closing_amount: Decimal = Field(ge=0)
    reason: str = Field(min_length=3)


@router.get("/pos/cash-sessions", operation_id="list_cash_sessions")
def list_cash(
    request: Request,
    state: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    sql = "SELECT * FROM cash_sessions WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if state:
        sql += " AND state=?"
        params.append(state)
    sql += " ORDER BY opened_at DESC"
    return {"items": request.state.store.fetch_all(sql, params)}


@router.post("/pos/cash-sessions/open", status_code=201, operation_id="open_cash_session")
def open_cash(
    data: CashOpen,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    existing = request.state.store.fetch_one(
        "SELECT id FROM cash_sessions WHERE tenant_id=? AND terminal_code=? AND state='open'",
        (tenant_id, data.terminal_code),
    )
    if existing:
        raise DomainError("CASH_SESSION_ALREADY_OPEN", "Já existe caixa aberto neste terminal.", 409)
    cash_id = uuid7()
    now = iso_now()
    result = {
        "id": cash_id,
        "terminal_code": data.terminal_code,
        "operator_user_id": user.id,
        "opening_amount": money_str(data.opening_amount),
        "state": "open",
        "opened_at": now,
    }
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO cash_sessions(id,tenant_id,terminal_code,operator_user_id,opened_at,opening_amount,"
            "state,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                cash_id,
                tenant_id,
                data.terminal_code,
                user.id,
                now,
                result["opening_amount"],
                "open",
                now,
            ),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="open",
            aggregate_type="cash_session",
            aggregate_id=cash_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.post("/pos/cash-sessions/{cash_id}/close", operation_id="close_cash_session")
def close_cash(
    cash_id: str,
    data: CashClose,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    now = iso_now()
    with request.state.store.transaction() as conn:
        row = conn.execute(
            "SELECT * FROM cash_sessions WHERE id=? AND tenant_id=?",
            (cash_id, tenant_id),
        ).fetchone()
        if not row:
            raise DomainError("CASH_SESSION_NOT_FOUND", "Caixa não localizado.", 404)
        if row["state"] != "open":
            raise DomainError("CASH_SESSION_NOT_OPEN", "Caixa não está aberto.", 409)
        closing_amount = money_str(data.closing_amount)
        sales_cash = money((conn.execute("SELECT COALESCE(SUM(sp.amount),0) AS total FROM sale_payments sp JOIN sales s ON s.id=sp.sale_id WHERE sp.tenant_id=? AND s.cash_session_id=? AND sp.method='cash'", (tenant_id,cash_id)).fetchone() or {"total":0})["total"])
        supplies = money((conn.execute("SELECT COALESCE(SUM(amount),0) AS total FROM cash_movements WHERE tenant_id=? AND cash_session_id=? AND movement_type='supply'", (tenant_id,cash_id)).fetchone() or {"total":0})["total"])
        withdrawals = money((conn.execute("SELECT COALESCE(SUM(amount),0) AS total FROM cash_movements WHERE tenant_id=? AND cash_session_id=? AND movement_type='withdrawal'", (tenant_id,cash_id)).fetchone() or {"total":0})["total"])
        refunds = money((conn.execute("SELECT COALESCE(SUM(rf.amount),0) AS total FROM sale_refunds rf JOIN sale_returns sr ON sr.id=rf.sale_return_id JOIN sales s ON s.id=sr.sale_id WHERE rf.tenant_id=? AND s.cash_session_id=? AND rf.method='cash' AND rf.state='completed'", (tenant_id,cash_id)).fetchone() or {"total":0})["total"])
        expected = money(row["opening_amount"]) + sales_cash + supplies - withdrawals - refunds
        difference = money(data.closing_amount) - expected
        conn.execute(
            "UPDATE cash_sessions SET state='closed',closing_amount=?,closed_at=? WHERE id=?",
            (closing_amount, now, cash_id),
        )
        result = {
            "id": cash_id,
            "state": "closed",
            "closing_amount": closing_amount,
            "expected_amount": money_str(expected),
            "difference": money_str(difference),
            "closed_at": now,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="close",
            aggregate_type="cash_session",
            aggregate_id=cash_id,
            correlation_id=request.state.correlation_id,
            before=dict(row),
            after=result,
            reason=data.reason,
        )
    return result


class CashMovementInput(BaseModel):
    movement_type: Literal["supply","withdrawal"]
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)


def _cash_summary(conn,tenant_id:str,cash_id:str,row:Any)->dict[str,str]:
    sales_cash=money((conn.execute("SELECT COALESCE(SUM(sp.amount),0) AS total FROM sale_payments sp JOIN sales s ON s.id=sp.sale_id WHERE sp.tenant_id=? AND s.cash_session_id=? AND sp.method='cash'",(tenant_id,cash_id)).fetchone() or {"total":0})["total"])
    supplies=money((conn.execute("SELECT COALESCE(SUM(amount),0) AS total FROM cash_movements WHERE tenant_id=? AND cash_session_id=? AND movement_type='supply'",(tenant_id,cash_id)).fetchone() or {"total":0})["total"])
    withdrawals=money((conn.execute("SELECT COALESCE(SUM(amount),0) AS total FROM cash_movements WHERE tenant_id=? AND cash_session_id=? AND movement_type='withdrawal'",(tenant_id,cash_id)).fetchone() or {"total":0})["total"])
    refunds=money((conn.execute("SELECT COALESCE(SUM(rf.amount),0) AS total FROM sale_refunds rf JOIN sale_returns sr ON sr.id=rf.sale_return_id JOIN sales s ON s.id=sr.sale_id WHERE rf.tenant_id=? AND s.cash_session_id=? AND rf.method='cash' AND rf.state='completed'",(tenant_id,cash_id)).fetchone() or {"total":0})["total"])
    expected=money(row["opening_amount"])+sales_cash+supplies-withdrawals-refunds
    return {"opening_amount":money_str(money(row["opening_amount"])),"cash_sales":money_str(sales_cash),"supplies":money_str(supplies),"withdrawals":money_str(withdrawals),"cash_refunds":money_str(refunds),"expected_amount":money_str(expected)}

@router.get("/pos/cash-sessions/{cash_id}/summary",operation_id="get_cash_session_summary")
def cash_summary(cash_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,SALES_ROLES);tid=tenant(user)
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM cash_sessions WHERE tenant_id=? AND id=?",(tid,cash_id)).fetchone()
        if not row:raise DomainError("CASH_SESSION_NOT_FOUND","Caixa não localizado.",404)
        result={**dict(row),**_cash_summary(conn,tid,cash_id,row)}
        result["movements"]=[dict(x) for x in conn.execute("SELECT * FROM cash_movements WHERE tenant_id=? AND cash_session_id=? ORDER BY created_at,id",(tid,cash_id)).fetchall()]
        return result

@router.post("/pos/cash-sessions/{cash_id}/movements",status_code=201,operation_id="register_cash_movement")
def register_cash_movement(cash_id:str,data:CashMovementInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,SALES_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM cash_sessions WHERE tenant_id=? AND id=?",(tid,cash_id)).fetchone()
        if not row:raise DomainError("CASH_SESSION_NOT_FOUND","Caixa não localizado.",404)
        if row["state"]!="open":raise DomainError("CASH_SESSION_NOT_OPEN","Caixa não está aberto.",409)
        rid=uuid7();conn.execute("INSERT INTO cash_movements(id,tenant_id,cash_session_id,movement_type,amount,reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(rid,tid,cash_id,data.movement_type,money_str(data.amount),data.reason,user.id,now));result={"id":rid,"cash_session_id":cash_id,"movement_type":data.movement_type,"amount":money_str(data.amount),"created_at":now};add_audit(conn,tenant_id=tid,actor_id=user.id,action=data.movement_type,aggregate_type="cash_session",aggregate_id=cash_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason)
    return result
