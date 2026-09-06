from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.operations.common import ADMIN_ROLES, boolint, dumps, require, row_or_404, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user
from app.shared.tenant_quotas import tenant_quota_limit

router=APIRouter(tags=["institutional-academic-core"])

class InstitutionInput(BaseModel):
    legal_name:str=Field(min_length=3,max_length=300);trade_name:str=Field(min_length=2,max_length=200);cnpj:str|None=None;education_system:str|None=None
class UnitInput(BaseModel):
    institution_id:str;code:str=Field(min_length=2,max_length=40);name:str=Field(min_length=2,max_length=200);timezone:str="America/Bahia";address:dict[str,Any]=Field(default_factory=dict)
class AcademicYearInput(BaseModel):
    institution_id:str;name:str;starts_on:date;ends_on:date
    @model_validator(mode="after")
    def dates(self):
        if self.ends_on<self.starts_on:raise ValueError("ends_on não pode anteceder starts_on")
        return self

class AcademicPeriodInput(BaseModel):
    academic_year_id: str
    name: str = Field(min_length=2, max_length=120)
    period_type: Literal["annual","semester","trimester","bimester","monthly","module","custom"]
    sequence: int = Field(ge=1, le=24)
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on não pode anteceder starts_on")
        return self
class ProgramInput(BaseModel):
    institution_id:str;code:str;name:str;education_level:str;modality:str|None=None
class CurriculumInput(BaseModel):
    program_id:str;code:str;name:str;effective_from:date;effective_until:date|None=None
class ComponentInput(BaseModel):
    curriculum_id:str;code:str;name:str;workload_hours:float=Field(ge=0);credits:float|None=Field(default=None,ge=0);syllabus:str|None=None
class ClassGroupInput(BaseModel):
    unit_id:str;academic_year_id:str;program_id:str;curriculum_id:str;code:str;name:str;shift:str|None=None;capacity:int|None=Field(default=None,ge=1);room:str|None=None
class PersonInput(BaseModel):
    full_name:str=Field(min_length=2,max_length=300);social_name:str|None=None;cpf:str|None=None;birth_date:date|None=None;email:EmailStr|None=None;phone:str|None=None;civil_data:dict[str,Any]=Field(default_factory=dict);address:dict[str,Any]=Field(default_factory=dict);emergency:dict[str,Any]=Field(default_factory=dict)
class StudentInput(BaseModel):
    person_id:str;registration_number:str=Field(min_length=1,max_length=80);needs:dict[str,Any]=Field(default_factory=dict)
class GuardianInput(BaseModel):person_id:str
class GuardianLinkInput(BaseModel):
    guardian_id:str;student_id:str;relationship:str;is_legal:bool=False;is_financial:bool=False;pickup_authorized:bool=False
class EmployeeInput(BaseModel):
    person_id:str;employee_number:str;department:str|None=None;position:str|None=None;admission_date:date|None=None
class TeacherAssignmentInput(BaseModel):
    employee_id:str;class_group_id:str;component_id:str;starts_on:date;ends_on:date|None=None;role:Literal["teacher","assistant_teacher"]="teacher"
class CandidateInput(BaseModel):
    person_id:str;program_id:str;academic_year_id:str;source:str|None=None;score:float|None=None;rank_position:int|None=None;notes:str|None=None
class EnrollmentInput(BaseModel):
    student_id:str;institution_id:str;unit_id:str;program_id:str;curriculum_id:str;academic_year_id:str;class_group_id:str|None=None;enrollment_number:str;financial_responsible_guardian_id:str|None=None
class EnrollmentAction(BaseModel):expected_version:int=Field(ge=1);reason:str=Field(min_length=3,max_length=2000)
class CandidateConvert(BaseModel):
    registration_number:str;institution_id:str;unit_id:str;curriculum_id:str;class_group_id:str|None=None;enrollment_number:str;financial_responsible_guardian_id:str|None=None

class CandidateStateInput(BaseModel):
    state: Literal["under_review", "approved", "selected", "waitlisted", "rejected", "cancelled"]
    reason: str = Field(min_length=3, max_length=2000)

class EnrollmentReserveInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)
    effective_on: date | None = None

class EnrollmentSuspendInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)
    effective_on: date | None = None

class EnrollmentCancelInput(BaseModel):
    expected_version: int = Field(ge=1)
    kind: Literal["cancelled", "withdrawn"] = "cancelled"
    reason: str = Field(min_length=3, max_length=2000)
    effective_on: date | None = None

class EnrollmentClassChangeInput(BaseModel):
    expected_version: int = Field(ge=1)
    class_group_id: str
    reason: str = Field(min_length=3, max_length=2000)
    effective_on: date | None = None

class EnrollmentTransferInput(BaseModel):
    expected_version: int = Field(ge=1)
    target_unit_id: str | None = None
    target_program_id: str | None = None
    target_curriculum_id: str | None = None
    target_class_group_id: str | None = None
    reason: str = Field(min_length=3, max_length=2000)
    effective_on: date | None = None

class EnrollmentRenewInput(BaseModel):
    enrollment_number: str = Field(min_length=1, max_length=80)
    academic_year_id: str
    unit_id: str | None = None
    program_id: str | None = None
    curriculum_id: str | None = None
    class_group_id: str | None = None
    financial_responsible_guardian_id: str | None = None
    reason: str = Field(min_length=3, max_length=2000)


def _create(request:Request,user:CurrentUser,table:str,fields:dict[str,Any],event:str)->dict[str,Any]:
    tid=tenant(user);now=iso_now();rid=uuid7();data={"id":rid,"tenant_id":tid,**fields,"created_at":now,"updated_at":now}
    cols=list(data);sql=f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' for _ in cols)})"
    with request.state.store.transaction() as conn:
        conn.execute(sql,tuple(data[c] for c in cols));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type=table,aggregate_id=rid,correlation_id=request.state.correlation_id,after=data);add_outbox(conn,tenant_id=tid,event_type=event,aggregate_type=table,aggregate_id=rid,payload=data,correlation_id=request.state.correlation_id)
    return data


def _enforce_active_student_quota(request: Request, conn, tenant_id: str) -> int:
    limit = tenant_quota_limit(
        request.app.state.data_router.control,
        tenant_id,
        "max_students",
    )
    request.state.store.transaction_lock(conn, f"tenant-active-student-quota:{tenant_id}")
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM students WHERE tenant_id=? AND state='active'",
        (tenant_id,),
    ).fetchone()
    if int(row["n"] if row else 0) >= limit:
        raise DomainError(
            "TENANT_QUOTA_EXCEEDED",
            f"A quota de alunos ativos ({limit}) foi atingida.",
            409,
        )
    return limit


def _list(request:Request,user:CurrentUser,table:str,order:str="created_at DESC",limit:int=100,where:str="",params:list[Any]|None=None):
    tid=tenant(user);params=[tid,*(params or [])];limit=min(max(limit,1),500);sql=f"SELECT * FROM {table} WHERE tenant_id=? {where} ORDER BY {order} LIMIT ?";params.append(limit);return {"items":request.state.store.fetch_all(sql,params),"limit":limit}



