from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.modules.finance.application.service import (
    cancel_charge_in_transaction,
    create_origin_charge_in_transaction,
)
from backend.app.modules.services.presentation.schemas import (
    BillingRuleCreate,
    CatalogCreate,
    CatalogUpdate,
    CompetenceGenerate,
    ExecutionCancel,
    ExecutionComplete,
    ExecutionCreate,
    ExecutionStart,
    FiscalProfileCreate,
    FiscalProfilePublish,
    OrderCancel,
    OrderConfirm,
    OrderCreate,
    PriceTableCreate,
    ServiceCreate,
    ServiceUpdate,
    SubscriptionCreate,
    SubscriptionDecision,
    VariantCreate,
    VariantUpdate,
)
from backend.app.shared.application.audit import audit_tenant, emit_tenant_event
from backend.app.shared.application.idempotency import complete, reserve_tenant
from backend.app.shared.application.serialization import json_value, model_to_dict
from backend.app.shared.database.models_tenant import (
    Charge,
    CostCenter,
    Enrollment,
    FinancialContract,
    Person,
    Service,
    ServiceBillingRule,
    ServiceCatalog,
    ServiceCompetence,
    ServiceExecution,
    ServiceFiscalEvent,
    ServiceFiscalProfile,
    ServiceOrder,
    ServiceOrderItem,
    ServicePriceTable,
    ServiceSubscription,
    ServiceVariant,
)
from backend.app.shared.domain.dates import utcnow
from backend.app.shared.domain.errors import ConflictError, NotFoundError, ValidationError
from backend.app.shared.domain.ids import new_id
from backend.app.shared.security.permissions import Actor

CENT = Decimal("0.01")
QTY = Decimal("0.0001")
ZERO = Decimal("0.00")


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(QTY, rounding=ROUND_HALF_UP)


