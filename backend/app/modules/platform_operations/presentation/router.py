from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.shared.domain.ids import iso_now
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, require_roles

router = APIRouter(tags=["platform-operations"])


class PlatformUserStateInput(BaseModel):
    active: bool
    reason: str = Field(min_length=10, max_length=2000)


def _require_platform(user: CurrentUser) -> None:
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)


def _roles(raw: object) -> list[str]:
    try:
        value = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return []
    return sorted({str(role) for role in value}) if isinstance(value, list) else []


def _platform_user(row: dict[str, Any], current_user_id: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "roles": _roles(row["roles_json"]),
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_current_user": row["id"] == current_user_id,
    }


@router.get("/platform/users", operation_id="list_platform_users")
def list_platform_users(
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    rows = request.state.store.fetch_all(
        """SELECT id,email,roles_json,active,created_at,updated_at
           FROM users WHERE tenant_id IS NULL ORDER BY active DESC,email"""
    )
    return {"items": [_platform_user(row, user.id) for row in rows]}


@router.patch("/platform/users/{user_id}/active", operation_id="set_platform_user_active")
def set_platform_user_active(
    user_id: str,
    data: PlatformUserStateInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin")),
):
    _require_platform(user)
    if user_id == user.id and not data.active:
        raise DomainError(
            "PLATFORM_ADMIN_SELF_DISABLE_FORBIDDEN",
            "Você não pode desativar a própria conta administrativa.",
            409,
        )
    now = iso_now()
    with request.state.store.transaction() as conn:
        # SQLite já serializa por BEGIN IMMEDIATE; PostgreSQL usa advisory lock.
        # O mesmo namespace impede que dois superadmins desativem um ao outro
        # simultaneamente e deixem a plataforma sem conta de recuperação.
        request.state.store.transaction_lock(conn, "platform-super-admin-active-invariant")
        current = conn.execute(
            """SELECT id,email,roles_json,active,created_at,updated_at
               FROM users WHERE id=? AND tenant_id IS NULL""",
            (user_id,),
        ).fetchone()
        if not current:
            raise DomainError("PLATFORM_USER_NOT_FOUND", "Usuário da plataforma não localizado.", 404)
        previous_active = bool(current["active"])
        if previous_active == data.active:
            return {**_platform_user(dict(current), user.id), "changed": False}
        current_roles = _roles(current["roles_json"])
        if not data.active and "platform_super_admin" in current_roles:
            active_admin_rows = conn.execute(
                """SELECT id,roles_json FROM users
                   WHERE tenant_id IS NULL AND active=1 AND id<>?""",
                (user_id,),
            ).fetchall()
            remaining_super_admins = sum(
                1 for row in active_admin_rows if "platform_super_admin" in _roles(row["roles_json"])
            )
            if remaining_super_admins < 1:
                raise DomainError(
                    "LAST_PLATFORM_SUPER_ADMIN",
                    "A última conta superadministradora ativa não pode ser desativada.",
                    409,
                )
        changed = conn.execute(
            "UPDATE users SET active=?,updated_at=? WHERE id=? AND tenant_id IS NULL AND active=?",
            (1 if data.active else 0, now, user_id, 1 if previous_active else 0),
        ).rowcount
        if changed != 1:
            raise DomainError(
                "PLATFORM_USER_STATE_CONFLICT",
                "O usuário foi alterado por outro operador. Atualize a tela antes de tentar novamente.",
                409,
            )
        if not data.active:
            conn.execute(
                "UPDATE refresh_tokens SET revoked_at=COALESCE(revoked_at,?) WHERE user_id=? AND tenant_id IS NULL",
                (now, user_id),
            )
        result = {
            "id": user_id,
            "email": current["email"],
            "roles": current_roles,
            "active": data.active,
            "created_at": current["created_at"],
            "updated_at": now,
            "is_current_user": user_id == user.id,
            "changed": True,
        }
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="activate_platform_user" if data.active else "deactivate_platform_user",
            aggregate_type="platform_user",
            aggregate_id=user_id,
            correlation_id=request.state.correlation_id,
            before={"active": previous_active},
            after={"active": data.active},
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="PlatformUserActivated" if data.active else "PlatformUserDeactivated",
            aggregate_type="platform_user",
            aggregate_id=user_id,
            payload={"id": user_id, "active": data.active, "changed_at": now},
            correlation_id=request.state.correlation_id,
        )
    return result


