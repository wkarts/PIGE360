from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.modules.operations.common import SALES_ROLES, require, row_or_404, tenant
from app.modules.procurement.application import vertical_service as service
from app.modules.procurement.presentation.vertical_schemas import (
    ActionReason,
    GoodsReceiptCreate,
    ProductBarcodeCreate,
    ProductVariantCreate,
    PurchaseOrderCreate,
    PurchaseReturnCreate,
    PurchaseSuggestionConvert,
    PurchaseSuggestionDismiss,
    PurchaseSuggestionGenerate,
    QuotationAward,
    QuotationCreate,
    RequisitionApproval,
    RequisitionCreate,
    ReorderPolicyCreate,
    ReorderPolicyPatch,
    ReservationCreate,
    SupplierCreateUnified,
    SupplierPatch,
    SupplierProposalCreate,
)
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["procurement"])

PROCUREMENT_ROLES = SALES_ROLES | {"unit_manager", "finance_manager", "auditor"}
PROCUREMENT_WRITE_ROLES = SALES_ROLES | {"unit_manager"}


def _created(response: Response, result: tuple[int, object]):
    status_code, payload = result
    response.status_code = status_code
    return payload


# Fornecedores ---------------------------------------------------------------


@router.get("/suppliers", operation_id="list_suppliers_relational")
def list_suppliers(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_ROLES)
    return service.list_suppliers(request, tenant(user), status, q)


@router.post("/suppliers", status_code=201, operation_id="create_supplier_relational")
def create_supplier(
    data: SupplierCreateUnified,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_supplier(request, tenant(user), user, data, idempotency_key))


