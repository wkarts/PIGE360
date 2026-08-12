from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.modules.inventory.application.service import change_stock, get_product, get_warehouse
from backend.app.modules.procurement.presentation.schemas import (
    GoodsReceiptCreate,
    InventoryCountComplete,
    InventoryCountCreate,
    ProductBarcodeCreate,
    ProductVariantCreate,
    PurchaseOrderCreate,
    PurchaseReturnCreate,
    QuotationAward,
    QuotationCreate,
    RequisitionApproval,
    RequisitionCreate,
    ReservationCreate,
    SupplierCreate,
    SupplierPatch,
    SupplierProposalCreate,
)
from backend.app.shared.application.audit import audit_tenant, emit_tenant_event
from backend.app.shared.application.idempotency import complete, reserve_tenant
from backend.app.shared.application.serialization import json_value, model_to_dict
from backend.app.shared.database.models_tenant import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryCount,
    InventoryCountItem,
    InventoryLot,
    Product,
    ProductBarcode,
    ProductVariant,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    PurchaseReturn,
    PurchaseReturnItem,
    QuotationItem,
    QuotationSupplier,
    QuotationSupplierItem,
    RequestForQuotation,
    StockBalance,
    StockReservation,
    Supplier,
    SupplierContact,
)
from backend.app.shared.domain.dates import utcnow
from backend.app.shared.domain.errors import ConflictError, NotFoundError, ValidationError
from backend.app.shared.domain.ids import new_id
from backend.app.shared.security.permissions import Actor

CENT = Decimal('0.01')
QTY = Decimal('0.0001')
COST = Decimal('0.0001')


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(QTY, rounding=ROUND_HALF_UP)


def cost(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(COST, rounding=ROUND_HALF_UP)


def _etag(row: Any, expected_version: int | None) -> None:
    if expected_version is not None and row.version != expected_version:
        raise ConflictError('O registro foi alterado por outro usuário.', code='OPTIMISTIC_CONCURRENCY_CONFLICT')


def _get_supplier(session: Session, tenant_id: str, supplier_id: str, *, active: bool = False) -> Supplier:
    row = session.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None)))
    if row is None:
        raise NotFoundError('Fornecedor não encontrado.', code='SUPPLIER_NOT_FOUND')
    if active and row.status != 'active':
        raise ConflictError('O fornecedor não está ativo.', code='SUPPLIER_INACTIVE')
    return row


def _get_requisition(session: Session, tenant_id: str, requisition_id: str) -> PurchaseRequisition:
    row = session.scalar(select(PurchaseRequisition).where(PurchaseRequisition.id == requisition_id, PurchaseRequisition.tenant_id == tenant_id))
    if row is None:
        raise NotFoundError('Requisição de compra não encontrada.', code='PURCHASE_REQUISITION_NOT_FOUND')
    return row


def _get_quotation(session: Session, tenant_id: str, quotation_id: str) -> RequestForQuotation:
    row = session.scalar(select(RequestForQuotation).where(RequestForQuotation.id == quotation_id, RequestForQuotation.tenant_id == tenant_id))
    if row is None:
        raise NotFoundError('Cotação não encontrada.', code='QUOTATION_NOT_FOUND')
    return row


def _get_order(session: Session, tenant_id: str, order_id: str) -> PurchaseOrder:
    row = session.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id, PurchaseOrder.tenant_id == tenant_id))
    if row is None:
        raise NotFoundError('Pedido de compra não encontrado.', code='PURCHASE_ORDER_NOT_FOUND')
    return row


