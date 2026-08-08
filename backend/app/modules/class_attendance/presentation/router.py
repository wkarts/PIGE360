from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.modules.portals.access import assert_class_access, assert_student_access, guardian_for_user, student_for_user
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["class-attendance"])

STATUS_CODES = {
    "present", "absent", "justified_absence", "excused_absence", "late", "late_justified",
    "early_departure", "early_departure_justified", "remote_present", "activity_present", "medical_leave",
    "institutional_leave", "attendance_pending", "not_expected", "not_enrolled", "transferred", "cancelled_session",
}
DEFAULT_EFFECTS = {
    "present": "1", "remote_present": "1", "activity_present": "1",
    "late": "0.75", "late_justified": "0.75", "early_departure": "0.75", "early_departure_justified": "0.75",
    "absent": "0", "justified_absence": "0", "excused_absence": "1", "medical_leave": None,
    "institutional_leave": None, "attendance_pending": None, "not_expected": None, "not_enrolled": None,
    "transferred": None, "cancelled_session": None,
}


class AttendancePolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    effective_from: date
    effective_until: date | None = None
    minimum_percentage: Decimal = Field(default=Decimal("75"), ge=0, le=100)
    status_effects: dict[str, Decimal | None] = Field(default_factory=lambda: {k: (Decimal(v) if v is not None else None) for k,v in DEFAULT_EFFECTS.items()})
    tolerances: dict[str, int | float | bool] = Field(default_factory=lambda: {"late_minutes": 10, "early_departure_minutes": 10, "rounding": 2})
    rules: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until não pode anteceder effective_from")
        unknown=set(self.status_effects)-STATUS_CODES
        if unknown: raise ValueError(f"Status desconhecidos: {sorted(unknown)}")
        for code,effect in self.status_effects.items():
            if effect is not None and not Decimal("0") <= effect <= Decimal("1"):
                raise ValueError(f"Efeito inválido para {code}")
        return self


class AttendancePolicyVersionInput(AttendancePolicyCreate):
    reason: str = Field(min_length=3)


class ClassSessionCreate(BaseModel):
    institution_id: str
    unit_id: str
    class_group_id: str
    component_id: str
    attendance_policy_id: str
    lesson_plan_id: str | None = None
    scheduled_start: datetime
    scheduled_end: datetime
    modality: Literal["regular", "practical", "laboratory", "remote", "hybrid", "replacement", "external"] = "regular"
    enrolled_student_ids: list[str] = Field(min_length=1)
    teacher_ids: list[str] = Field(min_length=1)
    room_id: str | None = None
    source_session_id: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_session(self):
        if self.scheduled_end <= self.scheduled_start: raise ValueError("scheduled_end deve ser posterior a scheduled_start")
        if len(set(self.enrolled_student_ids)) != len(self.enrolled_student_ids): raise ValueError("Aluno duplicado")
        if len(set(self.teacher_ids)) != len(self.teacher_ids): raise ValueError("Professor duplicado")
        return self


class SessionAction(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)


class SessionReschedule(BaseModel):
    reason: str = Field(min_length=3)
    expected_version: int = Field(ge=1)
    new_start: datetime
    new_end: datetime

    @model_validator(mode="after")
    def validate_times(self):
        if self.new_end <= self.new_start: raise ValueError("new_end deve ser posterior a new_start")
        return self


class AttendanceRecordInput(BaseModel):
    student_id: str
    status_code: str
    minutes_present: int | None = Field(default=None, ge=0, le=1440)
    observation: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_status(self):
        if self.status_code not in STATUS_CODES: raise ValueError(f"status_code inválido: {self.status_code}")
        return self


class AttendancePutInput(BaseModel):
    records: list[AttendanceRecordInput] = Field(min_length=1)
    mode: Literal["full_list", "quick", "all_present_exceptions", "grid", "qr", "barcode", "nfc", "kiosk", "import"] = "full_list"
    origin: Literal["online", "offline", "import", "integration"] = "online"
    device_id: str | None = None

    @model_validator(mode="after")
    def unique_students(self):
        ids=[r.student_id for r in self.records]
        if len(ids)!=len(set(ids)): raise ValueError("Existe mais de um registro para o mesmo aluno")
        return self


class SubmitAttendanceInput(BaseModel):
    expected_call_version: int = Field(ge=1)
    origin: Literal["online", "offline"] = "online"
    device_id: str | None = None


class CorrectionInput(BaseModel):
    student_id: str
    to_status: str
    reason: str = Field(min_length=3, max_length=2000)
    expected_record_version: int = Field(ge=1)
    origin: Literal["online", "offline"] = "online"
    device_id: str | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.to_status not in STATUS_CODES: raise ValueError("to_status inválido")
        return self


class JustificationCreate(BaseModel):
    student_id: str
    session_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=4000)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class JustificationDecision(BaseModel):
    notes: str = Field(min_length=3, max_length=4000)


def _tenant(user: CurrentUser) -> str:
    if user.plane!="tenant" or not user.tenant_id: raise DomainError("TENANT_ROUTE_REQUIRED","Rota disponível somente no domínio da instituição.",404)
    return user.tenant_id


def _coordinator(user: CurrentUser) -> None:
    if not set(user.roles).intersection({"tenant_owner","institution_director","academic_coordinator"}):
        raise DomainError("PERMISSION_DENIED","Operação reservada à coordenação.",403)


