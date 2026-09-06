from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request

from app.modules.commercial_administration.application.service import (
    begin_idempotent,
    canonical_json,
    finish_idempotent,
    json_object,
    plan_entitlements,
)
from app.modules.commercial_administration.presentation.schemas import (
    LifecycleInput,
    LinkTenantInput,
    PartnerCreate,
    PartnerUpdate,
    PlanCreate,
    PlanUpdate,
    SubscriptionInput,
    UsageSnapshotInput,
)
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, require_roles

router = APIRouter(prefix="/platform/commercial", tags=["platform-commercial"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$",
    ),
]

READ_ROLES = ("platform_super_admin", "platform_admin")
WRITE_ROLES = ("platform_super_admin", "platform_admin")


def _require_platform(user: CurrentUser) -> None:
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)


def _tenant(conn: Any, tenant_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id,code,legal_name,trade_name,status,version FROM platform_tenants WHERE id=?",
        (tenant_id,),
    ).fetchone()
    if not row:
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    return dict(row)


def _partner(conn: Any, partner_id: str) -> dict[str, Any]:
    row = conn.execute(
        """SELECT id,code,legal_name,trade_name,contact_email,notes,status,created_at,updated_at,version
           FROM commercial_partners WHERE id=?""",
        (partner_id,),
    ).fetchone()
    if not row:
        raise DomainError("COMMERCIAL_PARTNER_NOT_FOUND", "Parceiro comercial não localizado.", 404)
    return dict(row)


def _plan(conn: Any, plan_id: str) -> dict[str, Any]:
    row = conn.execute(
        """SELECT id,code,name,description,currency,billing_interval,price_minor,features_json,
                  limits_json,status,created_at,updated_at,version
           FROM commercial_plans WHERE id=?""",
        (plan_id,),
    ).fetchone()
    if not row:
        raise DomainError("COMMERCIAL_PLAN_NOT_FOUND", "Plano comercial não localizado.", 404)
    return dict(row)


def _partner_response(row: dict[str, Any], *, tenant_count: int | None = None) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "code": row["code"],
        "legal_name": row["legal_name"],
        "trade_name": row["trade_name"],
        "contact_email": row.get("contact_email"),
        "notes": row.get("notes"),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": int(row["version"]),
    }
    if tenant_count is not None:
        result["tenant_count"] = tenant_count
    return result


def _plan_response(row: dict[str, Any], *, subscription_count: int | None = None) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "description": row.get("description"),
        "currency": row["currency"],
        "billing_interval": row["billing_interval"],
        "price_minor": int(row["price_minor"]),
        "features": json_object(row.get("features_json")),
        "limits": json_object(row.get("limits_json")),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": int(row["version"]),
    }
    if subscription_count is not None:
        result["subscription_count"] = subscription_count
    return result


def _subscription_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "plan_id": row["plan_id"],
        "status": row["status"],
        "starts_at": row["starts_at"],
        "current_period_end": row.get("current_period_end"),
        "trial_ends_at": row.get("trial_ends_at"),
        "cancel_at_period_end": bool(row["cancel_at_period_end"]),
        "billing_mode": "manual",
        "automatic_charging": False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": int(row["version"]),
    }


def _usage_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "period": row["period"],
        "source": row["source"],
        "metrics": json_object(row.get("metrics_json")),
        "captured_at": row["captured_at"],
        "updated_at": row["updated_at"],
        "version": int(row["version"]),
    }


