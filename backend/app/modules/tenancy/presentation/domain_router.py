from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.tenancy.domain_management import (
    DomainLifecycleError,
    normalize_hostname,
    refresh_certificate,
    remove_edge_route,
    request_certificate,
    verification_challenge,
    verify_dns_txt,
)
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, require_roles

router = APIRouter(tags=["tenancy-domains"])


class CustomDomainCreate(BaseModel):
    hostname: str = Field(min_length=3, max_length=253)
    surface: Literal["admin", "public", "family", "student", "teacher"] = "admin"


def _platform(user: CurrentUser) -> None:
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)


def _tenant(request: Request, tenant_id: str) -> dict:
    row = request.state.store.fetch_one(
        "SELECT id,code,legal_name,trade_name,status FROM platform_tenants WHERE id=?",
        (tenant_id,),
    )
    if not row:
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    return row


def _domain(request: Request, tenant_id: str, domain_id: str) -> dict:
    row = request.state.store.fetch_one(
        "SELECT * FROM tenant_domains WHERE tenant_id=? AND id=?",
        (tenant_id, domain_id),
    )
    if not row:
        raise DomainError("TENANT_DOMAIN_NOT_FOUND", "Domínio não localizado.", 404)
    return row


def _safe(row: dict) -> dict:
    result = dict(row)
    token = result.get("verification_token")
    if token:
        result["verification_record"] = {
            "type": "TXT",
            "name": result.get("verification_name"),
            "value": token,
        }
    return result


