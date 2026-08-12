from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.modules.finance.application.ledger import money
from backend.app.modules.hr.presentation.schemas import (
    AdmissionCreate,
    AdmissionHire,
    AdmissionTransition,
    ApplicationCreate,
    ApplicationStage,
    BenefitPlanCreate,
    CandidateCreate,
    CompetencyCreate,
    DepartmentCreate,
    DepartmentPatch,
    DevelopmentPlanCreate,
    DevelopmentPlanProgress,
    EmployeeBenefitCreate,
    EmployeeCompetencyUpsert,
    EmployeePatch,
    JobOpeningCreate,
    JobOpeningTransition,
    LeaveCreate,
    LeaveTransition,
    OccurrenceCreate,
    OccurrenceResolve,
    OnboardingTaskComplete,
    OnboardingTaskCreate,
    PerformanceReviewComplete,
    PerformanceReviewCreate,
    PositionCreate,
    PositionPatch,
    TrainingComplete,
    TrainingCourseCreate,
    TrainingEnroll,
    VacationCreate,
    VacationTransition,
)
from backend.app.shared.application.audit import audit_tenant, emit_tenant_event
from backend.app.shared.application.idempotency import complete, reserve_tenant
from backend.app.shared.application.serialization import model_to_dict
from backend.app.shared.database.models_tenant import (
    AdmissionProcess,
    BenefitPlan,
    Competency,
    CostCenter,
    DevelopmentPlan,
    Employee,
    EmployeeAssignment,
    EmployeeBenefit,
    EmployeeCompetency,
    EmployeeLeave,
    EmployeeOccurrence,
    EmploymentContract,
    JobOpening,
    JobPosition,
    OnboardingTask,
    OrganizationalDepartment,
    PerformanceReview,
    Person,
    RecruitmentApplication,
    RecruitmentCandidate,
    RecruitmentStageHistory,
    SalaryHistory,
    TrainingCourse,
    TrainingEnrollment,
    VacationPeriod,
    WorkSchedule,
)
from backend.app.shared.domain.dates import utcnow
from backend.app.shared.domain.errors import ConflictError, NotFoundError, ValidationError
from backend.app.shared.domain.ids import new_id
from backend.app.shared.security.permissions import Actor

T = TypeVar("T")


def _number(prefix: str) -> str:
    return f"{prefix}-{new_id().replace('-', '')[-16:].upper()}"


def _get(session: Session, model: type[T], tenant_id: str, row_id: str, *, code: str, message: str) -> T:
    row = session.scalar(select(model).where(model.id == row_id, model.tenant_id == tenant_id, model.deleted_at.is_(None)))
    if row is None:
        raise NotFoundError(message, code=code)
    return row


def _get_person(session: Session, tenant_id: str, person_id: str) -> Person:
    return _get(session, Person, tenant_id, person_id, code="PERSON_NOT_FOUND", message="Pessoa não encontrada.")


def _get_department(session: Session, tenant_id: str, department_id: str) -> OrganizationalDepartment:
    return _get(session, OrganizationalDepartment, tenant_id, department_id, code="DEPARTMENT_NOT_FOUND", message="Departamento não encontrado.")


def _get_position(session: Session, tenant_id: str, position_id: str) -> JobPosition:
    return _get(session, JobPosition, tenant_id, position_id, code="JOB_POSITION_NOT_FOUND", message="Cargo não encontrado.")


def _get_opening(session: Session, tenant_id: str, opening_id: str) -> JobOpening:
    return _get(session, JobOpening, tenant_id, opening_id, code="JOB_OPENING_NOT_FOUND", message="Vaga não encontrada.")


def _get_candidate(session: Session, tenant_id: str, candidate_id: str) -> RecruitmentCandidate:
    return _get(session, RecruitmentCandidate, tenant_id, candidate_id, code="CANDIDATE_NOT_FOUND", message="Candidato não encontrado.")


def _get_application(session: Session, tenant_id: str, application_id: str) -> RecruitmentApplication:
    return _get(session, RecruitmentApplication, tenant_id, application_id, code="RECRUITMENT_APPLICATION_NOT_FOUND", message="Candidatura não encontrada.")


def _get_admission(session: Session, tenant_id: str, admission_id: str) -> AdmissionProcess:
    return _get(session, AdmissionProcess, tenant_id, admission_id, code="ADMISSION_PROCESS_NOT_FOUND", message="Processo de admissão não encontrado.")


def _get_employee(session: Session, tenant_id: str, employee_id: str) -> Employee:
    return _get(session, Employee, tenant_id, employee_id, code="EMPLOYEE_NOT_FOUND", message="Colaborador não encontrado.")


def _paginate(session: Session, model: type[T], tenant_id: str, *, conditions: list[Any] | None = None, cursor: str | None, limit: int, order_by: Any | None = None) -> dict[str, Any]:
    where = [model.tenant_id == tenant_id, model.deleted_at.is_(None), *(conditions or [])]
    if cursor:
        where.append(model.id > cursor)
    rows = session.scalars(select(model).where(*where).order_by(order_by or model.id).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [model_to_dict(row) for row in rows], "count": len(rows), "next_cursor": rows[-1].id if has_more and rows else None}


