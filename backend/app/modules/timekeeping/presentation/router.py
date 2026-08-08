from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel

from app.modules.operations.common import HR_ROLES, require, row_or_404, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["timekeeping"])

class TimeEntryInput(BaseModel):
    event_type:Literal["clock_in","break_out","break_in","clock_out"];occurred_at:datetime|None=None;origin:Literal["app","kiosk","rep","manual"]="app";device_id:str|None=None;latitude:Decimal|None=None;longitude:Decimal|None=None


def _validate_time_sequence(conn, tenant_id: str, employee_id: str, occurred_at: str, event_type: str) -> None:
    day = occurred_at[:10]
    rows = conn.execute(
        "SELECT event_type FROM time_entries WHERE tenant_id=? AND employee_id=? AND occurred_at>=? AND occurred_at<? AND state='valid' ORDER BY occurred_at,id",
        (tenant_id, employee_id, f"{day}T00:00:00", f"{day}T23:59:59.999999+00:00"),
    ).fetchall()
    events = [str(row["event_type"] if hasattr(row, "keys") else row[0]) for row in rows]
    if not events:
        if event_type != "clock_in":
            raise DomainError("TIMEKEEPING_INVALID_SEQUENCE", "A jornada deve iniciar com entrada.", 409)
        return
    last = events[-1]
    allowed = {
        "clock_in": {"break_out", "clock_out"},
        "break_out": {"break_in"},
        "break_in": {"break_out", "clock_out"},
        "clock_out": set(),
    }.get(last, set())
    if event_type not in allowed:
        raise DomainError("TIMEKEEPING_INVALID_SEQUENCE", f"Marcação {event_type} inválida após {last}.", 409)

