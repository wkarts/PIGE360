from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from app.modules.operations.common import SALES_ROLES, dumps, require, tenant
from app.modules.procurement.application import vertical_service as procurement_service
from app.modules.procurement.presentation.vertical_schemas import (
    InventoryCountComplete,
    InventoryCountCreate,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["inventory"])


class ProductInput(BaseModel):
    sku: str
    barcode: str | None = None
    name: str
    product_type: Literal["product", "food", "uniform", "book", "material", "kit"] = "product"
    ncm: str | None = None
    cest: str | None = None
    unit: str = "UN"
    cost: Decimal = Field(ge=0)
    sale_price: Decimal = Field(ge=0)
    fiscal_profile: dict[str, Any] = Field(default_factory=dict)
    allergens: list[str] = Field(default_factory=list)
    restrictions: dict[str, Any] = Field(default_factory=dict)


class StockAdjustment(BaseModel):
    quantity: Decimal
    warehouse: str = "default"
    reason: str = Field(min_length=3, max_length=1000)
    unit_cost: Decimal | None = Field(default=None, ge=0)


@router.get("/products", operation_id="list_products_relational")
def list_products(
    request: Request,
    q: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES | {"finance_manager", "finance_operator"})
    tenant_id = tenant(user)
    sql = (
        "SELECT p.*,COALESCE(sb.quantity,0) AS stock_quantity,COALESCE(sb.reserved,0) AS stock_reserved "
        "FROM products p LEFT JOIN stock_balances sb "
        "ON sb.product_id=p.id AND sb.tenant_id=p.tenant_id AND sb.warehouse='default' "
        "WHERE p.tenant_id=?"
    )
    params: list[Any] = [tenant_id]
    if q:
        sql += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ?)"
        term = f"%{q}%"
        params.extend([term, term, term])
    sql += " ORDER BY p.name"
    return {"items": request.state.store.fetch_all(sql, params)}


