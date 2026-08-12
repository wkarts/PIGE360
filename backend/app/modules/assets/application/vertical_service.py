from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from fastapi import Request

from app.modules.assets.presentation.vertical_schemas import (
    AssetCreate,
    AssetLoanCreate,
    AssetLoanReturn,
    AssetLocationCreate,
    AssetMaintenanceComplete,
    AssetMaintenanceCreate,
    AssetTransfer,
    DepreciationCalculate,
)
from app.modules.operations.common import dumps, loads
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _body(data: Any) -> dict[str, Any]:
    return data.model_dump(mode="json") if hasattr(data, "model_dump") else dict(data)


def _one(conn: Any, sql: str, params: Iterable[Any], code: str, message: str) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, message, 404)
    return dict(row)


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "state" in result:
        result.setdefault("status", result["state"])
    if "metadata_json" in result:
        result["metadata"] = loads(result["metadata_json"], {})
    return result


def _cached(conn: Any, scope: str, key: str | None, payload: Any) -> tuple[int, Any] | None:
    return get_idempotent(conn, scope, key, payload) if key else None


def _save(conn: Any, scope: str, key: str | None, payload: Any, status: int, result: Any) -> None:
    if key:
        save_idempotent(conn, scope, key, payload, status, result)


def _audit(
    conn: Any,
    *,
    tenant_id: str,
    user: CurrentUser,
    request: Request,
    action: str,
    aggregate_type: str,
    aggregate_id: str,
    before: Any = None,
    after: Any = None,
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
    payload: Any,
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


def _location(conn: Any, tenant_id: str, location_id: str, *, active: bool = True) -> dict[str, Any]:
    sql = "SELECT * FROM asset_locations WHERE tenant_id=? AND id=?"
    params: list[Any] = [tenant_id, location_id]
    if active:
        sql += " AND state='active'"
    return _one(
        conn,
        sql,
        params,
        "ASSET_LOCATION_NOT_FOUND",
        "Localização patrimonial não localizada ou inativa.",
    )


def _asset(conn: Any, tenant_id: str, asset_id: str) -> dict[str, Any]:
    return _one(
        conn,
        "SELECT * FROM assets WHERE tenant_id=? AND id=?",
        (tenant_id, asset_id),
        "ASSET_NOT_FOUND",
        "Patrimônio não localizado.",
    )


def _person(conn: Any, tenant_id: str, person_id: str | None) -> dict[str, Any] | None:
    if person_id is None:
        return None
    return _one(
        conn,
        "SELECT id FROM people WHERE tenant_id=? AND id=?",
        (tenant_id, person_id),
        "PERSON_NOT_FOUND",
        "Pessoa informada não pertence ao tenant.",
    )


def _number(prefix: str, identifier: str) -> str:
    return f"{prefix}-{date.today():%Y%m%d}-{identifier.replace('-', '').upper()[-12:]}"


def _month_index(value: date) -> int:
    return value.year * 12 + value.month


def list_locations(
    request: Request,
    tenant_id: str,
    *,
    status: str | None,
    parent_id: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    sql = "SELECT * FROM asset_locations WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if parent_id:
        sql += " AND parent_id=?"
        params.append(parent_id)
    if cursor:
        sql += " AND id>?"
        params.append(cursor)
    safe_limit = min(max(limit, 1), 500)
    sql += " ORDER BY id LIMIT ?"
    params.append(safe_limit + 1)
    rows = request.state.store.fetch_all(sql, params)
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    return {
        "items": [_normalize(row) for row in rows],
        "count": len(rows),
        "next_cursor": rows[-1]["id"] if has_more and rows else None,
    }


def create_location(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: AssetLocationCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"assets:location:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        parent = _location(conn, tenant_id, data.parent_id) if data.parent_id else None
        if conn.execute(
            "SELECT id FROM asset_locations WHERE tenant_id=? AND code=?",
            (tenant_id, data.code),
        ).fetchone():
            raise DomainError("ASSET_LOCATION_CODE_EXISTS", "Já existe localização com este código.", 409)
        if parent:
            if data.institution_id and parent.get("institution_id") and data.institution_id != parent["institution_id"]:
                raise DomainError("ASSET_LOCATION_SCOPE_MISMATCH", "A localização pai pertence a outra instituição.", 409)
            if data.unit_id and parent.get("unit_id") and data.unit_id != parent["unit_id"]:
                raise DomainError("ASSET_LOCATION_SCOPE_MISMATCH", "A localização pai pertence a outra unidade.", 409)
        location_id, now = uuid7(), iso_now()
        conn.execute(
            "INSERT INTO asset_locations(id,tenant_id,code,name,parent_id,state,institution_id,unit_id,version,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                location_id,
                tenant_id,
                data.code,
                data.name.strip(),
                data.parent_id,
                "active",
                data.institution_id or (parent.get("institution_id") if parent else None),
                data.unit_id or (parent.get("unit_id") if parent else None),
                1,
                now,
                now,
            ),
        )
        result = _normalize(
            dict(conn.execute("SELECT * FROM asset_locations WHERE id=?", (location_id,)).fetchone())
        )
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create",
            aggregate_type="asset_location",
            aggregate_id=location_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetLocationCreated",
            aggregate_type="asset_location",
            aggregate_id=location_id,
            payload=result,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def location_detail(request: Request, tenant_id: str, location_id: str) -> dict[str, Any]:
    location = request.state.store.fetch_one(
        "SELECT * FROM asset_locations WHERE tenant_id=? AND id=?", (tenant_id, location_id)
    )
    if not location:
        raise DomainError("ASSET_LOCATION_NOT_FOUND", "Localização patrimonial não localizada.", 404)
    children = request.state.store.fetch_all(
        "SELECT * FROM asset_locations WHERE tenant_id=? AND parent_id=? ORDER BY name,id",
        (tenant_id, location_id),
    )
    assets = request.state.store.fetch_all(
        "SELECT * FROM assets WHERE tenant_id=? AND location_id=? ORDER BY COALESCE(name,description),id LIMIT 200",
        (tenant_id, location_id),
    )
    return {
        "location": _normalize(location),
        "children": [_normalize(row) for row in children],
        "assets": [_normalize(row) for row in assets],
    }


def list_assets(
    request: Request,
    tenant_id: str,
    *,
    status: str | None,
    location_id: str | None,
    responsible_person_id: str | None,
    search: str | None,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    sql = (
        "SELECT a.*,l.code AS location_code,l.name AS location_name,p.name AS product_name "
        "FROM assets a LEFT JOIN asset_locations l ON l.id=a.location_id AND l.tenant_id=a.tenant_id "
        "LEFT JOIN products p ON p.id=a.product_id AND p.tenant_id=a.tenant_id WHERE a.tenant_id=?"
    )
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND a.state=?"
        params.append(status)
    if location_id:
        sql += " AND a.location_id=?"
        params.append(location_id)
    if responsible_person_id:
        sql += " AND a.responsible_person_id=?"
        params.append(responsible_person_id)
    if search:
        sql += " AND (a.name LIKE ? OR a.tag LIKE ? OR a.asset_number LIKE ? OR a.serial_number LIKE ? OR a.description LIKE ?)"
        term = f"%{search.strip()}%"
        params.extend([term, term, term, term, term])
    if cursor:
        sql += " AND a.id>?"
        params.append(cursor)
    safe_limit = min(max(limit, 1), 500)
    sql += " ORDER BY a.id LIMIT ?"
    params.append(safe_limit + 1)
    rows = request.state.store.fetch_all(sql, params)
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    return {
        "items": [_normalize(row) for row in rows],
        "count": len(rows),
        "next_cursor": rows[-1]["id"] if has_more and rows else None,
    }


def create_asset(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: AssetCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"assets:asset:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        location = _location(conn, tenant_id, data.location_id)
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        _person(conn, tenant_id, data.responsible_person_id)
        if conn.execute(
            "SELECT id FROM assets WHERE tenant_id=? AND tag=?", (tenant_id, data.tag)
        ).fetchone():
            raise DomainError("ASSET_TAG_EXISTS", "A etiqueta patrimonial já está cadastrada.", 409)
        product: dict[str, Any] | None = None
        if data.product_id:
            product = _one(
                conn,
                "SELECT * FROM products WHERE tenant_id=? AND id=? AND state='active'",
                (tenant_id, data.product_id),
                "PRODUCT_NOT_FOUND",
                "Produto não localizado ou inativo.",
            )
        receipt_item: dict[str, Any] | None = None
        if data.receipt_item_id:
            receipt_item = _one(
                conn,
                "SELECT * FROM goods_receipt_items WHERE tenant_id=? AND id=?",
                (tenant_id, data.receipt_item_id),
                "GOODS_RECEIPT_ITEM_NOT_FOUND",
                "Item de recebimento não localizado.",
            )
            if product and receipt_item["product_id"] != product["id"]:
                raise DomainError(
                    "ASSET_RECEIPT_PRODUCT_MISMATCH",
                    "O item recebido não corresponde ao produto do patrimônio.",
                    409,
                )
            if product is None:
                product = _one(
                    conn,
                    "SELECT * FROM products WHERE tenant_id=? AND id=?",
                    (tenant_id, receipt_item["product_id"]),
                    "PRODUCT_NOT_FOUND",
                    "Produto do recebimento não localizado.",
                )
            linked = conn.execute(
                "SELECT COUNT(*) AS total FROM assets WHERE tenant_id=? AND receipt_item_id=?",
                (tenant_id, receipt_item["id"]),
            ).fetchone()["total"]
            if Decimal(str(linked + 1)) > Decimal(str(receipt_item["quantity"])):
                raise DomainError(
                    "ASSET_RECEIPT_QUANTITY_EXCEEDED",
                    "A quantidade de patrimônios vinculados supera a quantidade recebida.",
                    409,
                )
        acquisition_cost = money(data.acquisition_cost)
        residual_value = money(data.residual_value)
        if residual_value > acquisition_cost:
            raise DomainError(
                "INVALID_ASSET_RESIDUAL_VALUE",
                "O valor residual não pode superar o custo de aquisição.",
                422,
            )
        if location.get("institution_id") and data.institution_id and location["institution_id"] != data.institution_id:
            raise DomainError("ASSET_LOCATION_SCOPE_MISMATCH", "A localização pertence a outra instituição.", 409)
        if location.get("unit_id") and data.unit_id and location["unit_id"] != data.unit_id:
            raise DomainError("ASSET_LOCATION_SCOPE_MISMATCH", "A localização pertence a outra unidade.", 409)
        asset_id, now = uuid7(), iso_now()
        asset_number = _number("PAT", asset_id)
        description = data.description or data.name.strip()
        conn.execute(
            "INSERT INTO assets(id,tenant_id,asset_number,description,acquisition_date,acquisition_cost,location,responsible_person_id,state,tag,name,location_id,product_id,receipt_item_id,serial_number,useful_life_months,residual_value,accumulated_depreciation,warranty_until,metadata_json,institution_id,unit_id,version,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                asset_id,
                tenant_id,
                asset_number,
                description,
                data.acquisition_date.isoformat(),
                str(acquisition_cost),
                location["name"],
                data.responsible_person_id,
                "active",
                data.tag,
                data.name.strip(),
                location["id"],
                product["id"] if product else None,
                receipt_item["id"] if receipt_item else None,
                data.serial_number,
                data.useful_life_months,
                str(residual_value),
                "0.00",
                data.warranty_until.isoformat() if data.warranty_until else None,
                dumps(data.metadata),
                data.institution_id or location.get("institution_id"),
                data.unit_id or location.get("unit_id"),
                1,
                now,
                now,
            ),
        )
        movement_id = uuid7()
        conn.execute(
            "INSERT INTO asset_movements(id,tenant_id,asset_id,movement_type,from_location_id,to_location_id,from_responsible_person_id,to_responsible_person_id,reason,occurred_at,occurred_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                movement_id,
                tenant_id,
                asset_id,
                "acquisition",
                None,
                location["id"],
                None,
                data.responsible_person_id,
                "Cadastro e incorporação do patrimônio",
                now,
                user.id,
                now,
            ),
        )
        asset = _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()))
        movement = dict(conn.execute("SELECT * FROM asset_movements WHERE id=?", (movement_id,)).fetchone())
        result = {"asset": asset, "movement": movement}
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create",
            aggregate_type="asset",
            aggregate_id=asset_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetRegistered",
            aggregate_type="asset",
            aggregate_id=asset_id,
            payload=asset,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def asset_detail(request: Request, tenant_id: str, asset_id: str) -> dict[str, Any]:
    asset = request.state.store.fetch_one("SELECT * FROM assets WHERE tenant_id=? AND id=?", (tenant_id, asset_id))
    if not asset:
        raise DomainError("ASSET_NOT_FOUND", "Patrimônio não localizado.", 404)
    return {
        "asset": _normalize(asset),
        "movements": request.state.store.fetch_all(
            "SELECT * FROM asset_movements WHERE tenant_id=? AND asset_id=? ORDER BY occurred_at DESC,id DESC",
            (tenant_id, asset_id),
        ),
        "maintenances": [_normalize(row) for row in request.state.store.fetch_all(
            "SELECT * FROM asset_maintenances WHERE tenant_id=? AND asset_id=? ORDER BY created_at DESC,id DESC",
            (tenant_id, asset_id),
        )],
        "loans": [_normalize(row) for row in request.state.store.fetch_all(
            "SELECT * FROM asset_loans WHERE tenant_id=? AND asset_id=? ORDER BY loaned_at DESC,id DESC",
            (tenant_id, asset_id),
        )],
        "depreciations": request.state.store.fetch_all(
            "SELECT * FROM asset_depreciations WHERE tenant_id=? AND asset_id=? ORDER BY competence,id",
            (tenant_id, asset_id),
        ),
    }


