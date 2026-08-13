from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import Request

from app.modules.fiscal.presentation.document_delivery_schemas import (
    FiscalDeliveryPolicyCreate,
    FiscalDeliveryPolicyPublish,
    FiscalDocumentRenderRequest,
    FiscalDocumentRetryRequest,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser


class FiscalRetryScheduled(TimeoutError):
    """Sinaliza ao worker um retry fiscal com countdown definido pela política versionada."""

    def __init__(self, message: str, *, delay_seconds: int, max_attempts: int):
        super().__init__(message)
        self.delay_seconds = max(0, int(delay_seconds))
        self.max_attempts = max(1, int(max_attempts))


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def _policy_result(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "code": row["code"], "name": row["name"],
        "document_type": row["document_type"], "provider_code": row.get("provider_code"),
        "environment": row["environment"], "valid_from": row["valid_from"], "valid_until": row.get("valid_until"),
        "priority": int(row["priority"]), "max_attempts": int(row["max_attempts"]),
        "base_delay_seconds": int(row["base_delay_seconds"]), "max_delay_seconds": int(row["max_delay_seconds"]),
        "backoff_multiplier": str(row["backoff_multiplier"]), "jitter_seconds": int(row["jitter_seconds"]),
        "auto_retry": bool(row["auto_retry"]),
        "contingency_after_attempts": int(row["contingency_after_attempts"]) if row.get("contingency_after_attempts") is not None else None,
        "contingency_mode": row.get("contingency_mode"), "notes": row.get("notes"),
        "state": row["state"], "version": int(row["version"]), "published_at": row.get("published_at"),
    }


def list_delivery_policies(request: Request, tenant_id: str) -> dict[str, Any]:
    rows = request.state.store.fetch_all(
        "SELECT * FROM fiscal_document_delivery_policies WHERE tenant_id=? ORDER BY code,version DESC,created_at DESC",
        (tenant_id,),
    )
    return {"items": [_policy_result(dict(item)) for item in rows]}


def create_delivery_policy(
    data: FiscalDeliveryPolicyCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str,
) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-delivery-policy:{tenant_id}:{data.code}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        version_row = conn.execute(
            "SELECT COALESCE(MAX(version),0) AS version FROM fiscal_document_delivery_policies WHERE tenant_id=? AND code=?",
            (tenant_id, data.code),
        ).fetchone()
        version = int(version_row["version"] if version_row else 0) + 1
        policy_id = uuid7(); now = iso_now()
        conn.execute(
            """INSERT INTO fiscal_document_delivery_policies(
               id,tenant_id,code,name,document_type,provider_code,environment,valid_from,valid_until,priority,
               max_attempts,base_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_seconds,auto_retry,
               contingency_after_attempts,contingency_mode,notes,state,version,created_by,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?,?,?)""",
            (
                policy_id, tenant_id, data.code, data.name, data.document_type, data.provider_code, data.environment,
                str(data.valid_from), str(data.valid_until) if data.valid_until else None, data.priority,
                data.max_attempts, data.base_delay_seconds, data.max_delay_seconds, str(data.backoff_multiplier),
                data.jitter_seconds, 1 if data.auto_retry else 0, data.contingency_after_attempts,
                data.contingency_mode, data.notes, version, user.id, now, now,
            ),
        )
        result = {"id": policy_id, "code": data.code, "state": "draft", "version": version}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="create", aggregate_type="fiscal_document_delivery_policy", aggregate_id=policy_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentDeliveryPolicyCreated", aggregate_type="fiscal_document_delivery_policy", aggregate_id=policy_id, payload=result, correlation_id=request.state.correlation_id)
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
        return 201, result


def publish_delivery_policy(policy_id: str, data: FiscalDeliveryPolicyPublish, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        raw = conn.execute("SELECT * FROM fiscal_document_delivery_policies WHERE tenant_id=? AND id=?", (tenant_id, policy_id)).fetchone()
        if not raw:
            raise DomainError("FISCAL_DELIVERY_POLICY_NOT_FOUND", "Política fiscal de entrega não localizada.", 404)
        row = dict(raw)
        if int(row["version"]) != data.expected_version:
            raise DomainError("VERSION_CONFLICT", "Versão divergente da política fiscal de entrega.", 409)
        if row["state"] == "published":
            return _policy_result(row)
        if row["state"] != "draft":
            raise DomainError("FISCAL_DELIVERY_POLICY_STATE", "Somente política em rascunho pode ser publicada.", 409)
        overlaps = conn.execute(
            """SELECT id FROM fiscal_document_delivery_policies
               WHERE tenant_id=? AND code=? AND state='published' AND id<>?
                 AND valid_from<=COALESCE(?, '9999-12-31') AND (valid_until IS NULL OR valid_until>=?)""",
            (tenant_id, row["code"], policy_id, row.get("valid_until"), row["valid_from"]),
        ).fetchall()
        now = iso_now(); superseded = [item["id"] for item in overlaps]
        for old_id in superseded:
            conn.execute("UPDATE fiscal_document_delivery_policies SET state='superseded',updated_at=? WHERE tenant_id=? AND id=?", (now, tenant_id, old_id))
        conn.execute("UPDATE fiscal_document_delivery_policies SET state='published',published_by=?,published_at=?,updated_at=? WHERE tenant_id=? AND id=?", (user.id, now, now, tenant_id, policy_id))
        updated = dict(row); updated.update({"state": "published", "published_by": user.id, "published_at": now, "updated_at": now})
        result = {**_policy_result(updated), "superseded_ids": superseded, "reason": data.reason}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="publish", aggregate_type="fiscal_document_delivery_policy", aggregate_id=policy_id, correlation_id=request.state.correlation_id, before={"state": row["state"]}, after=result, reason=data.reason)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentDeliveryPolicyPublished", aggregate_type="fiscal_document_delivery_policy", aggregate_id=policy_id, payload={"id": policy_id, "version": row["version"], "superseded_ids": superseded}, correlation_id=request.state.correlation_id)
        return result


def resolve_delivery_policy(db, *, tenant_id: str, document: dict[str, Any], provider_code: str | None = None) -> dict[str, Any] | None:
    occurred_on = str(document.get("created_at") or iso_now())[:10]
    sql = """SELECT * FROM fiscal_document_delivery_policies
           WHERE tenant_id=? AND state='published' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?)
             AND document_type IN ('any',?) AND environment IN ('any',?)
           ORDER BY priority ASC,version DESC,created_at DESC"""
    params = (tenant_id, occurred_on, occurred_on, document["document_type"], document["environment"])
    rows = db.fetch_all(sql, params) if hasattr(db, "fetch_all") else db.execute(sql, params).fetchall()
    candidates: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        configured_provider = str(row.get("provider_code") or "").strip()
        if configured_provider and configured_provider != str(provider_code or ""):
            continue
        specificity = int(row["document_type"] != "any") + int(row["environment"] != "any") + int(bool(configured_provider))
        row["_specificity"] = specificity
        candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-int(item["_specificity"]), int(item["priority"]), -int(item["version"])))
    return _policy_result(candidates[0])


