from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import HR_ROLES, dec, dumps, loads, require, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["payroll"])
CENT=Decimal("0.01")
def money(v:Any)->Decimal:return dec(v)
def m(v:Decimal)->str:return format(v.quantize(CENT),".2f")

class PayrollRuleInput(BaseModel):
    code:str;name:str;direction:Literal["earning","deduction"];calculation_type:Literal["fixed","percentage"];basis:Literal["salary","gross"];value:Decimal;effective_from:date;effective_until:date|None=None;priority:int=100;metadata:dict[str,Any]=Field(default_factory=dict)
class PayrollRunInput(BaseModel):
    competence:str=Field(pattern=r"^\d{4}-\d{2}$");run_type:Literal["monthly","vacation","13th","termination","retroactive"]="monthly"

@router.get("/payroll/rules",operation_id="list_payroll_rules")
def list_payroll_rules(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);return {"items":request.state.store.fetch_all("SELECT * FROM payroll_rules WHERE tenant_id=? ORDER BY priority,code,version DESC",(tenant(user),))}

@router.post("/payroll/rules",status_code=201,operation_id="create_payroll_rule")
def create_payroll_rule(data:PayrollRuleInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);version=(request.state.store.scalar("SELECT COALESCE(MAX(version),0) AS n FROM payroll_rules WHERE tenant_id=? AND code=?",(tid,data.code)) or 0)+1;rid=uuid7();now=iso_now();result={"id":rid,"code":data.code,"name":data.name,"direction":data.direction,"calculation_type":data.calculation_type,"basis":data.basis,"value":str(data.value),"version":int(version),"state":"active"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO payroll_rules(id,tenant_id,code,name,direction,calculation_type,basis,value,effective_from,effective_until,priority,state,version,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.name,data.direction,data.calculation_type,data.basis,str(data.value),str(data.effective_from),str(data.effective_until) if data.effective_until else None,data.priority,"active",int(version),dumps(data.metadata),now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="payroll_rule",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.get("/payroll/runs",operation_id="list_payroll_runs_relational")
def list_payroll_runs(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);return {"items":request.state.store.fetch_all("SELECT * FROM payroll_runs WHERE tenant_id=? ORDER BY competence DESC,run_type",(tenant(user),))}

@router.post("/payroll/runs",status_code=201,operation_id="process_payroll_run_relational")
def process_payroll(data:PayrollRunInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);existing=request.state.store.fetch_one("SELECT * FROM payroll_runs WHERE tenant_id=? AND competence=? AND run_type=?",(tid,data.competence,data.run_type))
    if existing:raise DomainError("PAYROLL_RUN_EXISTS","Já existe processamento para esta competência/tipo.",409)
    ref=f"{data.competence}-01";rules=request.state.store.fetch_all("SELECT * FROM payroll_rules WHERE tenant_id=? AND state='active' AND effective_from<=? AND (effective_until IS NULL OR effective_until>=?) ORDER BY priority,code,version DESC",(tid,ref,ref));contracts=request.state.store.fetch_all("SELECT ec.*,e.state AS employee_state FROM employment_contracts ec JOIN employees e ON e.id=ec.employee_id WHERE ec.tenant_id=? AND ec.state='active' AND e.state='active' AND ec.starts_on<=? AND (ec.ends_on IS NULL OR ec.ends_on>=?)",(tid,ref,ref));rid=uuid7();now=iso_now();gross_total=Decimal("0");ded_total=Decimal("0");net_total=Decimal("0");entries=[]
    for contract in contracts:
        salary=money(contract["salary"] or 0);gross=salary;deductions=Decimal("0");items=[{"code":"BASE_SALARY","name":"Salário base","direction":"earning","amount":m(salary)}]
        year,month=(int(part) for part in data.competence.split("-",1));period_start=date(year,month,1);period_end=date(year,month,monthrange(year,month)[1])
        leaves=request.state.store.fetch_all("SELECT starts_on,ends_on,leave_type FROM personnel_leaves WHERE tenant_id=? AND employee_id=? AND state='approved' AND deduct_payroll=1 AND NOT(ends_on<? OR starts_on>?)",(tid,contract["employee_id"],str(period_start),str(period_end)))
        unpaid_days=0
        for leave in leaves:
            starts=max(period_start,date.fromisoformat(str(leave["starts_on"])));ends=min(period_end,date.fromisoformat(str(leave["ends_on"])));unpaid_days+=max(0,(ends-starts).days+1)
        if unpaid_days:
            leave_amount=min(salary,(salary/Decimal("30")*Decimal(unpaid_days)).quantize(CENT));deductions+=leave_amount;items.append({"code":"UNPAID_LEAVE","name":"Afastamento com impacto em folha","direction":"deduction","amount":m(leave_amount),"days":unpaid_days})
        for rule in rules:
            basis=salary if rule["basis"]=="salary" else gross;amount=money(rule["value"]) if rule["calculation_type"]=="fixed" else (basis*money(rule["value"])/Decimal("100")).quantize(CENT)
            if rule["direction"]=="earning":gross+=amount
            else:deductions+=amount
            items.append({"code":rule["code"],"name":rule["name"],"direction":rule["direction"],"amount":m(amount),"rule_version":rule["version"]})
        net=(gross-deductions).quantize(CENT);gross_total+=gross;ded_total+=deductions;net_total+=net;entries.append((contract["employee_id"],gross,deductions,net,items))
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO payroll_runs(id,tenant_id,competence,run_type,state,gross_total,deductions_total,net_total,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.competence,data.run_type,"processed",m(gross_total),m(ded_total),m(net_total),1,now,now))
        for employee_id,gross,deductions,net,items in entries:conn.execute("INSERT INTO payroll_entries(id,tenant_id,payroll_run_id,employee_id,gross_amount,deductions_amount,net_amount,items_json,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,rid,employee_id,m(gross),m(deductions),m(net),dumps(items),"calculated",now))
        result={"id":rid,"competence":data.competence,"run_type":data.run_type,"state":"processed","employees":len(entries),"gross_total":m(gross_total),"deductions_total":m(ded_total),"net_total":m(net_total)};add_audit(conn,tenant_id=tid,actor_id=user.id,action="process",aggregate_type="payroll_run",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="PayrollProcessed",aggregate_type="payroll_run",aggregate_id=rid,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/payroll/runs/{run_id}/entries",operation_id="list_payroll_entries")
def list_payroll_entries(run_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);items=request.state.store.fetch_all("SELECT pe.*,p.full_name AS employee_name FROM payroll_entries pe JOIN employees e ON e.id=pe.employee_id JOIN people p ON p.id=e.person_id WHERE pe.tenant_id=? AND pe.payroll_run_id=? ORDER BY p.full_name",(tid,run_id))
    for item in items:item["items"]=loads(item.pop("items_json"),[])
    return {"items":items}


class PayrollStateInput(BaseModel):
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=3,max_length=2000)

@router.post("/payroll/runs/{run_id}/close",operation_id="close_payroll_run")
def close_payroll(run_id:str,data:PayrollStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM payroll_runs WHERE tenant_id=? AND id=?",(tid,run_id)).fetchone()
        if not raw:raise DomainError("PAYROLL_RUN_NOT_FOUND","Processamento de folha não localizado.",404)
        row=dict(raw)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","A folha foi alterada por outro usuário.",409)
        if row["state"]!="processed":raise DomainError("PAYROLL_NOT_CLOSABLE","A folha não está em estado processado.",409)
        version=data.expected_version+1;conn.execute("UPDATE payroll_runs SET state='closed',version=?,updated_at=? WHERE tenant_id=? AND id=?",(version,now,tid,run_id));conn.execute("UPDATE payroll_entries SET state='final' WHERE tenant_id=? AND payroll_run_id=?",(tid,run_id));result={"id":run_id,"state":"closed","version":version,"competence":row["competence"],"run_type":row["run_type"]};add_audit(conn,tenant_id=tid,actor_id=user.id,action="close",aggregate_type="payroll_run",aggregate_id=run_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="PayrollClosed",aggregate_type="payroll_run",aggregate_id=run_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/payroll/runs/{run_id}/reopen",operation_id="reopen_payroll_run")
def reopen_payroll(run_id:str,data:PayrollStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM payroll_runs WHERE tenant_id=? AND id=?",(tid,run_id)).fetchone()
        if not raw:raise DomainError("PAYROLL_RUN_NOT_FOUND","Processamento de folha não localizado.",404)
        row=dict(raw)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","A folha foi alterada por outro usuário.",409)
        if row["state"]!="closed":raise DomainError("PAYROLL_NOT_CLOSED","A folha não está fechada.",409)
        version=data.expected_version+1;conn.execute("UPDATE payroll_runs SET state='processed',version=?,updated_at=? WHERE tenant_id=? AND id=?",(version,now,tid,run_id));conn.execute("UPDATE payroll_entries SET state='calculated' WHERE tenant_id=? AND payroll_run_id=?",(tid,run_id));result={"id":run_id,"state":"processed","version":version,"competence":row["competence"],"run_type":row["run_type"]};add_audit(conn,tenant_id=tid,actor_id=user.id,action="reopen",aggregate_type="payroll_run",aggregate_id=run_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="PayrollReopened",aggregate_type="payroll_run",aggregate_id=run_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/payroll/runs/{run_id}/payslips/{employee_id}",operation_id="get_employee_payslip")
def get_payslip(run_id:str,employee_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user)
    if not set(user.roles).intersection(HR_ROLES):
        if not user.person_id:raise DomainError("PERSON_LINK_REQUIRED","Conta sem pessoa vinculada.",409)
        own=request.state.store.fetch_one("SELECT id FROM employees WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id))
        if not own or own["id"]!=employee_id:raise DomainError("PERMISSION_DENIED","Acesso permitido somente ao próprio holerite.",403)
    run=request.state.store.fetch_one("SELECT * FROM payroll_runs WHERE tenant_id=? AND id=?",(tid,run_id))
    if not run:raise DomainError("PAYROLL_RUN_NOT_FOUND","Processamento de folha não localizado.",404)
    entry=request.state.store.fetch_one("SELECT pe.*,p.full_name AS employee_name,e.employee_number FROM payroll_entries pe JOIN employees e ON e.id=pe.employee_id JOIN people p ON p.id=e.person_id WHERE pe.tenant_id=? AND pe.payroll_run_id=? AND pe.employee_id=?",(tid,run_id,employee_id))
    if not entry:raise DomainError("PAYSLIP_NOT_FOUND","Holerite não localizado para o colaborador.",404)
    entry["items"]=loads(entry.pop("items_json"),[])
    return {"run":{"id":run["id"],"competence":run["competence"],"run_type":run["run_type"],"state":run["state"],"version":run["version"]},"payslip":entry}
