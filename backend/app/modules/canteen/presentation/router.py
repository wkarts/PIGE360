from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.modules.operations.common import FINANCE_ROLES, SALES_ROLES, dumps, require, row_or_404, tenant
from app.modules.portals.access import assert_student_access, guardian_can_access_student, student_for_user
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.domain.money import money, money_str
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["canteen"])
CANTEEN_ADMIN = SALES_ROLES | {"finance_manager", "finance_operator", "secretary"}


class CanteenLocationInput(BaseModel):
    unit_id: str | None = None
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)


class MenuInput(BaseModel):
    canteen_location_id: str
    name: str = Field(min_length=2, max_length=160)
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on não pode anteceder starts_on")
        return self


class MenuItemInput(BaseModel):
    product_id: str
    price_override: Decimal | None = Field(default=None, ge=0)
    available_from: str | None = None
    available_until: str | None = None


class MenuStateInput(BaseModel):
    state: Literal["draft", "active", "suspended", "archived"]
    reason: str = Field(min_length=3, max_length=1000)


class WalletInput(BaseModel):
    student_id: str
    daily_limit: Decimal | None = Field(default=None, ge=0)
    weekly_limit: Decimal | None = Field(default=None, ge=0)


class WalletLimitInput(BaseModel):
    daily_limit: Decimal | None = Field(default=None, ge=0)
    weekly_limit: Decimal | None = Field(default=None, ge=0)
    state: Literal["active", "suspended"] = "active"
    expected_version: int = Field(ge=1)


class WalletCreditInput(BaseModel):
    amount: Decimal = Field(gt=0)
    method: Literal["pix", "cash", "card", "bank_transfer", "subsidy", "adjustment"]
    external_reference: str | None = None
    reason: str = Field(min_length=3, max_length=1000)


