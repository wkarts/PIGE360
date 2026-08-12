from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FiscalIbptProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiscalIbptProviderProfileCreate(FiscalIbptProfileModel):
    provider_code: str = Field(default="wwsoftwares", min_length=2, max_length=80)
    mode: Literal["disabled", "local_snapshot", "remote_sync"] = "local_snapshot"
    valid_from: date
    valid_until: date | None = None
    sync_enabled: bool = False
    fallback_enabled: bool = True
    fallback_max_age_days: int = Field(default=90, ge=0, le=3650)
    stale_after_days: int = Field(default=120, ge=0, le=3650)
    base_url: str | None = Field(default=None, max_length=1000)
    uf_path: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("provider_code")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        if self.mode != "remote_sync" and self.sync_enabled:
            raise ValueError("sync_enabled exige mode=remote_sync")
        return self


class FiscalIbptProviderProfilePublish(FiscalIbptProfileModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)