def _month_add(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_period(competence_key: str) -> tuple[date, date]:
    year, month = (int(part) for part in competence_key.split("-", maxsplit=1))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _due_date(period_start: date, due_day: int) -> date:
    return date(period_start.year, period_start.month, min(due_day, calendar.monthrange(period_start.year, period_start.month)[1]))


def _get(
    session: Session,
    model: type[Any],
    tenant_id: str,
    row_id: str,
    *,
    code: str,
    message: str,
    lock: bool = False,
) -> Any:
    query = select(model).where(model.id == row_id, model.tenant_id == tenant_id, model.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise NotFoundError(message, code=code)
    return row


def _paginate(
    session: Session,
    model: type[Any],
    tenant_id: str,
    *,
    conditions: Iterable[Any] = (),
    cursor: str | None,
    limit: int,
    order_by: Any | None = None,
) -> dict[str, Any]:
    where = [model.tenant_id == tenant_id, model.deleted_at.is_(None), *conditions]
    if cursor:
        where.append(model.id > cursor)
    ordering = order_by if order_by is not None else model.id
    rows = session.scalars(select(model).where(*where).order_by(ordering).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [model_to_dict(row) for row in rows],
        "count": len(rows),
        "next_cursor": rows[-1].id if has_more and rows else None,
    }


def _reserve(
    session: Session,
    tenant_id: str,
    *,
    scope: str,
    key: str,
    payload: Any,
    message: str,
) -> tuple[Any, dict[str, Any] | list[Any] | None]:
    record, reservation = reserve_tenant(session, tenant_id=tenant_id, scope=scope, key=key, payload=payload)
    if reservation.existing:
        if reservation.response_json is None:
            raise ConflictError(message, code="IDEMPOTENCY_IN_PROGRESS")
        return record, reservation.response_json
    return record, None


def _etag(row: Any, expected_version: int) -> None:
    if row.version != expected_version:
        raise ConflictError("O registro foi alterado por outro usuário.", code="OPTIMISTIC_CONCURRENCY_CONFLICT")


def _audit(
    session: Session,
    *,
    tenant_id: str,
    actor: Actor,
    action: str,
    resource_type: str,
    row: Any,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
    before: Any = None,
    after: Any = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    audit_tenant(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=row.id,
        correlation_id=correlation_id,
        request_id=request_id,
        before=before,
        after=after,
        metadata=metadata,
        ip_address=ip_address,
        institution_id=getattr(row, "institution_id", None),
        unit_id=getattr(row, "unit_id", None),
    )


def _event(
    session: Session,
    *,
    tenant_id: str,
    row: Any,
    event_type: str,
    aggregate_type: str,
    payload: Any,
    correlation_id: str,
) -> None:
    emit_tenant_event(
        session,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=row.id,
        payload=json_value(payload),
        correlation_id=correlation_id,
        institution_id=getattr(row, "institution_id", None),
        unit_id=getattr(row, "unit_id", None),
    )


def _get_catalog(session: Session, tenant_id: str, catalog_id: str, *, active: bool = False) -> ServiceCatalog:
    row = _get(session, ServiceCatalog, tenant_id, catalog_id, code="SERVICE_CATALOG_NOT_FOUND", message="Catálogo de serviços não encontrado.")
    if active and row.status != "active":
        raise ConflictError("O catálogo de serviços não está ativo.", code="SERVICE_CATALOG_INACTIVE")
    return row


def _get_service(session: Session, tenant_id: str, service_id: str, *, active: bool = False) -> Service:
    row = _get(session, Service, tenant_id, service_id, code="SERVICE_NOT_FOUND", message="Serviço não encontrado.")
    if active and row.status != "active":
        raise ConflictError("O serviço não está ativo.", code="SERVICE_INACTIVE")
    return row


def _get_variant(session: Session, tenant_id: str, variant_id: str, *, service_id: str | None = None, active: bool = False) -> ServiceVariant:
    row = _get(session, ServiceVariant, tenant_id, variant_id, code="SERVICE_VARIANT_NOT_FOUND", message="Variação do serviço não encontrada.")
    if service_id and row.service_id != service_id:
        raise ConflictError("A variação não pertence ao serviço informado.", code="SERVICE_VARIANT_MISMATCH")
    if active and row.status != "active":
        raise ConflictError("A variação do serviço não está ativa.", code="SERVICE_VARIANT_INACTIVE")
    return row


def _get_rule(session: Session, tenant_id: str, rule_id: str, *, service_id: str | None = None) -> ServiceBillingRule:
    row = _get(session, ServiceBillingRule, tenant_id, rule_id, code="SERVICE_BILLING_RULE_NOT_FOUND", message="Regra de cobrança não encontrada.")
    if service_id and row.service_id != service_id:
        raise ConflictError("A regra de cobrança não pertence ao serviço.", code="SERVICE_BILLING_RULE_MISMATCH")
    if row.status != "active":
        raise ConflictError("A regra de cobrança não está ativa.", code="SERVICE_BILLING_RULE_INACTIVE")
    return row


def _get_subscription(session: Session, tenant_id: str, subscription_id: str, *, lock: bool = False) -> ServiceSubscription:
    return _get(
        session,
        ServiceSubscription,
        tenant_id,
        subscription_id,
        code="SERVICE_SUBSCRIPTION_NOT_FOUND",
        message="Assinatura de serviço não encontrada.",
        lock=lock,
    )


def _get_order(session: Session, tenant_id: str, order_id: str, *, lock: bool = False) -> ServiceOrder:
    return _get(
        session,
        ServiceOrder,
        tenant_id,
        order_id,
        code="SERVICE_ORDER_NOT_FOUND",
        message="Pedido de serviço não encontrado.",
        lock=lock,
    )


def _get_execution(session: Session, tenant_id: str, execution_id: str, *, lock: bool = False) -> ServiceExecution:
    return _get(
        session,
        ServiceExecution,
        tenant_id,
        execution_id,
        code="SERVICE_EXECUTION_NOT_FOUND",
        message="Execução de serviço não encontrada.",
        lock=lock,
    )


def _validate_scope_references(
    session: Session,
    tenant_id: str,
    *,
    person_id: str | None = None,
    enrollment_id: str | None = None,
    financial_contract_id: str | None = None,
    cost_center_id: str | None = None,
) -> None:
    if person_id:
        _get(session, Person, tenant_id, person_id, code="SERVICE_SUBSCRIBER_NOT_FOUND", message="Pessoa vinculada ao serviço não encontrada.")
    if enrollment_id:
        _get(session, Enrollment, tenant_id, enrollment_id, code="SERVICE_ENROLLMENT_NOT_FOUND", message="Matrícula vinculada ao serviço não encontrada.")
    if financial_contract_id:
        _get(
            session,
            FinancialContract,
            tenant_id,
            financial_contract_id,
            code="SERVICE_FINANCIAL_CONTRACT_NOT_FOUND",
            message="Contrato financeiro vinculado ao serviço não encontrado.",
        )
    if cost_center_id:
        _get(session, CostCenter, tenant_id, cost_center_id, code="SERVICE_COST_CENTER_NOT_FOUND", message="Centro de custo vinculado ao serviço não encontrado.")


def _profile_conditions(service_id: str, variant_id: str | None, valid_from: date, valid_until: date | None) -> list[Any]:
    upper = valid_until or date.max
    variant_condition = ServiceFiscalProfile.variant_id == variant_id if variant_id else ServiceFiscalProfile.variant_id.is_(None)
    return [
        ServiceFiscalProfile.service_id == service_id,
        variant_condition,
        ServiceFiscalProfile.valid_from <= upper,
        or_(ServiceFiscalProfile.valid_until.is_(None), ServiceFiscalProfile.valid_until >= valid_from),
    ]


def _price_conditions(service_id: str, variant_id: str | None, valid_from: date, valid_until: date | None) -> list[Any]:
    upper = valid_until or date.max
    variant_condition = ServicePriceTable.variant_id == variant_id if variant_id else ServicePriceTable.variant_id.is_(None)
    return [
        ServicePriceTable.service_id == service_id,
        variant_condition,
        ServicePriceTable.valid_from <= upper,
        or_(ServicePriceTable.valid_until.is_(None), ServicePriceTable.valid_until >= valid_from),
        ServicePriceTable.status == "active",
    ]


def _resolve_price(session: Session, tenant_id: str, service_id: str, variant_id: str | None, on_date: date) -> ServicePriceTable:
    base = [
        ServicePriceTable.tenant_id == tenant_id,
        ServicePriceTable.service_id == service_id,
        ServicePriceTable.status == "active",
        ServicePriceTable.valid_from <= on_date,
        or_(ServicePriceTable.valid_until.is_(None), ServicePriceTable.valid_until >= on_date),
        ServicePriceTable.deleted_at.is_(None),
    ]
    if variant_id:
        exact = session.scalar(
            select(ServicePriceTable)
            .where(*base, ServicePriceTable.variant_id == variant_id)
            .order_by(ServicePriceTable.valid_from.desc())
        )
        if exact:
            return exact
    fallback = session.scalar(
        select(ServicePriceTable)
        .where(*base, ServicePriceTable.variant_id.is_(None))
        .order_by(ServicePriceTable.valid_from.desc())
    )
    if fallback is None:
        raise ConflictError("Não existe preço vigente para o serviço.", code="SERVICE_PRICE_NOT_CONFIGURED")
    return fallback


def _resolve_fiscal_profile(
    session: Session,
    tenant_id: str,
    service_id: str,
    variant_id: str | None,
    on_date: date,
) -> ServiceFiscalProfile | None:
    base = [
        ServiceFiscalProfile.tenant_id == tenant_id,
        ServiceFiscalProfile.service_id == service_id,
        ServiceFiscalProfile.status == "published",
        ServiceFiscalProfile.valid_from <= on_date,
        or_(ServiceFiscalProfile.valid_until.is_(None), ServiceFiscalProfile.valid_until >= on_date),
        ServiceFiscalProfile.deleted_at.is_(None),
    ]
    if variant_id:
        exact = session.scalar(
            select(ServiceFiscalProfile)
            .where(*base, ServiceFiscalProfile.variant_id == variant_id)
            .order_by(ServiceFiscalProfile.valid_from.desc())
        )
        if exact:
            return exact
    return session.scalar(
        select(ServiceFiscalProfile)
        .where(*base, ServiceFiscalProfile.variant_id.is_(None))
        .order_by(ServiceFiscalProfile.valid_from.desc())
    )


def _fiscal_snapshot(service: Service, profile: ServiceFiscalProfile | None) -> dict[str, Any]:
    if not service.taxable:
        return {"classification_status": "not_taxable", "taxable": False}
    if profile is None:
        return {"classification_status": "missing", "taxable": True}
    required = {
        "nbs_code": profile.nbs_code,
        "lc116_code": profile.lc116_code,
        "municipal_service_code": profile.municipal_service_code,
        "cnae_code": profile.cnae_code,
        "cclass_trib": profile.cclass_trib,
    }
    missing = sorted(key for key, value in required.items() if not value)
    snapshot = model_to_dict(profile)
    snapshot["classification_status"] = "complete" if not missing else "incomplete"
    snapshot["missing_fields"] = missing
    snapshot["taxable"] = True
    return snapshot


def catalog_detail(session: Session, tenant_id: str, catalog_id: str) -> dict[str, Any]:
    row = _get_catalog(session, tenant_id, catalog_id)
    result = model_to_dict(row)
    result["services"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(Service)
            .where(Service.tenant_id == tenant_id, Service.catalog_id == row.id, Service.deleted_at.is_(None))
            .order_by(Service.name)
        ).all()
    ]
    return result


def service_detail(session: Session, tenant_id: str, service_id: str) -> dict[str, Any]:
    row = _get_service(session, tenant_id, service_id)
    result = model_to_dict(row)
    result["variants"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceVariant)
            .where(ServiceVariant.tenant_id == tenant_id, ServiceVariant.service_id == row.id, ServiceVariant.deleted_at.is_(None))
            .order_by(ServiceVariant.name)
        ).all()
    ]
    result["prices"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServicePriceTable)
            .where(ServicePriceTable.tenant_id == tenant_id, ServicePriceTable.service_id == row.id, ServicePriceTable.deleted_at.is_(None))
            .order_by(ServicePriceTable.valid_from.desc())
        ).all()
    ]
    result["billing_rules"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceBillingRule)
            .where(ServiceBillingRule.tenant_id == tenant_id, ServiceBillingRule.service_id == row.id, ServiceBillingRule.deleted_at.is_(None))
            .order_by(ServiceBillingRule.code)
        ).all()
    ]
    result["fiscal_profiles"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceFiscalProfile)
            .where(ServiceFiscalProfile.tenant_id == tenant_id, ServiceFiscalProfile.service_id == row.id, ServiceFiscalProfile.deleted_at.is_(None))
            .order_by(ServiceFiscalProfile.valid_from.desc())
        ).all()
    ]
    return result


def subscription_detail(session: Session, tenant_id: str, subscription_id: str) -> dict[str, Any]:
    row = _get_subscription(session, tenant_id, subscription_id)
    result = model_to_dict(row)
    result["competencies"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceCompetence)
            .where(ServiceCompetence.tenant_id == tenant_id, ServiceCompetence.subscription_id == row.id, ServiceCompetence.deleted_at.is_(None))
            .order_by(ServiceCompetence.period_start.desc())
        ).all()
    ]
    result["orders"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceOrder)
            .where(ServiceOrder.tenant_id == tenant_id, ServiceOrder.subscription_id == row.id, ServiceOrder.deleted_at.is_(None))
            .order_by(ServiceOrder.created_at.desc())
        ).all()
    ]
    return result


