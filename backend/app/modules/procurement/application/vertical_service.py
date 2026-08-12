from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from fastapi import Request

from app.modules.operations.common import dumps, loads
from app.modules.procurement.presentation.vertical_schemas import (
    ActionReason,
    GoodsReceiptCreate,
    InventoryCountComplete,
    InventoryCountCreate,
    ProductBarcodeCreate,
    ProductVariantCreate,
    PurchaseOrderCreate,
    PurchaseReturnCreate,
    QuotationAward,
    QuotationCreate,
    PurchaseSuggestionConvert,
    PurchaseSuggestionDismiss,
    PurchaseSuggestionGenerate,
    RequisitionApproval,
    RequisitionCreate,
    ReorderPolicyCreate,
    ReorderPolicyPatch,
    ReservationCreate,
    SupplierCreateUnified,
    SupplierPatch,
    SupplierProposalCreate,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

CENT = Decimal("0.01")
QTY = Decimal("0.0001")
COST = Decimal("0.0001")


def quantity(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY, rounding=ROUND_HALF_UP)


def unit_cost(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(COST, rounding=ROUND_HALF_UP)


def _body(data: Any) -> dict[str, Any]:
    return data.model_dump(mode="json") if hasattr(data, "model_dump") else dict(data)


def _status(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "state" in result:
        result.setdefault("status", result["state"])
    for field, default in (
        ("payment_terms_json", {}),
        ("fiscal_profile_json", {}),
        ("attributes_json", {}),
        ("specifications_json", {}),
        ("snapshot_json", {}),
        ("metadata_json", {}),
    ):
        if field in result:
            result[field.removesuffix("_json")] = loads(result[field], default)
    return result


def _one(conn: Any, sql: str, params: Iterable[Any], code: str, message: str) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, message, 404)
    return dict(row)


def _product(conn: Any, tenant_id: str, product_id: str, *, active: bool = True) -> dict[str, Any]:
    sql = "SELECT * FROM products WHERE tenant_id=? AND id=?"
    params: list[Any] = [tenant_id, product_id]
    if active:
        sql += " AND state='active'"
    return _one(conn, sql, params, "PRODUCT_NOT_FOUND", "Produto não localizado ou inativo.")


def _supplier(conn: Any, tenant_id: str, supplier_id: str, *, active: bool = False) -> dict[str, Any]:
    sql = "SELECT * FROM suppliers WHERE tenant_id=? AND id=?"
    params: list[Any] = [tenant_id, supplier_id]
    if active:
        sql += " AND state='active'"
    return _one(conn, sql, params, "SUPPLIER_NOT_FOUND", "Fornecedor não localizado ou inativo.")


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


def _cached(conn: Any, scope: str, key: str | None, payload: Any) -> tuple[int, Any] | None:
    return get_idempotent(conn, scope, key, payload) if key else None


def _save(conn: Any, scope: str, key: str | None, payload: Any, status: int, result: Any) -> None:
    if key:
        save_idempotent(conn, scope, key, payload, status, result)


def _number(prefix: str, identifier: str) -> str:
    return f"{prefix}-{date.today():%Y%m%d}-{identifier.replace('-', '').upper()[-12:]}"


def _balance(conn: Any, tenant_id: str, product_id: str, warehouse: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse=?",
        (tenant_id, product_id, warehouse),
    ).fetchone()
    return dict(row) if row else None


def _set_balance(
    conn: Any,
    *,
    tenant_id: str,
    product_id: str,
    warehouse: str,
    physical: Decimal,
    reserved: Decimal | None = None,
    now: str,
) -> None:
    current = _balance(conn, tenant_id, product_id, warehouse)
    final_reserved = quantity(reserved if reserved is not None else (current.get("reserved") if current else 0))
    if physical < 0 or final_reserved < 0 or final_reserved > physical:
        raise DomainError("INVALID_STOCK_BALANCE", "Saldo físico ou reservado inválido.", 409)
    if current:
        conn.execute(
            "UPDATE stock_balances SET quantity=?,reserved=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse=?",
            (str(quantity(physical)), str(final_reserved), now, tenant_id, product_id, warehouse),
        )
    else:
        conn.execute(
            "INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) VALUES(?,?,?,?,?,?)",
            (tenant_id, product_id, warehouse, str(quantity(physical)), str(final_reserved), now),
        )


def _stock_change(
    conn: Any,
    *,
    tenant_id: str,
    user: CurrentUser,
    product_id: str,
    warehouse: str,
    movement_type: str,
    signed_amount: Decimal,
    cost_value: Decimal | None,
    reference_type: str,
    reference_id: str,
    reason: str | None,
    lot_id: str | None,
    now: str,
) -> dict[str, Any]:
    current = _balance(conn, tenant_id, product_id, warehouse)
    physical = quantity(current.get("quantity") if current else 0)
    reserved = quantity(current.get("reserved") if current else 0)
    new_physical = quantity(physical + signed_amount)
    if new_physical < reserved:
        raise DomainError("INSUFFICIENT_AVAILABLE_STOCK", "Saldo livre insuficiente para a movimentação.", 409)
    _set_balance(
        conn,
        tenant_id=tenant_id,
        product_id=product_id,
        warehouse=warehouse,
        physical=new_physical,
        reserved=reserved,
        now=now,
    )
    movement_id = uuid7()
    conn.execute(
        "INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by,lot_id,balance_after) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            movement_id,
            tenant_id,
            product_id,
            warehouse,
            movement_type,
            str(quantity(signed_amount)),
            str(unit_cost(cost_value)) if cost_value is not None else None,
            reference_type,
            reference_id,
            reason,
            now,
            user.id,
            lot_id,
            str(new_physical),
        ),
    )
    return {"id": movement_id, "balance_after": str(new_physical), "quantity": str(quantity(signed_amount))}


# Fornecedores ---------------------------------------------------------------


def list_suppliers(request: Request, tenant_id: str, status: str | None = None, q: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM suppliers WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if q:
        sql += " AND (legal_name LIKE ? OR trade_name LIKE ? OR code LIKE ? OR cnpj LIKE ?)"
        term = f"%{q}%"
        params.extend([term, term, term, term])
    sql += " ORDER BY legal_name,id"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def supplier_detail(request: Request, tenant_id: str, supplier_id: str) -> dict[str, Any]:
    supplier = request.state.store.fetch_one("SELECT * FROM suppliers WHERE tenant_id=? AND id=?", (tenant_id, supplier_id))
    if not supplier:
        raise DomainError("SUPPLIER_NOT_FOUND", "Fornecedor não localizado.", 404)
    result = _status(supplier)
    result["contacts"] = [
        _status(row)
        for row in request.state.store.fetch_all(
            "SELECT * FROM supplier_contacts WHERE tenant_id=? AND supplier_id=? ORDER BY is_primary DESC,name",
            (tenant_id, supplier_id),
        )
    ]
    result["purchase_orders"] = [
        _status(row)
        for row in request.state.store.fetch_all(
            "SELECT * FROM purchase_orders WHERE tenant_id=? AND supplier_id=? ORDER BY created_at DESC LIMIT 100",
            (tenant_id, supplier_id),
        )
    ]
    return result


def create_supplier(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: SupplierCreateUnified,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:supplier:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        supplier_id, now = uuid7(), iso_now()
        code = data.code or f"FOR-{supplier_id.replace('-', '').upper()[-10:]}"
        trade_name = data.trade_name or data.legal_name
        try:
            conn.execute(
                "INSERT INTO suppliers(id,tenant_id,legal_name,trade_name,cnpj,email,phone,state,code,rating,payment_terms_json,fiscal_profile_json,notes,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    supplier_id,
                    tenant_id,
                    data.legal_name,
                    trade_name,
                    data.cnpj,
                    data.email,
                    data.phone,
                    "active",
                    code,
                    str(data.rating) if data.rating is not None else None,
                    dumps(data.payment_terms),
                    dumps(data.fiscal_profile),
                    data.notes,
                    data.institution_id,
                    data.unit_id,
                    1,
                    now,
                    now,
                ),
            )
        except Exception as exc:
            text = str(exc).lower()
            if "unique" in text or "duplicate" in text:
                code_name = "SUPPLIER_CNPJ_EXISTS" if data.cnpj and "cnpj" in text else "SUPPLIER_CODE_EXISTS"
                raise DomainError(code_name, "Fornecedor já cadastrado com o mesmo código ou CNPJ.", 409) from exc
            raise
        contacts: list[dict[str, Any]] = []
        source_contacts = list(data.contacts)
        if not source_contacts and (data.email or data.phone):
            from app.modules.procurement.presentation.vertical_schemas import SupplierContactInput

            source_contacts = [
                SupplierContactInput(
                    name=trade_name,
                    email=data.email,
                    phone=data.phone,
                    role="commercial",
                    primary=True,
                )
            ]
        for item in source_contacts:
            contact_id = uuid7()
            conn.execute(
                "INSERT INTO supplier_contacts(id,tenant_id,supplier_id,name,email,phone,role,is_primary,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    contact_id,
                    tenant_id,
                    supplier_id,
                    item.name,
                    item.email,
                    item.phone,
                    item.role,
                    1 if item.primary else 0,
                    now,
                    now,
                ),
            )
            contacts.append(
                {
                    "id": contact_id,
                    "name": item.name,
                    "email": item.email,
                    "phone": item.phone,
                    "role": item.role,
                    "primary": item.primary,
                }
            )
        result = {
            "id": supplier_id,
            "code": code,
            "legal_name": data.legal_name,
            "trade_name": trade_name,
            "cnpj": data.cnpj,
            "state": "active",
            "status": "active",
            "version": 1,
            "contacts": contacts,
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create",
            aggregate_type="supplier",
            aggregate_id=supplier_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="SupplierCreated",
            aggregate_type="supplier",
            aggregate_id=supplier_id,
            payload=result,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def patch_supplier(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    supplier_id: str,
    data: SupplierPatch,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _supplier(conn, tenant_id, supplier_id)
        if int(before.get("version") or 1) != data.expected_version:
            raise DomainError("OPTIMISTIC_CONCURRENCY_CONFLICT", "O fornecedor foi alterado por outro usuário.", 409)
        values = data.model_dump(exclude={"expected_version"}, exclude_unset=True)
        mapping = {
            "status": "state",
            "payment_terms": "payment_terms_json",
            "fiscal_profile": "fiscal_profile_json",
        }
        assignments: list[str] = []
        params: list[Any] = []
        for field, value in values.items():
            column = mapping.get(field, field)
            assignments.append(f"{column}=?")
            params.append(dumps(value) if field in {"payment_terms", "fiscal_profile"} else str(value) if isinstance(value, Decimal) else value)
        if assignments:
            assignments.extend(["version=version+1", "updated_at=?"])
            params.extend([iso_now(), tenant_id, supplier_id])
            conn.execute(f"UPDATE suppliers SET {','.join(assignments)} WHERE tenant_id=? AND id=?", params)
        after = _status(dict(conn.execute("SELECT * FROM suppliers WHERE tenant_id=? AND id=?", (tenant_id, supplier_id)).fetchone()))
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="update",
            aggregate_type="supplier",
            aggregate_id=supplier_id,
            before=_status(before),
            after=after,
        )
        return after


# Variantes e códigos de barras ---------------------------------------------


def create_variant(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: ProductVariantCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:variant:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        product = _product(conn, tenant_id, data.product_id)
        variant_id, now = uuid7(), iso_now()
        try:
            conn.execute(
                "INSERT INTO product_variants(id,tenant_id,product_id,sku,name,attributes_json,sale_price,cost_price,state,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    variant_id,
                    tenant_id,
                    product["id"],
                    data.sku,
                    data.name,
                    dumps(data.attributes),
                    money_str(data.sale_price) if data.sale_price is not None else None,
                    str(unit_cost(data.cost_price)) if data.cost_price is not None else None,
                    "active",
                    None,
                    None,
                    1,
                    now,
                    now,
                ),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("PRODUCT_VARIANT_SKU_EXISTS", "SKU de variante já cadastrado.", 409) from exc
            raise
        result = {
            "id": variant_id,
            "product_id": product["id"],
            "sku": data.sku,
            "name": data.name,
            "attributes": data.attributes,
            "sale_price": money_str(data.sale_price) if data.sale_price is not None else None,
            "cost_price": str(unit_cost(data.cost_price)) if data.cost_price is not None else None,
            "state": "active",
            "status": "active",
            "version": 1,
        }
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create_variant", aggregate_type="product", aggregate_id=product["id"], after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="ProductVariantCreated", aggregate_type="product_variant", aggregate_id=variant_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def create_barcode(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: ProductBarcodeCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:barcode:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        product = _product(conn, tenant_id, data.product_id)
        if data.variant_id:
            _one(
                conn,
                "SELECT id FROM product_variants WHERE tenant_id=? AND id=? AND product_id=? AND state='active'",
                (tenant_id, data.variant_id, product["id"]),
                "PRODUCT_VARIANT_MISMATCH",
                "A variante não pertence ao produto.",
            )
        if data.primary:
            conn.execute(
                "UPDATE product_barcodes SET is_primary=0 WHERE tenant_id=? AND product_id=?",
                (tenant_id, product["id"]),
            )
        barcode_id, now = uuid7(), iso_now()
        try:
            conn.execute(
                "INSERT INTO product_barcodes(id,tenant_id,product_id,variant_id,barcode,barcode_type,is_primary,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    barcode_id,
                    tenant_id,
                    product["id"],
                    data.variant_id,
                    data.barcode,
                    data.barcode_type.lower(),
                    1 if data.primary else 0,
                    now,
                ),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("PRODUCT_BARCODE_EXISTS", "Código de barras já cadastrado.", 409) from exc
            raise
        result = {
            "id": barcode_id,
            "product_id": product["id"],
            "variant_id": data.variant_id,
            "barcode": data.barcode,
            "barcode_type": data.barcode_type.lower(),
            "primary": data.primary,
        }
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create_barcode", aggregate_type="product", aggregate_id=product["id"], after=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


# Requisições ---------------------------------------------------------------


def requisition_detail(request: Request, tenant_id: str, requisition_id: str) -> dict[str, Any]:
    requisition = request.state.store.fetch_one(
        "SELECT * FROM purchase_requisitions WHERE tenant_id=? AND id=?", (tenant_id, requisition_id)
    )
    if not requisition:
        raise DomainError("PURCHASE_REQUISITION_NOT_FOUND", "Requisição de compra não localizada.", 404)
    return {
        "requisition": _status(requisition),
        "items": [
            _status(row)
            for row in request.state.store.fetch_all(
                "SELECT pri.*,p.sku,p.name AS product_name FROM purchase_requisition_items pri JOIN products p ON p.id=pri.product_id WHERE pri.tenant_id=? AND pri.requisition_id=? ORDER BY pri.created_at,pri.id",
                (tenant_id, requisition_id),
            )
        ],
    }


def list_requisitions(request: Request, tenant_id: str, status: str | None = None) -> dict[str, Any]:
    sql = "SELECT id FROM purchase_requisitions WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    sql += " ORDER BY created_at DESC,id DESC"
    ids = [row["id"] for row in request.state.store.fetch_all(sql, params)]
    return {"items": [requisition_detail(request, tenant_id, item_id) for item_id in ids]}


def create_requisition(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: RequisitionCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:requisition:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        products = [_product(conn, tenant_id, item.product_id) for item in data.items]
        requisition_id, now = uuid7(), iso_now()
        number = _number("REQ", requisition_id)
        conn.execute(
            "INSERT INTO purchase_requisitions(id,tenant_id,requisition_number,requester_user_id,department_id,cost_center_id,needed_by,justification,state,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                requisition_id,
                tenant_id,
                number,
                user.id,
                data.department_id,
                data.cost_center_id,
                data.needed_by.isoformat() if data.needed_by else None,
                data.justification,
                "draft",
                data.institution_id,
                data.unit_id,
                1,
                now,
                now,
            ),
        )
        items: list[dict[str, Any]] = []
        for item, product in zip(data.items, products, strict=True):
            item_id = uuid7()
            conn.execute(
                "INSERT INTO purchase_requisition_items(id,tenant_id,requisition_id,product_id,quantity,approved_quantity,estimated_unit_price,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    tenant_id,
                    requisition_id,
                    product["id"],
                    str(quantity(item.quantity)),
                    "0.0000",
                    money_str(item.estimated_unit_price),
                    item.notes,
                    now,
                ),
            )
            items.append(
                {
                    "id": item_id,
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity": str(quantity(item.quantity)),
                    "approved_quantity": "0.0000",
                    "estimated_unit_price": money_str(item.estimated_unit_price),
                }
            )
        result = {
            "requisition": {
                "id": requisition_id,
                "requisition_number": number,
                "status": "draft",
                "state": "draft",
                "version": 1,
            },
            "items": items,
        }
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="purchase_requisition", aggregate_id=requisition_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="PurchaseRequisitionCreated", aggregate_type="purchase_requisition", aggregate_id=requisition_id, payload=result["requisition"])
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def transition_requisition(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    requisition_id: str,
    *,
    action: str,
    approval: RequisitionApproval | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(
            conn,
            "SELECT * FROM purchase_requisitions WHERE tenant_id=? AND id=?",
            (tenant_id, requisition_id),
            "PURCHASE_REQUISITION_NOT_FOUND",
            "Requisição de compra não localizada.",
        )
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM purchase_requisition_items WHERE tenant_id=? AND requisition_id=? ORDER BY created_at,id",
                (tenant_id, requisition_id),
            ).fetchall()
        ]
        now = iso_now()
        if action == "submit":
            if before["state"] != "draft":
                raise DomainError("INVALID_STATE_TRANSITION", "Somente requisição em rascunho pode ser enviada.", 409)
            target, event_type = "submitted", "PurchaseRequisitionSubmitted"
            conn.execute(
                "UPDATE purchase_requisitions SET state=?,submitted_at=?,submitted_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                (target, now, user.id, now, tenant_id, requisition_id),
            )
        elif action == "approve":
            if before["state"] != "submitted":
                raise DomainError("INVALID_STATE_TRANSITION", "Somente requisição enviada pode ser aprovada.", 409)
            quantities = approval.approved_quantities if approval else {}
            accepted = False
            for item in rows:
                approved = quantity(quantities.get(item["id"], item["quantity"]))
                if approved < 0 or approved > quantity(item["quantity"]):
                    raise DomainError("INVALID_APPROVED_QUANTITY", "Quantidade aprovada inválida.", 422)
                accepted = accepted or approved > 0
                conn.execute(
                    "UPDATE purchase_requisition_items SET approved_quantity=? WHERE tenant_id=? AND id=?",
                    (str(approved), tenant_id, item["id"]),
                )
            if not accepted:
                raise DomainError("REQUISITION_WITHOUT_APPROVED_ITEMS", "A aprovação deve manter ao menos um item.", 422)
            target, event_type = "approved", "PurchaseRequisitionApproved"
            conn.execute(
                "UPDATE purchase_requisitions SET state=?,approved_at=?,approved_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                (target, now, user.id, now, tenant_id, requisition_id),
            )
        elif action == "reject":
            if before["state"] not in {"submitted", "approved"}:
                raise DomainError("INVALID_STATE_TRANSITION", "A requisição não pode ser rejeitada neste estado.", 409)
            target, event_type = "rejected", "PurchaseRequisitionRejected"
            conn.execute(
                "UPDATE purchase_requisitions SET state=?,rejected_at=?,rejected_by=?,rejection_reason=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                (target, now, user.id, reason, now, tenant_id, requisition_id),
            )
        elif action == "cancel":
            if before["state"] in {"fulfilled", "cancelled"}:
                raise DomainError("INVALID_STATE_TRANSITION", "A requisição não pode ser cancelada neste estado.", 409)
            target, event_type = "cancelled", "PurchaseRequisitionCancelled"
            conn.execute(
                "UPDATE purchase_requisitions SET state=?,cancelled_at=?,cancelled_by=?,cancellation_reason=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                (target, now, user.id, reason, now, tenant_id, requisition_id),
            )
        else:
            raise DomainError("INVALID_REQUISITION_ACTION", "Ação de requisição inválida.", 422)
        after = _status(dict(conn.execute("SELECT * FROM purchase_requisitions WHERE tenant_id=? AND id=?", (tenant_id, requisition_id)).fetchone()))
        current_items = [_status(dict(row)) for row in conn.execute("SELECT * FROM purchase_requisition_items WHERE tenant_id=? AND requisition_id=? ORDER BY created_at,id", (tenant_id, requisition_id)).fetchall()]
        result = {"requisition": after, "items": current_items}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action=action, aggregate_type="purchase_requisition", aggregate_id=requisition_id, before=_status(before), after=result, reason=reason or (approval.reason if approval else None))
        _event(conn, tenant_id=tenant_id, request=request, event_type=event_type, aggregate_type="purchase_requisition", aggregate_id=requisition_id, payload=after)
        return result