def _tenant_resource_inventory(request: Request, row: dict[str, Any]) -> dict[str, Any]:
    production = request.app.state.settings.environment in {"production", "staging"}
    database_configured = bool(row.get("database_name")) if production else bool(row.get("database_path"))
    storage_path = str(row.get("storage_path") or "")
    storage_configured = bool(row.get("bucket_name")) if production else bool(storage_path) and Path(storage_path).is_dir()
    workloads: dict[str, Any] = {
        "outbox_pending": None,
        "builds": None,
        "integration_connections": None,
        "mail_accounts": None,
    }
    database_probe = "not_configured"
    if database_configured:
        try:
            store = request.app.state.data_router.tenant_store(row["id"])
            workloads["outbox_pending"] = int(
                store.scalar("SELECT COUNT(*) AS n FROM outbox_events WHERE published_at IS NULL") or 0
            )
            workloads["builds"] = {
                state: int(
                    store.scalar("SELECT COUNT(*) AS n FROM app_build_requests WHERE status=?", (state,)) or 0
                )
                for state in ("queued", "building", "failed", "completed")
            }
            workloads["integration_connections"] = int(
                store.scalar("SELECT COUNT(*) AS n FROM integration_connections") or 0
            )
            workloads["mail_accounts"] = int(store.scalar("SELECT COUNT(*) AS n FROM mail_accounts") or 0)
            database_probe = "reachable"
        except Exception:
            # A fronteira não retorna mensagens do driver, nomes de banco, hosts ou
            # credenciais. O correlation-id dos logs internos sustenta o diagnóstico.
            database_probe = "unavailable"
    return {
        "id": row["id"],
        "code": row["code"],
        "status": row["status"],
        "version": row["version"],
        "database": {
            "provider": "postgresql" if production else "sqlite",
            "configured": database_configured,
            "probe": database_probe,
        },
        "storage": {
            "provider": "s3-compatible" if production else "filesystem",
            "configured": storage_configured,
            "probe": "not_performed",
        },
        "workloads": workloads,
    }


@router.get("/platform/operations/inventory", operation_id="get_platform_operations_inventory")
def platform_operations_inventory(
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    """Inventário interno sem chamar Cloudflare, Mailcow, Connect API ou storage.

    A consulta testa somente os bancos já configurados. Probes de providers externos
    continuam deliberadamente fora deste endpoint para evitar efeitos colaterais e
    vazamento acidental de configuração sensível.
    """

    _require_platform(user)
    settings = request.app.state.settings
    production = settings.environment in {"production", "staging"}
    columns = (
        "id,code,status,version,database_path,database_name,storage_path,bucket_name"
        if production
        else "id,code,status,version,database_path,storage_path"
    )
    rows = request.state.store.fetch_all(f"SELECT {columns} FROM platform_tenants ORDER BY code")
    tenants = [_tenant_resource_inventory(request, row) for row in rows]
    build_totals = {state: 0 for state in ("queued", "building", "failed", "completed")}
    tenant_outbox_pending = 0
    integration_connections = 0
    mail_accounts = 0
    database_unavailable = 0
    for tenant in tenants:
        if tenant["database"]["probe"] == "unavailable":
            database_unavailable += 1
        workload = tenant["workloads"]
        if workload["outbox_pending"] is not None:
            tenant_outbox_pending += int(workload["outbox_pending"])
        if isinstance(workload["builds"], dict):
            for state in build_totals:
                build_totals[state] += int(workload["builds"].get(state) or 0)
        integration_connections += int(workload["integration_connections"] or 0)
        mail_accounts += int(workload["mail_accounts"] or 0)
    control_outbox_pending = int(
        request.state.store.scalar("SELECT COUNT(*) AS n FROM outbox_events WHERE published_at IS NULL") or 0
    )
    storage_credentials_configured = bool(
        settings.object_storage_endpoint
        and settings.object_storage_access_key
        and settings.object_storage_secret_key
    )
    return {
        "status": "degraded" if database_unavailable else "observed",
        "scope": "configuration_and_internal_persistence",
        "external_provider_probes_performed": False,
        "generated_at": iso_now(),
        "control_database": {
            "provider": "postgresql" if production else "sqlite",
            "state": "reachable",
            "pool_size": settings.database_pool_size if production else None,
            "max_overflow": settings.database_max_overflow if production else None,
        },
        "tenant_resources": {
            "total": len(tenants),
            "database_reachable": sum(1 for item in tenants if item["database"]["probe"] == "reachable"),
            "database_unavailable": database_unavailable,
            "storage_configured": sum(1 for item in tenants if item["storage"]["configured"]),
        },
        "workloads": {
            "control_outbox_pending": control_outbox_pending,
            "tenant_outbox_pending": tenant_outbox_pending,
            "builds": build_totals,
            "integration_connections": integration_connections,
            "mail_accounts": mail_accounts,
        },
        "configuration": {
            "environment": settings.environment,
            "version": settings.version,
            "domains": {
                "base_domain": settings.base_domain,
                "tenant_base_domain": settings.tenant_default_base_domain,
                "custom_domains_enabled": settings.tenant_custom_domains_enabled,
            },
            "storage": {
                "provider": "s3-compatible" if production else "filesystem",
                "configured": storage_credentials_configured if production else True,
                "secure_transport": settings.object_storage_secure if production else None,
            },
            "mail": {
                "mode": settings.mail_mode,
                "imap_configured": bool(settings.mail_imap_host),
                "smtp_configured": bool(settings.mail_smtp_host),
                "smtp_tls": settings.mail_smtp_tls,
            },
            "integrations": {"remote_calls_enabled": settings.integration_remote_enabled},
            "build_farm": {"token_configured": bool(settings.build_farm_token)},
            "remote_operations": {
                "ci_enabled": settings.remote_ci_enabled,
                "registry_enabled": settings.remote_registry_enabled,
                "release_enabled": settings.remote_release_enabled,
                "deploy_enabled": settings.remote_deploy_enabled,
            },
        },
        "tenants": tenants,
    }