def _enrollment_movement(
    conn, *, tenant_id: str, enrollment_id: str, movement_type: str, from_state: str | None,
    to_state: str | None, from_unit_id: str | None, to_unit_id: str | None,
    from_class_group_id: str | None, to_class_group_id: str | None, effective_on: str,
    reason: str, actor_id: str, payload: dict[str, Any] | None = None,
) -> str:
    movement_id = uuid7()
    conn.execute(
        "INSERT INTO enrollment_movements(id,tenant_id,enrollment_id,movement_type,from_state,to_state,"
        "from_unit_id,to_unit_id,from_class_group_id,to_class_group_id,effective_on,reason,payload_json,actor_id,occurred_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (movement_id, tenant_id, enrollment_id, movement_type, from_state, to_state, from_unit_id, to_unit_id,
         from_class_group_id, to_class_group_id, effective_on, reason, dumps(payload or {}), actor_id, iso_now()),
    )
    return movement_id


def _assert_class_capacity(conn, tenant_id: str, class_group_id: str, *, exclude_enrollment_id: str | None = None) -> dict[str, Any]:
    group = conn.execute(
        "SELECT * FROM class_groups WHERE tenant_id=? AND id=? AND state='active'",
        (tenant_id, class_group_id),
    ).fetchone()
    if not group:
        raise DomainError("CLASS_GROUP_NOT_FOUND", "Turma não localizada.", 404)
    sql = "SELECT COUNT(*) AS n FROM enrollments WHERE tenant_id=? AND class_group_id=? AND state IN ('active','reserved')"
    params: list[Any] = [tenant_id, class_group_id]
    if exclude_enrollment_id:
        sql += " AND id<>?"
        params.append(exclude_enrollment_id)
    occupied = int(conn.execute(sql, tuple(params)).fetchone()["n"] or 0)
    admission_reserved = int(conn.execute(
        "SELECT COUNT(*) AS n FROM admission_vacancy_reservations WHERE tenant_id=? AND class_group_id=? AND state='reserved' AND expires_at>?",
        (tenant_id, class_group_id, iso_now()),
    ).fetchone()["n"] or 0)
    if group["capacity"] and occupied + admission_reserved >= int(group["capacity"]):
        raise DomainError("CLASS_CAPACITY_EXCEEDED", "Turma sem vagas disponíveis.", 409)
    return dict(group)

@router.get("/institutions",operation_id="list_institutions")
def list_institutions(request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _list(request,user,"institutions","trade_name")
@router.post("/institutions",status_code=201,operation_id="create_institution")
def create_institution(data:InstitutionInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"institutions",{"legal_name":data.legal_name,"trade_name":data.trade_name,"cnpj":data.cnpj,"education_system":data.education_system,"state":"active"},"InstitutionCreated")

@router.get("/units",operation_id="list_units")
def list_units(request:Request,institution_id:str|None=None,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"teacher","assistant_teacher"});return _list(request,user,"units","name",where="AND institution_id=?" if institution_id else "",params=[institution_id] if institution_id else [])
@router.post("/units",status_code=201,operation_id="create_unit")
def create_unit(data:UnitInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM institutions WHERE id=? AND tenant_id=?",(data.institution_id,tid),"INSTITUTION_NOT_FOUND","Instituição não localizada.")
    return _create(request,user,"units",{"institution_id":data.institution_id,"code":data.code,"name":data.name,"timezone":data.timezone,"address_json":dumps(data.address),"state":"active"},"UnitCreated")

@router.get("/academic-years",operation_id="list_academic_years")
def list_years(request:Request,institution_id:str|None=None,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"teacher","assistant_teacher"});return _list(request,user,"academic_years","starts_on DESC",where="AND institution_id=?" if institution_id else "",params=[institution_id] if institution_id else [])
@router.post("/academic-years",status_code=201,operation_id="create_academic_year")
def create_year(data:AcademicYearInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES)
    tid=tenant(user)
    row_or_404(request,"SELECT id FROM institutions WHERE id=? AND tenant_id=?",(data.institution_id,tid),"INSTITUTION_NOT_FOUND","Instituição não localizada.")
    year=_create(request,user,"academic_years",{"institution_id":data.institution_id,"name":data.name,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on),"state":"draft","version":1},"AcademicYearCreated")
    # Compatibilidade controlada: o período anual compartilha o UUID do ano letivo.
    # Isso preserva planos alpha que usavam academic_year_id como academic_period_id,
    # sem impedir períodos bimestrais/trimestrais reais.
    now=iso_now()
    with request.state.store.transaction() as conn:
        exists=conn.execute("SELECT id FROM academic_periods WHERE tenant_id=? AND id=?",(tid,year["id"])).fetchone()
        if not exists:
            period={"id":year["id"],"tenant_id":tid,"academic_year_id":year["id"],"name":f"{data.name} — Anual",
                    "period_type":"annual","sequence":1,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on),
                    "state":"active","version":1,"created_at":now,"updated_at":now}
            conn.execute("INSERT INTO academic_periods(id,tenant_id,academic_year_id,name,period_type,sequence,starts_on,ends_on,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",tuple(period[k] for k in ["id","tenant_id","academic_year_id","name","period_type","sequence","starts_on","ends_on","state","version","created_at","updated_at"]))
            add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="academic_periods",aggregate_id=period["id"],correlation_id=request.state.correlation_id,after=period)
            add_outbox(conn,tenant_id=tid,event_type="AcademicPeriodCreated",aggregate_type="academic_periods",aggregate_id=period["id"],payload=period,correlation_id=request.state.correlation_id)
    return {**year,"annual_period_id":year["id"]}

@router.get("/academic-periods",operation_id="list_academic_periods")
def list_periods(request:Request,academic_year_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"teacher","assistant_teacher"})
    return _list(request,user,"academic_periods","starts_on, sequence",where="AND academic_year_id=?" if academic_year_id else "",params=[academic_year_id] if academic_year_id else [])

@router.post("/academic-periods",status_code=201,operation_id="create_academic_period")
def create_period(data:AcademicPeriodInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES)
    tid=tenant(user)
    year=row_or_404(request,"SELECT id,starts_on,ends_on FROM academic_years WHERE tenant_id=? AND id=?",(tid,data.academic_year_id),"ACADEMIC_YEAR_NOT_FOUND","Ano letivo não localizado.")
    if str(data.starts_on) < str(year["starts_on"]) or str(data.ends_on) > str(year["ends_on"]):
        raise DomainError("ACADEMIC_PERIOD_OUTSIDE_YEAR","O período deve estar integralmente contido no ano letivo.",409)
    overlap=request.state.store.fetch_one(
        "SELECT id FROM academic_periods WHERE tenant_id=? AND academic_year_id=? AND period_type=? AND state!='archived' AND NOT (ends_on<? OR starts_on>?) LIMIT 1",
        (tid,data.academic_year_id,data.period_type,str(data.starts_on),str(data.ends_on)),
    )
    if overlap:
        raise DomainError("ACADEMIC_PERIOD_OVERLAP","Já existe período do mesmo tipo sobrepondo essas datas.",409)
    return _create(request,user,"academic_periods",{"academic_year_id":data.academic_year_id,"name":data.name,"period_type":data.period_type,"sequence":data.sequence,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on),"state":"active","version":1},"AcademicPeriodCreated")

