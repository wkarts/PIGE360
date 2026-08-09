from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import ADMIN_ROLES, dumps, loads, require, tenant
from app.modules.operations.community_operations import REQUEST_AGENT_ROLES
from app.modules.workflows.application.service import load_definition_version
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["requests"])
TYPE_ROLES=ADMIN_ROLES|{"request_agent","support"}


class RequestTypeInput(BaseModel):
    code:str=Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    name:str=Field(min_length=2,max_length=160)
    department:str|None=None
    default_sla_hours:int=Field(default=72,ge=1,le=8760)
    form_schema:dict[str,Any]=Field(default_factory=lambda:{"fields":[]})
    workflow:dict[str,Any]=Field(default_factory=dict)


class RequestTypeVersionInput(BaseModel):
    form_schema:dict[str,Any]
    workflow:dict[str,Any]=Field(default_factory=dict)
    reason:str=Field(min_length=3,max_length=1000)


class RequestTypePublishInput(BaseModel):
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=3,max_length=1000)


class CommentInput(BaseModel):
    body:str=Field(min_length=1,max_length=10000)
    visibility:Literal["requester","internal"]="requester"



def _normalize_workflow_binding(request: Request, tid: str, workflow: dict[str, Any]) -> dict[str, Any]:
    if not workflow:
        return {}
    allowed={"definition_id","definition_code"}
    unknown=set(workflow)-allowed
    if unknown:
        raise DomainError("REQUEST_WORKFLOW_INVALID", f"Campos de workflow não suportados: {', '.join(sorted(unknown))}.", 422)
    definition_id=workflow.get("definition_id");definition_code=workflow.get("definition_code")
    if bool(definition_id)==bool(definition_code):
        raise DomainError("REQUEST_WORKFLOW_INVALID", "Informe definition_id ou definition_code, exclusivamente.", 422)
    with request.state.store.transaction() as conn:
        definition,version,_=load_definition_version(conn,tid,definition_id=definition_id,definition_code=definition_code)
    return {"definition_id":definition["id"],"definition_version":int(version["version"])}

def _type(request:Request,tid:str,type_id:str)->dict[str,Any]:
    row=request.state.store.fetch_one("SELECT * FROM request_type_definitions WHERE tenant_id=? AND id=?",(tid,type_id))
    if not row:raise DomainError("REQUEST_TYPE_NOT_FOUND","Tipo de solicitação não localizado.",404)
    return row


def _request_access(request:Request,user:CurrentUser,request_id:str)->tuple[str,dict[str,Any],bool]:
    tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM service_requests WHERE tenant_id=? AND id=?",(tid,request_id));agent=bool(set(user.roles).intersection(REQUEST_AGENT_ROLES|{"auditor"}))
    if not row or (not agent and (not user.person_id or row.get("requester_person_id")!=user.person_id)):raise DomainError("REQUEST_NOT_FOUND","Solicitação não localizada.",404)
    return tid,row,agent


@router.get("/request-types",operation_id="list_request_types")
def list_types(request:Request,user:CurrentUser=Depends(current_user)):
    tid=tenant(user);admin=bool(set(user.roles).intersection(TYPE_ROLES|{"auditor"}));sql="SELECT * FROM request_type_definitions WHERE tenant_id=?"+("" if admin else " AND state='published'");rows=request.state.store.fetch_all(sql+" ORDER BY name",(tid,))
    for row in rows:
        row["versions"]=request.state.store.fetch_all("SELECT id,version,form_schema_json,workflow_json,change_reason,state,created_by,created_at FROM request_type_versions WHERE tenant_id=? AND request_type_id=? ORDER BY version DESC",(tid,row["id"]))
        for version in row["versions"]:version["form_schema"]=loads(version.pop("form_schema_json"),{});version["workflow"]=loads(version.pop("workflow_json"),{})
    return {"items":rows}


