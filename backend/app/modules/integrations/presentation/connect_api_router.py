from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

import app.modules.integrations.presentation.router as legacy
from app.modules.operations.common import INTEGRATION_ROLES, require, tenant
from app.shared.domain.ids import iso_now
from app.shared.events.records import add_audit
from app.shared.integrations.connect_api import (
    CONNECT_API_PROVIDER_ALIASES,
    ConnectApiProvider,
    canonical_provider_name,
)
from app.shared.integrations.providers import IntegrationError, SecretResolver, build_provider
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["integrations"])


class ConnectApiTextInput(BaseModel):
    instance: str = Field(min_length=1, max_length=120)
    number: str = Field(pattern=r"^[0-9]{8,20}$")
    text: str = Field(min_length=1, max_length=4096)
    delay_ms: int = Field(default=0, ge=0, le=30000)


_original_decode = legacy._decode
_original_connection = legacy._connection


def _canonical_decode(row: dict) -> dict:
    result = _original_decode(row)
    raw_provider = str(result.get("provider") or "")
    result["provider"] = canonical_provider_name(raw_provider)
    if result["provider"] == "connect_api":
        result["provider_display_name"] = "Connect API"
        result["meta_compatible"] = True
        result["legacy_alias_detected"] = raw_provider != "connect_api"
    return result


def _canonical_connection(request: Request, user: CurrentUser, connection_id: str) -> dict:
    result = _original_connection(request, user, connection_id)
    result["provider"] = canonical_provider_name(str(result.get("provider") or ""))
    return result


# Os endpoints existentes resolvem estes nomes globais no momento da chamada.
# Assim registros antigos funcionam sem que Evolution volte a aparecer na API.
legacy._decode = _canonical_decode
legacy._connection = _canonical_connection
legacy.BUILT_INS = [
    ("cloudflare", "CloudflareDnsProvider"),
    ("mail", "MailcowProvider"),
    ("communication", "connect_api"),
    ("fiscal", "SefazNfeProvider"),
    ("fiscal", "NationalNfseProvider"),
    ("banking", "BankingProvider"),
    ("government", "GovBrAdvancedSignatureProvider"),
    ("ibpt", "WWSoftwaresCsvProvider"),
]
legacy._PROVIDER_ALIASES["connect_api"] = set(CONNECT_API_PROVIDER_ALIASES)

# Remove somente a superfície HTTP legada; aliases de persistência continuam
# internos para permitir atualização sem indisponibilidade de tenants antigos.
legacy.router.routes[:] = [
    route
    for route in legacy.router.routes
    if getattr(route, "operation_id", None) != "evolution_send_text"
    and "/evolution/" not in str(getattr(route, "path", "")).lower()
]


def _connect_provider(request: Request, row: dict, capability: str) -> ConnectApiProvider:
    provider_name = str(row.get("provider") or "")
    if provider_name != "connect_api":
        raise DomainError("INTEGRATION_PROVIDER_MISMATCH", "A conexão não é do provider Connect API.", 409)
    capabilities = set(row.get("capabilities") or [])
    if capability not in capabilities and "*" not in capabilities:
        raise DomainError(
            "INTEGRATION_CAPABILITY_NOT_ENABLED",
            f"Capability '{capability}' não está habilitada nesta conexão.",
            403,
        )
    if row.get("state") in {"suspended", "archived"}:
        raise DomainError("INTEGRATION_CONNECTION_INACTIVE", "A conexão está suspensa ou arquivada.", 409)
    secret = SecretResolver(legacy._secrets_root(request)).resolve(row.get("secret_reference"))
    try:
        provider = build_provider(
            "connect_api",
            config=row.get("config", {}),
            secret=secret,
            transport=legacy._transport(request),
        )
    except IntegrationError as exc:
        raise legacy._domain_from_integration(exc) from exc
    assert isinstance(provider, ConnectApiProvider)
    return provider


def _migrate_provider_alias_if_needed(
    request: Request, *, connection_id: str, tenant_id: str, user: CurrentUser
) -> bool:
    raw = request.state.store.fetch_one(
        "SELECT provider FROM integration_connections WHERE tenant_id=? AND id=?",
        (tenant_id, connection_id),
    )
    if not raw:
        raise DomainError("INTEGRATION_CONNECTION_NOT_FOUND", "Conexão de integração não localizada.", 404)
    previous = str(raw.get("provider") or "")
    if previous == "connect_api":
        return False
    if previous not in CONNECT_API_PROVIDER_ALIASES:
        raise DomainError("INTEGRATION_PROVIDER_MISMATCH", "A conexão não é compatível com Connect API.", 409)
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute(
            "UPDATE integration_connections SET provider='connect_api',updated_at=? WHERE tenant_id=? AND id=?",
            (now, tenant_id, connection_id),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="provider_alias_migrated",
            aggregate_type="integration_connection",
            aggregate_id=connection_id,
            correlation_id=request.state.correlation_id,
            before={"provider": "legacy_communication_provider"},
            after={"provider": "connect_api", "provider_display_name": "Connect API"},
            reason="Migração canônica de provider de comunicação",
        )
    return True


@router.post(
    "/integration-connections/{connection_id}/connect-api/migrate",
    operation_id="connect_api_migrate_legacy_connection",
)
def migrate_connect_api_connection(
    connection_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    migrated = _migrate_provider_alias_if_needed(
        request, connection_id=connection_id, tenant_id=tid, user=user
    )
    return {
        "connection_id": connection_id,
        "provider": "connect_api",
        "provider_display_name": "Connect API",
        "meta_compatible": True,
        "migrated": migrated,
    }


@router.post(
    "/integration-connections/{connection_id}/connect-api/messages/text",
    operation_id="connect_api_send_text",
)
def connect_api_send_text(
    connection_id: str,
    data: ConnectApiTextInput,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    _migrate_provider_alias_if_needed(
        request, connection_id=connection_id, tenant_id=tid, user=user
    )
    row = legacy._connection(request, user, connection_id)
    provider = _connect_provider(request, row, "send_text")
    body = data.model_dump(mode="json")
    cached = legacy._operation_begin(
        request,
        tenant_id=tid,
        connection_id=connection_id,
        capability="send_text",
        key=idempotency_key,
        body=body,
    )
    if cached is not None:
        return cached
    try:
        external = provider.send_text(**body)
        message_id = None
        if isinstance(external, dict):
            key = external.get("key")
            if isinstance(key, dict):
                message_id = key.get("id")
            message_id = message_id or external.get("id") or external.get("messageId") or external.get("message_id")
        result: dict[str, Any] = {
            "connection_id": connection_id,
            "provider": "connect_api",
            "provider_display_name": "Connect API",
            "meta_compatible": True,
            "provider_message_id": message_id,
            "number": data.number,
            "state": "submitted",
        }
        legacy._operation_finish(
            request,
            tenant_id=tid,
            connection_id=connection_id,
            capability="send_text",
            key=idempotency_key,
            user=user,
            result=result,
            audit_action="connect_api_text_submit",
        )
        return result
    except IntegrationError as exc:
        legacy._operation_fail(
            request,
            tenant_id=tid,
            connection_id=connection_id,
            capability="send_text",
            key=idempotency_key,
            user=user,
            exc=exc,
        )
        raise legacy._domain_from_integration(exc) from exc