def _teacher_or_coordinator(user: CurrentUser, session: dict[str, Any]) -> None:
    if set(user.roles).intersection({"tenant_owner","institution_director","academic_coordinator"}): return
    if "teacher" not in user.roles and "assistant_teacher" not in user.roles: raise DomainError("PERMISSION_DENIED","Permissão insuficiente para chamada.",403)
    if user.id not in json.loads(session["teacher_ids_json"]): raise DomainError("TEACHER_NOT_ASSIGNED","Professor não atribuído a esta sessão.",403)


def _validate_session_scope(request: Request, tenant_id: str, data: ClassSessionCreate) -> None:
    session_date = data.scheduled_start.date().isoformat()
    group = request.state.store.fetch_one(
        """SELECT cg.id,cg.unit_id,cg.curriculum_id,u.institution_id
             FROM class_groups cg JOIN units u ON u.id=cg.unit_id AND u.tenant_id=cg.tenant_id
            WHERE cg.id=? AND cg.tenant_id=? AND cg.state='active'""",
        (data.class_group_id, tenant_id),
    )
    if not group:
        raise DomainError("CLASS_GROUP_NOT_FOUND", "Turma ativa não localizada.", 404)
    if group["unit_id"] != data.unit_id or group["institution_id"] != data.institution_id:
        raise DomainError("CLASS_SCOPE_MISMATCH", "Turma não pertence à instituição/unidade informada.", 409)
    component = request.state.store.fetch_one(
        "SELECT id,curriculum_id FROM curriculum_components WHERE id=? AND tenant_id=? AND state='active'",
        (data.component_id, tenant_id),
    )
    if not component:
        raise DomainError("CURRICULUM_COMPONENT_NOT_FOUND", "Componente curricular ativo não localizado.", 404)
    if component["curriculum_id"] != group["curriculum_id"]:
        raise DomainError("COMPONENT_SCOPE_MISMATCH", "Componente não pertence ao currículo da turma.", 409)

    placeholders = ",".join("?" for _ in data.enrolled_student_ids)
    enrollment_rows = request.state.store.fetch_all(
        f"""SELECT student_id FROM enrollments
              WHERE tenant_id=? AND class_group_id=? AND state='active'
                AND student_id IN ({placeholders})
                AND enrolled_on IS NOT NULL AND enrolled_on<=?
                AND (ended_on IS NULL OR ended_on>=?)""",
        [tenant_id, data.class_group_id, *data.enrolled_student_ids, session_date, session_date],
    )
    valid_students = {row["student_id"] for row in enrollment_rows}
    invalid_students = [student_id for student_id in data.enrolled_student_ids if student_id not in valid_students]
    if invalid_students:
        raise DomainError(
            "STUDENT_NOT_ENROLLED_FOR_SESSION",
            "Há aluno sem matrícula ativa na turma/data da sessão.",
            409,
            errors=[{"field": "enrolled_student_ids", "code": "INVALID_ENROLLMENT", "message": student_id} for student_id in invalid_students],
        )

    for teacher_id in data.teacher_ids:
        teacher = request.state.store.fetch_one(
            "SELECT id,person_id,roles_json,active FROM users WHERE tenant_id=? AND id=?",
            (tenant_id, teacher_id),
        )
        if not teacher or not teacher["active"] or not teacher["person_id"]:
            raise DomainError("TEACHER_NOT_ASSIGNED", "Professor informado não possui conta docente ativa vinculada a uma pessoa.", 409)
        roles = set(json.loads(teacher["roles_json"] or "[]"))
        if not roles.intersection({"teacher", "assistant_teacher"}):
            raise DomainError("TEACHER_NOT_ASSIGNED", "Usuário informado não possui perfil docente.", 409)
        assignment = request.state.store.fetch_one(
            """SELECT ta.id FROM teacher_assignments ta
                 JOIN employees e ON e.id=ta.employee_id AND e.tenant_id=ta.tenant_id
                WHERE ta.tenant_id=? AND e.person_id=? AND e.state='active'
                  AND ta.class_group_id=? AND ta.component_id=? AND ta.state='active'
                  AND ta.starts_on<=? AND (ta.ends_on IS NULL OR ta.ends_on>=?)""",
            (tenant_id, teacher["person_id"], data.class_group_id, data.component_id, session_date, session_date),
        )
        if not assignment:
            raise DomainError("TEACHER_NOT_ASSIGNED", "Professor não possui atribuição ativa para a turma/componente na data da sessão.", 409)


def _session(row: dict[str, Any]) -> dict[str, Any]:
    return {"id":row["id"],"tenant_id":row["tenant_id"],"institution_id":row["institution_id"],"unit_id":row["unit_id"],
            "class_group_id":row["class_group_id"],"component_id":row["component_id"],"attendance_policy_id":row["attendance_policy_id"],
            "lesson_plan_id":row["lesson_plan_id"],"scheduled_start":row["scheduled_start"],"scheduled_end":row["scheduled_end"],
            "actual_start":row["actual_start"],"actual_end":row["actual_end"],"status":row["status"],"modality":row["modality"],
            "enrolled_student_ids":json.loads(row["enrolled_students_json"]),"teacher_ids":json.loads(row["teacher_ids_json"]),
            "payload":json.loads(row["payload_json"]),"version":row["version"],"created_by":row["created_by"],"updated_by":row["updated_by"],
            "created_at":row["created_at"],"updated_at":row["updated_at"]}


def _record(row: dict[str, Any]) -> dict[str, Any]:
    return {k:row[k] for k in ["id","tenant_id","attendance_call_id","class_session_id","student_id","status_code","minutes_present","observation","version","updated_by","updated_at"]}


def _get_session(request:Request,tenant_id:str,session_id:str)->dict[str,Any]:
    row=request.state.store.fetch_one("SELECT * FROM class_sessions WHERE id=? AND tenant_id=?",(session_id,tenant_id))
    if not row:raise DomainError("CLASS_SESSION_NOT_FOUND","Sessão de aula não localizada.",404)
    return row


