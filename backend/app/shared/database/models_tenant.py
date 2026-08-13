from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.shared.database.base import Base, TenantEntityMixin
from backend.app.shared.domain.dates import utcnow
from backend.app.shared.domain.ids import new_id

MONEY = Numeric(18, 2)
QUANTITY = Numeric(18, 4)
RATE = Numeric(18, 6)


# Fundação, identidade e trilha -------------------------------------------------


class Institution(TenantEntityMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_institution_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class Unit(TenantEntityMixin, Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("tenant_id", "institution_id", "code", name="uq_unit_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class Person(TenantEntityMixin, Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("tenant_id", "cpf", name="uq_person_cpf"),)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    social_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cpf: Mapped[str | None] = mapped_column(String(11), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class TenantUser(TenantEntityMixin, Base):
    __tablename__ = "tenant_users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_tenant_user_email"),)

    person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    permissions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    roles_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(TenantEntityMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("tenant_id", "token_hash", name="uq_refresh_token_hash"),)

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(180), nullable=True)


class IdempotencyRecord(TenantEntityMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("tenant_id", "scope", "key", name="uq_idempotency_scope_key"),)

    scope: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(TenantEntityMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    action: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    before_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class OutboxEvent(TenantEntityMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", name="uq_outbox_event_id"),)

    event_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_id)
    event_type: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


# Estoque ----------------------------------------------------------------------


class Warehouse(TenantEntityMixin, Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_warehouse_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class Product(TenantEntityMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_product_sku"),
        UniqueConstraint("tenant_id", "barcode", name="uq_product_barcode"),
    )

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="product")
    sale_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    cost_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    stock_controlled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fiscal_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class ProductVariant(TenantEntityMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_product_variant_sku"),)

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sale_price: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class ProductBarcode(TenantEntityMixin, Base):
    __tablename__ = "product_barcodes"
    __table_args__ = (UniqueConstraint("tenant_id", "barcode", name="uq_product_barcode_secondary"),)

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    barcode: Mapped[str] = mapped_column(String(80), nullable=False)
    barcode_type: Mapped[str] = mapped_column(String(40), nullable=False, default="ean13")
    primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StockBalance(TenantEntityMixin, Base):
    __tablename__ = "stock_balances"
    __table_args__ = (UniqueConstraint("tenant_id", "product_id", "warehouse_id", name="uq_stock_balance"),)

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    average_cost: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))


class StockMovement(TenantEntityMixin, Base):
    __tablename__ = "stock_movements"

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lot_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    movement_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    balance_after: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    reference_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


# Compras ----------------------------------------------------------------------


class Supplier(TenantEntityMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_supplier_code"),
        UniqueConstraint("tenant_id", "cnpj", name="uq_supplier_cnpj"),
    )

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    rating: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    payment_terms_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fiscal_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupplierContact(TenantEntityMixin, Base):
    __tablename__ = "supplier_contacts"

    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PurchaseRequisition(TenantEntityMixin, Base):
    __tablename__ = "purchase_requisitions"
    __table_args__ = (UniqueConstraint("tenant_id", "requisition_number", name="uq_requisition_number"),)

    requisition_number: Mapped[str] = mapped_column(String(80), nullable=False)
    requester_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PurchaseRequisitionItem(TenantEntityMixin, Base):
    __tablename__ = "purchase_requisition_items"

    requisition_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    approved_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    estimated_unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RequestForQuotation(TenantEntityMixin, Base):
    __tablename__ = "requests_for_quotation"
    __table_args__ = (UniqueConstraint("tenant_id", "quotation_number", name="uq_quotation_number"),)

    quotation_number: Mapped[str] = mapped_column(String(80), nullable=False)
    requisition_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    response_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    selected_supplier_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class QuotationItem(TenantEntityMixin, Base):
    __tablename__ = "quotation_items"

    quotation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    specifications_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class QuotationSupplier(TenantEntityMixin, Base):
    __tablename__ = "quotation_suppliers"
    __table_args__ = (UniqueConstraint("tenant_id", "quotation_id", "supplier_id", name="uq_quotation_supplier"),)

    quotation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="invited")
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_terms_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))


class QuotationSupplierItem(TenantEntityMixin, Base):
    __tablename__ = "quotation_supplier_items"
    __table_args__ = (UniqueConstraint("tenant_id", "quotation_supplier_id", "quotation_item_id", name="uq_quotation_supplier_item"),)

    quotation_supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quotation_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    quantity_available: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PurchaseOrder(TenantEntityMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "order_number", name="uq_purchase_order_number"),)

    order_number: Mapped[str] = mapped_column(String(80), nullable=False)
    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quotation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    requisition_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    freight_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    expected_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PurchaseOrderItem(TenantEntityMixin, Base):
    __tablename__ = "purchase_order_items"

    purchase_order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ordered_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    returned_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fiscal_profile_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class GoodsReceipt(TenantEntityMixin, Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "receipt_number", name="uq_goods_receipt_number"),)

    receipt_number: Mapped[str] = mapped_column(String(80), nullable=False)
    purchase_order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="confirmed")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    received_by: Mapped[str] = mapped_column(String(36), nullable=False)
    supplier_document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_document_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class GoodsReceiptItem(TenantEntityMixin, Base):
    __tablename__ = "goods_receipt_items"

    goods_receipt_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    purchase_order_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    lot_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    stock_movement_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class InventoryLot(TenantEntityMixin, Base):
    __tablename__ = "inventory_lots"
    __table_args__ = (UniqueConstraint("tenant_id", "product_id", "warehouse_id", "lot_number", name="uq_inventory_lot"),)

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    manufactured_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    reserved_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    unit_cost: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    receipt_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class PurchaseReturn(TenantEntityMixin, Base):
    __tablename__ = "purchase_returns"
    __table_args__ = (UniqueConstraint("tenant_id", "return_number", name="uq_purchase_return_number"),)

    return_number: Mapped[str] = mapped_column(String(80), nullable=False)
    purchase_order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="confirmed")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    returned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    returned_by: Mapped[str] = mapped_column(String(36), nullable=False)


class PurchaseReturnItem(TenantEntityMixin, Base):
    __tablename__ = "purchase_return_items"

    purchase_return_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    purchase_order_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    stock_movement_id: Mapped[str] = mapped_column(String(36), nullable=False)


