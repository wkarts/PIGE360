from __future__ import annotations

import calendar
import hashlib
import hmac
import io
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from fastapi import Request
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.modules.operations.common import dumps, loads
from app.modules.services.presentation.vertical_schemas import (
    BillingRuleCreate,
    CatalogCreate,
    CatalogUpdate,
    CompetenceGenerate,
    ExecutionCancel,
    ExecutionComplete,
    ExecutionCreate,
    ExecutionStart,
    FiscalProfileCreate,
    OrderCancel,
    OrderConfirm,
    PriceTableCreate,
    ServiceCreateUnified,
    ServiceOrderCreateUnified,
    ServiceReceiptCreate,
    ServiceReceiptVoid,
    ServiceUpdate,
    SubscriptionCreate,
    SubscriptionDecision,
    VariantCreate,
    VariantUpdate,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

CENT = Decimal("0.01")
QTY = Decimal("0.0001")


def quantity(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(QTY, rounding=ROUND_HALF_UP)


def _body(data: Any) -> dict[str, Any]:
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json")
    return dict(data)


def _status(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "state" in result:
        result.setdefault("status", result["state"])
    for key, default in (
        ("metadata_json", {}),
        ("fiscal_profile_json", {}),
        ("withholding_json", {}),
        ("rules_snapshot_json", {}),
        ("config_json", {}),
        ("evidence_json", {}),
        ("payload_snapshot_json", {}),
        ("snapshot_json", {}),
    ):
        if key in result:
            result[key.removesuffix("_json")] = loads(result[key], default)
    return result


def _one(conn: Any, sql: str, params: Iterable[Any], code: str, message: str) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, message, 404)
    return dict(row)


def _audit(
    conn: Any,
    *,
    tenant_id: str,
    user: CurrentUser,
    request: Request,
    action: str,
    aggregate_type: str,
    aggregate_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    add_audit(
        conn,
        tenant_id=tenant_id,
        actor_id=user.id,
        action=action,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        correlation_id=request.state.correlation_id,
        before=before,
        after=after,
        reason=reason,
    )


def _event(
    conn: Any,
    *,
    tenant_id: str,
    request: Request,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> None:
    add_outbox(
        conn,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )


def _cached(conn: Any, scope: str, key: str | None, payload: dict[str, Any]) -> tuple[int, Any] | None:
    return get_idempotent(conn, scope, key, payload) if key else None


def _save(conn: Any, scope: str, key: str | None, payload: dict[str, Any], status: int, result: Any) -> None:
    if key:
        save_idempotent(conn, scope, key, payload, status, result)


def _ensure_scope(conn: Any, tenant_id: str, institution_id: str | None, unit_id: str | None) -> None:
    if institution_id:
        _one(
            conn,
            "SELECT id FROM institutions WHERE tenant_id=? AND id=? AND state='active'",
            (tenant_id, institution_id),
            "INSTITUTION_NOT_FOUND",
            "Instituição não localizada ou inativa.",
        )
    if unit_id:
        unit = _one(
            conn,
            "SELECT id,institution_id FROM units WHERE tenant_id=? AND id=? AND state='active'",
            (tenant_id, unit_id),
            "UNIT_NOT_FOUND",
            "Unidade não localizada ou inativa.",
        )
        if institution_id and unit.get("institution_id") != institution_id:
            raise DomainError("UNIT_SCOPE_MISMATCH", "A unidade não pertence à instituição informada.", 409)


def _ensure_person(conn: Any, tenant_id: str, person_id: str | None) -> None:
    if person_id:
        _one(
            conn,
            "SELECT id FROM people WHERE tenant_id=? AND id=? AND state='active'",
            (tenant_id, person_id),
            "PERSON_NOT_FOUND",
            "Pessoa não localizada ou inativa.",
        )


def _month_period(key: str) -> tuple[date, date]:
    year, month = (int(value) for value in key.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _due_date(period_start: date, due_day: int) -> date:
    return date(period_start.year, period_start.month, min(due_day, calendar.monthrange(period_start.year, period_start.month)[1]))


def _month_add(value: date, months: int) -> date:
    idx = value.year * 12 + value.month - 1 + months
    year, month_idx = divmod(idx, 12)
    month = month_idx + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _normalize_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _price_for(conn: Any, tenant_id: str, service_id: str, variant_id: str | None, on_date: date) -> Decimal:
    rows = conn.execute(
        "SELECT * FROM service_price_tables WHERE tenant_id=? AND service_id=? AND state='active' "
        "ORDER BY valid_from DESC,created_at DESC",
        (tenant_id, service_id),
    ).fetchall()
    matches: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if (row.get("variant_id") or None) != (variant_id or None):
            continue
        start = _normalize_date(row.get("valid_from"))
        end = _normalize_date(row.get("valid_until"))
        if start and start <= on_date and (end is None or end >= on_date):
            matches.append(row)
    if matches:
        return money(matches[0]["amount"])
    service = _one(
        conn,
        "SELECT price FROM services WHERE tenant_id=? AND id=? AND state='active'",
        (tenant_id, service_id),
        "SERVICE_NOT_FOUND",
        "Serviço não localizado ou inativo.",
    )
    legacy_price = money(service.get("price") or 0)
    if legacy_price <= 0:
        raise DomainError("SERVICE_PRICE_NOT_FOUND", "Não existe preço vigente para o serviço.", 409)
    return legacy_price


def _fiscal_profile_for(
    conn: Any, tenant_id: str, service_id: str, variant_id: str | None, on_date: date
) -> dict[str, Any] | None:
    rows = conn.execute(
        "SELECT * FROM service_fiscal_profiles WHERE tenant_id=? AND service_id=? AND state='published' "
        "ORDER BY valid_from DESC,created_at DESC",
        (tenant_id, service_id),
    ).fetchall()
    for raw in rows:
        row = dict(raw)
        if (row.get("variant_id") or None) != (variant_id or None):
            continue
        start = _normalize_date(row.get("valid_from"))
        end = _normalize_date(row.get("valid_until"))
        if start and start <= on_date and (end is None or end >= on_date):
            return row
    return None


def _fiscal_snapshot(service: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    if profile:
        return {
            "profile_id": profile["id"],
            "classification_status": profile.get("classification_status", "incomplete"),
            "nbs_code": profile.get("nbs_code"),
            "lc116_code": profile.get("lc116_code"),
            "municipal_service_code": profile.get("municipal_service_code"),
            "cnae_code": profile.get("cnae_code"),
            "iss_rate": str(profile.get("iss_rate") or 0),
            "ibs_rate": str(profile.get("ibs_rate") or 0),
            "cbs_rate": str(profile.get("cbs_rate") or 0),
            "cclass_trib": profile.get("cclass_trib"),
            "fiscal_trigger": profile.get("fiscal_trigger") or "billing",
            "withholding": loads(profile.get("withholding_json"), {}),
            "rules_snapshot": loads(profile.get("rules_snapshot_json"), {}),
        }
    legacy = loads(service.get("fiscal_profile_json"), {})
    required = [service.get("nbs"), service.get("lc116_code"), service.get("municipal_code"), service.get("cnae")]
    status = "complete" if all(required) else "incomplete"
    return {
        "profile_id": None,
        "classification_status": status,
        "nbs_code": service.get("nbs"),
        "lc116_code": service.get("lc116_code"),
        "municipal_service_code": service.get("municipal_code"),
        "cnae_code": service.get("cnae"),
        "cclass_trib": legacy.get("cclass_trib"),
        "fiscal_trigger": legacy.get("fiscal_trigger", "billing"),
        **legacy,
    }


def _integration_configured(conn: Any, tenant_id: str) -> bool:
    # Providers reais permanecem condicionais. Apenas uma conexão ativa e com
    # referência de segredo é considerada configurada; fixtures não contam.
    rows = conn.execute(
        "SELECT provider,state,secret_reference FROM integration_connections WHERE tenant_id=?",
        (tenant_id,),
    ).fetchall()
    for raw in rows:
        row = dict(raw)
        provider = str(row.get("provider") or "").lower()
        if row.get("state") == "active" and row.get("secret_reference") and (
            "fiscal" in provider or "nfse" in provider
        ):
            return True
    return False


def catalog_detail(request: Request, tenant_id: str, catalog_id: str) -> dict[str, Any]:
    catalog = request.state.store.fetch_one(
        "SELECT * FROM service_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id)
    )
    if not catalog:
        raise DomainError("SERVICE_CATALOG_NOT_FOUND", "Catálogo de serviços não localizado.", 404)
    result = _status(catalog)
    result["services"] = [
        _status(row)
        for row in request.state.store.fetch_all(
            "SELECT * FROM services WHERE tenant_id=? AND catalog_id=? ORDER BY name", (tenant_id, catalog_id)
        )
    ]
    return result


def list_catalogs(request: Request, tenant_id: str, status: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM service_catalogs WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    sql += " ORDER BY name,id"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def create_catalog(
    request: Request, tenant_id: str, user: CurrentUser, data: CatalogCreate, key: str | None
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:catalog:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        catalog_id, now = uuid7(), iso_now()
        try:
            conn.execute(
                "INSERT INTO service_catalogs(id,tenant_id,code,name,description,valid_from,valid_until,state,institution_id,unit_id,version,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    catalog_id, tenant_id, data.code, data.name, data.description,
                    data.valid_from.isoformat() if data.valid_from else None,
                    data.valid_until.isoformat() if data.valid_until else None,
                    data.status, data.institution_id, data.unit_id, 1, now, now,
                ),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("SERVICE_CATALOG_CODE_EXISTS", "Já existe catálogo com este código.", 409) from exc
            raise
        result = {
            "id": catalog_id, "code": data.code, "name": data.name, "status": data.status,
            "state": data.status, "version": 1,
        }
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_catalog", aggregate_id=catalog_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceCatalogCreated", aggregate_type="service_catalog", aggregate_id=catalog_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def update_catalog(
    request: Request, tenant_id: str, user: CurrentUser, catalog_id: str, data: CatalogUpdate
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM service_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id), "SERVICE_CATALOG_NOT_FOUND", "Catálogo de serviços não localizado.")
        if int(before.get("version") or 1) != data.expected_version:
            raise DomainError("OPTIMISTIC_CONCURRENCY_CONFLICT", "O catálogo foi alterado por outro usuário.", 409)
        values = data.model_dump(exclude={"expected_version"}, exclude_unset=True)
        allowed = {"name", "description", "valid_from", "valid_until", "status"}
        assignments: list[str] = []
        params: list[Any] = []
        for field, value in values.items():
            if field not in allowed:
                continue
            column = "state" if field == "status" else field
            assignments.append(f"{column}=?")
            params.append(value.isoformat() if isinstance(value, date) else value)
        if not assignments:
            return _status(before)
        assignments.extend(["version=version+1", "updated_at=?"])
        params.extend([iso_now(), tenant_id, catalog_id])
        conn.execute(f"UPDATE service_catalogs SET {','.join(assignments)} WHERE tenant_id=? AND id=?", params)
        after = dict(conn.execute("SELECT * FROM service_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id)).fetchone())
        result = _status(after)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="update", aggregate_type="service_catalog", aggregate_id=catalog_id, before=_status(before), after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceCatalogUpdated", aggregate_type="service_catalog", aggregate_id=catalog_id, payload=result)
        return result


def list_services(request: Request, tenant_id: str, status: str | None = None, catalog_id: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM services WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if catalog_id:
        sql += " AND catalog_id=?"
        params.append(catalog_id)
    sql += " ORDER BY name,id"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def create_service(
    request: Request, tenant_id: str, user: CurrentUser, data: ServiceCreateUnified, key: str | None
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:service:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        if data.catalog_id:
            _one(conn, "SELECT id FROM service_catalogs WHERE tenant_id=? AND id=? AND state IN ('active','draft')", (tenant_id, data.catalog_id), "SERVICE_CATALOG_NOT_FOUND", "Catálogo de serviços não localizado.")
        service_id, now = uuid7(), iso_now()
        recurrence_type = data.recurrence_type
        if data.recurrence and data.recurrence_type == "one_time":
            recurrence_type = data.recurrence if data.recurrence in {"monthly", "bimonthly", "quarterly", "semiannual", "annual", "custom"} else "one_time"
        legacy_profile = dict(data.fiscal_profile)
        if data.nbs:
            legacy_profile.setdefault("nbs_code", data.nbs)
        try:
            conn.execute(
                "INSERT INTO services(id,tenant_id,code,name,description,price,recurrence,nbs,lc116_code,municipal_code,cnae,fiscal_profile_json,state,catalog_id,service_type,recurrence_type,unit_of_measure,default_duration_minutes,cost_center_id,taxable,metadata_json,institution_id,unit_id,version,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    service_id, tenant_id, data.code, data.name, data.description, money_str(data.price or 0),
                    data.recurrence or recurrence_type, data.nbs, data.lc116_code, data.municipal_code, data.cnae,
                    dumps(legacy_profile), data.status, data.catalog_id, data.service_type, recurrence_type,
                    data.unit_of_measure, data.default_duration_minutes, data.cost_center_id, 1 if data.taxable else 0,
                    dumps(data.metadata), data.institution_id, data.unit_id, 1, now, now,
                ),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("SERVICE_CODE_EXISTS", "Já existe serviço com este código.", 409) from exc
            raise
        result = {
            "id": service_id, "code": data.code, "name": data.name, "price": money_str(data.price or 0),
            "service_type": data.service_type, "recurrence_type": recurrence_type, "status": data.status,
            "state": data.status, "version": 1,
        }
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service", aggregate_id=service_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceCreated", aggregate_type="service", aggregate_id=service_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def service_detail(request: Request, tenant_id: str, service_id: str) -> dict[str, Any]:
    service = request.state.store.fetch_one("SELECT * FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id))
    if not service:
        raise DomainError("SERVICE_NOT_FOUND", "Serviço não localizado.", 404)
    result = _status(service)
    result["variants"] = [_status(row) for row in request.state.store.fetch_all("SELECT * FROM service_variants WHERE tenant_id=? AND service_id=? ORDER BY name", (tenant_id, service_id))]
    result["prices"] = [_status(row) for row in request.state.store.fetch_all("SELECT * FROM service_price_tables WHERE tenant_id=? AND service_id=? ORDER BY valid_from DESC", (tenant_id, service_id))]
    result["fiscal_profiles"] = [_status(row) for row in request.state.store.fetch_all("SELECT * FROM service_fiscal_profiles WHERE tenant_id=? AND service_id=? ORDER BY valid_from DESC", (tenant_id, service_id))]
    result["billing_rules"] = [_status(row) for row in request.state.store.fetch_all("SELECT * FROM service_billing_rules WHERE tenant_id=? AND service_id=? ORDER BY code", (tenant_id, service_id))]
    return result


def update_service(request: Request, tenant_id: str, user: CurrentUser, service_id: str, data: ServiceUpdate) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id), "SERVICE_NOT_FOUND", "Serviço não localizado.")
        if int(before.get("version") or 1) != data.expected_version:
            raise DomainError("OPTIMISTIC_CONCURRENCY_CONFLICT", "O serviço foi alterado por outro usuário.", 409)
        values = data.model_dump(exclude={"expected_version"}, exclude_unset=True)
        mapping = {"status": "state", "metadata": "metadata_json"}
        assignments: list[str] = []
        params: list[Any] = []
        for field, value in values.items():
            column = mapping.get(field, field)
            assignments.append(f"{column}=?")
            params.append(dumps(value) if field == "metadata" else (1 if value is True else 0 if value is False else value))
        if assignments:
            assignments.extend(["version=version+1", "updated_at=?"])
            params.extend([iso_now(), tenant_id, service_id])
            conn.execute(f"UPDATE services SET {','.join(assignments)} WHERE tenant_id=? AND id=?", params)
        after = dict(conn.execute("SELECT * FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id)).fetchone())
        result = _status(after)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="update", aggregate_type="service", aggregate_id=service_id, before=_status(before), after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceUpdated", aggregate_type="service", aggregate_id=service_id, payload={"id": service_id, "status": result["status"], "version": result["version"]})
        return result


def create_variant(request: Request, tenant_id: str, user: CurrentUser, service_id: str, data: VariantCreate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:variant:create:{tenant_id}:{service_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _one(conn, "SELECT id FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id), "SERVICE_NOT_FOUND", "Serviço não localizado.")
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        variant_id, now = uuid7(), iso_now()
        try:
            conn.execute(
                "INSERT INTO service_variants(id,tenant_id,service_id,code,name,description,duration_minutes,capacity,state,metadata_json,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (variant_id, tenant_id, service_id, data.code, data.name, data.description, data.duration_minutes, data.capacity, data.status, dumps(data.metadata), data.institution_id, data.unit_id, 1, now, now),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("SERVICE_VARIANT_CODE_EXISTS", "Já existe variação com este código.", 409) from exc
            raise
        result = {"id": variant_id, "service_id": service_id, "code": data.code, "name": data.name, "status": data.status, "state": data.status, "version": 1}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_variant", aggregate_id=variant_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceVariantCreated", aggregate_type="service_variant", aggregate_id=variant_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def update_variant(request: Request, tenant_id: str, user: CurrentUser, variant_id: str, data: VariantUpdate) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM service_variants WHERE tenant_id=? AND id=?", (tenant_id, variant_id), "SERVICE_VARIANT_NOT_FOUND", "Variação do serviço não localizada.")
        if int(before.get("version") or 1) != data.expected_version:
            raise DomainError("OPTIMISTIC_CONCURRENCY_CONFLICT", "A variação foi alterada por outro usuário.", 409)
        values = data.model_dump(exclude={"expected_version"}, exclude_unset=True)
        assignments, params = [], []
        for field, value in values.items():
            column = "state" if field == "status" else "metadata_json" if field == "metadata" else field
            assignments.append(f"{column}=?")
            params.append(dumps(value) if field == "metadata" else value)
        if assignments:
            assignments.extend(["version=version+1", "updated_at=?"])
            params.extend([iso_now(), tenant_id, variant_id])
            conn.execute(f"UPDATE service_variants SET {','.join(assignments)} WHERE tenant_id=? AND id=?", params)
        after = dict(conn.execute("SELECT * FROM service_variants WHERE tenant_id=? AND id=?", (tenant_id, variant_id)).fetchone())
        result = _status(after)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="update", aggregate_type="service_variant", aggregate_id=variant_id, before=_status(before), after=result)
        return result


def create_fiscal_profile(request: Request, tenant_id: str, user: CurrentUser, service_id: str, data: FiscalProfileCreate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:fiscal-profile:create:{tenant_id}:{service_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _one(conn, "SELECT id FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id), "SERVICE_NOT_FOUND", "Serviço não localizado.")
        if data.variant_id:
            _one(conn, "SELECT id FROM service_variants WHERE tenant_id=? AND id=? AND service_id=?", (tenant_id, data.variant_id, service_id), "SERVICE_VARIANT_NOT_FOUND", "Variação do serviço não localizada.")
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        profile_id, now = uuid7(), iso_now()
        required = [data.nbs_code, data.lc116_code, data.municipal_service_code, data.cnae_code, data.cclass_trib]
        classification = "complete" if all(required) else "incomplete"
        conn.execute(
            "INSERT INTO service_fiscal_profiles(id,tenant_id,service_id,variant_id,valid_from,valid_until,nbs_code,lc116_code,municipal_service_code,cnae_code,iss_rate,ibs_rate,cbs_rate,cclass_trib,fiscal_trigger,withholding_json,rules_snapshot_json,state,classification_status,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile_id, tenant_id, service_id, data.variant_id, data.valid_from.isoformat(), data.valid_until.isoformat() if data.valid_until else None, data.nbs_code, data.lc116_code, data.municipal_service_code, data.cnae_code, str(data.iss_rate), str(data.ibs_rate), str(data.cbs_rate), data.cclass_trib, data.fiscal_trigger, dumps(data.withholding), dumps(data.rules_snapshot), "draft", classification, data.institution_id, data.unit_id, 1, now, now),
        )
        result = {"id": profile_id, "service_id": service_id, "variant_id": data.variant_id, "status": "draft", "state": "draft", "classification_status": classification, "version": 1}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_fiscal_profile", aggregate_id=profile_id, after=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def publish_fiscal_profile(request: Request, tenant_id: str, user: CurrentUser, profile_id: str, notes: str | None) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM service_fiscal_profiles WHERE tenant_id=? AND id=?", (tenant_id, profile_id), "SERVICE_FISCAL_PROFILE_NOT_FOUND", "Perfil fiscal do serviço não localizado.")
        if before["state"] == "published":
            return _status(before)
        now = iso_now()
        conn.execute("UPDATE service_fiscal_profiles SET state='published',published_at=?,published_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, user.id, now, tenant_id, profile_id))
        after = dict(conn.execute("SELECT * FROM service_fiscal_profiles WHERE tenant_id=? AND id=?", (tenant_id, profile_id)).fetchone())
        result = _status(after)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="publish", aggregate_type="service_fiscal_profile", aggregate_id=profile_id, before=_status(before), after=result, reason=notes)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceFiscalProfilePublished", aggregate_type="service_fiscal_profile", aggregate_id=profile_id, payload={"id": profile_id, "classification_status": result["classification_status"]})
        return result


def create_price(request: Request, tenant_id: str, user: CurrentUser, service_id: str, data: PriceTableCreate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:price:create:{tenant_id}:{service_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _one(conn, "SELECT id FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id), "SERVICE_NOT_FOUND", "Serviço não localizado.")
        if data.variant_id:
            _one(conn, "SELECT id FROM service_variants WHERE tenant_id=? AND id=? AND service_id=?", (tenant_id, data.variant_id, service_id), "SERVICE_VARIANT_NOT_FOUND", "Variação do serviço não localizada.")
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        existing = conn.execute("SELECT valid_from,valid_until,variant_id FROM service_price_tables WHERE tenant_id=? AND service_id=? AND state='active'", (tenant_id, service_id)).fetchall()
        for raw in existing:
            row = dict(raw)
            if (row.get("variant_id") or None) != (data.variant_id or None):
                continue
            old_start = _normalize_date(row["valid_from"])
            old_end = _normalize_date(row.get("valid_until"))
            if old_start and not ((old_end is not None and old_end < data.valid_from) or (data.valid_until is not None and data.valid_until < old_start)):
                raise DomainError("SERVICE_PRICE_OVERLAP", "A vigência da tabela de preço se sobrepõe a outra tabela ativa.", 409)
        price_id, now = uuid7(), iso_now()
        conn.execute(
            "INSERT INTO service_price_tables(id,tenant_id,service_id,variant_id,name,valid_from,valid_until,currency,amount,billing_frequency,state,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (price_id, tenant_id, service_id, data.variant_id, data.name, data.valid_from.isoformat(), data.valid_until.isoformat() if data.valid_until else None, data.currency.upper(), money_str(data.amount), data.billing_frequency, data.status, data.institution_id, data.unit_id, 1, now, now),
        )
        result = {"id": price_id, "service_id": service_id, "variant_id": data.variant_id, "name": data.name, "amount": money_str(data.amount), "currency": data.currency.upper(), "status": data.status, "state": data.status, "version": 1}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_price_table", aggregate_id=price_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServicePricePublished", aggregate_type="service_price_table", aggregate_id=price_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def create_billing_rule(request: Request, tenant_id: str, user: CurrentUser, service_id: str, data: BillingRuleCreate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:billing-rule:create:{tenant_id}:{service_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _one(conn, "SELECT id FROM services WHERE tenant_id=? AND id=?", (tenant_id, service_id), "SERVICE_NOT_FOUND", "Serviço não localizado.")
        if data.variant_id:
            _one(conn, "SELECT id FROM service_variants WHERE tenant_id=? AND id=? AND service_id=?", (tenant_id, data.variant_id, service_id), "SERVICE_VARIANT_NOT_FOUND", "Variação do serviço não localizada.")
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        rule_id, now = uuid7(), iso_now()
        try:
            conn.execute(
                "INSERT INTO service_billing_rules(id,tenant_id,service_id,variant_id,code,name,billing_trigger,due_day,installment_count,interval_months,recognition_policy,fiscal_trigger,proration_policy,state,config_json,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rule_id, tenant_id, service_id, data.variant_id, data.code, data.name, data.billing_trigger, data.due_day, data.installment_count, data.interval_months, data.recognition_policy, data.fiscal_trigger, data.proration_policy, data.status, dumps(data.config), data.institution_id, data.unit_id, 1, now, now),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("SERVICE_BILLING_RULE_CODE_EXISTS", "Já existe regra de cobrança com este código.", 409) from exc
            raise
        result = {"id": rule_id, "service_id": service_id, "variant_id": data.variant_id, "code": data.code, "name": data.name, "billing_trigger": data.billing_trigger, "fiscal_trigger": data.fiscal_trigger, "status": data.status, "state": data.status, "version": 1}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_billing_rule", aggregate_id=rule_id, after=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def _receipt_public(row: dict[str, Any]) -> dict[str, Any]:
    result = _status(row)
    result.pop("document_storage_key", None)
    result.pop("recipient_document", None)
    result.pop("snapshot_json", None)
    result.pop("snapshot", None)
    return result


def _receipt_recipient_conn(conn: Any, tenant_id: str, order: dict[str, Any]) -> dict[str, str | None]:
    recipient: dict[str, Any] | None = None
    if order.get("subscriber_person_id"):
        raw = conn.execute(
            "SELECT full_name,cpf FROM people WHERE tenant_id=? AND id=?",
            (tenant_id, order["subscriber_person_id"]),
        ).fetchone()
        recipient = dict(raw) if raw else None
    elif order.get("responsible_guardian_id"):
        raw = conn.execute(
            """SELECT p.full_name,p.cpf
               FROM guardians g JOIN people p ON p.id=g.person_id AND p.tenant_id=g.tenant_id
               WHERE g.tenant_id=? AND g.id=?""",
            (tenant_id, order["responsible_guardian_id"]),
        ).fetchone()
        recipient = dict(raw) if raw else None
    return {
        "name": str((recipient or {}).get("full_name") or "Responsável não identificado"),
        "document": (recipient or {}).get("cpf"),
    }


def _receipt_issuer_conn(conn: Any, tenant_id: str, order: dict[str, Any]) -> dict[str, str | None]:
    institution: dict[str, Any] | None = None
    if order.get("institution_id"):
        raw = conn.execute(
            "SELECT legal_name,trade_name,cnpj FROM institutions WHERE tenant_id=? AND id=?",
            (tenant_id, order["institution_id"]),
        ).fetchone()
        institution = dict(raw) if raw else None
    return {
        "name": str((institution or {}).get("trade_name") or (institution or {}).get("legal_name") or "Instituição de ensino"),
        "legal_name": (institution or {}).get("legal_name"),
        "document": (institution or {}).get("cnpj"),
    }


def _receipt_pdf(snapshot: dict[str, Any]) -> bytes:
    """Gera o documento local de recibo sem declarar validade fiscal de NFS-e."""
    out = io.BytesIO()
    document = canvas.Canvas(out, pagesize=A4, pageCompression=1)
    width, height = A4
    document.setTitle(f"Recibo {snapshot['receipt_number']}")
    document.setAuthor("PIGE360")
    y = height - 56
    document.setFont("Helvetica-Bold", 16)
    document.drawString(50, y, "RECIBO DE PAGAMENTO DE SERVIÇO")
    y -= 24
    document.setFont("Helvetica", 10)
    lines = [
        f"Número: {snapshot['receipt_number']}",
        f"Emitido em: {snapshot['issued_at']}",
        f"Emitente: {snapshot['issuer']['name']}",
        f"Recebemos de: {snapshot['recipient']['name']}",
        f"Pedido de serviço: {snapshot['service_order']['order_number']}",
        f"Pagamento: {snapshot['payment']['method']} em {snapshot['payment']['paid_at']}",
        f"Referência externa: {snapshot['payment']['external_reference'] or 'não informada'}",
        "",
        "Itens recebidos:",
    ]
    for item in snapshot["items"]:
        lines.append(f"- {item['description']}: R$ {item['total_amount']}")
    lines.extend(
        [
            "",
            f"Valor recebido: R$ {snapshot['amount']} {snapshot['currency']}",
            "Este recibo comprova o pagamento informado e não substitui documento fiscal.",
        ]
    )
    for raw_line in lines:
        line = raw_line.replace("—", "-")
        document.drawString(50, y, line[:110])
        y -= 15
        if y < 60:
            document.showPage()
            document.setFont("Helvetica", 10)
            y = height - 56
    document.showPage()
    document.save()
    return out.getvalue()


def _receipt_payment_rows_conn(conn: Any, tenant_id: str, order_id: str) -> list[dict[str, Any]]:
    order = _one(
        conn,
        "SELECT id,charge_id FROM service_orders WHERE tenant_id=? AND id=?",
        (tenant_id, order_id),
        "SERVICE_ORDER_NOT_FOUND",
        "Pedido de serviço não localizado.",
    )
    if not order.get("charge_id"):
        return []
    rows = conn.execute(
        """SELECT p.id,p.method,p.amount,p.paid_at,p.external_reference,p.state,
                  COALESCE(SUM(pa.amount),0) AS service_amount,
                  (SELECT sr.id FROM service_receipts sr
                     WHERE sr.tenant_id=p.tenant_id AND sr.service_order_id=? AND sr.payment_id=p.id
                       AND sr.state='issued' ORDER BY sr.issued_at DESC LIMIT 1) AS receipt_id
           FROM payment_allocations pa
           JOIN payments p ON p.id=pa.payment_id AND p.tenant_id=pa.tenant_id
           JOIN accounts_receivable ar ON ar.installment_id=pa.installment_id AND ar.tenant_id=pa.tenant_id
           WHERE pa.tenant_id=? AND ar.charge_id=?
           GROUP BY p.id,p.method,p.amount,p.paid_at,p.external_reference,p.state,p.tenant_id
           ORDER BY p.paid_at DESC,p.id DESC""",
        (order_id, tenant_id, order["charge_id"]),
    ).fetchall()
    return [dict(row) for row in rows]


def issue_service_receipts_for_payment(
    conn: Any,
    *,
    tenant_id: str,
    payment_id: str,
    actor_id: str,
    storage: Any,
    correlation_id: str | None,
) -> list[dict[str, Any]]:
    """Emite um recibo por pedido de serviço contemplado pelo pagamento confirmado.

    A relação passa por `accounts_receivable.charge_id`, evitando atribuir um
    rateio de contrato recorrente ao pedido de serviço errado.
    """
    payment = _one(
        conn,
        "SELECT * FROM payments WHERE tenant_id=? AND id=?",
        (tenant_id, payment_id),
        "PAYMENT_NOT_FOUND",
        "Pagamento não localizado.",
    )
    if payment.get("state") != "confirmed":
        return []
    rows = conn.execute(
        """SELECT so.*,p.method AS payment_method,p.external_reference,p.paid_at,
                  COALESCE(SUM(pa.amount),0) AS receipt_amount
           FROM payment_allocations pa
           JOIN payments p ON p.id=pa.payment_id AND p.tenant_id=pa.tenant_id
           JOIN accounts_receivable ar ON ar.installment_id=pa.installment_id AND ar.tenant_id=pa.tenant_id
           JOIN service_orders so ON so.charge_id=ar.charge_id AND so.tenant_id=ar.tenant_id
           WHERE pa.tenant_id=? AND pa.payment_id=?
           GROUP BY so.id,p.method,p.external_reference,p.paid_at
           ORDER BY so.created_at,so.id""",
        (tenant_id, payment_id),
    ).fetchall()
    issued: list[dict[str, Any]] = []
    for raw in rows:
        order = dict(raw)
        amount = money(order["receipt_amount"])
        if amount <= 0 or not order.get("charge_id"):
            continue
        existing = conn.execute(
            """SELECT * FROM service_receipts
               WHERE tenant_id=? AND service_order_id=? AND payment_id=? AND state='issued'
               ORDER BY issued_at DESC LIMIT 1""",
            (tenant_id, order["id"], payment_id),
        ).fetchone()
        if existing:
            issued.append({**_receipt_public(dict(existing)), "idempotent": True})
            continue
        receipt_id, now = uuid7(), iso_now()
        receipt_number = f"RSV-{receipt_id[-12:].upper()}"
        recipient = _receipt_recipient_conn(conn, tenant_id, order)
        issuer = _receipt_issuer_conn(conn, tenant_id, order)
        items = [
            {
                "description": str(item["description"] or item["service_name"] or "Serviço"),
                "quantity": str(item["quantity"]),
                "total_amount": money_str(item["total_amount"]),
            }
            for item in conn.execute(
                """SELECT soi.description,soi.quantity,soi.total_amount,s.name AS service_name
                   FROM service_order_items soi JOIN services s ON s.id=soi.service_id AND s.tenant_id=soi.tenant_id
                   WHERE soi.tenant_id=? AND soi.service_order_id=? ORDER BY soi.created_at,soi.id""",
                (tenant_id, order["id"]),
            ).fetchall()
        ]
        snapshot = {
            "receipt_number": receipt_number,
            "issued_at": now,
            "issuer": issuer,
            "recipient": recipient,
            "service_order": {"id": order["id"], "order_number": order.get("order_number") or order["id"]},
            "payment": {
                "id": payment_id,
                "method": order["payment_method"],
                "paid_at": order["paid_at"],
                "external_reference": order.get("external_reference"),
            },
            "items": items,
            "currency": str(order.get("currency") or "BRL"),
            "amount": money_str(amount),
        }
        pdf = _receipt_pdf(snapshot)
        document_key = f"service-receipts/{now[:4]}/{receipt_id}/recibo.pdf"
        stored = storage.put_bytes(document_key, pdf, content_type="application/pdf")
        if stored.sha256 != hashlib.sha256(pdf).hexdigest():
            raise DomainError("SERVICE_RECEIPT_STORAGE_INTEGRITY_FAILED", "Falha de integridade ao armazenar o recibo.", 500)
        try:
            conn.execute(
                """INSERT INTO service_receipts(
                       id,tenant_id,receipt_number,service_order_id,charge_id,payment_id,currency,amount,payment_method,
                       external_reference,recipient_name,recipient_document,state,document_storage_key,document_sha256,
                       snapshot_json,issued_at,issued_by,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    receipt_id, tenant_id, receipt_number, order["id"], order["charge_id"], payment_id,
                    snapshot["currency"], snapshot["amount"], order["payment_method"], order.get("external_reference"),
                    recipient["name"], recipient["document"], "issued", stored.key, stored.sha256,
                    dumps(snapshot), now, actor_id, now, now,
                ),
            )
        except Exception as exc:
            if "unique" not in str(exc).lower() and "duplicate" not in str(exc).lower():
                raise
            concurrent = conn.execute(
                """SELECT * FROM service_receipts
                   WHERE tenant_id=? AND service_order_id=? AND payment_id=? AND state='issued'
                   ORDER BY issued_at DESC LIMIT 1""",
                (tenant_id, order["id"], payment_id),
            ).fetchone()
            if not concurrent:
                raise
            issued.append({**_receipt_public(dict(concurrent)), "idempotent": True})
            continue
        result = {
            "id": receipt_id,
            "receipt_number": receipt_number,
            "service_order_id": order["id"],
            "payment_id": payment_id,
            "amount": snapshot["amount"],
            "currency": snapshot["currency"],
            "state": "issued",
            "document_sha256": stored.sha256,
            "issued_at": now,
            "idempotent": False,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="issue",
            aggregate_type="service_receipt",
            aggregate_id=receipt_id,
            correlation_id=correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="ServiceReceiptIssued",
            aggregate_type="service_receipt",
            aggregate_id=receipt_id,
            payload=result,
            correlation_id=correlation_id,
        )
        issued.append(result)
    return issued


def _receipt_raw_conn(conn: Any, tenant_id: str, receipt_id: str) -> dict[str, Any]:
    return _one(
        conn,
        "SELECT * FROM service_receipts WHERE tenant_id=? AND id=?",
        (tenant_id, receipt_id),
        "SERVICE_RECEIPT_NOT_FOUND",
        "Recibo de serviço não localizado.",
    )


def _receipt_detail_conn(conn: Any, tenant_id: str, receipt_id: str) -> dict[str, Any]:
    return _receipt_public(_receipt_raw_conn(conn, tenant_id, receipt_id))


def list_service_receipts(request: Request, tenant_id: str, order_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        _one(
            conn,
            "SELECT id FROM service_orders WHERE tenant_id=? AND id=?",
            (tenant_id, order_id),
            "SERVICE_ORDER_NOT_FOUND",
            "Pedido de serviço não localizado.",
        )
        rows = conn.execute(
            "SELECT * FROM service_receipts WHERE tenant_id=? AND service_order_id=? ORDER BY issued_at DESC,id DESC",
            (tenant_id, order_id),
        ).fetchall()
        return {"items": [_receipt_public(dict(row)) for row in rows]}


def list_service_receipt_payments(request: Request, tenant_id: str, order_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        return {"items": _receipt_payment_rows_conn(conn, tenant_id, order_id)}


def create_service_receipt(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    order_id: str,
    data: ServiceReceiptCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:receipt:create:{tenant_id}:{order_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _one(conn, "SELECT id FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
        issued = issue_service_receipts_for_payment(
            conn,
            tenant_id=tenant_id,
            payment_id=data.payment_id,
            actor_id=user.id,
            storage=request.app.state.data_router.object_storage(tenant_id),
            correlation_id=request.state.correlation_id,
        )
        result = next((item for item in issued if item["service_order_id"] == order_id), None)
        if not result:
            raise DomainError("SERVICE_RECEIPT_PAYMENT_NOT_LINKED", "O pagamento não possui rateio confirmado para a cobrança deste pedido.", 409)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def service_receipt_detail(request: Request, tenant_id: str, receipt_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        return _receipt_detail_conn(conn, tenant_id, receipt_id)


def service_receipt_document(request: Request, tenant_id: str, receipt_id: str) -> tuple[bytes, str, str]:
    with request.state.store.transaction() as conn:
        receipt = _receipt_raw_conn(conn, tenant_id, receipt_id)
    storage = request.app.state.data_router.object_storage(tenant_id)
    storage_key = str(receipt["document_storage_key"])
    if not storage.exists(storage_key):
        raise DomainError("SERVICE_RECEIPT_DOCUMENT_MISSING", "O PDF do recibo não está disponível no armazenamento privado.", 503)
    content = storage.get_bytes(storage_key)
    digest = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(digest, str(receipt["document_sha256"])):
        raise DomainError("SERVICE_RECEIPT_DOCUMENT_INTEGRITY_FAILED", "A integridade do PDF do recibo não confere.", 409)
    return content, str(receipt["receipt_number"]), digest


def void_service_receipt(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    receipt_id: str,
    data: ServiceReceiptVoid,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _receipt_detail_conn(conn, tenant_id, receipt_id)
        if before["state"] == "voided":
            return {**before, "idempotent": True}
        now = iso_now()
        conn.execute(
            "UPDATE service_receipts SET state='voided',voided_at=?,voided_by=?,void_reason=?,updated_at=? WHERE tenant_id=? AND id=?",
            (now, user.id, data.reason, now, tenant_id, receipt_id),
        )
        result = _receipt_detail_conn(conn, tenant_id, receipt_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="void", aggregate_type="service_receipt", aggregate_id=receipt_id, before=before, after=result, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceReceiptVoided", aggregate_type="service_receipt", aggregate_id=receipt_id, payload={"id": receipt_id, "service_order_id": result["service_order_id"], "reason": data.reason})
        return result


def _order_detail_conn(conn: Any, tenant_id: str, order_id: str) -> dict[str, Any]:
    order = _one(conn, "SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
    result = _status(order)
    result["items"] = [
        _status(dict(row))
        for row in conn.execute(
            "SELECT soi.*,s.code AS service_code,s.name AS service_name FROM service_order_items soi JOIN services s ON s.id=soi.service_id WHERE soi.tenant_id=? AND soi.service_order_id=? ORDER BY soi.created_at,soi.id",
            (tenant_id, order_id),
        ).fetchall()
    ]
    result["executions"] = [
        _status(dict(row))
        for row in conn.execute("SELECT * FROM service_executions WHERE tenant_id=? AND service_order_id=? ORDER BY created_at,id", (tenant_id, order_id)).fetchall()
    ]
    result["fiscal_events"] = [
        _status(dict(row))
        for row in conn.execute("SELECT * FROM service_fiscal_events WHERE tenant_id=? AND service_order_id=? ORDER BY requested_at,id", (tenant_id, order_id)).fetchall()
    ]
    charge_id = result.get("charge_id")
    if charge_id:
        charge = conn.execute("SELECT * FROM charges WHERE tenant_id=? AND id=?", (tenant_id, charge_id)).fetchone()
        result["charge"] = _status(dict(charge)) if charge else None
    else:
        result["charge"] = None
    result["receipts"] = [
        _receipt_public(dict(row))
        for row in conn.execute(
            "SELECT * FROM service_receipts WHERE tenant_id=? AND service_order_id=? ORDER BY issued_at DESC,id DESC",
            (tenant_id, order_id),
        ).fetchall()
    ]
    result["receipt_payments"] = _receipt_payment_rows_conn(conn, tenant_id, order_id)
    return result


def order_detail(request: Request, tenant_id: str, order_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        return _order_detail_conn(conn, tenant_id, order_id)


def list_orders(request: Request, tenant_id: str, status: str | None = None, enrollment_id: str | None = None) -> dict[str, Any]:
    sql = "SELECT id FROM service_orders WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if enrollment_id:
        sql += " AND enrollment_id=?"
        params.append(enrollment_id)
    sql += " ORDER BY created_at DESC,id DESC"
    ids = [row["id"] for row in request.state.store.fetch_all(sql, params)]
    with request.state.store.transaction() as conn:
        return {"items": [_order_detail_conn(conn, tenant_id, order_id) for order_id in ids]}


def _insert_legacy_financial_contract(
    conn: Any,
    *,
    tenant_id: str,
    order_id: str,
    enrollment_id: str | None,
    responsible_guardian_id: str | None,
    total: Decimal,
    count: int,
    first_due_date: date,
    now: str,
) -> str:
    contract_id = uuid7()
    conn.execute(
        "INSERT INTO financial_contracts(id,tenant_id,enrollment_id,responsible_guardian_id,description,total_amount,currency,competence_rule,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (contract_id, tenant_id, enrollment_id, responsible_guardian_id, f"Pedido de serviços {order_id[-8:]}", money_str(total), "BRL", "billing", "active", 1, now, now),
    )
    base = (total / Decimal(count)).quantize(CENT, rounding=ROUND_HALF_UP)
    amounts = [base] * count
    amounts[-1] = (total - sum(amounts[:-1], Decimal("0"))).quantize(CENT)
    for sequence, amount in enumerate(amounts, 1):
        due = _month_add(first_due_date, sequence - 1)
        conn.execute(
            "INSERT INTO installments(id,tenant_id,financial_contract_id,sequence,competence,due_date,original_amount,discount_amount,penalty_amount,interest_amount,paid_amount,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uuid7(), tenant_id, contract_id, sequence, due.strftime("%Y-%m"), due.isoformat(), money_str(amount), "0.00", "0.00", "0.00", "0.00", "open", now, now),
        )
    return contract_id


def create_order(request: Request, tenant_id: str, user: CurrentUser, data: ServiceOrderCreateUnified, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:order:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        if data.enrollment_id:
            _one(conn, "SELECT id FROM enrollments WHERE tenant_id=? AND id=?", (tenant_id, data.enrollment_id), "ENROLLMENT_NOT_FOUND", "Matrícula não localizada.")
        if data.subscriber_person_id:
            _ensure_person(conn, tenant_id, data.subscriber_person_id)
        if data.subscription_id:
            _one(conn, "SELECT id FROM service_subscriptions WHERE tenant_id=? AND id=?", (tenant_id, data.subscription_id), "SERVICE_SUBSCRIPTION_NOT_FOUND", "Assinatura de serviço não localizada.")
        pricing_date = data.due_date or data.first_due_date or date.today()
        prepared: list[dict[str, Any]] = []
        subtotal = Decimal("0")
        for item in data.items:
            service = _one(conn, "SELECT * FROM services WHERE tenant_id=? AND id=? AND state='active'", (tenant_id, item.service_id), "SERVICE_NOT_FOUND", "Serviço não localizado ou inativo.")
            if item.variant_id:
                _one(conn, "SELECT id FROM service_variants WHERE tenant_id=? AND id=? AND service_id=? AND state='active'", (tenant_id, item.variant_id, item.service_id), "SERVICE_VARIANT_NOT_FOUND", "Variação do serviço não localizada ou inativa.")
            unit_price = money(item.unit_price) if item.unit_price is not None else _price_for(conn, tenant_id, item.service_id, item.variant_id, pricing_date)
            discount = money(item.discount_amount)
            gross = (unit_price * quantity(item.quantity)).quantize(CENT, rounding=ROUND_HALF_UP)
            total = (gross - discount).quantize(CENT, rounding=ROUND_HALF_UP)
            if total < 0:
                raise DomainError("SERVICE_ITEM_DISCOUNT_EXCEEDED", "O desconto do item excede seu valor bruto.", 422)
            profile = _fiscal_profile_for(conn, tenant_id, item.service_id, item.variant_id, pricing_date)
            snapshot = _fiscal_snapshot(service, profile)
            prepared.append({"input": item, "service": service, "unit_price": unit_price, "total": total, "snapshot": snapshot})
            subtotal += total
        overall_discount = money(data.discount_amount)
        final_total = (subtotal - overall_discount).quantize(CENT, rounding=ROUND_HALF_UP)
        if final_total < 0:
            raise DomainError("SERVICE_ORDER_DISCOUNT_EXCEEDED", "O desconto geral excede o subtotal do pedido.", 422)
        order_id, now = uuid7(), iso_now()
        legacy = data.legacy_mode
        state = "confirmed" if legacy else "draft"
        due = data.due_date or data.first_due_date or date.today()
        order_number = data.order_number or f"SRV-{order_id[-12:].upper()}"
        contract_id = data.financial_contract_id
        if legacy:
            contract_id = _insert_legacy_financial_contract(conn, tenant_id=tenant_id, order_id=order_id, enrollment_id=data.enrollment_id, responsible_guardian_id=data.responsible_guardian_id, total=final_total, count=data.installment_count, first_due_date=due, now=now)
        try:
            conn.execute(
                "INSERT INTO service_orders(id,tenant_id,enrollment_id,responsible_guardian_id,competence,state,total_amount,financial_contract_id,order_number,subscriber_person_id,subscription_id,competence_id,cost_center_id,currency,subtotal,discount_amount,due_date,installment_count,charge_id,fiscal_status,notes,confirmed_at,confirmed_by,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (order_id, tenant_id, data.enrollment_id, data.responsible_guardian_id, data.competence, state, money_str(final_total), contract_id, order_number, data.subscriber_person_id, data.subscription_id, data.competence_id, data.cost_center_id, data.currency.upper(), money_str(subtotal), money_str(overall_discount), due.isoformat(), data.installment_count, None, "pending", data.notes, now if legacy else None, user.id if legacy else None, data.institution_id, data.unit_id, 1, now, now),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("SERVICE_ORDER_NUMBER_EXISTS", "Já existe pedido com este número.", 409) from exc
            raise
        for prepared_item in prepared:
            item = prepared_item["input"]
            item_id = uuid7()
            conn.execute(
                "INSERT INTO service_order_items(id,tenant_id,service_order_id,service_id,quantity,unit_price,total_amount,variant_id,description,discount_amount,competence_start,competence_end,fiscal_profile_snapshot_json,execution_status,executed_quantity,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item_id, tenant_id, order_id, item.service_id, str(quantity(item.quantity)), money_str(prepared_item["unit_price"]), money_str(prepared_item["total"]), item.variant_id, item.description or prepared_item["service"]["name"], money_str(item.discount_amount), item.competence_start.isoformat() if item.competence_start else None, item.competence_end.isoformat() if item.competence_end else None, dumps(prepared_item["snapshot"]), "pending", "0.0000", now),
            )
        if legacy:
            result = {"id": order_id, "state": "confirmed", "status": "confirmed", "total_amount": money_str(final_total), "financial_contract_id": contract_id, "installments": data.installment_count}
        else:
            result = _order_detail_conn(conn, tenant_id, order_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="confirm" if legacy else "create", aggregate_type="service_order", aggregate_id=order_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceOrderConfirmed" if legacy else "ServiceOrderCreated", aggregate_type="service_order", aggregate_id=order_id, payload={"id": order_id, "status": state, "total_amount": money_str(final_total)})
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def _create_charge(conn: Any, tenant_id: str, user: CurrentUser, order: dict[str, Any], items: list[dict[str, Any]], now: str) -> str:
    charge_id = uuid7()
    charge_number = f"CHG-{charge_id[-12:].upper()}"
    total = money(order["total_amount"])
    responsible_person_id = order.get("subscriber_person_id")
    contract_id = order.get("financial_contract_id")
    if not contract_id:
        contract_id = _insert_legacy_financial_contract(
            conn,
            tenant_id=tenant_id,
            order_id=order["id"],
            enrollment_id=order.get("enrollment_id"),
            responsible_guardian_id=order.get("responsible_guardian_id"),
            total=total,
            count=max(int(order.get("installment_count") or 1), 1),
            first_due_date=_normalize_date(order.get("due_date")) or date.today(),
            now=now,
        )
        conn.execute("UPDATE service_orders SET financial_contract_id=? WHERE tenant_id=? AND id=?", (contract_id, tenant_id, order["id"]))
    conn.execute(
        "INSERT INTO charges(id,tenant_id,charge_number,financial_contract_id,enrollment_id,responsible_person_id,origin_type,origin_id,currency,total_amount,paid_amount,refunded_amount,outstanding_amount,due_date,state,generated_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (charge_id, tenant_id, charge_number, contract_id, order.get("enrollment_id"), responsible_person_id, "service_order", order["id"], order.get("currency") or "BRL", money_str(total), "0.00", "0.00", money_str(total), order.get("due_date") or date.today().isoformat(), "open", now, now, now),
    )
    for item in items:
        conn.execute(
            "INSERT INTO charge_items(id,tenant_id,charge_id,description,quantity,unit_amount,discount_amount,total_amount,accounting_code,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (uuid7(), tenant_id, charge_id, item.get("description") or item.get("service_name") or "Serviço", item["quantity"], item["unit_price"], item.get("discount_amount") or "0.00", item["total_amount"], item.get("service_code"), dumps({"service_order_item_id": item["id"], "service_id": item["service_id"]}), now),
        )
    installments = conn.execute("SELECT * FROM installments WHERE tenant_id=? AND financial_contract_id=? ORDER BY sequence", (tenant_id, contract_id)).fetchall()
    for raw in installments:
        installment = dict(raw)
        conn.execute(
            "INSERT INTO accounts_receivable(id,tenant_id,receivable_number,installment_id,charge_id,responsible_person_id,cost_center_id,amount,paid_amount,refunded_amount,outstanding_amount,due_date,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uuid7(), tenant_id, f"AR-{uuid7()[-12:].upper()}", installment["id"], charge_id, responsible_person_id, order.get("cost_center_id"), installment["original_amount"], installment.get("paid_amount") or "0.00", "0.00", money_str(money(installment["original_amount"]) - money(installment.get("paid_amount") or 0)), installment["due_date"], installment["state"], now, now),
        )
    conn.execute(
        "INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,debit_account,credit_account,amount,competence,occurred_at,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (uuid7(), tenant_id, "charge", "charge", charge_id, "accounts_receivable", "service_revenue", money_str(total), order.get("competence"), now, "Cobrança gerada por pedido de serviço", now),
    )
    return charge_id


def confirm_order(request: Request, tenant_id: str, user: CurrentUser, order_id: str, data: OrderConfirm) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        order = _one(conn, "SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
        if order["state"] == "confirmed":
            return _order_detail_conn(conn, tenant_id, order_id)
        if order["state"] != "draft":
            raise DomainError("SERVICE_ORDER_INVALID_STATE", "Somente pedidos em rascunho podem ser confirmados.", 409)
        items = [dict(row) for row in conn.execute("SELECT soi.*,s.code AS service_code,s.name AS service_name,s.taxable FROM service_order_items soi JOIN services s ON s.id=soi.service_id WHERE soi.tenant_id=? AND soi.service_order_id=?", (tenant_id, order_id)).fetchall()]
        if not items:
            raise DomainError("SERVICE_ORDER_EMPTY", "O pedido não possui itens.", 409)
        now = iso_now()
        charge_id = _create_charge(conn, tenant_id, user, order, items, now)
        configured = _integration_configured(conn, tenant_id)
        fiscal_states: list[str] = []
        for item in items:
            if not bool(item.get("taxable", 1)):
                continue
            snapshot = loads(item.get("fiscal_profile_snapshot_json"), {})
            complete = snapshot.get("classification_status") == "complete"
            if not complete:
                state, failure_code, failure_message = "blocked_validation", "SERVICE_FISCAL_CLASSIFICATION_INCOMPLETE", "Classificação fiscal obrigatória incompleta."
            elif not configured:
                state, failure_code, failure_message = "not_configured", "FISCAL_PROVIDER_NOT_CONFIGURED", "Provider fiscal não configurado."
            else:
                state, failure_code, failure_message = "queued", None, None
            event_id = uuid7()
            event_key = f"service-order:{order_id}:item:{item['id']}:billing"
            conn.execute(
                "INSERT INTO service_fiscal_events(id,tenant_id,event_key,service_order_id,service_order_item_id,competence_id,trigger_type,document_type,provider_code,state,payload_snapshot_json,requested_at,failure_code,failure_message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, tenant_id, event_key, order_id, item["id"], order.get("competence_id"), snapshot.get("fiscal_trigger") or "billing", "nfse", None, state, dumps({"order_id": order_id, "item_id": item["id"], "charge_id": charge_id, "classification": snapshot}), now, failure_code, failure_message, now, now),
            )
            fiscal_states.append(state)
            _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalDocumentRequested", aggregate_type="service_fiscal_event", aggregate_id=event_id, payload={"id": event_id, "order_id": order_id, "status": state})
            execution_id = uuid7()
            conn.execute(
                "INSERT INTO service_executions(id,tenant_id,execution_number,service_order_id,service_order_item_id,subscription_id,scheduled_at,quantity,state,notes,evidence_json,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (execution_id, tenant_id, f"EXE-{execution_id[-12:].upper()}", order_id, item["id"], order.get("subscription_id"), None, item["quantity"], "scheduled", None, "{}", order.get("institution_id"), order.get("unit_id"), 1, now, now),
            )
        fiscal_status = "blocked_validation" if "blocked_validation" in fiscal_states else "not_configured" if "not_configured" in fiscal_states else "queued" if fiscal_states else "not_applicable"
        conn.execute("UPDATE service_orders SET state='confirmed',charge_id=?,fiscal_status=?,notes=COALESCE(?,notes),confirmed_at=?,confirmed_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (charge_id, fiscal_status, data.notes, now, user.id, now, tenant_id, order_id))
        result = _order_detail_conn(conn, tenant_id, order_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="confirm", aggregate_type="service_order", aggregate_id=order_id, before=_status(order), after={"status": "confirmed", "charge_id": charge_id, "fiscal_status": fiscal_status}, reason=data.notes)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceOrderConfirmed", aggregate_type="service_order", aggregate_id=order_id, payload={"id": order_id, "charge_id": charge_id, "total_amount": order["total_amount"], "fiscal_status": fiscal_status})
        _event(conn, tenant_id=tenant_id, request=request, event_type="ChargeCreated", aggregate_type="charge", aggregate_id=charge_id, payload={"id": charge_id, "origin_id": order_id, "amount": order["total_amount"]})
        return result


def start_order(request: Request, tenant_id: str, user: CurrentUser, order_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        order = _one(conn, "SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
        if order["state"] == "in_progress":
            return _order_detail_conn(conn, tenant_id, order_id)
        if order["state"] != "confirmed":
            raise DomainError("SERVICE_ORDER_INVALID_STATE", "Somente pedidos confirmados podem ser iniciados.", 409)
        now = iso_now()
        conn.execute("UPDATE service_orders SET state='in_progress',started_at=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, now, tenant_id, order_id))
        result = _order_detail_conn(conn, tenant_id, order_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="start", aggregate_type="service_order", aggregate_id=order_id, before={"status": order["state"]}, after={"status": "in_progress"})
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceOrderStarted", aggregate_type="service_order", aggregate_id=order_id, payload={"id": order_id})
        return result


def complete_order(request: Request, tenant_id: str, user: CurrentUser, order_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        order = _one(conn, "SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
        if order["state"] == "completed":
            return _order_detail_conn(conn, tenant_id, order_id)
        if order["state"] not in {"confirmed", "in_progress"}:
            raise DomainError("SERVICE_ORDER_INVALID_STATE", "Pedido não pode ser concluído no estado atual.", 409)
        pending = conn.execute("SELECT COUNT(*) AS total FROM service_executions WHERE tenant_id=? AND service_order_id=? AND state NOT IN ('completed','cancelled')", (tenant_id, order_id)).fetchone()
        if pending and int(pending["total"]) > 0:
            raise DomainError("SERVICE_EXECUTIONS_PENDING", "Existem execuções pendentes para o pedido.", 409)
        now = iso_now()
        conn.execute("UPDATE service_orders SET state='completed',completed_at=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, now, tenant_id, order_id))
        result = _order_detail_conn(conn, tenant_id, order_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="complete", aggregate_type="service_order", aggregate_id=order_id, before={"status": order["state"]}, after={"status": "completed"})
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceOrderCompleted", aggregate_type="service_order", aggregate_id=order_id, payload={"id": order_id})
        return result


def cancel_order(request: Request, tenant_id: str, user: CurrentUser, order_id: str, data: OrderCancel) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        order = _one(conn, "SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
        if order["state"] == "cancelled":
            return _order_detail_conn(conn, tenant_id, order_id)
        if order["state"] == "completed":
            raise DomainError("SERVICE_ORDER_ALREADY_COMPLETED", "Pedido concluído não pode ser cancelado; use fluxo de estorno.", 409)
        now = iso_now()
        charge_id = order.get("charge_id")
        if charge_id:
            charge = _one(conn, "SELECT * FROM charges WHERE tenant_id=? AND id=?", (tenant_id, charge_id), "CHARGE_NOT_FOUND", "Cobrança vinculada não localizada.")
            if money(charge.get("paid_amount") or 0) > 0:
                raise DomainError("PAID_CHARGE_CANNOT_BE_CANCELLED", "Cobrança com pagamento deve ser estornada pelo fluxo financeiro.", 409)
            conn.execute("UPDATE charges SET state='cancelled',outstanding_amount=0,cancelled_at=?,cancellation_reason=?,updated_at=? WHERE tenant_id=? AND id=?", (now, data.reason, now, tenant_id, charge_id))
            conn.execute("UPDATE accounts_receivable SET state='cancelled',outstanding_amount=0,updated_at=? WHERE tenant_id=? AND charge_id=?", (now, tenant_id, charge_id))
            if order.get("financial_contract_id"):
                conn.execute("UPDATE installments SET state='cancelled',updated_at=? WHERE tenant_id=? AND financial_contract_id=? AND state IN ('open','partial')", (now, tenant_id, order["financial_contract_id"]))
            original = conn.execute("SELECT id FROM ledger_entries WHERE tenant_id=? AND reference_type='charge' AND reference_id=? AND entry_type='charge' ORDER BY occurred_at LIMIT 1", (tenant_id, charge_id)).fetchone()
            conn.execute(
                "INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,debit_account,credit_account,amount,occurred_at,reversal_of_id,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, "charge_reversal", "charge", charge_id, "service_revenue", "accounts_receivable", charge["total_amount"], now, original["id"] if original else None, "Cancelamento compensatório de cobrança de serviço", now),
            )
        conn.execute("UPDATE service_executions SET state='cancelled',completed_at=?,notes=COALESCE(notes,'') || ?,version=version+1,updated_at=? WHERE tenant_id=? AND service_order_id=? AND state NOT IN ('completed','cancelled')", (now, f"\nCancelada: {data.reason}", now, tenant_id, order_id))
        conn.execute("UPDATE service_orders SET state='cancelled',cancelled_at=?,cancellation_reason=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, data.reason, now, tenant_id, order_id))
        result = _order_detail_conn(conn, tenant_id, order_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="cancel", aggregate_type="service_order", aggregate_id=order_id, before={"status": order["state"]}, after={"status": "cancelled"}, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceOrderCancelled", aggregate_type="service_order", aggregate_id=order_id, payload={"id": order_id, "charge_id": charge_id, "reason": data.reason})
        return result


def create_execution(request: Request, tenant_id: str, user: CurrentUser, order_id: str, data: ExecutionCreate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:execution:create:{tenant_id}:{order_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        order = _one(conn, "SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "SERVICE_ORDER_NOT_FOUND", "Pedido de serviço não localizado.")
        if order["state"] not in {"confirmed", "in_progress"}:
            raise DomainError("SERVICE_ORDER_INVALID_STATE", "Execuções só podem ser criadas para pedidos confirmados ou em andamento.", 409)
        item = _one(conn, "SELECT * FROM service_order_items WHERE tenant_id=? AND id=? AND service_order_id=?", (tenant_id, data.order_item_id, order_id), "SERVICE_ORDER_ITEM_NOT_FOUND", "Item do pedido não localizado.")
        remaining = quantity(item["quantity"]) - quantity(item.get("executed_quantity") or 0)
        if quantity(data.quantity) > remaining:
            raise DomainError("SERVICE_EXECUTION_QUANTITY_EXCEEDED", "Quantidade da execução excede o saldo do item.", 409)
        _ensure_person(conn, tenant_id, data.performer_person_id)
        execution_id, now = uuid7(), iso_now()
        conn.execute(
            "INSERT INTO service_executions(id,tenant_id,execution_number,service_order_id,service_order_item_id,subscription_id,scheduled_at,quantity,state,performer_person_id,notes,evidence_json,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (execution_id, tenant_id, f"EXE-{execution_id[-12:].upper()}", order_id, data.order_item_id, order.get("subscription_id"), data.scheduled_at.isoformat() if data.scheduled_at else None, str(quantity(data.quantity)), "scheduled", data.performer_person_id, data.notes, "{}", data.institution_id or order.get("institution_id"), data.unit_id or order.get("unit_id"), 1, now, now),
        )
        result = _status(dict(conn.execute("SELECT * FROM service_executions WHERE tenant_id=? AND id=?", (tenant_id, execution_id)).fetchone()))
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_execution", aggregate_id=execution_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceExecutionScheduled", aggregate_type="service_execution", aggregate_id=execution_id, payload={"id": execution_id, "order_id": order_id})
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def _execution_transition(request: Request, tenant_id: str, user: CurrentUser, execution_id: str, action: str, data: Any) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        execution = _one(conn, "SELECT * FROM service_executions WHERE tenant_id=? AND id=?", (tenant_id, execution_id), "SERVICE_EXECUTION_NOT_FOUND", "Execução de serviço não localizada.")
        now = iso_now()
        if action == "start":
            if execution["state"] == "in_progress":
                return _status(execution)
            if execution["state"] != "scheduled":
                raise DomainError("SERVICE_EXECUTION_INVALID_STATE", "Somente execução agendada pode ser iniciada.", 409)
            conn.execute("UPDATE service_executions SET state='in_progress',started_at=?,notes=COALESCE(?,notes),version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, data.notes, now, tenant_id, execution_id))
            event, new_state, reason = "ServiceExecutionStarted", "in_progress", data.notes
        elif action == "complete":
            if execution["state"] == "completed":
                return _status(execution)
            if execution["state"] not in {"scheduled", "in_progress"}:
                raise DomainError("SERVICE_EXECUTION_INVALID_STATE", "Execução não pode ser concluída no estado atual.", 409)
            item = _one(conn, "SELECT * FROM service_order_items WHERE tenant_id=? AND id=?", (tenant_id, execution["service_order_item_id"]), "SERVICE_ORDER_ITEM_NOT_FOUND", "Item do pedido não localizado.")
            completed = quantity(data.completed_quantity or execution["quantity"])
            if completed > quantity(execution["quantity"]):
                raise DomainError("SERVICE_EXECUTION_QUANTITY_EXCEEDED", "Quantidade concluída excede a quantidade programada.", 409)
            accumulated = quantity(item.get("executed_quantity") or 0) + completed
            if accumulated > quantity(item["quantity"]):
                raise DomainError("SERVICE_ITEM_EXECUTION_QUANTITY_EXCEEDED", "Quantidade executada excede o item do pedido.", 409)
            item_state = "completed" if accumulated == quantity(item["quantity"]) else "partially_executed"
            conn.execute("UPDATE service_order_items SET executed_quantity=?,execution_status=? WHERE tenant_id=? AND id=?", (str(accumulated), item_state, tenant_id, item["id"]))
            conn.execute("UPDATE service_executions SET state='completed',started_at=COALESCE(started_at,?),completed_at=?,quantity=?,notes=COALESCE(?,notes),evidence_json=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, now, str(completed), data.notes, dumps(data.evidence), now, tenant_id, execution_id))
            event, new_state, reason = "ServiceExecutionCompleted", "completed", data.notes
        else:
            if execution["state"] == "cancelled":
                return _status(execution)
            if execution["state"] == "completed":
                raise DomainError("SERVICE_EXECUTION_ALREADY_COMPLETED", "Execução concluída não pode ser cancelada.", 409)
            conn.execute("UPDATE service_executions SET state='cancelled',completed_at=?,notes=COALESCE(notes,'') || ?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, f"\nCancelada: {data.reason}", now, tenant_id, execution_id))
            event, new_state, reason = "ServiceExecutionCancelled", "cancelled", data.reason
        after = _status(dict(conn.execute("SELECT * FROM service_executions WHERE tenant_id=? AND id=?", (tenant_id, execution_id)).fetchone()))
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action=action, aggregate_type="service_execution", aggregate_id=execution_id, before=_status(execution), after=after, reason=reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type=event, aggregate_type="service_execution", aggregate_id=execution_id, payload={"id": execution_id, "order_id": execution["service_order_id"], "status": new_state})
        return after


def start_execution(request: Request, tenant_id: str, user: CurrentUser, execution_id: str, data: ExecutionStart) -> dict[str, Any]:
    return _execution_transition(request, tenant_id, user, execution_id, "start", data)


def complete_execution(request: Request, tenant_id: str, user: CurrentUser, execution_id: str, data: ExecutionComplete) -> dict[str, Any]:
    return _execution_transition(request, tenant_id, user, execution_id, "complete", data)


def cancel_execution(request: Request, tenant_id: str, user: CurrentUser, execution_id: str, data: ExecutionCancel) -> dict[str, Any]:
    return _execution_transition(request, tenant_id, user, execution_id, "cancel", data)


def list_executions(request: Request, tenant_id: str, status: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM service_executions WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if order_id:
        sql += " AND service_order_id=?"
        params.append(order_id)
    sql += " ORDER BY created_at DESC,id DESC"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def subscription_detail(request: Request, tenant_id: str, subscription_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM service_subscriptions WHERE tenant_id=? AND id=?", (tenant_id, subscription_id))
    if not row:
        raise DomainError("SERVICE_SUBSCRIPTION_NOT_FOUND", "Assinatura de serviço não localizada.", 404)
    result = _status(row)
    result["competencies"] = [_status(item) for item in request.state.store.fetch_all("SELECT * FROM service_competencies WHERE tenant_id=? AND subscription_id=? ORDER BY competence_key DESC", (tenant_id, subscription_id))]
    return result


def list_subscriptions(request: Request, tenant_id: str, status: str | None = None, person_id: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM service_subscriptions WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if person_id:
        sql += " AND subscriber_person_id=?"
        params.append(person_id)
    sql += " ORDER BY created_at DESC,id DESC"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def create_subscription(request: Request, tenant_id: str, user: CurrentUser, data: SubscriptionCreate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:subscription:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        service = _one(conn, "SELECT * FROM services WHERE tenant_id=? AND id=? AND state='active'", (tenant_id, data.service_id), "SERVICE_NOT_FOUND", "Serviço não localizado ou inativo.")
        if data.variant_id:
            _one(conn, "SELECT id FROM service_variants WHERE tenant_id=? AND id=? AND service_id=? AND state='active'", (tenant_id, data.variant_id, data.service_id), "SERVICE_VARIANT_NOT_FOUND", "Variação do serviço não localizada ou inativa.")
        _ensure_person(conn, tenant_id, data.subscriber_person_id)
        if data.enrollment_id:
            _one(conn, "SELECT id FROM enrollments WHERE tenant_id=? AND id=?", (tenant_id, data.enrollment_id), "ENROLLMENT_NOT_FOUND", "Matrícula não localizada.")
        rule = _one(conn, "SELECT * FROM service_billing_rules WHERE tenant_id=? AND id=? AND service_id=? AND state='active'", (tenant_id, data.billing_rule_id, data.service_id), "SERVICE_BILLING_RULE_NOT_FOUND", "Regra de cobrança não localizada ou inativa.")
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        unit_price = money(data.unit_price) if data.unit_price is not None else _price_for(conn, tenant_id, data.service_id, data.variant_id, data.starts_on)
        cycle = (unit_price * quantity(data.quantity) - money(data.discount_amount)).quantize(CENT, rounding=ROUND_HALF_UP)
        if cycle < 0:
            raise DomainError("SERVICE_SUBSCRIPTION_DISCOUNT_EXCEEDED", "O desconto excede o valor do ciclo.", 422)
        subscription_id, now = uuid7(), iso_now()
        next_date = data.next_competence_on or data.starts_on
        try:
            conn.execute(
                "INSERT INTO service_subscriptions(id,tenant_id,subscription_number,service_id,variant_id,subscriber_person_id,enrollment_id,financial_contract_id,billing_rule_id,starts_on,ends_on,quantity,unit_price,discount_amount,cycle_amount,next_competence_on,auto_renew,state,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (subscription_id, tenant_id, data.subscription_number, data.service_id, data.variant_id, data.subscriber_person_id, data.enrollment_id, data.financial_contract_id, data.billing_rule_id, data.starts_on.isoformat(), data.ends_on.isoformat() if data.ends_on else None, str(quantity(data.quantity)), money_str(unit_price), money_str(data.discount_amount), money_str(cycle), next_date.isoformat(), 1 if data.auto_renew else 0, "draft", data.institution_id, data.unit_id, 1, now, now),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("SERVICE_SUBSCRIPTION_NUMBER_EXISTS", "Já existe assinatura com este número.", 409) from exc
            raise
        result = {"id": subscription_id, "subscription_number": data.subscription_number, "service_id": service["id"], "billing_rule_id": rule["id"], "unit_price": money_str(unit_price), "cycle_amount": money_str(cycle), "next_competence_on": next_date.isoformat(), "status": "draft", "state": "draft", "version": 1}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="service_subscription", aggregate_id=subscription_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceSubscriptionCreated", aggregate_type="service_subscription", aggregate_id=subscription_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def change_subscription_status(request: Request, tenant_id: str, user: CurrentUser, subscription_id: str, target: str, data: SubscriptionDecision) -> dict[str, Any]:
    transitions = {
        "active": {"draft", "suspended"},
        "suspended": {"active"},
        "cancelled": {"draft", "active", "suspended"},
    }
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM service_subscriptions WHERE tenant_id=? AND id=?", (tenant_id, subscription_id), "SERVICE_SUBSCRIPTION_NOT_FOUND", "Assinatura de serviço não localizada.")
        if before["state"] == target:
            return _status(before)
        if before["state"] not in transitions[target]:
            raise DomainError("SERVICE_SUBSCRIPTION_INVALID_STATE", "Transição de estado da assinatura não permitida.", 409)
        now = iso_now()
        suspended_at = now if target == "suspended" else None
        cancelled_at = now if target == "cancelled" else None
        cancellation_reason = data.reason if target == "cancelled" else None
        conn.execute("UPDATE service_subscriptions SET state=?,suspended_at=?,cancelled_at=?,cancellation_reason=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (target, suspended_at, cancelled_at, cancellation_reason, now, tenant_id, subscription_id))
        after = _status(dict(conn.execute("SELECT * FROM service_subscriptions WHERE tenant_id=? AND id=?", (tenant_id, subscription_id)).fetchone()))
        verb = {"active": "activate", "suspended": "suspend", "cancelled": "cancel"}[target]
        event = {"active": "ServiceSubscriptionActivated", "suspended": "ServiceSubscriptionSuspended", "cancelled": "ServiceSubscriptionCancelled"}[target]
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action=verb, aggregate_type="service_subscription", aggregate_id=subscription_id, before=_status(before), after=after, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type=event, aggregate_type="service_subscription", aggregate_id=subscription_id, payload={"id": subscription_id, "status": target})
        return after


def generate_competence(request: Request, tenant_id: str, user: CurrentUser, subscription_id: str, data: CompetenceGenerate, key: str | None) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"services:competence:create:{tenant_id}:{subscription_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        subscription = _one(conn, "SELECT * FROM service_subscriptions WHERE tenant_id=? AND id=?", (tenant_id, subscription_id), "SERVICE_SUBSCRIPTION_NOT_FOUND", "Assinatura de serviço não localizada.")
        if subscription["state"] != "active":
            raise DomainError("SERVICE_SUBSCRIPTION_NOT_ACTIVE", "Somente assinatura ativa pode gerar competência.", 409)
        existing = conn.execute("SELECT id FROM service_competencies WHERE tenant_id=? AND subscription_id=? AND competence_key=?", (tenant_id, subscription_id, data.competence_key)).fetchone()
        if existing and not data.force:
            result = _competence_detail_conn(conn, tenant_id, existing["id"])
            _save(conn, scope, key, payload, 201, result)
            return 201, result
        if existing and data.force:
            raise DomainError("SERVICE_COMPETENCE_ALREADY_EXISTS", "A competência já existe; utilize o fluxo de estorno/reprocessamento.", 409)
        period_start, period_end = _month_period(data.competence_key)
        starts_on = _normalize_date(subscription["starts_on"])
        ends_on = _normalize_date(subscription.get("ends_on"))
        if starts_on and period_end < starts_on:
            raise DomainError("SERVICE_COMPETENCE_BEFORE_SUBSCRIPTION", "Competência anterior ao início da assinatura.", 409)
        if ends_on and period_start > ends_on:
            raise DomainError("SERVICE_COMPETENCE_AFTER_SUBSCRIPTION", "Competência posterior ao término da assinatura.", 409)
        rule = _one(conn, "SELECT * FROM service_billing_rules WHERE tenant_id=? AND id=?", (tenant_id, subscription["billing_rule_id"]), "SERVICE_BILLING_RULE_NOT_FOUND", "Regra de cobrança não localizada.")
        due = data.due_date or _due_date(period_start, int(rule.get("due_day") or 10))
        competence_id, order_id, now = uuid7(), uuid7(), iso_now()
        amount = money(subscription["cycle_amount"])
        conn.execute(
            "INSERT INTO service_competencies(id,tenant_id,subscription_id,competence_key,period_start,period_end,due_date,amount,state,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (competence_id, tenant_id, subscription_id, data.competence_key, period_start.isoformat(), period_end.isoformat(), due.isoformat(), money_str(amount), "pending", subscription.get("institution_id"), subscription.get("unit_id"), 1, now, now),
        )
        service = _one(conn, "SELECT * FROM services WHERE tenant_id=? AND id=?", (tenant_id, subscription["service_id"]), "SERVICE_NOT_FOUND", "Serviço não localizado.")
        profile = _fiscal_profile_for(conn, tenant_id, service["id"], subscription.get("variant_id"), period_start)
        snapshot = _fiscal_snapshot(service, profile)
        conn.execute(
            "INSERT INTO service_orders(id,tenant_id,enrollment_id,competence,state,total_amount,order_number,subscriber_person_id,subscription_id,competence_id,cost_center_id,currency,subtotal,discount_amount,due_date,installment_count,fiscal_status,notes,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (order_id, tenant_id, subscription.get("enrollment_id"), data.competence_key, "draft", money_str(amount), f"SRV-{data.competence_key.replace('-','')}-{order_id[-8:].upper()}", subscription["subscriber_person_id"], subscription_id, competence_id, service.get("cost_center_id"), "BRL", money_str(amount), "0.00", due.isoformat(), int(rule.get("installment_count") or 1), "pending", f"Competência {data.competence_key} da assinatura {subscription['subscription_number']}", subscription.get("institution_id"), subscription.get("unit_id"), 1, now, now),
        )
        item_id = uuid7()
        conn.execute(
            "INSERT INTO service_order_items(id,tenant_id,service_order_id,service_id,quantity,unit_price,total_amount,variant_id,description,discount_amount,competence_start,competence_end,fiscal_profile_snapshot_json,execution_status,executed_quantity,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, tenant_id, order_id, service["id"], subscription["quantity"], subscription["unit_price"], money_str(amount), subscription.get("variant_id"), service["name"], subscription["discount_amount"], period_start.isoformat(), period_end.isoformat(), dumps(snapshot), "pending", "0.0000", now),
        )
        # Confirmação transacional, sem commit intermediário.
        order = dict(conn.execute("SELECT * FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id)).fetchone())
        items = [dict(conn.execute("SELECT soi.*,s.code AS service_code,s.name AS service_name,s.taxable FROM service_order_items soi JOIN services s ON s.id=soi.service_id WHERE soi.tenant_id=? AND soi.id=?", (tenant_id, item_id)).fetchone())]
        charge_id = _create_charge(conn, tenant_id, user, order, items, now)
        configured = _integration_configured(conn, tenant_id)
        complete = snapshot.get("classification_status") == "complete"
        if not complete:
            fiscal_state, failure_code, failure_message = "blocked_validation", "SERVICE_FISCAL_CLASSIFICATION_INCOMPLETE", "Classificação fiscal obrigatória incompleta."
        elif not configured:
            fiscal_state, failure_code, failure_message = "not_configured", "FISCAL_PROVIDER_NOT_CONFIGURED", "Provider fiscal não configurado."
        else:
            fiscal_state, failure_code, failure_message = "queued", None, None
        fiscal_event_id = uuid7()
        conn.execute(
            "INSERT INTO service_fiscal_events(id,tenant_id,event_key,service_order_id,service_order_item_id,competence_id,trigger_type,document_type,state,payload_snapshot_json,requested_at,failure_code,failure_message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fiscal_event_id, tenant_id, f"service-competence:{competence_id}:billing", order_id, item_id, competence_id, rule.get("fiscal_trigger") or "competence", "nfse", fiscal_state, dumps({"competence_id": competence_id, "order_id": order_id, "charge_id": charge_id, "classification": snapshot}), now, failure_code, failure_message, now, now),
        )
        execution_id = uuid7()
        conn.execute(
            "INSERT INTO service_executions(id,tenant_id,execution_number,service_order_id,service_order_item_id,subscription_id,quantity,state,evidence_json,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (execution_id, tenant_id, f"EXE-{execution_id[-12:].upper()}", order_id, item_id, subscription_id, subscription["quantity"], "scheduled", "{}", subscription.get("institution_id"), subscription.get("unit_id"), 1, now, now),
        )
        conn.execute("UPDATE service_orders SET state='confirmed',financial_contract_id=(SELECT financial_contract_id FROM charges WHERE id=?),charge_id=?,fiscal_status=?,confirmed_at=?,confirmed_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (charge_id, charge_id, fiscal_state, now, user.id, now, tenant_id, order_id))
        next_date = _month_add(period_start, int(rule.get("interval_months") or 1))
        conn.execute("UPDATE service_competencies SET service_order_id=?,charge_id=?,state='billed',billed_at=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (order_id, charge_id, now, now, tenant_id, competence_id))
        conn.execute("UPDATE service_subscriptions SET next_competence_on=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (next_date.isoformat(), now, tenant_id, subscription_id))
        result = _competence_detail_conn(conn, tenant_id, competence_id)
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="generate_competence", aggregate_type="service_subscription", aggregate_id=subscription_id, after={"competence_id": competence_id, "order_id": order_id, "charge_id": charge_id, "amount": money_str(amount)})
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceCompetenceBilled", aggregate_type="service_competence", aggregate_id=competence_id, payload={"id": competence_id, "subscription_id": subscription_id, "order_id": order_id, "charge_id": charge_id})
        _event(conn, tenant_id=tenant_id, request=request, event_type="ServiceOrderConfirmed", aggregate_type="service_order", aggregate_id=order_id, payload={"id": order_id, "charge_id": charge_id, "fiscal_status": fiscal_state})
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def _competence_detail_conn(conn: Any, tenant_id: str, competence_id: str) -> dict[str, Any]:
    row = _one(conn, "SELECT * FROM service_competencies WHERE tenant_id=? AND id=?", (tenant_id, competence_id), "SERVICE_COMPETENCE_NOT_FOUND", "Competência de serviço não localizada.")
    result = _status(row)
    if row.get("service_order_id"):
        result["order"] = _order_detail_conn(conn, tenant_id, row["service_order_id"])
    else:
        result["order"] = None
    return result


def list_fiscal_events(request: Request, tenant_id: str, status: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM service_fiscal_events WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if order_id:
        sql += " AND service_order_id=?"
        params.append(order_id)
    sql += " ORDER BY requested_at DESC,id DESC"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def dashboard(request: Request, tenant_id: str) -> dict[str, Any]:
    store = request.state.store
    def count(sql: str, params: tuple[Any, ...] = ()) -> int:
        row = store.fetch_one(sql, params)
        return int(next(iter(row.values()))) if row else 0
    billed = store.fetch_one("SELECT COALESCE(SUM(total_amount),0) AS total FROM service_orders WHERE tenant_id=? AND state IN ('confirmed','in_progress','completed')", (tenant_id,))
    return {
        "services": count("SELECT COUNT(*) AS total FROM services WHERE tenant_id=? AND state='active'", (tenant_id,)),
        "active_subscriptions": count("SELECT COUNT(*) AS total FROM service_subscriptions WHERE tenant_id=? AND state='active'", (tenant_id,)),
        "open_orders": count("SELECT COUNT(*) AS total FROM service_orders WHERE tenant_id=? AND state IN ('draft','confirmed','in_progress')", (tenant_id,)),
        "pending_executions": count("SELECT COUNT(*) AS total FROM service_executions WHERE tenant_id=? AND state IN ('scheduled','in_progress')", (tenant_id,)),
        "blocked_fiscal_events": count("SELECT COUNT(*) AS total FROM service_fiscal_events WHERE tenant_id=? AND state='blocked_validation'", (tenant_id,)),
        "not_configured_fiscal_events": count("SELECT COUNT(*) AS total FROM service_fiscal_events WHERE tenant_id=? AND state='not_configured'", (tenant_id,)),
        "billed_total": money_str(billed["total"] if billed else 0),
    }
