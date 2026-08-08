from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, EmailStr, Field

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import AuthService, CurrentUser, current_user, hash_password, require_roles

router = APIRouter(tags=["tenancy"])

class BootstrapInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=1024)

class TenantCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")
    legal_name: str = Field(min_length=3, max_length=300)
    trade_name: str = Field(min_length=2, max_length=200)
    hostname: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{2,252}$")
    owner_email: EmailStr
    owner_password: str = Field(min_length=10, max_length=1024)

class SupportSessionInput(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    ticket: str | None = Field(default=None, max_length=200)
    assumed_user_id: str | None = None
    minutes: int = Field(default=30, ge=5, le=120)

@router.post("/platform/bootstrap", operation_id="platform_bootstrap")
def bootstrap(data: BootstrapInput, request: Request,
              bootstrap_token: Annotated[str | None, Header(alias="X-Bootstrap-Token")] = None):
    if request.state.host_resolution.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota disponível somente no domínio global.", 404)
    expected = request.app.state.settings.bootstrap_token
    if not expected or bootstrap_token != expected:
        raise DomainError("INVALID_BOOTSTRAP_TOKEN", "Token de bootstrap inválido.", 403)
    existing = request.state.store.fetch_one("SELECT id,email,roles_json FROM users WHERE tenant_id IS NULL LIMIT 1")
    if existing:
        return {"status": "already_bootstrapped", "admin": {"id": existing["id"], "email": existing["email"], "roles": json.loads(existing["roles_json"])}}
    auth=AuthService(request.state.store,request.app.state.settings,tenant_id=None,plane="platform")
    admin=auth.create_user(str(data.email),data.password,["platform_super_admin","platform_admin"])
    return {"status":"bootstrapped","admin":admin}

@router.get("/platform/tenants", operation_id="list_platform_tenants")
def list_tenants(request: Request, user: CurrentUser = Depends(require_roles("platform_super_admin","platform_admin"))):
    if user.plane!="platform": raise DomainError("PLATFORM_ROUTE_REQUIRED","Rota global indisponível neste domínio.",404)
    rows=request.state.store.fetch_all("SELECT id,code,legal_name,trade_name,status,created_at,updated_at,version FROM platform_tenants ORDER BY trade_name")
    for row in rows:
        row["domains"]=request.state.store.fetch_all("SELECT id,hostname,surface,status,is_canonical,created_at FROM tenant_domains WHERE tenant_id=? ORDER BY hostname",(row["id"],))
    return {"items":rows}

@router.post("/platform/tenants", operation_id="create_platform_tenant", status_code=201)
def create_tenant(data: TenantCreate, request: Request,
                  user: CurrentUser = Depends(require_roles("platform_super_admin","platform_admin"))):
    if user.plane!="platform": raise DomainError("PLATFORM_ROUTE_REQUIRED","Rota global indisponível neste domínio.",404)
    tenant=request.app.state.data_router.provision_tenant(code=data.code,legal_name=data.legal_name,trade_name=data.trade_name,hostname=data.hostname.lower())
    store=request.app.state.data_router.tenant_store(tenant["id"])
    auth=AuthService(store,request.app.state.settings,tenant_id=tenant["id"],plane="tenant")
    existing=store.fetch_one("SELECT id,email,roles_json FROM users WHERE tenant_id=? AND email=?",(tenant["id"],str(data.owner_email).lower()))
    owner={"id":existing["id"],"email":existing["email"],"roles":json.loads(existing["roles_json"])} if existing else auth.create_user(str(data.owner_email),data.owner_password,["tenant_owner","institution_director"])
    with request.state.store.transaction() as conn:
        result={"id":tenant["id"],"code":tenant["code"],"legal_name":tenant["legal_name"],"trade_name":tenant["trade_name"],"status":tenant["status"],"hostname":data.hostname.lower(),"owner":owner}
        add_audit(conn,tenant_id=tenant["id"],actor_id=user.id,action="provision",aggregate_type="tenant",aggregate_id=tenant["id"],correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tenant["id"],event_type="TenantProvisioned",aggregate_type="tenant",aggregate_id=tenant["id"],payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/tenant/context", operation_id="get_tenant_context")
def tenant_context(request: Request, user: CurrentUser = Depends(current_user)):
    if user.plane!="tenant" or not user.tenant_id: raise DomainError("TENANT_ROUTE_REQUIRED","Rota tenant indisponível neste domínio.",404)
    row=request.app.state.data_router.control.fetch_one("SELECT id,code,legal_name,trade_name,status,created_at FROM platform_tenants WHERE id=?",(user.tenant_id,))
    return {**row,"hostname":request.state.host_resolution.hostname,"surface":request.state.host_resolution.surface,"user":{"id":user.id,"email":user.email,"roles":user.roles}}

@router.post("/platform/tenants/{tenant_id}/support-sessions",operation_id="create_support_session",status_code=201)
def support_session(tenant_id:str,data:SupportSessionInput,request:Request,user:CurrentUser=Depends(require_roles("platform_super_admin","platform_admin"))):
    if user.plane!="platform":raise DomainError("PLATFORM_ROUTE_REQUIRED","Rota global indisponível neste domínio.",404)
    tenant=request.state.store.fetch_one("SELECT id,status FROM platform_tenants WHERE id=?",(tenant_id,))
    if not tenant:raise DomainError("TENANT_NOT_FOUND","Tenant não localizado.",404)
    now=datetime.now(UTC);session_id=uuid7();expires=now+timedelta(minutes=data.minutes)
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO support_sessions(id,platform_admin_id,tenant_id,assumed_user_id,reason,ticket,ip,device,started_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(session_id,user.id,tenant_id,data.assumed_user_id,data.reason,data.ticket,request.client.host if request.client else None,request.headers.get("user-agent"),now.isoformat(),expires.isoformat()))
        result={"id":session_id,"tenant_id":tenant_id,"platform_admin_id":user.id,"assumed_user_id":data.assumed_user_id,"reason":data.reason,"ticket":data.ticket,"started_at":now.isoformat(),"expires_at":expires.isoformat(),"banner_required":True}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="support_session_started",aggregate_type="support_session",aggregate_id=session_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason)
    return result


@router.get("/platform/status", operation_id="get_platform_operational_status")
def platform_status(request: Request, user: CurrentUser = Depends(require_roles("platform_super_admin","platform_admin"))):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    store = request.state.store
    tenants = store.fetch_all("SELECT id,status FROM platform_tenants ORDER BY created_at")
    domain_count = int(store.scalar("SELECT COUNT(*) AS n FROM tenant_domains") or 0)
    pending_outbox = int(store.scalar("SELECT COUNT(*) AS n FROM outbox_events WHERE published_at IS NULL") or 0)
    active_support = int(store.scalar("SELECT COUNT(*) AS n FROM support_sessions WHERE ended_at IS NULL AND expires_at>?", (iso_now(),)) or 0)
    builds = {"queued": 0, "building": 0, "failed": 0, "completed": 0}
    for tenant in tenants:
        tenant_store = request.app.state.data_router.tenant_store(tenant["id"])
        for state in list(builds):
            builds[state] += int(tenant_store.scalar("SELECT COUNT(*) AS n FROM app_build_requests WHERE status=?", (state,)) or 0)
    return {
        "status": "operational",
        "tenants": {
            "total": len(tenants),
            "active": sum(1 for item in tenants if item["status"] == "active"),
            "degraded": sum(1 for item in tenants if item["status"] == "degraded"),
            "suspended": sum(1 for item in tenants if item["status"] == "suspended"),
        },
        "domains": domain_count,
        "pending_control_outbox": pending_outbox,
        "active_support_sessions": active_support,
        "builds": builds,
        "generated_at": iso_now(),
    }


@router.get("/platform/audit", operation_id="list_platform_audit")
def platform_audit(request: Request, tenant_id: str | None = None, limit: int = 100, user: CurrentUser = Depends(require_roles("platform_super_admin","platform_admin"))):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    limit = min(max(limit, 1), 500)
    sql = "SELECT * FROM audit_log"
    params: list[object] = []
    if tenant_id:
        sql += " WHERE tenant_id=?"; params.append(tenant_id)
    sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
    rows = request.state.store.fetch_all(sql, params)
    for row in rows:
        for key in ("before_json", "after_json"):
            raw = row.pop(key, None)
            if raw:
                try: row[key.removesuffix("_json")] = json.loads(raw)
                except (TypeError, json.JSONDecodeError): row[key.removesuffix("_json")] = None
    return {"items": rows, "limit": limit}


@router.get("/platform/support-sessions", operation_id="list_platform_support_sessions")
def list_support_sessions(request: Request, tenant_id: str | None = None, active_only: bool = False, user: CurrentUser = Depends(require_roles("platform_super_admin","platform_admin"))):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    sql = "SELECT * FROM support_sessions WHERE 1=1"; params: list[object] = []
    if tenant_id:
        sql += " AND tenant_id=?"; params.append(tenant_id)
    if active_only:
        sql += " AND ended_at IS NULL AND expires_at>?"; params.append(iso_now())
    sql += " ORDER BY started_at DESC LIMIT 500"
    return {"items": request.state.store.fetch_all(sql, params)}