@router.get("/programs",operation_id="list_programs")
def list_programs(request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"teacher","assistant_teacher"});return _list(request,user,"programs","name")
@router.post("/programs",status_code=201,operation_id="create_program")
def create_program(data:ProgramInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"programs",{"institution_id":data.institution_id,"code":data.code,"name":data.name,"education_level":data.education_level,"modality":data.modality,"state":"active"},"ProgramCreated")

@router.get("/curricula",operation_id="list_curricula")
def list_curricula(request:Request,program_id:str|None=None,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"teacher","assistant_teacher"});return _list(request,user,"curricula","effective_from DESC",where="AND program_id=?" if program_id else "",params=[program_id] if program_id else [])
@router.post("/curricula",status_code=201,operation_id="create_curriculum")
def create_curriculum(data:CurriculumInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);version=(request.state.store.scalar("SELECT COALESCE(MAX(version),0) AS n FROM curricula WHERE tenant_id=? AND program_id=? AND code=?",(tid,data.program_id,data.code)) or 0)+1
    return _create(request,user,"curricula",{"program_id":data.program_id,"code":data.code,"name":data.name,"version":int(version),"effective_from":str(data.effective_from),"effective_until":str(data.effective_until) if data.effective_until else None,"state":"active"},"CurriculumVersionCreated")

@router.get("/curriculum-components",operation_id="list_curriculum_components")
def list_components(request:Request,curriculum_id:str|None=None,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"teacher","assistant_teacher"});return _list(request,user,"curriculum_components","name",where="AND curriculum_id=?" if curriculum_id else "",params=[curriculum_id] if curriculum_id else [])
@router.post("/curriculum-components",status_code=201,operation_id="create_curriculum_component")
def create_component(data:ComponentInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"curriculum_components",{"curriculum_id":data.curriculum_id,"code":data.code,"name":data.name,"workload_hours":data.workload_hours,"credits":data.credits,"syllabus":data.syllabus,"state":"active"},"CurriculumComponentCreated")

@router.get("/class-groups",operation_id="list_class_groups")
def list_groups(request:Request,academic_year_id:str|None=None,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"teacher","assistant_teacher"});return _list(request,user,"class_groups","name",where="AND academic_year_id=?" if academic_year_id else "",params=[academic_year_id] if academic_year_id else [])
@router.post("/class-groups",status_code=201,operation_id="create_class_group")
def create_group(data:ClassGroupInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"class_groups",{"unit_id":data.unit_id,"academic_year_id":data.academic_year_id,"program_id":data.program_id,"curriculum_id":data.curriculum_id,"code":data.code,"name":data.name,"shift":data.shift,"capacity":data.capacity,"room":data.room,"state":"active"},"ClassGroupCreated")

@router.get("/people",operation_id="list_people")
def list_people(request:Request,q:str|None=None,limit:int=100,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"finance_manager","finance_operator","hr_manager","personnel_operator"});where="";params=[]
    if q:where="AND (full_name LIKE ? OR cpf LIKE ? OR email LIKE ?)";term=f"%{q}%";params=[term,term,term]
    return _list(request,user,"people","full_name",limit,where,params)
@router.post("/people",status_code=201,operation_id="create_person")
def create_person(data:PersonInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"hr_manager","personnel_operator"});tid=tenant(user);body=data.model_dump(mode="json");scope=f"create:people:{tid}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        now=iso_now();rid=uuid7();result={"id":rid,"tenant_id":tid,"full_name":data.full_name,"social_name":data.social_name,"cpf":data.cpf,"birth_date":str(data.birth_date) if data.birth_date else None,"email":str(data.email) if data.email else None,"phone":data.phone,"state":"active","created_at":now,"updated_at":now}
        conn.execute("INSERT INTO people(id,tenant_id,full_name,social_name,cpf,birth_date,email,phone,civil_data_json,address_json,emergency_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.full_name,data.social_name,data.cpf,str(data.birth_date) if data.birth_date else None,str(data.email) if data.email else None,data.phone,dumps(data.civil_data),dumps(data.address),dumps(data.emergency),"active",now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="people",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="PersonRegistered",aggregate_type="people",aggregate_id=rid,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    response.status_code=201;return result

@router.get("/students",operation_id="list_students_relational")
def list_students(request:Request,limit:int=100,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"finance_manager","finance_operator"});tid=tenant(user);return {"items":request.state.store.fetch_all("SELECT s.*,p.full_name,p.cpf,p.email FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? ORDER BY p.full_name LIMIT ?",(tid,min(max(limit,1),500)))}
@router.post("/students",status_code=201,operation_id="create_student_relational")
def create_student(data:StudentInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM people WHERE id=? AND tenant_id=?",(data.person_id,tid),"PERSON_NOT_FOUND","Pessoa não localizada.")
    now=iso_now();student_id=uuid7();result={"id":student_id,"tenant_id":tid,"person_id":data.person_id,"registration_number":data.registration_number,"state":"active","needs_json":dumps(data.needs),"created_at":now,"updated_at":now}
    with request.state.store.transaction() as conn:
        _enforce_active_student_quota(request,conn,tid)
        conn.execute("INSERT INTO students(id,tenant_id,person_id,registration_number,state,needs_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(student_id,tid,data.person_id,data.registration_number,"active",dumps(data.needs),now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="students",aggregate_id=student_id,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tid,event_type="StudentRegistered",aggregate_type="students",aggregate_id=student_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/students/{student_id}",operation_id="get_student_relational")
def get_student(student_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"finance_manager","finance_operator"});tid=tenant(user);return row_or_404(request,"SELECT s.*,p.full_name,p.cpf,p.email FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.id=?",(tid,student_id),"STUDENT_NOT_FOUND","Aluno não localizado.")

@router.post("/guardians",status_code=201,operation_id="create_guardian")
def create_guardian(data:GuardianInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"guardians",{"person_id":data.person_id,"state":"active"},"GuardianRegistered")
@router.post("/guardian-students",status_code=201,operation_id="link_guardian_student")
def link_guardian(data:GuardianLinkInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"guardian_students",{"guardian_id":data.guardian_id,"student_id":data.student_id,"relationship":data.relationship,"is_legal":boolint(data.is_legal),"is_financial":boolint(data.is_financial),"pickup_authorized":boolint(data.pickup_authorized)},"GuardianStudentLinked")

@router.get("/employees",operation_id="list_employees_relational")
def list_employees(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"hr_manager","personnel_operator","payroll_operator","timekeeping_operator"});tid=tenant(user);return {"items":request.state.store.fetch_all("SELECT e.*,p.full_name,p.email,p.cpf FROM employees e JOIN people p ON p.id=e.person_id WHERE e.tenant_id=? ORDER BY p.full_name",(tid,))}
@router.post("/employees",status_code=201,operation_id="create_employee_relational")
def create_employee(data:EmployeeInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES|{"hr_manager","personnel_operator"});return _create(request,user,"employees",{"person_id":data.person_id,"employee_number":data.employee_number,"department":data.department,"position":data.position,"admission_date":str(data.admission_date) if data.admission_date else None,"state":"active"},"EmployeeEmploymentActivated")