def transfer_asset(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    asset_id: str,
    data: AssetTransfer,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        asset = _asset(conn, tenant_id, asset_id)
        if asset["state"] in {"written_off", "lost", "disposed", "maintenance"}:
            raise DomainError("ASSET_NOT_TRANSFERABLE", "O patrimônio não pode ser transferido neste estado.", 409)
        location = _location(conn, tenant_id, data.location_id)
        _person(conn, tenant_id, data.responsible_person_id)
        if asset["state"] == "loaned":
            active_loan = conn.execute(
                "SELECT borrower_person_id FROM asset_loans WHERE tenant_id=? AND asset_id=? AND state='active'",
                (tenant_id, asset_id),
            ).fetchone()
            if active_loan and data.responsible_person_id != active_loan["borrower_person_id"]:
                raise DomainError(
                    "ASSET_LOAN_RESPONSIBLE_MISMATCH",
                    "Durante o empréstimo, o responsável deve permanecer o tomador ativo.",
                    409,
                )
        if asset.get("location_id") == location["id"] and asset.get("responsible_person_id") == data.responsible_person_id:
            raise DomainError("ASSET_TRANSFER_NO_CHANGE", "A localização e o responsável já são os informados.", 409)
        now, movement_id = iso_now(), uuid7()
        before = _normalize(asset)
        conn.execute(
            "INSERT INTO asset_movements(id,tenant_id,asset_id,movement_type,from_location_id,to_location_id,from_responsible_person_id,to_responsible_person_id,reason,occurred_at,occurred_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                movement_id,
                tenant_id,
                asset_id,
                "transfer",
                asset.get("location_id"),
                location["id"],
                asset.get("responsible_person_id"),
                data.responsible_person_id,
                data.reason,
                now,
                user.id,
                now,
            ),
        )
        conn.execute(
            "UPDATE assets SET location=?,location_id=?,responsible_person_id=?,institution_id=COALESCE(?,institution_id),unit_id=COALESCE(?,unit_id),version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (
                location["name"],
                location["id"],
                data.responsible_person_id,
                location.get("institution_id"),
                location.get("unit_id"),
                now,
                tenant_id,
                asset_id,
            ),
        )
        updated = _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()))
        movement = dict(conn.execute("SELECT * FROM asset_movements WHERE id=?", (movement_id,)).fetchone())
        result = {"asset": updated, "movement": movement}
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="transfer",
            aggregate_type="asset",
            aggregate_id=asset_id,
            before=before,
            after=result,
            reason=data.reason,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetTransferred",
            aggregate_type="asset",
            aggregate_id=asset_id,
            payload=result,
        )
        return result