class StockReservation(TenantEntityMixin, Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_stock_reservation_idempotency"),)

    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lot_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InventoryCount(TenantEntityMixin, Base):
    __tablename__ = "inventory_counts"
    __table_args__ = (UniqueConstraint("tenant_id", "count_number", name="uq_inventory_count_number"),)

    count_number: Mapped[str] = mapped_column(String(80), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="counting", index=True)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class InventoryCountItem(TenantEntityMixin, Base):
    __tablename__ = "inventory_count_items"
    __table_args__ = (UniqueConstraint("tenant_id", "inventory_count_id", "product_id", "lot_id", name="uq_inventory_count_item"),)

    inventory_count_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expected_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    counted_quantity: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    difference_quantity: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# Patrimônio -------------------------------------------------------------------


class AssetLocation(TenantEntityMixin, Base):
    __tablename__ = "asset_locations"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_asset_location_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class Asset(TenantEntityMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "asset_number", name="uq_asset_number"),
        UniqueConstraint("tenant_id", "tag", name="uq_asset_tag"),
    )

    asset_number: Mapped[str] = mapped_column(String(100), nullable=False)
    tag: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    receipt_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    location_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    responsible_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    acquisition_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    useful_life_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    accumulated_depreciation: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    warranty_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AssetMovement(TenantEntityMixin, Base):
    __tablename__ = "asset_movements"

    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    from_location_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    to_location_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_responsible_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    to_responsible_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class AssetMaintenance(TenantEntityMixin, Base):
    __tablename__ = "asset_maintenances"

    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    maintenance_type: Mapped[str] = mapped_column(String(60), nullable=False)
    scheduled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="scheduled", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetLoan(TenantEntityMixin, Base):
    __tablename__ = "asset_loans"

    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    borrower_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    loaned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    expected_return_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    condition_out: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_in: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_by: Mapped[str] = mapped_column(String(36), nullable=False)


class AssetDepreciation(TenantEntityMixin, Base):
    __tablename__ = "asset_depreciations"
    __table_args__ = (UniqueConstraint("tenant_id", "asset_id", "competence", name="uq_asset_depreciation_competence"),)

    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competence: Mapped[str] = mapped_column(String(7), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False, default="straight_line")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    accumulated_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    book_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    calculated_by: Mapped[str] = mapped_column(String(36), nullable=False)


# Financeiro -------------------------------------------------------------------


class CostCenter(TenantEntityMixin, Base):
    __tablename__ = "cost_centers"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_cost_center_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class FinancialContract(TenantEntityMixin, Base):
    __tablename__ = "financial_contracts"
    __table_args__ = (UniqueConstraint("tenant_id", "contract_number", name="uq_financial_contract_number"),)

    contract_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    enrollment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    responsible_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    recognized_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generation_policy: Mapped[str] = mapped_column(String(60), nullable=False, default="generate_on_approval")
    terms_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class FinancialContractVersion(TenantEntityMixin, Base):
    __tablename__ = "financial_contract_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "contract_id", "contract_version", name="uq_financial_contract_version"),)

    contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)


class FinancialPlan(TenantEntityMixin, Base):
    __tablename__ = "financial_plans"
    __table_args__ = (UniqueConstraint("tenant_id", "plan_number", name="uq_financial_plan_number"),)

    plan_number: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_months: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    billing_rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Charge(TenantEntityMixin, Base):
    __tablename__ = "charges"
    __table_args__ = (UniqueConstraint("tenant_id", "charge_number", name="uq_charge_number"),)

    charge_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    financial_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    enrollment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    responsible_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    origin_type: Mapped[str] = mapped_column(String(100), nullable=False, default="financial_contract")
    origin_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    refunded_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    outstanding_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChargeItem(TenantEntityMixin, Base):
    __tablename__ = "charge_items"

    charge_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("1.0000"))
    unit_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    accounting_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Installment(TenantEntityMixin, Base):
    __tablename__ = "installments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "installment_number", name="uq_installment_number"),
        UniqueConstraint("tenant_id", "charge_id", "sequence", name="uq_charge_installment_sequence"),
    )

    installment_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    charge_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    refunded_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    outstanding_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    penalty_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    interest_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Discount(TenantEntityMixin, Base):
    __tablename__ = "discounts"

    contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    charge_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    installment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    discount_type: Mapped[str] = mapped_column(String(40), nullable=False, default="fixed")
    value: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    applied_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class Scholarship(TenantEntityMixin, Base):
    __tablename__ = "scholarships"

    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enrollment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scholarship_type: Mapped[str] = mapped_column(String(60), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    fixed_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class Penalty(TenantEntityMixin, Base):
    __tablename__ = "penalties"

    installment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    penalty_type: Mapped[str] = mapped_column(String(60), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    rule_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class Payment(TenantEntityMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payment_number", name="uq_payment_number"),
        UniqueConstraint("tenant_id", "external_reference", name="uq_payment_external_reference"),
    )

    payment_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payer_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="incoming")
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    refunded_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    external_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class PaymentAllocation(TenantEntityMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (UniqueConstraint("tenant_id", "payment_id", "installment_id", name="uq_payment_installment_allocation"),)

    payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    installment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Refund(TenantEntityMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (UniqueConstraint("tenant_id", "refund_number", name="uq_refund_number"),)

    refund_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="processed", index=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_by: Mapped[str] = mapped_column(String(36), nullable=False)


class RefundAllocation(TenantEntityMixin, Base):
    __tablename__ = "refund_allocations"

    refund_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_allocation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class AccountReceivable(TenantEntityMixin, Base):
    __tablename__ = "accounts_receivable"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receivable_number", name="uq_receivable_number"),
        UniqueConstraint("tenant_id", "installment_id", name="uq_receivable_installment"),
    )

    receivable_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    installment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    responsible_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    refunded_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    outstanding_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)


class AccountPayable(TenantEntityMixin, Base):
    __tablename__ = "accounts_payable"
    __table_args__ = (UniqueConstraint("tenant_id", "payable_number", name="uq_payable_number"),)

    payable_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    outstanding_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayablePayment(TenantEntityMixin, Base):
    __tablename__ = "payable_payments"
    __table_args__ = (UniqueConstraint("tenant_id", "payment_id", "payable_id", name="uq_payment_payable_allocation"),)

    payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payable_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class LedgerBatch(TenantEntityMixin, Base):
    __tablename__ = "ledger_batches"
    __table_args__ = (UniqueConstraint("tenant_id", "batch_number", name="uq_ledger_batch_number"),)

    batch_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    reference_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    total_debit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    reversed_by_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LedgerEntry(TenantEntityMixin, Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "entry_number", name="uq_ledger_entry_number"),)

    entry_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    account_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entry_side: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    reference_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    reversal_of_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)



