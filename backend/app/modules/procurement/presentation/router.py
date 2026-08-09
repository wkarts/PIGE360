from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import SALES_ROLES, require, row_or_404, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["procurement"])


class SupplierInput(BaseModel):
    legal_name: str
    trade_name: str | None = None
    cnpj: str | None = None
    email: str | None = None
    phone: str | None = None


class PurchaseItemInput(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseOrderInput(BaseModel):
    supplier_id: str
    order_number: str
    expected_on: str | None = None
    items: list[PurchaseItemInput] = Field(min_length=1)


class PurchaseReceiveItem(BaseModel):
    purchase_order_item_id: str
    quantity: Decimal = Field(gt=0)


class PurchaseReceiveInput(BaseModel):
    reason: str = Field(min_length=3)
    items: list[PurchaseReceiveItem] | None = None


@router.get("/suppliers", operation_id="list_suppliers_relational")
def list_suppliers(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, SALES_ROLES)
    return {
        "items": request.state.store.fetch_all(
            "SELECT * FROM suppliers WHERE tenant_id=? ORDER BY legal_name",
            (tenant(user),),
        )
    }


@router.post("/suppliers", status_code=201, operation_id="create_supplier_relational")
def create_supplier(
    data: SupplierInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    supplier_id = uuid7()
    now = iso_now()
    result = {
        "id": supplier_id,
        "legal_name": data.legal_name,
        "cnpj": data.cnpj,
        "state": "active",
    }
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO suppliers(id,tenant_id,legal_name,trade_name,cnpj,email,phone,state,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                supplier_id,
                tenant_id,
                data.legal_name,
                data.trade_name,
                data.cnpj,
                data.email,
                data.phone,
                "active",
                now,
                now,
            ),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="supplier",
            aggregate_id=supplier_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.get("/purchase-orders", operation_id="list_purchase_orders_relational")
def list_orders(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, SALES_ROLES)
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
def create_order(
    data: PurchaseOrderInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
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
    for item in data.items:
        row_or_404(
            request,
            "SELECT id FROM products WHERE id=? AND tenant_id=? AND state='active'",
            (item.product_id, tenant_id),
            "PRODUCT_NOT_FOUND",
            "Produto não localizado.",
        )
        total += money(item.quantity) * money(item.unit_cost)
    order_id = uuid7()
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO purchase_orders(id,tenant_id,supplier_id,order_number,state,total_amount,expected_on,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                order_id,
                tenant_id,
                data.supplier_id,
                data.order_number,
                "ordered",
                money_str(total),
                data.expected_on,
                now,
                now,
            ),
        )
        for item in data.items:
            conn.execute(
                "INSERT INTO purchase_order_items(id,tenant_id,purchase_order_id,product_id,quantity,unit_cost,"
                "received_quantity,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    order_id,
                    item.product_id,
                    str(item.quantity),
                    money_str(item.unit_cost),
                    "0",
                    now,
                ),
            )
        result = {
            "id": order_id,
            "order_number": data.order_number,
            "state": "ordered",
            "total_amount": money_str(total),
        }
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
def receive_order(
    order_id: str,
    data: PurchaseReceiveInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    now = iso_now()
    with request.state.store.transaction() as conn:
        raw_order = conn.execute("SELECT * FROM purchase_orders WHERE id=? AND tenant_id=?", (order_id, tenant_id)).fetchone()
        if not raw_order:
            raise DomainError("PURCHASE_ORDER_NOT_FOUND", "Pedido de compra não localizado.", 404)
        order = dict(raw_order)
        if order["state"] not in {"ordered", "partially_received"}:
            raise DomainError("PURCHASE_ORDER_NOT_RECEIVABLE", "Pedido não aceita recebimento.", 409)
        rows = conn.execute("SELECT * FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=? ORDER BY created_at,id", (tenant_id, order_id)).fetchall()
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
        conn.execute("INSERT INTO purchase_receipts(id,tenant_id,purchase_order_id,state,reason,created_by,received_at) VALUES(?,?,?,?,?,?,?)", (receipt_id, tenant_id, order_id, "received", data.reason, user.id, now))
        received_lines = 0
        for item_id, quantity in requested.items():
            item = order_items[item_id]
            pending = money(item["quantity"]) - money(item["received_quantity"])
            if quantity > pending:
                raise DomainError("PURCHASE_RECEIPT_QUANTITY_EXCEEDED", "Quantidade recebida excede o saldo pendente do item.", 409)
            new_received = money(item["received_quantity"]) + quantity
            conn.execute("UPDATE purchase_order_items SET received_quantity=? WHERE tenant_id=? AND id=?", (str(new_received), tenant_id, item_id))
            balance = conn.execute("SELECT quantity FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'", (tenant_id, item["product_id"])).fetchone()
            current = money(balance["quantity"] if balance else 0); new_quantity = current + quantity
            if balance:
                conn.execute("UPDATE stock_balances SET quantity=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse='default'", (str(new_quantity), now, tenant_id, item["product_id"]))
            else:
                conn.execute("INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) VALUES(?,?,?,?,?,?)", (tenant_id, item["product_id"], "default", str(new_quantity), "0", now))
            conn.execute("INSERT INTO purchase_receipt_items(id,tenant_id,purchase_receipt_id,purchase_order_item_id,product_id,quantity,unit_cost,created_at) VALUES(?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,receipt_id,item_id,item["product_id"],str(quantity),item["unit_cost"],now))
            conn.execute("INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,item["product_id"],"default","purchase_receipt",str(quantity),item["unit_cost"],"purchase_receipt",receipt_id,data.reason,now,user.id))
            received_lines += 1
        remaining = conn.execute("SELECT COUNT(*) AS n FROM purchase_order_items WHERE tenant_id=? AND purchase_order_id=? AND CAST(received_quantity AS NUMERIC) < CAST(quantity AS NUMERIC)", (tenant_id,order_id)).fetchone()
        state = "partially_received" if int(remaining["n"]) else "received"
        conn.execute("UPDATE purchase_orders SET state=?,received_at=?,updated_at=? WHERE tenant_id=? AND id=?", (state, now if state=="received" else None, now, tenant_id, order_id))
        result={"id":order_id,"receipt_id":receipt_id,"state":state,"received_lines":received_lines,"received_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="receive",aggregate_type="purchase_order",aggregate_id=order_id,correlation_id=request.state.correlation_id,before=order,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="PurchaseOrderReceived" if state=="received" else "PurchaseOrderPartiallyReceived",aggregate_type="purchase_order",aggregate_id=order_id,payload=result,correlation_id=request.state.correlation_id)
    return result

