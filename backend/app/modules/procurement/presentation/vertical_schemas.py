from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProcurementModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SupplierContactInput(ProcurementModel):
    name: str = Field(min_length=2, max_length=180)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    role: str | None = Field(default=None, max_length=100)
    primary: bool = False


class SupplierCreateUnified(ProcurementModel):
    # Campos legados permanecem aceitos.
    legal_name: str = Field(min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    cnpj: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    # Campos verticais.
    code: str | None = Field(default=None, min_length=2, max_length=80)
    rating: Decimal | None = Field(default=None, ge=0, le=5, max_digits=5, decimal_places=2)
    payment_terms: dict = Field(default_factory=dict)
    fiscal_profile: dict = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=10000)
    contacts: list[SupplierContactInput] = Field(default_factory=list, max_length=50)
    institution_id: str | None = None
    unit_id: str | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("cnpj")
    @classmethod
    def digits_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) != 14:
            raise ValueError("CNPJ deve possuir 14 dígitos")
        return digits


class SupplierPatch(ProcurementModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    status: Literal["active", "inactive", "blocked", "archived"] | None = None
    rating: Decimal | None = Field(default=None, ge=0, le=5, max_digits=5, decimal_places=2)
    payment_terms: dict | None = None
    fiscal_profile: dict | None = None
    notes: str | None = Field(default=None, max_length=10000)
    expected_version: int = Field(default=1, ge=1)


class ProductVariantCreate(ProcurementModel):
    product_id: str
    sku: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=180)
    attributes: dict = Field(default_factory=dict)
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()


class ProductBarcodeCreate(ProcurementModel):
    product_id: str
    variant_id: str | None = None
    barcode: str = Field(min_length=4, max_length=80)
    barcode_type: str = Field(default="ean13", min_length=2, max_length=40)
    primary: bool = False


class RequisitionItemInput(ProcurementModel):
    product_id: str
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    estimated_unit_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)


class RequisitionCreate(ProcurementModel):
    needed_by: date | None = None
    justification: str = Field(min_length=3, max_length=10000)
    department_id: str | None = None
    cost_center_id: str | None = None
    items: list[RequisitionItemInput] = Field(min_length=1, max_length=500)
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def unique_products(self):
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Não repita produtos na requisição")
        return self


class RequisitionApproval(ProcurementModel):
    approved_quantities: dict[str, Decimal] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=2000)


class ActionReason(ProcurementModel):
    reason: str = Field(min_length=3, max_length=2000)


class QuotationItemInput(ProcurementModel):
    product_id: str
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    specifications: dict = Field(default_factory=dict)


class QuotationCreate(ProcurementModel):
    requisition_id: str | None = None
    response_deadline: datetime | None = None
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    items: list[QuotationItemInput] = Field(default_factory=list, max_length=500)
    supplier_ids: list[str] = Field(min_length=1, max_length=100)
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def source_and_unique(self):
        if not self.requisition_id and not self.items:
            raise ValueError("Informe uma requisição ou os itens da cotação")
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Não repita produtos na cotação")
        if len(self.supplier_ids) != len(set(self.supplier_ids)):
            raise ValueError("Não repita fornecedores convidados")
        return self


