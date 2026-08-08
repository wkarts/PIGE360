from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import HR_ROLES, dec, dumps, require, row_or_404, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["hr"])
CENT = Decimal("0.01")
def money(v: Any) -> Decimal: return dec(v)
def m(v: Decimal) -> str: return format(v.quantize(CENT), ".2f")

class EmploymentInput(BaseModel):
    employee_id:str;contract_type:str;starts_on:date;ends_on:date|None=None;salary:Decimal|None=Field(default=None,ge=0);weekly_hours:Decimal|None=Field(default=None,ge=0);schedule:dict[str,Any]=Field(default_factory=dict)
class HrEventInput(BaseModel):
    employee_id:str;event_type:str;starts_on:date;ends_on:date|None=None;payload:dict[str,Any]=Field(default_factory=dict)

@router.get("/hr/employment-contracts",operation_id="list_employment_contracts")
def list_employment(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);return {"items":request.state.store.fetch_all("SELECT ec.*,p.full_name AS employee_name FROM employment_contracts ec JOIN employees e ON e.id=ec.employee_id JOIN people p ON p.id=e.person_id WHERE ec.tenant_id=? ORDER BY ec.starts_on DESC",(tid,))}

@router.post("/hr/employment-contracts",status_code=201,operation_id="create_employment_contract")
def create_employment(data:EmploymentInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM employees WHERE id=? AND tenant_id=?",(data.employee_id,tid),"EMPLOYEE_NOT_FOUND","Colaborador não localizado.");eid=uuid7();now=iso_now();result={"id":eid,"employee_id":data.employee_id,"contract_type":data.contract_type,"salary":m(money(data.salary)) if data.salary is not None else None,"state":"active"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO employment_contracts(id,tenant_id,employee_id,contract_type,starts_on,ends_on,salary,weekly_hours,schedule_json,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(eid,tid,data.employee_id,data.contract_type,str(data.starts_on),str(data.ends_on) if data.ends_on else None,result["salary"],str(data.weekly_hours) if data.weekly_hours is not None else None,dumps(data.schedule),"active",1,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="activate",aggregate_type="employment_contract",aggregate_id=eid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="EmployeeEmploymentActivated",aggregate_type="employment_contract",aggregate_id=eid,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/hr/events",status_code=201,operation_id="create_hr_event")
def create_hr_event(data:HrEventInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM employees WHERE id=? AND tenant_id=?",(data.employee_id,tid),"EMPLOYEE_NOT_FOUND","Colaborador não localizado.");eid=uuid7();now=iso_now();result={"id":eid,"employee_id":data.employee_id,"event_type":data.event_type,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on) if data.ends_on else None,"state":"active"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO hr_events(id,tenant_id,employee_id,event_type,starts_on,ends_on,payload_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(eid,tid,data.employee_id,data.event_type,str(data.starts_on),str(data.ends_on) if data.ends_on else None,dumps(data.payload),"active",now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="hr_event",aggregate_id=eid,correlation_id=request.state.correlation_id,after=result)
    return result