@router.get("/teacher-assignments",operation_id="list_teacher_assignments")
def list_assignments(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user)
    if "teacher" in user.roles or "assistant_teacher" in user.roles:
        if not user.person_id:return {"items":[]}
        employee=request.state.store.fetch_one("SELECT id FROM employees WHERE tenant_id=? AND person_id=? AND state='active'",(tid,user.person_id))
        if not employee:return {"items":[]}
        where="AND ta.employee_id=?";params=(tid,employee["id"])
    else:
        require(user,ADMIN_ROLES);where="";params=(tid,)
    sql=f"""SELECT ta.*,p.full_name AS teacher_name,cg.name AS class_group_name,cc.name AS component_name,u.id AS user_id
             FROM teacher_assignments ta JOIN employees e ON e.id=ta.employee_id JOIN people p ON p.id=e.person_id
             JOIN class_groups cg ON cg.id=ta.class_group_id JOIN curriculum_components cc ON cc.id=ta.component_id
             LEFT JOIN users u ON u.person_id=p.id AND u.tenant_id=ta.tenant_id AND u.active=1
             WHERE ta.tenant_id=? {where} ORDER BY cg.name,cc.name,p.full_name"""
    return {"items":request.state.store.fetch_all(sql,params)}
@router.post("/teacher-assignments",status_code=201,operation_id="create_teacher_assignment")
def create_assignment(data:TeacherAssignmentInput,request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);return _create(request,user,"teacher_assignments",{"employee_id":data.employee_id,"class_group_id":data.class_group_id,"component_id":data.component_id,"starts_on":str(data.starts_on),"ends_on":str(data.ends_on) if data.ends_on else None,"role":data.role,"state":"active"},"TeacherAssignmentCreated")

@router.get("/admissions/candidates",operation_id="list_admission_candidates")
def list_candidates(request:Request,user:CurrentUser=Depends(current_user)):require(user,ADMIN_ROLES);tid=tenant(user);return {"items":request.state.store.fetch_all("SELECT c.*,p.full_name FROM admission_candidates c JOIN people p ON p.id=c.person_id WHERE c.tenant_id=? ORDER BY c.created_at DESC",(tid,))}
@router.post("/admissions/candidates",status_code=201,operation_id="create_admission_candidate")
def create_candidate(data:CandidateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user)
    row_or_404(request,"SELECT id FROM people WHERE tenant_id=? AND id=? AND state='active'",(tid,data.person_id),"PERSON_NOT_FOUND","Pessoa não localizada.")
    program=row_or_404(request,"SELECT institution_id FROM programs WHERE tenant_id=? AND id=? AND state='active'",(tid,data.program_id),"PROGRAM_NOT_FOUND","Programa não localizado.")
    row_or_404(request,"SELECT id FROM academic_years WHERE tenant_id=? AND id=? AND institution_id=?",(tid,data.academic_year_id,program["institution_id"]),"ACADEMIC_YEAR_NOT_FOUND","Ano letivo não pertence à instituição do programa.")
    return _create(request,user,"admission_candidates",{"person_id":data.person_id,"program_id":data.program_id,"academic_year_id":data.academic_year_id,"source":data.source,"score":data.score,"rank_position":data.rank_position,"state":"registered","notes":data.notes},"AdmissionCandidateRegistered")

@router.post("/admissions/candidates/{candidate_id}/convert",status_code=201,operation_id="convert_candidate_to_enrollment")
def convert_candidate(candidate_id:str,data:CandidateConvert,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);cand=row_or_404(request,"SELECT * FROM admission_candidates WHERE id=? AND tenant_id=?",(candidate_id,tid),"CANDIDATE_NOT_FOUND","Candidato não localizado.");now=iso_now()
    if cand["state"] == "converted":
        existing=request.state.store.fetch_one("SELECT e.id AS enrollment_id,e.student_id,e.state FROM enrollments e JOIN students s ON s.id=e.student_id WHERE e.tenant_id=? AND s.person_id=? AND e.program_id=? AND e.academic_year_id=? ORDER BY e.created_at DESC LIMIT 1",(tid,cand["person_id"],cand["program_id"],cand["academic_year_id"]))
        if existing:return {"candidate_id":candidate_id,"student_id":existing["student_id"],"enrollment_id":existing["enrollment_id"],"state":existing["state"],"replayed":True}
        raise DomainError("CANDIDATE_ALREADY_CONVERTED","Candidato já foi convertido e exige reconciliação administrativa.",409)
    if cand["state"] not in {"registered","approved","selected"}:raise DomainError("CANDIDATE_NOT_CONVERTIBLE","Candidato não pode ser convertido neste estado.",409)
    row_or_404(request,"SELECT id FROM institutions WHERE tenant_id=? AND id=?",(tid,data.institution_id),"INSTITUTION_NOT_FOUND","Instituição não localizada.")
    row_or_404(request,"SELECT id FROM units WHERE tenant_id=? AND id=? AND institution_id=?",(tid,data.unit_id,data.institution_id),"UNIT_NOT_FOUND","Unidade não localizada.")
    row_or_404(request,"SELECT id FROM curricula WHERE tenant_id=? AND id=? AND program_id=?",(tid,data.curriculum_id,cand["program_id"]),"CURRICULUM_NOT_FOUND","Currículo não localizado.")
    if data.class_group_id:
        row_or_404(request,"SELECT id FROM class_groups WHERE tenant_id=? AND id=? AND unit_id=? AND program_id=? AND curriculum_id=? AND academic_year_id=?",(tid,data.class_group_id,data.unit_id,cand["program_id"],data.curriculum_id,cand["academic_year_id"]),"CLASS_GROUP_NOT_FOUND","Turma não localizada para o contexto do candidato.")
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn,f"tenant-active-student-quota:{tid}")
        student=conn.execute("SELECT * FROM students WHERE tenant_id=? AND person_id=?",(tid,cand["person_id"])).fetchone();student_id=student["id"] if student else uuid7()
        if not student:
            _enforce_active_student_quota(request,conn,tid)
            conn.execute("INSERT INTO students(id,tenant_id,person_id,registration_number,state,needs_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(student_id,tid,cand["person_id"],data.registration_number,"active","{}",now,now))
        reservation=None
        if data.class_group_id:
            reservation=conn.execute("SELECT * FROM admission_vacancy_reservations WHERE tenant_id=? AND candidate_id=? AND class_group_id=? AND state='reserved' AND expires_at>? ORDER BY created_at DESC LIMIT 1",(tid,candidate_id,data.class_group_id,now)).fetchone()
        enrollment_state="reserved" if reservation else "pre_enrolled"
        enrollment_id=uuid7();conn.execute("INSERT INTO enrollments(id,tenant_id,student_id,institution_id,unit_id,program_id,curriculum_id,academic_year_id,class_group_id,enrollment_number,financial_responsible_guardian_id,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(enrollment_id,tid,student_id,data.institution_id,data.unit_id,cand["program_id"],data.curriculum_id,cand["academic_year_id"],data.class_group_id,data.enrollment_number,data.financial_responsible_guardian_id,enrollment_state,1,now,now))
        if reservation:
            conn.execute("UPDATE admission_vacancy_reservations SET state='consumed',consumed_enrollment_id=?,updated_at=? WHERE tenant_id=? AND id=? AND state='reserved'",(enrollment_id,now,tid,reservation["id"]))
            _enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="admission_reservation_consumed",from_state="pre_enrolled",to_state="reserved",from_unit_id=data.unit_id,to_unit_id=data.unit_id,from_class_group_id=data.class_group_id,to_class_group_id=data.class_group_id,effective_on=now[:10],reason="Reserva do processo seletivo consumida na conversão",actor_id=user.id,payload={"reservation_id":reservation["id"],"candidate_id":candidate_id})
        conn.execute("UPDATE admission_candidates SET state='converted',updated_at=? WHERE id=?",(now,candidate_id));conn.execute("INSERT INTO admission_candidate_events(id,tenant_id,candidate_id,event_type,from_state,to_state,reason,payload_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,candidate_id,"conversion",cand["state"],"converted","Conversão em pré-matrícula",dumps({"enrollment_id":enrollment_id,"student_id":student_id,"reservation_id":reservation["id"] if reservation else None}),user.id,now));result={"candidate_id":candidate_id,"student_id":student_id,"enrollment_id":enrollment_id,"state":enrollment_state,"reservation_id":reservation["id"] if reservation else None};add_audit(conn,tenant_id=tid,actor_id=user.id,action="convert",aggregate_type="admission_candidate",aggregate_id=candidate_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="AdmissionCandidateConverted",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/enrollments",operation_id="list_enrollments_relational")
def list_enrollments(request:Request,state:str|None=None,student_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"finance_manager","finance_operator"});tid=tenant(user);sql="""SELECT e.*,p.full_name AS student_name,cg.name AS class_group_name,pr.name AS program_name FROM enrollments e JOIN students s ON s.id=e.student_id JOIN people p ON p.id=s.person_id JOIN programs pr ON pr.id=e.program_id LEFT JOIN class_groups cg ON cg.id=e.class_group_id WHERE e.tenant_id=?""";params:[Any]=[tid]
    if state:sql+=" AND e.state=?";params.append(state)
    if student_id:sql+=" AND e.student_id=?";params.append(student_id)
    sql+=" ORDER BY e.created_at DESC";return {"items":request.state.store.fetch_all(sql,params)}