def order_detail(session: Session, tenant_id: str, order_id: str) -> dict[str, Any]:
    row = _get_order(session, tenant_id, order_id)
    result = model_to_dict(row)
    items = session.scalars(
        select(ServiceOrderItem)
        .where(ServiceOrderItem.tenant_id == tenant_id, ServiceOrderItem.order_id == row.id, ServiceOrderItem.deleted_at.is_(None))
        .order_by(ServiceOrderItem.created_at)
    ).all()
    result["items"] = [model_to_dict(item) for item in items]
    result["executions"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceExecution)
            .where(ServiceExecution.tenant_id == tenant_id, ServiceExecution.order_id == row.id, ServiceExecution.deleted_at.is_(None))
            .order_by(ServiceExecution.created_at)
        ).all()
    ]
    result["fiscal_events"] = [
        model_to_dict(item)
        for item in session.scalars(
            select(ServiceFiscalEvent)
            .where(ServiceFiscalEvent.tenant_id == tenant_id, ServiceFiscalEvent.order_id == row.id, ServiceFiscalEvent.deleted_at.is_(None))
            .order_by(ServiceFiscalEvent.requested_at)
        ).all()
    ]
    if row.charge_id:
        charge = session.scalar(select(Charge).where(Charge.tenant_id == tenant_id, Charge.id == row.charge_id, Charge.deleted_at.is_(None)))
        result["charge"] = model_to_dict(charge) if charge else None
    else:
        result["charge"] = None
    return result


# Catálogos e serviços ---------------------------------------------------------


