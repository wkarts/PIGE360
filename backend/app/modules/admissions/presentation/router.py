from __future__ import annotations
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field, model_validator
from app.modules.operations.common import ADMIN_ROLES, require, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user
router=APIRouter(tags=["admissions"])
class CampaignInput(BaseModel):
    code:str=Field(min_length=2,max_length=80);name:str=Field(min_length=3,max_length=240);program_id:str|None=None;academic_year_id:str|None=None;starts_on:date;ends_on:date|None=None;channels:list[str]=Field(default_factory=list);budget:Decimal|None=Field(default=None,ge=0)
    @model_validator(mode="after")
    def validate_period(self):
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on deve ser igual ou posterior a starts_on")
        if bool(self.program_id) != bool(self.academic_year_id):
            raise ValueError("program_id e academic_year_id devem ser informados em conjunto")
        return self
class CampaignStateInput(BaseModel):state:Literal["active","paused","closed","archived"];reason:str=Field(min_length=3,max_length=2000)
class LeadInput(BaseModel):
    campaign_id:str|None=None;full_name:str=Field(min_length=2,max_length=300);email:EmailStr|None=None;phone:str|None=None;desired_program_id:str|None=None;desired_academic_year_id:str|None=None;source:str=Field(default="manual",max_length=120);external_ref:str|None=Field(default=None,max_length=160);consent:bool=True;notes:str|None=Field(default=None,max_length=8000)
class LeadStateInput(BaseModel):state:Literal["contacted","qualified","nurturing","lost","cancelled"];reason:str=Field(min_length=3,max_length=2000)
class ProcessInput(BaseModel):
    code:str=Field(min_length=2,max_length=80);name:str=Field(min_length=3,max_length=240);program_id:str;academic_year_id:str;applications_open_at:datetime|None=None;applications_close_at:datetime|None=None;seats:int|None=Field(default=None,ge=1,le=100000);ranking_method:Literal["weighted_sum"]="weighted_sum"
    @model_validator(mode="after")
    def validate_window(self):
        if self.applications_open_at and self.applications_close_at and self.applications_close_at <= self.applications_open_at:
            raise ValueError("applications_close_at deve ser posterior a applications_open_at")
        return self
class ProcessStateInput(BaseModel):state:Literal["published","applications_open","applications_closed","ranking","completed","cancelled"];reason:str=Field(min_length=3,max_length=2000)
class AssessmentInput(BaseModel):code:str=Field(min_length=1,max_length=80);name:str=Field(min_length=2,max_length=240);assessment_type:Literal["exam","interview","document_review","portfolio","practical"];weight:Decimal=Field(default=Decimal("1"),gt=0,le=100);max_score:Decimal=Field(default=Decimal("100"),gt=0,le=10000);scheduled_at:datetime|None=None
class LeadConvertInput(BaseModel):process_id:str
class ApplicationInput(BaseModel):process_id:str;candidate_id:str
class ResultInput(BaseModel):assessment_id:str;score:Decimal=Field(ge=0);outcome:str|None=Field(default=None,max_length=200);notes:str|None=Field(default=None,max_length=4000)
class ApplicationStateInput(BaseModel):state:Literal["under_review","waitlisted","selected","rejected","cancelled"];reason:str=Field(min_length=3,max_length=2000)
class ReservationInput(BaseModel):class_group_id:str;expires_at:datetime;reason:str=Field(min_length=3,max_length=2000)

def _program_year(request:Request,tid:str,program_id:str,academic_year_id:str)->None:
    program=request.state.store.fetch_one("SELECT institution_id FROM programs WHERE tenant_id=? AND id=? AND state='active'",(tid,program_id))
    if not program:raise DomainError("PROGRAM_NOT_FOUND","Programa não localizado.",404)
    year=request.state.store.fetch_one("SELECT id FROM academic_years WHERE tenant_id=? AND id=? AND institution_id=?",(tid,academic_year_id,program["institution_id"]))
    if not year:raise DomainError("ACADEMIC_YEAR_NOT_FOUND","Ano letivo não pertence à instituição do programa.",404)