# Cotações -------------------------------------------------------------------


def quotation_detail(request: Request, tenant_id: str, quotation_id: str) -> dict[str, Any]:
    quotation = request.state.store.fetch_one(
        "SELECT * FROM requests_for_quotation WHERE tenant_id=? AND id=?", (tenant_id, quotation_id)
    )
    if not quotation:
        raise DomainError("QUOTATION_NOT_FOUND", "Cotação não localizada.", 404)
    items = [
        _status(row)
        for row in request.state.store.fetch_all(
            "SELECT qi.*,p.sku,p.name AS product_name FROM quotation_items qi JOIN products p ON p.id=qi.product_id WHERE qi.tenant_id=? AND qi.quotation_id=? ORDER BY qi.created_at,qi.id",
            (tenant_id, quotation_id),
        )
    ]
    invited = [
        _status(row)
        for row in request.state.store.fetch_all(
            "SELECT qs.*,s.code AS supplier_code,s.legal_name AS supplier_name FROM quotation_suppliers qs JOIN suppliers s ON s.id=qs.supplier_id WHERE qs.tenant_id=? AND qs.quotation_id=? ORDER BY s.legal_name",
            (tenant_id, quotation_id),
        )
    ]
    for supplier in invited:
        supplier["items"] = [
            _status(row)
            for row in request.state.store.fetch_all(
                "SELECT * FROM quotation_supplier_items WHERE tenant_id=? AND quotation_supplier_id=? ORDER BY created_at,id",
                (tenant_id, supplier["id"]),
            )
        ]
    return {"quotation": _status(quotation), "items": items, "suppliers": invited}


def list_quotations(request: Request, tenant_id: str, status: str | None = None) -> dict[str, Any]:
    sql = "SELECT id FROM requests_for_quotation WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    sql += " ORDER BY created_at DESC,id DESC"
    ids = [row["id"] for row in request.state.store.fetch_all(sql, params)]
    return {"items": [quotation_detail(request, tenant_id, item_id) for item_id in ids]}


