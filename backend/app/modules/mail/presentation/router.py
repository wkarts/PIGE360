from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, EmailStr, Field
from fastapi.responses import Response

from app.modules.operations.common import ADMIN_ROLES, require, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.integrations.providers import DisabledTransport, IntegrationError, SecretResolver
from app.shared.mail.provider import ImapSmtpMailProvider
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["mail"])
MAIL_ADMIN_ROLES = ADMIN_ROLES | {"mail_admin"}


class MailAccountInput(BaseModel):
    user_id: str
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=160)
    provider_connection_id: str
    credential_secret_reference: str = Field(min_length=1, max_length=120)
    mode: str = Field(default="generic_imap_smtp", pattern=r"^(generic_imap_smtp|mailcow_managed|dedicated_mailcow)$")
    quota_mb: int | None = Field(default=None, ge=64, le=102400)


class MailSendInput(BaseModel):
    to: list[EmailStr] = Field(min_length=1, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str | None = Field(default=None, max_length=4_000_000)


class MailDraftInput(BaseModel):
    to: list[EmailStr] = Field(default_factory=list, max_length=100)
    cc: list[EmailStr] = Field(default_factory=list, max_length=100)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str | None = Field(default=None, max_length=4_000_000)


class MailDraftPatch(MailDraftInput):
    expected_version: int = Field(ge=1)


class MailSeenInput(BaseModel):
    seen: bool = True


class MailMoveInput(BaseModel):
    destination_folder: str = Field(min_length=1, max_length=255)


class MailReplyInput(BaseModel):
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str | None = Field(default=None, max_length=4_000_000)
    reply_all: bool = False


class MailForwardInput(MailSendInput):
    pass


class MailDelegationInput(BaseModel):
    delegate_user_id: str
    can_read: bool = True
    can_send: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None


def _secret_root(request: Request) -> Path:
    settings = request.app.state.settings
    return Path("/run/secrets") if settings.environment in {"production", "staging"} else settings.data_root / "integration-secrets"


def _transport(request: Request):
    injected = getattr(request.app.state, "integration_transport", None)
    if injected is not None:
        return injected
    if request.app.state.settings.integration_remote_enabled:
        return None
    return DisabledTransport()


def _decode_account(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("credential_secret_reference", None)
    result["credential_configured"] = bool(row.get("credential_secret_reference"))
    return result


def _account_access(request: Request, user: CurrentUser, *, write: bool = False) -> dict[str, Any]:
    tid = tenant(user)
    direct = request.state.store.fetch_one("SELECT * FROM mail_accounts WHERE tenant_id=? AND user_id=? AND state='active'", (tid, user.id))
    if direct:
        return direct
    now = iso_now()
    delegated = request.state.store.fetch_one(
        """SELECT a.*,d.can_read,d.can_send FROM mail_delegations d
           JOIN mail_accounts a ON a.id=d.account_id AND a.tenant_id=d.tenant_id
           WHERE d.tenant_id=? AND d.delegate_user_id=? AND d.state='active'
             AND (d.valid_from IS NULL OR d.valid_from<=?) AND (d.valid_until IS NULL OR d.valid_until>=?)
           ORDER BY d.created_at LIMIT 1""",
        (tid, user.id, now, now),
    )
    if delegated and ((not write and delegated.get("can_read")) or (write and delegated.get("can_send"))):
        return delegated
    raise DomainError("MAIL_ACCOUNT_NOT_AVAILABLE", "Nenhuma caixa de e-mail disponível para este usuário.", 403)


def _provider(request: Request, account: dict[str, Any]) -> ImapSmtpMailProvider:
    connection = request.state.store.fetch_one(
        "SELECT * FROM integration_connections WHERE tenant_id=? AND id=?",
        (account["tenant_id"], account["provider_connection_id"]),
    )
    if not connection or connection.get("state") not in {"configured", "degraded"}:
        raise DomainError("MAIL_PROVIDER_NOT_CONFIGURED", "Provider de e-mail não configurado para esta conta.", 424)
    if connection.get("provider") not in {"generic_imap_smtp", "mailcow", "MailcowProvider"}:
        raise DomainError("MAIL_PROVIDER_CONNECTION_MISMATCH", "A conexão informada não oferece IMAP/SMTP.", 409)
    try:
        config = json.loads(connection.get("config_json") or "{}")
    except json.JSONDecodeError:
        config = {}
    settings = request.app.state.settings
    # Defaults globais existem para self-hosted de servidor único; cada tenant pode
    # sobrescrevê-los em sua integration_connection sem compartilhar credenciais.
    config.setdefault("imap_host", settings.mail_imap_host)
    config.setdefault("imap_port", settings.mail_imap_port)
    config.setdefault("smtp_host", settings.mail_smtp_host)
    config.setdefault("smtp_port", settings.mail_smtp_port)
    config.setdefault("smtp_tls", settings.mail_smtp_tls)
    try:
        secret = SecretResolver(_secret_root(request)).resolve(account.get("credential_secret_reference"))
        return ImapSmtpMailProvider(config=config, secret=secret, transport=_transport(request))
    except IntegrationError as exc:
        status = 503 if exc.retryable else (424 if exc.code.startswith(("MAIL_", "INTEGRATION_SECRET")) else 409)
        raise DomainError(exc.code, str(exc), status) from exc


def _thread_key(item: dict[str, Any]) -> str:
    source = str(item.get("in_reply_to") or item.get("message_id") or item.get("subject") or "sem-assunto").strip().lower()
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _message_access(request: Request, user: CurrentUser, message_id: str, *, write: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    account = _account_access(request, user, write=write)
    meta = request.state.store.fetch_one(
        """SELECT m.*,f.remote_name AS folder_name,f.special_use AS folder_special_use
           FROM mail_message_metadata m JOIN mail_folders f ON f.id=m.folder_id AND f.tenant_id=m.tenant_id
           WHERE m.tenant_id=? AND m.account_id=? AND m.id=?""",
        (account["tenant_id"], account["id"], message_id),
    )
    if not meta:
        raise DomainError("MAIL_MESSAGE_NOT_FOUND", "Mensagem não localizada nesta conta.", 404)
    return account, meta


def _recount_folder(store: Any, *, tenant_id: str, account_id: str, folder_id: str) -> None:
    counts = store.fetch_one(
        "SELECT COUNT(*) AS total,SUM(CASE WHEN flags_json NOT LIKE '%\\Seen%' THEN 1 ELSE 0 END) AS unread FROM mail_message_metadata WHERE tenant_id=? AND account_id=? AND folder_id=?",
        (tenant_id, account_id, folder_id),
    ) or {"total": 0, "unread": 0}
    store.execute(
        "UPDATE mail_folders SET total_count=?,unread_count=?,updated_at=? WHERE tenant_id=? AND account_id=? AND id=?",
        (int(counts.get("total") or 0), int(counts.get("unread") or 0), iso_now(), tenant_id, account_id, folder_id),
    )


def _folder_by_special_use(request: Request, account: dict[str, Any], *values: str) -> dict[str, Any] | None:
    rows = request.state.store.fetch_all(
        "SELECT * FROM mail_folders WHERE tenant_id=? AND account_id=?",
        (account["tenant_id"], account["id"]),
    )
    wanted = {value.lower() for value in values}
    for row in rows:
        special = str(row.get("special_use") or "").lower()
        remote = str(row.get("remote_name") or "").lower()
        if special in wanted or remote in wanted:
            return row
    return None


@router.get("/mail/accounts", operation_id="list_mail_accounts")
def list_mail_accounts(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, MAIL_ADMIN_ROLES)
    tid = tenant(user)
    rows = request.state.store.fetch_all("SELECT * FROM mail_accounts WHERE tenant_id=? ORDER BY email", (tid,))
    return {"items": [_decode_account(row) for row in rows]}


@router.post("/mail/accounts", status_code=201, operation_id="create_mail_account")
def create_mail_account(data: MailAccountInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, MAIL_ADMIN_ROLES)
    tid, now, account_id = tenant(user), iso_now(), uuid7()
    target = request.state.store.fetch_one("SELECT id,person_id,email,active FROM users WHERE tenant_id=? AND id=?", (tid, data.user_id))
    if not target:
        raise DomainError("MAIL_USER_NOT_FOUND", "Usuário da mailbox não localizado.", 404)
    connection = request.state.store.fetch_one("SELECT id,provider FROM integration_connections WHERE tenant_id=? AND id=?", (tid, data.provider_connection_id))
    if not connection:
        raise DomainError("INTEGRATION_CONNECTION_NOT_FOUND", "Conexão de e-mail não localizada.", 404)
    if connection["provider"] not in {"generic_imap_smtp", "mailcow", "MailcowProvider"}:
        raise DomainError("MAIL_PROVIDER_CONNECTION_MISMATCH", "A conexão não é compatível com cliente IMAP/SMTP.", 409)
    result = {"id": account_id, "user_id": data.user_id, "person_id": target.get("person_id"), "email": str(data.email).lower(), "display_name": data.display_name, "provider_connection_id": data.provider_connection_id, "mode": data.mode, "state": "active", "quota_mb": data.quota_mb, "credential_configured": True}
    try:
        with request.state.store.transaction() as conn:
            conn.execute("INSERT INTO mail_accounts(id,tenant_id,user_id,person_id,email,display_name,provider_connection_id,credential_secret_reference,mode,state,quota_mb,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (account_id,tid,data.user_id,target.get("person_id"),str(data.email).lower(),data.display_name,data.provider_connection_id,data.credential_secret_reference,data.mode,"active",data.quota_mb,now,now))
            add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="mail_account",aggregate_id=account_id,correlation_id=request.state.correlation_id,after={**result,"credential_secret_reference":None})
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise DomainError("MAIL_ACCOUNT_ALREADY_EXISTS", "Usuário ou endereço já possui conta de e-mail vinculada.", 409) from exc
        raise
    return result


@router.get("/mail/me/status", operation_id="get_my_mail_status")
def my_mail_status(request: Request, user: CurrentUser = Depends(current_user)):
    account = _account_access(request, user)
    folders = request.state.store.fetch_all("SELECT id,remote_name,display_name,special_use,unread_count,total_count,highest_uid,updated_at FROM mail_folders WHERE tenant_id=? AND account_id=? ORDER BY display_name", (account["tenant_id"], account["id"]))
    return {"account": _decode_account(account), "folders": folders}


@router.post("/mail/me/health", operation_id="health_my_mail")
def my_mail_health(request: Request, user: CurrentUser = Depends(current_user)):
    account = _account_access(request, user)
    try:
        health = _provider(request, account).health()
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 503 if exc.retryable else 424) from exc
    return {"status": health.status, "latency_ms": health.latency_ms, "details": health.details}


@router.post("/mail/me/sync", operation_id="sync_my_mail")
def sync_my_mail(request: Request, user: CurrentUser = Depends(current_user)):
    account = _account_access(request, user)
    provider = _provider(request, account); tid = account["tenant_id"]; run_id = uuid7(); started = iso_now()
    request.state.store.execute("INSERT INTO mail_sync_runs(id,tenant_id,account_id,state,started_at) VALUES(?,?,?,?,?)", (run_id,tid,account["id"],"running",started))
    folders_synced = messages_synced = 0
    try:
        folders = provider.list_folders()
        for folder in folders:
            remote_name = str(folder.get("remote_name") or "").strip()
            if not remote_name:
                continue
            existing = request.state.store.fetch_one("SELECT * FROM mail_folders WHERE tenant_id=? AND account_id=? AND remote_name=?", (tid,account["id"],remote_name))
            folder_id = existing["id"] if existing else uuid7(); highest = int(existing.get("highest_uid") or 0) if existing else 0; now=iso_now()
            if existing:
                request.state.store.execute("UPDATE mail_folders SET display_name=?,special_use=?,updated_at=? WHERE tenant_id=? AND id=?", (str(folder.get("display_name") or remote_name),folder.get("special_use"),now,tid,folder_id))
            else:
                request.state.store.execute("INSERT INTO mail_folders(id,tenant_id,account_id,remote_name,display_name,special_use,highest_uid,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (folder_id,tid,account["id"],remote_name,str(folder.get("display_name") or remote_name),folder.get("special_use"),0,now,now))
            folders_synced += 1
            items = provider.fetch_metadata(folder=remote_name, uid_after=highest, limit=500)
            for item in items:
                uid = int(item["remote_uid"]); now=iso_now(); thread_key=_thread_key(item)
                request.state.store.execute(
                    """INSERT OR IGNORE INTO mail_message_metadata(id,tenant_id,account_id,folder_id,remote_uid,message_id,thread_key,in_reply_to,subject,sender_json,recipients_json,cc_json,bcc_json,sent_at,received_at,flags_json,size_bytes,has_attachments,preview,content_sha256,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uuid7(),tid,account["id"],folder_id,uid,item.get("message_id"),thread_key,item.get("in_reply_to"),item.get("subject"),json.dumps(item.get("sender") or {},ensure_ascii=False),json.dumps(item.get("recipients") or [],ensure_ascii=False),json.dumps(item.get("cc") or [],ensure_ascii=False),json.dumps(item.get("bcc") or [],ensure_ascii=False),item.get("sent_at"),item.get("received_at"),json.dumps(item.get("flags") or []),item.get("size_bytes"),1 if item.get("has_attachments") else 0,item.get("preview"),item.get("content_sha256"),now,now),
                )
                highest=max(highest,uid); messages_synced += 1
            counts = request.state.store.fetch_one("SELECT COUNT(*) AS total,SUM(CASE WHEN flags_json NOT LIKE '%\\Seen%' THEN 1 ELSE 0 END) AS unread FROM mail_message_metadata WHERE tenant_id=? AND account_id=? AND folder_id=?", (tid,account["id"],folder_id)) or {"total":0,"unread":0}
            request.state.store.execute("UPDATE mail_folders SET highest_uid=?,total_count=?,unread_count=?,updated_at=? WHERE tenant_id=? AND id=?", (highest,int(counts.get("total") or 0),int(counts.get("unread") or 0),iso_now(),tid,folder_id))
        finished=iso_now(); request.state.store.execute("UPDATE mail_accounts SET last_sync_at=?,updated_at=? WHERE tenant_id=? AND id=?", (finished,finished,tid,account["id"])); request.state.store.execute("UPDATE mail_sync_runs SET state='completed',folders_synced=?,messages_synced=?,finished_at=? WHERE tenant_id=? AND id=?", (folders_synced,messages_synced,finished,tid,run_id))
        return {"run_id":run_id,"state":"completed","folders_synced":folders_synced,"messages_synced":messages_synced,"finished_at":finished}
    except IntegrationError as exc:
        finished=iso_now(); request.state.store.execute("UPDATE mail_sync_runs SET state='failed',error_code=?,error_message=?,finished_at=? WHERE tenant_id=? AND id=?", (exc.code,str(exc)[:500],finished,tid,run_id)); raise DomainError(exc.code,str(exc),503 if exc.retryable else 424) from exc


@router.get("/mail/me/messages", operation_id="list_my_mail_messages")
def list_my_messages(request: Request, folder: str | None = None, search: str | None = None, thread_key: str | None = None, limit: int = 100, user: CurrentUser = Depends(current_user)):
    account=_account_access(request,user);tid=account["tenant_id"];limit=max(1,min(limit,500))
    sql="""SELECT m.*,f.remote_name AS folder_name FROM mail_message_metadata m JOIN mail_folders f ON f.id=m.folder_id WHERE m.tenant_id=? AND m.account_id=?""";params:list[Any]=[tid,account["id"]]
    if folder: sql+=" AND f.remote_name=?";params.append(folder)
    if thread_key: sql+=" AND m.thread_key=?";params.append(thread_key)
    if search: sql+=" AND (LOWER(COALESCE(m.subject,'')) LIKE ? OR LOWER(COALESCE(m.preview,'')) LIKE ?)";term=f"%{search.lower()}%";params.extend([term,term])
    sql+=" ORDER BY COALESCE(m.received_at,m.sent_at,m.created_at) DESC LIMIT ?";params.append(limit)
    rows=request.state.store.fetch_all(sql,params)
    for row in rows:
        for field in ("sender_json","recipients_json","cc_json","bcc_json","flags_json"):
            row[field.removesuffix("_json")]=json.loads(row.pop(field) or ("{}" if field=="sender_json" else "[]"))
    return {"items":rows}


@router.get("/mail/me/messages/{message_id}", operation_id="get_my_mail_message")
def get_my_message(message_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    account=_account_access(request,user);tid=account["tenant_id"]
    meta=request.state.store.fetch_one("""SELECT m.*,f.remote_name AS folder_name FROM mail_message_metadata m JOIN mail_folders f ON f.id=m.folder_id WHERE m.tenant_id=? AND m.account_id=? AND m.id=?""",(tid,account["id"],message_id))
    if not meta: raise DomainError("MAIL_MESSAGE_NOT_FOUND","Mensagem não localizada nesta conta.",404)
    try: body=_provider(request,account).fetch_message(folder=meta["folder_name"],uid=int(meta["remote_uid"]))
    except IntegrationError as exc: raise DomainError(exc.code,str(exc),503 if exc.retryable else 424) from exc
    if meta.get("content_sha256") and body.get("content_sha256") and meta["content_sha256"] != body["content_sha256"]:
        # Headers-only hash e full-message hash podem diferir; não declarar corrupção nesse caso.
        body["metadata_revision_changed"] = True
    return {"metadata":meta,"content":body}


@router.post("/mail/me/send", status_code=201, operation_id="send_my_mail")
def send_my_mail(data: MailSendInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    account=_account_access(request,user,write=True);tid=account["tenant_id"];scope=f"mail:send:{tid}:{account['id']}";body=data.model_dump(mode="json")
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:return cached[1]
    try:
        external=_provider(request,account).send_message(to=[str(x) for x in data.to],cc=[str(x) for x in data.cc],bcc=[str(x) for x in data.bcc],subject=data.subject,text=data.body_text,html=data.body_html)
    except IntegrationError as exc: raise DomainError(exc.code,str(exc),503 if exc.retryable else 424) from exc
    result={"account_id":account["id"],"message_id":external.get("message_id"),"accepted":bool(external.get("accepted",True)),"sent_at":iso_now()}
    with request.state.store.transaction() as conn:
        save_idempotent(conn,scope,idempotency_key,body,201,result);add_audit(conn,tenant_id=tid,actor_id=user.id,action="send",aggregate_type="mail_message",aggregate_id=str(result.get("message_id") or idempotency_key),correlation_id=request.state.correlation_id,after={"to_count":len(data.to),"cc_count":len(data.cc),"bcc_count":len(data.bcc),"subject":data.subject[:200]});add_outbox(conn,tenant_id=tid,event_type="MailMessageSent",aggregate_type="mail_account",aggregate_id=account["id"],payload={"message_id":result.get("message_id"),"sent_at":result["sent_at"]},correlation_id=request.state.correlation_id)
    return result


@router.get("/mail/me/drafts", operation_id="list_my_mail_drafts")
def list_drafts(request:Request,user:CurrentUser=Depends(current_user)):
    account=_account_access(request,user,write=True);rows=request.state.store.fetch_all("SELECT * FROM mail_drafts WHERE tenant_id=? AND account_id=? AND state='draft' ORDER BY updated_at DESC",(account["tenant_id"],account["id"]));
    for row in rows:
        for field in ("to_json","cc_json","bcc_json","attachments_json"):row[field.removesuffix("_json")]=json.loads(row.pop(field) or "[]")
    return {"items":rows}


@router.post("/mail/me/drafts",status_code=201,operation_id="create_my_mail_draft")
def create_draft(data:MailDraftInput,request:Request,user:CurrentUser=Depends(current_user)):
    account=_account_access(request,user,write=True);tid=account["tenant_id"];did=uuid7();now=iso_now();request.state.store.execute("INSERT INTO mail_drafts(id,tenant_id,account_id,subject,to_json,cc_json,bcc_json,body_text,body_html,attachments_json,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(did,tid,account["id"],data.subject,json.dumps([str(x) for x in data.to]),json.dumps([str(x) for x in data.cc]),json.dumps([str(x) for x in data.bcc]),data.body_text,data.body_html,"[]","draft",1,user.id,now,now));return {"id":did,"state":"draft","version":1}


@router.patch("/mail/me/drafts/{draft_id}",operation_id="update_my_mail_draft")
def update_draft(draft_id:str,data:MailDraftPatch,request:Request,user:CurrentUser=Depends(current_user)):
    account=_account_access(request,user,write=True);tid=account["tenant_id"];row=request.state.store.fetch_one("SELECT * FROM mail_drafts WHERE tenant_id=? AND account_id=? AND id=?",(tid,account["id"],draft_id))
    if not row:raise DomainError("MAIL_DRAFT_NOT_FOUND","Rascunho não localizado.",404)
    if row["state"]!="draft":raise DomainError("MAIL_DRAFT_IMMUTABLE","Rascunho já foi enviado/cancelado.",409)
    if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente do rascunho.",409)
    version=int(row["version"])+1;now=iso_now();request.state.store.execute("UPDATE mail_drafts SET subject=?,to_json=?,cc_json=?,bcc_json=?,body_text=?,body_html=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(data.subject,json.dumps([str(x) for x in data.to]),json.dumps([str(x) for x in data.cc]),json.dumps([str(x) for x in data.bcc]),data.body_text,data.body_html,version,now,tid,draft_id));return {"id":draft_id,"state":"draft","version":version}


@router.post("/mail/me/drafts/{draft_id}/send",operation_id="send_my_mail_draft")
def send_draft(draft_id:str,request:Request,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    account=_account_access(request,user,write=True);tid=account["tenant_id"];row=request.state.store.fetch_one("SELECT * FROM mail_drafts WHERE tenant_id=? AND account_id=? AND id=?",(tid,account["id"],draft_id))
    if not row:raise DomainError("MAIL_DRAFT_NOT_FOUND","Rascunho não localizado.",404)
    if row["state"]=="sent":return {"id":draft_id,"state":"sent","message_id":row.get("provider_message_id")}
    payload={"draft_id":draft_id,"version":row["version"]};scope=f"mail:draft-send:{tid}:{draft_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,payload)
        if cached:return cached[1]
    try:external=_provider(request,account).send_message(to=json.loads(row["to_json"]),cc=json.loads(row["cc_json"]),bcc=json.loads(row["bcc_json"]),subject=row["subject"] or "",text=row["body_text"] or "",html=row.get("body_html"))
    except IntegrationError as exc:raise DomainError(exc.code,str(exc),503 if exc.retryable else 424) from exc
    result={"id":draft_id,"state":"sent","message_id":external.get("message_id"),"sent_at":iso_now()}
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE mail_drafts SET state='sent',provider_message_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(result["message_id"],result["sent_at"],tid,draft_id));save_idempotent(conn,scope,idempotency_key,payload,200,result);add_audit(conn,tenant_id=tid,actor_id=user.id,action="send_draft",aggregate_type="mail_draft",aggregate_id=draft_id,correlation_id=request.state.correlation_id,after={"message_id":result["message_id"]})
    return result


@router.post("/mail/accounts/{account_id}/delegations",status_code=201,operation_id="create_mail_delegation")
def create_delegation(account_id:str,data:MailDelegationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,MAIL_ADMIN_ROLES);tid=tenant(user);account=request.state.store.fetch_one("SELECT id FROM mail_accounts WHERE tenant_id=? AND id=?",(tid,account_id))
    if not account:raise DomainError("MAIL_ACCOUNT_NOT_FOUND","Conta não localizada.",404)
    if not request.state.store.fetch_one("SELECT id FROM users WHERE tenant_id=? AND id=?",(tid,data.delegate_user_id)):raise DomainError("MAIL_DELEGATE_NOT_FOUND","Usuário delegado não localizado.",404)
    if data.valid_from and data.valid_until and data.valid_until<=data.valid_from:raise DomainError("MAIL_DELEGATION_PERIOD_INVALID","Fim da delegação deve ser posterior ao início.",422)
    did=uuid7();now=iso_now();request.state.store.execute("INSERT INTO mail_delegations(id,tenant_id,account_id,delegate_user_id,can_read,can_send,valid_from,valid_until,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(did,tid,account_id,data.delegate_user_id,1 if data.can_read else 0,1 if data.can_send else 0,data.valid_from.isoformat() if data.valid_from else None,data.valid_until.isoformat() if data.valid_until else None,"active",now,now));return {"id":did,"account_id":account_id,"delegate_user_id":data.delegate_user_id,"can_read":data.can_read,"can_send":data.can_send,"state":"active"}

@router.post("/mail/me/messages/{message_id}/seen", operation_id="set_my_mail_message_seen")
def set_message_seen(message_id: str, data: MailSeenInput, request: Request, user: CurrentUser = Depends(current_user)):
    account, meta = _message_access(request, user, message_id, write=True); tid = account["tenant_id"]
    try:
        _provider(request, account).set_seen(folder=meta["folder_name"], uid=int(meta["remote_uid"]), seen=data.seen)
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 503 if exc.retryable else 424) from exc
    flags = json.loads(meta.get("flags_json") or "[]")
    flags = [flag for flag in flags if flag != "\\Seen"]
    if data.seen:
        flags.append("\\Seen")
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE mail_message_metadata SET flags_json=?,updated_at=? WHERE tenant_id=? AND id=?", (json.dumps(flags), now, tid, message_id))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="mark_seen" if data.seen else "mark_unseen", aggregate_type="mail_message", aggregate_id=message_id, correlation_id=request.state.correlation_id, after={"seen": data.seen})
    _recount_folder(request.state.store, tenant_id=tid, account_id=account["id"], folder_id=meta["folder_id"])
    return {"id": message_id, "seen": data.seen, "updated_at": now}


@router.post("/mail/me/messages/{message_id}/move", operation_id="move_my_mail_message")
def move_message(message_id: str, data: MailMoveInput, request: Request, user: CurrentUser = Depends(current_user)):
    account, meta = _message_access(request, user, message_id, write=True); tid = account["tenant_id"]
    destination = request.state.store.fetch_one(
        "SELECT * FROM mail_folders WHERE tenant_id=? AND account_id=? AND remote_name=?",
        (tid, account["id"], data.destination_folder),
    )
    if not destination:
        raise DomainError("MAIL_FOLDER_NOT_FOUND", "Pasta de destino não foi sincronizada para esta conta.", 404)
    if destination["id"] == meta["folder_id"]:
        return {"id": message_id, "folder": destination["remote_name"], "moved": False}
    try:
        _provider(request, account).move_message(folder=meta["folder_name"], uid=int(meta["remote_uid"]), destination=destination["remote_name"])
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 503 if exc.retryable else 424) from exc
    # UID pode mudar no servidor após MOVE; removemos o metadata local e o próximo sync
    # da pasta de destino recupera o UID canônico, evitando inventar identidade remota.
    with request.state.store.transaction() as conn:
        conn.execute("DELETE FROM mail_message_metadata WHERE tenant_id=? AND account_id=? AND id=?", (tid, account["id"], message_id))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="move", aggregate_type="mail_message", aggregate_id=message_id, correlation_id=request.state.correlation_id, after={"from": meta["folder_name"], "to": destination["remote_name"]})
    _recount_folder(request.state.store, tenant_id=tid, account_id=account["id"], folder_id=meta["folder_id"])
    return {"id": message_id, "folder": destination["remote_name"], "moved": True, "resync_required": True}


@router.post("/mail/me/messages/{message_id}/trash", operation_id="trash_my_mail_message")
def trash_message(message_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    account, _ = _message_access(request, user, message_id, write=True)
    trash = _folder_by_special_use(request, account, "\\trash", "trash", "lixeira")
    if not trash:
        raise DomainError("MAIL_TRASH_NOT_AVAILABLE", "A pasta de lixeira não foi localizada no servidor de e-mail.", 409)
    return move_message(message_id, MailMoveInput(destination_folder=trash["remote_name"]), request, user)


@router.post("/mail/me/messages/{message_id}/reply", status_code=201, operation_id="reply_my_mail_message")
def reply_message(message_id: str, data: MailReplyInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    account, meta = _message_access(request, user, message_id, write=True); tid = account["tenant_id"]
    sender = json.loads(meta.get("sender_json") or "{}")
    recipients = json.loads(meta.get("recipients_json") or "[]")
    cc = json.loads(meta.get("cc_json") or "[]")
    to = [str(sender.get("email") or "").lower()] if sender.get("email") else []
    cc_out: list[str] = []
    if data.reply_all:
        candidates = [*(str(x.get("email") or "").lower() for x in recipients), *(str(x.get("email") or "").lower() for x in cc)]
        own = str(account.get("email") or "").lower()
        cc_out = list(dict.fromkeys(x for x in candidates if x and x != own and x not in to))
    if not to:
        raise DomainError("MAIL_REPLY_RECIPIENT_MISSING", "A mensagem original não possui remetente válido.", 409)
    subject = str(meta.get("subject") or "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    payload = {"message_id": message_id, "reply_all": data.reply_all, "body_text": data.body_text, "body_html": data.body_html}
    scope = f"mail:reply:{tid}:{account['id']}:{message_id}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, payload)
        if cached: return cached[1]
    try:
        external = _provider(request, account).send_message(to=to, cc=cc_out, bcc=[], subject=subject, text=data.body_text, html=data.body_html, in_reply_to=meta.get("message_id"), references=meta.get("message_id"))
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 503 if exc.retryable else 424) from exc
    result = {"source_message_id": message_id, "message_id": external.get("message_id"), "accepted": bool(external.get("accepted", True)), "sent_at": iso_now()}
    with request.state.store.transaction() as conn:
        save_idempotent(conn, scope, idempotency_key, payload, 201, result)
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="reply", aggregate_type="mail_message", aggregate_id=message_id, correlation_id=request.state.correlation_id, after={"reply_all": data.reply_all, "to_count": len(to), "cc_count": len(cc_out)})
    return result


@router.post("/mail/me/messages/{message_id}/forward", status_code=201, operation_id="forward_my_mail_message")
def forward_message(message_id: str, data: MailForwardInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    account, meta = _message_access(request, user, message_id, write=True); tid = account["tenant_id"]
    subject = data.subject.strip() or str(meta.get("subject") or "")
    if not subject.lower().startswith(("fwd:", "enc:")):
        subject = f"Fwd: {subject}"
    payload = {**data.model_dump(mode="json"), "source_message_id": message_id, "subject": subject}
    scope = f"mail:forward:{tid}:{account['id']}:{message_id}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, payload)
        if cached: return cached[1]
    try:
        external = _provider(request, account).send_message(to=[str(x) for x in data.to], cc=[str(x) for x in data.cc], bcc=[str(x) for x in data.bcc], subject=subject, text=data.body_text, html=data.body_html, references=meta.get("message_id"))
    except IntegrationError as exc:
        raise DomainError(exc.code, str(exc), 503 if exc.retryable else 424) from exc
    result = {"source_message_id": message_id, "message_id": external.get("message_id"), "accepted": bool(external.get("accepted", True)), "sent_at": iso_now()}
    with request.state.store.transaction() as conn:
        save_idempotent(conn, scope, idempotency_key, payload, 201, result)
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="forward", aggregate_type="mail_message", aggregate_id=message_id, correlation_id=request.state.correlation_id, after={"to_count": len(data.to), "cc_count": len(data.cc), "bcc_count": len(data.bcc)})
    return result


@router.get("/mail/me/messages/{message_id}/attachments/{attachment_index}", operation_id="download_my_mail_attachment")
def download_attachment(message_id: str, attachment_index: int, request: Request, user: CurrentUser = Depends(current_user)):
    account, meta = _message_access(request, user, message_id)
    try:
        item = _provider(request, account).fetch_attachment(folder=meta["folder_name"], uid=int(meta["remote_uid"]), attachment_index=attachment_index)
    except IntegrationError as exc:
        status = 404 if exc.code == "MAIL_ATTACHMENT_NOT_FOUND" else (503 if exc.retryable else 424)
        raise DomainError(exc.code, str(exc), status) from exc
    filename = str(item.get("filename") or f"anexo-{attachment_index + 1}").replace('"', "").replace("\r", "").replace("\n", "")
    content = bytes(item["content"])
    headers = {"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-SHA256": str(item["sha256"]), "Cache-Control": "private, no-store"}
    return Response(content=content, media_type=str(item.get("content_type") or "application/octet-stream"), headers=headers)


@router.get("/mail/accounts/{account_id}/delegations", operation_id="list_mail_delegations")
def list_delegations(account_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, MAIL_ADMIN_ROLES); tid = tenant(user)
    if not request.state.store.fetch_one("SELECT id FROM mail_accounts WHERE tenant_id=? AND id=?", (tid, account_id)):
        raise DomainError("MAIL_ACCOUNT_NOT_FOUND", "Conta não localizada.", 404)
    return {"items": request.state.store.fetch_all("SELECT id,account_id,delegate_user_id,can_read,can_send,valid_from,valid_until,state,created_at,updated_at FROM mail_delegations WHERE tenant_id=? AND account_id=? ORDER BY created_at DESC", (tid, account_id))}


@router.post("/mail/accounts/{account_id}/delegations/{delegation_id}/revoke", operation_id="revoke_mail_delegation")
def revoke_delegation(account_id: str, delegation_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, MAIL_ADMIN_ROLES); tid = tenant(user); now = iso_now()
    row = request.state.store.fetch_one("SELECT * FROM mail_delegations WHERE tenant_id=? AND account_id=? AND id=?", (tid, account_id, delegation_id))
    if not row:
        raise DomainError("MAIL_DELEGATION_NOT_FOUND", "Delegação não localizada.", 404)
    if row["state"] == "revoked":
        return {"id": delegation_id, "state": "revoked", "updated_at": row["updated_at"]}
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE mail_delegations SET state='revoked',updated_at=? WHERE tenant_id=? AND id=?", (now, tid, delegation_id))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="revoke", aggregate_type="mail_delegation", aggregate_id=delegation_id, correlation_id=request.state.correlation_id, after={"state": "revoked"})
    return {"id": delegation_id, "state": "revoked", "updated_at": now}