@router.post("/enrollments",status_code=201,operation_id="create_enrollment_relational")
def create_enrollment(data:EnrollmentInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);body=data.model_dump(mode="json");scope=f"enrollment:create:{tid}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        if not conn.execute("SELECT id FROM students WHERE tenant_id=? AND id=? AND state='active'",(tid,data.student_id)).fetchone():raise DomainError("STUDENT_NOT_FOUND","Aluno não localizado.",404)
        if not conn.execute("SELECT id FROM institutions WHERE tenant_id=? AND id=? AND state='active'",(tid,data.institution_id)).fetchone():raise DomainError("INSTITUTION_NOT_FOUND","Instituição não localizada.",404)
        if not conn.execute("SELECT id FROM units WHERE tenant_id=? AND id=? AND institution_id=? AND state='active'",(tid,data.unit_id,data.institution_id)).fetchone():raise DomainError("UNIT_NOT_FOUND","Unidade não pertence à instituição.",404)
        if not conn.execute("SELECT id FROM programs WHERE tenant_id=? AND id=? AND institution_id=? AND state='active'",(tid,data.program_id,data.institution_id)).fetchone():raise DomainError("PROGRAM_NOT_FOUND","Programa não pertence à instituição.",404)
        if not conn.execute("SELECT id FROM curricula WHERE tenant_id=? AND id=? AND program_id=? AND state='active'",(tid,data.curriculum_id,data.program_id)).fetchone():raise DomainError("CURRICULUM_CONTEXT_MISMATCH","Currículo não pertence ao programa.",409)
        if not conn.execute("SELECT id FROM academic_years WHERE tenant_id=? AND id=? AND institution_id=?",(tid,data.academic_year_id,data.institution_id)).fetchone():raise DomainError("ACADEMIC_YEAR_NOT_FOUND","Ano letivo não pertence à instituição.",404)
        if data.class_group_id:
            group=conn.execute("SELECT id FROM class_groups WHERE tenant_id=? AND id=? AND unit_id=? AND academic_year_id=? AND program_id=? AND curriculum_id=? AND state='active'",(tid,data.class_group_id,data.unit_id,data.academic_year_id,data.program_id,data.curriculum_id)).fetchone()
            if not group:raise DomainError("CLASS_GROUP_CONTEXT_MISMATCH","Turma não pertence ao contexto acadêmico da matrícula.",409)
        if data.financial_responsible_guardian_id and not conn.execute("SELECT id FROM guardians WHERE tenant_id=? AND id=? AND state='active'",(tid,data.financial_responsible_guardian_id)).fetchone():raise DomainError("GUARDIAN_NOT_FOUND","Responsável financeiro não localizado.",404)
        now=iso_now();eid=uuid7();result={"id":eid,"tenant_id":tid,**body,"state":"pre_enrolled","version":1,"created_at":now,"updated_at":now};conn.execute("INSERT INTO enrollments(id,tenant_id,student_id,institution_id,unit_id,program_id,curriculum_id,academic_year_id,class_group_id,enrollment_number,financial_responsible_guardian_id,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(eid,tid,data.student_id,data.institution_id,data.unit_id,data.program_id,data.curriculum_id,data.academic_year_id,data.class_group_id,data.enrollment_number,data.financial_responsible_guardian_id,"pre_enrolled",1,now,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="enrollment",aggregate_id=eid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="EnrollmentCreated",aggregate_type="enrollment",aggregate_id=eid,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result

@router.post("/enrollments/{enrollment_id}/activate",operation_id="activate_enrollment_relational")
def activate_enrollment(enrollment_id:str,data:EnrollmentAction,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM enrollments WHERE id=? AND tenant_id=?",(enrollment_id,tid)).fetchone()
        if not row:raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"] not in {"pre_enrolled","reserved","suspended"}:raise DomainError("INVALID_STATE_TRANSITION","Matrícula não pode ser ativada neste estado.",409)
        if row["class_group_id"]:_assert_class_capacity(conn,tid,row["class_group_id"],exclude_enrollment_id=enrollment_id)
        unit_row=conn.execute("SELECT timezone FROM units WHERE tenant_id=? AND id=?",(tid,row["unit_id"])).fetchone(); tz_name=(unit_row["timezone"] if unit_row and unit_row["timezone"] else "America/Bahia")
        try: effective_date=datetime.now(ZoneInfo(tz_name)).date().isoformat()
        except Exception: effective_date=date.today().isoformat()
        version=row["version"]+1;conn.execute("UPDATE enrollments SET state='active',enrolled_on=COALESCE(enrolled_on,?),ended_on=NULL,version=?,updated_at=? WHERE id=?",(effective_date,version,now,enrollment_id));movement_id=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="activation" if row["state"]!="suspended" else "reopening",from_state=row["state"],to_state="active",from_unit_id=row["unit_id"],to_unit_id=row["unit_id"],from_class_group_id=row["class_group_id"],to_class_group_id=row["class_group_id"],effective_on=effective_date,reason=data.reason,actor_id=user.id);result={"id":enrollment_id,"state":"active","version":version,"enrolled_on":row["enrolled_on"] or effective_date,"movement_id":movement_id};add_audit(conn,tenant_id=tid,actor_id=user.id,action="activate",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentActivated",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/references/catalog",operation_id="tenant_reference_catalog")
def reference_catalog(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES|{"finance_manager","finance_operator","hr_manager","personnel_operator","inventory_manager","library_manager","transport_manager","health_operator"});tid=tenant(user)
    def rows(sql:str):return request.state.store.fetch_all(sql,(tid,))
    return {"people":rows("SELECT id,COALESCE(NULLIF(social_name,''),full_name) AS label FROM people WHERE tenant_id=? AND state='active' ORDER BY full_name"),"institutions":rows("SELECT id,trade_name AS label FROM institutions WHERE tenant_id=? AND state='active' ORDER BY trade_name"),"units":rows("SELECT id,name AS label,institution_id FROM units WHERE tenant_id=? AND state='active' ORDER BY name"),"academic_years":rows("SELECT id,name AS label,state FROM academic_years WHERE tenant_id=? ORDER BY starts_on DESC"),"academic_periods":rows("SELECT id,name AS label,academic_year_id,period_type,sequence,starts_on,ends_on,state FROM academic_periods WHERE tenant_id=? AND state='active' ORDER BY starts_on,sequence"),"programs":rows("SELECT id,name AS label FROM programs WHERE tenant_id=? AND state='active' ORDER BY name"),"curricula":rows("SELECT id,name AS label,program_id,version FROM curricula WHERE tenant_id=? AND state='active' ORDER BY name"),"components":rows("SELECT id,name AS label,curriculum_id FROM curriculum_components WHERE tenant_id=? AND state='active' ORDER BY name"),"class_groups":rows("SELECT id,name AS label,curriculum_id,program_id FROM class_groups WHERE tenant_id=? AND state='active' ORDER BY name"),"students":rows("SELECT s.id,p.full_name AS label FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.state='active' ORDER BY p.full_name"),"guardians":rows("SELECT g.id,p.full_name AS label FROM guardians g JOIN people p ON p.id=g.person_id WHERE g.tenant_id=? AND g.state='active' ORDER BY p.full_name"),"employees":rows("SELECT e.id,p.full_name AS label,e.position FROM employees e JOIN people p ON p.id=e.person_id WHERE e.tenant_id=? AND e.state='active' ORDER BY p.full_name")}

@router.get("/admissions/candidates/{candidate_id}", operation_id="get_admission_candidate")
def get_candidate(candidate_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES)
    tid = tenant(user)
    candidate = row_or_404(
        request,
        "SELECT c.*,p.full_name,p.email FROM admission_candidates c JOIN people p ON p.id=c.person_id WHERE c.tenant_id=? AND c.id=?",
        (tid, candidate_id),
        "CANDIDATE_NOT_FOUND",
        "Candidato não localizado.",
    )
    candidate["events"] = request.state.store.fetch_all(
        "SELECT * FROM admission_candidate_events WHERE tenant_id=? AND candidate_id=? ORDER BY occurred_at,id",
        (tid, candidate_id),
    )
    return candidate


@router.post("/admissions/candidates/{candidate_id}/state", operation_id="transition_admission_candidate")
def transition_candidate(candidate_id: str, data: CandidateStateInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES)
    tid = tenant(user)
    allowed = {
        "registered": {"under_review", "approved", "waitlisted", "rejected", "cancelled"},
        "under_review": {"approved", "waitlisted", "rejected", "cancelled"},
        "approved": {"selected", "waitlisted", "rejected", "cancelled"},
        "waitlisted": {"selected", "rejected", "cancelled"},
        "selected": {"cancelled"},
    }
    now = iso_now()
    with request.state.store.transaction() as conn:
        raw = conn.execute("SELECT * FROM admission_candidates WHERE tenant_id=? AND id=?", (tid, candidate_id)).fetchone()
        if not raw:
            raise DomainError("CANDIDATE_NOT_FOUND", "Candidato não localizado.", 404)
        candidate = dict(raw)
        if candidate["state"] == "converted":
            raise DomainError("CANDIDATE_ALREADY_CONVERTED", "Candidato já foi convertido em matrícula.", 409)
        if data.state not in allowed.get(candidate["state"], set()):
            raise DomainError("INVALID_STATE_TRANSITION", "Transição de candidato não permitida.", 409)
        conn.execute("UPDATE admission_candidates SET state=?,updated_at=? WHERE tenant_id=? AND id=?", (data.state, now, tid, candidate_id))
        event_id = uuid7()
        conn.execute(
            "INSERT INTO admission_candidate_events(id,tenant_id,candidate_id,event_type,from_state,to_state,reason,payload_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (event_id, tid, candidate_id, "state_transition", candidate["state"], data.state, data.reason, "{}", user.id, now),
        )
        result = {"id": candidate_id, "state": data.state, "previous_state": candidate["state"], "event_id": event_id}
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="transition", aggregate_type="admission_candidate", aggregate_id=candidate_id, correlation_id=request.state.correlation_id, before={"state": candidate["state"]}, after=result, reason=data.reason)
        add_outbox(conn, tenant_id=tid, event_type="AdmissionCandidateStateChanged", aggregate_type="admission_candidate", aggregate_id=candidate_id, payload=result, correlation_id=request.state.correlation_id)
    return result


