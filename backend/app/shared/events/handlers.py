from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from app.shared.database.router import DataRouter
from app.modules.fiscal.application.ibpt import execute_ibpt_sync
from app.modules.fiscal.application.document_routing_service import process_emission_trigger, apply_fiscal_financial_adjustment
from app.modules.fiscal.application.document_delivery_service import FiscalRetryScheduled, record_rejection, resolve_delivery_policy, resolve_rejections, retry_plan
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.signatures.otp import derive_otp
from app.shared.integrations.providers import (
    DisabledTransport,
    EvolutionProvider,
    FiscalApiProvider,
    GovernmentEducationProvider,
    IntegrationError,
    SecretResolver,
    SmtpEmailProvider,
    Transport,
    build_provider,
)

FISCAL_PROVIDERS = {
    "SefazNfeProvider",
    "SefazNfceProvider",
    "NationalNfseProvider",
    "MunicipalNfseProvider",
    "ThirdPartyFiscalProvider",
}


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _secret_root(router: DataRouter) -> Path:
    if router.settings.environment in {"production", "staging"}:
        return Path("/run/secrets")
    return router.settings.data_root / "integration-secrets"


def _provider_transport(router: DataRouter, transport: Transport | None) -> Transport | None:
    if transport is not None:
        return transport
    if not router.settings.integration_remote_enabled:
        return DisabledTransport()
    return None


def _fiscal_connection(store, document: dict[str, Any]) -> dict[str, Any] | None:
    connection_id = document.get("provider_connection_id")
    if not connection_id:
        return None
    row = store.fetch_one(
        "SELECT * FROM integration_connections WHERE tenant_id=? AND id=?",
        (document["tenant_id"], connection_id),
    )
    if not row:
        return None
    result = dict(row)
    result["config"] = _json(result.get("config_json"), {})
    result["capabilities"] = _json(result.get("capabilities_json"), [])
    return result


def _fiscal_provider(router: DataRouter, connection: dict[str, Any], *, transport: Transport | None) -> FiscalApiProvider:
    if connection["provider"] not in FISCAL_PROVIDERS:
        raise IntegrationError("FISCAL_PROVIDER_INVALID", "Conexão vinculada ao perfil não é um provider fiscal.")
    secret = SecretResolver(_secret_root(router)).resolve(connection.get("secret_reference"))
    provider = build_provider(
        connection["provider"],
        config=connection.get("config") or {},
        secret=secret,
        transport=_provider_transport(router, transport),
    )
    if not isinstance(provider, FiscalApiProvider):
        raise IntegrationError("FISCAL_PROVIDER_INVALID", "Provider não implementa o contrato fiscal esperado.")
    return provider


def _safe_provider_payload(result: dict[str, Any]) -> dict[str, Any]:
    raw = dict(result.get("raw") or {})
    for key in ("xml", "xml_base64", "pdf_base64", "pdf"):
        raw.pop(key, None)
    return {
        "state": result.get("state"),
        "provider_document_id": result.get("provider_document_id"),
        "provider_event_id": result.get("provider_event_id"),
        "access_key": result.get("access_key"),
        "protocol": result.get("protocol"),
        "number": result.get("number"),
        "series": result.get("series"),
        "error_code": result.get("error_code"),
        "error_message": result.get("error_message"),
        "provider": raw,
    }


def _decode_artifact(result: dict[str, Any], *, text_key: str, base64_key: str) -> bytes | None:
    encoded = result.get(base64_key)
    if encoded:
        try:
            return base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise IntegrationError("FISCAL_ARTIFACT_INVALID", f"Provider retornou {base64_key} inválido.") from exc
    text = result.get(text_key)
    if text is not None:
        return str(text).encode("utf-8")
    return None


