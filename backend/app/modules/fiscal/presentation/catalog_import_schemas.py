from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CatalogSourceProvider = Literal["local_file", "external_http", "manual_snapshot"]
CatalogImportFormat = Literal["csv", "json", "xsd"]


class CatalogGovernanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiscalCatalogSourceCreate(CatalogGovernanceModel):
    provider_type: CatalogSourceProvider = "local_file"
    provider_key: str = Field(min_length=2, max_length=120)
    provider_version: str = Field(default="1", min_length=1, max_length=40)
    import_format: CatalogImportFormat
    source_reference: str | None = Field(default=None, max_length=2000)
    encoding: str = Field(default="utf-8", min_length=3, max_length=40)
    delimiter: str = Field(default=";", min_length=1, max_length=4)
    max_age_days: int = Field(default=90, ge=1, le=3650)
    mapping: dict[str, Any] = Field(default_factory=dict)
    validation_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_provider(self):
        if self.provider_type == "external_http" and not self.source_reference:
            # Perfil pode existir sem URL, mas permanecerá not_configured.
            return self
        if self.import_format == "csv" and len(self.delimiter) != 1:
            raise ValueError("CSV exige delimitador de um único caractere")
        return self


class FiscalCatalogImportCreate(CatalogGovernanceModel):
    source_profile_id: str
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4)
    version_label: str = Field(min_length=1, max_length=120)
    valid_from: date
    valid_until: date | None = None
    schema_version: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    auto_publish: bool = False

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        return self


class FiscalCatalogImportPublish(CatalogGovernanceModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class FiscalCatalogRollback(CatalogGovernanceModel):
    effective_from: date
    reason: str = Field(min_length=3, max_length=4000)


class FiscalCatalogQuarantineResolve(CatalogGovernanceModel):
    action: Literal["resolved", "discarded"]
    reason: str = Field(min_length=3, max_length=4000)