# Serviços ---------------------------------------------------------------------


class ServiceCatalog(TenantEntityMixin, Base):
    __tablename__ = "service_catalogs"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_service_catalog_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class Service(TenantEntityMixin, Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("tenant_id", "catalog_id", "code", name="uq_service_catalog_code_item"),)

    catalog_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    recurrence_type: Mapped[str] = mapped_column(String(40), nullable=False, default="one_time")
    unit_of_measure: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")
    default_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ServiceVariant(TenantEntityMixin, Base):
    __tablename__ = "service_variants"
    __table_args__ = (UniqueConstraint("tenant_id", "service_id", "code", name="uq_service_variant_code"),)

    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ServiceFiscalProfile(TenantEntityMixin, Base):
    __tablename__ = "service_fiscal_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_id", "variant_id", "valid_from", name="uq_service_fiscal_profile_validity"),
    )

    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    nbs_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    lc116_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    municipal_service_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cnae_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    iss_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0.000000"))
    ibs_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0.000000"))
    cbs_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0.000000"))
    cclass_trib: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    fiscal_trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="billing")
    withholding_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rules_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ServicePriceTable(TenantEntityMixin, Base):
    __tablename__ = "service_price_tables"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_id", "variant_id", "valid_from", name="uq_service_price_validity"),
    )

    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    billing_frequency: Mapped[str] = mapped_column(String(40), nullable=False, default="one_time")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class ServiceBillingRule(TenantEntityMixin, Base):
    __tablename__ = "service_billing_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "service_id", "code", name="uq_service_billing_rule_code"),)

    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    billing_trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="competence")
    due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interval_months: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recognition_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="competence")
    fiscal_trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="competence")
    proration_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="none")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ServiceSubscription(TenantEntityMixin, Base):
    __tablename__ = "service_subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", "subscription_number", name="uq_service_subscription_number"),)

    subscription_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    subscriber_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enrollment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    financial_contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    billing_rule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("1.0000"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    cycle_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    next_competence_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ServiceOrder(TenantEntityMixin, Base):
    __tablename__ = "service_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "order_number", name="uq_service_order_number"),)

    order_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subscriber_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    enrollment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    financial_contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    competence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    charge_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    fiscal_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ServiceOrderItem(TenantEntityMixin, Base):
    __tablename__ = "service_order_items"

    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    competence_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    competence_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    fiscal_profile_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    executed_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))


class ServiceExecution(TenantEntityMixin, Base):
    __tablename__ = "service_executions"
    __table_args__ = (UniqueConstraint("tenant_id", "execution_number", name="uq_service_execution_number"),)

    execution_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    order_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="scheduled", index=True)
    performer_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ServiceCompetence(TenantEntityMixin, Base):
    __tablename__ = "service_competencies"
    __table_args__ = (UniqueConstraint("tenant_id", "subscription_id", "competence_key", name="uq_service_subscription_competence"),)

    subscription_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competence_key: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    charge_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    billed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceFiscalEvent(TenantEntityMixin, Base):
    __tablename__ = "service_fiscal_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_key", name="uq_service_fiscal_event_key"),)

    event_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    order_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    competence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, default="nfse")
    provider_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fiscal_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    fiscal_assembly_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured", index=True)
    payload_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ServiceReceipt(TenantEntityMixin, Base):
    __tablename__ = "service_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "receipt_number", name="uq_service_receipt_number"),)

    receipt_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    service_order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    charge_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(60), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_document: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="issued", index=True)
    document_storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    issued_by: Mapped[str] = mapped_column(String(36), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# Vendas, PDV e cantina --------------------------------------------------------


class Canteen(TenantEntityMixin, Base):
    __tablename__ = "canteens"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_canteen_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CanteenMenu(TenantEntityMixin, Base):
    __tablename__ = "canteen_menus"
    __table_args__ = (UniqueConstraint("tenant_id", "canteen_id", "code", name="uq_canteen_menu_code"),)

    canteen_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    availability_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CanteenMenuItem(TenantEntityMixin, Base):
    __tablename__ = "canteen_menu_items"
    __table_args__ = (UniqueConstraint("tenant_id", "menu_id", "product_id", name="uq_canteen_menu_product"),)

    menu_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    price_override: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    availability_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CanteenRecipe(TenantEntityMixin, Base):
    __tablename__ = "canteen_recipes"
    __table_args__ = (UniqueConstraint("tenant_id", "product_id", name="uq_canteen_recipe_product"),)

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    yield_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("1.0000"))
    allergens_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    nutrition_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class CanteenRecipeIngredient(TenantEntityMixin, Base):
    __tablename__ = "canteen_recipe_ingredients"
    __table_args__ = (UniqueConstraint("tenant_id", "recipe_id", "ingredient_product_id", name="uq_recipe_ingredient"),)

    recipe_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ingredient_product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(40), nullable=False, default="unit")


class StudentWallet(TenantEntityMixin, Base):
    __tablename__ = "student_wallets"
    __table_args__ = (UniqueConstraint("tenant_id", "student_id", "currency", name="uq_student_wallet_currency"),)

    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    last_transaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WalletTransaction(TenantEntityMixin, Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (UniqueConstraint("tenant_id", "transaction_number", name="uq_wallet_transaction_number"),)

    transaction_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(60), nullable=True)
    finance_payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    reference_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CanteenStudentPolicy(TenantEntityMixin, Base):
    __tablename__ = "canteen_student_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "canteen_id", "student_id", name="uq_canteen_student_policy"),)

    canteen_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    daily_limit: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    weekly_limit: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    blocked_product_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blocked_categories_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blocked_allergens_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allowed_time_windows_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requires_guardian_authorization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class CanteenPurchaseAuthorization(TenantEntityMixin, Base):
    __tablename__ = "canteen_purchase_authorizations"
    __table_args__ = (UniqueConstraint("tenant_id", "authorization_number", name="uq_canteen_authorization_number"),)

    authorization_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    canteen_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    granted_by_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    maximum_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    allowed_product_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    used_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))


