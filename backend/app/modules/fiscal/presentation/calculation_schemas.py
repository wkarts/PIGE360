from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaxCode = Literal[
    "ICMS", "ICMS_ST", "FCP", "IPI", "PIS", "COFINS", "ISS",
    "IBS_ESTADUAL", "IBS_MUNICIPAL", "CBS", "IS",
]
Incidence = Literal[
    "taxable", "exempt", "deferred", "suspended", "immune",
    "non_incident", "zero_rate", "monophase",
]
BaseMode = Literal["operation_total", "custom", "mva"]
RuleItemKind = Literal["product", "service", "mixed", "any"]
RtcScope = Literal["any", "disabled", "simulation_only", "optional_emit", "required_emit"]


class FiscalCalcModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiscalTaxComponentInput(FiscalCalcModel):
    tax: TaxCode
    incidence: Incidence = "taxable"
    base_mode: BaseMode = "operation_total"
    rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    base_reduction_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    deferral_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    suspension_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    mva_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1000)
    monophase_amount_per_unit: Decimal | None = Field(default=None, ge=0)
    custom_base_key: str | None = Field(default=None, max_length=80)
    include_amount_keys: list[str] = Field(default_factory=list, max_length=20)
    deduct_amount_keys: list[str] = Field(default_factory=list, max_length=20)
    deduct_tax_codes: list[TaxCode] = Field(default_factory=list, max_length=10)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_component(self):
        if self.base_mode == "custom" and not self.custom_base_key:
            raise ValueError("custom_base_key é obrigatório quando base_mode=custom")
        if self.incidence == "monophase" and self.monophase_amount_per_unit is None and self.rate_pct == 0:
            raise ValueError("Regra monofásica exige valor por unidade ou alíquota")
        if self.incidence != "deferred" and self.deferral_pct:
            raise ValueError("deferral_pct somente é permitido para incidência deferred")
        if self.incidence != "suspended" and self.suspension_pct:
            raise ValueError("suspension_pct somente é permitido para incidência suspended")
        return self


class FiscalTaxRuleSetCreate(FiscalCalcModel):
    fiscal_context_id: str
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    establishment_code: str | None = Field(default=None, max_length=80)
    operation_type: str = Field(default="sale", min_length=1, max_length=80)
    item_kind: RuleItemKind = "any"
    tax_regime: str = Field(default="any", min_length=1, max_length=80)
    rtc_mode: RtcScope = "any"
    priority: int = Field(default=100, ge=0, le=100000)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")

    @field_validator("operation_type", "tax_regime")
    @classmethod
    def normalize_scope(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class FiscalTaxRuleVersionCreate(FiscalCalcModel):
    version_label: str = Field(min_length=1, max_length=120)
    valid_from: date
    valid_until: date | None = None
    source_name: str = Field(min_length=2, max_length=255)
    source_reference: str | None = Field(default=None, max_length=2000)
    source_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    legal_basis: list[str] = Field(default_factory=list, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)
    components: list[FiscalTaxComponentInput] = Field(min_length=1, max_length=30)
    expected_rule_set_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_version(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        taxes = [component.tax for component in self.components]
        if len(taxes) != len(set(taxes)):
            raise ValueError("Não pode existir mais de um componente para o mesmo tributo na mesma versão")
        return self


class FiscalTaxRuleVersionPublish(FiscalCalcModel):
    expected_rule_set_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class FiscalTaxSimulationInput(FiscalCalcModel):
    fiscal_context_id: str
    establishment_code: str | None = Field(default=None, max_length=80)
    operation_type: str = Field(default="sale", min_length=1, max_length=80)
    item_kind: Literal["product", "service", "mixed"]
    item_id: str | None = None
    occurred_on: date = Field(default_factory=date.today)
    amount: Decimal = Field(ge=0)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    freight: Decimal = Field(default=Decimal("0"), ge=0)
    insurance: Decimal = Field(default=Decimal("0"), ge=0)
    other_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    custom_bases: dict[str, Decimal] = Field(default_factory=dict)
    custom_amounts: dict[str, Decimal] = Field(default_factory=dict)
    expected_taxes: dict[str, Decimal] = Field(default_factory=dict)
    recipient_scope: str = Field(default="any", max_length=80)
    document_type: str = Field(default="any", max_length=40)
    origin_uf: str | None = Field(default=None, min_length=2, max_length=2)
    destination_uf: str | None = Field(default=None, min_length=2, max_length=2)
    final_consumer: bool = False

    @model_validator(mode="after")
    def validate_totals(self):
        gross = self.amount + self.freight + self.insurance + self.other_amount
        if self.discount > gross:
            raise ValueError("Desconto não pode ser superior ao valor bruto da operação")
        return self
