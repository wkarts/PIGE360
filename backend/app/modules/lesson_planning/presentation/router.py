from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["lesson-planning"])

PLAN_STATUSES = {
    "draft", "submitted_for_review", "changes_requested", "approved", "scheduled", "ready",
    "in_progress", "partially_executed", "executed", "rescheduled", "cancelled", "superseded", "archived",
}
PLAN_TYPES = {"annual", "semester", "trimester", "bimester", "monthly", "weekly", "didactic_unit", "sequence", "project", "lesson"}
EDITABLE_PLAN_STATUSES = {"draft", "changes_requested"}
LESSON_STATUSES = {"draft", "scheduled", "ready", "in_progress", "partially_executed", "executed", "rescheduled", "cancelled", "superseded", "archived"}


class TeachingPlanCreate(BaseModel):
    institution_id: str
    unit_id: str
    academic_period_id: str
    program_id: str | None = None
    curriculum_id: str
    class_group_id: str
    component_id: str
    teacher_ids: list[str] = Field(min_length=1)
    plan_type: str
    title: str = Field(min_length=3, max_length=300)
    start_date: date
    end_date: date
    duration_minutes: int | None = Field(default=None, ge=1)
    workload_hours: float | None = Field(default=None, ge=0)
    objectives: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    curriculum_links: list[dict[str, Any]] = Field(default_factory=list)
    content: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    accommodations: list[dict[str, Any]] = Field(default_factory=list)
    assessments: list[dict[str, Any]] = Field(default_factory=list)
    homework: list[dict[str, Any]] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    approval_required: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.plan_type not in PLAN_TYPES:
            raise ValueError(f"plan_type inválido: {self.plan_type}")
        if self.end_date < self.start_date:
            raise ValueError("end_date não pode anteceder start_date")
        if len(set(self.teacher_ids)) != len(self.teacher_ids):
            raise ValueError("teacher_ids contém duplicidade")
        return self


class TeachingPlanPatch(BaseModel):
    expected_version: int = Field(ge=1)
    changes: dict[str, Any]
    reason: str = Field(min_length=3, max_length=2000)


class ActionInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)
    comments: str | None = Field(default=None, max_length=4000)