class PosTerminal(TenantEntityMixin, Base):
    __tablename__ = "pos_terminals"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_pos_terminal_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    canteen_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    allow_offline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class CashRegisterSession(TenantEntityMixin, Base):
    __tablename__ = "cash_register_sessions"
    __table_args__ = (UniqueConstraint("tenant_id", "session_number", name="uq_cash_register_session_number"),)

    session_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    terminal_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operator_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    opening_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    expected_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    declared_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    variance_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    closing_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CashMovement(TenantEntityMixin, Base):
    __tablename__ = "cash_movements"
    __table_args__ = (UniqueConstraint("tenant_id", "movement_number", name="uq_cash_movement_number"),)

    movement_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    cash_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(60), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)


class Sale(TenantEntityMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sale_number", name="uq_sale_number"),
        UniqueConstraint("tenant_id", "offline_sync_id", name="uq_sale_offline_sync"),
    )

    sale_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, default="pos", index=True)
    terminal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cash_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    canteen_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    student_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    responsible_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    paid_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    change_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    charge_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    fiscal_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_requested", index=True)
    offline_origin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    offline_sync_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SaleItem(TenantEntityMixin, Base):
    __tablename__ = "sale_items"

    sale_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    returned_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    product_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fiscal_profile_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stock_consumption_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class SalePayment(TenantEntityMixin, Base):
    __tablename__ = "sale_payments"
    __table_args__ = (UniqueConstraint("tenant_id", "sale_id", "payment_sequence", name="uq_sale_payment_sequence"),)

    sale_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tendered_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    change_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    finance_payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    wallet_transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    external_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="confirmed", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SaleReturn(TenantEntityMixin, Base):
    __tablename__ = "sale_returns"
    __table_args__ = (UniqueConstraint("tenant_id", "return_number", name="uq_sale_return_number"),)

    return_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sale_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="processing", index=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fiscal_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured", index=True)


class SaleReturnItem(TenantEntityMixin, Base):
    __tablename__ = "sale_return_items"

    sale_return_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sale_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    stock_restoration_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class SaleReturnPayment(TenantEntityMixin, Base):
    __tablename__ = "sale_return_payments"

    sale_return_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sale_payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="pending", index=True)
    finance_refund_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    wallet_transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    external_confirmation_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FiscalDocumentRequest(TenantEntityMixin, Base):
    __tablename__ = "fiscal_document_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "origin_type", "origin_id", "request_kind", name="uq_fiscal_origin_request"),)

    origin_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    origin_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    request_kind: Mapped[str] = mapped_column(String(60), nullable=False, default="issue")
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured", index=True)
    payload_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Bancário ---------------------------------------------------------------------


class BankProviderConfiguration(TenantEntityMixin, Base):
    __tablename__ = "bank_provider_configurations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_code", "environment", name="uq_bank_provider_environment"),)

    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="homologation")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_configured", index=True)
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    webhook_tolerance_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_health_status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_configured")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BankAccount(TenantEntityMixin, Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "account_code", name="uq_bank_account_code"),)

    account_code: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    bank_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_number_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False, default="checking")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    pix_key_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pix_key_masked: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class BankPaymentRequest(TenantEntityMixin, Base):
    __tablename__ = "bank_payment_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_number", name="uq_bank_payment_request_number"),
        UniqueConstraint("tenant_id", "provider_reference", name="uq_bank_provider_reference"),
    )

    request_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_configuration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    bank_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    charge_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    installment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="not_configured", index=True)
    pix_copy_paste: Mapped[str | None] = mapped_column(Text, nullable=True)
    boleto_digit_line: Mapped[str | None] = mapped_column(String(120), nullable=True)
    boleto_barcode: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class BankProviderAttempt(TenantEntityMixin, Base):
    __tablename__ = "bank_provider_attempts"

    provider_configuration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_masked_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BankWebhookInbox(TenantEntityMixin, Base):
    __tablename__ = "bank_webhook_inbox"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_code", "event_id", name="uq_bank_webhook_event"),)

    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_masked_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="received", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BankStatementImport(TenantEntityMixin, Base):
    __tablename__ = "bank_statement_imports"
    __table_args__ = (UniqueConstraint("tenant_id", "content_hash", name="uq_bank_statement_hash"),)

    bank_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="ofx")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="processed", index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    imported_by: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BankStatementEntry(TenantEntityMixin, Base):
    __tablename__ = "bank_statement_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "statement_import_id", "provider_entry_id", name="uq_bank_statement_entry"),)

    statement_import_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    bank_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider_entry_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    posted_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    memo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="unreconciled", index=True)
    payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class BankReconciliation(TenantEntityMixin, Base):
    __tablename__ = "bank_reconciliations"
    __table_args__ = (UniqueConstraint("tenant_id", "reconciliation_number", name="uq_bank_reconciliation_number"),)

    reconciliation_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    bank_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    difference_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class BankReconciliationItem(TenantEntityMixin, Base):
    __tablename__ = "bank_reconciliation_items"
    __table_args__ = (UniqueConstraint("tenant_id", "reconciliation_id", "statement_entry_id", name="uq_bank_reconciliation_item"),)

    reconciliation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    statement_entry_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    match_method: Mapped[str] = mapped_column(String(40), nullable=False, default="unmatched")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    difference_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="unmatched", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BankFileExchange(TenantEntityMixin, Base):
    __tablename__ = "bank_file_exchanges"
    __table_args__ = (UniqueConstraint("tenant_id", "content_hash", name="uq_bank_file_exchange_hash"),)

    bank_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider_configuration_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    file_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    layout_version: Mapped[str] = mapped_column(String(40), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="generated_for_review", index=True)
    provider_validation_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Núcleo educacional ------------------------------------------------------------


class Student(TenantEntityMixin, Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("tenant_id", "person_id", name="uq_student_person"),
        UniqueConstraint("tenant_id", "registration_number", name="uq_student_registration"),
    )

    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    registration_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    accessibility_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class StudentGuardian(TenantEntityMixin, Base):
    __tablename__ = "student_guardians"
    __table_args__ = (UniqueConstraint("tenant_id", "student_id", "person_id", "relationship", name="uq_student_guardian_relation"),)

    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    relationship: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_responsible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    financial_responsible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pickup_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class AcademicProgram(TenantEntityMixin, Base):
    __tablename__ = "academic_programs"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_academic_program_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    education_level: Mapped[str] = mapped_column(String(80), nullable=False)
    modality: Mapped[str] = mapped_column(String(80), nullable=False, default="presential")
    workload_hours: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class Curriculum(TenantEntityMixin, Base):
    __tablename__ = "curricula"
    __table_args__ = (UniqueConstraint("tenant_id", "program_id", "code", "curriculum_version", name="uq_curriculum_version"),)

    program_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    curriculum_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)