@router.get("/class-groups/{class_group_id}/capacity", operation_id="get_class_group_capacity")
def class_group_capacity(class_group_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES | {"teacher", "assistant_teacher"})
    tid = tenant(user)
    group = row_or_404(request, "SELECT * FROM class_groups WHERE tenant_id=? AND id=?", (tid, class_group_id), "CLASS_GROUP_NOT_FOUND", "Turma não localizada.")
    occupied = int(request.state.store.scalar(
        "SELECT COUNT(*) AS n FROM enrollments WHERE tenant_id=? AND class_group_id=? AND state IN ('active','reserved')",
        (tid, class_group_id),
    ) or 0)
    admission_reserved = int(request.state.store.scalar(
        "SELECT COUNT(*) AS n FROM admission_vacancy_reservations WHERE tenant_id=? AND class_group_id=? AND state='reserved' AND expires_at>?",
        (tid, class_group_id, iso_now()),
    ) or 0)
    capacity = int(group["capacity"] or 0);committed=occupied+admission_reserved
    return {"class_group_id": class_group_id, "capacity": capacity or None, "occupied": occupied, "admission_reserved": admission_reserved, "committed": committed, "available": max(capacity - committed, 0) if capacity else None}


@router.get("/enrollments/{enrollment_id}", operation_id="get_enrollment_relational")
def get_enrollment(enrollment_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES | {"finance_manager", "finance_operator", "auditor"})
    tid = tenant(user)
    enrollment = row_or_404(
        request,
        "SELECT e.*,p.full_name AS student_name,cg.name AS class_group_name,pr.name AS program_name,u.name AS unit_name FROM enrollments e JOIN students s ON s.id=e.student_id JOIN people p ON p.id=s.person_id JOIN programs pr ON pr.id=e.program_id JOIN units u ON u.id=e.unit_id LEFT JOIN class_groups cg ON cg.id=e.class_group_id WHERE e.tenant_id=? AND e.id=?",
        (tid, enrollment_id),
        "ENROLLMENT_NOT_FOUND",
        "Matrícula não localizada.",
    )
    enrollment["movements"] = request.state.store.fetch_all(
        "SELECT * FROM enrollment_movements WHERE tenant_id=? AND enrollment_id=? ORDER BY occurred_at,id",
        (tid, enrollment_id),
    )
    return enrollment


