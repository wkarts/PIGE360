from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.modules.operations.common import ADMIN_ROLES, tenant
from app.modules.portals.access import guardian_for_user
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["compliance-lgpd"])
COMPLIANCE_ROLES=ADMIN_ROLES|{"auditor","support"}
REQUEST_TYPES={"access","export","rectification","anonymization","restriction","objection"}

class PrivacyNoticeInput(BaseModel):
    code:str=Field(min_length=2,max_length=100);title:str=Field(min_length=3,max_length=240);content:str=Field(min_length=20,max_length=200000);effective_from:date;effective_until:date|None=None
class PublishInput(BaseModel):reason:str=Field(min_length=3,max_length=2000)
class ProcessingActivityInput(BaseModel):
    code:str=Field(min_length=2,max_length=100);name:str=Field(min_length=3,max_length=240);purpose:str=Field(min_length=3,max_length=4000);legal_basis:str=Field(min_length=2,max_length=120);privacy_notice_code:str|None=None;data_categories:list[str]=Field(default_factory=list);data_subjects:list[str]=Field(default_factory=list);recipients:list[str]=Field(default_factory=list);international_transfer:bool=False;retention_rule:str|None=None;security_measures:list[str]=Field(default_factory=list);owner_department:str|None=None
class ConsentInput(BaseModel):
    subject_person_id:str;granted_by_person_id:str;purpose_code:str=Field(min_length=2,max_length=120);privacy_notice_id:str;channel:Literal["web","mobile","paper","contract","administrative"]="web";evidence:dict[str,Any]=Field(default_factory=dict)
class ConsentRevokeInput(BaseModel):reason:str=Field(min_length=3,max_length=2000)
class DsarInput(BaseModel):
    subject_person_id:str;request_type:Literal["access","export","rectification","anonymization","restriction","objection"];description:str|None=Field(default=None,max_length=8000);priority:Literal["normal","urgent"]="normal"
class DsarStateInput(BaseModel):
    state:Literal["under_review","approved","rejected","fulfilled","cancelled"];reason:str=Field(min_length=3,max_length=4000);assigned_to:str|None=None
class RetentionInput(BaseModel):
    data_category:str=Field(min_length=2,max_length=120);purpose_code:str|None=None;retention_days:int=Field(ge=1,le=36500);disposition:Literal["archive","anonymize","delete"];legal_basis:str=Field(min_length=2,max_length=240);starts_on:date
class LegalHoldInput(BaseModel):
    person_id:str|None=None;aggregate_type:str|None=None;aggregate_id:str|None=None;reason:str=Field(min_length=3,max_length=4000);ends_at:datetime|None=None
    @model_validator(mode="after")
    def scope(self):
        if not self.person_id and not (self.aggregate_type and self.aggregate_id):raise ValueError("Informe person_id ou aggregate_type + aggregate_id")
        return self


def require_compliance(user:CurrentUser)->str:
    tid=tenant(user)
    if not set(user.roles)&COMPLIANCE_ROLES:raise DomainError("PERMISSION_DENIED","Permissão de compliance/LGPD insuficiente.",403)
    return tid

def person_row(request:Request,tid:str,person_id:str)->dict[str,Any]:
    row=request.state.store.fetch_one("SELECT * FROM people WHERE tenant_id=? AND id=?",(tid,person_id))
    if not row:raise DomainError("PERSON_NOT_FOUND","Titular não localizado.",404)
    return row