def list_catalogs(session: Session, tenant_id: str, *, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    conditions = [ServiceCatalog.status == status] if status else []
    return _paginate(session, ServiceCatalog, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceCatalog.name)


def create_catalog(
    session: Session,
    tenant_id: str,
    data: CatalogCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope="services.catalog.create", key=idempotency_key, payload=payload, message="O catálogo ainda está sendo criado.")
    if existing is not None:
        return existing
    row = ServiceCatalog(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        code=data.code.upper(),
        name=data.name,
        description=data.description,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        status=data.status,
    )
    session.add(row)
    session.flush()
    result = catalog_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.catalog.created", resource_type="service_catalog", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceCatalogCreated", aggregate_type="service_catalog", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def update_catalog(
    session: Session,
    tenant_id: str,
    catalog_id: str,
    data: CatalogUpdate,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_catalog(session, tenant_id, catalog_id)
    _etag(row, data.expected_version)
    before = model_to_dict(row)
    updates = data.model_dump(exclude_unset=True)
    updates.pop("expected_version", None)
    for key, value in updates.items():
        setattr(row, key, value)
    if row.valid_from and row.valid_until and row.valid_until < row.valid_from:
        raise ValidationError("A vigência final não pode ser anterior à inicial.", code="INVALID_SERVICE_CATALOG_VALIDITY")
    row.version += 1
    session.flush()
    result = catalog_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.catalog.updated", resource_type="service_catalog", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceCatalogUpdated", aggregate_type="service_catalog", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def list_services(
    session: Session,
    tenant_id: str,
    *,
    catalog_id: str | None,
    status: str | None,
    service_type: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if catalog_id:
        conditions.append(Service.catalog_id == catalog_id)
    if status:
        conditions.append(Service.status == status)
    if service_type:
        conditions.append(Service.service_type == service_type)
    return _paginate(session, Service, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=Service.name)


def create_service(
    session: Session,
    tenant_id: str,
    data: ServiceCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope="services.service.create", key=idempotency_key, payload=payload, message="O serviço ainda está sendo criado.")
    if existing is not None:
        return existing
    _get_catalog(session, tenant_id, data.catalog_id, active=True)
    if data.cost_center_id:
        _validate_scope_references(session, tenant_id, cost_center_id=data.cost_center_id)
    row = Service(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        catalog_id=data.catalog_id,
        code=data.code.upper(),
        name=data.name,
        description=data.description,
        service_type=data.service_type,
        recurrence_type=data.recurrence_type,
        unit_of_measure=data.unit_of_measure,
        default_duration_minutes=data.default_duration_minutes,
        cost_center_id=data.cost_center_id,
        taxable=data.taxable,
        status=data.status,
        metadata_json=json_value(data.metadata),
    )
    session.add(row)
    session.flush()
    result = service_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.service.created", resource_type="service", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceCreated", aggregate_type="service", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def update_service(
    session: Session,
    tenant_id: str,
    service_id: str,
    data: ServiceUpdate,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_service(session, tenant_id, service_id)
    _etag(row, data.expected_version)
    before = service_detail(session, tenant_id, row.id)
    updates = data.model_dump(exclude_unset=True)
    updates.pop("expected_version", None)
    if "metadata" in updates:
        updates["metadata_json"] = json_value(updates.pop("metadata"))
    if updates.get("cost_center_id"):
        _validate_scope_references(session, tenant_id, cost_center_id=updates["cost_center_id"])
    for key, value in updates.items():
        setattr(row, key, value)
    row.version += 1
    session.flush()
    result = service_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.service.updated", resource_type="service", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceUpdated", aggregate_type="service", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def create_variant(
    session: Session,
    tenant_id: str,
    service_id: str,
    data: VariantCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope=f"services.variant.create:{service_id}", key=idempotency_key, payload=payload, message="A variação ainda está sendo criada.")
    if existing is not None:
        return existing
    service = _get_service(session, tenant_id, service_id)
    row = ServiceVariant(
        tenant_id=tenant_id,
        institution_id=data.institution_id or service.institution_id,
        unit_id=data.unit_id or service.unit_id,
        service_id=service.id,
        code=data.code.upper(),
        name=data.name,
        description=data.description,
        duration_minutes=data.duration_minutes,
        capacity=data.capacity,
        status=data.status,
        metadata_json=json_value(data.metadata),
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.variant.created", resource_type="service_variant", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceVariantCreated", aggregate_type="service_variant", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def update_variant(
    session: Session,
    tenant_id: str,
    variant_id: str,
    data: VariantUpdate,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_variant(session, tenant_id, variant_id)
    _etag(row, data.expected_version)
    before = model_to_dict(row)
    updates = data.model_dump(exclude_unset=True)
    updates.pop("expected_version", None)
    if "metadata" in updates:
        updates["metadata_json"] = json_value(updates.pop("metadata"))
    for key, value in updates.items():
        setattr(row, key, value)
    row.version += 1
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.variant.updated", resource_type="service_variant", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceVariantUpdated", aggregate_type="service_variant", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def create_fiscal_profile(
    session: Session,
    tenant_id: str,
    service_id: str,
    data: FiscalProfileCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope=f"services.fiscal_profile.create:{service_id}", key=idempotency_key, payload=payload, message="O perfil fiscal ainda está sendo criado.")
    if existing is not None:
        return existing
    service = _get_service(session, tenant_id, service_id)
    if data.variant_id:
        _get_variant(session, tenant_id, data.variant_id, service_id=service_id)
    overlap = session.scalar(
        select(ServiceFiscalProfile).where(
            ServiceFiscalProfile.tenant_id == tenant_id,
            ServiceFiscalProfile.deleted_at.is_(None),
            *_profile_conditions(service_id, data.variant_id, data.valid_from, data.valid_until),
        )
    )
    if overlap:
        raise ConflictError("Já existe perfil fiscal sobreposto para o serviço e variação.", code="SERVICE_FISCAL_PROFILE_OVERLAP")
    row = ServiceFiscalProfile(
        tenant_id=tenant_id,
        institution_id=data.institution_id or service.institution_id,
        unit_id=data.unit_id or service.unit_id,
        service_id=service.id,
        variant_id=data.variant_id,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        nbs_code=data.nbs_code,
        lc116_code=data.lc116_code,
        municipal_service_code=data.municipal_service_code,
        cnae_code=data.cnae_code,
        iss_rate=data.iss_rate,
        ibs_rate=data.ibs_rate,
        cbs_rate=data.cbs_rate,
        cclass_trib=data.cclass_trib,
        fiscal_trigger=data.fiscal_trigger,
        withholding_json=json_value(data.withholding),
        rules_snapshot_json=json_value(data.rules_snapshot),
        status="draft",
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    result.update(_fiscal_snapshot(service, row))
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.fiscal_profile.created", resource_type="service_fiscal_profile", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceFiscalProfileCreated", aggregate_type="service_fiscal_profile", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def publish_fiscal_profile(
    session: Session,
    tenant_id: str,
    profile_id: str,
    data: FiscalProfilePublish,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get(session, ServiceFiscalProfile, tenant_id, profile_id, code="SERVICE_FISCAL_PROFILE_NOT_FOUND", message="Perfil fiscal não encontrado.", lock=True)
    if row.status == "published":
        result = model_to_dict(row)
        result.update(_fiscal_snapshot(_get_service(session, tenant_id, row.service_id), row))
        return result
    service = _get_service(session, tenant_id, row.service_id)
    classification = _fiscal_snapshot(service, row)
    if classification["classification_status"] == "incomplete":
        raise ConflictError(
            "O perfil fiscal não pode ser publicado com classificação incompleta.",
            code="SERVICE_FISCAL_CLASSIFICATION_INCOMPLETE",
            errors=[{"field": field, "code": "REQUIRED", "message": "Campo fiscal obrigatório."} for field in classification["missing_fields"]],
        )
    before = model_to_dict(row)
    row.status = "published"
    row.published_at = utcnow()
    row.published_by = actor.id
    row.version += 1
    session.flush()
    result = model_to_dict(row)
    result.update(_fiscal_snapshot(service, row))
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.fiscal_profile.published", resource_type="service_fiscal_profile", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result, metadata={"notes": data.notes})
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceFiscalProfilePublished", aggregate_type="service_fiscal_profile", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def create_price(
    session: Session,
    tenant_id: str,
    service_id: str,
    data: PriceTableCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope=f"services.price.create:{service_id}", key=idempotency_key, payload=payload, message="O preço ainda está sendo criado.")
    if existing is not None:
        return existing
    service = _get_service(session, tenant_id, service_id)
    if data.variant_id:
        _get_variant(session, tenant_id, data.variant_id, service_id=service_id)
    overlap = session.scalar(
        select(ServicePriceTable).where(
            ServicePriceTable.tenant_id == tenant_id,
            ServicePriceTable.deleted_at.is_(None),
            *_price_conditions(service_id, data.variant_id, data.valid_from, data.valid_until),
        )
    )
    if overlap:
        raise ConflictError("Já existe preço ativo sobreposto para o serviço e variação.", code="SERVICE_PRICE_OVERLAP")
    row = ServicePriceTable(
        tenant_id=tenant_id,
        institution_id=data.institution_id or service.institution_id,
        unit_id=data.unit_id or service.unit_id,
        service_id=service.id,
        variant_id=data.variant_id,
        name=data.name,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        currency=data.currency.upper(),
        amount=money(data.amount),
        billing_frequency=data.billing_frequency,
        status=data.status,
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.price.created", resource_type="service_price", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServicePriceCreated", aggregate_type="service_price", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def create_billing_rule(
    session: Session,
    tenant_id: str,
    service_id: str,
    data: BillingRuleCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope=f"services.billing_rule.create:{service_id}", key=idempotency_key, payload=payload, message="A regra de cobrança ainda está sendo criada.")
    if existing is not None:
        return existing
    service = _get_service(session, tenant_id, service_id)
    if data.variant_id:
        _get_variant(session, tenant_id, data.variant_id, service_id=service_id)
    row = ServiceBillingRule(
        tenant_id=tenant_id,
        institution_id=data.institution_id or service.institution_id,
        unit_id=data.unit_id or service.unit_id,
        service_id=service.id,
        variant_id=data.variant_id,
        code=data.code.upper(),
        name=data.name,
        billing_trigger=data.billing_trigger,
        due_day=data.due_day,
        installment_count=data.installment_count,
        interval_months=data.interval_months,
        recognition_policy=data.recognition_policy,
        fiscal_trigger=data.fiscal_trigger,
        proration_policy=data.proration_policy,
        status=data.status,
        config_json=json_value(data.config),
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.billing_rule.created", resource_type="service_billing_rule", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceBillingRuleCreated", aggregate_type="service_billing_rule", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


# Pedidos ----------------------------------------------------------------------


def _allocate_order_discount(values: list[Decimal], total_discount: Decimal) -> list[Decimal]:
    discount = money(total_discount)
    total = money(sum(values, ZERO))
    if discount == ZERO:
        return [ZERO for _ in values]
    if discount >= total:
        raise ValidationError("O desconto do pedido deve ser inferior ao subtotal.", code="INVALID_SERVICE_ORDER_DISCOUNT")
    remaining_cents = int((discount * 100).to_integral_value())
    allocations: list[Decimal] = []
    for index, value in enumerate(values):
        if index == len(values) - 1:
            cents = remaining_cents
        else:
            cents = min(remaining_cents, int((discount * value / total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
        allocations.append(Decimal(cents) / 100)
        remaining_cents -= cents
    return allocations


def _build_order(
    session: Session,
    tenant_id: str,
    *,
    data: OrderCreate,
) -> ServiceOrder:
    _validate_scope_references(
        session,
        tenant_id,
        person_id=data.subscriber_person_id,
        enrollment_id=data.enrollment_id,
        financial_contract_id=data.financial_contract_id,
        cost_center_id=data.cost_center_id,
    )
    subscription: ServiceSubscription | None = None
    if data.subscription_id:
        subscription = _get_subscription(session, tenant_id, data.subscription_id)
        if subscription.subscriber_person_id != data.subscriber_person_id:
            raise ConflictError("A assinatura pertence a outro assinante.", code="SERVICE_SUBSCRIPTION_SUBSCRIBER_MISMATCH")
    if data.competence_id:
        competence = _get(session, ServiceCompetence, tenant_id, data.competence_id, code="SERVICE_COMPETENCE_NOT_FOUND", message="Competência de serviço não encontrada.")
        if subscription and competence.subscription_id != subscription.id:
            raise ConflictError("A competência não pertence à assinatura.", code="SERVICE_COMPETENCE_SUBSCRIPTION_MISMATCH")

    prepared: list[dict[str, Any]] = []
    line_nets: list[Decimal] = []
    for item in data.items:
        service = _get_service(session, tenant_id, item.service_id, active=True)
        variant = _get_variant(session, tenant_id, item.variant_id, service_id=service.id, active=True) if item.variant_id else None
        unit_price = money(item.unit_price) if item.unit_price is not None else money(_resolve_price(session, tenant_id, service.id, variant.id if variant else None, data.due_date).amount)
        gross = money(quantity(item.quantity) * unit_price)
        explicit_discount = money(item.discount_amount)
        if explicit_discount >= gross:
            raise ValidationError("O desconto do item deve ser inferior ao valor bruto.", code="INVALID_SERVICE_ORDER_ITEM_DISCOUNT")
        net = money(gross - explicit_discount)
        line_nets.append(net)
        profile = _resolve_fiscal_profile(session, tenant_id, service.id, variant.id if variant else None, data.due_date)
        prepared.append(
            {
                "service": service,
                "variant": variant,
                "description": item.description or (variant.name if variant else service.name),
                "quantity": quantity(item.quantity),
                "unit_price": unit_price,
                "explicit_discount": explicit_discount,
                "competence_start": item.competence_start,
                "competence_end": item.competence_end,
                "fiscal_snapshot": _fiscal_snapshot(service, profile),
            }
        )
    allocated = _allocate_order_discount(line_nets, money(data.discount_amount))
    subtotal = money(sum((money(item["quantity"] * item["unit_price"]) for item in prepared), ZERO))
    total = ZERO
    row = ServiceOrder(
        tenant_id=tenant_id,
        institution_id=data.institution_id,
        unit_id=data.unit_id,
        order_number=data.order_number,
        subscriber_person_id=data.subscriber_person_id,
        subscription_id=data.subscription_id,
        enrollment_id=data.enrollment_id,
        financial_contract_id=data.financial_contract_id,
        competence_id=data.competence_id,
        cost_center_id=data.cost_center_id,
        status="draft",
        currency=data.currency.upper(),
        subtotal=subtotal,
        discount_amount=money(data.discount_amount),
        total_amount=ZERO,
        due_date=data.due_date,
        installment_count=data.installment_count,
        fiscal_status="pending",
        notes=data.notes,
    )
    session.add(row)
    session.flush()
    for definition, allocated_discount in zip(prepared, allocated, strict=True):
        total_discount = money(definition["explicit_discount"] + allocated_discount)
        line_total = money(definition["quantity"] * definition["unit_price"] - total_discount)
        total = money(total + line_total)
        session.add(
            ServiceOrderItem(
                tenant_id=tenant_id,
                institution_id=data.institution_id,
                unit_id=data.unit_id,
                order_id=row.id,
                service_id=definition["service"].id,
                variant_id=definition["variant"].id if definition["variant"] else None,
                description=definition["description"],
                quantity=definition["quantity"],
                unit_price=definition["unit_price"],
                discount_amount=total_discount,
                total_amount=line_total,
                competence_start=definition["competence_start"],
                competence_end=definition["competence_end"],
                fiscal_profile_snapshot_json=json_value(definition["fiscal_snapshot"]),
                execution_status="pending",
                executed_quantity=Decimal("0.0000"),
            )
        )
    row.total_amount = total
    session.flush()
    return row


def list_orders(
    session: Session,
    tenant_id: str,
    *,
    status: str | None,
    subscriber_person_id: str | None,
    subscription_id: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(ServiceOrder.status == status)
    if subscriber_person_id:
        conditions.append(ServiceOrder.subscriber_person_id == subscriber_person_id)
    if subscription_id:
        conditions.append(ServiceOrder.subscription_id == subscription_id)
    return _paginate(session, ServiceOrder, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceOrder.created_at.desc())


def create_order(
    session: Session,
    tenant_id: str,
    data: OrderCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope="services.order.create", key=idempotency_key, payload=payload, message="O pedido de serviço ainda está sendo criado.")
    if existing is not None:
        return existing
    row = _build_order(session, tenant_id, data=data)
    result = order_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.order.created", resource_type="service_order", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceOrderCreated", aggregate_type="service_order", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def _create_fiscal_event_for_item(
    session: Session,
    *,
    tenant_id: str,
    order: ServiceOrder,
    item: ServiceOrderItem,
    trigger_type: str,
) -> ServiceFiscalEvent | None:
    snapshot = dict(item.fiscal_profile_snapshot_json or {})
    configured_trigger = snapshot.get("fiscal_trigger")
    if configured_trigger and configured_trigger != trigger_type:
        return None
    event_key = f"service:{order.id}:{item.id}:{trigger_type}"
    existing = session.scalar(
        select(ServiceFiscalEvent).where(
            ServiceFiscalEvent.tenant_id == tenant_id,
            ServiceFiscalEvent.event_key == event_key,
            ServiceFiscalEvent.deleted_at.is_(None),
        )
    )
    if existing:
        return existing
    classification = snapshot.get("classification_status", "missing")
    if classification in {"complete", "not_taxable"}:
        status = "not_configured"
        failure_code = "FISCAL_PROVIDER_NOT_CONFIGURED"
        failure_message = "Provider fiscal real não configurado para o tenant."
    else:
        status = "blocked_validation"
        failure_code = "SERVICE_FISCAL_CLASSIFICATION_INCOMPLETE"
        failure_message = "A classificação fiscal do serviço está incompleta."
    row = ServiceFiscalEvent(
        tenant_id=tenant_id,
        institution_id=order.institution_id,
        unit_id=order.unit_id,
        event_key=event_key,
        order_id=order.id,
        order_item_id=item.id,
        competence_id=order.competence_id,
        trigger_type=trigger_type,
        document_type="nfse",
        provider_code=None,
        status=status,
        payload_snapshot_json={
            "order_id": order.id,
            "order_item_id": item.id,
            "amount": format(money(item.total_amount), ".2f"),
            "fiscal_profile": snapshot,
        },
        failure_code=failure_code,
        failure_message=failure_message,
    )
    session.add(row)
    return row


def confirm_order(
    session: Session,
    tenant_id: str,
    order_id: str,
    data: OrderConfirm,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
    commit_transaction: bool = True,
) -> dict[str, Any]:
    row = _get_order(session, tenant_id, order_id, lock=True)
    if row.status in {"confirmed", "in_progress", "completed"}:
        return order_detail(session, tenant_id, row.id)
    if row.status != "draft":
        raise ConflictError("Somente pedido em rascunho pode ser confirmado.", code="INVALID_SERVICE_ORDER_CONFIRMATION_STATE")
    before = order_detail(session, tenant_id, row.id)
    items = session.scalars(
        select(ServiceOrderItem).where(
            ServiceOrderItem.tenant_id == tenant_id,
            ServiceOrderItem.order_id == row.id,
            ServiceOrderItem.deleted_at.is_(None),
        )
    ).all()
    if not items:
        raise ConflictError("O pedido não possui itens.", code="SERVICE_ORDER_EMPTY")
    charge = create_origin_charge_in_transaction(
        session,
        tenant_id,
        charge_number=f"SRV-{row.order_number}",
        responsible_person_id=row.subscriber_person_id,
        enrollment_id=row.enrollment_id,
        origin_type="service_order",
        origin_id=row.id,
        due_date=row.due_date,
        currency=row.currency,
        items=[
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_amount": item.unit_price,
                "discount_amount": item.discount_amount,
                "total_amount": item.total_amount,
                "accounting_code": "service_revenue",
                "metadata": {"service_id": item.service_id, "variant_id": item.variant_id, "order_item_id": item.id},
            }
            for item in items
        ],
        installment_count=row.installment_count,
        contract_id=row.financial_contract_id,
        cost_center_id=row.cost_center_id,
        institution_id=row.institution_id,
        unit_id=row.unit_id,
        actor=actor,
        correlation_id=correlation_id,
        request_id=request_id,
        ip_address=ip_address,
    )
    row.charge_id = charge.id
    row.status = "confirmed"
    row.confirmed_at = utcnow()
    row.confirmed_by = actor.id
    row.notes = data.notes or row.notes
    row.version += 1
    fiscal_statuses: set[str] = set()
    for item in items:
        event = _create_fiscal_event_for_item(session, tenant_id=tenant_id, order=row, item=item, trigger_type="billing")
        if event:
            fiscal_statuses.add(event.status)
        existing_execution = session.scalar(
            select(ServiceExecution).where(
                ServiceExecution.tenant_id == tenant_id,
                ServiceExecution.order_item_id == item.id,
                ServiceExecution.deleted_at.is_(None),
            )
        )
        if existing_execution is None:
            session.add(
                ServiceExecution(
                    tenant_id=tenant_id,
                    institution_id=row.institution_id,
                    unit_id=row.unit_id,
                    execution_number=f"EXE-{row.order_number}-{item.id.replace('-', '')[:8].upper()}",
                    order_id=row.id,
                    order_item_id=item.id,
                    subscription_id=row.subscription_id,
                    quantity=item.quantity,
                    status="scheduled",
                )
            )
    if "blocked_validation" in fiscal_statuses:
        row.fiscal_status = "blocked_validation"
    elif "not_configured" in fiscal_statuses:
        row.fiscal_status = "not_configured"
    else:
        row.fiscal_status = "not_required_or_deferred"
    session.flush()
    result = order_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.order.confirmed", resource_type="service_order", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceOrderConfirmed", aggregate_type="service_order", payload=result, correlation_id=correlation_id)
    if commit_transaction:
        session.commit()
    return result


def start_order(
    session: Session,
    tenant_id: str,
    order_id: str,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_order(session, tenant_id, order_id, lock=True)
    if row.status == "in_progress":
        return order_detail(session, tenant_id, row.id)
    if row.status != "confirmed":
        raise ConflictError("Somente pedido confirmado pode iniciar execução.", code="INVALID_SERVICE_ORDER_START_STATE")
    before = model_to_dict(row)
    row.status = "in_progress"
    row.started_at = utcnow()
    row.version += 1
    session.flush()
    result = order_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.order.started", resource_type="service_order", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceOrderStarted", aggregate_type="service_order", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def complete_order(
    session: Session,
    tenant_id: str,
    order_id: str,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_order(session, tenant_id, order_id, lock=True)
    if row.status == "completed":
        return order_detail(session, tenant_id, row.id)
    if row.status not in {"confirmed", "in_progress"}:
        raise ConflictError("O pedido não está em execução.", code="INVALID_SERVICE_ORDER_COMPLETION_STATE")
    items = session.scalars(
        select(ServiceOrderItem).where(
            ServiceOrderItem.tenant_id == tenant_id,
            ServiceOrderItem.order_id == row.id,
            ServiceOrderItem.deleted_at.is_(None),
        )
    ).all()
    incomplete = [item.id for item in items if quantity(item.executed_quantity) < quantity(item.quantity)]
    if incomplete:
        raise ConflictError("Existem itens sem execução integral.", code="SERVICE_ORDER_EXECUTION_INCOMPLETE", errors=[{"field": "items", "code": "INCOMPLETE", "message": item_id} for item_id in incomplete])
    before = model_to_dict(row)
    row.status = "completed"
    row.completed_at = utcnow()
    row.version += 1
    session.flush()
    result = order_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.order.completed", resource_type="service_order", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceOrderCompleted", aggregate_type="service_order", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def cancel_order(
    session: Session,
    tenant_id: str,
    order_id: str,
    data: OrderCancel,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_order(session, tenant_id, order_id, lock=True)
    if row.status == "cancelled":
        return order_detail(session, tenant_id, row.id)
    if row.status == "completed":
        raise ConflictError("Pedido concluído não pode ser cancelado; use fluxo de estorno específico.", code="COMPLETED_SERVICE_ORDER_CANNOT_BE_CANCELLED")
    completed_execution = session.scalar(
        select(ServiceExecution).where(
            ServiceExecution.tenant_id == tenant_id,
            ServiceExecution.order_id == row.id,
            ServiceExecution.status == "completed",
            ServiceExecution.deleted_at.is_(None),
        )
    )
    if completed_execution:
        raise ConflictError("Pedido com execução concluída não pode ser cancelado diretamente.", code="SERVICE_ORDER_HAS_COMPLETED_EXECUTION")
    before = order_detail(session, tenant_id, row.id)
    if row.charge_id:
        cancel_charge_in_transaction(
            session,
            tenant_id,
            row.charge_id,
            reason=data.reason,
            actor=actor,
            correlation_id=correlation_id,
            request_id=request_id,
            ip_address=ip_address,
        )
    executions = session.scalars(
        select(ServiceExecution).where(
            ServiceExecution.tenant_id == tenant_id,
            ServiceExecution.order_id == row.id,
            ServiceExecution.deleted_at.is_(None),
        )
    ).all()
    for execution in executions:
        if execution.status not in {"completed", "cancelled"}:
            execution.status = "cancelled"
            execution.notes = data.reason
            execution.version += 1
    fiscal_events = session.scalars(
        select(ServiceFiscalEvent).where(
            ServiceFiscalEvent.tenant_id == tenant_id,
            ServiceFiscalEvent.order_id == row.id,
            ServiceFiscalEvent.deleted_at.is_(None),
        )
    ).all()
    for event in fiscal_events:
        if event.status not in {"completed", "cancelled"}:
            event.status = "cancelled"
            event.failure_code = "SERVICE_ORDER_CANCELLED"
            event.failure_message = data.reason
            event.version += 1
    row.status = "cancelled"
    row.cancelled_at = utcnow()
    row.cancellation_reason = data.reason
    row.version += 1
    session.flush()
    result = order_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.order.cancelled", resource_type="service_order", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result, metadata={"reason": data.reason})
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceOrderCancelled", aggregate_type="service_order", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


# Execuções --------------------------------------------------------------------


def list_executions(
    session: Session,
    tenant_id: str,
    *,
    order_id: str | None,
    status: str | None,
    performer_person_id: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if order_id:
        conditions.append(ServiceExecution.order_id == order_id)
    if status:
        conditions.append(ServiceExecution.status == status)
    if performer_person_id:
        conditions.append(ServiceExecution.performer_person_id == performer_person_id)
    return _paginate(session, ServiceExecution, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceExecution.created_at.desc())


def create_execution(
    session: Session,
    tenant_id: str,
    order_id: str,
    data: ExecutionCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope=f"services.execution.create:{order_id}", key=idempotency_key, payload=payload, message="A execução ainda está sendo criada.")
    if existing is not None:
        return existing
    order = _get_order(session, tenant_id, order_id)
    if order.status not in {"confirmed", "in_progress"}:
        raise ConflictError("O pedido deve estar confirmado ou em execução.", code="SERVICE_ORDER_NOT_EXECUTABLE")
    item = _get(session, ServiceOrderItem, tenant_id, data.order_item_id, code="SERVICE_ORDER_ITEM_NOT_FOUND", message="Item do pedido não encontrado.")
    if item.order_id != order.id:
        raise ConflictError("O item não pertence ao pedido.", code="SERVICE_ORDER_ITEM_MISMATCH")
    allocated = session.scalar(
        select(func.coalesce(func.sum(ServiceExecution.quantity), 0)).where(
            ServiceExecution.tenant_id == tenant_id,
            ServiceExecution.order_item_id == item.id,
            ServiceExecution.status != "cancelled",
            ServiceExecution.deleted_at.is_(None),
        )
    )
    if quantity(allocated) + quantity(data.quantity) > quantity(item.quantity):
        raise ConflictError("A quantidade total de execuções supera o item.", code="SERVICE_EXECUTION_QUANTITY_EXCEEDED")
    if data.performer_person_id:
        _validate_scope_references(session, tenant_id, person_id=data.performer_person_id)
    row = ServiceExecution(
        tenant_id=tenant_id,
        institution_id=data.institution_id or order.institution_id,
        unit_id=data.unit_id or order.unit_id,
        execution_number=f"EXE-{order.order_number}-{new_id().replace('-', '')[:10].upper()}",
        order_id=order.id,
        order_item_id=item.id,
        subscription_id=order.subscription_id,
        scheduled_at=data.scheduled_at,
        quantity=quantity(data.quantity),
        status="scheduled",
        performer_person_id=data.performer_person_id,
        notes=data.notes,
    )
    session.add(row)
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.execution.created", resource_type="service_execution", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceExecutionScheduled", aggregate_type="service_execution", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def start_execution(
    session: Session,
    tenant_id: str,
    execution_id: str,
    data: ExecutionStart,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_execution(session, tenant_id, execution_id, lock=True)
    if row.status == "in_progress":
        return model_to_dict(row)
    if row.status != "scheduled":
        raise ConflictError("Somente execução agendada pode iniciar.", code="INVALID_SERVICE_EXECUTION_START_STATE")
    order = _get_order(session, tenant_id, row.order_id)
    if order.status == "confirmed":
        order.status = "in_progress"
        order.started_at = utcnow()
        order.version += 1
    before = model_to_dict(row)
    row.status = "in_progress"
    row.started_at = utcnow()
    row.notes = data.notes or row.notes
    row.version += 1
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.execution.started", resource_type="service_execution", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceExecutionStarted", aggregate_type="service_execution", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def complete_execution(
    session: Session,
    tenant_id: str,
    execution_id: str,
    data: ExecutionComplete,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_execution(session, tenant_id, execution_id, lock=True)
    if row.status == "completed":
        return model_to_dict(row)
    if row.status not in {"scheduled", "in_progress"}:
        raise ConflictError("A execução não está em estado que permita conclusão.", code="INVALID_SERVICE_EXECUTION_COMPLETION_STATE")
    item = _get(session, ServiceOrderItem, tenant_id, row.order_item_id, code="SERVICE_ORDER_ITEM_NOT_FOUND", message="Item do pedido não encontrado.", lock=True)
    order = _get_order(session, tenant_id, row.order_id, lock=True)
    completed_quantity = quantity(data.completed_quantity if data.completed_quantity is not None else row.quantity)
    if completed_quantity > quantity(row.quantity):
        raise ConflictError("A quantidade concluída supera a quantidade da execução.", code="SERVICE_EXECUTION_COMPLETED_QUANTITY_EXCEEDED")
    if quantity(item.executed_quantity) + completed_quantity > quantity(item.quantity):
        raise ConflictError("A execução supera a quantidade contratada do item.", code="SERVICE_ORDER_ITEM_EXECUTION_EXCEEDED")
    before = model_to_dict(row)
    row.quantity = completed_quantity
    row.status = "completed"
    row.started_at = row.started_at or utcnow()
    row.completed_at = utcnow()
    row.notes = data.notes or row.notes
    row.evidence_json = json_value(data.evidence)
    row.version += 1
    item.executed_quantity = quantity(item.executed_quantity) + completed_quantity
    item.execution_status = "completed" if quantity(item.executed_quantity) >= quantity(item.quantity) else "partially_executed"
    item.version += 1
    if order.status == "confirmed":
        order.status = "in_progress"
        order.started_at = row.started_at
        order.version += 1
    _create_fiscal_event_for_item(session, tenant_id=tenant_id, order=order, item=item, trigger_type="execution")
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.execution.completed", resource_type="service_execution", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceExecutionCompleted", aggregate_type="service_execution", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def cancel_execution(
    session: Session,
    tenant_id: str,
    execution_id: str,
    data: ExecutionCancel,
    *,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_execution(session, tenant_id, execution_id, lock=True)
    if row.status == "cancelled":
        return model_to_dict(row)
    if row.status == "completed":
        raise ConflictError("Execução concluída não pode ser cancelada.", code="COMPLETED_SERVICE_EXECUTION_CANNOT_BE_CANCELLED")
    before = model_to_dict(row)
    row.status = "cancelled"
    row.notes = data.reason
    row.version += 1
    session.flush()
    result = model_to_dict(row)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.execution.cancelled", resource_type="service_execution", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result, metadata={"reason": data.reason})
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceExecutionCancelled", aggregate_type="service_execution", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


# Assinaturas e competências ---------------------------------------------------


def list_subscriptions(
    session: Session,
    tenant_id: str,
    *,
    status: str | None,
    subscriber_person_id: str | None,
    service_id: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(ServiceSubscription.status == status)
    if subscriber_person_id:
        conditions.append(ServiceSubscription.subscriber_person_id == subscriber_person_id)
    if service_id:
        conditions.append(ServiceSubscription.service_id == service_id)
    return _paginate(session, ServiceSubscription, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceSubscription.created_at.desc())


def create_subscription(
    session: Session,
    tenant_id: str,
    data: SubscriptionCreate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope="services.subscription.create", key=idempotency_key, payload=payload, message="A assinatura ainda está sendo criada.")
    if existing is not None:
        return existing
    service = _get_service(session, tenant_id, data.service_id, active=True)
    variant = _get_variant(session, tenant_id, data.variant_id, service_id=service.id, active=True) if data.variant_id else None
    rule = _get_rule(session, tenant_id, data.billing_rule_id, service_id=service.id)
    if rule.variant_id and rule.variant_id != (variant.id if variant else None):
        raise ConflictError("A regra de cobrança não corresponde à variação.", code="SERVICE_BILLING_RULE_VARIANT_MISMATCH")
    _validate_scope_references(
        session,
        tenant_id,
        person_id=data.subscriber_person_id,
        enrollment_id=data.enrollment_id,
        financial_contract_id=data.financial_contract_id,
        cost_center_id=service.cost_center_id,
    )
    unit_price = money(data.unit_price) if data.unit_price is not None else money(_resolve_price(session, tenant_id, service.id, variant.id if variant else None, data.starts_on).amount)
    gross = money(quantity(data.quantity) * unit_price)
    discount = money(data.discount_amount)
    if discount >= gross:
        raise ValidationError("O desconto da assinatura deve ser inferior ao valor do ciclo.", code="INVALID_SERVICE_SUBSCRIPTION_DISCOUNT")
    row = ServiceSubscription(
        tenant_id=tenant_id,
        institution_id=data.institution_id or service.institution_id,
        unit_id=data.unit_id or service.unit_id,
        subscription_number=data.subscription_number,
        service_id=service.id,
        variant_id=variant.id if variant else None,
        subscriber_person_id=data.subscriber_person_id,
        enrollment_id=data.enrollment_id,
        financial_contract_id=data.financial_contract_id,
        billing_rule_id=rule.id,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        quantity=quantity(data.quantity),
        unit_price=unit_price,
        discount_amount=discount,
        cycle_amount=money(gross - discount),
        next_competence_on=data.next_competence_on or data.starts_on,
        auto_renew=data.auto_renew,
        status="draft",
    )
    session.add(row)
    session.flush()
    result = subscription_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.subscription.created", resource_type="service_subscription", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=row, event_type="ServiceSubscriptionCreated", aggregate_type="service_subscription", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


def _change_subscription_status(
    session: Session,
    tenant_id: str,
    subscription_id: str,
    *,
    allowed: set[str],
    target: str,
    reason: str | None,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    row = _get_subscription(session, tenant_id, subscription_id, lock=True)
    if row.status == target:
        return subscription_detail(session, tenant_id, row.id)
    if row.status not in allowed:
        raise ConflictError("A assinatura não está em estado que permita a transição.", code="INVALID_SERVICE_SUBSCRIPTION_STATE")
    before = model_to_dict(row)
    row.status = target
    row.version += 1
    if target == "suspended":
        row.suspended_at = utcnow()
    elif target == "active":
        row.suspended_at = None
    elif target == "cancelled":
        row.cancelled_at = utcnow()
        row.cancellation_reason = reason
    session.flush()
    result = subscription_detail(session, tenant_id, row.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action=f"services.subscription.{target}", resource_type="service_subscription", row=row, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, before=before, after=result, metadata={"reason": reason})
    _event(session, tenant_id=tenant_id, row=row, event_type=f"ServiceSubscription{target.title()}", aggregate_type="service_subscription", payload=result, correlation_id=correlation_id)
    session.commit()
    return result


def activate_subscription(session: Session, tenant_id: str, subscription_id: str, data: SubscriptionDecision, **context: Any) -> dict[str, Any]:
    return _change_subscription_status(session, tenant_id, subscription_id, allowed={"draft", "suspended"}, target="active", reason=data.reason, **context)


def suspend_subscription(session: Session, tenant_id: str, subscription_id: str, data: SubscriptionDecision, **context: Any) -> dict[str, Any]:
    return _change_subscription_status(session, tenant_id, subscription_id, allowed={"active"}, target="suspended", reason=data.reason, **context)


def resume_subscription(session: Session, tenant_id: str, subscription_id: str, data: SubscriptionDecision, **context: Any) -> dict[str, Any]:
    return _change_subscription_status(session, tenant_id, subscription_id, allowed={"suspended"}, target="active", reason=data.reason, **context)


def cancel_subscription(session: Session, tenant_id: str, subscription_id: str, data: SubscriptionDecision, **context: Any) -> dict[str, Any]:
    if not data.reason:
        raise ValidationError("Informe o motivo do cancelamento.", code="SERVICE_SUBSCRIPTION_CANCELLATION_REASON_REQUIRED")
    return _change_subscription_status(session, tenant_id, subscription_id, allowed={"draft", "active", "suspended"}, target="cancelled", reason=data.reason, **context)


def generate_competence(
    session: Session,
    tenant_id: str,
    subscription_id: str,
    data: CompetenceGenerate,
    *,
    idempotency_key: str,
    actor: Actor,
    correlation_id: str,
    request_id: str,
    ip_address: str | None,
) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    idem, existing = _reserve(session, tenant_id, scope=f"services.competence.generate:{subscription_id}", key=idempotency_key, payload=payload, message="A competência ainda está sendo gerada.")
    if existing is not None:
        return existing
    subscription = _get_subscription(session, tenant_id, subscription_id, lock=True)
    if subscription.status != "active":
        raise ConflictError("Somente assinatura ativa pode gerar competência.", code="SERVICE_SUBSCRIPTION_NOT_ACTIVE")
    period_start, period_end = _month_period(data.competence_key)
    if period_end < subscription.starts_on or (subscription.ends_on and period_start > subscription.ends_on):
        raise ConflictError("A competência está fora da vigência da assinatura.", code="SERVICE_COMPETENCE_OUTSIDE_SUBSCRIPTION")
    existing_competence = session.scalar(
        select(ServiceCompetence).where(
            ServiceCompetence.tenant_id == tenant_id,
            ServiceCompetence.subscription_id == subscription.id,
            ServiceCompetence.competence_key == data.competence_key,
            ServiceCompetence.deleted_at.is_(None),
        )
    )
    if existing_competence and not data.force:
        result = model_to_dict(existing_competence)
        result["order"] = order_detail(session, tenant_id, existing_competence.order_id) if existing_competence.order_id else None
        complete(idem, status=200, response=result)
        session.commit()
        return result
    if existing_competence and data.force:
        raise ConflictError("A competência já existe; use reprocessamento específico após cancelar seus efeitos.", code="SERVICE_COMPETENCE_ALREADY_EXISTS")
    service = _get_service(session, tenant_id, subscription.service_id, active=True)
    rule = _get_rule(session, tenant_id, subscription.billing_rule_id, service_id=service.id)
    due = data.due_date or _due_date(period_start, rule.due_day)
    competence = ServiceCompetence(
        tenant_id=tenant_id,
        institution_id=subscription.institution_id,
        unit_id=subscription.unit_id,
        subscription_id=subscription.id,
        competence_key=data.competence_key,
        period_start=period_start,
        period_end=period_end,
        due_date=due,
        amount=subscription.cycle_amount,
        status="pending",
    )
    session.add(competence)
    session.flush()
    order_data = OrderCreate(
        order_number=f"SUB-{subscription.subscription_number}-{data.competence_key}",
        subscriber_person_id=subscription.subscriber_person_id,
        subscription_id=subscription.id,
        enrollment_id=subscription.enrollment_id,
        financial_contract_id=subscription.financial_contract_id,
        competence_id=competence.id,
        cost_center_id=service.cost_center_id,
        currency="BRL",
        discount_amount=subscription.discount_amount,
        due_date=due,
        installment_count=rule.installment_count,
        items=[
            {
                "service_id": service.id,
                "variant_id": subscription.variant_id,
                "quantity": subscription.quantity,
                "unit_price": subscription.unit_price,
                "discount_amount": Decimal("0.00"),
                "competence_start": period_start,
                "competence_end": period_end,
            }
        ],
        notes=f"Competência {data.competence_key} da assinatura {subscription.subscription_number}",
        institution_id=subscription.institution_id,
        unit_id=subscription.unit_id,
    )
    order = _build_order(session, tenant_id, data=order_data)
    competence.order_id = order.id
    session.flush()
    confirmed = confirm_order(
        session,
        tenant_id,
        order.id,
        OrderConfirm(notes="Gerado automaticamente pela competência da assinatura."),
        actor=actor,
        correlation_id=correlation_id,
        request_id=request_id,
        ip_address=ip_address,
        commit_transaction=False,
    )
    competence = _get(session, ServiceCompetence, tenant_id, competence.id, code="SERVICE_COMPETENCE_NOT_FOUND", message="Competência não encontrada.", lock=True)
    competence.charge_id = confirmed.get("charge_id")
    competence.status = "billed"
    competence.billed_at = utcnow()
    competence.version += 1
    subscription = _get_subscription(session, tenant_id, subscription.id, lock=True)
    subscription.next_competence_on = _month_add(period_start, rule.interval_months)
    subscription.version += 1
    session.flush()
    result = model_to_dict(competence)
    result["order"] = order_detail(session, tenant_id, order.id)
    _audit(session, tenant_id=tenant_id, actor=actor, action="services.competence.generated", resource_type="service_competence", row=competence, correlation_id=correlation_id, request_id=request_id, ip_address=ip_address, after=result)
    _event(session, tenant_id=tenant_id, row=competence, event_type="ServiceCompetenceBilled", aggregate_type="service_competence", payload=result, correlation_id=correlation_id)
    complete(idem, status=201, response=result)
    session.commit()
    return result


# Consultas operacionais -------------------------------------------------------


def list_fiscal_events(
    session: Session,
    tenant_id: str,
    *,
    status: str | None,
    order_id: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if status:
        conditions.append(ServiceFiscalEvent.status == status)
    if order_id:
        conditions.append(ServiceFiscalEvent.order_id == order_id)
    return _paginate(session, ServiceFiscalEvent, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceFiscalEvent.requested_at.desc())


def dashboard(session: Session, tenant_id: str) -> dict[str, Any]:
    def count(model: type[Any], *conditions: Any) -> int:
        return int(
            session.scalar(
                select(func.count(model.id)).where(
                    model.tenant_id == tenant_id,
                    model.deleted_at.is_(None),
                    *conditions,
                )
            )
            or 0
        )

    active_subscriptions = count(ServiceSubscription, ServiceSubscription.status == "active")
    open_orders = count(ServiceOrder, ServiceOrder.status.in_(["draft", "confirmed", "in_progress"]))
    pending_executions = count(ServiceExecution, ServiceExecution.status.in_(["scheduled", "in_progress"]))
    blocked_fiscal = count(ServiceFiscalEvent, ServiceFiscalEvent.status == "blocked_validation")
    not_configured_fiscal = count(ServiceFiscalEvent, ServiceFiscalEvent.status == "not_configured")
    billed_total = money(
        session.scalar(
            select(func.coalesce(func.sum(ServiceOrder.total_amount), 0)).where(
                ServiceOrder.tenant_id == tenant_id,
                ServiceOrder.status.in_(["confirmed", "in_progress", "completed"]),
                ServiceOrder.deleted_at.is_(None),
            )
        )
        or ZERO
    )
    return {
        "catalogs": count(ServiceCatalog),
        "services": count(Service),
        "active_subscriptions": active_subscriptions,
        "open_orders": open_orders,
        "pending_executions": pending_executions,
        "fiscal": {"blocked_validation": blocked_fiscal, "not_configured": not_configured_fiscal},
        "billed_total": format(billed_total, ".2f"),
    }


def list_variants(
    session: Session,
    tenant_id: str,
    *,
    service_id: str | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if service_id:
        conditions.append(ServiceVariant.service_id == service_id)
    if status:
        conditions.append(ServiceVariant.status == status)
    return _paginate(session, ServiceVariant, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceVariant.name)


def list_fiscal_profiles(
    session: Session,
    tenant_id: str,
    *,
    service_id: str | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if service_id:
        conditions.append(ServiceFiscalProfile.service_id == service_id)
    if status:
        conditions.append(ServiceFiscalProfile.status == status)
    return _paginate(session, ServiceFiscalProfile, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceFiscalProfile.valid_from.desc())


def fiscal_profile_detail(session: Session, tenant_id: str, profile_id: str) -> dict[str, Any]:
    row = _get(session, ServiceFiscalProfile, tenant_id, profile_id, code="SERVICE_FISCAL_PROFILE_NOT_FOUND", message="Perfil fiscal não encontrado.")
    service = _get_service(session, tenant_id, row.service_id)
    result = model_to_dict(row)
    result.update(_fiscal_snapshot(service, row))
    return result


def list_prices(
    session: Session,
    tenant_id: str,
    *,
    service_id: str | None,
    status: str | None,
    on_date: date | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if service_id:
        conditions.append(ServicePriceTable.service_id == service_id)
    if status:
        conditions.append(ServicePriceTable.status == status)
    if on_date:
        conditions.extend(
            [
                ServicePriceTable.valid_from <= on_date,
                or_(ServicePriceTable.valid_until.is_(None), ServicePriceTable.valid_until >= on_date),
            ]
        )
    return _paginate(session, ServicePriceTable, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServicePriceTable.valid_from.desc())


def list_billing_rules(
    session: Session,
    tenant_id: str,
    *,
    service_id: str | None,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    conditions: list[Any] = []
    if service_id:
        conditions.append(ServiceBillingRule.service_id == service_id)
    if status:
        conditions.append(ServiceBillingRule.status == status)
    return _paginate(session, ServiceBillingRule, tenant_id, conditions=conditions, cursor=cursor, limit=limit, order_by=ServiceBillingRule.code)