def create_maintenance(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    asset_id: str,
    data: AssetMaintenanceCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"assets:maintenance:create:{tenant_id}:{asset_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        asset = _asset(conn, tenant_id, asset_id)
        if asset["state"] != "active":
            raise DomainError("ASSET_MAINTENANCE_NOT_ALLOWED", "Somente patrimônio ativo aceita manutenção.", 409)
        if conn.execute(
            "SELECT id FROM asset_loans WHERE tenant_id=? AND asset_id=? AND state='active'",
            (tenant_id, asset_id),
        ).fetchone():
            raise DomainError("ASSET_ACTIVE_LOAN", "O patrimônio está emprestado e não aceita manutenção.", 409)
        if conn.execute(
            "SELECT id FROM asset_maintenances WHERE tenant_id=? AND asset_id=? AND state IN ('scheduled','in_progress')",
            (tenant_id, asset_id),
        ).fetchone():
            raise DomainError("ASSET_ACTIVE_MAINTENANCE", "Já existe manutenção aberta para o patrimônio.", 409)
        if data.supplier_id:
            _one(
                conn,
                "SELECT id FROM suppliers WHERE tenant_id=? AND id=? AND state='active'",
                (tenant_id, data.supplier_id),
                "SUPPLIER_NOT_FOUND",
                "Fornecedor de manutenção não localizado.",
            )
        maintenance_id, now = uuid7(), iso_now()
        number = _number("MAN", maintenance_id)
        conn.execute(
            "INSERT INTO asset_maintenances(id,tenant_id,asset_id,maintenance_number,maintenance_type,scheduled_on,supplier_id,estimated_cost,actual_cost,description,result_notes,state,started_at,completed_at,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                maintenance_id,
                tenant_id,
                asset_id,
                number,
                data.maintenance_type.strip().lower(),
                data.scheduled_on.isoformat() if data.scheduled_on else None,
                data.supplier_id,
                str(money(data.estimated_cost)),
                None,
                data.description,
                None,
                "scheduled",
                None,
                None,
                user.id,
                now,
                now,
            ),
        )
        result = _normalize(dict(conn.execute("SELECT * FROM asset_maintenances WHERE id=?", (maintenance_id,)).fetchone()))
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="schedule",
            aggregate_type="asset_maintenance",
            aggregate_id=maintenance_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetMaintenanceScheduled",
            aggregate_type="asset",
            aggregate_id=asset_id,
            payload=result,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def start_maintenance(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    maintenance_id: str,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        maintenance = _one(
            conn,
            "SELECT * FROM asset_maintenances WHERE tenant_id=? AND id=?",
            (tenant_id, maintenance_id),
            "ASSET_MAINTENANCE_NOT_FOUND",
            "Manutenção patrimonial não localizada.",
        )
        if maintenance["state"] != "scheduled":
            raise DomainError("ASSET_MAINTENANCE_NOT_SCHEDULED", "A manutenção não está agendada.", 409)
        asset = _asset(conn, tenant_id, maintenance["asset_id"])
        if asset["state"] != "active":
            raise DomainError("ASSET_MAINTENANCE_NOT_ALLOWED", "O patrimônio não está disponível para manutenção.", 409)
        if conn.execute(
            "SELECT id FROM asset_loans WHERE tenant_id=? AND asset_id=? AND state='active'",
            (tenant_id, asset["id"]),
        ).fetchone():
            raise DomainError("ASSET_ACTIVE_LOAN", "O patrimônio está emprestado.", 409)
        now = iso_now()
        before = {"maintenance": _normalize(maintenance), "asset": _normalize(asset)}
        conn.execute(
            "UPDATE asset_maintenances SET state='in_progress',started_at=?,updated_at=? WHERE tenant_id=? AND id=?",
            (now, now, tenant_id, maintenance_id),
        )
        conn.execute(
            "UPDATE assets SET state='maintenance',version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (now, tenant_id, asset["id"]),
        )
        result = {
            "maintenance": _normalize(dict(conn.execute("SELECT * FROM asset_maintenances WHERE id=?", (maintenance_id,)).fetchone())),
            "asset": _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset["id"],)).fetchone())),
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="start",
            aggregate_type="asset_maintenance",
            aggregate_id=maintenance_id,
            before=before,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetMaintenanceStarted",
            aggregate_type="asset",
            aggregate_id=asset["id"],
            payload=result,
        )
        return result


