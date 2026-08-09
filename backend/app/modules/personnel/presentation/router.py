from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from app.shared.application.sql import dumps, loads, row_or_404
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user
from app.shared.security.authorization import HR_ROLES, require_roles, tenant_id

router = APIRouter(tags=["personnel"])


class BenefitInput(BaseModel):
    employee_id: str
    benefit_type: str = Field(min_length=2, max_length=80)
    provider: str | None = Field(default=None, max_length=160)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    starts_on: date
    ends_on: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_period(self):
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on não pode anteceder starts_on")
        return self


class BenefitStateInput(BaseModel):
    expected_version: int = Field(ge=1)
    state: Literal["active", "suspended", "cancelled"]
    reason: str = Field(min_length=3, max_length=1000)


class LeaveInput(BaseModel):
    employee_id: str | None = None
    leave_type: str = Field(min_length=2, max_length=80)
    starts_on: date
    ends_on: date
    reason: str = Field(min_length=3, max_length=2000)
    deduct_payroll: bool = False
    deduct_timekeeping: bool = True
    document_id: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on não pode anteceder starts_on")
        return self


class ReviewInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)


class VacationInput(BaseModel):
    employee_id: str
    accrual_start: date
    accrual_end: date
    scheduled_start: date
    scheduled_end: date

    @model_validator(mode="after")
    def validate_periods(self):
        if self.accrual_end < self.accrual_start:
            raise ValueError("Período aquisitivo inválido")
        if self.scheduled_end < self.scheduled_start:
            raise ValueError("Período de férias inválido")
        return self


def _employee_for_user(request: Request, user: CurrentUser) -> dict[str, Any]:
    tid = tenant_id(user)
    if not user.person_id:
        raise DomainError("PERSON_LINK_REQUIRED", "Conta sem pessoa vinculada.", 409)
    return row_or_404(
        request,
        "SELECT e.*,p.full_name FROM employees e JOIN people p ON p.id=e.person_id WHERE e.tenant_id=? AND e.person_id=? AND e.state='active'",
        (tid, user.person_id),
        "EMPLOYEE_LINK_REQUIRED",
        "Conta não está vinculada a colaborador ativo.",
    )


def _employee(request: Request, tid: str, employee_id: str) -> dict[str, Any]:
    return row_or_404(
        request,
        "SELECT e.*,p.full_name FROM employees e JOIN people p ON p.id=e.person_id WHERE e.tenant_id=? AND e.id=?",
        (tid, employee_id),
        "EMPLOYEE_NOT_FOUND",
        "Colaborador não localizado.",
    )


@router.get("/personnel/benefits", operation_id="list_employee_benefits")
def list_benefits(request: Request, employee_id: str | None = None, user: CurrentUser = Depends(current_user)):
    require_roles(user, HR_ROLES)
    tid = tenant_id(user)
    sql = "SELECT b.*,p.full_name AS employee_name FROM employee_benefits b JOIN employees e ON e.id=b.employee_id JOIN people p ON p.id=e.person_id WHERE b.tenant_id=?"
    params: list[Any] = [tid]
    if employee_id:
        sql += " AND b.employee_id=?"; params.append(employee_id)
    sql += " ORDER BY b.starts_on DESC,b.created_at DESC"
    items = request.state.store.fetch_all(sql, params)
    for item in items:
        item["metadata"] = loads(item.pop("metadata_json", "{}"), {})
    return {"items": items}


@router.post("/personnel/benefits", status_code=201, operation_id="create_employee_benefit")
def create_benefit(data: BenefitInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user, HR_ROLES); tid = tenant_id(user); _employee(request, tid, data.employee_id)
    rid = uuid7(); now = iso_now()
    result = {"id": rid, "employee_id": data.employee_id, "benefit_type": data.benefit_type, "state": "active", "version": 1}
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO employee_benefits(id,tenant_id,employee_id,benefit_type,provider,amount,starts_on,ends_on,state,version,metadata_json,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid,tid,data.employee_id,data.benefit_type,data.provider,str(data.amount),str(data.starts_on),str(data.ends_on) if data.ends_on else None,"active",1,dumps(data.metadata),user.id,now,now),
        )
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="create", aggregate_type="employee_benefit", aggregate_id=rid, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tid, event_type="EmployeeBenefitActivated", aggregate_type="employee", aggregate_id=data.employee_id, payload=result, correlation_id=request.state.correlation_id)
    return result


