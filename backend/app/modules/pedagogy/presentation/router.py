from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator

from app.modules.portals.access import assert_student_access, employee_for_user
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["pedagogy"])
ADMIN = {"tenant_owner", "institution_director", "academic_coordinator", "secretary"}
TEACHERS = {"teacher", "assistant_teacher"}


def _tenant(user: CurrentUser) -> str:
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Rota disponível somente no domínio da instituição.", 404)
    return user.tenant_id


def _admin(user: CurrentUser) -> bool:
    return bool(set(user.roles) & ADMIN)


def _require_staff(user: CurrentUser) -> str:
    tid = _tenant(user)
    if not (set(user.roles) & (ADMIN | TEACHERS)):
        raise DomainError("PERMISSION_DENIED", "Permissão insuficiente no módulo de avaliações.", 403)
    return tid


def _scope(request: Request, user: CurrentUser, period_id: str, class_id: str, component_id: str) -> tuple[dict, dict]:
    tid = _require_staff(user)
    group = request.state.store.fetch_one("SELECT * FROM class_groups WHERE tenant_id=? AND id=? AND state='active'", (tid, class_id))
    if not group: raise DomainError("CLASS_GROUP_NOT_FOUND", "Turma ativa não localizada.", 404)
    period = request.state.store.fetch_one("SELECT * FROM academic_periods WHERE tenant_id=? AND id=? AND state='active'", (tid, period_id))
    if not period or period["academic_year_id"] != group["academic_year_id"]:
        raise DomainError("ACADEMIC_PERIOD_SCOPE_MISMATCH", "Período não pertence ao ano letivo da turma.", 409)
    component = request.state.store.fetch_one("SELECT * FROM curriculum_components WHERE tenant_id=? AND id=? AND state='active'", (tid, component_id))
    if not component or component["curriculum_id"] != group["curriculum_id"]:
        raise DomainError("COMPONENT_SCOPE_MISMATCH", "Componente não pertence ao currículo da turma.", 409)
    if not _admin(user):
        employee = employee_for_user(request, user)
        assignment = request.state.store.fetch_one(
            "SELECT id FROM teacher_assignments WHERE tenant_id=? AND employee_id=? AND class_group_id=? AND component_id=? AND state='active' AND starts_on<=? AND (ends_on IS NULL OR ends_on>=?) LIMIT 1",
            (tid, employee["id"], class_id, component_id, period["ends_on"], period["starts_on"]),
        )
        if not assignment: raise DomainError("TEACHER_NOT_ASSIGNED", "Professor não possui atribuição ativa para turma/componente.", 403)
    return group, period


def _policy(request: Request, tid: str, year_id: str, class_id: str, component_id: str, when: str) -> dict:
    row = request.state.store.fetch_one(
        """SELECT * FROM grading_policies WHERE tenant_id=? AND academic_year_id=? AND state='active'
             AND effective_from<=? AND (effective_until IS NULL OR effective_until>=?)
             AND (class_group_id=? OR class_group_id IS NULL) AND (component_id=? OR component_id IS NULL)
             ORDER BY CASE WHEN class_group_id=? THEN 0 ELSE 1 END,CASE WHEN component_id=? THEN 0 ELSE 1 END,version DESC LIMIT 1""",
        (tid, year_id, when, when, class_id, component_id, class_id, component_id),
    )
    if not row: raise DomainError("GRADING_POLICY_NOT_FOUND", "Nenhuma política de notas vigente corresponde ao contexto.", 409)
    return row


