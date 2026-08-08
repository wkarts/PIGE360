from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import INTEGRATION_ROLES, require, tenant
from app.shared.application.idempotency import canonical_hash
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit
from app.shared.integrations.providers import (
    CloudflareProvider,
    DisabledTransport,
    EvolutionProvider,
    IntegrationError,
    MailcowProvider,
    SecretResolver,
    build_provider,
)
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["integrations"])

BUILT_INS = [
    ("cloudflare", "CloudflareDnsProvider"),
    ("mail", "MailcowProvider"),
    ("communication", "EvolutionApiProvider"),
    ("fiscal", "SefazNfeProvider"),
    ("fiscal", "NationalNfseProvider"),
    ("banking", "BankingProvider"),
    ("government", "GovBrAdvancedSignatureProvider"),
    ("ibpt", "WWSoftwaresCsvProvider"),
]

_PROVIDER_ALIASES = {
    "cloudflare": {"cloudflare", "CloudflareDnsProvider"},
    "mailcow": {"mailcow", "MailcowProvider"},
    "evolution": {"evolution", "EvolutionApiProvider"},
}


class IntegrationConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    environment: Literal["homologation", "production"] | None = None
    capabilities: list[str] | None = None
    secret_reference: str | None = Field(default=None, max_length=120)
    config: dict[str, Any] | None = None
    state: Literal["not_configured", "configured", "suspended", "archived"] | None = None


class CloudflareDnsInput(BaseModel):
    zone_id: str = Field(min_length=3, max_length=100)
    record_type: Literal["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA"] = "CNAME"
    name: str = Field(min_length=1, max_length=253)
    content: str = Field(min_length=1, max_length=2048)
    proxied: bool = True
    ttl: int = Field(default=1, ge=1, le=86400)
    comment: str = Field(default="PIGE360", max_length=200)


class CloudflareHostnameInput(BaseModel):
    zone_id: str = Field(min_length=3, max_length=100)
    hostname: str = Field(min_length=3, max_length=253)
    ssl_method: Literal["http", "txt", "email"] = "http"


class MailboxCreateInput(BaseModel):
    local_part: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    domain: str = Field(min_length=3, max_length=253)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=256)
    quota_mb: int = Field(default=1024, ge=64, le=102400)


class MailboxStateInput(BaseModel):
    active: bool


class EvolutionTextInput(BaseModel):
    instance: str = Field(min_length=1, max_length=120)
    number: str = Field(pattern=r"^[0-9]{8,20}$")
    text: str = Field(min_length=1, max_length=4096)
    delay_ms: int = Field(default=0, ge=0, le=30000)


def _secrets_root(request: Request) -> Path:
    settings = request.app.state.settings
    if settings.environment in {"production", "staging"}:
        return Path("/run/secrets")
    return settings.data_root / "integration-secrets"


def _transport(request: Request):
    injected = getattr(request.app.state, "integration_transport", None)
    if injected is not None:
        return injected
    if request.app.state.settings.integration_remote_enabled:
        return None
    return DisabledTransport()


def _decode(row: dict) -> dict:
    result = dict(row)
    for source, target, default in (("capabilities_json", "capabilities", []), ("config_json", "config", {})):
        raw = result.pop(source, None)
        try:
            result[target] = json.loads(raw) if raw else default
        except (TypeError, json.JSONDecodeError):
            result[target] = default
    # Nunca exponha referência de segredo no status público do tenant além de booleano.
    if "secret_reference" in result:
        result["secret_configured"] = bool(result.pop("secret_reference"))
    return result


def _connection(request: Request, user: CurrentUser, connection_id: str) -> dict:
    tid = tenant(user)
    row = request.state.store.fetch_one(
        "SELECT * FROM integration_connections WHERE tenant_id=? AND id=?",
        (tid, connection_id),
    )
    if not row:
        raise DomainError("INTEGRATION_CONNECTION_NOT_FOUND", "Conexão de integração não localizada.", 404)
    # Internamente precisamos da secret_reference; a decodificação aqui não pode removê-la.
    result = dict(row)
    for source, target, default in (("capabilities_json", "capabilities", []), ("config_json", "config", {})):
        raw = result.pop(source, None)
        try:
            result[target] = json.loads(raw) if raw else default
        except (TypeError, json.JSONDecodeError):
            result[target] = default
    return result