class AcademicComponent(TenantEntityMixin, Base):
    __tablename__ = "academic_components"
    __table_args__ = (UniqueConstraint("tenant_id", "curriculum_id", "code", name="uq_academic_component_code"),)

    curriculum_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    workload_hours: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    credits: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    syllabus_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AcademicPeriod(TenantEntityMixin, Base):
    __tablename__ = "academic_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_academic_period_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(40), nullable=False, default="annual")
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClassGroup(TenantEntityMixin, Base):
    __tablename__ = "class_groups"
    __table_args__ = (UniqueConstraint("tenant_id", "academic_period_id", "code", name="uq_class_group_code"),)

    program_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    curriculum_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    academic_period_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    shift: Mapped[str] = mapped_column(String(40), nullable=False, default="morning")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    room: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class TeacherAssignment(TenantEntityMixin, Base):
    __tablename__ = "teacher_assignments"
    __table_args__ = (UniqueConstraint("tenant_id", "class_group_id", "component_id", "teacher_person_id", "valid_from", name="uq_teacher_assignment"),)

    class_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    teacher_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_teacher: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class Enrollment(TenantEntityMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "enrollment_number", name="uq_enrollment_number"),
        UniqueConstraint("tenant_id", "student_id", "academic_period_id", "class_group_id", name="uq_student_period_class_enrollment"),
    )

    enrollment_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    program_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    curriculum_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    academic_period_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    class_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    financial_responsible_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    enrolled_on: Mapped[date] = mapped_column(Date, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class EnrollmentStatusHistory(TenantEntityMixin, Base):
    __tablename__ = "enrollment_status_history"

    enrollment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TeachingPlan(TenantEntityMixin, Base):
    __tablename__ = "teaching_plans"

    class_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    teacher_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(60), nullable=False, default="annual")
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class TeachingPlanVersion(TenantEntityMixin, Base):
    __tablename__ = "teaching_plan_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "teaching_plan_id", "plan_version", name="uq_teaching_plan_version"),)

    teaching_plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    objectives_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    curriculum_links_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    skills_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    competencies_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    methodologies_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resources_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    assessments_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    accommodations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TeachingPlanApproval(TenantEntityMixin, Base):
    __tablename__ = "teaching_plan_approvals"

    teaching_plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class LessonPlan(TenantEntityMixin, Base):
    __tablename__ = "lesson_plans"

    teaching_plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    teaching_plan_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    class_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    teacher_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rescheduled_from_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="scheduled", index=True)
    planned_content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    executed_content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    execution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reschedule_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonPlanExecution(TenantEntityMixin, Base):
    __tablename__ = "lesson_plan_executions"

    lesson_plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    execution_status: Mapped[str] = mapped_column(String(40), nullable=False)
    executed_content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    additional_content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pending_content_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AttendancePolicy(TenantEntityMixin, Base):
    __tablename__ = "attendance_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "code", "policy_version", name="uq_attendance_policy_version"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    minimum_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("75.00"))
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)


class ClassSession(TenantEntityMixin, Base):
    __tablename__ = "class_sessions"

    lesson_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    rescheduled_from_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    class_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    component_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    expected_teacher_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actual_teacher_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    attendance_policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="scheduled", index=True)
    room: Mapped[str | None] = mapped_column(String(120), nullable=True)
    modality: Mapped[str] = mapped_column(String(40), nullable=False, default="presential")
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reschedule_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AttendanceCall(TenantEntityMixin, Base):
    __tablename__ = "attendance_calls"
    __table_args__ = (UniqueConstraint("tenant_id", "class_session_id", "call_version", name="uq_attendance_call_version"),)

    class_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    call_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="list")
    offline_origin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    offline_batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AttendanceRecord(TenantEntityMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("tenant_id", "attendance_call_id", "student_id", name="uq_attendance_record_student"),)

    attendance_call_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enrollment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    attendance_status: Mapped[str] = mapped_column(String(60), nullable=False, default="attendance_pending", index=True)
    presence_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    early_departure_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    recorded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AttendanceJustification(TenantEntityMixin, Base):
    __tablename__ = "attendance_justifications"

    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    attendance_record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="submitted", index=True)
    submitted_by_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    effect_status: Mapped[str | None] = mapped_column(String(60), nullable=True)


class AttendanceCorrection(TenantEntityMixin, Base):
    __tablename__ = "attendance_corrections"

    attendance_record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(60), nullable=False)
    to_status: Mapped[str] = mapped_column(String(60), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="applied")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttendanceRiskIndicator(TenantEntityMixin, Base):
    __tablename__ = "attendance_risk_indicators"
    __table_args__ = (UniqueConstraint("tenant_id", "student_id", "academic_period_id", "component_id", name="uq_attendance_risk_scope"),)

    student_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    academic_period_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    component_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    presence_equivalent: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    absence_equivalent: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0.0000"))
    percentage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("100.00"))
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False, default="none", index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


# Fiscal -----------------------------------------------------------------------


class FiscalEstablishment(TenantEntityMixin, Base):
    __tablename__ = "fiscal_establishments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cnpj", name="uq_fiscal_establishment_cnpj"),
        UniqueConstraint("tenant_id", "code", name="uq_fiscal_establishment_code"),
    )

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    state_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    municipal_registration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tax_regime: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    municipality_code: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    address_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fiscal_environment: Mapped[str] = mapped_column(String(40), nullable=False, default="homologation", index=True)
    rtc_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="simulation_only")
    default_nfe_provider_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    default_nfce_provider_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    default_nfse_provider_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FiscalProviderConfiguration(TenantEntityMixin, Base):
    __tablename__ = "fiscal_provider_configurations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_code", "document_type", "environment", name="uq_fiscal_provider_document_environment"),
    )

    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="homologation", index=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certificate_metadata_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured", index=True)
    last_health_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured")
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_tolerance_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)


