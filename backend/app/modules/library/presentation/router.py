from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.library.application.service import active_policy, ensure_policy, promote_next_reservation
from app.modules.operations.common import ADMIN_ROLES, dumps, loads, require, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["library"])
LIBRARY_ROLES=ADMIN_ROLES|{"library_manager","auditor"}

class PolicyInput(BaseModel):
    code:str="default";effective_from:date;max_loan_days:int=Field(ge=1,le=365);max_renewals:int=Field(ge=0,le=20);grace_days:int=Field(default=0,ge=0,le=30);daily_fine:str="0.00";reservation_hold_hours:int=Field(default=48,ge=1,le=720)
class ReservationInput(BaseModel):library_item_id:str;person_id:str|None=None
class ReservationCancelInput(BaseModel):reason:str=Field(min_length=3,max_length=500)
class RenewInput(BaseModel):reason:str=Field(min_length=3,max_length=500)
class FineSettleInput(BaseModel):action:Literal["paid","waived"];reason:str=Field(min_length=3,max_length=500)


def _can_manage(user:CurrentUser)->bool:return bool(set(user.roles).intersection(LIBRARY_ROLES))
def _person(user:CurrentUser,requested:str|None)->str:
    if requested and _can_manage(user):return requested
    if user.person_id:return user.person_id
    raise DomainError("PERSON_CONTEXT_REQUIRED","O usuário não possui pessoa vinculada.",422)

@router.get("/library/policies",operation_id="list_library_policies")
def policies(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,LIBRARY_ROLES);tid=tenant(user);return {"items":request.state.store.fetch_all("SELECT * FROM library_policies WHERE tenant_id=? ORDER BY effective_from DESC,version DESC",(tid,))}

