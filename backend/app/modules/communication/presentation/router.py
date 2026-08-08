from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, model_validator

from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user
from app.shared.security.authorization import ADMIN_ROLES, require_roles, tenant_id

router = APIRouter(tags=["communication"])
COMMUNICATION_ROLES = ADMIN_ROLES | {"event_manager", "finance_manager", "hr_manager", "request_agent", "support"}
CHANNELS = {"internal", "email", "whatsapp", "push", "sms"}
_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.-]{0,79})\s*\}\}")


class TemplateInput(BaseModel):
    template_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    name: str = Field(min_length=2, max_length=160)
    channel: Literal["internal", "email", "whatsapp", "push", "sms"]
    subject_template: str | None = Field(default=None, max_length=300)
    body_template: str = Field(min_length=1, max_length=20000)
    variables: list[str] = Field(default_factory=list, max_length=100)


class TemplateVersionInput(BaseModel):
    subject_template: str | None = Field(default=None, max_length=300)
    body_template: str = Field(min_length=1, max_length=20000)
    variables: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)


class PublishInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class PreferenceInput(BaseModel):
    channel: Literal["internal", "email", "whatsapp", "push", "sms"]
    enabled: bool = True
    quiet_hours: dict[str, Any] = Field(default_factory=dict)


class NotificationInput(BaseModel):
    recipient_person_id: str
    channel: Literal["internal", "email", "whatsapp", "push", "sms"]
    template_key: str | None = None
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    variables: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def content_required(self):
        if not self.template_key and not self.body:
            raise ValueError("Informe template_key ou body.")
        return self


