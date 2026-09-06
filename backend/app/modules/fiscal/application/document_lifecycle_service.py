from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request

from app.modules.fiscal.presentation.document_lifecycle_schemas import (
    FiscalCertificateMetadataCreate,
    FiscalDocumentQueryRequest,
    FiscalDocumentSubstituteRequest,
    FiscalInutilizationCreate,
    FiscalProviderConfigurationCreate,
    FiscalProviderConfigurationPatch,
    FiscalProviderEventCreate,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.integrations.providers import IntegrationError, SecretResolver, build_provider
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser
from app.shared.tenant_quotas import tenant_quota_limit

PROVIDERS = {
    "SefazNfeProvider": {"documents": {"NF-e"}, "certificate_required": True},
    "SefazNfceProvider": {"documents": {"NFC-e"}, "certificate_required": True},
    "NationalNfseProvider": {"documents": {"NFS-e"}, "certificate_required": False},
    "MunicipalNfseProvider": {"documents": {"NFS-e"}, "certificate_required": False},
    "ThirdPartyFiscalProvider": {"documents": {"NF-e", "NFC-e", "NFS-e"}, "certificate_required": False},
}


def _secret_root(request: Request) -> Path:
    settings = request.app.state.settings
    if settings.environment in {"production", "staging"}:
        return Path("/run/secrets")
    return settings.data_root / "integration-secrets"


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _provider_status(request: Request, tenant_id: str, data: dict[str, Any]) -> tuple[str, str]:
    provider_code = str(data["provider_code"])
    endpoint = str(data.get("endpoint_url") or "").strip()
    secret_ref = str(data.get("secret_ref") or "").strip()
    enabled = bool(data.get("enabled"))
    if not enabled:
        return "not_configured", "Provider desabilitado por configuração."
    if not endpoint or not secret_ref:
        return "not_configured", "Endpoint HTTPS e referência de credencial são obrigatórios."
    try:
        SecretResolver(_secret_root(request)).resolve(secret_ref)
    except IntegrationError as exc:
        return "not_configured", exc.code
    if PROVIDERS[provider_code]["certificate_required"]:
        certificate_id = data.get("certificate_metadata_id")
        if not certificate_id:
            return "not_configured", "Certificado A1 por referência é obrigatório para este provider."
        row = request.state.store.fetch_one(
            "SELECT * FROM fiscal_certificate_metadata WHERE tenant_id=? AND id=? AND status='active'",
            (tenant_id, certificate_id),
        )
        if not row:
            return "not_configured", "Metadados de certificado não encontrados ou inativos."
        if str(row["valid_until"]) <= iso_now():
            return "expired_certificate", "Certificado fiscal expirado."
        try:
            SecretResolver(_secret_root(request)).resolve(row["secret_ref"])
        except IntegrationError as exc:
            return "not_configured", f"CERTIFICATE_{exc.code}"
    return "configured", "Configuração local completa; homologação externa não presumida."


def list_certificates(request: Request, tenant_id: str) -> dict[str, Any]:
    items = request.state.store.fetch_all(
        "SELECT * FROM fiscal_certificate_metadata WHERE tenant_id=? ORDER BY valid_until DESC,created_at DESC",
        (tenant_id,),
    )
    for item in items:
        item.pop("secret_ref", None)
        item["secret_configured"] = True
        item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
    return {"items": items}


def create_certificate(data: FiscalCertificateMetadataCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-certificate:{tenant_id}:{data.fingerprint_sha256}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        existing = conn.execute(
            "SELECT id FROM fiscal_certificate_metadata WHERE tenant_id=? AND fingerprint_sha256=?",
            (tenant_id, data.fingerprint_sha256),
        ).fetchone()
        if existing:
            raise DomainError("FISCAL_CERTIFICATE_EXISTS", "O fingerprint deste certificado já está cadastrado.", 409)
        certificate_id = uuid7(); now = iso_now()
        state = "expired" if data.valid_until.astimezone(UTC) <= datetime.now(UTC) else "active"
        conn.execute(
            """INSERT INTO fiscal_certificate_metadata(
                   id,tenant_id,certificate_type,subject_name,subject_document,serial_number,issuer_name,valid_from,valid_until,
                   fingerprint_sha256,secret_ref,status,metadata_json,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                certificate_id, tenant_id, data.certificate_type, data.subject_name, data.subject_document,
                data.serial_number, data.issuer_name, data.valid_from.isoformat(), data.valid_until.isoformat(),
                data.fingerprint_sha256, data.secret_ref, state,
                json.dumps(data.metadata, ensure_ascii=False, sort_keys=True), now, now,
            ),
        )
        result = {
            "id": certificate_id, "certificate_type": data.certificate_type, "subject_name": data.subject_name,
            "subject_document": data.subject_document, "serial_number": data.serial_number, "issuer_name": data.issuer_name,
            "valid_from": data.valid_from.isoformat(), "valid_until": data.valid_until.isoformat(),
            "fingerprint_sha256": data.fingerprint_sha256, "secret_configured": True, "status": state,
        }
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="create", aggregate_type="fiscal_certificate_metadata", aggregate_id=certificate_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalCertificateMetadataCreated", aggregate_type="fiscal_certificate_metadata", aggregate_id=certificate_id, payload=result, correlation_id=request.state.correlation_id)
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return 201, result


def list_provider_configurations(request: Request, tenant_id: str) -> dict[str, Any]:
    items = request.state.store.fetch_all(
        "SELECT * FROM fiscal_provider_configurations WHERE tenant_id=? ORDER BY document_type,environment,display_name",
        (tenant_id,),
    )
    for item in items:
        item["capabilities"] = _loads(item.pop("capabilities_json", "[]"), [])
        item["settings"] = _loads(item.pop("settings_json", "{}"), {})
        item["secret_configured"] = bool(item.pop("secret_ref", None))
    return {"items": items, "remote_execution_enabled": request.app.state.settings.integration_remote_enabled}


def create_provider_configuration(data: FiscalProviderConfigurationCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int, dict[str, Any]]:
    if data.document_type not in PROVIDERS[data.provider_code]["documents"]:
        raise DomainError("FISCAL_PROVIDER_DOCUMENT_UNSUPPORTED", "O provider selecionado não atende este tipo de documento.", 422)
    body = data.model_dump(mode="json")
    scope = f"fiscal-provider-config:{tenant_id}:{data.provider_code}:{data.document_type}:{data.environment}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        limit = tenant_quota_limit(
            request.app.state.data_router.control,
            tenant_id,
            "max_integrations",
        )
        request.state.store.transaction_lock(conn, f"tenant-integration-quota:{tenant_id}")
        if conn.execute(
            "SELECT 1 FROM fiscal_provider_configurations WHERE tenant_id=? AND provider_code=? AND document_type=? AND environment=?",
            (tenant_id, data.provider_code, data.document_type, data.environment),
        ).fetchone():
            raise DomainError("FISCAL_PROVIDER_CONFIG_EXISTS", "Já existe configuração deste provider/documento/ambiente.", 409)
        current_integrations = conn.execute(
            "SELECT COUNT(*) AS n FROM integration_connections WHERE tenant_id=? AND state<>'archived'",
            (tenant_id,),
        ).fetchone()
        if int(current_integrations["n"] if current_integrations else 0) >= limit:
            raise DomainError(
                "TENANT_QUOTA_EXCEEDED",
                f"A quota de integrações não arquivadas ({limit}) foi atingida.",
                409,
            )
        if data.certificate_metadata_id and not conn.execute(
            "SELECT 1 FROM fiscal_certificate_metadata WHERE tenant_id=? AND id=?", (tenant_id, data.certificate_metadata_id)
        ).fetchone():
            raise DomainError("FISCAL_CERTIFICATE_NOT_FOUND", "Certificado fiscal não localizado.", 404)
        config_id = uuid7(); now = iso_now()
        status, detail = _provider_status(request, tenant_id, body)
        integration_config = dict(data.settings)
        if data.endpoint_url:
            integration_config["base_url"] = data.endpoint_url
        integration_config["fiscal_provider_configuration_id"] = config_id
        if data.certificate_metadata_id:
            cert = conn.execute("SELECT secret_ref,fingerprint_sha256,valid_until FROM fiscal_certificate_metadata WHERE tenant_id=? AND id=?", (tenant_id, data.certificate_metadata_id)).fetchone()
            if cert:
                integration_config["certificate_secret_reference"] = cert["secret_ref"]
                integration_config["certificate_fingerprint_sha256"] = cert["fingerprint_sha256"]
                integration_config["certificate_valid_until"] = cert["valid_until"]
        conn.execute(
            """INSERT INTO integration_connections(id,tenant_id,provider,name,environment,capabilities_json,secret_reference,config_json,state,last_health_at,last_health_state,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (config_id, tenant_id, data.provider_code, data.display_name, data.environment, json.dumps(data.capabilities), data.secret_ref, json.dumps(integration_config, ensure_ascii=False, sort_keys=True), status, None, "not_checked", now, now),
        )
        conn.execute(
            """INSERT INTO fiscal_provider_configurations(
                   id,tenant_id,provider_code,display_name,document_type,environment,endpoint_url,secret_ref,certificate_metadata_id,
                   capabilities_json,settings_json,enabled,status,last_health_status,last_health_at,last_health_detail,webhook_tolerance_seconds,version,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (config_id, tenant_id, data.provider_code, data.display_name, data.document_type, data.environment, data.endpoint_url, data.secret_ref, data.certificate_metadata_id, json.dumps(data.capabilities), json.dumps(data.settings, ensure_ascii=False, sort_keys=True), 1 if data.enabled else 0, status, "not_checked", None, detail, data.webhook_tolerance_seconds, 1, now, now),
        )
        result = {"id": config_id, "provider_code": data.provider_code, "display_name": data.display_name, "document_type": data.document_type, "environment": data.environment, "capabilities": data.capabilities, "enabled": data.enabled, "status": status, "status_detail": detail, "secret_configured": bool(data.secret_ref), "certificate_metadata_id": data.certificate_metadata_id, "version": 1}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="create", aggregate_type="fiscal_provider_configuration", aggregate_id=config_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalProviderConfigurationCreated", aggregate_type="fiscal_provider_configuration", aggregate_id=config_id, payload=result, correlation_id=request.state.correlation_id)
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return 201, result


def patch_provider_configuration(configuration_id: str, data: FiscalProviderConfigurationPatch, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM fiscal_provider_configurations WHERE tenant_id=? AND id=?", (tenant_id, configuration_id))
    if not row:
        raise DomainError("FISCAL_PROVIDER_CONFIG_NOT_FOUND", "Configuração fiscal não localizada.", 404)
    if int(row["version"]) != data.expected_version:
        raise DomainError("VERSION_CONFLICT", "A configuração fiscal foi alterada por outro processo.", 409)
    patch = data.model_dump(exclude_unset=True, mode="json"); patch.pop("expected_version", None)
    current = dict(row)
    for key in ("display_name", "endpoint_url", "secret_ref", "certificate_metadata_id", "enabled", "webhook_tolerance_seconds"):
        if key in patch:
            current[key] = patch[key]
    if "capabilities" in patch:
        current["capabilities"] = patch["capabilities"]
    else:
        current["capabilities"] = _loads(current.get("capabilities_json"), [])
    if "settings" in patch:
        current["settings"] = patch["settings"]
    else:
        current["settings"] = _loads(current.get("settings_json"), {})
    status, detail = _provider_status(request, tenant_id, current)
    now = iso_now(); version = int(row["version"]) + 1
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"tenant-integration-quota:{tenant_id}")
        connection = conn.execute(
            "SELECT state FROM integration_connections WHERE tenant_id=? AND id=?",
            (tenant_id, configuration_id),
        ).fetchone()
        if not connection:
            raise DomainError(
                "INTEGRATION_CONNECTION_NOT_FOUND",
                "Conexão de integração fiscal não localizada.",
                409,
            )
        if connection["state"] == "archived" and status != "archived":
            limit = tenant_quota_limit(
                request.app.state.data_router.control,
                tenant_id,
                "max_integrations",
            )
            active = conn.execute(
                "SELECT COUNT(*) AS n FROM integration_connections WHERE tenant_id=? AND state<>'archived'",
                (tenant_id,),
            ).fetchone()
            if int(active["n"] if active else 0) >= limit:
                raise DomainError(
                    "TENANT_QUOTA_EXCEEDED",
                    f"A quota de integrações não arquivadas ({limit}) foi atingida.",
                    409,
                )
        changed = conn.execute(
            """UPDATE fiscal_provider_configurations SET display_name=?,endpoint_url=?,secret_ref=?,certificate_metadata_id=?,capabilities_json=?,settings_json=?,enabled=?,status=?,last_health_detail=?,webhook_tolerance_seconds=?,version=?,updated_at=? WHERE tenant_id=? AND id=? AND version=?""",
            (current["display_name"], current.get("endpoint_url"), current.get("secret_ref"), current.get("certificate_metadata_id"), json.dumps(current["capabilities"]), json.dumps(current["settings"], ensure_ascii=False, sort_keys=True), 1 if current.get("enabled") else 0, status, detail, current.get("webhook_tolerance_seconds", 300), version, now, tenant_id, configuration_id, row["version"]),
        )
        if changed.rowcount != 1:
            raise DomainError(
                "VERSION_CONFLICT",
                "A configuração fiscal foi alterada por outro processo.",
                409,
            )
        integration_config = dict(current["settings"])
        if current.get("endpoint_url"):
            integration_config["base_url"] = current["endpoint_url"]
        integration_config["fiscal_provider_configuration_id"] = configuration_id
        conn.execute("UPDATE integration_connections SET name=?,capabilities_json=?,secret_reference=?,config_json=?,state=?,updated_at=? WHERE tenant_id=? AND id=?", (current["display_name"], json.dumps(current["capabilities"]), current.get("secret_ref"), json.dumps(integration_config, ensure_ascii=False, sort_keys=True), status, now, tenant_id, configuration_id))
        result = {"id": configuration_id, "status": status, "status_detail": detail, "version": version, "enabled": bool(current.get("enabled")), "secret_configured": bool(current.get("secret_ref")), "capabilities": current["capabilities"]}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="update", aggregate_type="fiscal_provider_configuration", aggregate_id=configuration_id, correlation_id=request.state.correlation_id, before={"status": row["status"], "version": row["version"]}, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalProviderConfigurationUpdated", aggregate_type="fiscal_provider_configuration", aggregate_id=configuration_id, payload=result, correlation_id=request.state.correlation_id)
    return result


def provider_health(configuration_id: str, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM fiscal_provider_configurations WHERE tenant_id=? AND id=?", (tenant_id, configuration_id))
    if not row:
        raise DomainError("FISCAL_PROVIDER_CONFIG_NOT_FOUND", "Configuração fiscal não localizada.", 404)
    row = dict(row); status, detail = _provider_status(request, tenant_id, row); now = iso_now()
    if status != "configured":
        health = "not_configured" if status == "not_configured" else status
        checked = {"configuration_id": configuration_id, "health": health, "detail": detail, "remote_check_executed": False, "checked_at": now}
    elif not request.app.state.settings.integration_remote_enabled:
        checked = {"configuration_id": configuration_id, "health": "configured_unchecked", "detail": "I/O remoto desabilitado neste runtime; configuração local validada sem afirmar homologação.", "remote_check_executed": False, "checked_at": now}
    else:
        connection = request.state.store.fetch_one("SELECT * FROM integration_connections WHERE tenant_id=? AND id=?", (tenant_id, configuration_id))
        try:
            secret = SecretResolver(_secret_root(request)).resolve(connection.get("secret_reference") if connection else None)
            config = _loads(connection.get("config_json") if connection else None, {})
            provider = build_provider(row["provider_code"], config=config, secret=secret)
            result = provider.health()
            checked = {"configuration_id": configuration_id, "health": result.status, "detail": result.details, "latency_ms": result.latency_ms, "remote_check_executed": True, "checked_at": now}
        except IntegrationError as exc:
            checked = {"configuration_id": configuration_id, "health": "failed", "detail": exc.code, "remote_check_executed": True, "checked_at": now}
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE fiscal_provider_configurations SET last_health_status=?,last_health_at=?,last_health_detail=?,updated_at=? WHERE tenant_id=? AND id=?", (checked["health"], now, json.dumps(checked.get("detail"), ensure_ascii=False) if isinstance(checked.get("detail"), (dict,list)) else str(checked.get("detail") or ""), now, tenant_id, configuration_id))
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="health_check", aggregate_type="fiscal_provider_configuration", aggregate_id=configuration_id, correlation_id=request.state.correlation_id, after={k:v for k,v in checked.items() if k != "detail"})
    return checked


def document_detail(document_id: str, request: Request, tenant_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
    if not row:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    result = dict(row)
    for source, target, default in (("totals_json","totals",{}),("request_json","request",{}),("response_json","response",{}),("fiscal_context_snapshot_json","fiscal_context_snapshot",{})):
        result[target] = _loads(result.pop(source, None), default)
    attempts = request.state.store.fetch_all("SELECT * FROM fiscal_document_attempts WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at,id", (tenant_id, document_id))
    artifacts = request.state.store.fetch_all("SELECT id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at FROM fiscal_document_artifacts WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at,id", (tenant_id, document_id))
    events = request.state.store.fetch_all("SELECT * FROM fiscal_document_events WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at,id", (tenant_id, document_id))
    for event in events:
        event["payload"] = _loads(event.pop("payload_json", None), {})
    for attempt in attempts:
        attempt["request"] = _loads(attempt.pop("request_json", None), {})
        attempt["response"] = _loads(attempt.pop("response_json", None), {})
    result["attempts"] = attempts; result["artifacts"] = artifacts; result["events"] = events
    return result


def queue_document_query(document_id: str, data: FiscalDocumentQueryRequest, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
    if not row:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    if not row.get("provider_connection_id"):
        raise DomainError("FISCAL_PROVIDER_REQUIRED", "Documento não possui provider configurado para consulta.", 409)
    if row["state"] == "cancelled":
        return {"id": document_id, "state": "cancelled", "idempotent": True}
    payload = {"id": document_id, "reason": data.reason}
    with request.state.store.transaction() as conn:
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="query_requested", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=request.state.correlation_id, before={"state": row["state"]}, after=payload, reason=data.reason)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentQueryRequested", aggregate_type="fiscal_document", aggregate_id=document_id, payload=payload, correlation_id=request.state.correlation_id)
    return {**payload, "provider_status": "queued"}


def substitute_document(document_id: str, data: FiscalDocumentSubstituteRequest, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int, dict[str, Any]]:
    original = request.state.store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
    if not original:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    if original["state"] != "authorized":
        raise DomainError("FISCAL_DOCUMENT_NOT_AUTHORIZED", "Somente documento autorizado pode ser substituído.", 409)
    if not original.get("provider_connection_id"):
        raise DomainError("FISCAL_PROVIDER_REQUIRED", "Documento autorizado não possui provider configurado para substituição.", 409)
    body = data.model_dump(mode="json")
    scope = f"fiscal-substitution:{tenant_id}:{document_id}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        if conn.execute("SELECT id FROM fiscal_documents WHERE tenant_id=? AND replacement_of_document_id=? AND state NOT IN ('cancelled','rejected')", (tenant_id, document_id)).fetchone():
            raise DomainError("FISCAL_SUBSTITUTION_ALREADY_OPEN", "Já existe substituição ativa para este documento.", 409)
        child_id = uuid7(); now=iso_now()
        result = {"id": child_id, "replacement_of_document_id": document_id, "document_type": original["document_type"], "source_type": data.source_type, "source_id": data.source_id, "environment": original["environment"], "state": "substitution_requested", "provider_status": "queued", "reason": data.reason}
        conn.execute(
            """INSERT INTO fiscal_documents(id,tenant_id,fiscal_profile_id,fiscal_context_id,fiscal_context_version_id,fiscal_context_snapshot_json,document_type,source_type,source_id,environment,state,provider_connection_id,provider_status,totals_json,request_json,response_json,replacement_of_document_id,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (child_id,tenant_id,original.get("fiscal_profile_id"),original.get("fiscal_context_id"),original.get("fiscal_context_version_id"),original.get("fiscal_context_snapshot_json") or "{}",original["document_type"],data.source_type,data.source_id,original["environment"],"substitution_requested",original.get("provider_connection_id"),"queued",json.dumps(data.totals,ensure_ascii=False,sort_keys=True),json.dumps(data.payload,ensure_ascii=False,sort_keys=True),"{}",document_id,now,now),
        )
        conn.execute("UPDATE fiscal_documents SET state='substitution_requested',updated_at=? WHERE tenant_id=? AND id=?", (now,tenant_id,document_id))
        conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,child_id,"substitution_requested","substitution_requested",original.get("provider_connection_id"),json.dumps(result,ensure_ascii=False,sort_keys=True),now))
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="substitute_requested", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=request.state.correlation_id, before={"state":"authorized"}, after=result, reason=data.reason)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentSubstitutionRequested", aggregate_type="fiscal_document", aggregate_id=child_id, payload={**result,"original_document_id":document_id}, correlation_id=request.state.correlation_id)
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return 201, result


def create_inutilization(data: FiscalInutilizationCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json"); scope=f"fiscal-inutilization:{tenant_id}:{data.document_type}:{data.year}:{data.series}:{data.start_number}:{data.end_number}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:return cached
        profile=conn.execute("SELECT id FROM fiscal_profiles WHERE tenant_id=? AND id=? AND state='active'",(tenant_id,data.fiscal_profile_id)).fetchone()
        if not profile:raise DomainError("FISCAL_PROFILE_NOT_FOUND","Perfil fiscal não localizado.",404)
        provider=conn.execute("SELECT * FROM fiscal_provider_configurations WHERE tenant_id=? AND id=?",(tenant_id,data.provider_configuration_id)).fetchone()
        if not provider:raise DomainError("FISCAL_PROVIDER_CONFIG_NOT_FOUND","Configuração fiscal não localizada.",404)
        if provider["document_type"]!=data.document_type:raise DomainError("FISCAL_PROVIDER_DOCUMENT_UNSUPPORTED","Provider não corresponde ao documento da inutilização.",422)
        iid=uuid7();now=iso_now();state="requested" if provider["status"]=="configured" else "awaiting_provider_configuration";provider_status="queued" if state=="requested" else "not_configured"
        result={"id":iid,"document_type":data.document_type,"year":data.year,"series":data.series,"start_number":data.start_number,"end_number":data.end_number,"state":state,"provider_status":provider_status}
        conn.execute("""INSERT INTO fiscal_inutilization_requests(id,tenant_id,fiscal_profile_id,provider_configuration_id,document_type,environment,year,series,start_number,end_number,reason,state,provider_status,attempts,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(iid,tenant_id,data.fiscal_profile_id,data.provider_configuration_id,data.document_type,provider["environment"],data.year,data.series,data.start_number,data.end_number,data.reason,state,provider_status,0,user.id,now,now))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="request",aggregate_type="fiscal_inutilization",aggregate_id=iid,correlation_id=request.state.correlation_id,after=result,reason=data.reason)
        if state=="requested":add_outbox(conn,tenant_id=tenant_id,event_type="FiscalInutilizationRequested",aggregate_type="fiscal_inutilization",aggregate_id=iid,payload=result,correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,body,201,result)
    return 201,result


def list_inutilizations(request: Request, tenant_id: str) -> dict[str,Any]:
    return {"items":request.state.store.fetch_all("SELECT * FROM fiscal_inutilization_requests WHERE tenant_id=? ORDER BY created_at DESC",(tenant_id,))}


def queue_provider_event(document_id: str, data: FiscalProviderEventCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int,dict[str,Any]]:
    row=request.state.store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?",(tenant_id,document_id))
    if not row:raise DomainError("FISCAL_DOCUMENT_NOT_FOUND","Documento fiscal não localizado.",404)
    if row["state"]!="authorized":raise DomainError("FISCAL_DOCUMENT_NOT_AUTHORIZED","Evento externo exige documento autorizado.",409)
    if not row.get("provider_connection_id"):raise DomainError("FISCAL_PROVIDER_REQUIRED","Documento não possui provider configurado.",409)
    body=data.model_dump(mode="json");scope=f"fiscal-provider-event:{tenant_id}:{document_id}:{data.event_type}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:return cached
        event_id=uuid7();now=iso_now();result={"id":event_id,"fiscal_document_id":document_id,"event_type":data.event_type,"state":"requested","provider_status":"queued"}
        conn.execute("INSERT INTO fiscal_provider_event_requests(id,tenant_id,fiscal_document_id,event_type,payload_json,reason,state,provider_status,attempts,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(event_id,tenant_id,document_id,data.event_type,json.dumps(data.payload,ensure_ascii=False,sort_keys=True),data.reason,"requested","queued",0,user.id,now,now))
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="provider_event_requested",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentProviderEventRequested",aggregate_type="fiscal_document",aggregate_id=document_id,payload={**result,"provider_event_request_id":event_id,"payload":data.payload,"reason":data.reason},correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,body,201,result)
    return 201,result