def _provider(request: Request, row: dict, kind: str, capability: str):
    if row["provider"] not in _PROVIDER_ALIASES[kind]:
        raise DomainError("INTEGRATION_PROVIDER_MISMATCH", f"A conexão não é do provider {kind}.", 409)
    capabilities = set(row.get("capabilities") or [])
    if capability not in capabilities and "*" not in capabilities:
        raise DomainError("INTEGRATION_CAPABILITY_NOT_ENABLED", f"Capability '{capability}' não está habilitada nesta conexão.", 403)
    if row.get("state") in {"suspended", "archived"}:
        raise DomainError("INTEGRATION_CONNECTION_INACTIVE", "A conexão está suspensa ou arquivada.", 409)
    secret = SecretResolver(_secrets_root(request)).resolve(row.get("secret_reference"))
    try:
        return build_provider(row["provider"], config=row.get("config", {}), secret=secret, transport=_transport(request))
    except IntegrationError as exc:
        raise _domain_from_integration(exc) from exc


def _domain_from_integration(exc: IntegrationError) -> DomainError:
    status = 424 if exc.code.startswith("INTEGRATION_SECRET") else (503 if exc.retryable else 409)
    if exc.status in {400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504}:
        status = 424 if exc.status < 500 else 503
    return DomainError(exc.code, str(exc), status)


