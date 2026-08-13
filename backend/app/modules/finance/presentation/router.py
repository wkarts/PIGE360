from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.modules.finance.application.ledger import (
    CENT,
    apply_payment_allocations,
    money,
    money_str,
    month_add,
    installment_total_due,
)
from app.modules.operations.common import FINANCE_ROLES, dumps, require, row_or_404, tenant
from app.modules.portals.access import guardian_for_user
from app.modules.services.application.vertical_service import issue_service_receipts_for_payment
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["finance"])


class FinancialContractInput(BaseModel):
    enrollment_id: str | None = None
    responsible_guardian_id: str | None = None
    description: str = Field(min_length=3, max_length=300)
    total_amount: Decimal = Field(gt=0)
    competence_rule: Literal["billing", "competence", "payment"] = "billing"


class InstallmentPlanInput(BaseModel):
    count: int = Field(ge=1, le=120)
    first_due_date: date
    interval_months: int = Field(default=1, ge=1, le=12)
    first_competence: str | None = None


class PaymentAllocationInput(BaseModel):
    installment_id: str
    amount: Decimal = Field(gt=0)


class PaymentInput(BaseModel):
    method: Literal[
        "pix",
        "cash",
        "card",
        "boleto",
        "bank_transfer",
        "institutional_credit",
        "other",
    ]
    amount: Decimal = Field(gt=0)
    paid_at: datetime | None = None
    external_reference: str | None = None
    allocations: list[PaymentAllocationInput] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_allocations_total(self) -> "PaymentInput":
        allocated = sum((item.amount for item in self.allocations), Decimal("0"))
        if allocated.quantize(CENT) != self.amount.quantize(CENT):
            raise ValueError("Soma dos rateios difere do pagamento")
        return self