def _record_fiscal_event(
    conn,
    *,
    tenant_id: str,
    document_id: str,
    event_type: str,
    state: str,
    provider_connection_id: str | None,
    payload: dict[str, Any],
    provider_event_id: str | None = None,
    xml_storage_key: str | None = None,
    xml_sha256: str | None = None,
) -> str:
    event_id = uuid7()
    conn.execute(
        """INSERT INTO fiscal_document_events(
               id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,provider_event_id,
               payload_json,xml_storage_key,xml_sha256,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id, tenant_id, document_id, event_type, state, provider_connection_id,
            provider_event_id, json.dumps(payload, ensure_ascii=False, sort_keys=True),
            xml_storage_key, xml_sha256, iso_now(),
        ),
    )
    return event_id


def _record_fiscal_attempt(
    conn, *, tenant_id: str, document_id: str, provider_connection_id: str | None,
    operation: str, request_payload: dict[str, Any], state: str, response_payload: dict[str, Any] | None = None,
    error_code: str | None = None, retryable: bool = False,
) -> str:
    canonical = json.dumps(request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    row = conn.execute(
        "SELECT COALESCE(MAX(attempt_number),0) AS n FROM fiscal_document_attempts WHERE tenant_id=? AND fiscal_document_id=? AND operation=?",
        (tenant_id, document_id, operation),
    ).fetchone()
    attempt_number = int(row["n"] if row else 0) + 1
    attempt_id = uuid7(); now = iso_now()
    conn.execute(
        """INSERT INTO fiscal_document_attempts(
               id,tenant_id,fiscal_document_id,provider_connection_id,operation,attempt_number,state,request_sha256,
               request_json,response_json,error_code,retryable,started_at,finished_at,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (attempt_id, tenant_id, document_id, provider_connection_id, operation, attempt_number, state, digest,
         json.dumps(request_payload, ensure_ascii=False, sort_keys=True),
         json.dumps(response_payload or {}, ensure_ascii=False, sort_keys=True), error_code, 1 if retryable else 0, now, now, now),
    )
    return attempt_id


def _record_fiscal_artifact(
    conn, *, tenant_id: str, document_id: str, artifact_type: str, content_type: str,
    storage_key: str, sha256: str, bytes_count: int, provider_event_id: str | None = None,
) -> str:
    artifact_id = uuid7()
    conn.execute(
        """INSERT OR IGNORE INTO fiscal_document_artifacts(
               id,tenant_id,fiscal_document_id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (artifact_id, tenant_id, document_id, artifact_type, content_type, storage_key, sha256, bytes_count, provider_event_id, iso_now()),
    )
    return artifact_id


def _sync_service_fiscal_document_state(
    conn,
    *,
    tenant_id: str,
    document: dict[str, Any],
    state: str,
    provider_code: str | None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> None:
    """Propaga o estado real de uma NFS-e aos eventos fiscais do serviço.

    A relação é criada pelo roteamento fiscal. Esta função apenas espelha o
    lifecycle do documento e preserva a origem por item no módulo de serviços.
    """
    if document.get("source_type") != "service_order":
        return
    document_id = str(document.get("id") or "")
    service_order_id = str(document.get("source_id") or "")
    if not document_id or not service_order_id:
        return
    now = iso_now()
    completed_at = now if state in {"authorized", "rejected", "cancelled", "substituted"} else None
    conn.execute(
        """UPDATE service_fiscal_events
           SET state=?, provider_code=COALESCE(?,provider_code), failure_code=?, failure_message=?,
               completed_at=?, updated_at=?
           WHERE tenant_id=? AND fiscal_document_id=?""",
        (
            state,
            provider_code or None,
            failure_code,
            (failure_message or "")[:2000] or None,
            completed_at,
            now,
            tenant_id,
            document_id,
        ),
    )
    rows = conn.execute(
        "SELECT state FROM service_fiscal_events WHERE tenant_id=? AND service_order_id=?",
        (tenant_id, service_order_id),
    ).fetchall()
    states = {str(row["state"]) for row in rows}
    if not states:
        return
    if "blocked_validation" in states:
        order_status = "blocked_validation"
    elif states <= {"authorized"}:
        order_status = "authorized"
    elif "awaiting_provider_configuration" in states:
        order_status = "awaiting_provider_configuration"
    elif "rejected" in states:
        order_status = "rejected"
    elif "cancelled" in states and states <= {"cancelled", "substituted"}:
        order_status = "cancelled"
    else:
        order_status = "emission_requested"
    conn.execute(
        "UPDATE service_orders SET fiscal_status=?,updated_at=? WHERE tenant_id=? AND id=?",
        (order_status, now, tenant_id, service_order_id),
    )


def _find_connection(store, tenant_id: str, providers: tuple[str, ...], capability: str) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in providers)
    rows = store.fetch_all(
        f"SELECT * FROM integration_connections WHERE tenant_id=? AND provider IN ({placeholders}) AND state IN ('configured','degraded') ORDER BY updated_at DESC",
        (tenant_id, *providers),
    )
    for row in rows:
        item = dict(row)
        item["config"] = _json(item.get("config_json"), {})
        item["capabilities"] = _json(item.get("capabilities_json"), [])
        if capability in set(item["capabilities"]) or "*" in set(item["capabilities"]):
            return item
    return None


def _mark_notification(store, tenant_id: str, notification_id: str, *, state: str, provider_message_id: str | None = None, error: str | None = None) -> None:
    now = iso_now()
    # O corpo do erro não é persistido. O histórico registra apenas código/estado técnico.
    details = {"error_code": error} if error else {}
    with store.transaction() as conn:
        conn.execute(
            "UPDATE notifications SET state=?,provider_message_id=?,attempts=attempts+1,sent_at=? WHERE tenant_id=? AND id=?",
            (state, provider_message_id, now if state == "sent" else None, tenant_id, notification_id),
        )
        conn.execute(
            "INSERT INTO notification_events(id,tenant_id,notification_id,event_type,state,provider_message_id,details_json,occurred_at) VALUES(?,?,?,?,?,?,?,?)",
            (uuid7(), tenant_id, notification_id, "delivery_state_changed", state, provider_message_id, json.dumps(details, sort_keys=True), now),
        )


def build_domain_event_handlers(
    router: DataRouter,
    *,
    tenant_id: str,
    transport: Transport | None = None,
) -> dict[str, Any]:
    store = router.tenant_store(tenant_id)

    def fiscal_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        document_id = str(envelope["aggregate_id"])
        document = store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
        if not document:
            return {"state": "ignored", "reason": "document_not_found"}
        if document["state"] in {"authorized", "cancelled"}:
            return {"state": document["state"], "idempotent": True}
        request_payload = {
            "id": document_id,
            "environment": document["environment"],
            "source_type": document["source_type"],
            "source_id": document["source_id"],
            "totals": _json(document.get("totals_json"), {}),
            "payload": _json(document.get("request_json"), {}),
            "contingency_mode": document.get("contingency_mode"),
        }
        connection = _fiscal_connection(store, document)
        if not connection or connection.get("state") not in {"configured", "degraded"}:
            now = iso_now()
            with store.transaction() as conn:
                conn.execute(
                    "UPDATE fiscal_documents SET state='awaiting_provider_configuration',provider_status='not_configured',attempts=attempts+1,last_attempt_at=?,updated_at=? WHERE tenant_id=? AND id=?",
                    (now, now, tenant_id, document_id),
                )
                _record_fiscal_attempt(conn, tenant_id=tenant_id, document_id=document_id, provider_connection_id=document.get("provider_connection_id"), operation="issue", request_payload=request_payload, state="not_configured", error_code="FISCAL_PROVIDER_NOT_CONFIGURED")
                _record_fiscal_event(conn, tenant_id=tenant_id, document_id=document_id, event_type="provider_not_configured", state="awaiting_provider_configuration", provider_connection_id=document.get("provider_connection_id"), payload={"provider_status": "not_configured"})
                add_audit(conn, tenant_id=tenant_id, actor_id="system-worker", action="provider_not_configured", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]), after={"state":"awaiting_provider_configuration"})
                _sync_service_fiscal_document_state(
                    conn,
                    tenant_id=tenant_id,
                    document=dict(document),
                    state="awaiting_provider_configuration",
                    provider_code=None,
                    failure_code="FISCAL_PROVIDER_NOT_CONFIGURED",
                    failure_message="Provider fiscal não configurado.",
                )
            return {"state": "awaiting_provider_configuration", "provider_status": "not_configured"}
        try:
            provider = _fiscal_provider(router, connection, transport=transport)
            result = provider.issue_document(document_type=document["document_type"], document=request_payload)
        except IntegrationError as exc:
            now = iso_now()
            should_raise = False
            response_state = "rejected"
            with store.transaction() as conn:
                policy = resolve_delivery_policy(conn, tenant_id=tenant_id, document=dict(document), provider_code=connection.get("provider"))
                attempt_id = _record_fiscal_attempt(conn, tenant_id=tenant_id, document_id=document_id, provider_connection_id=document.get("provider_connection_id"), operation="issue", request_payload=request_payload, state="failed", error_code=exc.code, retryable=exc.retryable)
                attempt_row = conn.execute("SELECT attempt_number FROM fiscal_document_attempts WHERE id=?", (attempt_id,)).fetchone()
                attempt_number = int(attempt_row["attempt_number"] if attempt_row else 1)
                plan = retry_plan(policy, document_id=document_id, attempt_number=attempt_number)
                retry_pending = bool(exc.retryable and plan.get("allowed"))
                next_state = "requested" if retry_pending else "rejected"
                response_state = "retry_pending" if retry_pending else "rejected"
                contingency = plan.get("contingency_mode") or document.get("contingency_mode")
                conn.execute(
                    "UPDATE fiscal_documents SET state=?,provider_status='failed',attempts=attempts+1,retry_count=retry_count+1,last_attempt_at=?,error_code=?,error_message=?,delivery_policy_id=?,next_retry_at=?,contingency_mode=?,updated_at=? WHERE tenant_id=? AND id=?",
                    (next_state, now, exc.code, str(exc)[:2000], plan.get("policy_id"), plan.get("next_retry_at"), contingency, now, tenant_id, document_id),
                )
                rejection = record_rejection(
                    conn, tenant_id=tenant_id, document_id=document_id, attempt_id=attempt_id, error_code=exc.code,
                    error_message=str(exc), retryable=exc.retryable, provider_status="failed",
                    category="transport" if exc.retryable else "provider_error", plan=plan,
                    explanation={"source": "integration_error", "retryable": exc.retryable, "delivery_policy": policy, "contingency_activated": bool(plan.get("contingency_mode"))},
                )
                _record_fiscal_event(conn, tenant_id=tenant_id, document_id=document_id, event_type="provider_error", state=response_state, provider_connection_id=document.get("provider_connection_id"), payload={"code": exc.code, "message": str(exc)[:1000], "retryable": exc.retryable, "retry": plan, "rejection_id": rejection["id"]})
                if plan.get("contingency_mode") and plan.get("contingency_mode") != document.get("contingency_mode"):
                    contingency_payload={"mode":plan["contingency_mode"],"attempt_number":attempt_number,"delivery_policy_id":plan.get("policy_id")}
                    _record_fiscal_event(conn, tenant_id=tenant_id, document_id=document_id, event_type="contingency_activated", state=next_state, provider_connection_id=document.get("provider_connection_id"), payload=contingency_payload)
                    add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentContingencyActivated", aggregate_type="fiscal_document", aggregate_id=document_id, payload=contingency_payload, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
                add_audit(conn, tenant_id=tenant_id, actor_id="system-worker", action="provider_issue_failed", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]), after={"code":exc.code,"retryable":exc.retryable,"retry":plan,"rejection_id":rejection["id"]})
                if not retry_pending:
                    add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentRejected", aggregate_type="fiscal_document", aggregate_id=document_id, payload={"id": document_id, "error_code": exc.code, "rejection_id": rejection["id"], "retry_limit_reached": bool(plan.get("limit_reached"))}, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
                _sync_service_fiscal_document_state(
                    conn,
                    tenant_id=tenant_id,
                    document=dict(document),
                    state=response_state,
                    provider_code=str(connection.get("provider") or ""),
                    failure_code=exc.code,
                    failure_message=str(exc),
                )
                should_raise = bool(retry_pending and (policy is None or plan.get("auto_retry")))
            if should_raise:
                if policy:
                    raise FiscalRetryScheduled(str(exc), delay_seconds=int(plan.get("delay_seconds") or 0), max_attempts=int(policy["max_attempts"])) from exc
                raise TimeoutError(str(exc)) from exc
            return {"state": response_state, "error_code": exc.code}

        xml_bytes = _decode_artifact(result, text_key="xml", base64_key="xml_base64")
        pdf_bytes = _decode_artifact(result, text_key="pdf", base64_key="pdf_base64")
        xml_obj = pdf_obj = None
        storage = router.object_storage(tenant_id)
        if xml_bytes:
            xml_obj = storage.put_bytes(f"fiscal/{document_id}/provider-response.xml", xml_bytes, content_type="application/xml")
        if pdf_bytes:
            pdf_obj = storage.put_bytes(f"fiscal/{document_id}/provider-document.pdf", pdf_bytes, content_type="application/pdf")
        normalized = _safe_provider_payload(result); state = str(result.get("state") or "processing"); now = iso_now()
        with store.transaction() as conn:
            conn.execute(
                """UPDATE fiscal_documents SET state=?,provider_document_id=?,provider_status=?,attempts=attempts+1,last_attempt_at=?,access_key=?,protocol=?,number=?,series=?,response_json=?,xml_storage_key=?,pdf_storage_key=?,xml_sha256=?,error_code=?,error_message=?,authorized_at=CASE WHEN ?='authorized' THEN ? ELSE authorized_at END,updated_at=? WHERE tenant_id=? AND id=?""",
                (state, result.get("provider_document_id"), state, now, result.get("access_key"), result.get("protocol"), result.get("number"), result.get("series"), json.dumps(normalized, ensure_ascii=False, sort_keys=True), xml_obj.key if xml_obj else None, pdf_obj.key if pdf_obj else None, xml_obj.sha256 if xml_obj else None, result.get("error_code"), result.get("error_message"), state, now, now, tenant_id, document_id),
            )
            attempt_id = _record_fiscal_attempt(conn, tenant_id=tenant_id, document_id=document_id, provider_connection_id=document.get("provider_connection_id"), operation="issue", request_payload=request_payload, state="rejected" if state == "rejected" else "completed", response_payload=normalized, error_code=result.get("error_code"))
            if state == "authorized":
                resolve_rejections(conn, tenant_id=tenant_id, document_id=document_id, resolution="authorized")
                conn.execute("UPDATE fiscal_documents SET next_retry_at=NULL WHERE tenant_id=? AND id=?", (tenant_id, document_id))
            elif state == "rejected":
                policy = resolve_delivery_policy(conn, tenant_id=tenant_id, document=dict(document), provider_code=connection.get("provider"))
                attempt_row = conn.execute("SELECT attempt_number FROM fiscal_document_attempts WHERE id=?", (attempt_id,)).fetchone()
                attempt_number = int(attempt_row["attempt_number"] if attempt_row else 1)
                raw_provider = result.get("raw") if isinstance(result.get("raw"), dict) else {}
                retryable = bool(raw_provider.get("retryable", False))
                plan = retry_plan(policy, document_id=document_id, attempt_number=attempt_number)
                rejection = record_rejection(conn, tenant_id=tenant_id, document_id=document_id, attempt_id=attempt_id, error_code=result.get("error_code"), error_message=result.get("error_message"), retryable=retryable, provider_status=state, category="provider_rejection", plan=plan, explanation={"source":"provider_response","delivery_policy":policy,"provider_state":state})
                conn.execute("UPDATE fiscal_documents SET delivery_policy_id=?,next_retry_at=?,retry_count=retry_count+1 WHERE tenant_id=? AND id=?", (plan.get("policy_id"), plan.get("next_retry_at") if retryable and plan.get("allowed") else None, tenant_id, document_id))
            if xml_obj:
                _record_fiscal_artifact(conn, tenant_id=tenant_id, document_id=document_id, artifact_type="authorized_xml" if state=="authorized" else "provider_xml", content_type="application/xml", storage_key=xml_obj.key, sha256=xml_obj.sha256, bytes_count=xml_obj.bytes, provider_event_id=result.get("provider_event_id"))
            if pdf_obj:
                _record_fiscal_artifact(conn, tenant_id=tenant_id, document_id=document_id, artifact_type="danfe" if document["document_type"]=="NF-e" else ("danfce" if document["document_type"]=="NFC-e" else "danfse"), content_type="application/pdf", storage_key=pdf_obj.key, sha256=pdf_obj.sha256, bytes_count=pdf_obj.bytes, provider_event_id=result.get("provider_event_id"))
            _record_fiscal_event(conn, tenant_id=tenant_id, document_id=document_id, event_type="authorized" if state == "authorized" else ("rejected" if state == "rejected" else "provider_processing"), state=state, provider_connection_id=document.get("provider_connection_id"), provider_event_id=result.get("provider_event_id"), payload=normalized, xml_storage_key=xml_obj.key if xml_obj else None, xml_sha256=xml_obj.sha256 if xml_obj else None)
            add_audit(conn, tenant_id=tenant_id, actor_id="system-worker", action="provider_issue_response", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]), before={"state":document["state"]}, after={"state":state,"protocol":result.get("protocol"),"xml_sha256":xml_obj.sha256 if xml_obj else None})
            if state == "authorized":
                add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentAuthorized", aggregate_type="fiscal_document", aggregate_id=document_id, payload={"id": document_id, "access_key": result.get("access_key"), "protocol": result.get("protocol")}, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
            elif state == "rejected":
                add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentRejected", aggregate_type="fiscal_document", aggregate_id=document_id, payload={"id": document_id, "error_code": result.get("error_code")}, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
            _sync_service_fiscal_document_state(
                conn,
                tenant_id=tenant_id,
                document=dict(document),
                state=state,
                provider_code=str(connection.get("provider") or ""),
                failure_code=result.get("error_code"),
                failure_message=result.get("error_message"),
            )
        return {"state": state, "document_id": document_id, "xml_sha256": xml_obj.sha256 if xml_obj else None}

    def fiscal_cancel_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        document_id = str(envelope["aggregate_id"]); document = store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
        if not document: return {"state":"ignored","reason":"document_not_found"}
        if document["state"] == "cancelled": return {"state":"cancelled","idempotent":True}
        payload = dict(envelope.get("payload") or {}); connection = _fiscal_connection(store, document)
        request_payload={"reason":str(payload.get("reason") or "Cancelamento solicitado"),"access_key":document.get("access_key")}
        if not connection:
            with store.transaction() as conn:
                _record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="cancel",request_payload=request_payload,state="not_configured",error_code="FISCAL_PROVIDER_NOT_CONFIGURED")
            return {"state":"cancellation_requested","provider_status":"not_configured"}
        try:
            provider=_fiscal_provider(router,connection,transport=transport); provider_id=str(document.get("provider_document_id") or document.get("access_key") or "")
            if not provider_id: raise IntegrationError("FISCAL_PROVIDER_DOCUMENT_ID_MISSING","Documento não possui identificador do provider para cancelamento.")
            result=provider.cancel_document(provider_document_id=provider_id,reason=request_payload["reason"],access_key=document.get("access_key"))
        except IntegrationError as exc:
            with store.transaction() as conn:
                _record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="cancel",request_payload=request_payload,state="failed",error_code=exc.code,retryable=exc.retryable)
            if exc.retryable: raise TimeoutError(str(exc)) from exc
            return {"state":"cancellation_requested","error_code":exc.code}
        state=str(result.get("state") or "processing");now=iso_now();normalized=_safe_provider_payload(result)
        with store.transaction() as conn:
            conn.execute("UPDATE fiscal_documents SET state=?,provider_status=?,attempts=attempts+1,last_attempt_at=?,response_json=?,error_code=?,error_message=?,cancelled_at=CASE WHEN ?='cancelled' THEN ? ELSE cancelled_at END,updated_at=? WHERE tenant_id=? AND id=?",(state,state,now,json.dumps(normalized,ensure_ascii=False,sort_keys=True),result.get("error_code"),result.get("error_message"),state,now,now,tenant_id,document_id))
            _record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="cancel",request_payload=request_payload,state="completed",response_payload=normalized,error_code=result.get("error_code"))
            _record_fiscal_event(conn,tenant_id=tenant_id,document_id=document_id,event_type="cancelled" if state=="cancelled" else "cancellation_provider_response",state=state,provider_connection_id=document.get("provider_connection_id"),provider_event_id=result.get("provider_event_id"),payload=normalized)
            add_audit(conn,tenant_id=tenant_id,actor_id="system-worker",action="provider_cancel_response",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]),before={"state":document["state"]},after={"state":state})
            if state=="cancelled": add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentCancelled",aggregate_type="fiscal_document",aggregate_id=document_id,payload={"id":document_id},correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
            _sync_service_fiscal_document_state(conn,tenant_id=tenant_id,document=dict(document),state=state,provider_code=str(connection.get("provider") or ""),failure_code=result.get("error_code"),failure_message=result.get("error_message"))
        return {"state":state,"document_id":document_id}

    def fiscal_query_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        document_id=str(envelope["aggregate_id"]);document=store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?",(tenant_id,document_id))
        if not document:return {"state":"ignored","reason":"document_not_found"}
        connection=_fiscal_connection(store,document);provider_id=str(document.get("provider_document_id") or document.get("access_key") or "")
        request_payload={"provider_document_id":provider_id,"access_key":document.get("access_key")}
        if not connection or not provider_id:
            with store.transaction() as conn:_record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="query",request_payload=request_payload,state="not_configured",error_code="FISCAL_PROVIDER_NOT_CONFIGURED")
            return {"state":document["state"],"provider_status":"not_configured"}
        try: result=_fiscal_provider(router,connection,transport=transport).query_document(provider_document_id=provider_id,access_key=document.get("access_key"))
        except IntegrationError as exc:
            with store.transaction() as conn:_record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="query",request_payload=request_payload,state="failed",error_code=exc.code,retryable=exc.retryable)
            if exc.retryable:raise TimeoutError(str(exc)) from exc
            return {"state":document["state"],"error_code":exc.code}
        normalized=_safe_provider_payload(result);provider_state=str(result.get("state") or "processing");new_state=document["state"] if provider_state=="processing" else provider_state;now=iso_now()
        xml_bytes=_decode_artifact(result,text_key="xml",base64_key="xml_base64");xml_obj=router.object_storage(tenant_id).put_bytes(f"fiscal/{document_id}/query-{uuid7()}.xml",xml_bytes,content_type="application/xml") if xml_bytes else None
        with store.transaction() as conn:
            conn.execute("UPDATE fiscal_documents SET state=?,provider_status=?,protocol=COALESCE(?,protocol),access_key=COALESCE(?,access_key),response_json=?,xml_storage_key=COALESCE(?,xml_storage_key),xml_sha256=COALESCE(?,xml_sha256),updated_at=? WHERE tenant_id=? AND id=?",(new_state,provider_state,result.get("protocol"),result.get("access_key"),json.dumps(normalized,ensure_ascii=False,sort_keys=True),xml_obj.key if xml_obj else None,xml_obj.sha256 if xml_obj else None,now,tenant_id,document_id))
            _record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="query",request_payload=request_payload,state="completed",response_payload=normalized,error_code=result.get("error_code"))
            if xml_obj:_record_fiscal_artifact(conn,tenant_id=tenant_id,document_id=document_id,artifact_type="query_xml",content_type="application/xml",storage_key=xml_obj.key,sha256=xml_obj.sha256,bytes_count=xml_obj.bytes,provider_event_id=result.get("provider_event_id"))
            _record_fiscal_event(conn,tenant_id=tenant_id,document_id=document_id,event_type="query_response",state=new_state,provider_connection_id=document.get("provider_connection_id"),provider_event_id=result.get("provider_event_id"),payload=normalized,xml_storage_key=xml_obj.key if xml_obj else None,xml_sha256=xml_obj.sha256 if xml_obj else None)
            add_audit(conn,tenant_id=tenant_id,actor_id="system-worker",action="provider_query_response",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]),before={"state":document["state"]},after={"state":new_state,"provider_state":provider_state})
        return {"state":new_state,"provider_state":provider_state,"document_id":document_id}

    def fiscal_substitution_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        child_id=str(envelope["aggregate_id"]);payload=dict(envelope.get("payload") or {});original_id=str(payload.get("original_document_id") or "")
        child=store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?",(tenant_id,child_id));original=store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?",(tenant_id,original_id))
        if not child or not original:return {"state":"ignored","reason":"substitution_document_missing"}
        connection=_fiscal_connection(store,child);provider_id=str(original.get("provider_document_id") or original.get("access_key") or "")
        request_payload={"original_document_id":original_id,"replacement_document_id":child_id,"reason":payload.get("reason"),"document":{"source_type":child["source_type"],"source_id":child["source_id"],"totals":_json(child.get("totals_json"),{}),"payload":_json(child.get("request_json"),{})}}
        if not connection or not provider_id:return {"state":"substitution_requested","provider_status":"not_configured"}
        try:result=_fiscal_provider(router,connection,transport=transport).substitute_document(provider_document_id=provider_id,document_type=child["document_type"],document=request_payload["document"],reason=str(payload.get("reason") or "Substituição solicitada"))
        except IntegrationError as exc:
            with store.transaction() as conn:_record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=child_id,provider_connection_id=child.get("provider_connection_id"),operation="substitute",request_payload=request_payload,state="failed",error_code=exc.code,retryable=exc.retryable)
            if exc.retryable:raise TimeoutError(str(exc)) from exc
            return {"state":"substitution_requested","error_code":exc.code}
        normalized=_safe_provider_payload(result);state=str(result.get("state") or "processing");now=iso_now();xml_bytes=_decode_artifact(result,text_key="xml",base64_key="xml_base64");pdf_bytes=_decode_artifact(result,text_key="pdf",base64_key="pdf_base64");storage=router.object_storage(tenant_id);xml_obj=storage.put_bytes(f"fiscal/{child_id}/substitution.xml",xml_bytes,content_type="application/xml") if xml_bytes else None;pdf_obj=storage.put_bytes(f"fiscal/{child_id}/substitution.pdf",pdf_bytes,content_type="application/pdf") if pdf_bytes else None
        with store.transaction() as conn:
            conn.execute("UPDATE fiscal_documents SET state=?,provider_document_id=?,provider_status=?,access_key=?,protocol=?,number=?,series=?,response_json=?,xml_storage_key=?,pdf_storage_key=?,xml_sha256=?,authorized_at=CASE WHEN ?='authorized' THEN ? ELSE authorized_at END,updated_at=? WHERE tenant_id=? AND id=?",(state,result.get("provider_document_id"),state,result.get("access_key"),result.get("protocol"),result.get("number"),result.get("series"),json.dumps(normalized,ensure_ascii=False,sort_keys=True),xml_obj.key if xml_obj else None,pdf_obj.key if pdf_obj else None,xml_obj.sha256 if xml_obj else None,state,now,now,tenant_id,child_id))
            if state=="authorized":conn.execute("UPDATE fiscal_documents SET state='substituted',substituted_by_document_id=?,updated_at=? WHERE tenant_id=? AND id=?",(child_id,now,tenant_id,original_id))
            _record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=child_id,provider_connection_id=child.get("provider_connection_id"),operation="substitute",request_payload=request_payload,state="completed",response_payload=normalized,error_code=result.get("error_code"))
            if xml_obj:_record_fiscal_artifact(conn,tenant_id=tenant_id,document_id=child_id,artifact_type="substitution_xml",content_type="application/xml",storage_key=xml_obj.key,sha256=xml_obj.sha256,bytes_count=xml_obj.bytes,provider_event_id=result.get("provider_event_id"))
            if pdf_obj:_record_fiscal_artifact(conn,tenant_id=tenant_id,document_id=child_id,artifact_type="substitution_pdf",content_type="application/pdf",storage_key=pdf_obj.key,sha256=pdf_obj.sha256,bytes_count=pdf_obj.bytes,provider_event_id=result.get("provider_event_id"))
            _record_fiscal_event(conn,tenant_id=tenant_id,document_id=child_id,event_type="substitution_authorized" if state=="authorized" else "substitution_provider_response",state=state,provider_connection_id=child.get("provider_connection_id"),provider_event_id=result.get("provider_event_id"),payload=normalized,xml_storage_key=xml_obj.key if xml_obj else None,xml_sha256=xml_obj.sha256 if xml_obj else None)
            add_audit(conn,tenant_id=tenant_id,actor_id="system-worker",action="provider_substitution_response",aggregate_type="fiscal_document",aggregate_id=child_id,correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]),after={"state":state,"original_document_id":original_id})
            if state=="authorized":add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentSubstituted",aggregate_type="fiscal_document",aggregate_id=original_id,payload={"id":original_id,"substituted_by":child_id},correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
        return {"state":state,"document_id":child_id,"original_document_id":original_id}

    def fiscal_inutilization_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        request_id=str(envelope["aggregate_id"]);row=store.fetch_one("SELECT * FROM fiscal_inutilization_requests WHERE tenant_id=? AND id=?",(tenant_id,request_id))
        if not row:return {"state":"ignored","reason":"inutilization_not_found"}
        if row["state"]=="authorized":return {"state":"authorized","idempotent":True}
        connection=_fiscal_connection(store,{"tenant_id":tenant_id,"provider_connection_id":row["provider_configuration_id"]})
        if not connection:return {"state":"awaiting_provider_configuration","provider_status":"not_configured"}
        try:result=_fiscal_provider(router,connection,transport=transport).inutilize_numbers(document_type=row["document_type"],year=int(row["year"]),series=row["series"],start_number=int(row["start_number"]),end_number=int(row["end_number"]),reason=row["reason"])
        except IntegrationError as exc:
            now=iso_now();store.execute("UPDATE fiscal_inutilization_requests SET provider_status='failed',attempts=attempts+1,error_code=?,error_message=?,updated_at=? WHERE tenant_id=? AND id=?",(exc.code,str(exc)[:2000],now,tenant_id,request_id))
            if exc.retryable:raise TimeoutError(str(exc)) from exc
            return {"state":"requested","error_code":exc.code}
        state=str(result.get("state") or "processing");now=iso_now()
        with store.transaction() as conn:
            conn.execute("UPDATE fiscal_inutilization_requests SET state=?,provider_status=?,protocol=?,provider_request_id=?,attempts=attempts+1,error_code=?,error_message=?,updated_at=? WHERE tenant_id=? AND id=?",(state,state,result.get("protocol"),result.get("provider_request_id"),result.get("error_code"),result.get("error_message"),now,tenant_id,request_id))
            add_audit(conn,tenant_id=tenant_id,actor_id="system-worker",action="provider_inutilization_response",aggregate_type="fiscal_inutilization",aggregate_id=request_id,correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]),after={"state":state,"protocol":result.get("protocol")})
            if state=="authorized":add_outbox(conn,tenant_id=tenant_id,event_type="FiscalInutilizationAuthorized",aggregate_type="fiscal_inutilization",aggregate_id=request_id,payload={"id":request_id,"protocol":result.get("protocol")},correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
        return {"state":state,"id":request_id,"protocol":result.get("protocol")}

    def fiscal_provider_event_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        payload=dict(envelope.get("payload") or {});request_id=str(payload.get("provider_event_request_id") or "");document_id=str(envelope["aggregate_id"])
        row=store.fetch_one("SELECT * FROM fiscal_provider_event_requests WHERE tenant_id=? AND id=?",(tenant_id,request_id));document=store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?",(tenant_id,document_id))
        if not row or not document:return {"state":"ignored","reason":"provider_event_request_missing"}
        connection=_fiscal_connection(store,document);provider_id=str(document.get("provider_document_id") or document.get("access_key") or "")
        request_payload={"event_type":row["event_type"],"payload":_json(row.get("payload_json"),{}),"reason":row["reason"]}
        if not connection or not provider_id:return {"state":"requested","provider_status":"not_configured"}
        try:result=_fiscal_provider(router,connection,transport=transport).register_event(provider_document_id=provider_id,event_type=row["event_type"],payload=request_payload["payload"],reason=row["reason"])
        except IntegrationError as exc:
            with store.transaction() as conn:
                conn.execute("UPDATE fiscal_provider_event_requests SET provider_status='failed',attempts=attempts+1,error_code=?,error_message=?,updated_at=? WHERE tenant_id=? AND id=?",(exc.code,str(exc)[:2000],iso_now(),tenant_id,request_id));_record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="provider_event",request_payload=request_payload,state="failed",error_code=exc.code,retryable=exc.retryable)
            if exc.retryable:raise TimeoutError(str(exc)) from exc
            return {"state":"requested","error_code":exc.code}
        state=str(result.get("state") or "processing");now=iso_now();xml_bytes=_decode_artifact(result,text_key="xml",base64_key="xml_base64");xml_obj=router.object_storage(tenant_id).put_bytes(f"fiscal/{document_id}/events/{request_id}.xml",xml_bytes,content_type="application/xml") if xml_bytes else None;normalized={k:v for k,v in result.items() if k not in {"xml","xml_base64","raw"}}
        with store.transaction() as conn:
            conn.execute("UPDATE fiscal_provider_event_requests SET state=?,provider_status=?,protocol=?,provider_event_id=?,attempts=attempts+1,error_code=?,error_message=?,updated_at=? WHERE tenant_id=? AND id=?",(state,state,result.get("protocol"),result.get("provider_event_id"),result.get("error_code"),result.get("error_message"),now,tenant_id,request_id))
            _record_fiscal_attempt(conn,tenant_id=tenant_id,document_id=document_id,provider_connection_id=document.get("provider_connection_id"),operation="provider_event",request_payload=request_payload,state="completed",response_payload=normalized,error_code=result.get("error_code"))
            if xml_obj:_record_fiscal_artifact(conn,tenant_id=tenant_id,document_id=document_id,artifact_type=f"event_{row['event_type']}_xml",content_type="application/xml",storage_key=xml_obj.key,sha256=xml_obj.sha256,bytes_count=xml_obj.bytes,provider_event_id=result.get("provider_event_id"))
            _record_fiscal_event(conn,tenant_id=tenant_id,document_id=document_id,event_type=row["event_type"],state=state,provider_connection_id=document.get("provider_connection_id"),provider_event_id=result.get("provider_event_id"),payload=normalized,xml_storage_key=xml_obj.key if xml_obj else None,xml_sha256=xml_obj.sha256 if xml_obj else None)
            add_audit(conn,tenant_id=tenant_id,actor_id="system-worker",action="provider_event_response",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]),after={"event_type":row["event_type"],"state":state,"protocol":result.get("protocol")})
        return {"state":state,"document_id":document_id,"event_type":row["event_type"],"protocol":result.get("protocol")}

    def notification_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        notification_id = str((envelope.get("payload") or {}).get("notification_id") or envelope.get("aggregate_id") or "")
        row = store.fetch_one("SELECT * FROM notifications WHERE tenant_id=? AND id=?", (tenant_id, notification_id))
        if not row:
            return {"state": "ignored", "reason": "notification_not_found"}
        if row["state"] == "sent":
            return {"state": "sent", "idempotent": True}
        channel = str(row.get("channel") or "internal")
        if channel == "internal":
            _mark_notification(store, tenant_id, notification_id, state="sent", provider_message_id=f"internal:{notification_id}")
            return {"state": "sent", "channel": "internal"}
        person = None
        if row.get("recipient_person_id"):
            person = store.fetch_one("SELECT email,phone,full_name FROM people WHERE tenant_id=? AND id=?", (tenant_id, row["recipient_person_id"]))
        if channel == "whatsapp":
            destination = str((person or {}).get("phone") or "").strip()
            connection = _find_connection(store, tenant_id, ("evolution", "EvolutionApiProvider"), "send_text")
            if not destination or not connection:
                _mark_notification(store, tenant_id, notification_id, state="awaiting_provider_configuration")
                return {"state": "awaiting_provider_configuration", "channel": channel}
            secret = SecretResolver(_secret_root(router)).resolve(connection.get("secret_reference"))
            provider = build_provider(connection["provider"], config=connection["config"], secret=secret, transport=_provider_transport(router, transport))
            if not isinstance(provider, EvolutionProvider):
                raise IntegrationError("NOTIFICATION_PROVIDER_INVALID", "Conexão de WhatsApp não implementa EvolutionProvider.")
            instance = str(connection["config"].get("instance") or "").strip()
            if not instance:
                _mark_notification(store, tenant_id, notification_id, state="awaiting_provider_configuration")
                return {"state": "awaiting_provider_configuration", "channel": channel}
            try:
                external = provider.send_text(instance=instance, number="".join(ch for ch in destination if ch.isdigit()), text=str(row["body"]))
            except IntegrationError as exc:
                _mark_notification(store, tenant_id, notification_id, state="retry_pending" if exc.retryable else "failed")
                if exc.retryable:
                    raise TimeoutError(str(exc)) from exc
                return {"state": "failed", "channel": channel, "error_code": exc.code}
            message_id = None
            if isinstance(external, dict):
                message_id = external.get("key", {}).get("id") if isinstance(external.get("key"), dict) else external.get("id") or external.get("messageId")
            _mark_notification(store, tenant_id, notification_id, state="sent", provider_message_id=str(message_id) if message_id else None)
            return {"state": "sent", "channel": channel, "provider_message_id": message_id}
        if channel == "email":
            destination = str((person or {}).get("email") or "").strip()
            connection = _find_connection(store, tenant_id, ("smtp", "EmailProvider", "SmtpEmailProvider"), "send_email")
            if not destination or not connection:
                _mark_notification(store, tenant_id, notification_id, state="awaiting_provider_configuration")
                return {"state": "awaiting_provider_configuration", "channel": channel}
            secret = SecretResolver(_secret_root(router)).resolve(connection.get("secret_reference"))
            provider = build_provider(connection["provider"], config=connection["config"], secret=secret, transport=_provider_transport(router, transport))
            if not isinstance(provider, SmtpEmailProvider):
                raise IntegrationError("NOTIFICATION_PROVIDER_INVALID", "Conexão de e-mail não implementa SmtpEmailProvider.")
            try:
                external = provider.send_message(to=destination, subject=str(row.get("subject") or "Notificação institucional"), text=str(row["body"]))
            except IntegrationError as exc:
                _mark_notification(store, tenant_id, notification_id, state="retry_pending" if exc.retryable else "failed")
                if exc.retryable:
                    raise TimeoutError(str(exc)) from exc
                return {"state": "failed", "channel": channel, "error_code": exc.code}
            message_id = external.get("message_id") if isinstance(external, dict) else None
            _mark_notification(store, tenant_id, notification_id, state="sent", provider_message_id=str(message_id) if message_id else None)
            return {"state": "sent", "channel": channel, "provider_message_id": message_id}
        # Push/SMS permanecem aguardando provider específico, nunca marcados como enviados.
        _mark_notification(store, tenant_id, notification_id, state="awaiting_provider_configuration")
        return {"state": "awaiting_provider_configuration", "channel": channel}

    def signature_otp_delivery_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        payload = dict(envelope.get("payload") or {})
        challenge_id = str(payload.get("challenge_id") or "")
        user_id = str(payload.get("user_id") or "")
        challenge = store.fetch_one("SELECT * FROM signature_otp_challenges WHERE tenant_id=? AND id=? AND user_id=?", (tenant_id, challenge_id, user_id))
        if not challenge:
            return {"state": "ignored", "reason": "challenge_not_found"}
        if challenge.get("consumed_at"):
            return {"state": "consumed", "idempotent": True}
        now = iso_now()
        if str(challenge["expires_at"]) <= now:
            store.execute("UPDATE signature_otp_challenges SET delivery_state='expired',delivery_error_code='OTP_EXPIRED' WHERE tenant_id=? AND id=?", (tenant_id, challenge_id))
            return {"state": "expired"}
        code = derive_otp(router.settings.jwt_secret, challenge_id=challenge_id, user_id=user_id)
        channel = str(challenge["channel"]); destination = str(payload.get("destination") or "").strip()
        provider_name = None; message_id = None
        try:
            if channel == "email":
                connection = _find_connection(store, tenant_id, ("smtp", "EmailProvider", "SmtpEmailProvider"), "send_email")
                if not connection:
                    store.execute("UPDATE signature_otp_challenges SET delivery_state='awaiting_provider_configuration',delivery_error_code='EMAIL_PROVIDER_NOT_CONFIGURED' WHERE tenant_id=? AND id=?", (tenant_id, challenge_id))
                    return {"state": "awaiting_provider_configuration", "channel": channel}
                secret = SecretResolver(_secret_root(router)).resolve(connection.get("secret_reference"))
                provider = build_provider(connection["provider"], config=connection["config"], secret=secret, transport=_provider_transport(router, transport))
                if not isinstance(provider, SmtpEmailProvider):
                    raise IntegrationError("SIGNATURE_OTP_PROVIDER_INVALID", "Provider de e-mail inválido.")
                external = provider.send_message(to=destination, subject="Código de assinatura eletrônica", text=f"Seu código de assinatura é {code}. Ele expira em poucos minutos.")
                provider_name = provider.provider_name; message_id = external.get("message_id") if isinstance(external, dict) else None
            elif channel == "whatsapp":
                connection = _find_connection(store, tenant_id, ("evolution", "EvolutionApiProvider"), "send_text")
                if not connection:
                    store.execute("UPDATE signature_otp_challenges SET delivery_state='awaiting_provider_configuration',delivery_error_code='WHATSAPP_PROVIDER_NOT_CONFIGURED' WHERE tenant_id=? AND id=?", (tenant_id, challenge_id))
                    return {"state": "awaiting_provider_configuration", "channel": channel}
                secret = SecretResolver(_secret_root(router)).resolve(connection.get("secret_reference"))
                provider = build_provider(connection["provider"], config=connection["config"], secret=secret, transport=_provider_transport(router, transport))
                if not isinstance(provider, EvolutionProvider):
                    raise IntegrationError("SIGNATURE_OTP_PROVIDER_INVALID", "Provider WhatsApp inválido.")
                instance = str(connection["config"].get("instance") or "").strip()
                if not instance:
                    raise IntegrationError("SIGNATURE_OTP_PROVIDER_NOT_CONFIGURED", "Instância Evolution não configurada.")
                external = provider.send_text(instance=instance, number="".join(ch for ch in destination if ch.isdigit()), text=f"Seu código de assinatura eletrônica é {code}. Não compartilhe este código.")
                provider_name = provider.provider_name
                if isinstance(external, dict):
                    message_id = external.get("key", {}).get("id") if isinstance(external.get("key"), dict) else external.get("id") or external.get("messageId")
            else:
                raise IntegrationError("SIGNATURE_OTP_CHANNEL_UNSUPPORTED", "Canal OTP não suportado.")
        except IntegrationError as exc:
            store.execute("UPDATE signature_otp_challenges SET delivery_state=?,delivery_error_code=? WHERE tenant_id=? AND id=?", ("retry_pending" if exc.retryable else "failed", exc.code, tenant_id, challenge_id))
            if exc.retryable:
                raise TimeoutError(str(exc)) from exc
            return {"state": "failed", "channel": channel, "error_code": exc.code}
        store.execute("UPDATE signature_otp_challenges SET delivery_state='sent',delivery_provider=?,delivery_message_id=?,delivery_error_code=NULL,delivered_at=? WHERE tenant_id=? AND id=?", (provider_name, str(message_id) if message_id else None, iso_now(), tenant_id, challenge_id))
        # Código deliberadamente NÃO integra o resultado/inbox/outbox.
        return {"state": "sent", "channel": channel, "provider": provider_name, "message_id": message_id}

    def government_education_transmission_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        payload = dict(envelope.get("payload") or {})
        transmission_id = str(envelope.get("aggregate_id") or payload.get("transmission_id") or "")
        row = store.fetch_one(
            "SELECT gt.*,ge.layout_id,ge.reference_period,ge.sha256 AS export_sha256,ge.storage_key,gl.authority,gl.layout_code,gl.version AS layout_version "
            "FROM government_transmissions gt JOIN government_exports ge ON ge.id=gt.export_id "
            "JOIN government_export_layouts gl ON gl.id=ge.layout_id "
            "WHERE gt.tenant_id=? AND gt.id=?",
            (tenant_id, transmission_id),
        )
        if not row:
            return {"state": "ignored", "reason": "transmission_not_found"}
        if row["state"] == "accepted":
            return {"state": "accepted", "protocol": row.get("protocol"), "idempotent": True}
        connection_id = str(row.get("connection_id") or "")
        if not connection_id:
            return {"state": "awaiting_configuration"}
        connection = store.fetch_one("SELECT * FROM integration_connections WHERE tenant_id=? AND id=?", (tenant_id, connection_id))
        if not connection or connection.get("state") not in {"configured", "degraded"}:
            store.execute("UPDATE government_transmissions SET state='awaiting_configuration',updated_at=? WHERE tenant_id=? AND id=?", (iso_now(), tenant_id, transmission_id))
            return {"state": "awaiting_configuration"}
        capabilities = set(_json(connection.get("capabilities_json"), []))
        if "government_submission" not in capabilities and "*" not in capabilities:
            store.execute("UPDATE government_transmissions SET state='failed',last_error='GOVERNMENT_SUBMISSION_CAPABILITY_MISSING',updated_at=? WHERE tenant_id=? AND id=?", (iso_now(), tenant_id, transmission_id))
            return {"state": "failed", "error_code": "GOVERNMENT_SUBMISSION_CAPABILITY_MISSING"}
        config = _json(connection.get("config_json"), {})
        try:
            secret = SecretResolver(_secret_root(router)).resolve(connection.get("secret_reference"))
            provider = build_provider(str(connection["provider"]), config=config, secret=secret, transport=_provider_transport(router, transport))
            if not isinstance(provider, GovernmentEducationProvider):
                raise IntegrationError("GOVERNMENT_PROVIDER_INVALID", "Conexão não implementa GovernmentEducationProvider.")
            storage = router.object_storage(tenant_id)
            content = storage.get_bytes(str(row["storage_key"]))
            digest = __import__("hashlib").sha256(content).hexdigest()
            if digest != row["export_sha256"]:
                raise IntegrationError("GOVERNMENT_EXPORT_INTEGRITY_FAILED", "SHA-256 da exportação não confere antes da transmissão.")
            now = iso_now()
            with store.transaction() as conn:
                conn.execute("UPDATE government_transmissions SET state='transmitting',attempts=attempts+1,submitted_at=COALESCE(submitted_at,?),updated_at=? WHERE tenant_id=? AND id=?", (now, now, tenant_id, transmission_id))
                conn.execute("INSERT INTO government_transmission_events(id,tenant_id,transmission_id,event_type,from_state,to_state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,transmission_id,"dispatch_started",row["state"],"transmitting",json.dumps({"connection_id":connection_id},sort_keys=True),"system-worker",now))
            result = provider.submit_export(
                metadata={"authority":row["authority"],"layout_code":row["layout_code"],"layout_version":row["layout_version"],"reference_period":row["reference_period"],"export_id":row["export_id"]},
                content=content, sha256=digest,
            )
        except IntegrationError as exc:
            now = iso_now(); next_state = "retry_pending" if exc.retryable else "failed"
            with store.transaction() as conn:
                conn.execute("UPDATE government_transmissions SET state=?,last_error=?,updated_at=? WHERE tenant_id=? AND id=?", (next_state, f"{exc.code}: {str(exc)[:500]}", now, tenant_id, transmission_id))
                conn.execute("INSERT INTO government_transmission_events(id,tenant_id,transmission_id,event_type,from_state,to_state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,transmission_id,"provider_error","transmitting",next_state,json.dumps({"code":exc.code,"retryable":exc.retryable},sort_keys=True),"system-worker",now))
            if exc.retryable:
                raise TimeoutError(str(exc)) from exc
            return {"state": next_state, "error_code": exc.code}
        state = str(result.get("state") or "processing")
        protocol = result.get("protocol") if state == "accepted" else None
        if state == "accepted" and not protocol:
            state = "processing"
        now = iso_now(); receipt = dict(result.get("receipt") or {}); receipt.update({"provider_submission_id":result.get("provider_submission_id"),"message":result.get("message")})
        with store.transaction() as conn:
            conn.execute("UPDATE government_transmissions SET state=?,protocol=?,receipt_json=?,provider_status=?,last_error=NULL,completed_at=?,updated_at=? WHERE tenant_id=? AND id=?", (state,protocol,json.dumps(receipt,ensure_ascii=False,sort_keys=True),result.get("provider_status"),now if state in {"accepted","rejected"} else None,now,tenant_id,transmission_id))
            conn.execute("UPDATE government_exports SET state=?,protocol=? WHERE tenant_id=? AND id=?", (state,protocol,tenant_id,row["export_id"]))
            conn.execute("INSERT INTO government_transmission_events(id,tenant_id,transmission_id,event_type,from_state,to_state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,transmission_id,"provider_response","transmitting",state,json.dumps({"protocol":protocol,"provider_status":result.get("provider_status")},sort_keys=True),"system-worker",now))
            if state == "accepted":
                add_outbox(conn,tenant_id=tenant_id,event_type="GovernmentEducationTransmissionAccepted",aggregate_type="government_transmission",aggregate_id=transmission_id,payload={"export_id":row["export_id"],"protocol":protocol},correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
        return {"state":state,"protocol":protocol,"provider_status":result.get("provider_status")}

    def fiscal_emission_source_event(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        return process_emission_trigger(router, tenant_id, str(envelope.get("event_type") or ""), str(envelope.get("aggregate_id") or ""), dict(envelope.get("payload") or {}), str(envelope.get("correlation_id") or envelope.get("event_id") or ""))

    def ibpt_sync_requested(_store, envelope: dict[str, Any]) -> dict[str, Any]:
        payload = envelope.get("payload") or {}
        run_id = str(payload.get("run_id") or envelope.get("aggregate_id") or "")
        if not run_id:
            return {"state": "ignored", "reason": "sync_run_id_missing"}
        return execute_ibpt_sync(router, tenant_id=tenant_id, run_id=run_id, transport=transport)

    return {
        "FiscalDocumentRequested": fiscal_requested,
        "FiscalDocumentCancellationRequested": fiscal_cancel_requested,
        "FiscalDocumentQueryRequested": fiscal_query_requested,
        "FiscalDocumentSubstitutionRequested": fiscal_substitution_requested,
        "FiscalInutilizationRequested": fiscal_inutilization_requested,
        "FiscalDocumentProviderEventRequested": fiscal_provider_event_requested,
        "SaleCompleted": fiscal_emission_source_event,
        "ServiceOrderConfirmed": fiscal_emission_source_event,
        "ServiceCompetenceBilled": fiscal_emission_source_event,
        "PaymentConfirmed": fiscal_emission_source_event,
        "ChargeCreated": fiscal_emission_source_event,
        "NotificationRequested": notification_requested,
        "SignatureOtpDeliveryRequested": signature_otp_delivery_requested,
        "IbptSyncRequested": ibpt_sync_requested,
        "GovernmentEducationTransmissionRequested": government_education_transmission_requested,
    }