class SupplierProposalItemInput(ProcurementModel):
    quotation_item_id: str
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    quantity_available: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    brand: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class SupplierProposalCreate(ProcurementModel):
    delivery_days: int | None = Field(default=None, ge=0, le=3650)
    payment_terms: dict = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=10000)
    items: list[SupplierProposalItemInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [item.quotation_item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Não repita itens da cotação")
        return self


class QuotationAward(ProcurementModel):
    supplier_id: str
    warehouse_id: str = Field(default="default", min_length=1, max_length=80)
    expected_on: date | None = None
    reason: str = Field(min_length=3, max_length=5000)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class PurchaseOrderItemInput(ProcurementModel):
    product_id: str
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class PurchaseOrderCreate(ProcurementModel):
    supplier_id: str
    warehouse_id: str = Field(default="default", min_length=1, max_length=80)
    requisition_id: str | None = None
    expected_on: date | None = None
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    notes: str | None = Field(default=None, max_length=10000)
    items: list[PurchaseOrderItemInput] = Field(min_length=1, max_length=500)
    institution_id: str | None = None
    unit_id: str | None = None


class ReceiptItemInput(ProcurementModel):
    purchase_order_item_id: str
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    lot_number: str | None = Field(default=None, max_length=100)
    manufactured_on: date | None = None
    expires_on: date | None = None

    @model_validator(mode="after")
    def date_order(self):
        if self.manufactured_on and self.expires_on and self.expires_on < self.manufactured_on:
            raise ValueError("Validade não pode anteceder a fabricação")
        return self


class GoodsReceiptCreate(ProcurementModel):
    supplier_document_number: str | None = Field(default=None, max_length=100)
    supplier_document_key: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=10000)
    items: list[ReceiptItemInput] = Field(min_length=1, max_length=500)


class ReturnItemInput(ProcurementModel):
    purchase_order_item_id: str
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    lot_id: str | None = None


class PurchaseReturnCreate(ProcurementModel):
    reason: str = Field(min_length=3, max_length=5000)
    items: list[ReturnItemInput] = Field(min_length=1, max_length=500)


class ReservationCreate(ProcurementModel):
    product_id: str
    warehouse_id: str = Field(default="default", min_length=1, max_length=80)
    lot_id: str | None = None
    source_type: str = Field(min_length=2, max_length=80)
    source_id: str
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    expires_at: datetime | None = None
    institution_id: str | None = None
    unit_id: str | None = None


class InventoryCountCreate(ProcurementModel):
    warehouse_id: str = Field(default="default", min_length=1, max_length=80)
    product_ids: list[str] = Field(default_factory=list, max_length=5000)
    include_zero_balance: bool = False
    institution_id: str | None = None
    unit_id: str | None = None


class InventoryCountLine(ProcurementModel):
    item_id: str
    counted_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    notes: str | None = Field(default=None, max_length=2000)


class InventoryCountComplete(ProcurementModel):
    reason: str = Field(min_length=3, max_length=5000)
    items: list[InventoryCountLine] = Field(min_length=1, max_length=5000)


class ReorderPolicyCreate(ProcurementModel):
    product_id: str
    warehouse_id: str = Field(default="default", min_length=1, max_length=80)
    minimum_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    target_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    lead_time_days: int = Field(default=0, ge=0, le=3650)
    preferred_supplier_id: str | None = None
    institution_id: str | None = None
    unit_id: str | None = None

    @model_validator(mode="after")
    def target_covers_minimum(self):
        if self.target_quantity < self.minimum_quantity:
            raise ValueError("Estoque alvo não pode ser inferior ao estoque mínimo")
        return self


class ReorderPolicyPatch(ProcurementModel):
    minimum_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    target_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    preferred_supplier_id: str | None = None
    state: Literal["active", "inactive"] | None = None
    institution_id: str | None = None
    unit_id: str | None = None
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def supplied_target_covers_minimum(self):
        if (
            self.minimum_quantity is not None
            and self.target_quantity is not None
            and self.target_quantity < self.minimum_quantity
        ):
            raise ValueError("Estoque alvo não pode ser inferior ao estoque mínimo")
        return self


class PurchaseSuggestionGenerate(ProcurementModel):
    warehouse_id: str | None = Field(default=None, min_length=1, max_length=80)
    product_ids: list[str] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def unique_products(self):
        if len(self.product_ids) != len(set(self.product_ids)):
            raise ValueError("Não repita produtos ao gerar sugestões")
        return self


class PurchaseSuggestionConvert(ProcurementModel):
    expected_version: int = Field(ge=1)
    needed_by: date | None = None
    department_id: str | None = None
    cost_center_id: str | None = None
    justification: str | None = Field(default=None, min_length=3, max_length=10000)


class PurchaseSuggestionDismiss(ProcurementModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=5000)