@router.post("/personnel/benefits/{benefit_id}/state", operation_id="change_employee_benefit_state")
def change_benefit_state(benefit_id: str, data: BenefitStateInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user, HR_ROLES); tid = tenant_id(user); now = iso_now()
    with request.state.store.transaction() as conn:
        raw = conn.execute("SELECT * FROM employee_benefits WHERE tenant_id=? AND id=?", (tid, benefit_id)).fetchone()
        if not raw: raise DomainError("BENEFIT_NOT_FOUND", "Benefício não localizado.", 404)
        row = dict(raw)
        if int(row["version"]) != data.expected_version: raise DomainError("VERSION_CONFLICT", "O benefício foi alterado por outro usuário.", 409)
        version = data.expected_version + 1
        conn.execute("UPDATE employee_benefits SET state=?,version=?,updated_at=? WHERE tenant_id=? AND id=?", (data.state,version,now,tid,benefit_id))
        result={"id":benefit_id,"state":data.state,"version":version}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="change_state",aggregate_type="employee_benefit",aggregate_id=benefit_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result,reason=data.reason)
    return result


@router.get("/personnel/leaves", operation_id="list_personnel_leaves")
def list_leaves(request: Request, employee_id: str | None = None, user: CurrentUser = Depends(current_user)):
    tid=tenant_id(user)
    if set(user.roles).intersection(HR_ROLES): target=employee_id
    else: target=_employee_for_user(request,user)["id"]
    sql="SELECT l.*,p.full_name AS employee_name FROM personnel_leaves l JOIN employees e ON e.id=l.employee_id JOIN people p ON p.id=e.person_id WHERE l.tenant_id=?"; params:[Any]=[tid]
    if target: sql+=" AND l.employee_id=?"; params.append(target)
    sql+=" ORDER BY l.starts_on DESC,l.created_at DESC"
    return {"items":request.state.store.fetch_all(sql,params)}


@router.post("/personnel/leaves", status_code=201, operation_id="submit_personnel_leave")
def submit_leave(data: LeaveInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant_id(user)
    if set(user.roles).intersection(HR_ROLES):
        if not data.employee_id: raise DomainError("EMPLOYEE_REQUIRED", "Informe o colaborador.", 422)
        employee=_employee(request,tid,data.employee_id)
    else:
        employee=_employee_for_user(request,user)
        if data.employee_id and data.employee_id != employee["id"]: raise DomainError("PERMISSION_DENIED", "Não é permitido solicitar afastamento para outro colaborador.", 403)
    overlap=request.state.store.fetch_one("SELECT id FROM personnel_leaves WHERE tenant_id=? AND employee_id=? AND state IN ('submitted','approved') AND NOT(ends_on<? OR starts_on>?)",(tid,employee["id"],str(data.starts_on),str(data.ends_on)))
    if overlap: raise DomainError("LEAVE_PERIOD_CONFLICT", "Já existe afastamento sobreposto neste período.", 409)
    rid=uuid7();now=iso_now();result={"id":rid,"employee_id":employee["id"],"leave_type":data.leave_type,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on),"state":"submitted","version":1}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO personnel_leaves(id,tenant_id,employee_id,leave_type,starts_on,ends_on,reason,deduct_payroll,deduct_timekeeping,document_id,state,version,requested_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,employee["id"],data.leave_type,str(data.starts_on),str(data.ends_on),data.reason,1 if data.deduct_payroll else 0,1 if data.deduct_timekeeping else 0,data.document_id,"submitted",1,user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="submit",aggregate_type="personnel_leave",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tid,event_type="PersonnelLeaveSubmitted",aggregate_type="employee",aggregate_id=employee["id"],payload=result,correlation_id=request.state.correlation_id)
    return result