@router.get("/attendance/policies",operation_id="list_attendance_policies")
def list_policies(request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);rows=request.state.store.fetch_all("SELECT * FROM attendance_policies WHERE tenant_id=? ORDER BY updated_at DESC",(tenant_id,))
    for row in rows:
        row["versions"]=request.state.store.fetch_all("SELECT id,version,effective_from,effective_until,minimum_percentage,status_effects_json,tolerances_json,payload_json,created_by,created_at FROM attendance_policy_versions WHERE policy_id=? ORDER BY version",(row["id"],))
        for v in row["versions"]:
            for f in ["status_effects_json","tolerances_json","payload_json"]:v[f.removesuffix("_json")]=json.loads(v.pop(f))
    return {"items":rows}


@router.post("/attendance/policies",operation_id="create_attendance_policy",status_code=201)
def create_policy(data:AttendancePolicyCreate,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user);now=iso_now();policy_id=uuid7();body=data.model_dump(mode="json")
    effects={k:(str(v) if v is not None else None) for k,v in data.status_effects.items()}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO attendance_policies(id,tenant_id,name,status,current_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(policy_id,tenant_id,data.name,"active",1,now,now))
        conn.execute("INSERT INTO attendance_policy_versions(id,tenant_id,policy_id,version,effective_from,effective_until,minimum_percentage,status_effects_json,tolerances_json,payload_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,policy_id,1,str(data.effective_from),str(data.effective_until) if data.effective_until else None,str(data.minimum_percentage),json.dumps(effects,sort_keys=True),json.dumps(data.tolerances,sort_keys=True),json.dumps(body,ensure_ascii=False,sort_keys=True),user.id,now))
        result={"id":policy_id,"name":data.name,"status":"active","current_version":1,"effective_from":str(data.effective_from),"minimum_percentage":str(data.minimum_percentage),"status_effects":effects,"tolerances":data.tolerances}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="create",aggregate_type="attendance_policy",aggregate_id=policy_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="AttendancePolicyPublished",aggregate_type="attendance_policy",aggregate_id=policy_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/attendance/policies/{policy_id}/versions",operation_id="create_attendance_policy_version")
def policy_version(policy_id:str,data:AttendancePolicyVersionInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user);now=iso_now();body=data.model_dump(mode="json");reason=body.pop("reason");effects={k:(str(v) if v is not None else None) for k,v in data.status_effects.items()}
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM attendance_policies WHERE id=? AND tenant_id=?",(policy_id,tenant_id)).fetchone()
        if not row:raise DomainError("ATTENDANCE_POLICY_NOT_FOUND","Política não localizada.",404)
        version=row["current_version"]+1
        conn.execute("UPDATE attendance_policies SET name=?,current_version=?,updated_at=? WHERE id=?",(data.name,version,now,policy_id))
        conn.execute("INSERT INTO attendance_policy_versions(id,tenant_id,policy_id,version,effective_from,effective_until,minimum_percentage,status_effects_json,tolerances_json,payload_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,policy_id,version,str(data.effective_from),str(data.effective_until) if data.effective_until else None,str(data.minimum_percentage),json.dumps(effects,sort_keys=True),json.dumps(data.tolerances,sort_keys=True),json.dumps(body,ensure_ascii=False,sort_keys=True),user.id,now))
        result={"id":policy_id,"name":data.name,"current_version":version,"effective_from":str(data.effective_from),"minimum_percentage":str(data.minimum_percentage),"reason":reason}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="new_version",aggregate_type="attendance_policy",aggregate_id=policy_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="AttendancePolicyVersionPublished",aggregate_type="attendance_policy",aggregate_id=policy_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/class-sessions",operation_id="list_class_sessions")
def list_sessions(request:Request,status:str|None=None,class_group_id:str|None=None,from_date:date|None=None,to_date:date|None=None,limit:int=100,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);roles=set(user.roles)
    allowed_admin={"tenant_owner","institution_director","academic_coordinator"}
    if not roles.intersection(allowed_admin|{"teacher","assistant_teacher"}):
        raise DomainError("PERMISSION_DENIED","Sem permissão para consultar sessões de aula.",403)
    if class_group_id and roles.intersection({"teacher","assistant_teacher"}) and not roles.intersection(allowed_admin):
        assert_class_access(request,user,class_group_id)
    sql="SELECT * FROM class_sessions WHERE tenant_id=?";params:list[Any]=[tenant_id]
    if status:sql+=" AND status=?";params.append(status)
    if class_group_id:sql+=" AND class_group_id=?";params.append(class_group_id)
    if from_date:sql+=" AND scheduled_start>=?";params.append(str(from_date))
    if to_date:sql+=" AND scheduled_start<?";params.append(str(to_date)+"T23:59:59")
    sql+=" ORDER BY scheduled_start DESC LIMIT ?";params.append(min(max(limit*3,limit),1500))
    rows=request.state.store.fetch_all(sql,params)
    if roles.intersection({"teacher","assistant_teacher"}) and not roles.intersection(allowed_admin):
        rows=[row for row in rows if user.id in json.loads(row["teacher_ids_json"])]
    return {"items":[_session(x) for x in rows[:limit]]}


@router.post("/class-sessions",operation_id="create_class_session",status_code=201)
def create_session(data:ClassSessionCreate,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user);body=data.model_dump(mode="json");now=iso_now();session_id=uuid7();scope=f"class-session:create:{tenant_id}"
    policy=request.state.store.fetch_one("SELECT * FROM attendance_policies WHERE id=? AND tenant_id=? AND status='active'",(data.attendance_policy_id,tenant_id))
    if not policy:raise DomainError("ATTENDANCE_POLICY_NOT_FOUND","Política ativa não localizada.",404)
    _validate_session_scope(request, tenant_id, data)
    if data.lesson_plan_id:
        lesson=request.state.store.fetch_one("SELECT class_group_id,component_id,status FROM lesson_plans WHERE id=? AND tenant_id=?",(data.lesson_plan_id,tenant_id))
        if not lesson:raise DomainError("LESSON_PLAN_NOT_FOUND","Plano de aula não localizado.",404)
        if lesson["class_group_id"]!=data.class_group_id or lesson["component_id"]!=data.component_id:raise DomainError("LESSON_SCOPE_MISMATCH","Plano de aula não pertence à turma/componente.",409)
        if lesson["status"]=="cancelled":raise DomainError("LESSON_CANCELLED","Plano de aula cancelado não pode gerar sessão.",409)
    result={"id":session_id,"tenant_id":tenant_id,**body,"status":"scheduled","version":1,"created_by":user.id,"updated_by":user.id,"created_at":now,"updated_at":now}
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        conn.execute("""INSERT INTO class_sessions(id,tenant_id,institution_id,unit_id,class_group_id,component_id,attendance_policy_id,lesson_plan_id,scheduled_start,scheduled_end,status,modality,enrolled_students_json,teacher_ids_json,payload_json,version,created_by,updated_by,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(session_id,tenant_id,data.institution_id,data.unit_id,data.class_group_id,data.component_id,data.attendance_policy_id,data.lesson_plan_id,data.scheduled_start.isoformat(),data.scheduled_end.isoformat(),"scheduled",data.modality,json.dumps(data.enrolled_student_ids),json.dumps(data.teacher_ids),json.dumps(body,ensure_ascii=False,sort_keys=True),1,user.id,user.id,now,now))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="create",aggregate_type="class_session",aggregate_id=session_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="ClassSessionScheduled",aggregate_type="class_session",aggregate_id=session_id,payload=result,correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,body,201,result)
    response.status_code=201;response.headers["ETag"]='"1"';return result


@router.get("/class-sessions/{session_id}",operation_id="get_class_session")
def get_session(session_id:str,request:Request,response:Response,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);row=_get_session(request,tenant_id,session_id);_teacher_or_coordinator(user,row);result=_session(row);result["attendance"]=get_attendance(session_id,request,user)
    response.headers["ETag"]=f'"{row["version"]}"';return result


def _session_transition(session_id:str,data:SessionAction,request:Request,user:CurrentUser,expected:set[str],target:str,event:str,coordinator_only:bool=False):
    tenant_id=_tenant(user);now=iso_now()
    if coordinator_only:_coordinator(user)
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM class_sessions WHERE id=? AND tenant_id=?",(session_id,tenant_id)).fetchone()
        if not row:raise DomainError("CLASS_SESSION_NOT_FOUND","Sessão não localizada.",404)
        if not coordinator_only:_teacher_or_coordinator(user,dict(row))
        if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] not in expected:raise DomainError("INVALID_STATE_TRANSITION",f"Não é possível mudar {row['status']} para {target}.",409)
        before=_session(dict(row));version=row["version"]+1
        actual_start=now if target=="started" and not row["actual_start"] else row["actual_start"]
        actual_end=now if target in {"closed","completed"} else row["actual_end"]
        conn.execute("UPDATE class_sessions SET status=?,actual_start=?,actual_end=?,version=?,updated_by=?,updated_at=? WHERE id=?",(target,actual_start,actual_end,version,user.id,now,session_id))
        result={**before,"status":target,"actual_start":actual_start,"actual_end":actual_end,"version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action=target,aggregate_type="class_session",aggregate_id=session_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type=event,aggregate_type="class_session",aggregate_id=session_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/class-sessions/{session_id}/start",operation_id="start_class_session")
def start_session(session_id:str,data:SessionAction,request:Request,user:CurrentUser=Depends(current_user)):
    return _session_transition(session_id,data,request,user,{"scheduled","ready"},"started","ClassSessionStarted")


@router.post("/class-sessions/{session_id}/cancel",operation_id="cancel_class_session")
def cancel_session(session_id:str,data:SessionAction,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user)
    # A sessão cancelada não gera faltas. Registros ainda não fechados são preservados como evidência, mas excluídos de indicadores.
    return _session_transition(session_id,data,request,user,{"scheduled","ready","started","attendance_open"},"cancelled","ClassSessionCancelled",True)


@router.post("/class-sessions/{session_id}/reschedule",operation_id="reschedule_class_session")
def reschedule_session(session_id:str,data:SessionReschedule,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user);now=iso_now();new_id=uuid7()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM class_sessions WHERE id=? AND tenant_id=?",(session_id,tenant_id)).fetchone()
        if not row:raise DomainError("CLASS_SESSION_NOT_FOUND","Sessão não localizada.",404)
        if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["status"] in {"closed","cancelled","rescheduled"}:raise DomainError("SESSION_NOT_RESCHEDULABLE","Sessão não pode ser reagendada neste estado.",409)
        payload=json.loads(row["payload_json"]);payload["source_session_id"]=session_id;payload["scheduled_start"]=data.new_start.isoformat();payload["scheduled_end"]=data.new_end.isoformat()
        conn.execute("UPDATE class_sessions SET status='rescheduled',version=version+1,updated_by=?,updated_at=? WHERE id=?",(user.id,now,session_id))
        conn.execute("""INSERT INTO class_sessions(id,tenant_id,institution_id,unit_id,class_group_id,component_id,attendance_policy_id,lesson_plan_id,scheduled_start,scheduled_end,status,modality,enrolled_students_json,teacher_ids_json,payload_json,version,created_by,updated_by,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(new_id,tenant_id,row["institution_id"],row["unit_id"],row["class_group_id"],row["component_id"],row["attendance_policy_id"],row["lesson_plan_id"],data.new_start.isoformat(),data.new_end.isoformat(),"scheduled",row["modality"],row["enrolled_students_json"],row["teacher_ids_json"],json.dumps(payload,ensure_ascii=False,sort_keys=True),1,user.id,user.id,now,now))
        result={"original_session_id":session_id,"replacement_session_id":new_id,"scheduled_start":data.new_start.isoformat(),"scheduled_end":data.new_end.isoformat(),"reason":data.reason}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="reschedule",aggregate_type="class_session",aggregate_id=session_id,correlation_id=request.state.correlation_id,before=_session(dict(row)),after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="ClassSessionRescheduled",aggregate_type="class_session",aggregate_id=session_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/class-sessions/{session_id}/close",operation_id="close_class_session")
def close_session(session_id:str,data:SessionAction,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);session=_get_session(request,tenant_id,session_id);_teacher_or_coordinator(user,session)
    call=request.state.store.fetch_one("SELECT status FROM attendance_calls WHERE class_session_id=?",(session_id,))
    if not call or call["status"]!="submitted":raise DomainError("ATTENDANCE_NOT_SUBMITTED","Envie a chamada antes de fechar a sessão.",409)
    result=_session_transition(session_id,data,request,user,{"attendance_submitted","completed","started","attendance_open"},"closed","AttendanceClosed")
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE attendance_calls SET status='closed',closed_by=?,closed_at=? WHERE class_session_id=?",(user.id,iso_now(),session_id))
    return result


@router.post("/class-sessions/{session_id}/reopen",operation_id="reopen_class_session")
def reopen_session(session_id:str,data:SessionAction,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user);result=_session_transition(session_id,data,request,user,{"closed"},"reopened","AttendanceReopened",True)
    with request.state.store.transaction() as conn:conn.execute("UPDATE attendance_calls SET status='open',closed_by=NULL,closed_at=NULL WHERE class_session_id=?",(session_id,))
    return result


@router.get("/class-sessions/{session_id}/attendance",operation_id="get_session_attendance")
def get_attendance(session_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);session=_get_session(request,tenant_id,session_id);_teacher_or_coordinator(user,session)
    call=request.state.store.fetch_one("SELECT * FROM attendance_calls WHERE class_session_id=? AND tenant_id=?",(session_id,tenant_id))
    records=request.state.store.fetch_all("SELECT * FROM attendance_records WHERE class_session_id=? AND tenant_id=? ORDER BY student_id",(session_id,tenant_id))
    return {"call":call,"records":[_record(r) for r in records]}


@router.put("/class-sessions/{session_id}/attendance",operation_id="save_session_attendance")
def put_attendance(session_id:str,data:AttendancePutInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);session=_get_session(request,tenant_id,session_id);_teacher_or_coordinator(user,session)
    if session["status"] in {"cancelled","rescheduled","closed"}:raise DomainError("ATTENDANCE_CLOSED","Chamada indisponível para esta sessão.",409)
    enrolled=set(json.loads(session["enrolled_students_json"]));provided={r.student_id for r in data.records};invalid=provided-enrolled
    if invalid:raise DomainError("STUDENT_NOT_ENROLLED",f"Alunos não matriculados na data: {sorted(invalid)}",422)
    body=data.model_dump(mode="json");scope=f"attendance:{session_id}";now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        call=conn.execute("SELECT * FROM attendance_calls WHERE class_session_id=?",(session_id,)).fetchone()
        if not call:
            call_id=uuid7();call_version=1
            conn.execute("INSERT INTO attendance_calls(id,tenant_id,class_session_id,status,current_version,mode,opened_by,opened_at) VALUES(?,?,?,?,?,?,?,?)",(call_id,tenant_id,session_id,"open",call_version,data.mode,user.id,now))
            add_outbox(conn,tenant_id=tenant_id,event_type="AttendanceCallOpened",aggregate_type="attendance_call",aggregate_id=call_id,payload={"class_session_id":session_id,"mode":data.mode},correlation_id=request.state.correlation_id)
        else:
            if call["status"] in {"submitted","closed"}:raise DomainError("ATTENDANCE_ALREADY_SUBMITTED","A chamada exige reabertura ou correção auditada.",409)
            call_id=call["id"];call_version=call["current_version"]+1
            conn.execute("UPDATE attendance_calls SET current_version=?,mode=? WHERE id=?",(call_version,data.mode,call_id))
        changed=[]
        for item in data.records:
            old=conn.execute("SELECT * FROM attendance_records WHERE class_session_id=? AND student_id=?",(session_id,item.student_id)).fetchone()
            if old:
                new_version=old["version"]+1
                conn.execute("UPDATE attendance_records SET status_code=?,minutes_present=?,observation=?,version=?,updated_by=?,updated_at=? WHERE id=?",(item.status_code,item.minutes_present,item.observation,new_version,user.id,now,old["id"]))
                record_id=old["id"];before=_record(dict(old));event_type="updated"
            else:
                record_id=uuid7();new_version=1;before=None;event_type="created"
                conn.execute("INSERT INTO attendance_records(id,tenant_id,attendance_call_id,class_session_id,student_id,status_code,minutes_present,observation,version,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(record_id,tenant_id,call_id,session_id,item.student_id,item.status_code,item.minutes_present,item.observation,new_version,user.id,now))
            after={"id":record_id,"student_id":item.student_id,"status_code":item.status_code,"minutes_present":item.minutes_present,"observation":item.observation,"version":new_version}
            conn.execute("INSERT INTO attendance_record_events(id,tenant_id,attendance_record_id,event_type,before_json,after_json,actor_id,origin,device_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,record_id,event_type,json.dumps(before,ensure_ascii=False,sort_keys=True) if before else None,json.dumps(after,ensure_ascii=False,sort_keys=True),user.id,data.origin,data.device_id,now))
            changed.append(after)
            if item.status_code=="absent":add_outbox(conn,tenant_id=tenant_id,event_type="StudentMarkedAbsent",aggregate_type="attendance_record",aggregate_id=record_id,payload={"class_session_id":session_id,"student_id":item.student_id},correlation_id=request.state.correlation_id)
            if item.status_code in {"late","late_justified"}:add_outbox(conn,tenant_id=tenant_id,event_type="StudentMarkedLate",aggregate_type="attendance_record",aggregate_id=record_id,payload={"class_session_id":session_id,"student_id":item.student_id},correlation_id=request.state.correlation_id)
        snapshot={"records":changed,"mode":data.mode,"origin":data.origin,"device_id":data.device_id}
        conn.execute("INSERT INTO attendance_call_versions(id,tenant_id,attendance_call_id,version,snapshot_json,actor_id,origin,device_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,call_id,call_version,json.dumps(snapshot,ensure_ascii=False,sort_keys=True),user.id,data.origin,data.device_id,now))
        new_session_status="attendance_open";session_version=session["version"]+1
        conn.execute("UPDATE class_sessions SET status=?,version=?,updated_by=?,updated_at=? WHERE id=?",(new_session_status,session_version,user.id,now,session_id))
        result={"attendance_call_id":call_id,"class_session_id":session_id,"status":"open","current_version":call_version,"session_version":session_version,"saved_records":changed,"missing_students":sorted(enrolled-provided),"saved_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="attendance_draft_saved",aggregate_type="attendance_call",aggregate_id=call_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="AttendanceDraftSaved",aggregate_type="attendance_call",aggregate_id=call_id,payload=result,correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,body,200,result)
    response.headers["ETag"]=f'"{call_version}"';return result


@router.post("/class-sessions/{session_id}/attendance/submit",operation_id="submit_session_attendance")
def submit_attendance(session_id:str,data:SubmitAttendanceInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);session=_get_session(request,tenant_id,session_id);_teacher_or_coordinator(user,session)
    if session["status"] in {"cancelled","rescheduled","closed"}:raise DomainError("ATTENDANCE_CLOSED","Sessão não aceita envio.",409)
    enrolled=set(json.loads(session["enrolled_students_json"]));now=iso_now()
    with request.state.store.transaction() as conn:
        call=conn.execute("SELECT * FROM attendance_calls WHERE class_session_id=?",(session_id,)).fetchone()
        if not call:raise DomainError("ATTENDANCE_EMPTY","Nenhuma chamada foi iniciada.",409)
        if call["current_version"]!=data.expected_call_version:raise DomainError("VERSION_CONFLICT","Versão da chamada divergente.",409)
        if call["status"]!="open":raise DomainError("ATTENDANCE_ALREADY_SUBMITTED","Chamada já enviada.",409)
        rows=conn.execute("SELECT student_id,status_code FROM attendance_records WHERE class_session_id=?",(session_id,)).fetchall();present_ids={r["student_id"] for r in rows};missing=enrolled-present_ids
        if missing:raise DomainError("ATTENDANCE_INCOMPLETE",f"Faltam registros para {len(missing)} aluno(s).",409,errors=[{"field":"records","code":"MISSING_STUDENTS","message":", ".join(sorted(missing))}])
        version=call["current_version"]+1;session_version=session["version"]+1
        conn.execute("UPDATE attendance_calls SET status='submitted',current_version=?,submitted_by=?,submitted_at=? WHERE id=?",(version,user.id,now,call["id"]))
        snapshot={"records":[dict(r) for r in rows],"submitted_at":now,"origin":data.origin,"device_id":data.device_id}
        conn.execute("INSERT INTO attendance_call_versions(id,tenant_id,attendance_call_id,version,snapshot_json,actor_id,origin,device_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,call["id"],version,json.dumps(snapshot,ensure_ascii=False,sort_keys=True),user.id,data.origin,data.device_id,now))
        conn.execute("UPDATE class_sessions SET status='attendance_submitted',version=?,updated_by=?,updated_at=? WHERE id=?",(session_version,user.id,now,session_id))
        result={"attendance_call_id":call["id"],"class_session_id":session_id,"status":"submitted","current_version":version,"session_version":session_version,"submitted_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="submit",aggregate_type="attendance_call",aggregate_id=call["id"],correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="AttendanceSubmitted",aggregate_type="attendance_call",aggregate_id=call["id"],payload=result,correlation_id=request.state.correlation_id)
        absent=[r["student_id"] for r in rows if r["status_code"] in {"absent","late","early_departure"}]
        for student_id in absent:add_outbox(conn,tenant_id=tenant_id,event_type="GuardianAbsenceNotificationRequested",aggregate_type="student",aggregate_id=student_id,payload={"class_session_id":session_id,"delay_policy":"configured"},correlation_id=request.state.correlation_id)
    return result


@router.post("/class-sessions/{session_id}/attendance/corrections",operation_id="correct_session_attendance")
def correct_attendance(session_id:str,data:CorrectionInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);session=_get_session(request,tenant_id,session_id);_teacher_or_coordinator(user,session);now=iso_now()
    if session["status"]=="closed" and not set(user.roles).intersection({"tenant_owner","institution_director","academic_coordinator"}):raise DomainError("REOPEN_REQUIRED","Sessão fechada requer reabertura pela coordenação.",409)
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM attendance_records WHERE class_session_id=? AND student_id=? AND tenant_id=?",(session_id,data.student_id,tenant_id)).fetchone()
        if not row:raise DomainError("ATTENDANCE_RECORD_NOT_FOUND","Registro de frequência não localizado.",404)
        if row["version"]!=data.expected_record_version:raise DomainError("VERSION_CONFLICT","Versão do registro divergente.",409)
        before=_record(dict(row));version=row["version"]+1
        conn.execute("UPDATE attendance_records SET status_code=?,version=?,updated_by=?,updated_at=? WHERE id=?",(data.to_status,version,user.id,now,row["id"]))
        after={**before,"status_code":data.to_status,"version":version,"updated_by":user.id,"updated_at":now}
        correction_id=uuid7();conn.execute("INSERT INTO attendance_corrections(id,tenant_id,attendance_record_id,from_status,to_status,reason,actor_id,approved_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(correction_id,tenant_id,row["id"],row["status_code"],data.to_status,data.reason,user.id,user.id if set(user.roles).intersection({"tenant_owner","institution_director","academic_coordinator"}) else None,now))
        conn.execute("INSERT INTO attendance_record_events(id,tenant_id,attendance_record_id,event_type,before_json,after_json,reason,actor_id,origin,device_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,row["id"],"corrected",json.dumps(before,ensure_ascii=False,sort_keys=True),json.dumps(after,ensure_ascii=False,sort_keys=True),data.reason,user.id,data.origin,data.device_id,now))
        result={"correction_id":correction_id,"record":after,"reason":data.reason}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="correct",aggregate_type="attendance_record",aggregate_id=row["id"],correlation_id=request.state.correlation_id,before=before,after=after,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="AttendanceCorrected",aggregate_type="attendance_record",aggregate_id=row["id"],payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/attendance/justifications",operation_id="create_attendance_justification",status_code=201)
def create_justification(data:JustificationCreate,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);allowed={"guardian","student","secretary","academic_coordinator","institution_director","tenant_owner"}
    if not set(user.roles).intersection(allowed):raise DomainError("PERMISSION_DENIED","Sem permissão para justificar frequência.",403)
    if set(user.roles).intersection({"guardian","student"}):assert_student_access(request,user,data.student_id)
    for session_id in data.session_ids:
        session=_get_session(request,tenant_id,session_id)
        if data.student_id not in set(json.loads(session["enrolled_students_json"])):
            raise DomainError("STUDENT_NOT_ENROLLED","Aluno não pertence à sessão informada.",422)
    now=iso_now();just_id=uuid7();body=data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO attendance_justifications(id,tenant_id,student_id,session_ids_json,reason,state,attachments_json,submitted_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(just_id,tenant_id,data.student_id,json.dumps(data.session_ids),data.reason,"submitted",json.dumps(data.attachments,ensure_ascii=False),user.id,now,now))
        result={"id":just_id,"tenant_id":tenant_id,**body,"state":"submitted","submitted_by":user.id,"created_at":now,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="submit",aggregate_type="attendance_justification",aggregate_id=just_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant_id,event_type="AttendanceJustificationSubmitted",aggregate_type="attendance_justification",aggregate_id=just_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/attendance/justifications",operation_id="list_attendance_justifications")
def list_justifications(request:Request,student_id:str|None=None,state:str|None=None,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);roles=set(user.roles);admin={"tenant_owner","institution_director","academic_coordinator","secretary","auditor"}
    sql="SELECT * FROM attendance_justifications WHERE tenant_id=?";params:list[Any]=[tenant_id]
    if not roles.intersection(admin):
        if student_id:
            assert_student_access(request,user,student_id);sql+=" AND student_id=?";params.append(student_id)
        elif "student" in roles:
            student=student_for_user(request,user);sql+=" AND student_id=?";params.append(student["id"])
        elif "guardian" in roles:
            guardian=guardian_for_user(request,user)
            ids=[r["student_id"] for r in request.state.store.fetch_all("SELECT student_id FROM guardian_students WHERE tenant_id=? AND guardian_id=?",(tenant_id,guardian["id"]))]
            if not ids:return {"items":[]}
            sql+=f" AND student_id IN ({','.join('?' for _ in ids)})";params.extend(ids)
        else:
            raise DomainError("PERMISSION_DENIED","Sem permissão para consultar justificativas.",403)
    elif student_id:
        sql+=" AND student_id=?";params.append(student_id)
    if state:sql+=" AND state=?";params.append(state)
    sql+=" ORDER BY created_at DESC";rows=request.state.store.fetch_all(sql,params)
    for r in rows:r["session_ids"]=json.loads(r.pop("session_ids_json"));r["attachments"]=json.loads(r.pop("attachments_json"))
    return {"items":rows}


def _decide_justification(justification_id:str,data:JustificationDecision,request:Request,user:CurrentUser,target:str,event:str):
    tenant_id=_tenant(user);_coordinator(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM attendance_justifications WHERE id=? AND tenant_id=?",(justification_id,tenant_id)).fetchone()
        if not row:raise DomainError("JUSTIFICATION_NOT_FOUND","Justificativa não localizada.",404)
        if row["state"] not in {"submitted","under_review","additional_information_required"}:raise DomainError("JUSTIFICATION_ALREADY_DECIDED","Justificativa já decidida.",409)
        conn.execute("UPDATE attendance_justifications SET state=?,reviewed_by=?,review_notes=?,updated_at=? WHERE id=?",(target,user.id,data.notes,now,justification_id))
        result={"id":justification_id,"state":target,"reviewed_by":user.id,"review_notes":data.notes,"updated_at":now,"policy_effect":"A aprovação não converte automaticamente falta em presença."}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action=target,aggregate_type="attendance_justification",aggregate_id=justification_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.notes)
        add_outbox(conn,tenant_id=tenant_id,event_type=event,aggregate_type="attendance_justification",aggregate_id=justification_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/attendance/justifications/{justification_id}/approve",operation_id="approve_attendance_justification")
def approve_justification(justification_id:str,data:JustificationDecision,request:Request,user:CurrentUser=Depends(current_user)):
    return _decide_justification(justification_id,data,request,user,"approved","AttendanceJustificationApproved")

@router.post("/attendance/justifications/{justification_id}/reject",operation_id="reject_attendance_justification")
def reject_justification(justification_id:str,data:JustificationDecision,request:Request,user:CurrentUser=Depends(current_user)):
    return _decide_justification(justification_id,data,request,user,"rejected","AttendanceJustificationRejected")


def _policy_effects(store,policy_id:str,when:str)->tuple[dict[str,Decimal|None],Decimal,int]:
    row=store.fetch_one("SELECT * FROM attendance_policy_versions WHERE policy_id=? AND effective_from<=? AND (effective_until IS NULL OR effective_until>=?) ORDER BY version DESC LIMIT 1",(policy_id,when,when))
    if not row:raise DomainError("POLICY_VERSION_NOT_FOUND","Nenhuma versão vigente da política.",409)
    effects={k:(Decimal(v) if v is not None else None) for k,v in json.loads(row["status_effects_json"]).items()}
    return effects,Decimal(row["minimum_percentage"]),row["version"]


@router.get("/attendance/risks",operation_id="get_attendance_risks")
def attendance_risks(request:Request,threshold_margin:Decimal=Decimal("5"),user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);_coordinator(user);student_rows=request.state.store.fetch_all("SELECT DISTINCT student_id FROM attendance_records WHERE tenant_id=?",(tenant_id,));items=[]
    for sr in student_rows:
        summary=_student_attendance_summary(sr["student_id"],request,tenant_id);percentage=Decimal(summary["attendance_percentage"])
        # Use the highest applicable minimum among referenced policies as conservative risk boundary.
        minimum=Decimal("75")
        for pv in summary["policy_versions"]:
            row=request.state.store.fetch_one("SELECT minimum_percentage FROM attendance_policy_versions WHERE policy_id=? AND version=?",(pv["policy_id"],pv["version"]));minimum=max(minimum,Decimal(row["minimum_percentage"])) if row else minimum
        if percentage < minimum+threshold_margin:
            level="critical" if percentage<minimum else "warning";items.append({"student_id":sr["student_id"],"percentage":str(percentage),"minimum":str(minimum),"level":level,"policy_versions":summary["policy_versions"]})
    items.sort(key=lambda x:Decimal(x["percentage"]));return {"items":items,"generated_at":iso_now(),"policy_bound":True}

def _student_attendance_summary(student_id:str,request:Request,tenant_id:str):
    rows=request.state.store.fetch_all("""SELECT r.*,s.attendance_policy_id,s.scheduled_start,s.status AS session_status,s.component_id
      FROM attendance_records r JOIN class_sessions s ON s.id=r.class_session_id
      WHERE r.tenant_id=? AND r.student_id=? ORDER BY s.scheduled_start""",(tenant_id,student_id))
    weighted=Decimal("0");denom=0;details=[];policy_versions=set()
    for r in rows:
        if r["session_status"] in {"cancelled","rescheduled"}:continue
        effects,minimum,pv=_policy_effects(request.state.store,r["attendance_policy_id"],r["scheduled_start"][:10]);effect=effects.get(r["status_code"]);policy_versions.add((r["attendance_policy_id"],pv))
        if effect is not None:weighted+=effect;denom+=1
        details.append({"session_id":r["class_session_id"],"component_id":r["component_id"],"scheduled_start":r["scheduled_start"],"status_code":r["status_code"],"effect":str(effect) if effect is not None else None})
    percentage=(weighted/denom*100).quantize(Decimal("0.01")) if denom else Decimal("0")
    return {"student_id":student_id,"attendance_percentage":str(percentage),"counted_sessions":denom,"policy_versions":[{"policy_id":p,"version":v} for p,v in sorted(policy_versions)],"details":details}


@router.get("/attendance/students/{student_id}",operation_id="get_student_attendance")
def student_attendance(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);assert_student_access(request,user,student_id);return _student_attendance_summary(student_id,request,tenant_id)


@router.get("/attendance/classes/{class_id}",operation_id="get_class_attendance")
def class_attendance(class_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);assert_class_access(request,user,class_id);sessions=request.state.store.fetch_all("SELECT id,status FROM class_sessions WHERE tenant_id=? AND class_group_id=?",(tenant_id,class_id));session_ids=[x["id"] for x in sessions if x["status"] not in {"cancelled","rescheduled"}]
    students={}
    for sid in session_ids:
        for r in request.state.store.fetch_all("SELECT student_id,status_code FROM attendance_records WHERE class_session_id=?",(sid,)):
            students.setdefault(r["student_id"],{}).setdefault(r["status_code"],0);students[r["student_id"]][r["status_code"]]+=1
    return {"class_group_id":class_id,"sessions":len(session_ids),"students":students}

