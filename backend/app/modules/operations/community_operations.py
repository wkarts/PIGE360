from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Header, Request, Response, UploadFile
from pydantic import BaseModel, Field

from app.modules.operations.common import ADMIN_ROLES, HR_ROLES, INTEGRATION_ROLES, dumps, loads, require, row_or_404, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.modules.workflows.application.service import start_workflow_in_connection
from app.modules.library.application.service import ensure_policy, fine_for_return, promote_next_reservation
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["community-documents-integrations"])
EVENT_ROLES = ADMIN_ROLES | {"event_manager"}
NOTICE_ROLES = ADMIN_ROLES | {"event_manager", "finance_manager", "hr_manager"}
REQUEST_AGENT_ROLES = ADMIN_ROLES | {"request_agent", "support"}
LIBRARY_ROLES = ADMIN_ROLES | {"auditor"}
TRANSPORT_ROLES = ADMIN_ROLES | {"unit_manager"}
HEALTH_ROLES = {"tenant_owner", "institution_director", "unit_manager", "secretary", "health_operator"}


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _serialize(rows: list[dict[str, Any]], json_fields: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    for row in rows:
        for field in json_fields:
            if field in row:
                row[field.removesuffix("_json")] = loads(row.pop(field), [] if field.endswith("s_json") else {})
    return rows


def _notice_visible(request: Request, tid: str, row: dict[str, Any], user: CurrentUser) -> bool:
    if set(user.roles).intersection(NOTICE_ROLES):
        return True
    if row.get("state") != "published" or not user.person_id:
        return False
    now = iso_now()
    if row.get("expires_at") and str(row["expires_at"]) < now:
        return False
    audience = loads(row.get("audience_json"), {})
    kind = str(audience.get("type") or "all")
    if kind == "all":
        return True
    if user.person_id in set(str(x) for x in audience.get("person_ids", [])):
        return True
    if set(user.roles).intersection(set(str(x) for x in audience.get("roles", []))):
        return True
    direct_students = {str(r["id"]) for r in request.state.store.fetch_all("SELECT id FROM students WHERE tenant_id=? AND person_id=? AND state='active'", (tid, user.person_id))}
    guardian_students = {str(r["student_id"]) for r in request.state.store.fetch_all("SELECT gs.student_id FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id WHERE g.tenant_id=? AND g.person_id=? AND g.state='active'", (tid, user.person_id))}
    student_ids = direct_students | guardian_students
    if student_ids.intersection(set(str(x) for x in audience.get("student_ids", []))):
        return True
    groups = {str(r["class_group_id"]) for r in request.state.store.fetch_all("SELECT class_group_id FROM enrollments WHERE tenant_id=? AND student_id IN (SELECT id FROM students WHERE tenant_id=? AND person_id=?) AND state='active' AND class_group_id IS NOT NULL", (tid, tid, user.person_id))}
    if guardian_students:
        placeholders = ",".join("?" for _ in guardian_students)
        groups.update(str(r["class_group_id"]) for r in request.state.store.fetch_all(f"SELECT class_group_id FROM enrollments WHERE tenant_id=? AND student_id IN ({placeholders}) AND state='active' AND class_group_id IS NOT NULL", (tid, *sorted(guardian_students))))
    groups.update(str(r["class_group_id"]) for r in request.state.store.fetch_all("SELECT ta.class_group_id FROM employees e JOIN teacher_assignments ta ON ta.employee_id=e.id AND ta.tenant_id=e.tenant_id WHERE e.tenant_id=? AND e.person_id=? AND e.state='active' AND ta.state='active'", (tid, user.person_id)))
    return bool(groups.intersection(set(str(x) for x in audience.get("class_group_ids", []))))


def _validate_request_form(schema: dict[str, Any], form_data: dict[str, Any]) -> None:
    errors: list[dict[str, str]] = []
    for field in schema.get("fields", []):
        if not isinstance(field, dict) or not field.get("name"):
            continue
        name = str(field["name"]); value = form_data.get(name)
        if field.get("required") and (value is None or value == ""):
            errors.append({"field": name, "code": "REQUIRED", "message": "Campo obrigatório."}); continue
        if value is None or value == "":
            continue
        kind = field.get("type", "string")
        if kind == "string" and not isinstance(value, str): errors.append({"field": name, "code": "INVALID_TYPE", "message": "Informe um texto."})
        elif kind == "number" and not isinstance(value, (int, float)): errors.append({"field": name, "code": "INVALID_TYPE", "message": "Informe um número."})
        elif kind == "boolean" and not isinstance(value, bool): errors.append({"field": name, "code": "INVALID_TYPE", "message": "Informe verdadeiro ou falso."})
        elif kind == "email" and (not isinstance(value, str) or "@" not in value): errors.append({"field": name, "code": "INVALID_EMAIL", "message": "Informe um e-mail válido."})
        elif kind == "date":
            try: date.fromisoformat(str(value))
            except ValueError: errors.append({"field": name, "code": "INVALID_DATE", "message": "Informe uma data ISO válida."})
    if errors:
        raise DomainError("REQUEST_FORM_INVALID", "Existem campos inválidos na solicitação.", 422, errors=errors)


class EventInput(BaseModel):
    event_type: str
    name: str = Field(min_length=2, max_length=200)
    starts_at: datetime
    ends_at: datetime
    location: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    budget: str | None = None
    registration_fee: Decimal = Field(default=Decimal("0"), ge=0)
    authorization_required: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class TripInput(BaseModel):
    event_id: str | None = None
    name: str
    destination: str
    starts_at: datetime
    ends_at: datetime
    itinerary: list[dict[str, Any]] = Field(default_factory=list)
    vehicles: list[dict[str, Any]] = Field(default_factory=list)
    emergency: dict[str, Any] = Field(default_factory=dict)


@router.get("/events", operation_id="list_events_relational")
def list_events(request: Request, user: CurrentUser = Depends(current_user)):
    tid = tenant(user)
    if set(user.roles).intersection(EVENT_ROLES):
        rows = request.state.store.fetch_all("SELECT * FROM events WHERE tenant_id=? ORDER BY starts_at DESC", (tid,))
    else:
        rows = request.state.store.fetch_all("SELECT * FROM events WHERE tenant_id=? AND state='published' ORDER BY starts_at DESC", (tid,))
    return {"items": _serialize(rows, ("payload_json",))}


@router.post("/events", status_code=201, operation_id="create_event_relational")
def create_event(data: EventInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, EVENT_ROLES)
    if data.ends_at <= data.starts_at:
        raise DomainError("INVALID_EVENT_PERIOD", "O término deve ser posterior ao início.", 422)
    tid, eid, now = tenant(user), uuid7(), iso_now()
    result = {"id": eid, "event_type": data.event_type, "name": data.name, "starts_at": data.starts_at.isoformat(), "ends_at": data.ends_at.isoformat(), "registration_fee": money_str(data.registration_fee), "authorization_required": data.authorization_required, "state": "draft"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO events(id,tenant_id,event_type,name,starts_at,ends_at,location,capacity,state,budget,registration_fee,authorization_required,payload_json,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (eid,tid,data.event_type,data.name,data.starts_at.isoformat(),data.ends_at.isoformat(),data.location,data.capacity,"draft",data.budget,money_str(data.registration_fee),1 if data.authorization_required else 0,dumps(data.payload),1,now,now))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="create", aggregate_type="event", aggregate_id=eid, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tid, event_type="EventCreated", aggregate_type="event", aggregate_id=eid, payload=result, correlation_id=request.state.correlation_id)
    return result


@router.post("/events/{event_id}/publish", operation_id="publish_event_relational")
def publish_event(event_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, EVENT_ROLES); tid=tenant(user)
    row=row_or_404(request,"SELECT * FROM events WHERE tenant_id=? AND id=?",(tid,event_id),"EVENT_NOT_FOUND","Evento não localizado.")
    if row["state"] not in {"draft","scheduled"}: raise DomainError("INVALID_EVENT_STATE","Evento não pode ser publicado neste estado.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE events SET state='published',version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(now,tid,event_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="event",aggregate_id=event_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":"published"})
        add_outbox(conn,tenant_id=tid,event_type="EventPublished",aggregate_type="event",aggregate_id=event_id,payload={"id":event_id,"state":"published"},correlation_id=request.state.correlation_id)
    return {"id":event_id,"state":"published"}