class FiscalCertificateMetadata(TenantEntityMixin, Base):
    __tablename__ = "fiscal_certificate_metadata"
    __table_args__ = (UniqueConstraint("tenant_id", "fingerprint_sha256", name="uq_fiscal_certificate_fingerprint"),)

    certificate_type: Mapped[str] = mapped_column(String(40), nullable=False, default="a1")
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_document: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    serial_number: Mapped[str] = mapped_column(String(180), nullable=False)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FiscalCatalogSnapshot(TenantEntityMixin, Base):
    __tablename__ = "fiscal_catalog_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "catalog_type", "scope_code", "version_code", name="uq_fiscal_catalog_snapshot_version"),
    )

    catalog_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    scope_code: Mapped[str] = mapped_column(String(40), nullable=False, default="BR", index=True)
    version_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="validating", index=True)
    validation_errors_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    imported_by: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FiscalCatalogEntry(TenantEntityMixin, Base):
    __tablename__ = "fiscal_catalog_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "snapshot_id", "code", name="uq_fiscal_catalog_entry_code"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FiscalRuleSet(TenantEntityMixin, Base):
    __tablename__ = "fiscal_rule_sets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version_number", name="uq_fiscal_rule_set_version"),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tax_regime: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    municipality_code: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rules_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class ProductFiscalProfile(TenantEntityMixin, Base):
    __tablename__ = "product_fiscal_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", "variant_id", "valid_from", name="uq_product_fiscal_profile_validity"),
    )

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    ncm_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cest_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    origin_code: Mapped[str] = mapped_column(String(4), nullable=False, default="0")
    cst_icms: Mapped[str | None] = mapped_column(String(4), nullable=True)
    csosn: Mapped[str | None] = mapped_column(String(4), nullable=True)
    cfop_internal: Mapped[str] = mapped_column(String(8), nullable=False)
    cfop_interstate: Mapped[str] = mapped_column(String(8), nullable=False)
    cst_pis: Mapped[str | None] = mapped_column(String(4), nullable=True)
    cst_cofins: Mapped[str | None] = mapped_column(String(4), nullable=True)
    cst_ibs_cbs: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    cclass_trib: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    cbenef: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fiscal_unit: Mapped[str] = mapped_column(String(12), nullable=False, default="UN")
    rates_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rules_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FiscalNumberSequence(TenantEntityMixin, Base):
    __tablename__ = "fiscal_number_sequences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "establishment_id", "document_type", "environment", "series", name="uq_fiscal_number_sequence"),
    )

    establishment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(20), nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class FiscalDocument(TenantEntityMixin, Base):
    __tablename__ = "fiscal_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "establishment_id", "document_type", "environment", "series", "document_number", name="uq_fiscal_document_number"),
        UniqueConstraint("tenant_id", "access_key", name="uq_fiscal_document_access_key"),
    )

    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    establishment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    origin_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    origin_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model_code: Mapped[str] = mapped_column(String(8), nullable=False)
    series: Mapped[str] = mapped_column(String(20), nullable=False)
    document_number: Mapped[int] = mapped_column(Integer, nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider_configuration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="queued", index=True)
    official_authorization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    protocol_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0.00"))
    tax_totals_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rule_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FiscalDocumentArtifact(TenantEntityMixin, Base):
    __tablename__ = "fiscal_document_artifacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "artifact_type", "version_number", name="uq_fiscal_document_artifact_version"),
    )

    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FiscalDocumentEvent(TenantEntityMixin, Base):
    __tablename__ = "fiscal_document_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "event_type", "event_sequence", name="uq_fiscal_document_event_sequence"),
    )

    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provider_event_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    protocol_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FiscalProcessingAttempt(TenantEntityMixin, Base):
    __tablename__ = "fiscal_processing_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", "attempt_number", name="uq_fiscal_processing_attempt_number"),
    )

    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="started", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FiscalJob(TenantEntityMixin, Base):
    __tablename__ = "fiscal_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "job_key", name="uq_fiscal_job_key"),)

    job_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FiscalWebhookInbox(TenantEntityMixin, Base):
    __tablename__ = "fiscal_webhook_inbox"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_configuration_id", "provider_event_id", name="uq_fiscal_webhook_provider_event"),
        UniqueConstraint("tenant_id", "provider_configuration_id", "content_sha256", name="uq_fiscal_webhook_content"),
    )

    provider_configuration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider_event_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="received", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_masked_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IbptSnapshot(TenantEntityMixin, Base):
    __tablename__ = "ibpt_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "state_code", "version_code", name="uq_ibpt_snapshot_state_version"),
    )

    state_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    version_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="validated", index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    imported_by: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IbptEntry(TenantEntityMixin, Base):
    __tablename__ = "ibpt_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "snapshot_id", "code", "ex_code", name="uq_ibpt_entry_code_ex"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ex_code: Mapped[str] = mapped_column(String(10), nullable=False, default="0")
    table_type: Mapped[str] = mapped_column(String(20), nullable=False, default="0")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    national_federal_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0"))
    imported_federal_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0"))
    state_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0"))
    municipal_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0"))
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(180), nullable=True)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


# RH, setor pessoal, folha e controle de ponto ---------------------------------


class OrganizationalDepartment(TenantEntityMixin, Base):
    __tablename__ = "organizational_departments"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_organizational_department_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    manager_employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class JobPosition(TenantEntityMixin, Base):
    __tablename__ = "job_positions"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_job_position_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    cbo_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requirements_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    salary_floor: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    salary_ceiling: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class JobOpening(TenantEntityMixin, Base):
    __tablename__ = "job_openings"
    __table_args__ = (UniqueConstraint("tenant_id", "opening_number", name="uq_job_opening_number"),)

    opening_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    hiring_manager_employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="clt")
    workplace_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="onsite")
    openings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    filled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class RecruitmentCandidate(TenantEntityMixin, Base):
    __tablename__ = "recruitment_candidates"
    __table_args__ = (UniqueConstraint("tenant_id", "person_id", name="uq_recruitment_candidate_person"),)

    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resume_storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    resume_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RecruitmentApplication(TenantEntityMixin, Base):
    __tablename__ = "recruitment_applications"
    __table_args__ = (UniqueConstraint("tenant_id", "job_opening_id", "candidate_id", name="uq_recruitment_application"),)

    job_opening_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    current_stage: Mapped[str] = mapped_column(String(60), nullable=False, default="applied", index=True)
    score: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class RecruitmentStageHistory(TenantEntityMixin, Base):
    __tablename__ = "recruitment_stage_history"
    __table_args__ = (UniqueConstraint("tenant_id", "application_id", "sequence", name="uq_recruitment_stage_sequence"),)

    application_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(60), nullable=True)
    score: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    evaluator_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AdmissionProcess(TenantEntityMixin, Base):
    __tablename__ = "admission_processes"
    __table_args__ = (UniqueConstraint("tenant_id", "application_id", name="uq_admission_application"),)

    application_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    proposed_position_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    proposed_salary: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    proposed_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="clt")
    checklist_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="draft", index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Employee(TenantEntityMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "person_id", name="uq_employee_person"),
        UniqueConstraint("tenant_id", "registration_number", name="uq_employee_registration"),
    )

    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    registration_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    admission_process_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    employment_status: Mapped[str] = mapped_column(String(60), nullable=False, default="active", index=True)
    hired_at: Mapped[date] = mapped_column(Date, nullable=False)
    terminated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    corporate_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class EmploymentContract(TenantEntityMixin, Base):
    __tablename__ = "employment_contracts"
    __table_args__ = (UniqueConstraint("tenant_id", "contract_number", name="uq_employment_contract_number"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    contract_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="clt")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    probation_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekly_hours: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("44"))
    salary_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    salary_unit: Mapped[str] = mapped_column(String(30), nullable=False, default="monthly")
    payment_frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="monthly")
    position_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    work_schedule_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    union_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    terms_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active", index=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmployeeAssignment(TenantEntityMixin, Base):
    __tablename__ = "employee_assignments"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "valid_from", name="uq_employee_assignment_start"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    position_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cost_center_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    manager_employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    allocation_percentage: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("100"))
    primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class OnboardingTask(TenantEntityMixin, Base):
    __tablename__ = "onboarding_tasks"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "task_code", name="uq_onboarding_employee_task"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class EmployeeDocument(TenantEntityMixin, Base):
    __tablename__ = "employee_documents"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "document_type", "document_number", name="uq_employee_document"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(160), nullable=False)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class OccupationalMedicalExam(TenantEntityMixin, Base):
    __tablename__ = "occupational_medical_exams"

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    exam_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    restrictions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="valid", index=True)


