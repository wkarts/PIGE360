from __future__ import annotations

from datetime import date, time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, model_validator

from app.modules.operations.common import ADMIN_ROLES, dumps, loads, require, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["transportation"])
TRANSPORT_ROLES=ADMIN_ROLES|{"transport_manager","unit_manager"}

class ScheduleInput(BaseModel):
    route_id:str;weekdays:list[int]=Field(min_length=1,max_length=7);outbound_time:time|None=None;return_time:time|None=None;valid_from:date;valid_until:date|None=None
    @model_validator(mode="after")
    def validate_schedule(self):
        if any(day<0 or day>6 for day in self.weekdays):raise ValueError("weekdays deve usar 0=segunda até 6=domingo.")
        if len(set(self.weekdays))!=len(self.weekdays):raise ValueError("weekdays não pode conter duplicidades.")
        if self.valid_until and self.valid_until<self.valid_from:raise ValueError("valid_until deve ser posterior a valid_from.")
        return self
class TripEventInput(BaseModel):
    route_id:str;rider_id:str;event_type:Literal["boarded","disembarked","missed","not_expected"];stop_name:str|None=None;occurred_at:str;device_id:str|None=None;location:dict[str,Any]=Field(default_factory=dict)
class OccurrenceInput(BaseModel):route_id:str;student_id:str|None=None;occurrence_type:str=Field(min_length=2,max_length=80);description:str=Field(min_length=3,max_length=4000);severity:Literal["low","normal","high","critical"]="normal"
class ResolveOccurrenceInput(BaseModel):resolution:str=Field(min_length=3,max_length=4000)


def _manager(user:CurrentUser)->bool:return bool(set(user.roles).intersection(TRANSPORT_ROLES))

def _student_access(request:Request,tid:str,user:CurrentUser,student_id:str)->bool:
    if _manager(user):return True
    if not user.person_id:return False
    own=request.state.store.fetch_one("SELECT id FROM students WHERE tenant_id=? AND id=? AND person_id=? AND state='active'",(tid,student_id,user.person_id))
    if own:return True
    guardian=request.state.store.fetch_one("SELECT 1 AS ok FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id WHERE g.tenant_id=? AND g.person_id=? AND gs.student_id=? AND g.state='active' LIMIT 1",(tid,user.person_id,student_id))
    return bool(guardian)

@router.get("/transport/riders",operation_id="list_transport_riders")
def list_riders(request:Request,route_id:str|None=None,student_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);sql="SELECT tr.*,s.registration_number,p.full_name AS student_name,r.name AS route_name,r.vehicle FROM transport_riders tr JOIN students s ON s.id=tr.student_id JOIN people p ON p.id=s.person_id JOIN transport_routes r ON r.id=tr.route_id WHERE tr.tenant_id=?";params:list[Any]=[tid]
    if route_id:sql+=" AND tr.route_id=?";params.append(route_id)
    if student_id:
        if not _student_access(request,tid,user,student_id):raise DomainError("TRANSPORT_RIDER_NOT_FOUND","Vínculo de transporte não localizado.",404)
        sql+=" AND tr.student_id=?";params.append(student_id)
    elif not _manager(user):
        if not user.person_id:return {"items":[]}
        students=request.state.store.fetch_all("SELECT s.id FROM students s WHERE s.tenant_id=? AND s.person_id=? UNION SELECT gs.student_id AS id FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id WHERE g.tenant_id=? AND g.person_id=?",(tid,user.person_id,tid,user.person_id));ids=[str(x["id"]) for x in students]
        if not ids:return {"items":[]}
        sql+=f" AND tr.student_id IN ({','.join('?' for _ in ids)})";params.extend(ids)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY student_name",params)}

@router.get("/transport/schedules",operation_id="list_transport_schedules")
def list_schedules(request:Request,route_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);sql="SELECT s.*,r.name AS route_name FROM transport_route_schedules s JOIN transport_routes r ON r.id=s.route_id WHERE s.tenant_id=?";params:list[Any]=[tid]
    if route_id:
        if not _manager(user):
            accessible=request.state.store.fetch_one("SELECT 1 AS ok FROM transport_riders tr WHERE tr.tenant_id=? AND tr.route_id=? AND tr.state='active' AND (tr.student_id IN (SELECT id FROM students WHERE tenant_id=? AND person_id=?) OR tr.student_id IN (SELECT gs.student_id FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id WHERE g.tenant_id=? AND g.person_id=? AND g.state='active')) LIMIT 1",(tid,route_id,tid,user.person_id or '',tid,user.person_id or ''))
            if not accessible:raise DomainError("TRANSPORT_SCHEDULE_NOT_FOUND","Agenda de transporte não localizada.",404)
        sql+=" AND s.route_id=?";params.append(route_id)
    elif not _manager(user):
        if not user.person_id:return {"items":[]}
        sql+=" AND s.route_id IN (SELECT tr.route_id FROM transport_riders tr WHERE tr.tenant_id=? AND tr.state='active' AND (tr.student_id IN (SELECT id FROM students WHERE tenant_id=? AND person_id=?) OR tr.student_id IN (SELECT gs.student_id FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id WHERE g.tenant_id=? AND g.person_id=? AND g.state='active')))"
        params.extend([tid,tid,user.person_id,tid,user.person_id])
    rows=request.state.store.fetch_all(sql+" ORDER BY valid_from DESC",params)
    for row in rows:row["weekdays"]=loads(row.pop("weekdays_json"),[])
    return {"items":rows}