@router.post("/library/policies",status_code=201,operation_id="create_library_policy_version")
def create_policy(data:PolicyInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,LIBRARY_ROLES);tid=tenant(user);now=iso_now();latest=request.state.store.fetch_one("SELECT MAX(version) AS version FROM library_policies WHERE tenant_id=? AND code=?",(tid,data.code));version=int(latest["version"] or 0)+1;pid=uuid7();result={"id":pid,"code":data.code,"version":version,"effective_from":str(data.effective_from),"state":"active"}
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE library_policies SET state='superseded',updated_at=? WHERE tenant_id=? AND code=? AND state='active' AND effective_from<=?",(now,tid,data.code,str(data.effective_from)))
        conn.execute("INSERT INTO library_policies(id,tenant_id,code,version,effective_from,max_loan_days,max_renewals,grace_days,daily_fine,reservation_hold_hours,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,tid,data.code,version,str(data.effective_from),data.max_loan_days,data.max_renewals,data.grace_days,data.daily_fine,data.reservation_hold_hours,"active",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="library_policy",aggregate_id=pid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.get("/library/reservations",operation_id="list_library_reservations")
def reservations(request:Request,person_id:str|None=None,state:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);manager=_can_manage(user);target=person_id if manager else user.person_id
    sql="SELECT r.*,i.title,i.inventory_code FROM library_reservations r JOIN library_items i ON i.id=r.library_item_id WHERE r.tenant_id=?";params:list[Any]=[tid]
    if target:sql+=" AND r.person_id=?";params.append(target)
    elif not manager:return {"items":[]}
    if state:sql+=" AND r.state=?";params.append(state)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY r.queued_at DESC",params)}

@router.post("/library/reservations",status_code=201,operation_id="create_library_reservation")
def reserve(data:ReservationInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);person_id=_person(user,data.person_id);item=request.state.store.fetch_one("SELECT * FROM library_items WHERE tenant_id=? AND id=?",(tid,data.library_item_id))
    if not item:raise DomainError("LIBRARY_ITEM_NOT_FOUND","Exemplar não localizado.",404)
    if request.state.store.fetch_one("SELECT id FROM library_reservations WHERE tenant_id=? AND library_item_id=? AND person_id=? AND state IN ('queued','ready')",(tid,data.library_item_id,person_id)):raise DomainError("LIBRARY_RESERVATION_EXISTS","Já existe reserva ativa para esta pessoa.",409)
    if request.state.store.fetch_one("SELECT id FROM library_loans WHERE tenant_id=? AND library_item_id=? AND person_id=? AND state='open'",(tid,data.library_item_id,person_id)):raise DomainError("LIBRARY_ITEM_ALREADY_LOANED_TO_PERSON","A pessoa já está com este exemplar emprestado.",409)
    now=datetime.now(UTC);rid=uuid7();state="queued";ready_at=None;expires_at=None
    with request.state.store.transaction() as conn:
        policy=ensure_policy(conn,tid,user.id)
        if item["state"]=="available":state="ready";ready_at=now.isoformat();expires_at=(now+timedelta(hours=int(policy["reservation_hold_hours"]))).isoformat();conn.execute("UPDATE library_items SET state='reserved',updated_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),tid,data.library_item_id))
        conn.execute("INSERT INTO library_reservations(id,tenant_id,library_item_id,person_id,state,queued_at,ready_at,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(rid,tid,data.library_item_id,person_id,state,now.isoformat(),ready_at,expires_at,now.isoformat()));add_audit(conn,tenant_id=tid,actor_id=user.id,action="reserve",aggregate_type="library_item",aggregate_id=data.library_item_id,correlation_id=request.state.correlation_id,after={"reservation_id":rid,"person_id":person_id,"state":state});add_outbox(conn,tenant_id=tid,event_type="LibraryItemReserved",aggregate_type="library_reservation",aggregate_id=rid,payload={"library_item_id":data.library_item_id,"person_id":person_id,"state":state},correlation_id=request.state.correlation_id)
    return {"id":rid,"library_item_id":data.library_item_id,"person_id":person_id,"state":state,"ready_at":ready_at,"expires_at":expires_at}

@router.post("/library/reservations/{reservation_id}/cancel",operation_id="cancel_library_reservation")
def cancel_reservation(reservation_id:str,data:ReservationCancelInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM library_reservations WHERE tenant_id=? AND id=?",(tid,reservation_id))
    if not row or (not _can_manage(user) and row["person_id"]!=user.person_id):raise DomainError("LIBRARY_RESERVATION_NOT_FOUND","Reserva não localizada.",404)
    if row["state"] not in {"queued","ready"}:return {"id":reservation_id,"state":row["state"]}
    now=datetime.now(UTC)
    with request.state.store.transaction() as conn:
        policy=ensure_policy(conn,tid,user.id);conn.execute("UPDATE library_reservations SET state='cancelled',cancelled_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),tid,reservation_id))
        if row["state"]=="ready":promote_next_reservation(conn,tenant_id=tid,item_id=row["library_item_id"],policy=policy,now=now)
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="cancel_reservation",aggregate_type="library_reservation",aggregate_id=reservation_id,correlation_id=request.state.correlation_id,after={"state":"cancelled"},reason=data.reason)
    return {"id":reservation_id,"state":"cancelled"}

@router.post("/library/loans/{loan_id}/renew",operation_id="renew_library_loan")
def renew(loan_id:str,data:RenewInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);loan=request.state.store.fetch_one("SELECT * FROM library_loans WHERE tenant_id=? AND id=?",(tid,loan_id))
    if not loan or (not _can_manage(user) and loan["person_id"]!=user.person_id):raise DomainError("LOAN_NOT_FOUND","Empréstimo não localizado.",404)
    if loan["state"]!="open":raise DomainError("LOAN_NOT_OPEN","Empréstimo não está aberto.",409)
    now=datetime.now(UTC)
    with request.state.store.transaction() as conn:
        policy=ensure_policy(conn,tid,user.id)
        if int(loan["renewal_count"] or 0)>=int(policy["max_renewals"]):raise DomainError("LOAN_RENEWAL_LIMIT","Limite de renovações atingido.",409)
        waiting=conn.execute("SELECT id FROM library_reservations WHERE tenant_id=? AND library_item_id=? AND person_id<>? AND state IN ('queued','ready') LIMIT 1",(tid,loan["library_item_id"],loan["person_id"])).fetchone()
        if waiting:raise DomainError("LOAN_RENEWAL_BLOCKED_BY_RESERVATION","Existe reserva de outra pessoa para este exemplar.",409)
        base=max(datetime.fromisoformat(loan["due_at"]),now);new_due=(base+timedelta(days=int(policy["max_loan_days"]))).isoformat();count=int(loan["renewal_count"] or 0)+1
        conn.execute("UPDATE library_loans SET due_at=?,renewal_count=?,policy_version=? WHERE tenant_id=? AND id=?",(new_due,count,int(policy["version"]),tid,loan_id));conn.execute("INSERT INTO library_loan_events(id,tenant_id,library_loan_id,event_type,payload_json,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,loan_id,"renewed",dumps({"due_at":new_due,"renewal_count":count,"reason":data.reason}),user.id,now.isoformat()));add_audit(conn,tenant_id=tid,actor_id=user.id,action="renew",aggregate_type="library_loan",aggregate_id=loan_id,correlation_id=request.state.correlation_id,after={"due_at":new_due,"renewal_count":count},reason=data.reason)
    return {"id":loan_id,"state":"open","due_at":new_due,"renewal_count":count}

@router.get("/library/fines",operation_id="list_library_fines")
def fines(request:Request,person_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);manager=_can_manage(user);target=person_id if manager else user.person_id
    sql="SELECT f.*,i.title FROM library_fines f JOIN library_loans l ON l.id=f.library_loan_id JOIN library_items i ON i.id=l.library_item_id WHERE f.tenant_id=?";params:list[Any]=[tid]
    if target:sql+=" AND f.person_id=?";params.append(target)
    elif not manager:return {"items":[]}
    rows=request.state.store.fetch_all(sql+" ORDER BY f.issued_at DESC",params)
    for row in rows: row["amount"]=f"{Decimal(str(row['amount'])):.2f}"
    return {"items":rows}

@router.post("/library/fines/{fine_id}/settle",operation_id="settle_library_fine")
def settle(fine_id:str,data:FineSettleInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,LIBRARY_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM library_fines WHERE tenant_id=? AND id=?",(tid,fine_id))
    if not row:raise DomainError("LIBRARY_FINE_NOT_FOUND","Multa não localizada.",404)
    if row["state"]!="open":return {"id":fine_id,"state":row["state"]}
    now=iso_now();request.state.store.execute("UPDATE library_fines SET state=?,settled_at=?,settlement_reason=? WHERE tenant_id=? AND id=?",(data.action,now,data.reason,tid,fine_id));return {"id":fine_id,"state":data.action,"settled_at":now}