@router.post("/products", status_code=201, operation_id="create_product_relational")
def create_product(
    data: ProductInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    product_id = uuid7()
    now = iso_now()
    result = {
        "id": product_id,
        "sku": data.sku,
        "barcode": data.barcode,
        "name": data.name,
        "sale_price": money_str(data.sale_price),
        "state": "active",
    }
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO products(id,tenant_id,sku,barcode,name,product_type,ncm,cest,unit,cost,sale_price,"
            "fiscal_profile_json,allergen_json,restriction_json,state,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                product_id,
                tenant_id,
                data.sku,
                data.barcode,
                data.name,
                data.product_type,
                data.ncm,
                data.cest,
                data.unit,
                money_str(data.cost),
                money_str(data.sale_price),
                dumps(data.fiscal_profile),
                dumps(data.allergens),
                dumps(data.restrictions),
                "active",
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (tenant_id, product_id, "default", "0", "0", now),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="create",
            aggregate_type="product",
            aggregate_id=product_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.post("/products/{product_id}/stock-adjustments", operation_id="adjust_product_stock")
def adjust_stock(
    product_id: str,
    data: StockAdjustment,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    body = data.model_dump(mode="json")
    scope = f"stock-adjust:{tenant_id}:{product_id}:{data.warehouse}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            response.status_code = cached[0]
            return cached[1]
        product = conn.execute(
            "SELECT id FROM products WHERE id=? AND tenant_id=? AND state='active'",
            (product_id, tenant_id),
        ).fetchone()
        if not product:
            raise DomainError("PRODUCT_NOT_FOUND", "Produto não localizado.", 404)
        balance = conn.execute(
            "SELECT * FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse=?",
            (tenant_id, product_id, data.warehouse),
        ).fetchone()
        current = money(balance["quantity"] if balance else 0)
        new_quantity = current + data.quantity
        if new_quantity < 0:
            raise DomainError(
                "NEGATIVE_STOCK_NOT_ALLOWED",
                "Ajuste resultaria em estoque negativo.",
                409,
            )
        now = iso_now()
        if balance:
            conn.execute(
                "UPDATE stock_balances SET quantity=?,updated_at=? "
                "WHERE tenant_id=? AND product_id=? AND warehouse=?",
                (str(new_quantity), now, tenant_id, product_id, data.warehouse),
            )
        else:
            conn.execute(
                "INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (tenant_id, product_id, data.warehouse, str(new_quantity), "0", now),
            )
        movement_id = uuid7()
        conn.execute(
            "INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,"
            "reference_type,reference_id,reason,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                movement_id,
                tenant_id,
                product_id,
                data.warehouse,
                "adjustment",
                str(data.quantity),
                money_str(data.unit_cost) if data.unit_cost is not None else None,
                "manual_adjustment",
                movement_id,
                data.reason,
                now,
                user.id,
            ),
        )
        result = {
            "product_id": product_id,
            "warehouse": data.warehouse,
            "previous_quantity": str(current),
            "quantity": str(new_quantity),
            "movement_id": movement_id,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="stock_adjustment",
            aggregate_type="product",
            aggregate_id=product_id,
            correlation_id=request.state.correlation_id,
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="StockAdjusted",
            aggregate_type="product",
            aggregate_id=product_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        save_idempotent(conn, scope, idempotency_key, body, 200, result)
    return result


class StockTransferItem(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class StockTransferInput(BaseModel):
    from_warehouse: str = Field(min_length=1, max_length=80)
    to_warehouse: str = Field(min_length=1, max_length=80)
    items: list[StockTransferItem] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=1000)


class InventoryCountItemInput(BaseModel):
    product_id: str
    counted_quantity: Decimal = Field(ge=0)


class InventoryCountInput(BaseModel):
    warehouse: str = Field(min_length=1, max_length=80)
    items: list[InventoryCountItemInput] = Field(min_length=1)


class InventoryFinalizeInput(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.get("/inventory/movements", operation_id="list_stock_movements")
def list_stock_movements(
    request: Request,
    product_id: str | None = None,
    warehouse: str | None = None,
    limit: int = 200,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES | {"finance_manager", "finance_operator", "fiscal_manager"})
    tid = tenant(user)
    sql = "SELECT sm.*,p.sku,p.name AS product_name FROM stock_movements sm JOIN products p ON p.id=sm.product_id WHERE sm.tenant_id=?"
    params: list[Any] = [tid]
    if product_id:
        sql += " AND sm.product_id=?"; params.append(product_id)
    if warehouse:
        sql += " AND sm.warehouse=?"; params.append(warehouse)
    sql += " ORDER BY sm.occurred_at DESC,sm.id DESC LIMIT ?"; params.append(min(max(limit, 1), 1000))
    return {"items": request.state.store.fetch_all(sql, params)}


@router.post("/inventory/transfers", status_code=201, operation_id="transfer_stock_between_warehouses")
def transfer_stock(
    data: StockTransferInput,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES); tid = tenant(user)
    if data.from_warehouse == data.to_warehouse:
        raise DomainError("SAME_WAREHOUSE_TRANSFER", "Depósito de origem e destino devem ser diferentes.", 422)
    body = data.model_dump(mode="json"); scope = f"stock-transfer:{tid}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            response.status_code = cached[0]; return cached[1]
        seen: set[str] = set(); validated: list[tuple[StockTransferItem, Decimal]] = []
        for item in data.items:
            if item.product_id in seen: raise DomainError("DUPLICATE_TRANSFER_ITEM", "Produto repetido na transferência.", 422)
            seen.add(item.product_id)
            product = conn.execute("SELECT id FROM products WHERE tenant_id=? AND id=? AND state='active'", (tid, item.product_id)).fetchone()
            if not product: raise DomainError("PRODUCT_NOT_FOUND", "Produto não localizado.", 404)
            source = conn.execute("SELECT quantity,reserved FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse=?", (tid,item.product_id,data.from_warehouse)).fetchone()
            physical = money(source["quantity"] if source else 0)
            available = physical - money(source["reserved"] if source else 0)
            if available < item.quantity: raise DomainError("INSUFFICIENT_STOCK", "Estoque insuficiente para transferência.", 409)
            validated.append((item, physical))
        transfer_id=uuid7(); now=iso_now()
        conn.execute("INSERT INTO stock_transfers(id,tenant_id,from_warehouse,to_warehouse,state,reason,created_by,created_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?)",(transfer_id,tid,data.from_warehouse,data.to_warehouse,"completed",data.reason,user.id,now,now))
        for item,physical in validated:
            source_new=physical-item.quantity
            conn.execute("UPDATE stock_balances SET quantity=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse=?",(str(source_new),now,tid,item.product_id,data.from_warehouse))
            target=conn.execute("SELECT quantity FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse=?",(tid,item.product_id,data.to_warehouse)).fetchone()
            if target:
                conn.execute("UPDATE stock_balances SET quantity=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse=?",(str(money(target["quantity"])+item.quantity),now,tid,item.product_id,data.to_warehouse))
            else:
                conn.execute("INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) VALUES(?,?,?,?,?,?)",(tid,item.product_id,data.to_warehouse,str(item.quantity),"0",now))
            conn.execute("INSERT INTO stock_transfer_items(id,tenant_id,stock_transfer_id,product_id,quantity,created_at) VALUES(?,?,?,?,?,?)",(uuid7(),tid,transfer_id,item.product_id,str(item.quantity),now))
            for warehouse,qty,movement_type in ((data.from_warehouse,-item.quantity,"transfer_out"),(data.to_warehouse,item.quantity,"transfer_in")):
                conn.execute("INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,item.product_id,warehouse,movement_type,str(qty),None,"stock_transfer",transfer_id,data.reason,now,user.id))
        result={"id":transfer_id,"from_warehouse":data.from_warehouse,"to_warehouse":data.to_warehouse,"items":len(validated),"state":"completed"}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="transfer",aggregate_type="stock_transfer",aggregate_id=transfer_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="StockTransferred",aggregate_type="stock_transfer",aggregate_id=transfer_id,payload=result,correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result


@router.post("/inventory/counts", status_code=201, operation_id="create_inventory_count")
def create_inventory_count(
    data: InventoryCountInput | InventoryCountCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=8, max_length=200
    ),
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tid = tenant(user)
    if isinstance(data, InventoryCountCreate):
        status_code, result = procurement_service.create_inventory_count(
            request, tid, user, data, idempotency_key
        )
        response.status_code = status_code
        return result

    count_id = uuid7()
    now = iso_now()
    seen: set[str] = set()
    rows = []
    for item in data.items:
        if item.product_id in seen:
            raise DomainError("DUPLICATE_COUNT_ITEM", "Produto repetido no inventário.", 422)
        seen.add(item.product_id)
        product = request.state.store.fetch_one(
            "SELECT id FROM products WHERE tenant_id=? AND id=? AND state='active'",
            (tid, item.product_id),
        )
        if not product:
            raise DomainError("PRODUCT_NOT_FOUND", "Produto não localizado.", 404)
        balance = request.state.store.fetch_one(
            "SELECT quantity FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse=?",
            (tid, item.product_id, data.warehouse),
        )
        expected = money(balance["quantity"] if balance else 0)
        rows.append((item, expected))
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO inventory_counts(id,tenant_id,warehouse,state,created_by,created_at) VALUES(?,?,?,?,?,?)",
            (count_id, tid, data.warehouse, "draft", user.id, now),
        )
        for item, expected in rows:
            diff = item.counted_quantity - expected
            conn.execute(
                "INSERT INTO inventory_count_items(id,tenant_id,inventory_count_id,product_id,expected_quantity,counted_quantity,difference,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tid,
                    count_id,
                    item.product_id,
                    str(expected),
                    str(item.counted_quantity),
                    str(diff),
                    now,
                ),
            )
        result = {
            "id": count_id,
            "warehouse": data.warehouse,
            "state": "draft",
            "items": len(rows),
        }
        add_audit(
            conn,
            tenant_id=tid,
            actor_id=user.id,
            action="create",
            aggregate_type="inventory_count",
            aggregate_id=count_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
    return result


@router.get("/inventory/counts/{count_id}", operation_id="get_inventory_count_detail")
def get_inventory_count(
    count_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES | {"finance_manager", "auditor"})
    return procurement_service.inventory_count_detail(request, tenant(user), count_id)


@router.post("/inventory/counts/{count_id}/complete", operation_id="complete_inventory_count")
def complete_inventory_count(
    count_id: str,
    data: InventoryCountComplete,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    return procurement_service.complete_inventory_count(
        request, tenant(user), user, count_id, data
    )


@router.post("/inventory/counts/{count_id}/finalize", operation_id="finalize_inventory_count")
def finalize_inventory_count(count_id:str,data:InventoryFinalizeInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,SALES_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM inventory_counts WHERE tenant_id=? AND id=?",(tid,count_id)).fetchone()
        if not raw:raise DomainError("INVENTORY_COUNT_NOT_FOUND","Inventário não localizado.",404)
        count=dict(raw)
        if count["state"]!="draft":raise DomainError("INVENTORY_COUNT_NOT_DRAFT","Inventário já foi finalizado.",409)
        items=conn.execute("SELECT * FROM inventory_count_items WHERE tenant_id=? AND inventory_count_id=?",(tid,count_id)).fetchall()
        adjustments=0
        for raw_item in items:
            item=dict(raw_item);current=conn.execute("SELECT quantity FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse=?",(tid,item["product_id"],count["warehouse"])).fetchone();current_qty=money(current["quantity"] if current else 0);counted=money(item["counted_quantity"]);diff=counted-current_qty
            if current:conn.execute("UPDATE stock_balances SET quantity=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse=?",(str(counted),now,tid,item["product_id"],count["warehouse"]))
            else:conn.execute("INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) VALUES(?,?,?,?,?,?)",(tid,item["product_id"],count["warehouse"],str(counted),"0",now))
            movement=None
            if diff!=0:
                movement=uuid7();adjustments+=1;conn.execute("INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(movement,tid,item["product_id"],count["warehouse"],"inventory_count",str(diff),None,"inventory_count",count_id,data.reason,now,user.id))
            conn.execute("UPDATE inventory_count_items SET expected_quantity=?,difference=?,movement_id=? WHERE id=?",(str(current_qty),str(diff),movement,item["id"]))
        conn.execute("UPDATE inventory_counts SET state='finalized',reason=?,approved_by=?,finalized_at=? WHERE tenant_id=? AND id=?",(data.reason,user.id,now,tid,count_id));result={"id":count_id,"state":"finalized","adjustments":adjustments,"warehouse":count["warehouse"]};add_audit(conn,tenant_id=tid,actor_id=user.id,action="finalize",aggregate_type="inventory_count",aggregate_id=count_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="InventoryCountFinalized",aggregate_type="inventory_count",aggregate_id=count_id,payload=result,correlation_id=request.state.correlation_id)
    return result
