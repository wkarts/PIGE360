from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.integrations.providers import DisabledTransport, IntegrationError, SecretResolver
from app.shared.signatures.providers import GovBrAdvancedSignatureProvider, IcpBrasilCertificateProvider
from app.shared.signatures.pades import PadesError, embed_validated_external_cades, prepare_incremental_signature
from app.shared.security.auth import CurrentUser, current_user
from app.shared.signatures.otp import derive_otp, evidence_hmac, signature_domain_key

router = APIRouter(tags=["contracts-signatures"])
VARIABLE = re.compile(r"{{\s*([a-zA-Z0-9_.-]+)\s*}}")
CONTRACT_ROLES = {"tenant_owner", "institution_director", "secretary", "finance_manager", "finance_operator"}


class ContractCreateInput(BaseModel):
    contract_type: str
    number: str | None = None
    enrollment_id: str | None = None
    financial_contract_id: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    parties: list[dict[str, Any]] = Field(default_factory=list)


class ContractAction(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)


class TemplateCreateInput(BaseModel):
    contract_type: str
    name: str = Field(min_length=2, max_length=200)


class TemplateVersionInput(BaseModel):
    body_text: str = Field(min_length=10, max_length=200000)
    variables: list[str] = Field(default_factory=list)
    rules: dict[str, Any] = Field(default_factory=dict)


class GenerateContractInput(BaseModel):
    expected_version: int = Field(ge=1)
    template_version_id: str | None = None
    template_text: str | None = Field(default=None, min_length=10, max_length=200000)
    variables: dict[str, Any]
    source_references: dict[str, Any] = Field(default_factory=dict)


class SendSignatureInput(BaseModel):
    expected_version: int = Field(ge=1)
    signing_order: Literal["parallel", "sequential", "hybrid"] = "parallel"
    signers: list[dict[str, Any]] = Field(min_length=1)


class SignInput(BaseModel):
    consent: bool
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method: Literal["simple_electronic"] = "simple_electronic"
    otp_challenge_id: str | None = None
    otp_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class SignatureOtpRequestInput(BaseModel):
    channel: Literal["email", "whatsapp"] = "email"


class DeclineInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ValidateFileInput(BaseModel):
    content_base64: str


class ContractPatchInput(BaseModel):
    expected_version: int = Field(ge=1)
    effective_from: date | None = None
    effective_until: date | None = None
    financial_contract_id: str | None = None
    reason: str = Field(min_length=3, max_length=2000)


class ContractRenewInput(BaseModel):
    expected_version: int = Field(ge=1)
    effective_from: date
    effective_until: date | None = None
    number: str | None = None
    reason: str = Field(min_length=3, max_length=2000)


