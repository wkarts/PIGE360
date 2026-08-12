from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FISCAL_PROVIDER_CODES = Literal[
    "SefazNfeProvider",
    "SefazNfceProvider",
    "NationalNfseProvider",
    "MunicipalNfseProvider",
    "ThirdPartyFiscalProvider",
]
FISCAL_DOCUMENT_TYPES = Literal["NF-e", "NFC-e", "NFS-e"]
FISCAL_ENVIRONMENTS = Literal["homologation", "production"]


class FiscalLifecycleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiscalCertificateMetadataCreate(FiscalLifecycleModel):
    certificate_type: Literal["a1"] = "a1"
    subject_name: str = Field(min_length=2, max_length=255)
    subject_document: str | None = Field(default=None, max_length=20)
    serial_number: str = Field(min_length=1, max_length=180)
    issuer_name: str = Field(min_length=2, max_length=255)
    valid_from: datetime
    valid_until: datetime
    fingerprint_sha256: str = Field(min_length=64, max_length=64)
    secret_ref: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fingerprint_sha256")
    @classmethod
    def fingerprint(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("Fingerprint SHA-256 inválido")
        return normalized

    @model_validator(mode="after")
    def dates(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("A validade final do certificado deve ser posterior à inicial")
        return self


class FiscalProviderConfigurationCreate(FiscalLifecycleModel):
    provider_code: FISCAL_PROVIDER_CODES
    display_name: str = Field(min_length=2, max_length=180)
    document_type: FISCAL_DOCUMENT_TYPES
    environment: FISCAL_ENVIRONMENTS = "homologation"
    endpoint_url: str | None = Field(default=None, max_length=500)
    secret_ref: str | None = Field(default=None, max_length=500)
    certificate_metadata_id: str | None = None
    capabilities: list[Literal["issue", "query", "cancel", "substitute", "inutilize", "event", "health"]] = Field(default_factory=lambda: ["issue", "query", "cancel", "health"], min_length=1, max_length=20)
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    webhook_tolerance_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("endpoint_url")
    @classmethod
    def endpoint(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("Provider fiscal externo deve utilizar HTTPS")
        return normalized


class FiscalProviderConfigurationPatch(FiscalLifecycleModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=180)
    endpoint_url: str | None = Field(default=None, max_length=500)
    secret_ref: str | None = Field(default=None, max_length=500)
    certificate_metadata_id: str | None = None
    capabilities: list[str] | None = Field(default=None, min_length=1, max_length=20)
    settings: dict[str, Any] | None = None
    enabled: bool | None = None
    webhook_tolerance_seconds: int | None = Field(default=None, ge=30, le=3600)
    expected_version: int = Field(ge=1)


class FiscalDocumentQueryRequest(FiscalLifecycleModel):
    reason: str = Field(default="Consulta de estado fiscal.", min_length=3, max_length=2000)


class FiscalDocumentSubstituteRequest(FiscalLifecycleModel):
    source_type: Literal["sale", "service_order", "manual"] = "manual"
    source_id: str = Field(min_length=1, max_length=255)
    totals: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=2000)


class FiscalInutilizationCreate(FiscalLifecycleModel):
    fiscal_profile_id: str
    provider_configuration_id: str
    document_type: Literal["NF-e", "NFC-e"]
    year: int = Field(ge=2000, le=2100)
    series: str = Field(min_length=1, max_length=20)
    start_number: int = Field(ge=1)
    end_number: int = Field(ge=1)
    reason: str = Field(min_length=15, max_length=255)

    @model_validator(mode="after")
    def interval(self):
        if self.end_number < self.start_number:
            raise ValueError("Número final deve ser maior ou igual ao inicial")
        if self.end_number - self.start_number > 10000:
            raise ValueError("Intervalo de inutilização excede o limite operacional")
        return self


class FiscalProviderEventCreate(FiscalLifecycleModel):
    event_type: Literal["correction_letter", "manifestation", "other"]
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=2000)
