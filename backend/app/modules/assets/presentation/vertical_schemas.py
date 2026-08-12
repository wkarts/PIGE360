from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetLocationCreate(AssetModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=180)
    parent_id: str | None = None
    institution_id: str | None = None
    unit_id: str | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class AssetCreate(AssetModel):
    tag: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=255)
    location_id: str
    product_id: str | None = None
    receipt_item_id: str | None = None
    description: str | None = Field(default=None, max_length=10000)
    serial_number: str | None = Field(default=None, max_length=160)
    responsible_person_id: str | None = None
    acquisition_date: date
    acquisition_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    useful_life_months: int | None = Field(default=None, ge=1, le=1200)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    warranty_until: date | None = None
    metadata: dict = Field(default_factory=dict)
    institution_id: str | None = None
    unit_id: str | None = None

    @field_validator("tag")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_values(self):
        if self.residual_value > self.acquisition_cost:
            raise ValueError("O valor residual não pode superar o custo de aquisição")
        if self.warranty_until and self.warranty_until < self.acquisition_date:
            raise ValueError("A garantia não pode anteceder a aquisição")
        return self


class AssetTransfer(AssetModel):
    location_id: str
    responsible_person_id: str | None = None
    reason: str = Field(min_length=3, max_length=5000)


class AssetMaintenanceCreate(AssetModel):
    maintenance_type: str = Field(min_length=2, max_length=60)
    scheduled_on: date | None = None
    supplier_id: str | None = None
    estimated_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    description: str = Field(min_length=3, max_length=10000)


class AssetMaintenanceComplete(AssetModel):
    result_notes: str = Field(min_length=3, max_length=10000)
    actual_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)


class AssetLoanCreate(AssetModel):
    borrower_person_id: str
    expected_return_at: datetime | None = None
    condition_out: str | None = Field(default=None, max_length=5000)


class AssetLoanReturn(AssetModel):
    condition_in: str | None = Field(default=None, max_length=5000)


class DepreciationCalculate(AssetModel):
    competence: str = Field(pattern=r"^\d{4}-\d{2}$")
