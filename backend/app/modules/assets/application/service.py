from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.modules.assets.presentation.schemas import (
    AssetCreate,
    AssetLoanCreate,
    AssetLoanReturn,
    AssetLocationCreate,
    AssetMaintenanceComplete,
    AssetMaintenanceCreate,
    AssetTransfer,
    DepreciationCalculate,
)
from backend.app.shared.application.audit import audit_tenant, emit_tenant_event
from backend.app.shared.application.idempotency import complete, reserve_tenant
from backend.app.shared.application.serialization import json_value, model_to_dict
from backend.app.shared.database.models_tenant import (
    Asset,
    AssetDepreciation,
    AssetLoan,
    AssetLocation,
    AssetMaintenance,
    AssetMovement,
    GoodsReceiptItem,
    Person,
    Product,
    Supplier,
)
from backend.app.shared.domain.dates import utcnow
from backend.app.shared.domain.errors import ConflictError, NotFoundError, ValidationError
from backend.app.shared.domain.ids import new_id
from backend.app.shared.security.permissions import Actor

CENT = Decimal('0.01')


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _location(session: Session, tenant_id: str, location_id: str) -> AssetLocation:
    row = session.scalar(select(AssetLocation).where(AssetLocation.id == location_id, AssetLocation.tenant_id == tenant_id, AssetLocation.deleted_at.is_(None)))
    if row is None:
        raise NotFoundError('Localização patrimonial não encontrada.', code='ASSET_LOCATION_NOT_FOUND')
    if row.status != 'active':
        raise ConflictError('A localização patrimonial não está ativa.', code='ASSET_LOCATION_INACTIVE')
    return row


def _asset(session: Session, tenant_id: str, asset_id: str, *, lock: bool = False) -> Asset:
    query = select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id, Asset.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise NotFoundError('Bem patrimonial não encontrado.', code='ASSET_NOT_FOUND')
    return row


def _person(session: Session, tenant_id: str, person_id: str | None) -> Person | None:
    if person_id is None:
        return None
    row = session.scalar(select(Person).where(Person.id == person_id, Person.tenant_id == tenant_id, Person.deleted_at.is_(None)))
    if row is None:
        raise ValidationError('Pessoa informada não pertence ao tenant.', code='PERSON_NOT_FOUND')
    return row


def _month_index(value: date) -> int:
    return value.year * 12 + value.month


