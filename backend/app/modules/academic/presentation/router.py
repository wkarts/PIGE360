from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from app.modules.portals.access import assert_student_access, student_for_user
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["academic-progress"])
ADMIN={"tenant_owner","institution_director","academic_coordinator","secretary"}
STAFF=ADMIN|{"teacher","assistant_teacher"}

def tid(user:CurrentUser)->str:
    if user.plane!="tenant" or not user.tenant_id:raise DomainError("TENANT_ROUTE_REQUIRED","Rota disponível somente no domínio da instituição.",404)
    return user.tenant_id

def admin(user:CurrentUser)->bool:return bool(set(user.roles)&ADMIN)
def require_staff(user:CurrentUser):
    tenant=tid(user)
    if not set(user.roles)&STAFF:raise DomainError("PERMISSION_DENIED","Permissão acadêmica insuficiente.",403)
    return tenant

def enrollment(request:Request,tenant:str,enrollment_id:str)->dict:
    row=request.state.store.fetch_one("SELECT e.*,p.education_level FROM enrollments e JOIN programs p ON p.id=e.program_id WHERE e.tenant_id=? AND e.id=?",(tenant,enrollment_id))
    if not row:raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
    return row

ADVANCED_EDUCATION_LEVELS={"technical","tecnico","técnico","superior","higher_education","graduacao","graduação","pos_graduacao","pós_graduação","postgraduate"}

def require_advanced_active_enrollment(row:dict[str,Any], *, feature:str)->None:
    if row["state"]!="active":raise DomainError("ACTIVE_ENROLLMENT_REQUIRED",f"{feature} exige matrícula acadêmica ativa.",409)
    level=str(row.get("education_level") or "").lower().strip().replace(" ","_")
    if level not in ADVANCED_EDUCATION_LEVELS:raise DomainError("ADVANCED_EDUCATION_PROGRAM_REQUIRED",f"{feature} é exclusivo de programa técnico ou de ensino superior.",409)

class DailyRecordInput(BaseModel):
    student_id:str;record_date:date;meals:list[dict[str,Any]]=Field(default_factory=list);sleep:dict[str,Any]=Field(default_factory=dict);hygiene:list[dict[str,Any]]=Field(default_factory=list);diaper_changes:list[dict[str,Any]]=Field(default_factory=list);mood:str|None=Field(default=None,max_length=120);development_notes:str|None=Field(default=None,max_length=6000);authorized_photos:list[str]=Field(default_factory=list)
class PickupInput(BaseModel):
    student_id:str;guardian_id:str;released_at:datetime;identity_document_masked:str|None=Field(default=None,max_length=80);notes:str|None=Field(default=None,max_length=2000)
class PrerequisiteInput(BaseModel):component_id:str;prerequisite_component_id:str;minimum_final_score:Decimal|None=Field(default=None,ge=0)
class ComponentCompletionInput(BaseModel):enrollment_id:str;component_id:str;source_type:Literal["grade","equivalence","transfer","credit_recognition"];source_reference_id:str|None=None;final_score:Decimal|None=Field(default=None,ge=0);completed_on:date;reason:str=Field(min_length=3,max_length=2000)
class InternshipInput(BaseModel):
    enrollment_id:str;organization_name:str=Field(min_length=2,max_length=240);supervisor_name:str|None=None;advisor_employee_id:str|None=None;starts_on:date;ends_on:date|None=None;required_hours:Decimal=Field(default=Decimal("0"),ge=0);notes:str|None=None
    @model_validator(mode="after")
    def valid_dates(self):
        if self.ends_on and self.ends_on<self.starts_on:raise ValueError("ends_on deve ser posterior a starts_on")
        return self
class InternshipHoursInput(BaseModel):activity_date:date;hours:Decimal=Field(gt=0,le=24);description:str=Field(min_length=3,max_length=3000)
class InternshipStateInput(BaseModel):state:Literal["approved","in_progress","completed","cancelled"];expected_version:int=Field(ge=1);reason:str=Field(min_length=3,max_length=2000)
class ActivityInput(BaseModel):enrollment_id:str;category:str=Field(min_length=2,max_length=100);title:str=Field(min_length=2,max_length=240);requested_hours:Decimal=Field(gt=0);evidence_document_id:str|None=None
class ActivityDecision(BaseModel):state:Literal["approved","rejected","additional_information_required"];approved_hours:Decimal=Field(default=Decimal("0"),ge=0);notes:str=Field(min_length=3,max_length=2000)
class ThesisInput(BaseModel):enrollment_id:str;title:str=Field(min_length=3,max_length=500);advisor_employee_id:str|None=None;coadvisor_name:str|None=None;abstract:str|None=Field(default=None,max_length=12000);document_id:str|None=None
class ThesisStateInput(BaseModel):state:Literal["approved","in_progress","submitted","defended","passed","rejected","cancelled"];expected_version:int=Field(ge=1);grade:Decimal|None=Field(default=None,ge=0);defense_at:datetime|None=None;reason:str=Field(min_length=3,max_length=2000)