def _application_number(process_id:str,application_id:str)->str:return f"APP-{process_id.replace('-','')[-6:].upper()}-{application_id.replace('-','')[-8:].upper()}"
def _candidate_event(conn,tid,candidate_id,event_type,actor,payload):conn.execute("INSERT INTO admission_candidate_events(id,tenant_id,candidate_id,event_type,from_state,to_state,reason,payload_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,candidate_id,event_type,None,None,None,json.dumps(payload,ensure_ascii=False),actor,iso_now()))


def _require_process_state(process:dict[str,Any], *allowed:str)->None:
    if process.get("state") not in set(allowed):
        raise DomainError("ADMISSION_PROCESS_STATE_INVALID", f"Processo seletivo deve estar em: {', '.join(allowed)}.", 409)

def _assert_application_window(process:dict[str,Any])->None:
    now=datetime.now(UTC)
    if process.get("applications_open_at"):
        opened=datetime.fromisoformat(str(process["applications_open_at"]).replace("Z","+00:00"))
        if opened.tzinfo is None:opened=opened.replace(tzinfo=UTC)
        if now < opened:raise DomainError("ADMISSION_APPLICATIONS_NOT_OPEN_YET","Período de inscrições ainda não foi iniciado.",409)
    if process.get("applications_close_at"):
        closed=datetime.fromisoformat(str(process["applications_close_at"]).replace("Z","+00:00"))
        if closed.tzinfo is None:closed=closed.replace(tzinfo=UTC)
        if now > closed:raise DomainError("ADMISSION_APPLICATIONS_CLOSED","Período de inscrições já foi encerrado.",409)

@router.get("/admissions/campaigns",operation_id="list_admission_campaigns")
def list_campaigns(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);rows=request.state.store.fetch_all("SELECT * FROM admission_campaigns WHERE tenant_id=? ORDER BY starts_on DESC,created_at DESC",(tenant(user),));
    for r in rows:
        try:r["channels"]=json.loads(r.pop("channels_json") or "[]")
        except Exception:r["channels"]=[]
    return {"items":rows}
@router.post("/admissions/campaigns",status_code=201,operation_id="create_admission_campaign")
def create_campaign(data:CampaignInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user)
    if data.program_id and data.academic_year_id:_program_year(request,tid,data.program_id,data.academic_year_id)
    rid=uuid7();now=iso_now();state="active" if data.starts_on<=date.today() and (not data.ends_on or data.ends_on>=date.today()) else "draft"
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO admission_campaigns(id,tenant_id,code,name,program_id,academic_year_id,starts_on,ends_on,channels_json,budget,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.name,data.program_id,data.academic_year_id,str(data.starts_on),str(data.ends_on) if data.ends_on else None,json.dumps(data.channels),str(data.budget) if data.budget is not None else None,state,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="admission_campaign",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"state":state,"code":data.code})
    return {"id":rid,"code":data.code,"name":data.name,"state":state}