@router.get("/events/me/registrations", operation_id="list_my_event_registrations")
def list_my_event_registrations(request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user)
    if not user.person_id:return {"items":[]}
    params:list[Any]=[tid]
    if "guardian" in user.roles:
        guardian=request.state.store.fetch_one("SELECT id FROM guardians WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id))
        if not guardian:return {"items":[]}
        where="er.guardian_id=?";params.append(guardian["id"])
    elif "student" in user.roles:
        student=request.state.store.fetch_one("SELECT id FROM students WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id))
        if not student:return {"items":[]}
        where="er.student_id=?";params.append(student["id"])
    else:
        raise DomainError("ROLE_FORBIDDEN","Recurso disponível para aluno ou responsável.",403)
    rows=request.state.store.fetch_all(f"""SELECT er.*,e.name AS event_name,e.starts_at,e.ends_at,e.location,
        ea.id AS authorization_id,ea.state AS authorization_state,ea.decided_at
        FROM event_registrations er JOIN events e ON e.id=er.event_id
        LEFT JOIN event_authorizations ea ON ea.event_registration_id=er.id AND ea.tenant_id=er.tenant_id
        WHERE er.tenant_id=? AND {where} ORDER BY e.starts_at DESC""",params)
    return {"items":rows}


class EventScheduleInput(BaseModel):
    sequence: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=200)
    starts_at: datetime
    ends_at: datetime
    location: str | None = None
    description: str | None = Field(default=None, max_length=4000)


class EventRegistrationInput(BaseModel):
    person_id: str | None = None
    student_id: str | None = None
    guardian_id: str | None = None
    due_date: date | None = None


class EventAuthorizationInput(BaseModel):
    decision: Literal["approved", "rejected"]
    consent_text: str = Field(min_length=3, max_length=4000)


def _guardian_for_user(conn, tid: str, user: CurrentUser):
    if not user.person_id:
        return None
    return conn.execute("SELECT * FROM guardians WHERE tenant_id=? AND person_id=? AND state='active'", (tid, user.person_id)).fetchone()


@router.get("/events/{event_id}", operation_id="get_event_details_relational")
def get_event_details(event_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user);event=row_or_404(request,"SELECT * FROM events WHERE tenant_id=? AND id=?",(tid,event_id),"EVENT_NOT_FOUND","Evento não localizado.")
    if not set(user.roles).intersection(EVENT_ROLES) and event["state"]!="published":raise DomainError("EVENT_NOT_FOUND","Evento não localizado.",404)
    result=dict(event);result["payload"]=loads(result.pop("payload_json"),{})
    result["schedule"]=request.state.store.fetch_all("SELECT * FROM event_schedule_items WHERE tenant_id=? AND event_id=? ORDER BY sequence",(tid,event_id))
    if set(user.roles).intersection(EVENT_ROLES):
        result["registrations"]=request.state.store.fetch_all("SELECT er.*,p.full_name AS person_name FROM event_registrations er LEFT JOIN people p ON p.id=er.person_id WHERE er.tenant_id=? AND er.event_id=? ORDER BY er.created_at",(tid,event_id))
    return result


@router.post("/events/{event_id}/schedule", status_code=201, operation_id="add_event_schedule_item")
def add_event_schedule(event_id: str, data: EventScheduleInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);event=row_or_404(request,"SELECT * FROM events WHERE tenant_id=? AND id=?",(tid,event_id),"EVENT_NOT_FOUND","Evento não localizado.")
    if data.ends_at<=data.starts_at or data.starts_at.isoformat()<str(event["starts_at"]) or data.ends_at.isoformat()>str(event["ends_at"]):raise DomainError("EVENT_SCHEDULE_OUT_OF_RANGE","Item da programação deve estar contido no período do evento.",422)
    item_id=uuid7();now=iso_now();result={"id":item_id,"event_id":event_id,"sequence":data.sequence,"title":data.title,"starts_at":data.starts_at.isoformat(),"ends_at":data.ends_at.isoformat()}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO event_schedule_items(id,tenant_id,event_id,sequence,title,starts_at,ends_at,location,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(item_id,tid,event_id,data.sequence,data.title,data.starts_at.isoformat(),data.ends_at.isoformat(),data.location,data.description,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="schedule_item",aggregate_type="event",aggregate_id=event_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.post("/events/{event_id}/registrations", status_code=201, operation_id="register_event_participant")
def register_event(event_id: str, data: EventRegistrationInput, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key",min_length=8,max_length=200), user: CurrentUser = Depends(current_user)):
    tid=tenant(user);body=data.model_dump(mode="json");scope=f"event-registration:{tid}:{event_id}";now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        event=conn.execute("SELECT * FROM events WHERE tenant_id=? AND id=?",(tid,event_id)).fetchone()
        if not event:raise DomainError("EVENT_NOT_FOUND","Evento não localizado.",404)
        is_manager=bool(set(user.roles).intersection(EVENT_ROLES))
        if not is_manager and event["state"]!="published":raise DomainError("EVENT_NOT_OPEN","Evento não está disponível para inscrição.",409)
        if not data.person_id and not data.student_id:raise DomainError("PARTICIPANT_REQUIRED","Informe pessoa ou aluno para a inscrição.",422)
        person_id=data.person_id;student=None;guardian_id=data.guardian_id
        if data.student_id:
            student=conn.execute("SELECT s.*,p.id AS person_id FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.id=? AND s.state='active'",(tid,data.student_id)).fetchone()
            if not student:raise DomainError("STUDENT_NOT_FOUND","Aluno não localizado.",404)
            person_id=student["person_id"]
            if not is_manager:
                if "student" in user.roles and user.person_id!=person_id:raise DomainError("EVENT_REGISTRATION_FORBIDDEN","Aluno só pode inscrever a própria pessoa.",403)
                if "guardian" in user.roles:
                    guardian=_guardian_for_user(conn,tid,user)
                    if not guardian or not conn.execute("SELECT id FROM guardian_students WHERE tenant_id=? AND guardian_id=? AND student_id=?",(tid,guardian["id"],data.student_id)).fetchone():raise DomainError("EVENT_REGISTRATION_FORBIDDEN","Responsável não possui vínculo com o aluno.",403)
                    guardian_id=guardian["id"]
            if guardian_id:
                link=conn.execute("SELECT * FROM guardian_students WHERE tenant_id=? AND guardian_id=? AND student_id=?",(tid,guardian_id,data.student_id)).fetchone()
                if not link:raise DomainError("GUARDIAN_STUDENT_LINK_NOT_FOUND","Responsável não está vinculado ao aluno.",422)
            elif event["authorization_required"]:
                link=conn.execute("SELECT * FROM guardian_students WHERE tenant_id=? AND student_id=? AND is_legal=1 ORDER BY is_financial DESC,created_at LIMIT 1",(tid,data.student_id)).fetchone()
                if not link:raise DomainError("LEGAL_GUARDIAN_REQUIRED","Evento exige responsável legal vinculado.",409)
                guardian_id=link["guardian_id"]
        elif not is_manager and user.person_id!=person_id:
            raise DomainError("EVENT_REGISTRATION_FORBIDDEN","Usuário só pode inscrever a própria pessoa.",403)
        occupied=conn.execute("SELECT COUNT(*) AS n FROM event_registrations WHERE tenant_id=? AND event_id=? AND state IN ('awaiting_authorization','confirmed','checked_in')",(tid,event_id)).fetchone()["n"]
        if event["capacity"] is not None and int(occupied)>=int(event["capacity"]):raise DomainError("EVENT_CAPACITY_EXCEEDED","Evento sem vagas disponíveis.",409)
        registration_id=uuid7();fee=money(event["registration_fee"] or 0);financial_contract_id=None
        state="awaiting_authorization" if event["authorization_required"] and data.student_id else "confirmed"
        if fee>0:
            financial_contract_id=uuid7();due=data.due_date or date.fromisoformat(str(event["starts_at"])[:10]);installment_id=uuid7()
            conn.execute("INSERT INTO financial_contracts(id,tenant_id,enrollment_id,responsible_guardian_id,description,total_amount,currency,competence_rule,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(financial_contract_id,tid,None,guardian_id,f"Inscrição no evento {event['name']}",money_str(fee),"BRL","billing","active",1,now,now))
            conn.execute("INSERT INTO installments(id,tenant_id,financial_contract_id,sequence,competence,due_date,original_amount,discount_amount,penalty_amount,interest_amount,paid_amount,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(installment_id,tid,financial_contract_id,1,due.strftime("%Y-%m"),str(due),money_str(fee),"0.00","0.00","0.00","0.00","open",now,now))
        conn.execute("INSERT INTO event_registrations(id,tenant_id,event_id,person_id,student_id,guardian_id,state,fee_amount,financial_contract_id,idempotency_key,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(registration_id,tid,event_id,person_id,data.student_id,guardian_id,state,money_str(fee),financial_contract_id,idempotency_key,user.id,now,now))
        authorization_id=None
        if state=="awaiting_authorization":
            authorization_id=uuid7();conn.execute("INSERT INTO event_authorizations(id,tenant_id,event_registration_id,guardian_id,state,evidence_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(authorization_id,tid,registration_id,guardian_id,"pending","{}",now,now))
        result={"id":registration_id,"event_id":event_id,"student_id":data.student_id,"person_id":person_id,"guardian_id":guardian_id,"state":state,"fee_amount":money_str(fee),"financial_contract_id":financial_contract_id,"authorization_id":authorization_id};add_audit(conn,tenant_id=tid,actor_id=user.id,action="register",aggregate_type="event_registration",aggregate_id=registration_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="EventRegistrationCreated",aggregate_type="event_registration",aggregate_id=registration_id,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result


@router.post("/event-registrations/{registration_id}/authorization", operation_id="decide_event_authorization")
def decide_event_authorization(registration_id: str, data: EventAuthorizationInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        registration=conn.execute("SELECT * FROM event_registrations WHERE tenant_id=? AND id=?",(tid,registration_id)).fetchone()
        if not registration:raise DomainError("EVENT_REGISTRATION_NOT_FOUND","Inscrição não localizada.",404)
        authorization=conn.execute("SELECT * FROM event_authorizations WHERE tenant_id=? AND event_registration_id=?",(tid,registration_id)).fetchone()
        if not authorization:raise DomainError("EVENT_AUTHORIZATION_NOT_REQUIRED","Inscrição não exige autorização.",409)
        guardian=_guardian_for_user(conn,tid,user)
        if not guardian or guardian["id"]!=authorization["guardian_id"]:raise DomainError("EVENT_AUTHORIZATION_FORBIDDEN","Somente o responsável legal vinculado pode decidir a autorização.",403)
        if authorization["state"]!="pending":raise DomainError("EVENT_AUTHORIZATION_ALREADY_DECIDED","Autorização já foi decidida.",409)
        evidence={"guardian_id":guardian["id"],"user_id":user.id,"person_id":user.person_id,"correlation_id":request.state.correlation_id,"decided_at":now,"method":"authenticated_consent"}
        registration_state="confirmed" if data.decision=="approved" else "cancelled"
        conn.execute("UPDATE event_authorizations SET state=?,consent_text=?,evidence_json=?,decided_at=?,updated_at=? WHERE tenant_id=? AND id=?",(data.decision,data.consent_text,dumps(evidence),now,now,tid,authorization["id"]))
        conn.execute("UPDATE event_registrations SET state=?,updated_at=? WHERE tenant_id=? AND id=?",(registration_state,now,tid,registration_id))
        result={"registration_id":registration_id,"authorization_id":authorization["id"],"decision":data.decision,"state":registration_state,"decided_at":now};add_audit(conn,tenant_id=tid,actor_id=user.id,action="authorize" if data.decision=="approved" else "reject_authorization",aggregate_type="event_registration",aggregate_id=registration_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="EventAuthorizationApproved" if data.decision=="approved" else "EventAuthorizationRejected",aggregate_type="event_registration",aggregate_id=registration_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/event-registrations/{registration_id}/check-in", operation_id="check_in_event_participant")
def event_check_in(registration_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM event_registrations WHERE tenant_id=? AND id=?",(tid,registration_id)).fetchone()
        if not row:raise DomainError("EVENT_REGISTRATION_NOT_FOUND","Inscrição não localizada.",404)
        if row["state"] not in {"confirmed","checked_in"}:raise DomainError("EVENT_CHECKIN_NOT_ALLOWED","Inscrição não está confirmada para check-in.",409)
        if not row["checked_in_at"]:conn.execute("UPDATE event_registrations SET state='checked_in',checked_in_at=?,updated_at=? WHERE tenant_id=? AND id=?",(now,now,tid,registration_id))
        return {"id":registration_id,"state":"checked_in","checked_in_at":row["checked_in_at"] or now}


@router.post("/event-registrations/{registration_id}/check-out", operation_id="check_out_event_participant")
def event_check_out(registration_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM event_registrations WHERE tenant_id=? AND id=?",(tid,registration_id)).fetchone()
        if not row:raise DomainError("EVENT_REGISTRATION_NOT_FOUND","Inscrição não localizada.",404)
        if not row["checked_in_at"]:raise DomainError("EVENT_CHECKOUT_REQUIRES_CHECKIN","Check-out exige check-in prévio.",409)
        if not row["checked_out_at"]:conn.execute("UPDATE event_registrations SET state='completed',checked_out_at=?,updated_at=? WHERE tenant_id=? AND id=?",(now,now,tid,registration_id))
        return {"id":registration_id,"state":"completed","checked_out_at":row["checked_out_at"] or now}


@router.get("/trips", operation_id="list_trips_relational")
def list_trips(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user); rows=request.state.store.fetch_all("SELECT * FROM trips WHERE tenant_id=? ORDER BY starts_at DESC",(tid,)); return {"items":_serialize(rows,("itinerary_json","vehicles_json","emergency_json"))}


@router.post("/trips",status_code=201,operation_id="create_trip_relational")
def create_trip(data:TripInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user)
    if data.ends_at<=data.starts_at:raise DomainError("INVALID_TRIP_PERIOD","O término deve ser posterior ao início.",422)
    if data.event_id:row_or_404(request,"SELECT id FROM events WHERE tenant_id=? AND id=?",(tid,data.event_id),"EVENT_NOT_FOUND","Evento não localizado.")
    trip_id=uuid7();now=iso_now();result={"id":trip_id,"name":data.name,"destination":data.destination,"state":"draft"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO trips(id,tenant_id,event_id,name,destination,starts_at,ends_at,itinerary_json,vehicles_json,emergency_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(trip_id,tid,data.event_id,data.name,data.destination,data.starts_at.isoformat(),data.ends_at.isoformat(),dumps(data.itinerary),dumps(data.vehicles),dumps(data.emergency),"draft",now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="trip",aggregate_id=trip_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.get("/trips/me", operation_id="list_my_trips")
def list_my_trips(request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user)
    if not user.person_id:return {"items":[]}
    if "student" in user.roles:
        students=request.state.store.fetch_all("SELECT id FROM students WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id))
    elif "guardian" in user.roles:
        students=request.state.store.fetch_all("SELECT gs.student_id AS id FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id WHERE g.tenant_id=? AND g.person_id=? AND g.state='active'",(tid,user.person_id))
    else:raise DomainError("ROLE_FORBIDDEN","Recurso disponível para aluno ou responsável.",403)
    ids=[str(row["id"]) for row in students]
    if not ids:return {"items":[]}
    placeholders=','.join('?' for _ in ids)
    rows=request.state.store.fetch_all(f"""SELECT tp.*,t.name AS trip_name,t.destination,t.starts_at,t.ends_at,t.state AS trip_state
        FROM trip_passengers tp JOIN trips t ON t.id=tp.trip_id WHERE tp.tenant_id=? AND tp.student_id IN ({placeholders})
        ORDER BY t.starts_at DESC""",(tid,*ids))
    return {"items":rows}


class TripPassengerInput(BaseModel):
    student_id: str
    guardian_id: str | None = None
    event_registration_id: str | None = None
    emergency_snapshot: dict[str, Any] = Field(default_factory=dict)


class TripCheckpointInput(BaseModel):
    sequence: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=200)
    planned_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TripIncidentInput(BaseModel):
    passenger_id: str | None = None
    incident_type: str = Field(min_length=2, max_length=80)
    severity: Literal["low", "medium", "high", "critical"] = "low"
    description: str = Field(min_length=3, max_length=4000)
    occurred_at: datetime | None = None


@router.get("/trips/{trip_id}", operation_id="get_trip_details_relational")
def get_trip_details(trip_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);trip=row_or_404(request,"SELECT * FROM trips WHERE tenant_id=? AND id=?",(tid,trip_id),"TRIP_NOT_FOUND","Viagem não localizada.")
    result=dict(trip);result["itinerary"]=loads(result.pop("itinerary_json"),[]);result["vehicles"]=loads(result.pop("vehicles_json"),[]);result["emergency"]=loads(result.pop("emergency_json"),{})
    result["passengers"]=request.state.store.fetch_all("SELECT tp.*,p.full_name AS student_name FROM trip_passengers tp JOIN students s ON s.id=tp.student_id JOIN people p ON p.id=s.person_id WHERE tp.tenant_id=? AND tp.trip_id=? ORDER BY p.full_name",(tid,trip_id))
    result["checkpoints"]=request.state.store.fetch_all("SELECT * FROM trip_checkpoints WHERE tenant_id=? AND trip_id=? ORDER BY sequence",(tid,trip_id))
    result["incidents"]=request.state.store.fetch_all("SELECT * FROM trip_incidents WHERE tenant_id=? AND trip_id=? ORDER BY occurred_at DESC",(tid,trip_id))
    return result


@router.post("/trips/{trip_id}/publish", operation_id="publish_trip_relational")
def publish_trip(trip_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM trips WHERE tenant_id=? AND id=?",(tid,trip_id)).fetchone()
        if not row:raise DomainError("TRIP_NOT_FOUND","Viagem não localizada.",404)
        if row["state"] not in {"draft","scheduled"}:raise DomainError("INVALID_TRIP_STATE","Viagem não pode ser publicada neste estado.",409)
        conn.execute("UPDATE trips SET state='published',updated_at=? WHERE tenant_id=? AND id=?",(now,tid,trip_id));result={"id":trip_id,"state":"published"};add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="trip",aggregate_id=trip_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result);add_outbox(conn,tenant_id=tid,event_type="TripPublished",aggregate_type="trip",aggregate_id=trip_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/trips/{trip_id}/passengers", status_code=201, operation_id="add_trip_passenger")
def add_trip_passenger(trip_id: str, data: TripPassengerInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        trip=conn.execute("SELECT * FROM trips WHERE tenant_id=? AND id=?",(tid,trip_id)).fetchone()
        if not trip:raise DomainError("TRIP_NOT_FOUND","Viagem não localizada.",404)
        student=conn.execute("SELECT * FROM students WHERE tenant_id=? AND id=? AND state='active'",(tid,data.student_id)).fetchone()
        if not student:raise DomainError("STUDENT_NOT_FOUND","Aluno não localizado.",404)
        guardian_id=data.guardian_id;registration=None
        if trip["event_id"]:
            if not data.event_registration_id:raise DomainError("TRIP_EVENT_REGISTRATION_REQUIRED","Viagem vinculada a evento exige inscrição confirmada.",409)
            registration=conn.execute("SELECT * FROM event_registrations WHERE tenant_id=? AND id=? AND event_id=? AND student_id=?",(tid,data.event_registration_id,trip["event_id"],data.student_id)).fetchone()
            if not registration or registration["state"] not in {"confirmed","checked_in","completed"}:raise DomainError("TRIP_EVENT_REGISTRATION_INVALID","Inscrição do evento não está confirmada para a viagem.",409)
            guardian_id=guardian_id or registration["guardian_id"]
            auth=conn.execute("SELECT state FROM event_authorizations WHERE tenant_id=? AND event_registration_id=?",(tid,registration["id"])).fetchone()
            if auth and auth["state"]!="approved":raise DomainError("TRIP_AUTHORIZATION_REQUIRED","Autorização do responsável ainda não foi aprovada.",409)
        if guardian_id and not conn.execute("SELECT id FROM guardian_students WHERE tenant_id=? AND guardian_id=? AND student_id=?",(tid,guardian_id,data.student_id)).fetchone():raise DomainError("GUARDIAN_STUDENT_LINK_NOT_FOUND","Responsável não está vinculado ao aluno.",422)
        passenger_id=uuid7();result={"id":passenger_id,"trip_id":trip_id,"student_id":data.student_id,"guardian_id":guardian_id,"event_registration_id":data.event_registration_id,"state":"confirmed"}
        conn.execute("INSERT INTO trip_passengers(id,tenant_id,trip_id,student_id,guardian_id,event_registration_id,state,emergency_snapshot_json,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(passenger_id,tid,trip_id,data.student_id,guardian_id,data.event_registration_id,"confirmed",dumps(data.emergency_snapshot),user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="add_passenger",aggregate_type="trip",aggregate_id=trip_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="TripPassengerAdded",aggregate_type="trip",aggregate_id=trip_id,payload=result,correlation_id=request.state.correlation_id)
    return result


def _trip_passenger_transition(trip_id: str, passenger_id: str, field: str, state: str, request: Request, user: CurrentUser):
    require(user,EVENT_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM trip_passengers WHERE tenant_id=? AND trip_id=? AND id=?",(tid,trip_id,passenger_id)).fetchone()
        if not row:raise DomainError("TRIP_PASSENGER_NOT_FOUND","Passageiro não localizado.",404)
        if field=="disembarked_at" and not row["boarded_at"]:raise DomainError("TRIP_DISEMBARK_REQUIRES_BOARDING","Desembarque exige embarque prévio.",409)
        if not row[field]:conn.execute(f"UPDATE trip_passengers SET {field}=?,state=?,updated_at=? WHERE tenant_id=? AND id=?",(now,state,now,tid,passenger_id))
        result={"id":passenger_id,"trip_id":trip_id,"state":state,field:row[field] or now};add_audit(conn,tenant_id=tid,actor_id=user.id,action="board" if field=="boarded_at" else "disembark",aggregate_type="trip_passenger",aggregate_id=passenger_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="TripPassengerBoarded" if field=="boarded_at" else "TripPassengerDisembarked",aggregate_type="trip_passenger",aggregate_id=passenger_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/trips/{trip_id}/passengers/{passenger_id}/board", operation_id="board_trip_passenger")
def board_trip_passenger(trip_id: str, passenger_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    return _trip_passenger_transition(trip_id,passenger_id,"boarded_at","boarded",request,user)


@router.post("/trips/{trip_id}/passengers/{passenger_id}/disembark", operation_id="disembark_trip_passenger")
def disembark_trip_passenger(trip_id: str, passenger_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    return _trip_passenger_transition(trip_id,passenger_id,"disembarked_at","completed",request,user)


@router.post("/trips/{trip_id}/checkpoints", status_code=201, operation_id="add_trip_checkpoint")
def add_trip_checkpoint(trip_id: str, data: TripCheckpointInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM trips WHERE tenant_id=? AND id=?",(tid,trip_id),"TRIP_NOT_FOUND","Viagem não localizada.");checkpoint_id=uuid7();now=iso_now();result={"id":checkpoint_id,"trip_id":trip_id,"sequence":data.sequence,"name":data.name,"state":"planned"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO trip_checkpoints(id,tenant_id,trip_id,sequence,name,planned_at,state,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(checkpoint_id,tid,trip_id,data.sequence,data.name,data.planned_at.isoformat() if data.planned_at else None,"planned",data.notes,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="checkpoint_create",aggregate_type="trip",aggregate_id=trip_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.post("/trips/{trip_id}/checkpoints/{checkpoint_id}/reach", operation_id="reach_trip_checkpoint")
def reach_trip_checkpoint(trip_id: str, checkpoint_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM trip_checkpoints WHERE tenant_id=? AND trip_id=? AND id=?",(tid,trip_id,checkpoint_id)).fetchone()
        if not row:raise DomainError("TRIP_CHECKPOINT_NOT_FOUND","Checkpoint não localizado.",404)
        conn.execute("UPDATE trip_checkpoints SET state='reached',actual_at=?,updated_at=? WHERE tenant_id=? AND id=?",(now,now,tid,checkpoint_id));result={"id":checkpoint_id,"trip_id":trip_id,"state":"reached","actual_at":now};add_outbox(conn,tenant_id=tid,event_type="TripCheckpointReached",aggregate_type="trip",aggregate_id=trip_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/trips/{trip_id}/incidents", status_code=201, operation_id="create_trip_incident")
def create_trip_incident(trip_id: str, data: TripIncidentInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,EVENT_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM trips WHERE tenant_id=? AND id=?",(tid,trip_id),"TRIP_NOT_FOUND","Viagem não localizada.")
    if data.passenger_id:row_or_404(request,"SELECT id FROM trip_passengers WHERE tenant_id=? AND trip_id=? AND id=?",(tid,trip_id,data.passenger_id),"TRIP_PASSENGER_NOT_FOUND","Passageiro não localizado.")
    incident_id=uuid7();now=iso_now();occurred=(data.occurred_at or _now_dt()).isoformat();result={"id":incident_id,"trip_id":trip_id,"passenger_id":data.passenger_id,"incident_type":data.incident_type,"severity":data.severity,"occurred_at":occurred}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO trip_incidents(id,tenant_id,trip_id,passenger_id,incident_type,severity,description,occurred_at,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(incident_id,tid,trip_id,data.passenger_id,data.incident_type,data.severity,data.description,occurred,user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="incident",aggregate_type="trip",aggregate_id=trip_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="TripIncidentRecorded",aggregate_type="trip",aggregate_id=trip_id,payload=result,correlation_id=request.state.correlation_id)
    return result


class NoticeInput(BaseModel):
    title:str=Field(min_length=2,max_length=200); body:str=Field(min_length=2,max_length=20000); priority:Literal["normal","high","urgent","emergency"]="normal"; audience:dict[str,Any]=Field(default_factory=lambda:{"type":"all"}); channels:list[str]=Field(default_factory=lambda:["internal"]); scheduled_at:datetime|None=None; expires_at:datetime|None=None; publish_immediately:bool=True; requires_acknowledgement:bool=False


@router.get("/notices",operation_id="list_notices_relational")
def list_notices(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);rows=request.state.store.fetch_all("SELECT * FROM notices WHERE tenant_id=? ORDER BY created_at DESC",(tid,));rows=[row for row in rows if _notice_visible(request,tid,row,user)];return {"items":_serialize(rows,("audience_json","channels_json"))}


@router.post("/notices",status_code=201,operation_id="create_notice_relational")
def create_notice(data:NoticeInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,NOTICE_ROLES);tid=tenant(user);nid=uuid7();now=iso_now();future=bool(data.scheduled_at and data.scheduled_at>_now_dt());state="scheduled" if future else ("published" if data.publish_immediately else "draft");audience=dict(data.audience);audience["requires_acknowledgement"]=bool(data.requires_acknowledgement);snapshot={"title":data.title,"body":data.body,"priority":data.priority,"audience":audience,"channels":data.channels,"scheduled_at":data.scheduled_at.isoformat() if data.scheduled_at else None,"expires_at":data.expires_at.isoformat() if data.expires_at else None,"state":state};result={"id":nid,"title":data.title,"priority":data.priority,"state":state,"version":1,"requires_acknowledgement":data.requires_acknowledgement}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO notices(id,tenant_id,title,body,priority,audience_json,channels_json,scheduled_at,expires_at,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(nid,tid,data.title,data.body,data.priority,dumps(audience),dumps(data.channels),data.scheduled_at.isoformat() if data.scheduled_at else None,data.expires_at.isoformat() if data.expires_at else None,state,1,user.id,now,now));conn.execute("INSERT INTO notice_versions(id,tenant_id,notice_id,version,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,nid,1,dumps(snapshot),user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish" if state=="published" else ("schedule" if state=="scheduled" else "create"),aggregate_type="notice",aggregate_id=nid,correlation_id=request.state.correlation_id,after=result);
        if state=="published":add_outbox(conn,tenant_id=tid,event_type="NoticePublished",aggregate_type="notice",aggregate_id=nid,payload=result,correlation_id=request.state.correlation_id)
    return result


class ServiceRequestInput(BaseModel):
    request_type:str; subject:str=Field(min_length=2,max_length=250); description:str|None=None; priority:Literal["low","normal","high","urgent"]="normal"; department:str|None=None; sla_hours:int|None=Field(default=None,ge=1,le=8760); form_data:dict[str,Any]=Field(default_factory=dict)
class RequestTransitionInput(BaseModel): state:Literal["in_progress","awaiting_requester","resolved","closed","cancelled","reopened"]; reason:str=Field(min_length=3,max_length=2000)


@router.get("/service-requests",operation_id="list_service_requests_relational")
def list_requests(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);sql="SELECT * FROM service_requests WHERE tenant_id=?";params:list[Any]=[tid]
    if not set(user.roles).intersection(REQUEST_AGENT_ROLES):
        if not user.person_id:return {"items":[]}
        sql+=" AND requester_person_id=?";params.append(user.person_id)
    sql+=" ORDER BY created_at DESC";rows=request.state.store.fetch_all(sql,params)
    for row in rows: row["form_data"]=loads(row.pop("form_data_json"),{}) if "form_data_json" in row else {}
    return {"items":rows}


@router.post("/service-requests",status_code=201,operation_id="create_service_request_relational")
def create_request(data:ServiceRequestInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);definition=request.state.store.fetch_one("SELECT d.*,v.form_schema_json,v.workflow_json FROM request_type_definitions d JOIN request_type_versions v ON v.request_type_id=d.id AND v.tenant_id=d.tenant_id AND v.version=d.current_version WHERE d.tenant_id=? AND d.code=? AND d.state='published' AND v.state='published'",(tid,data.request_type));type_version=None;department=data.department;sla_hours=data.sla_hours or 72;workflow_config:dict[str,Any]={}
    if definition:
        schema=loads(definition["form_schema_json"],{});_validate_request_form(schema,data.form_data);type_version=int(definition["current_version"]);department=department or definition["department"];sla_hours=data.sla_hours or int(definition["default_sla_hours"] or 72);workflow_config=loads(definition.get("workflow_json"),{})
    rid=uuid7();now_dt=_now_dt();now=now_dt.isoformat();protocol=f"REQ-{now_dt:%Y%m%d}-{rid[-8:].upper()}";result={"id":rid,"protocol":protocol,"request_type":data.request_type,"request_type_version":type_version,"subject":data.subject,"state":"open","sla_due_at":(now_dt+timedelta(hours=sla_hours)).isoformat()}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO service_requests(id,tenant_id,protocol,requester_person_id,request_type,subject,description,priority,department,sla_due_at,state,version,request_type_version,form_data_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,protocol,user.person_id,data.request_type,data.subject,data.description,data.priority,department,result["sla_due_at"],"open",1,type_version,dumps(data.form_data),now,now));conn.execute("INSERT INTO service_request_events(id,tenant_id,service_request_id,event_type,to_state,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,rid,"created","open",user.id,now));
        if workflow_config.get("definition_id") or workflow_config.get("definition_code"):
            workflow=start_workflow_in_connection(conn,tenant_id=tid,actor_user_id=user.id,correlation_id=request.state.correlation_id,aggregate_type="service_request",aggregate_id=rid,context={"protocol":protocol,"request_type":data.request_type,"requester_person_id":user.person_id},definition_id=workflow_config.get("definition_id"),definition_code=workflow_config.get("definition_code"),definition_version=workflow_config.get("definition_version"));conn.execute("UPDATE service_requests SET workflow_instance_id=? WHERE tenant_id=? AND id=?",(workflow["id"],tid,rid));result["workflow_instance_id"]=workflow["id"]
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="service_request",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="ServiceRequestCreated",aggregate_type="service_request",aggregate_id=rid,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/service-requests/{request_id}/transition",operation_id="transition_service_request")
def transition_request(request_id:str,data:RequestTransitionInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,REQUEST_AGENT_ROLES);tid=tenant(user);row=row_or_404(request,"SELECT * FROM service_requests WHERE tenant_id=? AND id=?",(tid,request_id),"REQUEST_NOT_FOUND","Solicitação não localizada.");now=iso_now()
    if row.get("workflow_instance_id") and data.state in {"resolved","closed","cancelled"}:
        workflow=request.state.store.fetch_one("SELECT state FROM workflow_instances WHERE tenant_id=? AND id=?",(tid,row["workflow_instance_id"]))
        if workflow and workflow["state"]=="active":raise DomainError("REQUEST_WORKFLOW_ACTIVE","Conclua ou cancele o workflow humano antes de encerrar esta solicitação.",409)
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE service_requests SET state=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(data.state,now,tid,request_id));conn.execute("INSERT INTO service_request_events(id,tenant_id,service_request_id,event_type,from_state,to_state,reason,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,request_id,"transition",row["state"],data.state,data.reason,user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="transition",aggregate_type="service_request",aggregate_id=request_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":data.state,"reason":data.reason})
    return {"id":request_id,"state":data.state,"version":int(row["version"])+1}


class AutomationRuleInput(BaseModel):
    name:str;trigger_type:Literal["domain_event","schedule","webhook","state_transition","threshold","manual"];trigger_key:str;conditions:dict[str,Any]=Field(default_factory=dict);actions:list[dict[str,Any]]=Field(default_factory=list)
class AutomationExecuteInput(BaseModel): event_id:str|None=None; payload:dict[str,Any]=Field(default_factory=dict); dry_run:bool=False


class EventRetryInput(BaseModel):
    reason:str=Field(min_length=3,max_length=1000)

@router.get("/operations/events/outbox",operation_id="list_operational_outbox")
def list_operational_outbox(request:Request,state:Literal["pending","published","failed","all"]="all",limit:int=100,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"auditor","support"});tid=tenant(user);limit=max(1,min(limit,500))
    sql="SELECT id,event_type,event_version,aggregate_type,aggregate_id,correlation_id,created_at,published_at,attempts,last_error,next_attempt_at FROM outbox_events WHERE tenant_id=?";params:[Any]=[tid]
    if state=="pending":sql+=" AND published_at IS NULL AND last_error IS NULL"
    elif state=="failed":sql+=" AND published_at IS NULL AND last_error IS NOT NULL"
    elif state=="published":sql+=" AND published_at IS NOT NULL"
    sql+=" ORDER BY created_at DESC LIMIT ?";params.append(limit)
    return {"items":request.state.store.fetch_all(sql,params)}

@router.get("/operations/events/inbox",operation_id="list_operational_inbox")
def list_operational_inbox(request:Request,state:Literal["processing","failed","completed","all"]="all",limit:int=100,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"auditor","support"});tid=tenant(user);limit=max(1,min(limit,500))
    sql="SELECT id,event_id,consumer,event_type,state,attempts,last_error,created_at,updated_at,processed_at FROM inbox_events WHERE tenant_id=?";params:[Any]=[tid]
    if state!="all":sql+=" AND state=?";params.append(state)
    sql+=" ORDER BY updated_at DESC LIMIT ?";params.append(limit)
    return {"items":request.state.store.fetch_all(sql,params)}

@router.post("/operations/events/{event_id}/retry",operation_id="retry_operational_event")
def retry_operational_event(event_id:str,data:EventRetryInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"support"});tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM outbox_events WHERE tenant_id=? AND id=?",(tid,event_id)).fetchone()
        if not row:raise DomainError("OUTBOX_EVENT_NOT_FOUND","Evento não localizado no outbox do tenant.",404)
        completed=conn.execute("SELECT id FROM inbox_events WHERE tenant_id=? AND event_id=? AND state='completed' LIMIT 1",(tid,event_id)).fetchone()
        if completed:raise DomainError("EVENT_ALREADY_COMPLETED","O evento já foi processado com sucesso e não pode ser reexecutado por retry operacional.",409)
        before=dict(row);conn.execute("UPDATE outbox_events SET published_at=NULL,last_error=NULL,next_attempt_at=NULL WHERE tenant_id=? AND id=?",(tid,event_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="retry",aggregate_type="outbox_event",aggregate_id=event_id,correlation_id=request.state.correlation_id,before=before,after={"state":"pending","retry_requested_at":now},reason=data.reason)
    return {"id":event_id,"state":"pending","retry_requested_at":now}


def _matches(conditions:dict[str,Any],payload:dict[str,Any])->bool:
    for key,expected in conditions.items():
        current:Any=payload
        for part in key.split("."):
            if not isinstance(current,dict) or part not in current:return False
            current=current[part]
        if isinstance(expected,dict):
            if "eq" in expected and current!=expected["eq"]:return False
            if "in" in expected and current not in expected["in"]:return False
            if "gte" in expected and current<expected["gte"]:return False
            if "lte" in expected and current>expected["lte"]:return False
        elif current!=expected:return False
    return True


@router.get("/automations/rules",operation_id="list_automation_rules_relational")
def list_automation_rules(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);rows=request.state.store.fetch_all("SELECT * FROM automation_rules WHERE tenant_id=? ORDER BY name,version DESC",(tenant(user),));return {"items":_serialize(rows,("conditions_json","actions_json"))}


@router.post("/automations/rules",status_code=201,operation_id="create_automation_rule_relational")
def create_automation_rule(data:AutomationRuleInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);rid=uuid7();now=iso_now();result={"id":rid,"name":data.name,"trigger_type":data.trigger_type,"trigger_key":data.trigger_key,"state":"active","version":1}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO automation_rules(id,tenant_id,name,trigger_type,trigger_key,conditions_json,actions_json,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.name,data.trigger_type,data.trigger_key,dumps(data.conditions),dumps(data.actions),"active",1,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="automation_rule",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result


@router.post("/automations/rules/{rule_id}/execute",operation_id="execute_automation_rule")
def execute_automation(rule_id:str,data:AutomationExecuteInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);rule=row_or_404(request,"SELECT * FROM automation_rules WHERE tenant_id=? AND id=? AND state='active'",(tid,rule_id),"AUTOMATION_RULE_NOT_FOUND","Regra não localizada ou inativa.");execution_id=uuid7();started=iso_now();matched=_matches(loads(rule["conditions_json"],{}),data.payload);results=[]
    if matched:
        for action in loads(rule["actions_json"],[]):
            kind=action.get("type")
            if data.dry_run:results.append({"type":kind,"state":"would_execute"});continue
            if kind=="send_notification":
                nid=uuid7();recipient=action.get("recipient_person_id") or data.payload.get("person_id");body=str(action.get("body") or data.payload.get("message") or rule["name"]);key=f"automation:{execution_id}:{len(results)}";now=iso_now();channel=action.get("channel","internal")
                with request.state.store.transaction() as conn:
                    conn.execute("INSERT INTO notifications(id,tenant_id,recipient_person_id,channel,template_key,subject,body,state,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(nid,tid,recipient,channel,action.get("template_key"),action.get("subject"),body,"queued",key,now))
                    add_outbox(conn,tenant_id=tid,event_type="NotificationRequested",aggregate_type="notification",aggregate_id=nid,payload={"notification_id":nid,"channel":channel},correlation_id=request.state.correlation_id)
                results.append({"type":kind,"id":nid,"state":"queued"})
            elif kind=="create_request":
                req_id=uuid7();protocol=f"AUTO-{req_id[-10:].upper()}";now=iso_now()
                with request.state.store.transaction() as conn:
                    conn.execute("INSERT INTO service_requests(id,tenant_id,protocol,requester_person_id,request_type,subject,description,priority,department,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(req_id,tid,protocol,data.payload.get("person_id"),action.get("request_type","automation"),action.get("subject",rule["name"]),action.get("description"),action.get("priority","normal"),action.get("department"),"open",1,now,now))
                    add_outbox(conn,tenant_id=tid,event_type="ServiceRequestCreated",aggregate_type="service_request",aggregate_id=req_id,payload={"id":req_id,"protocol":protocol,"source":"automation"},correlation_id=request.state.correlation_id)
                results.append({"type":kind,"id":req_id,"state":"open"})
            else:results.append({"type":kind,"state":"unsupported"})
    finished=iso_now();state="dry_run" if data.dry_run else "completed"
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO automation_executions(id,tenant_id,rule_id,event_id,state,dry_run,input_json,result_json,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(execution_id,tid,rule_id,data.event_id,state,1 if data.dry_run else 0,dumps(data.payload),dumps({"matched":matched,"actions":results}),started,finished));add_audit(conn,tenant_id=tid,actor_id=user.id,action="execute",aggregate_type="automation_rule",aggregate_id=rule_id,correlation_id=request.state.correlation_id,after={"execution_id":execution_id,"matched":matched,"dry_run":data.dry_run})
    return {"id":execution_id,"matched":matched,"dry_run":data.dry_run,"actions":results,"state":state}


class LibraryItemInput(BaseModel): inventory_code:str;title:str;authors:str|None=None;isbn:str|None=None;category:str|None=None;item_type:str="book"
class LoanInput(BaseModel):library_item_id:str;person_id:str;due_at:datetime|None=None

@router.get("/library/items",operation_id="list_library_items_relational")
def list_library_items(request:Request,user:CurrentUser=Depends(current_user)):return {"items":request.state.store.fetch_all("SELECT * FROM library_items WHERE tenant_id=? ORDER BY title",(tenant(user),))}
@router.post("/library/items",status_code=201,operation_id="create_library_item_relational")
def create_library_item(data:LibraryItemInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,LIBRARY_ROLES);tid=tenant(user);iid=uuid7();now=iso_now();result={"id":iid,"inventory_code":data.inventory_code,"title":data.title,"state":"available"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO library_items(id,tenant_id,inventory_code,title,authors,isbn,category,item_type,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(iid,tid,data.inventory_code,data.title,data.authors,data.isbn,data.category,data.item_type,"available",now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="library_item",aggregate_id=iid,correlation_id=request.state.correlation_id,after=result)
    return result
@router.get("/library/loans",operation_id="list_library_loans_relational")
def list_library_loans(request:Request,person_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);manager=bool(set(user.roles).intersection(LIBRARY_ROLES));target=person_id if manager else user.person_id
    sql="SELECT l.*,i.title,i.inventory_code FROM library_loans l JOIN library_items i ON i.id=l.library_item_id WHERE l.tenant_id=?";params:list[Any]=[tid]
    if target:sql+=" AND l.person_id=?";params.append(target)
    elif not manager:return {"items":[]}
    return {"items":request.state.store.fetch_all(sql+" ORDER BY l.loaned_at DESC",params)}
@router.post("/library/loans",status_code=201,operation_id="create_library_loan_relational")
def create_library_loan(data:LoanInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,LIBRARY_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,data.person_id),"PERSON_NOT_FOUND","Pessoa não localizada.");now=datetime.now(UTC);lid=uuid7()
    with request.state.store.transaction() as conn:
        item_row=conn.execute("SELECT * FROM library_items WHERE tenant_id=? AND id=?",(tid,data.library_item_id)).fetchone();item=dict(item_row) if item_row else None
        if not item:raise DomainError("LIBRARY_ITEM_NOT_FOUND","Exemplar não localizado.",404)
        policy=ensure_policy(conn,tid,user.id)
        ready=conn.execute("SELECT * FROM library_reservations WHERE tenant_id=? AND library_item_id=? AND state='ready' ORDER BY ready_at LIMIT 1",(tid,data.library_item_id)).fetchone();ready=dict(ready) if ready else None
        if item["state"]=="reserved" and (not ready or ready["person_id"]!=data.person_id):raise DomainError("LIBRARY_ITEM_RESERVED","Exemplar reservado para outra pessoa.",409)
        if item["state"] not in {"available","reserved"}:raise DomainError("LIBRARY_ITEM_UNAVAILABLE","Exemplar não está disponível.",409)
        due=(data.due_at or (now+timedelta(days=int(policy["max_loan_days"])))).isoformat()
        conn.execute("INSERT INTO library_loans(id,tenant_id,library_item_id,person_id,loaned_at,due_at,renewal_count,fine_amount,policy_version,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(lid,tid,data.library_item_id,data.person_id,now.isoformat(),due,0,"0.00",int(policy["version"]),"open",now.isoformat()))
        conn.execute("UPDATE library_items SET state='loaned',updated_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),tid,data.library_item_id))
        if ready and ready["person_id"]==data.person_id:conn.execute("UPDATE library_reservations SET state='fulfilled',fulfilled_at=? WHERE tenant_id=? AND id=?",(now.isoformat(),tid,ready["id"]))
        conn.execute("INSERT INTO library_loan_events(id,tenant_id,library_loan_id,event_type,payload_json,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,lid,"loaned",dumps({"person_id":data.person_id,"due_at":due,"policy_version":int(policy["version"])}),user.id,now.isoformat()));add_audit(conn,tenant_id=tid,actor_id=user.id,action="loan",aggregate_type="library_item",aggregate_id=data.library_item_id,correlation_id=request.state.correlation_id,after={"loan_id":lid,"person_id":data.person_id,"due_at":due})
    return {"id":lid,"library_item_id":data.library_item_id,"person_id":data.person_id,"due_at":due,"state":"open","policy_version":int(policy["version"])}

@router.post("/library/loans/{loan_id}/return",operation_id="return_library_loan")
def return_library_loan(loan_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,LIBRARY_ROLES);tid=tenant(user);loan=row_or_404(request,"SELECT * FROM library_loans WHERE tenant_id=? AND id=?",(tid,loan_id),"LOAN_NOT_FOUND","Empréstimo não localizado.")
    if loan["state"]!="open":return {"id":loan_id,"state":loan["state"],"fine_amount":loan.get("fine_amount","0.00")}
    now=datetime.now(UTC);fine_id=None
    with request.state.store.transaction() as conn:
        policy=ensure_policy(conn,tid,user.id);fine=fine_for_return(due_at=loan["due_at"],returned_at=now,grace_days=int(policy["grace_days"]),daily_fine=policy["daily_fine"]);conn.execute("UPDATE library_loans SET state='returned',returned_at=?,fine_amount=? WHERE tenant_id=? AND id=?",(now.isoformat(),str(fine),tid,loan_id))
        if fine>0:
            fine_id=uuid7();conn.execute("INSERT INTO library_fines(id,tenant_id,library_loan_id,person_id,amount,reason,state,issued_at) VALUES(?,?,?,?,?,?,?,?)",(fine_id,tid,loan_id,loan["person_id"],str(fine),"Atraso na devolução","open",now.isoformat()))
        next_reservation=promote_next_reservation(conn,tenant_id=tid,item_id=loan["library_item_id"],policy=policy,now=now)
        conn.execute("INSERT INTO library_loan_events(id,tenant_id,library_loan_id,event_type,payload_json,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,loan_id,"returned",dumps({"fine_amount":str(fine),"fine_id":fine_id,"next_reservation_id":next_reservation["id"] if next_reservation else None}),user.id,now.isoformat()));add_audit(conn,tenant_id=tid,actor_id=user.id,action="return",aggregate_type="library_loan",aggregate_id=loan_id,correlation_id=request.state.correlation_id,after={"state":"returned","fine_amount":str(fine),"next_reservation_id":next_reservation["id"] if next_reservation else None})
        if next_reservation:add_outbox(conn,tenant_id=tid,event_type="LibraryReservationReady",aggregate_type="library_reservation",aggregate_id=next_reservation["id"],payload={"person_id":next_reservation["person_id"],"library_item_id":loan["library_item_id"],"expires_at":next_reservation["expires_at"]},correlation_id=request.state.correlation_id)
    return {"id":loan_id,"state":"returned","returned_at":now.isoformat(),"fine_amount":str(fine),"fine_id":fine_id}


class TransportRouteInput(BaseModel):code:str;name:str;vehicle:str|None=None;driver_person_id:str|None=None;monitor_person_id:str|None=None;stops:list[dict[str,Any]]=Field(default_factory=list)
class RiderInput(BaseModel):route_id:str;student_id:str;boarding_stop:str|None=None;dropoff_stop:str|None=None
@router.get("/transport/routes",operation_id="list_transport_routes_relational")
def list_transport_routes(request:Request,user:CurrentUser=Depends(current_user)):rows=request.state.store.fetch_all("SELECT * FROM transport_routes WHERE tenant_id=? ORDER BY name",(tenant(user),));return {"items":_serialize(rows,("stops_json",))}
@router.post("/transport/routes",status_code=201,operation_id="create_transport_route_relational")
def create_transport_route(data:TransportRouteInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user)
    for person_id in (data.driver_person_id,data.monitor_person_id):
        if person_id and not request.state.store.fetch_one("SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,person_id)):raise DomainError("PERSON_NOT_FOUND","Motorista/monitor não pertence ao tenant.",404)
    rid=uuid7();now=iso_now();result={"id":rid,"code":data.code,"name":data.name,"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO transport_routes(id,tenant_id,code,name,vehicle,driver_person_id,monitor_person_id,stops_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.name,data.vehicle,data.driver_person_id,data.monitor_person_id,dumps(data.stops),"active",now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="transport_route",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result
@router.post("/transport/riders",status_code=201,operation_id="create_transport_rider")
def create_transport_rider(data:RiderInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TRANSPORT_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM transport_routes WHERE tenant_id=? AND id=?",(tid,data.route_id),"ROUTE_NOT_FOUND","Rota não localizada.");row_or_404(request,"SELECT id FROM students WHERE tenant_id=? AND id=?",(tid,data.student_id),"STUDENT_NOT_FOUND","Aluno não localizado.");rid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO transport_riders(id,tenant_id,route_id,student_id,boarding_stop,dropoff_stop,state,created_at) VALUES(?,?,?,?,?,?,?,?)",(rid,tid,data.route_id,data.student_id,data.boarding_stop,data.dropoff_stop,"active",now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="assign",aggregate_type="transport_route",aggregate_id=data.route_id,correlation_id=request.state.correlation_id,after={"student_id":data.student_id})
    return {"id":rid,"route_id":data.route_id,"student_id":data.student_id,"state":"active"}


class HealthRecordInput(BaseModel):person_id:str;record_type:str;summary:str;details:dict[str,Any]=Field(default_factory=dict);sensitivity:Literal["restricted","highly_restricted"]="restricted";valid_from:date|None=None;valid_until:date|None=None
class HealthAccessInput(BaseModel):reason:str=Field(min_length=5,max_length=1000)
@router.post("/health/records",status_code=201,operation_id="create_health_record_relational")
def create_health_record(data:HealthRecordInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,data.person_id),"PERSON_NOT_FOUND","Pessoa não localizada.");rid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO health_records(id,tenant_id,person_id,record_type,summary,details_json,sensitivity,valid_from,valid_until,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.person_id,data.record_type,data.summary,dumps(data.details),data.sensitivity,str(data.valid_from) if data.valid_from else None,str(data.valid_until) if data.valid_until else None,"active",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="health_record",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"person_id":data.person_id,"record_type":data.record_type,"sensitivity":data.sensitivity})
    return {"id":rid,"person_id":data.person_id,"record_type":data.record_type,"sensitivity":data.sensitivity,"state":"active"}
@router.post("/health/records/{record_id}/access",operation_id="access_health_record")
def access_health_record(record_id:str,data:HealthAccessInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);row=row_or_404(request,"SELECT * FROM health_records WHERE tenant_id=? AND id=?",(tid,record_id),"HEALTH_RECORD_NOT_FOUND","Registro de saúde não localizado.");now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO health_access_log(id,tenant_id,health_record_id,actor_user_id,reason,accessed_at) VALUES(?,?,?,?,?,?)",(uuid7(),tid,record_id,user.id,data.reason,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="view_sensitive",aggregate_type="health_record",aggregate_id=record_id,correlation_id=request.state.correlation_id,after={"reason":data.reason})
    row["details"]=loads(row.pop("details_json"),{});return row


ALLOWED_MIME={"application/pdf":".pdf","image/png":".png","image/jpeg":".jpg","text/plain":".txt","text/csv":".csv"}
def _detect_mime(content:bytes)->str:
    if content.startswith(b"%PDF-"):return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):return "image/png"
    if content.startswith(b"\xff\xd8\xff"):return "image/jpeg"
    try:content.decode("utf-8");return "text/plain"
    except UnicodeDecodeError:return "application/octet-stream"

@router.get("/documents",operation_id="list_documents_relational")
def list_documents(request:Request,owner_type:str|None=None,owner_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"auditor"});tid=tenant(user);sql="SELECT * FROM documents WHERE tenant_id=?";params:list[Any]=[tid]
    if owner_type:sql+=" AND owner_type=?";params.append(owner_type)
    if owner_id:sql+=" AND owner_id=?";params.append(owner_id)
    sql+=" ORDER BY created_at DESC";return {"items":request.state.store.fetch_all(sql,params)}
@router.post("/documents",status_code=201,operation_id="upload_document_relational")
async def upload_document(request:Request,owner_type:str,category:str,owner_id:str|None=None,file:UploadFile=File(...),user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"auditor"});tid=tenant(user);content=await file.read();max_bytes=25*1024*1024
    if len(content)>max_bytes:raise DomainError("FILE_TOO_LARGE","Arquivo excede 25 MB.",413)
    mime=_detect_mime(content)
    if mime not in ALLOWED_MIME:raise DomainError("UNSUPPORTED_FILE_TYPE","Tipo de arquivo não permitido.",415)
    digest=hashlib.sha256(content).hexdigest();existing=request.state.store.fetch_one("SELECT * FROM documents WHERE tenant_id=? AND sha256=? AND category=? AND owner_type=? AND owner_id IS ?",(tid,digest,category,owner_type,owner_id))
    if existing:return existing
    did=uuid7();key=f"documents/{category}/{did}{ALLOWED_MIME[mime]}";stored=request.app.state.data_router.object_storage(tid).put_bytes(key,content,content_type=mime);now=iso_now();filename=Path(file.filename or f"document{ALLOWED_MIME[mime]}").name
    if stored.sha256 != digest:raise DomainError("DOCUMENT_STORAGE_INTEGRITY_FAILED","Falha de integridade ao armazenar o documento.",500)
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO documents(id,tenant_id,owner_type,owner_id,category,original_filename,mime_type,bytes,sha256,storage_key,antivirus_state,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,owner_type,owner_id,category,filename,mime,len(content),digest,key,"not_configured","active",user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="upload",aggregate_type="document",aggregate_id=did,correlation_id=request.state.correlation_id,after={"sha256":digest,"bytes":len(content),"mime_type":mime})
    return {"id":did,"owner_type":owner_type,"owner_id":owner_id,"category":category,"original_filename":filename,"mime_type":mime,"bytes":len(content),"sha256":digest,"state":"active"}
@router.get("/documents/{document_id}/download",operation_id="download_document_relational")
def download_document(document_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"auditor"});tid=tenant(user);doc=row_or_404(request,"SELECT * FROM documents WHERE tenant_id=? AND id=? AND state='active'",(tid,document_id),"DOCUMENT_NOT_FOUND","Documento não localizado.");storage=request.app.state.data_router.object_storage(tid)
    if not storage.exists(doc["storage_key"]):raise DomainError("DOCUMENT_MISSING","Arquivo não está disponível no storage.",503)
    content=storage.get_bytes(doc["storage_key"])
    if hashlib.sha256(content).hexdigest()!=doc["sha256"]:raise DomainError("DOCUMENT_INTEGRITY_FAILED","A integridade do arquivo falhou.",409)
    headers={"Content-Disposition":f'attachment; filename="{Path(doc["original_filename"]).name}"',"X-Content-SHA256":doc["sha256"]}
    return Response(content=content,media_type=doc["mime_type"],headers=headers)


class IntegrationConnectionInput(BaseModel):provider:str;name:str;environment:Literal["homologation","production"]="production";capabilities:list[str]=Field(default_factory=list);secret_reference:str|None=None;config:dict[str,Any]=Field(default_factory=dict)
@router.get("/integration-connections",operation_id="list_integration_connections_relational")
def list_connections(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,INTEGRATION_ROLES);rows=request.state.store.fetch_all("SELECT id,tenant_id,provider,name,environment,capabilities_json,state,last_health_at,last_health_state,CASE WHEN secret_reference IS NULL OR secret_reference='' THEN 0 ELSE 1 END AS secret_configured,created_at,updated_at FROM integration_connections WHERE tenant_id=? ORDER BY name",(tenant(user),));return {"items":_serialize(rows,("capabilities_json",))}
@router.post("/integration-connections",status_code=201,operation_id="create_integration_connection_relational")
def create_connection(data:IntegrationConnectionInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,INTEGRATION_ROLES);tid=tenant(user);iid=uuid7();now=iso_now();state="configured" if data.secret_reference else "not_configured";result={"id":iid,"provider":data.provider,"name":data.name,"environment":data.environment,"capabilities":data.capabilities,"state":state}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO integration_connections(id,tenant_id,provider,name,environment,capabilities_json,secret_reference,config_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(iid,tid,data.provider,data.name,data.environment,dumps(data.capabilities),data.secret_reference,dumps(data.config),state,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="configure",aggregate_type="integration_connection",aggregate_id=iid,correlation_id=request.state.correlation_id,after={**result,"secret_reference":bool(data.secret_reference)})
    return result


class GovLayoutInput(BaseModel):authority:str;layout_code:str;version:str;effective_from:date;effective_until:date|None=None;layout_schema:dict[str,Any]
class GovExportInput(BaseModel):layout_id:str;reference_period:str;records:list[dict[str,Any]]
@router.get("/government-education/layouts",operation_id="list_government_layouts")
def list_gov_layouts(request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"auditor"});rows=request.state.store.fetch_all("SELECT * FROM government_export_layouts WHERE tenant_id=? ORDER BY authority,layout_code,version DESC",(tenant(user),));return {"items":_serialize(rows,("schema_json",))}
@router.post("/government-education/layouts",status_code=201,operation_id="create_government_layout")
def create_gov_layout(data:GovLayoutInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);lid=uuid7();now=iso_now();result={"id":lid,"authority":data.authority,"layout_code":data.layout_code,"version":data.version,"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO government_export_layouts(id,tenant_id,authority,layout_code,version,effective_from,effective_until,schema_json,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(lid,tid,data.authority,data.layout_code,data.version,str(data.effective_from),str(data.effective_until) if data.effective_until else None,dumps(data.layout_schema),"active",now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="government_export_layout",aggregate_id=lid,correlation_id=request.state.correlation_id,after=result)
    return result
@router.post("/government-education/exports",status_code=201,operation_id="generate_government_export")
def generate_gov_export(data:GovExportInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"auditor"});tid=tenant(user);layout=row_or_404(request,"SELECT * FROM government_export_layouts WHERE tenant_id=? AND id=? AND state='active'",(tid,data.layout_id),"GOV_LAYOUT_NOT_FOUND","Layout não localizado.");schema=loads(layout["schema_json"],{});fields=schema.get("fields",[]);names=[f["name"] if isinstance(f,dict) else str(f) for f in fields]
    errors=[]
    for idx,record in enumerate(data.records,1):
        for name in names:
            if name not in record:errors.append({"row":idx,"field":name,"code":"REQUIRED"})
    if errors:raise DomainError("GOV_EXPORT_VALIDATION_FAILED","Existem registros incompatíveis com o layout.",422,errors=errors[:200])
    buffer=io.StringIO(newline="");writer=csv.DictWriter(buffer,fieldnames=names,extrasaction="ignore",lineterminator="\n");writer.writeheader();writer.writerows(data.records);content=buffer.getvalue().encode("utf-8");digest=hashlib.sha256(content).hexdigest();eid=uuid7();key=f"exports/government/{layout['authority']}/{eid}.csv";stored=request.app.state.data_router.object_storage(tid).put_bytes(key,content,content_type="text/csv");now=iso_now();validation={"errors":[],"layout_version":layout["version"]}
    if stored.sha256 != digest:raise DomainError("GOV_EXPORT_STORAGE_INTEGRITY_FAILED","Falha de integridade ao armazenar a exportação.",500)
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO government_exports(id,tenant_id,layout_id,reference_period,state,record_count,sha256,storage_key,validation_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(eid,tid,data.layout_id,data.reference_period,"generated",len(data.records),digest,key,dumps(validation),user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="generate",aggregate_type="government_export",aggregate_id=eid,correlation_id=request.state.correlation_id,after={"sha256":digest,"record_count":len(data.records),"authority":layout["authority"]})
    return {"id":eid,"state":"generated","record_count":len(data.records),"sha256":digest,"layout_version":layout["version"],"transmission":"not_configured"}