def complete_maintenance(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    maintenance_id: str,
    data: AssetMaintenanceComplete,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        maintenance = _one(
            conn,
            "SELECT * FROM asset_maintenances WHERE tenant_id=? AND id=?",
            (tenant_id, maintenance_id),
            "ASSET_MAINTENANCE_NOT_FOUND",
            "Manutenção patrimonial não localizada.",
        )
        if maintenance["state"] != "in_progress":
            raise DomainError("ASSET_MAINTENANCE_NOT_IN_PROGRESS", "A manutenção não está em andamento.", 409)
        asset = _asset(conn, tenant_id, maintenance["asset_id"])
        now = iso_now()
        before = {"maintenance": _normalize(maintenance), "asset": _normalize(asset)}
        conn.execute(
            "UPDATE asset_maintenances SET state='completed',actual_cost=?,result_notes=?,completed_at=?,updated_at=? WHERE tenant_id=? AND id=?",
            (
                str(money(data.actual_cost)) if data.actual_cost is not None else maintenance.get("estimated_cost"),
                data.result_notes,
                now,
                now,
                tenant_id,
                maintenance_id,
            ),
        )
        conn.execute(
            "UPDATE assets SET state='active',version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (now, tenant_id, asset["id"]),
        )
        result = {
            "maintenance": _normalize(dict(conn.execute("SELECT * FROM asset_maintenances WHERE id=?", (maintenance_id,)).fetchone())),
            "asset": _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset["id"],)).fetchone())),
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="complete",
            aggregate_type="asset_maintenance",
            aggregate_id=maintenance_id,
            before=before,
            after=result,
            reason=data.result_notes,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetMaintenanceCompleted",
            aggregate_type="asset",
            aggregate_id=asset["id"],
            payload=result,
        )
        return result


