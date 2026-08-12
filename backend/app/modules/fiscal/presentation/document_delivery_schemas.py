from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FiscalDeliveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiscalDeliveryPolicyCreate(FiscalDeliveryModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=2, max_length=180)
    document_type: Literal["any", "NF-e", "NFC-e", "NFS-e"] = "any"
    provider_code: str | None = Field(default=None, max_length=80)
    environment: Literal["any", "homologation", "production"] = "any"
    valid_from: date
    valid_until: date | None = None
    priority: int = Field(default=100, ge=0, le=10000)
    max_attempts: int = Field(default=3, ge=1, le=30)
    base_delay_seconds: int = Field(default=30, ge=0, le=86400)
    max_delay_seconds: int = Field(default=1800, ge=0, le=604800)
    backoff_multiplier: Decimal = Field(default=Decimal("2"), ge=Decimal("1"), le=Decimal("10"))
    jitter_seconds: int = Field(default=0, ge=0, le=3600)
    auto_retry: bool = True
    contingency_after_attempts: int | None = Field(default=None, ge=1, le=30)
    contingency_mode: Literal["offline", "svc", "epec"] | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds deve ser maior ou igual a base_delay_seconds")
        if self.contingency_after_attempts is not None and not self.contingency_mode:
            raise ValueError("contingency_mode é obrigatório quando contingency_after_attempts é informado")
        return self


class FiscalDeliveryPolicyPublish(FiscalDeliveryModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class FiscalDocumentRetryRequest(FiscalDeliveryModel):
    reason: str = Field(min_length=3, max_length=2000)
    force: bool = False


class FiscalDocumentRenderRequest(FiscalDeliveryModel):
    force: bool = False