def _operation_begin(request: Request, *, tenant_id: str, connection_id: str, capability: str, key: str, body: dict[str, Any]) -> dict | None:
    request_hash = canonical_hash(body)
    existing = request.state.store.fetch_one(
        "SELECT request_hash,state,response_json,error FROM integration_operation_keys WHERE tenant_id=? AND connection_id=? AND idempotency_key=?",
        (tenant_id, connection_id, key),
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise DomainError("IDEMPOTENCY_CONFLICT", "A mesma chave foi reutilizada com conteúdo diferente.", 409)
        if existing["state"] == "completed":
            return json.loads(existing["response_json"] or "{}")
        raise DomainError(
            "INTEGRATION_OPERATION_NOT_REPLAYABLE",
            "Esta chave já iniciou uma operação externa sem conclusão reutilizável. Reconcilie o provider antes de usar uma nova chave.",
            409,
        )
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO integration_operation_keys(tenant_id,connection_id,idempotency_key,capability,request_hash,state,response_json,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (tenant_id, connection_id, key, capability, request_hash, "in_progress", None, None, now, now),
        )
    return None


def _operation_finish(request: Request, *, tenant_id: str, connection_id: str, capability: str, key: str, user: CurrentUser, result: dict[str, Any], audit_action: str) -> None:
    finished = iso_now()
    run_id = uuid7()
    with request.state.store.transaction() as conn:
        conn.execute(
            "UPDATE integration_operation_keys SET state='completed',response_json=?,error=NULL,updated_at=? WHERE tenant_id=? AND connection_id=? AND idempotency_key=?",
            (json.dumps(result, ensure_ascii=False, sort_keys=True), finished, tenant_id, connection_id, key),
        )
        conn.execute(
            "INSERT INTO integration_runs(id,tenant_id,connection_id,direction,capability,state,cursor,stats_json,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, tenant_id, connection_id, "outbound", capability, "completed", None, json.dumps(result, ensure_ascii=False, sort_keys=True), None, finished, finished),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action=audit_action,
            aggregate_type="integration_connection",
            aggregate_id=connection_id,
            correlation_id=request.state.correlation_id,
            after=result,
        )


def _operation_fail(request: Request, *, tenant_id: str, connection_id: str, capability: str, key: str, user: CurrentUser, exc: IntegrationError) -> None:
    finished = iso_now()
    safe_error = f"{exc.code}: {str(exc)[:500]}"
    with request.state.store.transaction() as conn:
        conn.execute(
            "UPDATE integration_operation_keys SET state='failed',error=?,updated_at=? WHERE tenant_id=? AND connection_id=? AND idempotency_key=?",
            (safe_error, finished, tenant_id, connection_id, key),
        )
        conn.execute(
            "INSERT INTO integration_runs(id,tenant_id,connection_id,direction,capability,state,cursor,stats_json,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (uuid7(), tenant_id, connection_id, "outbound", capability, "failed", None, "{}", safe_error, finished, finished),
        )
        add_audit(
            conn,
            tenant_id=tenant_id,
            actor_id=user.id,
            action="external_operation_failed",
            aggregate_type="integration_connection",
            aggregate_id=connection_id,
            correlation_id=request.state.correlation_id,
            after={"capability": capability, "code": exc.code, "retryable": exc.retryable},
        )


@router.get("/integrations/providers/status", operation_id="integration_provider_status")
def provider_status(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    rows = request.state.store.fetch_all(
        "SELECT id,provider,name,state,last_health_at,last_health_state,capabilities_json,config_json,secret_reference FROM integration_connections WHERE tenant_id=? ORDER BY name",
        (tid,),
    )
    connections = [_decode(row) for row in rows]
    by_provider: dict[str, list[dict]] = {}
    for item in connections:
        by_provider.setdefault(item["provider"], []).append(item)
    items = []
    for domain, provider in BUILT_INS:
        aliases = {provider, {"CloudflareDnsProvider": "cloudflare", "MailcowProvider": "mailcow", "EvolutionApiProvider": "evolution"}.get(provider, provider)}
        configured = [row for key in aliases for row in by_provider.get(key, [])]
        state = "not_configured"
        if configured:
            states = {row.get("last_health_state") or row.get("state") for row in configured}
            state = "healthy" if "healthy" in states else ("degraded" if "degraded" in states or "failed" in states else "configured")
        if provider == "WWSoftwaresCsvProvider" and not configured:
            state = "disabled_offline_build"
        items.append({"domain": domain, "provider": provider, "status": state, "connections": len(configured), "mock_active_in_production": False})
    return {"items": items, "connections": connections, "remote_operations_enabled": request.app.state.settings.integration_remote_enabled}


@router.patch("/integration-connections/{connection_id}", operation_id="update_integration_connection")
def update_connection(connection_id: str, data: IntegrationConnectionUpdate, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    row = _connection(request, user, connection_id)
    tid = tenant(user)
    patch = data.model_dump(exclude_unset=True)
    name = patch.get("name", row["name"])
    environment = patch.get("environment", row["environment"])
    capabilities = patch.get("capabilities", row["capabilities"])
    config = patch.get("config", row["config"])
    secret_reference = patch.get("secret_reference", row.get("secret_reference"))
    state = patch.get("state", row["state"])
    if state == "configured" and not secret_reference:
        state = "not_configured"
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute(
            "UPDATE integration_connections SET name=?,environment=?,capabilities_json=?,secret_reference=?,config_json=?,state=?,updated_at=? WHERE tenant_id=? AND id=?",
            (name, environment, json.dumps(capabilities), secret_reference, json.dumps(config), state, now, tid, connection_id),
        )
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="update", aggregate_type="integration_connection", aggregate_id=connection_id, correlation_id=request.state.correlation_id, after={"name": name, "environment": environment, "capabilities": capabilities, "state": state, "secret_configured": bool(secret_reference)})
    return {"id": connection_id, "name": name, "environment": environment, "capabilities": capabilities, "state": state, "secret_configured": bool(secret_reference)}


@router.get("/integration-connections/{connection_id}/health", operation_id="get_integration_connection_health")
def connection_health(connection_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    row = _connection(request, user, connection_id)
    return {"connection_id": connection_id, "state": row["state"], "last_health_at": row.get("last_health_at"), "last_health_state": row.get("last_health_state"), "provider": row["provider"]}


@router.post("/integration-connections/{connection_id}/test", operation_id="test_integration_connection")
def test_connection(connection_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    row = _connection(request, user, connection_id)
    run_id = uuid7()
    started = iso_now()
    try:
        secret = SecretResolver(_secrets_root(request)).resolve(row.get("secret_reference"))
        provider = build_provider(row["provider"], config=row.get("config", {}), secret=secret, transport=_transport(request))
        health = provider.health()
        state = health.status
        result = {"connection_id": connection_id, "provider": row["provider"], "status": state, "latency_ms": health.latency_ms, "details": health.details, "checked_at": iso_now()}
        with request.state.store.transaction() as conn:
            conn.execute("UPDATE integration_connections SET state=?,last_health_at=?,last_health_state=?,updated_at=? WHERE tenant_id=? AND id=?", ("configured" if state == "healthy" else "degraded", result["checked_at"], state, result["checked_at"], tid, connection_id))
            conn.execute("INSERT INTO integration_runs(id,tenant_id,connection_id,direction,capability,state,cursor,stats_json,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, tid, connection_id, "outbound", "health", state, None, json.dumps({"latency_ms": health.latency_ms, "details": health.details}, ensure_ascii=False, sort_keys=True), None, started, result["checked_at"]))
            add_audit(conn, tenant_id=tid, actor_id=user.id, action="health_check", aggregate_type="integration_connection", aggregate_id=connection_id, correlation_id=request.state.correlation_id, after=result)
        return result
    except IntegrationError as exc:
        finished = iso_now()
        with request.state.store.transaction() as conn:
            conn.execute("UPDATE integration_connections SET state='degraded',last_health_at=?,last_health_state='failed',updated_at=? WHERE tenant_id=? AND id=?", (finished, finished, tid, connection_id))
            conn.execute("INSERT INTO integration_runs(id,tenant_id,connection_id,direction,capability,state,cursor,stats_json,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, tid, connection_id, "outbound", "health", "failed", None, "{}", f"{exc.code}: {str(exc)[:500]}", started, finished))
            add_audit(conn, tenant_id=tid, actor_id=user.id, action="health_check_failed", aggregate_type="integration_connection", aggregate_id=connection_id, correlation_id=request.state.correlation_id, after={"code": exc.code, "retryable": exc.retryable})
        raise _domain_from_integration(exc) from exc


@router.post("/integration-connections/{connection_id}/cloudflare/dns", operation_id="cloudflare_upsert_dns")
def cloudflare_dns(connection_id: str, data: CloudflareDnsInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    body = data.model_dump(mode="json")
    row = _connection(request, user, connection_id)
    provider = _provider(request, row, "cloudflare", "dns")
    cached = _operation_begin(request, tenant_id=tid, connection_id=connection_id, capability="dns", key=idempotency_key, body=body)
    if cached is not None:
        return cached
    assert isinstance(provider, CloudflareProvider)
    try:
        external = provider.upsert_dns_record(**body)
        result = {"connection_id": connection_id, "record_id": external.get("id"), "name": external.get("name", data.name), "type": external.get("type", data.record_type), "content": external.get("content", data.content), "proxied": external.get("proxied", data.proxied), "state": "applied"}
        _operation_finish(request, tenant_id=tid, connection_id=connection_id, capability="dns", key=idempotency_key, user=user, result=result, audit_action="cloudflare_dns_upsert")
        return result
    except IntegrationError as exc:
        _operation_fail(request, tenant_id=tid, connection_id=connection_id, capability="dns", key=idempotency_key, user=user, exc=exc)
        raise _domain_from_integration(exc) from exc


@router.post("/integration-connections/{connection_id}/cloudflare/custom-hostnames", operation_id="cloudflare_create_custom_hostname")
def cloudflare_hostname(connection_id: str, data: CloudflareHostnameInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    body = data.model_dump(mode="json")
    row = _connection(request, user, connection_id)
    provider = _provider(request, row, "cloudflare", "custom_hostnames")
    cached = _operation_begin(request, tenant_id=tid, connection_id=connection_id, capability="custom_hostnames", key=idempotency_key, body=body)
    if cached is not None:
        return cached
    assert isinstance(provider, CloudflareProvider)
    try:
        external = provider.create_custom_hostname(**body)
        ssl = external.get("ssl") if isinstance(external.get("ssl"), dict) else {}
        result = {"connection_id": connection_id, "custom_hostname_id": external.get("id"), "hostname": external.get("hostname", data.hostname), "status": external.get("status", "pending"), "ssl_status": ssl.get("status", "pending"), "state": "requested"}
        _operation_finish(request, tenant_id=tid, connection_id=connection_id, capability="custom_hostnames", key=idempotency_key, user=user, result=result, audit_action="cloudflare_custom_hostname_create")
        return result
    except IntegrationError as exc:
        _operation_fail(request, tenant_id=tid, connection_id=connection_id, capability="custom_hostnames", key=idempotency_key, user=user, exc=exc)
        raise _domain_from_integration(exc) from exc


@router.post("/integration-connections/{connection_id}/mailcow/mailboxes", operation_id="mailcow_create_mailbox")
def mailcow_create(connection_id: str, data: MailboxCreateInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    body = data.model_dump(mode="json")
    row = _connection(request, user, connection_id)
    provider = _provider(request, row, "mailcow", "mailboxes")
    cached = _operation_begin(request, tenant_id=tid, connection_id=connection_id, capability="mailboxes", key=idempotency_key, body=body)
    if cached is not None:
        return cached
    assert isinstance(provider, MailcowProvider)
    try:
        provider.create_mailbox(**body)
        result = {"connection_id": connection_id, "email": f"{data.local_part}@{data.domain}", "state": "provisioned"}
        _operation_finish(request, tenant_id=tid, connection_id=connection_id, capability="mailboxes", key=idempotency_key, user=user, result=result, audit_action="mailcow_mailbox_create")
        return result
    except IntegrationError as exc:
        _operation_fail(request, tenant_id=tid, connection_id=connection_id, capability="mailboxes", key=idempotency_key, user=user, exc=exc)
        raise _domain_from_integration(exc) from exc


@router.patch("/integration-connections/{connection_id}/mailcow/mailboxes/{email}/state", operation_id="mailcow_set_mailbox_state")
def mailcow_state(connection_id: str, email: str, data: MailboxStateInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    if "@" not in email or len(email) > 254:
        raise DomainError("MAILBOX_EMAIL_INVALID", "E-mail da mailbox é inválido.", 422)
    tid = tenant(user)
    body = {"email": email.lower(), "active": data.active}
    row = _connection(request, user, connection_id)
    provider = _provider(request, row, "mailcow", "mailboxes")
    cached = _operation_begin(request, tenant_id=tid, connection_id=connection_id, capability="mailboxes", key=idempotency_key, body=body)
    if cached is not None:
        return cached
    assert isinstance(provider, MailcowProvider)
    try:
        provider.suspend_mailbox(email.lower(), active=data.active)
        result = {"connection_id": connection_id, "email": email.lower(), "state": "active" if data.active else "suspended"}
        _operation_finish(request, tenant_id=tid, connection_id=connection_id, capability="mailboxes", key=idempotency_key, user=user, result=result, audit_action="mailcow_mailbox_state")
        return result
    except IntegrationError as exc:
        _operation_fail(request, tenant_id=tid, connection_id=connection_id, capability="mailboxes", key=idempotency_key, user=user, exc=exc)
        raise _domain_from_integration(exc) from exc


@router.post("/integration-connections/{connection_id}/evolution/messages/text", operation_id="evolution_send_text")
def evolution_send(connection_id: str, data: EvolutionTextInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, INTEGRATION_ROLES)
    tid = tenant(user)
    body = data.model_dump(mode="json")
    row = _connection(request, user, connection_id)
    provider = _provider(request, row, "evolution", "send_text")
    cached = _operation_begin(request, tenant_id=tid, connection_id=connection_id, capability="send_text", key=idempotency_key, body=body)
    if cached is not None:
        return cached
    assert isinstance(provider, EvolutionProvider)
    try:
        external = provider.send_text(**body)
        message_id = None
        if isinstance(external, dict):
            message_id = external.get("key", {}).get("id") if isinstance(external.get("key"), dict) else external.get("id") or external.get("messageId")
        result = {"connection_id": connection_id, "provider_message_id": message_id, "number": data.number, "state": "submitted"}
        _operation_finish(request, tenant_id=tid, connection_id=connection_id, capability="send_text", key=idempotency_key, user=user, result=result, audit_action="evolution_text_submit")
        return result
    except IntegrationError as exc:
        _operation_fail(request, tenant_id=tid, connection_id=connection_id, capability="send_text", key=idempotency_key, user=user, exc=exc)
        raise _domain_from_integration(exc) from exc