@router.post("/transport/schedules",status_code=201,operation_id="create_transport_schedule")
def create_schedule(data:ScheduleInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user);route=request.state.store.fetch_one("SELECT id FROM transport_routes WHERE tenant_id=? AND id=? AND state='active'",(tid,data.route_id))
    if not route:raise DomainError("ROUTE_NOT_FOUND","Rota ativa não localizada.",404)
    sid=uuid7();now=iso_now();result={"id":sid,"route_id":data.route_id,"weekdays":data.weekdays,"valid_from":str(data.valid_from),"state":"active"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO transport_route_schedules(id,tenant_id,route_id,weekdays_json,outbound_time,return_time,valid_from,valid_until,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(sid,tid,data.route_id,dumps(sorted(data.weekdays)),data.outbound_time.isoformat() if data.outbound_time else None,data.return_time.isoformat() if data.return_time else None,str(data.valid_from),str(data.valid_until) if data.valid_until else None,"active",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="schedule",aggregate_type="transport_route",aggregate_id=data.route_id,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/transport/events",status_code=201,operation_id="register_transport_trip_event")
def register_event(data:TripEventInput,request:Request,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=160),user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user);payload=data.model_dump();scope=f"transport:event:{tid}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,payload)
        if cached:return cached[1]
        rider_row=conn.execute("SELECT * FROM transport_riders WHERE tenant_id=? AND id=? AND route_id=? AND state='active'",(tid,data.rider_id,data.route_id)).fetchone();rider=dict(rider_row) if rider_row else None
        if not rider:raise DomainError("TRANSPORT_RIDER_NOT_FOUND","Aluno não está vinculado a esta rota.",404)
        eid=uuid7();now=iso_now();result={"id":eid,"route_id":data.route_id,"rider_id":data.rider_id,"student_id":rider["student_id"],"event_type":data.event_type,"occurred_at":data.occurred_at}
        conn.execute("INSERT INTO transport_trip_events(id,tenant_id,route_id,rider_id,student_id,event_type,stop_name,occurred_at,device_id,location_json,idempotency_key,actor_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(eid,tid,data.route_id,data.rider_id,rider["student_id"],data.event_type,data.stop_name,data.occurred_at,data.device_id,dumps(data.location),idempotency_key,user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="transport_event",aggregate_type="transport_rider",aggregate_id=data.rider_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type={"boarded":"StudentTransportBoarded","disembarked":"StudentTransportDisembarked","missed":"StudentTransportMissed","not_expected":"StudentTransportNotExpected"}[data.event_type],aggregate_type="transport_trip_event",aggregate_id=eid,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,payload,201,result)
    return result

@router.get("/transport/students/{student_id}/events",operation_id="list_student_transport_events")
def student_events(student_id:str,request:Request,limit:int=100,user:CurrentUser=Depends(current_user)):
    tid=tenant(user)
    if not _student_access(request,tid,user,student_id):raise DomainError("STUDENT_NOT_FOUND","Aluno não localizado.",404)
    limit=max(1,min(limit,500));rows=request.state.store.fetch_all("SELECT e.*,r.name AS route_name,r.vehicle FROM transport_trip_events e JOIN transport_routes r ON r.id=e.route_id WHERE e.tenant_id=? AND e.student_id=? ORDER BY e.occurred_at DESC LIMIT ?",(tid,student_id,limit))
    for row in rows:row["location"]=loads(row.pop("location_json"),{})
    return {"items":rows}

@router.get("/transport/occurrences",operation_id="list_transport_occurrences")
def occurrences(request:Request,state:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user);sql="SELECT o.*,r.name AS route_name FROM transport_occurrences o JOIN transport_routes r ON r.id=o.route_id WHERE o.tenant_id=?";params:list[Any]=[tid]
    if state:sql+=" AND o.state=?";params.append(state)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY o.reported_at DESC",params)}

@router.post("/transport/occurrences",status_code=201,operation_id="create_transport_occurrence")
def create_occurrence(data:OccurrenceInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user)
    if not request.state.store.fetch_one("SELECT id FROM transport_routes WHERE tenant_id=? AND id=?",(tid,data.route_id)):raise DomainError("ROUTE_NOT_FOUND","Rota não localizada.",404)
    if data.student_id and not request.state.store.fetch_one("SELECT id FROM students WHERE tenant_id=? AND id=?",(tid,data.student_id)):raise DomainError("STUDENT_NOT_FOUND","Aluno não localizado.",404)
    oid=uuid7();now=iso_now();result={"id":oid,"route_id":data.route_id,"student_id":data.student_id,"occurrence_type":data.occurrence_type,"severity":data.severity,"state":"open"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO transport_occurrences(id,tenant_id,route_id,student_id,occurrence_type,description,severity,state,reported_by,reported_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(oid,tid,data.route_id,data.student_id,data.occurrence_type,data.description,data.severity,"open",user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="report",aggregate_type="transport_occurrence",aggregate_id=oid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="TransportOccurrenceReported",aggregate_type="transport_occurrence",aggregate_id=oid,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/transport/occurrences/{occurrence_id}/resolve",operation_id="resolve_transport_occurrence")
def resolve_occurrence(occurrence_id:str,data:ResolveOccurrenceInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM transport_occurrences WHERE tenant_id=? AND id=?",(tid,occurrence_id))
    if not row:raise DomainError("TRANSPORT_OCCURRENCE_NOT_FOUND","Ocorrência não localizada.",404)
    if row["state"]=="resolved":return {"id":occurrence_id,"state":"resolved","resolved_at":row["resolved_at"]}
    now=iso_now();request.state.store.execute("UPDATE transport_occurrences SET state='resolved',resolved_by=?,resolved_at=?,resolution=? WHERE tenant_id=? AND id=?",(user.id,now,data.resolution,tid,occurrence_id));return {"id":occurrence_id,"state":"resolved","resolved_at":now}