class FoodPolicyInput(BaseModel):
    blocked_allergens: list[str] = Field(default_factory=list)
    blocked_product_ids: list[str] = Field(default_factory=list)
    daily_limit: Decimal | None = Field(default=None, ge=0)
    weekly_limit: Decimal | None = Field(default=None, ge=0)
    purchase_start_time: str | None = None
    purchase_end_time: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SubsidyInput(BaseModel):
    student_id: str
    subsidy_type: Literal["fixed", "percentage", "free_meal"]
    amount: Decimal | None = Field(default=None, ge=0)
    percentage: Decimal | None = Field(default=None, ge=0, le=100)
    valid_from: date
    valid_until: date | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def validate_values(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until não pode anteceder valid_from")
        if self.subsidy_type == "fixed" and self.amount is None:
            raise ValueError("amount é obrigatório para subsídio fixo")
        if self.subsidy_type == "percentage" and self.percentage is None:
            raise ValueError("percentage é obrigatório para subsídio percentual")
        return self


class CanteenQuoteItem(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)


class CanteenQuoteInput(BaseModel):
    canteen_location_id: str
    student_id: str
    items: list[CanteenQuoteItem] = Field(min_length=1)


def _wallet_row(request: Request, tenant_id: str, student_id: str):
    return request.state.store.fetch_one(
        "SELECT * FROM student_wallets WHERE tenant_id=? AND student_id=?",
        (tenant_id, student_id),
    )


def _wallet_payload(request: Request, row: dict):
    item = dict(row)
    item["transactions"] = request.state.store.fetch_all(
        "SELECT * FROM wallet_transactions WHERE tenant_id=? AND wallet_id=? ORDER BY created_at DESC,id DESC LIMIT 200",
        (row["tenant_id"], row["id"]),
    )
    return item


@router.get("/canteen/pos/students", operation_id="search_canteen_pos_students")
def search_pos_students(request: Request, q: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);sql="""SELECT s.id,s.registration_number,p.full_name,p.social_name,
      sw.id AS wallet_id,sw.balance AS wallet_balance,sw.state AS wallet_state
      FROM students s JOIN people p ON p.id=s.person_id LEFT JOIN student_wallets sw ON sw.student_id=s.id AND sw.tenant_id=s.tenant_id
      WHERE s.tenant_id=? AND s.state='active'""";params:list[object]=[tid]
    if q:
        sql+=" AND (LOWER(p.full_name) LIKE LOWER(?) OR LOWER(COALESCE(p.social_name,'')) LIKE LOWER(?) OR LOWER(s.registration_number) LIKE LOWER(?))";term=f"%{q}%";params.extend([term,term,term])
    sql+=" ORDER BY p.full_name LIMIT 50"
    return {"items":request.state.store.fetch_all(sql,params)}


@router.post("/canteen/quote", operation_id="quote_canteen_sale")
def quote_canteen_sale(data: CanteenQuoteInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user)
    with request.state.store.transaction() as conn:
        location=conn.execute("SELECT * FROM canteen_locations WHERE tenant_id=? AND id=? AND state='active'",(tid,data.canteen_location_id)).fetchone()
        if not location:raise DomainError("CANTEEN_LOCATION_NOT_FOUND","Cantina ativa não localizada.",404)
        student=conn.execute("SELECT id FROM students WHERE tenant_id=? AND id=? AND state='active'",(tid,data.student_id)).fetchone()
        if not student:raise DomainError("STUDENT_NOT_FOUND","Aluno não localizado.",404)
        tzrow=conn.execute("SELECT u.timezone FROM enrollments e JOIN units u ON u.id=e.unit_id WHERE e.tenant_id=? AND e.student_id=? AND e.state='active' ORDER BY e.created_at DESC LIMIT 1",(tid,data.student_id)).fetchone()
        try:local_now=datetime.now(UTC).astimezone(ZoneInfo(str(tzrow["timezone"] if tzrow else "America/Bahia")))
        except Exception:local_now=datetime.now(UTC)
        today=local_now.date();policy=conn.execute("SELECT * FROM student_food_policies WHERE tenant_id=? AND student_id=? AND state='active'",(tid,data.student_id)).fetchone();wallet=conn.execute("SELECT * FROM student_wallets WHERE tenant_id=? AND student_id=? AND state='active'",(tid,data.student_id)).fetchone()
        blocked_products=set(json.loads(policy["blocked_product_ids_json"] or "[]")) if policy else set();blocked_allergens={str(x).strip().lower() for x in json.loads(policy["blocked_allergens_json"] or "[]")} if policy else set();lines=[];total=Decimal("0")
        for requested in data.items:
            product=conn.execute("SELECT * FROM products WHERE tenant_id=? AND id=? AND state='active'",(tid,requested.product_id)).fetchone()
            if not product:raise DomainError("PRODUCT_NOT_FOUND","Produto não localizado.",404)
            if requested.product_id in blocked_products:raise DomainError("CANTEEN_PRODUCT_BLOCKED",f"Produto {product['name']} está bloqueado para o aluno.",409)
            allergens={str(x).strip().lower() for x in json.loads(product["allergen_json"] or "[]")};intersection=sorted(allergens&blocked_allergens)
            if intersection:raise DomainError("CANTEEN_ALLERGEN_BLOCKED",f"Produto {product['name']} contém alergênico/restrição bloqueada: {', '.join(intersection)}.",409)
            menu=conn.execute("SELECT cmi.price_override FROM canteen_menu_items cmi JOIN canteen_menus cm ON cm.id=cmi.canteen_menu_id WHERE cmi.tenant_id=? AND cmi.product_id=? AND cmi.state='active' AND cm.canteen_location_id=? AND cm.state='active' AND (cm.starts_on IS NULL OR cm.starts_on<=?) AND (cm.ends_on IS NULL OR cm.ends_on>=?) ORDER BY cm.starts_on DESC,cm.created_at DESC LIMIT 1",(tid,requested.product_id,data.canteen_location_id,today.isoformat(),today.isoformat())).fetchone()
            if not menu:raise DomainError("CANTEEN_PRODUCT_NOT_ON_MENU",f"Produto {product['name']} não está disponível no cardápio ativo desta cantina.",409)
            balance=conn.execute("SELECT quantity,reserved FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",(tid,requested.product_id)).fetchone();available=money(balance["quantity"] if balance else 0)-money(balance["reserved"] if balance else 0)
            if available<requested.quantity:raise DomainError("INSUFFICIENT_STOCK",f"Estoque insuficiente para {product['name']}.",409)
            unit=money(menu["price_override"] if menu["price_override"] is not None else product["sale_price"]);line=(unit*requested.quantity).quantize(Decimal("0.01"));total+=line;lines.append({"product_id":requested.product_id,"name":product["name"],"quantity":str(requested.quantity),"unit_price":money_str(unit),"total":money_str(line)})
        if policy:
            current=local_now.strftime("%H:%M")
            if policy["purchase_start_time"] and current<str(policy["purchase_start_time"]):raise DomainError("CANTEEN_PURCHASE_TIME_BLOCKED","Compra fora do horário permitido para o aluno.",409)
            if policy["purchase_end_time"] and current>str(policy["purchase_end_time"]):raise DomainError("CANTEEN_PURCHASE_TIME_BLOCKED","Compra fora do horário permitido para o aluno.",409)
        week_start=today-timedelta(days=today.weekday())
        def spent_since(start:str):
            row=conn.execute("SELECT COALESCE(SUM(s.total_amount - COALESCE((SELECT SUM(sr.total_amount) FROM sale_returns sr WHERE sr.tenant_id=s.tenant_id AND sr.sale_id=s.id AND sr.state='completed'),0)),0) AS total FROM sales s WHERE s.tenant_id=? AND s.student_id=? AND s.channel='canteen' AND s.state IN ('completed','partially_returned') AND s.created_at>=?",(tid,data.student_id,start)).fetchone();return money(row["total"] if row else 0)
        daily_limit=money(policy["daily_limit"]) if policy and policy["daily_limit"] is not None else (money(wallet["daily_limit"]) if wallet and wallet["daily_limit"] is not None else None);weekly_limit=money(policy["weekly_limit"]) if policy and policy["weekly_limit"] is not None else (money(wallet["weekly_limit"]) if wallet and wallet["weekly_limit"] is not None else None)
        daily_spent=spent_since(f"{today.isoformat()}T00:00:00");weekly_spent=spent_since(f"{week_start.isoformat()}T00:00:00")
        if daily_limit is not None and daily_spent+total>daily_limit:raise DomainError("CANTEEN_DAILY_LIMIT_EXCEEDED","Compra excede o limite diário configurado para o aluno.",409)
        if weekly_limit is not None and weekly_spent+total>weekly_limit:raise DomainError("CANTEEN_WEEKLY_LIMIT_EXCEEDED","Compra excede o limite semanal configurado para o aluno.",409)
        subsidies=conn.execute("SELECT * FROM canteen_subsidies WHERE tenant_id=? AND student_id=? AND state='active' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?)",(tid,data.student_id,today.isoformat(),today.isoformat())).fetchall();benefits=[]
        for subsidy in subsidies:
            if subsidy["subsidy_type"]=="free_meal":benefit=total
            elif subsidy["subsidy_type"]=="fixed":benefit=money(subsidy["amount"] or 0)
            elif subsidy["subsidy_type"]=="percentage":benefit=(total*money(subsidy["percentage"] or 0)/Decimal("100")).quantize(Decimal("0.01"))
            else:benefit=Decimal("0")
            benefits.append(min(benefit,total))
        subsidy_amount=max(benefits,default=Decimal("0")).quantize(Decimal("0.01"));due=(total-subsidy_amount).quantize(Decimal("0.01"))
        return {"canteen_location_id":data.canteen_location_id,"student_id":data.student_id,"lines":lines,"total_amount":money_str(total),"subsidy_amount":money_str(subsidy_amount),"customer_due":money_str(due),"wallet_balance":money_str(wallet["balance"]) if wallet else None,"daily_spent":money_str(daily_spent),"daily_limit":money_str(daily_limit) if daily_limit is not None else None,"weekly_spent":money_str(weekly_spent),"weekly_limit":money_str(weekly_limit) if weekly_limit is not None else None}


@router.get("/canteen/locations", operation_id="list_canteen_locations")
def list_locations(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, CANTEEN_ADMIN | {"guardian", "student"})
    return {"items": request.state.store.fetch_all("SELECT * FROM canteen_locations WHERE tenant_id=? AND state!='archived' ORDER BY name", (tenant(user),))}


@router.post("/canteen/locations", status_code=201, operation_id="create_canteen_location")
def create_location(data: CanteenLocationInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, CANTEEN_ADMIN); tid=tenant(user); now=iso_now()
    if data.unit_id:
        row_or_404(request,"SELECT id FROM units WHERE tenant_id=? AND id=? AND state='active'",(tid,data.unit_id),"UNIT_NOT_FOUND","Unidade não localizada.")
    location_id=uuid7()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO canteen_locations(id,tenant_id,unit_id,code,name,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(location_id,tid,data.unit_id,data.code,data.name,"active",now,now))
        result={"id":location_id,"unit_id":data.unit_id,"code":data.code,"name":data.name,"state":"active"}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="canteen_location",aggregate_id=location_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.get("/canteen/menus", operation_id="list_canteen_menus")
def list_menus(request: Request, location_id: str | None = None, active_on: date | None = None, user: CurrentUser = Depends(current_user)):
    require(user, CANTEEN_ADMIN | {"guardian", "student"});tid=tenant(user)
    sql="SELECT * FROM canteen_menus WHERE tenant_id=?";params:list[object]=[tid]
    if location_id: sql+=" AND canteen_location_id=?";params.append(location_id)
    if active_on:
        sql+=" AND state='active' AND (starts_on IS NULL OR starts_on<=?) AND (ends_on IS NULL OR ends_on>=?)";params.extend([str(active_on),str(active_on)])
    sql+=" ORDER BY starts_on DESC,created_at DESC"
    menus=request.state.store.fetch_all(sql,params)
    for menu in menus:
        menu["items"]=request.state.store.fetch_all("SELECT cmi.*,p.name AS product_name,p.allergen_json,p.restriction_json,p.sale_price FROM canteen_menu_items cmi JOIN products p ON p.id=cmi.product_id WHERE cmi.tenant_id=? AND cmi.canteen_menu_id=? AND cmi.state='active' ORDER BY p.name",(tid,menu["id"]))
    return {"items":menus}


@router.post("/canteen/menus", status_code=201, operation_id="create_canteen_menu")
def create_menu(data: MenuInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);now=iso_now()
    row_or_404(request,"SELECT id FROM canteen_locations WHERE tenant_id=? AND id=? AND state='active'",(tid,data.canteen_location_id),"CANTEEN_LOCATION_NOT_FOUND","Cantina não localizada.")
    menu_id=uuid7()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO canteen_menus(id,tenant_id,canteen_location_id,name,starts_on,ends_on,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(menu_id,tid,data.canteen_location_id,data.name,str(data.starts_on) if data.starts_on else None,str(data.ends_on) if data.ends_on else None,"draft",1,now,now))
        result={"id":menu_id,"canteen_location_id":data.canteen_location_id,"name":data.name,"state":"draft","version":1}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="canteen_menu",aggregate_id=menu_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.post("/canteen/menus/{menu_id}/items", status_code=201, operation_id="add_canteen_menu_item")
def add_menu_item(menu_id: str, data: MenuItemInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);now=iso_now()
    row_or_404(request,"SELECT id FROM canteen_menus WHERE tenant_id=? AND id=?",(tid,menu_id),"CANTEEN_MENU_NOT_FOUND","Cardápio não localizado.")
    row_or_404(request,"SELECT id FROM products WHERE tenant_id=? AND id=? AND state='active'",(tid,data.product_id),"PRODUCT_NOT_FOUND","Produto não localizado.")
    item_id=uuid7()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO canteen_menu_items(id,tenant_id,canteen_menu_id,product_id,price_override,available_from,available_until,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(item_id,tid,menu_id,data.product_id,money_str(data.price_override) if data.price_override is not None else None,data.available_from,data.available_until,"active",now))
        result={"id":item_id,"menu_id":menu_id,"product_id":data.product_id,"price_override":money_str(data.price_override) if data.price_override is not None else None}
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="add_item",aggregate_type="canteen_menu",aggregate_id=menu_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.post("/canteen/menus/{menu_id}/state", operation_id="change_canteen_menu_state")
def change_menu_state(menu_id: str, data: MenuStateInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM canteen_menus WHERE tenant_id=? AND id=?",(tid,menu_id)).fetchone()
        if not raw: raise DomainError("CANTEEN_MENU_NOT_FOUND","Cardápio não localizado.",404)
        version=raw["version"]+1;conn.execute("UPDATE canteen_menus SET state=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(data.state,version,now,tid,menu_id))
        result={"id":menu_id,"state":data.state,"version":version};add_audit(conn,tenant_id=tid,actor_id=user.id,action="state",aggregate_type="canteen_menu",aggregate_id=menu_id,correlation_id=request.state.correlation_id,before={"state":raw["state"]},after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="CanteenMenuStateChanged",aggregate_type="canteen_menu",aggregate_id=menu_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/canteen/wallets", operation_id="list_student_wallets")
def list_wallets(request: Request, student_id: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);sql="SELECT sw.*,p.full_name AS student_name FROM student_wallets sw JOIN students s ON s.id=sw.student_id JOIN people p ON p.id=s.person_id WHERE sw.tenant_id=?";params:list[object]=[tid]
    if student_id:sql+=" AND sw.student_id=?";params.append(student_id)
    sql+=" ORDER BY p.full_name"
    return {"items":request.state.store.fetch_all(sql,params)}


@router.post("/canteen/wallets", status_code=201, operation_id="create_student_wallet")
def create_wallet(data: WalletInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);now=iso_now();row_or_404(request,"SELECT id FROM students WHERE tenant_id=? AND id=? AND state='active'",(tid,data.student_id),"STUDENT_NOT_FOUND","Aluno não localizado.")
    existing=_wallet_row(request,tid,data.student_id)
    if existing:return _wallet_payload(request,existing)
    wallet_id=uuid7()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO student_wallets(id,tenant_id,student_id,balance,daily_limit,weekly_limit,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(wallet_id,tid,data.student_id,"0.00",money_str(data.daily_limit) if data.daily_limit is not None else None,money_str(data.weekly_limit) if data.weekly_limit is not None else None,"active",1,now,now))
        result={"id":wallet_id,"student_id":data.student_id,"balance":"0.00","daily_limit":money_str(data.daily_limit) if data.daily_limit is not None else None,"weekly_limit":money_str(data.weekly_limit) if data.weekly_limit is not None else None,"state":"active","version":1};add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="student_wallet",aggregate_id=wallet_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.get("/canteen/wallets/me", operation_id="get_my_canteen_wallets")
def my_wallets(request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user)
    if "student" in user.roles:
        student=student_for_user(request,user);ids=[student["id"]]
    elif "guardian" in user.roles:
        from app.modules.portals.access import guardian_for_user
        guardian=guardian_for_user(request,user);ids=[r["student_id"] for r in request.state.store.fetch_all("SELECT student_id FROM guardian_students WHERE tenant_id=? AND guardian_id=?",(tid,guardian["id"]))]
    else:
        raise DomainError("ROLE_FORBIDDEN","Recurso disponível para aluno ou responsável.",403)
    items=[]
    for student_id in ids:
        student=request.state.store.fetch_one("SELECT s.id,p.full_name FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.id=?",(tid,student_id))
        wallet=_wallet_row(request,tid,student_id)
        items.append({"student":student,"wallet":_wallet_payload(request,wallet) if wallet else None})
    return {"items":items}


@router.patch("/canteen/wallets/{wallet_id}", operation_id="update_student_wallet_limits")
def update_wallet(wallet_id: str, data: WalletLimitInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM student_wallets WHERE tenant_id=? AND id=?",(tid,wallet_id)).fetchone()
        if not raw:raise DomainError("WALLET_NOT_FOUND","Carteira não localizada.",404)
        if raw["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente da carteira.",409)
        version=raw["version"]+1;conn.execute("UPDATE student_wallets SET daily_limit=?,weekly_limit=?,state=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(money_str(data.daily_limit) if data.daily_limit is not None else None,money_str(data.weekly_limit) if data.weekly_limit is not None else None,data.state,version,now,tid,wallet_id));result={"id":wallet_id,"daily_limit":money_str(data.daily_limit) if data.daily_limit is not None else None,"weekly_limit":money_str(data.weekly_limit) if data.weekly_limit is not None else None,"state":data.state,"version":version};add_audit(conn,tenant_id=tid,actor_id=user.id,action="update",aggregate_type="student_wallet",aggregate_id=wallet_id,correlation_id=request.state.correlation_id,before=dict(raw),after=result)
    return result


@router.post("/canteen/wallets/{wallet_id}/credits", status_code=201, operation_id="credit_student_wallet")
def credit_wallet(wallet_id: str, data: WalletCreditInput, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN | FINANCE_ROLES);tid=tenant(user);scope=f"wallet-credit:{tid}:{wallet_id}";body=data.model_dump(mode="json");now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        raw=conn.execute("SELECT * FROM student_wallets WHERE tenant_id=? AND id=? AND state='active'",(tid,wallet_id)).fetchone()
        if not raw:raise DomainError("WALLET_NOT_FOUND","Carteira ativa não localizada.",404)
        before=money(raw["balance"]);after=before+money(data.amount);tx_id=uuid7();conn.execute("UPDATE student_wallets SET balance=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(money_str(after),now,tid,wallet_id));conn.execute("INSERT INTO wallet_transactions(id,tenant_id,wallet_id,transaction_type,amount,balance_before,balance_after,reference_type,reference_id,reason,created_by,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(tx_id,tid,wallet_id,"credit",money_str(data.amount),money_str(before),money_str(after),data.method,data.external_reference,data.reason,user.id,idempotency_key,now));result={"id":tx_id,"wallet_id":wallet_id,"amount":money_str(data.amount),"balance_before":money_str(before),"balance_after":money_str(after),"state":"confirmed"};add_audit(conn,tenant_id=tid,actor_id=user.id,action="credit",aggregate_type="student_wallet",aggregate_id=wallet_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="StudentWalletCredited",aggregate_type="student_wallet",aggregate_id=wallet_id,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result


@router.get("/canteen/students/{student_id}/policy", operation_id="get_student_food_policy")
def get_food_policy(student_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user)
    if not (user.roles & CANTEEN_ADMIN):
        assert_student_access(request,user,student_id)
    policy=request.state.store.fetch_one("SELECT * FROM student_food_policies WHERE tenant_id=? AND student_id=?",(tid,student_id))
    if not policy:return {"student_id":student_id,"blocked_allergens":[],"blocked_product_ids":[],"state":"not_configured"}
    policy["blocked_allergens"]=json.loads(policy.pop("blocked_allergens_json") or "[]");policy["blocked_product_ids"]=json.loads(policy.pop("blocked_product_ids_json") or "[]")
    return policy


@router.put("/canteen/students/{student_id}/policy", operation_id="set_student_food_policy")
def set_food_policy(student_id: str, data: FoodPolicyInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant(user)
    if "guardian" in user.roles:
        if not guardian_can_access_student(request,user,student_id):raise DomainError("STUDENT_ACCESS_DENIED","Aluno não pertence ao responsável.",403)
    else:require(user,CANTEEN_ADMIN)
    row_or_404(request,"SELECT id FROM students WHERE tenant_id=? AND id=?",(tid,student_id),"STUDENT_NOT_FOUND","Aluno não localizado.")
    for product_id in set(data.blocked_product_ids):row_or_404(request,"SELECT id FROM products WHERE tenant_id=? AND id=?",(tid,product_id),"PRODUCT_NOT_FOUND","Produto bloqueado não localizado.")
    now=iso_now()
    with request.state.store.transaction() as conn:
        current=conn.execute("SELECT * FROM student_food_policies WHERE tenant_id=? AND student_id=?",(tid,student_id)).fetchone()
        if current:
            version=current["version"]+1;conn.execute("UPDATE student_food_policies SET blocked_allergens_json=?,blocked_product_ids_json=?,daily_limit=?,weekly_limit=?,purchase_start_time=?,purchase_end_time=?,notes=?,state='active',version=?,updated_at=? WHERE tenant_id=? AND student_id=?",(dumps(sorted(set(data.blocked_allergens))),dumps(sorted(set(data.blocked_product_ids))),money_str(data.daily_limit) if data.daily_limit is not None else None,money_str(data.weekly_limit) if data.weekly_limit is not None else None,data.purchase_start_time,data.purchase_end_time,data.notes,version,now,tid,student_id));policy_id=current["id"]
        else:
            version=1;policy_id=uuid7();conn.execute("INSERT INTO student_food_policies(id,tenant_id,student_id,blocked_allergens_json,blocked_product_ids_json,daily_limit,weekly_limit,purchase_start_time,purchase_end_time,notes,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(policy_id,tid,student_id,dumps(sorted(set(data.blocked_allergens))),dumps(sorted(set(data.blocked_product_ids))),money_str(data.daily_limit) if data.daily_limit is not None else None,money_str(data.weekly_limit) if data.weekly_limit is not None else None,data.purchase_start_time,data.purchase_end_time,data.notes,"active",1,user.id,now,now))
        result={"id":policy_id,"student_id":student_id,"blocked_allergens":sorted(set(data.blocked_allergens)),"blocked_product_ids":sorted(set(data.blocked_product_ids)),"daily_limit":money_str(data.daily_limit) if data.daily_limit is not None else None,"weekly_limit":money_str(data.weekly_limit) if data.weekly_limit is not None else None,"state":"active","version":version};add_audit(conn,tenant_id=tid,actor_id=user.id,action="set_policy",aggregate_type="student_food_policy",aggregate_id=policy_id,correlation_id=request.state.correlation_id,after=result)
    return result


@router.get("/canteen/subsidies", operation_id="list_canteen_subsidies")
def list_subsidies(request: Request, student_id: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN | FINANCE_ROLES);tid=tenant(user);sql="SELECT * FROM canteen_subsidies WHERE tenant_id=?";params:list[object]=[tid]
    if student_id:sql+=" AND student_id=?";params.append(student_id)
    sql+=" ORDER BY valid_from DESC,created_at DESC";return {"items":request.state.store.fetch_all(sql,params)}


@router.post("/canteen/subsidies", status_code=201, operation_id="create_canteen_subsidy")
def create_subsidy(data: SubsidyInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user,CANTEEN_ADMIN | FINANCE_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM students WHERE tenant_id=? AND id=?",(tid,data.student_id),"STUDENT_NOT_FOUND","Aluno não localizado.");sid=uuid7();now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO canteen_subsidies(id,tenant_id,student_id,subsidy_type,amount,percentage,valid_from,valid_until,reason,state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,tid,data.student_id,data.subsidy_type,money_str(data.amount) if data.amount is not None else None,money_str(data.percentage) if data.percentage is not None else None,str(data.valid_from),str(data.valid_until) if data.valid_until else None,data.reason,"active",user.id,now,now));result={"id":sid,"student_id":data.student_id,"subsidy_type":data.subsidy_type,"amount":money_str(data.amount) if data.amount is not None else None,"percentage":money_str(data.percentage) if data.percentage is not None else None,"state":"active"};add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="canteen_subsidy",aggregate_id=sid,correlation_id=request.state.correlation_id,after=result,reason=data.reason)
    return result