@router.post("/academic/early-childhood/daily-records",status_code=201,operation_id="save_early_childhood_daily_record")
def save_daily(data:DailyRecordInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=require_staff(user);assert_student_access(request,user,data.student_id);enr=request.state.store.fetch_one("SELECT e.*,p.education_level FROM enrollments e JOIN programs p ON p.id=e.program_id WHERE e.tenant_id=? AND e.student_id=? AND e.state='active' ORDER BY e.created_at DESC LIMIT 1",(tenant,data.student_id))
    if not enr:raise DomainError("ACTIVE_ENROLLMENT_REQUIRED","Aluno não possui matrícula ativa.",409)
    level=str(enr["education_level"] or "").lower().replace(" ","_")
    if level not in {"infantil","educacao_infantil","educação_infantil","early_childhood"}:raise DomainError("EARLY_CHILDHOOD_PROGRAM_REQUIRED","Agenda diária é exclusiva de programa configurado como educação infantil.",409)
    existing=request.state.store.fetch_one("SELECT * FROM early_childhood_daily_records WHERE tenant_id=? AND student_id=? AND record_date=?",(tenant,data.student_id,str(data.record_date)));now=iso_now();rid=existing["id"] if existing else uuid7();version=(existing["version"]+1) if existing else 1;result={"id":rid,"student_id":data.student_id,"unit_id":enr["unit_id"],"record_date":str(data.record_date),"meals":data.meals,"sleep":data.sleep,"hygiene":data.hygiene,"diaper_changes":data.diaper_changes,"mood":data.mood,"development_notes":data.development_notes,"authorized_photos":data.authorized_photos,"version":version,"state":"active"}
    with request.state.store.transaction() as conn:
        if existing:conn.execute("UPDATE early_childhood_daily_records SET meals_json=?,sleep_json=?,hygiene_json=?,diaper_changes_json=?,mood=?,development_notes=?,authorized_photos_json=?,version=?,updated_at=? WHERE id=?",(json.dumps(data.meals),json.dumps(data.sleep),json.dumps(data.hygiene),json.dumps(data.diaper_changes),data.mood,data.development_notes,json.dumps(data.authorized_photos),version,now,rid))
        else:conn.execute("INSERT INTO early_childhood_daily_records(id,tenant_id,student_id,unit_id,record_date,meals_json,sleep_json,hygiene_json,diaper_changes_json,mood,development_notes,authorized_photos_json,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tenant,data.student_id,enr["unit_id"],str(data.record_date),json.dumps(data.meals),json.dumps(data.sleep),json.dumps(data.hygiene),json.dumps(data.diaper_changes),data.mood,data.development_notes,json.dumps(data.authorized_photos),"active",version,user.id,now,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="daily_record",aggregate_type="early_childhood_daily_record",aggregate_id=rid,correlation_id=request.state.correlation_id,before=dict(existing) if existing else None,after=result);add_outbox(conn,tenant_id=tenant,event_type="EarlyChildhoodDailyRecordUpdated",aggregate_type="early_childhood_daily_record",aggregate_id=rid,payload={"student_id":data.student_id,"record_date":str(data.record_date)},correlation_id=request.state.correlation_id)
    return result

@router.get("/academic/early-childhood/students/{student_id}/daily-records",operation_id="list_early_childhood_daily_records")
def list_daily(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);assert_student_access(request,user,student_id);items=request.state.store.fetch_all("SELECT * FROM early_childhood_daily_records WHERE tenant_id=? AND student_id=? ORDER BY record_date DESC LIMIT 180",(tenant,student_id))
    for item in items:
        for src,dst,default in (("meals_json","meals",[]),("sleep_json","sleep",{}),("hygiene_json","hygiene",[]),("diaper_changes_json","diaper_changes",[]),("authorized_photos_json","authorized_photos",[])):item[dst]=json.loads(item.pop(src) or json.dumps(default))
    return {"items":items}



@router.get("/academic/early-childhood/students/{student_id}/authorized-pickups",operation_id="list_authorized_student_pickups")
def authorized_pickups(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=require_staff(user);assert_student_access(request,user,student_id)
    return {"items":request.state.store.fetch_all(
        "SELECT g.id AS guardian_id,gs.relationship,p.full_name,p.social_name FROM guardian_students gs "
        "JOIN guardians g ON g.id=gs.guardian_id AND g.tenant_id=gs.tenant_id "
        "JOIN people p ON p.id=g.person_id AND p.tenant_id=g.tenant_id "
        "WHERE gs.tenant_id=? AND gs.student_id=? AND gs.pickup_authorized=1 AND g.state='active' ORDER BY p.full_name",
        (tenant,student_id),
    )}


@router.post("/academic/early-childhood/pickups",status_code=201,operation_id="record_student_pickup")
def record_pickup(data:PickupInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=require_staff(user);assert_student_access(request,user,data.student_id);row=request.state.store.fetch_one("SELECT gs.relationship,g.id AS guardian_id,p.full_name FROM guardian_students gs JOIN guardians g ON g.id=gs.guardian_id JOIN people p ON p.id=g.person_id WHERE gs.tenant_id=? AND gs.student_id=? AND g.id=? AND gs.pickup_authorized=1 AND g.state='active'",(tenant,data.student_id,data.guardian_id))
    if not row:raise DomainError("PICKUP_NOT_AUTHORIZED","Responsável não está autorizado para retirada do aluno.",403)
    pid=uuid7();now=iso_now();result={"id":pid,"student_id":data.student_id,"guardian_id":data.guardian_id,"pickup_person_name":row["full_name"],"relationship":row["relationship"],"released_at":data.released_at.isoformat()}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO student_pickup_records(id,tenant_id,student_id,guardian_id,pickup_person_name,relationship,identity_document_masked,released_at,released_by,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(pid,tenant,data.student_id,data.guardian_id,row["full_name"],row["relationship"],data.identity_document_masked,data.released_at.isoformat(),user.id,data.notes,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="release_student",aggregate_type="student_pickup",aggregate_id=pid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tenant,event_type="StudentReleasedToAuthorizedPerson",aggregate_type="student_pickup",aggregate_id=pid,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/academic/early-childhood/students/{student_id}/pickups",operation_id="list_student_pickups")
def list_pickups(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);assert_student_access(request,user,student_id);return {"items":request.state.store.fetch_all("SELECT * FROM student_pickup_records WHERE tenant_id=? AND student_id=? ORDER BY released_at DESC LIMIT 200",(tenant,student_id))}

@router.get("/academic/component-prerequisites",operation_id="list_component_prerequisites")
def list_prerequisites(request:Request,component_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);sql="SELECT cp.*,c.name AS component_name,p.name AS prerequisite_name FROM component_prerequisites cp JOIN curriculum_components c ON c.id=cp.component_id JOIN curriculum_components p ON p.id=cp.prerequisite_component_id WHERE cp.tenant_id=? AND cp.state='active'";params:list[Any]=[tenant]
    if component_id:sql+=" AND cp.component_id=?";params.append(component_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY c.name,p.name",params)}

@router.post("/academic/component-prerequisites",status_code=201,operation_id="create_component_prerequisite")
def create_prerequisite(data:PrerequisiteInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user)
    if not admin(user):raise DomainError("PERMISSION_DENIED","Somente coordenação/direção pode configurar pré-requisitos.",403)
    rows=request.state.store.fetch_all("SELECT id,curriculum_id FROM curriculum_components WHERE tenant_id=? AND id IN (?,?)",(tenant,data.component_id,data.prerequisite_component_id))
    if len(rows)!=2 or len({r["curriculum_id"] for r in rows})!=1 or data.component_id==data.prerequisite_component_id:raise DomainError("PREREQUISITE_SCOPE_INVALID","Componentes devem ser distintos e pertencer ao mesmo currículo.",409)
    existing=request.state.store.fetch_one("SELECT * FROM component_prerequisites WHERE tenant_id=? AND component_id=? AND prerequisite_component_id=?",(tenant,data.component_id,data.prerequisite_component_id))
    if existing:return {**existing,"idempotent":True}
    rid=uuid7();now=iso_now();result={"id":rid,**data.model_dump(mode="json"),"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO component_prerequisites(id,tenant_id,component_id,prerequisite_component_id,minimum_final_score,state,created_at) VALUES(?,?,?,?,?,?,?)",(rid,tenant,data.component_id,data.prerequisite_component_id,str(data.minimum_final_score) if data.minimum_final_score is not None else None,"active",now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="create",aggregate_type="component_prerequisite",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    return result

def _prerequisite_gaps(request: Request, tenant: str, enrollment_id: str, component_id: str) -> list[dict[str, Any]]:
    prerequisites = request.state.store.fetch_all(
        "SELECT cp.*,cc.name AS prerequisite_name FROM component_prerequisites cp "
        "JOIN curriculum_components cc ON cc.id=cp.prerequisite_component_id "
        "WHERE cp.tenant_id=? AND cp.component_id=? AND cp.state='active'",
        (tenant, component_id),
    )
    gaps: list[dict[str, Any]] = []
    for prerequisite in prerequisites:
        completion = request.state.store.fetch_one(
            "SELECT * FROM student_component_completions WHERE tenant_id=? AND enrollment_id=? "
            "AND component_id=? AND state='approved' ORDER BY created_at DESC LIMIT 1",
            (tenant, enrollment_id, prerequisite["prerequisite_component_id"]),
        )
        minimum = Decimal(str(prerequisite["minimum_final_score"])) if prerequisite["minimum_final_score"] is not None else None
        if not completion:
            gaps.append({**prerequisite, "reason": "not_completed"})
            continue
        score = Decimal(str(completion["final_score"])) if completion["final_score"] is not None else None
        if minimum is not None and (score is None or score < minimum):
            gaps.append({**prerequisite, "reason": "minimum_score_not_met", "completed_score": str(score) if score is not None else None})
    return gaps


@router.post("/academic/component-completions",status_code=201,operation_id="recognize_component_completion")
def complete_component(data:ComponentCompletionInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user)
    if not admin(user):raise DomainError("PERMISSION_DENIED","Somente secretaria/coordenação pode reconhecer integralização.",403)
    enr=enrollment(request,tenant,data.enrollment_id);component=request.state.store.fetch_one("SELECT * FROM curriculum_components WHERE tenant_id=? AND id=? AND curriculum_id=?",(tenant,data.component_id,enr["curriculum_id"]))
    if not component:raise DomainError("COMPONENT_SCOPE_MISMATCH","Componente não pertence ao currículo da matrícula.",409)
    # Conclusão acadêmica ordinária deve respeitar pré-requisitos. Reconhecimentos por
    # equivalência/transferência/crédito são atos administrativos explícitos e auditados.
    if data.source_type == "grade":
        gaps=_prerequisite_gaps(request,tenant,data.enrollment_id,data.component_id)
        if gaps:raise DomainError("COMPONENT_PREREQUISITES_NOT_MET","Pré-requisitos do componente ainda não foram integralizados com os critérios mínimos.",409,errors=[{"field":"component_id","code":"PREREQUISITE_NOT_MET","message":f"Pré-requisito {gap['prerequisite_name']} não atendido ({gap['reason']})."} for gap in gaps])
    rid=uuid7();now=iso_now();result={"id":rid,**data.model_dump(mode="json"),"credits_awarded":component["credits"],"workload_hours_awarded":component["workload_hours"],"state":"approved"}
    with request.state.store.transaction() as conn:
        old=conn.execute("SELECT id FROM student_component_completions WHERE tenant_id=? AND enrollment_id=? AND component_id=? AND state='approved'",(tenant,data.enrollment_id,data.component_id)).fetchone()
        if old:raise DomainError("COMPONENT_ALREADY_COMPLETED","Componente já integralizado nesta matrícula.",409)
        conn.execute("INSERT INTO student_component_completions(id,tenant_id,enrollment_id,component_id,source_type,source_reference_id,final_score,credits_awarded,workload_hours_awarded,completed_on,state,reason,approved_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tenant,data.enrollment_id,data.component_id,data.source_type,data.source_reference_id,str(data.final_score) if data.final_score is not None else None,component["credits"],component["workload_hours"],str(data.completed_on),"approved",data.reason,user.id,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="recognize",aggregate_type="component_completion",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tenant,event_type="CurriculumComponentCompleted",aggregate_type="component_completion",aggregate_id=rid,payload={"enrollment_id":data.enrollment_id,"component_id":data.component_id},correlation_id=request.state.correlation_id)
    return result

@router.get("/academic/internships",operation_id="list_internships")
def list_internships(request:Request,enrollment_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);sql="SELECT * FROM internships WHERE tenant_id=?";params:list[Any]=[tenant]
    if "student" in user.roles:
        student=student_for_user(request,user);sql+=" AND enrollment_id IN (SELECT id FROM enrollments WHERE tenant_id=? AND student_id=?)";params.extend([tenant,student["id"]])
    elif not (set(user.roles)&(ADMIN|TEACHERS)):raise DomainError("PERMISSION_DENIED","Permissão insuficiente.",403)
    if enrollment_id:sql+=" AND enrollment_id=?";params.append(enrollment_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY starts_on DESC",params)}

@router.post("/academic/internships",status_code=201,operation_id="create_internship")
def create_internship(data:InternshipInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user)
    if not admin(user):raise DomainError("PERMISSION_DENIED","Somente secretaria/coordenação pode cadastrar estágio.",403)
    enr=enrollment(request,tenant,data.enrollment_id);require_advanced_active_enrollment(enr,feature="Estágio")
    if data.advisor_employee_id and not request.state.store.fetch_one("SELECT id FROM employees WHERE tenant_id=? AND id=? AND state='active'",(tenant,data.advisor_employee_id)):raise DomainError("ADVISOR_NOT_FOUND","Orientador não localizado.",404)
    iid=uuid7();now=iso_now();result={"id":iid,**data.model_dump(mode="json"),"completed_hours":"0","state":"draft","version":1}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO internships(id,tenant_id,enrollment_id,organization_name,supervisor_name,advisor_employee_id,starts_on,ends_on,required_hours,completed_hours,state,version,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,tenant,data.enrollment_id,data.organization_name,data.supervisor_name,data.advisor_employee_id,str(data.starts_on),str(data.ends_on) if data.ends_on else None,str(data.required_hours),"0","draft",1,data.notes,user.id,now,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="create",aggregate_type="internship",aggregate_id=iid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/academic/internships/{internship_id}/hours",status_code=201,operation_id="log_internship_hours")
def log_hours(internship_id:str,data:InternshipHoursInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);row=request.state.store.fetch_one("SELECT * FROM internships WHERE tenant_id=? AND id=?",(tenant,internship_id))
    if not row:raise DomainError("INTERNSHIP_NOT_FOUND","Estágio não localizado.",404)
    if row["state"]!="in_progress":raise DomainError("INTERNSHIP_NOT_IN_PROGRESS","Horas somente podem ser lançadas durante estágio em andamento.",409)
    if not admin(user) and "student" not in user.roles:raise DomainError("PERMISSION_DENIED","Permissão insuficiente para registrar horas.",403)
    if "student" in user.roles:
        student=student_for_user(request,user);enr=request.state.store.fetch_one("SELECT id FROM enrollments WHERE tenant_id=? AND id=? AND student_id=?",(tenant,row["enrollment_id"],student["id"]));
        if not enr:raise DomainError("INTERNSHIP_ACCESS_DENIED","Estágio não pertence ao aluno autenticado.",403)
    hid=uuid7();now=iso_now();new_hours=Decimal(str(row["completed_hours"]))+data.hours
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO internship_hour_logs(id,tenant_id,internship_id,activity_date,hours,description,state,recorded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(hid,tenant,internship_id,str(data.activity_date),str(data.hours),data.description,"approved",user.id,now));conn.execute("UPDATE internships SET completed_hours=?,version=version+1,updated_at=? WHERE id=?",(str(new_hours),now,internship_id));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="log_hours",aggregate_type="internship",aggregate_id=internship_id,correlation_id=request.state.correlation_id,after={"hours":str(data.hours),"completed_hours":str(new_hours)})
    return {"id":hid,"internship_id":internship_id,"hours":str(data.hours),"completed_hours":str(new_hours)}

@router.post("/academic/internships/{internship_id}/state",operation_id="transition_internship")
def internship_state(internship_id:str,data:InternshipStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user)
    if not admin(user):raise DomainError("PERMISSION_DENIED","Somente secretaria/coordenação pode alterar o estágio.",403)
    row=request.state.store.fetch_one("SELECT * FROM internships WHERE tenant_id=? AND id=?",(tenant,internship_id))
    if not row:raise DomainError("INTERNSHIP_NOT_FOUND","Estágio não localizado.",404)
    if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Estágio alterado por outro usuário.",409)
    allowed={"draft":{"approved","cancelled"},"approved":{"in_progress","cancelled"},"in_progress":{"completed","cancelled"},"completed":set(),"cancelled":set()}
    if data.state not in allowed.get(row["state"],set()):raise DomainError("INVALID_STATE_TRANSITION",f"Transição de estágio {row['state']} → {data.state} não permitida.",409)
    if data.state=="completed" and Decimal(str(row["completed_hours"]))<Decimal(str(row["required_hours"])):raise DomainError("INTERNSHIP_HOURS_INCOMPLETE","Carga horária obrigatória do estágio ainda não foi cumprida.",409)
    now=iso_now();version=row["version"]+1
    with request.state.store.transaction() as conn:conn.execute("UPDATE internships SET state=?,version=?,updated_at=? WHERE id=?",(data.state,version,now,internship_id));add_audit(conn,tenant_id=tenant,actor_id=user.id,action=data.state,aggregate_type="internship",aggregate_id=internship_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":data.state,"version":version},reason=data.reason);add_outbox(conn,tenant_id=tenant,event_type="InternshipStateChanged",aggregate_type="internship",aggregate_id=internship_id,payload={"state":data.state,"version":version},correlation_id=request.state.correlation_id)
    return {"id":internship_id,"state":data.state,"version":version}

@router.get("/academic/complementary-activities",operation_id="list_complementary_activities")
def list_activities(request:Request,enrollment_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);sql="SELECT * FROM complementary_activities WHERE tenant_id=?";params:list[Any]=[tenant]
    if "student" in user.roles:
        student=student_for_user(request,user);sql+=" AND enrollment_id IN (SELECT id FROM enrollments WHERE tenant_id=? AND student_id=?)";params.extend([tenant,student["id"]])
    elif not (set(user.roles)&(ADMIN|TEACHERS)):raise DomainError("PERMISSION_DENIED","Permissão insuficiente.",403)
    if enrollment_id:sql+=" AND enrollment_id=?";params.append(enrollment_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY submitted_at DESC",params)}

@router.post("/academic/complementary-activities",status_code=201,operation_id="submit_complementary_activity")
def create_activity(data:ActivityInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);enr=enrollment(request,tenant,data.enrollment_id)
    if "student" in user.roles:
        student=student_for_user(request,user)
        if enr["student_id"]!=student["id"]:raise DomainError("ACTIVITY_ACCESS_DENIED","Matrícula não pertence ao aluno autenticado.",403)
    elif not admin(user):raise DomainError("PERMISSION_DENIED","Permissão insuficiente.",403)
    if data.evidence_document_id and not request.state.store.fetch_one("SELECT id FROM documents WHERE tenant_id=? AND id=? AND state='active'",(tenant,data.evidence_document_id)):raise DomainError("EVIDENCE_DOCUMENT_NOT_FOUND","Documento comprobatório não localizado.",404)
    aid=uuid7();now=iso_now();result={"id":aid,**data.model_dump(mode="json"),"approved_hours":"0","state":"submitted"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO complementary_activities(id,tenant_id,enrollment_id,category,title,requested_hours,approved_hours,evidence_document_id,state,submitted_by,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(aid,tenant,data.enrollment_id,data.category,data.title,str(data.requested_hours),"0",data.evidence_document_id,"submitted",user.id,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="submit",aggregate_type="complementary_activity",aggregate_id=aid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tenant,event_type="ComplementaryActivitySubmitted",aggregate_type="complementary_activity",aggregate_id=aid,payload={"enrollment_id":data.enrollment_id,"hours":str(data.requested_hours)},correlation_id=request.state.correlation_id)
    return result

@router.post("/academic/complementary-activities/{activity_id}/decision",operation_id="decide_complementary_activity")
def decide_activity(activity_id:str,data:ActivityDecision,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user)
    if not admin(user):raise DomainError("PERMISSION_DENIED","Somente secretaria/coordenação pode analisar atividade.",403)
    row=request.state.store.fetch_one("SELECT * FROM complementary_activities WHERE tenant_id=? AND id=?",(tenant,activity_id))
    if not row:raise DomainError("ACTIVITY_NOT_FOUND","Atividade não localizada.",404)
    if data.approved_hours>Decimal(str(row["requested_hours"])):raise DomainError("ACTIVITY_HOURS_INVALID","Horas aprovadas não podem exceder as solicitadas.",422)
    now=iso_now();approved=data.approved_hours if data.state=="approved" else Decimal("0")
    with request.state.store.transaction() as conn:conn.execute("UPDATE complementary_activities SET state=?,approved_hours=?,review_notes=?,reviewed_by=?,reviewed_at=? WHERE id=?",(data.state,str(approved),data.notes,user.id,now,activity_id));add_audit(conn,tenant_id=tenant,actor_id=user.id,action=data.state,aggregate_type="complementary_activity",aggregate_id=activity_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":data.state,"approved_hours":str(approved)},reason=data.notes)
    return {"id":activity_id,"state":data.state,"approved_hours":str(approved)}

@router.get("/academic/theses",operation_id="list_theses")
def list_theses(request:Request,enrollment_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);sql="SELECT * FROM theses WHERE tenant_id=?";params:list[Any]=[tenant]
    if "student" in user.roles:
        student=student_for_user(request,user);sql+=" AND enrollment_id IN (SELECT id FROM enrollments WHERE tenant_id=? AND student_id=?)";params.extend([tenant,student["id"]])
    elif not (set(user.roles)&(ADMIN|TEACHERS)):raise DomainError("PERMISSION_DENIED","Permissão insuficiente.",403)
    if enrollment_id:sql+=" AND enrollment_id=?";params.append(enrollment_id)
    return {"items":request.state.store.fetch_all(sql+" ORDER BY created_at DESC",params)}

@router.post("/academic/theses",status_code=201,operation_id="create_thesis")
def create_thesis(data:ThesisInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);enr=enrollment(request,tenant,data.enrollment_id);require_advanced_active_enrollment(enr,feature="TCC")
    if "student" in user.roles:
        student=student_for_user(request,user)
        if enr["student_id"]!=student["id"]:raise DomainError("THESIS_ACCESS_DENIED","Matrícula não pertence ao aluno autenticado.",403)
    elif not admin(user):raise DomainError("PERMISSION_DENIED","Permissão insuficiente.",403)
    if data.advisor_employee_id and not request.state.store.fetch_one("SELECT id FROM employees WHERE tenant_id=? AND id=? AND state='active'",(tenant,data.advisor_employee_id)):raise DomainError("ADVISOR_NOT_FOUND","Orientador não localizado.",404)
    thesis_id=uuid7();now=iso_now();result={"id":thesis_id,**data.model_dump(mode="json"),"state":"proposal","version":1}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO theses(id,tenant_id,enrollment_id,title,advisor_employee_id,coadvisor_name,state,abstract,document_id,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(thesis_id,tenant,data.enrollment_id,data.title,data.advisor_employee_id,data.coadvisor_name,"proposal",data.abstract,data.document_id,1,user.id,now,now));conn.execute("INSERT INTO thesis_events(id,tenant_id,thesis_id,event_type,state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant,thesis_id,"created","proposal","{}",user.id,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action="create",aggregate_type="thesis",aggregate_id=thesis_id,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/academic/theses/{thesis_id}/state",operation_id="transition_thesis")
def thesis_state(thesis_id:str,data:ThesisStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user)
    if not admin(user):raise DomainError("PERMISSION_DENIED","Somente coordenação/direção pode homologar o TCC.",403)
    row=request.state.store.fetch_one("SELECT * FROM theses WHERE tenant_id=? AND id=?",(tenant,thesis_id))
    if not row:raise DomainError("THESIS_NOT_FOUND","TCC não localizado.",404)
    if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","TCC alterado por outro usuário.",409)
    allowed={"proposal":{"approved","rejected","cancelled"},"approved":{"in_progress","cancelled"},"in_progress":{"submitted","cancelled"},"submitted":{"defended","rejected","cancelled"},"defended":{"passed","rejected"},"passed":set(),"rejected":set(),"cancelled":set()}
    if data.state not in allowed.get(row["state"],set()):raise DomainError("INVALID_STATE_TRANSITION",f"Transição de TCC {row['state']} → {data.state} não permitida.",409)
    if data.state in {"defended","passed"} and not data.defense_at and not row["defense_at"]:raise DomainError("THESIS_DEFENSE_REQUIRED","Defesa deve ser informada para este estado.",422)
    now=iso_now();version=row["version"]+1;defense=data.defense_at.isoformat() if data.defense_at else row["defense_at"]
    with request.state.store.transaction() as conn:conn.execute("UPDATE theses SET state=?,grade=?,defense_at=?,version=?,updated_at=? WHERE id=?",(data.state,str(data.grade) if data.grade is not None else row["grade"],defense,version,now,thesis_id));conn.execute("INSERT INTO thesis_events(id,tenant_id,thesis_id,event_type,state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant,thesis_id,"state_changed",data.state,json.dumps({"reason":data.reason,"grade":str(data.grade) if data.grade is not None else None,"defense_at":defense}),user.id,now));add_audit(conn,tenant_id=tenant,actor_id=user.id,action=data.state,aggregate_type="thesis",aggregate_id=thesis_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":data.state,"grade":str(data.grade) if data.grade is not None else row["grade"],"version":version},reason=data.reason);add_outbox(conn,tenant_id=tenant,event_type="ThesisStateChanged",aggregate_type="thesis",aggregate_id=thesis_id,payload={"state":data.state,"version":version},correlation_id=request.state.correlation_id)
    return {"id":thesis_id,"state":data.state,"grade":str(data.grade) if data.grade is not None else row["grade"],"version":version}

@router.get("/academic/students/{student_id}/integralization",operation_id="get_student_integralization")
def integralization(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant=tid(user);assert_student_access(request,user,student_id);enrs=request.state.store.fetch_all("SELECT e.*,p.name AS program_name,c.name AS curriculum_name FROM enrollments e JOIN programs p ON p.id=e.program_id JOIN curricula c ON c.id=e.curriculum_id WHERE e.tenant_id=? AND e.student_id=? ORDER BY e.created_at DESC",(tenant,student_id));items=[]
    for enr in enrs:
        components=request.state.store.fetch_all("SELECT * FROM curriculum_components WHERE tenant_id=? AND curriculum_id=? AND state='active' ORDER BY name",(tenant,enr["curriculum_id"]));completed=request.state.store.fetch_all("SELECT * FROM student_component_completions WHERE tenant_id=? AND enrollment_id=? AND state='approved'",(tenant,enr["id"]));done={x["component_id"]:x for x in completed};total_hours=sum((Decimal(str(c["workload_hours"] or 0)) for c in components),Decimal("0"));done_hours=sum((Decimal(str(done[c["id"]]["workload_hours_awarded"] or c["workload_hours"] or 0)) for c in components if c["id"] in done),Decimal("0"));total_credits=sum((Decimal(str(c["credits"] or 0)) for c in components),Decimal("0"));done_credits=sum((Decimal(str(done[c["id"]]["credits_awarded"] or c["credits"] or 0)) for c in components if c["id"] in done),Decimal("0"));internships=request.state.store.fetch_all("SELECT id,required_hours,completed_hours,state FROM internships WHERE tenant_id=? AND enrollment_id=?",(tenant,enr["id"]));activities=request.state.store.fetch_all("SELECT id,category,title,approved_hours,state FROM complementary_activities WHERE tenant_id=? AND enrollment_id=?",(tenant,enr["id"]));theses=request.state.store.fetch_all("SELECT id,title,state,grade,defense_at FROM theses WHERE tenant_id=? AND enrollment_id=?",(tenant,enr["id"]));prereq=request.state.store.fetch_all("SELECT cp.component_id,cp.prerequisite_component_id,cp.minimum_final_score,ccp.name AS prerequisite_name FROM component_prerequisites cp JOIN curriculum_components cc ON cc.id=cp.component_id JOIN curriculum_components ccp ON ccp.id=cp.prerequisite_component_id WHERE cp.tenant_id=? AND cc.curriculum_id=? AND cp.state='active'",(tenant,enr["curriculum_id"]));pending_prereq=[]
        for rule in prereq:
            if rule["component_id"] in done:continue
            prerequisite_completion=done.get(rule["prerequisite_component_id"]);minimum=Decimal(str(rule["minimum_final_score"])) if rule["minimum_final_score"] is not None else None
            if prerequisite_completion is None:pending_prereq.append({**rule,"reason":"not_completed"});continue
            score=Decimal(str(prerequisite_completion["final_score"])) if prerequisite_completion["final_score"] is not None else None
            if minimum is not None and (score is None or score<minimum):pending_prereq.append({**rule,"reason":"minimum_score_not_met","completed_score":str(score) if score is not None else None})
        items.append({"enrollment":enr,"curriculum":{"components_total":len(components),"components_completed":len(done),"workload_hours_total":str(total_hours),"workload_hours_completed":str(done_hours),"credits_total":str(total_credits),"credits_completed":str(done_credits),"completion_percentage":str((done_hours/total_hours*100).quantize(Decimal('0.01')) if total_hours else Decimal('0'))},"components":[{**c,"completed":c["id"] in done,"completion":done.get(c["id"])} for c in components],"pending_prerequisites":pending_prereq,"internships":internships,"complementary_activities":activities,"complementary_hours_approved":str(sum((Decimal(str(x["approved_hours"] or 0)) for x in activities if x["state"]=="approved"),Decimal('0'))),"theses":theses})
    return {"student_id":student_id,"enrollments":items,"generated_at":iso_now()}