@router.get("/enrollments/{enrollment_id}/movements", operation_id="list_enrollment_movements")
def list_enrollment_movements(enrollment_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES | {"auditor"})
    tid = tenant(user)
    row_or_404(request, "SELECT id FROM enrollments WHERE tenant_id=? AND id=?", (tid, enrollment_id), "ENROLLMENT_NOT_FOUND", "Matrícula não localizada.")
    return {"items": request.state.store.fetch_all("SELECT * FROM enrollment_movements WHERE tenant_id=? AND enrollment_id=? ORDER BY occurred_at,id", (tid, enrollment_id))}


@router.post("/enrollments/{enrollment_id}/reserve", operation_id="reserve_enrollment_vacancy")
def reserve_enrollment(enrollment_id: str, data: EnrollmentReserveInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid = tenant(user); now = iso_now(); effective = str(data.effective_on or date.today())
    with request.state.store.transaction() as conn:
        raw = conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?", (tid, enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND", "Matrícula não localizada.", 404)
        row = dict(raw)
        if row["version"] != data.expected_version: raise DomainError("VERSION_CONFLICT", "Versão divergente.", 409)
        if row["state"] != "pre_enrolled": raise DomainError("INVALID_STATE_TRANSITION", "Somente pré-matrícula pode reservar vaga.", 409)
        if not row["class_group_id"]: raise DomainError("CLASS_GROUP_REQUIRED", "Defina a turma antes de reservar a vaga.", 409)
        _assert_class_capacity(conn, tid, row["class_group_id"], exclude_enrollment_id=enrollment_id)
        version = row["version"] + 1
        conn.execute("UPDATE enrollments SET state='reserved',version=?,updated_at=? WHERE tenant_id=? AND id=?", (version, now, tid, enrollment_id))
        movement_id = _enrollment_movement(conn, tenant_id=tid, enrollment_id=enrollment_id, movement_type="vacancy_reserved", from_state=row["state"], to_state="reserved", from_unit_id=row["unit_id"], to_unit_id=row["unit_id"], from_class_group_id=row["class_group_id"], to_class_group_id=row["class_group_id"], effective_on=effective, reason=data.reason, actor_id=user.id)
        result={"id":enrollment_id,"state":"reserved","version":version,"movement_id":movement_id}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="reserve",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="EnrollmentVacancyReserved",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/enrollments/{enrollment_id}/suspend", operation_id="suspend_enrollment")
def suspend_enrollment(enrollment_id: str, data: EnrollmentSuspendInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid=tenant(user); now=iso_now(); effective=str(data.effective_on or date.today())
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        row=dict(raw)
        if row["version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"]!="active": raise DomainError("INVALID_STATE_TRANSITION","Somente matrícula ativa pode ser trancada/suspensa.",409)
        version=row["version"]+1;conn.execute("UPDATE enrollments SET state='suspended',version=?,updated_at=? WHERE tenant_id=? AND id=?",(version,now,tid,enrollment_id))
        mid=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="suspension",from_state="active",to_state="suspended",from_unit_id=row["unit_id"],to_unit_id=row["unit_id"],from_class_group_id=row["class_group_id"],to_class_group_id=row["class_group_id"],effective_on=effective,reason=data.reason,actor_id=user.id)
        result={"id":enrollment_id,"state":"suspended","version":version,"movement_id":mid};add_audit(conn,tenant_id=tid,actor_id=user.id,action="suspend",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentSuspended",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/enrollments/{enrollment_id}/cancel", operation_id="cancel_or_withdraw_enrollment")