class TrainingCourse(TenantEntityMixin, Base):
    __tablename__ = "training_courses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_course_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workload_hours: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=Decimal("0"))
    validity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class TrainingEnrollment(TenantEntityMixin, Base):
    __tablename__ = "training_enrollments"
    __table_args__ = (UniqueConstraint("tenant_id", "course_id", "employee_id", "enrolled_at", name="uq_training_enrollment"),)

    course_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    certificate_storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    certificate_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="enrolled", index=True)


class Competency(TenantEntityMixin, Base):
    __tablename__ = "competencies"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_competency_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="technical")
    scale_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class EmployeeCompetency(TenantEntityMixin, Base):
    __tablename__ = "employee_competencies"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "competency_id", name="uq_employee_competency"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competency_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    current_level: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0"))
    target_level: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluator_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class PerformanceReview(TenantEntityMixin, Base):
    __tablename__ = "performance_reviews"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "cycle_code", name="uq_performance_review_cycle"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cycle_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reviewer_employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    overall_score: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    goals_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    competencies_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DevelopmentPlan(TenantEntityMixin, Base):
    __tablename__ = "development_plans"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "cycle_code", name="uq_development_plan_cycle"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    performance_review_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cycle_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    objectives_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    actions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress_percentage: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class BenefitPlan(TenantEntityMixin, Base):
    __tablename__ = "benefit_plans"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_benefit_plan_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    benefit_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employer_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    employee_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    payroll_rubric_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class EmployeeBenefit(TenantEntityMixin, Base):
    __tablename__ = "employee_benefits"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "benefit_plan_id", "valid_from", name="uq_employee_benefit_start"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    benefit_plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    employer_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    employee_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    dependents_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class VacationPeriod(TenantEntityMixin, Base):
    __tablename__ = "vacation_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "accrual_start", "accrual_end", name="uq_vacation_accrual_period"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    accrual_start: Mapped[date] = mapped_column(Date, nullable=False)
    accrual_end: Mapped[date] = mapped_column(Date, nullable=False)
    entitlement_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    scheduled_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    scheduled_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    sold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taken_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="accruing", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmployeeLeave(TenantEntityMixin, Base):
    __tablename__ = "employee_leaves"

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    leave_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    affects_payroll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="submitted", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmployeeOccurrence(TenantEntityMixin, Base):
    __tablename__ = "employee_occurrences"

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    occurrence_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="informational")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)


class EmploymentTermination(TenantEntityMixin, Base):
    __tablename__ = "employment_terminations"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", name="uq_employment_termination_employee"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employment_contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    termination_type: Mapped[str] = mapped_column(String(80), nullable=False)
    notice_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    settlement_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    checklist_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmployeeDependent(TenantEntityMixin, Base):
    __tablename__ = "employee_dependents"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "person_id", name="uq_employee_dependent_person"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    relationship: Mapped[str] = mapped_column(String(60), nullable=False)
    income_tax_dependent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    family_allowance_dependent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    health_plan_dependent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class SalaryHistory(TenantEntityMixin, Base):
    __tablename__ = "salary_history"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "effective_from", name="uq_salary_history_effective"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employment_contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    salary_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    salary_unit: Mapped[str] = mapped_column(String(30), nullable=False, default="monthly")
    change_type: Mapped[str] = mapped_column(String(60), nullable=False, default="admission")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class StabilityPeriod(TenantEntityMixin, Base):
    __tablename__ = "stability_periods"

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    stability_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class LaborUnion(TenantEntityMixin, Base):
    __tablename__ = "labor_unions"
    __table_args__ = (UniqueConstraint("tenant_id", "document_number", name="uq_labor_union_document"),)

    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    union_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    base_date_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collective_agreement_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class EmployeeLoan(TenantEntityMixin, Base):
    __tablename__ = "employee_loans"
    __table_args__ = (UniqueConstraint("tenant_id", "loan_number", name="uq_employee_loan_number"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    loan_number: Mapped[str] = mapped_column(String(100), nullable=False)
    lender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    principal_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    installment_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_installments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_competence: Mapped[str] = mapped_column(String(7), nullable=False)
    payroll_rubric_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class AlimonyOrder(TenantEntityMixin, Base):
    __tablename__ = "alimony_orders"

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    beneficiary_person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    court_case_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    calculation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    fixed_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    calculation_base: Mapped[str] = mapped_column(String(80), nullable=False, default="net")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class GovernmentLaborProviderConfiguration(TenantEntityMixin, Base):
    __tablename__ = "government_labor_provider_configurations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_code", "environment", name="uq_government_labor_provider"),)

    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="homologation")
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certificate_secret_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured", index=True)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_configured")