def _get_lot(session: Session, tenant_id: str, lot_id: str, *, lock: bool = False) -> InventoryLot:
    query = select(InventoryLot).where(InventoryLot.id == lot_id, InventoryLot.tenant_id == tenant_id, InventoryLot.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise NotFoundError('Lote não encontrado.', code='INVENTORY_LOT_NOT_FOUND')
    return row


def _create_or_update_lot(
    session: Session,
    *,
    tenant_id: str,
    product: Product,
    warehouse_id: str,
    lot_number: str,
    manufactured_on: date | None,
    expires_on: date | None,
    amount: Decimal,
    unit_cost: Decimal,
    receipt_item_id: str | None,
    institution_id: str | None,
    unit_id: str | None,
) -> InventoryLot:
    row = session.scalar(
        select(InventoryLot)
        .where(
            InventoryLot.tenant_id == tenant_id,
            InventoryLot.product_id == product.id,
            InventoryLot.warehouse_id == warehouse_id,
            InventoryLot.lot_number == lot_number,
            InventoryLot.deleted_at.is_(None),
        )
        .with_for_update()
    )
    incoming = quantity(amount)
    if row is None:
        row = InventoryLot(
            tenant_id=tenant_id,
            institution_id=institution_id,
            unit_id=unit_id,
            product_id=product.id,
            warehouse_id=warehouse_id,
            lot_number=lot_number,
            manufactured_on=manufactured_on,
            expires_on=expires_on,
            quantity=incoming,
            reserved_quantity=Decimal('0.0000'),
            unit_cost=cost(unit_cost),
            status='active',
            receipt_item_id=receipt_item_id,
        )
        session.add(row)
    else:
        if row.expires_on and expires_on and row.expires_on != expires_on:
            raise ConflictError('O lote já existe com outra validade.', code='INVENTORY_LOT_EXPIRY_CONFLICT')
        previous_quantity = quantity(row.quantity)
        next_quantity = quantity(previous_quantity + incoming)
        if next_quantity > 0:
            row.unit_cost = cost(((previous_quantity * cost(row.unit_cost)) + (incoming * cost(unit_cost))) / next_quantity)
        row.quantity = next_quantity
        row.expires_on = row.expires_on or expires_on
        row.manufactured_on = row.manufactured_on or manufactured_on
        row.status = 'active'
        row.version += 1
    session.flush()
    return row


# Fornecedores -----------------------------------------------------------------


def list_suppliers(session: Session, tenant_id: str, *, status: str | None, search: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions = [Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None)]
    if status:
        conditions.append(Supplier.status == status)
    if search:
        pattern = f'%{search.strip()}%'
        conditions.append(Supplier.trade_name.ilike(pattern) | Supplier.legal_name.ilike(pattern) | Supplier.code.ilike(pattern))
    if cursor:
        conditions.append(Supplier.id > cursor)
    rows = session.scalars(select(Supplier).where(*conditions).order_by(Supplier.id).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [model_to_dict(row) for row in rows], 'count': len(rows), 'next_cursor': rows[-1].id if has_more and rows else None}


def create_supplier(session: Session, tenant_id: str, data: SupplierCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='procurement.supplier.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O fornecedor ainda está sendo criado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    duplicate = session.scalar(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.code == data.code, Supplier.deleted_at.is_(None)))
    if duplicate:
        raise ConflictError('Já existe fornecedor com este código.', code='SUPPLIER_CODE_EXISTS')
    if data.cnpj:
        duplicate_cnpj = session.scalar(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.cnpj == data.cnpj, Supplier.deleted_at.is_(None)))
        if duplicate_cnpj:
            raise ConflictError('Já existe fornecedor com este CNPJ.', code='SUPPLIER_CNPJ_EXISTS')
    row = Supplier(tenant_id=tenant_id, institution_id=data.institution_id, unit_id=data.unit_id, code=data.code, legal_name=data.legal_name.strip(), trade_name=data.trade_name.strip(), cnpj=data.cnpj, status='active', rating=data.rating, payment_terms_json=json_value(data.payment_terms), fiscal_profile_json=json_value(data.fiscal_profile), notes=data.notes)
    session.add(row)
    session.flush()
    contacts = []
    for item in data.contacts:
        contact = SupplierContact(tenant_id=tenant_id, institution_id=row.institution_id, unit_id=row.unit_id, supplier_id=row.id, name=item.name.strip(), email=item.email, phone=item.phone, role=item.role, primary=item.primary)
        session.add(contact)
        contacts.append(contact)
    session.flush()
    response = {'supplier': model_to_dict(row), 'contacts': [model_to_dict(item) for item in contacts]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.supplier.created', resource_type='supplier', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='SupplierCreated', aggregate_type='supplier', aggregate_id=row.id, payload=response['supplier'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def supplier_detail(session: Session, tenant_id: str, supplier_id: str) -> dict[str, Any]:
    row = _get_supplier(session, tenant_id, supplier_id)
    contacts = session.scalars(select(SupplierContact).where(SupplierContact.tenant_id == tenant_id, SupplierContact.supplier_id == row.id, SupplierContact.deleted_at.is_(None)).order_by(SupplierContact.primary.desc(), SupplierContact.name)).all()
    orders = session.scalars(select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.supplier_id == row.id).order_by(PurchaseOrder.created_at.desc()).limit(50)).all()
    return {'supplier': model_to_dict(row), 'contacts': [model_to_dict(item) for item in contacts], 'recent_orders': [model_to_dict(item) for item in orders]}


def patch_supplier(session: Session, tenant_id: str, supplier_id: str, data: SupplierPatch, *, expected_version: int | None, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_supplier(session, tenant_id, supplier_id)
    _etag(row, expected_version)
    before = model_to_dict(row)
    values = data.model_dump(exclude_unset=True)
    for field in ('legal_name', 'trade_name', 'rating', 'notes'):
        if field in values:
            setattr(row, field, values[field])
    if values.get('status') is not None:
        status = values['status'].strip().lower()
        if status not in {'active', 'inactive', 'blocked'}:
            raise ValidationError('Status de fornecedor inválido.', code='INVALID_SUPPLIER_STATUS')
        row.status = status
    if values.get('payment_terms') is not None:
        row.payment_terms_json = json_value(values['payment_terms'])
    if values.get('fiscal_profile') is not None:
        row.fiscal_profile_json = json_value(values['fiscal_profile'])
    row.version += 1
    session.flush()
    after = model_to_dict(row)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.supplier.updated', resource_type='supplier', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, before=before, after=after, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='SupplierUpdated', aggregate_type='supplier', aggregate_id=row.id, payload=after, correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    session.commit()
    return after


# Variantes e códigos de barras ------------------------------------------------


def create_variant(session: Session, tenant_id: str, data: ProductVariantCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='inventory.variant.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A variante ainda está sendo criada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    product = get_product(session, tenant_id, data.product_id)
    duplicate = session.scalar(select(ProductVariant).where(ProductVariant.tenant_id == tenant_id, ProductVariant.sku == data.sku, ProductVariant.deleted_at.is_(None)))
    if duplicate:
        raise ConflictError('SKU de variante já cadastrado.', code='PRODUCT_VARIANT_SKU_EXISTS')
    row = ProductVariant(tenant_id=tenant_id, institution_id=product.institution_id, unit_id=product.unit_id, product_id=product.id, sku=data.sku.strip().upper(), name=data.name.strip(), attributes_json=json_value(data.attributes), sale_price=money(data.sale_price) if data.sale_price is not None else None, cost_price=money(data.cost_price) if data.cost_price is not None else None, status='active')
    session.add(row)
    session.flush()
    response = model_to_dict(row)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='inventory.variant.created', resource_type='product_variant', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def create_barcode(session: Session, tenant_id: str, data: ProductBarcodeCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='inventory.barcode.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O código de barras ainda está sendo criado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    product = get_product(session, tenant_id, data.product_id)
    variant = None
    if data.variant_id:
        variant = session.scalar(select(ProductVariant).where(ProductVariant.id == data.variant_id, ProductVariant.tenant_id == tenant_id, ProductVariant.product_id == product.id, ProductVariant.deleted_at.is_(None)))
        if variant is None:
            raise ValidationError('Variante não pertence ao produto.', code='PRODUCT_VARIANT_MISMATCH')
    duplicate = session.scalar(select(ProductBarcode).where(ProductBarcode.tenant_id == tenant_id, ProductBarcode.barcode == data.barcode, ProductBarcode.deleted_at.is_(None)))
    if duplicate:
        raise ConflictError('Código de barras já cadastrado.', code='PRODUCT_BARCODE_EXISTS')
    if data.primary:
        for current in session.scalars(select(ProductBarcode).where(ProductBarcode.tenant_id == tenant_id, ProductBarcode.product_id == product.id, ProductBarcode.primary.is_(True), ProductBarcode.deleted_at.is_(None))).all():
            current.primary = False
            current.version += 1
    row = ProductBarcode(tenant_id=tenant_id, institution_id=product.institution_id, unit_id=product.unit_id, product_id=product.id, variant_id=variant.id if variant else None, barcode=data.barcode.strip(), barcode_type=data.barcode_type.strip().lower(), primary=data.primary)
    session.add(row)
    session.flush()
    response = model_to_dict(row)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='inventory.barcode.created', resource_type='product_barcode', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


# Requisições ------------------------------------------------------------------


def create_requisition(session: Session, tenant_id: str, data: RequisitionCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='procurement.requisition.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A requisição ainda está sendo criada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    products = {item.product_id: get_product(session, tenant_id, item.product_id) for item in data.items}
    row = PurchaseRequisition(tenant_id=tenant_id, institution_id=data.institution_id, unit_id=data.unit_id, requisition_number=f'REQ-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}', requester_user_id=actor.id, department_id=data.department_id, cost_center_id=data.cost_center_id, status='draft', needed_by=data.needed_by, justification=data.justification.strip())
    session.add(row)
    session.flush()
    items = []
    for item in data.items:
        product = products[item.product_id]
        child = PurchaseRequisitionItem(tenant_id=tenant_id, institution_id=row.institution_id or product.institution_id, unit_id=row.unit_id or product.unit_id, requisition_id=row.id, product_id=product.id, quantity=quantity(item.quantity), estimated_unit_price=money(item.estimated_unit_price), notes=item.notes)
        session.add(child)
        items.append(child)
    session.flush()
    response = {'requisition': model_to_dict(row), 'items': [model_to_dict(item) for item in items]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.requisition.created', resource_type='purchase_requisition', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='PurchaseRequisitionCreated', aggregate_type='purchase_requisition', aggregate_id=row.id, payload=response['requisition'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def requisition_detail(session: Session, tenant_id: str, requisition_id: str) -> dict[str, Any]:
    row = _get_requisition(session, tenant_id, requisition_id)
    items = session.scalars(select(PurchaseRequisitionItem).where(PurchaseRequisitionItem.tenant_id == tenant_id, PurchaseRequisitionItem.requisition_id == row.id).order_by(PurchaseRequisitionItem.created_at)).all()
    return {'requisition': model_to_dict(row), 'items': [model_to_dict(item) for item in items]}


def transition_requisition(session: Session, tenant_id: str, requisition_id: str, *, action: str, data: RequisitionApproval | None, reason: str | None, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _get_requisition(session, tenant_id, requisition_id)
    before = model_to_dict(row)
    items = session.scalars(select(PurchaseRequisitionItem).where(PurchaseRequisitionItem.tenant_id == tenant_id, PurchaseRequisitionItem.requisition_id == row.id)).all()
    if action == 'submit':
        if row.status != 'draft':
            raise ConflictError('Somente requisição em rascunho pode ser enviada.', code='INVALID_STATE_TRANSITION')
        row.status = 'submitted'
        event_type = 'PurchaseRequisitionSubmitted'
    elif action == 'approve':
        if row.status != 'submitted':
            raise ConflictError('Somente requisição enviada pode ser aprovada.', code='INVALID_STATE_TRANSITION')
        quantities = data.approved_quantities if data else {}
        for item in items:
            approved = quantity(quantities.get(item.id, item.quantity))
            if approved < 0 or approved > quantity(item.quantity):
                raise ValidationError('Quantidade aprovada inválida.', code='INVALID_APPROVED_QUANTITY')
            item.approved_quantity = approved
            item.version += 1
        if not any(quantity(item.approved_quantity or 0) > 0 for item in items):
            raise ValidationError('A aprovação deve manter ao menos um item.', code='REQUISITION_WITHOUT_APPROVED_ITEMS')
        row.status = 'approved'
        row.approved_by = actor.id
        row.approved_at = utcnow()
        event_type = 'PurchaseRequisitionApproved'
    elif action == 'reject':
        if row.status not in {'submitted', 'approved'}:
            raise ConflictError('A requisição não pode ser rejeitada neste estado.', code='INVALID_STATE_TRANSITION')
        row.status = 'rejected'
        row.rejection_reason = reason
        event_type = 'PurchaseRequisitionRejected'
    elif action == 'cancel':
        if row.status in {'fulfilled', 'cancelled'}:
            raise ConflictError('A requisição não pode ser cancelada neste estado.', code='INVALID_STATE_TRANSITION')
        row.status = 'cancelled'
        row.rejection_reason = reason
        event_type = 'PurchaseRequisitionCancelled'
    else:
        raise ValidationError('Ação de requisição inválida.', code='INVALID_REQUISITION_ACTION')
    row.version += 1
    session.flush()
    after = {'requisition': model_to_dict(row), 'items': [model_to_dict(item) for item in items]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action=f'procurement.requisition.{action}', resource_type='purchase_requisition', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, before=before, after=after, metadata={'reason': reason}, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type=event_type, aggregate_type='purchase_requisition', aggregate_id=row.id, payload=after['requisition'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    session.commit()
    return after


# Cotações e pedidos ------------------------------------------------------------


def create_quotation(session: Session, tenant_id: str, data: QuotationCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='procurement.quotation.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A cotação ainda está sendo criada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    requisition = _get_requisition(session, tenant_id, data.requisition_id) if data.requisition_id else None
    if requisition and requisition.status != 'approved':
        raise ConflictError('A requisição precisa estar aprovada.', code='REQUISITION_NOT_APPROVED')
    supplier_rows = [_get_supplier(session, tenant_id, supplier_id, active=True) for supplier_id in data.supplier_ids]
    source_items: list[tuple[Product, Decimal, dict]] = []
    if requisition:
        requisition_items = session.scalars(select(PurchaseRequisitionItem).where(PurchaseRequisitionItem.tenant_id == tenant_id, PurchaseRequisitionItem.requisition_id == requisition.id)).all()
        for item in requisition_items:
            approved = quantity(item.approved_quantity or 0)
            if approved > 0:
                source_items.append((get_product(session, tenant_id, item.product_id), approved, {}))
    else:
        for item in data.items:
            source_items.append((get_product(session, tenant_id, item.product_id), quantity(item.quantity), item.specifications))
    if not source_items:
        raise ValidationError('A cotação não possui itens.', code='QUOTATION_WITHOUT_ITEMS')
    row = RequestForQuotation(tenant_id=tenant_id, institution_id=data.institution_id or (requisition.institution_id if requisition else None), unit_id=data.unit_id or (requisition.unit_id if requisition else None), quotation_number=f'COT-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}', requisition_id=requisition.id if requisition else None, status='sent', response_deadline=data.response_deadline, currency=data.currency.upper())
    session.add(row)
    session.flush()
    items = []
    for product, amount, specifications in source_items:
        child = QuotationItem(tenant_id=tenant_id, institution_id=row.institution_id or product.institution_id, unit_id=row.unit_id or product.unit_id, quotation_id=row.id, product_id=product.id, quantity=amount, specifications_json=json_value(specifications))
        session.add(child)
        items.append(child)
    invited = []
    for supplier in supplier_rows:
        invitation = QuotationSupplier(tenant_id=tenant_id, institution_id=row.institution_id, unit_id=row.unit_id, quotation_id=row.id, supplier_id=supplier.id, status='invited', invited_at=utcnow(), payment_terms_json={})
        session.add(invitation)
        invited.append(invitation)
    session.flush()
    response = {'quotation': model_to_dict(row), 'items': [model_to_dict(item) for item in items], 'suppliers': [model_to_dict(item) for item in invited]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.quotation.created', resource_type='request_for_quotation', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='QuotationRequested', aggregate_type='request_for_quotation', aggregate_id=row.id, payload=response['quotation'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def quotation_detail(session: Session, tenant_id: str, quotation_id: str) -> dict[str, Any]:
    row = _get_quotation(session, tenant_id, quotation_id)
    items = session.scalars(select(QuotationItem).where(QuotationItem.tenant_id == tenant_id, QuotationItem.quotation_id == row.id).order_by(QuotationItem.created_at)).all()
    suppliers = session.scalars(select(QuotationSupplier).where(QuotationSupplier.tenant_id == tenant_id, QuotationSupplier.quotation_id == row.id).order_by(QuotationSupplier.created_at)).all()
    proposal_items = session.scalars(select(QuotationSupplierItem).join(QuotationSupplier, QuotationSupplier.id == QuotationSupplierItem.quotation_supplier_id).where(QuotationSupplier.tenant_id == tenant_id, QuotationSupplier.quotation_id == row.id)).all()
    return {'quotation': model_to_dict(row), 'items': [model_to_dict(item) for item in items], 'suppliers': [model_to_dict(item) for item in suppliers], 'proposal_items': [model_to_dict(item) for item in proposal_items]}


def submit_supplier_proposal(session: Session, tenant_id: str, quotation_id: str, supplier_id: str, data: SupplierProposalCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'procurement.quotation.{quotation_id}.proposal.{supplier_id}', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A proposta ainda está sendo processada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    quotation = _get_quotation(session, tenant_id, quotation_id)
    if quotation.status not in {'sent', 'responses_received'}:
        raise ConflictError('A cotação não aceita propostas neste estado.', code='QUOTATION_NOT_OPEN')
    invitation = session.scalar(select(QuotationSupplier).where(QuotationSupplier.tenant_id == tenant_id, QuotationSupplier.quotation_id == quotation.id, QuotationSupplier.supplier_id == supplier_id).with_for_update())
    if invitation is None:
        raise ConflictError('O fornecedor não foi convidado para esta cotação.', code='SUPPLIER_NOT_INVITED')
    if invitation.status == 'responded':
        raise ConflictError('O fornecedor já respondeu a cotação.', code='SUPPLIER_ALREADY_RESPONDED')
    quote_items = {item.id: item for item in session.scalars(select(QuotationItem).where(QuotationItem.tenant_id == tenant_id, QuotationItem.quotation_id == quotation.id)).all()}
    if set(quote_items) != {item.quotation_item_id for item in data.items}:
        raise ValidationError('A proposta deve responder a todos os itens da cotação.', code='PROPOSAL_ITEMS_MISMATCH')
    rows = []
    total = Decimal('0')
    for item in data.items:
        quote_item = quote_items[item.quotation_item_id]
        line_total = money(quantity(quote_item.quantity) * money(item.unit_price))
        total += line_total
        child = QuotationSupplierItem(tenant_id=tenant_id, institution_id=quotation.institution_id, unit_id=quotation.unit_id, quotation_supplier_id=invitation.id, quotation_item_id=quote_item.id, unit_price=money(item.unit_price), quantity_available=quantity(item.quantity_available), brand=item.brand, notes=item.notes)
        session.add(child)
        rows.append(child)
    invitation.status = 'responded'
    invitation.responded_at = utcnow()
    invitation.total_amount = money(total)
    invitation.delivery_days = data.delivery_days
    invitation.payment_terms_json = json_value(data.payment_terms)
    invitation.notes = data.notes
    invitation.version += 1
    quotation.status = 'responses_received'
    quotation.version += 1
    session.flush()
    response = {'supplier': model_to_dict(invitation), 'items': [model_to_dict(item) for item in rows]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.quotation.proposal_submitted', resource_type='quotation_supplier', resource_id=invitation.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=quotation.institution_id, unit_id=quotation.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='SupplierQuotationResponded', aggregate_type='request_for_quotation', aggregate_id=quotation.id, payload={'supplier_id': supplier_id, 'total_amount': str(invitation.total_amount)}, correlation_id=correlation_id, institution_id=quotation.institution_id, unit_id=quotation.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def _create_order_rows(session: Session, *, tenant_id: str, supplier: Supplier, warehouse_id: str, items: list[tuple[Product, Decimal, Decimal, Decimal]], institution_id: str | None, unit_id: str | None, quotation_id: str | None, requisition_id: str | None, freight_amount: Decimal, discount_amount: Decimal, expected_on: date | None, notes: str | None, status: str, actor: Actor) -> tuple[PurchaseOrder, list[PurchaseOrderItem]]:
    warehouse = get_warehouse(session, tenant_id, warehouse_id)
    gross_lines = [money(amount * unit_price) for _, amount, unit_price, _ in items]
    subtotal = money(sum(gross_lines, Decimal('0')))
    line_discounts = money(sum((line_discount for _, _, _, line_discount in items), Decimal('0')))
    order_discount = money(discount_amount)
    total = money(subtotal - line_discounts - order_discount + money(freight_amount))
    if total < 0:
        raise ValidationError('O desconto excede o total do pedido.', code='PURCHASE_ORDER_NEGATIVE_TOTAL')
    row = PurchaseOrder(tenant_id=tenant_id, institution_id=institution_id or warehouse.institution_id, unit_id=unit_id or warehouse.unit_id, order_number=f'PC-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}', supplier_id=supplier.id, quotation_id=quotation_id, requisition_id=requisition_id, warehouse_id=warehouse.id, status=status, currency='BRL', subtotal=subtotal, discount_amount=money(line_discounts + order_discount), freight_amount=money(freight_amount), total_amount=total, expected_on=expected_on, approved_by=actor.id if status == 'approved' else None, approved_at=utcnow() if status == 'approved' else None, notes=notes)
    session.add(row)
    session.flush()
    order_items = []
    for product, amount, unit_price, line_discount in items:
        gross = money(amount * unit_price)
        item = PurchaseOrderItem(tenant_id=tenant_id, institution_id=row.institution_id, unit_id=row.unit_id, purchase_order_id=row.id, product_id=product.id, ordered_quantity=quantity(amount), received_quantity=Decimal('0.0000'), returned_quantity=Decimal('0.0000'), unit_price=money(unit_price), discount_amount=money(line_discount), total_amount=money(gross - line_discount), fiscal_profile_snapshot_json=json_value(product.fiscal_profile_json))
        session.add(item)
        order_items.append(item)
    session.flush()
    return row, order_items


def award_quotation(session: Session, tenant_id: str, quotation_id: str, data: QuotationAward, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'procurement.quotation.{quotation_id}.award', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A adjudicação ainda está sendo processada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    quotation = _get_quotation(session, tenant_id, quotation_id)
    if quotation.status != 'responses_received':
        raise ConflictError('A cotação precisa possuir propostas antes da adjudicação.', code='QUOTATION_WITHOUT_RESPONSES')
    supplier = _get_supplier(session, tenant_id, data.supplier_id, active=True)
    proposal = session.scalar(select(QuotationSupplier).where(QuotationSupplier.tenant_id == tenant_id, QuotationSupplier.quotation_id == quotation.id, QuotationSupplier.supplier_id == supplier.id, QuotationSupplier.status == 'responded'))
    if proposal is None:
        raise ConflictError('O fornecedor não possui proposta válida.', code='SUPPLIER_PROPOSAL_NOT_FOUND')
    quote_items = {item.id: item for item in session.scalars(select(QuotationItem).where(QuotationItem.tenant_id == tenant_id, QuotationItem.quotation_id == quotation.id)).all()}
    proposal_items = session.scalars(select(QuotationSupplierItem).where(QuotationSupplierItem.tenant_id == tenant_id, QuotationSupplierItem.quotation_supplier_id == proposal.id)).all()
    order_payload: list[tuple[Product, Decimal, Decimal, Decimal]] = []
    for item in proposal_items:
        source = quote_items[item.quotation_item_id]
        if quantity(item.quantity_available) < quantity(source.quantity):
            raise ConflictError('A proposta selecionada não atende a quantidade solicitada.', code='SUPPLIER_QUANTITY_INSUFFICIENT')
        order_payload.append((get_product(session, tenant_id, source.product_id), quantity(source.quantity), money(item.unit_price), Decimal('0.00')))
    order, order_items = _create_order_rows(session, tenant_id=tenant_id, supplier=supplier, warehouse_id=data.warehouse_id, items=order_payload, institution_id=quotation.institution_id, unit_id=quotation.unit_id, quotation_id=quotation.id, requisition_id=quotation.requisition_id, freight_amount=data.freight_amount, discount_amount=data.discount_amount, expected_on=data.expected_on, notes=data.reason, status='approved', actor=actor)
    quotation.status = 'awarded'
    quotation.selected_supplier_id = supplier.id
    quotation.selection_reason = data.reason
    quotation.awarded_at = utcnow()
    quotation.version += 1
    if quotation.requisition_id:
        requisition = _get_requisition(session, tenant_id, quotation.requisition_id)
        requisition.status = 'ordered'
        requisition.version += 1
    session.flush()
    response = {'quotation': model_to_dict(quotation), 'order': model_to_dict(order), 'items': [model_to_dict(item) for item in order_items]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.quotation.awarded', resource_type='request_for_quotation', resource_id=quotation.id, correlation_id=correlation_id, request_id=request_id, after=response, metadata={'reason': data.reason}, ip_address=ip_address, institution_id=quotation.institution_id, unit_id=quotation.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='PurchaseOrderApproved', aggregate_type='purchase_order', aggregate_id=order.id, payload=response['order'], correlation_id=correlation_id, institution_id=order.institution_id, unit_id=order.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def create_purchase_order(session: Session, tenant_id: str, data: PurchaseOrderCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='procurement.order.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O pedido ainda está sendo criado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    supplier = _get_supplier(session, tenant_id, data.supplier_id, active=True)
    requisition = _get_requisition(session, tenant_id, data.requisition_id) if data.requisition_id else None
    if requisition and requisition.status not in {'approved', 'ordered'}:
        raise ConflictError('Requisição não aprovada.', code='REQUISITION_NOT_APPROVED')
    items = [(get_product(session, tenant_id, item.product_id), quantity(item.quantity), money(item.unit_price), money(item.discount_amount)) for item in data.items]
    order, order_items = _create_order_rows(session, tenant_id=tenant_id, supplier=supplier, warehouse_id=data.warehouse_id, items=items, institution_id=data.institution_id, unit_id=data.unit_id, quotation_id=None, requisition_id=requisition.id if requisition else None, freight_amount=data.freight_amount, discount_amount=data.discount_amount, expected_on=data.expected_on, notes=data.notes, status='draft', actor=actor)
    response = {'order': model_to_dict(order), 'items': [model_to_dict(item) for item in order_items]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.order.created', resource_type='purchase_order', resource_id=order.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=order.institution_id, unit_id=order.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='PurchaseOrderCreated', aggregate_type='purchase_order', aggregate_id=order.id, payload=response['order'], correlation_id=correlation_id, institution_id=order.institution_id, unit_id=order.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def order_detail(session: Session, tenant_id: str, order_id: str) -> dict[str, Any]:
    order = _get_order(session, tenant_id, order_id)
    items = session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.tenant_id == tenant_id, PurchaseOrderItem.purchase_order_id == order.id).order_by(PurchaseOrderItem.created_at)).all()
    receipts = session.scalars(select(GoodsReceipt).where(GoodsReceipt.tenant_id == tenant_id, GoodsReceipt.purchase_order_id == order.id).order_by(GoodsReceipt.received_at)).all()
    returns = session.scalars(select(PurchaseReturn).where(PurchaseReturn.tenant_id == tenant_id, PurchaseReturn.purchase_order_id == order.id).order_by(PurchaseReturn.returned_at)).all()
    return {'order': model_to_dict(order), 'items': [model_to_dict(item) for item in items], 'receipts': [model_to_dict(item) for item in receipts], 'returns': [model_to_dict(item) for item in returns]}


def approve_order(session: Session, tenant_id: str, order_id: str, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    order = _get_order(session, tenant_id, order_id)
    if order.status != 'draft':
        raise ConflictError('Somente pedido em rascunho pode ser aprovado.', code='INVALID_STATE_TRANSITION')
    before = model_to_dict(order)
    order.status = 'approved'
    order.approved_by = actor.id
    order.approved_at = utcnow()
    order.version += 1
    session.flush()
    after = model_to_dict(order)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.order.approved', resource_type='purchase_order', resource_id=order.id, correlation_id=correlation_id, request_id=request_id, before=before, after=after, ip_address=ip_address, institution_id=order.institution_id, unit_id=order.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='PurchaseOrderApproved', aggregate_type='purchase_order', aggregate_id=order.id, payload=after, correlation_id=correlation_id, institution_id=order.institution_id, unit_id=order.unit_id)
    session.commit()
    return after


# Recebimento e devolução -------------------------------------------------------


def receive_order(session: Session, tenant_id: str, order_id: str, data: GoodsReceiptCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'procurement.order.{order_id}.receipt', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O recebimento ainda está sendo processado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    order = _get_order(session, tenant_id, order_id)
    if order.status not in {'approved', 'partially_received'}:
        raise ConflictError('O pedido não está disponível para recebimento.', code='PURCHASE_ORDER_NOT_RECEIVABLE')
    order_items = {item.id: item for item in session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.tenant_id == tenant_id, PurchaseOrderItem.purchase_order_id == order.id).with_for_update()).all()}
    if len({item.purchase_order_item_id for item in data.items}) != len(data.items):
        raise ValidationError('Não repita itens no recebimento.', code='DUPLICATE_RECEIPT_ITEM')
    prepared = []
    total = Decimal('0')
    for incoming in data.items:
        order_item = order_items.get(incoming.purchase_order_item_id)
        if order_item is None:
            raise ValidationError('Item não pertence ao pedido.', code='PURCHASE_ORDER_ITEM_NOT_FOUND')
        remaining = quantity(order_item.ordered_quantity - order_item.received_quantity)
        amount = quantity(incoming.quantity)
        if amount > remaining:
            raise ConflictError('Quantidade recebida excede o saldo do pedido.', code='RECEIPT_QUANTITY_EXCEEDS_REMAINING')
        product = get_product(session, tenant_id, order_item.product_id)
        requires_lot = bool((product.fiscal_profile_json or {}).get('requires_lot'))
        if requires_lot and not incoming.lot_number:
            raise ValidationError(f'O produto {product.name} exige lote.', code='INVENTORY_LOT_REQUIRED')
        if incoming.expires_on and incoming.expires_on < utcnow().date():
            raise ConflictError('Não é permitido receber lote vencido.', code='INVENTORY_LOT_EXPIRED')
        line_total = money(amount * cost(incoming.unit_cost))
        total += line_total
        prepared.append((incoming, order_item, product, amount, line_total))
    receipt = GoodsReceipt(tenant_id=tenant_id, institution_id=order.institution_id, unit_id=order.unit_id, receipt_number=f'REC-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}', purchase_order_id=order.id, supplier_id=order.supplier_id, warehouse_id=order.warehouse_id, status='confirmed', received_at=utcnow(), received_by=actor.id, supplier_document_number=data.supplier_document_number, supplier_document_key=data.supplier_document_key, total_amount=money(total), notes=data.notes)
    session.add(receipt)
    session.flush()
    receipt_items = []
    stock_changes = []
    lots = []
    for incoming, order_item, product, amount, _line_total in prepared:
        child = GoodsReceiptItem(tenant_id=tenant_id, institution_id=order.institution_id, unit_id=order.unit_id, goods_receipt_id=receipt.id, purchase_order_item_id=order_item.id, product_id=product.id, quantity=amount, unit_cost=cost(incoming.unit_cost), expires_on=incoming.expires_on)
        session.add(child)
        session.flush()
        lot = None
        if incoming.lot_number:
            lot = _create_or_update_lot(session, tenant_id=tenant_id, product=product, warehouse_id=order.warehouse_id, lot_number=incoming.lot_number.strip(), manufactured_on=incoming.manufactured_on, expires_on=incoming.expires_on, amount=amount, unit_cost=incoming.unit_cost, receipt_item_id=child.id, institution_id=order.institution_id, unit_id=order.unit_id)
            child.lot_id = lot.id
            lots.append(lot)
        balance, movement = change_stock(session, tenant_id=tenant_id, product_id=product.id, warehouse_id=order.warehouse_id, movement_type='purchase', amount=amount, unit_cost=incoming.unit_cost, reference_type='goods_receipt', reference_id=receipt.id, institution_id=order.institution_id, unit_id=order.unit_id, lot_id=lot.id if lot else None)
        child.stock_movement_id = movement.id
        order_item.received_quantity = quantity(order_item.received_quantity + amount)
        order_item.version += 1
        receipt_items.append(child)
        stock_changes.append({'balance': model_to_dict(balance), 'movement': model_to_dict(movement)})
    all_received = all(quantity(item.received_quantity) >= quantity(item.ordered_quantity) for item in order_items.values())
    order.status = 'received' if all_received else 'partially_received'
    if all_received:
        order.closed_at = utcnow()
        if order.requisition_id:
            requisition = _get_requisition(session, tenant_id, order.requisition_id)
            requisition.status = 'fulfilled'
            requisition.version += 1
    order.version += 1
    session.flush()
    response = {'receipt': model_to_dict(receipt), 'items': [model_to_dict(item) for item in receipt_items], 'lots': [model_to_dict(item) for item in lots], 'stock': stock_changes, 'order': model_to_dict(order)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.receipt.confirmed', resource_type='goods_receipt', resource_id=receipt.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=order.institution_id, unit_id=order.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='GoodsReceived', aggregate_type='goods_receipt', aggregate_id=receipt.id, payload=response, correlation_id=correlation_id, institution_id=order.institution_id, unit_id=order.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def return_purchase(session: Session, tenant_id: str, order_id: str, data: PurchaseReturnCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'procurement.order.{order_id}.return', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A devolução ainda está sendo processada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    order = _get_order(session, tenant_id, order_id)
    if order.status not in {'received', 'partially_received', 'partially_returned'}:
        raise ConflictError('O pedido não possui recebimento disponível para devolução.', code='PURCHASE_ORDER_NOT_RETURNABLE')
    order_items = {item.id: item for item in session.scalars(select(PurchaseOrderItem).where(PurchaseOrderItem.tenant_id == tenant_id, PurchaseOrderItem.purchase_order_id == order.id).with_for_update()).all()}
    prepared = []
    total = Decimal('0')
    for requested in data.items:
        order_item = order_items.get(requested.purchase_order_item_id)
        if order_item is None:
            raise ValidationError('Item não pertence ao pedido.', code='PURCHASE_ORDER_ITEM_NOT_FOUND')
        available = quantity(order_item.received_quantity - order_item.returned_quantity)
        amount = quantity(requested.quantity)
        if amount > available:
            raise ConflictError('Quantidade devolvida excede o recebido líquido.', code='PURCHASE_RETURN_EXCEEDS_RECEIVED')
        lot = _get_lot(session, tenant_id, requested.lot_id, lock=True) if requested.lot_id else None
        if lot and (lot.product_id != order_item.product_id or lot.warehouse_id != order.warehouse_id):
            raise ValidationError('Lote não corresponde ao item e depósito.', code='PURCHASE_RETURN_LOT_MISMATCH')
        if lot and quantity(lot.quantity - lot.reserved_quantity) < amount:
            raise ConflictError('Saldo livre do lote insuficiente para devolução.', code='INVENTORY_LOT_INSUFFICIENT')
        unit_cost = cost(lot.unit_cost if lot else order_item.unit_price)
        line_total = money(amount * unit_cost)
        total += line_total
        prepared.append((requested, order_item, lot, amount, unit_cost, line_total))
    return_row = PurchaseReturn(tenant_id=tenant_id, institution_id=order.institution_id, unit_id=order.unit_id, return_number=f'DFC-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}', purchase_order_id=order.id, supplier_id=order.supplier_id, warehouse_id=order.warehouse_id, status='confirmed', reason=data.reason.strip(), total_amount=money(total), returned_at=utcnow(), returned_by=actor.id)
    session.add(return_row)
    session.flush()
    return_items = []
    stock_changes = []
    for _requested, order_item, lot, amount, unit_cost, line_total in prepared:
        balance, movement = change_stock(session, tenant_id=tenant_id, product_id=order_item.product_id, warehouse_id=order.warehouse_id, movement_type='purchase_return_out', amount=amount, unit_cost=unit_cost, reference_type='purchase_return', reference_id=return_row.id, institution_id=order.institution_id, unit_id=order.unit_id, lot_id=lot.id if lot else None)
        if lot:
            lot.quantity = quantity(lot.quantity - amount)
            lot.status = 'depleted' if quantity(lot.quantity) == Decimal('0.0000') else 'active'
            lot.version += 1
        order_item.returned_quantity = quantity(order_item.returned_quantity + amount)
        order_item.version += 1
        child = PurchaseReturnItem(tenant_id=tenant_id, institution_id=order.institution_id, unit_id=order.unit_id, purchase_return_id=return_row.id, purchase_order_item_id=order_item.id, product_id=order_item.product_id, lot_id=lot.id if lot else None, quantity=amount, unit_cost=unit_cost, total_amount=line_total, stock_movement_id=movement.id)
        session.add(child)
        return_items.append(child)
        stock_changes.append({'balance': model_to_dict(balance), 'movement': model_to_dict(movement)})
    order.status = 'partially_returned'
    order.version += 1
    session.flush()
    response = {'return': model_to_dict(return_row), 'items': [model_to_dict(item) for item in return_items], 'stock': stock_changes, 'order': model_to_dict(order)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='procurement.purchase.returned', resource_type='purchase_return', resource_id=return_row.id, correlation_id=correlation_id, request_id=request_id, after=response, metadata={'reason': data.reason}, ip_address=ip_address, institution_id=order.institution_id, unit_id=order.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='PurchaseReturned', aggregate_type='purchase_return', aggregate_id=return_row.id, payload=response, correlation_id=correlation_id, institution_id=order.institution_id, unit_id=order.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


# Reservas e inventários --------------------------------------------------------


def reserve_stock(session: Session, tenant_id: str, data: ReservationCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='inventory.reservation.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A reserva ainda está sendo processada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    product = get_product(session, tenant_id, data.product_id)
    warehouse = get_warehouse(session, tenant_id, data.warehouse_id)
    requested = quantity(data.quantity)
    lot = _get_lot(session, tenant_id, data.lot_id, lock=True) if data.lot_id else None
    if lot and (lot.product_id != product.id or lot.warehouse_id != warehouse.id):
        raise ValidationError('Lote não corresponde ao produto/depósito.', code='RESERVATION_LOT_MISMATCH')
    if lot:
        available = quantity(lot.quantity - lot.reserved_quantity)
    else:
        balance = session.scalar(select(StockBalance).where(StockBalance.tenant_id == tenant_id, StockBalance.product_id == product.id, StockBalance.warehouse_id == warehouse.id).with_for_update())
        total = quantity(balance.quantity if balance else 0)
        reserved = session.scalar(select(func.sum(StockReservation.quantity)).where(StockReservation.tenant_id == tenant_id, StockReservation.product_id == product.id, StockReservation.warehouse_id == warehouse.id, StockReservation.lot_id.is_(None), StockReservation.status == 'active')) or Decimal('0')
        available = quantity(total - reserved)
    if requested > available:
        raise ConflictError('Saldo disponível insuficiente para reserva.', code='INSUFFICIENT_AVAILABLE_STOCK')
    row = StockReservation(tenant_id=tenant_id, institution_id=data.institution_id or product.institution_id, unit_id=data.unit_id or product.unit_id, idempotency_key=idempotency_key, product_id=product.id, warehouse_id=warehouse.id, lot_id=lot.id if lot else None, source_type=data.source_type, source_id=data.source_id, quantity=requested, status='active', reserved_at=utcnow(), expires_at=data.expires_at)
    session.add(row)
    if lot:
        lot.reserved_quantity = quantity(lot.reserved_quantity + requested)
        lot.version += 1
    session.flush()
    response = {'reservation': model_to_dict(row), 'available_after': str(quantity(available - requested)), 'lot': model_to_dict(lot) if lot else None}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='inventory.stock.reserved', resource_type='stock_reservation', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='StockReserved', aggregate_type='stock_reservation', aggregate_id=row.id, payload=response['reservation'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def transition_reservation(session: Session, tenant_id: str, reservation_id: str, *, action: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = session.scalar(select(StockReservation).where(StockReservation.id == reservation_id, StockReservation.tenant_id == tenant_id).with_for_update())
    if row is None:
        raise NotFoundError('Reserva não encontrada.', code='STOCK_RESERVATION_NOT_FOUND')
    if row.status != 'active':
        raise ConflictError('A reserva não está ativa.', code='STOCK_RESERVATION_NOT_ACTIVE')
    lot = _get_lot(session, tenant_id, row.lot_id, lock=True) if row.lot_id else None
    if action == 'release':
        row.status = 'released'
        row.released_at = utcnow()
        event_type = 'StockReservationReleased'
    elif action == 'consume':
        row.status = 'consumed'
        row.consumed_at = utcnow()
        event_type = 'StockReservationConsumed'
    else:
        raise ValidationError('Ação de reserva inválida.', code='INVALID_RESERVATION_ACTION')
    if lot:
        lot.reserved_quantity = quantity(max(Decimal('0'), lot.reserved_quantity - row.quantity))
        lot.version += 1
    row.version += 1
    session.flush()
    response = model_to_dict(row)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action=f'inventory.reservation.{action}', resource_type='stock_reservation', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type=event_type, aggregate_type='stock_reservation', aggregate_id=row.id, payload=response, correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    session.commit()
    return response


def create_inventory_count(session: Session, tenant_id: str, data: InventoryCountCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='inventory.count.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O inventário ainda está sendo criado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    warehouse = get_warehouse(session, tenant_id, data.warehouse_id)
    active = session.scalar(select(InventoryCount).where(InventoryCount.tenant_id == tenant_id, InventoryCount.warehouse_id == warehouse.id, InventoryCount.status.in_({'draft', 'counting'})))
    if active:
        raise ConflictError('Já existe inventário aberto para o depósito.', code='INVENTORY_COUNT_ALREADY_OPEN')
    conditions = [StockBalance.tenant_id == tenant_id, StockBalance.warehouse_id == warehouse.id]
    if data.product_ids:
        for product_id in data.product_ids:
            get_product(session, tenant_id, product_id)
        conditions.append(StockBalance.product_id.in_(data.product_ids))
    if not data.include_zero_balance:
        conditions.append(StockBalance.quantity != 0)
    balances = session.scalars(select(StockBalance).where(*conditions).order_by(StockBalance.product_id)).all()
    if not balances:
        raise ConflictError('Nenhum saldo foi encontrado para o inventário.', code='INVENTORY_COUNT_EMPTY')
    row = InventoryCount(tenant_id=tenant_id, institution_id=data.institution_id or warehouse.institution_id, unit_id=data.unit_id or warehouse.unit_id, count_number=f'INV-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}', warehouse_id=warehouse.id, status='counting', scope_json={'product_ids': data.product_ids, 'include_zero_balance': data.include_zero_balance}, started_at=utcnow())
    session.add(row)
    session.flush()
    items = []
    for balance in balances:
        child = InventoryCountItem(tenant_id=tenant_id, institution_id=row.institution_id, unit_id=row.unit_id, inventory_count_id=row.id, product_id=balance.product_id, lot_id=None, expected_quantity=quantity(balance.quantity), status='pending')
        session.add(child)
        items.append(child)
    session.flush()
    response = {'count': model_to_dict(row), 'items': [model_to_dict(item) for item in items]}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='inventory.count.started', resource_type='inventory_count', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='InventoryCountStarted', aggregate_type='inventory_count', aggregate_id=row.id, payload=response['count'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def inventory_count_detail(session: Session, tenant_id: str, count_id: str) -> dict[str, Any]:
    row = session.scalar(select(InventoryCount).where(InventoryCount.id == count_id, InventoryCount.tenant_id == tenant_id))
    if row is None:
        raise NotFoundError('Inventário não encontrado.', code='INVENTORY_COUNT_NOT_FOUND')
    items = session.scalars(select(InventoryCountItem).where(InventoryCountItem.tenant_id == tenant_id, InventoryCountItem.inventory_count_id == row.id).order_by(InventoryCountItem.product_id)).all()
    return {'count': model_to_dict(row), 'items': [model_to_dict(item) for item in items]}


def complete_inventory_count(session: Session, tenant_id: str, count_id: str, data: InventoryCountComplete, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = session.scalar(select(InventoryCount).where(InventoryCount.id == count_id, InventoryCount.tenant_id == tenant_id).with_for_update())
    if row is None:
        raise NotFoundError('Inventário não encontrado.', code='INVENTORY_COUNT_NOT_FOUND')
    if row.status != 'counting':
        raise ConflictError('O inventário não está em contagem.', code='INVENTORY_COUNT_NOT_OPEN')
    items = {item.id: item for item in session.scalars(select(InventoryCountItem).where(InventoryCountItem.tenant_id == tenant_id, InventoryCountItem.inventory_count_id == row.id)).all()}
    if set(items) != {entry.item_id for entry in data.items}:
        raise ValidationError('Informe a contagem de todos os itens.', code='INVENTORY_COUNT_ITEMS_MISMATCH')
    adjustments = []
    for entry in data.items:
        item = items[entry.item_id]
        counted = quantity(entry.counted_quantity)
        difference = quantity(counted - item.expected_quantity)
        item.counted_quantity = counted
        item.difference_quantity = difference
        item.status = 'counted'
        item.notes = entry.notes
        item.version += 1
        if difference != Decimal('0.0000'):
            balance, movement = change_stock(session, tenant_id=tenant_id, product_id=item.product_id, warehouse_id=row.warehouse_id, movement_type='inventory_adjustment_in' if difference > 0 else 'inventory_adjustment_out', amount=abs(difference), unit_cost=Decimal('0'), reference_type='inventory_count', reference_id=row.id, institution_id=row.institution_id, unit_id=row.unit_id)
            adjustments.append({'balance': model_to_dict(balance), 'movement': model_to_dict(movement)})
    row.status = 'completed'
    row.completed_at = utcnow()
    row.completed_by = actor.id
    row.reason = data.reason
    row.version += 1
    session.flush()
    response = {'count': model_to_dict(row), 'items': [model_to_dict(item) for item in items.values()], 'adjustments': adjustments}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='inventory.count.completed', resource_type='inventory_count', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, metadata={'reason': data.reason}, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='InventoryCountCompleted', aggregate_type='inventory_count', aggregate_id=row.id, payload={'count': response['count'], 'adjustments': adjustments}, correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    session.commit()
    return response


def list_lots(session: Session, tenant_id: str, *, product_id: str | None, warehouse_id: str | None, expiring_before: date | None, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions = [InventoryLot.tenant_id == tenant_id, InventoryLot.deleted_at.is_(None)]
    if product_id:
        conditions.append(InventoryLot.product_id == product_id)
    if warehouse_id:
        conditions.append(InventoryLot.warehouse_id == warehouse_id)
    if expiring_before:
        conditions.append(InventoryLot.expires_on.is_not(None))
        conditions.append(InventoryLot.expires_on <= expiring_before)
    if status:
        conditions.append(InventoryLot.status == status)
    if cursor:
        conditions.append(InventoryLot.id > cursor)
    rows = session.scalars(select(InventoryLot).where(*conditions).order_by(InventoryLot.id).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [model_to_dict(row) for row in rows], 'count': len(rows), 'next_cursor': rows[-1].id if has_more and rows else None}