class RetryInput(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


def _lookup_variable(variables: dict[str, Any], path: str) -> tuple[bool, Any]:
    value: Any = variables
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _safe_template(template: str | None, variables: dict[str, Any], declared: list[str]) -> str | None:
    if template is None:
        return None
    required = set(_VARIABLE.findall(template)) | set(declared)
    missing = sorted(key for key in required if not _lookup_variable(variables, key)[0])
    if missing:
        raise DomainError("COMMUNICATION_VARIABLES_REQUIRED", "Existem variáveis obrigatórias ausentes.", 422, errors=[{"field": key, "code": "REQUIRED", "message": "Variável obrigatória."} for key in missing])
    def repl(match: re.Match[str]) -> str:
        found, value = _lookup_variable(variables, match.group(1))
        return str(value if found and value is not None else "")
    return _VARIABLE.sub(repl, template)


def _template(store, tid: str, key: str, channel: str) -> tuple[dict[str, Any], dict[str, Any]]:
    row = store.fetch_one("SELECT * FROM communication_templates WHERE tenant_id=? AND template_key=? AND state='published'", (tid, key))
    if not row:
        raise DomainError("COMMUNICATION_TEMPLATE_NOT_FOUND", "Template publicado não localizado.", 404)
    if row["channel"] != channel:
        raise DomainError("COMMUNICATION_TEMPLATE_CHANNEL_MISMATCH", "O template não pertence ao canal solicitado.", 422)
    version = store.fetch_one("SELECT * FROM communication_template_versions WHERE tenant_id=? AND template_id=? AND version=? AND state='published'", (tid, row["id"], row["current_version"]))
    if not version:
        raise DomainError("COMMUNICATION_TEMPLATE_VERSION_NOT_FOUND", "Versão publicada do template não localizada.", 409)
    return row, version


def _can_view_all(user: CurrentUser) -> bool:
    return bool(set(user.roles).intersection(COMMUNICATION_ROLES | {"auditor"}))


@router.get("/communication/templates", operation_id="list_communication_templates")
def list_templates(request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user, COMMUNICATION_ROLES | {"auditor"}); tid=tenant_id(user)
    rows=request.state.store.fetch_all("SELECT * FROM communication_templates WHERE tenant_id=? ORDER BY name",(tid,))
    for row in rows:
        row["versions"]=request.state.store.fetch_all("SELECT id,version,state,subject_template,body_template,variables_json,change_reason,created_by,created_at FROM communication_template_versions WHERE tenant_id=? AND template_id=? ORDER BY version DESC",(tid,row["id"]))
        for version in row["versions"]: version["variables"]=json.loads(version.pop("variables_json") or "[]")
    return {"items":rows}


@router.post("/communication/templates", status_code=201, operation_id="create_communication_template")
def create_template(data: TemplateInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user,COMMUNICATION_ROLES);tid=tenant_id(user);now=iso_now();template_id=uuid7();version_id=uuid7()
    declared=sorted(set(data.variables)|set(_VARIABLE.findall(data.body_template))|set(_VARIABLE.findall(data.subject_template or "")))
    result={"id":template_id,"template_key":data.template_key,"name":data.name,"channel":data.channel,"state":"draft","current_version":1}
    try:
        with request.state.store.transaction() as conn:
            conn.execute("INSERT INTO communication_templates(id,tenant_id,template_key,name,channel,state,current_version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(template_id,tid,data.template_key,data.name,data.channel,"draft",1,user.id,now,now))
            conn.execute("INSERT INTO communication_template_versions(id,tenant_id,template_id,version,subject_template,body_template,variables_json,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(version_id,tid,template_id,1,data.subject_template,data.body_template,json.dumps(declared,ensure_ascii=False,sort_keys=True),"draft",user.id,now))
            add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="communication_template",aggregate_id=template_id,correlation_id=request.state.correlation_id,after=result)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper() or "duplicate" in str(exc).lower(): raise DomainError("COMMUNICATION_TEMPLATE_EXISTS","Já existe template com esta chave.",409) from exc
        raise
    return result


@router.post("/communication/templates/{template_id}/versions", status_code=201, operation_id="create_communication_template_version")
def create_template_version(template_id: str, data: TemplateVersionInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user,COMMUNICATION_ROLES);tid=tenant_id(user);row=request.state.store.fetch_one("SELECT * FROM communication_templates WHERE tenant_id=? AND id=?",(tid,template_id))
    if not row: raise DomainError("COMMUNICATION_TEMPLATE_NOT_FOUND","Template não localizado.",404)
    version=int(row["current_version"])+1;now=iso_now();declared=sorted(set(data.variables)|set(_VARIABLE.findall(data.body_template))|set(_VARIABLE.findall(data.subject_template or "")))
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO communication_template_versions(id,tenant_id,template_id,version,subject_template,body_template,variables_json,state,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,template_id,version,data.subject_template,data.body_template,json.dumps(declared,ensure_ascii=False,sort_keys=True),"draft",data.reason,user.id,now))
        conn.execute("UPDATE communication_templates SET current_version=?,state='draft',updated_at=? WHERE tenant_id=? AND id=?",(version,now,tid,template_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="version",aggregate_type="communication_template",aggregate_id=template_id,correlation_id=request.state.correlation_id,before={"version":row["current_version"]},after={"version":version},reason=data.reason)
    return {"id":template_id,"current_version":version,"state":"draft"}


@router.post("/communication/templates/{template_id}/publish", operation_id="publish_communication_template")
def publish_template(template_id: str, data: PublishInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user,COMMUNICATION_ROLES);tid=tenant_id(user);row=request.state.store.fetch_one("SELECT * FROM communication_templates WHERE tenant_id=? AND id=?",(tid,template_id))
    if not row: raise DomainError("COMMUNICATION_TEMPLATE_NOT_FOUND","Template não localizado.",404)
    if int(row["current_version"])!=data.expected_version: raise DomainError("VERSION_CONFLICT","O template foi alterado por outro usuário.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE communication_template_versions SET state='superseded' WHERE tenant_id=? AND template_id=? AND state='published'",(tid,template_id))
        conn.execute("UPDATE communication_template_versions SET state='published' WHERE tenant_id=? AND template_id=? AND version=?",(tid,template_id,data.expected_version))
        conn.execute("UPDATE communication_templates SET state='published',updated_at=? WHERE tenant_id=? AND id=?",(now,tid,template_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="communication_template",aggregate_id=template_id,correlation_id=request.state.correlation_id,after={"version":data.expected_version,"state":"published"},reason=data.reason)
    return {"id":template_id,"current_version":data.expected_version,"state":"published"}


@router.get("/communication/preferences/me", operation_id="get_my_communication_preferences")
def my_preferences(request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant_id(user)
    if not user.person_id: return {"items":[]}
    rows=request.state.store.fetch_all("SELECT channel,enabled,quiet_hours_json,updated_at FROM communication_preferences WHERE tenant_id=? AND person_id=? ORDER BY channel",(tid,user.person_id))
    for row in rows: row["enabled"]=bool(row["enabled"]);row["quiet_hours"]=json.loads(row.pop("quiet_hours_json") or "{}")
    return {"items":rows}


@router.put("/communication/preferences/me", operation_id="set_my_communication_preference")
def set_preference(data: PreferenceInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant_id(user)
    if not user.person_id: raise DomainError("PERSON_LINK_REQUIRED","A conta precisa estar vinculada a uma pessoa.",403)
    now=iso_now();existing=request.state.store.fetch_one("SELECT id FROM communication_preferences WHERE tenant_id=? AND person_id=? AND channel=?",(tid,user.person_id,data.channel))
    if existing: request.state.store.execute("UPDATE communication_preferences SET enabled=?,quiet_hours_json=?,updated_by=?,updated_at=? WHERE tenant_id=? AND id=?",(1 if data.enabled else 0,json.dumps(data.quiet_hours,ensure_ascii=False,sort_keys=True),user.id,now,tid,existing["id"]))
    else: request.state.store.execute("INSERT INTO communication_preferences(id,tenant_id,person_id,channel,enabled,quiet_hours_json,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,user.person_id,data.channel,1 if data.enabled else 0,json.dumps(data.quiet_hours,ensure_ascii=False,sort_keys=True),user.id,now))
    return {"channel":data.channel,"enabled":data.enabled,"quiet_hours":data.quiet_hours,"updated_at":now}


@router.get("/notifications", operation_id="list_notifications")
def list_notifications(request: Request, state: str | None = None, channel: str | None = None, limit: int = 100, user: CurrentUser = Depends(current_user)):
    tid=tenant_id(user);limit=max(1,min(limit,500));sql="SELECT * FROM notifications WHERE tenant_id=?";params:list[Any]=[tid]
    if not _can_view_all(user):
        if not user.person_id:return {"items":[]}
        sql+=" AND recipient_person_id=?";params.append(user.person_id)
    if state:sql+=" AND state=?";params.append(state)
    if channel:sql+=" AND channel=?";params.append(channel)
    sql+=" ORDER BY created_at DESC LIMIT ?";params.append(limit)
    return {"items":request.state.store.fetch_all(sql,params)}


@router.get("/notifications/{notification_id}", operation_id="get_notification")
def get_notification(notification_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    tid=tenant_id(user);row=request.state.store.fetch_one("SELECT * FROM notifications WHERE tenant_id=? AND id=?",(tid,notification_id))
    if not row or (not _can_view_all(user) and row.get("recipient_person_id")!=user.person_id): raise DomainError("NOTIFICATION_NOT_FOUND","Notificação não localizada.",404)
    row["events"]=request.state.store.fetch_all("SELECT id,event_type,state,provider_message_id,details_json,occurred_at FROM notification_events WHERE tenant_id=? AND notification_id=? ORDER BY occurred_at",(tid,notification_id))
    for event in row["events"]:event["details"]=json.loads(event.pop("details_json") or "{}")
    return row


@router.post("/notifications", status_code=201, operation_id="queue_notification")
def queue_notification(data: NotificationInput, request: Request, idempotency_key: str | None = Header(None, alias="Idempotency-Key"), user: CurrentUser = Depends(current_user)):
    require_roles(user,COMMUNICATION_ROLES);tid=tenant_id(user)
    if not idempotency_key: raise DomainError("IDEMPOTENCY_KEY_REQUIRED","Informe Idempotency-Key para enfileirar notificações.",400)
    person=request.state.store.fetch_one("SELECT id FROM people WHERE tenant_id=? AND id=?",(tid,data.recipient_person_id))
    if not person: raise DomainError("PERSON_NOT_FOUND","Destinatário não localizado.",404)
    preference=request.state.store.fetch_one("SELECT enabled FROM communication_preferences WHERE tenant_id=? AND person_id=? AND channel=?",(tid,data.recipient_person_id,data.channel))
    if preference is not None and not bool(preference["enabled"]): raise DomainError("COMMUNICATION_CHANNEL_DISABLED","O destinatário desabilitou este canal.",409)
    template_key=data.template_key;subject=data.subject;body=data.body
    if template_key:
        _,version=_template(request.state.store,tid,template_key,data.channel);declared=json.loads(version["variables_json"] or "[]");subject=_safe_template(version.get("subject_template"),data.variables,declared);body=_safe_template(version["body_template"],data.variables,declared)
    assert body is not None
    payload=data.model_dump(mode="json");payload.update({"subject":subject,"body":body})
    scope=f"notification:{tid}"
    with request.state.store.transaction() as conn:
        replay=get_idempotent(conn,scope,idempotency_key,payload)
        if replay:return replay[1]
        nid=uuid7();now=iso_now();scheduled_text=data.scheduled_at.isoformat() if data.scheduled_at else None
        scheduled_future=bool(data.scheduled_at and data.scheduled_at.astimezone(UTC)>datetime.now(UTC))
        state="scheduled" if scheduled_future else "queued"
        result={"id":nid,"recipient_person_id":data.recipient_person_id,"channel":data.channel,"template_key":template_key,"subject":subject,"body":body,"state":state,"scheduled_at":scheduled_text}
        conn.execute("INSERT INTO notifications(id,tenant_id,recipient_person_id,channel,template_key,subject,body,state,scheduled_at,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(nid,tid,data.recipient_person_id,data.channel,template_key,subject,body,state,scheduled_text,idempotency_key,now))
        conn.execute("INSERT INTO notification_events(id,tenant_id,notification_id,event_type,state,details_json,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,nid,"queued",state,json.dumps({"scheduled_at":scheduled_text},ensure_ascii=False,sort_keys=True),now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="queue",aggregate_type="notification",aggregate_id=nid,correlation_id=request.state.correlation_id,after={"channel":data.channel,"state":state,"recipient_person_id":data.recipient_person_id})
        if state=="queued": add_outbox(conn,tenant_id=tid,event_type="NotificationRequested",aggregate_type="notification",aggregate_id=nid,payload={"notification_id":nid,"channel":data.channel},correlation_id=request.state.correlation_id)
        save_idempotent(conn,scope,idempotency_key,payload,201,result)
    return result


@router.post("/notifications/{notification_id}/retry", operation_id="retry_notification")
def retry_notification(notification_id: str, data: RetryInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user,COMMUNICATION_ROLES);tid=tenant_id(user);row=request.state.store.fetch_one("SELECT * FROM notifications WHERE tenant_id=? AND id=?",(tid,notification_id))
    if not row:raise DomainError("NOTIFICATION_NOT_FOUND","Notificação não localizada.",404)
    if row["state"]=="sent":raise DomainError("NOTIFICATION_ALREADY_SENT","Notificação já enviada não pode ser reenviada por retry.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE notifications SET state='queued' WHERE tenant_id=? AND id=?",(tid,notification_id))
        conn.execute("INSERT INTO notification_events(id,tenant_id,notification_id,event_type,state,details_json,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,notification_id,"retry_requested","queued",json.dumps({"reason":data.reason},ensure_ascii=False,sort_keys=True),now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="retry",aggregate_type="notification",aggregate_id=notification_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":"queued"},reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="NotificationRequested",aggregate_type="notification",aggregate_id=notification_id,payload={"notification_id":notification_id,"channel":row["channel"]},correlation_id=request.state.correlation_id)
    return {"id":notification_id,"state":"queued"}


@router.post("/notifications/{notification_id}/cancel", operation_id="cancel_notification")
def cancel_notification(notification_id: str, data: RetryInput, request: Request, user: CurrentUser = Depends(current_user)):
    require_roles(user,COMMUNICATION_ROLES);tid=tenant_id(user);row=request.state.store.fetch_one("SELECT * FROM notifications WHERE tenant_id=? AND id=?",(tid,notification_id))
    if not row:raise DomainError("NOTIFICATION_NOT_FOUND","Notificação não localizada.",404)
    if row["state"] in {"sent","cancelled"}:raise DomainError("NOTIFICATION_NOT_CANCELLABLE","Notificação não pode ser cancelada neste estado.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE notifications SET state='cancelled' WHERE tenant_id=? AND id=?",(tid,notification_id))
        conn.execute("INSERT INTO notification_events(id,tenant_id,notification_id,event_type,state,details_json,occurred_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,notification_id,"cancelled","cancelled",json.dumps({"reason":data.reason},ensure_ascii=False,sort_keys=True),now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="cancel",aggregate_type="notification",aggregate_id=notification_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":"cancelled"},reason=data.reason)
    return {"id":notification_id,"state":"cancelled"}
