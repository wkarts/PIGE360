from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgentCapability = Literal["backup.execute", "restore.execute", "deploy.execute"]
AgentType = Literal["host", "backup", "restore", "deploy", "multi"]
OperationType = Literal["backup", "restore", "deploy"]
OperationState = Literal["queued", "claimed", "running", "succeeded", "failed", "cancelled"]

_SEMVER_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
_OPAQUE_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,239}$"
_RESULT_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{2,79}$"


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRegistrationInput(StrictInput):
    name: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    agent_type: AgentType
    capabilities: list[AgentCapability] = Field(min_length=1, max_length=3)
    software_version: str | None = Field(default=None, max_length=64, pattern=_SEMVER_PATTERN)
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[AgentCapability]) -> list[AgentCapability]:
        if len(value) != len(set(value)):
            raise ValueError("Capabilities repetidas não são permitidas")
        return sorted(value)

    @model_validator(mode="after")
    def capability_matches_type(self):
        expected = {
            "backup": "backup.execute",
            "restore": "restore.execute",
            "deploy": "deploy.execute",
        }.get(self.agent_type)
        if expected and self.capabilities != [expected]:
            raise ValueError(f"O agent_type '{self.agent_type}' aceita somente '{expected}'")
        return self


class AgentHeartbeatInput(StrictInput):
    software_version: str | None = Field(default=None, max_length=64, pattern=_SEMVER_PATTERN)


class AgentRevokeInput(StrictInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


class OperationalJobCreate(StrictInput):
    operation_type: OperationType
    resource_scope: Literal["platform", "tenant"] = "platform"
    tenant_id: str | None = Field(default=None, min_length=1, max_length=100)
    deployment_target: Literal["base", "cloudpanel", "edge", "dockge", "portainer"] | None = None
    image_mode: Literal["source", "registry"] | None = None
    release_version: str | None = Field(default=None, max_length=64, pattern=_SEMVER_PATTERN)
    backup_reference: str | None = Field(default=None, max_length=200, pattern=_OPAQUE_REFERENCE_PATTERN)
    reason: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def validate_typed_operation(self):
        if self.resource_scope == "tenant" and not self.tenant_id:
            raise ValueError("tenant_id é obrigatório para resource_scope=tenant")
        if self.resource_scope == "platform" and self.tenant_id:
            raise ValueError("tenant_id não é aceito para resource_scope=platform")

        if self.operation_type == "backup":
            if any((self.backup_reference, self.release_version, self.deployment_target, self.image_mode)):
                raise ValueError("Backup não aceita referência, release ou parâmetros de deploy")
        elif self.operation_type == "restore":
            if not self.backup_reference:
                raise ValueError("backup_reference é obrigatório para restore")
            if any((self.release_version, self.deployment_target, self.image_mode)):
                raise ValueError("Restore não aceita release ou parâmetros de deploy")
        else:
            if self.resource_scope != "platform":
                raise ValueError("Deploy é uma operação de escopo platform")
            if not self.release_version or not self.deployment_target or not self.image_mode:
                raise ValueError("Deploy exige release_version, deployment_target e image_mode")
            if self.backup_reference:
                raise ValueError("Deploy não aceita backup_reference")
        return self


class OperationalJobCancelInput(StrictInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


class AgentJobStateInput(StrictInput):
    expected_version: int = Field(ge=1)
    state: Literal["running", "succeeded", "failed"]
    result_code: str | None = Field(default=None, pattern=_RESULT_CODE_PATTERN)
    evidence_reference: str | None = Field(default=None, max_length=240, pattern=_OPAQUE_REFERENCE_PATTERN)
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    failure_code: str | None = Field(default=None, pattern=_RESULT_CODE_PATTERN)

    @model_validator(mode="after")
    def validate_state_evidence(self):
        if self.state == "running":
            if any((self.result_code, self.evidence_reference, self.evidence_sha256, self.failure_code)):
                raise ValueError("running não aceita resultado, evidência ou falha")
        elif self.state == "succeeded":
            if not self.result_code or not self.evidence_reference:
                raise ValueError("succeeded exige result_code e evidence_reference")
            if self.failure_code:
                raise ValueError("succeeded não aceita failure_code")
        else:
            if not self.failure_code:
                raise ValueError("failed exige failure_code")
            if any((self.result_code, self.evidence_reference, self.evidence_sha256)):
                raise ValueError("failed não aceita resultado ou evidência de sucesso")
        return self