def can_access_person(request:Request,user:CurrentUser,person_id:str)->bool:
    tid=tenant(user)
    if set(user.roles)&COMPLIANCE_ROLES:return bool(request.state.store.fetch_one("SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,person_id)))
    if user.person_id==person_id:return True
    if "guardian" in user.roles:
        guardian=guardian_for_user(request,user)
        return bool(request.state.store.fetch_one("SELECT 1 FROM guardian_students gs JOIN students s ON s.id=gs.student_id WHERE gs.tenant_id=? AND gs.guardian_id=? AND s.person_id=?",(tid,guardian["id"],person_id)))
    return False

def assert_person_access(request:Request,user:CurrentUser,person_id:str)->None:
    person_row(request,tenant(user),person_id)
    if not can_access_person(request,user,person_id):raise DomainError("DATA_SUBJECT_ACCESS_DENIED","Titular fora do escopo desta conta.",403)

def _protocol(request:Request,tid:str)->str:
    # Protocolo legível e concorrência-segura; não depende de COUNT/MAX sujeito a corrida.
    token=uuid7().replace("-","")[-12:].upper()
    return f"LGPD-{datetime.now(UTC).year}-{token}"

def _event(conn,tid:str,request_id:str,event_type:str,actor_id:str,from_state:str|None,to_state:str|None,details:dict[str,Any]|None=None)->None:
    conn.execute("INSERT INTO data_subject_request_events(id,tenant_id,request_id,event_type,from_state,to_state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,request_id,event_type,from_state,to_state,json.dumps(details or {},ensure_ascii=False),actor_id,iso_now()))

def _snapshot(request:Request,tid:str,person_id:str)->dict[str,Any]:
    store=request.state.store;person=person_row(request,tid,person_id)
    students=store.fetch_all("SELECT * FROM students WHERE tenant_id=? AND person_id=?",(tid,person_id));student_ids=[x["id"] for x in students]
    guardians=store.fetch_all("SELECT * FROM guardians WHERE tenant_id=? AND person_id=?",(tid,person_id));guardian_ids=[x["id"] for x in guardians]
    employees=store.fetch_all("SELECT * FROM employees WHERE tenant_id=? AND person_id=?",(tid,person_id));employee_ids=[x["id"] for x in employees]
    def rows(sql:str,params:list[Any]):return store.fetch_all(sql,params)
    enrollments=[];attendance=[];financial=[]
    health=rows("SELECT id,record_type,summary,details_json,sensitivity,valid_from,valid_until,state,created_at,updated_at FROM health_records WHERE tenant_id=? AND person_id=?",[tid,person_id])
    for sid in student_ids:
        enrollments.extend(rows("SELECT id,enrollment_number,institution_id,unit_id,program_id,curriculum_id,academic_year_id,class_group_id,state,enrolled_on,ended_on,created_at,updated_at FROM enrollments WHERE tenant_id=? AND student_id=?",[tid,sid]))
        attendance.extend(rows("SELECT class_session_id,status_code,minutes_present,observation,version,updated_at FROM attendance_records WHERE tenant_id=? AND student_id=?",[tid,sid]))
    enrollment_ids=[x["id"] for x in enrollments]
    for eid in enrollment_ids:
        financial.extend(rows("SELECT id,description,total_amount,currency,state,created_at,updated_at FROM financial_contracts WHERE tenant_id=? AND enrollment_id=?",[tid,eid]))
    relationships=[]
    for gid in guardian_ids:relationships.extend(rows("SELECT student_id,relationship,is_legal,is_financial,pickup_authorized,created_at,updated_at FROM guardian_students WHERE tenant_id=? AND guardian_id=?",[tid,gid]))
    return {"schema":"pige360-lgpd-export-v1","generated_at":iso_now(),"subject":{"person":person,"students":students,"guardians":guardians,"employees":employees},"academic":{"enrollments":enrollments,"attendance":attendance},"family_relationships":relationships,"financial":{"contracts":financial},"health":{"records":health},"consents":rows("SELECT id,purpose_code,legal_basis,privacy_notice_id,channel,state,granted_at,revoked_at,revocation_reason FROM consent_records WHERE tenant_id=? AND subject_person_id=? ORDER BY granted_at",[tid,person_id]),"requests":rows("SELECT id,protocol,request_type,state,created_at,fulfilled_at FROM data_subject_requests WHERE tenant_id=? AND subject_person_id=? ORDER BY created_at",[tid,person_id])}

@router.get("/compliance/privacy-notices",operation_id="list_privacy_notices")
def list_notices(request:Request,code:str|None=None,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);sql="SELECT id,code,title,version,effective_from,effective_until,state,sha256,published_at,created_at,updated_at FROM privacy_notices WHERE tenant_id=?";params:list[Any]=[tid]
    if code:sql+=" AND code=?";params.append(code)
    if not set(user.roles)&COMPLIANCE_ROLES:sql+=" AND state='published'"
    return {"items":request.state.store.fetch_all(sql+" ORDER BY code,version DESC",params)}

@router.get("/compliance/privacy-notices/{notice_id}",operation_id="get_privacy_notice")
def get_notice(notice_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);row=request.state.store.fetch_one("SELECT id,code,title,version,content,effective_from,effective_until,state,sha256,published_at,created_at,updated_at FROM privacy_notices WHERE tenant_id=? AND id=?",(tid,notice_id))
    if not row:raise DomainError("PRIVACY_NOTICE_NOT_FOUND","Aviso de privacidade não localizado.",404)
    if row["state"]!="published" and not set(user.roles)&COMPLIANCE_ROLES:raise DomainError("PRIVACY_NOTICE_NOT_FOUND","Aviso de privacidade não localizado.",404)
    return row

@router.post("/compliance/privacy-notices",status_code=201,operation_id="create_privacy_notice")
def create_notice(data:PrivacyNoticeInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);version=int(request.state.store.scalar("SELECT COALESCE(MAX(version),0) AS n FROM privacy_notices WHERE tenant_id=? AND code=?",(tid,data.code)) or 0)+1;now=iso_now();digest=hashlib.sha256(data.content.encode()).hexdigest();rid=uuid7();result={"id":rid,**data.model_dump(mode="json"),"version":version,"state":"draft","sha256":digest}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO privacy_notices(id,tenant_id,code,title,version,content,effective_from,effective_until,state,sha256,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.title,version,data.content,str(data.effective_from),str(data.effective_until) if data.effective_until else None,"draft",digest,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="privacy_notice",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/compliance/privacy-notices/{notice_id}/publish",operation_id="publish_privacy_notice")
def publish_notice(notice_id:str,data:PublishInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);row=request.state.store.fetch_one("SELECT * FROM privacy_notices WHERE tenant_id=? AND id=?",(tid,notice_id))
    if not row:raise DomainError("PRIVACY_NOTICE_NOT_FOUND","Aviso de privacidade não localizado.",404)
    if row["state"]!="draft":raise DomainError("INVALID_STATE_TRANSITION","Somente aviso em rascunho pode ser publicado.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE privacy_notices SET state='superseded',updated_at=? WHERE tenant_id=? AND code=? AND state='published'",(now,tid,row["code"]));conn.execute("UPDATE privacy_notices SET state='published',published_by=?,published_at=?,updated_at=? WHERE id=?",(user.id,now,now,notice_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="privacy_notice",aggregate_id=notice_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":"published"},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="PrivacyNoticePublished",aggregate_type="privacy_notice",aggregate_id=notice_id,payload={"code":row["code"],"version":row["version"]},correlation_id=request.state.correlation_id)
    return {"id":notice_id,"state":"published","version":row["version"],"sha256":row["sha256"]}

@router.get("/compliance/processing-activities",operation_id="list_processing_activities")
def list_processing(request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);items=request.state.store.fetch_all("SELECT * FROM processing_activities WHERE tenant_id=? ORDER BY code,version DESC",(tid,))
    for x in items:
        for src,dst in (("data_categories_json","data_categories"),("data_subjects_json","data_subjects"),("recipients_json","recipients"),("security_measures_json","security_measures")):x[dst]=json.loads(x.pop(src) or "[]")
    return {"items":items}

@router.post("/compliance/processing-activities",status_code=201,operation_id="create_processing_activity")
def create_processing(data:ProcessingActivityInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);version=int(request.state.store.scalar("SELECT COALESCE(MAX(version),0) AS n FROM processing_activities WHERE tenant_id=? AND code=?",(tid,data.code)) or 0)+1;rid=uuid7();now=iso_now();result={"id":rid,**data.model_dump(mode="json"),"version":version,"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO processing_activities(id,tenant_id,code,name,purpose,legal_basis,privacy_notice_code,data_categories_json,data_subjects_json,recipients_json,international_transfer,retention_rule,security_measures_json,owner_department,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.name,data.purpose,data.legal_basis,data.privacy_notice_code,json.dumps(data.data_categories),json.dumps(data.data_subjects),json.dumps(data.recipients),1 if data.international_transfer else 0,data.retention_rule,json.dumps(data.security_measures),data.owner_department,"active",version,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="processing_activity",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.get("/compliance/consent-purposes",operation_id="list_consent_purposes")
def consent_purposes(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);rows=request.state.store.fetch_all(
        "SELECT pa.code,pa.name,pa.purpose,pa.privacy_notice_code,pn.id AS privacy_notice_id,pn.title AS privacy_notice_title,pn.version AS privacy_notice_version,pn.sha256 AS privacy_notice_sha256 "
        "FROM processing_activities pa LEFT JOIN privacy_notices pn ON pn.tenant_id=pa.tenant_id AND pn.code=pa.privacy_notice_code AND pn.state='published' "
        "WHERE pa.tenant_id=? AND pa.state='active' AND lower(pa.legal_basis)='consent' ORDER BY pa.code,pa.version DESC",(tid,))
    seen=set();items=[]
    for row in rows:
        if row["code"] in seen:continue
        seen.add(row["code"]);items.append(row)
    return {"items":items}


@router.get("/compliance/persons/{person_id}/consents",operation_id="list_person_consents")
def list_consents(person_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    assert_person_access(request,user,person_id);tid=tenant(user);return {"items":request.state.store.fetch_all("SELECT id,subject_person_id,granted_by_person_id,purpose_code,legal_basis,privacy_notice_id,channel,state,granted_at,revoked_at,revocation_reason FROM consent_records WHERE tenant_id=? AND subject_person_id=? ORDER BY granted_at DESC",(tid,person_id))}

@router.post("/compliance/consents",status_code=201,operation_id="grant_consent")
def grant_consent(data:ConsentInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);subject=person_row(request,tid,data.subject_person_id);person_row(request,tid,data.granted_by_person_id)
    purpose=request.state.store.fetch_one(
        "SELECT code,privacy_notice_code,legal_basis,version FROM processing_activities WHERE tenant_id=? AND code=? AND state='active' AND lower(legal_basis)='consent' ORDER BY version DESC LIMIT 1",
        (tid,data.purpose_code),
    )
    if not purpose:raise DomainError("CONSENT_PURPOSE_NOT_AVAILABLE","Finalidade não está cadastrada como tratamento ativo baseado em consentimento.",409)
    notice=request.state.store.fetch_one("SELECT id,code,state,effective_from,effective_until FROM privacy_notices WHERE tenant_id=? AND id=?",(tid,data.privacy_notice_id))
    if not notice or notice["state"]!="published":raise DomainError("PRIVACY_NOTICE_NOT_PUBLISHED","Consentimento exige aviso de privacidade publicado.",409)
    if not purpose.get("privacy_notice_code") or notice["code"]!=purpose["privacy_notice_code"]:raise DomainError("CONSENT_NOTICE_MISMATCH","Aviso de privacidade não corresponde à finalidade de tratamento selecionada.",409)
    today=date.today().isoformat()
    if notice["effective_from"]>today or (notice["effective_until"] and notice["effective_until"]<today):raise DomainError("PRIVACY_NOTICE_NOT_EFFECTIVE","Aviso de privacidade não está vigente na data do consentimento.",409)
    if not set(user.roles)&COMPLIANCE_ROLES:
        if user.person_id!=data.granted_by_person_id:raise DomainError("CONSENT_GRANTOR_MISMATCH","A conta deve corresponder à pessoa que concede o consentimento.",403)
        if data.subject_person_id==data.granted_by_person_id:
            if "student" in user.roles and not subject.get("birth_date"):
                raise DomainError("CONSENT_AGE_UNVERIFIED","Não foi possível comprovar a maioridade do aluno para consentimento próprio.",409)
            if subject.get("birth_date"):
                born=date.fromisoformat(str(subject["birth_date"]));today_date=date.today();age=today_date.year-born.year-((today_date.month,today_date.day)<(born.month,born.day))
                if age<18:raise DomainError("MINOR_REQUIRES_LEGAL_GUARDIAN","Titular menor de idade exige consentimento do responsável legal vinculado.",403)
        if data.subject_person_id!=data.granted_by_person_id:
            if "guardian" not in user.roles:raise DomainError("CONSENT_REPRESENTATIVE_REQUIRED","Consentimento por terceiro exige responsável legal vinculado.",403)
            guardian=guardian_for_user(request,user);linked=request.state.store.fetch_one("SELECT 1 FROM guardian_students gs JOIN students s ON s.id=gs.student_id WHERE gs.tenant_id=? AND gs.guardian_id=? AND gs.is_legal=1 AND s.person_id=?",(tid,guardian["id"],data.subject_person_id))
            if not linked:raise DomainError("LEGAL_GUARDIAN_REQUIRED","Responsável não possui vínculo legal com o titular.",403)
    now=iso_now();rid=uuid7();evidence={**data.evidence,"actor_user_id":user.id,"correlation_id":request.state.correlation_id,"granted_at":now};result={"id":rid,"subject_person_id":data.subject_person_id,"granted_by_person_id":data.granted_by_person_id,"purpose_code":data.purpose_code,"privacy_notice_id":data.privacy_notice_id,"channel":data.channel,"state":"granted","granted_at":now}
    with request.state.store.transaction() as conn:conn.execute("UPDATE consent_records SET state='superseded',updated_at=? WHERE tenant_id=? AND subject_person_id=? AND purpose_code=? AND state='granted'",(now,tid,data.subject_person_id,data.purpose_code));conn.execute("INSERT INTO consent_records(id,tenant_id,subject_person_id,granted_by_person_id,purpose_code,legal_basis,privacy_notice_id,channel,evidence_json,state,granted_at,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.subject_person_id,data.granted_by_person_id,data.purpose_code,"consent",data.privacy_notice_id,data.channel,json.dumps(evidence,ensure_ascii=False),"granted",now,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="grant",aggregate_type="consent",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="ConsentGranted",aggregate_type="consent",aggregate_id=rid,payload={"subject_person_id":data.subject_person_id,"purpose_code":data.purpose_code},correlation_id=request.state.correlation_id)
    return result

@router.post("/compliance/consents/{consent_id}/revoke",operation_id="revoke_consent")
def revoke_consent(consent_id:str,data:ConsentRevokeInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM consent_records WHERE tenant_id=? AND id=?",(tid,consent_id))
    if not row:raise DomainError("CONSENT_NOT_FOUND","Consentimento não localizado.",404)
    if not (set(user.roles)&COMPLIANCE_ROLES or user.person_id in {row["subject_person_id"],row["granted_by_person_id"]}):raise DomainError("CONSENT_ACCESS_DENIED","Conta não pode revogar este consentimento.",403)
    if row["state"]!="granted":raise DomainError("CONSENT_NOT_ACTIVE","Consentimento não está ativo.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE consent_records SET state='revoked',revoked_at=?,revoked_by=?,revocation_reason=?,updated_at=? WHERE id=?",(now,user.id,data.reason,now,consent_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="revoke",aggregate_type="consent",aggregate_id=consent_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":"revoked","revoked_at":now},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="ConsentRevoked",aggregate_type="consent",aggregate_id=consent_id,payload={"subject_person_id":row["subject_person_id"],"purpose_code":row["purpose_code"]},correlation_id=request.state.correlation_id)
    return {"id":consent_id,"state":"revoked","revoked_at":now}

@router.get("/compliance/data-subject-requests",operation_id="list_data_subject_requests")
def list_dsar(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);sql="SELECT * FROM data_subject_requests WHERE tenant_id=?";params:list[Any]=[tid]
    if not set(user.roles)&COMPLIANCE_ROLES:
        if not user.person_id:raise DomainError("PERSON_LINK_REQUIRED","Conta sem vínculo de pessoa.",403)
        sql+=" AND requester_person_id=?";params.append(user.person_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY created_at DESC",params)}

@router.post("/compliance/data-subject-requests",status_code=201,operation_id="create_data_subject_request")
def create_dsar(data:DsarInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);assert_person_access(request,user,data.subject_person_id)
    requester=user.person_id
    if not requester:
        if set(user.roles)&COMPLIANCE_ROLES:requester=data.subject_person_id
        else:raise DomainError("PERSON_LINK_REQUIRED","Conta sem vínculo de pessoa.",403)
    now_dt=datetime.now(UTC);now=now_dt.isoformat();rid=uuid7();protocol=_protocol(request,tid);due=(now_dt+timedelta(days=7 if data.priority=="urgent" else 15)).isoformat();result={"id":rid,"protocol":protocol,"subject_person_id":data.subject_person_id,"requester_person_id":requester,"request_type":data.request_type,"state":"submitted","priority":data.priority,"due_at":due}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO data_subject_requests(id,tenant_id,protocol,subject_person_id,requester_person_id,request_type,description,state,priority,due_at,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,protocol,data.subject_person_id,requester,data.request_type,data.description,"submitted",data.priority,due,user.id,now,now));_event(conn,tid,rid,"submitted",user.id,None,"submitted",{"request_type":data.request_type});add_audit(conn,tenant_id=tid,actor_id=user.id,action="submit",aggregate_type="data_subject_request",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="DataSubjectRequestSubmitted",aggregate_type="data_subject_request",aggregate_id=rid,payload={"protocol":protocol,"request_type":data.request_type},correlation_id=request.state.correlation_id)
    return result

@router.post("/compliance/data-subject-requests/{request_id}/state",operation_id="transition_data_subject_request")
def transition_dsar(request_id:str,data:DsarStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);row=request.state.store.fetch_one("SELECT * FROM data_subject_requests WHERE tenant_id=? AND id=?",(tid,request_id))
    if not row:raise DomainError("DATA_SUBJECT_REQUEST_NOT_FOUND","Solicitação do titular não localizada.",404)
    allowed={"submitted":{"under_review","cancelled"},"under_review":{"approved","rejected","cancelled"},"approved":{"fulfilled","rejected"},"fulfilled":set(),"rejected":set(),"cancelled":set()}
    if data.state not in allowed.get(row["state"],set()):raise DomainError("INVALID_STATE_TRANSITION",f"Transição LGPD {row['state']} → {data.state} não permitida.",409)
    now=iso_now();fulfilled=now if data.state=="fulfilled" else row["fulfilled_at"]
    with request.state.store.transaction() as conn:conn.execute("UPDATE data_subject_requests SET state=?,decision_reason=?,assigned_to=?,fulfilled_at=?,updated_at=? WHERE id=?",(data.state,data.reason,data.assigned_to,fulfilled,now,request_id));_event(conn,tid,request_id,"state_changed",user.id,row["state"],data.state,{"reason":data.reason,"assigned_to":data.assigned_to});add_audit(conn,tenant_id=tid,actor_id=user.id,action=data.state,aggregate_type="data_subject_request",aggregate_id=request_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":data.state},reason=data.reason)
    return {"id":request_id,"state":data.state,"fulfilled_at":fulfilled}

@router.post("/compliance/data-subject-requests/{request_id}/export",operation_id="generate_data_subject_export")
def export_dsar(request_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);row=request.state.store.fetch_one("SELECT * FROM data_subject_requests WHERE tenant_id=? AND id=?",(tid,request_id))
    if not row:raise DomainError("DATA_SUBJECT_REQUEST_NOT_FOUND","Solicitação do titular não localizada.",404)
    if row["request_type"] not in {"access","export"}:raise DomainError("DATA_SUBJECT_EXPORT_NOT_APPLICABLE","Tipo de solicitação não permite exportação.",409)
    if row["state"] not in {"under_review","approved"}:raise DomainError("DATA_SUBJECT_REQUEST_STATE_INVALID","Solicitação deve estar em análise ou aprovada para exportação.",409)
    snapshot=_snapshot(request,tid,row["subject_person_id"]);content=json.dumps(snapshot,ensure_ascii=False,indent=2,sort_keys=True,default=str).encode();key=f"compliance/lgpd/{row['subject_person_id']}/{request_id}/data-export.json";stored=request.app.state.data_router.object_storage(tid).put_bytes(key,content,content_type="application/json");now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE data_subject_requests SET export_storage_key=?,export_sha256=?,export_bytes=?,exported_at=?,updated_at=? WHERE id=?",(stored.key,stored.sha256,stored.bytes,now,now,request_id));_event(conn,tid,request_id,"export_generated",user.id,row["state"],row["state"],{"sha256":stored.sha256,"bytes":stored.bytes});add_audit(conn,tenant_id=tid,actor_id=user.id,action="export",aggregate_type="data_subject_request",aggregate_id=request_id,correlation_id=request.state.correlation_id,after={"sha256":stored.sha256,"bytes":stored.bytes})
    return {"id":request_id,"sha256":stored.sha256,"bytes":stored.bytes,"generated_at":now}

@router.get("/compliance/data-subject-requests/{request_id}/export",operation_id="download_data_subject_export")
def download_dsar(request_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM data_subject_requests WHERE tenant_id=? AND id=?",(tid,request_id))
    if not row:raise DomainError("DATA_SUBJECT_REQUEST_NOT_FOUND","Solicitação do titular não localizada.",404)
    if not (set(user.roles)&COMPLIANCE_ROLES or user.person_id in {row["subject_person_id"],row["requester_person_id"]}):raise DomainError("DATA_SUBJECT_ACCESS_DENIED","Conta não pode baixar esta exportação.",403)
    if not row["export_storage_key"]:raise DomainError("DATA_SUBJECT_EXPORT_NOT_READY","Exportação ainda não foi gerada.",409)
    content=request.app.state.data_router.object_storage(tid).get_bytes(row["export_storage_key"])
    if hashlib.sha256(content).hexdigest()!=row["export_sha256"]:raise DomainError("DATA_SUBJECT_EXPORT_INTEGRITY_ERROR","Hash da exportação não confere.",500)
    return Response(content,media_type="application/json",headers={"Content-Disposition":f'attachment; filename="{row["protocol"]}.json"',"X-Content-SHA256":row["export_sha256"]})

@router.get("/compliance/retention-policies",operation_id="list_retention_policies")
def list_retention(request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);return {"items":request.state.store.fetch_all("SELECT * FROM retention_policies WHERE tenant_id=? ORDER BY data_category,version DESC",(tid,))}

@router.post("/compliance/retention-policies",status_code=201,operation_id="create_retention_policy")
def create_retention(data:RetentionInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);version=int(request.state.store.scalar("SELECT COALESCE(MAX(version),0) AS n FROM retention_policies WHERE tenant_id=? AND data_category=? AND COALESCE(purpose_code,'')=COALESCE(?, '')",(tid,data.data_category,data.purpose_code)) or 0)+1;rid=uuid7();now=iso_now();result={"id":rid,**data.model_dump(mode="json"),"version":version,"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("UPDATE retention_policies SET state='superseded',updated_at=? WHERE tenant_id=? AND data_category=? AND COALESCE(purpose_code,'')=COALESCE(?, '') AND state='active'",(now,tid,data.data_category,data.purpose_code));conn.execute("INSERT INTO retention_policies(id,tenant_id,data_category,purpose_code,retention_days,disposition,legal_basis,starts_on,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.data_category,data.purpose_code,data.retention_days,data.disposition,data.legal_basis,str(data.starts_on),"active",version,user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="retention_policy",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.get("/compliance/legal-holds",operation_id="list_legal_holds")
def list_holds(request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);return {"items":request.state.store.fetch_all("SELECT * FROM legal_holds WHERE tenant_id=? ORDER BY created_at DESC",(tid,))}

@router.post("/compliance/legal-holds",status_code=201,operation_id="create_legal_hold")
def create_hold(data:LegalHoldInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user)
    if data.person_id:person_row(request,tid,data.person_id)
    rid=uuid7();now=iso_now();result={"id":rid,**data.model_dump(mode="json"),"state":"active","starts_at":now}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO legal_holds(id,tenant_id,person_id,aggregate_type,aggregate_id,reason,starts_at,ends_at,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.person_id,data.aggregate_type,data.aggregate_id,data.reason,now,data.ends_at.isoformat() if data.ends_at else None,"active",user.id,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="legal_hold",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/compliance/legal-holds/{hold_id}/release",operation_id="release_legal_hold")
def release_hold(hold_id:str,data:PublishInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);row=request.state.store.fetch_one("SELECT * FROM legal_holds WHERE tenant_id=? AND id=?",(tid,hold_id))
    if not row:raise DomainError("LEGAL_HOLD_NOT_FOUND","Legal hold não localizado.",404)
    if row["state"]!="active":raise DomainError("LEGAL_HOLD_NOT_ACTIVE","Legal hold não está ativo.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:conn.execute("UPDATE legal_holds SET state='released',released_by=?,released_at=?,updated_at=? WHERE id=?",(user.id,now,now,hold_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="release",aggregate_type="legal_hold",aggregate_id=hold_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":"released"},reason=data.reason)
    return {"id":hold_id,"state":"released","released_at":now}

@router.post("/compliance/data-subject-requests/{request_id}/anonymize",operation_id="execute_data_subject_anonymization")
def anonymize(request_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);row=request.state.store.fetch_one("SELECT * FROM data_subject_requests WHERE tenant_id=? AND id=?",(tid,request_id))
    if not row:raise DomainError("DATA_SUBJECT_REQUEST_NOT_FOUND","Solicitação do titular não localizada.",404)
    if row["request_type"]!="anonymization" or row["state"]!="approved":raise DomainError("ANONYMIZATION_REQUEST_NOT_APPROVED","Anonimização exige solicitação aprovada específica.",409)
    pid=row["subject_person_id"]
    hold=request.state.store.fetch_one("SELECT id FROM legal_holds WHERE tenant_id=? AND person_id=? AND state='active' AND (ends_at IS NULL OR ends_at>?)",(tid,pid,iso_now()))
    if hold:raise DomainError("LEGAL_HOLD_ACTIVE","Titular possui legal hold ativo; anonimização bloqueada.",409)
    active_enrollment=request.state.store.fetch_one("SELECT e.id FROM enrollments e JOIN students s ON s.id=e.student_id WHERE e.tenant_id=? AND s.person_id=? AND e.state IN ('pre_enrolled','reserved','active','suspended') LIMIT 1",(tid,pid))
    if active_enrollment:raise DomainError("ACTIVE_ACADEMIC_RELATIONSHIP","Há matrícula acadêmica ativa; anonimização bloqueada.",409)
    active_employment=request.state.store.fetch_one("SELECT ec.id FROM employment_contracts ec JOIN employees e ON e.id=ec.employee_id WHERE ec.tenant_id=? AND e.person_id=? AND ec.state='active' LIMIT 1",(tid,pid))
    if active_employment:raise DomainError("ACTIVE_EMPLOYMENT_RELATIONSHIP","Há vínculo trabalhista ativo; anonimização bloqueada.",409)
    person=person_row(request,tid,pid);now=iso_now();alias=f"Titular anonimizado {pid[-8:]}"
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE people SET full_name=?,social_name=NULL,cpf=NULL,birth_date=NULL,email=NULL,phone=NULL,civil_data_json='{}',address_json='{}',emergency_json='{}',state='anonymized',updated_at=? WHERE tenant_id=? AND id=?",(alias,now,tid,pid))
        conn.execute("UPDATE students SET state='archived',updated_at=? WHERE tenant_id=? AND person_id=?",(now,tid,pid));conn.execute("UPDATE guardians SET state='archived',updated_at=? WHERE tenant_id=? AND person_id=?",(now,tid,pid));conn.execute("UPDATE employees SET state='archived',updated_at=? WHERE tenant_id=? AND person_id=?",(now,tid,pid))
        conn.execute("UPDATE users SET email=?,active=0,updated_at=? WHERE tenant_id=? AND person_id=?",(f"anonymized-{pid}@invalid.local",now,tid,pid))
        conn.execute("UPDATE data_subject_requests SET state='fulfilled',fulfilled_at=?,decision_reason=COALESCE(decision_reason,'')||?,updated_at=? WHERE id=?",(now," | Anonimização executada",now,request_id));_event(conn,tid,request_id,"anonymization_executed",user.id,"approved","fulfilled",{"person_alias":alias});add_audit(conn,tenant_id=tid,actor_id=user.id,action="anonymize",aggregate_type="person",aggregate_id=pid,correlation_id=request.state.correlation_id,before={"state":person["state"]},after={"state":"anonymized","alias":alias},reason="Solicitação LGPD aprovada");add_outbox(conn,tenant_id=tid,event_type="DataSubjectAnonymized",aggregate_type="person",aggregate_id=pid,payload={"request_id":request_id},correlation_id=request.state.correlation_id)
    return {"request_id":request_id,"person_id":pid,"state":"fulfilled","person_state":"anonymized","anonymized_at":now}

@router.get("/compliance/dashboard",operation_id="get_compliance_dashboard")
def dashboard(request:Request,user:CurrentUser=Depends(current_user)):
    tid=require_compliance(user);s=request.state.store.scalar
    return {"open_data_subject_requests":int(s("SELECT COUNT(*) AS n FROM data_subject_requests WHERE tenant_id=? AND state NOT IN ('fulfilled','rejected','cancelled')",(tid,)) or 0),"active_consents":int(s("SELECT COUNT(*) AS n FROM consent_records WHERE tenant_id=? AND state='granted'",(tid,)) or 0),"active_legal_holds":int(s("SELECT COUNT(*) AS n FROM legal_holds WHERE tenant_id=? AND state='active'",(tid,)) or 0),"active_retention_policies":int(s("SELECT COUNT(*) AS n FROM retention_policies WHERE tenant_id=? AND state='active'",(tid,)) or 0),"processing_activities":int(s("SELECT COUNT(*) AS n FROM processing_activities WHERE tenant_id=? AND state='active'",(tid,)) or 0)}