class GovernmentLaborSubmission(TenantEntityMixin, Base):
    __tablename__ = "government_labor_submissions"
    __table_args__ = (UniqueConstraint("tenant_id", "provider_configuration_id", "idempotency_reference", name="uq_government_submission_reference"),)

    provider_configuration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    competence: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    idempotency_reference: Mapped[str] = mapped_column(String(180), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="queued", index=True)
    protocol_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkShift(TenantEntityMixin, Base):
    __tablename__ = "work_shifts"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_work_shift_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    expected_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    night_start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    night_end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    late_tolerance_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    early_departure_tolerance_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    overtime_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class WorkSchedule(TenantEntityMixin, Base):
    __tablename__ = "work_schedules"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_work_schedule_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    weekly_hours: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bahia")
    holiday_calendar_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class WorkScheduleDay(TenantEntityMixin, Base):
    __tablename__ = "work_schedule_days"
    __table_args__ = (UniqueConstraint("tenant_id", "work_schedule_id", "weekday", name="uq_work_schedule_weekday"),)

    work_schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    shift_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    working_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expected_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EmployeeScheduleAssignment(TenantEntityMixin, Base):
    __tablename__ = "employee_schedule_assignments"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "valid_from", name="uq_employee_schedule_assignment"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    work_schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class TimeClockDevice(TenantEntityMixin, Base):
    __tablename__ = "time_clock_devices"
    __table_args__ = (UniqueConstraint("tenant_id", "device_code", name="uq_time_clock_device_code"),)

    device_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(String(60), nullable=False, default="app")
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, default="local")
    serial_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimePunch(TenantEntityMixin, Base):
    __tablename__ = "time_punches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_id", "source_idempotency_key", name="uq_time_punch_source_key"),
        UniqueConstraint("tenant_id", "device_id", "nsr", name="uq_time_punch_device_nsr"),
    )

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    punched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Bahia")
    punch_type: Mapped[str] = mapped_column(String(40), nullable=False, default="regular")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="web", index=True)
    source_idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    nsr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    location_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    photo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offline_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="valid", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class TimekeepingPeriod(TenantEntityMixin, Base):
    __tablename__ = "timekeeping_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_timekeeping_period_code"),)

    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TimesheetEntry(TenantEntityMixin, Base):
    __tablename__ = "timesheet_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "period_id", "employee_id", "work_date", name="uq_timesheet_employee_date"),)

    period_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    schedule_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expected_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worked_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    early_departure_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    night_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    absence_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    justified_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    punch_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="calculated", index=True)
    calculation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TimeAdjustment(TenantEntityMixin, Base):
    __tablename__ = "time_adjustments"

    timesheet_entry_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    adjustment_type: Mapped[str] = mapped_column(String(60), nullable=False)
    minutes_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="submitted", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimeJustification(TenantEntityMixin, Base):
    __tablename__ = "time_justifications"

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    period_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    justification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="submitted", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimeApproval(TenantEntityMixin, Base):
    __tablename__ = "time_approvals"
    __table_args__ = (UniqueConstraint("tenant_id", "period_id", "employee_id", name="uq_time_approval_employee_period"),)

    period_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TimeBankEntry(TenantEntityMixin, Base):
    __tablename__ = "time_bank_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "reference_type", "reference_id", name="uq_time_bank_reference"),)

    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class AfdImport(TenantEntityMixin, Base):
    __tablename__ = "afd_imports"
    __table_args__ = (UniqueConstraint("tenant_id", "source_sha256", name="uq_afd_import_hash"),)

    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider_code: Mapped[str] = mapped_column(String(80), nullable=False, default="generic_afd")
    layout_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_nsr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_nsr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="validating", index=True)
    errors_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    imported_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)


class AfdRecord(TenantEntityMixin, Base):
    __tablename__ = "afd_records"
    __table_args__ = (UniqueConstraint("tenant_id", "afd_import_id", "nsr", name="uq_afd_record_nsr"),)

    afd_import_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    nsr: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    employee_registration: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_line_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    time_punch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="parsed", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollRubric(TenantEntityMixin, Base):
    __tablename__ = "payroll_rubrics"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_payroll_rubric_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nature: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    calculation_type: Mapped[str] = mapped_column(String(50), nullable=False, default="fixed")
    default_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    default_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    incidences_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    formula_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    accounting_debit_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accounting_credit_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)


class PayrollCompetence(TenantEntityMixin, Base):
    __tablename__ = "payroll_competences"
    __table_args__ = (UniqueConstraint("tenant_id", "code", "payroll_type", name="uq_payroll_competence_type"),)

    code: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    payroll_type: Mapped[str] = mapped_column(String(40), nullable=False, default="regular")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    timekeeping_period_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollRun(TenantEntityMixin, Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "competence_id", "run_number", name="uq_payroll_run_number"),)

    competence_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="simulation")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft", index=True)
    employee_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    deduction_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    employer_charge_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    processing_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class PayrollEmployeeCalculation(TenantEntityMixin, Base):
    __tablename__ = "payroll_employee_calculations"
    __table_args__ = (UniqueConstraint("tenant_id", "payroll_run_id", "employee_id", name="uq_payroll_run_employee"),)

    payroll_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competence_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employment_contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    base_salary: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    deduction_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    employer_charge_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    worked_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    absence_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    night_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bases_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="calculated", index=True)
    calculation_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PayrollLine(TenantEntityMixin, Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_calculation_id", "sequence", name="uq_payroll_line_sequence"),)

    employee_calculation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rubric_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rubric_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    nature: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_quantity: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    calculation_base: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    incidences_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, default="calculation")
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class PayrollCostAllocation(TenantEntityMixin, Base):
    __tablename__ = "payroll_cost_allocations"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_calculation_id", "cost_center_id", name="uq_payroll_cost_allocation"),)

    employee_calculation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    cost_center_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    percentage: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class Payslip(TenantEntityMixin, Base):
    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_calculation_id", name="uq_payslip_employee_calculation"),)

    employee_calculation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competence_code: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    document_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="generated", index=True)


class PayrollProvision(TenantEntityMixin, Base):
    __tablename__ = "payroll_provisions"
    __table_args__ = (UniqueConstraint("tenant_id", "competence_id", "employee_id", "provision_type", name="uq_payroll_provision"),)

    competence_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provision_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    base_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    provision_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reversed_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)


class PayrollAccountingBatch(TenantEntityMixin, Base):
    __tablename__ = "payroll_accounting_batches"
    __table_args__ = (UniqueConstraint("tenant_id", "payroll_run_id", name="uq_payroll_accounting_run"),)

    payroll_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ledger_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    total_debit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="posted", index=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