@router.get("/suppliers/{supplier_id}", operation_id="get_supplier_detail")
def get_supplier(supplier_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.supplier_detail(request, tenant(user), supplier_id)


@router.patch("/suppliers/{supplier_id}", operation_id="update_supplier")
def update_supplier(
    supplier_id: str,
    data: SupplierPatch,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.patch_supplier(request, tenant(user), user, supplier_id, data)


# Compatibilidade: pedido de compra direto legado ---------------------------


class LegacyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PurchaseItemInput(LegacyModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseOrderInput(LegacyModel):
    supplier_id: str
    order_number: str
    expected_on: str | None = None
    items: list[PurchaseItemInput] = Field(min_length=1)


class PurchaseReceiveItem(LegacyModel):
    purchase_order_item_id: str
    quantity: Decimal = Field(gt=0)


class PurchaseReceiveInput(LegacyModel):
    reason: str = Field(min_length=3)
    items: list[PurchaseReceiveItem] | None = None


@router.get("/purchase-orders", operation_id="list_purchase_orders_relational")
def list_legacy_orders(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    orders = request.state.store.fetch_all(
        "SELECT po.*,s.legal_name AS supplier_name FROM purchase_orders po "
        "JOIN suppliers s ON s.id=po.supplier_id WHERE po.tenant_id=? ORDER BY po.created_at DESC",
        (tenant(user),),
    )
    for order in orders:
        order["items"] = request.state.store.fetch_all(
            "SELECT poi.*,p.sku,p.name FROM purchase_order_items poi "
            "JOIN products p ON p.id=poi.product_id WHERE poi.purchase_order_id=? ORDER BY poi.created_at,poi.id",
            (order["id"],),
        )
    return {"items": orders}


@router.post("/purchase-orders", status_code=201, operation_id="create_purchase_order_relational")
def create_legacy_order(
    data: PurchaseOrderInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    tenant_id = tenant(user)
    row_or_404(
        request,
        "SELECT id FROM suppliers WHERE id=? AND tenant_id=? AND state='active'",
        (data.supplier_id, tenant_id),
        "SUPPLIER_NOT_FOUND",
        "Fornecedor não localizado.",
    )
    now = iso_now()
    total = Decimal("0")
    products: list[dict] = []
    for item in data.items:
        product = row_or_404(
            request,
            "SELECT * FROM products WHERE id=? AND tenant_id=? AND state='active'",
            (item.product_id, tenant_id),
            "PRODUCT_NOT_FOUND",
            "Produto não localizado.",
        )
        products.append(product)
        total += money(item.quantity) * money(item.unit_cost)
    order_id = uuid7()
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO purchase_orders(id,tenant_id,supplier_id,order_number,state,total_amount,expected_on,warehouse_id,currency,subtotal,freight_amount,discount_amount,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                order_id,
                tenant_id,
                data.supplier_id,
                data.order_number,
                "ordered",
                money_str(total),
                data.expected_on,
                "default",
                "BRL",
                money_str(total),
                "0.00",
                "0.00",
                1,
                now,
                now,
            ),
        )
        for item, product in zip(data.items, products, strict=True):
            line_total = money(item.quantity) * money(item.unit_cost)
            conn.execute(
                "INSERT INTO purchase_order_items(id,tenant_id,purchase_order_id,product_id,quantity,unit_cost,received_quantity,returned_quantity,discount_amount,total_amount,fiscal_profile_snapshot_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    order_id,
                    item.product_id,
                    str(item.quantity),
                    money_str(item.unit_cost),
                    "0",
                    "0",
                    "0.00",
                    money_str(line_total),
                    product.get("fiscal_profile_json") or "{}",
                    now,
                ),
            )
        result = {"id": order_id, "order_number": data.order_number, "state": "ordered", "total_amount": money_str(total)}
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="order",
            aggregate_type="purchase_order",
            aggregate_id=order_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="PurchaseOrderCreated",
            aggregate_type="purchase_order",
            aggregate_id=order_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


@router.post("/purchase-orders/{order_id}/receive", operation_id="receive_purchase_order")
def receive_legacy_order(
    order_id: str,
    data: PurchaseReceiveInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    tenant_id = tenant(user)
    now = iso_now()
    with request.state.store.transaction() as conn:
        raw_order = conn.execute("SELECT * FROM purchase_orders WHERE id=? AND tenant_id=?", (order_id, tenant_id)).fetchone()
        if not raw_order:
            raise DomainError("PURCHASE_ORDER_NOT_FOUND", "Pedido de compra não localizado.", 404)
        order = dict(raw_order)
        if order["state"] not in {"ordered", "partially_received"}:
            raise DomainError("PURCHASE_ORDER_NOT_RECEIVABLE", "Pedido não aceita recebimento.", 409)
        rows = conn.execute(
            "SELECT * FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=? ORDER BY created_at,id",
            (tenant_id, order_id),
        ).fetchall()
        order_items = {dict(row)["id"]: dict(row) for row in rows}
        requested: dict[str, Decimal] = {}
        if data.items:
            for item in data.items:
                if item.purchase_order_item_id in requested:
                    raise DomainError("DUPLICATE_RECEIPT_ITEM", "Item repetido no recebimento.", 422)
                if item.purchase_order_item_id not in order_items:
                    raise DomainError("PURCHASE_ORDER_ITEM_NOT_FOUND", "Item não pertence ao pedido de compra.", 404)
                requested[item.purchase_order_item_id] = item.quantity
        else:
            for item_id, item in order_items.items():
                pending = money(item["quantity"]) - money(item["received_quantity"])
                if pending > 0:
                    requested[item_id] = pending
        if not requested:
            raise DomainError("NOTHING_TO_RECEIVE", "Não há quantidades pendentes para recebimento.", 409)
        receipt_id = uuid7()
        conn.execute(
            "INSERT INTO purchase_receipts(id,tenant_id,purchase_order_id,state,reason,created_by,received_at) VALUES(?,?,?,?,?,?,?)",
            (receipt_id, tenant_id, order_id, "received", data.reason, user.id, now),
        )
        received_lines = 0
        for item_id, amount in requested.items():
            item = order_items[item_id]
            pending = money(item["quantity"]) - money(item["received_quantity"])
            if amount > pending:
                raise DomainError("PURCHASE_RECEIPT_QUANTITY_EXCEEDED", "Quantidade recebida excede o saldo pendente do item.", 409)
            new_received = money(item["received_quantity"]) + amount
            conn.execute("UPDATE purchase_order_items SET received_quantity=? WHERE tenant_id=? AND id=?", (str(new_received), tenant_id, item_id))
            balance = conn.execute(
                "SELECT quantity FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",
                (tenant_id, item["product_id"]),
            ).fetchone()
            current = money(balance["quantity"] if balance else 0)
            new_quantity = current + amount
            if balance:
                conn.execute(
                    "UPDATE stock_balances SET quantity=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse='default'",
                    (str(new_quantity), now, tenant_id, item["product_id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) VALUES(?,?,?,?,?,?)",
                    (tenant_id, item["product_id"], "default", str(new_quantity), "0", now),
                )
            conn.execute(
                "INSERT INTO purchase_receipt_items(id,tenant_id,purchase_receipt_id,purchase_order_item_id,product_id,quantity,unit_cost,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, receipt_id, item_id, item["product_id"], str(amount), item["unit_cost"], now),
            )
            conn.execute(
                "INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by,balance_after) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, item["product_id"], "default", "purchase_receipt", str(amount), item["unit_cost"], "purchase_receipt", receipt_id, data.reason, now, user.id, str(new_quantity)),
            )
            received_lines += 1
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=? AND CAST(received_quantity AS NUMERIC) < CAST(quantity AS NUMERIC)",
            (tenant_id, order_id),
        ).fetchone()
        state = "partially_received" if int(remaining["n"]) else "received"
        conn.execute(
            "UPDATE purchase_orders SET state=?,received_at=?,updated_at=? WHERE tenant_id=? AND id=?",
            (state, now if state == "received" else None, now, tenant_id, order_id),
        )
        result = {"id": order_id, "receipt_id": receipt_id, "state": state, "received_lines": received_lines, "received_at": now}
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="receive",
            aggregate_type="purchase_order",
            aggregate_id=order_id,
            correlation_id=request.state.correlation_id,
            before=order,
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="PurchaseOrderReceived" if state == "received" else "PurchaseOrderPartiallyReceived",
            aggregate_type="purchase_order",
            aggregate_id=order_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


# Requisições ----------------------------------------------------------------


@router.get("/procurement/requisitions", operation_id="list_purchase_requisitions")
def list_requisitions(request: Request, status: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.list_requisitions(request, tenant(user), status)


@router.post("/procurement/requisitions", status_code=201, operation_id="create_purchase_requisition")
def create_requisition(
    data: RequisitionCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_requisition(request, tenant(user), user, data, idempotency_key))


@router.get("/procurement/requisitions/{requisition_id}", operation_id="get_purchase_requisition")
def get_requisition(requisition_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.requisition_detail(request, tenant(user), requisition_id)


@router.post("/procurement/requisitions/{requisition_id}/submit", operation_id="submit_purchase_requisition")
def submit_requisition(requisition_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.transition_requisition(request, tenant(user), user, requisition_id, action="submit")


@router.post("/procurement/requisitions/{requisition_id}/approve", operation_id="approve_purchase_requisition")
def approve_requisition(
    requisition_id: str,
    data: RequisitionApproval,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.transition_requisition(request, tenant(user), user, requisition_id, action="approve", approval=data)


@router.post("/procurement/requisitions/{requisition_id}/reject", operation_id="reject_purchase_requisition")
def reject_requisition(requisition_id: str, data: ActionReason, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.transition_requisition(request, tenant(user), user, requisition_id, action="reject", reason=data.reason)


@router.post("/procurement/requisitions/{requisition_id}/cancel", operation_id="cancel_purchase_requisition")
def cancel_requisition(requisition_id: str, data: ActionReason, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.transition_requisition(request, tenant(user), user, requisition_id, action="cancel", reason=data.reason)


# Cotações -------------------------------------------------------------------


@router.get("/procurement/quotations", operation_id="list_procurement_quotations")
def list_quotations(request: Request, status: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.list_quotations(request, tenant(user), status)


@router.post("/procurement/quotations", status_code=201, operation_id="create_procurement_quotation")
def create_quotation(
    data: QuotationCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_quotation(request, tenant(user), user, data, idempotency_key))


@router.get("/procurement/quotations/{quotation_id}", operation_id="get_procurement_quotation")
def get_quotation(quotation_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.quotation_detail(request, tenant(user), quotation_id)


@router.post(
    "/procurement/quotations/{quotation_id}/suppliers/{supplier_id}/proposal",
    status_code=201,
    operation_id="submit_supplier_quotation_proposal",
)
def submit_proposal(
    quotation_id: str,
    supplier_id: str,
    data: SupplierProposalCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(
        response,
        service.submit_supplier_proposal(request, tenant(user), user, quotation_id, supplier_id, data, idempotency_key),
    )


@router.post("/procurement/quotations/{quotation_id}/award", status_code=201, operation_id="award_procurement_quotation")
def award_quotation(
    quotation_id: str,
    data: QuotationAward,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.award_quotation(request, tenant(user), user, quotation_id, data, idempotency_key))


# Pedidos verticais ----------------------------------------------------------


@router.get("/procurement/orders", operation_id="list_procurement_orders")
def list_orders(request: Request, status: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.list_orders(request, tenant(user), status)


@router.post("/procurement/orders", status_code=201, operation_id="create_procurement_order")
def create_order(
    data: PurchaseOrderCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_purchase_order(request, tenant(user), user, data, idempotency_key))


@router.get("/procurement/orders/{order_id}", operation_id="get_procurement_order")
def get_order(order_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.order_detail(request, tenant(user), order_id)


@router.post("/procurement/orders/{order_id}/approve", operation_id="approve_procurement_order")
def approve_order(order_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.approve_order(request, tenant(user), user, order_id)


@router.post("/procurement/orders/{order_id}/receipts", status_code=201, operation_id="receive_procurement_order")
def receive_order(
    order_id: str,
    data: GoodsReceiptCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.receive_order(request, tenant(user), user, order_id, data, idempotency_key))


@router.post("/procurement/orders/{order_id}/returns", status_code=201, operation_id="return_procurement_order")
def return_order(
    order_id: str,
    data: PurchaseReturnCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.return_purchase(request, tenant(user), user, order_id, data, idempotency_key))


# Variantes, lotes e reservas ------------------------------------------------


@router.post("/inventory/product-variants", status_code=201, operation_id="create_inventory_product_variant")
def create_product_variant(
    data: ProductVariantCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_variant(request, tenant(user), user, data, idempotency_key))


@router.post("/inventory/product-barcodes", status_code=201, operation_id="create_inventory_product_barcode")
def create_product_barcode(
    data: ProductBarcodeCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_barcode(request, tenant(user), user, data, idempotency_key))


@router.get("/inventory/lots", operation_id="list_inventory_lots")
def list_lots(
    request: Request,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    status: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_ROLES)
    return service.list_lots(request, tenant(user), product_id, warehouse_id, status)


@router.get("/inventory/reservations", operation_id="list_inventory_reservations")
def list_reservations(request: Request, status: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.list_reservations(request, tenant(user), status)


@router.post("/inventory/reservations", status_code=201, operation_id="create_inventory_reservation")
def create_reservation(
    data: ReservationCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.reserve_stock(request, tenant(user), user, data, idempotency_key))


@router.post("/inventory/reservations/{reservation_id}/release", operation_id="release_inventory_reservation")
def release_reservation(reservation_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.transition_reservation(request, tenant(user), user, reservation_id, "release")


@router.post("/inventory/reservations/{reservation_id}/consume", operation_id="consume_inventory_reservation")
def consume_reservation(reservation_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.transition_reservation(request, tenant(user), user, reservation_id, "consume")


# Estoque mínimo e sugestões de compra --------------------------------------


@router.get("/inventory/reorder-policies", operation_id="list_inventory_reorder_policies")
def list_reorder_policies(
    request: Request,
    status: str | None = None,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_ROLES)
    return service.list_reorder_policies(request, tenant(user), status, product_id, warehouse_id)


@router.post("/inventory/reorder-policies", status_code=201, operation_id="create_inventory_reorder_policy")
def create_reorder_policy(
    data: ReorderPolicyCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(response, service.create_reorder_policy(request, tenant(user), user, data, idempotency_key))


@router.get("/inventory/reorder-policies/{policy_id}", operation_id="get_inventory_reorder_policy")
def get_reorder_policy(policy_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.reorder_policy_detail(request, tenant(user), policy_id)


@router.patch("/inventory/reorder-policies/{policy_id}", operation_id="update_inventory_reorder_policy")
def update_reorder_policy(
    policy_id: str,
    data: ReorderPolicyPatch,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return service.patch_reorder_policy(request, tenant(user), user, policy_id, data)


@router.post("/inventory/purchase-suggestions/generate", operation_id="generate_inventory_purchase_suggestions")
def generate_purchase_suggestions(
    data: PurchaseSuggestionGenerate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(
        response,
        service.generate_purchase_suggestions(request, tenant(user), user, data, idempotency_key),
    )


@router.get("/inventory/purchase-suggestions", operation_id="list_inventory_purchase_suggestions")
def list_purchase_suggestions(
    request: Request,
    status: str | None = None,
    product_id: str | None = None,
    warehouse_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_ROLES)
    return service.list_purchase_suggestions(request, tenant(user), status, product_id, warehouse_id)


@router.get("/inventory/purchase-suggestions/{suggestion_id}", operation_id="get_inventory_purchase_suggestion")
def get_purchase_suggestion(suggestion_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, PROCUREMENT_ROLES)
    return service.purchase_suggestion_detail(request, tenant(user), suggestion_id)


@router.post(
    "/inventory/purchase-suggestions/{suggestion_id}/convert",
    status_code=201,
    operation_id="convert_inventory_purchase_suggestion",
)
def convert_purchase_suggestion(
    suggestion_id: str,
    data: PurchaseSuggestionConvert,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(
        response,
        service.convert_purchase_suggestion(
            request,
            tenant(user),
            user,
            suggestion_id,
            data,
            idempotency_key,
        ),
    )


@router.post(
    "/inventory/purchase-suggestions/{suggestion_id}/dismiss",
    operation_id="dismiss_inventory_purchase_suggestion",
)
def dismiss_purchase_suggestion(
    suggestion_id: str,
    data: PurchaseSuggestionDismiss,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, PROCUREMENT_WRITE_ROLES)
    return _created(
        response,
        service.dismiss_purchase_suggestion(
            request,
            tenant(user),
            user,
            suggestion_id,
            data,
            idempotency_key,
        ),
    )