def create_loan(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    asset_id: str,
    data: AssetLoanCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"assets:loan:create:{tenant_id}:{asset_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        asset = _asset(conn, tenant_id, asset_id)
        if asset["state"] != "active":
            raise DomainError("ASSET_NOT_AVAILABLE_FOR_LOAN", "Somente patrimônio ativo pode ser emprestado.", 409)
        _person(conn, tenant_id, data.borrower_person_id)
        if conn.execute(
            "SELECT id FROM asset_loans WHERE tenant_id=? AND asset_id=? AND state='active'",
            (tenant_id, asset_id),
        ).fetchone():
            raise DomainError("ASSET_ACTIVE_LOAN", "O patrimônio já possui empréstimo ativo.", 409)
        if conn.execute(
            "SELECT id FROM asset_maintenances WHERE tenant_id=? AND asset_id=? AND state='in_progress'",
            (tenant_id, asset_id),
        ).fetchone():
            raise DomainError("ASSET_ACTIVE_MAINTENANCE", "O patrimônio está em manutenção.", 409)
        loan_id, movement_id, now = uuid7(), uuid7(), iso_now()
        loan_number = _number("EMP", loan_id)
        conn.execute(
            "INSERT INTO asset_loans(id,tenant_id,asset_id,loan_number,borrower_person_id,loaned_at,expected_return_at,returned_at,condition_out,condition_in,state,created_by,returned_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                loan_id,
                tenant_id,
                asset_id,
                loan_number,
                data.borrower_person_id,
                now,
                data.expected_return_at.isoformat() if data.expected_return_at else None,
                None,
                data.condition_out,
                None,
                "active",
                user.id,
                None,
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO asset_movements(id,tenant_id,asset_id,movement_type,from_location_id,to_location_id,from_responsible_person_id,to_responsible_person_id,reason,occurred_at,occurred_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                movement_id,
                tenant_id,
                asset_id,
                "loan",
                asset.get("location_id"),
                asset.get("location_id"),
                asset.get("responsible_person_id"),
                data.borrower_person_id,
                "Empréstimo patrimonial",
                now,
                user.id,
                now,
            ),
        )
        conn.execute(
            "UPDATE assets SET state='loaned',responsible_person_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (data.borrower_person_id, now, tenant_id, asset_id),
        )
        result = {
            "loan": _normalize(dict(conn.execute("SELECT * FROM asset_loans WHERE id=?", (loan_id,)).fetchone())),
            "asset": _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone())),
            "movement": dict(conn.execute("SELECT * FROM asset_movements WHERE id=?", (movement_id,)).fetchone()),
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="loan",
            aggregate_type="asset",
            aggregate_id=asset_id,
            before=_normalize(asset),
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetLoaned",
            aggregate_type="asset",
            aggregate_id=asset_id,
            payload=result,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def return_loan(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    loan_id: str,
    data: AssetLoanReturn,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        loan = _one(
            conn,
            "SELECT * FROM asset_loans WHERE tenant_id=? AND id=?",
            (tenant_id, loan_id),
            "ASSET_LOAN_NOT_FOUND",
            "Empréstimo patrimonial não localizado.",
        )
        if loan["state"] != "active":
            raise DomainError("ASSET_LOAN_NOT_ACTIVE", "O empréstimo não está ativo.", 409)
        asset = _asset(conn, tenant_id, loan["asset_id"])
        now, movement_id = iso_now(), uuid7()
        before = {"loan": _normalize(loan), "asset": _normalize(asset)}
        conn.execute(
            "UPDATE asset_loans SET state='returned',returned_at=?,condition_in=?,returned_by=?,updated_at=? WHERE tenant_id=? AND id=?",
            (now, data.condition_in, user.id, now, tenant_id, loan_id),
        )
        conn.execute(
            "INSERT INTO asset_movements(id,tenant_id,asset_id,movement_type,from_location_id,to_location_id,from_responsible_person_id,to_responsible_person_id,reason,occurred_at,occurred_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                movement_id,
                tenant_id,
                asset["id"],
                "loan_return",
                asset.get("location_id"),
                asset.get("location_id"),
                loan["borrower_person_id"],
                None,
                "Devolução de empréstimo patrimonial",
                now,
                user.id,
                now,
            ),
        )
        conn.execute(
            "UPDATE assets SET state='active',responsible_person_id=NULL,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (now, tenant_id, asset["id"]),
        )
        result = {
            "loan": _normalize(dict(conn.execute("SELECT * FROM asset_loans WHERE id=?", (loan_id,)).fetchone())),
            "asset": _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset["id"],)).fetchone())),
            "movement": dict(conn.execute("SELECT * FROM asset_movements WHERE id=?", (movement_id,)).fetchone()),
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="return",
            aggregate_type="asset_loan",
            aggregate_id=loan_id,
            before=before,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetLoanReturned",
            aggregate_type="asset",
            aggregate_id=asset["id"],
            payload=result,
        )
        return result


