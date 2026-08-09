from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, model_validator

from app.modules.operations.common import dumps, loads, require, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["health"])
HEALTH_ROLES={"tenant_owner","institution_director","unit_manager","secretary","health_operator"}

class IncidentInput(BaseModel):
    person_id:str;incident_type:str=Field(min_length=2,max_length=80);occurred_at:datetime;location:str|None=None;summary:str=Field(min_length=3,max_length=4000);first_aid:dict[str,Any]=Field(default_factory=dict);referred_to:str|None=None;guardian_notified:bool=False
class IncidentCloseInput(BaseModel):reason:str=Field(min_length=3,max_length=2000)
class MedicationAuthorizationInput(BaseModel):
    person_id:str;medication_name:str=Field(min_length=2,max_length=200);dosage:str=Field(min_length=1,max_length=200);instructions:str=Field(min_length=2,max_length=2000);starts_on:date;ends_on:date|None=None;prescriber:str|None=None;guardian_person_id:str|None=None;consent_document_id:str|None=None
    @model_validator(mode="after")
    def dates(self):
        if self.ends_on and self.ends_on<self.starts_on:raise ValueError("ends_on deve ser posterior a starts_on.")
        return self
class MedicationAdministrationInput(BaseModel):authorization_id:str;administered_at:datetime;dosage:str|None=None;notes:str|None=Field(default=None,max_length=2000)