@router.get("/platform/tenants/{tenant_id}/domains", operation_id="list_platform_tenant_domains")
def list_domains(
    tenant_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _platform(user)
    _tenant(request, tenant_id)
    rows = request.state.store.fetch_all(
        "SELECT * FROM tenant_domains WHERE tenant_id=? ORDER BY is_canonical DESC, hostname",
        (tenant_id,),
    )
    return {"items": [_safe(row) for row in rows]}


@router.post("/platform/tenants/{tenant_id}/domains", operation_id="create_platform_tenant_custom_domain", status_code=201)
def create_domain(
    tenant_id: str,
    data: CustomDomainCreate,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _platform(user)
    tenant = _tenant(request, tenant_id)
    settings = request.app.state.settings
    if not settings.tenant_custom_domains_enabled:
        raise DomainError("CUSTOM_DOMAINS_DISABLED", "Domínios personalizados estão desabilitados.", 409)
    try:
        hostname = normalize_hostname(data.hostname)
    except DomainLifecycleError as exc:
        raise DomainError(exc.code, str(exc), 422) from exc
    base = settings.tenant_default_base_domain
    if hostname == base or hostname.endswith(f".{base}"):
        raise DomainError(
            "CUSTOM_DOMAIN_CANONICAL_ZONE_FORBIDDEN",
            f"Hosts dentro de {base} são provisionados pelo domínio canônico do tenant.",
            409,
        )
    existing = request.state.store.fetch_one("SELECT id,tenant_id FROM tenant_domains WHERE hostname=?", (hostname,))
    if existing:
        raise DomainError("TENANT_DOMAIN_ALREADY_EXISTS", "Este hostname já está cadastrado.", 409)
    name, token = verification_challenge(hostname)
    domain_id = uuid7()
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute(
            """INSERT INTO tenant_domains(
                id,tenant_id,hostname,surface,status,is_canonical,certificate_policy,certificate_status,
                verification_method,verification_name,verification_token,verification_status,provider,
                provider_reference,verified_at,activated_at,last_error,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                domain_id, tenant_id, hostname, data.surface, "pending_verification", 0,
                "cloudflare_saas" if __import__("os").getenv("CLOUDFLARE_SAAS_ENABLED", "false").lower() in {"1","true","yes","on"} else "edge_acme",
                "not_requested", "dns_txt", name, token, "pending", None, None, None, None, None, now, now,
            ),
        )
        after = {
            "id": domain_id,
            "tenant_id": tenant_id,
            "tenant_code": tenant["code"],
            "hostname": hostname,
            "surface": data.surface,
            "status": "pending_verification",
            "verification_name": name,
        }
        add_audit(
            conn, tenant_id=tenant_id, actor_id=user.id, action="custom_domain_requested",
            aggregate_type="tenant_domain", aggregate_id=domain_id,
            correlation_id=request.state.correlation_id, after=after,
        )
        add_outbox(
            conn, tenant_id=tenant_id, event_type="TenantCustomDomainRequested",
            aggregate_type="tenant_domain", aggregate_id=domain_id,
            payload=after, correlation_id=request.state.correlation_id,
        )
    return _safe(_domain(request, tenant_id, domain_id))


@router.post("/platform/tenants/{tenant_id}/domains/{domain_id}/verify", operation_id="verify_platform_tenant_custom_domain")
def verify_domain(
    tenant_id: str,
    domain_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _platform(user)
    _tenant(request, tenant_id)
    row = _domain(request, tenant_id, domain_id)
    if row.get("is_canonical"):
        return _safe(row)
    if row.get("verification_status") == "verified" and row.get("status") in {"pending_tls", "active"}:
        return _safe(row)
    lookup = getattr(request.app.state, "domain_txt_lookup", None)
    try:
        valid = verify_dns_txt(str(row["verification_name"]), str(row["verification_token"]), lookup=lookup)
    except DomainLifecycleError as exc:
        raise DomainError(exc.code, str(exc), 409) from exc
    if not valid:
        raise DomainError("DOMAIN_VERIFICATION_MISMATCH", "O TXT existe, mas não contém o token esperado.", 409)
    try:
        cert = request_certificate(str(row["hostname"]))
    except DomainLifecycleError as exc:
        with request.state.store.transaction() as conn:
            conn.execute(
                "UPDATE tenant_domains SET verification_status='verified',verified_at=?,status='verified_waiting_provider',last_error=?,updated_at=? WHERE id=?",
                (iso_now(), str(exc), iso_now(), domain_id),
            )
        raise DomainError(exc.code, str(exc), 503) from exc
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute(
            """UPDATE tenant_domains SET verification_status='verified',verified_at=?,status=?,certificate_status=?,
               provider=?,provider_reference=?,last_error=NULL,updated_at=? WHERE id=?""",
            (now, cert["status"], cert["certificate_status"], cert["provider"], cert["provider_reference"], now, domain_id),
        )
        after = {"hostname": row["hostname"], "status": cert["status"], "provider": cert["provider"]}
        add_audit(
            conn, tenant_id=tenant_id, actor_id=user.id, action="custom_domain_verified",
            aggregate_type="tenant_domain", aggregate_id=domain_id,
            correlation_id=request.state.correlation_id, after=after,
        )
        add_outbox(
            conn, tenant_id=tenant_id, event_type="TenantCustomDomainVerified",
            aggregate_type="tenant_domain", aggregate_id=domain_id,
            payload=after, correlation_id=request.state.correlation_id,
        )
    return _safe(_domain(request, tenant_id, domain_id))


@router.post("/platform/tenants/{tenant_id}/domains/{domain_id}/refresh", operation_id="refresh_platform_tenant_custom_domain")
def refresh_domain(
    tenant_id: str,
    domain_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _platform(user)
    _tenant(request, tenant_id)
    row = _domain(request, tenant_id, domain_id)
    if row.get("verification_status") != "verified":
        raise DomainError("DOMAIN_NOT_VERIFIED", "Verifique a propriedade do domínio antes do TLS.", 409)
    try:
        result = refresh_certificate(str(row["hostname"]), row.get("provider"), row.get("provider_reference"))
    except DomainLifecycleError as exc:
        with request.state.store.transaction() as conn:
            conn.execute("UPDATE tenant_domains SET last_error=?,updated_at=? WHERE id=?", (str(exc), iso_now(), domain_id))
        raise DomainError(exc.code, str(exc), 503) from exc
    now = iso_now()
    active = result["status"] == "active" and result["certificate_status"] == "active"
    with request.state.store.transaction() as conn:
        conn.execute(
            "UPDATE tenant_domains SET status=?,certificate_status=?,activated_at=CASE WHEN ? THEN COALESCE(activated_at,?) ELSE activated_at END,last_error=NULL,updated_at=? WHERE id=?",
            (result["status"], result["certificate_status"], 1 if active else 0, now, now, domain_id),
        )
        if active:
            after = {"hostname": row["hostname"], "status": "active", "certificate_status": "active"}
            add_audit(
                conn, tenant_id=tenant_id, actor_id=user.id, action="custom_domain_activated",
                aggregate_type="tenant_domain", aggregate_id=domain_id,
                correlation_id=request.state.correlation_id, after=after,
            )
            add_outbox(
                conn, tenant_id=tenant_id, event_type="TenantCustomDomainActivated",
                aggregate_type="tenant_domain", aggregate_id=domain_id,
                payload=after, correlation_id=request.state.correlation_id,
            )
    return _safe(_domain(request, tenant_id, domain_id))


@router.delete("/platform/tenants/{tenant_id}/domains/{domain_id}", operation_id="deactivate_platform_tenant_custom_domain")
def deactivate_domain(
    tenant_id: str,
    domain_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _platform(user)
    row = _domain(request, tenant_id, domain_id)
    if row.get("is_canonical"):
        raise DomainError("CANONICAL_DOMAIN_CANNOT_BE_REMOVED", "O domínio canônico do tenant não pode ser removido.", 409)
    remove_edge_route(str(row["hostname"]))
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE tenant_domains SET status='disabled',updated_at=? WHERE id=?", (now, domain_id))
        add_audit(
            conn, tenant_id=tenant_id, actor_id=user.id, action="custom_domain_disabled",
            aggregate_type="tenant_domain", aggregate_id=domain_id,
            correlation_id=request.state.correlation_id,
            before={"hostname": row["hostname"], "status": row["status"]},
            after={"hostname": row["hostname"], "status": "disabled"},
        )
    return {"id": domain_id, "hostname": row["hostname"], "status": "disabled"}
