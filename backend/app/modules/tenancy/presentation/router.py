from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import AuthService, CurrentUser, current_user, require_roles
from app.shared.tenant_quotas import (
    DEFAULT_TENANT_QUOTAS,
    TENANT_QUOTA_ENFORCEMENT,
    configured_tenant_quotas,
)

router = APIRouter(tags=["tenancy"])
logger = logging.getLogger("pige360.platform.status")


class BootstrapInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=1024)


class TenantCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")
    legal_name: str = Field(min_length=3, max_length=300)
    trade_name: str = Field(min_length=2, max_length=200)
    hostname: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9.-]{2,252}$")
    owner_email: EmailStr
    owner_password: str = Field(min_length=10, max_length=1024)


class SupportSessionInput(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    ticket: str | None = Field(default=None, max_length=200)
    assumed_user_id: str | None = None
    minutes: int = Field(default=30, ge=5, le=120)


class TenantLifecycleInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


class SupportSessionEndInput(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class TenantQuotaValues(BaseModel):
    """Limites administrativos conhecidos; campos não reconhecidos são rejeitados.

    O PATCH lógico preserva chaves legadas já persistidas em ``quotas_json`` para
    que a evolução do contrato não apague configuração de versões anteriores.
    """

    model_config = ConfigDict(extra="forbid")

    max_users: int | None = Field(default=None, ge=1, le=1_000_000)
    max_students: int | None = Field(default=None, ge=0, le=10_000_000)
    storage_bytes: int | None = Field(default=None, ge=1_048_576, le=10_000_000_000_000_000)
    api_requests_per_minute: int | None = Field(default=None, ge=1, le=1_000_000)
    max_integrations: int | None = Field(default=None, ge=0, le=10_000)
    max_concurrent_builds: int | None = Field(default=None, ge=1, le=64)
    max_custom_domains: int | None = Field(default=None, ge=0, le=1_000)

    @model_validator(mode="after")
    def require_one_value(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Informe ao menos uma quota para atualizar")
        return self


class TenantQuotasInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)
    quotas: TenantQuotaValues


def _require_platform(user: CurrentUser) -> None:
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)


def _json_object(raw: object) -> dict[str, object]:
    return configured_tenant_quotas(raw)


def _canonical_tenant_hostname(code: str, request: Request) -> str:
    settings = request.app.state.settings
    normalized = code.strip().lower()
    if normalized in set(settings.tenant_reserved_slugs):
        raise DomainError(
            "TENANT_SLUG_RESERVED",
            f"O identificador '{normalized}' é reservado pela plataforma PIGE360.",
            409,
            "Identificador de tenant reservado",
        )
    return f"{normalized}.{settings.tenant_default_base_domain}".lower().rstrip(".")


def _provision_hostname(data: TenantCreate, request: Request) -> str:
    canonical = _canonical_tenant_hostname(data.code, request)
    requested = data.hostname.strip().lower().rstrip(".") if data.hostname else canonical
    settings = request.app.state.settings

    # Em produção o primeiro domínio nasce sempre no wildcard canônico. Domínio
    # próprio exige prova de posse + TLS e deve ser associado em fluxo separado,
    # evitando que um hostname arbitrário seja ativado no ato do provisionamento.
    if settings.environment in {"production", "staging"} and requested != canonical:
        raise DomainError(
            "CUSTOM_DOMAIN_REQUIRES_VERIFICATION",
            f"Na criação use o domínio canônico '{canonical}'. Domínios próprios são vinculados após verificação de posse e TLS.",
            409,
            "Domínio personalizado requer verificação",
        )
    return requested


@router.post("/platform/bootstrap", operation_id="platform_bootstrap")
def bootstrap(
    data: BootstrapInput,
    request: Request,
    bootstrap_token: Annotated[str | None, Header(alias="X-Bootstrap-Token")] = None,
):
    if request.state.host_resolution.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota disponível somente no domínio global.", 404)
    expected = request.app.state.settings.bootstrap_token
    if not expected or bootstrap_token != expected:
        raise DomainError("INVALID_BOOTSTRAP_TOKEN", "Token de bootstrap inválido.", 403)
    existing = request.state.store.fetch_one("SELECT id,email,roles_json FROM users WHERE tenant_id IS NULL LIMIT 1")
    if existing:
        return {
            "status": "already_bootstrapped",
            "admin": {"id": existing["id"], "email": existing["email"], "roles": json.loads(existing["roles_json"])},
        }
    auth = AuthService(request.state.store, request.app.state.settings, tenant_id=None, plane="platform")
    admin = auth.create_user(str(data.email), data.password, ["platform_super_admin", "platform_admin"])
    return {"status": "bootstrapped", "admin": admin}


@router.get("/platform/tenants", operation_id="list_platform_tenants")
def list_tenants(request: Request, user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin"))):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    rows = request.state.store.fetch_all(
        "SELECT id,code,legal_name,trade_name,status,created_at,updated_at,version FROM platform_tenants ORDER BY trade_name"
    )
    for row in rows:
        row["domains"] = request.state.store.fetch_all(
            "SELECT id,hostname,surface,status,is_canonical,created_at FROM tenant_domains WHERE tenant_id=? ORDER BY hostname",
            (row["id"],),
        )
        row["canonical_hostname"] = next(
            (domain["hostname"] for domain in row["domains"] if bool(domain.get("is_canonical"))),
            f"{row['code']}.{request.app.state.settings.tenant_default_base_domain}",
        )
    return {"items": rows}


@router.post("/platform/tenants", operation_id="create_platform_tenant", status_code=201)
def create_tenant(
    data: TenantCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)

    hostname = _provision_hostname(data, request)
    tenant = request.app.state.data_router.provision_tenant(
        code=data.code,
        legal_name=data.legal_name,
        trade_name=data.trade_name,
        hostname=hostname,
    )
    store = request.app.state.data_router.tenant_store(tenant["id"])
    auth = AuthService(store, request.app.state.settings, tenant_id=tenant["id"], plane="tenant")
    existing = store.fetch_one(
        "SELECT id,email,roles_json FROM users WHERE tenant_id=? AND email=?",
        (tenant["id"], str(data.owner_email).lower()),
    )
    owner = (
        {"id": existing["id"], "email": existing["email"], "roles": json.loads(existing["roles_json"])}
        if existing
        else auth.create_user(
            str(data.owner_email), data.owner_password, ["tenant_owner", "institution_director"]
        )
    )
    with request.state.store.transaction() as conn:
        result = {
            "id": tenant["id"],
            "code": tenant["code"],
            "legal_name": tenant["legal_name"],
            "trade_name": tenant["trade_name"],
            "status": tenant["status"],
            "hostname": hostname,
            "canonical_hostname": hostname,
            "domain_mode": "wildcard" if hostname.endswith(f".{request.app.state.settings.tenant_default_base_domain}") else "explicit",
            "owner": owner,
        }
        add_audit(
            conn,
            tenant_id=tenant["id"],
            actor_id=user.id,
            action="provision",
            aggregate_type="tenant",
            aggregate_id=tenant["id"],
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=tenant["id"],
            event_type="TenantProvisioned",
            aggregate_type="tenant",
            aggregate_id=tenant["id"],
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


def _transition_tenant(
    tenant_id: str,
    target: str,
    data: TenantLifecycleInput,
    request: Request,
    user: CurrentUser,
) -> dict[str, object]:
    _require_platform(user)
    allowed_from = {"suspended"} if target == "active" else {"active", "degraded"}
    event_type = "TenantReactivated" if target == "active" else "TenantSuspended"
    action = "reactivate" if target == "active" else "suspend"
    now = iso_now()
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"tenant-lifecycle:{tenant_id}")
        current = conn.execute(
            "SELECT id,code,status,version,updated_at FROM platform_tenants WHERE id=?",
            (tenant_id,),
        ).fetchone()
        if not current:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        before = dict(current)
        if int(current["version"]) != data.expected_version:
            raise DomainError(
                "TENANT_VERSION_CONFLICT",
                "O tenant foi alterado por outro operador. Atualize a tela antes de tentar novamente.",
                409,
            )
        if str(current["status"]) not in allowed_from:
            raise DomainError(
                "INVALID_TENANT_TRANSITION",
                f"Não é possível executar {action} a partir do status '{current['status']}'.",
                409,
            )
        changed = conn.execute(
            "UPDATE platform_tenants SET status=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND status=?",
            (target, now, tenant_id, data.expected_version, current["status"]),
        ).rowcount
        if changed != 1:
            raise DomainError(
                "TENANT_VERSION_CONFLICT",
                "O tenant foi alterado por outro operador. Atualize a tela antes de tentar novamente.",
                409,
            )
        support_sessions_revoked = 0
        if target == "suspended":
            support_sessions_revoked = conn.execute(
                """UPDATE support_sessions SET ended_at=?
                   WHERE tenant_id=? AND ended_at IS NULL AND expires_at>?""",
                (now, tenant_id, now),
            ).rowcount
        result: dict[str, object] = {
            "id": tenant_id,
            "code": current["code"],
            "status": target,
            "version": data.expected_version + 1,
            "changed_at": now,
            "reason": data.reason,
            "support_sessions_revoked": support_sessions_revoked,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action=action,
            aggregate_type="tenant",
            aggregate_id=tenant_id,
            correlation_id=request.state.correlation_id,
            before=before,
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type=event_type,
            aggregate_type="tenant",
            aggregate_id=tenant_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


@router.post("/platform/tenants/{tenant_id}/suspend", operation_id="suspend_platform_tenant")
def suspend_tenant(
    tenant_id: str,
    data: TenantLifecycleInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    return _transition_tenant(tenant_id, "suspended", data, request, user)


@router.post("/platform/tenants/{tenant_id}/reactivate", operation_id="reactivate_platform_tenant")
def reactivate_tenant(
    tenant_id: str,
    data: TenantLifecycleInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    return _transition_tenant(tenant_id, "active", data, request, user)


@router.get("/platform/tenants/{tenant_id}/quotas", operation_id="get_platform_tenant_quotas")
def get_tenant_quotas(
    tenant_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    row = request.state.store.fetch_one(
        "SELECT id,quotas_json,version,updated_at FROM platform_tenants WHERE id=?",
        (tenant_id,),
    )
    if not row:
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    configured = _json_object(row.get("quotas_json"))
    return {
        "tenant_id": tenant_id,
        "version": row["version"],
        "configured": configured,
        "effective": {**DEFAULT_TENANT_QUOTAS, **configured},
        "enforcement": {key: dict(value) for key, value in TENANT_QUOTA_ENFORCEMENT.items()},
        "updated_at": row["updated_at"],
    }


@router.put("/platform/tenants/{tenant_id}/quotas", operation_id="update_platform_tenant_quotas")
def update_tenant_quotas(
    tenant_id: str,
    data: TenantQuotasInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    now = iso_now()
    with request.state.store.transaction() as conn:
        current = conn.execute(
            "SELECT id,quotas_json,version,updated_at FROM platform_tenants WHERE id=?",
            (tenant_id,),
        ).fetchone()
        if not current:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        if int(current["version"]) != data.expected_version:
            raise DomainError(
                "TENANT_VERSION_CONFLICT",
                "As quotas foram alteradas por outro operador. Atualize a tela antes de tentar novamente.",
                409,
            )
        before = _json_object(current["quotas_json"])
        configured = {**before, **data.quotas.model_dump(exclude_none=True)}
        serialized = json.dumps(configured, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 4096:
            raise DomainError("TENANT_QUOTAS_TOO_LARGE", "A configuração de quotas excede 4 KiB.", 422)
        changed = conn.execute(
            "UPDATE platform_tenants SET quotas_json=?,updated_at=?,version=version+1 WHERE id=? AND version=?",
            (serialized, now, tenant_id, data.expected_version),
        ).rowcount
        if changed != 1:
            raise DomainError(
                "TENANT_VERSION_CONFLICT",
                "As quotas foram alteradas por outro operador. Atualize a tela antes de tentar novamente.",
                409,
            )
        result = {
            "tenant_id": tenant_id,
            "version": data.expected_version + 1,
            "configured": configured,
            "effective": {**DEFAULT_TENANT_QUOTAS, **configured},
            "enforcement": {key: dict(value) for key, value in TENANT_QUOTA_ENFORCEMENT.items()},
            "updated_at": now,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="update_quotas",
            aggregate_type="tenant",
            aggregate_id=tenant_id,
            correlation_id=request.state.correlation_id,
            before={"quotas": before, "version": data.expected_version},
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="TenantQuotasChanged",
            aggregate_type="tenant",
            aggregate_id=tenant_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result


@router.get("/platform/domain-policy", operation_id="get_platform_domain_policy")
def domain_policy(request: Request, user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin"))):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    settings = request.app.state.settings
    return {
        "base_domain": settings.base_domain,
        "tenant_base_domain": settings.tenant_default_base_domain,
        "canonical_pattern": f"{{slug}}.{settings.tenant_default_base_domain}",
        "wildcard": f"*.{settings.tenant_default_base_domain}",
        "dns_per_canonical_tenant_required": False,
        "custom_domains_enabled": settings.tenant_custom_domains_enabled,
        "custom_domains_require_verification": True,
        "reserved_slugs": list(settings.tenant_reserved_slugs),
        "tenant_selector": "hostname_only",
    }


@router.get("/tenant/context", operation_id="get_tenant_context")
def tenant_context(request: Request, user: CurrentUser = Depends(current_user)):
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Rota tenant indisponível neste domínio.", 404)
    row = request.app.state.data_router.control.fetch_one(
        "SELECT id,code,legal_name,trade_name,status,created_at FROM platform_tenants WHERE id=?", (user.tenant_id,)
    )
    return {
        **row,
        "hostname": request.state.host_resolution.hostname,
        "surface": request.state.host_resolution.surface,
        "user": {"id": user.id, "email": user.email, "roles": user.roles},
    }


@router.post("/platform/tenants/{tenant_id}/support-sessions", operation_id="create_support_session", status_code=201)
def support_session(
    tenant_id: str,
    data: SupportSessionInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    session_id = uuid7()
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"tenant-lifecycle:{tenant_id}")
        tenant = conn.execute(
            "SELECT id,status FROM platform_tenants WHERE id=?",
            (tenant_id,),
        ).fetchone()
        if not tenant:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        if tenant["status"] != "active":
            raise DomainError(
                "TENANT_SUPPORT_UNAVAILABLE",
                "Sessões de suporte só podem ser abertas para tenants ativos.",
                409,
            )
        if data.assumed_user_id:
            try:
                assumed_user = request.app.state.data_router.tenant_store(tenant_id).fetch_one(
                    "SELECT id,active FROM users WHERE tenant_id=? AND id=?",
                    (tenant_id, data.assumed_user_id),
                )
            except DomainError:
                raise
            except Exception as exc:
                raise DomainError(
                    "TENANT_DATABASE_UNAVAILABLE",
                    "Não foi possível validar o usuário assumido no banco do tenant.",
                    503,
                ) from exc
            if not assumed_user or not bool(assumed_user["active"]):
                raise DomainError(
                    "SUPPORT_ASSUMED_USER_INVALID",
                    "O usuário assumido não pertence ao tenant ou não está ativo.",
                    409,
                )
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=data.minutes)
        conn.execute(
            "INSERT INTO support_sessions(id,platform_admin_id,tenant_id,assumed_user_id,reason,ticket,ip,device,started_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                session_id,
                user.id,
                tenant_id,
                data.assumed_user_id,
                data.reason,
                data.ticket,
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
                now.isoformat(),
                expires.isoformat(),
            ),
        )
        result = {
            "id": session_id,
            "tenant_id": tenant_id,
            "platform_admin_id": user.id,
            "assumed_user_id": data.assumed_user_id,
            "reason": data.reason,
            "ticket": data.ticket,
            "started_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "banner_required": True,
        }
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="support_session_started",
            aggregate_type="support_session",
            aggregate_id=session_id,
            correlation_id=request.state.correlation_id,
            after=result,
            reason=data.reason,
        )
    return result


@router.get("/platform/status", operation_id="get_platform_operational_status")
def platform_status(request: Request, user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin"))):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    store = request.state.store
    tenants = store.fetch_all("SELECT id,status FROM platform_tenants ORDER BY created_at")
    domain_count = int(store.scalar("SELECT COUNT(*) AS n FROM tenant_domains") or 0)
    pending_outbox = int(store.scalar("SELECT COUNT(*) AS n FROM outbox_events WHERE published_at IS NULL") or 0)
    active_support = int(
        store.scalar(
            "SELECT COUNT(*) AS n FROM support_sessions WHERE ended_at IS NULL AND expires_at>?", (iso_now(),)
        )
        or 0
    )
    builds = {"queued": 0, "building": 0, "failed": 0, "completed": 0}
    unavailable_tenants: list[dict[str, str]] = []
    for tenant in tenants:
        try:
            tenant_store = request.app.state.data_router.tenant_store(tenant["id"])
            for state in list(builds):
                builds[state] += int(
                    tenant_store.scalar(
                        "SELECT COUNT(*) AS n FROM app_build_requests WHERE status=?",
                        (state,),
                    )
                    or 0
                )
        except Exception:
            unavailable_tenants.append(
                {
                    "tenant_id": str(tenant["id"]),
                    "tenant_status": str(tenant["status"]),
                    "code": "TENANT_DATABASE_UNAVAILABLE",
                }
            )
            logger.warning(
                json.dumps(
                    {
                        "event": "platform_status_tenant_unavailable",
                        "tenant_id": str(tenant["id"]),
                        "correlation_id": request.state.correlation_id,
                    },
                    separators=(",", ":"),
                )
            )
    return {
        "status": "degraded" if unavailable_tenants else "operational",
        "tenants": {
            "total": len(tenants),
            "active": sum(1 for item in tenants if item["status"] == "active"),
            "degraded": sum(1 for item in tenants if item["status"] == "degraded"),
            "suspended": sum(1 for item in tenants if item["status"] == "suspended"),
        },
        "domains": domain_count,
        "domain_policy": {
            "wildcard": f"*.{request.app.state.settings.tenant_default_base_domain}",
            "dns_per_canonical_tenant_required": False,
        },
        "pending_control_outbox": pending_outbox,
        "active_support_sessions": active_support,
        "builds": builds,
        "tenant_datastores": {
            "checked": len(tenants),
            "available": len(tenants) - len(unavailable_tenants),
            "unavailable": len(unavailable_tenants),
            "items": unavailable_tenants,
        },
        "generated_at": iso_now(),
    }


@router.get("/platform/audit", operation_id="list_platform_audit")
def platform_audit(
    request: Request,
    tenant_id: str | None = None,
    limit: int = 100,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    limit = min(max(limit, 1), 500)
    sql = "SELECT * FROM audit_log"
    params: list[object] = []
    if tenant_id:
        sql += " WHERE tenant_id=?"
        params.append(tenant_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = request.state.store.fetch_all(sql, params)
    for row in rows:
        for key in ("before_json", "after_json"):
            raw = row.pop(key, None)
            if raw:
                try:
                    row[key.removesuffix("_json")] = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    row[key.removesuffix("_json")] = None
    return {"items": rows, "limit": limit}


@router.get("/platform/support-sessions", operation_id="list_platform_support_sessions")
def list_support_sessions(
    request: Request,
    tenant_id: str | None = None,
    active_only: bool = False,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    sql = "SELECT * FROM support_sessions WHERE 1=1"
    params: list[object] = []
    if tenant_id:
        sql += " AND tenant_id=?"
        params.append(tenant_id)
    if active_only:
        sql += " AND ended_at IS NULL AND expires_at>?"
        params.append(iso_now())
    sql += " ORDER BY started_at DESC LIMIT 500"
    return {"items": request.state.store.fetch_all(sql, params)}


@router.post("/platform/support-sessions/{session_id}/revoke", operation_id="revoke_platform_support_session")
def revoke_support_session(
    session_id: str,
    data: SupportSessionEndInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    now = iso_now()
    with request.state.store.transaction() as conn:
        current = conn.execute(
            "SELECT id,tenant_id,platform_admin_id,started_at,expires_at,ended_at FROM support_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if not current:
            raise DomainError("SUPPORT_SESSION_NOT_FOUND", "Sessão de suporte não localizada.", 404)
        if current["ended_at"]:
            raise DomainError("SUPPORT_SESSION_ALREADY_ENDED", "A sessão de suporte já foi encerrada.", 409)
        changed = conn.execute(
            "UPDATE support_sessions SET ended_at=? WHERE id=? AND ended_at IS NULL",
            (now, session_id),
        ).rowcount
        if changed != 1:
            raise DomainError("SUPPORT_SESSION_ALREADY_ENDED", "A sessão de suporte já foi encerrada.", 409)
        result = {
            "id": session_id,
            "tenant_id": current["tenant_id"],
            "state": "revoked",
            "ended_at": now,
            "reason": data.reason,
        }
        add_audit(
            conn,
            tenant_id=current["tenant_id"],
            actor_id=user.id,
            action="support_session_revoked",
            aggregate_type="support_session",
            aggregate_id=session_id,
            correlation_id=request.state.correlation_id,
            before=dict(current),
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=current["tenant_id"],
            event_type="SupportSessionRevoked",
            aggregate_type="support_session",
            aggregate_id=session_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
    return result
