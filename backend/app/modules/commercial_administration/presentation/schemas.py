from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, StrictInt, field_validator, model_validator


Code = str


class PartnerCreate(BaseModel):
    code: Code = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    legal_name: str = Field(min_length=2, max_length=300)
    trade_name: str = Field(min_length=2, max_length=200)
    contact_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().lower()


class PartnerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)
    legal_name: str | None = Field(default=None, min_length=2, max_length=300)
    trade_name: str | None = Field(default=None, min_length=2, max_length=200)
    contact_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set.intersection({"legal_name", "trade_name", "contact_email", "notes"}):
            raise ValueError("Informe ao menos um campo do parceiro para atualizar")
        for name in ("legal_name", "trade_name"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} não pode ser nulo")
        return self


class LifecycleInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


class LinkTenantInput(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class PlanCreate(BaseModel):
    code: Code = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,49}$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    billing_interval: Literal["monthly", "annual", "custom"] = "monthly"
    price_minor: int = Field(default=0, ge=0, le=10_000_000_000)
    features: dict[str, StrictBool] = Field(default_factory=dict)
    limits: dict[str, StrictInt] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("features", "limits")
    @classmethod
    def validate_keys(cls, value: dict[str, object]) -> dict[str, object]:
        if len(value) > 200:
            raise ValueError("O catálogo aceita no máximo 200 itens por mapa")
        for key in value:
            if not key or len(key) > 100 or not key.replace("_", "").replace("-", "").isalnum():
                raise ValueError("Chave de feature/limite inválida")
        if any(
            isinstance(item, int)
            and not isinstance(item, bool)
            and (item < 0 or item > 10_000_000_000_000_000)
            for item in value.values()
        ):
            raise ValueError("Limites devem estar entre zero e 10 quadrilhões")
        return value


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    billing_interval: Literal["monthly", "annual", "custom"] | None = None
    price_minor: int | None = Field(default=None, ge=0, le=10_000_000_000)
    features: dict[str, StrictBool] | None = None
    limits: dict[str, StrictInt] | None = None
    status: Literal["active", "inactive"] | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def require_change(self):
        mutable = {"name", "description", "currency", "billing_interval", "price_minor", "features", "limits", "status"}
        if not self.model_fields_set.intersection(mutable):
            raise ValueError("Informe ao menos um campo do plano para atualizar")
        for name in ("name", "currency", "billing_interval", "price_minor", "features", "limits", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} não pode ser nulo")
        if self.features is not None:
            PlanCreate.validate_keys(self.features)
        if self.limits is not None:
            PlanCreate.validate_keys(self.limits)
        return self


class SubscriptionInput(BaseModel):
    expected_version: int = Field(default=0, ge=0)
    plan_id: str = Field(min_length=1, max_length=100)
    status: Literal["active", "trialing", "suspended", "canceled"] = "active"
    starts_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    current_period_end: datetime | None = None
    trial_ends_at: datetime | None = None
    cancel_at_period_end: bool = False
    reason: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def validate_dates(self):
        for name in ("starts_at", "current_period_end", "trial_ends_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} deve incluir fuso horário")
        if self.current_period_end and self.current_period_end <= self.starts_at:
            raise ValueError("current_period_end deve ser posterior a starts_at")
        if self.trial_ends_at and self.trial_ends_at <= self.starts_at:
            raise ValueError("trial_ends_at deve ser posterior a starts_at")
        return self


class UsageSnapshotInput(BaseModel):
    expected_version: int = Field(default=0, ge=0)
    source: str = Field(default="manual", pattern=r"^[a-z0-9][a-z0-9._-]{1,49}$")
    metrics: dict[str, StrictInt]
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, int]) -> dict[str, int]:
        if not value:
            raise ValueError("Informe ao menos uma métrica")
        if len(value) > 200:
            raise ValueError("O snapshot aceita no máximo 200 métricas")
        for key, metric in value.items():
            if not key or len(key) > 100 or not key.replace("_", "").replace("-", "").isalnum():
                raise ValueError("Nome de métrica inválido")
            if isinstance(metric, bool) or metric < 0 or metric > 10_000_000_000_000_000:
                raise ValueError("Métricas devem ser inteiros entre zero e 10 quadrilhões")
        return value


class PeriodPath(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
