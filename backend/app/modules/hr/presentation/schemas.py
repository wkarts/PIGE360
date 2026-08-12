from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HrModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DepartmentCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    parent_id: str | None = None
    cost_center_id: str | None = None


class DepartmentPatch(HrModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    parent_id: str | None = None
    cost_center_id: str | None = None
    manager_employee_id: str | None = None
    status: Literal["active", "inactive", "archived"] | None = None


class PositionCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    code: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=255)
    cbo_code: str | None = Field(default=None, max_length=20)
    department_id: str | None = None
    description: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    salary_floor: Decimal | None = Field(default=None, ge=0)
    salary_ceiling: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def salary_range(self) -> "PositionCreate":
        if self.salary_floor is not None and self.salary_ceiling is not None and self.salary_ceiling < self.salary_floor:
            raise ValueError("O teto salarial não pode ser menor que o piso.")
        return self


class PositionPatch(HrModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    cbo_code: str | None = Field(default=None, max_length=20)
    department_id: str | None = None
    description: str | None = None
    responsibilities: list[str] | None = None
    requirements: list[str] | None = None
    salary_floor: Decimal | None = Field(default=None, ge=0)
    salary_ceiling: Decimal | None = Field(default=None, ge=0)
    status: Literal["active", "inactive", "archived"] | None = None


class JobOpeningCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    position_id: str
    department_id: str | None = None
    hiring_manager_employee_id: str | None = None
    employment_type: Literal["clt", "temporary", "internship", "apprentice", "contractor", "public_servant"] = "clt"
    workplace_mode: Literal["onsite", "hybrid", "remote"] = "onsite"
    openings_count: int = Field(default=1, ge=1, le=999)
    target_start_date: date | None = None
    description: str | None = None
    requirements: list[str] = Field(default_factory=list)


class JobOpeningTransition(HrModel):
    action: Literal["publish", "pause", "reopen", "close", "cancel"]
    reason: str | None = Field(default=None, max_length=1000)


class CandidateCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    person_id: str
    source: str | None = Field(default=None, max_length=100)
    linkedin_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    resume_storage_key: str | None = Field(default=None, max_length=1000)
    resume_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    notes: str | None = None


class ApplicationCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    job_opening_id: str
    candidate_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplicationStage(HrModel):
    stage: Literal["screening", "interview", "technical_test", "behavioral_test", "manager_interview", "reference_check", "offer", "approved", "rejected", "withdrawn"]
    outcome: str | None = Field(default=None, max_length=60)
    score: Decimal | None = Field(default=None, ge=0, le=100)
    scheduled_at: datetime | None = None
    notes: str | None = None
    rejection_reason: str | None = None


class AdmissionCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    application_id: str
    proposed_position_id: str
    proposed_salary: Decimal = Field(gt=0)
    proposed_start_date: date
    employment_type: Literal["clt", "temporary", "internship", "apprentice", "contractor", "public_servant"] = "clt"
    checklist: list[dict[str, Any]] = Field(default_factory=list)


class AdmissionTransition(HrModel):
    action: Literal["submit", "approve", "request_changes", "cancel"]
    reason: str | None = None


class AdmissionHire(HrModel):
    registration_number: str = Field(min_length=2, max_length=80)
    corporate_email: str | None = Field(default=None, max_length=320)
    contract_number: str = Field(min_length=2, max_length=100)
    department_id: str | None = None
    cost_center_id: str | None = None
    manager_employee_id: str | None = None
    weekly_hours: Decimal = Field(default=Decimal("44"), gt=0, le=60)
    salary_unit: Literal["monthly", "hourly", "daily"] = "monthly"
    payment_frequency: Literal["monthly", "weekly", "biweekly"] = "monthly"
    work_schedule_id: str | None = None
    union_id: str | None = None
    probation_end_date: date | None = None
    onboarding_tasks: list[dict[str, Any]] = Field(default_factory=list)
    terms: dict[str, Any] = Field(default_factory=dict)


class EmployeePatch(HrModel):
    corporate_email: str | None = Field(default=None, max_length=320)
    employment_status: Literal["active", "on_leave", "vacation", "suspended", "terminated"] | None = None
    metadata: dict[str, Any] | None = None


class OnboardingTaskCreate(HrModel):
    task_code: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=2, max_length=255)
    assigned_to_user_id: str | None = None
    due_date: date | None = None
    required: bool = True