def _create_contract(
    request: Request,
    user: CurrentUser,
    data: FinancialContractInput,
) -> dict[str, Any]:
    tenant_id = tenant(user)
    now = iso_now()
    contract_id = uuid7()
    amount = money(data.total_amount)

    if data.enrollment_id:
        row_or_404(
            request,
            "SELECT id FROM enrollments WHERE id=? AND tenant_id=?",
            (data.enrollment_id, tenant_id),
            "ENROLLMENT_NOT_FOUND",
            "Matrícula não localizada.",
        )

    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO financial_contracts("
            "id,tenant_id,enrollment_id,responsible_guardian_id,description,total_amount,currency,"
            "competence_rule,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                contract_id,
                tenant_id,
                data.enrollment_id,
                data.responsible_guardian_id,
                data.description,
                money_str(amount),
                "BRL",
                data.competence_rule,
                "draft",
                1,
                now,
                now,
            ),
        )
        result = {
            "id": contract_id,
            "tenant_id": tenant_id,
            "enrollment_id": data.enrollment_id,
            "responsible_guardian_id": data.responsible_guardian_id,
            "description": data.description,
            "total_amount": money_str(amount),
            "currency": "BRL",
            "competence_rule": data.competence_rule,
            "state": "draft",
            "version": 1,
            "created_at": now,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="financial_contract",
            aggregate_id=contract_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="FinancialContractCreated",
            aggregate_type="financial_contract",
            aggregate_id=contract_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


@router.get("/finance/contracts", operation_id="list_financial_contracts")
def list_contracts(
    request: Request,
    enrollment_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES | {"secretary"})
    tenant_id = tenant(user)
    sql = "SELECT * FROM financial_contracts WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if enrollment_id:
        sql += " AND enrollment_id=?"
        params.append(enrollment_id)
    sql += " ORDER BY created_at DESC"
    items = request.state.store.fetch_all(sql, params)
    for item in items:
        item["installments"] = request.state.store.fetch_all(
            "SELECT * FROM installments WHERE financial_contract_id=? ORDER BY sequence",
            (item["id"],),
        )
    return {"items": items}


@router.post("/finance/contracts", status_code=201, operation_id="create_financial_contract")
def create_contract(
    data: FinancialContractInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    return _create_contract(request, user, data)


@router.post(
    "/finance/contracts/{contract_id}/installments",
    status_code=201,
    operation_id="generate_financial_installments",
)
def generate_installments(
    contract_id: str,
    data: InstallmentPlanInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    contract = row_or_404(
        request,
        "SELECT * FROM financial_contracts WHERE id=? AND tenant_id=?",
        (contract_id, tenant_id),
        "FINANCIAL_CONTRACT_NOT_FOUND",
        "Contrato financeiro não localizado.",
    )
    if request.state.store.scalar(
        "SELECT COUNT(*) AS n FROM installments WHERE financial_contract_id=?",
        (contract_id,),
    ):
        raise DomainError("INSTALLMENTS_ALREADY_EXIST", "O contrato já possui parcelas.", 409)

    total = money(contract["total_amount"])
    base = (total / Decimal(data.count)).quantize(CENT, rounding=ROUND_HALF_UP)
    amounts = [base] * data.count
    amounts[-1] = (total - sum(amounts[:-1], Decimal("0"))).quantize(CENT)
    now = iso_now()
    created: list[dict[str, Any]] = []

    with request.state.store.transaction() as conn:
        for sequence, amount in enumerate(amounts, 1):
            due = month_add(data.first_due_date, (sequence - 1) * data.interval_months)
            installment_id = uuid7()
            competence = data.first_competence or due.strftime("%Y-%m")
            conn.execute(
                "INSERT INTO installments("
                "id,tenant_id,financial_contract_id,sequence,competence,due_date,original_amount,"
                "discount_amount,penalty_amount,interest_amount,paid_amount,state,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    installment_id,
                    tenant_id,
                    contract_id,
                    sequence,
                    competence,
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
            created.append(
                {
                    "id": installment_id,
                    "sequence": sequence,
                    "due_date": str(due),
                    "amount": money_str(amount),
                    "state": "open",
                }
            )
        conn.execute(
            "UPDATE financial_contracts SET state='active',version=version+1,updated_at=? WHERE id=?",
            (now, contract_id),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="generate_installments",
            aggregate_type="financial_contract",
            aggregate_id=contract_id,
            correlation_id=request.state.correlation_id,
            after={"installments": created},
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="InstallmentsGenerated",
            aggregate_type="financial_contract",
            aggregate_id=contract_id,
            payload={"installments": created},
            correlation_id=request.state.correlation_id,
        )
    return {
        "contract_id": contract_id,
        "total_amount": money_str(total),
        "installments": created,
    }


@router.get("/finance/my-installments", operation_id="list_my_financial_installments")
def list_my_installments(
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, {"guardian"})
    tenant_id = tenant(user)
    guardian = guardian_for_user(request, user)
    rows = request.state.store.fetch_all(
        """
        SELECT DISTINCT i.*,fc.enrollment_id,fc.description,e.student_id,p.full_name AS student_name
          FROM installments i
          JOIN financial_contracts fc ON fc.id=i.financial_contract_id
          LEFT JOIN enrollments e ON e.id=fc.enrollment_id
          LEFT JOIN students s ON s.id=e.student_id
          LEFT JOIN people p ON p.id=s.person_id
          LEFT JOIN guardian_students gs
            ON gs.tenant_id=i.tenant_id
           AND gs.guardian_id=?
           AND gs.student_id=e.student_id
           AND gs.is_financial=1
         WHERE i.tenant_id=?
           AND (fc.responsible_guardian_id=? OR e.financial_responsible_guardian_id=? OR gs.id IS NOT NULL)
         ORDER BY i.due_date,i.sequence
        """,
        (guardian["id"], tenant_id, guardian["id"], guardian["id"]),
    )
    return {"items": rows, "guardian_id": guardian["id"]}


@router.post("/finance/payments", status_code=201, operation_id="register_payment")
def register_payment(
    data: PaymentInput,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES)
    tenant_id = tenant(user)
    body = data.model_dump(mode="json")
    scope = f"payment:create:{tenant_id}"
    paid_at = (data.paid_at or datetime.now(UTC)).isoformat()
    payment_id = uuid7()
    amount = money(data.amount)

    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            response.status_code = cached[0]
            return cached[1]
        conn.execute(
            "INSERT INTO payments(id,tenant_id,method,amount,paid_at,external_reference,state,"
            "idempotency_key,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                payment_id,
                tenant_id,
                data.method,
                money_str(amount),
                paid_at,
                data.external_reference,
                "confirmed",
                idempotency_key,
                dumps(data.metadata),
                iso_now(),
            ),
        )
        applied = apply_payment_allocations(
            conn,
            tenant_id=tenant_id,
            payment_id=payment_id,
            allocations=[(item.installment_id, item.amount) for item in data.allocations],
            now=iso_now(),
        )
        service_receipts = issue_service_receipts_for_payment(
            conn,
            tenant_id=tenant_id,
            payment_id=payment_id,
            actor_id=user.id,
            storage=request.app.state.data_router.object_storage(tenant_id),
            correlation_id=request.state.correlation_id,
        )
        conn.execute(
            "INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,"
            "debit_account,credit_account,amount,occurred_at,description,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                uuid7(),
                tenant_id,
                "receipt",
                "payment",
                payment_id,
                "bank_or_cash",
                "accounts_receivable",
                money_str(amount),
                paid_at,
                "Recebimento",
                iso_now(),
            ),
        )
        result = {
            "id": payment_id,
            "method": data.method,
            "amount": money_str(amount),
            "paid_at": paid_at,
            "state": "confirmed",
            "allocations": applied,
            "service_receipts": service_receipts,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="confirm",
            aggregate_type="payment",
            aggregate_id=payment_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="PaymentConfirmed",
            aggregate_type="payment",
            aggregate_id=payment_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return result


@router.get("/finance/ledger", operation_id="list_financial_ledger")
def list_financial_ledger(
    request: Request,
    entry_type: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 500,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES | {"auditor"})
    tenant_id = tenant(user)
    sql = "SELECT * FROM ledger_entries WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if entry_type:
        sql += " AND entry_type=?"
        params.append(entry_type)
    if reference_type:
        sql += " AND reference_type=?"
        params.append(reference_type)
    if reference_id:
        sql += " AND reference_id=?"
        params.append(reference_id)
    if occurred_from:
        sql += " AND occurred_at>=?"
        params.append(occurred_from.isoformat())
    if occurred_to:
        sql += " AND occurred_at<=?"
        params.append(occurred_to.isoformat())
    sql += " ORDER BY occurred_at DESC,id DESC LIMIT ?"
    params.append(min(max(limit, 1), 2000))
    return {"items": request.state.store.fetch_all(sql, params)}


@router.get("/finance/installments", operation_id="list_installments")
def list_installments(
    request: Request,
    state: str | None = None,
    guardian_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FINANCE_ROLES | {"secretary"})
    tenant_id = tenant(user)
    sql = (
        "SELECT i.*,fc.enrollment_id,fc.responsible_guardian_id,fc.description "
        "FROM installments i JOIN financial_contracts fc ON fc.id=i.financial_contract_id "
        "WHERE i.tenant_id=?"
    )
    params: list[Any] = [tenant_id]
    if state:
        sql += " AND i.state=?"
        params.append(state)
    if guardian_id:
        sql += " AND fc.responsible_guardian_id=?"
        params.append(guardian_id)
    sql += " ORDER BY i.due_date,i.sequence"
    return {"items": request.state.store.fetch_all(sql, params)}


class PaymentRefundAllocationInput(BaseModel):
    installment_id: str
    amount: Decimal = Field(gt=0)

class PaymentRefundInput(BaseModel):
    amount: Decimal = Field(gt=0)
    method: Literal["pix","cash","card","boleto","bank_transfer","institutional_credit","other"]
    reason: str = Field(min_length=3,max_length=2000)
    external_reference: str | None = None
    allocations: list[PaymentRefundAllocationInput] = Field(min_length=1)
    @model_validator(mode="after")
    def total(self):
        if sum((x.amount for x in self.allocations),Decimal("0")).quantize(CENT)!=self.amount.quantize(CENT):raise ValueError("Soma dos rateios do reembolso difere do valor total")
        return self

class RenegotiationInput(BaseModel):
    installments: int = Field(ge=1,le=120)
    first_due_date: date
    interval_months: int = Field(default=1,ge=1,le=12)
    new_total_amount: Decimal | None = Field(default=None,gt=0)
    reason: str = Field(min_length=3,max_length=2000)
    terms: dict[str,Any] = Field(default_factory=dict)

@router.get("/finance/payments/{payment_id}/refunds",operation_id="list_payment_refunds")
def list_payment_refunds(payment_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FINANCE_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM payments WHERE tenant_id=? AND id=?",(tid,payment_id),"PAYMENT_NOT_FOUND","Pagamento não localizado.")
    items=request.state.store.fetch_all("SELECT * FROM payment_refunds WHERE tenant_id=? AND payment_id=? ORDER BY created_at DESC",(tid,payment_id))
    for item in items:item["allocations"]=request.state.store.fetch_all("SELECT * FROM payment_refund_allocations WHERE tenant_id=? AND payment_refund_id=?",(tid,item["id"]))
    return {"items":items}

@router.post("/finance/payments/{payment_id}/refunds",status_code=201,operation_id="refund_payment")
def refund_payment(payment_id:str,data:PaymentRefundInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,FINANCE_ROLES);tid=tenant(user);scope=f"payment-refund:{tid}:{payment_id}";body=data.model_dump(mode="json");now=iso_now();amount=money(data.amount)
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        raw=conn.execute("SELECT * FROM payments WHERE tenant_id=? AND id=?",(tid,payment_id)).fetchone()
        if not raw:raise DomainError("PAYMENT_NOT_FOUND","Pagamento não localizado.",404)
        payment=dict(raw)
        if payment["state"] not in {"confirmed","partially_refunded"}:raise DomainError("PAYMENT_NOT_REFUNDABLE","Pagamento não aceita reembolso neste estado.",409)
        prior=conn.execute("SELECT COALESCE(SUM(amount),0) AS total FROM payment_refunds WHERE tenant_id=? AND payment_id=? AND state='confirmed'",(tid,payment_id)).fetchone();already=money(prior["total"] if prior else 0)
        if already+amount>money(payment["amount"]):raise DomainError("REFUND_EXCEEDS_PAYMENT","Reembolso excede o valor disponível do pagamento.",409)
        for allocation in data.allocations:
            original=conn.execute("SELECT amount FROM payment_allocations WHERE tenant_id=? AND payment_id=? AND installment_id=?",(tid,payment_id,allocation.installment_id)).fetchone()
            if not original:raise DomainError("PAYMENT_ALLOCATION_NOT_FOUND","Parcela não pertence ao rateio original do pagamento.",404)
            prior_alloc=conn.execute("SELECT COALESCE(SUM(pra.amount),0) AS total FROM payment_refund_allocations pra JOIN payment_refunds pr ON pr.id=pra.payment_refund_id WHERE pra.tenant_id=? AND pr.payment_id=? AND pra.installment_id=? AND pr.state='confirmed'",(tid,payment_id,allocation.installment_id)).fetchone();available=money(original["amount"])-money(prior_alloc["total"] if prior_alloc else 0)
            if allocation.amount>available:raise DomainError("REFUND_ALLOCATION_EXCEEDS_PAYMENT","Rateio do reembolso excede o valor originalmente aplicado à parcela.",409)
        refund_id=uuid7();conn.execute("INSERT INTO payment_refunds(id,tenant_id,payment_id,amount,method,reason,state,external_reference,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(refund_id,tid,payment_id,money_str(amount),data.method,data.reason,"confirmed",data.external_reference,user.id,now))
        refunded_allocations=[]
        for allocation in data.allocations:
            installment=conn.execute("SELECT * FROM installments WHERE tenant_id=? AND id=?",(tid,allocation.installment_id)).fetchone();paid=money(installment["paid_amount"]);new_paid=paid-money(allocation.amount)
            if new_paid<0:raise DomainError("REFUND_EXCEEDS_INSTALLMENT_PAID","Reembolso excede o valor pago da parcela.",409)
            due=installment_total_due(installment);state="paid" if new_paid>=due else ("partial" if new_paid>0 else "open")
            conn.execute("UPDATE installments SET paid_amount=?,state=?,updated_at=? WHERE tenant_id=? AND id=?",(money_str(new_paid),state,now,tid,allocation.installment_id));aid=uuid7();conn.execute("INSERT INTO payment_refund_allocations(id,tenant_id,payment_refund_id,installment_id,amount,created_at) VALUES(?,?,?,?,?,?)",(aid,tid,refund_id,allocation.installment_id,money_str(allocation.amount),now));refunded_allocations.append({"id":aid,"installment_id":allocation.installment_id,"amount":money_str(allocation.amount),"state":state})
        total_refunded=already+amount;payment_state="refunded" if total_refunded>=money(payment["amount"]) else "partially_refunded";conn.execute("UPDATE payments SET state=? WHERE tenant_id=? AND id=?",(payment_state,tid,payment_id));conn.execute("INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,debit_account,credit_account,amount,occurred_at,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,"refund","payment_refund",refund_id,"accounts_receivable","bank_or_cash",money_str(amount),now,"Reembolso/estorno de pagamento",now));result={"id":refund_id,"payment_id":payment_id,"amount":money_str(amount),"state":"confirmed","payment_state":payment_state,"allocations":refunded_allocations};add_audit(conn,tenant_id=tid,actor_id=user.id,action="refund",aggregate_type="payment",aggregate_id=payment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="PaymentRefunded",aggregate_type="payment",aggregate_id=payment_id,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result

@router.get("/finance/contracts/{contract_id}/renegotiations",operation_id="list_financial_renegotiations")
def list_renegotiations(contract_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FINANCE_ROLES|{"secretary"});tid=tenant(user);row_or_404(request,"SELECT id FROM financial_contracts WHERE tenant_id=? AND id=?",(tid,contract_id),"FINANCIAL_CONTRACT_NOT_FOUND","Contrato financeiro não localizado.");return {"items":request.state.store.fetch_all("SELECT * FROM financial_renegotiations WHERE tenant_id=? AND original_contract_id=? ORDER BY created_at DESC",(tid,contract_id))}

@router.post("/finance/contracts/{contract_id}/renegotiate",status_code=201,operation_id="renegotiate_financial_contract")
def renegotiate_contract(contract_id:str,data:RenegotiationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FINANCE_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM financial_contracts WHERE tenant_id=? AND id=?",(tid,contract_id)).fetchone()
        if not raw:raise DomainError("FINANCIAL_CONTRACT_NOT_FOUND","Contrato financeiro não localizado.",404)
        contract=dict(raw)
        if contract["state"] not in {"active","defaulted"}:raise DomainError("FINANCIAL_CONTRACT_NOT_RENEGOTIABLE","Contrato não aceita renegociação neste estado.",409)
        rows=conn.execute("SELECT * FROM installments WHERE tenant_id=? AND financial_contract_id=? AND state IN ('open','partial','overdue') ORDER BY sequence",(tid,contract_id)).fetchall();open_amount=Decimal("0")
        for row in rows:open_amount+=(installment_total_due(row)-money(row["paid_amount"]))
        open_amount=open_amount.quantize(CENT)
        if open_amount<=0:raise DomainError("NO_OPEN_BALANCE","Contrato não possui saldo em aberto para renegociação.",409)
        new_total=money(data.new_total_amount) if data.new_total_amount is not None else open_amount
        new_id=uuid7();description=f"Renegociação — {contract['description']}";conn.execute("INSERT INTO financial_contracts(id,tenant_id,enrollment_id,responsible_guardian_id,description,total_amount,currency,competence_rule,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(new_id,tid,contract.get("enrollment_id"),contract.get("responsible_guardian_id"),description,money_str(new_total),contract["currency"],contract["competence_rule"],"active",1,now,now));base=(new_total/Decimal(data.installments)).quantize(CENT,rounding=ROUND_HALF_UP);amounts=[base]*data.installments;amounts[-1]=(new_total-sum(amounts[:-1],Decimal("0"))).quantize(CENT)
        created=[]
        for seq,amt in enumerate(amounts,1):
            due=month_add(data.first_due_date,(seq-1)*data.interval_months);iid=uuid7();conn.execute("INSERT INTO installments(id,tenant_id,financial_contract_id,sequence,competence,due_date,original_amount,discount_amount,penalty_amount,interest_amount,paid_amount,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,tid,new_id,seq,due.strftime("%Y-%m"),str(due),money_str(amt),"0.00","0.00","0.00","0.00","open",now,now));created.append({"id":iid,"sequence":seq,"due_date":str(due),"amount":money_str(amt)})
        conn.execute("UPDATE installments SET state='renegotiated',updated_at=? WHERE tenant_id=? AND financial_contract_id=? AND state IN ('open','partial','overdue')",(now,tid,contract_id));conn.execute("UPDATE financial_contracts SET state='renegotiated',version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(now,tid,contract_id));ren_id=uuid7();conn.execute("INSERT INTO financial_renegotiations(id,tenant_id,original_contract_id,new_contract_id,original_open_amount,new_total_amount,reason,state,terms_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(ren_id,tid,contract_id,new_id,money_str(open_amount),money_str(new_total),data.reason,"completed",dumps({**data.terms,"installments":data.installments,"interval_months":data.interval_months}),user.id,now));result={"id":ren_id,"original_contract_id":contract_id,"new_contract_id":new_id,"original_open_amount":money_str(open_amount),"new_total_amount":money_str(new_total),"installments":created,"state":"completed"};add_audit(conn,tenant_id=tid,actor_id=user.id,action="renegotiate",aggregate_type="financial_contract",aggregate_id=contract_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="FinancialContractRenegotiated",aggregate_type="financial_contract",aggregate_id=contract_id,payload=result,correlation_id=request.state.correlation_id)
    return result
