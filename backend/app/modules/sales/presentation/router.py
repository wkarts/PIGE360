from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from app.modules.operations.common import SALES_ROLES, dumps, require, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import CENT, money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["sales"])


class SaleItemInput(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)


class SalePaymentInput(BaseModel):
    method: Literal["pix", "cash", "card", "wallet", "institutional_credit", "other"]
    amount: Decimal = Field(gt=0)
    external_reference: str | None = None


class SaleInput(BaseModel):
    cash_session_id: str
    channel: Literal["pos", "canteen", "mobile", "kiosk", "web"]
    canteen_location_id: str | None = None
    customer_person_id: str | None = None
    student_id: str | None = None
    items: list[SaleItemInput] = Field(min_length=1)
    payments: list[SalePaymentInput] = Field(default_factory=list)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    request_fiscal_document: bool = True


@router.get("/sales", operation_id="list_sales_relational")
def list_sales(
    request: Request,
    limit: int = 100,
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES | {"finance_manager", "finance_operator", "fiscal_manager"})
    return {
        "items": request.state.store.fetch_all(
            "SELECT * FROM sales WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
            (tenant(user), min(max(limit, 1), 500)),
        )
    }


@router.post("/sales", status_code=201, operation_id="complete_sale_relational")
def complete_sale(
    data: SaleInput,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, SALES_ROLES)
    tenant_id = tenant(user)
    body = data.model_dump(mode="json")
    scope = f"sale:complete:{tenant_id}"
    now = iso_now()

    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            response.status_code = cached[0]
            return cached[1]
        cash = conn.execute(
            "SELECT * FROM cash_sessions WHERE id=? AND tenant_id=? AND state='open'",
            (data.cash_session_id, tenant_id),
        ).fetchone()
        if not cash:
            raise DomainError("OPEN_CASH_REQUIRED", "É necessário caixa aberto para concluir a venda.", 409)
        if data.channel == "canteen":
            if not data.canteen_location_id:
                raise DomainError("CANTEEN_LOCATION_REQUIRED", "Venda de cantina exige a unidade/ponto de cantina.", 422)
            location = conn.execute("SELECT id FROM canteen_locations WHERE tenant_id=? AND id=? AND state='active'", (tenant_id, data.canteen_location_id)).fetchone()
            if not location:
                raise DomainError("CANTEEN_LOCATION_NOT_FOUND", "Cantina ativa não localizada.", 404)
        canteen_local_now = datetime.now(UTC)
        if data.channel == "canteen" and data.student_id:
            timezone_row = conn.execute(
                "SELECT u.timezone FROM enrollments e JOIN units u ON u.id=e.unit_id WHERE e.tenant_id=? AND e.student_id=? AND e.state='active' ORDER BY e.created_at DESC LIMIT 1",
                (tenant_id, data.student_id),
            ).fetchone()
            try:
                canteen_local_now = datetime.now(UTC).astimezone(ZoneInfo(str(timezone_row["timezone"] if timezone_row else "America/Bahia")))
            except Exception:
                canteen_local_now = datetime.now(UTC)

        lines = []
        subtotal = Decimal("0")
        for item in data.items:
            product = conn.execute(
                "SELECT * FROM products WHERE id=? AND tenant_id=? AND state='active'",
                (item.product_id, tenant_id),
            ).fetchone()
            if not product:
                raise DomainError("PRODUCT_NOT_FOUND", "Produto não localizado.", 404)
            balance = conn.execute(
                "SELECT * FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",
                (tenant_id, item.product_id),
            ).fetchone()
            physical_quantity = money(balance["quantity"] if balance else 0)
            available = physical_quantity - money(balance["reserved"] if balance else 0)
            if available < item.quantity:
                raise DomainError(
                    "INSUFFICIENT_STOCK",
                    f"Estoque insuficiente para {product['name']}.",
                    409,
                )
            unit_price = money(product["sale_price"])
            if data.channel == "canteen":
                current_day = canteen_local_now.date().isoformat()
                menu_item = conn.execute(
                    "SELECT cmi.price_override FROM canteen_menu_items cmi JOIN canteen_menus cm ON cm.id=cmi.canteen_menu_id "
                    "WHERE cmi.tenant_id=? AND cmi.product_id=? AND cmi.state='active' AND cm.canteen_location_id=? AND cm.state='active' "
                    "AND (cm.starts_on IS NULL OR cm.starts_on<=?) AND (cm.ends_on IS NULL OR cm.ends_on>=?) "
                    "ORDER BY cm.starts_on DESC,cm.created_at DESC LIMIT 1",
                    (tenant_id, item.product_id, data.canteen_location_id, current_day, current_day),
                ).fetchone()
                if not menu_item:
                    raise DomainError("CANTEEN_PRODUCT_NOT_ON_MENU", f"Produto {product['name']} não está disponível no cardápio ativo desta cantina.", 409)
                if menu_item["price_override"] is not None:
                    unit_price = money(menu_item["price_override"])
            line_total = (unit_price * item.quantity - money(item.discount)).quantize(CENT)
            if line_total < 0:
                raise DomainError(
                    "INVALID_ITEM_DISCOUNT",
                    "Desconto do item excede o valor bruto.",
                    422,
                )
            subtotal += line_total
            lines.append((item, product, unit_price, line_total, physical_quantity))

        discount = money(data.discount)
        total = (subtotal - discount).quantize(CENT)
        if total < 0:
            raise DomainError("INVALID_SALE_DISCOUNT", "Desconto total excede o subtotal.", 422)

        wallet = None
        wallet_payment = sum((money(item.amount) for item in data.payments if item.method == "wallet"), Decimal("0"))
        subsidy_amount = Decimal("0")
        local_now = canteen_local_now
        if data.channel == "canteen" and data.student_id:
            student = conn.execute("SELECT id FROM students WHERE tenant_id=? AND id=? AND state='active'", (tenant_id, data.student_id)).fetchone()
            if not student:
                raise DomainError("STUDENT_NOT_FOUND", "Aluno não localizado para a venda da cantina.", 404)
            policy = conn.execute("SELECT * FROM student_food_policies WHERE tenant_id=? AND student_id=? AND state='active'", (tenant_id, data.student_id)).fetchone()
            wallet = conn.execute("SELECT * FROM student_wallets WHERE tenant_id=? AND student_id=? AND state='active'", (tenant_id, data.student_id)).fetchone()
            if policy:
                blocked_products = set(json.loads(policy["blocked_product_ids_json"] or "[]"))
                blocked_allergens = {str(x).strip().lower() for x in json.loads(policy["blocked_allergens_json"] or "[]")}
                for item, product, *_ in lines:
                    if item.product_id in blocked_products:
                        raise DomainError("CANTEEN_PRODUCT_BLOCKED", f"Produto {product['name']} está bloqueado para o aluno.", 409)
                    allergens = {str(x).strip().lower() for x in json.loads(product["allergen_json"] or "[]")}
                    intersection = sorted(allergens & blocked_allergens)
                    if intersection:
                        raise DomainError("CANTEEN_ALLERGEN_BLOCKED", f"Produto {product['name']} contém alergênico/restrição bloqueada: {', '.join(intersection)}.", 409)
                local_time = local_now.strftime("%H:%M")
                if policy["purchase_start_time"] and local_time < str(policy["purchase_start_time"]):
                    raise DomainError("CANTEEN_PURCHASE_TIME_BLOCKED", "Compra fora do horário permitido para o aluno.", 409)
                if policy["purchase_end_time"] and local_time > str(policy["purchase_end_time"]):
                    raise DomainError("CANTEEN_PURCHASE_TIME_BLOCKED", "Compra fora do horário permitido para o aluno.", 409)
            today = local_now.date()
            week_start = today - timedelta(days=today.weekday())
            def spent_since(start_date: str) -> Decimal:
                row = conn.execute(
                    "SELECT COALESCE(SUM(s.total_amount - COALESCE((SELECT SUM(sr.total_amount) FROM sale_returns sr WHERE sr.tenant_id=s.tenant_id AND sr.sale_id=s.id AND sr.state='completed'),0)),0) AS total "
                    "FROM sales s WHERE s.tenant_id=? AND s.student_id=? AND s.channel='canteen' AND s.state IN ('completed','partially_returned') AND s.created_at>=?",
                    (tenant_id, data.student_id, start_date),
                ).fetchone()
                return money(row["total"] if row else 0)
            daily_limit = money(policy["daily_limit"]) if policy and policy["daily_limit"] is not None else (money(wallet["daily_limit"]) if wallet and wallet["daily_limit"] is not None else None)
            weekly_limit = money(policy["weekly_limit"]) if policy and policy["weekly_limit"] is not None else (money(wallet["weekly_limit"]) if wallet and wallet["weekly_limit"] is not None else None)
            if daily_limit is not None and spent_since(f"{today.isoformat()}T00:00:00") + total > daily_limit:
                raise DomainError("CANTEEN_DAILY_LIMIT_EXCEEDED", "Compra excede o limite diário configurado para o aluno.", 409)
            if weekly_limit is not None and spent_since(f"{week_start.isoformat()}T00:00:00") + total > weekly_limit:
                raise DomainError("CANTEEN_WEEKLY_LIMIT_EXCEEDED", "Compra excede o limite semanal configurado para o aluno.", 409)
            subsidies = conn.execute("SELECT * FROM canteen_subsidies WHERE tenant_id=? AND student_id=? AND state='active' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?)", (tenant_id, data.student_id, today.isoformat(), today.isoformat())).fetchall()
            benefits=[]
            for subsidy in subsidies:
                if subsidy["subsidy_type"] == "free_meal": benefit = total
                elif subsidy["subsidy_type"] == "fixed": benefit = money(subsidy["amount"] or 0)
                elif subsidy["subsidy_type"] == "percentage": benefit = (total * money(subsidy["percentage"] or 0) / Decimal("100")).quantize(CENT)
                else: benefit = Decimal("0")
                benefits.append(min(benefit, total))
            subsidy_amount = max(benefits, default=Decimal("0")).quantize(CENT)

        if wallet_payment > 0:
            if not data.student_id:
                raise DomainError("WALLET_STUDENT_REQUIRED", "Pagamento com carteira exige aluno identificado.", 422)
            wallet = wallet or conn.execute("SELECT * FROM student_wallets WHERE tenant_id=? AND student_id=? AND state='active'", (tenant_id, data.student_id)).fetchone()
            if not wallet:
                raise DomainError("WALLET_NOT_FOUND", "Carteira ativa do aluno não localizada.", 409)
            if money(wallet["balance"]) < wallet_payment:
                raise DomainError("WALLET_INSUFFICIENT_BALANCE", "Saldo insuficiente na carteira da cantina.", 409)

        customer_due = (total - subsidy_amount).quantize(CENT)
        paid = sum((money(item.amount) for item in data.payments), Decimal("0"))
        if paid != customer_due:
            raise DomainError(
                "SALE_PAYMENT_MISMATCH",
                "Soma dos pagamentos deve ser igual ao valor devido após subsídio.",
                422,
            )

        sale_id = uuid7()
        conn.execute(
            "INSERT INTO sales(id,tenant_id,cash_session_id,customer_person_id,student_id,canteen_location_id,channel,subtotal,"
            "discount,total_amount,state,fiscal_status,idempotency_key,created_by,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sale_id,
                tenant_id,
                data.cash_session_id,
                data.customer_person_id,
                data.student_id,
                data.canteen_location_id,
                data.channel,
                money_str(subtotal),
                money_str(discount),
                money_str(total),
                "completed",
                "requested" if data.request_fiscal_document else "not_required",
                idempotency_key,
                user.id,
                now,
            ),
        )
        for item, product, unit_price, line_total, physical_quantity in lines:
            conn.execute(
                "INSERT INTO sale_items(id,tenant_id,sale_id,product_id,quantity,unit_price,discount,total_amount,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    sale_id,
                    item.product_id,
                    str(item.quantity),
                    money_str(unit_price),
                    money_str(item.discount),
                    money_str(line_total),
                    now,
                ),
            )
            new_quantity = physical_quantity - item.quantity
            conn.execute(
                "UPDATE stock_balances SET quantity=?,updated_at=? "
                "WHERE tenant_id=? AND product_id=? AND warehouse='default'",
                (str(new_quantity), now, tenant_id, item.product_id),
            )
            conn.execute(
                "INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,"
                "reference_type,reference_id,reason,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    item.product_id,
                    "default",
                    "sale",
                    str(-item.quantity),
                    product["cost"],
                    "sale",
                    sale_id,
                    "Baixa transacional da venda",
                    now,
                    user.id,
                ),
            )
        for payment in data.payments:
            conn.execute(
                "INSERT INTO sale_payments(id,tenant_id,sale_id,method,amount,external_reference,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, sale_id, payment.method, money_str(payment.amount), payment.external_reference, now),
            )
        if subsidy_amount > 0:
            conn.execute(
                "INSERT INTO sale_payments(id,tenant_id,sale_id,method,amount,external_reference,created_at) VALUES(?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, sale_id, "institutional_credit", money_str(subsidy_amount), "canteen-subsidy", now),
            )
        if wallet_payment > 0 and wallet:
            before = money(wallet["balance"]); after = before - wallet_payment
            conn.execute("UPDATE student_wallets SET balance=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (money_str(after), now, tenant_id, wallet["id"]))
            conn.execute(
                "INSERT INTO wallet_transactions(id,tenant_id,wallet_id,transaction_type,amount,balance_before,balance_after,reference_type,reference_id,reason,created_by,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, wallet["id"], "purchase", money_str(wallet_payment), money_str(before), money_str(after), "sale", sale_id, "Compra na cantina", user.id, f"sale:{sale_id}", now),
            )

        fiscal_id = None
        if data.request_fiscal_document:
            profile = conn.execute(
                "SELECT * FROM fiscal_profiles WHERE tenant_id=? AND state='active' "
                "ORDER BY created_at LIMIT 1",
                (tenant_id,),
            ).fetchone()
            profile_data = dict(profile) if profile else {}
            fiscal_id = uuid7()
            provider_connection_id = profile_data.get("provider_connection_id")
            provider_status = "queued" if provider_connection_id else "not_configured"
            conn.execute(
                "INSERT INTO fiscal_documents(id,tenant_id,fiscal_profile_id,document_type,source_type,source_id,"
                "environment,state,provider_connection_id,provider_status,totals_json,request_json,response_json,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fiscal_id,
                    tenant_id,
                    profile_data.get("id"),
                    "NFC-e",
                    "sale",
                    sale_id,
                    profile_data.get("environment") or "homologation",
                    "requested",
                    provider_connection_id,
                    provider_status,
                    dumps({"total": money_str(total)}),
                    dumps({"sale_id": sale_id}),
                    "{}",
                    now,
                    now,
                ),
            )
            fiscal_payload = {
                "id": fiscal_id,
                "document_type": "NFC-e",
                "source_type": "sale",
                "source_id": sale_id,
                "state": "requested",
                "provider_connection_id": provider_connection_id,
                "provider_status": provider_status,
            }
            conn.execute(
                "INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,"
                "provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    fiscal_id,
                    "requested",
                    "requested",
                    provider_connection_id,
                    dumps(fiscal_payload),
                    now,
                ),
            )
            add_outbox(
                conn,
                tenant_id=tenant_id,
                event_type="FiscalDocumentRequested",
                aggregate_type="fiscal_document",
                aggregate_id=fiscal_id,
                payload=fiscal_payload,
                correlation_id=request.state.correlation_id,
            )

        result = {
            "id": sale_id,
            "state": "completed",
            "subtotal": money_str(subtotal),
            "discount": money_str(discount),
            "total_amount": money_str(total),
            "subsidy_amount": money_str(subsidy_amount),
            "customer_due": money_str(customer_due),
            "fiscal_status": "requested" if fiscal_id else "not_required",
            "fiscal_document_id": fiscal_id,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="complete",
            aggregate_type="sale",
            aggregate_id=sale_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="SaleCompleted",
            aggregate_type="sale",
            aggregate_id=sale_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return result


class SaleReturnItemInput(BaseModel):
    sale_item_id: str
    quantity: Decimal = Field(gt=0)


class SaleReturnInput(BaseModel):
    items: list[SaleReturnItemInput] = Field(min_length=1)
    refund_method: Literal["cash", "pix", "card", "wallet", "institutional_credit", "other"]
    external_reference: str | None = None
    reason: str = Field(min_length=3, max_length=1000)


@router.get("/sales/{sale_id}", operation_id="get_sale_details")
def get_sale_details(sale_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,SALES_ROLES|{"finance_manager","finance_operator","fiscal_manager"});tid=tenant(user)
    sale=request.state.store.fetch_one("SELECT * FROM sales WHERE tenant_id=? AND id=?",(tid,sale_id))
    if not sale:raise DomainError("SALE_NOT_FOUND","Venda não localizada.",404)
    sale["items"]=request.state.store.fetch_all("SELECT si.*,p.sku,p.name FROM sale_items si JOIN products p ON p.id=si.product_id WHERE si.tenant_id=? AND si.sale_id=? ORDER BY si.created_at,si.id",(tid,sale_id))
    sale["payments"]=request.state.store.fetch_all("SELECT * FROM sale_payments WHERE tenant_id=? AND sale_id=? ORDER BY created_at,id",(tid,sale_id))
    sale["returns"]=request.state.store.fetch_all("SELECT * FROM sale_returns WHERE tenant_id=? AND sale_id=? ORDER BY created_at DESC",(tid,sale_id))
    return sale


@router.post("/sales/{sale_id}/returns", status_code=201, operation_id="return_sale_items")
def return_sale_items(
    sale_id:str,
    data:SaleReturnInput,
    request:Request,
    response:Response,
    idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),
    user:CurrentUser=Depends(current_user),
):
    require(user,SALES_ROLES|{"finance_manager"});tid=tenant(user);body=data.model_dump(mode="json");scope=f"sale-return:{tid}:{sale_id}";now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        raw=conn.execute("SELECT * FROM sales WHERE tenant_id=? AND id=?",(tid,sale_id)).fetchone()
        if not raw:raise DomainError("SALE_NOT_FOUND","Venda não localizada.",404)
        sale=dict(raw)
        if sale["state"] not in {"completed","partially_returned"}:raise DomainError("SALE_NOT_RETURNABLE","Venda não aceita devolução neste estado.",409)
        seen:set[str]=set();lines=[];total=Decimal("0")
        for requested in data.items:
            if requested.sale_item_id in seen:raise DomainError("DUPLICATE_RETURN_ITEM","Item repetido na devolução.",422)
            seen.add(requested.sale_item_id)
            item_raw=conn.execute("SELECT * FROM sale_items WHERE tenant_id=? AND sale_id=? AND id=?",(tid,sale_id,requested.sale_item_id)).fetchone()
            if not item_raw:raise DomainError("SALE_ITEM_NOT_FOUND","Item da venda não localizado.",404)
            item=dict(item_raw);already=conn.execute("SELECT COALESCE(SUM(sri.quantity),0) AS q FROM sale_return_items sri JOIN sale_returns sr ON sr.id=sri.sale_return_id WHERE sri.tenant_id=? AND sr.sale_id=? AND sri.sale_item_id=? AND sr.state='completed'",(tid,sale_id,requested.sale_item_id)).fetchone();returned=money(already["q"] if already else 0);sold=money(item["quantity"])
            if returned+requested.quantity>sold:raise DomainError("RETURN_QUANTITY_EXCEEDED","Quantidade devolvida excede a quantidade vendida.",409)
            unit_effective=(money(item["total_amount"])/sold).quantize(CENT);amount=(unit_effective*requested.quantity).quantize(CENT);total+=amount;lines.append((item,requested,amount))
        return_id=uuid7();conn.execute("INSERT INTO sale_returns(id,tenant_id,sale_id,total_amount,refund_method,state,reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(return_id,tid,sale_id,money_str(total),data.refund_method,"completed",data.reason,user.id,now))
        for item,requested,amount in lines:
            conn.execute("INSERT INTO sale_return_items(id,tenant_id,sale_return_id,sale_item_id,product_id,quantity,amount,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,return_id,item["id"],item["product_id"],str(requested.quantity),money_str(amount),now))
            balance=conn.execute("SELECT quantity FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",(tid,item["product_id"])).fetchone();qty=money(balance["quantity"] if balance else 0)+requested.quantity
            if balance:conn.execute("UPDATE stock_balances SET quantity=?,updated_at=? WHERE tenant_id=? AND product_id=? AND warehouse='default'",(str(qty),now,tid,item["product_id"]))
            else:conn.execute("INSERT INTO stock_balances(tenant_id,product_id,warehouse,quantity,reserved,updated_at) VALUES(?,?,?,?,?,?)",(tid,item["product_id"],"default",str(requested.quantity),"0",now))
            conn.execute("INSERT INTO stock_movements(id,tenant_id,product_id,warehouse,movement_type,quantity,unit_cost,reference_type,reference_id,reason,occurred_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,item["product_id"],"default","sale_return",str(requested.quantity),None,"sale_return",return_id,data.reason,now,user.id))
        original_items=conn.execute("SELECT id,quantity FROM sale_items WHERE tenant_id=? AND sale_id=?",(tid,sale_id)).fetchall();fully=True
        for oi in original_items:
            q=conn.execute("SELECT COALESCE(SUM(sri.quantity),0) AS q FROM sale_return_items sri JOIN sale_returns sr ON sr.id=sri.sale_return_id WHERE sri.tenant_id=? AND sr.sale_id=? AND sri.sale_item_id=? AND sr.state='completed'",(tid,sale_id,oi["id"])).fetchone()
            if money(q["q"] if q else 0)<money(oi["quantity"]):fully=False;break
        sale_total=money(sale["total_amount"])
        institutional_row=conn.execute("SELECT COALESCE(SUM(amount),0) AS amount FROM sale_payments WHERE tenant_id=? AND sale_id=? AND method='institutional_credit'",(tid,sale_id)).fetchone()
        institutional_paid=money(institutional_row["amount"] if institutional_row else 0)
        customer_paid=max(Decimal("0"),sale_total-institutional_paid)
        prior_refunds_row=conn.execute(
            "SELECT COALESCE(SUM(sf.amount),0) AS amount FROM sale_refunds sf JOIN sale_returns sr ON sr.id=sf.sale_return_id WHERE sf.tenant_id=? AND sr.sale_id=? AND sf.state='completed'",
            (tid,sale_id),
        ).fetchone()
        prior_customer_refunds=money(prior_refunds_row["amount"] if prior_refunds_row else 0)
        remaining_customer_refund=max(Decimal("0"),customer_paid-prior_customer_refunds)
        if fully:
            customer_refund=remaining_customer_refund
        elif sale_total>0:
            customer_ratio=(customer_paid/sale_total)
            customer_refund=min((total*customer_ratio).quantize(CENT),remaining_customer_refund)
        else:
            customer_refund=Decimal("0")
        subsidy_reversal=(total-customer_refund).quantize(CENT)
        refund_state="completed" if data.refund_method in {"cash","wallet"} else "pending"
        if data.refund_method == "wallet" and customer_refund>0:
            if not sale.get("student_id"): raise DomainError("WALLET_STUDENT_REQUIRED","Venda não possui aluno para devolução em carteira.",409)
            wallet=conn.execute("SELECT * FROM student_wallets WHERE tenant_id=? AND student_id=? AND state='active'",(tid,sale["student_id"])).fetchone()
            if not wallet: raise DomainError("WALLET_NOT_FOUND","Carteira ativa do aluno não localizada.",409)
            before=money(wallet["balance"]);after=before+customer_refund
            conn.execute("UPDATE student_wallets SET balance=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(money_str(after),now,tid,wallet["id"]))
            conn.execute("INSERT INTO wallet_transactions(id,tenant_id,wallet_id,transaction_type,amount,balance_before,balance_after,reference_type,reference_id,reason,created_by,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,wallet["id"],"refund",money_str(customer_refund),money_str(before),money_str(after),"sale_return",return_id,data.reason,user.id,f"sale-return:{return_id}",now))
        conn.execute("INSERT INTO sale_refunds(id,tenant_id,sale_return_id,method,amount,state,external_reference,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,return_id,data.refund_method,money_str(customer_refund),refund_state,data.external_reference,now))
        sale_state="returned" if fully else "partially_returned";conn.execute("UPDATE sales SET state=? WHERE tenant_id=? AND id=?",(sale_state,tid,sale_id))
        fiscal=conn.execute("SELECT id FROM fiscal_documents WHERE tenant_id=? AND source_type='sale' AND source_id=?",(tid,sale_id)).fetchone()
        if fiscal:conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,fiscal["id"],"sale_return_requested","pending",dumps({"sale_return_id":return_id,"amount":money_str(total)}),now))
        result={"id":return_id,"sale_id":sale_id,"total_amount":money_str(total),"refund_amount":money_str(customer_refund),"subsidy_reversal_amount":money_str(subsidy_reversal),"state":"completed","refund_state":refund_state,"sale_state":sale_state};add_audit(conn,tenant_id=tid,actor_id=user.id,action="return",aggregate_type="sale",aggregate_id=sale_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="SaleReturned",aggregate_type="sale",aggregate_id=sale_id,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result