def calculate_depreciation(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    asset_id: str,
    data: DepreciationCalculate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"assets:depreciation:{tenant_id}:{asset_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        asset = _asset(conn, tenant_id, asset_id)
        if not asset.get("useful_life_months"):
            raise DomainError("ASSET_USEFUL_LIFE_NOT_CONFIGURED", "O patrimônio não possui vida útil configurada.", 409)
        try:
            year, month = (int(part) for part in data.competence.split("-"))
            competence_date = date(year, month, 1)
        except ValueError as exc:
            raise DomainError("INVALID_COMPETENCE", "Competência inválida.", 422) from exc
        acquisition = date.fromisoformat(asset["acquisition_date"])
        acquisition_month = date(acquisition.year, acquisition.month, 1)
        if competence_date < acquisition_month:
            raise DomainError("DEPRECIATION_BEFORE_ACQUISITION", "A competência antecede a aquisição.", 422)
        existing = conn.execute(
            "SELECT * FROM asset_depreciations WHERE tenant_id=? AND asset_id=? AND competence=?",
            (tenant_id, asset_id, data.competence),
        ).fetchone()
        if existing:
            result = {"asset": _normalize(asset), "depreciation": dict(existing)}
            _save(conn, scope, key, payload, 200, result)
            return 200, result
        prior = conn.execute(
            "SELECT * FROM asset_depreciations WHERE tenant_id=? AND asset_id=? ORDER BY competence DESC LIMIT 1",
            (tenant_id, asset_id),
        ).fetchone()
        if prior and data.competence <= prior["competence"]:
            raise DomainError("DEPRECIATION_OUT_OF_ORDER", "Calcule as competências em ordem cronológica.", 409)
        acquisition_cost = money(asset["acquisition_cost"])
        residual = money(asset.get("residual_value"))
        accumulated_before = money(asset.get("accumulated_depreciation"))
        useful_life = int(asset["useful_life_months"])
        months_since_acquisition = _month_index(competence_date) - _month_index(acquisition_month) + 1
        depreciable = money(acquisition_cost - residual)
        monthly = money(depreciable / Decimal(useful_life)) if useful_life else Decimal("0.00")
        remaining = money(max(Decimal("0.00"), depreciable - accumulated_before))
        amount = Decimal("0.00") if months_since_acquisition > useful_life else money(min(monthly, remaining))
        opening = money(acquisition_cost - accumulated_before)
        accumulated = money(accumulated_before + amount)
        closing = money(acquisition_cost - accumulated)
        if closing < residual:
            amount = money(max(Decimal("0.00"), opening - residual))
            accumulated = money(accumulated_before + amount)
            closing = residual
        depreciation_id, now = uuid7(), iso_now()
        conn.execute(
            "INSERT INTO asset_depreciations(id,tenant_id,asset_id,competence,opening_book_value,depreciation_amount,accumulated_depreciation,closing_book_value,method,calculated_at,calculated_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                depreciation_id,
                tenant_id,
                asset_id,
                data.competence,
                str(opening),
                str(amount),
                str(accumulated),
                str(closing),
                "linear",
                now,
                user.id,
                now,
            ),
        )
        conn.execute(
            "UPDATE assets SET accumulated_depreciation=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (str(accumulated), now, tenant_id, asset_id),
        )
        result = {
            "asset": _normalize(dict(conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone())),
            "depreciation": dict(conn.execute("SELECT * FROM asset_depreciations WHERE id=?", (depreciation_id,)).fetchone()),
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="calculate",
            aggregate_type="asset_depreciation",
            aggregate_id=depreciation_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="AssetDepreciationCalculated",
            aggregate_type="asset",
            aggregate_id=asset_id,
            payload=result,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result