def _review_leave(leave_id:str,data:ReviewInput,request:Request,user:CurrentUser,state:str):
    require_roles(user,HR_ROLES);tid=tenant_id(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM personnel_leaves WHERE tenant_id=? AND id=?",(tid,leave_id)).fetchone()
        if not raw:raise DomainError("LEAVE_NOT_FOUND","Afastamento não localizado.",404)
        row=dict(raw)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","O afastamento foi alterado por outro usuário.",409)
        if row["state"]!="submitted":raise DomainError("LEAVE_NOT_REVIEWABLE","Afastamento não está pendente de análise.",409)
        version=data.expected_version+1
        conn.execute("UPDATE personnel_leaves SET state=?,version=?,approved_by=?,approved_at=?,rejection_reason=?,updated_at=? WHERE tenant_id=? AND id=?",(state,version,user.id,now,None if state=="approved" else data.reason,now,tid,leave_id))
        result={"id":leave_id,"state":state,"version":version,"employee_id":row["employee_id"]}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action=state,aggregate_type="personnel_leave",aggregate_id=leave_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="PersonnelLeaveApproved" if state=="approved" else "PersonnelLeaveRejected",aggregate_type="employee",aggregate_id=row["employee_id"],payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/personnel/leaves/{leave_id}/approve", operation_id="approve_personnel_leave")
def approve_leave(leave_id:str,data:ReviewInput,request:Request,user:CurrentUser=Depends(current_user)):return _review_leave(leave_id,data,request,user,"approved")

@router.post("/personnel/leaves/{leave_id}/reject", operation_id="reject_personnel_leave")
def reject_leave(leave_id:str,data:ReviewInput,request:Request,user:CurrentUser=Depends(current_user)):return _review_leave(leave_id,data,request,user,"rejected")


@router.get("/personnel/vacations", operation_id="list_vacation_periods")
def list_vacations(request:Request,employee_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant_id(user)
    if set(user.roles).intersection(HR_ROLES):target=employee_id
    else:target=_employee_for_user(request,user)["id"]
    sql="SELECT v.*,p.full_name AS employee_name FROM vacation_periods v JOIN employees e ON e.id=v.employee_id JOIN people p ON p.id=e.person_id WHERE v.tenant_id=?";params:[Any]=[tid]
    if target:sql+=" AND v.employee_id=?";params.append(target)
    sql+=" ORDER BY v.scheduled_start DESC"
    return {"items":request.state.store.fetch_all(sql,params)}


@router.post("/personnel/vacations",status_code=201,operation_id="schedule_vacation_period")
def schedule_vacation(data:VacationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require_roles(user,HR_ROLES);tid=tenant_id(user);_employee(request,tid,data.employee_id)
    overlap=request.state.store.fetch_one("SELECT id FROM vacation_periods WHERE tenant_id=? AND employee_id=? AND state IN ('scheduled','approved','active') AND NOT(scheduled_end<? OR scheduled_start>?)",(tid,data.employee_id,str(data.scheduled_start),str(data.scheduled_end)))
    if overlap:raise DomainError("VACATION_PERIOD_CONFLICT","Já existem férias sobrepostas neste período.",409)
    days=(data.scheduled_end-data.scheduled_start).days+1;rid=uuid7();now=iso_now();result={"id":rid,"employee_id":data.employee_id,"scheduled_start":str(data.scheduled_start),"scheduled_end":str(data.scheduled_end),"days":days,"state":"scheduled","version":1}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO vacation_periods(id,tenant_id,employee_id,accrual_start,accrual_end,scheduled_start,scheduled_end,days,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.employee_id,str(data.accrual_start),str(data.accrual_end),str(data.scheduled_start),str(data.scheduled_end),days,"scheduled",1,user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="schedule",aggregate_type="vacation_period",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tid,event_type="VacationScheduled",aggregate_type="employee",aggregate_id=data.employee_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/personnel/vacations/{vacation_id}/approve",operation_id="approve_vacation_period")
def approve_vacation(vacation_id:str,data:ReviewInput,request:Request,user:CurrentUser=Depends(current_user)):
    require_roles(user,HR_ROLES);tid=tenant_id(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM vacation_periods WHERE tenant_id=? AND id=?",(tid,vacation_id)).fetchone()
        if not raw:raise DomainError("VACATION_NOT_FOUND","Férias não localizadas.",404)
        row=dict(raw)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","As férias foram alteradas por outro usuário.",409)
        if row["state"]!="scheduled":raise DomainError("VACATION_NOT_APPROVABLE","Férias não estão aguardando aprovação.",409)
        version=data.expected_version+1;conn.execute("UPDATE vacation_periods SET state='approved',version=?,approved_by=?,approved_at=?,updated_at=? WHERE tenant_id=? AND id=?",(version,user.id,now,now,tid,vacation_id));result={"id":vacation_id,"state":"approved","version":version,"employee_id":row["employee_id"]};add_audit(conn,tenant_id=tid,actor_id=user.id,action="approve",aggregate_type="vacation_period",aggregate_id=vacation_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="VacationApproved",aggregate_type="employee",aggregate_id=row["employee_id"],payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/personnel/vacations/{vacation_id}/cancel",operation_id="cancel_vacation_period")
def cancel_vacation(vacation_id:str,data:ReviewInput,request:Request,user:CurrentUser=Depends(current_user)):
    require_roles(user,HR_ROLES);tid=tenant_id(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM vacation_periods WHERE tenant_id=? AND id=?",(tid,vacation_id)).fetchone()
        if not raw:raise DomainError("VACATION_NOT_FOUND","Férias não localizadas.",404)
        row=dict(raw)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","As férias foram alteradas por outro usuário.",409)
        if row["state"] in {"completed","cancelled"}:raise DomainError("VACATION_NOT_CANCELLABLE","Férias não podem mais ser canceladas.",409)
        version=data.expected_version+1;conn.execute("UPDATE vacation_periods SET state='cancelled',version=?,cancellation_reason=?,updated_at=? WHERE tenant_id=? AND id=?",(version,data.reason,now,tid,vacation_id));result={"id":vacation_id,"state":"cancelled","version":version,"employee_id":row["employee_id"]};add_audit(conn,tenant_id=tid,actor_id=user.id,action="cancel",aggregate_type="vacation_period",aggregate_id=vacation_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="VacationCancelled",aggregate_type="employee",aggregate_id=row["employee_id"],payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/personnel/employees/{employee_id}/timeline", operation_id="get_employee_personnel_timeline")
def personnel_timeline(employee_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant_id(user)
    if set(user.roles).intersection(HR_ROLES): _employee(request,tid,employee_id)
    else:
        own=_employee_for_user(request,user)
        if own["id"]!=employee_id:raise DomainError("PERMISSION_DENIED","Acesso permitido somente ao próprio histórico funcional.",403)
    timeline:list[dict[str,Any]]=[]
    for row in request.state.store.fetch_all("SELECT id,contract_type,starts_on,ends_on,state,created_at FROM employment_contracts WHERE tenant_id=? AND employee_id=?",(tid,employee_id)):
        timeline.append({"kind":"employment_contract","occurred_at":row["starts_on"],**row})
    for row in request.state.store.fetch_all("SELECT id,event_type,starts_on,ends_on,state,created_at,payload_json FROM hr_events WHERE tenant_id=? AND employee_id=?",(tid,employee_id)):
        row["payload"]=loads(row.pop("payload_json","{}"),{});timeline.append({"kind":"hr_event","occurred_at":row["starts_on"],**row})
    for row in request.state.store.fetch_all("SELECT id,leave_type,starts_on,ends_on,state,created_at FROM personnel_leaves WHERE tenant_id=? AND employee_id=?",(tid,employee_id)):
        timeline.append({"kind":"leave","occurred_at":row["starts_on"],**row})
    for row in request.state.store.fetch_all("SELECT id,scheduled_start,scheduled_end,state,created_at FROM vacation_periods WHERE tenant_id=? AND employee_id=?",(tid,employee_id)):
        timeline.append({"kind":"vacation","occurred_at":row["scheduled_start"],**row})
    for row in request.state.store.fetch_all("SELECT id,benefit_type,starts_on,ends_on,state,created_at FROM employee_benefits WHERE tenant_id=? AND employee_id=?",(tid,employee_id)):
        timeline.append({"kind":"benefit","occurred_at":row["starts_on"],**row})
    timeline.sort(key=lambda x:(str(x.get("occurred_at") or ""),str(x.get("created_at") or "")),reverse=True)
    return {"employee_id":employee_id,"items":timeline}
