from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CatalogKind = Literal[
    "NCM", "NBS", "LC116", "CFOP", "CEST", "CST", "CSOSN", "CST_IBS_CBS", "CCLASSTRIB", "CBENEF",
    "CREDITO_PRESUMIDO", "RTC_TABLE", "NFSE_CORRELATION", "MUNICIPAL_CODE", "TAX_RATE", "TECHNICAL_NOTE"
]
ItemKind = Literal["product", "service", "mixed"]


class FiscalCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def normalize_catalog_code(value: str) -> str:
    value = value.strip().upper().replace(" ", "")
    if not value:
        raise ValueError("Código do catálogo é obrigatório")
    return value


class FiscalCatalogCreate(FiscalCatalogModel):
    kind: CatalogKind
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    normalization: Literal["digits", "upper_alnum", "preserve"] = "upper_alnum"
    code_pattern: str | None = Field(default=None, max_length=240)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FiscalCatalogEntryInput(FiscalCatalogModel):
    code: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    parent_code: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "parent_code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return normalize_catalog_code(value) if value else value


class FiscalCatalogVersionCreate(FiscalCatalogModel):
    version_label: str = Field(min_length=1, max_length=120)
    valid_from: date
    valid_until: date | None = None
    source_name: str = Field(min_length=2, max_length=255)
    source_reference: str | None = Field(default=None, max_length=2000)
    source_sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    schema_version: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    entries: list[FiscalCatalogEntryInput] = Field(min_length=1, max_length=50000)

    @model_validator(mode="after")
    def validate_period_and_duplicates(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        codes = [entry.code for entry in self.entries]
        if len(codes) != len(set(codes)):
            raise ValueError("Existem códigos duplicados na versão do catálogo")
        return self


class FiscalCatalogVersionPublish(FiscalCatalogModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class FiscalClassificationRuleCreate(FiscalCatalogModel):
    fiscal_context_id: str
    establishment_code: str | None = Field(default=None, max_length=80)
    item_kind: ItemKind
    item_id: str | None = None
    operation_type: str = Field(min_length=1, max_length=80)
    valid_from: date
    valid_until: date | None = None
    priority: int = Field(default=100, ge=0, le=100000)
    ncm: str | None = Field(default=None, max_length=80)
    nbs: str | None = Field(default=None, max_length=80)
    lc116: str | None = Field(default=None, max_length=80)
    cfop: str | None = Field(default=None, max_length=80)
    cest: str | None = Field(default=None, max_length=80)
    cst: str | None = Field(default=None, max_length=80)
    csosn: str | None = Field(default=None, max_length=80)
    cst_ibs_cbs: str | None = Field(default=None, max_length=80)
    cclasstrib: str | None = Field(default=None, max_length=80)
    cbenef: str | None = Field(default=None, max_length=80)
    municipal_code: str | None = Field(default=None, max_length=80)
    cnae: str | None = Field(default=None, max_length=20)
    tax_configuration: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("operation_type")
    @classmethod
    def normalize_operation(cls, value: str) -> str:
        value = value.strip().lower().replace(" ", "_")
        if not value:
            raise ValueError("Tipo de operação obrigatório")
        return value

    @field_validator("ncm", "nbs", "lc116", "cfop", "cest", "cst", "csosn", "cst_ibs_cbs", "cclasstrib", "cbenef")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
        return normalize_catalog_code(value) if value else None

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        return self


class FiscalClassificationRulePatch(FiscalCatalogModel):
    expected_version: int = Field(ge=1)
    valid_until: date | None = None
    priority: int | None = Field(default=None, ge=0, le=100000)
    tax_configuration: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["draft", "archived"] | None = None


class FiscalClassificationRulePublish(FiscalCatalogModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class FiscalReadinessQuery(FiscalCatalogModel):
    fiscal_context_id: str
    establishment_code: str | None = None
    occurred_on: date = Field(default_factory=date.today)
    operation_type: str = Field(default="sale", min_length=1, max_length=80)