@router.get("/partners", operation_id="list_commercial_partners")
def list_partners(
    request: Request,
    status: str | None = Query(default=None, pattern=r"^(active|suspended|archived)$"),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("p.status=?")
        params.append(status)
    if q:
        clauses.append("(lower(p.code) LIKE ? OR lower(p.legal_name) LIKE ? OR lower(p.trade_name) LIKE ?)")
        value = f"%{q.strip().lower()}%"
        params.extend((value, value, value))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend((limit, offset))
    rows = request.state.store.fetch_all(
        f"""SELECT p.id,p.code,p.legal_name,p.trade_name,p.contact_email,p.notes,p.status,
                   p.created_at,p.updated_at,p.version,COUNT(pt.tenant_id) AS tenant_count
            FROM commercial_partners p
            LEFT JOIN commercial_partner_tenants pt ON pt.partner_id=p.id
            {where}
            GROUP BY p.id,p.code,p.legal_name,p.trade_name,p.contact_email,p.notes,p.status,
                     p.created_at,p.updated_at,p.version
            ORDER BY p.trade_name,p.code LIMIT ? OFFSET ?""",
        params,
    )
    return {
        "items": [_partner_response(row, tenant_count=int(row["tenant_count"])) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/partners/{partner_id}", operation_id="get_commercial_partner")
def get_partner(
    partner_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    row = request.state.store.fetch_one(
        """SELECT id,code,legal_name,trade_name,contact_email,notes,status,created_at,updated_at,version
           FROM commercial_partners WHERE id=?""",
        (partner_id,),
    )
    if not row:
        raise DomainError("COMMERCIAL_PARTNER_NOT_FOUND", "Parceiro comercial não localizado.", 404)
    tenants = request.state.store.fetch_all(
        """SELECT t.id,t.code,t.legal_name,t.trade_name,t.status,pt.linked_at
           FROM commercial_partner_tenants pt
           JOIN platform_tenants t ON t.id=pt.tenant_id
           WHERE pt.partner_id=? ORDER BY t.trade_name,t.code""",
        (partner_id,),
    )
    return {**_partner_response(row, tenant_count=len(tenants)), "tenants": tenants}


@router.post("/partners", operation_id="create_commercial_partner", status_code=201)
def create_partner(
    data: PartnerCreate,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(
            conn,
            scope="commercial.partner.create",
            key=idempotency_key,
            payload=payload,
        )
        if replay is not None:
            return replay
        existing = conn.execute("SELECT id FROM commercial_partners WHERE code=?", (data.code,)).fetchone()
        if existing:
            raise DomainError("COMMERCIAL_PARTNER_CODE_EXISTS", "Já existe parceiro com este código.", 409)
        partner_id, now = uuid7(), iso_now()
        conn.execute(
            """INSERT INTO commercial_partners(
                   id,code,legal_name,trade_name,contact_email,notes,status,created_at,updated_at,version
               ) VALUES(?,?,?,?,?,?,?,?,?,1)""",
            (
                partner_id,
                data.code,
                data.legal_name,
                data.trade_name,
                str(data.contact_email).lower() if data.contact_email else None,
                data.notes,
                "active",
                now,
                now,
            ),
        )
        result = {
            "id": partner_id,
            "code": data.code,
            "legal_name": data.legal_name,
            "trade_name": data.trade_name,
            "contact_email": str(data.contact_email).lower() if data.contact_email else None,
            "notes": data.notes,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "tenant_count": 0,
        }
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="commercial_partner_created",
            aggregate_type="commercial_partner",
            aggregate_id=partner_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="CommercialPartnerCreated",
            aggregate_type="commercial_partner",
            aggregate_id=partner_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(
            conn,
            scope="commercial.partner.create",
            key=idempotency_key,
            fingerprint=fingerprint,
            result=result,
        )
    return result


@router.patch("/partners/{partner_id}", operation_id="update_commercial_partner")
def update_partner(
    partner_id: str,
    data: PartnerUpdate,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = data.model_dump(mode="json", exclude_unset=True)
    scope = f"commercial.partner.update:{partner_id}"
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        current = _partner(conn, partner_id)
        if int(current["version"]) != data.expected_version:
            raise DomainError("COMMERCIAL_PARTNER_VERSION_CONFLICT", "O parceiro foi alterado por outro operador.", 409)
        fields = {
            key: payload[key]
            for key in ("legal_name", "trade_name", "contact_email", "notes")
            if key in payload
        }
        if "contact_email" in fields and fields["contact_email"]:
            fields["contact_email"] = str(fields["contact_email"]).lower()
        now = iso_now()
        assignments = ",".join(f"{key}=?" for key in fields)
        params = [*fields.values(), now, partner_id, data.expected_version]
        changed = conn.execute(
            f"UPDATE commercial_partners SET {assignments},updated_at=?,version=version+1 WHERE id=? AND version=?",
            params,
        ).rowcount
        if changed != 1:
            raise DomainError("COMMERCIAL_PARTNER_VERSION_CONFLICT", "O parceiro foi alterado por outro operador.", 409)
        result = _partner_response(
            {**current, **fields, "updated_at": now, "version": data.expected_version + 1}
        )
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="commercial_partner_updated",
            aggregate_type="commercial_partner",
            aggregate_id=partner_id,
            correlation_id=request.state.correlation_id,
            before=_partner_response(current),
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="CommercialPartnerUpdated",
            aggregate_type="commercial_partner",
            aggregate_id=partner_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


def _partner_lifecycle(
    *,
    partner_id: str,
    target: str,
    data: LifecycleInput,
    request: Request,
    key: str,
    user: CurrentUser,
) -> dict[str, Any]:
    scope = f"commercial.partner.lifecycle:{partner_id}:{target}"
    payload = data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=key, payload=payload)
        if replay is not None:
            return replay
        request.state.store.transaction_lock(conn, f"commercial-partner:{partner_id}")
        current = _partner(conn, partner_id)
        if int(current["version"]) != data.expected_version:
            raise DomainError("COMMERCIAL_PARTNER_VERSION_CONFLICT", "O parceiro foi alterado por outro operador.", 409)
        if target == "archived":
            linked = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM commercial_partner_tenants WHERE partner_id=?",
                    (partner_id,),
                ).fetchone()["n"]
            )
            if linked:
                raise DomainError(
                    "COMMERCIAL_PARTNER_HAS_TENANTS",
                    "Desvincule os tenants antes de arquivar o parceiro.",
                    409,
                )
        allowed = {
            "active": {"suspended"},
            "suspended": {"active"},
            "archived": {"active", "suspended"},
        }
        if current["status"] not in allowed[target]:
            raise DomainError(
                "COMMERCIAL_PARTNER_TRANSITION_INVALID",
                f"Não é possível alterar parceiro de '{current['status']}' para '{target}'.",
                409,
            )
        now = iso_now()
        changed = conn.execute(
            """UPDATE commercial_partners SET status=?,updated_at=?,version=version+1
               WHERE id=? AND version=? AND status=?""",
            (target, now, partner_id, data.expected_version, current["status"]),
        ).rowcount
        if changed != 1:
            raise DomainError("COMMERCIAL_PARTNER_VERSION_CONFLICT", "O parceiro foi alterado por outro operador.", 409)
        result = _partner_response(
            {**current, "status": target, "updated_at": now, "version": data.expected_version + 1}
        )
        result["reason"] = data.reason
        event_suffix = {"active": "Reactivated", "suspended": "Suspended", "archived": "Archived"}[target]
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action=f"commercial_partner_{target}",
            aggregate_type="commercial_partner",
            aggregate_id=partner_id,
            correlation_id=request.state.correlation_id,
            before={"status": current["status"], "version": current["version"]},
            after={"status": target, "version": result["version"]},
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type=f"CommercialPartner{event_suffix}",
            aggregate_type="commercial_partner",
            aggregate_id=partner_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(conn, scope=scope, key=key, fingerprint=fingerprint, result=result)
    return result


@router.post("/partners/{partner_id}/suspend", operation_id="suspend_commercial_partner")
def suspend_partner(
    partner_id: str,
    data: LifecycleInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    return _partner_lifecycle(
        partner_id=partner_id, target="suspended", data=data, request=request, key=idempotency_key, user=user
    )


@router.post("/partners/{partner_id}/reactivate", operation_id="reactivate_commercial_partner")
def reactivate_partner(
    partner_id: str,
    data: LifecycleInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    return _partner_lifecycle(
        partner_id=partner_id, target="active", data=data, request=request, key=idempotency_key, user=user
    )


@router.delete("/partners/{partner_id}", operation_id="archive_commercial_partner")
def archive_partner(
    partner_id: str,
    data: LifecycleInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    return _partner_lifecycle(
        partner_id=partner_id, target="archived", data=data, request=request, key=idempotency_key, user=user
    )


@router.put("/partners/{partner_id}/tenants/{tenant_id}", operation_id="link_commercial_partner_tenant")
def link_partner_tenant(
    partner_id: str,
    tenant_id: str,
    data: LinkTenantInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    scope = f"commercial.partner.link:{partner_id}:{tenant_id}"
    payload = data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        request.state.store.transaction_lock(conn, f"commercial-partner:{partner_id}")
        request.state.store.transaction_lock(conn, f"commercial-partner-tenant:{tenant_id}")
        partner = _partner(conn, partner_id)
        tenant = _tenant(conn, tenant_id)
        if partner["status"] != "active":
            raise DomainError("COMMERCIAL_PARTNER_INACTIVE", "Somente parceiro ativo pode receber tenant.", 409)
        current = conn.execute(
            "SELECT partner_id,linked_at FROM commercial_partner_tenants WHERE tenant_id=?",
            (tenant_id,),
        ).fetchone()
        if current and current["partner_id"] != partner_id:
            raise DomainError(
                "TENANT_ALREADY_LINKED_TO_PARTNER",
                "O tenant já está vinculado a outro parceiro.",
                409,
            )
        changed = current is None
        now = iso_now()
        if changed:
            conn.execute(
                """INSERT INTO commercial_partner_tenants(tenant_id,partner_id,linked_by,linked_at)
                   VALUES(?,?,?,?)""",
                (tenant_id, partner_id, user.id, now),
            )
            add_audit(
                conn,
                tenant_id=tenant_id,
                actor_id=user.id,
                action="commercial_partner_tenant_linked",
                aggregate_type="tenant",
                aggregate_id=tenant_id,
                correlation_id=request.state.correlation_id,
                after={"partner_id": partner_id},
                reason=data.reason,
            )
            add_outbox(
                conn,
                tenant_id=tenant_id,
                event_type="TenantLinkedToCommercialPartner",
                aggregate_type="tenant",
                aggregate_id=tenant_id,
                payload={"tenant_id": tenant_id, "partner_id": partner_id, "linked_at": now},
                correlation_id=request.state.correlation_id,
            )
        result = {
            "tenant_id": tenant_id,
            "tenant_code": tenant["code"],
            "partner_id": partner_id,
            "partner_code": partner["code"],
            "linked_at": now if changed else current["linked_at"],
            "changed": changed,
        }
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


@router.delete("/partners/{partner_id}/tenants/{tenant_id}", operation_id="unlink_commercial_partner_tenant")
def unlink_partner_tenant(
    partner_id: str,
    tenant_id: str,
    data: LinkTenantInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    scope = f"commercial.partner.unlink:{partner_id}:{tenant_id}"
    payload = data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        request.state.store.transaction_lock(conn, f"commercial-partner:{partner_id}")
        request.state.store.transaction_lock(conn, f"commercial-partner-tenant:{tenant_id}")
        _partner(conn, partner_id)
        _tenant(conn, tenant_id)
        changed = conn.execute(
            "DELETE FROM commercial_partner_tenants WHERE tenant_id=? AND partner_id=?",
            (tenant_id, partner_id),
        ).rowcount == 1
        if changed:
            add_audit(
                conn,
                tenant_id=tenant_id,
                actor_id=user.id,
                action="commercial_partner_tenant_unlinked",
                aggregate_type="tenant",
                aggregate_id=tenant_id,
                correlation_id=request.state.correlation_id,
                before={"partner_id": partner_id},
                after={"partner_id": None},
                reason=data.reason,
            )
            add_outbox(
                conn,
                tenant_id=tenant_id,
                event_type="TenantUnlinkedFromCommercialPartner",
                aggregate_type="tenant",
                aggregate_id=tenant_id,
                payload={"tenant_id": tenant_id, "partner_id": partner_id, "unlinked_at": iso_now()},
                correlation_id=request.state.correlation_id,
            )
        result = {"tenant_id": tenant_id, "partner_id": partner_id, "changed": changed}
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


@router.get("/plans", operation_id="list_commercial_plans")
def list_plans(
    request: Request,
    status: str | None = Query(default=None, pattern=r"^(active|inactive|archived)$"),
    include_archived: bool = False,
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    if status:
        where, params = "WHERE p.status=?", [status]
    elif include_archived:
        where, params = "", []
    else:
        where, params = "WHERE p.status<>'archived'", []
    rows = request.state.store.fetch_all(
        f"""SELECT p.id,p.code,p.name,p.description,p.currency,p.billing_interval,p.price_minor,
                   p.features_json,p.limits_json,p.status,p.created_at,p.updated_at,p.version,
                   COUNT(s.id) AS subscription_count
            FROM commercial_plans p
            LEFT JOIN commercial_subscriptions s ON s.plan_id=p.id
            {where}
            GROUP BY p.id,p.code,p.name,p.description,p.currency,p.billing_interval,p.price_minor,
                     p.features_json,p.limits_json,p.status,p.created_at,p.updated_at,p.version
            ORDER BY p.name,p.code""",
        params,
    )
    return {
        "items": [_plan_response(row, subscription_count=int(row["subscription_count"])) for row in rows],
        "billing_automation": False,
    }


@router.get("/plans/{plan_id}", operation_id="get_commercial_plan")
def get_plan(
    plan_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    row = request.state.store.fetch_one(
        """SELECT id,code,name,description,currency,billing_interval,price_minor,features_json,
                  limits_json,status,created_at,updated_at,version
           FROM commercial_plans WHERE id=?""",
        (plan_id,),
    )
    if not row:
        raise DomainError("COMMERCIAL_PLAN_NOT_FOUND", "Plano comercial não localizado.", 404)
    count = int(
        request.state.store.scalar(
            "SELECT COUNT(*) AS n FROM commercial_subscriptions WHERE plan_id=?",
            (plan_id,),
        )
        or 0
    )
    return _plan_response(row, subscription_count=count)


@router.post("/plans", operation_id="create_commercial_plan", status_code=201)
def create_plan(
    data: PlanCreate,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(
            conn, scope="commercial.plan.create", key=idempotency_key, payload=payload
        )
        if replay is not None:
            return replay
        if conn.execute("SELECT id FROM commercial_plans WHERE code=?", (data.code,)).fetchone():
            raise DomainError("COMMERCIAL_PLAN_CODE_EXISTS", "Já existe plano com este código.", 409)
        serialized_features = canonical_json(data.features)
        serialized_limits = canonical_json(data.limits)
        if len(serialized_features.encode("utf-8")) + len(serialized_limits.encode("utf-8")) > 32768:
            raise DomainError("COMMERCIAL_PLAN_CONFIGURATION_TOO_LARGE", "Features e limites excedem 32 KiB.", 422)
        plan_id, now = uuid7(), iso_now()
        conn.execute(
            """INSERT INTO commercial_plans(
                   id,code,name,description,currency,billing_interval,price_minor,features_json,
                   limits_json,status,created_at,updated_at,version
               ) VALUES(?,?,?,?,?,?,?,?,?,'active',?,?,1)""",
            (
                plan_id,
                data.code,
                data.name,
                data.description,
                data.currency,
                data.billing_interval,
                data.price_minor,
                serialized_features,
                serialized_limits,
                now,
                now,
            ),
        )
        result = _plan_response(
            {
                "id": plan_id,
                "code": data.code,
                "name": data.name,
                "description": data.description,
                "currency": data.currency,
                "billing_interval": data.billing_interval,
                "price_minor": data.price_minor,
                "features_json": serialized_features,
                "limits_json": serialized_limits,
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "version": 1,
            },
            subscription_count=0,
        )
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="commercial_plan_created",
            aggregate_type="commercial_plan",
            aggregate_id=plan_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="CommercialPlanCreated",
            aggregate_type="commercial_plan",
            aggregate_id=plan_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(
            conn,
            scope="commercial.plan.create",
            key=idempotency_key,
            fingerprint=fingerprint,
            result=result,
        )
    return result


@router.patch("/plans/{plan_id}", operation_id="update_commercial_plan")
def update_plan(
    plan_id: str,
    data: PlanUpdate,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = data.model_dump(mode="json", exclude_unset=True)
    scope = f"commercial.plan.update:{plan_id}"
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        current = _plan(conn, plan_id)
        if int(current["version"]) != data.expected_version:
            raise DomainError("COMMERCIAL_PLAN_VERSION_CONFLICT", "O plano foi alterado por outro operador.", 409)
        if current["status"] == "archived":
            raise DomainError(
                "COMMERCIAL_PLAN_ARCHIVED",
                "Plano arquivado é imutável. Crie outro plano para voltar a ofertar o catálogo.",
                409,
            )
        fields = {
            key: payload[key]
            for key in ("name", "description", "currency", "billing_interval", "price_minor", "status")
            if key in payload
        }
        if "features" in payload:
            fields["features_json"] = canonical_json(payload["features"])
        if "limits" in payload:
            fields["limits_json"] = canonical_json(payload["limits"])
        projected_features = str(fields.get("features_json", current["features_json"]))
        projected_limits = str(fields.get("limits_json", current["limits_json"]))
        if len(projected_features.encode("utf-8")) + len(projected_limits.encode("utf-8")) > 32768:
            raise DomainError("COMMERCIAL_PLAN_CONFIGURATION_TOO_LARGE", "Features e limites excedem 32 KiB.", 422)
        now = iso_now()
        assignments = ",".join(f"{key}=?" for key in fields)
        changed = conn.execute(
            f"UPDATE commercial_plans SET {assignments},updated_at=?,version=version+1 WHERE id=? AND version=?",
            [*fields.values(), now, plan_id, data.expected_version],
        ).rowcount
        if changed != 1:
            raise DomainError("COMMERCIAL_PLAN_VERSION_CONFLICT", "O plano foi alterado por outro operador.", 409)
        result = _plan_response(
            {**current, **fields, "updated_at": now, "version": data.expected_version + 1}
        )
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="commercial_plan_updated",
            aggregate_type="commercial_plan",
            aggregate_id=plan_id,
            correlation_id=request.state.correlation_id,
            before=_plan_response(current),
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="CommercialPlanUpdated",
            aggregate_type="commercial_plan",
            aggregate_id=plan_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


@router.delete("/plans/{plan_id}", operation_id="archive_commercial_plan")
def archive_plan(
    plan_id: str,
    data: LifecycleInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = data.model_dump(mode="json")
    scope = f"commercial.plan.archive:{plan_id}"
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        request.state.store.transaction_lock(conn, f"commercial-plan:{plan_id}")
        current = _plan(conn, plan_id)
        if int(current["version"]) != data.expected_version:
            raise DomainError("COMMERCIAL_PLAN_VERSION_CONFLICT", "O plano foi alterado por outro operador.", 409)
        active_subscriptions = int(
            conn.execute(
                """SELECT COUNT(*) AS n FROM commercial_subscriptions
                   WHERE plan_id=? AND status IN ('active','trialing','suspended')""",
                (plan_id,),
            ).fetchone()["n"]
        )
        if active_subscriptions:
            raise DomainError(
                "COMMERCIAL_PLAN_HAS_SUBSCRIPTIONS",
                "Cancele ou migre as assinaturas antes de arquivar o plano.",
                409,
            )
        if current["status"] == "archived":
            raise DomainError("COMMERCIAL_PLAN_ALREADY_ARCHIVED", "O plano já está arquivado.", 409)
        now = iso_now()
        changed = conn.execute(
            """UPDATE commercial_plans SET status='archived',updated_at=?,version=version+1
               WHERE id=? AND version=? AND status<>'archived'""",
            (now, plan_id, data.expected_version),
        ).rowcount
        if changed != 1:
            raise DomainError("COMMERCIAL_PLAN_VERSION_CONFLICT", "O plano foi alterado por outro operador.", 409)
        result = _plan_response(
            {**current, "status": "archived", "updated_at": now, "version": data.expected_version + 1}
        )
        result["reason"] = data.reason
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="commercial_plan_archived",
            aggregate_type="commercial_plan",
            aggregate_id=plan_id,
            correlation_id=request.state.correlation_id,
            before={"status": current["status"]},
            after={"status": "archived"},
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="CommercialPlanArchived",
            aggregate_type="commercial_plan",
            aggregate_id=plan_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


@router.get("/tenants/{tenant_id}/subscription", operation_id="get_commercial_subscription")
def get_subscription(
    tenant_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    if not request.state.store.fetch_one("SELECT id FROM platform_tenants WHERE id=?", (tenant_id,)):
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    row = request.state.store.fetch_one(
        """SELECT id,tenant_id,plan_id,status,starts_at,current_period_end,trial_ends_at,
                  cancel_at_period_end,billing_mode,created_at,updated_at,version
           FROM commercial_subscriptions WHERE tenant_id=?""",
        (tenant_id,),
    )
    return {"subscription": _subscription_response(row) if row else None}


@router.put("/tenants/{tenant_id}/subscription", operation_id="set_commercial_subscription")
def set_subscription(
    tenant_id: str,
    data: SubscriptionInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = data.model_dump(mode="json")
    scope = f"commercial.subscription.set:{tenant_id}"
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        # O mesmo lock de archive do plano impede que uma assinatura ativa seja
        # criada entre a contagem de vínculos e a mudança de estado do catálogo.
        request.state.store.transaction_lock(conn, f"commercial-plan:{data.plan_id}")
        request.state.store.transaction_lock(conn, f"commercial-subscription:{tenant_id}")
        tenant = _tenant(conn, tenant_id)
        plan = _plan(conn, data.plan_id)
        if data.status in {"active", "trialing"} and plan["status"] != "active":
            raise DomainError("COMMERCIAL_PLAN_INACTIVE", "Somente plano ativo aceita nova assinatura ativa.", 409)
        current_row = conn.execute(
            """SELECT id,tenant_id,plan_id,status,starts_at,current_period_end,trial_ends_at,
                      cancel_at_period_end,billing_mode,created_at,updated_at,version
               FROM commercial_subscriptions WHERE tenant_id=?""",
            (tenant_id,),
        ).fetchone()
        current = dict(current_row) if current_row else None
        if current is None and data.expected_version != 0:
            raise DomainError("COMMERCIAL_SUBSCRIPTION_VERSION_CONFLICT", "A assinatura ainda não existe.", 409)
        if current is not None and int(current["version"]) != data.expected_version:
            raise DomainError("COMMERCIAL_SUBSCRIPTION_VERSION_CONFLICT", "A assinatura foi alterada por outro operador.", 409)
        if current is None and data.status not in {"active", "trialing"}:
            raise DomainError(
                "COMMERCIAL_SUBSCRIPTION_INITIAL_STATUS_INVALID",
                "Uma nova assinatura deve iniciar ativa ou em período de teste.",
                409,
            )
        if plan["status"] == "archived":
            canceling_same_plan = bool(
                current
                and current["plan_id"] == data.plan_id
                and data.status == "canceled"
            )
            if not canceling_same_plan:
                raise DomainError(
                    "COMMERCIAL_PLAN_ARCHIVED",
                    "Plano arquivado só pode ser referenciado para cancelar a assinatura que já o utiliza.",
                    409,
                )
        now = iso_now()
        starts_at = data.starts_at.astimezone(UTC).isoformat()
        period_end = data.current_period_end.astimezone(UTC).isoformat() if data.current_period_end else None
        trial_end = data.trial_ends_at.astimezone(UTC).isoformat() if data.trial_ends_at else None
        if current is None:
            subscription_id, version, created_at = uuid7(), 1, now
            conn.execute(
                """INSERT INTO commercial_subscriptions(
                       id,tenant_id,plan_id,status,starts_at,current_period_end,trial_ends_at,
                       cancel_at_period_end,billing_mode,created_at,updated_at,version
                   ) VALUES(?,?,?,?,?,?,?,?,'manual',?,?,1)""",
                (
                    subscription_id,
                    tenant_id,
                    data.plan_id,
                    data.status,
                    starts_at,
                    period_end,
                    trial_end,
                    1 if data.cancel_at_period_end else 0,
                    now,
                    now,
                ),
            )
            action, event_type = "commercial_subscription_created", "CommercialSubscriptionCreated"
        else:
            subscription_id, version, created_at = current["id"], data.expected_version + 1, current["created_at"]
            changed = conn.execute(
                """UPDATE commercial_subscriptions
                   SET plan_id=?,status=?,starts_at=?,current_period_end=?,trial_ends_at=?,
                       cancel_at_period_end=?,updated_at=?,version=version+1
                   WHERE tenant_id=? AND version=?""",
                (
                    data.plan_id,
                    data.status,
                    starts_at,
                    period_end,
                    trial_end,
                    1 if data.cancel_at_period_end else 0,
                    now,
                    tenant_id,
                    data.expected_version,
                ),
            ).rowcount
            if changed != 1:
                raise DomainError("COMMERCIAL_SUBSCRIPTION_VERSION_CONFLICT", "A assinatura foi alterada por outro operador.", 409)
            action, event_type = "commercial_subscription_updated", "CommercialSubscriptionUpdated"
        result = _subscription_response(
            {
                "id": subscription_id,
                "tenant_id": tenant_id,
                "plan_id": data.plan_id,
                "status": data.status,
                "starts_at": starts_at,
                "current_period_end": period_end,
                "trial_ends_at": trial_end,
                "cancel_at_period_end": 1 if data.cancel_at_period_end else 0,
                "billing_mode": "manual",
                "created_at": created_at,
                "updated_at": now,
                "version": version,
            }
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action=action,
            aggregate_type="commercial_subscription",
            aggregate_id=subscription_id,
            correlation_id=request.state.correlation_id,
            before=_subscription_response(current) if current else None,
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type=event_type,
            aggregate_type="commercial_subscription",
            aggregate_id=subscription_id,
            payload={**result, "tenant_code": tenant["code"], "plan_code": plan["code"]},
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


@router.put("/tenants/{tenant_id}/usage/{period}", operation_id="record_commercial_usage")
def record_usage(
    tenant_id: str,
    period: Annotated[str, Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    data: UsageSnapshotInput,
    request: Request,
    idempotency_key: IdempotencyKey,
    user: CurrentUser = Depends(require_roles(*WRITE_ROLES)),
):
    _require_platform(user)
    payload = {"period": period, **data.model_dump(mode="json")}
    scope = f"commercial.usage.set:{tenant_id}:{period}:{data.source}"
    with request.state.store.transaction() as conn:
        replay, fingerprint = begin_idempotent(conn, scope=scope, key=idempotency_key, payload=payload)
        if replay is not None:
            return replay
        request.state.store.transaction_lock(conn, f"commercial-usage:{tenant_id}:{period}:{data.source}")
        _tenant(conn, tenant_id)
        current_row = conn.execute(
            """SELECT id,tenant_id,period,source,metrics_json,captured_at,updated_at,version
               FROM commercial_usage_snapshots WHERE tenant_id=? AND period=? AND source=?""",
            (tenant_id, period, data.source),
        ).fetchone()
        current = dict(current_row) if current_row else None
        if current is None and data.expected_version != 0:
            raise DomainError("COMMERCIAL_USAGE_VERSION_CONFLICT", "O snapshot de uso ainda não existe.", 409)
        if current is not None and int(current["version"]) != data.expected_version:
            raise DomainError("COMMERCIAL_USAGE_VERSION_CONFLICT", "O snapshot de uso foi alterado por outro operador.", 409)
        serialized = canonical_json(data.metrics)
        if len(serialized.encode("utf-8")) > 16384:
            raise DomainError("COMMERCIAL_USAGE_TOO_LARGE", "O snapshot de uso excede 16 KiB.", 422)
        now = iso_now()
        if current is None:
            usage_id, version = uuid7(), 1
            conn.execute(
                """INSERT INTO commercial_usage_snapshots(
                       id,tenant_id,period,source,metrics_json,captured_at,updated_at,version
                   ) VALUES(?,?,?,?,?,?,?,1)""",
                (usage_id, tenant_id, period, data.source, serialized, now, now),
            )
        else:
            usage_id, version = current["id"], data.expected_version + 1
            changed = conn.execute(
                """UPDATE commercial_usage_snapshots
                   SET metrics_json=?,captured_at=?,updated_at=?,version=version+1
                   WHERE tenant_id=? AND period=? AND source=? AND version=?""",
                (serialized, now, now, tenant_id, period, data.source, data.expected_version),
            ).rowcount
            if changed != 1:
                raise DomainError("COMMERCIAL_USAGE_VERSION_CONFLICT", "O snapshot de uso foi alterado por outro operador.", 409)
        result = _usage_response(
            {
                "id": usage_id,
                "tenant_id": tenant_id,
                "period": period,
                "source": data.source,
                "metrics_json": serialized,
                "captured_at": now,
                "updated_at": now,
                "version": version,
            }
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="commercial_usage_recorded",
            aggregate_type="commercial_usage",
            aggregate_id=usage_id,
            correlation_id=request.state.correlation_id,
            before=_usage_response(current) if current else None,
            after=result,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="CommercialUsageRecorded",
            aggregate_type="commercial_usage",
            aggregate_id=usage_id,
            payload=result,
            correlation_id=request.state.correlation_id,
        )
        finish_idempotent(conn, scope=scope, key=idempotency_key, fingerprint=fingerprint, result=result)
    return result


@router.get("/tenants/{tenant_id}/usage", operation_id="list_commercial_usage")
def list_usage(
    tenant_id: str,
    request: Request,
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(default=100, ge=1, le=200),
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    if not request.state.store.fetch_one("SELECT id FROM platform_tenants WHERE id=?", (tenant_id,)):
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    where = "tenant_id=?"
    params: list[Any] = [tenant_id]
    if period:
        where += " AND period=?"
        params.append(period)
    params.append(limit)
    rows = request.state.store.fetch_all(
        f"""SELECT id,tenant_id,period,source,metrics_json,captured_at,updated_at,version
            FROM commercial_usage_snapshots WHERE {where}
            ORDER BY period DESC,source LIMIT ?""",
        params,
    )
    return {"items": [_usage_response(row) for row in rows]}


@router.get("/tenants/{tenant_id}/entitlements", operation_id="get_commercial_entitlements")
def get_entitlements(
    tenant_id: str,
    request: Request,
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    user: CurrentUser = Depends(require_roles(*READ_ROLES)),
):
    _require_platform(user)
    period = period or datetime.now(UTC).strftime("%Y-%m")
    tenant = request.state.store.fetch_one(
        "SELECT id,code,legal_name,trade_name,status FROM platform_tenants WHERE id=?",
        (tenant_id,),
    )
    if not tenant:
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
    subscription = request.state.store.fetch_one(
        """SELECT id,tenant_id,plan_id,status,starts_at,current_period_end,trial_ends_at,
                  cancel_at_period_end,billing_mode,created_at,updated_at,version
           FROM commercial_subscriptions WHERE tenant_id=?""",
        (tenant_id,),
    )
    plan = (
        request.state.store.fetch_one(
            """SELECT id,code,name,description,currency,billing_interval,price_minor,features_json,
                      limits_json,status,created_at,updated_at,version
               FROM commercial_plans WHERE id=?""",
            (subscription["plan_id"],),
        )
        if subscription
        else None
    )
    usage_rows = request.state.store.fetch_all(
        "SELECT metrics_json FROM commercial_usage_snapshots WHERE tenant_id=? AND period=?",
        (tenant_id, period),
    )
    usage: dict[str, int] = {}
    for row in usage_rows:
        for name, value in json_object(row.get("metrics_json")).items():
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                usage[name] = usage.get(name, 0) + value
    partner = request.state.store.fetch_one(
        """SELECT p.id,p.code,p.trade_name,p.status
           FROM commercial_partner_tenants pt
           JOIN commercial_partners p ON p.id=pt.partner_id
           WHERE pt.tenant_id=?""",
        (tenant_id,),
    )
    effective = plan_entitlements(subscription=subscription, plan=plan, usage=usage)
    return {
        "tenant": {
            "id": tenant["id"],
            "code": tenant["code"],
            "trade_name": tenant["trade_name"],
            "status": tenant["status"],
        },
        "partner": partner,
        "subscription": _subscription_response(subscription) if subscription else None,
        "plan": _plan_response(plan) if plan else None,
        "period": period,
        "entitlements": effective,
        "commercial_policy": {
            "billing_mode": "manual",
            "automatic_charging": False,
            "external_billing_provider": None,
            "usage_collection": "administrative_snapshots",
            "entitlement_enforcement": "informational",
        },
    }