class DuplicateInput(BaseModel):
    title: str | None = None
    academic_period_id: str | None = None
    class_group_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ScheduledLesson(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime
    modality: Literal["regular", "practical", "laboratory", "remote", "hybrid", "replacement", "external"] = "regular"
    room_id: str | None = None
    teacher_ids: list[str] | None = None
    title: str | None = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end deve ser posterior a scheduled_start")
        return self


class ScheduleInput(BaseModel):
    expected_version: int = Field(ge=1)
    sessions: list[ScheduledLesson] = Field(min_length=1, max_length=500)


class LessonPlanCreate(BaseModel):
    teaching_plan_id: str | None = None
    class_group_id: str
    component_id: str
    scheduled_start: datetime
    scheduled_end: datetime
    title: str = Field(min_length=3, max_length=300)
    teacher_ids: list[str] = Field(min_length=1)
    modality: str = "regular"
    room_id: str | None = None
    objectives: list[str] = Field(default_factory=list)
    planned_content: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    accommodations: list[dict[str, Any]] = Field(default_factory=list)
    assessments: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end deve ser posterior a scheduled_start")
        return self


class LessonPatch(BaseModel):
    expected_version: int = Field(ge=1)
    changes: dict[str, Any]
    reason: str = Field(min_length=3)


class CompleteLessonInput(BaseModel):
    expected_version: int = Field(ge=1)
    completion_percentage: int = Field(ge=0, le=100)
    delivered_content: list[str] = Field(default_factory=list)
    pending_content: list[str] = Field(default_factory=list)
    additional_content: list[str] = Field(default_factory=list)
    notes: str | None = None


class RescheduleLessonInput(BaseModel):
    expected_version: int = Field(ge=1)
    new_start: datetime
    new_end: datetime
    reason: str = Field(min_length=3)

    @model_validator(mode="after")
    def validate_times(self):
        if self.new_end <= self.new_start:
            raise ValueError("new_end deve ser posterior a new_start")
        return self


def _authorize(user: CurrentUser, *, review: bool = False) -> str:
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Rota disponível somente no domínio da instituição.", 404)
    allowed = {"teacher", "assistant_teacher", "academic_coordinator", "institution_director", "tenant_owner"}
    if review:
        allowed = {"academic_coordinator", "institution_director", "tenant_owner"}
    if not set(user.roles).intersection(allowed):
        raise DomainError("PERMISSION_DENIED", "Permissão insuficiente no planejamento pedagógico.", 403)
    return user.tenant_id


ADMIN_PLANNING_ROLES = {"academic_coordinator", "institution_director", "tenant_owner"}


def _is_planning_admin(user: CurrentUser) -> bool:
    return bool(set(user.roles).intersection(ADMIN_PLANNING_ROLES))


def _teacher_assignment(request: Request, user: CurrentUser, tenant_id: str, class_group_id: str, component_id: str, on_date: str | None = None):
    if _is_planning_admin(user):
        return {"admin": True}
    if not user.person_id:
        raise DomainError("PERSON_LINK_REQUIRED", "A conta docente precisa estar vinculada a uma pessoa.", 403)
    query = """SELECT ta.id FROM teacher_assignments ta
               JOIN employees e ON e.id=ta.employee_id AND e.tenant_id=ta.tenant_id
              WHERE ta.tenant_id=? AND e.person_id=? AND e.state='active'
                AND ta.class_group_id=? AND ta.component_id=? AND ta.state='active'"""
    params: list[Any] = [tenant_id, user.person_id, class_group_id, component_id]
    if on_date:
        query += " AND ta.starts_on<=? AND (ta.ends_on IS NULL OR ta.ends_on>=?)"
        params.extend([on_date, on_date])
    row = request.state.store.fetch_one(query, params)
    if not row:
        raise DomainError("TEACHER_NOT_ASSIGNED", "Professor não possui atribuição ativa para a turma/componente.", 403)
    return row


def _validate_teacher_ids(request: Request, tenant_id: str, teacher_ids: list[str], class_group_id: str, component_id: str, on_date: str) -> None:
    for teacher_id in teacher_ids:
        row = request.state.store.fetch_one("SELECT person_id,roles_json,active FROM users WHERE tenant_id=? AND id=?", (tenant_id, teacher_id))
        if not row or not row["active"] or not row["person_id"]:
            raise DomainError("TEACHER_NOT_ASSIGNED", "Usuário docente informado não é válido.", 409)
        roles = set(json.loads(row["roles_json"] or "[]"))
        if not roles.intersection({"teacher", "assistant_teacher"}):
            raise DomainError("TEACHER_NOT_ASSIGNED", "Usuário informado não possui perfil docente.", 409)
        assignment = request.state.store.fetch_one(
            """SELECT ta.id FROM teacher_assignments ta JOIN employees e ON e.id=ta.employee_id AND e.tenant_id=ta.tenant_id
                 WHERE ta.tenant_id=? AND e.person_id=? AND e.state='active' AND ta.class_group_id=? AND ta.component_id=?
                   AND ta.state='active' AND ta.starts_on<=? AND (ta.ends_on IS NULL OR ta.ends_on>=?)""",
            (tenant_id, row["person_id"], class_group_id, component_id, on_date, on_date),
        )
        if not assignment:
            raise DomainError("TEACHER_NOT_ASSIGNED", "Professor informado não possui atribuição ativa para a turma/componente.", 409)


def _validate_plan_context(request: Request, user: CurrentUser, tenant_id: str, data: TeachingPlanCreate) -> None:
    group = request.state.store.fetch_one(
        """SELECT cg.unit_id,cg.academic_year_id,cg.program_id,cg.curriculum_id,u.institution_id
             FROM class_groups cg JOIN units u ON u.id=cg.unit_id AND u.tenant_id=cg.tenant_id
            WHERE cg.id=? AND cg.tenant_id=? AND cg.state='active'""", (data.class_group_id, tenant_id))
    if not group:
        raise DomainError("CLASS_GROUP_NOT_FOUND", "Turma ativa não localizada.", 404)
    expected = (group["institution_id"], group["unit_id"], group["program_id"], group["curriculum_id"])
    supplied = (data.institution_id, data.unit_id, data.program_id, data.curriculum_id)
    if expected != supplied:
        raise DomainError("PLAN_ACADEMIC_SCOPE_MISMATCH", "O contexto acadêmico do plano diverge da turma selecionada.", 409)
    period = request.state.store.fetch_one(
        "SELECT academic_year_id,starts_on,ends_on,state FROM academic_periods WHERE tenant_id=? AND id=?",
        (tenant_id, data.academic_period_id),
    )
    if not period or period["state"] != "active" or period["academic_year_id"] != group["academic_year_id"]:
        raise DomainError("ACADEMIC_PERIOD_SCOPE_MISMATCH", "O período acadêmico não pertence ao ano letivo da turma.", 409)
    if str(data.start_date) < str(period["starts_on"]) or str(data.end_date) > str(period["ends_on"]):
        raise DomainError("PLAN_OUTSIDE_ACADEMIC_PERIOD", "As datas do plano devem estar contidas no período acadêmico selecionado.", 409)
    component = request.state.store.fetch_one("SELECT curriculum_id FROM curriculum_components WHERE tenant_id=? AND id=? AND state='active'", (tenant_id, data.component_id))
    if not component or component["curriculum_id"] != data.curriculum_id:
        raise DomainError("COMPONENT_SCOPE_MISMATCH", "Componente não pertence ao currículo da turma.", 409)
    _teacher_assignment(request, user, tenant_id, data.class_group_id, data.component_id, str(data.start_date))
    if not _is_planning_admin(user) and user.id not in data.teacher_ids:
        raise DomainError("TEACHER_IDENTITY_MISMATCH", "O professor deve constar entre os docentes do próprio plano.", 403)
    _validate_teacher_ids(request, tenant_id, data.teacher_ids, data.class_group_id, data.component_id, str(data.start_date))


def _assert_plan_access(request: Request, user: CurrentUser, row: dict[str, Any]) -> None:
    _teacher_assignment(request, user, row["tenant_id"], row["class_group_id"], row["component_id"], row["start_date"])


def _assert_lesson_access(request: Request, user: CurrentUser, row: dict[str, Any]) -> None:
    day = str(row["scheduled_start"])[:10]
    _teacher_assignment(request, user, row["tenant_id"], row["class_group_id"], row["component_id"], day)


def _plan(row: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    return {
        "id": row["id"], "tenant_id": row["tenant_id"], "institution_id": row["institution_id"],
        "unit_id": row["unit_id"], "academic_period_id": row["academic_period_id"], "program_id": row["program_id"],
        "curriculum_id": row["curriculum_id"], "class_group_id": row["class_group_id"], "component_id": row["component_id"],
        "title": row["title"], "plan_type": row["plan_type"], "start_date": row["start_date"], "end_date": row["end_date"],
        "status": row["status"], "current_version": row["current_version"], "approval_required": bool(row["approval_required"]),
        "payload": payload, "created_by": row["created_by"], "updated_by": row["updated_by"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _lesson(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "tenant_id": row["tenant_id"], "teaching_plan_id": row["teaching_plan_id"],
        "class_group_id": row["class_group_id"], "component_id": row["component_id"],
        "scheduled_start": row["scheduled_start"], "scheduled_end": row["scheduled_end"],
        "status": row["status"], "current_version": row["current_version"], "payload": json.loads(row["payload_json"]),
        "created_by": row["created_by"], "updated_by": row["updated_by"], "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _fetch_plan(request: Request, tenant_id: str, plan_id: str):
    row = request.state.store.fetch_one("SELECT * FROM teaching_plans WHERE id=? AND tenant_id=?", (plan_id, tenant_id))
    if not row:
        raise DomainError("TEACHING_PLAN_NOT_FOUND", "Plano de ensino não localizado.", 404)
    return row


def _fetch_lesson(request: Request, tenant_id: str, lesson_id: str):
    row = request.state.store.fetch_one("SELECT * FROM lesson_plans WHERE id=? AND tenant_id=?", (lesson_id, tenant_id))
    if not row:
        raise DomainError("LESSON_PLAN_NOT_FOUND", "Plano de aula não localizado.", 404)
    return row


@router.get("/teaching-plans", operation_id="list_teaching_plans")
def list_teaching_plans(request: Request, status: str | None = None, class_group_id: str | None = None,
                        component_id: str | None = None, limit: int = 100,
                        user: CurrentUser = Depends(current_user)):
    tenant_id = _authorize(user); limit=min(max(limit,1),500)
    sql="SELECT * FROM teaching_plans WHERE tenant_id=?"; params: list[Any]=[tenant_id]
    for field,value in (("status",status),("class_group_id",class_group_id),("component_id",component_id)):
        if value: sql+=f" AND {field}=?"; params.append(value)
    sql+=" ORDER BY updated_at DESC LIMIT ?"; params.append(min(limit * 5, 1000))
    rows=request.state.store.fetch_all(sql,params)
    if not _is_planning_admin(user):
        visible=[]
        for row in rows:
            try:
                _assert_plan_access(request,user,row); visible.append(row)
            except DomainError:
                pass
        rows=visible
    return {"items":[_plan(x) for x in rows[:limit]],"limit":limit}


@router.post("/teaching-plans", operation_id="create_teaching_plan", status_code=201)
def create_teaching_plan(data: TeachingPlanCreate, request: Request, response: Response,
                         idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
                         user: CurrentUser = Depends(current_user)):
    tenant_id=_authorize(user); _validate_plan_context(request,user,tenant_id,data); body=data.model_dump(mode="json"); now=iso_now(); plan_id=uuid7(); version_id=uuid7()
    result={"id":plan_id,"tenant_id":tenant_id,"institution_id":data.institution_id,"unit_id":data.unit_id,
            "academic_period_id":data.academic_period_id,"program_id":data.program_id,"curriculum_id":data.curriculum_id,
            "class_group_id":data.class_group_id,"component_id":data.component_id,"title":data.title,"plan_type":data.plan_type,
            "start_date":str(data.start_date),"end_date":str(data.end_date),"status":"draft","current_version":1,
            "approval_required":data.approval_required,"payload":body,"created_by":user.id,"updated_by":user.id,"created_at":now,"updated_at":now}
    scope=f"teaching-plan:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached: response.status_code=cached[0]; return cached[1]
        conn.execute("""INSERT INTO teaching_plans(id,tenant_id,institution_id,unit_id,academic_period_id,program_id,curriculum_id,class_group_id,component_id,title,plan_type,start_date,end_date,status,current_version,approval_required,payload_json,created_by,updated_by,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (plan_id,tenant_id,data.institution_id,data.unit_id,data.academic_period_id,data.program_id,data.curriculum_id,data.class_group_id,data.component_id,data.title,data.plan_type,str(data.start_date),str(data.end_date),"draft",1,int(data.approval_required),json.dumps(body,ensure_ascii=False,sort_keys=True),user.id,user.id,now,now))
        conn.execute("INSERT INTO teaching_plan_versions(id,tenant_id,teaching_plan_id,version,status,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (version_id,tenant_id,plan_id,1,"draft",json.dumps(body,ensure_ascii=False,sort_keys=True),user.id,now))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="create",aggregate_type="teaching_plan",aggregate_id=plan_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="TeachingPlanCreated",aggregate_type="teaching_plan",aggregate_id=plan_id,payload=result,correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,body,201,result)
    response.status_code=201; response.headers["ETag"]='"1"'; return result


@router.get("/teaching-plans/{plan_id}", operation_id="get_teaching_plan")
def get_teaching_plan(plan_id: str, request: Request, response: Response, user: CurrentUser = Depends(current_user)):
    tenant_id=_authorize(user); row=_fetch_plan(request,tenant_id,plan_id); _assert_plan_access(request,user,row)
    result=_plan(row)
    result["versions"]=request.state.store.fetch_all("SELECT id,version,status,change_reason,created_by,created_at FROM teaching_plan_versions WHERE teaching_plan_id=? ORDER BY version",(plan_id,))
    result["approvals"]=request.state.store.fetch_all("SELECT id,version,decision,comments,actor_id,created_at FROM teaching_plan_approvals WHERE teaching_plan_id=? ORDER BY created_at",(plan_id,))
    response.headers["ETag"]=f'"{row["current_version"]}"'; return result


@router.patch("/teaching-plans/{plan_id}", operation_id="patch_teaching_plan")
def patch_teaching_plan(plan_id: str, data: TeachingPlanPatch, request: Request, response: Response,
                        user: CurrentUser = Depends(current_user)):
    tenant_id=_authorize(user); now=iso_now()
    forbidden={"id","tenant_id","status","current_version","created_by","created_at"}
    if forbidden.intersection(data.changes): raise DomainError("IMMUTABLE_FIELD","A alteração contém campos imutáveis.",422)
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM teaching_plans WHERE id=? AND tenant_id=?",(plan_id,tenant_id)).fetchone()
        if not row: raise DomainError("TEACHING_PLAN_NOT_FOUND","Plano de ensino não localizado.",404)
        _assert_plan_access(request,user,dict(row))
        if row["status"] not in EDITABLE_PLAN_STATUSES: raise DomainError("PLAN_NOT_EDITABLE","Crie nova versão para alterar um plano já submetido ou executado.",409)
        if row["current_version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","O plano foi alterado por outra operação.",409)
        before=_plan(dict(row)); payload={**json.loads(row["payload_json"]),**data.changes}; version=row["current_version"]+1
        title=str(payload.get("title",row["title"])); start=str(payload.get("start_date",row["start_date"])); end=str(payload.get("end_date",row["end_date"]))
        conn.execute("UPDATE teaching_plans SET title=?,start_date=?,end_date=?,payload_json=?,current_version=?,updated_by=?,updated_at=? WHERE id=?",
                     (title,start,end,json.dumps(payload,ensure_ascii=False,sort_keys=True),version,user.id,now,plan_id))
        conn.execute("INSERT INTO teaching_plan_versions(id,tenant_id,teaching_plan_id,version,status,snapshot_json,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (uuid7(),tenant_id,plan_id,version,row["status"],json.dumps(payload,ensure_ascii=False,sort_keys=True),data.reason,user.id,now))
        result={**before,"title":title,"start_date":start,"end_date":end,"payload":payload,"current_version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="update",aggregate_type="teaching_plan",aggregate_id=plan_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="TeachingPlanVersionCreated",aggregate_type="teaching_plan",aggregate_id=plan_id,payload=result,correlation_id=request.state.correlation_id)
    response.headers["ETag"]=f'"{version}"'; return result


@router.post("/teaching-plans/{plan_id}/versions", operation_id="create_teaching_plan_version")
def create_version(plan_id: str, data: TeachingPlanPatch, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id=_authorize(user); row=_fetch_plan(request,tenant_id,plan_id); _assert_plan_access(request,user,row)
    if row["status"] in {"executed","archived","cancelled"}:
        raise DomainError("PLAN_IMMUTABLE","Plano consolidado requer complemento ou duplicação, não alteração retroativa.",409)
    # Reuse patch semantics only after returning to draft through an explicit superseding version.
    with request.state.store.transaction() as conn:
        current=conn.execute("SELECT * FROM teaching_plans WHERE id=? AND tenant_id=?",(plan_id,tenant_id)).fetchone()
        if current["current_version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        before=_plan(dict(current)); payload={**json.loads(current["payload_json"]),**data.changes}; version=current["current_version"]+1; now=iso_now()
        conn.execute("UPDATE teaching_plans SET status='draft',payload_json=?,current_version=?,updated_by=?,updated_at=? WHERE id=?",(json.dumps(payload,ensure_ascii=False,sort_keys=True),version,user.id,now,plan_id))
        conn.execute("INSERT INTO teaching_plan_versions(id,tenant_id,teaching_plan_id,version,status,snapshot_json,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,plan_id,version,"draft",json.dumps(payload,ensure_ascii=False,sort_keys=True),data.reason,user.id,now))
        result={**before,"status":"draft","payload":payload,"current_version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="new_version",aggregate_type="teaching_plan",aggregate_id=plan_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="TeachingPlanVersionCreated",aggregate_type="teaching_plan",aggregate_id=plan_id,payload=result,correlation_id=request.state.correlation_id)
    return result


def _transition_plan(plan_id: str, data: ActionInput, request: Request, user: CurrentUser, *, expected: set[str], target: str, event: str, review: bool=False):
    tenant_id=_authorize(user,review=review); now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM teaching_plans WHERE id=? AND tenant_id=?",(plan_id,tenant_id)).fetchone()
        if not row: raise DomainError("TEACHING_PLAN_NOT_FOUND","Plano de ensino não localizado.",404)
        _assert_plan_access(request,user,dict(row))
        if row["current_version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] not in expected: raise DomainError("INVALID_STATE_TRANSITION",f"Não é possível mudar {row['status']} para {target}.",409)
        before=_plan(dict(row)); version=row["current_version"]+1
        conn.execute("UPDATE teaching_plans SET status=?,current_version=?,updated_by=?,updated_at=? WHERE id=?",(target,version,user.id,now,plan_id))
        conn.execute("INSERT INTO teaching_plan_versions(id,tenant_id,teaching_plan_id,version,status,snapshot_json,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,plan_id,version,target,row["payload_json"],data.reason,user.id,now))
        if target in {"approved","changes_requested"}:
            conn.execute("INSERT INTO teaching_plan_approvals(id,tenant_id,teaching_plan_id,version,decision,comments,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,plan_id,version,target,data.comments,user.id,now))
        result={**before,"status":target,"current_version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action=target,aggregate_type="teaching_plan",aggregate_id=plan_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type=event,aggregate_type="teaching_plan",aggregate_id=plan_id,payload={**result,"comments":data.comments},correlation_id=request.state.correlation_id)
    return result


@router.post("/teaching-plans/{plan_id}/submit", operation_id="submit_teaching_plan")
def submit_plan(plan_id: str, data: ActionInput, request: Request, user: CurrentUser = Depends(current_user)):
    return _transition_plan(plan_id,data,request,user,expected={"draft","changes_requested"},target="submitted_for_review",event="TeachingPlanSubmitted")

@router.post("/teaching-plans/{plan_id}/approve", operation_id="approve_teaching_plan")
def approve_plan(plan_id: str, data: ActionInput, request: Request, user: CurrentUser = Depends(current_user)):
    return _transition_plan(plan_id,data,request,user,expected={"submitted_for_review"},target="approved",event="TeachingPlanApproved",review=True)

@router.post("/teaching-plans/{plan_id}/request-changes", operation_id="request_teaching_plan_changes")
def request_changes(plan_id: str, data: ActionInput, request: Request, user: CurrentUser = Depends(current_user)):
    return _transition_plan(plan_id,data,request,user,expected={"submitted_for_review"},target="changes_requested",event="TeachingPlanChangesRequested",review=True)

@router.post("/teaching-plans/{plan_id}/archive", operation_id="archive_teaching_plan")
def archive_plan(plan_id: str, data: ActionInput, request: Request, user: CurrentUser = Depends(current_user)):
    return _transition_plan(plan_id,data,request,user,expected={"draft","cancelled","superseded","executed"},target="archived",event="TeachingPlanArchived",review=True)


@router.post("/teaching-plans/{plan_id}/duplicate", operation_id="duplicate_teaching_plan", status_code=201)
def duplicate_plan(plan_id: str, data: DuplicateInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id=_authorize(user); source=_fetch_plan(request,tenant_id,plan_id); _assert_plan_access(request,user,source); payload=json.loads(source["payload_json"]); now=iso_now(); new_id=uuid7()
    payload.update({k:v for k,v in data.model_dump(mode="json").items() if v is not None})
    payload["title"]=data.title or f"{source['title']} — cópia"
    start=str(data.start_date or source["start_date"]); end=str(data.end_date or source["end_date"]); period=data.academic_period_id or source["academic_period_id"]; group=data.class_group_id or source["class_group_id"]
    target_group=request.state.store.fetch_one(
        """SELECT cg.unit_id,cg.academic_year_id,cg.program_id,cg.curriculum_id,u.institution_id
             FROM class_groups cg JOIN units u ON u.id=cg.unit_id AND u.tenant_id=cg.tenant_id
            WHERE cg.tenant_id=? AND cg.id=? AND cg.state='active'""",(tenant_id,group))
    if not target_group: raise DomainError("CLASS_GROUP_NOT_FOUND","Turma de destino não localizada.",404)
    target_period=request.state.store.fetch_one("SELECT academic_year_id,starts_on,ends_on,state FROM academic_periods WHERE tenant_id=? AND id=?",(tenant_id,period))
    if not target_period or target_period["state"]!='active' or target_period["academic_year_id"]!=target_group["academic_year_id"]:
        raise DomainError("ACADEMIC_PERIOD_SCOPE_MISMATCH","Período acadêmico incompatível com a turma de destino.",409)
    if start < str(target_period["starts_on"]) or end > str(target_period["ends_on"]):
        raise DomainError("PLAN_OUTSIDE_ACADEMIC_PERIOD","Datas da cópia fora do período acadêmico selecionado.",409)
    component=request.state.store.fetch_one("SELECT curriculum_id FROM curriculum_components WHERE tenant_id=? AND id=? AND state='active'",(tenant_id,source["component_id"]))
    if not component or component["curriculum_id"]!=target_group["curriculum_id"]:
        raise DomainError("COMPONENT_SCOPE_MISMATCH","Componente não pertence ao currículo da turma de destino.",409)
    _teacher_assignment(request,user,tenant_id,group,source["component_id"],start)
    with request.state.store.transaction() as conn:
        conn.execute("""INSERT INTO teaching_plans(id,tenant_id,institution_id,unit_id,academic_period_id,program_id,curriculum_id,class_group_id,component_id,title,plan_type,start_date,end_date,status,current_version,approval_required,payload_json,created_by,updated_by,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (new_id,tenant_id,target_group["institution_id"],target_group["unit_id"],period,target_group["program_id"],target_group["curriculum_id"],group,source["component_id"],payload["title"],source["plan_type"],start,end,"draft",1,source["approval_required"],json.dumps(payload,ensure_ascii=False,sort_keys=True),user.id,user.id,now,now))
        conn.execute("INSERT INTO teaching_plan_versions(id,tenant_id,teaching_plan_id,version,status,snapshot_json,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,new_id,1,"draft",json.dumps(payload,ensure_ascii=False,sort_keys=True),f"Duplicado de {plan_id}",user.id,now))
        result=_plan(dict(conn.execute("SELECT * FROM teaching_plans WHERE id=?",(new_id,)).fetchone()))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="duplicate",aggregate_type="teaching_plan",aggregate_id=new_id,correlation_id=request.state.correlation_id,after=result,reason=f"Origem {plan_id}")
        add_outbox(conn,tenant_id=tenant_id,event_type="TeachingPlanCreated",aggregate_type="teaching_plan",aggregate_id=new_id,payload={**result,"source_plan_id":plan_id},correlation_id=request.state.correlation_id)
    return result


@router.post("/teaching-plans/{plan_id}/schedule", operation_id="schedule_teaching_plan")
def schedule_plan(plan_id: str, data: ScheduleInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id=_authorize(user); now=iso_now(); created=[]
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM teaching_plans WHERE id=? AND tenant_id=?",(plan_id,tenant_id)).fetchone()
        if not row: raise DomainError("TEACHING_PLAN_NOT_FOUND","Plano de ensino não localizado.",404)
        _assert_plan_access(request,user,dict(row))
        if row["current_version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] not in {"approved","scheduled"}: raise DomainError("PLAN_NOT_APPROVED","O plano deve estar aprovado para agendamento.",409)
        plan_payload=json.loads(row["payload_json"])
        for item in data.sessions:
            session_teachers=item.teacher_ids or plan_payload.get("teacher_ids",[])
            _validate_teacher_ids(request,tenant_id,session_teachers,row["class_group_id"],row["component_id"],item.scheduled_start.date().isoformat())
            if not _is_planning_admin(user) and user.id not in session_teachers:
                raise DomainError("TEACHER_IDENTITY_MISMATCH","O professor deve constar na aula que está agendando.",403)
            lesson_id=uuid7(); lp={"title":item.title or row["title"],"teacher_ids":session_teachers,"modality":item.modality,"room_id":item.room_id,"objectives":plan_payload.get("objectives",[]),"planned_content":plan_payload.get("content",[]),"methodologies":plan_payload.get("methodologies",[]),"resources":plan_payload.get("resources",[]),"accommodations":plan_payload.get("accommodations",[]),"assessments":plan_payload.get("assessments",[])}
            conn.execute("INSERT INTO lesson_plans(id,tenant_id,teaching_plan_id,class_group_id,component_id,scheduled_start,scheduled_end,status,current_version,payload_json,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(lesson_id,tenant_id,plan_id,row["class_group_id"],row["component_id"],item.scheduled_start.isoformat(),item.scheduled_end.isoformat(),"scheduled",1,json.dumps(lp,ensure_ascii=False,sort_keys=True),user.id,user.id,now,now))
            conn.execute("INSERT INTO lesson_plan_versions(id,tenant_id,lesson_plan_id,version,status,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,lesson_id,1,"scheduled",json.dumps(lp,ensure_ascii=False,sort_keys=True),user.id,now))
            created.append({"id":lesson_id,"scheduled_start":item.scheduled_start.isoformat(),"scheduled_end":item.scheduled_end.isoformat(),"status":"scheduled"})
            add_outbox(conn,tenant_id=tenant_id,event_type="LessonPlanScheduled",aggregate_type="lesson_plan",aggregate_id=lesson_id,payload=created[-1],correlation_id=request.state.correlation_id)
        version=row["current_version"]+1
        conn.execute("UPDATE teaching_plans SET status='scheduled',current_version=?,updated_by=?,updated_at=? WHERE id=?",(version,user.id,now,plan_id))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="schedule",aggregate_type="teaching_plan",aggregate_id=plan_id,correlation_id=request.state.correlation_id,before=_plan(dict(row)),after={"status":"scheduled","lessons":created})
    return {"teaching_plan_id":plan_id,"status":"scheduled","current_version":version,"lessons":created}


@router.get("/lesson-plans", operation_id="list_lesson_plans")
def list_lessons(request: Request, teaching_plan_id: str | None=None, status: str | None=None, limit: int=100,
                 user: CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user); sql="SELECT * FROM lesson_plans WHERE tenant_id=?"; params: list[Any]=[tenant_id]
    if teaching_plan_id: sql+=" AND teaching_plan_id=?";params.append(teaching_plan_id)
    if status: sql+=" AND status=?";params.append(status)
    sql+=" ORDER BY scheduled_start LIMIT ?";params.append(min(max(limit*5,limit),1000))
    rows=request.state.store.fetch_all(sql,params)
    if not _is_planning_admin(user):
        visible=[]
        for row in rows:
            try:
                _assert_lesson_access(request,user,row); visible.append(row)
            except DomainError:
                pass
        rows=visible
    return {"items":[_lesson(x) for x in rows[:limit]]}


@router.post("/lesson-plans", operation_id="create_lesson_plan", status_code=201)
def create_lesson(data: LessonPlanCreate, request: Request, user: CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user); body=data.model_dump(mode="json"); now=iso_now(); lesson_id=uuid7()
    _teacher_assignment(request,user,tenant_id,data.class_group_id,data.component_id,data.scheduled_start.date().isoformat())
    if not _is_planning_admin(user) and user.id not in data.teacher_ids:
        raise DomainError("TEACHER_IDENTITY_MISMATCH","O professor deve constar na própria aula.",403)
    _validate_teacher_ids(request,tenant_id,data.teacher_ids,data.class_group_id,data.component_id,data.scheduled_start.date().isoformat())
    if data.teaching_plan_id:
        plan=_fetch_plan(request,tenant_id,data.teaching_plan_id)
        if plan["class_group_id"]!=data.class_group_id or plan["component_id"]!=data.component_id:
            raise DomainError("PLAN_SCOPE_MISMATCH","Turma ou componente diverge do plano de ensino.",409)
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO lesson_plans(id,tenant_id,teaching_plan_id,class_group_id,component_id,scheduled_start,scheduled_end,status,current_version,payload_json,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(lesson_id,tenant_id,data.teaching_plan_id,data.class_group_id,data.component_id,data.scheduled_start.isoformat(),data.scheduled_end.isoformat(),"draft",1,json.dumps(body,ensure_ascii=False,sort_keys=True),user.id,user.id,now,now))
        conn.execute("INSERT INTO lesson_plan_versions(id,tenant_id,lesson_plan_id,version,status,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,lesson_id,1,"draft",json.dumps(body,ensure_ascii=False,sort_keys=True),user.id,now))
        result=_lesson(dict(conn.execute("SELECT * FROM lesson_plans WHERE id=?",(lesson_id,)).fetchone()))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="create",aggregate_type="lesson_plan",aggregate_id=lesson_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="LessonPlanCreated",aggregate_type="lesson_plan",aggregate_id=lesson_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/lesson-plans/{lesson_id}", operation_id="get_lesson_plan")
def get_lesson(lesson_id: str, request: Request, response: Response, user: CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user); row=_fetch_lesson(request,tenant_id,lesson_id); _assert_lesson_access(request,user,row); result=_lesson(row)
    result["execution"]=request.state.store.fetch_one("SELECT * FROM lesson_plan_execution_records WHERE lesson_plan_id=?",(lesson_id,))
    response.headers["ETag"]=f'"{row["current_version"]}"';return result


@router.patch("/lesson-plans/{lesson_id}", operation_id="patch_lesson_plan")
def patch_lesson(lesson_id: str,data:LessonPatch,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM lesson_plans WHERE id=? AND tenant_id=?",(lesson_id,tenant_id)).fetchone()
        if not row:raise DomainError("LESSON_PLAN_NOT_FOUND","Plano de aula não localizado.",404)
        _assert_lesson_access(request,user,dict(row))
        if row["current_version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] not in {"draft","scheduled","ready"}:raise DomainError("LESSON_NOT_EDITABLE","A aula iniciada ou consolidada não pode ser alterada.",409)
        before=_lesson(dict(row));payload={**json.loads(row["payload_json"]),**data.changes};version=row["current_version"]+1
        conn.execute("UPDATE lesson_plans SET payload_json=?,current_version=?,updated_by=?,updated_at=? WHERE id=?",(json.dumps(payload,ensure_ascii=False,sort_keys=True),version,user.id,now,lesson_id))
        conn.execute("INSERT INTO lesson_plan_versions(id,tenant_id,lesson_plan_id,version,status,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,lesson_id,version,row["status"],json.dumps(payload,ensure_ascii=False,sort_keys=True),user.id,now))
        result={**before,"payload":payload,"current_version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="update",aggregate_type="lesson_plan",aggregate_id=lesson_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=data.reason)
    return result


def _transition_lesson(lesson_id:str,expected_version:int,reason:str,request:Request,user:CurrentUser,expected:set[str],target:str,event:str):
    tenant_id=_authorize(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM lesson_plans WHERE id=? AND tenant_id=?",(lesson_id,tenant_id)).fetchone()
        if not row:raise DomainError("LESSON_PLAN_NOT_FOUND","Plano de aula não localizado.",404)
        if row["current_version"]!=expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] not in expected:raise DomainError("INVALID_STATE_TRANSITION",f"Não é possível mudar {row['status']} para {target}.",409)
        before=_lesson(dict(row));version=row["current_version"]+1
        conn.execute("UPDATE lesson_plans SET status=?,current_version=?,updated_by=?,updated_at=? WHERE id=?",(target,version,user.id,now,lesson_id))
        result={**before,"status":target,"current_version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action=target,aggregate_type="lesson_plan",aggregate_id=lesson_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=reason)
        add_outbox(conn,tenant_id=tenant_id,event_type=event,aggregate_type="lesson_plan",aggregate_id=lesson_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/lesson-plans/{lesson_id}/start", operation_id="start_lesson_plan")
def start_lesson(lesson_id:str,data:ActionInput,request:Request,user:CurrentUser=Depends(current_user)):
    return _transition_lesson(lesson_id,data.expected_version,data.reason,request,user,{"draft","scheduled","ready"},"in_progress","LessonStarted")


@router.post("/lesson-plans/{lesson_id}/complete", operation_id="complete_lesson_plan")
def complete_lesson(lesson_id:str,data:CompleteLessonInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user);now=iso_now();target="executed" if data.completion_percentage==100 else ("partially_executed" if data.completion_percentage>0 else "ready")
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM lesson_plans WHERE id=? AND tenant_id=?",(lesson_id,tenant_id)).fetchone()
        if not row:raise DomainError("LESSON_PLAN_NOT_FOUND","Plano de aula não localizado.",404)
        _assert_lesson_access(request,user,dict(row))
        if row["current_version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"]!="in_progress":raise DomainError("LESSON_NOT_STARTED","A aula precisa estar iniciada.",409)
        if conn.execute("SELECT id FROM lesson_plan_execution_records WHERE lesson_plan_id=?",(lesson_id,)).fetchone():raise DomainError("EXECUTION_ALREADY_RECORDED","A execução já foi registrada; use complemento versionado.",409)
        payload=json.loads(row["payload_json"]);execution_id=uuid7();version=row["current_version"]+1
        conn.execute("INSERT INTO lesson_plan_execution_records(id,tenant_id,lesson_plan_id,execution_status,completion_percentage,planned_content_json,delivered_content_json,pending_content_json,additional_content_json,notes,executed_by,executed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(execution_id,tenant_id,lesson_id,target,data.completion_percentage,json.dumps(payload.get("planned_content",[]),ensure_ascii=False),json.dumps(data.delivered_content,ensure_ascii=False),json.dumps(data.pending_content,ensure_ascii=False),json.dumps(data.additional_content,ensure_ascii=False),data.notes,user.id,now))
        conn.execute("UPDATE lesson_plans SET status=?,current_version=?,updated_by=?,updated_at=? WHERE id=?",(target,version,user.id,now,lesson_id))
        result={"lesson_plan_id":lesson_id,"execution_id":execution_id,"status":target,"current_version":version,"completion_percentage":data.completion_percentage,"delivered_content":data.delivered_content,"pending_content":data.pending_content,"additional_content":data.additional_content,"executed_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="complete",aggregate_type="lesson_plan",aggregate_id=lesson_id,correlation_id=request.state.correlation_id,before=_lesson(dict(row)),after=result)
        event="LessonCompleted" if target=="executed" else "LessonPartiallyExecuted"
        add_outbox(conn,tenant_id=tenant_id,event_type=event,aggregate_type="lesson_plan",aggregate_id=lesson_id,payload=result,correlation_id=request.state.correlation_id)
        if row["teaching_plan_id"]:
            add_outbox(conn,tenant_id=tenant_id,event_type="CurriculumCoverageUpdated",aggregate_type="teaching_plan",aggregate_id=row["teaching_plan_id"],payload={"lesson_plan_id":lesson_id,"completion_percentage":data.completion_percentage},correlation_id=request.state.correlation_id)
    return result


@router.post("/lesson-plans/{lesson_id}/reschedule", operation_id="reschedule_lesson_plan")
def reschedule_lesson(lesson_id:str,data:RescheduleLessonInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user);now=iso_now();new_id=uuid7()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM lesson_plans WHERE id=? AND tenant_id=?",(lesson_id,tenant_id)).fetchone()
        if not row:raise DomainError("LESSON_PLAN_NOT_FOUND","Plano de aula não localizado.",404)
        _assert_lesson_access(request,user,dict(row))
        if row["current_version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] in {"executed","cancelled","archived","rescheduled"}:raise DomainError("LESSON_NOT_RESCHEDULABLE","Aula não pode ser reagendada neste estado.",409)
        payload=json.loads(row["payload_json"]);payload["rescheduled_from_id"]=lesson_id
        conn.execute("UPDATE lesson_plans SET status='rescheduled',current_version=current_version+1,updated_by=?,updated_at=? WHERE id=?",(user.id,now,lesson_id))
        conn.execute("INSERT INTO lesson_plans(id,tenant_id,teaching_plan_id,class_group_id,component_id,scheduled_start,scheduled_end,status,current_version,payload_json,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(new_id,tenant_id,row["teaching_plan_id"],row["class_group_id"],row["component_id"],data.new_start.isoformat(),data.new_end.isoformat(),"scheduled",1,json.dumps(payload,ensure_ascii=False,sort_keys=True),user.id,user.id,now,now))
        conn.execute("INSERT INTO lesson_plan_versions(id,tenant_id,lesson_plan_id,version,status,snapshot_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,new_id,1,"scheduled",json.dumps(payload,ensure_ascii=False,sort_keys=True),user.id,now))
        result={"original_lesson_id":lesson_id,"replacement_lesson_id":new_id,"status":"scheduled","scheduled_start":data.new_start.isoformat(),"scheduled_end":data.new_end.isoformat(),"reason":data.reason}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="reschedule",aggregate_type="lesson_plan",aggregate_id=lesson_id,correlation_id=request.state.correlation_id,before=_lesson(dict(row)),after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="LessonRescheduled",aggregate_type="lesson_plan",aggregate_id=lesson_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/lesson-plans/{lesson_id}/cancel", operation_id="cancel_lesson_plan")
def cancel_lesson(lesson_id:str,data:ActionInput,request:Request,user:CurrentUser=Depends(current_user)):
    return _transition_lesson(lesson_id,data.expected_version,data.reason,request,user,{"draft","scheduled","ready","in_progress"},"cancelled","LessonCancelled")


@router.get("/lesson-plans/{lesson_id}/execution", operation_id="get_lesson_execution")
def get_execution(lesson_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user); lesson=_fetch_lesson(request,tenant_id,lesson_id); _assert_lesson_access(request,user,lesson)
    row=request.state.store.fetch_one("SELECT * FROM lesson_plan_execution_records WHERE lesson_plan_id=? AND tenant_id=?",(lesson_id,tenant_id))
    if not row:raise DomainError("EXECUTION_NOT_FOUND","Execução ainda não registrada.",404)
    for field in ["planned_content_json","delivered_content_json","pending_content_json","additional_content_json"]:row[field.removesuffix("_json")]=json.loads(row.pop(field))
    return row


@router.get("/teaching-plans/reports/coverage", operation_id="teaching_plan_coverage_report")
def coverage_report(request:Request,class_group_id:str|None=None,component_id:str|None=None,user:CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user);sql="SELECT * FROM lesson_plans WHERE tenant_id=?";params:[Any]=[tenant_id]
    if class_group_id:sql+=" AND class_group_id=?";params.append(class_group_id)
    if component_id:sql+=" AND component_id=?";params.append(component_id)
    rows=request.state.store.fetch_all(sql,params)
    if not _is_planning_admin(user):
        visible=[]
        for row in rows:
            try:
                _assert_lesson_access(request,user,row); visible.append(row)
            except DomainError:
                pass
        rows=visible
    planned=len(rows);executed=sum(1 for r in rows if r["status"]=="executed");partial=sum(1 for r in rows if r["status"]=="partially_executed");cancelled=sum(1 for r in rows if r["status"]=="cancelled")
    percentage=round(((executed+partial*0.5)/planned*100),2) if planned else 0
    return {"tenant_id":tenant_id,"filters":{"class_group_id":class_group_id,"component_id":component_id},"planned_lessons":planned,"executed_lessons":executed,"partially_executed_lessons":partial,"cancelled_lessons":cancelled,"coverage_percentage":percentage,"generated_at":iso_now()}