def create_quotation(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: QuotationCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:quotation:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        requisition: dict[str, Any] | None = None
        if data.requisition_id:
            requisition = _one(
                conn,
                "SELECT * FROM purchase_requisitions WHERE tenant_id=? AND id=?",
                (tenant_id, data.requisition_id),
                "PURCHASE_REQUISITION_NOT_FOUND",
                "Requisição de compra não localizada.",
            )
            if requisition["state"] != "approved":
                raise DomainError("REQUISITION_NOT_APPROVED", "A requisição precisa estar aprovada.", 409)
        suppliers = [_supplier(conn, tenant_id, supplier_id, active=True) for supplier_id in data.supplier_ids]
        _ensure_scope(
            conn,
            tenant_id,
            data.institution_id or (requisition.get("institution_id") if requisition else None),
            data.unit_id or (requisition.get("unit_id") if requisition else None),
        )
        source_items: list[tuple[dict[str, Any], Decimal, dict[str, Any]]] = []
        if requisition:
            rows = conn.execute(
                "SELECT * FROM purchase_requisition_items WHERE tenant_id=? AND requisition_id=?",
                (tenant_id, requisition["id"]),
            ).fetchall()
            for raw in rows:
                row = dict(raw)
                approved = quantity(row.get("approved_quantity"))
                if approved > 0:
                    source_items.append((_product(conn, tenant_id, row["product_id"]), approved, {}))
        else:
            for item in data.items:
                source_items.append((_product(conn, tenant_id, item.product_id), quantity(item.quantity), item.specifications))
        if not source_items:
            raise DomainError("QUOTATION_WITHOUT_ITEMS", "A cotação não possui itens.", 422)
        quotation_id, now = uuid7(), iso_now()
        number = _number("COT", quotation_id)
        institution_id = data.institution_id or (requisition.get("institution_id") if requisition else None)
        unit_id = data.unit_id or (requisition.get("unit_id") if requisition else None)
        conn.execute(
            "INSERT INTO requests_for_quotation(id,tenant_id,quotation_number,requisition_id,response_deadline,currency,state,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                quotation_id,
                tenant_id,
                number,
                requisition["id"] if requisition else None,
                data.response_deadline.isoformat() if data.response_deadline else None,
                data.currency.upper(),
                "sent",
                institution_id,
                unit_id,
                1,
                now,
                now,
            ),
        )
        item_rows: list[dict[str, Any]] = []
        for product, amount, specifications in source_items:
            item_id = uuid7()
            conn.execute(
                "INSERT INTO quotation_items(id,tenant_id,quotation_id,product_id,quantity,specifications_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (item_id, tenant_id, quotation_id, product["id"], str(amount), dumps(specifications), now),
            )
            item_rows.append({"id": item_id, "product_id": product["id"], "product_name": product["name"], "quantity": str(amount), "specifications": specifications})
        supplier_rows: list[dict[str, Any]] = []
        for supplier in suppliers:
            invitation_id = uuid7()
            conn.execute(
                "INSERT INTO quotation_suppliers(id,tenant_id,quotation_id,supplier_id,state,invited_at,payment_terms_json,total_amount,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (invitation_id, tenant_id, quotation_id, supplier["id"], "invited", now, "{}", "0.00", now, now),
            )
            supplier_rows.append({"id": invitation_id, "supplier_id": supplier["id"], "supplier_name": supplier["legal_name"], "status": "invited", "state": "invited"})
        result = {
            "quotation": {"id": quotation_id, "quotation_number": number, "status": "sent", "state": "sent", "currency": data.currency.upper(), "version": 1},
            "items": item_rows,
            "suppliers": supplier_rows,
        }
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="request_for_quotation", aggregate_id=quotation_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="QuotationRequested", aggregate_type="request_for_quotation", aggregate_id=quotation_id, payload=result["quotation"])
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def submit_supplier_proposal(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    quotation_id: str,
    supplier_id: str,
    data: SupplierProposalCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:quotation:proposal:{tenant_id}:{quotation_id}:{supplier_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        quotation = _one(conn, "SELECT * FROM requests_for_quotation WHERE tenant_id=? AND id=?", (tenant_id, quotation_id), "QUOTATION_NOT_FOUND", "Cotação não localizada.")
        if quotation["state"] not in {"sent", "responses_received"}:
            raise DomainError("QUOTATION_NOT_OPEN", "A cotação não aceita propostas neste estado.", 409)
        invitation = _one(
            conn,
            "SELECT * FROM quotation_suppliers WHERE tenant_id=? AND quotation_id=? AND supplier_id=?",
            (tenant_id, quotation_id, supplier_id),
            "SUPPLIER_NOT_INVITED",
            "O fornecedor não foi convidado para esta cotação.",
        )
        if invitation["state"] == "responded":
            raise DomainError("SUPPLIER_ALREADY_RESPONDED", "O fornecedor já respondeu a cotação.", 409)
        quotation_items = {
            row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM quotation_items WHERE tenant_id=? AND quotation_id=?", (tenant_id, quotation_id)).fetchall()
        }
        if set(quotation_items) != {item.quotation_item_id for item in data.items}:
            raise DomainError("PROPOSAL_ITEMS_MISMATCH", "A proposta deve responder a todos os itens da cotação.", 422)
        now, total = iso_now(), Decimal("0")
        results: list[dict[str, Any]] = []
        for item in data.items:
            quote_item = quotation_items[item.quotation_item_id]
            line_total = money(quantity(quote_item["quantity"]) * money(item.unit_price))
            total += line_total
            child_id = uuid7()
            conn.execute(
                "INSERT INTO quotation_supplier_items(id,tenant_id,quotation_supplier_id,quotation_item_id,unit_price,quantity_available,brand,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (child_id, tenant_id, invitation["id"], item.quotation_item_id, money_str(item.unit_price), str(quantity(item.quantity_available)), item.brand, item.notes, now),
            )
            results.append({"id": child_id, "quotation_item_id": item.quotation_item_id, "unit_price": money_str(item.unit_price), "quantity_available": str(quantity(item.quantity_available)), "line_total": money_str(line_total)})
        conn.execute(
            "UPDATE quotation_suppliers SET state='responded',submitted_at=?,delivery_days=?,payment_terms_json=?,notes=?,total_amount=?,updated_at=? WHERE tenant_id=? AND id=?",
            (now, data.delivery_days, dumps(data.payment_terms), data.notes, money_str(total), now, tenant_id, invitation["id"]),
        )
        conn.execute("UPDATE requests_for_quotation SET state='responses_received',version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, tenant_id, quotation_id))
        result = {"supplier": {"id": invitation["id"], "supplier_id": supplier_id, "status": "responded", "state": "responded", "total_amount": money_str(total), "delivery_days": data.delivery_days}, "items": results}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="submit_proposal", aggregate_type="request_for_quotation", aggregate_id=quotation_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="SupplierQuotationResponded", aggregate_type="request_for_quotation", aggregate_id=quotation_id, payload={"supplier_id": supplier_id, "total_amount": money_str(total)})
        _save(conn, scope, key, payload, 201, result)
        return 201, result


# Pedidos de compra ----------------------------------------------------------


def _create_order_rows(
    conn: Any,
    *,
    tenant_id: str,
    user: CurrentUser,
    supplier: dict[str, Any],
    warehouse: str,
    item_payload: list[tuple[dict[str, Any], Decimal, Decimal, Decimal]],
    quotation_id: str | None,
    requisition_id: str | None,
    expected_on: date | None,
    freight: Decimal,
    order_discount: Decimal,
    notes: str | None,
    state: str,
    institution_id: str | None,
    unit_id: str | None,
    now: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    subtotal = sum((money(amount * price) for _, amount, price, _ in item_payload), Decimal("0"))
    line_discounts = sum((discount for _, _, _, discount in item_payload), Decimal("0"))
    total = money(subtotal - line_discounts - money(order_discount) + money(freight))
    if total < 0:
        raise DomainError("PURCHASE_ORDER_NEGATIVE_TOTAL", "O desconto excede o total do pedido.", 422)
    order_id = uuid7()
    number = _number("PC", order_id)
    conn.execute(
        "INSERT INTO purchase_orders(id,tenant_id,supplier_id,order_number,state,total_amount,expected_on,warehouse_id,quotation_id,requisition_id,currency,subtotal,freight_amount,discount_amount,notes,approved_at,approved_by,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            order_id,
            tenant_id,
            supplier["id"],
            number,
            state,
            money_str(total),
            expected_on.isoformat() if expected_on else None,
            warehouse,
            quotation_id,
            requisition_id,
            "BRL",
            money_str(subtotal),
            money_str(freight),
            money_str(line_discounts + money(order_discount)),
            notes,
            now if state == "approved" else None,
            user.id if state == "approved" else None,
            institution_id,
            unit_id,
            1,
            now,
            now,
        ),
    )
    items: list[dict[str, Any]] = []
    for product, amount, price, discount in item_payload:
        item_id = uuid7()
        total_line = money(amount * price - discount)
        conn.execute(
            "INSERT INTO purchase_order_items(id,tenant_id,purchase_order_id,product_id,quantity,unit_cost,received_quantity,returned_quantity,discount_amount,total_amount,fiscal_profile_snapshot_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item_id,
                tenant_id,
                order_id,
                product["id"],
                str(amount),
                money_str(price),
                "0.0000",
                "0.0000",
                money_str(discount),
                money_str(total_line),
                product.get("fiscal_profile_json") or "{}",
                now,
            ),
        )
        items.append({"id": item_id, "product_id": product["id"], "product_name": product["name"], "quantity": str(amount), "unit_price": money_str(price), "unit_cost": money_str(price), "discount_amount": money_str(discount), "total_amount": money_str(total_line), "received_quantity": "0.0000", "returned_quantity": "0.0000"})
    order = {"id": order_id, "order_number": number, "supplier_id": supplier["id"], "warehouse_id": warehouse, "state": state, "status": state, "subtotal": money_str(subtotal), "discount_amount": money_str(line_discounts + money(order_discount)), "freight_amount": money_str(freight), "total_amount": money_str(total), "version": 1}
    return order, items


def order_detail(request: Request, tenant_id: str, order_id: str) -> dict[str, Any]:
    order = request.state.store.fetch_one("SELECT po.*,s.legal_name AS supplier_name FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id WHERE po.tenant_id=? AND po.id=?", (tenant_id, order_id))
    if not order:
        raise DomainError("PURCHASE_ORDER_NOT_FOUND", "Pedido de compra não localizado.", 404)
    return {
        "order": _status(order),
        "items": [
            _status(row)
            for row in request.state.store.fetch_all(
                "SELECT poi.*,p.sku,p.name AS product_name FROM purchase_order_items poi JOIN products p ON p.id=poi.product_id WHERE poi.tenant_id=? AND poi.purchase_order_id=? ORDER BY poi.created_at,poi.id",
                (tenant_id, order_id),
            )
        ],
        "receipts": [_status(row) for row in request.state.store.fetch_all("SELECT * FROM goods_receipts WHERE tenant_id=? AND purchase_order_id=? ORDER BY received_at DESC", (tenant_id, order_id))],
        "returns": [_status(row) for row in request.state.store.fetch_all("SELECT * FROM purchase_returns WHERE tenant_id=? AND purchase_order_id=? ORDER BY returned_at DESC", (tenant_id, order_id))],
    }


def list_orders(request: Request, tenant_id: str, status: str | None = None) -> dict[str, Any]:
    sql = "SELECT id FROM purchase_orders WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    sql += " ORDER BY created_at DESC,id DESC"
    ids = [row["id"] for row in request.state.store.fetch_all(sql, params)]
    return {"items": [order_detail(request, tenant_id, item_id) for item_id in ids]}


def create_purchase_order(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: PurchaseOrderCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:order:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        supplier = _supplier(conn, tenant_id, data.supplier_id, active=True)
        requisition = None
        if data.requisition_id:
            requisition = _one(conn, "SELECT * FROM purchase_requisitions WHERE tenant_id=? AND id=?", (tenant_id, data.requisition_id), "PURCHASE_REQUISITION_NOT_FOUND", "Requisição não localizada.")
            if requisition["state"] not in {"approved", "ordered"}:
                raise DomainError("REQUISITION_NOT_APPROVED", "Requisição não aprovada.", 409)
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        item_payload = [(_product(conn, tenant_id, item.product_id), quantity(item.quantity), money(item.unit_price), money(item.discount_amount)) for item in data.items]
        now = iso_now()
        order, items = _create_order_rows(conn, tenant_id=tenant_id, user=user, supplier=supplier, warehouse=data.warehouse_id, item_payload=item_payload, quotation_id=None, requisition_id=requisition["id"] if requisition else None, expected_on=data.expected_on, freight=data.freight_amount, order_discount=data.discount_amount, notes=data.notes, state="draft", institution_id=data.institution_id, unit_id=data.unit_id, now=now)
        result = {"order": order, "items": items}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="purchase_order", aggregate_id=order["id"], after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="PurchaseOrderCreated", aggregate_type="purchase_order", aggregate_id=order["id"], payload=order)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def approve_order(request: Request, tenant_id: str, user: CurrentUser, order_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM purchase_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "PURCHASE_ORDER_NOT_FOUND", "Pedido de compra não localizado.")
        if before["state"] != "draft":
            raise DomainError("INVALID_STATE_TRANSITION", "Somente pedido em rascunho pode ser aprovado.", 409)
        now = iso_now()
        conn.execute("UPDATE purchase_orders SET state='approved',approved_at=?,approved_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, user.id, now, tenant_id, order_id))
        after = _status(dict(conn.execute("SELECT * FROM purchase_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id)).fetchone()))
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="approve", aggregate_type="purchase_order", aggregate_id=order_id, before=_status(before), after=after)
        _event(conn, tenant_id=tenant_id, request=request, event_type="PurchaseOrderApproved", aggregate_type="purchase_order", aggregate_id=order_id, payload=after)
        return after


def award_quotation(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    quotation_id: str,
    data: QuotationAward,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:quotation:award:{tenant_id}:{quotation_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        quotation = _one(conn, "SELECT * FROM requests_for_quotation WHERE tenant_id=? AND id=?", (tenant_id, quotation_id), "QUOTATION_NOT_FOUND", "Cotação não localizada.")
        if quotation["state"] != "responses_received":
            raise DomainError("QUOTATION_WITHOUT_RESPONSES", "A cotação precisa possuir propostas antes da adjudicação.", 409)
        supplier = _supplier(conn, tenant_id, data.supplier_id, active=True)
        proposal = _one(conn, "SELECT * FROM quotation_suppliers WHERE tenant_id=? AND quotation_id=? AND supplier_id=? AND state='responded'", (tenant_id, quotation_id, supplier["id"]), "SUPPLIER_PROPOSAL_NOT_FOUND", "O fornecedor não possui proposta válida.")
        quote_items = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM quotation_items WHERE tenant_id=? AND quotation_id=?", (tenant_id, quotation_id)).fetchall()}
        proposal_items = [dict(row) for row in conn.execute("SELECT * FROM quotation_supplier_items WHERE tenant_id=? AND quotation_supplier_id=?", (tenant_id, proposal["id"])).fetchall()]
        item_payload: list[tuple[dict[str, Any], Decimal, Decimal, Decimal]] = []
        for item in proposal_items:
            source = quote_items[item["quotation_item_id"]]
            required = quantity(source["quantity"])
            if quantity(item["quantity_available"]) < required:
                raise DomainError("SUPPLIER_QUANTITY_INSUFFICIENT", "A proposta selecionada não atende a quantidade solicitada.", 409)
            item_payload.append((_product(conn, tenant_id, source["product_id"]), required, money(item["unit_price"]), Decimal("0.00")))
        now = iso_now()
        order, order_items = _create_order_rows(conn, tenant_id=tenant_id, user=user, supplier=supplier, warehouse=data.warehouse_id, item_payload=item_payload, quotation_id=quotation_id, requisition_id=quotation.get("requisition_id"), expected_on=data.expected_on, freight=data.freight_amount, order_discount=data.discount_amount, notes=data.reason, state="approved", institution_id=quotation.get("institution_id"), unit_id=quotation.get("unit_id"), now=now)
        conn.execute("UPDATE requests_for_quotation SET state='awarded',selected_supplier_id=?,selection_reason=?,awarded_at=?,awarded_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (supplier["id"], data.reason, now, user.id, now, tenant_id, quotation_id))
        if quotation.get("requisition_id"):
            conn.execute("UPDATE purchase_requisitions SET state='ordered',version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, tenant_id, quotation["requisition_id"]))
        result = {"quotation": {"id": quotation_id, "status": "awarded", "state": "awarded", "selected_supplier_id": supplier["id"], "selection_reason": data.reason}, "order": order, "items": order_items}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="award", aggregate_type="request_for_quotation", aggregate_id=quotation_id, after=result, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type="PurchaseOrderApproved", aggregate_type="purchase_order", aggregate_id=order["id"], payload=order)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def _lot_upsert(
    conn: Any,
    *,
    tenant_id: str,
    product_id: str,
    warehouse: str,
    lot_number: str,
    manufactured_on: date | None,
    expires_on: date | None,
    amount: Decimal,
    cost_value: Decimal,
    now: str,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM inventory_lots WHERE tenant_id=? AND product_id=? AND warehouse_id=? AND lot_number=?", (tenant_id, product_id, warehouse, lot_number)).fetchone()
    if row:
        current = dict(row)
        old_quantity = quantity(current["quantity"])
        new_quantity = quantity(old_quantity + amount)
        weighted = unit_cost((old_quantity * unit_cost(current["unit_cost"]) + amount * unit_cost(cost_value)) / new_quantity) if new_quantity > 0 else unit_cost(cost_value)
        conn.execute("UPDATE inventory_lots SET quantity=?,unit_cost=?,manufactured_on=COALESCE(?,manufactured_on),expires_on=COALESCE(?,expires_on),state='active',updated_at=? WHERE tenant_id=? AND id=?", (str(new_quantity), str(weighted), manufactured_on.isoformat() if manufactured_on else None, expires_on.isoformat() if expires_on else None, now, tenant_id, current["id"]))
        return _status(dict(conn.execute("SELECT * FROM inventory_lots WHERE tenant_id=? AND id=?", (tenant_id, current["id"])).fetchone()))
    lot_id = uuid7()
    conn.execute("INSERT INTO inventory_lots(id,tenant_id,product_id,warehouse_id,lot_number,manufactured_on,expires_on,quantity,reserved_quantity,unit_cost,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (lot_id, tenant_id, product_id, warehouse, lot_number, manufactured_on.isoformat() if manufactured_on else None, expires_on.isoformat() if expires_on else None, str(amount), "0.0000", str(unit_cost(cost_value)), "active", now, now))
    return _status(dict(conn.execute("SELECT * FROM inventory_lots WHERE tenant_id=? AND id=?", (tenant_id, lot_id)).fetchone()))


def receive_order(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    order_id: str,
    data: GoodsReceiptCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:order:receipt:{tenant_id}:{order_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        order = _one(conn, "SELECT * FROM purchase_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "PURCHASE_ORDER_NOT_FOUND", "Pedido de compra não localizado.")
        if order["state"] not in {"approved", "partially_received"}:
            raise DomainError("PURCHASE_ORDER_NOT_RECEIVABLE", "O pedido não está disponível para recebimento.", 409)
        order_items = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=?", (tenant_id, order_id)).fetchall()}
        if len({item.purchase_order_item_id for item in data.items}) != len(data.items):
            raise DomainError("DUPLICATE_RECEIPT_ITEM", "Não repita itens no recebimento.", 422)
        prepared: list[tuple[Any, dict[str, Any], dict[str, Any], Decimal, Decimal]] = []
        total = Decimal("0")
        for incoming in data.items:
            order_item = order_items.get(incoming.purchase_order_item_id)
            if not order_item:
                raise DomainError("PURCHASE_ORDER_ITEM_NOT_FOUND", "Item não pertence ao pedido.", 422)
            amount = quantity(incoming.quantity)
            remaining = quantity(order_item["quantity"]) - quantity(order_item["received_quantity"])
            if amount > remaining:
                raise DomainError("RECEIPT_QUANTITY_EXCEEDS_REMAINING", "Quantidade recebida excede o saldo do pedido.", 409)
            product = _product(conn, tenant_id, order_item["product_id"])
            profile = loads(product.get("fiscal_profile_json"), {})
            if profile.get("requires_lot") and not incoming.lot_number:
                raise DomainError("INVENTORY_LOT_REQUIRED", f"O produto {product['name']} exige lote.", 422)
            if incoming.expires_on and incoming.expires_on < date.today():
                raise DomainError("INVENTORY_LOT_EXPIRED", "Não é permitido receber lote vencido.", 409)
            cost_value = unit_cost(incoming.unit_cost)
            total += money(amount * cost_value)
            prepared.append((incoming, order_item, product, amount, cost_value))
        receipt_id, now = uuid7(), iso_now()
        receipt_number = _number("REC", receipt_id)
        conn.execute("INSERT INTO goods_receipts(id,tenant_id,receipt_number,purchase_order_id,supplier_id,warehouse_id,state,received_at,received_by,supplier_document_number,supplier_document_key,total_amount,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (receipt_id, tenant_id, receipt_number, order_id, order["supplier_id"], order["warehouse_id"], "confirmed", now, user.id, data.supplier_document_number, data.supplier_document_key, money_str(total), data.notes, now, now))
        receipt_items: list[dict[str, Any]] = []
        lots: list[dict[str, Any]] = []
        movements: list[dict[str, Any]] = []
        for incoming, order_item, product, amount, cost_value in prepared:
            lot = None
            if incoming.lot_number:
                lot = _lot_upsert(conn, tenant_id=tenant_id, product_id=product["id"], warehouse=order["warehouse_id"], lot_number=incoming.lot_number, manufactured_on=incoming.manufactured_on, expires_on=incoming.expires_on, amount=amount, cost_value=cost_value, now=now)
                lots.append(lot)
            existing_balance = _balance(conn, tenant_id, product["id"], order["warehouse_id"])
            old_qty = quantity(existing_balance.get("quantity") if existing_balance else 0)
            old_cost = unit_cost(product.get("cost") or 0)
            movement = _stock_change(conn, tenant_id=tenant_id, user=user, product_id=product["id"], warehouse=order["warehouse_id"], movement_type="purchase_receipt", signed_amount=amount, cost_value=cost_value, reference_type="goods_receipt", reference_id=receipt_id, reason=data.notes or "Recebimento de compra", lot_id=lot["id"] if lot else None, now=now)
            new_qty = quantity(old_qty + amount)
            average_cost = unit_cost((old_qty * old_cost + amount * cost_value) / new_qty) if new_qty > 0 else cost_value
            conn.execute("UPDATE products SET cost=?,updated_at=? WHERE tenant_id=? AND id=?", (str(average_cost), now, tenant_id, product["id"]))
            new_received = quantity(order_item["received_quantity"]) + amount
            conn.execute("UPDATE purchase_order_items SET received_quantity=? WHERE tenant_id=? AND id=?", (str(new_received), tenant_id, order_item["id"]))
            receipt_item_id = uuid7()
            conn.execute("INSERT INTO goods_receipt_items(id,tenant_id,goods_receipt_id,purchase_order_item_id,product_id,quantity,unit_cost,lot_id,stock_movement_id,expires_on,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (receipt_item_id, tenant_id, receipt_id, order_item["id"], product["id"], str(amount), str(cost_value), lot["id"] if lot else None, movement["id"], incoming.expires_on.isoformat() if incoming.expires_on else None, now))
            receipt_items.append({"id": receipt_item_id, "purchase_order_item_id": order_item["id"], "product_id": product["id"], "quantity": str(amount), "unit_cost": str(cost_value), "lot_id": lot["id"] if lot else None, "stock_movement_id": movement["id"]})
            movements.append(movement)
        updated_items = [dict(row) for row in conn.execute("SELECT * FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=?", (tenant_id, order_id)).fetchall()]
        all_received = all(quantity(item["received_quantity"]) >= quantity(item["quantity"]) for item in updated_items)
        new_state = "received" if all_received else "partially_received"
        conn.execute("UPDATE purchase_orders SET state=?,received_at=?,closed_at=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (new_state, now if all_received else None, now if all_received else None, now, tenant_id, order_id))
        if all_received and order.get("requisition_id"):
            conn.execute("UPDATE purchase_requisitions SET state='fulfilled',version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, tenant_id, order["requisition_id"]))
        result = {"receipt": {"id": receipt_id, "receipt_number": receipt_number, "purchase_order_id": order_id, "state": "confirmed", "status": "confirmed", "total_amount": money_str(total)}, "items": receipt_items, "lots": lots, "stock": movements, "order": {"id": order_id, "state": new_state, "status": new_state}}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="receive", aggregate_type="goods_receipt", aggregate_id=receipt_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="GoodsReceived", aggregate_type="goods_receipt", aggregate_id=receipt_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def return_purchase(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    order_id: str,
    data: PurchaseReturnCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"procurement:order:return:{tenant_id}:{order_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        order = _one(conn, "SELECT * FROM purchase_orders WHERE tenant_id=? AND id=?", (tenant_id, order_id), "PURCHASE_ORDER_NOT_FOUND", "Pedido de compra não localizado.")
        if order["state"] not in {"received", "partially_received", "partially_returned"}:
            raise DomainError("PURCHASE_ORDER_NOT_RETURNABLE", "O pedido não possui recebimento disponível para devolução.", 409)
        order_items = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=?", (tenant_id, order_id)).fetchall()}
        prepared: list[tuple[Any, dict[str, Any], dict[str, Any] | None, Decimal, Decimal]] = []
        total = Decimal("0")
        for requested in data.items:
            order_item = order_items.get(requested.purchase_order_item_id)
            if not order_item:
                raise DomainError("PURCHASE_ORDER_ITEM_NOT_FOUND", "Item não pertence ao pedido.", 422)
            amount = quantity(requested.quantity)
            available_return = quantity(order_item["received_quantity"]) - quantity(order_item.get("returned_quantity"))
            if amount > available_return:
                raise DomainError("PURCHASE_RETURN_EXCEEDS_RECEIVED", "Quantidade devolvida excede o recebido líquido.", 409)
            lot = None
            if requested.lot_id:
                lot = _one(conn, "SELECT * FROM inventory_lots WHERE tenant_id=? AND id=?", (tenant_id, requested.lot_id), "INVENTORY_LOT_NOT_FOUND", "Lote não localizado.")
                if lot["product_id"] != order_item["product_id"] or lot["warehouse_id"] != order["warehouse_id"]:
                    raise DomainError("PURCHASE_RETURN_LOT_MISMATCH", "Lote não corresponde ao item e depósito.", 422)
                if quantity(lot["quantity"]) - quantity(lot["reserved_quantity"]) < amount:
                    raise DomainError("INVENTORY_LOT_INSUFFICIENT", "Saldo livre do lote insuficiente para devolução.", 409)
            cost_value = unit_cost(lot["unit_cost"] if lot else order_item["unit_cost"])
            total += money(amount * cost_value)
            prepared.append((requested, order_item, lot, amount, cost_value))
        return_id, now = uuid7(), iso_now()
        return_number = _number("DFC", return_id)
        conn.execute("INSERT INTO purchase_returns(id,tenant_id,return_number,purchase_order_id,supplier_id,warehouse_id,reason,total_amount,state,returned_at,returned_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (return_id, tenant_id, return_number, order_id, order["supplier_id"], order["warehouse_id"], data.reason, money_str(total), "confirmed", now, user.id, now, now))
        items: list[dict[str, Any]] = []
        movements: list[dict[str, Any]] = []
        for requested, order_item, lot, amount, cost_value in prepared:
            movement = _stock_change(conn, tenant_id=tenant_id, user=user, product_id=order_item["product_id"], warehouse=order["warehouse_id"], movement_type="purchase_return_out", signed_amount=-amount, cost_value=cost_value, reference_type="purchase_return", reference_id=return_id, reason=data.reason, lot_id=lot["id"] if lot else None, now=now)
            if lot:
                new_lot_qty = quantity(lot["quantity"]) - amount
                conn.execute("UPDATE inventory_lots SET quantity=?,state=?,updated_at=? WHERE tenant_id=? AND id=?", (str(new_lot_qty), "depleted" if new_lot_qty == 0 else "active", now, tenant_id, lot["id"]))
            returned_quantity = quantity(order_item.get("returned_quantity")) + amount
            conn.execute("UPDATE purchase_order_items SET returned_quantity=? WHERE tenant_id=? AND id=?", (str(returned_quantity), tenant_id, order_item["id"]))
            item_id = uuid7()
            conn.execute("INSERT INTO purchase_return_items(id,tenant_id,purchase_return_id,purchase_order_item_id,product_id,lot_id,quantity,unit_cost,stock_movement_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (item_id, tenant_id, return_id, order_item["id"], order_item["product_id"], lot["id"] if lot else None, str(amount), str(cost_value), movement["id"], now))
            items.append({"id": item_id, "product_id": order_item["product_id"], "quantity": str(amount), "unit_cost": str(cost_value), "lot_id": lot["id"] if lot else None})
            movements.append(movement)
        conn.execute("UPDATE purchase_orders SET state='partially_returned',version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (now, tenant_id, order_id))
        result = {"return": {"id": return_id, "return_number": return_number, "purchase_order_id": order_id, "state": "confirmed", "status": "confirmed", "total_amount": money_str(total), "reason": data.reason}, "items": items, "stock": movements, "order": {"id": order_id, "state": "partially_returned", "status": "partially_returned"}}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="return", aggregate_type="purchase_return", aggregate_id=return_id, after=result, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type="PurchaseReturned", aggregate_type="purchase_return", aggregate_id=return_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


# Lotes, reservas e inventários ---------------------------------------------


def list_lots(
    request: Request,
    tenant_id: str,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    sql = "SELECT il.*,p.sku,p.name AS product_name FROM inventory_lots il JOIN products p ON p.id=il.product_id WHERE il.tenant_id=?"
    params: list[Any] = [tenant_id]
    if product_id:
        sql += " AND il.product_id=?"
        params.append(product_id)
    if warehouse_id:
        sql += " AND il.warehouse_id=?"
        params.append(warehouse_id)
    if status:
        sql += " AND il.state=?"
        params.append(status)
    sql += " ORDER BY il.expires_on IS NULL,il.expires_on,il.created_at"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def list_reservations(request: Request, tenant_id: str, status: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM inventory_reservations WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    sql += " ORDER BY created_at DESC,id DESC"
    return {"items": [_status(row) for row in request.state.store.fetch_all(sql, params)]}


def reserve_stock(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: ReservationCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:reservation:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        product = _product(conn, tenant_id, data.product_id)
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        requested = quantity(data.quantity)
        balance = _balance(conn, tenant_id, product["id"], data.warehouse_id)
        physical = quantity(balance.get("quantity") if balance else 0)
        reserved = quantity(balance.get("reserved") if balance else 0)
        lot = None
        if data.lot_id:
            lot = _one(conn, "SELECT * FROM inventory_lots WHERE tenant_id=? AND id=?", (tenant_id, data.lot_id), "INVENTORY_LOT_NOT_FOUND", "Lote não localizado.")
            if lot["product_id"] != product["id"] or lot["warehouse_id"] != data.warehouse_id:
                raise DomainError("RESERVATION_LOT_MISMATCH", "Lote não corresponde ao produto e depósito.", 422)
            available = quantity(lot["quantity"]) - quantity(lot["reserved_quantity"])
        else:
            available = physical - reserved
        if requested > available:
            raise DomainError("INSUFFICIENT_AVAILABLE_STOCK", "Saldo disponível insuficiente para reserva.", 409)
        reservation_id, now = uuid7(), iso_now()
        try:
            conn.execute("INSERT INTO inventory_reservations(id,tenant_id,product_id,warehouse_id,lot_id,source_type,source_id,quantity,consumed_quantity,state,expires_at,institution_id,unit_id,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (reservation_id, tenant_id, product["id"], data.warehouse_id, data.lot_id, data.source_type, data.source_id, str(requested), "0.0000", "active", data.expires_at.isoformat() if data.expires_at else None, data.institution_id, data.unit_id, 1, now, now))
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DomainError("STOCK_RESERVATION_EXISTS", "Já existe reserva para a mesma origem, produto, depósito e lote.", 409) from exc
            raise
        _set_balance(conn, tenant_id=tenant_id, product_id=product["id"], warehouse=data.warehouse_id, physical=physical, reserved=reserved + requested, now=now)
        if lot:
            conn.execute("UPDATE inventory_lots SET reserved_quantity=?,updated_at=? WHERE tenant_id=? AND id=?", (str(quantity(lot["reserved_quantity"]) + requested), now, tenant_id, lot["id"]))
        result = {"id": reservation_id, "product_id": product["id"], "warehouse_id": data.warehouse_id, "lot_id": data.lot_id, "quantity": str(requested), "consumed_quantity": "0.0000", "state": "active", "status": "active", "available_after": str(available - requested), "version": 1}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="reserve", aggregate_type="inventory_reservation", aggregate_id=reservation_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="StockReserved", aggregate_type="inventory_reservation", aggregate_id=reservation_id, payload=result)
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def transition_reservation(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    reservation_id: str,
    action: str,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        row = _one(conn, "SELECT * FROM inventory_reservations WHERE tenant_id=? AND id=?", (tenant_id, reservation_id), "STOCK_RESERVATION_NOT_FOUND", "Reserva não localizada.")
        if row["state"] != "active":
            raise DomainError("STOCK_RESERVATION_NOT_ACTIVE", "A reserva não está ativa.", 409)
        if action not in {"release", "consume"}:
            raise DomainError("INVALID_RESERVATION_ACTION", "Ação de reserva inválida.", 422)
        now = iso_now()
        balance = _balance(conn, tenant_id, row["product_id"], row["warehouse_id"])
        physical = quantity(balance.get("quantity") if balance else 0)
        reserved = quantity(balance.get("reserved") if balance else 0)
        amount = quantity(row["quantity"]) - quantity(row.get("consumed_quantity"))
        new_reserved = max(Decimal("0"), reserved - amount)
        movement = None
        if action == "consume":
            if physical < amount:
                raise DomainError("INSUFFICIENT_PHYSICAL_STOCK", "Saldo físico insuficiente para consumir a reserva.", 409)
            new_physical = quantity(physical - amount)
            _set_balance(
                conn,
                tenant_id=tenant_id,
                product_id=row["product_id"],
                warehouse=row["warehouse_id"],
                physical=new_physical,
                reserved=new_reserved,
                now=now,
            )
            movement_id = uuid7()
            conn.execute(
                "INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by,lot_id,balance_after) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    movement_id, tenant_id, row["product_id"], row["warehouse_id"],
                    "reservation_consume", str(-amount), None, "inventory_reservation",
                    reservation_id, "Consumo de reserva de estoque", now, user.id,
                    row.get("lot_id"), str(new_physical),
                ),
            )
            movement = {
                "id": movement_id,
                "product_id": row["product_id"],
                "warehouse": row["warehouse_id"],
                "quantity": str(-amount),
                "balance_after": str(new_physical),
                "lot_id": row.get("lot_id"),
            }
        else:
            _set_balance(
                conn,
                tenant_id=tenant_id,
                product_id=row["product_id"],
                warehouse=row["warehouse_id"],
                physical=physical,
                reserved=new_reserved,
                now=now,
            )
        if row.get("lot_id"):
            lot = _one(conn, "SELECT * FROM inventory_lots WHERE tenant_id=? AND id=?", (tenant_id, row["lot_id"]), "INVENTORY_LOT_NOT_FOUND", "Lote não localizado.")
            new_lot_reserved = max(Decimal("0"), quantity(lot["reserved_quantity"]) - amount)
            new_lot_quantity = quantity(lot["quantity"]) - amount if action == "consume" else quantity(lot["quantity"])
            if new_lot_quantity < 0:
                raise DomainError("INVENTORY_LOT_INSUFFICIENT", "Saldo do lote insuficiente para consumir a reserva.", 409)
            conn.execute(
                "UPDATE inventory_lots SET quantity=?,reserved_quantity=?,state=?,updated_at=? WHERE tenant_id=? AND id=?",
                (
                    str(new_lot_quantity), str(new_lot_reserved),
                    "depleted" if new_lot_quantity == 0 else "active", now, tenant_id, lot["id"],
                ),
            )
        state = "released" if action == "release" else "consumed"
        conn.execute("UPDATE inventory_reservations SET state=?,consumed_quantity=?,released_at=?,consumed_at=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (state, str(quantity(row["quantity"])) if action == "consume" else row.get("consumed_quantity") or "0.0000", now if action == "release" else None, now if action == "consume" else None, now, tenant_id, reservation_id))
        result = _status(dict(conn.execute("SELECT * FROM inventory_reservations WHERE tenant_id=? AND id=?", (tenant_id, reservation_id)).fetchone()))
        if movement:
            result["stock_movement"] = movement
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action=action, aggregate_type="inventory_reservation", aggregate_id=reservation_id, before=_status(row), after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="StockReservationReleased" if action == "release" else "StockReservationConsumed", aggregate_type="inventory_reservation", aggregate_id=reservation_id, payload=result)
        return result


def create_inventory_count(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: InventoryCountCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:count:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        open_count = conn.execute("SELECT id FROM inventory_counts WHERE tenant_id=? AND warehouse=? AND state IN ('draft','counting')", (tenant_id, data.warehouse_id)).fetchone()
        if open_count:
            raise DomainError("INVENTORY_COUNT_ALREADY_OPEN", "Já existe inventário aberto para o depósito.", 409)
        product_ids = list(dict.fromkeys(data.product_ids))
        rows: list[tuple[dict[str, Any], Decimal]] = []
        if product_ids:
            for product_id in product_ids:
                product = _product(conn, tenant_id, product_id)
                balance = _balance(conn, tenant_id, product_id, data.warehouse_id)
                amount = quantity(balance.get("quantity") if balance else 0)
                if amount != 0 or data.include_zero_balance:
                    rows.append((product, amount))
        else:
            for balance in conn.execute("SELECT * FROM stock_balances WHERE tenant_id=? AND warehouse=? ORDER BY product_id", (tenant_id, data.warehouse_id)).fetchall():
                raw = dict(balance)
                amount = quantity(raw["quantity"])
                if amount != 0 or data.include_zero_balance:
                    rows.append((_product(conn, tenant_id, raw["product_id"]), amount))
        if not rows:
            raise DomainError("INVENTORY_COUNT_EMPTY", "Nenhum saldo foi encontrado para o inventário.", 409)
        count_id, now = uuid7(), iso_now()
        snapshot = {"product_ids": product_ids, "include_zero_balance": data.include_zero_balance}
        conn.execute("INSERT INTO inventory_counts(id,tenant_id,warehouse,state,created_by,created_at,started_at,snapshot_json,institution_id,unit_id,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (count_id, tenant_id, data.warehouse_id, "counting", user.id, now, now, dumps(snapshot), data.institution_id, data.unit_id, 1))
        items: list[dict[str, Any]] = []
        for product, expected in rows:
            item_id = uuid7()
            conn.execute("INSERT INTO inventory_count_items(id,tenant_id,inventory_count_id,product_id,expected_quantity,counted_quantity,difference,movement_id,lot_id,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (item_id, tenant_id, count_id, product["id"], str(expected), "0.0000", str(-expected), None, None, None, now))
            items.append({"id": item_id, "product_id": product["id"], "product_name": product["name"], "expected_quantity": str(expected), "counted_quantity": None})
        result = {"count": {"id": count_id, "warehouse_id": data.warehouse_id, "warehouse": data.warehouse_id, "state": "counting", "status": "counting", "snapshot": snapshot, "version": 1}, "items": items}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="start", aggregate_type="inventory_count", aggregate_id=count_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="InventoryCountStarted", aggregate_type="inventory_count", aggregate_id=count_id, payload=result["count"])
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def inventory_count_detail(request: Request, tenant_id: str, count_id: str) -> dict[str, Any]:
    count = request.state.store.fetch_one("SELECT * FROM inventory_counts WHERE tenant_id=? AND id=?", (tenant_id, count_id))
    if not count:
        raise DomainError("INVENTORY_COUNT_NOT_FOUND", "Inventário não localizado.", 404)
    result_count = _status(count)
    result_count.setdefault("warehouse_id", result_count.get("warehouse"))
    return {"count": result_count, "items": [_status(row) for row in request.state.store.fetch_all("SELECT ici.*,p.sku,p.name AS product_name FROM inventory_count_items ici JOIN products p ON p.id=ici.product_id WHERE ici.tenant_id=? AND ici.inventory_count_id=? ORDER BY p.name,ici.id", (tenant_id, count_id))]}


def complete_inventory_count(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    count_id: str,
    data: InventoryCountComplete,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        count = _one(conn, "SELECT * FROM inventory_counts WHERE tenant_id=? AND id=?", (tenant_id, count_id), "INVENTORY_COUNT_NOT_FOUND", "Inventário não localizado.")
        if count["state"] != "counting":
            raise DomainError("INVENTORY_COUNT_NOT_OPEN", "O inventário não está em contagem.", 409)
        items = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM inventory_count_items WHERE tenant_id=? AND inventory_count_id=?", (tenant_id, count_id)).fetchall()}
        if set(items) != {entry.item_id for entry in data.items}:
            raise DomainError("INVENTORY_COUNT_ITEMS_MISMATCH", "Informe a contagem de todos os itens.", 422)
        now = iso_now()
        adjustments: list[dict[str, Any]] = []
        for entry in data.items:
            item = items[entry.item_id]
            counted = quantity(entry.counted_quantity)
            balance = _balance(conn, tenant_id, item["product_id"], count["warehouse"])
            current = quantity(balance.get("quantity") if balance else 0)
            difference = quantity(counted - current)
            movement_id = None
            if difference != 0:
                movement = _stock_change(conn, tenant_id=tenant_id, user=user, product_id=item["product_id"], warehouse=count["warehouse"], movement_type="inventory_adjustment_in" if difference > 0 else "inventory_adjustment_out", signed_amount=difference, cost_value=None, reference_type="inventory_count", reference_id=count_id, reason=data.reason, lot_id=item.get("lot_id"), now=now)
                movement_id = movement["id"]
                adjustments.append(movement)
            else:
                _set_balance(conn, tenant_id=tenant_id, product_id=item["product_id"], warehouse=count["warehouse"], physical=counted, now=now)
            conn.execute("UPDATE inventory_count_items SET expected_quantity=?,counted_quantity=?,difference=?,movement_id=?,notes=? WHERE tenant_id=? AND id=?", (str(current), str(counted), str(difference), movement_id, entry.notes, tenant_id, item["id"]))
        conn.execute("UPDATE inventory_counts SET state='completed',reason=?,approved_by=?,finalized_at=?,version=version+1 WHERE tenant_id=? AND id=?", (data.reason, user.id, now, tenant_id, count_id))
        result = {"count": {"id": count_id, "warehouse_id": count["warehouse"], "warehouse": count["warehouse"], "state": "completed", "status": "completed"}, "items": [_status(dict(row)) for row in conn.execute("SELECT * FROM inventory_count_items WHERE tenant_id=? AND inventory_count_id=? ORDER BY id", (tenant_id, count_id)).fetchall()], "adjustments": adjustments}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="complete", aggregate_type="inventory_count", aggregate_id=count_id, before=_status(count), after=result, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type="InventoryCountCompleted", aggregate_type="inventory_count", aggregate_id=count_id, payload={"count": result["count"], "adjustments": adjustments})
        return result


# Estoque mínimo e sugestões automáticas de compra ---------------------------


def _open_purchase_quantity(conn: Any, tenant_id: str, product_id: str, warehouse_id: str) -> Decimal:
    rows = conn.execute(
        "SELECT poi.quantity,poi.received_quantity "
        "FROM purchase_order_items poi "
        "JOIN purchase_orders po ON po.id=poi.purchase_order_id AND po.tenant_id=poi.tenant_id "
        "WHERE poi.tenant_id=? AND poi.product_id=? AND po.warehouse_id=? "
        "AND po.state IN ('ordered','approved','partially_received')",
        (tenant_id, product_id, warehouse_id),
    ).fetchall()
    pending = Decimal("0")
    for raw in rows:
        row = dict(raw)
        remaining = quantity(row["quantity"]) - quantity(row.get("received_quantity"))
        if remaining > 0:
            pending += remaining
    return quantity(pending)


def _reorder_snapshot(conn: Any, tenant_id: str, policy: dict[str, Any]) -> dict[str, str]:
    balance = _balance(conn, tenant_id, policy["product_id"], policy["warehouse_id"])
    physical = quantity(balance.get("quantity") if balance else 0)
    reserved = quantity(balance.get("reserved") if balance else 0)
    available = quantity(physical - reserved)
    if available < 0:
        raise DomainError("INVALID_STOCK_BALANCE", "O saldo reservado excede o saldo físico.", 409)
    incoming = _open_purchase_quantity(conn, tenant_id, policy["product_id"], policy["warehouse_id"])
    projected = quantity(available + incoming)
    minimum = quantity(policy["minimum_quantity"])
    target = quantity(policy["target_quantity"])
    suggested = quantity(max(target - projected, Decimal("0")))
    return {
        "physical_quantity": str(physical),
        "reserved_quantity": str(reserved),
        "available_quantity": str(available),
        "open_purchase_quantity": str(incoming),
        "projected_quantity": str(projected),
        "minimum_quantity": str(minimum),
        "target_quantity": str(target),
        "suggested_quantity": str(suggested),
    }


def _policy_result(conn: Any, tenant_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    product = _product(conn, tenant_id, policy["product_id"], active=False)
    supplier = None
    if policy.get("preferred_supplier_id"):
        supplier = _supplier(conn, tenant_id, policy["preferred_supplier_id"], active=False)
    result = _status(policy)
    result.update(
        {
            "warehouse": policy["warehouse_id"],
            "product_name": product["name"],
            "product_sku": product["sku"],
            "product_type": product.get("product_type"),
            "preferred_supplier_name": (
                supplier.get("trade_name") or supplier.get("legal_name") if supplier else None
            ),
            "minimum_quantity": str(quantity(policy["minimum_quantity"])),
            "target_quantity": str(quantity(policy["target_quantity"])),
            "stock": _reorder_snapshot(conn, tenant_id, policy),
        }
    )
    return result


def _suggestion_result(conn: Any, tenant_id: str, suggestion: dict[str, Any]) -> dict[str, Any]:
    product = _product(conn, tenant_id, suggestion["product_id"], active=False)
    supplier = None
    if suggestion.get("preferred_supplier_id"):
        supplier = _supplier(conn, tenant_id, suggestion["preferred_supplier_id"], active=False)
    result = _status(suggestion)
    for field in (
        "physical_quantity",
        "reserved_quantity",
        "available_quantity",
        "open_purchase_quantity",
        "projected_quantity",
        "minimum_quantity",
        "target_quantity",
        "suggested_quantity",
    ):
        result[field] = str(quantity(suggestion[field]))
    result["estimated_unit_cost"] = money_str(suggestion.get("estimated_unit_cost") or 0)
    result["estimated_total"] = money_str(suggestion.get("estimated_total") or 0)
    result.update(
        {
            "warehouse": suggestion["warehouse_id"],
            "product_name": product["name"],
            "product_sku": product["sku"],
            "product_type": product.get("product_type"),
            "preferred_supplier_name": (
                supplier.get("trade_name") or supplier.get("legal_name") if supplier else None
            ),
        }
    )
    return result


def list_reorder_policies(
    request: Request,
    tenant_id: str,
    status: str | None = None,
    product_id: str | None = None,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    sql = "SELECT * FROM inventory_reorder_policies WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if product_id:
        sql += " AND product_id=?"
        params.append(product_id)
    if warehouse_id:
        sql += " AND warehouse_id=?"
        params.append(warehouse_id)
    sql += " ORDER BY created_at DESC,id DESC"
    with request.state.store.transaction() as conn:
        rows = [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        return {"items": [_policy_result(conn, tenant_id, row) for row in rows]}


def reorder_policy_detail(request: Request, tenant_id: str, policy_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        policy = _one(
            conn,
            "SELECT * FROM inventory_reorder_policies WHERE tenant_id=? AND id=?",
            (tenant_id, policy_id),
            "REORDER_POLICY_NOT_FOUND",
            "Política de estoque mínimo não localizada.",
        )
        return _policy_result(conn, tenant_id, policy)


def create_reorder_policy(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: ReorderPolicyCreate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:reorder-policy:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        product = _product(conn, tenant_id, data.product_id)
        supplier = _supplier(conn, tenant_id, data.preferred_supplier_id, active=True) if data.preferred_supplier_id else None
        _ensure_scope(conn, tenant_id, data.institution_id, data.unit_id)
        existing = conn.execute(
            "SELECT id FROM inventory_reorder_policies WHERE tenant_id=? AND product_id=? AND warehouse_id=?",
            (tenant_id, product["id"], data.warehouse_id),
        ).fetchone()
        if existing:
            raise DomainError(
                "REORDER_POLICY_EXISTS",
                "Já existe política de estoque mínimo para o produto e depósito.",
                409,
            )
        policy_id, now = uuid7(), iso_now()
        conn.execute(
            "INSERT INTO inventory_reorder_policies("
            "id,tenant_id,product_id,warehouse_id,minimum_quantity,target_quantity,lead_time_days,"
            "preferred_supplier_id,state,institution_id,unit_id,version,created_by,created_at,updated_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                policy_id,
                tenant_id,
                product["id"],
                data.warehouse_id,
                str(quantity(data.minimum_quantity)),
                str(quantity(data.target_quantity)),
                data.lead_time_days,
                supplier["id"] if supplier else None,
                "active",
                data.institution_id,
                data.unit_id,
                1,
                user.id,
                now,
                now,
            ),
        )
        policy = dict(
            conn.execute(
                "SELECT * FROM inventory_reorder_policies WHERE tenant_id=? AND id=?",
                (tenant_id, policy_id),
            ).fetchone()
        )
        result = _policy_result(conn, tenant_id, policy)
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create",
            aggregate_type="inventory_reorder_policy",
            aggregate_id=policy_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="InventoryReorderPolicyCreated",
            aggregate_type="inventory_reorder_policy",
            aggregate_id=policy_id,
            payload=result,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def patch_reorder_policy(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    policy_id: str,
    data: ReorderPolicyPatch,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(
            conn,
            "SELECT * FROM inventory_reorder_policies WHERE tenant_id=? AND id=?",
            (tenant_id, policy_id),
            "REORDER_POLICY_NOT_FOUND",
            "Política de estoque mínimo não localizada.",
        )
        if int(before["version"]) != data.expected_version:
            raise DomainError(
                "OPTIMISTIC_CONCURRENCY_CONFLICT",
                "A política foi alterada por outro usuário.",
                409,
            )
        supplied = data.model_fields_set
        minimum = quantity(data.minimum_quantity if "minimum_quantity" in supplied else before["minimum_quantity"])
        target = quantity(data.target_quantity if "target_quantity" in supplied else before["target_quantity"])
        if target < minimum:
            raise DomainError(
                "REORDER_TARGET_BELOW_MINIMUM",
                "Estoque alvo não pode ser inferior ao estoque mínimo.",
                422,
            )
        lead_time = data.lead_time_days if "lead_time_days" in supplied else int(before["lead_time_days"])
        supplier_id = data.preferred_supplier_id if "preferred_supplier_id" in supplied else before.get("preferred_supplier_id")
        if supplier_id:
            _supplier(conn, tenant_id, supplier_id, active=True)
        institution_id = data.institution_id if "institution_id" in supplied else before.get("institution_id")
        unit_id = data.unit_id if "unit_id" in supplied else before.get("unit_id")
        _ensure_scope(conn, tenant_id, institution_id, unit_id)
        state = data.state if "state" in supplied else before["state"]
        now = iso_now()
        conn.execute(
            "UPDATE inventory_reorder_policies SET minimum_quantity=?,target_quantity=?,lead_time_days=?,"
            "preferred_supplier_id=?,state=?,institution_id=?,unit_id=?,version=version+1,updated_at=? "
            "WHERE tenant_id=? AND id=?",
            (
                str(minimum),
                str(target),
                lead_time,
                supplier_id,
                state,
                institution_id,
                unit_id,
                now,
                tenant_id,
                policy_id,
            ),
        )
        if state == "inactive":
            stale = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND policy_id=? AND state='open'",
                    (tenant_id, policy_id),
                ).fetchall()
            ]
            for suggestion in stale:
                conn.execute(
                    "UPDATE purchase_suggestions SET state='superseded',closed_at=?,closed_by=?,"
                    "closure_reason='policy_inactivated',version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                    (now, user.id, now, tenant_id, suggestion["id"]),
                )
                closed = dict(
                    conn.execute(
                        "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
                        (tenant_id, suggestion["id"]),
                    ).fetchone()
                )
                _audit(
                    conn,
                    tenant_id=tenant_id,
                    user=user,
                    request=request,
                    action="supersede",
                    aggregate_type="purchase_suggestion",
                    aggregate_id=suggestion["id"],
                    before=_suggestion_result(conn, tenant_id, suggestion),
                    after=_suggestion_result(conn, tenant_id, closed),
                    reason="policy_inactivated",
                )
                _event(
                    conn,
                    tenant_id=tenant_id,
                    request=request,
                    event_type="PurchaseSuggestionSuperseded",
                    aggregate_type="purchase_suggestion",
                    aggregate_id=suggestion["id"],
                    payload={"id": suggestion["id"], "reason": "policy_inactivated"},
                )
        after_row = dict(
            conn.execute(
                "SELECT * FROM inventory_reorder_policies WHERE tenant_id=? AND id=?",
                (tenant_id, policy_id),
            ).fetchone()
        )
        result = _policy_result(conn, tenant_id, after_row)
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="update",
            aggregate_type="inventory_reorder_policy",
            aggregate_id=policy_id,
            before=_policy_result(conn, tenant_id, before),
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="InventoryReorderPolicyUpdated",
            aggregate_type="inventory_reorder_policy",
            aggregate_id=policy_id,
            payload=result,
        )
        return result


def generate_purchase_suggestions(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    data: PurchaseSuggestionGenerate,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:purchase-suggestions:generate:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        if data.product_ids:
            for product_id in data.product_ids:
                _product(conn, tenant_id, product_id, active=False)
        sql = "SELECT * FROM inventory_reorder_policies WHERE tenant_id=? AND state='active'"
        params: list[Any] = [tenant_id]
        if data.warehouse_id:
            sql += " AND warehouse_id=?"
            params.append(data.warehouse_id)
        if data.product_ids:
            placeholders = ",".join("?" for _ in data.product_ids)
            sql += f" AND product_id IN ({placeholders})"
            params.extend(data.product_ids)
        sql += " ORDER BY created_at,id"
        policies = [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        now = iso_now()
        generated: list[dict[str, Any]] = []
        created = refreshed = superseded = not_required = 0
        for policy in policies:
            product = _product(conn, tenant_id, policy["product_id"], active=False)
            snapshot = _reorder_snapshot(conn, tenant_id, policy)
            projected = quantity(snapshot["projected_quantity"])
            minimum = quantity(snapshot["minimum_quantity"])
            existing_raw = conn.execute(
                "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND policy_id=? AND state='open'",
                (tenant_id, policy["id"]),
            ).fetchone()
            existing = dict(existing_raw) if existing_raw else None
            if projected >= minimum:
                not_required += 1
                if existing:
                    conn.execute(
                        "UPDATE purchase_suggestions SET state='superseded',physical_quantity=?,reserved_quantity=?,"
                        "available_quantity=?,open_purchase_quantity=?,projected_quantity=?,minimum_quantity=?,"
                        "target_quantity=?,suggested_quantity='0.0000',closed_at=?,closed_by=?,"
                        "closure_reason='stock_requirement_satisfied',version=version+1,updated_at=? "
                        "WHERE tenant_id=? AND id=?",
                        (
                            snapshot["physical_quantity"],
                            snapshot["reserved_quantity"],
                            snapshot["available_quantity"],
                            snapshot["open_purchase_quantity"],
                            snapshot["projected_quantity"],
                            snapshot["minimum_quantity"],
                            snapshot["target_quantity"],
                            now,
                            user.id,
                            now,
                            tenant_id,
                            existing["id"],
                        ),
                    )
                    superseded += 1
                    after = dict(
                        conn.execute(
                            "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
                            (tenant_id, existing["id"]),
                        ).fetchone()
                    )
                    _audit(
                        conn,
                        tenant_id=tenant_id,
                        user=user,
                        request=request,
                        action="supersede",
                        aggregate_type="purchase_suggestion",
                        aggregate_id=existing["id"],
                        before=_suggestion_result(conn, tenant_id, existing),
                        after=_suggestion_result(conn, tenant_id, after),
                        reason="stock_requirement_satisfied",
                    )
                    _event(
                        conn,
                        tenant_id=tenant_id,
                        request=request,
                        event_type="PurchaseSuggestionSuperseded",
                        aggregate_type="purchase_suggestion",
                        aggregate_id=existing["id"],
                        payload={"id": existing["id"], "reason": "stock_requirement_satisfied"},
                    )
                continue
            estimated_cost = money(product.get("cost") or 0)
            estimated_total = money(estimated_cost * quantity(snapshot["suggested_quantity"]))
            if existing:
                suggestion_id = existing["id"]
                conn.execute(
                    "UPDATE purchase_suggestions SET preferred_supplier_id=?,physical_quantity=?,reserved_quantity=?,"
                    "available_quantity=?,open_purchase_quantity=?,projected_quantity=?,minimum_quantity=?,"
                    "target_quantity=?,suggested_quantity=?,estimated_unit_cost=?,estimated_total=?,reason=?,"
                    "generated_at=?,generated_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                    (
                        policy.get("preferred_supplier_id"),
                        snapshot["physical_quantity"],
                        snapshot["reserved_quantity"],
                        snapshot["available_quantity"],
                        snapshot["open_purchase_quantity"],
                        snapshot["projected_quantity"],
                        snapshot["minimum_quantity"],
                        snapshot["target_quantity"],
                        snapshot["suggested_quantity"],
                        money_str(estimated_cost),
                        money_str(estimated_total),
                        "available_below_minimum",
                        now,
                        user.id,
                        now,
                        tenant_id,
                        suggestion_id,
                    ),
                )
                refreshed += 1
                event_type = "PurchaseSuggestionRefreshed"
                action = "refresh"
            else:
                suggestion_id = uuid7()
                conn.execute(
                    "INSERT INTO purchase_suggestions("
                    "id,tenant_id,policy_id,product_id,warehouse_id,preferred_supplier_id,physical_quantity,"
                    "reserved_quantity,available_quantity,open_purchase_quantity,projected_quantity,minimum_quantity,"
                    "target_quantity,suggested_quantity,estimated_unit_cost,estimated_total,reason,state,generated_at,"
                    "generated_by,version,created_at,updated_at"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        suggestion_id,
                        tenant_id,
                        policy["id"],
                        policy["product_id"],
                        policy["warehouse_id"],
                        policy.get("preferred_supplier_id"),
                        snapshot["physical_quantity"],
                        snapshot["reserved_quantity"],
                        snapshot["available_quantity"],
                        snapshot["open_purchase_quantity"],
                        snapshot["projected_quantity"],
                        snapshot["minimum_quantity"],
                        snapshot["target_quantity"],
                        snapshot["suggested_quantity"],
                        money_str(estimated_cost),
                        money_str(estimated_total),
                        "available_below_minimum",
                        "open",
                        now,
                        user.id,
                        1,
                        now,
                        now,
                    ),
                )
                created += 1
                event_type = "PurchaseSuggestionGenerated"
                action = "generate"
            row = dict(
                conn.execute(
                    "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
                    (tenant_id, suggestion_id),
                ).fetchone()
            )
            rendered = _suggestion_result(conn, tenant_id, row)
            generated.append(rendered)
            _audit(
                conn,
                tenant_id=tenant_id,
                user=user,
                request=request,
                action=action,
                aggregate_type="purchase_suggestion",
                aggregate_id=suggestion_id,
                before=_suggestion_result(conn, tenant_id, existing) if existing else None,
                after=rendered,
            )
            _event(
                conn,
                tenant_id=tenant_id,
                request=request,
                event_type=event_type,
                aggregate_type="purchase_suggestion",
                aggregate_id=suggestion_id,
                payload=rendered,
            )
        result = {
            "items": generated,
            "summary": {
                "policies_evaluated": len(policies),
                "created": created,
                "refreshed": refreshed,
                "superseded": superseded,
                "not_required": not_required,
            },
        }
        _save(conn, scope, key, payload, 200, result)
        return 200, result


def list_purchase_suggestions(
    request: Request,
    tenant_id: str,
    status: str | None = None,
    product_id: str | None = None,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    sql = "SELECT * FROM purchase_suggestions WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if product_id:
        sql += " AND product_id=?"
        params.append(product_id)
    if warehouse_id:
        sql += " AND warehouse_id=?"
        params.append(warehouse_id)
    sql += " ORDER BY generated_at DESC,id DESC"
    with request.state.store.transaction() as conn:
        rows = [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        return {"items": [_suggestion_result(conn, tenant_id, row) for row in rows]}


def purchase_suggestion_detail(request: Request, tenant_id: str, suggestion_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        row = _one(
            conn,
            "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
            (tenant_id, suggestion_id),
            "PURCHASE_SUGGESTION_NOT_FOUND",
            "Sugestão de compra não localizada.",
        )
        return _suggestion_result(conn, tenant_id, row)


def convert_purchase_suggestion(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    suggestion_id: str,
    data: PurchaseSuggestionConvert,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:purchase-suggestion:convert:{tenant_id}:{suggestion_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        before = _one(
            conn,
            "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
            (tenant_id, suggestion_id),
            "PURCHASE_SUGGESTION_NOT_FOUND",
            "Sugestão de compra não localizada.",
        )
        if before["state"] != "open":
            raise DomainError("PURCHASE_SUGGESTION_NOT_OPEN", "A sugestão não está aberta.", 409)
        if int(before["version"]) != data.expected_version:
            raise DomainError(
                "OPTIMISTIC_CONCURRENCY_CONFLICT",
                "A sugestão foi alterada por outro usuário.",
                409,
            )
        policy = _one(
            conn,
            "SELECT * FROM inventory_reorder_policies WHERE tenant_id=? AND id=?",
            (tenant_id, before["policy_id"]),
            "REORDER_POLICY_NOT_FOUND",
            "Política de estoque mínimo não localizada.",
        )
        if policy["state"] != "active":
            raise DomainError("REORDER_POLICY_INACTIVE", "A política de estoque mínimo está inativa.", 409)
        snapshot = _reorder_snapshot(conn, tenant_id, policy)
        if quantity(snapshot["projected_quantity"]) >= quantity(snapshot["minimum_quantity"]):
            raise DomainError(
                "PURCHASE_SUGGESTION_OUTDATED",
                "O estoque projetado já atende ao mínimo; regenere as sugestões.",
                409,
            )
        suggested = quantity(snapshot["suggested_quantity"])
        if suggested <= 0:
            raise DomainError("PURCHASE_SUGGESTION_WITHOUT_QUANTITY", "Não há quantidade a requisitar.", 409)
        product = _product(conn, tenant_id, before["product_id"])
        requisition_id, now = uuid7(), iso_now()
        requisition_number = _number("REQ", requisition_id)
        needed_by = data.needed_by or (date.today() + timedelta(days=int(policy["lead_time_days"])))
        justification = data.justification or (
            f"Reposição automática do produto {product['name']} para o depósito {policy['warehouse_id']}; "
            f"estoque projetado {snapshot['projected_quantity']} abaixo do mínimo {snapshot['minimum_quantity']}."
        )
        conn.execute(
            "INSERT INTO purchase_requisitions(id,tenant_id,requisition_number,requester_user_id,department_id,"
            "cost_center_id,needed_by,justification,state,institution_id,unit_id,version,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                requisition_id,
                tenant_id,
                requisition_number,
                user.id,
                data.department_id,
                data.cost_center_id,
                needed_by.isoformat(),
                justification,
                "draft",
                policy.get("institution_id"),
                policy.get("unit_id"),
                1,
                now,
                now,
            ),
        )
        item_id = uuid7()
        estimated_unit_price = money(product.get("cost") or before.get("estimated_unit_cost") or 0)
        conn.execute(
            "INSERT INTO purchase_requisition_items(id,tenant_id,requisition_id,product_id,quantity,"
            "approved_quantity,estimated_unit_price,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                item_id,
                tenant_id,
                requisition_id,
                product["id"],
                str(suggested),
                "0.0000",
                money_str(estimated_unit_price),
                f"Gerada pela sugestão de compra {suggestion_id}.",
                now,
            ),
        )
        estimated_total = money(estimated_unit_price * suggested)
        conn.execute(
            "UPDATE purchase_suggestions SET state='converted',requisition_id=?,physical_quantity=?,"
            "reserved_quantity=?,available_quantity=?,open_purchase_quantity=?,projected_quantity=?,"
            "minimum_quantity=?,target_quantity=?,suggested_quantity=?,estimated_unit_cost=?,estimated_total=?,"
            "converted_at=?,converted_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (
                requisition_id,
                snapshot["physical_quantity"],
                snapshot["reserved_quantity"],
                snapshot["available_quantity"],
                snapshot["open_purchase_quantity"],
                snapshot["projected_quantity"],
                snapshot["minimum_quantity"],
                snapshot["target_quantity"],
                snapshot["suggested_quantity"],
                money_str(estimated_unit_price),
                money_str(estimated_total),
                now,
                user.id,
                now,
                tenant_id,
                suggestion_id,
            ),
        )
        suggestion = dict(
            conn.execute(
                "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
                (tenant_id, suggestion_id),
            ).fetchone()
        )
        requisition = {
            "id": requisition_id,
            "requisition_number": requisition_number,
            "status": "draft",
            "state": "draft",
            "needed_by": needed_by.isoformat(),
            "justification": justification,
            "version": 1,
        }
        item = {
            "id": item_id,
            "product_id": product["id"],
            "product_name": product["name"],
            "quantity": str(suggested),
            "approved_quantity": "0.0000",
            "estimated_unit_price": money_str(estimated_unit_price),
        }
        result = {
            "suggestion": _suggestion_result(conn, tenant_id, suggestion),
            "requisition": requisition,
            "items": [item],
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="convert",
            aggregate_type="purchase_suggestion",
            aggregate_id=suggestion_id,
            before=_suggestion_result(conn, tenant_id, before),
            after=result["suggestion"],
        )
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create_from_suggestion",
            aggregate_type="purchase_requisition",
            aggregate_id=requisition_id,
            after={"requisition": requisition, "items": [item]},
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="PurchaseSuggestionConverted",
            aggregate_type="purchase_suggestion",
            aggregate_id=suggestion_id,
            payload={"suggestion_id": suggestion_id, "requisition_id": requisition_id},
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="PurchaseRequisitionCreated",
            aggregate_type="purchase_requisition",
            aggregate_id=requisition_id,
            payload=requisition,
        )
        _save(conn, scope, key, payload, 201, result)
        return 201, result


def dismiss_purchase_suggestion(
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    suggestion_id: str,
    data: PurchaseSuggestionDismiss,
    key: str | None,
) -> tuple[int, dict[str, Any]]:
    payload = _body(data)
    scope = f"inventory:purchase-suggestion:dismiss:{tenant_id}:{suggestion_id}"
    with request.state.store.transaction() as conn:
        cached = _cached(conn, scope, key, payload)
        if cached:
            return cached
        before = _one(
            conn,
            "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
            (tenant_id, suggestion_id),
            "PURCHASE_SUGGESTION_NOT_FOUND",
            "Sugestão de compra não localizada.",
        )
        if before["state"] != "open":
            raise DomainError("PURCHASE_SUGGESTION_NOT_OPEN", "A sugestão não está aberta.", 409)
        if int(before["version"]) != data.expected_version:
            raise DomainError(
                "OPTIMISTIC_CONCURRENCY_CONFLICT",
                "A sugestão foi alterada por outro usuário.",
                409,
            )
        now = iso_now()
        conn.execute(
            "UPDATE purchase_suggestions SET state='dismissed',closed_at=?,closed_by=?,closure_reason=?,"
            "version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (now, user.id, data.reason, now, tenant_id, suggestion_id),
        )
        after = dict(
            conn.execute(
                "SELECT * FROM purchase_suggestions WHERE tenant_id=? AND id=?",
                (tenant_id, suggestion_id),
            ).fetchone()
        )
        result = _suggestion_result(conn, tenant_id, after)
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="dismiss",
            aggregate_type="purchase_suggestion",
            aggregate_id=suggestion_id,
            before=_suggestion_result(conn, tenant_id, before),
            after=result,
            reason=data.reason,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="PurchaseSuggestionDismissed",
            aggregate_type="purchase_suggestion",
            aggregate_id=suggestion_id,
            payload={"id": suggestion_id, "reason": data.reason},
        )
        _save(conn, scope, key, payload, 200, result)
        return 200, result
