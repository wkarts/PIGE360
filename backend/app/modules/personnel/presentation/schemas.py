from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PersonnelModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DependentCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    person_id: str
    relationship: str = Field(min_length=2, max_length=60)
    income_tax_dependent: bool = False
    family_allowance_dependent: bool = False
    health_plan_dependent: bool = False
    valid_from: date
    valid_until: date | None = None


class SalaryChangeCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    employment_contract_id: str
    effective_from: date
    salary_amount: Decimal = Field(gt=0)
    salary_unit: Literal["monthly", "hourly", "daily"] = "monthly"
    change_type: Literal["admission", "promotion", "adjustment", "collective_agreement", "court_order", "correction"]
    reason: str = Field(min_length=2)


class StabilityCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    stability_type: str = Field(min_length=2, max_length=80)
    start_date: date
    end_date: date | None = None
    legal_basis: str | None = None


class UnionCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    legal_name: str = Field(min_length=2, max_length=255)
    trade_name: str = Field(min_length=2, max_length=255)
    document_number: str = Field(min_length=8, max_length=20)
    union_code: str | None = Field(default=None, max_length=80)
    base_date_month: int | None = Field(default=None, ge=1, le=12)
    collective_agreement: dict[str, Any] = Field(default_factory=dict)


class EmployeeLoanCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    loan_number: str = Field(min_length=2, max_length=100)
    lender_name: str = Field(min_length=2, max_length=255)
    principal_amount: Decimal = Field(gt=0)
    installment_amount: Decimal = Field(gt=0)
    installment_count: int = Field(ge=1, le=600)
    first_competence: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    payroll_rubric_code: str = Field(min_length=2, max_length=80)


class AlimonyCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    beneficiary_person_id: str
    court_case_number: str = Field(min_length=2, max_length=120)
    calculation_type: Literal["fixed", "percentage"]
    rate: Decimal | None = Field(default=None, gt=0, le=100)
    fixed_amount: Decimal | None = Field(default=None, gt=0)
    calculation_base: Literal["gross", "net", "taxable", "salary"] = "net"
    valid_from: date
    valid_until: date | None = None

    @model_validator(mode="after")
    def mode_value(self) -> "AlimonyCreate":
        if self.calculation_type == "fixed" and self.fixed_amount is None:
            raise ValueError("Informe o valor fixo da pensão.")
        if self.calculation_type == "percentage" and self.rate is None:
            raise ValueError("Informe o percentual da pensão.")
        return self


class EmployeeDocumentCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    document_type: str = Field(min_length=2, max_length=80)
    document_number: str = Field(min_length=1, max_length=160)
    issued_on: date | None = None
    expires_on: date | None = None
    storage_key: str | None = Field(default=None, max_length=1000)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MedicalExamCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    exam_type: Literal["admission", "periodic", "return_to_work", "change_of_risk", "termination", "other"]
    performed_on: date
    expires_on: date | None = None
    result: Literal["fit", "fit_with_restrictions", "unfit"]
    provider_name: str | None = Field(default=None, max_length=255)
    storage_key: str | None = Field(default=None, max_length=1000)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    restrictions: list[str] = Field(default_factory=list)


class TerminationCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    employee_id: str
    employment_contract_id: str
    termination_type: str = Field(min_length=2, max_length=80)
    notice_type: str | None = Field(default=None, max_length=80)
    notice_date: date | None = None
    effective_date: date
    reason: str = Field(min_length=2)
    settlement_amount: Decimal | None = Field(default=None, ge=0)
    checklist: list[dict[str, Any]] = Field(default_factory=list)


class TerminationTransition(PersonnelModel):
    action: Literal["submit", "approve", "complete", "cancel"]
    reason: str | None = None


class GovernmentProviderCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    provider_code: Literal["esocial", "fgts_digital", "dctfweb", "local_test"]
    display_name: str = Field(min_length=2, max_length=180)
    environment: Literal["homologation", "production", "test"] = "homologation"
    endpoint_url: str | None = Field(default=None, max_length=500)
    secret_ref: str | None = Field(default=None, max_length=500)
    certificate_secret_ref: str | None = Field(default=None, max_length=500)
    schema_version: str | None = Field(default=None, max_length=80)
    capabilities: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False


class GovernmentSubmissionCreate(PersonnelModel):
    institution_id: str | None = None
    unit_id: str | None = None
    provider_configuration_id: str
    event_type: str = Field(min_length=2, max_length=100)
    employee_id: str | None = None
    competence: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    idempotency_reference: str = Field(min_length=8, max_length=180)
    schema_version: str = Field(min_length=1, max_length=80)
    payload_snapshot: dict[str, Any] = Field(default_factory=dict)


class GovernmentSubmissionProcess(PersonnelModel):
    force: bool = False