def retry_plan(policy: dict[str, Any] | None, *, document_id: str, attempt_number: int, now: datetime | None = None) -> dict[str, Any]:
    if not policy:
        return {"policy_id": None, "allowed": True, "auto_retry": True, "attempt_number": attempt_number, "next_retry_at": None, "contingency_mode": None, "limit_reached": False}
    max_attempts = int(policy["max_attempts"])
    limit_reached = attempt_number >= max_attempts
    delay = min(
        int(policy["max_delay_seconds"]),
        int(Decimal(str(policy["base_delay_seconds"])) * (Decimal(str(policy["backoff_multiplier"])) ** max(0, attempt_number - 1))),
    )
    jitter = int(policy.get("jitter_seconds") or 0)
    if jitter:
        seed = int(hashlib.sha256(f"{document_id}:{attempt_number}".encode()).hexdigest()[:8], 16)
        delay += seed % (jitter + 1)
    current = now or datetime.now(UTC)
    next_retry = (current + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z") if not limit_reached else None
    contingency = None
    threshold = policy.get("contingency_after_attempts")
    if threshold is not None and attempt_number >= int(threshold):
        contingency = policy.get("contingency_mode")
    return {
        "policy_id": policy["id"], "allowed": not limit_reached, "auto_retry": bool(policy["auto_retry"]),
        "attempt_number": attempt_number, "next_retry_at": next_retry, "contingency_mode": contingency,
        "limit_reached": limit_reached, "delay_seconds": delay,
    }


def record_rejection(
    conn, *, tenant_id: str, document_id: str, attempt_id: str | None, error_code: str | None,
    error_message: str | None, retryable: bool, provider_status: str, category: str, plan: dict[str, Any],
    explanation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rejection_id = uuid7(); now = iso_now()
    state = "retry_scheduled" if retryable and plan.get("allowed") else "open"
    payload = {
        "id": rejection_id, "fiscal_document_id": document_id, "error_code": error_code,
        "error_message": (error_message or "")[:2000] or None, "category": category, "retryable": bool(retryable),
        "provider_status": provider_status, "state": state, "next_retry_at": plan.get("next_retry_at"),
        "delivery_policy_id": plan.get("policy_id"), "attempt_number": plan.get("attempt_number"),
        "limit_reached": bool(plan.get("limit_reached")), "explanation": explanation or {}, "created_at": now,
    }
    conn.execute(
        """INSERT INTO fiscal_document_rejections(
           id,tenant_id,fiscal_document_id,attempt_id,delivery_policy_id,error_code,error_message,category,retryable,
           provider_status,state,next_retry_at,explanation_json,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rejection_id, tenant_id, document_id, attempt_id, plan.get("policy_id"), error_code, payload["error_message"], category,
         1 if retryable else 0, provider_status, state, plan.get("next_retry_at"), json.dumps(payload["explanation"], ensure_ascii=False, sort_keys=True), now),
    )
    return payload


def resolve_rejections(conn, *, tenant_id: str, document_id: str, resolution: str) -> None:
    conn.execute(
        "UPDATE fiscal_document_rejections SET state='resolved',resolved_at=?,resolution=? WHERE tenant_id=? AND fiscal_document_id=? AND state<>'resolved'",
        (iso_now(), resolution, tenant_id, document_id),
    )


def latest_rejection(request: Request, tenant_id: str, document_id: str) -> dict[str, Any]:
    document = request.state.store.fetch_one("SELECT id,state FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
    if not document:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    row = request.state.store.fetch_one(
        "SELECT * FROM fiscal_document_rejections WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
        (tenant_id, document_id),
    )
    if not row:
        return {"fiscal_document_id": document_id, "state": document["state"], "rejection": None}
    item = dict(row); item["retryable"] = bool(item["retryable"]); item["explanation"] = _loads(item.pop("explanation_json", None), {})
    return {"fiscal_document_id": document_id, "state": document["state"], "rejection": item}


def queue_document_retry(document_id: str, data: FiscalDocumentRetryRequest, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    now = iso_now()
    with request.state.store.transaction() as conn:
        raw = conn.execute("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id)).fetchone()
        if not raw:
            raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
        document = dict(raw)
        if document["state"] in {"authorized", "cancelled", "substituted"}:
            raise DomainError("FISCAL_DOCUMENT_FINAL", "Documento fiscal já está em estado final.", 409)
        if not document.get("provider_connection_id"):
            raise DomainError("FISCAL_PROVIDER_REQUIRED", "Configure um provider fiscal antes de reprocessar.", 409)
        connection = conn.execute("SELECT provider FROM integration_connections WHERE tenant_id=? AND id=?", (tenant_id, document["provider_connection_id"])).fetchone()
        provider_code = connection["provider"] if connection else None
        policy = resolve_delivery_policy(conn, tenant_id=tenant_id, document=document, provider_code=provider_code)
        attempt_row = conn.execute("SELECT COALESCE(MAX(attempt_number),0) AS n FROM fiscal_document_attempts WHERE tenant_id=? AND fiscal_document_id=? AND operation='issue'", (tenant_id, document_id)).fetchone()
        attempts = int(attempt_row["n"] if attempt_row else 0)
        plan = retry_plan(policy, document_id=document_id, attempt_number=max(1, attempts))
        if policy and plan["limit_reached"] and not data.force:
            raise DomainError("FISCAL_RETRY_LIMIT_REACHED", "Limite de tentativas da política fiscal atingido. Use force somente após análise operacional.", 409)
        conn.execute("UPDATE fiscal_documents SET state='requested',provider_status='queued',error_code=NULL,error_message=NULL,next_retry_at=NULL,delivery_policy_id=?,updated_at=? WHERE tenant_id=? AND id=?", (policy["id"] if policy else None, now, tenant_id, document_id))
        conn.execute("UPDATE fiscal_document_rejections SET state='retry_requested',next_retry_at=NULL WHERE tenant_id=? AND fiscal_document_id=? AND state IN ('open','retry_scheduled')", (tenant_id, document_id))
        result = {"id": document_id, "state": "requested", "provider_status": "queued", "reason": data.reason, "force": data.force, "delivery_policy_id": policy["id"] if policy else None, "attempts": attempts}
        conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (uuid7(), tenant_id, document_id, "retry_requested", "requested", document.get("provider_connection_id"), json.dumps(result, ensure_ascii=False, sort_keys=True), now))
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="retry", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=request.state.correlation_id, before={"state": document["state"], "attempts": attempts}, after=result, reason=data.reason)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentRequested", aggregate_type="fiscal_document", aggregate_id=document_id, payload=result, correlation_id=request.state.correlation_id)
        return result


def _ascii(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _deterministic_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "40 800 Td", "12 TL"]
    for index, line in enumerate(lines):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_escape(_ascii(line)[:110])}) Tj")
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n% deterministic fiscal rendering\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(out)); out.extend(f"{index} 0 obj\n".encode()); out.extend(obj); out.extend(b"\nendobj\n")
    xref = len(out); out.extend(f"xref\n0 {len(objects)+1}\n".encode()); out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(out)


def render_fiscal_document(document_id: str, data: FiscalDocumentRenderRequest, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    store = request.state.store
    document = store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (tenant_id, document_id))
    if not document:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    document = dict(document)
    artifact_type = {"NF-e": "danfe_local", "NFC-e": "danfce_local", "NFS-e": "danfse_local"}[document["document_type"]]
    previous = store.fetch_one("SELECT * FROM fiscal_document_artifacts WHERE tenant_id=? AND fiscal_document_id=? AND artifact_type=? ORDER BY created_at DESC LIMIT 1", (tenant_id, document_id, artifact_type))
    storage = request.app.state.data_router.object_storage(tenant_id)
    if previous and not data.force and storage.exists(previous["storage_key"]):
        return {"id": previous["id"], "fiscal_document_id": document_id, "artifact_type": artifact_type, "storage_key": previous["storage_key"], "sha256": previous["sha256"], "bytes_count": previous["bytes_count"], "idempotent": True}
    profile = store.fetch_one("SELECT establishment_name,cnpj,uf FROM fiscal_profiles WHERE tenant_id=? AND id=?", (tenant_id, document.get("fiscal_profile_id"))) if document.get("fiscal_profile_id") else None
    response = _loads(document.get("response_json"), {})
    request_payload = _loads(document.get("request_json"), {})
    xml_sha = document.get("xml_sha256")
    lines = [
        {"NF-e": "DANFE - Documento Auxiliar da NF-e", "NFC-e": "DANFC-e - Documento Auxiliar da NFC-e", "NFS-e": "DANFSe - Documento Auxiliar da NFS-e"}[document["document_type"]],
        f"Estabelecimento: {(profile or {}).get('establishment_name') or 'nao informado'}",
        f"CNPJ: {(profile or {}).get('cnpj') or 'nao informado'}  UF: {(profile or {}).get('uf') or 'nao informada'}",
        f"Documento: {document['document_type']}  Ambiente: {document['environment']}  Estado: {document['state']}",
        f"Origem: {document['source_type']} / {document['source_id']}",
        f"Chave: {document.get('access_key') or 'nao autorizada'}",
        f"Protocolo: {document.get('protocol') or 'nao autorizado'}  Numero: {document.get('number') or '-'}  Serie: {document.get('series') or '-'}",
        f"XML SHA-256: {xml_sha or 'indisponivel'}",
        f"Total: {(_loads(document.get('totals_json'), {}) or {}).get('total') or request_payload.get('total') or '-'}",
        f"Provider status: {document.get('provider_status') or '-'}  Contingencia: {document.get('contingency_mode') or 'nao'}",
        "Artefato local deterministico. Nao representa autorizacao fiscal por si so.",
    ]
    pdf = _deterministic_pdf(lines)
    obj = storage.put_bytes(f"fiscal/{document_id}/rendered/{artifact_type}.pdf", pdf, content_type="application/pdf")
    now = iso_now(); artifact_id = uuid7()
    with store.transaction() as conn:
        existing = conn.execute("SELECT id FROM fiscal_document_artifacts WHERE tenant_id=? AND fiscal_document_id=? AND artifact_type=? AND sha256=?", (tenant_id, document_id, artifact_type, obj.sha256)).fetchone()
        if existing:
            artifact_id = existing["id"]
        else:
            conn.execute("INSERT INTO fiscal_document_artifacts(id,tenant_id,fiscal_document_id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (artifact_id, tenant_id, document_id, artifact_type, "application/pdf", obj.key, obj.sha256, obj.bytes, None, now))
        result = {"id": artifact_id, "fiscal_document_id": document_id, "artifact_type": artifact_type, "storage_key": obj.key, "sha256": obj.sha256, "bytes_count": obj.bytes, "idempotent": bool(existing)}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="render", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentRendered", aggregate_type="fiscal_document", aggregate_id=document_id, payload=result, correlation_id=request.state.correlation_id)
    return result


def list_fiscal_document_artifacts(request: Request, tenant_id: str, document_id: str) -> dict[str, Any]:
    """Lista somente artefatos do documento dentro do tenant autenticado."""
    document = request.state.store.fetch_one(
        "SELECT id FROM fiscal_documents WHERE tenant_id=? AND id=?",
        (tenant_id, document_id),
    )
    if not document:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    storage = request.app.state.data_router.object_storage(tenant_id)
    rows = request.state.store.fetch_all(
        """SELECT id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at
           FROM fiscal_document_artifacts
           WHERE tenant_id=? AND fiscal_document_id=?
           ORDER BY created_at DESC,id DESC""",
        (tenant_id, document_id),
    )
    items: list[dict[str, Any]] = []
    for raw in rows:
        item = dict(raw)
        storage_key = str(item.pop("storage_key"))
        item["available"] = bool(storage.exists(storage_key))
        items.append(item)
    return {"fiscal_document_id": document_id, "items": items}


def read_fiscal_document_artifact(
    request: Request, tenant_id: str, document_id: str, artifact_id: str, user: CurrentUser,
) -> tuple[bytes, dict[str, Any]]:
    """Lê um artefato e bloqueia resposta quando o objeto não confere com o hash persistido."""
    document = request.state.store.fetch_one(
        "SELECT id FROM fiscal_documents WHERE tenant_id=? AND id=?",
        (tenant_id, document_id),
    )
    if not document:
        raise DomainError("FISCAL_DOCUMENT_NOT_FOUND", "Documento fiscal não localizado.", 404)
    row = request.state.store.fetch_one(
        """SELECT id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at
           FROM fiscal_document_artifacts
           WHERE tenant_id=? AND fiscal_document_id=? AND id=?""",
        (tenant_id, document_id, artifact_id),
    )
    if not row:
        raise DomainError("FISCAL_ARTIFACT_NOT_FOUND", "Artefato fiscal não localizado.", 404)
    artifact = dict(row)
    storage = request.app.state.data_router.object_storage(tenant_id)
    storage_key = str(artifact["storage_key"])
    if not storage.exists(storage_key):
        raise DomainError("FISCAL_ARTIFACT_NOT_FOUND", "Objeto do artefato fiscal não está disponível.", 404)
    content = storage.get_bytes(storage_key)
    actual_sha256 = hashlib.sha256(content).hexdigest()
    expected_sha256 = str(artifact["sha256"])
    if actual_sha256 != expected_sha256:
        with request.state.store.transaction() as conn:
            add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="artifact_integrity_failure", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=request.state.correlation_id, after={"artifact_id": artifact_id, "expected_sha256": expected_sha256, "actual_sha256": actual_sha256, "bytes_count": len(content)}, reason="SHA-256 do objeto diverge do registro persistido.")
            add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentArtifactIntegrityFailed", aggregate_type="fiscal_document", aggregate_id=document_id, payload={"artifact_id": artifact_id, "expected_sha256": expected_sha256, "actual_sha256": actual_sha256}, correlation_id=request.state.correlation_id)
        raise DomainError("FISCAL_ARTIFACT_INTEGRITY_FAILED", "A integridade do artefato fiscal não pôde ser comprovada.", 409)
    with request.state.store.transaction() as conn:
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="artifact_download", aggregate_type="fiscal_document", aggregate_id=document_id, correlation_id=request.state.correlation_id, after={"artifact_id": artifact_id, "artifact_type": artifact["artifact_type"], "sha256": expected_sha256, "bytes_count": len(content)})
        add_outbox(conn, tenant_id=tenant_id, event_type="FiscalDocumentArtifactDownloaded", aggregate_type="fiscal_document", aggregate_id=document_id, payload={"artifact_id": artifact_id, "artifact_type": artifact["artifact_type"], "sha256": expected_sha256, "bytes_count": len(content)}, correlation_id=request.state.correlation_id)
    artifact.pop("storage_key", None)
    artifact["filename"] = f"{artifact['artifact_type']}-{document_id}.pdf"
    return content, artifact
