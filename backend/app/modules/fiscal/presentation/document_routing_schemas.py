from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DocumentType = Literal["NF-e", "NFC-e", "NFS-e"]
RecipientScope = Literal["individual", "company", "government", "foreign"]
TriggerType = Literal["manual", "sale_completed", "service_order_confirmed", "competence", "payment", "billing", "nature", "contract"]


class RoutingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiscalDocumentSchemaCreate(RoutingModel):
    document_type: DocumentType
    schema_code: str = Field(min_length=2, max_length=120)
    version_label: str = Field(min_length=1, max_length=80)
    valid_from: date
    valid_until: date | None = None
    root_element: str = Field(min_length=1, max_length=120)
    namespace_uri: str | None = Field(default=None, max_length=500)
    xsd_text: str | None = Field(default=None, min_length=20)
    xsd_base64: str | None = None
    source_reference: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_input(self):
        if bool(self.xsd_text) == bool(self.xsd_base64):
            raise ValueError("Informe exatamente um entre xsd_text e xsd_base64")
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until anterior a valid_from")
        return self


class FiscalDocumentSchemaPublish(RoutingModel):
    reason: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)


class FiscalRoutingPolicyCreate(RoutingModel):
    fiscal_context_id: str
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    operation_type: str = Field(default="sale", min_length=1, max_length=80)
    recipient_scope: Literal["any", "individual", "company", "government", "foreign"] = "any"
    channel_scope: str = Field(default="any", min_length=1, max_length=80)
    product_document_type: Literal["NF-e", "NFC-e"] | None = None
    service_document_type: Literal["NFS-e"] = "NFS-e"
    trigger_types: list[TriggerType] = Field(default_factory=lambda: ["manual"], min_length=1, max_length=20)
    valid_from: date
    valid_until: date | None = None
    priority: int = Field(default=100, ge=0, le=10000)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "-")

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until anterior a valid_from")
        return self


class FiscalRoutingPolicyPublish(RoutingModel):
    reason: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)


class FiscalRoutingRecipient(RoutingModel):
    name: str | None = Field(default=None, max_length=255)
    document: str | None = Field(default=None, max_length=30)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    municipality_code: str | None = Field(default=None, max_length=10)
    email: str | None = Field(default=None, max_length=255)


class FiscalAssemblyItem(RoutingModel):
    line_id: str = Field(min_length=1, max_length=120)
    item_kind: Literal["product", "service"]
    item_id: str | None = None
    code: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    total_amount: Decimal = Field(ge=0)
    classification: dict[str, Any] = Field(default_factory=dict)


class FiscalDocumentAssemblyCreate(RoutingModel):
    fiscal_context_id: str
    fiscal_profile_id: str
    source_type: Literal["sale", "service_order", "manual"]
    source_id: str = Field(min_length=1, max_length=255)
    occurred_on: date = Field(default_factory=date.today)
    operation_type: str = Field(default="sale", min_length=1, max_length=80)
    recipient_scope: RecipientScope = "individual"
    channel: str = Field(default="web", min_length=1, max_length=80)
    destination_uf: str | None = Field(default=None, min_length=2, max_length=2)
    trigger_type: TriggerType = "manual"
    recipient: FiscalRoutingRecipient = Field(default_factory=FiscalRoutingRecipient)
    items: list[FiscalAssemblyItem] = Field(default_factory=list, max_length=10000)
    request_emission: bool = False
    contingency_mode: Literal["offline", "svc", "ecpec"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("destination_uf")
    @classmethod
    def uf(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class FiscalEmissionTriggerEvaluate(RoutingModel):
    event_type: Literal["SaleCompleted", "ServiceOrderConfirmed", "ServiceCompetenceBilled", "PaymentConfirmed", "ChargeCreated"]
    aggregate_id: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