class OnboardingTaskComplete(HrModel):
    evidence: dict[str, Any] = Field(default_factory=dict)


class TrainingCourseCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    provider_name: str | None = Field(default=None, max_length=255)
    workload_hours: Decimal = Field(gt=0)
    validity_months: int | None = Field(default=None, ge=1, le=240)
    mandatory: bool = False


class TrainingEnroll(HrModel):
    employee_id: str


class TrainingComplete(HrModel):
    score: Decimal | None = Field(default=None, ge=0, le=100)
    certificate_storage_key: str | None = Field(default=None, max_length=1000)
    certificate_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class CompetencyCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    category: Literal["technical", "behavioral", "leadership", "compliance", "pedagogical"] = "technical"
    scale: list[dict[str, Any]] = Field(default_factory=list)


class EmployeeCompetencyUpsert(HrModel):
    employee_id: str
    current_level: Decimal = Field(ge=0)
    target_level: Decimal | None = Field(default=None, ge=0)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class PerformanceReviewCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    cycle_code: str = Field(min_length=2, max_length=100)
    reviewer_employee_id: str | None = None
    period_start: date
    period_end: date
    goals: list[dict[str, Any]] = Field(default_factory=list)
    competencies: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def dates(self) -> "PerformanceReviewCreate":
        if self.period_end < self.period_start:
            raise ValueError("O fim da avaliação deve ser posterior ao início.")
        return self


class PerformanceReviewComplete(HrModel):
    overall_score: Decimal = Field(ge=0, le=100)
    feedback: str = Field(min_length=2)
    competencies: list[dict[str, Any]] | None = None


class DevelopmentPlanCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    performance_review_id: str | None = None
    cycle_code: str = Field(min_length=2, max_length=100)
    objectives: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    started_on: date
    due_on: date | None = None


class DevelopmentPlanProgress(HrModel):
    progress_percentage: Decimal = Field(ge=0, le=100)
    status: Literal["active", "paused", "completed", "cancelled"] | None = None


class BenefitPlanCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    benefit_type: str = Field(min_length=2, max_length=80)
    provider_name: str | None = Field(default=None, max_length=255)
    employer_amount: Decimal = Field(default=Decimal("0"), ge=0)
    employee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    payroll_rubric_code: str | None = Field(default=None, max_length=80)
    settings: dict[str, Any] = Field(default_factory=dict)


class EmployeeBenefitCreate(HrModel):
    employee_id: str
    benefit_plan_id: str
    valid_from: date
    valid_until: date | None = None
    employer_amount: Decimal | None = Field(default=None, ge=0)
    employee_amount: Decimal | None = Field(default=None, ge=0)
    dependents: list[str] = Field(default_factory=list)


class VacationCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    accrual_start: date
    accrual_end: date
    entitlement_days: int = Field(default=30, ge=1, le=60)
    scheduled_start: date | None = None
    scheduled_end: date | None = None
    sold_days: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def period(self) -> "VacationCreate":
        if self.accrual_end < self.accrual_start:
            raise ValueError("Período aquisitivo inválido.")
        if (self.scheduled_start is None) != (self.scheduled_end is None):
            raise ValueError("Informe início e fim das férias conjuntamente.")
        if self.scheduled_start and self.scheduled_end and self.scheduled_end < self.scheduled_start:
            raise ValueError("Período de gozo inválido.")
        return self


class VacationTransition(HrModel):
    action: Literal["schedule", "approve", "start", "complete", "cancel"]
    scheduled_start: date | None = None
    scheduled_end: date | None = None
    reason: str | None = None


class LeaveCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    leave_type: str = Field(min_length=2, max_length=80)
    start_date: date
    end_date: date | None = None
    paid: bool = True
    affects_payroll: bool = True
    reason: str = Field(min_length=2)
    document_id: str | None = None


class LeaveTransition(HrModel):
    action: Literal["approve", "reject", "cancel", "complete"]
    reason: str | None = None


class OccurrenceCreate(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    occurrence_type: str = Field(min_length=2, max_length=80)
    occurred_at: datetime
    severity: Literal["informational", "low", "medium", "high", "critical"] = "informational"
    description: str = Field(min_length=2)
    confidential: bool = False


class OccurrenceResolve(HrModel):
    resolution: str = Field(min_length=2)


class HrDashboardFilter(HrModel):
    institution_id: str | None = None
    unit_id: str | None = None