def _audit(
    session: Session,
    *,
    tenant_id: str,
    actor: Actor,
    action: str,
    resource_type: str,
    row: Any,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
    before: Any | None = None,
    after: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    audit_tenant(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=row.id,
        correlation_id=correlation_id,
        request_id=request_id,
        before=before,
        after=after,
        metadata=metadata,
        ip_address=ip_address,
        institution_id=getattr(row, "institution_id", None),
        unit_id=getattr(row, "unit_id", None),
    )


def _event(session: Session, *, tenant_id: str, row: Any, event_type: str, aggregate_type: str, payload: Any, correlation_id: str) -> None:
    emit_tenant_event(
        session,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=row.id,
        payload=payload,
        correlation_id=correlation_id,
        institution_id=getattr(row, "institution_id", None),
        unit_id=getattr(row, "unit_id", None),
    )


# Departamentos e cargos -------------------------------------------------------


def list_departments(session: Session, tenant_id: str, *, search: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(OrganizationalDepartment.code.ilike(term), OrganizationalDepartment.name.ilike(term)))
    if status:
        conditions.append(OrganizationalDepartment.status == status)
    return _paginate(session, OrganizationalDepartment, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_department(session: Session, tenant_id: str, data: DepartmentCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.department.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O departamento ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    if data.parent_id:
        _get_department(session, tenant_id, data.parent_id)
    if data.cost_center_id:
        _get(session, CostCenter, tenant_id, data.cost_center_id, code="COST_CENTER_NOT_FOUND", message="Centro de custo não encontrado.")
    row = OrganizationalDepartment(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        code=data.code.upper(),
        name=data.name,
        parent_id=data.parent_id,
        cost_center_id=data.cost_center_id,
        status="active",
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.department.created", resource_type="organizational_department", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="DepartmentCreated", aggregate_type="organizational_department", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def patch_department(session: Session, tenant_id: str, department_id: str, data: DepartmentPatch, *, expected_version: int | None, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_department(session, tenant_id, department_id)
    if expected_version is not None and row.version != expected_version:
        raise ConflictError("O departamento foi alterado por outro usuário.", code="OPTIMISTIC_CONCURRENCY_CONFLICT")
    before = model_to_dict(row)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("parent_id"):
        if changes["parent_id"] == row.id:
            raise ValidationError("Departamento não pode ser pai de si próprio.", code="DEPARTMENT_SELF_PARENT")
        _get_department(session, tenant_id, changes["parent_id"])
    if changes.get("cost_center_id"):
        _get(session, CostCenter, tenant_id, changes["cost_center_id"], code="COST_CENTER_NOT_FOUND", message="Centro de custo não encontrado.")
    if changes.get("manager_employee_id"):
        _get_employee(session, tenant_id, changes["manager_employee_id"])
    for key, value in changes.items():
        setattr(row, key, value)
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.department.updated", resource_type="organizational_department", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    session.commit()
    return after


def list_positions(session: Session, tenant_id: str, *, search: str | None, department_id: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(JobPosition.code.ilike(term), JobPosition.title.ilike(term), JobPosition.cbo_code.ilike(term)))
    if department_id:
        conditions.append(JobPosition.department_id == department_id)
    if status:
        conditions.append(JobPosition.status == status)
    return _paginate(session, JobPosition, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_position(session: Session, tenant_id: str, data: PositionCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.position.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O cargo ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    if data.department_id:
        _get_department(session, tenant_id, data.department_id)
    row = JobPosition(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        code=data.code.upper(),
        title=data.title,
        cbo_code=data.cbo_code,
        department_id=data.department_id,
        description=data.description,
        responsibilities_json=data.responsibilities,
        requirements_json=data.requirements,
        salary_floor=money(data.salary_floor) if data.salary_floor is not None else None,
        salary_ceiling=money(data.salary_ceiling) if data.salary_ceiling is not None else None,
        status="active",
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.position.created", resource_type="job_position", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="JobPositionCreated", aggregate_type="job_position", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def patch_position(session: Session, tenant_id: str, position_id: str, data: PositionPatch, *, expected_version: int | None, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_position(session, tenant_id, position_id)
    if expected_version is not None and row.version != expected_version:
        raise ConflictError("O cargo foi alterado por outro usuário.", code="OPTIMISTIC_CONCURRENCY_CONFLICT")
    before = model_to_dict(row)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("department_id"):
        _get_department(session, tenant_id, changes["department_id"])
    floor = changes.get("salary_floor", row.salary_floor)
    ceiling = changes.get("salary_ceiling", row.salary_ceiling)
    if floor is not None and ceiling is not None and Decimal(str(ceiling)) < Decimal(str(floor)):
        raise ValidationError("O teto salarial não pode ser menor que o piso.", code="INVALID_SALARY_RANGE")
    mapping = {"responsibilities": "responsibilities_json", "requirements": "requirements_json"}
    for key, value in changes.items():
        target = mapping.get(key, key)
        if key in {"salary_floor", "salary_ceiling"} and value is not None:
            value = money(value)
        setattr(row, target, value)
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.position.updated", resource_type="job_position", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    session.commit()
    return after


# Recrutamento e admissão ------------------------------------------------------


def list_job_openings(session: Session, tenant_id: str, *, status: str | None, position_id: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(JobOpening.status == status)
    if position_id:
        conditions.append(JobOpening.position_id == position_id)
    return _paginate(session, JobOpening, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def job_opening_detail(session: Session, tenant_id: str, opening_id: str) -> dict[str, Any]:
    row = _get_opening(session, tenant_id, opening_id)
    result = model_to_dict(row)
    result["applications"] = [model_to_dict(item) for item in session.scalars(select(RecruitmentApplication).where(RecruitmentApplication.tenant_id == tenant_id, RecruitmentApplication.job_opening_id == row.id, RecruitmentApplication.deleted_at.is_(None)).order_by(RecruitmentApplication.id)).all()]
    return result


def create_job_opening(session: Session, tenant_id: str, data: JobOpeningCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.job_opening.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A vaga ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    position = _get_position(session, tenant_id, data.position_id)
    department_id = data.department_id or position.department_id
    if department_id:
        _get_department(session, tenant_id, department_id)
    if data.hiring_manager_employee_id:
        _get_employee(session, tenant_id, data.hiring_manager_employee_id)
    row = JobOpening(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        opening_number=_number("VAG"),
        position_id=position.id,
        department_id=department_id,
        hiring_manager_employee_id=data.hiring_manager_employee_id,
        employment_type=data.employment_type,
        workplace_mode=data.workplace_mode,
        openings_count=data.openings_count,
        filled_count=0,
        target_start_date=data.target_start_date,
        status="draft",
        description=data.description,
        requirements_json=data.requirements,
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.job_opening.created", resource_type="job_opening", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="JobOpeningCreated", aggregate_type="job_opening", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def transition_job_opening(session: Session, tenant_id: str, opening_id: str, data: JobOpeningTransition, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_opening(session, tenant_id, opening_id)
    before = model_to_dict(row)
    transitions = {
        "publish": ({"draft", "paused"}, "published"),
        "pause": ({"published"}, "paused"),
        "reopen": ({"closed", "cancelled"}, "published"),
        "close": ({"published", "paused"}, "closed"),
        "cancel": ({"draft", "published", "paused"}, "cancelled"),
    }
    allowed, target = transitions[data.action]
    if row.status not in allowed:
        raise ConflictError("A vaga não permite esta transição.", code="INVALID_JOB_OPENING_STATE")
    if data.action in {"close", "cancel"} and not data.reason:
        raise ValidationError("Informe o motivo da operação.", code="JOB_OPENING_REASON_REQUIRED")
    row.status = target
    if data.action == "publish":
        row.published_at = row.published_at or utcnow()
    if data.action in {"close", "cancel"}:
        row.closed_at = utcnow()
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action=f"hr.job_opening.{data.action}", resource_type="job_opening", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after, metadata={"reason": data.reason})
    _event(session, tenant_id=tenant_id, row=row, event_type=f"JobOpening{data.action.title().replace('_', '')}", aggregate_type="job_opening", payload={"opening_id": row.id, "status": row.status, "reason": data.reason}, correlation_id=correlation_id)
    session.commit()
    return after


def list_candidates(session: Session, tenant_id: str, *, search: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(RecruitmentCandidate.status == status)
    if search:
        term = f"%{search.strip()}%"
        person_ids = select(Person.id).where(Person.tenant_id == tenant_id, Person.deleted_at.is_(None), or_(Person.full_name.ilike(term), Person.email.ilike(term), Person.cpf.ilike(term)))
        conditions.append(RecruitmentCandidate.person_id.in_(person_ids))
    result = _paginate(session, RecruitmentCandidate, tenant_id, conditions=conditions, cursor=cursor, limit=limit)
    for item in result["items"]:
        person = _get_person(session, tenant_id, item["person_id"])
        item["person"] = model_to_dict(person)
    return result


def create_candidate(session: Session, tenant_id: str, data: CandidateCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.candidate.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O candidato ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    _get_person(session, tenant_id, data.person_id)
    row = RecruitmentCandidate(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        person_id=data.person_id,
        source=data.source,
        linkedin_url=data.linkedin_url,
        portfolio_url=data.portfolio_url,
        resume_storage_key=data.resume_storage_key,
        resume_sha256=data.resume_sha256.lower() if data.resume_sha256 else None,
        status="active",
        notes=data.notes,
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.candidate.created", resource_type="recruitment_candidate", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="RecruitmentCandidateRegistered", aggregate_type="recruitment_candidate", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def list_applications(session: Session, tenant_id: str, *, opening_id: str | None, candidate_id: str | None, status: str | None, stage: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if opening_id:
        conditions.append(RecruitmentApplication.job_opening_id == opening_id)
    if candidate_id:
        conditions.append(RecruitmentApplication.candidate_id == candidate_id)
    if status:
        conditions.append(RecruitmentApplication.status == status)
    if stage:
        conditions.append(RecruitmentApplication.current_stage == stage)
    return _paginate(session, RecruitmentApplication, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def application_detail(session: Session, tenant_id: str, application_id: str) -> dict[str, Any]:
    row = _get_application(session, tenant_id, application_id)
    result = model_to_dict(row)
    result["history"] = [model_to_dict(item) for item in session.scalars(select(RecruitmentStageHistory).where(RecruitmentStageHistory.tenant_id == tenant_id, RecruitmentStageHistory.application_id == row.id, RecruitmentStageHistory.deleted_at.is_(None)).order_by(RecruitmentStageHistory.sequence)).all()]
    return result


def create_application(session: Session, tenant_id: str, data: ApplicationCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.application.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A candidatura ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    opening = _get_opening(session, tenant_id, data.job_opening_id)
    if opening.status != "published":
        raise ConflictError("A vaga não está aberta para candidaturas.", code="JOB_OPENING_NOT_PUBLISHED")
    candidate = _get_candidate(session, tenant_id, data.candidate_id)
    row = RecruitmentApplication(
        tenant_id=tenant_id,
        institution_id=data.institution_id or opening.institution_id,
        unit_id=data.unit_id or opening.unit_id,
        job_opening_id=opening.id,
        candidate_id=candidate.id,
        current_stage="applied",
        status="active",
        metadata_json=data.metadata,
    )
    session.add(row)
    session.flush()
    history = RecruitmentStageHistory(
        tenant_id=tenant_id,
        institution_id=row.institution_id,
        unit_id=row.unit_id,
        application_id=row.id,
        sequence=1,
        stage="applied",
        outcome="received",
        evaluator_user_id=actor.id,
        completed_at=utcnow(),
    )
    session.add(history)
    session.flush()
    result = application_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.application.created", resource_type="recruitment_application", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="RecruitmentApplicationCreated", aggregate_type="recruitment_application", payload={"application_id": row.id, "opening_id": opening.id, "candidate_id": candidate.id}, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def advance_application(session: Session, tenant_id: str, application_id: str, data: ApplicationStage, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_application(session, tenant_id, application_id)
    if row.status not in {"active", "offer"}:
        raise ConflictError("Candidatura encerrada não pode avançar.", code="APPLICATION_ALREADY_DECIDED")
    before = application_detail(session, tenant_id, row.id)
    sequence = int(session.scalar(select(func.coalesce(func.max(RecruitmentStageHistory.sequence), 0)).where(RecruitmentStageHistory.tenant_id == tenant_id, RecruitmentStageHistory.application_id == row.id)) or 0) + 1
    terminal = data.stage in {"approved", "rejected", "withdrawn"}
    row.current_stage = data.stage
    row.score = data.score if data.score is not None else row.score
    if data.stage == "approved":
        row.status = "approved"
        row.decided_at = utcnow()
    elif data.stage == "rejected":
        row.status = "rejected"
        row.rejection_reason = data.rejection_reason or data.notes
        row.decided_at = utcnow()
    elif data.stage == "withdrawn":
        row.status = "withdrawn"
        row.decided_at = utcnow()
    elif data.stage == "offer":
        row.status = "offer"
    else:
        row.status = "active"
    row.version += 1
    history = RecruitmentStageHistory(
        tenant_id=tenant_id,
        institution_id=row.institution_id,
        unit_id=row.unit_id,
        application_id=row.id,
        sequence=sequence,
        stage=data.stage,
        outcome=data.outcome,
        score=data.score,
        evaluator_user_id=actor.id,
        scheduled_at=data.scheduled_at,
        completed_at=utcnow() if data.scheduled_at is None or data.scheduled_at <= utcnow() else None,
        notes=data.notes or data.rejection_reason,
    )
    session.add(history)
    session.flush()
    after = application_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.application.stage_changed", resource_type="recruitment_application", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    event_type = "RecruitmentApplicationDecided" if terminal else "RecruitmentApplicationAdvanced"
    _event(session, tenant_id=tenant_id, row=row, event_type=event_type, aggregate_type="recruitment_application", payload={"application_id": row.id, "stage": row.current_stage, "status": row.status}, correlation_id=correlation_id)
    session.commit()
    return after


def list_admissions(session: Session, tenant_id: str, *, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions = [AdmissionProcess.status == status] if status else []
    return _paginate(session, AdmissionProcess, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def admission_detail(session: Session, tenant_id: str, admission_id: str) -> dict[str, Any]:
    row = _get_admission(session, tenant_id, admission_id)
    result = model_to_dict(row)
    employee = session.scalar(select(Employee).where(Employee.tenant_id == tenant_id, Employee.admission_process_id == row.id, Employee.deleted_at.is_(None)))
    result["employee"] = employee_detail(session, tenant_id, employee.id) if employee else None
    return result


def create_admission(session: Session, tenant_id: str, data: AdmissionCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.admission.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A admissão ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    application = _get_application(session, tenant_id, data.application_id)
    if application.status != "approved":
        raise ConflictError("A candidatura precisa estar aprovada.", code="APPLICATION_NOT_APPROVED")
    _get_position(session, tenant_id, data.proposed_position_id)
    candidate = _get_candidate(session, tenant_id, application.candidate_id)
    row = AdmissionProcess(
        tenant_id=tenant_id,
        institution_id=data.institution_id or application.institution_id,
        unit_id=data.unit_id or application.unit_id,
        application_id=application.id,
        candidate_id=candidate.id,
        proposed_position_id=data.proposed_position_id,
        proposed_salary=money(data.proposed_salary),
        proposed_start_date=data.proposed_start_date,
        employment_type=data.employment_type,
        checklist_json=data.checklist,
        status="draft",
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.admission.created", resource_type="admission_process", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="AdmissionProcessCreated", aggregate_type="admission_process", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def transition_admission(session: Session, tenant_id: str, admission_id: str, data: AdmissionTransition, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_admission(session, tenant_id, admission_id)
    before = model_to_dict(row)
    if data.action == "submit":
        if row.status not in {"draft", "changes_requested"}:
            raise ConflictError("Processo não pode ser enviado no estado atual.", code="INVALID_ADMISSION_STATE")
        row.status = "submitted"
    elif data.action == "approve":
        if row.status != "submitted":
            raise ConflictError("Somente processo enviado pode ser aprovado.", code="INVALID_ADMISSION_STATE")
        required_missing = [item for item in row.checklist_json if item.get("required") and not item.get("completed")]
        if required_missing:
            raise ValidationError("Existem itens obrigatórios pendentes na admissão.", code="ADMISSION_CHECKLIST_INCOMPLETE", errors=[{"field": "checklist", "code": "REQUIRED_ITEM_PENDING", "message": str(item.get("title") or item.get("code"))} for item in required_missing])
        row.status = "approved"
        row.approved_at = utcnow()
    elif data.action == "request_changes":
        if row.status != "submitted":
            raise ConflictError("Somente processo enviado pode ser devolvido.", code="INVALID_ADMISSION_STATE")
        if not data.reason:
            raise ValidationError("Informe a alteração necessária.", code="ADMISSION_REASON_REQUIRED")
        row.status = "changes_requested"
    elif data.action == "cancel":
        if row.status in {"admitted", "cancelled"}:
            raise ConflictError("Processo não pode ser cancelado no estado atual.", code="INVALID_ADMISSION_STATE")
        if not data.reason:
            raise ValidationError("Informe o motivo do cancelamento.", code="ADMISSION_REASON_REQUIRED")
        row.status = "cancelled"
        row.cancellation_reason = data.reason
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action=f"hr.admission.{data.action}", resource_type="admission_process", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after, metadata={"reason": data.reason})
    _event(session, tenant_id=tenant_id, row=row, event_type=f"AdmissionProcess{data.action.title().replace('_', '')}", aggregate_type="admission_process", payload={"admission_id": row.id, "status": row.status}, correlation_id=correlation_id)
    session.commit()
    return after


def hire_admission(session: Session, tenant_id: str, admission_id: str, data: AdmissionHire, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope=f"hr.admission.{admission_id}.hire", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A contratação ainda está sendo processada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    admission = _get_admission(session, tenant_id, admission_id)
    if admission.status != "approved":
        raise ConflictError("Somente admissão aprovada pode gerar contratação.", code="ADMISSION_NOT_APPROVED")
    application = _get_application(session, tenant_id, admission.application_id)
    candidate = _get_candidate(session, tenant_id, admission.candidate_id)
    _get_person(session, tenant_id, candidate.person_id)
    position = _get_position(session, tenant_id, admission.proposed_position_id)
    department_id = data.department_id or position.department_id
    if department_id:
        _get_department(session, tenant_id, department_id)
    if data.cost_center_id:
        _get(session, CostCenter, tenant_id, data.cost_center_id, code="COST_CENTER_NOT_FOUND", message="Centro de custo não encontrado.")
    if data.manager_employee_id:
        _get_employee(session, tenant_id, data.manager_employee_id)
    if data.work_schedule_id:
        _get(session, WorkSchedule, tenant_id, data.work_schedule_id, code="WORK_SCHEDULE_NOT_FOUND", message="Jornada não encontrada.")
    employee = Employee(
        tenant_id=tenant_id,
        institution_id=admission.institution_id,
        unit_id=admission.unit_id,
        person_id=candidate.person_id,
        registration_number=data.registration_number.upper(),
        admission_process_id=admission.id,
        employment_status="active",
        hired_at=admission.proposed_start_date,
        corporate_email=data.corporate_email.lower() if data.corporate_email else None,
        metadata_json={"source": "recruitment"},
    )
    session.add(employee)
    session.flush()
    contract = EmploymentContract(
        tenant_id=tenant_id,
        institution_id=admission.institution_id,
        unit_id=admission.unit_id,
        employee_id=employee.id,
        contract_number=data.contract_number.upper(),
        employment_type=admission.employment_type,
        start_date=admission.proposed_start_date,
        probation_end_date=data.probation_end_date,
        weekly_hours=data.weekly_hours,
        salary_amount=money(admission.proposed_salary),
        salary_unit=data.salary_unit,
        payment_frequency=data.payment_frequency,
        position_id=position.id,
        department_id=department_id,
        work_schedule_id=data.work_schedule_id,
        union_id=data.union_id,
        terms_json=data.terms,
        status="active",
    )
    session.add(contract)
    session.flush()
    assignment = EmployeeAssignment(
        tenant_id=tenant_id,
        institution_id=admission.institution_id,
        unit_id=admission.unit_id,
        employee_id=employee.id,
        position_id=position.id,
        department_id=department_id,
        cost_center_id=data.cost_center_id,
        manager_employee_id=data.manager_employee_id,
        valid_from=admission.proposed_start_date,
        allocation_percentage=Decimal("100"),
        primary=True,
        reason="Admissão",
        status="active",
    )
    salary = SalaryHistory(
        tenant_id=tenant_id,
        institution_id=admission.institution_id,
        unit_id=admission.unit_id,
        employee_id=employee.id,
        employment_contract_id=contract.id,
        effective_from=admission.proposed_start_date,
        salary_amount=money(admission.proposed_salary),
        salary_unit=data.salary_unit,
        change_type="admission",
        reason="Salário inicial da admissão",
        approved_by_user_id=actor.id,
    )
    session.add_all([assignment, salary])
    default_tasks = data.onboarding_tasks or [
        {"task_code": "DOCUMENTS", "title": "Validar documentos admissionais", "required": True},
        {"task_code": "ACCESS", "title": "Provisionar acessos institucionais", "required": True},
        {"task_code": "INTEGRATION", "title": "Realizar integração institucional", "required": True},
    ]
    for item in default_tasks:
        session.add(
            OnboardingTask(
                tenant_id=tenant_id,
                institution_id=admission.institution_id,
                unit_id=admission.unit_id,
                employee_id=employee.id,
                task_code=str(item.get("task_code") or item.get("code") or _number("TASK")).upper(),
                title=str(item.get("title") or "Atividade de onboarding"),
                assigned_to_user_id=item.get("assigned_to_user_id"),
                due_date=date.fromisoformat(item["due_date"]) if isinstance(item.get("due_date"), str) else item.get("due_date"),
                required=bool(item.get("required", True)),
                status="pending",
            )
        )
    admission.status = "admitted"
    admission.admitted_at = utcnow()
    admission.version += 1
    application.status = "hired"
    application.version += 1
    opening = _get_opening(session, tenant_id, application.job_opening_id)
    opening.filled_count += 1
    if opening.filled_count >= opening.openings_count:
        opening.status = "closed"
        opening.closed_at = utcnow()
    opening.version += 1
    session.flush()
    result = employee_detail(session, tenant_id, employee.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.employee.hired", resource_type="employee", row=employee, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result, metadata={"admission_process_id": admission.id})
    _event(session, tenant_id=tenant_id, row=employee, event_type="EmployeeEmploymentActivated", aggregate_type="employee", payload={"employee_id": employee.id, "person_id": employee.person_id, "contract_id": contract.id, "start_date": contract.start_date.isoformat()}, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


# Colaborador, onboarding e desenvolvimento ----------------------------------


def list_employees(session: Session, tenant_id: str, *, search: str | None, status: str | None, department_id: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(Employee.employment_status == status)
    if search:
        term = f"%{search.strip()}%"
        person_ids = select(Person.id).where(Person.tenant_id == tenant_id, Person.deleted_at.is_(None), or_(Person.full_name.ilike(term), Person.cpf.ilike(term), Person.email.ilike(term)))
        conditions.append(or_(Employee.registration_number.ilike(term), Employee.corporate_email.ilike(term), Employee.person_id.in_(person_ids)))
    if department_id:
        employee_ids = select(EmployeeAssignment.employee_id).where(EmployeeAssignment.tenant_id == tenant_id, EmployeeAssignment.department_id == department_id, EmployeeAssignment.status == "active", EmployeeAssignment.deleted_at.is_(None))
        conditions.append(Employee.id.in_(employee_ids))
    result = _paginate(session, Employee, tenant_id, conditions=conditions, cursor=cursor, limit=limit)
    for item in result["items"]:
        person = _get_person(session, tenant_id, item["person_id"])
        item["person"] = model_to_dict(person)
    return result


def employee_detail(session: Session, tenant_id: str, employee_id: str) -> dict[str, Any]:
    row = _get_employee(session, tenant_id, employee_id)
    result = model_to_dict(row)
    result["person"] = model_to_dict(_get_person(session, tenant_id, row.person_id))
    result["contracts"] = [model_to_dict(item) for item in session.scalars(select(EmploymentContract).where(EmploymentContract.tenant_id == tenant_id, EmploymentContract.employee_id == row.id, EmploymentContract.deleted_at.is_(None)).order_by(EmploymentContract.start_date.desc())).all()]
    result["assignments"] = [model_to_dict(item) for item in session.scalars(select(EmployeeAssignment).where(EmployeeAssignment.tenant_id == tenant_id, EmployeeAssignment.employee_id == row.id, EmployeeAssignment.deleted_at.is_(None)).order_by(EmployeeAssignment.valid_from.desc())).all()]
    result["salary_history"] = [model_to_dict(item) for item in session.scalars(select(SalaryHistory).where(SalaryHistory.tenant_id == tenant_id, SalaryHistory.employee_id == row.id, SalaryHistory.deleted_at.is_(None)).order_by(SalaryHistory.effective_from.desc())).all()]
    result["onboarding"] = [model_to_dict(item) for item in session.scalars(select(OnboardingTask).where(OnboardingTask.tenant_id == tenant_id, OnboardingTask.employee_id == row.id, OnboardingTask.deleted_at.is_(None)).order_by(OnboardingTask.id)).all()]
    return result


def patch_employee(session: Session, tenant_id: str, employee_id: str, data: EmployeePatch, *, expected_version: int | None, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_employee(session, tenant_id, employee_id)
    if expected_version is not None and row.version != expected_version:
        raise ConflictError("O colaborador foi alterado por outro usuário.", code="OPTIMISTIC_CONCURRENCY_CONFLICT")
    before = employee_detail(session, tenant_id, row.id)
    changes = data.model_dump(exclude_unset=True)
    if "corporate_email" in changes and changes["corporate_email"]:
        changes["corporate_email"] = changes["corporate_email"].lower()
    if "metadata" in changes:
        changes["metadata_json"] = changes.pop("metadata")
    for key, value in changes.items():
        setattr(row, key, value)
    row.version += 1
    session.flush()
    after = employee_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.employee.updated", resource_type="employee", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    session.commit()
    return after


def create_onboarding_task(session: Session, tenant_id: str, employee_id: str, data: OnboardingTaskCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope=f"hr.employee.{employee_id}.onboarding.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A tarefa ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, employee_id)
    row = OnboardingTask(tenant_id=tenant_id, institution_id=employee.institution_id, unit_id=employee.unit_id, employee_id=employee.id, task_code=data.task_code.upper(), title=data.title, assigned_to_user_id=data.assigned_to_user_id, due_date=data.due_date, required=data.required, status="pending")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.onboarding_task.created", resource_type="onboarding_task", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def complete_onboarding_task(session: Session, tenant_id: str, task_id: str, data: OnboardingTaskComplete, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, OnboardingTask, tenant_id, task_id, code="ONBOARDING_TASK_NOT_FOUND", message="Tarefa de onboarding não encontrada.")
    if row.status == "completed":
        return model_to_dict(row)
    if row.status not in {"pending", "in_progress"}:
        raise ConflictError("Tarefa não pode ser concluída no estado atual.", code="INVALID_ONBOARDING_TASK_STATE")
    before = model_to_dict(row)
    row.status = "completed"
    row.completed_at = utcnow()
    row.evidence_json = data.evidence
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.onboarding_task.completed", resource_type="onboarding_task", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    pending_required = session.scalar(select(func.count(OnboardingTask.id)).where(OnboardingTask.tenant_id == tenant_id, OnboardingTask.employee_id == row.employee_id, OnboardingTask.required.is_(True), OnboardingTask.status != "completed", OnboardingTask.deleted_at.is_(None))) or 0
    if pending_required == 0:
        employee = _get_employee(session, tenant_id, row.employee_id)
        _event(session, tenant_id=tenant_id, row=employee, event_type="EmployeeOnboardingCompleted", aggregate_type="employee", payload={"employee_id": employee.id}, correlation_id=correlation_id)
    session.commit()
    return after


def list_training_courses(session: Session, tenant_id: str, *, status: str | None, search: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(TrainingCourse.status == status)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(TrainingCourse.code.ilike(term), TrainingCourse.name.ilike(term)))
    return _paginate(session, TrainingCourse, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_training_course(session: Session, tenant_id: str, data: TrainingCourseCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.training_course.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O treinamento ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    row = TrainingCourse(tenant_id=tenant_id, institution_id=data.institution_id, unit_id=data.unit_id, code=data.code.upper(), name=data.name, description=data.description, provider_name=data.provider_name, workload_hours=data.workload_hours, validity_months=data.validity_months, mandatory=data.mandatory, status="active")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.training_course.created", resource_type="training_course", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def enroll_training(session: Session, tenant_id: str, course_id: str, data: TrainingEnroll, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope=f"hr.training.{course_id}.enroll", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A inscrição ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    course = _get(session, TrainingCourse, tenant_id, course_id, code="TRAINING_COURSE_NOT_FOUND", message="Treinamento não encontrado.")
    if course.status != "active":
        raise ConflictError("Treinamento inativo.", code="TRAINING_COURSE_INACTIVE")
    employee = _get_employee(session, tenant_id, data.employee_id)
    row = TrainingEnrollment(tenant_id=tenant_id, institution_id=employee.institution_id, unit_id=employee.unit_id, course_id=course.id, employee_id=employee.id, status="enrolled")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.training.enrolled", resource_type="training_enrollment", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def complete_training(session: Session, tenant_id: str, enrollment_id: str, data: TrainingComplete, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, TrainingEnrollment, tenant_id, enrollment_id, code="TRAINING_ENROLLMENT_NOT_FOUND", message="Inscrição de treinamento não encontrada.")
    if row.status not in {"enrolled", "in_progress"}:
        raise ConflictError("Inscrição não pode ser concluída.", code="INVALID_TRAINING_STATE")
    before = model_to_dict(row)
    row.status = "completed"
    row.completed_at = utcnow()
    row.score = data.score
    row.certificate_storage_key = data.certificate_storage_key
    row.certificate_sha256 = data.certificate_sha256.lower() if data.certificate_sha256 else None
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.training.completed", resource_type="training_enrollment", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    _event(session, tenant_id=tenant_id, row=row, event_type="EmployeeTrainingCompleted", aggregate_type="training_enrollment", payload=after, correlation_id=correlation_id)
    session.commit()
    return after


def list_competencies(session: Session, tenant_id: str, *, status: str | None, search: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(Competency.status == status)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(Competency.code.ilike(term), Competency.name.ilike(term)))
    return _paginate(session, Competency, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_competency(session: Session, tenant_id: str, data: CompetencyCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.competency.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A competência ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    row = Competency(tenant_id=tenant_id, institution_id=data.institution_id, unit_id=data.unit_id, code=data.code.upper(), name=data.name, description=data.description, category=data.category, scale_json=data.scale, status="active")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.competency.created", resource_type="competency", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def upsert_employee_competency(session: Session, tenant_id: str, competency_id: str, data: EmployeeCompetencyUpsert, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    competency = _get(session, Competency, tenant_id, competency_id, code="COMPETENCY_NOT_FOUND", message="Competência não encontrada.")
    employee = _get_employee(session, tenant_id, data.employee_id)
    row = session.scalar(select(EmployeeCompetency).where(EmployeeCompetency.tenant_id == tenant_id, EmployeeCompetency.employee_id == employee.id, EmployeeCompetency.competency_id == competency.id, EmployeeCompetency.deleted_at.is_(None)))
    before = model_to_dict(row) if row else None
    if row is None:
        row = EmployeeCompetency(tenant_id=tenant_id, institution_id=employee.institution_id, unit_id=employee.unit_id, employee_id=employee.id, competency_id=competency.id, current_level=data.current_level, target_level=data.target_level, evaluated_at=utcnow(), evaluator_user_id=actor.id, evidence_json=data.evidence)
        session.add(row)
    else:
        row.current_level = data.current_level
        row.target_level = data.target_level
        row.evaluated_at = utcnow()
        row.evaluator_user_id = actor.id
        row.evidence_json = data.evidence
        row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.employee_competency.assessed", resource_type="employee_competency", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    session.commit()
    return after


def list_performance_reviews(session: Session, tenant_id: str, *, employee_id: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if employee_id:
        conditions.append(PerformanceReview.employee_id == employee_id)
    if status:
        conditions.append(PerformanceReview.status == status)
    return _paginate(session, PerformanceReview, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_performance_review(session: Session, tenant_id: str, data: PerformanceReviewCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.performance_review.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A avaliação ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, data.employee_id)
    if data.reviewer_employee_id:
        _get_employee(session, tenant_id, data.reviewer_employee_id)
    row = PerformanceReview(tenant_id=tenant_id, institution_id=data.institution_id or employee.institution_id, unit_id=data.unit_id or employee.unit_id, employee_id=employee.id, cycle_code=data.cycle_code, reviewer_employee_id=data.reviewer_employee_id, period_start=data.period_start, period_end=data.period_end, goals_json=data.goals, competencies_json=data.competencies, status="draft")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.performance_review.created", resource_type="performance_review", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def complete_performance_review(session: Session, tenant_id: str, review_id: str, data: PerformanceReviewComplete, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, PerformanceReview, tenant_id, review_id, code="PERFORMANCE_REVIEW_NOT_FOUND", message="Avaliação não encontrada.")
    if row.status not in {"draft", "in_progress", "submitted"}:
        raise ConflictError("Avaliação não pode ser concluída.", code="INVALID_PERFORMANCE_REVIEW_STATE")
    before = model_to_dict(row)
    row.overall_score = data.overall_score
    row.feedback = data.feedback
    if data.competencies is not None:
        row.competencies_json = data.competencies
    row.status = "completed"
    row.completed_at = utcnow()
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.performance_review.completed", resource_type="performance_review", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    _event(session, tenant_id=tenant_id, row=row, event_type="PerformanceReviewCompleted", aggregate_type="performance_review", payload=after, correlation_id=correlation_id)
    session.commit()
    return after


def list_development_plans(session: Session, tenant_id: str, *, employee_id: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if employee_id:
        conditions.append(DevelopmentPlan.employee_id == employee_id)
    if status:
        conditions.append(DevelopmentPlan.status == status)
    return _paginate(session, DevelopmentPlan, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_development_plan(session: Session, tenant_id: str, data: DevelopmentPlanCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.development_plan.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O plano ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, data.employee_id)
    if data.performance_review_id:
        review = _get(session, PerformanceReview, tenant_id, data.performance_review_id, code="PERFORMANCE_REVIEW_NOT_FOUND", message="Avaliação não encontrada.")
        if review.employee_id != employee.id:
            raise ValidationError("A avaliação não pertence ao colaborador.", code="REVIEW_EMPLOYEE_MISMATCH")
    row = DevelopmentPlan(tenant_id=tenant_id, institution_id=data.institution_id or employee.institution_id, unit_id=data.unit_id or employee.unit_id, employee_id=employee.id, performance_review_id=data.performance_review_id, cycle_code=data.cycle_code, objectives_json=data.objectives, actions_json=data.actions, started_on=data.started_on, due_on=data.due_on, progress_percentage=Decimal("0"), status="active")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.development_plan.created", resource_type="development_plan", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def update_development_plan_progress(session: Session, tenant_id: str, plan_id: str, data: DevelopmentPlanProgress, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, DevelopmentPlan, tenant_id, plan_id, code="DEVELOPMENT_PLAN_NOT_FOUND", message="Plano de desenvolvimento não encontrado.")
    if row.status in {"completed", "cancelled"}:
        raise ConflictError("Plano encerrado não pode ser alterado.", code="DEVELOPMENT_PLAN_CLOSED")
    before = model_to_dict(row)
    row.progress_percentage = data.progress_percentage
    row.status = data.status or ("completed" if data.progress_percentage == 100 else row.status)
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.development_plan.progress_updated", resource_type="development_plan", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    session.commit()
    return after


# Benefícios, férias, afastamentos e ocorrências ------------------------------


def list_benefit_plans(session: Session, tenant_id: str, *, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    return _paginate(session, BenefitPlan, tenant_id, conditions=[BenefitPlan.status == status] if status else [], cursor=cursor, limit=limit)


def create_benefit_plan(session: Session, tenant_id: str, data: BenefitPlanCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.benefit_plan.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O benefício ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    row = BenefitPlan(tenant_id=tenant_id, institution_id=data.institution_id, unit_id=data.unit_id, code=data.code.upper(), name=data.name, benefit_type=data.benefit_type, provider_name=data.provider_name, employer_amount=money(data.employer_amount), employee_amount=money(data.employee_amount), payroll_rubric_code=data.payroll_rubric_code, settings_json=data.settings, status="active")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.benefit_plan.created", resource_type="benefit_plan", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def create_employee_benefit(session: Session, tenant_id: str, data: EmployeeBenefitCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.employee_benefit.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O vínculo do benefício ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, data.employee_id)
    plan = _get(session, BenefitPlan, tenant_id, data.benefit_plan_id, code="BENEFIT_PLAN_NOT_FOUND", message="Plano de benefício não encontrado.")
    if plan.status != "active":
        raise ConflictError("Plano de benefício inativo.", code="BENEFIT_PLAN_INACTIVE")
    if data.valid_until and data.valid_until < data.valid_from:
        raise ValidationError("Vigência do benefício inválida.", code="INVALID_BENEFIT_VALIDITY")
    row = EmployeeBenefit(tenant_id=tenant_id, institution_id=employee.institution_id, unit_id=employee.unit_id, employee_id=employee.id, benefit_plan_id=plan.id, valid_from=data.valid_from, valid_until=data.valid_until, employer_amount=money(data.employer_amount if data.employer_amount is not None else plan.employer_amount), employee_amount=money(data.employee_amount if data.employee_amount is not None else plan.employee_amount), dependents_json=data.dependents, status="active")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.employee_benefit.enrolled", resource_type="employee_benefit", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="EmployeeBenefitActivated", aggregate_type="employee_benefit", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def list_vacations(session: Session, tenant_id: str, *, employee_id: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if employee_id:
        conditions.append(VacationPeriod.employee_id == employee_id)
    if status:
        conditions.append(VacationPeriod.status == status)
    return _paginate(session, VacationPeriod, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_vacation(session: Session, tenant_id: str, data: VacationCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.vacation.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O período de férias ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, data.employee_id)
    scheduled_days = ((data.scheduled_end - data.scheduled_start).days + 1) if data.scheduled_start and data.scheduled_end else 0
    if scheduled_days + data.sold_days > data.entitlement_days:
        raise ValidationError("Dias programados e vendidos excedem o direito de férias.", code="VACATION_DAYS_EXCEEDED")
    row = VacationPeriod(tenant_id=tenant_id, institution_id=data.institution_id or employee.institution_id, unit_id=data.unit_id or employee.unit_id, employee_id=employee.id, accrual_start=data.accrual_start, accrual_end=data.accrual_end, entitlement_days=data.entitlement_days, scheduled_start=data.scheduled_start, scheduled_end=data.scheduled_end, sold_days=data.sold_days, taken_days=0, status="scheduled" if data.scheduled_start else "accruing")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.vacation.created", resource_type="vacation_period", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def transition_vacation(session: Session, tenant_id: str, vacation_id: str, data: VacationTransition, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, VacationPeriod, tenant_id, vacation_id, code="VACATION_PERIOD_NOT_FOUND", message="Período de férias não encontrado.")
    before = model_to_dict(row)
    if data.action == "schedule":
        if row.status not in {"accruing", "available", "cancelled"}:
            raise ConflictError("Férias não podem ser programadas no estado atual.", code="INVALID_VACATION_STATE")
        if not data.scheduled_start or not data.scheduled_end or data.scheduled_end < data.scheduled_start:
            raise ValidationError("Informe um período de férias válido.", code="INVALID_VACATION_SCHEDULE")
        days = (data.scheduled_end - data.scheduled_start).days + 1
        if days + row.sold_days > row.entitlement_days:
            raise ValidationError("Período programado excede o saldo de férias.", code="VACATION_DAYS_EXCEEDED")
        row.scheduled_start = data.scheduled_start
        row.scheduled_end = data.scheduled_end
        row.status = "scheduled"
    elif data.action == "approve":
        if row.status != "scheduled":
            raise ConflictError("Somente férias programadas podem ser aprovadas.", code="INVALID_VACATION_STATE")
        row.status = "approved"
        row.approved_by_user_id = actor.id
        row.approved_at = utcnow()
    elif data.action == "start":
        if row.status != "approved":
            raise ConflictError("Somente férias aprovadas podem ser iniciadas.", code="INVALID_VACATION_STATE")
        row.status = "in_progress"
        employee = _get_employee(session, tenant_id, row.employee_id)
        employee.employment_status = "vacation"
        employee.version += 1
    elif data.action == "complete":
        if row.status != "in_progress":
            raise ConflictError("Somente férias em andamento podem ser concluídas.", code="INVALID_VACATION_STATE")
        row.status = "completed"
        if row.scheduled_start and row.scheduled_end:
            row.taken_days = (row.scheduled_end - row.scheduled_start).days + 1
        employee = _get_employee(session, tenant_id, row.employee_id)
        employee.employment_status = "active"
        employee.version += 1
    elif data.action == "cancel":
        if row.status in {"completed", "in_progress"}:
            raise ConflictError("Férias iniciadas ou concluídas não podem ser canceladas.", code="INVALID_VACATION_STATE")
        if not data.reason:
            raise ValidationError("Informe o motivo do cancelamento.", code="VACATION_REASON_REQUIRED")
        row.status = "cancelled"
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action=f"hr.vacation.{data.action}", resource_type="vacation_period", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after, metadata={"reason": data.reason})
    _event(session, tenant_id=tenant_id, row=row, event_type=f"EmployeeVacation{data.action.title()}", aggregate_type="vacation_period", payload={"vacation_id": row.id, "employee_id": row.employee_id, "status": row.status}, correlation_id=correlation_id)
    session.commit()
    return after


def list_leaves(session: Session, tenant_id: str, *, employee_id: str | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if employee_id:
        conditions.append(EmployeeLeave.employee_id == employee_id)
    if status:
        conditions.append(EmployeeLeave.status == status)
    return _paginate(session, EmployeeLeave, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_leave(session: Session, tenant_id: str, data: LeaveCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.leave.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("O afastamento ainda está sendo criado.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, data.employee_id)
    if data.end_date and data.end_date < data.start_date:
        raise ValidationError("Período do afastamento inválido.", code="INVALID_LEAVE_PERIOD")
    overlap = session.scalar(select(EmployeeLeave.id).where(EmployeeLeave.tenant_id == tenant_id, EmployeeLeave.employee_id == employee.id, EmployeeLeave.status.in_(["submitted", "approved", "active"]), EmployeeLeave.start_date <= (data.end_date or date.max), or_(EmployeeLeave.end_date.is_(None), EmployeeLeave.end_date >= data.start_date), EmployeeLeave.deleted_at.is_(None)))
    if overlap:
        raise ConflictError("Já existe afastamento sobreposto para o colaborador.", code="LEAVE_PERIOD_OVERLAP")
    row = EmployeeLeave(tenant_id=tenant_id, institution_id=data.institution_id or employee.institution_id, unit_id=data.unit_id or employee.unit_id, employee_id=employee.id, leave_type=data.leave_type, start_date=data.start_date, end_date=data.end_date, paid=data.paid, affects_payroll=data.affects_payroll, reason=data.reason, document_id=data.document_id, status="submitted")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.leave.created", resource_type="employee_leave", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def transition_leave(session: Session, tenant_id: str, leave_id: str, data: LeaveTransition, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, EmployeeLeave, tenant_id, leave_id, code="EMPLOYEE_LEAVE_NOT_FOUND", message="Afastamento não encontrado.")
    before = model_to_dict(row)
    if data.action == "approve":
        if row.status != "submitted":
            raise ConflictError("Somente afastamento enviado pode ser aprovado.", code="INVALID_LEAVE_STATE")
        row.status = "approved"
        row.approved_by_user_id = actor.id
        row.approved_at = utcnow()
        employee = _get_employee(session, tenant_id, row.employee_id)
        if row.start_date <= date.today() and (row.end_date is None or row.end_date >= date.today()):
            employee.employment_status = "on_leave"
            employee.version += 1
            row.status = "active"
    elif data.action == "reject":
        if row.status != "submitted":
            raise ConflictError("Somente afastamento enviado pode ser rejeitado.", code="INVALID_LEAVE_STATE")
        if not data.reason:
            raise ValidationError("Informe o motivo da rejeição.", code="LEAVE_REASON_REQUIRED")
        row.status = "rejected"
    elif data.action == "cancel":
        if row.status in {"completed", "cancelled", "rejected"}:
            raise ConflictError("Afastamento não pode ser cancelado.", code="INVALID_LEAVE_STATE")
        if not data.reason:
            raise ValidationError("Informe o motivo do cancelamento.", code="LEAVE_REASON_REQUIRED")
        row.status = "cancelled"
    elif data.action == "complete":
        if row.status not in {"approved", "active"}:
            raise ConflictError("Afastamento não pode ser concluído.", code="INVALID_LEAVE_STATE")
        row.status = "completed"
        employee = _get_employee(session, tenant_id, row.employee_id)
        employee.employment_status = "active"
        employee.version += 1
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action=f"hr.leave.{data.action}", resource_type="employee_leave", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after, metadata={"reason": data.reason})
    _event(session, tenant_id=tenant_id, row=row, event_type=f"EmployeeLeave{data.action.title()}", aggregate_type="employee_leave", payload={"leave_id": row.id, "employee_id": row.employee_id, "status": row.status}, correlation_id=correlation_id)
    session.commit()
    return after


def list_occurrences(session: Session, tenant_id: str, *, employee_id: str | None, status: str | None, severity: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions: list[Any] = []
    if employee_id:
        conditions.append(EmployeeOccurrence.employee_id == employee_id)
    if status:
        conditions.append(EmployeeOccurrence.status == status)
    if severity:
        conditions.append(EmployeeOccurrence.severity == severity)
    return _paginate(session, EmployeeOccurrence, tenant_id, conditions=conditions, cursor=cursor, limit=limit)


def create_occurrence(session: Session, tenant_id: str, data: OccurrenceCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, reservation = reserve_tenant(session, tenant_id=tenant_id, scope="hr.occurrence.create", key=idempotency_key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError("A ocorrência ainda está sendo criada.", code="IDEMPOTENCY_IN_PROGRESS")
        return reservation.response_json
    employee = _get_employee(session, tenant_id, data.employee_id)
    row = EmployeeOccurrence(tenant_id=tenant_id, institution_id=data.institution_id or employee.institution_id, unit_id=data.unit_id or employee.unit_id, employee_id=employee.id, occurrence_type=data.occurrence_type, occurred_at=data.occurred_at, severity=data.severity, description=data.description, confidential=data.confidential, status="open")
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.occurrence.created", resource_type="employee_occurrence", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result, metadata={"confidential": row.confidential})
    _event(session, tenant_id=tenant_id, row=row, event_type="EmployeeOccurrenceRegistered", aggregate_type="employee_occurrence", payload={"occurrence_id": row.id, "employee_id": row.employee_id, "type": row.occurrence_type, "severity": row.severity}, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def resolve_occurrence(session: Session, tenant_id: str, occurrence_id: str, data: OccurrenceResolve, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get(session, EmployeeOccurrence, tenant_id, occurrence_id, code="EMPLOYEE_OCCURRENCE_NOT_FOUND", message="Ocorrência não encontrada.")
    if row.status != "open":
        raise ConflictError("Ocorrência já encerrada.", code="OCCURRENCE_ALREADY_CLOSED")
    before = model_to_dict(row)
    row.resolution = data.resolution
    row.status = "resolved"
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="hr.occurrence.resolved", resource_type="employee_occurrence", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=after)
    session.commit()
    return after


def hr_dashboard(session: Session, tenant_id: str) -> dict[str, Any]:
    def count(model: Any, *conditions: Any) -> int:
        return int(session.scalar(select(func.count(model.id)).where(model.tenant_id == tenant_id, model.deleted_at.is_(None), *conditions)) or 0)

    return {
        "employees": {
            "total": count(Employee),
            "active": count(Employee, Employee.employment_status == "active"),
            "on_leave": count(Employee, Employee.employment_status == "on_leave"),
            "vacation": count(Employee, Employee.employment_status == "vacation"),
            "terminated": count(Employee, Employee.employment_status == "terminated"),
        },
        "recruitment": {
            "open_positions": count(JobOpening, JobOpening.status == "published"),
            "active_applications": count(RecruitmentApplication, RecruitmentApplication.status.in_(["active", "offer"])),
            "admissions_pending": count(AdmissionProcess, AdmissionProcess.status.in_(["draft", "submitted", "changes_requested", "approved"])),
        },
        "people_development": {
            "pending_onboarding": count(OnboardingTask, OnboardingTask.status != "completed"),
            "training_enrollments": count(TrainingEnrollment, TrainingEnrollment.status.in_(["enrolled", "in_progress"])),
            "reviews_open": count(PerformanceReview, PerformanceReview.status != "completed"),
            "development_plans_active": count(DevelopmentPlan, DevelopmentPlan.status == "active"),
        },
        "availability": {
            "vacations_scheduled": count(VacationPeriod, VacationPeriod.status.in_(["scheduled", "approved", "in_progress"])),
            "leaves_active": count(EmployeeLeave, EmployeeLeave.status.in_(["approved", "active"])),
            "occurrences_open": count(EmployeeOccurrence, EmployeeOccurrence.status == "open"),
        },
    }