def list_locations(session: Session, tenant_id: str, *, status: str | None, parent_id: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions = [AssetLocation.tenant_id == tenant_id, AssetLocation.deleted_at.is_(None)]
    if status:
        conditions.append(AssetLocation.status == status)
    if parent_id:
        conditions.append(AssetLocation.parent_id == parent_id)
    if cursor:
        conditions.append(AssetLocation.id > cursor)
    rows = session.scalars(select(AssetLocation).where(*conditions).order_by(AssetLocation.id).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [model_to_dict(row) for row in rows], 'count': len(rows), 'next_cursor': rows[-1].id if has_more and rows else None}


def create_location(session: Session, tenant_id: str, data: AssetLocationCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='assets.location.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A localização ainda está sendo criada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    code = data.code.strip().upper()
    if session.scalar(select(AssetLocation.id).where(AssetLocation.tenant_id == tenant_id, AssetLocation.code == code, AssetLocation.deleted_at.is_(None))):
        raise ConflictError('Já existe localização com este código.', code='ASSET_LOCATION_CODE_EXISTS')
    parent = _location(session, tenant_id, data.parent_id) if data.parent_id else None
    row = AssetLocation(tenant_id=tenant_id, institution_id=data.institution_id or (parent.institution_id if parent else None), unit_id=data.unit_id or (parent.unit_id if parent else None), code=code, name=data.name.strip(), parent_id=parent.id if parent else None, status='active')
    session.add(row)
    session.flush()
    response = model_to_dict(row)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.location.created', resource_type='asset_location', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetLocationCreated', aggregate_type='asset_location', aggregate_id=row.id, payload=response, correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def location_detail(session: Session, tenant_id: str, location_id: str) -> dict[str, Any]:
    row = _location(session, tenant_id, location_id)
    children = session.scalars(select(AssetLocation).where(AssetLocation.tenant_id == tenant_id, AssetLocation.parent_id == row.id, AssetLocation.deleted_at.is_(None)).order_by(AssetLocation.name)).all()
    assets = session.scalars(select(Asset).where(Asset.tenant_id == tenant_id, Asset.location_id == row.id, Asset.deleted_at.is_(None)).order_by(Asset.name).limit(200)).all()
    return {'location': model_to_dict(row), 'children': [model_to_dict(item) for item in children], 'assets': [model_to_dict(item) for item in assets]}


def list_assets(session: Session, tenant_id: str, *, status: str | None, location_id: str | None, responsible_person_id: str | None, search: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions = [Asset.tenant_id == tenant_id, Asset.deleted_at.is_(None)]
    if status:
        conditions.append(Asset.status == status)
    if location_id:
        conditions.append(Asset.location_id == location_id)
    if responsible_person_id:
        conditions.append(Asset.responsible_person_id == responsible_person_id)
    if search:
        pattern = f'%{search.strip()}%'
        conditions.append(Asset.name.ilike(pattern) | Asset.tag.ilike(pattern) | Asset.asset_number.ilike(pattern) | Asset.serial_number.ilike(pattern))
    if cursor:
        conditions.append(Asset.id > cursor)
    rows = session.scalars(select(Asset).where(*conditions).order_by(Asset.id).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [model_to_dict(row) for row in rows], 'count': len(rows), 'next_cursor': rows[-1].id if has_more and rows else None}


def create_asset(session: Session, tenant_id: str, data: AssetCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope='assets.asset.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O bem ainda está sendo criado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    location = _location(session, tenant_id, data.location_id)
    _person(session, tenant_id, data.responsible_person_id)
    tag = data.tag.strip().upper()
    if session.scalar(select(Asset.id).where(Asset.tenant_id == tenant_id, Asset.tag == tag, Asset.deleted_at.is_(None))):
        raise ConflictError('A etiqueta patrimonial já está cadastrada.', code='ASSET_TAG_EXISTS')
    product = None
    if data.product_id:
        product = session.scalar(select(Product).where(Product.id == data.product_id, Product.tenant_id == tenant_id, Product.deleted_at.is_(None)))
        if product is None:
            raise ValidationError('Produto não encontrado.', code='PRODUCT_NOT_FOUND')
    receipt_item = None
    if data.receipt_item_id:
        receipt_item = session.scalar(select(GoodsReceiptItem).where(GoodsReceiptItem.id == data.receipt_item_id, GoodsReceiptItem.tenant_id == tenant_id))
        if receipt_item is None:
            raise ValidationError('Item de recebimento não encontrado.', code='GOODS_RECEIPT_ITEM_NOT_FOUND')
        if product and receipt_item.product_id != product.id:
            raise ValidationError('O item recebido não corresponde ao produto do bem.', code='ASSET_RECEIPT_PRODUCT_MISMATCH')
        if product is None:
            product = session.scalar(select(Product).where(Product.id == receipt_item.product_id, Product.tenant_id == tenant_id))
    acquisition_cost = money(data.acquisition_cost)
    residual_value = money(data.residual_value)
    if residual_value > acquisition_cost:
        raise ValidationError('O valor residual não pode superar o custo de aquisição.', code='INVALID_ASSET_RESIDUAL_VALUE')
    row = Asset(
        tenant_id=tenant_id,
        institution_id=data.institution_id or location.institution_id,
        unit_id=data.unit_id or location.unit_id,
        asset_number=f'PAT-{utcnow():%Y%m%d}-{new_id().replace("-", "").upper()[-12:]}',
        tag=tag,
        product_id=product.id if product else None,
        receipt_item_id=receipt_item.id if receipt_item else None,
        name=data.name.strip(),
        description=data.description,
        serial_number=data.serial_number,
        location_id=location.id,
        responsible_person_id=data.responsible_person_id,
        status='active',
        acquisition_date=data.acquisition_date,
        acquisition_cost=acquisition_cost,
        useful_life_months=data.useful_life_months,
        residual_value=residual_value,
        accumulated_depreciation=Decimal('0.00'),
        warranty_until=data.warranty_until,
        metadata_json=json_value(data.metadata),
    )
    session.add(row)
    session.flush()
    movement = AssetMovement(tenant_id=tenant_id, institution_id=row.institution_id, unit_id=row.unit_id, asset_id=row.id, movement_type='acquisition', from_location_id=None, to_location_id=location.id, from_responsible_person_id=None, to_responsible_person_id=row.responsible_person_id, occurred_at=utcnow(), actor_id=actor.id, reason='Cadastro e incorporação do bem')
    session.add(movement)
    session.flush()
    response = {'asset': model_to_dict(row), 'movement': model_to_dict(movement)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.asset.created', resource_type='asset', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetRegistered', aggregate_type='asset', aggregate_id=row.id, payload=response['asset'], correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def asset_detail(session: Session, tenant_id: str, asset_id: str) -> dict[str, Any]:
    row = _asset(session, tenant_id, asset_id)
    movements = session.scalars(select(AssetMovement).where(AssetMovement.tenant_id == tenant_id, AssetMovement.asset_id == row.id).order_by(AssetMovement.occurred_at.desc())).all()
    maintenances = session.scalars(select(AssetMaintenance).where(AssetMaintenance.tenant_id == tenant_id, AssetMaintenance.asset_id == row.id).order_by(AssetMaintenance.created_at.desc())).all()
    loans = session.scalars(select(AssetLoan).where(AssetLoan.tenant_id == tenant_id, AssetLoan.asset_id == row.id).order_by(AssetLoan.loaned_at.desc())).all()
    depreciations = session.scalars(select(AssetDepreciation).where(AssetDepreciation.tenant_id == tenant_id, AssetDepreciation.asset_id == row.id).order_by(AssetDepreciation.competence)).all()
    return {'asset': model_to_dict(row), 'movements': [model_to_dict(item) for item in movements], 'maintenances': [model_to_dict(item) for item in maintenances], 'loans': [model_to_dict(item) for item in loans], 'depreciations': [model_to_dict(item) for item in depreciations]}


def transfer_asset(session: Session, tenant_id: str, asset_id: str, data: AssetTransfer, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = _asset(session, tenant_id, asset_id, lock=True)
    if row.status in {'disposed', 'lost', 'written_off'}:
        raise ConflictError('O bem não pode ser movimentado neste estado.', code='ASSET_NOT_TRANSFERABLE')
    location = _location(session, tenant_id, data.location_id)
    _person(session, tenant_id, data.responsible_person_id)
    if row.location_id == location.id and row.responsible_person_id == data.responsible_person_id:
        raise ConflictError('A localização e o responsável já são os informados.', code='ASSET_TRANSFER_NO_CHANGE')
    before = model_to_dict(row)
    movement = AssetMovement(tenant_id=tenant_id, institution_id=row.institution_id, unit_id=row.unit_id, asset_id=row.id, movement_type='transfer', from_location_id=row.location_id, to_location_id=location.id, from_responsible_person_id=row.responsible_person_id, to_responsible_person_id=data.responsible_person_id, occurred_at=utcnow(), actor_id=actor.id, reason=data.reason)
    row.location_id = location.id
    row.responsible_person_id = data.responsible_person_id
    row.version += 1
    session.add(movement)
    session.flush()
    response = {'asset': model_to_dict(row), 'movement': model_to_dict(movement)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.asset.transferred', resource_type='asset', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, before=before, after=response, metadata={'reason': data.reason}, ip_address=ip_address, institution_id=row.institution_id, unit_id=row.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetTransferred', aggregate_type='asset', aggregate_id=row.id, payload=response, correlation_id=correlation_id, institution_id=row.institution_id, unit_id=row.unit_id)
    session.commit()
    return response


def create_maintenance(session: Session, tenant_id: str, asset_id: str, data: AssetMaintenanceCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'assets.asset.{asset_id}.maintenance.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A manutenção ainda está sendo criada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    asset = _asset(session, tenant_id, asset_id, lock=True)
    if asset.status not in {'active', 'maintenance'}:
        raise ConflictError('O bem não aceita manutenção neste estado.', code='ASSET_MAINTENANCE_NOT_ALLOWED')
    if data.supplier_id and session.scalar(select(Supplier.id).where(Supplier.id == data.supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None))) is None:
        raise ValidationError('Fornecedor de manutenção não encontrado.', code='SUPPLIER_NOT_FOUND')
    row = AssetMaintenance(tenant_id=tenant_id, institution_id=asset.institution_id, unit_id=asset.unit_id, asset_id=asset.id, maintenance_type=data.maintenance_type.strip().lower(), status='scheduled', scheduled_on=data.scheduled_on, supplier_id=data.supplier_id, cost=money(data.cost), description=data.description)
    session.add(row)
    session.flush()
    response = model_to_dict(row)
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.maintenance.created', resource_type='asset_maintenance', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=asset.institution_id, unit_id=asset.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetMaintenanceScheduled', aggregate_type='asset', aggregate_id=asset.id, payload=response, correlation_id=correlation_id, institution_id=asset.institution_id, unit_id=asset.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def start_maintenance(session: Session, tenant_id: str, maintenance_id: str, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = session.scalar(select(AssetMaintenance).where(AssetMaintenance.id == maintenance_id, AssetMaintenance.tenant_id == tenant_id).with_for_update())
    if row is None:
        raise NotFoundError('Manutenção não encontrada.', code='ASSET_MAINTENANCE_NOT_FOUND')
    if row.status != 'scheduled':
        raise ConflictError('A manutenção não está agendada.', code='ASSET_MAINTENANCE_NOT_SCHEDULED')
    asset = _asset(session, tenant_id, row.asset_id, lock=True)
    if session.scalar(select(AssetLoan.id).where(AssetLoan.tenant_id == tenant_id, AssetLoan.asset_id == asset.id, AssetLoan.status == 'active')):
        raise ConflictError('O bem está emprestado e não pode entrar em manutenção.', code='ASSET_ACTIVE_LOAN')
    before = {'maintenance': model_to_dict(row), 'asset': model_to_dict(asset)}
    row.status = 'in_progress'
    row.started_at = utcnow()
    row.version += 1
    asset.status = 'maintenance'
    asset.version += 1
    session.flush()
    response = {'maintenance': model_to_dict(row), 'asset': model_to_dict(asset)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.maintenance.started', resource_type='asset_maintenance', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, before=before, after=response, ip_address=ip_address, institution_id=asset.institution_id, unit_id=asset.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetMaintenanceStarted', aggregate_type='asset', aggregate_id=asset.id, payload=response, correlation_id=correlation_id, institution_id=asset.institution_id, unit_id=asset.unit_id)
    session.commit()
    return response


def complete_maintenance(session: Session, tenant_id: str, maintenance_id: str, data: AssetMaintenanceComplete, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = session.scalar(select(AssetMaintenance).where(AssetMaintenance.id == maintenance_id, AssetMaintenance.tenant_id == tenant_id).with_for_update())
    if row is None:
        raise NotFoundError('Manutenção não encontrada.', code='ASSET_MAINTENANCE_NOT_FOUND')
    if row.status != 'in_progress':
        raise ConflictError('A manutenção não está em andamento.', code='ASSET_MAINTENANCE_NOT_IN_PROGRESS')
    asset = _asset(session, tenant_id, row.asset_id, lock=True)
    before = {'maintenance': model_to_dict(row), 'asset': model_to_dict(asset)}
    row.status = 'completed'
    row.completed_at = utcnow()
    row.result_notes = data.result_notes
    if data.actual_cost is not None:
        row.cost = money(data.actual_cost)
    row.version += 1
    asset.status = 'active'
    asset.version += 1
    session.flush()
    response = {'maintenance': model_to_dict(row), 'asset': model_to_dict(asset)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.maintenance.completed', resource_type='asset_maintenance', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, before=before, after=response, ip_address=ip_address, institution_id=asset.institution_id, unit_id=asset.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetMaintenanceCompleted', aggregate_type='asset', aggregate_id=asset.id, payload=response, correlation_id=correlation_id, institution_id=asset.institution_id, unit_id=asset.unit_id)
    session.commit()
    return response


def create_loan(session: Session, tenant_id: str, asset_id: str, data: AssetLoanCreate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'assets.asset.{asset_id}.loan.create', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('O empréstimo ainda está sendo criado.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    asset = _asset(session, tenant_id, asset_id, lock=True)
    if asset.status != 'active':
        raise ConflictError('Somente bens ativos podem ser emprestados.', code='ASSET_NOT_AVAILABLE_FOR_LOAN')
    _person(session, tenant_id, data.borrower_person_id)
    if session.scalar(select(AssetLoan.id).where(AssetLoan.tenant_id == tenant_id, AssetLoan.asset_id == asset.id, AssetLoan.status == 'active')):
        raise ConflictError('O bem já possui empréstimo ativo.', code='ASSET_ACTIVE_LOAN')
    row = AssetLoan(tenant_id=tenant_id, institution_id=asset.institution_id, unit_id=asset.unit_id, asset_id=asset.id, borrower_person_id=data.borrower_person_id, status='active', loaned_at=utcnow(), expected_return_at=data.expected_return_at, condition_out=data.condition_out, authorized_by=actor.id)
    session.add(row)
    asset.status = 'loaned'
    asset.responsible_person_id = data.borrower_person_id
    asset.version += 1
    session.flush()
    movement = AssetMovement(tenant_id=tenant_id, institution_id=asset.institution_id, unit_id=asset.unit_id, asset_id=asset.id, movement_type='loan', from_location_id=asset.location_id, to_location_id=asset.location_id, from_responsible_person_id=None, to_responsible_person_id=data.borrower_person_id, occurred_at=utcnow(), actor_id=actor.id, reason='Empréstimo patrimonial')
    session.add(movement)
    session.flush()
    response = {'loan': model_to_dict(row), 'asset': model_to_dict(asset), 'movement': model_to_dict(movement)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.loan.created', resource_type='asset_loan', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=asset.institution_id, unit_id=asset.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetLoaned', aggregate_type='asset', aggregate_id=asset.id, payload=response, correlation_id=correlation_id, institution_id=asset.institution_id, unit_id=asset.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response


def return_loan(session: Session, tenant_id: str, loan_id: str, data: AssetLoanReturn, *, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    row = session.scalar(select(AssetLoan).where(AssetLoan.id == loan_id, AssetLoan.tenant_id == tenant_id).with_for_update())
    if row is None:
        raise NotFoundError('Empréstimo patrimonial não encontrado.', code='ASSET_LOAN_NOT_FOUND')
    if row.status != 'active':
        raise ConflictError('O empréstimo não está ativo.', code='ASSET_LOAN_NOT_ACTIVE')
    asset = _asset(session, tenant_id, row.asset_id, lock=True)
    before = {'loan': model_to_dict(row), 'asset': model_to_dict(asset)}
    row.status = 'returned'
    row.returned_at = utcnow()
    row.condition_in = data.condition_in
    row.version += 1
    asset.status = 'active'
    asset.responsible_person_id = None
    asset.version += 1
    session.flush()
    movement = AssetMovement(tenant_id=tenant_id, institution_id=asset.institution_id, unit_id=asset.unit_id, asset_id=asset.id, movement_type='loan_return', from_location_id=asset.location_id, to_location_id=asset.location_id, from_responsible_person_id=row.borrower_person_id, to_responsible_person_id=None, occurred_at=utcnow(), actor_id=actor.id, reason='Devolução de empréstimo patrimonial')
    session.add(movement)
    session.flush()
    response = {'loan': model_to_dict(row), 'asset': model_to_dict(asset), 'movement': model_to_dict(movement)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.loan.returned', resource_type='asset_loan', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, before=before, after=response, ip_address=ip_address, institution_id=asset.institution_id, unit_id=asset.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetLoanReturned', aggregate_type='asset', aggregate_id=asset.id, payload=response, correlation_id=correlation_id, institution_id=asset.institution_id, unit_id=asset.unit_id)
    session.commit()
    return response


def calculate_depreciation(session: Session, tenant_id: str, asset_id: str, data: DepreciationCalculate, *, idempotency_key: str, actor: Actor, correlation_id: str, request_id: str, ip_address: str | None) -> dict[str, Any]:
    payload = data.model_dump(mode='json')
    idem, result = reserve_tenant(session, tenant_id=tenant_id, scope=f'assets.asset.{asset_id}.depreciation', key=idempotency_key, payload=payload)
    if result.existing:
        if result.response_json is None:
            raise ConflictError('A depreciação ainda está sendo calculada.', code='IDEMPOTENCY_IN_PROGRESS')
        return result.response_json
    asset = _asset(session, tenant_id, asset_id, lock=True)
    if not asset.useful_life_months:
        raise ConflictError('O bem não possui vida útil configurada.', code='ASSET_USEFUL_LIFE_NOT_CONFIGURED')
    year, month = (int(part) for part in data.competence.split('-'))
    try:
        competence_date = date(year, month, 1)
    except ValueError as exc:
        raise ValidationError('Competência inválida.', code='INVALID_COMPETENCE') from exc
    acquisition_month = date(asset.acquisition_date.year, asset.acquisition_date.month, 1)
    if competence_date < acquisition_month:
        raise ValidationError('A competência não pode anteceder a aquisição.', code='DEPRECIATION_BEFORE_ACQUISITION')
    existing = session.scalar(select(AssetDepreciation).where(AssetDepreciation.tenant_id == tenant_id, AssetDepreciation.asset_id == asset.id, AssetDepreciation.competence == data.competence))
    if existing:
        response = {'asset': model_to_dict(asset), 'depreciation': model_to_dict(existing)}
        complete(idem, status=200, response=response)
        session.commit()
        return response
    prior = session.scalars(select(AssetDepreciation).where(AssetDepreciation.tenant_id == tenant_id, AssetDepreciation.asset_id == asset.id).order_by(AssetDepreciation.competence)).all()
    if prior and data.competence <= prior[-1].competence:
        raise ConflictError('Calcule as competências em ordem cronológica.', code='DEPRECIATION_OUT_OF_ORDER')
    months_since_acquisition = _month_index(competence_date) - _month_index(acquisition_month) + 1
    if months_since_acquisition > asset.useful_life_months:
        amount = Decimal('0.00')
    else:
        depreciable = money(asset.acquisition_cost - asset.residual_value)
        monthly = money(depreciable / Decimal(asset.useful_life_months))
        remaining = money(depreciable - asset.accumulated_depreciation)
        amount = money(min(monthly, max(Decimal('0.00'), remaining)))
    accumulated = money(asset.accumulated_depreciation + amount)
    book_value = money(asset.acquisition_cost - accumulated)
    if book_value < asset.residual_value:
        amount = money(amount - (asset.residual_value - book_value))
        accumulated = money(asset.accumulated_depreciation + amount)
        book_value = money(asset.acquisition_cost - accumulated)
    row = AssetDepreciation(tenant_id=tenant_id, institution_id=asset.institution_id, unit_id=asset.unit_id, asset_id=asset.id, competence=data.competence, method='straight_line', amount=amount, accumulated_amount=accumulated, book_value=book_value, calculated_at=utcnow(), calculated_by=actor.id)
    session.add(row)
    asset.accumulated_depreciation = accumulated
    asset.version += 1
    session.flush()
    response = {'asset': model_to_dict(asset), 'depreciation': model_to_dict(row)}
    audit_tenant(session, tenant_id=tenant_id, actor=actor, action='assets.depreciation.calculated', resource_type='asset_depreciation', resource_id=row.id, correlation_id=correlation_id, request_id=request_id, after=response, ip_address=ip_address, institution_id=asset.institution_id, unit_id=asset.unit_id)
    emit_tenant_event(session, tenant_id=tenant_id, event_type='AssetDepreciationCalculated', aggregate_type='asset', aggregate_id=asset.id, payload=response, correlation_id=correlation_id, institution_id=asset.institution_id, unit_id=asset.unit_id)
    complete(idem, status=201, response=response)
    session.commit()
    return response
