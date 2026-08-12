from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CatalogCreate(StrictModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    valid_from: date | None = None
    valid_until: date | None = None
    status: Literal["draft", "active", "inactive", "archived"] = "active"
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        return self


class CatalogUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    valid_from: date | None = None
    valid_until: date | None = None
    status: Literal["draft", "active", "inactive", "archived"] | None = None
    expected_version: int = Field(ge=1)


class ServiceCreateUnified(StrictModel):
    # Contrato legado preservado.
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    recurrence: str | None = Field(default=None, max_length=40)
    nbs: str | None = Field(default=None, max_length=20)
    lc116_code: str | None = Field(default=None, max_length=20)
    municipal_code: str | None = Field(default=None, max_length=80)
    cnae: str | None = Field(default=None, max_length=20)
    fiscal_profile: dict[str, Any] = Field(default_factory=dict)
    # Contrato vertical atual.
    catalog_id: str | None = None
    service_type: Literal[
        "tuition", "enrollment", "course", "transportation", "extracurricular", "event", "travel",
        "document", "training", "rental", "administrative", "recurring", "one_time", "package", "other",
    ] = "other"
    recurrence_type: Literal["one_time", "monthly", "bimonthly", "quarterly", "semiannual", "annual", "custom"] = "one_time"
    unit_of_measure: str = Field(default="unit", min_length=1, max_length=40)
    default_duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    cost_center_id: str | None = None
    taxable: bool = True
    status: Literal["draft", "active", "inactive", "archived"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    institution_id: str | None = None
    unit_id: str | None = None


class ServiceUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    recurrence_type: Literal["one_time", "monthly", "bimonthly", "quarterly", "semiannual", "annual", "custom"] | None = None
    unit_of_measure: str | None = Field(default=None, min_length=1, max_length=40)
    default_duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    cost_center_id: str | None = None
    taxable: bool | None = None
    status: Literal["draft", "active", "inactive", "archived"] | None = None
    metadata: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class VariantCreate(StrictModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    capacity: int | None = Field(default=None, ge=1)
    status: Literal["active", "inactive", "archived"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    institution_id: str | None = None
    unit_id: str | None = None


class VariantUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    capacity: int | None = Field(default=None, ge=1)
    status: Literal["active", "inactive", "archived"] | None = None
    metadata: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class FiscalProfileCreate(StrictModel):
    variant_id: str | None = None
    valid_from: date
    valid_until: date | None = None
    nbs_code: str | None = Field(default=None, max_length=20)
    lc116_code: str | None = Field(default=None, max_length=20)
    municipal_service_code: str | None = Field(default=None, max_length=80)
    cnae_code: str | None = Field(default=None, max_length=20)
    iss_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=18, decimal_places=6)
    ibs_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=18, decimal_places=6)
    cbs_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=18, decimal_places=6)
    cclass_trib: str | None = Field(default=None, max_length=20)
    fiscal_trigger: Literal["competence", "billing", "payment", "execution", "manual"] = "billing"
    withholding: dict[str, Any] = Field(default_factory=dict)
    rules_snapshot: dict[str, Any] = Field(default_factory=dict)
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        return self


class FiscalProfilePublish(StrictModel):
    notes: str | None = Field(default=None, max_length=4000)


class PriceTableCreate(StrictModel):
    variant_id: str | None = None
    name: str = Field(min_length=2, max_length=180)
    valid_from: date
    valid_until: date | None = None
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    billing_frequency: Literal["one_time", "monthly", "bimonthly", "quarterly", "semiannual", "annual", "custom"] = "one_time"
    status: Literal["active", "inactive", "archived"] = "active"
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        return self


class BillingRuleCreate(StrictModel):
    variant_id: str | None = None
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    billing_trigger: Literal["competence", "billing", "payment", "execution", "manual"] = "competence"
    due_day: int = Field(default=10, ge=1, le=31)
    installment_count: int = Field(default=1, ge=1, le=240)
    interval_months: int = Field(default=1, ge=1, le=24)
    recognition_policy: Literal["competence", "billing", "payment", "execution"] = "competence"
    fiscal_trigger: Literal["competence", "billing", "payment", "execution", "manual"] = "competence"
    proration_policy: Literal["none", "daily", "monthly_30", "full_cycle"] = "none"
    status: Literal["active", "inactive", "archived"] = "active"
    config: dict[str, Any] = Field(default_factory=dict)
    institution_id: str | None = None
    unit_id: str | None = None


class SubscriptionCreate(StrictModel):
    subscription_number: str = Field(min_length=1, max_length=100)
    service_id: str
    variant_id: str | None = None
    subscriber_person_id: str
    enrollment_id: str | None = None
    financial_contract_id: str | None = None
    billing_rule_id: str
    starts_on: date
    ends_on: date | None = None
    quantity: Decimal = Field(default=Decimal("1.0000"), gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    next_competence_on: date | None = None
    auto_renew: bool = False
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on não pode ser anterior a starts_on")
        return self


class SubscriptionDecision(StrictModel):
    reason: str | None = Field(default=None, max_length=4000)


class CompetenceGenerate(StrictModel):
    competence_key: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    due_date: date | None = None
    force: bool = False


class OrderItemInput(StrictModel):
    service_id: str
    variant_id: str | None = None
    description: str | None = Field(default=None, max_length=255)
    quantity: Decimal = Field(default=Decimal("1.0000"), gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    competence_start: date | None = None
    competence_end: date | None = None


class ServiceOrderCreateUnified(StrictModel):
    # Contrato legado.
    responsible_guardian_id: str | None = None
    competence: str | None = None
    first_due_date: date | None = None
    # Contrato vertical.
    order_number: str | None = Field(default=None, max_length=100)
    subscriber_person_id: str | None = None
    subscription_id: str | None = None
    enrollment_id: str | None = None
    financial_contract_id: str | None = None
    competence_id: str | None = None
    cost_center_id: str | None = None
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    due_date: date | None = None
    installment_count: int = Field(default=1, ge=1, le=240)
    items: list[OrderItemInput] = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    institution_id: str | None = None
    unit_id: str | None = None

    @property
    def legacy_mode(self) -> bool:
        return not self.order_number and not self.subscriber_person_id and self.due_date is None


class OrderConfirm(StrictModel):
    notes: str | None = Field(default=None, max_length=4000)


class OrderCancel(StrictModel):
    reason: str = Field(min_length=3, max_length=4000)


class ExecutionCreate(StrictModel):
    order_item_id: str
    scheduled_at: datetime | None = None
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    performer_person_id: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    institution_id: str | None = None
    unit_id: str | None = None


class ExecutionStart(StrictModel):
    notes: str | None = Field(default=None, max_length=4000)


class ExecutionComplete(StrictModel):
    completed_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    notes: str | None = Field(default=None, max_length=4000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ExecutionCancel(StrictModel):
    reason: str = Field(min_length=3, max_length=4000)