def _person_exists(request:Request,tid:str,person_id:str)->bool:return bool(request.state.store.fetch_one("SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,person_id)))
def _managed(user:CurrentUser)->bool:return bool(set(user.roles).intersection(HEALTH_ROLES))

def _visible_people(request:Request,tid:str,user:CurrentUser)->set[str]:
    if not user.person_id:return set()
    people={user.person_id}
    dependents=request.state.store.fetch_all("SELECT s.person_id FROM guardians g JOIN guardian_students gs ON gs.guardian_id=g.id AND gs.tenant_id=g.tenant_id JOIN students s ON s.id=gs.student_id AND s.tenant_id=gs.tenant_id WHERE g.tenant_id=? AND g.person_id=? AND g.state='active' AND s.state='active'",(tid,user.person_id))
    people.update(str(x["person_id"]) for x in dependents);return people

@router.get("/health/records",operation_id="list_health_record_metadata")
def list_records(request:Request,person_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);sql="SELECT id,person_id,record_type,summary,sensitivity,valid_from,valid_until,state,created_by,created_at,updated_at FROM health_records WHERE tenant_id=?";params:list[Any]=[tid]
    if person_id:sql+=" AND person_id=?";params.append(person_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY updated_at DESC",params)}

@router.get("/health/access-log",operation_id="list_health_access_log")
def access_log(request:Request,record_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,{"tenant_owner","institution_director","health_operator"});tid=tenant(user);sql="SELECT * FROM health_access_log WHERE tenant_id=?";params:list[Any]=[tid]
    if record_id:sql+=" AND health_record_id=?";params.append(record_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY accessed_at DESC LIMIT 500",params)}

@router.get("/health/incidents",operation_id="list_health_incidents")
def list_incidents(request:Request,person_id:str|None=None,state:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);sql="SELECT * FROM health_incidents WHERE tenant_id=?";params:list[Any]=[tid]
    if person_id:sql+=" AND person_id=?";params.append(person_id)
    if state:sql+=" AND state=?";params.append(state)
    rows=request.state.store.fetch_all(sql+" ORDER BY occurred_at DESC",params)
    for row in rows:row["first_aid"]=loads(row.pop("first_aid_json"),{})
    return {"items":rows}

@router.post("/health/incidents",status_code=201,operation_id="create_health_incident")
def create_incident(data:IncidentInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user)
    if not _person_exists(request,tid,data.person_id):raise DomainError("PERSON_NOT_FOUND","Pessoa não localizada.",404)
    iid=uuid7();now=iso_now();notified=now if data.guardian_notified else None;result={"id":iid,"person_id":data.person_id,"incident_type":data.incident_type,"state":"open","guardian_notified_at":notified}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO health_incidents(id,tenant_id,person_id,incident_type,occurred_at,location,summary,first_aid_json,referred_to,guardian_notified_at,state,reported_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,tid,data.person_id,data.incident_type,data.occurred_at.isoformat(),data.location,data.summary,dumps(data.first_aid),data.referred_to,notified,"open",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="report",aggregate_type="health_incident",aggregate_id=iid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="HealthIncidentReported",aggregate_type="health_incident",aggregate_id=iid,payload={"person_id":data.person_id,"incident_type":data.incident_type,"guardian_notification_requested":not data.guardian_notified},correlation_id=request.state.correlation_id)
    return result

@router.post("/health/incidents/{incident_id}/close",operation_id="close_health_incident")
def close_incident(incident_id:str,data:IncidentCloseInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM health_incidents WHERE tenant_id=? AND id=?",(tid,incident_id))
    if not row:raise DomainError("HEALTH_INCIDENT_NOT_FOUND","Ocorrência de saúde não localizada.",404)
    if row["state"]=="closed":return {"id":incident_id,"state":"closed","closed_at":row["closed_at"]}
    now=iso_now();request.state.store.execute("UPDATE health_incidents SET state='closed',closed_at=?,closed_by=?,updated_at=? WHERE tenant_id=? AND id=?",(now,user.id,now,tid,incident_id));return {"id":incident_id,"state":"closed","closed_at":now}

@router.get("/health/medication-authorizations",operation_id="list_medication_authorizations")
def list_authorizations(request:Request,person_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);sql="SELECT * FROM medication_authorizations WHERE tenant_id=?";params:list[Any]=[tid]
    if person_id:sql+=" AND person_id=?";params.append(person_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY starts_on DESC",params)}

@router.post("/health/medication-authorizations",status_code=201,operation_id="create_medication_authorization")
def create_authorization(data:MedicationAuthorizationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user)
    if not _person_exists(request,tid,data.person_id):raise DomainError("PERSON_NOT_FOUND","Pessoa não localizada.",404)
    if data.guardian_person_id and not _person_exists(request,tid,data.guardian_person_id):raise DomainError("GUARDIAN_PERSON_NOT_FOUND","Responsável não localizado.",404)
    if data.consent_document_id and not request.state.store.fetch_one("SELECT id FROM documents WHERE tenant_id=? AND id=? AND state='active'",(tid,data.consent_document_id)):raise DomainError("CONSENT_DOCUMENT_NOT_FOUND","Documento de consentimento não localizado.",404)
    aid=uuid7();now=iso_now();result={"id":aid,"person_id":data.person_id,"medication_name":data.medication_name,"dosage":data.dosage,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on) if data.ends_on else None,"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO medication_authorizations(id,tenant_id,person_id,medication_name,dosage,instructions,starts_on,ends_on,prescriber,guardian_person_id,consent_document_id,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(aid,tid,data.person_id,data.medication_name,data.dosage,data.instructions,str(data.starts_on),str(data.ends_on) if data.ends_on else None,data.prescriber,data.guardian_person_id,data.consent_document_id,"active",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="authorize_medication",aggregate_type="medication_authorization",aggregate_id=aid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/health/medication-administrations",status_code=201,operation_id="administer_medication")
def administer(data:MedicationAdministrationInput,request:Request,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=160),user:CurrentUser=Depends(current_user)):
    require(user,HEALTH_ROLES);tid=tenant(user);payload=data.model_dump(mode="json");scope=f"health:medication:{tid}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,payload)
        if cached:return cached[1]
        row=conn.execute("SELECT * FROM medication_authorizations WHERE tenant_id=? AND id=? AND state='active'",(tid,data.authorization_id)).fetchone();auth=dict(row) if row else None
        if not auth:raise DomainError("MEDICATION_AUTHORIZATION_NOT_FOUND","Autorização ativa não localizada.",404)
        administered_date=data.administered_at.astimezone(UTC).date();start=date.fromisoformat(auth["starts_on"]);end=date.fromisoformat(auth["ends_on"]) if auth.get("ends_on") else None
        if administered_date<start or (end and administered_date>end):raise DomainError("MEDICATION_OUTSIDE_AUTHORIZATION_PERIOD","Administração fora da vigência autorizada.",409)
        mid=uuid7();now=iso_now();dosage=data.dosage or auth["dosage"];result={"id":mid,"authorization_id":data.authorization_id,"person_id":auth["person_id"],"administered_at":data.administered_at.isoformat(),"dosage":dosage}
        conn.execute("INSERT INTO medication_administrations(id,tenant_id,authorization_id,person_id,administered_at,dosage,notes,administered_by,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(mid,tid,data.authorization_id,auth["person_id"],data.administered_at.isoformat(),dosage,data.notes,user.id,idempotency_key,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="administer_medication",aggregate_type="medication_authorization",aggregate_id=data.authorization_id,correlation_id=request.state.correlation_id,after={"administration_id":mid,"person_id":auth["person_id"],"administered_at":data.administered_at.isoformat()});add_outbox(conn,tenant_id=tid,event_type="MedicationAdministered",aggregate_type="medication_administration",aggregate_id=mid,payload={"person_id":auth["person_id"],"authorization_id":data.authorization_id,"administered_at":data.administered_at.isoformat()},correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,payload,201,result)
    return result

@router.get("/health/me",operation_id="get_my_health_context")
def my_health(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);people=_visible_people(request,tid,user)
    if not people:return {"people":[],"records":[],"incidents":[],"medications":[]}
    placeholders=','.join('?' for _ in people);params=(tid,*sorted(people))
    person_rows=request.state.store.fetch_all(f"SELECT id,full_name FROM people WHERE tenant_id=? AND id IN ({placeholders}) ORDER BY full_name",params)
    records=request.state.store.fetch_all(f"SELECT id,person_id,record_type,summary,valid_from,valid_until,state FROM health_records WHERE tenant_id=? AND person_id IN ({placeholders}) AND sensitivity='restricted' AND state='active' ORDER BY updated_at DESC",params)
    incidents=request.state.store.fetch_all(f"SELECT id,person_id,incident_type,occurred_at,location,summary,referred_to,guardian_notified_at,state FROM health_incidents WHERE tenant_id=? AND person_id IN ({placeholders}) ORDER BY occurred_at DESC LIMIT 100",params)
    medications=request.state.store.fetch_all(f"SELECT id,person_id,medication_name,dosage,instructions,starts_on,ends_on,state FROM medication_authorizations WHERE tenant_id=? AND person_id IN ({placeholders}) AND state='active' ORDER BY starts_on DESC",params)
    return {"people":person_rows,"records":records,"incidents":incidents,"medications":medications}