def cancel_enrollment(enrollment_id: str, data: EnrollmentCancelInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid=tenant(user); now=iso_now(); effective=str(data.effective_on or date.today())
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        row=dict(raw)
        if row["version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"] in {"cancelled","withdrawn","transferred","completed"}: raise DomainError("INVALID_STATE_TRANSITION","Matrícula já está encerrada.",409)
        version=row["version"]+1;conn.execute("UPDATE enrollments SET state=?,ended_on=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(data.kind,effective,version,now,tid,enrollment_id))
        mid=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type=data.kind,from_state=row["state"],to_state=data.kind,from_unit_id=row["unit_id"],to_unit_id=row["unit_id"],from_class_group_id=row["class_group_id"],to_class_group_id=row["class_group_id"],effective_on=effective,reason=data.reason,actor_id=user.id)
        result={"id":enrollment_id,"state":data.kind,"version":version,"ended_on":effective,"movement_id":mid};add_audit(conn,tenant_id=tid,actor_id=user.id,action=data.kind,aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentWithdrawn" if data.kind=="withdrawn" else "EnrollmentCancelled",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/enrollments/{enrollment_id}/change-class", operation_id="change_enrollment_class_group")
def change_enrollment_class(enrollment_id: str, data: EnrollmentClassChangeInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid=tenant(user); now=iso_now(); effective=str(data.effective_on or date.today())
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        row=dict(raw)
        if row["version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"] not in {"active","reserved"}: raise DomainError("INVALID_STATE_TRANSITION","Matrícula não permite mudança de turma neste estado.",409)
        target=conn.execute("SELECT * FROM class_groups WHERE tenant_id=? AND id=? AND unit_id=? AND academic_year_id=? AND program_id=? AND curriculum_id=?",(tid,data.class_group_id,row["unit_id"],row["academic_year_id"],row["program_id"],row["curriculum_id"])).fetchone()
        if not target: raise DomainError("CLASS_GROUP_CONTEXT_MISMATCH","Turma de destino não pertence ao contexto acadêmico da matrícula.",409)
        _assert_class_capacity(conn,tid,data.class_group_id,exclude_enrollment_id=enrollment_id)
        version=row["version"]+1;conn.execute("UPDATE enrollments SET class_group_id=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(data.class_group_id,version,now,tid,enrollment_id))
        mid=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="class_change",from_state=row["state"],to_state=row["state"],from_unit_id=row["unit_id"],to_unit_id=row["unit_id"],from_class_group_id=row["class_group_id"],to_class_group_id=data.class_group_id,effective_on=effective,reason=data.reason,actor_id=user.id)
        result={"id":enrollment_id,"state":row["state"],"version":version,"class_group_id":data.class_group_id,"movement_id":mid};add_audit(conn,tenant_id=tid,actor_id=user.id,action="change_class",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentClassChanged",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/enrollments/{enrollment_id}/transfer", operation_id="transfer_enrollment")
def transfer_enrollment(enrollment_id: str, data: EnrollmentTransferInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid=tenant(user); now=iso_now(); effective=str(data.effective_on or date.today())
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        row=dict(raw)
        if row["version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"] not in {"active","suspended"}: raise DomainError("INVALID_STATE_TRANSITION","Matrícula não pode ser transferida neste estado.",409)
        internal = data.target_unit_id is not None
        to_unit=row["unit_id"];to_program=row["program_id"];to_curriculum=row["curriculum_id"];to_class=row["class_group_id"];to_state="transferred";ended=effective
        if internal:
            to_unit=data.target_unit_id or row["unit_id"];to_program=data.target_program_id or row["program_id"];to_curriculum=data.target_curriculum_id or row["curriculum_id"];to_class=data.target_class_group_id
            unit=conn.execute("SELECT id FROM units WHERE tenant_id=? AND id=? AND institution_id=? AND state='active'",(tid,to_unit,row["institution_id"])).fetchone()
            if not unit: raise DomainError("UNIT_NOT_FOUND","Unidade de destino não localizada.",404)
            curr=conn.execute("SELECT id FROM curricula WHERE tenant_id=? AND id=? AND program_id=?",(tid,to_curriculum,to_program)).fetchone()
            if not curr: raise DomainError("CURRICULUM_CONTEXT_MISMATCH","Currículo de destino não pertence ao programa.",409)
            if to_class:
                target=conn.execute("SELECT id FROM class_groups WHERE tenant_id=? AND id=? AND unit_id=? AND academic_year_id=? AND program_id=? AND curriculum_id=?",(tid,to_class,to_unit,row["academic_year_id"],to_program,to_curriculum)).fetchone()
                if not target: raise DomainError("CLASS_GROUP_CONTEXT_MISMATCH","Turma de destino inválida.",409)
                _assert_class_capacity(conn,tid,to_class,exclude_enrollment_id=enrollment_id)
            to_state="active";ended=None
        version=row["version"]+1
        conn.execute("UPDATE enrollments SET unit_id=?,program_id=?,curriculum_id=?,class_group_id=?,state=?,ended_on=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(to_unit,to_program,to_curriculum,to_class,to_state,ended,version,now,tid,enrollment_id))
        mid=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="internal_transfer" if internal else "external_transfer",from_state=row["state"],to_state=to_state,from_unit_id=row["unit_id"],to_unit_id=to_unit if internal else None,from_class_group_id=row["class_group_id"],to_class_group_id=to_class if internal else None,effective_on=effective,reason=data.reason,actor_id=user.id,payload={"program_id":to_program if internal else None,"curriculum_id":to_curriculum if internal else None})
        result={"id":enrollment_id,"state":to_state,"version":version,"unit_id":to_unit if internal else row["unit_id"],"class_group_id":to_class if internal else row["class_group_id"],"ended_on":ended,"movement_id":mid};add_audit(conn,tenant_id=tid,actor_id=user.id,action="transfer",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentTransferred",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/enrollments/{enrollment_id}/complete", operation_id="complete_enrollment")
def complete_enrollment(enrollment_id: str, data: EnrollmentAction, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid=tenant(user); now=iso_now(); effective=now[:10]
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        row=dict(raw)
        if row["version"]!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"]!="active": raise DomainError("INVALID_STATE_TRANSITION","Somente matrícula ativa pode ser concluída.",409)
        version=row["version"]+1;conn.execute("UPDATE enrollments SET state='completed',ended_on=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(effective,version,now,tid,enrollment_id))
        mid=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="completion",from_state="active",to_state="completed",from_unit_id=row["unit_id"],to_unit_id=row["unit_id"],from_class_group_id=row["class_group_id"],to_class_group_id=row["class_group_id"],effective_on=effective,reason=data.reason,actor_id=user.id)
        result={"id":enrollment_id,"state":"completed","version":version,"ended_on":effective,"movement_id":mid};add_audit(conn,tenant_id=tid,actor_id=user.id,action="complete",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentCompleted",aggregate_type="enrollment",aggregate_id=enrollment_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/enrollments/{enrollment_id}/renew", status_code=201, operation_id="renew_enrollment")
def renew_enrollment(enrollment_id: str, data: EnrollmentRenewInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES); tid=tenant(user); now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM enrollments WHERE tenant_id=? AND id=?",(tid,enrollment_id)).fetchone()
        if not raw: raise DomainError("ENROLLMENT_NOT_FOUND","Matrícula não localizada.",404)
        row=dict(raw)
        if row["state"] not in {"active","completed"}: raise DomainError("INVALID_STATE_TRANSITION","Matrícula não pode originar rematrícula neste estado.",409)
        unit_id=data.unit_id or row["unit_id"];program_id=data.program_id or row["program_id"];curriculum_id=data.curriculum_id or row["curriculum_id"]
        year=conn.execute("SELECT * FROM academic_years WHERE tenant_id=? AND id=? AND institution_id=?",(tid,data.academic_year_id,row["institution_id"])).fetchone()
        if not year: raise DomainError("ACADEMIC_YEAR_NOT_FOUND","Ano letivo de destino não localizado.",404)
        unit=conn.execute("SELECT id FROM units WHERE tenant_id=? AND id=? AND institution_id=?",(tid,unit_id,row["institution_id"])).fetchone()
        if not unit: raise DomainError("UNIT_NOT_FOUND","Unidade de destino não localizada.",404)
        curr=conn.execute("SELECT id FROM curricula WHERE tenant_id=? AND id=? AND program_id=?",(tid,curriculum_id,program_id)).fetchone()
        if not curr: raise DomainError("CURRICULUM_CONTEXT_MISMATCH","Currículo de destino inválido.",409)
        if data.class_group_id:
            target=conn.execute("SELECT id FROM class_groups WHERE tenant_id=? AND id=? AND unit_id=? AND academic_year_id=? AND program_id=? AND curriculum_id=?",(tid,data.class_group_id,unit_id,data.academic_year_id,program_id,curriculum_id)).fetchone()
            if not target: raise DomainError("CLASS_GROUP_CONTEXT_MISMATCH","Turma de destino inválida.",409)
            _assert_class_capacity(conn,tid,data.class_group_id)
        new_id=uuid7();guardian=data.financial_responsible_guardian_id if data.financial_responsible_guardian_id is not None else row["financial_responsible_guardian_id"]
        conn.execute("INSERT INTO enrollments(id,tenant_id,student_id,institution_id,unit_id,program_id,curriculum_id,academic_year_id,class_group_id,enrollment_number,financial_responsible_guardian_id,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(new_id,tid,row["student_id"],row["institution_id"],unit_id,program_id,curriculum_id,data.academic_year_id,data.class_group_id,data.enrollment_number,guardian,"pre_enrolled",1,now,now))
        mid=_enrollment_movement(conn,tenant_id=tid,enrollment_id=enrollment_id,movement_type="renewal_created",from_state=row["state"],to_state=row["state"],from_unit_id=row["unit_id"],to_unit_id=unit_id,from_class_group_id=row["class_group_id"],to_class_group_id=data.class_group_id,effective_on=str(year["starts_on"]),reason=data.reason,actor_id=user.id,payload={"new_enrollment_id":new_id,"academic_year_id":data.academic_year_id})
        result={"source_enrollment_id":enrollment_id,"id":new_id,"student_id":row["student_id"],"academic_year_id":data.academic_year_id,"state":"pre_enrolled","version":1,"movement_id":mid};add_audit(conn,tenant_id=tid,actor_id=user.id,action="renew",aggregate_type="enrollment",aggregate_id=enrollment_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="EnrollmentRenewalCreated",aggregate_type="enrollment",aggregate_id=new_id,payload=result,correlation_id=request.state.correlation_id)
    return result
