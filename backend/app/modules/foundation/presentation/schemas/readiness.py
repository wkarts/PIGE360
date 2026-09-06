from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReadinessTenant(BaseModel):
    id: str
    code: str | None = None


class ReadinessCheck(BaseModel):
    name: str
    status: Literal["pass", "fail"]
    critical: bool
    duration_ms: float = Field(ge=0)
    details: dict[str, Any] | None = None
    tenant: ReadinessTenant | None = None


class ReadinessSummary(BaseModel):
    checks: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    active_tenants: int = Field(ge=0)
    failed_critical: list[str]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    plane: str
    environment: str
    checked_at: str
    summary: ReadinessSummary
    checks: list[ReadinessCheck]