def _attendance(request: Request, tid: str, enrollment: dict, period: dict, component_id: str) -> Decimal:
    rows = request.state.store.fetch_all(
        """SELECT ar.status_code,cs.attendance_policy_id,cs.scheduled_start,cs.status AS session_status
             FROM attendance_records ar JOIN class_sessions cs ON cs.id=ar.class_session_id
            WHERE ar.tenant_id=? AND ar.student_id=? AND cs.class_group_id=? AND cs.component_id=?
              AND substr(cs.scheduled_start,1,10)>=? AND substr(cs.scheduled_start,1,10)<=?
            ORDER BY cs.scheduled_start""",
        (tid, enrollment["student_id"], enrollment["class_group_id"], component_id, period["starts_on"], period["ends_on"]),
    )
    weighted = Decimal("0"); counted = 0
    for row in rows:
        if row["session_status"] in {"cancelled", "rescheduled"}: continue
        version = request.state.store.fetch_one(
            "SELECT status_effects_json FROM attendance_policy_versions WHERE policy_id=? AND effective_from<=? AND (effective_until IS NULL OR effective_until>=?) ORDER BY version DESC LIMIT 1",
            (row["attendance_policy_id"], str(row["scheduled_start"])[:10], str(row["scheduled_start"])[:10]),
        )
        if not version: continue
        effects = json.loads(version["status_effects_json"] or "{}")
        effect = effects.get(row["status_code"])
        if effect is None: continue
        weighted += Decimal(str(effect)); counted += 1
    if not counted: return Decimal("100.00")
    return (weighted / Decimal(counted) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PolicyInput(BaseModel):
    academic_year_id: str; name: str = Field(min_length=2, max_length=160)
    class_group_id: str | None = None; component_id: str | None = None
    calculation_method: Literal["weighted_average"] = "weighted_average"
    max_score: Decimal = Field(default=Decimal("10"), gt=0)
    passing_score: Decimal = Field(default=Decimal("6"), ge=0)
    attendance_minimum: Decimal = Field(default=Decimal("75"), ge=0, le=100)
    rounding_precision: int = Field(default=2, ge=0, le=4)
    recovery_strategy: Literal["replace_if_higher", "average_with_recovery", "replace"] = "replace_if_higher"
    missing_score_strategy: Literal["zero", "ignore"] = "zero"
    effective_from: date; effective_until: date | None = None

    @model_validator(mode="after")
    def validate_scores(self):
        if self.passing_score > self.max_score: raise ValueError("passing_score não pode exceder max_score")
        if self.effective_until and self.effective_until < self.effective_from: raise ValueError("effective_until inválido")
        return self


class AssessmentInput(BaseModel):
    academic_period_id: str; class_group_id: str; component_id: str; grading_policy_id: str | None = None
    title: str = Field(min_length=2, max_length=180); assessment_type: str = Field(default="exam", min_length=2, max_length=50)
    weight: Decimal = Field(default=Decimal("1"), gt=0); max_score: Decimal = Field(default=Decimal("10"), gt=0); due_on: date | None = None


class AssessmentPatch(BaseModel):
    expected_version: int = Field(ge=1); title: str | None = Field(default=None, min_length=2, max_length=180)
    weight: Decimal | None = Field(default=None, gt=0); max_score: Decimal | None = Field(default=None, gt=0); due_on: date | None = None
    reason: str = Field(min_length=3, max_length=1000)


class StateInput(BaseModel): expected_version: int = Field(ge=1); reason: str = Field(min_length=3, max_length=1000)


class GradeItem(BaseModel):
    enrollment_id: str; score: Decimal | None = Field(default=None, ge=0); concept: str | None = Field(default=None, max_length=40)
    status: Literal["graded", "missing", "excused"] = "graded"; feedback: str | None = Field(default=None, max_length=4000); expected_version: int | None = Field(default=None, ge=1)


class GradeBatch(BaseModel): grades: list[GradeItem] = Field(min_length=1); reason: str = Field(default="Lançamento de avaliação", min_length=3, max_length=1000)


class CalculateInput(BaseModel): academic_period_id: str; class_group_id: str; component_id: str; enrollment_ids: list[str] = Field(default_factory=list)


class RecoveryInput(BaseModel): score: Decimal = Field(ge=0); reason: str = Field(min_length=3, max_length=1000); expected_version: int = Field(ge=1)


class CloseInput(BaseModel): academic_period_id: str; class_group_id: str; component_id: str; reason: str = Field(min_length=3, max_length=1000)


@router.get("/pedagogy/grading-policies", operation_id="list_grading_policies")
def list_policies(request: Request, academic_year_id: str | None = None, user: CurrentUser = Depends(current_user)):
    tid = _require_staff(user); sql="SELECT * FROM grading_policies WHERE tenant_id=?"; params: list[Any]=[tid]
    if academic_year_id: sql += " AND academic_year_id=?"; params.append(academic_year_id)
    sql += " ORDER BY effective_from DESC,version DESC"; items=request.state.store.fetch_all(sql,params)
    for item in items: item["settings"] = json.loads(item.pop("settings_json") or "{}")
    return {"items":items}


@router.post("/pedagogy/grading-policies", status_code=201, operation_id="create_grading_policy")
def create_policy(data: PolicyInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_tenant(user)
    if not _admin(user): raise DomainError("PERMISSION_DENIED", "Somente coordenação/direção pode publicar política de notas.", 403)
    year=request.state.store.fetch_one("SELECT * FROM academic_years WHERE tenant_id=? AND id=?",(tid,data.academic_year_id))
    if not year: raise DomainError("ACADEMIC_YEAR_NOT_FOUND","Ano letivo não localizado.",404)
    if data.class_group_id:
        group=request.state.store.fetch_one("SELECT * FROM class_groups WHERE tenant_id=? AND id=?",(tid,data.class_group_id))
        if not group or group["academic_year_id"]!=data.academic_year_id: raise DomainError("GRADING_POLICY_SCOPE_MISMATCH","Turma não pertence ao ano letivo.",409)
    if data.component_id and data.class_group_id:
        comp=request.state.store.fetch_one("SELECT cc.id FROM curriculum_components cc JOIN class_groups cg ON cg.curriculum_id=cc.curriculum_id WHERE cc.tenant_id=? AND cc.id=? AND cg.id=?",(tid,data.component_id,data.class_group_id))
        if not comp: raise DomainError("GRADING_POLICY_SCOPE_MISMATCH","Componente não pertence à turma.",409)
    version=(request.state.store.scalar("SELECT COALESCE(MAX(version),0) FROM grading_policies WHERE tenant_id=? AND academic_year_id=? AND (class_group_id=? OR (class_group_id IS NULL AND ? IS NULL)) AND (component_id=? OR (component_id IS NULL AND ? IS NULL))",(tid,data.academic_year_id,data.class_group_id,data.class_group_id,data.component_id,data.component_id)) or 0)+1
    pid=uuid7();now=iso_now();settings={"missing_score_strategy":data.missing_score_strategy};result={"id":pid,**data.model_dump(mode="json"),"version":int(version),"state":"active","settings":settings}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO grading_policies(id,tenant_id,academic_year_id,class_group_id,component_id,name,calculation_method,max_score,passing_score,attendance_minimum,rounding_precision,recovery_strategy,settings_json,effective_from,effective_until,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,tid,data.academic_year_id,data.class_group_id,data.component_id,data.name,data.calculation_method,str(data.max_score),str(data.passing_score),str(data.attendance_minimum),data.rounding_precision,data.recovery_strategy,json.dumps(settings,sort_keys=True),str(data.effective_from),str(data.effective_until) if data.effective_until else None,"active",int(version),user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="grading_policy",aggregate_id=pid,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tid,event_type="GradingPolicyPublished",aggregate_type="grading_policy",aggregate_id=pid,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/pedagogy/assessments", operation_id="list_assessments")
def list_assessments(request: Request, academic_period_id: str | None=None, class_group_id: str|None=None, component_id: str|None=None, user: CurrentUser=Depends(current_user)):
    tid=_require_staff(user); sql="SELECT * FROM assessments WHERE tenant_id=?"; params:list[Any]=[tid]
    if academic_period_id: sql+=" AND academic_period_id=?";params.append(academic_period_id)
    if class_group_id: sql+=" AND class_group_id=?";params.append(class_group_id)
    if component_id: sql+=" AND component_id=?";params.append(component_id)
    if not _admin(user):
        employee=employee_for_user(request,user);sql+=" AND EXISTS(SELECT 1 FROM teacher_assignments ta WHERE ta.tenant_id=assessments.tenant_id AND ta.employee_id=? AND ta.class_group_id=assessments.class_group_id AND ta.component_id=assessments.component_id AND ta.state='active')";params.append(employee["id"])
    sql+=" ORDER BY due_on,created_at";return {"items":request.state.store.fetch_all(sql,params)}


@router.post("/pedagogy/assessments", status_code=201, operation_id="create_assessment")
def create_assessment(data:AssessmentInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=_tenant(user);group,period=_scope(request,user,data.academic_period_id,data.class_group_id,data.component_id);policy_id=data.grading_policy_id
    if policy_id:
        p=request.state.store.fetch_one("SELECT id,max_score FROM grading_policies WHERE tenant_id=? AND id=? AND state='active'",(tid,policy_id))
        if not p:raise DomainError("GRADING_POLICY_NOT_FOUND","Política de notas não localizada.",404)
    else: policy_id=_policy(request,tid,group["academic_year_id"],data.class_group_id,data.component_id,period["starts_on"])["id"]
    aid=uuid7();now=iso_now();result={"id":aid,**data.model_dump(mode="json"),"grading_policy_id":policy_id,"state":"draft","version":1}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO assessments(id,tenant_id,academic_period_id,class_group_id,component_id,grading_policy_id,title,assessment_type,weight,max_score,due_on,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(aid,tid,data.academic_period_id,data.class_group_id,data.component_id,policy_id,data.title,data.assessment_type,str(data.weight),str(data.max_score),str(data.due_on) if data.due_on else None,"draft",1,user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="assessment",aggregate_id=aid,correlation_id=request.state.correlation_id,after=result)
    return result


def _assessment(request:Request,user:CurrentUser,assessment_id:str)->dict:
    tid=_require_staff(user);row=request.state.store.fetch_one("SELECT * FROM assessments WHERE tenant_id=? AND id=?",(tid,assessment_id))
    if not row:raise DomainError("ASSESSMENT_NOT_FOUND","Avaliação não localizada.",404)
    _scope(request,user,row["academic_period_id"],row["class_group_id"],row["component_id"]);return row


@router.get("/pedagogy/assessments/{assessment_id}", operation_id="get_assessment")
def get_assessment(assessment_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    row=_assessment(request,user,assessment_id);grades=request.state.store.fetch_all("SELECT ag.*,e.student_id,p.full_name,p.social_name,s.registration_number FROM assessment_grades ag JOIN enrollments e ON e.id=ag.enrollment_id JOIN students s ON s.id=e.student_id JOIN people p ON p.id=s.person_id WHERE ag.tenant_id=? AND ag.assessment_id=? ORDER BY p.full_name",(row["tenant_id"],assessment_id));roster=request.state.store.fetch_all("SELECT e.id AS enrollment_id,e.student_id,p.full_name,p.social_name,s.registration_number FROM enrollments e JOIN students s ON s.id=e.student_id JOIN people p ON p.id=s.person_id WHERE e.tenant_id=? AND e.class_group_id=? AND e.state='active' ORDER BY p.full_name",(row["tenant_id"],row["class_group_id"]));return {**row,"grades":grades,"roster":roster}


@router.patch("/pedagogy/assessments/{assessment_id}", operation_id="update_assessment")
def update_assessment(assessment_id:str,data:AssessmentPatch,request:Request,user:CurrentUser=Depends(current_user)):
    row=_assessment(request,user,assessment_id)
    if row["state"]!="draft":raise DomainError("ASSESSMENT_IMMUTABLE","Avaliação publicada só pode receber notas ou ser fechada.",409)
    if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","A avaliação foi alterada por outro usuário.",409)
    title=data.title or row["title"];weight=str(data.weight if data.weight is not None else row["weight"]);max_score=str(data.max_score if data.max_score is not None else row["max_score"]);due=str(data.due_on) if data.due_on else row["due_on"];now=iso_now();version=row["version"]+1
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE assessments SET title=?,weight=?,max_score=?,due_on=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(title,weight,max_score,due,version,now,row["tenant_id"],assessment_id));add_audit(conn,tenant_id=row["tenant_id"],actor_id=user.id,action="update",aggregate_type="assessment",aggregate_id=assessment_id,correlation_id=request.state.correlation_id,before=dict(row),after={"title":title,"weight":weight,"max_score":max_score,"due_on":due,"version":version},reason=data.reason)
    return {"id":assessment_id,"title":title,"weight":weight,"max_score":max_score,"due_on":due,"state":"draft","version":version}


def _assessment_state(assessment_id:str,data:StateInput,request:Request,user:CurrentUser,target:str,event:str):
    row=_assessment(request,user,assessment_id)
    allowed={"published":{"draft"},"closed":{"published"}}[target]
    if row["state"]==target:return {"id":assessment_id,"state":target,"version":row["version"],"idempotent":True}
    if row["state"] not in allowed:raise DomainError("ASSESSMENT_STATE_INVALID",f"Avaliação não pode ir de {row['state']} para {target}.",409)
    if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","A avaliação foi alterada por outro usuário.",409)
    version=row["version"]+1;now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE assessments SET state=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(target,version,now,row["tenant_id"],assessment_id));add_audit(conn,tenant_id=row["tenant_id"],actor_id=user.id,action=target,aggregate_type="assessment",aggregate_id=assessment_id,correlation_id=request.state.correlation_id,before=dict(row),after={"state":target,"version":version},reason=data.reason);add_outbox(conn,tenant_id=row["tenant_id"],event_type=event,aggregate_type="assessment",aggregate_id=assessment_id,payload={"id":assessment_id,"state":target,"version":version},correlation_id=request.state.correlation_id)
    return {"id":assessment_id,"state":target,"version":version}


@router.post("/pedagogy/assessments/{assessment_id}/publish",operation_id="publish_assessment")
def publish_assessment(assessment_id:str,data:StateInput,request:Request,user:CurrentUser=Depends(current_user)):return _assessment_state(assessment_id,data,request,user,"published","AssessmentPublished")
@router.post("/pedagogy/assessments/{assessment_id}/close",operation_id="close_assessment")
def close_assessment(assessment_id:str,data:StateInput,request:Request,user:CurrentUser=Depends(current_user)):return _assessment_state(assessment_id,data,request,user,"closed","AssessmentClosed")


@router.put("/pedagogy/assessments/{assessment_id}/grades", operation_id="save_assessment_grades")
def save_grades(assessment_id:str,data:GradeBatch,request:Request,user:CurrentUser=Depends(current_user)):
    assessment=_assessment(request,user,assessment_id);tid=assessment["tenant_id"]
    if assessment["state"]!="published":raise DomainError("ASSESSMENT_NOT_OPEN_FOR_GRADING","Notas só podem ser lançadas em avaliação publicada.",409)
    now=iso_now();results=[]
    with request.state.store.transaction() as conn:
        for item in data.grades:
            enrollment=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=? AND class_group_id=? AND state='active'",(tid,item.enrollment_id,assessment["class_group_id"])).fetchone()
            if not enrollment:raise DomainError("ENROLLMENT_SCOPE_MISMATCH","Matrícula não pertence à turma ativa da avaliação.",409)
            if item.status=="graded" and item.score is None:raise DomainError("GRADE_SCORE_REQUIRED","Nota é obrigatória para status graded.",422)
            if item.score is not None and item.score>Decimal(str(assessment["max_score"])):raise DomainError("GRADE_EXCEEDS_MAX","Nota excede a pontuação máxima da avaliação.",422)
            existing=conn.execute("SELECT * FROM assessment_grades WHERE tenant_id=? AND assessment_id=? AND enrollment_id=?",(tid,assessment_id,item.enrollment_id)).fetchone()
            before=dict(existing) if existing else {}
            if existing:
                if item.expected_version is None or existing["version"]!=item.expected_version:raise DomainError("VERSION_CONFLICT","Nota foi alterada por outro usuário; recarregue antes de salvar.",409)
                gid=existing["id"];version=existing["version"]+1
                conn.execute("UPDATE assessment_grades SET score=?,concept=?,status=?,feedback=?,version=?,graded_by=?,graded_at=?,updated_at=? WHERE id=?",(str(item.score) if item.score is not None else None,item.concept,item.status,item.feedback,version,user.id,now,now,gid))
            else:
                gid=uuid7();version=1;conn.execute("INSERT INTO assessment_grades(id,tenant_id,assessment_id,enrollment_id,score,concept,status,feedback,version,graded_by,graded_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(gid,tid,assessment_id,item.enrollment_id,str(item.score) if item.score is not None else None,item.concept,item.status,item.feedback,version,user.id,now,now))
            after={"id":gid,"assessment_id":assessment_id,"enrollment_id":item.enrollment_id,"score":str(item.score) if item.score is not None else None,"concept":item.concept,"status":item.status,"feedback":item.feedback,"version":version}
            conn.execute("INSERT INTO assessment_grade_events(id,tenant_id,assessment_grade_id,event_type,before_json,after_json,reason,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,gid,"grade_saved",json.dumps(before,default=str,sort_keys=True),json.dumps(after,sort_keys=True),data.reason,user.id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="grade",aggregate_type="assessment_grade",aggregate_id=gid,correlation_id=request.state.correlation_id,before=before,after=after,reason=data.reason);results.append(after)
        add_outbox(conn,tenant_id=tid,event_type="GradesSaved",aggregate_type="assessment",aggregate_id=assessment_id,payload={"assessment_id":assessment_id,"count":len(results)},correlation_id=request.state.correlation_id)
    return {"items":results}


def _calculate_one(request:Request,tid:str,period:dict,group:dict,component_id:str,enrollment:dict,policy:dict,recovery_score:Decimal|None=None)->dict:
    assessments=request.state.store.fetch_all("SELECT * FROM assessments WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=? AND state IN ('published','closed') ORDER BY created_at",(tid,period["id"],group["id"],component_id))
    settings=json.loads(policy["settings_json"] or "{}");missing=settings.get("missing_score_strategy","zero");weighted=Decimal("0");weight_total=Decimal("0");detail=[]
    for assessment in assessments:
        grade=request.state.store.fetch_one("SELECT * FROM assessment_grades WHERE tenant_id=? AND assessment_id=? AND enrollment_id=?",(tid,assessment["id"],enrollment["id"]));weight=Decimal(str(assessment["weight"]));amax=Decimal(str(assessment["max_score"]));score=None;status="missing"
        if grade: score=Decimal(str(grade["score"])) if grade["score"] is not None else None;status=grade["status"]
        if status=="excused" or (score is None and missing=="ignore"): detail.append({"assessment_id":assessment["id"],"title":assessment["title"],"status":status,"score":str(score) if score is not None else None,"included":False});continue
        score=score if score is not None else Decimal("0");normalized=(score/amax) if amax else Decimal("0");weighted+=normalized*weight;weight_total+=weight;detail.append({"assessment_id":assessment["id"],"title":assessment["title"],"status":status,"score":str(score),"included":True,"weight":str(weight)})
    max_score=Decimal(str(policy["max_score"]));precision=int(policy["rounding_precision"]);quant=Decimal("1").scaleb(-precision);average=((weighted/weight_total)*max_score if weight_total else Decimal("0")).quantize(quant,rounding=ROUND_HALF_UP)
    final=average
    if recovery_score is not None:
        strategy=policy["recovery_strategy"]
        if strategy=="replace":final=recovery_score
        elif strategy=="average_with_recovery":final=((average+recovery_score)/Decimal("2")).quantize(quant,rounding=ROUND_HALF_UP)
        else:final=max(average,recovery_score)
    final=final.quantize(quant,rounding=ROUND_HALF_UP)
    attendance=_attendance(request,tid,enrollment,period,component_id);passing=Decimal(str(policy["passing_score"]));attendance_min=Decimal(str(policy["attendance_minimum"]));outcome="approved" if final>=passing and attendance>=attendance_min else ("failed_attendance" if attendance<attendance_min else "recovery")
    return {"average_score":str(average),"recovery_score":str(recovery_score) if recovery_score is not None else None,"final_score":str(final),"attendance_percentage":str(attendance),"outcome":outcome,"calculation":{"assessment_count":len(assessments),"weighted_assessment_count":len([x for x in detail if x.get('included')]),"assessments":detail,"policy_version":policy["version"],"policy_id":policy["id"]}}


def _upsert_result(request:Request,user:CurrentUser,period:dict,group:dict,component_id:str,enrollment:dict,policy:dict,recovery_score:Decimal|None=None)->dict:
    tid=group["tenant_id"];calc=_calculate_one(request,tid,period,group,component_id,enrollment,policy,recovery_score);existing=request.state.store.fetch_one("SELECT * FROM period_results WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=? AND enrollment_id=?",(tid,period["id"],group["id"],component_id,enrollment["id"]));now=iso_now();rid=existing["id"] if existing else uuid7();version=(existing["version"]+1) if existing else 1;state=existing["state"] if existing else "open"
    if state=="closed":raise DomainError("GRADE_PERIOD_CLOSED","Período de notas está fechado.",409)
    with request.state.store.transaction() as conn:
        if existing:conn.execute("UPDATE period_results SET grading_policy_id=?,average_score=?,recovery_score=?,final_score=?,attendance_percentage=?,outcome=?,calculation_json=?,version=?,calculated_at=?,updated_at=? WHERE id=?",(policy["id"],calc["average_score"],calc["recovery_score"],calc["final_score"],calc["attendance_percentage"],calc["outcome"],json.dumps(calc["calculation"],sort_keys=True),version,now,now,rid))
        else:conn.execute("INSERT INTO period_results(id,tenant_id,academic_period_id,class_group_id,component_id,enrollment_id,grading_policy_id,average_score,recovery_score,final_score,attendance_percentage,outcome,state,calculation_json,version,calculated_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,period["id"],group["id"],component_id,enrollment["id"],policy["id"],calc["average_score"],calc["recovery_score"],calc["final_score"],calc["attendance_percentage"],calc["outcome"],"open",json.dumps(calc["calculation"],sort_keys=True),version,now,now))
    return {"id":rid,"enrollment_id":enrollment["id"],**calc,"state":"open","version":version}


@router.post("/pedagogy/period-results/calculate",operation_id="calculate_period_results")
def calculate_results(data:CalculateInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=_tenant(user);group,period=_scope(request,user,data.academic_period_id,data.class_group_id,data.component_id);policy=_policy(request,tid,group["academic_year_id"],group["id"],data.component_id,period["starts_on"]);sql="SELECT * FROM enrollments WHERE tenant_id=? AND class_group_id=? AND state='active'";params:list[Any]=[tid,group["id"]]
    if data.enrollment_ids:sql+=f" AND id IN ({','.join('?' for _ in data.enrollment_ids)})";params.extend(data.enrollment_ids)
    enrollments=request.state.store.fetch_all(sql,params);items=[_upsert_result(request,user,period,group,data.component_id,e,policy) for e in enrollments];return {"items":items,"policy_id":policy["id"]}


@router.get("/pedagogy/period-results",operation_id="list_period_results")
def list_results(request:Request,academic_period_id:str,class_group_id:str,component_id:str,user:CurrentUser=Depends(current_user)):
    tid=_tenant(user);_scope(request,user,academic_period_id,class_group_id,component_id);items=request.state.store.fetch_all("SELECT pr.*,e.student_id,p.full_name FROM period_results pr JOIN enrollments e ON e.id=pr.enrollment_id JOIN students s ON s.id=e.student_id JOIN people p ON p.id=s.person_id WHERE pr.tenant_id=? AND pr.academic_period_id=? AND pr.class_group_id=? AND pr.component_id=? ORDER BY p.full_name",(tid,academic_period_id,class_group_id,component_id));
    for item in items:item["calculation"]=json.loads(item.pop("calculation_json") or "{}")
    return {"items":items}


@router.post("/pedagogy/period-results/{result_id}/recovery",operation_id="save_recovery_grade")
def save_recovery(result_id:str,data:RecoveryInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=_require_staff(user);row=request.state.store.fetch_one("SELECT * FROM period_results WHERE tenant_id=? AND id=?",(tid,result_id))
    if not row:raise DomainError("PERIOD_RESULT_NOT_FOUND","Resultado do período não localizado.",404)
    _scope(request,user,row["academic_period_id"],row["class_group_id"],row["component_id"])
    if row["state"]=="closed":raise DomainError("GRADE_PERIOD_CLOSED","Período de notas está fechado.",409)
    if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Resultado foi alterado por outro usuário.",409)
    policy=request.state.store.fetch_one("SELECT * FROM grading_policies WHERE tenant_id=? AND id=?",(tid,row["grading_policy_id"]));enrollment=request.state.store.fetch_one("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,row["enrollment_id"]));period=request.state.store.fetch_one("SELECT * FROM academic_periods WHERE tenant_id=? AND id=?",(tid,row["academic_period_id"]));group=request.state.store.fetch_one("SELECT * FROM class_groups WHERE tenant_id=? AND id=?",(tid,row["class_group_id"]));result=_upsert_result(request,user,period,group,row["component_id"],enrollment,policy,data.score)
    with request.state.store.transaction() as conn:add_audit(conn,tenant_id=tid,actor_id=user.id,action="recovery",aggregate_type="period_result",aggregate_id=result_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="RecoveryGradePublished",aggregate_type="period_result",aggregate_id=result_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/pedagogy/grade-periods/close",operation_id="close_grade_period")
def close_grade_period(data:CloseInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=_tenant(user)
    if not _admin(user):raise DomainError("PERMISSION_DENIED","Somente coordenação/direção pode fechar o período de notas.",403)
    group,period=_scope(request,user,data.academic_period_id,data.class_group_id,data.component_id);policy=_policy(request,tid,group["academic_year_id"],group["id"],data.component_id,period["starts_on"]);existing=request.state.store.fetch_one("SELECT * FROM grade_period_closures WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=?",(tid,period["id"],group["id"],data.component_id))
    if existing and existing["state"]=="closed":return {"id":existing["id"],"state":"closed","version":existing["version"],"idempotent":True}
    enrollments=request.state.store.fetch_all("SELECT * FROM enrollments WHERE tenant_id=? AND class_group_id=? AND state='active'",(tid,group["id"]));results=[]
    for enrollment in enrollments:
        current=request.state.store.fetch_one("SELECT recovery_score FROM period_results WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=? AND enrollment_id=?",(tid,period["id"],group["id"],data.component_id,enrollment["id"]));recovery=Decimal(str(current["recovery_score"])) if current and current["recovery_score"] is not None else None;results.append(_upsert_result(request,user,period,group,data.component_id,enrollment,policy,recovery))
    now=iso_now();cid=existing["id"] if existing else uuid7();version=(existing["version"]+1) if existing else 1
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE period_results SET state='closed',closed_at=?,closed_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=?",(now,user.id,now,tid,period["id"],group["id"],data.component_id));conn.execute("UPDATE assessments SET state='closed',version=version+1,updated_at=? WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=? AND state='published'",(now,tid,period["id"],group["id"],data.component_id))
        if existing:conn.execute("UPDATE grade_period_closures SET state='closed',version=?,reason=?,closed_by=?,closed_at=?,reopened_by=NULL,reopened_at=NULL,updated_at=? WHERE id=?",(version,data.reason,user.id,now,now,cid))
        else:conn.execute("INSERT INTO grade_period_closures(id,tenant_id,academic_period_id,class_group_id,component_id,state,version,reason,closed_by,closed_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(cid,tid,period["id"],group["id"],data.component_id,"closed",version,data.reason,user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="close",aggregate_type="grade_period",aggregate_id=cid,correlation_id=request.state.correlation_id,after={"state":"closed","results":len(results)},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="GradePeriodClosed",aggregate_type="grade_period",aggregate_id=cid,payload={"academic_period_id":period["id"],"class_group_id":group["id"],"component_id":data.component_id,"results":len(results)},correlation_id=request.state.correlation_id)
    return {"id":cid,"state":"closed","version":version,"results":len(results)}


@router.post("/pedagogy/grade-periods/reopen",operation_id="reopen_grade_period")
def reopen_grade_period(data:CloseInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid=_tenant(user)
    if not _admin(user):raise DomainError("PERMISSION_DENIED","Somente coordenação/direção pode reabrir o período de notas.",403)
    group,period=_scope(request,user,data.academic_period_id,data.class_group_id,data.component_id);row=request.state.store.fetch_one("SELECT * FROM grade_period_closures WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=?",(tid,period["id"],group["id"],data.component_id))
    if not row or row["state"]!="closed":raise DomainError("GRADE_PERIOD_NOT_CLOSED","Período de notas não está fechado.",409)
    now=iso_now();version=row["version"]+1
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE grade_period_closures SET state='reopened',version=?,reason=?,reopened_by=?,reopened_at=?,updated_at=? WHERE id=?",(version,data.reason,user.id,now,now,row["id"]));conn.execute("UPDATE period_results SET state='open',closed_at=NULL,closed_by=NULL,version=version+1,updated_at=? WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=?",(now,tid,period["id"],group["id"],data.component_id));conn.execute("UPDATE assessments SET state='published',version=version+1,updated_at=? WHERE tenant_id=? AND academic_period_id=? AND class_group_id=? AND component_id=? AND state='closed'",(now,tid,period["id"],group["id"],data.component_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="reopen",aggregate_type="grade_period",aggregate_id=row["id"],correlation_id=request.state.correlation_id,before=dict(row),after={"state":"reopened","version":version},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="GradePeriodReopened",aggregate_type="grade_period",aggregate_id=row["id"],payload={"state":"reopened","version":version},correlation_id=request.state.correlation_id)
    return {"id":row["id"],"state":"reopened","version":version}


@router.get("/pedagogy/students/{student_id}/report-card",operation_id="get_student_report_card")
def report_card(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=_tenant(user);assert_student_access(request,user,student_id);enrollments=request.state.store.fetch_all("SELECT e.*,cg.name AS class_name,ay.name AS academic_year_name,c.name AS curriculum_name FROM enrollments e LEFT JOIN class_groups cg ON cg.id=e.class_group_id LEFT JOIN academic_years ay ON ay.id=e.academic_year_id LEFT JOIN curricula c ON c.id=e.curriculum_id WHERE e.tenant_id=? AND e.student_id=? ORDER BY e.created_at DESC",(tid,student_id));cards=[]
    for enrollment in enrollments:
        results=request.state.store.fetch_all("SELECT pr.*,ap.name AS period_name,ap.sequence,cc.name AS component_name FROM period_results pr JOIN academic_periods ap ON ap.id=pr.academic_period_id JOIN curriculum_components cc ON cc.id=pr.component_id WHERE pr.tenant_id=? AND pr.enrollment_id=? ORDER BY ap.starts_on,cc.name",(tid,enrollment["id"]));cards.append({"enrollment":enrollment,"results":results})
    person=request.state.store.fetch_one("SELECT p.full_name,p.social_name,s.registration_number FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.id=?",(tid,student_id));return {"student_id":student_id,"student":person,"enrollments":cards,"generated_at":iso_now()}