@router.post("/admissions/campaigns/{campaign_id}/state",operation_id="transition_admission_campaign")
def campaign_state(campaign_id:str,data:CampaignStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM admission_campaigns WHERE tenant_id=? AND id=?",(tid,campaign_id))
    if not row:raise DomainError("ADMISSION_CAMPAIGN_NOT_FOUND","Campanha não localizada.",404)
    allowed={"draft":{"active","archived"},"active":{"paused","closed","archived"},"paused":{"active","closed","archived"},"closed":{"archived"}}
    if data.state not in allowed.get(row["state"],set()):raise DomainError("INVALID_STATE_TRANSITION","Transição da campanha não permitida.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE admission_campaigns SET state=?,updated_at=? WHERE tenant_id=? AND id=?",(data.state,now,tid,campaign_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="transition",aggregate_type="admission_campaign",aggregate_id=campaign_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":data.state},reason=data.reason)
    return {"id":campaign_id,"state":data.state}

@router.get("/admissions/leads",operation_id="list_admission_leads")
def list_leads(request:Request,state:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);sql="SELECT l.*,c.name AS campaign_name,p.name AS program_name FROM admission_leads l LEFT JOIN admission_campaigns c ON c.id=l.campaign_id LEFT JOIN programs p ON p.id=l.desired_program_id WHERE l.tenant_id=?";params=[tid]
    if state:sql+=" AND l.state=?";params.append(state)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY l.created_at DESC",params)}
@router.post("/admissions/leads",status_code=201,operation_id="create_admission_lead")
def create_lead(data:LeadInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);return _create_lead(data,request,tenant(user),user.id,request.state.correlation_id)

def _create_lead(data:LeadInput,request:Request,tid:str,actor:str,correlation_id:str):
    if not data.consent:raise DomainError("LEAD_CONSENT_REQUIRED","Captação exige registro de consentimento/ciência para contato.",422)
    campaign=None
    if data.campaign_id:
        campaign=request.state.store.fetch_one("SELECT * FROM admission_campaigns WHERE tenant_id=? AND id=? AND state='active'",(tid,data.campaign_id))
        if not campaign:raise DomainError("ADMISSION_CAMPAIGN_NOT_FOUND","Campanha ativa não localizada.",404)
    desired_program_id=data.desired_program_id or (campaign.get("program_id") if campaign else None)
    desired_academic_year_id=data.desired_academic_year_id or (campaign.get("academic_year_id") if campaign else None)
    if bool(desired_program_id)!=bool(desired_academic_year_id):raise DomainError("LEAD_ACADEMIC_CONTEXT_INCOMPLETE","Programa e ano letivo devem ser informados em conjunto.",422)
    if desired_program_id and desired_academic_year_id:_program_year(request,tid,desired_program_id,desired_academic_year_id)
    if data.external_ref:
        existing=request.state.store.fetch_one("SELECT * FROM admission_leads WHERE tenant_id=? AND source=? AND external_ref=?",(tid,data.source,data.external_ref))
        if existing:return {**existing,"replayed":True}
    rid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO admission_leads(id,tenant_id,campaign_id,full_name,email,phone,desired_program_id,desired_academic_year_id,source,external_ref,consent_at,state,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.campaign_id,data.full_name,str(data.email) if data.email else None,data.phone,desired_program_id,desired_academic_year_id,data.source,data.external_ref,now,"new",data.notes,now,now));add_audit(conn,tenant_id=tid,actor_id=actor,action="create",aggregate_type="admission_lead",aggregate_id=rid,correlation_id=correlation_id,after={"state":"new","source":data.source,"consent_at":now});add_outbox(conn,tenant_id=tid,event_type="AdmissionLeadCreated",aggregate_type="admission_lead",aggregate_id=rid,payload={"source":data.source,"campaign_id":data.campaign_id},correlation_id=correlation_id)
    return {"id":rid,"state":"new","full_name":data.full_name,"email":str(data.email) if data.email else None,"source":data.source,"replayed":False}

@router.get("/public/admissions/campaigns",operation_id="list_public_admission_campaigns")
def public_campaigns(request:Request):
    resolution=request.state.host_resolution
    if resolution.plane!="tenant" or not resolution.tenant_id:raise DomainError("TENANT_ROUTE_REQUIRED","Campanhas disponíveis somente no domínio da instituição.",404)
    today=date.today().isoformat()
    rows=request.state.store.fetch_all("SELECT ac.id,ac.code,ac.name,ac.program_id,ac.academic_year_id,ac.starts_on,ac.ends_on,p.name AS program_name,ay.name AS academic_year_name FROM admission_campaigns ac LEFT JOIN programs p ON p.id=ac.program_id LEFT JOIN academic_years ay ON ay.id=ac.academic_year_id WHERE ac.tenant_id=? AND ac.state='active' AND ac.starts_on<=? AND (ac.ends_on IS NULL OR ac.ends_on>=?) ORDER BY ac.starts_on DESC,ac.name",(resolution.tenant_id,today,today))
    return {"items":rows}

@router.post("/public/admissions/leads",status_code=201,operation_id="create_public_admission_lead")
def public_lead(data:LeadInput,request:Request):
    resolution=request.state.host_resolution
    if resolution.plane!="tenant" or not resolution.tenant_id:raise DomainError("TENANT_ROUTE_REQUIRED","Formulário disponível somente no domínio da instituição.",404)
    if data.source=="manual":data.source="public_form"
    # Limite simples por e-mail/telefone em janela de uma hora; não persiste IP bruto.
    tid=resolution.tenant_id;since=(datetime.now(UTC)-timedelta(hours=1)).isoformat()
    if data.email:
        recent=int(request.state.store.scalar("SELECT COUNT(*) AS n FROM admission_leads WHERE tenant_id=? AND email=? AND created_at>=?",(tid,str(data.email),since)) or 0)
        if recent>=3:raise DomainError("PUBLIC_FORM_RATE_LIMITED","Muitas solicitações recentes para este contato.",429)
    return _create_lead(data,request,tid,"public-form",request.state.correlation_id)

@router.post("/admissions/leads/{lead_id}/state",operation_id="transition_admission_lead")
def lead_state(lead_id:str,data:LeadStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM admission_leads WHERE tenant_id=? AND id=?",(tid,lead_id))
    if not row:raise DomainError("ADMISSION_LEAD_NOT_FOUND","Lead não localizado.",404)
    if row["state"] in {"converted","lost","cancelled"}:raise DomainError("LEAD_STATE_FINAL","Lead já está em estado final.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE admission_leads SET state=?,updated_at=? WHERE tenant_id=? AND id=?",(data.state,now,tid,lead_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="transition",aggregate_type="admission_lead",aggregate_id=lead_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":data.state},reason=data.reason)
    return {"id":lead_id,"state":data.state}

@router.get("/admissions/processes",operation_id="list_admission_processes")
def list_processes(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);return {"items":request.state.store.fetch_all("SELECT ap.*,p.name AS program_name,ay.name AS academic_year_name FROM admission_processes ap JOIN programs p ON p.id=ap.program_id JOIN academic_years ay ON ay.id=ap.academic_year_id WHERE ap.tenant_id=? ORDER BY ap.created_at DESC",(tenant(user),))}
@router.post("/admissions/processes",status_code=201,operation_id="create_admission_process")
def create_process(data:ProcessInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);_program_year(request,tid,data.program_id,data.academic_year_id);rid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO admission_processes(id,tenant_id,code,name,program_id,academic_year_id,applications_open_at,applications_close_at,seats,ranking_method,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.name,data.program_id,data.academic_year_id,data.applications_open_at.isoformat() if data.applications_open_at else None,data.applications_close_at.isoformat() if data.applications_close_at else None,data.seats,data.ranking_method,"draft",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="admission_process",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"state":"draft","code":data.code,"seats":data.seats})
    return {"id":rid,"state":"draft","code":data.code,"name":data.name,"seats":data.seats}
@router.post("/admissions/processes/{process_id}/state",operation_id="transition_admission_process")
def process_state(process_id:str,data:ProcessStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM admission_processes WHERE tenant_id=? AND id=?",(tid,process_id))
    if not row:raise DomainError("ADMISSION_PROCESS_NOT_FOUND","Processo seletivo não localizado.",404)
    allowed={"draft":{"published","cancelled"},"published":{"applications_open","cancelled"},"applications_open":{"applications_closed","cancelled"},"applications_closed":{"ranking","completed"},"ranking":{"completed"}}
    if data.state not in allowed.get(row["state"],set()):raise DomainError("INVALID_STATE_TRANSITION","Transição do processo seletivo não permitida.",409)
    if data.state=="applications_open":_assert_application_window(row)
    now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE admission_processes SET state=?,updated_at=? WHERE tenant_id=? AND id=?",(data.state,now,tid,process_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="transition",aggregate_type="admission_process",aggregate_id=process_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":data.state},reason=data.reason)
    return {"id":process_id,"state":data.state}

@router.get("/admissions/processes/{process_id}/assessments",operation_id="list_admission_assessments")
def list_assessments(process_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);return {"items":request.state.store.fetch_all("SELECT * FROM admission_assessments WHERE tenant_id=? AND process_id=? ORDER BY scheduled_at,code",(tenant(user),process_id))}
@router.post("/admissions/processes/{process_id}/assessments",status_code=201,operation_id="create_admission_assessment")
def create_assessment(process_id:str,data:AssessmentInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);process=request.state.store.fetch_one("SELECT * FROM admission_processes WHERE tenant_id=? AND id=?",(tid,process_id))
    if not process:raise DomainError("ADMISSION_PROCESS_NOT_FOUND","Processo seletivo não localizado.",404)
    _require_process_state(process,"draft","published","applications_open")
    rid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO admission_assessments(id,tenant_id,process_id,code,name,assessment_type,weight,max_score,scheduled_at,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,process_id,data.code,data.name,data.assessment_type,str(data.weight),str(data.max_score),data.scheduled_at.isoformat() if data.scheduled_at else None,"active",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="admission_assessment",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"process_id":process_id,"weight":str(data.weight),"max_score":str(data.max_score)})
    return {"id":rid,"process_id":process_id,"code":data.code,"name":data.name,"state":"active"}

@router.post("/admissions/applications",status_code=201,operation_id="create_admission_application")
def create_application(data:ApplicationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);process=request.state.store.fetch_one("SELECT * FROM admission_processes WHERE tenant_id=? AND id=?",(tid,data.process_id));candidate=request.state.store.fetch_one("SELECT * FROM admission_candidates WHERE tenant_id=? AND id=?",(tid,data.candidate_id))
    if not process:raise DomainError("ADMISSION_PROCESS_NOT_FOUND","Processo seletivo não localizado.",404)
    _require_process_state(process,"applications_open");_assert_application_window(process)
    if not candidate:raise DomainError("CANDIDATE_NOT_FOUND","Candidato não localizado.",404)
    if candidate["program_id"]!=process["program_id"] or candidate["academic_year_id"]!=process["academic_year_id"]:raise DomainError("APPLICATION_CONTEXT_MISMATCH","Candidato não pertence ao programa/ano do processo seletivo.",409)
    existing=request.state.store.fetch_one("SELECT * FROM admission_applications WHERE tenant_id=? AND process_id=? AND candidate_id=?",(tid,data.process_id,data.candidate_id))
    if existing:return {**existing,"replayed":True}
    rid=uuid7();now=iso_now();number=_application_number(data.process_id,rid)
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO admission_applications(id,tenant_id,process_id,candidate_id,application_number,state,applied_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(rid,tid,data.process_id,data.candidate_id,number,"applied",now,now));_candidate_event(conn,tid,data.candidate_id,"application_created",user.id,{"application_id":rid,"process_id":data.process_id});add_audit(conn,tenant_id=tid,actor_id=user.id,action="apply",aggregate_type="admission_application",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"candidate_id":data.candidate_id,"application_number":number});add_outbox(conn,tenant_id=tid,event_type="AdmissionApplicationCreated",aggregate_type="admission_application",aggregate_id=rid,payload={"candidate_id":data.candidate_id,"process_id":data.process_id},correlation_id=request.state.correlation_id)
    return {"id":rid,"application_number":number,"state":"applied","candidate_id":data.candidate_id,"replayed":False}

@router.post("/admissions/leads/{lead_id}/convert",status_code=201,operation_id="convert_lead_to_admission_application")
def convert_lead(lead_id:str,data:LeadConvertInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);lead=request.state.store.fetch_one("SELECT * FROM admission_leads WHERE tenant_id=? AND id=?",(tid,lead_id));process=request.state.store.fetch_one("SELECT * FROM admission_processes WHERE tenant_id=? AND id=?",(tid,data.process_id))
    if not lead:raise DomainError("ADMISSION_LEAD_NOT_FOUND","Lead não localizado.",404)
    if not process:raise DomainError("ADMISSION_PROCESS_NOT_FOUND","Processo seletivo não localizado.",404)
    _require_process_state(process,"applications_open");_assert_application_window(process)
    if lead.get("converted_candidate_id"):
        app=request.state.store.fetch_one("SELECT * FROM admission_applications WHERE tenant_id=? AND process_id=? AND candidate_id=?",(tid,data.process_id,lead["converted_candidate_id"]))
        if app:return {"lead_id":lead_id,"candidate_id":lead["converted_candidate_id"],"application_id":app["id"],"state":app["state"],"replayed":True}
    if lead.get("desired_program_id") and lead["desired_program_id"]!=process["program_id"]:raise DomainError("LEAD_PROCESS_MISMATCH","Processo seletivo não corresponde ao programa desejado pelo lead.",409)
    if lead.get("desired_academic_year_id") and lead["desired_academic_year_id"]!=process["academic_year_id"]:raise DomainError("LEAD_PROCESS_MISMATCH","Processo seletivo não corresponde ao ano desejado pelo lead.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:
        person=conn.execute("SELECT * FROM people WHERE tenant_id=? AND email=? AND state='active' ORDER BY created_at LIMIT 1",(tid,lead["email"])).fetchone() if lead.get("email") else None;person_id=person["id"] if person else uuid7()
        if not person:conn.execute("INSERT INTO people(id,tenant_id,full_name,email,phone,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(person_id,tid,lead["full_name"],lead.get("email"),lead.get("phone"),"active",now,now))
        candidate_id=uuid7();conn.execute("INSERT INTO admission_candidates(id,tenant_id,person_id,program_id,academic_year_id,source,state,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(candidate_id,tid,person_id,process["program_id"],process["academic_year_id"],lead.get("source"),"registered",lead.get("notes"),now,now));app_id=uuid7();number=_application_number(data.process_id,app_id);conn.execute("INSERT INTO admission_applications(id,tenant_id,process_id,candidate_id,application_number,state,applied_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(app_id,tid,data.process_id,candidate_id,number,"applied",now,now));conn.execute("UPDATE admission_leads SET person_id=?,converted_candidate_id=?,state='converted',updated_at=? WHERE tenant_id=? AND id=?",(person_id,candidate_id,now,tid,lead_id));_candidate_event(conn,tid,candidate_id,"lead_conversion",user.id,{"lead_id":lead_id,"application_id":app_id});add_audit(conn,tenant_id=tid,actor_id=user.id,action="convert",aggregate_type="admission_lead",aggregate_id=lead_id,correlation_id=request.state.correlation_id,after={"candidate_id":candidate_id,"application_id":app_id});add_outbox(conn,tenant_id=tid,event_type="AdmissionLeadConverted",aggregate_type="admission_application",aggregate_id=app_id,payload={"lead_id":lead_id,"candidate_id":candidate_id},correlation_id=request.state.correlation_id)
    return {"lead_id":lead_id,"candidate_id":candidate_id,"application_id":app_id,"application_number":number,"state":"applied","replayed":False}

@router.get("/admissions/processes/{process_id}/applications",operation_id="list_admission_applications")
def list_applications(process_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);return {"items":request.state.store.fetch_all("SELECT aa.*,p.full_name,p.email,c.score AS candidate_score,c.rank_position AS candidate_rank FROM admission_applications aa JOIN admission_candidates c ON c.id=aa.candidate_id JOIN people p ON p.id=c.person_id WHERE aa.tenant_id=? AND aa.process_id=? ORDER BY COALESCE(aa.rank_position,999999),aa.applied_at",(tenant(user),process_id))}
@router.post("/admissions/applications/{application_id}/results",operation_id="record_admission_assessment_result")
def record_result(application_id:str,data:ResultInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);app=request.state.store.fetch_one("SELECT aa.*,ap.state AS process_state FROM admission_applications aa JOIN admission_processes ap ON ap.id=aa.process_id WHERE aa.tenant_id=? AND aa.id=?",(tid,application_id));assessment=request.state.store.fetch_one("SELECT * FROM admission_assessments WHERE tenant_id=? AND id=?",(tid,data.assessment_id))
    if not app:raise DomainError("ADMISSION_APPLICATION_NOT_FOUND","Inscrição não localizada.",404)
    if app["process_state"] not in {"applications_open","applications_closed","ranking"}:raise DomainError("ADMISSION_PROCESS_STATE_INVALID","Resultados só podem ser lançados durante avaliação/classificação do processo.",409)
    if not assessment or assessment["process_id"]!=app["process_id"]:raise DomainError("ADMISSION_ASSESSMENT_NOT_FOUND","Avaliação não pertence ao processo da inscrição.",404)
    if Decimal(str(data.score))>Decimal(str(assessment["max_score"])):raise DomainError("ASSESSMENT_SCORE_EXCEEDED","Nota excede o máximo da avaliação.",422)
    now=iso_now();existing=request.state.store.fetch_one("SELECT * FROM admission_assessment_results WHERE tenant_id=? AND application_id=? AND assessment_id=?",(tid,application_id,data.assessment_id))
    with request.state.store.transaction() as conn:
        if existing:version=int(existing["version"])+1;conn.execute("UPDATE admission_assessment_results SET score=?,outcome=?,notes=?,version=?,created_by=?,updated_at=? WHERE tenant_id=? AND id=?",(str(data.score),data.outcome,data.notes,version,user.id,now,tid,existing["id"]));rid=existing["id"]
        else:version=1;rid=uuid7();conn.execute("INSERT INTO admission_assessment_results(id,tenant_id,application_id,assessment_id,score,outcome,notes,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,application_id,data.assessment_id,str(data.score),data.outcome,data.notes,version,user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="score",aggregate_type="admission_application",aggregate_id=application_id,correlation_id=request.state.correlation_id,after={"assessment_id":data.assessment_id,"score":str(data.score),"version":version})
    return {"id":rid,"application_id":application_id,"assessment_id":data.assessment_id,"score":str(data.score),"version":version}

@router.post("/admissions/processes/{process_id}/ranking",operation_id="calculate_admission_ranking")
def calculate_ranking(process_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);process=request.state.store.fetch_one("SELECT * FROM admission_processes WHERE tenant_id=? AND id=?",(tid,process_id))
    if not process:raise DomainError("ADMISSION_PROCESS_NOT_FOUND","Processo seletivo não localizado.",404)
    _require_process_state(process,"ranking")
    assessments=request.state.store.fetch_all("SELECT * FROM admission_assessments WHERE tenant_id=? AND process_id=? AND state='active'",(tid,process_id))
    if not assessments:raise DomainError("ADMISSION_ASSESSMENTS_REQUIRED","Processo seletivo não possui avaliações ativas.",409)
    apps=request.state.store.fetch_all("SELECT * FROM admission_applications WHERE tenant_id=? AND process_id=? AND state NOT IN ('rejected','cancelled')",(tid,process_id));scores=[]
    total_weight=sum(Decimal(str(a["weight"])) for a in assessments)
    for app in apps:
        results={r["assessment_id"]:r for r in request.state.store.fetch_all("SELECT * FROM admission_assessment_results WHERE tenant_id=? AND application_id=?",(tid,app["id"]))}
        complete=all(a["id"] in results for a in assessments)
        if not complete:continue
        weighted=sum((Decimal(str(results[a["id"]]["score"]))/Decimal(str(a["max_score"])))*Decimal(str(a["weight"])) for a in assessments)
        score=(weighted/total_weight*Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP);scores.append((score,app))
    scores.sort(key=lambda x:(-x[0],x[1]["applied_at"],x[1]["id"]));now=iso_now();items=[]
    with request.state.store.transaction() as conn:
        for pos,(score,app) in enumerate(scores,1):conn.execute("UPDATE admission_applications SET final_score=?,rank_position=?,state=CASE WHEN state IN ('applied','under_review') THEN 'evaluated' ELSE state END,updated_at=? WHERE tenant_id=? AND id=?",(str(score),pos,now,tid,app["id"]));conn.execute("UPDATE admission_candidates SET score=?,rank_position=?,updated_at=? WHERE tenant_id=? AND id=?",(str(score),pos,now,tid,app["candidate_id"]));items.append({"application_id":app["id"],"candidate_id":app["candidate_id"],"score":str(score),"rank_position":pos})
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="rank",aggregate_type="admission_process",aggregate_id=process_id,correlation_id=request.state.correlation_id,after={"ranked":len(items)})
    return {"process_id":process_id,"ranked":len(items),"items":items}

@router.post("/admissions/applications/{application_id}/state",operation_id="transition_admission_application")
def application_state(application_id:str,data:ApplicationStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);app=request.state.store.fetch_one("SELECT aa.*,ap.seats,ap.state AS process_state FROM admission_applications aa JOIN admission_processes ap ON ap.id=aa.process_id WHERE aa.tenant_id=? AND aa.id=?",(tid,application_id))
    if not app:raise DomainError("ADMISSION_APPLICATION_NOT_FOUND","Inscrição não localizada.",404)
    allowed={"applied":{"under_review","cancelled"},"under_review":{"waitlisted","selected","rejected","cancelled"},"evaluated":{"waitlisted","selected","rejected","cancelled"},"waitlisted":{"selected","rejected","cancelled"}}
    if data.state not in allowed.get(app["state"],set()):raise DomainError("INVALID_STATE_TRANSITION","Transição da inscrição não permitida.",409)
    if data.state=="under_review" and app["process_state"]!="applications_open":raise DomainError("ADMISSION_PROCESS_STATE_INVALID","Revisão individual exige processo com inscrições abertas.",409)
    if data.state in {"waitlisted","selected","rejected"} and app["process_state"]!="ranking":raise DomainError("ADMISSION_PROCESS_STATE_INVALID","Classificação final exige processo no estado ranking.",409)
    if data.state=="selected" and app.get("seats"):
        selected=int(request.state.store.scalar("SELECT COUNT(*) AS n FROM admission_applications WHERE tenant_id=? AND process_id=? AND state='selected' AND id<>?",(tid,app["process_id"],application_id)) or 0)
        if selected>=int(app["seats"]):raise DomainError("ADMISSION_SEATS_EXCEEDED","Número de selecionados excede as vagas do processo.",409)
    now=iso_now();selected_at=now if data.state=="selected" else None;rejected_at=now if data.state=="rejected" else None
    with request.state.store.transaction() as conn:conn.execute("UPDATE admission_applications SET state=?,selected_at=COALESCE(?,selected_at),rejected_at=COALESCE(?,rejected_at),updated_at=? WHERE tenant_id=? AND id=?",(data.state,selected_at,rejected_at,now,tid,application_id));candidate_state={"selected":"selected","waitlisted":"waitlisted","rejected":"rejected","cancelled":"cancelled"}.get(data.state);conn.execute("UPDATE admission_candidates SET state=?,updated_at=? WHERE tenant_id=? AND id=?",(candidate_state,now,tid,app["candidate_id"])) if candidate_state else None;_candidate_event(conn,tid,app["candidate_id"],"application_state",user.id,{"application_id":application_id,"from":app["state"],"to":data.state,"reason":data.reason});add_audit(conn,tenant_id=tid,actor_id=user.id,action="transition",aggregate_type="admission_application",aggregate_id=application_id,correlation_id=request.state.correlation_id,before={"state":app["state"]},after={"state":data.state},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="AdmissionApplicationStateChanged",aggregate_type="admission_application",aggregate_id=application_id,payload={"candidate_id":app["candidate_id"],"state":data.state},correlation_id=request.state.correlation_id)
    return {"id":application_id,"state":data.state}

@router.post("/admissions/applications/{application_id}/reserve",status_code=201,operation_id="reserve_admission_vacancy")
def reserve_vacancy(application_id:str,data:ReservationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);app=request.state.store.fetch_one("SELECT aa.*,ap.program_id,ap.academic_year_id FROM admission_applications aa JOIN admission_processes ap ON ap.id=aa.process_id WHERE aa.tenant_id=? AND aa.id=?",(tid,application_id))
    if not app:raise DomainError("ADMISSION_APPLICATION_NOT_FOUND","Inscrição não localizada.",404)
    if app["state"]!="selected":raise DomainError("ADMISSION_APPLICATION_NOT_SELECTED","Somente candidato selecionado pode reservar vaga.",409)
    if data.expires_at<=datetime.now(UTC):raise DomainError("RESERVATION_EXPIRY_INVALID","Expiração da reserva deve estar no futuro.",422)
    group=request.state.store.fetch_one("SELECT * FROM class_groups WHERE tenant_id=? AND id=? AND program_id=? AND academic_year_id=? AND state='active'",(tid,data.class_group_id,app["program_id"],app["academic_year_id"]))
    if not group:raise DomainError("CLASS_GROUP_CONTEXT_MISMATCH","Turma não pertence ao processo seletivo.",409)
    existing=request.state.store.fetch_one("SELECT * FROM admission_vacancy_reservations WHERE tenant_id=? AND application_id=? AND state='reserved' AND expires_at>? ORDER BY created_at DESC LIMIT 1",(tid,application_id,iso_now()))
    if existing:return {**existing,"replayed":True}
    occupied=int(request.state.store.scalar("SELECT COUNT(*) AS n FROM enrollments WHERE tenant_id=? AND class_group_id=? AND state IN ('active','reserved')",(tid,data.class_group_id)) or 0);reserved=int(request.state.store.scalar("SELECT COUNT(*) AS n FROM admission_vacancy_reservations WHERE tenant_id=? AND class_group_id=? AND state='reserved' AND expires_at>?",(tid,data.class_group_id,iso_now())) or 0)
    if group.get("capacity") and occupied+reserved>=int(group["capacity"]):raise DomainError("CLASS_CAPACITY_EXCEEDED","Turma sem vagas disponíveis para nova reserva.",409)
    rid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO admission_vacancy_reservations(id,tenant_id,application_id,candidate_id,class_group_id,expires_at,state,reason,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,application_id,app["candidate_id"],data.class_group_id,data.expires_at.isoformat(),"reserved",data.reason,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="reserve",aggregate_type="admission_vacancy",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"application_id":application_id,"class_group_id":data.class_group_id,"expires_at":data.expires_at.isoformat()});add_outbox(conn,tenant_id=tid,event_type="AdmissionVacancyReserved",aggregate_type="admission_vacancy",aggregate_id=rid,payload={"candidate_id":app["candidate_id"],"class_group_id":data.class_group_id,"expires_at":data.expires_at.isoformat()},correlation_id=request.state.correlation_id)
    return {"id":rid,"application_id":application_id,"class_group_id":data.class_group_id,"expires_at":data.expires_at.isoformat(),"state":"reserved","replayed":False}

@router.get("/admissions/reservations",operation_id="list_admission_vacancy_reservations")
def list_reservations(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);return {"items":request.state.store.fetch_all("SELECT avr.*,p.full_name,cg.name AS class_group_name FROM admission_vacancy_reservations avr JOIN admission_candidates ac ON ac.id=avr.candidate_id JOIN people p ON p.id=ac.person_id JOIN class_groups cg ON cg.id=avr.class_group_id WHERE avr.tenant_id=? ORDER BY avr.created_at DESC",(tenant(user),))}