class ContractAmendmentInput(BaseModel):
    amendment_type: Literal["value", "term", "responsible_party", "service", "scholarship", "class_change", "renegotiation", "other"]
    title: str = Field(min_length=3, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    effective_from: date | None = None


class TemplatePreviewInput(BaseModel):
    version_id: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class EnvelopeActionInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ProviderTestInput(BaseModel):
    provider: Literal["internal_electronic", "icp_brasil_pades", "govbr_advanced", "external"]
    connection_id: str | None = None


class GovBrAuthorizationInput(BaseModel):
    connection_id: str
    redirect_uri: str = Field(min_length=12, max_length=500)


class GovBrCallbackInput(BaseModel):
    connection_id: str
    attempt_id: str
    state: str = Field(min_length=64, max_length=64)
    code: str = Field(min_length=3, max_length=4096)
    redirect_uri: str = Field(min_length=12, max_length=500)


class IcpBrasilDetachedSignInput(BaseModel):
    connection_id: str


def _tenant(user: CurrentUser) -> str:
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Rota disponível somente no domínio da instituição.", 404)
    return user.tenant_id


def _authorize(user: CurrentUser) -> str:
    tid = _tenant(user)
    if not set(user.roles).intersection(CONTRACT_ROLES):
        raise DomainError("PERMISSION_DENIED", "Permissão insuficiente para contratos.", 403, "Acesso negado")
    return tid


def _contract_row(request: Request, tenant_id: str, contract_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one(
        "SELECT * FROM legal_contracts WHERE id=? AND tenant_id=?", (contract_id, tenant_id)
    )
    if not row:
        raise DomainError("CONTRACT_NOT_FOUND", "Contrato não localizado.", 404)
    return row


def _record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "tenant_id": row["tenant_id"], "contract_type": row["contract_type"],
        "number": row["number"], "enrollment_id": row.get("enrollment_id"),
        "financial_contract_id": row.get("financial_contract_id"), "template_version_id": row.get("template_version_id"),
        "state": row["state"], "effective_from": row.get("effective_from"), "effective_until": row.get("effective_until"),
        "validation_code": row.get("validation_code"), "document_sha256": row.get("document_sha256"),
        "document_storage_key": row.get("document_storage_key"), "signed_document_sha256": row.get("signed_document_sha256"),
        "signed_document_storage_key": row.get("signed_document_storage_key"), "signature_profile": row.get("signature_profile"), "snapshot_id": row.get("snapshot_id"),
        "version": row["version"], "created_by": row["created_by"], "updated_by": row["updated_by"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }




def _append_contract_version(conn, row: dict[str, Any], *, actor_id: str | None, reason: str | None = None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO contract_versions(id,tenant_id,contract_id,version,state,effective_from,effective_until,document_sha256,document_storage_key,signed_document_sha256,signed_document_storage_key,signature_profile,snapshot_id,reason,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (uuid7(), row["tenant_id"], row["id"], int(row["version"]), row["state"], row.get("effective_from"), row.get("effective_until"), row.get("document_sha256"), row.get("document_storage_key"), row.get("signed_document_sha256"), row.get("signed_document_storage_key"), row.get("signature_profile"), row.get("snapshot_id"), reason, actor_id, iso_now()),
    )


def _template_version(request: Request, tenant_id: str, template_id: str, version_id: str | None = None) -> dict[str, Any]:
    if version_id:
        row = request.state.store.fetch_one("SELECT * FROM contract_template_versions WHERE tenant_id=? AND template_id=? AND id=?", (tenant_id, template_id, version_id))
    else:
        row = request.state.store.fetch_one("SELECT * FROM contract_template_versions WHERE tenant_id=? AND template_id=? ORDER BY version DESC LIMIT 1", (tenant_id, template_id))
    if not row:
        raise DomainError("CONTRACT_TEMPLATE_VERSION_NOT_FOUND", "Versão do modelo não localizada.", 404)
    return row


def _template_structure(version: dict[str, Any]) -> dict[str, Any]:
    referenced = sorted(set(VARIABLE.findall(version["body_text"])))
    try:
        declared = json.loads(version.get("variables_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        declared = []
    if not isinstance(declared, list):
        declared = []
    declared = [str(item) for item in declared]
    invalid_declared = sorted({item for item in declared if not re.fullmatch(r"[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*", item)})
    duplicates = sorted({item for item in declared if declared.count(item) > 1})
    undeclared = sorted(set(referenced) - set(declared))
    declared_unused = sorted(set(declared) - set(referenced))
    return {
        "referenced_variables": referenced,
        "declared_variables": declared,
        "undeclared_variables": undeclared,
        "declared_unused": declared_unused,
        "invalid_declared_variables": invalid_declared,
        "duplicate_declared_variables": duplicates,
        "valid_structure": not undeclared and not invalid_declared and not duplicates,
    }


def _resolve(path: str, data: dict[str, Any]) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise DomainError("CONTRACT_VARIABLE_MISSING", f"Variável obrigatória ausente: {path}.", 422)
    return current


def _render_text(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = _resolve(match.group(1), variables)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    return VARIABLE.sub(replace, template)


def _pdf(content: str, title: str) -> bytes:
    out = io.BytesIO(); c = canvas.Canvas(out, pagesize=A4, pageCompression=1); width, height = A4
    c.setTitle(title); c.setAuthor("Tenant PIGE360"); y = height - 64; c.setFont("Helvetica-Bold", 14); c.drawString(50, y, title[:90]); y -= 30; c.setFont("Helvetica", 10)
    for paragraph in content.splitlines() or [content]:
        words = paragraph.split(); line = ""
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, "Helvetica", 10) > width - 100:
                c.drawString(50, y, line); y -= 15; line = word
                if y < 64: c.showPage(); c.setFont("Helvetica", 10); y = height - 64
            else: line = test
        if line: c.drawString(50, y, line); y -= 15
        y -= 6
        if y < 64: c.showPage(); c.setFont("Helvetica", 10); y = height - 64
    c.showPage(); c.save(); return out.getvalue()


def _mask_destination(channel: str, destination: str) -> str:
    if channel == "email" and "@" in destination:
        local, domain = destination.split("@", 1)
        visible = local[:1] + ("***" if len(local) > 1 else "*")
        return f"{visible}@{domain}"
    digits = "".join(ch for ch in destination if ch.isdigit())
    return ("*" * max(0, len(digits) - 4)) + digits[-4:] if digits else "***"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _otp_challenge_for_sign(request: Request, *, tenant_id: str, envelope_id: str, signer: dict[str, Any], user: CurrentUser, data: SignInput) -> dict[str, Any] | None:
    settings = request.app.state.settings
    if not settings.signature_internal_otp_required:
        return None
    if not data.otp_challenge_id or not data.otp_code:
        raise DomainError("SIGNATURE_OTP_REQUIRED", "Confirme o código OTP antes de assinar.", 422)
    challenge = request.state.store.fetch_one(
        "SELECT * FROM signature_otp_challenges WHERE tenant_id=? AND id=? AND envelope_id=? AND signer_id=? AND user_id=?",
        (tenant_id, data.otp_challenge_id, envelope_id, signer["id"], user.id),
    )
    if not challenge:
        raise DomainError("SIGNATURE_OTP_CHALLENGE_NOT_FOUND", "Desafio OTP não localizado para este signatário.", 404)
    if challenge.get("consumed_at"):
        raise DomainError("SIGNATURE_OTP_ALREADY_USED", "O código OTP já foi utilizado.", 409)
    if int(challenge.get("attempts") or 0) >= int(challenge.get("max_attempts") or settings.signature_otp_max_attempts):
        raise DomainError("SIGNATURE_OTP_LOCKED", "Número máximo de tentativas do OTP excedido.", 423)
    if _parse_utc(str(challenge["expires_at"])) <= datetime.now(UTC):
        raise DomainError("SIGNATURE_OTP_EXPIRED", "O código OTP expirou.", 410)
    expected = derive_otp(settings.jwt_secret, challenge_id=str(challenge["id"]), user_id=user.id)
    if not hmac.compare_digest(expected, data.otp_code):
        request.state.store.execute(
            "UPDATE signature_otp_challenges SET attempts=attempts+1 WHERE tenant_id=? AND id=?",
            (tenant_id, challenge["id"]),
        )
        raise DomainError("SIGNATURE_OTP_INVALID", "Código OTP inválido.", 422)
    return challenge


@router.get("/contracts", operation_id="list_legal_contracts")
def list_contracts(request: Request, state: str | None = None, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); sql = "SELECT * FROM legal_contracts WHERE tenant_id=?"; params: list[Any] = [tid]
    if state: sql += " AND state=?"; params.append(state)
    sql += " ORDER BY created_at DESC"
    return {"items": [_record(x) for x in request.state.store.fetch_all(sql, params)]}


@router.post("/contracts", status_code=201, operation_id="create_legal_contract")
def create_contract(data: ContractCreateInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); cid = uuid7(); now = iso_now(); number = data.number or f"CTR-{datetime.now(UTC):%Y%m%d}-{cid[-8:].upper()}"
    if data.enrollment_id:
        if not request.state.store.fetch_one("SELECT id FROM enrollments WHERE tenant_id=? AND id=?", (tid, data.enrollment_id)):
            raise DomainError("ENROLLMENT_NOT_FOUND", "Matrícula não localizada.", 404)
    if data.financial_contract_id:
        if not request.state.store.fetch_one("SELECT id FROM financial_contracts WHERE tenant_id=? AND id=?", (tid, data.financial_contract_id)):
            raise DomainError("FINANCIAL_CONTRACT_NOT_FOUND", "Contrato financeiro não localizado.", 404)
    result = {"id": cid, "number": number, "contract_type": data.contract_type, "state": "draft", "version": 1}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO legal_contracts(id,tenant_id,contract_type,number,enrollment_id,financial_contract_id,state,effective_from,effective_until,version,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (cid,tid,data.contract_type,number,data.enrollment_id,data.financial_contract_id,"draft",str(data.effective_from) if data.effective_from else None,str(data.effective_until) if data.effective_until else None,1,user.id,user.id,now,now))
        for idx, party in enumerate(data.parties, 1):
            person_id = party.get("person_id")
            if person_id and not conn.execute("SELECT id FROM people WHERE tenant_id=? AND id=?", (tid, person_id)).fetchone():
                raise DomainError("PERSON_NOT_FOUND", f"Parte {idx}: pessoa não localizada.", 404)
            conn.execute("INSERT INTO contract_parties(id,tenant_id,contract_id,party_type,person_id,legal_name,document_number,role,signing_required,signing_order,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (uuid7(),tid,cid,party.get("party_type","person"),person_id,party.get("legal_name"),party.get("document_number"),party.get("role","contractor"),1 if party.get("signing_required",True) else 0,int(party.get("signing_order",idx)),now))
        _append_contract_version(conn,{"id":cid,"tenant_id":tid,"version":1,"state":"draft","effective_from":str(data.effective_from) if data.effective_from else None,"effective_until":str(data.effective_until) if data.effective_until else None,"document_sha256":None,"document_storage_key":None,"snapshot_id":None},actor_id=user.id)
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="contract",aggregate_id=cid,correlation_id=request.state.correlation_id,after=result)
        add_outbox(conn,tenant_id=tid,event_type="ContractCreated",aggregate_type="contract",aggregate_id=cid,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/contracts/{contract_id}", operation_id="get_legal_contract")
def get_contract(contract_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); row = _contract_row(request, tid, contract_id); result = _record(row)
    result["parties"] = request.state.store.fetch_all("SELECT * FROM contract_parties WHERE tenant_id=? AND contract_id=? ORDER BY signing_order", (tid, contract_id))
    return result


@router.patch("/contracts/{contract_id}", operation_id="patch_legal_contract")
def patch_contract(contract_id: str, data: ContractPatchInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); row = _contract_row(request, tid, contract_id)
    if int(row["version"]) != data.expected_version:
        raise DomainError("VERSION_CONFLICT", "Versão divergente.", 409)
    if row["state"] != "draft":
        raise DomainError("CONTRACT_IMMUTABLE_AFTER_GENERATION", "Após gerar o documento, alterações materiais exigem nova versão/aditivo.", 409)
    if data.financial_contract_id and not request.state.store.fetch_one("SELECT id FROM financial_contracts WHERE tenant_id=? AND id=?", (tid, data.financial_contract_id)):
        raise DomainError("FINANCIAL_CONTRACT_NOT_FOUND", "Contrato financeiro não localizado.", 404)
    version = int(row["version"]) + 1; now = iso_now()
    effective_from = str(data.effective_from) if data.effective_from else row.get("effective_from")
    effective_until = str(data.effective_until) if data.effective_until else row.get("effective_until")
    financial_contract_id = data.financial_contract_id if data.financial_contract_id is not None else row.get("financial_contract_id")
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE legal_contracts SET effective_from=?,effective_until=?,financial_contract_id=?,version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?", (effective_from,effective_until,financial_contract_id,version,user.id,now,tid,contract_id))
        updated={**row,"effective_from":effective_from,"effective_until":effective_until,"financial_contract_id":financial_contract_id,"version":version,"updated_by":user.id,"updated_at":now}
        _append_contract_version(conn,updated,actor_id=user.id,reason=data.reason)
        conn.execute("INSERT INTO contract_events(id,tenant_id,contract_id,event_type,payload_json,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,contract_id,"updated",json.dumps({"version":version},sort_keys=True),user.id,data.reason,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="update",aggregate_type="contract",aggregate_id=contract_id,correlation_id=request.state.correlation_id,before=_record(row),after=_record(updated),reason=data.reason)
    return _record(updated)


@router.get("/contracts/{contract_id}/versions", operation_id="list_contract_versions")
def contract_versions(contract_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); _contract_row(request,tid,contract_id)
    rows=request.state.store.fetch_all("SELECT * FROM contract_versions WHERE tenant_id=? AND contract_id=? ORDER BY version DESC",(tid,contract_id))
    return {"items":rows}


@router.get("/contracts/{contract_id}/document", operation_id="download_contract_document")
def contract_document(contract_id: str, request: Request, original: bool = False, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); row=_contract_row(request,tid,contract_id)
    if original or not row.get("signed_document_storage_key"):
        key=row.get("document_storage_key"); digest=row.get("document_sha256"); revision="original"
    else:
        key=row.get("signed_document_storage_key"); digest=row.get("signed_document_sha256"); revision="signed"
    if not key or not digest: raise DomainError("CONTRACT_DOCUMENT_MISSING","Documento do contrato ainda não foi gerado.",404)
    storage=request.app.state.data_router.object_storage(tid)
    if not storage.exists(key): raise DomainError("CONTRACT_DOCUMENT_MISSING","Documento não está disponível no storage.",503)
    content=storage.get_bytes(key)
    if not hmac.compare_digest(hashlib.sha256(content).hexdigest(),str(digest)): raise DomainError("CONTRACT_DOCUMENT_INTEGRITY_FAILED","Integridade do PDF inválida.",409)
    return Response(content=content,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{row["number"]}.pdf"',"X-Content-SHA256":str(digest),"X-PIGE360-Document-Revision":revision,"X-PIGE360-Signature-Profile":str(row.get("signature_profile") or "")})


@router.get("/contracts/{contract_id}/evidence", operation_id="get_contract_evidence")
def contract_evidence(contract_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); _contract_row(request,tid,contract_id)
    snapshots=request.state.store.fetch_all("SELECT * FROM contract_snapshots WHERE tenant_id=? AND contract_id=? ORDER BY generated_at DESC",(tid,contract_id))
    envelopes=request.state.store.fetch_all("SELECT * FROM signature_envelopes WHERE tenant_id=? AND contract_id=? ORDER BY created_at DESC",(tid,contract_id))
    for item in envelopes:
        item["signers"]=json.loads(item.pop("signers_json") or "[]"); item["evidence"]=json.loads(item.pop("evidence_json") or "[]")
        item["validations"]=request.state.store.fetch_all("SELECT * FROM signature_validations WHERE tenant_id=? AND envelope_id=? ORDER BY created_at DESC",(tid,item["id"]))
        item["artifacts"]=request.state.store.fetch_all("SELECT id,signer_id,provider,artifact_type,sha256,storage_key,certificate_subject,certificate_serial,metadata_json,created_at FROM signature_artifacts WHERE tenant_id=? AND envelope_id=? ORDER BY created_at DESC",(tid,item["id"]))
        for artifact in item["artifacts"]:
            artifact["metadata"] = json.loads(artifact.pop("metadata_json") or "{}")
        item["evidence_packages"]=request.state.store.fetch_all("SELECT id,sha256,created_at FROM signature_evidence_packages WHERE tenant_id=? AND envelope_id=? ORDER BY created_at DESC",(tid,item["id"]))
    return {"snapshots":snapshots,"envelopes":envelopes}


@router.get("/contracts/{contract_id}/audit", operation_id="get_contract_audit")
def contract_audit(contract_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); _contract_row(request, tid, contract_id)
    events = request.state.store.fetch_all("SELECT * FROM contract_events WHERE tenant_id=? AND contract_id=? ORDER BY created_at", (tid, contract_id))
    audits = request.state.store.fetch_all("SELECT * FROM audit_log WHERE tenant_id=? AND aggregate_type='contract' AND aggregate_id=?", (tid, contract_id))
    envelope_ids = [row["id"] for row in request.state.store.fetch_all("SELECT id FROM signature_envelopes WHERE tenant_id=? AND contract_id=?", (tid, contract_id))]
    for envelope_id in envelope_ids:
        audits.extend(request.state.store.fetch_all("SELECT * FROM audit_log WHERE tenant_id=? AND aggregate_type='signature_envelope' AND aggregate_id=?", (tid, envelope_id)))
    audits.sort(key=lambda item: str(item.get("created_at") or ""))
    for item in events:
        try:
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
    return {"events": events, "audit": audits}


@router.get("/contract-templates", operation_id="list_contract_templates")
def list_templates(request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); return {"items": request.state.store.fetch_all("SELECT * FROM contract_templates WHERE tenant_id=? ORDER BY name", (tid,))}


@router.post("/contract-templates", status_code=201, operation_id="create_contract_template")
def create_template(data: TemplateCreateInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); template_id = uuid7(); now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO contract_templates(id,tenant_id,contract_type,name,state,current_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (template_id,tid,data.contract_type,data.name,"draft",0,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="contract_template",aggregate_id=template_id,correlation_id=request.state.correlation_id,after={"name":data.name,"contract_type":data.contract_type})
    return {"id":template_id,"contract_type":data.contract_type,"name":data.name,"state":"draft","current_version":0}


@router.post("/contract-templates/{template_id}/versions", status_code=201, operation_id="create_contract_template_version")
def create_template_version(template_id: str, data: TemplateVersionInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); template = request.state.store.fetch_one("SELECT * FROM contract_templates WHERE tenant_id=? AND id=?", (tid,template_id))
    if not template: raise DomainError("CONTRACT_TEMPLATE_NOT_FOUND", "Modelo não localizado.", 404)
    version = int(template["current_version"]) + 1; version_id = uuid7(); now = iso_now(); digest = hashlib.sha256(data.body_text.encode()).hexdigest()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO contract_template_versions(id,tenant_id,template_id,version,body_text,variables_json,rules_json,sha256,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (version_id,tid,template_id,version,data.body_text,json.dumps(data.variables,ensure_ascii=False),json.dumps(data.rules,ensure_ascii=False,sort_keys=True),digest,"draft",user.id,now))
        conn.execute("UPDATE contract_templates SET current_version=?,updated_at=? WHERE tenant_id=? AND id=?", (version,now,tid,template_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="version",aggregate_type="contract_template",aggregate_id=template_id,correlation_id=request.state.correlation_id,after={"version_id":version_id,"version":version,"sha256":digest})
    return {"id":version_id,"template_id":template_id,"version":version,"sha256":digest,"state":"draft"}


@router.post("/contract-templates/{template_id}/validate", operation_id="validate_contract_template")
def validate_template(template_id: str, data: TemplatePreviewInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); version = _template_version(request, tid, template_id, data.version_id)
    structure = _template_structure(version)
    missing = []
    for path in structure["referenced_variables"]:
        try:
            _resolve(path, data.variables)
        except DomainError:
            missing.append(path)
    return {
        "template_id": template_id, "version_id": version["id"], "version": version["version"], "sha256": version["sha256"],
        **structure, "missing_preview_variables": missing, "preview_complete": structure["valid_structure"] and not missing,
    }


@router.post("/contract-templates/{template_id}/preview", operation_id="preview_contract_template")
def preview_template(template_id: str, data: TemplatePreviewInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); version=_template_version(request,tid,template_id,data.version_id)
    rendered=_render_text(version["body_text"],data.variables); digest=hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return {"template_id":template_id,"version_id":version["id"],"version":version["version"],"rendered_text":rendered,"rendered_sha256":digest}


@router.post("/contract-templates/{template_id}/publish", operation_id="publish_contract_template")
def publish_template(template_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); template=request.state.store.fetch_one("SELECT * FROM contract_templates WHERE tenant_id=? AND id=?",(tid,template_id))
    if not template or int(template["current_version"]) < 1:
        raise DomainError("CONTRACT_TEMPLATE_NOT_READY", "Modelo sem versão publicável.", 409)
    candidate = _template_version(request, tid, template_id)
    structure = _template_structure(candidate)
    if not structure["valid_structure"]:
        raise DomainError("CONTRACT_TEMPLATE_INVALID", "Modelo possui variáveis não declaradas, inválidas ou duplicadas.", 422, errors=[
            {"field": "variables", "code": "INVALID_TEMPLATE_VARIABLES", "message": json.dumps(structure, ensure_ascii=False, sort_keys=True)}
        ])
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE contract_template_versions SET state='superseded' WHERE tenant_id=? AND template_id=? AND state='published'",(tid,template_id));conn.execute("UPDATE contract_template_versions SET state='published' WHERE tenant_id=? AND template_id=? AND version=?",(tid,template_id,template["current_version"]));conn.execute("UPDATE contract_templates SET state='published',updated_at=? WHERE tenant_id=? AND id=?",(now,tid,template_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="contract_template",aggregate_id=template_id,correlation_id=request.state.correlation_id,after={"version":template["current_version"]})
    return {"id":template_id,"state":"published","version":template["current_version"]}


@router.post("/contracts/{contract_id}/generate", operation_id="generate_contract")
def generate_contract(contract_id: str, data: GenerateContractInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id = _authorize(user); row = _contract_row(request, tenant_id, contract_id)
    if row["version"] != data.expected_version: raise DomainError("VERSION_CONFLICT", "Versão divergente.", 409)
    if row["state"] != "draft": raise DomainError("CONTRACT_NOT_DRAFT", "Apenas contrato em rascunho pode ser gerado.", 409)
    template_text = data.template_text; template_version_id = data.template_version_id
    if template_version_id:
        version_row = request.state.store.fetch_one("SELECT * FROM contract_template_versions WHERE tenant_id=? AND id=? AND state='published'", (tenant_id,template_version_id))
        if not version_row: raise DomainError("CONTRACT_TEMPLATE_VERSION_NOT_PUBLISHED","Versão de modelo publicada não localizada.",404)
        template_text = version_row["body_text"]
    if not template_text: raise DomainError("CONTRACT_TEMPLATE_REQUIRED","Informe uma versão de modelo publicada ou texto do modelo.",422)
    rendered = _render_text(template_text, data.variables); pdf = _pdf(rendered, f"Contrato {row['number']}"); digest = hashlib.sha256(pdf).hexdigest(); now = iso_now(); snapshot_id = uuid7(); validation_code = uuid7().replace("-", "")[:20].upper(); version = row["version"] + 1
    storage=request.app.state.data_router.object_storage(tenant_id);prefix=f"contracts/{datetime.now(UTC).strftime('%Y')}/{contract_id}";storage_key=f"{prefix}/generated-v{version}.pdf"
    stored_pdf=storage.put_bytes(storage_key,pdf,content_type="application/pdf")
    if stored_pdf.sha256 != digest:raise DomainError("CONTRACT_STORAGE_INTEGRITY_FAILED","Falha de integridade ao armazenar o contrato.",500)
    snapshot = {"contract_id":contract_id,"template_version_id":template_version_id,"schema_version":1,"rendered_variables":data.variables,"source_references":data.source_references,"rendered_text":rendered,"generated_document_sha256":digest,"validation_code":validation_code,"generated_at":now,"generated_by":user.id}
    snapshot_bytes=json.dumps(snapshot,ensure_ascii=False,indent=2).encode("utf-8");snapshot_key=f"{prefix}/source-snapshot-v{version}.json";snapshot_digest=hashlib.sha256(snapshot_bytes).hexdigest();storage.put_bytes(snapshot_key,snapshot_bytes,content_type="application/json")
    sums=f"{digest}  generated-v{version}.pdf\n{snapshot_digest}  source-snapshot-v{version}.json\n".encode("utf-8");storage.put_bytes(f"{prefix}/SHA256SUMS",sums,content_type="text/plain")
    before = _record(row)
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE legal_contracts SET state='generated',template_version_id=?,validation_code=?,document_sha256=?,document_storage_key=?,snapshot_id=?,version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?", (template_version_id,validation_code,digest,storage_key,snapshot_id,version,user.id,now,tenant_id,contract_id))
        _append_contract_version(conn,{**row,"state":"generated","version":version,"template_version_id":template_version_id,"validation_code":validation_code,"document_sha256":digest,"document_storage_key":storage_key,"snapshot_id":snapshot_id},actor_id=user.id,reason="Documento congelado gerado")
        conn.execute("INSERT INTO contract_snapshots(id,tenant_id,contract_id,template_version_id,schema_version,rendered_variables_json,source_references_json,generated_document_sha256,storage_key,generated_at,generated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (snapshot_id,tenant_id,contract_id,template_version_id,1,json.dumps(data.variables,ensure_ascii=False,sort_keys=True),json.dumps(data.source_references,ensure_ascii=False,sort_keys=True),digest,storage_key,now,user.id))
        conn.execute("INSERT INTO contract_events(id,tenant_id,contract_id,event_type,payload_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tenant_id,contract_id,"generated",json.dumps({"snapshot_id":snapshot_id,"sha256":digest},sort_keys=True),user.id,now))
        result={"contract_id":contract_id,"state":"generated","version":version,"document_sha256":digest,"storage_key":storage_key,"validation_code":validation_code,"snapshot_id":snapshot_id,"generated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="generate",aggregate_type="contract",aggregate_id=contract_id,correlation_id=request.state.correlation_id,before=before,after=result);add_outbox(conn,tenant_id=tenant_id,event_type="ContractGenerated",aggregate_type="contract",aggregate_id=contract_id,payload=result,correlation_id=request.state.correlation_id)
    return result


def _transition(contract_id: str, data: ContractAction, request: Request, user: CurrentUser, expected: set[str], target: str, event: str):
    tenant_id = _authorize(user); now = iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM legal_contracts WHERE id=? AND tenant_id=?",(contract_id,tenant_id)).fetchone()
        if not raw: raise DomainError("CONTRACT_NOT_FOUND","Contrato não localizado.",404)
        row=dict(raw)
        if row["version"] != data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"] not in expected: raise DomainError("INVALID_STATE_TRANSITION",f"Não é possível mudar {row['state']} para {target}.",409)
        before=_record(row);version=row["version"]+1
        conn.execute("UPDATE legal_contracts SET state=?,version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?",(target,version,user.id,now,tenant_id,contract_id));_append_contract_version(conn,{**row,"state":target,"version":version},actor_id=user.id,reason=data.reason);conn.execute("INSERT INTO contract_events(id,tenant_id,contract_id,event_type,payload_json,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,contract_id,target,"{}",user.id,data.reason,now));result={**before,"state":target,"version":version,"updated_by":user.id,"updated_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action=target,aggregate_type="contract",aggregate_id=contract_id,correlation_id=request.state.correlation_id,before=before,after=result,reason=data.reason);add_outbox(conn,tenant_id=tenant_id,event_type=event,aggregate_type="contract",aggregate_id=contract_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/contracts/{contract_id}/approve", operation_id="approve_contract")
def approve(contract_id:str,data:ContractAction,request:Request,user:CurrentUser=Depends(current_user)):return _transition(contract_id,data,request,user,{"generated","under_internal_review"},"approved","ContractApproved")
@router.post("/contracts/{contract_id}/cancel", operation_id="cancel_contract")
def cancel(contract_id:str,data:ContractAction,request:Request,user:CurrentUser=Depends(current_user)):return _transition(contract_id,data,request,user,{"draft","generated","under_internal_review","approved","awaiting_signatures","partially_signed"},"cancelled","ContractCancelled")
@router.post("/contracts/{contract_id}/terminate", operation_id="terminate_contract")
def terminate(contract_id:str,data:ContractAction,request:Request,user:CurrentUser=Depends(current_user)):return _transition(contract_id,data,request,user,{"active","signed","suspended"},"terminated","ContractTerminated")


@router.post("/contracts/{contract_id}/renew", status_code=201, operation_id="renew_contract")
def renew_contract(contract_id: str, data: ContractRenewInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); row=_contract_row(request,tid,contract_id)
    if int(row["version"])!=data.expected_version: raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
    if row["state"] not in {"signed","active","expired","terminated"}: raise DomainError("CONTRACT_NOT_RENEWABLE","Contrato ainda não está em estado renovável.",409)
    new_id=uuid7(); now=iso_now(); number=data.number or f"{row['number']}-R{now[:4]}-{new_id[-4:].upper()}"
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO legal_contracts(id,tenant_id,contract_type,number,enrollment_id,financial_contract_id,state,effective_from,effective_until,version,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(new_id,tid,row["contract_type"],number,row.get("enrollment_id"),row.get("financial_contract_id"),"draft",str(data.effective_from),str(data.effective_until) if data.effective_until else None,1,user.id,user.id,now,now))
        parties=conn.execute("SELECT * FROM contract_parties WHERE tenant_id=? AND contract_id=? ORDER BY signing_order",(tid,contract_id)).fetchall()
        for raw_party in parties:
            party = dict(raw_party)
            conn.execute("INSERT INTO contract_parties(id,tenant_id,contract_id,party_type,person_id,legal_name,document_number,role,signing_required,signing_order,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,new_id,party["party_type"],party.get("person_id"),party.get("legal_name"),party.get("document_number"),party["role"],party["signing_required"],party["signing_order"],now))
        conn.execute("INSERT INTO contract_relationships(id,tenant_id,source_contract_id,target_contract_id,relationship_type,created_by,created_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,contract_id,new_id,"renewal",user.id,now))
        _append_contract_version(conn,{"id":new_id,"tenant_id":tid,"version":1,"state":"draft","effective_from":str(data.effective_from),"effective_until":str(data.effective_until) if data.effective_until else None,"document_sha256":None,"document_storage_key":None,"snapshot_id":None},actor_id=user.id,reason=data.reason)
        conn.execute("INSERT INTO contract_events(id,tenant_id,contract_id,event_type,payload_json,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,contract_id,"renewed",json.dumps({"renewed_contract_id":new_id,"number":number},sort_keys=True),user.id,data.reason,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="renew",aggregate_type="contract",aggregate_id=contract_id,correlation_id=request.state.correlation_id,after={"renewed_contract_id":new_id,"number":number},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="ContractRenewed",aggregate_type="contract",aggregate_id=contract_id,payload={"renewed_contract_id":new_id,"number":number},correlation_id=request.state.correlation_id)
    return {"id":new_id,"number":number,"contract_type":row["contract_type"],"state":"draft","version":1,"renews_contract_id":contract_id}


@router.get("/contracts/{contract_id}/amendments", operation_id="list_contract_amendments")
def list_amendments(contract_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); _contract_row(request, tid, contract_id)
    rows = request.state.store.fetch_all(
        "SELECT a.*, c.number AS amendment_number, c.state AS document_state, c.version AS document_version, c.document_sha256 "
        "FROM contract_amendments a JOIN legal_contracts c ON c.tenant_id=a.tenant_id AND c.id=a.amendment_contract_id "
        "WHERE a.tenant_id=? AND a.contract_id=? ORDER BY a.created_at DESC",
        (tid, contract_id),
    )
    for item in rows:
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
    return {"items": rows}


@router.post("/contracts/{contract_id}/amendments", status_code=201, operation_id="create_contract_amendment")
def create_amendment(contract_id: str, data: ContractAmendmentInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user); row = _contract_row(request, tid, contract_id)
    if row["state"] not in {"approved", "awaiting_signatures", "partially_signed", "signed", "active", "suspended"}:
        raise DomainError("CONTRACT_NOT_AMENDABLE", "Contrato não aceita aditivo neste estado.", 409)
    aid = uuid7(); amendment_contract_id = uuid7(); now = iso_now()
    amendment_number = f"{row['number']}-AD{aid[-4:].upper()}"
    effective_from = str(data.effective_from) if data.effective_from else None
    result = {
        "id": aid, "contract_id": contract_id, "amendment_contract_id": amendment_contract_id,
        "amendment_number": amendment_number, "amendment_type": data.amendment_type, "title": data.title,
        "effective_from": effective_from, "state": "draft", "document_state": "draft", "version": 1,
    }
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO legal_contracts(id,tenant_id,contract_type,number,enrollment_id,financial_contract_id,state,effective_from,effective_until,version,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (amendment_contract_id, tid, f"amendment:{data.amendment_type}", amendment_number, row.get("enrollment_id"), row.get("financial_contract_id"), "draft", effective_from, None, 1, user.id, user.id, now, now),
        )
        parties = conn.execute("SELECT * FROM contract_parties WHERE tenant_id=? AND contract_id=? ORDER BY signing_order", (tid, contract_id)).fetchall()
        for party in parties:
            party = dict(party)
            conn.execute(
                "INSERT INTO contract_parties(id,tenant_id,contract_id,party_type,person_id,legal_name,document_number,role,signing_required,signing_order,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (uuid7(), tid, amendment_contract_id, party["party_type"], party.get("person_id"), party.get("legal_name"), party.get("document_number"), party["role"], party["signing_required"], party["signing_order"], now),
            )
        conn.execute(
            "INSERT INTO contract_amendments(id,tenant_id,contract_id,amendment_contract_id,amendment_type,title,payload_json,effective_from,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, tid, contract_id, amendment_contract_id, data.amendment_type, data.title, json.dumps(data.payload, ensure_ascii=False, sort_keys=True), effective_from, "draft", 1, user.id, now, now),
        )
        conn.execute(
            "INSERT INTO contract_relationships(id,tenant_id,source_contract_id,target_contract_id,relationship_type,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
            (uuid7(), tid, contract_id, amendment_contract_id, "amendment", user.id, now),
        )
        _append_contract_version(conn, {"id": amendment_contract_id, "tenant_id": tid, "version": 1, "state": "draft", "effective_from": effective_from, "effective_until": None, "document_sha256": None, "document_storage_key": None, "snapshot_id": None}, actor_id=user.id, reason=f"Aditivo do contrato {row['number']}")
        conn.execute(
            "INSERT INTO contract_events(id,tenant_id,contract_id,event_type,payload_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?)",
            (uuid7(), tid, contract_id, "amendment_created", json.dumps({**result, "payload": data.payload}, ensure_ascii=False, sort_keys=True), user.id, now),
        )
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="create_amendment", aggregate_type="contract", aggregate_id=contract_id, correlation_id=request.state.correlation_id, after=result)
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="create", aggregate_type="contract", aggregate_id=amendment_contract_id, correlation_id=request.state.correlation_id, after={"number": amendment_number, "contract_type": f"amendment:{data.amendment_type}", "state": "draft"}, reason=f"Aditivo de {row['number']}")
        add_outbox(conn, tenant_id=tid, event_type="ContractAmendmentCreated", aggregate_type="contract", aggregate_id=contract_id, payload=result, correlation_id=request.state.correlation_id)
    return result


@router.post("/contracts/{contract_id}/send-for-signature", operation_id="send_contract_for_signature")
def send_signature(contract_id:str,data:SendSignatureInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_authorize(user);row=_contract_row(request,tenant_id,contract_id)
    if row["version"]!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
    if row["state"]!="approved":raise DomainError("CONTRACT_NOT_APPROVED","Contrato deve ser aprovado antes da assinatura.",409)
    digest=row.get("document_sha256")
    if not digest:raise DomainError("CONTRACT_DOCUMENT_MISSING","Documento congelado não localizado.",409)
    normalized=[]
    for index,s in enumerate(data.signers):
        if not s.get("name") or not s.get("email"):raise DomainError("INVALID_SIGNER",f"Signatário {index+1} incompleto.",422)
        normalized.append({"id":s.get("id") or uuid7(),"user_id":s.get("user_id"),"name":s["name"],"email":s["email"],"phone":s.get("phone"),"role":s.get("role","signer"),"required":s.get("required",True),"order":s.get("order",index+1),"status":"pending"})
    envelope_id=uuid7();now=iso_now();version=row["version"]+1
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO signature_envelopes(id,tenant_id,contract_id,document_sha256,state,signing_order,signers_json,evidence_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(envelope_id,tenant_id,contract_id,digest,"sent",data.signing_order,json.dumps(normalized,ensure_ascii=False,sort_keys=True),"[]",now,now));conn.execute("UPDATE legal_contracts SET state='awaiting_signatures',version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?",(version,user.id,now,tenant_id,contract_id));_append_contract_version(conn,{**row,"state":"awaiting_signatures","version":version},actor_id=user.id,reason="Enviado para assinatura");result={"id":envelope_id,"contract_id":contract_id,"document_sha256":digest,"state":"sent","signing_order":data.signing_order,"signers":normalized,"created_at":now,"contract_version":version};add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="send_for_signature",aggregate_type="signature_envelope",aggregate_id=envelope_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tenant_id,event_type="ContractSentForSignature",aggregate_type="contract",aggregate_id=contract_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.get("/signature-envelopes/{envelope_id}",operation_id="get_signature_envelope_details")
def get_envelope(envelope_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);row=request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE id=? AND tenant_id=?",(envelope_id,tenant_id))
    if not row:raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND","Envelope não localizado.",404)
    row["signers"]=json.loads(row.pop("signers_json"));row["evidence"]=json.loads(row.pop("evidence_json"));return row


@router.post("/signature-envelopes/{envelope_id}/otp", operation_id="request_signature_otp")
def request_signature_otp(envelope_id: str, data: SignatureOtpRequestInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id = _tenant(user)
    row = request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id))
    if not row:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if row["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita confirmação OTP neste estado.", 409)
    signers = json.loads(row["signers_json"] or "[]")
    signer = next((item for item in signers if item.get("user_id") == user.id), None)
    if not signer:
        raise DomainError("USER_NOT_SIGNER", "Usuário autenticado não é signatário deste envelope.", 403)
    if signer.get("status") == "signed":
        raise DomainError("SIGNER_ALREADY_SIGNED", "O signatário já concluiu sua assinatura.", 409)
    if data.channel == "email":
        destination = str(signer.get("email") or "").strip()
    else:
        destination = str(signer.get("phone") or "").strip()
    if not destination:
        raise DomainError("SIGNATURE_OTP_DESTINATION_MISSING", "O signatário não possui destino verificado para o canal selecionado.", 422)
    challenge_id = uuid7(); now_dt = datetime.now(UTC); now = now_dt.isoformat().replace("+00:00", "Z")
    expires_at = (now_dt + timedelta(seconds=request.app.state.settings.signature_otp_ttl_seconds)).isoformat().replace("+00:00", "Z")
    masked = _mask_destination(data.channel, destination)
    with request.state.store.transaction() as conn:
        conn.execute(
            "INSERT INTO signature_otp_challenges(id,tenant_id,envelope_id,signer_id,user_id,channel,destination_masked,expires_at,attempts,max_attempts,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (challenge_id, tenant_id, envelope_id, signer["id"], user.id, data.channel, masked, expires_at, 0, request.app.state.settings.signature_otp_max_attempts, now),
        )
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="request_otp", aggregate_type="signature_envelope", aggregate_id=envelope_id, correlation_id=request.state.correlation_id, after={"challenge_id": challenge_id, "channel": data.channel, "destination_masked": masked, "expires_at": expires_at})
        add_outbox(conn, tenant_id=tenant_id, event_type="SignatureOtpDeliveryRequested", aggregate_type="signature_envelope", aggregate_id=envelope_id, payload={"challenge_id": challenge_id, "signer_id": signer["id"], "user_id": user.id, "channel": data.channel, "destination": destination, "expires_at": expires_at}, correlation_id=request.state.correlation_id)
    result = {"challenge_id": challenge_id, "channel": data.channel, "destination_masked": masked, "expires_at": expires_at, "state": "queued"}
    if request.app.state.settings.environment == "testing":
        result["test_code"] = derive_otp(request.app.state.settings.jwt_secret, challenge_id=challenge_id, user_id=user.id)
    return result


@router.post("/signature-envelopes/{envelope_id}/sign",operation_id="sign_signature_envelope")
def sign_envelope(envelope_id:str,data:SignInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id = _tenant(user)
    if not data.consent:
        raise DomainError("SIGNATURE_CONSENT_REQUIRED", "O consentimento expresso é obrigatório.", 422)

    # Validação de credencial/OTP antes da transação de consolidação. Isso permite
    # registrar tentativa inválida sem competir pelo mesmo lock SQLite e mantém o
    # caminho PostgreSQL igualmente seguro. O estado é revalidado dentro da transação.
    preview = request.state.store.fetch_one(
        "SELECT * FROM signature_envelopes WHERE id=? AND tenant_id=?", (envelope_id, tenant_id)
    )
    if not preview:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if preview["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura.", 409)
    if not hmac.compare_digest(str(preview["document_sha256"]), data.document_sha256):
        raise DomainError("DOCUMENT_HASH_MISMATCH", "O documento apresentado não corresponde ao envelope.", 409)
    preview_signers = json.loads(preview["signers_json"] or "[]")
    preview_signer = next((item for item in preview_signers if item.get("user_id") == user.id), None)
    if not preview_signer:
        raise DomainError("USER_NOT_SIGNER", "Usuário autenticado não é signatário deste envelope.", 403)
    if preview_signer.get("status") == "signed":
        return {"status": "already_signed", "envelope_id": envelope_id, "signer_id": preview_signer["id"]}
    challenge = _otp_challenge_for_sign(
        request, tenant_id=tenant_id, envelope_id=envelope_id, signer=preview_signer, user=user, data=data
    )

    now = iso_now()
    with request.state.store.transaction() as conn:
        raw = conn.execute("SELECT * FROM signature_envelopes WHERE id=? AND tenant_id=?", (envelope_id, tenant_id)).fetchone()
        if not raw:
            raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
        row = dict(raw)
        if row["state"] not in {"sent", "partially_signed"}:
            raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura.", 409)
        if not hmac.compare_digest(str(row["document_sha256"]), data.document_sha256):
            raise DomainError("DOCUMENT_HASH_MISMATCH", "O documento apresentado não corresponde ao envelope.", 409)
        signers = json.loads(row["signers_json"] or "[]")
        signer = next((item for item in signers if item.get("user_id") == user.id), None)
        if not signer:
            raise DomainError("USER_NOT_SIGNER", "Usuário autenticado não é signatário deste envelope.", 403)
        if signer.get("status") == "signed":
            return {"status": "already_signed", "envelope_id": envelope_id, "signer_id": signer["id"]}

        if challenge:
            challenge_raw = conn.execute(
                "SELECT * FROM signature_otp_challenges WHERE tenant_id=? AND id=? AND consumed_at IS NULL",
                (tenant_id, challenge["id"]),
            ).fetchone()
            if not challenge_raw:
                raise DomainError("SIGNATURE_OTP_ALREADY_USED", "O código OTP já foi utilizado.", 409)
            consumed = conn.execute(
                "UPDATE signature_otp_challenges SET consumed_at=? WHERE tenant_id=? AND id=? AND consumed_at IS NULL",
                (now, tenant_id, challenge["id"]),
            )
            if getattr(consumed, "rowcount", 0) != 1:
                raise DomainError("SIGNATURE_OTP_ALREADY_USED", "O código OTP já foi utilizado.", 409)

        evidence = {
            "id": uuid7(), "signer_id": signer["id"], "user_id": user.id, "consent": True,
            "method": data.method, "document_sha256": data.document_sha256,
            "ip": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent"),
            "correlation_id": request.state.correlation_id, "signed_at": now,
        }
        if challenge:
            evidence.update({"otp_challenge_id": challenge["id"], "otp_channel": challenge["channel"], "otp_verified_at": now})
        canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        evidence["evidence_hmac_sha256"] = evidence_hmac(request.app.state.settings.jwt_secret, canonical)
        signer.update({"status": "signed", "signed_at": now, "evidence_id": evidence["id"]})
        evidences = json.loads(row["evidence_json"] or "[]"); evidences.append(evidence)
        required = [item for item in signers if item.get("required", True)]
        state = "signed" if all(item["status"] == "signed" for item in required) else "partially_signed"
        contract_state = "signed" if state == "signed" else "partially_signed"
        conn.execute(
            "UPDATE signature_envelopes SET state=?,signers_json=?,evidence_json=?,updated_at=? WHERE id=?",
            (state, json.dumps(signers, ensure_ascii=False, sort_keys=True), json.dumps(evidences, ensure_ascii=False, sort_keys=True), now, envelope_id),
        )
        contract_raw = conn.execute("SELECT * FROM legal_contracts WHERE tenant_id=? AND id=?", (tenant_id, row["contract_id"])).fetchone()
        contract_row = dict(contract_raw); new_contract_version = int(contract_row["version"]) + 1
        conn.execute(
            "UPDATE legal_contracts SET state=?,version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?",
            (contract_state, new_contract_version, user.id, now, tenant_id, row["contract_id"]),
        )
        _append_contract_version(conn, {**contract_row, "state": contract_state, "version": new_contract_version}, actor_id=user.id, reason="Manifestação de assinatura")
        result = {"envelope_id": envelope_id, "state": state, "contract_id": row["contract_id"], "contract_state": contract_state, "signer_id": signer["id"], "evidence": evidence}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="sign", aggregate_type="signature_envelope", aggregate_id=envelope_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="ContractFullySigned" if state == "signed" else "ContractPartiallySigned", aggregate_type="contract", aggregate_id=row["contract_id"], payload=result, correlation_id=request.state.correlation_id)
    return result


@router.post("/signature-envelopes/{envelope_id}/decline",operation_id="decline_signature_envelope")
def decline(envelope_id:str,data:DeclineInput,request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id=_tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        raw=conn.execute("SELECT * FROM signature_envelopes WHERE id=? AND tenant_id=?",(envelope_id,tenant_id)).fetchone()
        if not raw:raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND","Envelope não localizado.",404)
        row=dict(raw);signers=json.loads(row["signers_json"]);signer=next((s for s in signers if s.get("user_id")==user.id),None)
        if not signer:raise DomainError("USER_NOT_SIGNER","Usuário não é signatário.",403)
        signer.update({"status":"declined","declined_at":now,"decline_reason":data.reason});conn.execute("UPDATE signature_envelopes SET state='declined',signers_json=?,updated_at=? WHERE id=?",(json.dumps(signers,ensure_ascii=False,sort_keys=True),now,envelope_id));result={"envelope_id":envelope_id,"state":"declined","reason":data.reason,"signer_id":signer["id"]};add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="decline",aggregate_type="signature_envelope",aggregate_id=envelope_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tenant_id,event_type="ContractDeclined",aggregate_type="contract",aggregate_id=row["contract_id"],payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/signature-envelopes/{envelope_id}/remind", operation_id="remind_signature_envelope")
def remind_envelope(envelope_id: str, data: EnvelopeActionInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); row=request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?",(tid,envelope_id))
    if not row: raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND","Envelope não localizado.",404)
    if row["state"] not in {"sent","partially_signed"}: raise DomainError("ENVELOPE_NOT_PENDING","Envelope não possui assinaturas pendentes.",409)
    signers=json.loads(row["signers_json"] or "[]");pending=[{"signer_id":x.get("id"),"email":x.get("email"),"role":x.get("role")} for x in signers if x.get("status")=="pending"]
    now=iso_now();attempt_id=uuid7();result={"envelope_id":envelope_id,"pending_signers":len(pending),"state":"queued","requested_at":now}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO signature_attempts(id,tenant_id,envelope_id,provider,action,state,request_json,response_json,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(attempt_id,tid,envelope_id,"notification","remind","queued",json.dumps({"reason":data.reason,"signers":pending},ensure_ascii=False,sort_keys=True),"{}",request.state.correlation_id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="remind",aggregate_type="signature_envelope",aggregate_id=envelope_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="ContractSignatureReminderRequested",aggregate_type="signature_envelope",aggregate_id=envelope_id,payload={"attempt_id":attempt_id,"signers":pending},correlation_id=request.state.correlation_id)
    return result


@router.post("/signature-envelopes/{envelope_id}/retry", operation_id="retry_signature_envelope")
def retry_envelope(envelope_id: str, data: EnvelopeActionInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); row=request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?",(tid,envelope_id))
    if not row: raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND","Envelope não localizado.",404)
    if row["state"] in {"signed","declined"}: raise DomainError("ENVELOPE_FINALIZED","Envelope finalizado não pode ser reenviado.",409)
    attempt_id=uuid7();now=iso_now();result={"attempt_id":attempt_id,"envelope_id":envelope_id,"state":"queued"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO signature_attempts(id,tenant_id,envelope_id,provider,action,state,request_json,response_json,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(attempt_id,tid,envelope_id,"configured","retry","queued",json.dumps({"reason":data.reason},ensure_ascii=False),"{}",request.state.correlation_id,now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="retry",aggregate_type="signature_envelope",aggregate_id=envelope_id,correlation_id=request.state.correlation_id,after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="SignatureRetryRequested",aggregate_type="signature_envelope",aggregate_id=envelope_id,payload=result,correlation_id=request.state.correlation_id)
    return result


@router.post("/signature-envelopes/{envelope_id}/validate", operation_id="validate_signature_envelope")
def validate_envelope(envelope_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=_authorize(user); row=request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?",(tid,envelope_id))
    if not row: raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND","Envelope não localizado.",404)
    contract=_contract_row(request,tid,row["contract_id"]);document_hash_valid=bool(contract.get("document_sha256")) and hmac.compare_digest(str(row["document_sha256"]),str(contract.get("document_sha256")))
    signers=json.loads(row["signers_json"] or "[]");evidences=json.loads(row["evidence_json"] or "[]");evidence_valid=True;invalid=[]
    for evidence in evidences:
        signature=evidence.get("evidence_hmac_sha256");source={k:v for k,v in evidence.items() if k!="evidence_hmac_sha256"};canonical=json.dumps(source,ensure_ascii=False,sort_keys=True,separators=(",",":"));expected=evidence_hmac(request.app.state.settings.jwt_secret,canonical)
        if not signature or not hmac.compare_digest(str(signature),expected): evidence_valid=False;invalid.append(evidence.get("id"))
    package={"envelope_id":envelope_id,"contract_id":row["contract_id"],"document_sha256":row["document_sha256"],"state":row["state"],"signers":signers,"evidence":evidences,"validated_at":iso_now()};package_json=json.dumps(package,ensure_ascii=False,sort_keys=True,separators=(",",":"));package_sha=hashlib.sha256(package_json.encode()).hexdigest();valid=document_hash_valid and evidence_valid
    with request.state.store.transaction() as conn:
        vid=uuid7();conn.execute("INSERT INTO signature_validations(id,tenant_id,envelope_id,valid,document_hash_valid,evidence_valid,details_json,validated_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(vid,tid,envelope_id,1 if valid else 0,1 if document_hash_valid else 0,1 if evidence_valid else 0,json.dumps({"invalid_evidence_ids":invalid,"signers":len(signers)},sort_keys=True),user.id,iso_now()));conn.execute("INSERT OR IGNORE INTO signature_evidence_packages(id,tenant_id,envelope_id,sha256,payload_json,created_at) VALUES(?,?,?,?,?,?)",(uuid7(),tid,envelope_id,package_sha,package_json,iso_now()));add_audit(conn,tenant_id=tid,actor_id=user.id,action="validate",aggregate_type="signature_envelope",aggregate_id=envelope_id,correlation_id=request.state.correlation_id,after={"valid":valid,"package_sha256":package_sha})
    return {"envelope_id":envelope_id,"valid":valid,"document_hash_valid":document_hash_valid,"evidence_valid":evidence_valid,"invalid_evidence_ids":invalid,"evidence_package_sha256":package_sha}


def _signature_connection(request: Request, tenant_id: str, connection_id: str, allowed: set[str]) -> tuple[dict[str, Any], dict[str, Any], str]:
    row = request.state.store.fetch_one("SELECT * FROM integration_connections WHERE tenant_id=? AND id=?", (tenant_id, connection_id))
    if not row:
        raise DomainError("INTEGRATION_CONNECTION_NOT_FOUND", "Conexão de integração não localizada.", 404)
    if row["provider"] not in allowed:
        raise DomainError("SIGNATURE_PROVIDER_CONNECTION_MISMATCH", "A conexão informada pertence a outro provider.", 409)
    if row.get("state") != "configured":
        raise DomainError("SIGNATURE_PROVIDER_NOT_CONFIGURED", "A conexão de assinatura não está configurada/ativa.", 409)
    try:
        config = json.loads(row.get("config_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        config = {}
    try:
        secret = SecretResolver(_signature_secret_root(request)).resolve(row.get("secret_reference"))
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 424) from exc
    return row, config, secret


def _signer_for_user(envelope: dict[str, Any], user: CurrentUser) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    signers = json.loads(envelope.get("signers_json") or "[]")
    signer = next((item for item in signers if item.get("user_id") == user.id), None)
    if not signer:
        raise DomainError("USER_NOT_SIGNER", "Usuário autenticado não é signatário deste envelope.", 403)
    if signer.get("status") == "signed":
        raise DomainError("SIGNER_ALREADY_SIGNED", "O signatário já concluiu sua assinatura.", 409)
    return signers, signer


def _govbr_state(secret: str, *, attempt_id: str, tenant_id: str, envelope_id: str, user_id: str) -> str:
    message = f"govbr-state:{attempt_id}:{tenant_id}:{envelope_id}:{user_id}".encode("utf-8")
    return hmac.new(signature_domain_key(secret), message, hashlib.sha256).hexdigest()


def _govbr_pkce(secret: str, *, attempt_id: str, user_id: str) -> tuple[str, str]:
    raw = hmac.new(signature_domain_key(secret), f"govbr-pkce:{attempt_id}:{user_id}".encode("utf-8"), hashlib.sha256).digest()
    verifier = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def _validate_redirect_uri(value: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise DomainError("SIGNATURE_REDIRECT_URI_INVALID", "redirect_uri deve usar HTTPS, sem credenciais ou fragmento.", 422)


def _finalize_provider_signature(
    request: Request, *, tenant_id: str, envelope_id: str, user: CurrentUser, provider: str,
    artifact: bytes, artifact_type: str, certificate_subject: str | None = None, certificate_serial: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id))
    if not envelope:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if envelope["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura neste estado.", 409)
    signers, signer = _signer_for_user(envelope, user)
    contract = _contract_row(request, tenant_id, envelope["contract_id"])
    digest = hashlib.sha256(artifact).hexdigest()
    prefix = str(contract.get("document_storage_key") or f"contracts/{contract['id']}").rsplit("/", 1)[0]
    extension = ".p7s" if artifact_type == "pkcs7_detached" else ".bin"
    storage_key = f"{prefix}/detached-signatures/{provider}-{signer['id']}{extension}"
    stored = request.app.state.data_router.object_storage(tenant_id).put_bytes(storage_key, artifact, content_type="application/pkcs7-signature" if extension == ".p7s" else "application/octet-stream")
    if stored.sha256 != digest:
        raise DomainError("SIGNATURE_ARTIFACT_STORAGE_INTEGRITY_FAILED", "Falha de integridade ao armazenar o artefato de assinatura.", 500)
    now = iso_now(); artifact_id = uuid7()
    evidence = {
        "id": uuid7(), "signer_id": signer["id"], "user_id": user.id, "consent": True, "method": provider,
        "document_sha256": envelope["document_sha256"], "artifact_id": artifact_id, "artifact_sha256": digest,
        "artifact_type": artifact_type, "certificate_subject": certificate_subject, "certificate_serial": certificate_serial,
        "correlation_id": request.state.correlation_id, "signed_at": now,
    }
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    evidence["evidence_hmac_sha256"] = evidence_hmac(request.app.state.settings.jwt_secret, canonical)
    signer.update({"status": "signed", "signed_at": now, "evidence_id": evidence["id"], "provider": provider})
    evidences = json.loads(envelope.get("evidence_json") or "[]"); evidences.append(evidence)
    required = [item for item in signers if item.get("required", True)]
    envelope_state = "signed" if all(item.get("status") == "signed" for item in required) else "partially_signed"
    contract_state = "signed" if envelope_state == "signed" else "partially_signed"
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE signature_envelopes SET state=?,signers_json=?,evidence_json=?,updated_at=? WHERE tenant_id=? AND id=?", (envelope_state, json.dumps(signers, ensure_ascii=False, sort_keys=True), json.dumps(evidences, ensure_ascii=False, sort_keys=True), now, tenant_id, envelope_id))
        conn.execute("INSERT INTO signature_artifacts(id,tenant_id,envelope_id,signer_id,provider,artifact_type,sha256,storage_key,certificate_subject,certificate_serial,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (artifact_id, tenant_id, envelope_id, signer["id"], provider, artifact_type, digest, storage_key, certificate_subject, certificate_serial, json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True), now))
        current = dict(conn.execute("SELECT * FROM legal_contracts WHERE tenant_id=? AND id=?", (tenant_id, envelope["contract_id"])).fetchone())
        next_version = int(current["version"]) + 1
        conn.execute("UPDATE legal_contracts SET state=?,version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?", (contract_state, next_version, user.id, now, tenant_id, current["id"]))
        _append_contract_version(conn, {**current, "state": contract_state, "version": next_version}, actor_id=user.id, reason=f"Assinatura via {provider}")
        result = {"envelope_id": envelope_id, "state": envelope_state, "contract_id": current["id"], "contract_state": contract_state, "provider": provider, "artifact_id": artifact_id, "artifact_sha256": digest, "storage_key": storage_key, "evidence": evidence}
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="sign", aggregate_type="signature_envelope", aggregate_id=envelope_id, correlation_id=request.state.correlation_id, after=result)
        add_outbox(conn, tenant_id=tenant_id, event_type="ContractFullySigned" if envelope_state == "signed" else "ContractPartiallySigned", aggregate_type="contract", aggregate_id=current["id"], payload={k:v for k,v in result.items() if k != "storage_key"}, correlation_id=request.state.correlation_id)
    return result


def _finalize_pades_signature(
    request: Request,
    *,
    tenant_id: str,
    envelope_id: str,
    user: CurrentUser,
    provider: str,
    signed_pdf: bytes,
    expected_input_sha256: str,
    profile: str,
    field_name: str,
    certificate_subject: str | None,
    certificate_serial: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    envelope = request.state.store.fetch_one(
        "SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id)
    )
    if not envelope:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if envelope["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura neste estado.", 409)
    signers, signer = _signer_for_user(envelope, user)
    contract = _contract_row(request, tenant_id, envelope["contract_id"])
    current_input_sha256 = str(contract.get("signed_document_sha256") or contract.get("document_sha256") or "")
    if not hmac.compare_digest(current_input_sha256, expected_input_sha256):
        raise DomainError(
            "SIGNATURE_DOCUMENT_REVISION_CONFLICT",
            "O documento recebeu outra revisão assinada; recarregue o envelope antes de assinar.",
            409,
        )
    output_sha256 = hashlib.sha256(signed_pdf).hexdigest()
    prefix = str(contract.get("document_storage_key") or f"contracts/{contract['id']}").rsplit("/", 1)[0]
    storage_key = f"{prefix}/signed-revisions/{output_sha256}.pdf"
    storage = request.app.state.data_router.object_storage(tenant_id)
    stored = storage.put_bytes(storage_key, signed_pdf, content_type="application/pdf")
    if stored.sha256 != output_sha256:
        storage.delete(storage_key)
        raise DomainError("SIGNATURE_ARTIFACT_STORAGE_INTEGRITY_FAILED", "Falha de integridade ao armazenar o PDF PAdES.", 500)

    now = iso_now(); artifact_id = uuid7()
    evidence = {
        "id": uuid7(), "signer_id": signer["id"], "user_id": user.id, "consent": True, "method": provider,
        "original_document_sha256": envelope["document_sha256"], "signed_revision_input_sha256": expected_input_sha256,
        "signed_revision_output_sha256": output_sha256, "artifact_id": artifact_id, "artifact_sha256": output_sha256,
        "artifact_type": "pades_pdf", "signature_profile": profile, "signature_field": field_name,
        "certificate_subject": certificate_subject, "certificate_serial": certificate_serial,
        "correlation_id": request.state.correlation_id, "signed_at": now,
    }
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    evidence["evidence_hmac_sha256"] = evidence_hmac(request.app.state.settings.jwt_secret, canonical)
    signer.update({"status": "signed", "signed_at": now, "evidence_id": evidence["id"], "provider": provider, "signature_field": field_name})
    evidences = json.loads(envelope.get("evidence_json") or "[]"); evidences.append(evidence)
    required = [item for item in signers if item.get("required", True)]
    envelope_state = "signed" if all(item.get("status") == "signed" for item in required) else "partially_signed"
    contract_state = "signed" if envelope_state == "signed" else "partially_signed"

    try:
        with request.state.store.transaction() as conn:
            raw = conn.execute("SELECT * FROM legal_contracts WHERE tenant_id=? AND id=?", (tenant_id, envelope["contract_id"])).fetchone()
            if not raw:
                raise DomainError("CONTRACT_NOT_FOUND", "Contrato não localizado.", 404)
            current = dict(raw)
            transaction_input = str(current.get("signed_document_sha256") or current.get("document_sha256") or "")
            if not hmac.compare_digest(transaction_input, expected_input_sha256):
                raise DomainError(
                    "SIGNATURE_DOCUMENT_REVISION_CONFLICT",
                    "O documento recebeu outra revisão assinada durante a assinatura.",
                    409,
                )
            # Revalida o signatário dentro da transação para impedir replay concorrente.
            raw_envelope = conn.execute("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id)).fetchone()
            if not raw_envelope:
                raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
            current_envelope = dict(raw_envelope)
            current_signers = json.loads(current_envelope.get("signers_json") or "[]")
            current_signer = next((item for item in current_signers if item.get("user_id") == user.id), None)
            if not current_signer or current_signer.get("status") == "signed":
                raise DomainError("SIGNER_ALREADY_SIGNED", "O signatário já concluiu sua assinatura.", 409)
            # Substitui a versão corrente dos signers já preparada, preservando a ordem original.
            current_signers = [signer if item.get("id") == signer.get("id") else item for item in current_signers]
            current_required = [item for item in current_signers if item.get("required", True)]
            current_envelope_state = "signed" if all(item.get("status") == "signed" for item in current_required) else "partially_signed"
            current_contract_state = "signed" if current_envelope_state == "signed" else "partially_signed"
            current_evidences = json.loads(current_envelope.get("evidence_json") or "[]"); current_evidences.append(evidence)
            conn.execute(
                "UPDATE signature_envelopes SET state=?,signers_json=?,evidence_json=?,updated_at=? WHERE tenant_id=? AND id=?",
                (current_envelope_state, json.dumps(current_signers, ensure_ascii=False, sort_keys=True), json.dumps(current_evidences, ensure_ascii=False, sort_keys=True), now, tenant_id, envelope_id),
            )
            conn.execute(
                "INSERT INTO signature_artifacts(id,tenant_id,envelope_id,signer_id,provider,artifact_type,sha256,storage_key,certificate_subject,certificate_serial,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (artifact_id, tenant_id, envelope_id, signer["id"], provider, "pades_pdf", output_sha256, storage_key, certificate_subject, certificate_serial, json.dumps(metadata, ensure_ascii=False, sort_keys=True), now),
            )
            next_version = int(current["version"]) + 1
            conn.execute(
                "UPDATE legal_contracts SET state=?,signed_document_sha256=?,signed_document_storage_key=?,signature_profile=?,version=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?",
                (current_contract_state, output_sha256, storage_key, profile, next_version, user.id, now, tenant_id, current["id"]),
            )
            updated = {**current, "state": current_contract_state, "signed_document_sha256": output_sha256, "signed_document_storage_key": storage_key, "signature_profile": profile, "version": next_version}
            _append_contract_version(conn, updated, actor_id=user.id, reason=f"Assinatura embutida {profile} via {provider}")
            result = {
                "envelope_id": envelope_id, "state": current_envelope_state, "contract_id": current["id"],
                "contract_state": current_contract_state, "provider": provider, "artifact_id": artifact_id,
                "artifact_sha256": output_sha256, "storage_key": storage_key, "evidence": evidence,
                "pades_embedded": True, "signature_profile": profile, "signature_field": field_name,
                "signed_document_sha256": output_sha256,
            }
            add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="sign_pades", aggregate_type="signature_envelope", aggregate_id=envelope_id, correlation_id=request.state.correlation_id, after={k: v for k, v in result.items() if k != "storage_key"})
            add_outbox(conn, tenant_id=tenant_id, event_type="ContractFullySigned" if current_envelope_state == "signed" else "ContractPartiallySigned", aggregate_type="contract", aggregate_id=current["id"], payload={k: v for k, v in result.items() if k not in {"storage_key", "evidence"}}, correlation_id=request.state.correlation_id)
    except Exception:
        # A chave é content-addressed. Em conflito ou rollback ela não pode ser referenciada pelo banco.
        try:
            storage.delete(storage_key)
        except Exception:
            pass
        raise
    return result


@router.post("/signature-envelopes/{envelope_id}/icp-brasil/sign", operation_id="sign_icp_brasil_pades")
def sign_icp_brasil_pades(envelope_id: str, data: IcpBrasilDetachedSignInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id = _tenant(user)
    envelope = request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id))
    if not envelope:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if envelope["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura.", 409)
    _, signer = _signer_for_user(envelope, user)
    _, config, secret = _signature_connection(request, tenant_id, data.connection_id, {"icp_brasil", "IcpBrasilPadesProvider"})
    try:
        provider = IcpBrasilCertificateProvider(config=config, secret=secret)
        health = provider.health()
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 424) from exc
    if not health.certificate_valid_now:
        raise DomainError("ICP_BRASIL_CERTIFICATE_NOT_VALID", "Certificado fora da vigência; assinatura bloqueada.", 409)
    if not health.trust_chain_validated:
        raise DomainError("ICP_BRASIL_TRUST_CHAIN_UNVERIFIED", "A cadeia de confiança configurada não valida este certificado; assinatura qualificada bloqueada.", 424)

    contract = _contract_row(request, tenant_id, envelope["contract_id"])
    source_key = contract.get("signed_document_storage_key") or contract.get("document_storage_key")
    expected_input_sha256 = str(contract.get("signed_document_sha256") or contract.get("document_sha256") or "")
    if not source_key or not expected_input_sha256:
        raise DomainError("CONTRACT_DOCUMENT_MISSING", "Documento congelado não localizado.", 409)
    storage = request.app.state.data_router.object_storage(tenant_id)
    source_pdf = storage.get_bytes(source_key)
    if not hmac.compare_digest(hashlib.sha256(source_pdf).hexdigest(), expected_input_sha256):
        raise DomainError("CONTRACT_DOCUMENT_INTEGRITY_FAILED", "Hash da revisão PDF diverge do contrato.", 409)
    field_name = f"PIGE360_{envelope_id.replace('-', '')[-12:]}_{str(signer['id']).replace('-', '')[-12:]}"
    try:
        signed = provider.sign_pades_b_b(
            source_pdf,
            field_name=field_name,
            signer_name=str(signer.get("name") or health.subject),
            reason=f"Assinatura do contrato {contract['number']}",
        )
        validations = provider.validate_pades(signed.pdf)
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 424) from exc
    current_validation = next((item for item in validations if item.get("field_name") == field_name), None)
    if not current_validation or not current_validation.get("valid"):
        raise DomainError("ICP_BRASIL_PADES_VALIDATION_FAILED", "A revisão PAdES gerada não passou na validação local.", 500)
    metadata = {
        "connection_id": data.connection_id, "trust_chain_validated": True, "pades_embedded": True,
        "pades_profile": signed.profile, "signature_field": field_name, "byte_range": list(signed.byte_range),
        "signed_content_sha256": signed.signed_content_sha256, "input_sha256": signed.input_sha256,
        "output_sha256": signed.output_sha256, "signing_certificate_v2": True,
        "embedded_signature_count": len(validations),
    }
    result = _finalize_pades_signature(
        request, tenant_id=tenant_id, envelope_id=envelope_id, user=user, provider="icp_brasil_pades",
        signed_pdf=signed.pdf, expected_input_sha256=expected_input_sha256, profile=signed.profile, field_name=field_name,
        certificate_subject=health.subject, certificate_serial=health.serial_number, metadata=metadata,
    )
    return {**result, "trust_chain_validated": True, "qualification_claim": "certificate_chain_validated_pades_b_b"}


@router.post("/signature-envelopes/{envelope_id}/govbr/authorize", operation_id="authorize_govbr_signature")
def authorize_govbr_signature(envelope_id: str, data: GovBrAuthorizationInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id = _tenant(user); _validate_redirect_uri(data.redirect_uri)
    envelope = request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id))
    if not envelope:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if envelope["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura.", 409)
    _, signer = _signer_for_user(envelope, user)
    _, config, secret = _signature_connection(request, tenant_id, data.connection_id, {"govbr", "GovBrAdvancedSignatureProvider"})
    try:
        provider = GovBrAdvancedSignatureProvider(config=config, secret=secret, transport=_signature_transport(request))
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 424) from exc
    contract = _contract_row(request, tenant_id, envelope["contract_id"])
    document_revision_sha256 = str(contract.get("signed_document_sha256") or contract.get("document_sha256") or "")
    if not document_revision_sha256:
        raise DomainError("CONTRACT_DOCUMENT_MISSING", "Documento congelado não localizado.", 409)
    attempt_id = uuid7(); state = _govbr_state(request.app.state.settings.jwt_secret, attempt_id=attempt_id, tenant_id=tenant_id, envelope_id=envelope_id, user_id=user.id)
    _, challenge = _govbr_pkce(request.app.state.settings.jwt_secret, attempt_id=attempt_id, user_id=user.id)
    authorization_url = provider.authorization_url(state=state, redirect_uri=data.redirect_uri, code_challenge=challenge)
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO signature_attempts(id,tenant_id,envelope_id,signer_id,provider,action,state,request_json,response_json,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (attempt_id, tenant_id, envelope_id, signer["id"], "govbr_advanced", "authorize", "awaiting_callback", json.dumps({"connection_id": data.connection_id, "state": state, "redirect_uri": data.redirect_uri, "code_challenge": challenge, "document_revision_sha256": document_revision_sha256}, sort_keys=True), "{}", request.state.correlation_id, now))
        add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action="govbr_authorize", aggregate_type="signature_envelope", aggregate_id=envelope_id, correlation_id=request.state.correlation_id, after={"attempt_id": attempt_id, "connection_id": data.connection_id})
    return {"attempt_id": attempt_id, "state": state, "authorization_url": authorization_url, "expires_policy": "provider", "homologated": False}


@router.post("/signature-envelopes/{envelope_id}/govbr/callback", operation_id="complete_govbr_signature")
def complete_govbr_signature(envelope_id: str, data: GovBrCallbackInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id = _tenant(user); _validate_redirect_uri(data.redirect_uri)
    attempt = request.state.store.fetch_one("SELECT * FROM signature_attempts WHERE tenant_id=? AND id=? AND envelope_id=? AND provider='govbr_advanced' AND action='authorize'", (tenant_id, data.attempt_id, envelope_id))
    if not attempt:
        raise DomainError("GOVBR_SIGNATURE_ATTEMPT_NOT_FOUND", "Tentativa GOV.BR não localizada.", 404)
    if attempt["state"] != "awaiting_callback":
        raise DomainError("GOVBR_SIGNATURE_ATTEMPT_FINALIZED", "A tentativa GOV.BR já foi concluída ou falhou.", 409)
    request_data = json.loads(attempt.get("request_json") or "{}")
    expected_state = _govbr_state(request.app.state.settings.jwt_secret, attempt_id=data.attempt_id, tenant_id=tenant_id, envelope_id=envelope_id, user_id=user.id)
    if not hmac.compare_digest(expected_state, data.state) or request_data.get("state") != data.state:
        raise DomainError("GOVBR_OAUTH_STATE_INVALID", "Estado OAuth inválido; possível replay ou sessão divergente.", 409)
    if request_data.get("connection_id") != data.connection_id or request_data.get("redirect_uri") != data.redirect_uri:
        raise DomainError("GOVBR_OAUTH_CONTEXT_MISMATCH", "Contexto OAuth diverge da autorização original.", 409)
    _, config, secret = _signature_connection(request, tenant_id, data.connection_id, {"govbr", "GovBrAdvancedSignatureProvider"})
    verifier, _ = _govbr_pkce(request.app.state.settings.jwt_secret, attempt_id=data.attempt_id, user_id=user.id)
    envelope = request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id))
    if not envelope:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    try:
        provider = GovBrAdvancedSignatureProvider(config=config, secret=secret, transport=_signature_transport(request))
        token = provider.exchange_code(code=data.code, redirect_uri=data.redirect_uri, code_verifier=verifier)
        access_token = str(token["access_token"])
        certificate = provider.certificate(access_token=access_token)
        _, signer = _signer_for_user(envelope, user)
        contract = _contract_row(request, tenant_id, envelope["contract_id"])
        source_key = contract.get("signed_document_storage_key") or contract.get("document_storage_key")
        current_revision_sha256 = str(contract.get("signed_document_sha256") or contract.get("document_sha256") or "")
        expected_revision_sha256 = str(request_data.get("document_revision_sha256") or "")
        if not source_key or not current_revision_sha256:
            raise IntegrationError("CONTRACT_DOCUMENT_MISSING", "Documento congelado não localizado para assinatura GOV.BR.")
        if not hmac.compare_digest(current_revision_sha256, expected_revision_sha256):
            raise IntegrationError("GOVBR_DOCUMENT_REVISION_CONFLICT", "O documento mudou após a autorização GOV.BR; reinicie a assinatura.")
        storage = request.app.state.data_router.object_storage(tenant_id)
        source_pdf = storage.get_bytes(source_key)
        if not hmac.compare_digest(hashlib.sha256(source_pdf).hexdigest(), current_revision_sha256):
            raise IntegrationError("CONTRACT_DOCUMENT_INTEGRITY_FAILED", "Integridade da revisão PDF divergente.")
        field_name = f"PIGE360_GOVBR_{envelope_id.replace('-', '')[-10:]}_{str(signer['id']).replace('-', '')[-10:]}"
        prepared = prepare_incremental_signature(
            source_pdf, field_name=field_name, signer_name=str(signer.get("name") or certificate.get("subject") or "GOV.BR"),
            reason=f"Assinatura GOV.BR do contrato {contract['number']}",
        )
        digest_b64 = base64.b64encode(hashlib.sha256(prepared.signed_content).digest()).decode("ascii")
        signed = provider.sign_hash(access_token=access_token, sha256_base64=digest_b64)
        encoded = signed.get("pkcs7") or signed.get("signature")
        try:
            cms_der = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise IntegrationError("GOVBR_PKCS7_INVALID", "Provider retornou PKCS#7 não codificado em Base64 válido.") from exc
        if not cms_der:
            raise IntegrationError("GOVBR_PKCS7_INVALID", "Provider retornou PKCS#7 vazio.")
        try:
            signed_pdf, cms_validation = embed_validated_external_cades(prepared, cms_der)
        except PadesError as exc:
            raise IntegrationError("GOVBR_PADES_VALIDATION_FAILED", str(exc)) from exc
        result = _finalize_pades_signature(
            request, tenant_id=tenant_id, envelope_id=envelope_id, user=user, provider="govbr_advanced",
            signed_pdf=signed_pdf, expected_input_sha256=current_revision_sha256, profile="PAdES-B-B", field_name=field_name,
            certificate_subject=str(certificate.get("subject") or cms_validation.get("certificate_subject") or "") or None,
            certificate_serial=str(certificate.get("serial_number") or certificate.get("serial") or cms_validation.get("certificate_serial") or "") or None,
            metadata={"connection_id": data.connection_id, "provider_certificate_received": True, "pades_embedded": True, "pades_profile": "PAdES-B-B", "signature_field": field_name, "byte_range": list(prepared.byte_range), "signed_content_sha256": hashlib.sha256(prepared.signed_content).hexdigest(), "signing_certificate_v2": True, "homologated": False},
        )
    except IntegrationError as exc:
        request.state.store.execute("UPDATE signature_attempts SET state='failed',error=?,finished_at=? WHERE tenant_id=? AND id=?", (f"{exc.code}: {str(exc)[:500]}", iso_now(), tenant_id, data.attempt_id))
        status = 503 if exc.retryable else 424
        raise DomainError(exc.code, str(exc), status) from exc
    request.state.store.execute("UPDATE signature_attempts SET state='completed',response_json=?,finished_at=? WHERE tenant_id=? AND id=?", (json.dumps({"artifact_id": result["artifact_id"], "artifact_sha256": result["artifact_sha256"], "provider": "govbr_advanced"}, sort_keys=True), iso_now(), tenant_id, data.attempt_id))
    return {**result, "homologated": False}


@router.post("/signature-envelopes/{envelope_id}/icp-brasil/sign-detached", operation_id="sign_icp_brasil_detached")
def sign_icp_brasil_detached(envelope_id: str, data: IcpBrasilDetachedSignInput, request: Request, user: CurrentUser = Depends(current_user)):
    tenant_id = _tenant(user)
    envelope = request.state.store.fetch_one("SELECT * FROM signature_envelopes WHERE tenant_id=? AND id=?", (tenant_id, envelope_id))
    if not envelope:
        raise DomainError("SIGNATURE_ENVELOPE_NOT_FOUND", "Envelope não localizado.", 404)
    if envelope["state"] not in {"sent", "partially_signed"}:
        raise DomainError("ENVELOPE_NOT_SIGNABLE", "Envelope não aceita assinatura.", 409)
    _signer_for_user(envelope, user)
    _, config, secret = _signature_connection(request, tenant_id, data.connection_id, {"icp_brasil", "IcpBrasilPadesProvider"})
    try:
        provider = IcpBrasilCertificateProvider(config=config, secret=secret)
        health = provider.health()
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 424) from exc
    if not health.certificate_valid_now:
        raise DomainError("ICP_BRASIL_CERTIFICATE_NOT_VALID", "Certificado fora da vigência; assinatura bloqueada.", 409)
    if not health.trust_chain_validated:
        raise DomainError("ICP_BRASIL_TRUST_CHAIN_UNVERIFIED", "A cadeia de confiança configurada não valida este certificado; assinatura qualificada bloqueada.", 424)
    contract = _contract_row(request, tenant_id, envelope["contract_id"])
    key = contract.get("document_storage_key")
    if not key:
        raise DomainError("CONTRACT_DOCUMENT_MISSING", "Documento congelado não localizado.", 409)
    storage = request.app.state.data_router.object_storage(tenant_id)
    document = storage.get_bytes(key)
    if not hmac.compare_digest(hashlib.sha256(document).hexdigest(), str(envelope["document_sha256"])):
        raise DomainError("CONTRACT_DOCUMENT_INTEGRITY_FAILED", "Hash do PDF diverge do envelope de assinatura.", 409)
    try:
        artifact = provider.sign_detached_cms(document)
    except Exception as exc:
        if isinstance(exc, IntegrationError):
            raise DomainError(exc.code, str(exc), 424) from exc
        raise DomainError("ICP_BRASIL_CMS_SIGN_FAILED", "Falha criptográfica ao gerar a assinatura CMS.", 500) from exc
    result = _finalize_provider_signature(
        request, tenant_id=tenant_id, envelope_id=envelope_id, user=user, provider="icp_brasil",
        artifact=artifact, artifact_type="pkcs7_detached", certificate_subject=health.subject, certificate_serial=health.serial_number,
        metadata={"connection_id": data.connection_id, "trust_chain_validated": True, "pades_embedded": False},
    )
    return {**result, "trust_chain_validated": True, "pades_embedded": False, "qualification_claim": "certificate_chain_validated_cms_detached"}


@router.get("/signatures/providers",operation_id="list_signature_providers")
def signature_providers(request:Request,user:CurrentUser=Depends(current_user)):
    tid = _tenant(user)
    rows = request.state.store.fetch_all(
        "SELECT provider,state,last_health_state FROM integration_connections WHERE tenant_id=? AND provider IN ('icp_brasil','IcpBrasilPadesProvider','govbr','GovBrAdvancedSignatureProvider','external_signature')",
        (tid,),
    )
    configured = {str(row["provider"]): row for row in rows}
    def external_status(aliases: set[str]) -> str:
        matches = [row for name, row in configured.items() if name in aliases and row.get("state") == "configured"]
        if not matches:
            return "not_configured"
        if any(row.get("last_health_state") == "healthy" for row in matches):
            return "healthy"
        return "configured_unverified"
    return {"items":[
        {"provider":"internal_electronic","status":"available","methods":["simple_electronic"],"otp_required":request.app.state.settings.signature_internal_otp_required,"validated_locally":True},
        {"provider":"icp_brasil_pades","status":external_status({"icp_brasil","IcpBrasilPadesProvider"}),"methods":["pades_b_b","pkcs7_detached","qualified_icp_brasil"],"pades_embedding_validated":True,"pades_profile":"PAdES-B-B","engine_validated_locally":True},
        {"provider":"govbr_advanced","status":external_status({"govbr","GovBrAdvancedSignatureProvider"}),"methods":["govbr_advanced"],"eligible_tenants":"public_authorized_only","validated_locally":False},
        {"provider":"external","status":external_status({"external_signature"}),"methods":["external_provider","manual_import"],"validated_locally":False},
    ]}


def _signature_secret_root(request: Request) -> Path:
    return Path("/run/secrets") if request.app.state.settings.environment in {"production", "staging"} else request.app.state.settings.data_root / "integration-secrets"


def _signature_transport(request: Request):
    injected = getattr(request.app.state, "integration_transport", None)
    if injected is not None:
        return injected
    if request.app.state.settings.integration_remote_enabled:
        return None
    return DisabledTransport()


@router.post("/signatures/providers/{provider}/test", operation_id="test_signature_provider")
def test_signature_provider(provider: Literal["internal_electronic","icp_brasil_pades","govbr_advanced","external"], data: ProviderTestInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = _authorize(user)
    if provider != data.provider:
        raise DomainError("SIGNATURE_PROVIDER_MISMATCH", "Provider da rota diverge do payload.", 422)
    if provider == "internal_electronic":
        return {"provider": provider, "status": "available", "validated_locally": True, "otp_required": request.app.state.settings.signature_internal_otp_required}
    if not data.connection_id:
        return {"provider": provider, "status": "not_configured", "validated_locally": False}
    row = request.state.store.fetch_one("SELECT * FROM integration_connections WHERE tenant_id=? AND id=?", (tid, data.connection_id))
    if not row:
        raise DomainError("INTEGRATION_CONNECTION_NOT_FOUND", "Conexão de integração não localizada.", 404)
    aliases = {
        "icp_brasil_pades": {"icp_brasil", "IcpBrasilPadesProvider"},
        "govbr_advanced": {"govbr", "GovBrAdvancedSignatureProvider"},
        "external": {"external_signature"},
    }[provider]
    if row["provider"] not in aliases:
        raise DomainError("SIGNATURE_PROVIDER_CONNECTION_MISMATCH", "A conexão informada pertence a outro provider.", 409)
    try:
        config = json.loads(row.get("config_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        config = {}
    try:
        secret = SecretResolver(_signature_secret_root(request)).resolve(row.get("secret_reference"))
        if provider == "icp_brasil_pades":
            health = IcpBrasilCertificateProvider(config=config, secret=secret).health()
            result = {"provider": provider, "status": health.status, "subject": health.subject, "issuer": health.issuer, "serial_number": health.serial_number, "not_valid_before": health.not_valid_before, "not_valid_after": health.not_valid_after, "has_private_key": health.has_private_key, "chain_certificates": health.chain_certificates, "certificate_valid_now": health.certificate_valid_now, "trust_chain_validated": health.trust_chain_validated, "validated_locally": True, "pades_embedding_validated": True, "pades_profile": "PAdES-B-B"}
            health_state = "healthy" if health.certificate_valid_now else "degraded"
        elif provider == "govbr_advanced":
            health = GovBrAdvancedSignatureProvider(config=config, secret=secret, transport=_signature_transport(request)).health()
            result = {"provider": provider, "status": health.status, "latency_ms": health.latency_ms, "details": health.details, "validated_locally": False, "homologated": False}
            health_state = health.status
        else:
            result = {"provider": provider, "status": "configured_unverified", "validated_locally": False}
            health_state = "configured_unverified"
    except IntegrationError as exc:
        status = 424 if exc.code.startswith(("INTEGRATION_SECRET", "ICP_BRASIL", "GOVBR_CLIENT")) else (503 if exc.retryable else 409)
        raise DomainError(exc.code, str(exc), status) from exc
    now = iso_now()
    request.state.store.execute("UPDATE integration_connections SET last_health_at=?,last_health_state=?,updated_at=? WHERE tenant_id=? AND id=?", (now, health_state, now, tid, data.connection_id))
    return {**result, "connection_id": data.connection_id}


@router.get("/public/contracts/validate/{code}",operation_id="validate_public_contract")
def public_validate(code:str,request:Request):
    tenant_id=request.state.host_resolution.tenant_id;rows=request.state.store.fetch_all("SELECT id,number,state,validation_code,document_sha256,signed_document_sha256,signature_profile,updated_at FROM legal_contracts WHERE tenant_id=? AND validation_code IS NOT NULL",(tenant_id,))
    for row in rows:
        if hmac.compare_digest(str(row.get("validation_code") or ""),code):
            return {"authentic":True,"status":row["state"],"contract_number":row["number"],"document_sha256":row["document_sha256"],"signed_document_sha256":row.get("signed_document_sha256"),"signature_profile":row.get("signature_profile"),"signatures":request.state.store.scalar("SELECT COUNT(*) AS n FROM signature_artifacts WHERE tenant_id=? AND envelope_id IN (SELECT id FROM signature_envelopes WHERE tenant_id=? AND contract_id=?) AND artifact_type='pades_pdf'",(tenant_id,tenant_id,row["id"])) or 0,"validated_at":iso_now()}
    raise DomainError("VALIDATION_CODE_NOT_FOUND","Código de validação não localizado.",404)


@router.post("/public/contracts/validate-file",operation_id="validate_public_contract_file")
def validate_file(data:ValidateFileInput,request:Request):
    try:content=base64.b64decode(data.content_base64,validate=True)
    except Exception as exc:raise DomainError("INVALID_BASE64","Arquivo inválido.",422) from exc
    digest=hashlib.sha256(content).hexdigest();tenant_id=request.state.host_resolution.tenant_id
    signed=request.state.store.fetch_one("SELECT id,number,state,signature_profile,updated_at FROM legal_contracts WHERE tenant_id=? AND signed_document_sha256=?",(tenant_id,digest))
    if signed:
        return {"authentic":True,"sha256":digest,"contract_id":signed["id"],"contract_number":signed["number"],"status":signed["state"],"revision":"signed","signature_profile":signed.get("signature_profile"),"validated_at":iso_now()}
    row=request.state.store.fetch_one("SELECT contract_id,generated_at FROM contract_snapshots WHERE tenant_id=? AND generated_document_sha256=?",(tenant_id,digest))
    return {"authentic":bool(row),"sha256":digest,"contract_id":row["contract_id"] if row else None,"generated_at":row["generated_at"] if row else None,"revision":"original" if row else None,"signature_profile":None}