@router.post("/request-types",status_code=201,operation_id="create_request_type")
def create_type(data:RequestTypeInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TYPE_ROLES);tid=tenant(user);workflow=_normalize_workflow_binding(request,tid,data.workflow);rid=uuid7();now=iso_now();result={"id":rid,"code":data.code,"name":data.name,"state":"draft","current_version":1}
    try:
        with request.state.store.transaction() as conn:
            conn.execute("INSERT INTO request_type_definitions(id,tenant_id,code,name,department,default_sla_hours,state,current_version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.code,data.name,data.department,data.default_sla_hours,"draft",1,user.id,now,now))
            conn.execute("INSERT INTO request_type_versions(id,tenant_id,request_type_id,version,form_schema_json,workflow_json,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,rid,1,dumps(data.form_schema),dumps(workflow),"draft",user.id,now))
            add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="request_type",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper() or "duplicate" in str(exc).lower():raise DomainError("REQUEST_TYPE_EXISTS","Já existe tipo de solicitação com este código.",409) from exc
        raise
    return result


@router.post("/request-types/{type_id}/versions",status_code=201,operation_id="create_request_type_version")
def version_type(type_id:str,data:RequestTypeVersionInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TYPE_ROLES);tid=tenant(user);workflow=_normalize_workflow_binding(request,tid,data.workflow);row=_type(request,tid,type_id);version=int(row["current_version"])+1;now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO request_type_versions(id,tenant_id,request_type_id,version,form_schema_json,workflow_json,change_reason,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,type_id,version,dumps(data.form_schema),dumps(workflow),data.reason,"draft",user.id,now))
        conn.execute("UPDATE request_type_definitions SET current_version=?,state='draft',updated_at=? WHERE tenant_id=? AND id=?",(version,now,tid,type_id))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="version",aggregate_type="request_type",aggregate_id=type_id,correlation_id=request.state.correlation_id,before={"version":row["current_version"]},after={"version":version},reason=data.reason)
    return {"id":type_id,"current_version":version,"state":"draft"}


@router.post("/request-types/{type_id}/publish",operation_id="publish_request_type")
def publish_type(type_id:str,data:RequestTypePublishInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,TYPE_ROLES);tid=tenant(user);row=_type(request,tid,type_id)
    if int(row["current_version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","O tipo foi alterado por outro usuário.",409)
    now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE request_type_versions SET state='superseded' WHERE tenant_id=? AND request_type_id=? AND state='published'",(tid,type_id));conn.execute("UPDATE request_type_versions SET state='published' WHERE tenant_id=? AND request_type_id=? AND version=?",(tid,type_id,data.expected_version));conn.execute("UPDATE request_type_definitions SET state='published',updated_at=? WHERE tenant_id=? AND id=?",(now,tid,type_id));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="request_type",aggregate_id=type_id,correlation_id=request.state.correlation_id,after={"version":data.expected_version,"state":"published"},reason=data.reason)
    return {"id":type_id,"state":"published","current_version":data.expected_version}


@router.get("/service-requests/{request_id}",operation_id="get_service_request")
def get_request(request_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid,row,agent=_request_access(request,user,request_id);row["form_data"]=loads(row.pop("form_data_json"),{});row["events"]=request.state.store.fetch_all("SELECT * FROM service_request_events WHERE tenant_id=? AND service_request_id=? ORDER BY occurred_at",(tid,request_id));sql="SELECT * FROM service_request_comments WHERE tenant_id=? AND service_request_id=?";params:list[Any]=[tid,request_id]
    if not agent:sql+=" AND visibility='requester'"
    row["comments"]=request.state.store.fetch_all(sql+" ORDER BY created_at",params);return row


@router.post("/service-requests/{request_id}/comments",status_code=201,operation_id="comment_service_request")
def comment_request(request_id:str,data:CommentInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid,row,agent=_request_access(request,user,request_id)
    if data.visibility=="internal" and not agent:raise DomainError("REQUEST_INTERNAL_COMMENT_FORBIDDEN","Somente atendentes podem criar comentário interno.",403)
    cid=uuid7();now=iso_now();request.state.store.execute("INSERT INTO service_request_comments(id,tenant_id,service_request_id,author_user_id,body,visibility,created_at) VALUES(?,?,?,?,?,?,?)",(cid,tid,request_id,user.id,data.body,data.visibility,now));return {"id":cid,"request_id":request_id,"visibility":data.visibility,"created_at":now}
