from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

FISCAL_PROVIDER_CODES = {
    "SefazNfeProvider",
    "SefazNfceProvider",
    "NationalNfseProvider",
    "MunicipalNfseProvider",
    "ThirdPartyFiscalProvider",
}


class FiscalContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def normalize_cnpj(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) != 14:
        raise ValueError("CNPJ deve possuir 14 dígitos")
    if len(set(digits)) == 1:
        raise ValueError("CNPJ inválido")

    numbers = [int(character) for character in digits]
    for position, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        remainder = sum(numbers[index] * weights[index] for index in range(position)) % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if numbers[position] != expected:
            raise ValueError("CNPJ inválido")
    return digits


def normalize_code(value: str) -> str:
    normalized = "-".join(value.strip().upper().replace("_", "-").split())
    if not normalized:
        raise ValueError("Código fiscal obrigatório")
    return normalized


def normalize_operation(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_.:-")
    if not normalized or any(character not in allowed for character in normalized):
        raise ValueError("Tipo de operação deve usar somente letras, números, ponto, hífen, dois-pontos ou sublinhado")
    return normalized


class FiscalContextCreate(FiscalContextModel):
    code: str = Field(min_length=2, max_length=80)
    establishment_name: str = Field(min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    cnpj: str = Field(min_length=14, max_length=20)
    institution_id: str | None = None
    unit_id: str | None = None
    state_registration: str | None = Field(default=None, max_length=40)
    municipal_registration: str | None = Field(default=None, max_length=40)
    provider_connection_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_code(value)

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        return normalize_cnpj(value)


class FiscalContextPatch(FiscalContextModel):
    establishment_name: str | None = Field(default=None, min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    state_registration: str | None = Field(default=None, max_length=40)
    municipal_registration: str | None = Field(default=None, max_length=40)
    provider_connection_id: str | None = None
    status: Literal["active", "inactive", "archived"] | None = None
    metadata: dict[str, Any] | None = None
    expected_version: int = Field(ge=1)


class FiscalOperationScopeInput(FiscalContextModel):
    operation_type: str = Field(min_length=1, max_length=80)
    item_kind: Literal["any", "product", "service", "mixed"] = "any"
    recipient_scope: Literal["any", "individual", "company", "government", "foreign"] = "any"
    document_type: Literal["any", "NF-e", "NFC-e", "NFS-e"] = "any"

    @field_validator("operation_type")
    @classmethod
    def validate_operation_type(cls, value: str) -> str:
        return normalize_operation(value)


class FiscalContextVersionCreate(FiscalContextModel):
    tax_regime: Literal[
        "simples_nacional",
        "normal",
        "lucro_presumido",
        "lucro_real",
        "mei",
        "imune",
        "isenta",
        "public_entity",
        "other",
    ]
    uf: str = Field(min_length=2, max_length=2)
    municipality_code: str = Field(min_length=7, max_length=7)
    valid_from: date
    valid_until: date | None = None
    environment: Literal["homologation", "production"] = "homologation"
    rtc_mode: Literal["disabled", "simulation_only", "optional_emit", "required_emit"] = "simulation_only"
    layout_version: str | None = Field(default=None, max_length=80)
    schema_version: str | None = Field(default=None, max_length=80)
    technical_note_version: str | None = Field(default=None, max_length=80)
    ruleset_version: str | None = Field(default=None, max_length=120)
    configuration: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=10000)
    scopes: list[FiscalOperationScopeInput] = Field(min_length=1, max_length=100)
    expected_context_version: int = Field(ge=1)

    @field_validator("uf")
    @classmethod
    def validate_uf(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in UF_CODES:
            raise ValueError("UF inválida")
        return normalized

    @field_validator("municipality_code")
    @classmethod
    def validate_municipality(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) != 7:
            raise ValueError("Código do município deve possuir 7 dígitos")
        return digits

    @model_validator(mode="after")
    def validate_period_and_scopes(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode ser anterior a valid_from")
        keys = {
            (scope.operation_type, scope.item_kind, scope.recipient_scope, scope.document_type)
            for scope in self.scopes
        }
        if len(keys) != len(self.scopes):
            raise ValueError("Escopos fiscais duplicados na mesma versão")
        return self


class FiscalContextVersionPublish(FiscalContextModel):
    expected_context_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class FiscalContextResolveInput(FiscalContextModel):
    occurred_on: date = Field(default_factory=date.today)
    operation_type: str = Field(min_length=1, max_length=80)
    item_kind: Literal["product", "service", "mixed"]
    recipient_scope: Literal["individual", "company", "government", "foreign"] = "individual"
    document_type: Literal["NF-e", "NFC-e", "NFS-e"]
    context_id: str | None = None
    cnpj: str | None = Field(default=None, min_length=14, max_length=20)
    institution_id: str | None = None
    unit_id: str | None = None

    @field_validator("operation_type")
    @classmethod
    def validate_operation_type(cls, value: str) -> str:
        return normalize_operation(value)

    @field_validator("cnpj")
    @classmethod
    def validate_optional_cnpj(cls, value: str | None) -> str | None:
        return normalize_cnpj(value) if value else None

    @model_validator(mode="after")
    def validate_selector(self):
        if not any((self.context_id, self.cnpj, self.institution_id, self.unit_id)):
            raise ValueError("Informe context_id, CNPJ, instituição ou unidade para resolver o contexto fiscal")
        return self
