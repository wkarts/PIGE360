from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.community_operations import NOTICE_ROLES, _notice_visible
from app.modules.operations.common import dumps, loads, require, tenant
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["notices"])


class NoticeVersionInput(BaseModel):
    title:str=Field(min_length=2,max_length=200)
    body:str=Field(min_length=2,max_length=20000)
    priority:Literal["normal","high","urgent","emergency"]="normal"
    audience:dict[str,Any]=Field(default_factory=lambda:{"type":"all"})
    channels:list[str]=Field(default_factory=lambda:["internal"])
    scheduled_at:str|None=None
    expires_at:str|None=None
    requires_acknowledgement:bool=False
    reason:str=Field(min_length=3,max_length=1000)


class NoticeReasonInput(BaseModel):
    reason:str=Field(min_length=3,max_length=1000)


def _row(request:Request,tid:str,notice_id:str)->dict[str,Any]:
    row=request.state.store.fetch_one("SELECT * FROM notices WHERE tenant_id=? AND id=?",(tid,notice_id))
    if not row:raise DomainError("NOTICE_NOT_FOUND","Aviso não localizado.",404)
    return row


@router.get("/notices/{notice_id}",operation_id="get_notice")
def get_notice(notice_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);row=_row(request,tid,notice_id)
    if not _notice_visible(request,tid,row,user):raise DomainError("NOTICE_NOT_FOUND","Aviso não localizado.",404)
    row["audience"]=loads(row.pop("audience_json"),{});row["channels"]=loads(row.pop("channels_json"),[])
    row["versions"]=request.state.store.fetch_all("SELECT id,version,snapshot_json,change_reason,created_by,created_at FROM notice_versions WHERE tenant_id=? AND notice_id=? ORDER BY version DESC",(tid,notice_id))
    for version in row["versions"]:version["snapshot"]=loads(version.pop("snapshot_json"),{})
    if user.person_id:
        receipt=request.state.store.fetch_one("SELECT first_seen_at,acknowledged_at FROM notice_receipts WHERE tenant_id=? AND notice_id=? AND person_id=?",(tid,notice_id,user.person_id));row["receipt"]=receipt
    return row


@router.post("/notices/{notice_id}/versions",status_code=201,operation_id="create_notice_version")
def create_notice_version(notice_id:str,data:NoticeVersionInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,NOTICE_ROLES);tid=tenant(user);row=_row(request,tid,notice_id);version=int(row.get("version") or 1)+1;now=iso_now();audience=dict(data.audience);audience["requires_acknowledgement"]=data.requires_acknowledgement
    snapshot={"title":data.title,"body":data.body,"priority":data.priority,"audience":audience,"channels":data.channels,"scheduled_at":data.scheduled_at,"expires_at":data.expires_at,"state":"draft"}
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE notices SET title=?,body=?,priority=?,audience_json=?,channels_json=?,scheduled_at=?,expires_at=?,state='draft',version=?,updated_at=? WHERE tenant_id=? AND id=?",(data.title,data.body,data.priority,dumps(audience),dumps(data.channels),data.scheduled_at,data.expires_at,version,now,tid,notice_id))
        conn.execute("INSERT INTO notice_versions(id,tenant_id,notice_id,version,snapshot_json,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,notice_id,version,dumps(snapshot),data.reason,user.id,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="version",aggregate_type="notice",aggregate_id=notice_id,correlation_id=request.state.correlation_id,before={"version":row.get("version"),"state":row["state"]},after={"version":version,"state":"draft"},reason=data.reason)
    return {"id":notice_id,"version":version,"state":"draft"}


@router.post("/notices/{notice_id}/publish",operation_id="publish_notice")
def publish_notice(notice_id:str,data:NoticeReasonInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,NOTICE_ROLES);tid=tenant(user);row=_row(request,tid,notice_id)
    if row["state"]=="published":return {"id":notice_id,"state":"published","version":row["version"],"idempotent":True}
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE notices SET state='published',updated_at=? WHERE tenant_id=? AND id=?",(now,tid,notice_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="notice",aggregate_id=notice_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":"published","version":row["version"]},reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="NoticePublished",aggregate_type="notice",aggregate_id=notice_id,payload={"id":notice_id,"state":"published","version":row["version"]},correlation_id=request.state.correlation_id)
    return {"id":notice_id,"state":"published","version":row["version"]}


def _receipt(notice_id:str,request:Request,user:CurrentUser,*,acknowledge:bool)->dict[str,Any]:
    tid=tenant(user);row=_row(request,tid,notice_id)
    if not _notice_visible(request,tid,row,user) or not user.person_id:raise DomainError("NOTICE_NOT_FOUND","Aviso não localizado.",404)
    now=iso_now();existing=request.state.store.fetch_one("SELECT * FROM notice_receipts WHERE tenant_id=? AND notice_id=? AND person_id=?",(tid,notice_id,user.person_id))
    if existing:
        if acknowledge and not existing.get("acknowledged_at"):request.state.store.execute("UPDATE notice_receipts SET acknowledged_at=?,first_seen_at=COALESCE(first_seen_at,?) WHERE tenant_id=? AND id=?",(now,now,tid,existing["id"]))
        elif not existing.get("first_seen_at"):request.state.store.execute("UPDATE notice_receipts SET first_seen_at=? WHERE tenant_id=? AND id=?",(now,tid,existing["id"]))
    else:
        request.state.store.execute("INSERT INTO notice_receipts(id,tenant_id,notice_id,person_id,first_seen_at,acknowledged_at,created_at) VALUES(?,?,?,?,?,?,?)",(uuid7(),tid,notice_id,user.person_id,now,now if acknowledge else None,now))
    return {"notice_id":notice_id,"person_id":user.person_id,"first_seen_at":existing.get("first_seen_at") if existing and existing.get("first_seen_at") else now,"acknowledged_at":now if acknowledge else (existing.get("acknowledged_at") if existing else None)}


@router.post("/notices/{notice_id}/read",operation_id="mark_notice_read")
def mark_read(notice_id:str,request:Request,user:CurrentUser=Depends(current_user)):return _receipt(notice_id,request,user,acknowledge=False)


@router.post("/notices/{notice_id}/acknowledge",operation_id="acknowledge_notice")
def acknowledge(notice_id:str,request:Request,user:CurrentUser=Depends(current_user)):return _receipt(notice_id,request,user,acknowledge=True)


@router.get("/notices/{notice_id}/receipts",operation_id="list_notice_receipts")
def receipts(notice_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,NOTICE_ROLES|{"auditor"});tid=tenant(user);_row(request,tid,notice_id)
    rows=request.state.store.fetch_all("SELECT nr.*,p.full_name FROM notice_receipts nr JOIN people p ON p.id=nr.person_id AND p.tenant_id=nr.tenant_id WHERE nr.tenant_id=? AND nr.notice_id=? ORDER BY nr.first_seen_at",(tid,notice_id));return {"items":rows}