@router.get("/timekeeping/entries",operation_id="list_time_entries_relational")
def list_time_entries(request:Request,employee_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user)
    if set(user.roles).intersection(HR_ROLES):target=employee_id
    else:
        if not user.person_id:raise DomainError("PERSON_LINK_REQUIRED","Conta sem pessoa vinculada.",409)
        employee=row_or_404(request,"SELECT id FROM employees WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id),"EMPLOYEE_LINK_REQUIRED","Conta não está vinculada a colaborador ativo.");target=employee["id"]
    sql="SELECT * FROM time_entries WHERE tenant_id=?";params:[Any]=[tid]
    if target:sql+=" AND employee_id=?";params.append(target)
    sql+=" ORDER BY occurred_at DESC LIMIT 500";return {"items":request.state.store.fetch_all(sql,params)}

@router.post("/timekeeping/me/entries",status_code=201,operation_id="clock_current_employee")
def clock_me(data:TimeEntryInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    tid=tenant(user)
    if not user.person_id:raise DomainError("PERSON_LINK_REQUIRED","Conta sem pessoa vinculada.",409)
    employee=row_or_404(request,"SELECT id FROM employees WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id),"EMPLOYEE_LINK_REQUIRED","Conta não está vinculada a colaborador ativo.");scope=f"time-entry:{tid}:{employee['id']}";body=data.model_dump(mode="json");occurred=(data.occurred_at or datetime.now(UTC)).isoformat()
    competence=occurred[:7]
    closure=request.state.store.fetch_one("SELECT state FROM timekeeping_period_closures WHERE tenant_id=? AND competence=?",(tid,competence))
    if closure and closure["state"]=="closed":raise DomainError("TIMEKEEPING_PERIOD_CLOSED","A competência do ponto está fechada para novas marcações.",409)
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        _validate_time_sequence(conn,tid,employee["id"],occurred,data.event_type)
        eid=uuid7();now=iso_now();conn.execute("INSERT INTO time_entries(id,tenant_id,employee_id,occurred_at,event_type,origin,device_id,latitude,longitude,idempotency_key,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(eid,tid,employee["id"],occurred,data.event_type,data.origin,data.device_id,str(data.latitude) if data.latitude is not None else None,str(data.longitude) if data.longitude is not None else None,idempotency_key,"valid",now));result={"id":eid,"employee_id":employee["id"],"occurred_at":occurred,"event_type":data.event_type,"origin":data.origin,"state":"valid"};add_audit(conn,tenant_id=tid,actor_id=user.id,action="clock",aggregate_type="time_entry",aggregate_id=eid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="TimeEntryRegistered",aggregate_type="employee",aggregate_id=employee["id"],payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result


class TimeAdjustmentInput(BaseModel):
    employee_id: str | None = None
    time_entry_id: str | None = None
    requested_event_type: Literal["clock_in","break_out","break_in","clock_out"]
    requested_occurred_at: datetime
    reason: str

class TimeAdjustmentReview(BaseModel):
    expected_version: int
    reason: str

class PeriodClosureInput(BaseModel):
    competence: str
    reason: str


def _employee_for_actor(request:Request,user:CurrentUser,employee_id:str|None=None)->dict[str,Any]:
    tid=tenant(user)
    if set(user.roles).intersection(HR_ROLES):
        if not employee_id:raise DomainError("EMPLOYEE_REQUIRED","Informe o colaborador.",422)
        return row_or_404(request,"SELECT id,person_id FROM employees WHERE tenant_id=? AND id=? AND state='active'",(tid,employee_id),"EMPLOYEE_NOT_FOUND","Colaborador não localizado.")
    if not user.person_id:raise DomainError("PERSON_LINK_REQUIRED","Conta sem pessoa vinculada.",409)
    own=row_or_404(request,"SELECT id,person_id FROM employees WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id),"EMPLOYEE_LINK_REQUIRED","Conta não está vinculada a colaborador ativo.")
    if employee_id and employee_id!=own["id"]:raise DomainError("PERMISSION_DENIED","Não é permitido ajustar o ponto de outro colaborador.",403)
    return own


def _validate_full_day_sequence(conn,tenant_id:str,employee_id:str,day:str,candidate_at:str,candidate_type:str,exclude_id:str|None=None)->None:
    rows=conn.execute("SELECT id,occurred_at,event_type FROM time_entries WHERE tenant_id=? AND employee_id=? AND occurred_at>=? AND occurred_at<? AND state='valid' ORDER BY occurred_at,id",(tenant_id,employee_id,f"{day}T00:00:00",f"{day}T23:59:59.999999+00:00")).fetchall()
    events=[]
    for row in rows:
        d=dict(row)
        if exclude_id and d["id"]==exclude_id:continue
        events.append((str(d["occurred_at"]),str(d["event_type"])))
    events.append((candidate_at,candidate_type));events.sort(key=lambda x:x[0])
    allowed_first="clock_in";last=None
    transitions={"clock_in":{"break_out","clock_out"},"break_out":{"break_in"},"break_in":{"break_out","clock_out"},"clock_out":set()}
    for _,event in events:
        if last is None:
            if event!=allowed_first:raise DomainError("TIMEKEEPING_INVALID_SEQUENCE","A jornada deve iniciar com entrada.",409)
        elif event not in transitions.get(last,set()):
            raise DomainError("TIMEKEEPING_INVALID_SEQUENCE",f"Sequência inválida: {event} após {last}.",409)
        last=event


@router.get("/timekeeping/adjustments",operation_id="list_timekeeping_adjustments")
def list_adjustments(request:Request,employee_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);employee=_employee_for_actor(request,user,employee_id) if not set(user.roles).intersection(HR_ROLES) else None
    target=employee["id"] if employee else employee_id
    sql="SELECT a.*,p.full_name AS employee_name FROM timekeeping_adjustments a JOIN employees e ON e.id=a.employee_id JOIN people p ON p.id=e.person_id WHERE a.tenant_id=?";params:[Any]=[tid]
    if target:sql+=" AND a.employee_id=?";params.append(target)
    sql+=" ORDER BY a.created_at DESC"
    return {"items":request.state.store.fetch_all(sql,params)}

@router.post("/timekeeping/adjustments",status_code=201,operation_id="request_timekeeping_adjustment")
def request_adjustment(data:TimeAdjustmentInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);employee=_employee_for_actor(request,user,data.employee_id);occurred=data.requested_occurred_at.isoformat();competence=occurred[:7]
    closure=request.state.store.fetch_one("SELECT state FROM timekeeping_period_closures WHERE tenant_id=? AND competence=?",(tid,competence))
    if closure and closure["state"]=="closed" and not set(user.roles).intersection(HR_ROLES):raise DomainError("TIMEKEEPING_PERIOD_CLOSED","A competência está fechada; solicite reabertura ao RH.",409)
    if data.time_entry_id:
        row_or_404(request,"SELECT id FROM time_entries WHERE tenant_id=? AND id=? AND employee_id=?",(tid,data.time_entry_id,employee["id"]),"TIME_ENTRY_NOT_FOUND","Marcação original não localizada.")
    rid=uuid7();now=iso_now();result={"id":rid,"employee_id":employee["id"],"state":"submitted","version":1,"requested_event_type":data.requested_event_type,"requested_occurred_at":occurred}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO timekeeping_adjustments(id,tenant_id,employee_id,time_entry_id,requested_event_type,requested_occurred_at,reason,state,version,requested_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,employee["id"],data.time_entry_id,data.requested_event_type,occurred,data.reason,"submitted",1,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="request_adjustment",aggregate_type="timekeeping_adjustment",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="TimekeepingAdjustmentRequested",aggregate_type="employee",aggregate_id=employee["id"],payload=result,correlation_id=request.state.correlation_id)
    return result


def _review_adjustment(adjustment_id:str,data:TimeAdjustmentReview,request:Request,user:CurrentUser,approve:bool):
    require(user,HR_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM timekeeping_adjustments WHERE tenant_id=? AND id=?",(tid,adjustment_id)).fetchone()
        if not raw:raise DomainError("TIMEKEEPING_ADJUSTMENT_NOT_FOUND","Solicitação de ajuste não localizada.",404)
        row=dict(raw)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","O ajuste foi alterado por outro usuário.",409)
        if row["state"]!="submitted":raise DomainError("TIMEKEEPING_ADJUSTMENT_NOT_REVIEWABLE","Ajuste não está pendente de análise.",409)
        version=data.expected_version+1;replacement=None
        if approve:
            competence=str(row["requested_occurred_at"])[:7]
            closure=conn.execute("SELECT state FROM timekeeping_period_closures WHERE tenant_id=? AND competence=?",(tid,competence)).fetchone()
            if closure and dict(closure)["state"]=="closed":raise DomainError("TIMEKEEPING_PERIOD_CLOSED","Reabra a competência antes de aprovar ajustes.",409)
            _validate_full_day_sequence(conn,tid,row["employee_id"],str(row["requested_occurred_at"])[:10],str(row["requested_occurred_at"]),row["requested_event_type"],row.get("time_entry_id"))
            if row.get("time_entry_id"):conn.execute("UPDATE time_entries SET state='superseded' WHERE tenant_id=? AND id=?",(tid,row["time_entry_id"]))
            replacement=uuid7();conn.execute("INSERT INTO time_entries(id,tenant_id,employee_id,occurred_at,event_type,origin,device_id,latitude,longitude,idempotency_key,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(replacement,tid,row["employee_id"],row["requested_occurred_at"],row["requested_event_type"],"manual",None,None,None,None,"valid",now))
        state="approved" if approve else "rejected";conn.execute("UPDATE timekeeping_adjustments SET state=?,version=?,reviewed_by=?,reviewed_at=?,review_reason=?,replacement_entry_id=?,updated_at=? WHERE tenant_id=? AND id=?",(state,version,user.id,now,data.reason,replacement,now,tid,adjustment_id));result={"id":adjustment_id,"state":state,"version":version,"replacement_entry_id":replacement,"employee_id":row["employee_id"]};add_audit(conn,tenant_id=tid,actor_id=user.id,action=state,aggregate_type="timekeeping_adjustment",aggregate_id=adjustment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="TimekeepingAdjustmentApproved" if approve else "TimekeepingAdjustmentRejected",aggregate_type="employee",aggregate_id=row["employee_id"],payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/timekeeping/adjustments/{adjustment_id}/approve",operation_id="approve_timekeeping_adjustment")
def approve_adjustment(adjustment_id:str,data:TimeAdjustmentReview,request:Request,user:CurrentUser=Depends(current_user)):return _review_adjustment(adjustment_id,data,request,user,True)

@router.post("/timekeeping/adjustments/{adjustment_id}/reject",operation_id="reject_timekeeping_adjustment")
def reject_adjustment(adjustment_id:str,data:TimeAdjustmentReview,request:Request,user:CurrentUser=Depends(current_user)):return _review_adjustment(adjustment_id,data,request,user,False)

@router.get("/timekeeping/summary",operation_id="get_timekeeping_summary")
def timekeeping_summary(request:Request,employee_id:str|None=None,date_from:str|None=None,date_to:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);employee=_employee_for_actor(request,user,employee_id);start=date_from or datetime.now(UTC).strftime("%Y-%m-01");end=date_to or datetime.now(UTC).strftime("%Y-%m-%d")
    rows=request.state.store.fetch_all("SELECT occurred_at,event_type FROM time_entries WHERE tenant_id=? AND employee_id=? AND state='valid' AND substr(occurred_at,1,10)>=? AND substr(occurred_at,1,10)<=? ORDER BY occurred_at,id",(tid,employee["id"],start,end));by_day:dict[str,list[dict[str,Any]]]={}
    for row in rows:by_day.setdefault(str(row["occurred_at"])[:10],[]).append(row)
    days=[];total=0
    for day,events in sorted(by_day.items()):
        seconds=0;active:datetime|None=None
        for event in events:
            at=datetime.fromisoformat(str(event["occurred_at"]).replace("Z","+00:00"));typ=event["event_type"]
            if typ in {"clock_in","break_in"}:active=at
            elif typ in {"break_out","clock_out"} and active is not None:seconds+=max(0,int((at-active).total_seconds()));active=None
        total+=seconds;days.append({"date":day,"worked_minutes":seconds//60,"entries":len(events),"open":active is not None})
    return {"employee_id":employee["id"],"date_from":start,"date_to":end,"worked_minutes":total//60,"days":days}

@router.get("/timekeeping/closures",operation_id="list_timekeeping_closures")
def list_closures(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);return {"items":request.state.store.fetch_all("SELECT * FROM timekeeping_period_closures WHERE tenant_id=? ORDER BY competence DESC",(tenant(user),))}

@router.post("/timekeeping/closures/close",operation_id="close_timekeeping_period")
def close_period(data:PeriodClosureInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);now=iso_now();existing=request.state.store.fetch_one("SELECT * FROM timekeeping_period_closures WHERE tenant_id=? AND competence=?",(tid,data.competence))
    with request.state.store.transaction() as conn:
        if existing:
            if existing["state"]=="closed":raise DomainError("TIMEKEEPING_PERIOD_ALREADY_CLOSED","Competência já está fechada.",409)
            version=int(existing["version"])+1;conn.execute("UPDATE timekeeping_period_closures SET state='closed',version=?,closed_by=?,closed_at=?,updated_at=? WHERE tenant_id=? AND competence=?",(version,user.id,now,now,tid,data.competence));rid=existing["id"]
        else:
            rid=uuid7();version=1;conn.execute("INSERT INTO timekeeping_period_closures(id,tenant_id,competence,state,version,closed_by,closed_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(rid,tid,data.competence,"closed",version,user.id,now,now,now))
        result={"id":rid,"competence":data.competence,"state":"closed","version":version};add_audit(conn,tenant_id=tid,actor_id=user.id,action="close",aggregate_type="timekeeping_period",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="TimekeepingPeriodClosed",aggregate_type="timekeeping_period",aggregate_id=rid,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/timekeeping/closures/{competence}/reopen",operation_id="reopen_timekeeping_period")
def reopen_period(competence:str,data:PeriodClosureInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HR_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM timekeeping_period_closures WHERE tenant_id=? AND competence=?",(tid,competence)).fetchone()
        if not raw:raise DomainError("TIMEKEEPING_PERIOD_NOT_FOUND","Fechamento de competência não localizado.",404)
        row=dict(raw)
        if row["state"]!="closed":raise DomainError("TIMEKEEPING_PERIOD_NOT_CLOSED","Competência não está fechada.",409)
        version=int(row["version"])+1;conn.execute("UPDATE timekeeping_period_closures SET state='reopened',version=?,reopened_by=?,reopened_at=?,reopen_reason=?,updated_at=? WHERE tenant_id=? AND competence=?",(version,user.id,now,data.reason,now,tid,competence));result={"id":row["id"],"competence":competence,"state":"reopened","version":version};add_audit(conn,tenant_id=tid,actor_id=user.id,action="reopen",aggregate_type="timekeeping_period",aggregate_id=row["id"],correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="TimekeepingPeriodReopened",aggregate_type="timekeeping_period",aggregate_id=row["id"],payload=result,correlation_id=request.state.correlation_id)
    return result
