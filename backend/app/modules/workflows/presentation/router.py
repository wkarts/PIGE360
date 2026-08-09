from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from app.modules.operations.common import ADMIN_ROLES, dumps, loads, require, tenant
from app.modules.workflows.application.service import (
    create_tasks,
    load_definition_version,
    resolve_next_step,
    start_workflow_in_connection,
    user_can_act,
)
from app.modules.workflows.domain.models import WorkflowGraph, WorkflowStep
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["workflows"])
WORKFLOW_ADMIN_ROLES = ADMIN_ROLES | {"request_agent", "finance_manager", "hr_manager", "auditor", "support"}


class WorkflowDefinitionInput(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    name: str = Field(min_length=2, max_length=160)
    aggregate_type: str = Field(min_length=2, max_length=80)
    steps: list[WorkflowStep]


class WorkflowVersionInput(BaseModel):
    steps: list[WorkflowStep]
    reason: str = Field(min_length=3, max_length=1000)


class PublishInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class WorkflowStartInput(BaseModel):
    definition_id: str | None = None
    definition_code: str | None = None
    definition_version: int | None = Field(default=None, ge=1)
    aggregate_type: str = Field(min_length=2, max_length=80)
    aggregate_id: str = Field(min_length=1, max_length=160)
    context: dict[str, Any] = Field(default_factory=dict)


class TaskDecisionInput(BaseModel):
    expected_instance_version: int = Field(ge=1)
    decision: Literal["approve", "reject", "complete"]
    comment: str | None = Field(default=None, max_length=4000)




class TaskReassignInput(BaseModel):
    expected_task_version: int = Field(ge=1)
    assignee_roles: list[str] = Field(default_factory=list, max_length=20)
    assignee_user_id: str | None = None
    reason: str = Field(min_length=3, max_length=1000)

class CancelInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


def _definition(request: Request, tenant_id: str, definition_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM workflow_definitions WHERE tenant_id=? AND id=?", (tenant_id, definition_id))
    if not row:
        raise DomainError("WORKFLOW_DEFINITION_NOT_FOUND", "Workflow não localizado.", 404)
    return row


def _instance(request: Request, tenant_id: str, instance_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM workflow_instances WHERE tenant_id=? AND id=?", (tenant_id, instance_id))
    if not row:
        raise DomainError("WORKFLOW_INSTANCE_NOT_FOUND", "Instância de workflow não localizada.", 404)
    return row


def _serialize_definition(request: Request, tenant_id: str, row: dict[str, Any]) -> dict[str, Any]:
    versions = request.state.store.fetch_all("SELECT id,version,steps_json,state,change_reason,created_by,created_at FROM workflow_definition_versions WHERE tenant_id=? AND workflow_definition_id=? ORDER BY version DESC", (tenant_id, row["id"]))
    for version in versions:
        version["steps"] = loads(version.pop("steps_json"), [])
    row["versions"] = versions
    return row


@router.get("/workflows/definitions", operation_id="list_workflow_definitions")
def list_definitions(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user)
    return {"items": [_serialize_definition(request, tid, row) for row in request.state.store.fetch_all("SELECT * FROM workflow_definitions WHERE tenant_id=? ORDER BY name", (tid,))]}


@router.post("/workflows/definitions", status_code=201, operation_id="create_workflow_definition")
def create_definition(data: WorkflowDefinitionInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user)
    graph = WorkflowGraph(steps=data.steps)
    definition_id = uuid7(); now = iso_now()
    result = {"id": definition_id, "code": data.code, "name": data.name, "aggregate_type": data.aggregate_type, "state": "draft", "current_version": 1}
    try:
        with request.state.store.transaction() as conn:
            conn.execute("INSERT INTO workflow_definitions(id,tenant_id,code,name,aggregate_type,state,current_version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (definition_id, tid, data.code, data.name, data.aggregate_type, "draft", 1, user.id, now, now))
            conn.execute("INSERT INTO workflow_definition_versions(id,tenant_id,workflow_definition_id,version,steps_json,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)", (uuid7(), tid, definition_id, 1, dumps([s.model_dump() for s in graph.steps]), "draft", user.id, now))
            add_audit(conn, tenant_id=tid, actor_id=user.id, action="create", aggregate_type="workflow_definition", aggregate_id=definition_id, correlation_id=request.state.correlation_id, after=result)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper() or "duplicate" in str(exc).lower():
            raise DomainError("WORKFLOW_CODE_EXISTS", "Já existe workflow com este código.", 409) from exc
        raise
    return result


@router.post("/workflows/definitions/{definition_id}/versions", status_code=201, operation_id="create_workflow_definition_version")
def version_definition(definition_id: str, data: WorkflowVersionInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user); row = _definition(request, tid, definition_id); graph = WorkflowGraph(steps=data.steps); version = int(row["current_version"]) + 1; now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO workflow_definition_versions(id,tenant_id,workflow_definition_id,version,steps_json,state,change_reason,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (uuid7(), tid, definition_id, version, dumps([s.model_dump() for s in graph.steps]), "draft", data.reason, user.id, now))
        conn.execute("UPDATE workflow_definitions SET current_version=?,state='draft',updated_at=? WHERE tenant_id=? AND id=?", (version, now, tid, definition_id))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="version", aggregate_type="workflow_definition", aggregate_id=definition_id, correlation_id=request.state.correlation_id, before={"version": row["current_version"]}, after={"version": version}, reason=data.reason)
    return {"id": definition_id, "current_version": version, "state": "draft"}


@router.post("/workflows/definitions/{definition_id}/publish", operation_id="publish_workflow_definition")
def publish_definition(definition_id: str, data: PublishInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user); row = _definition(request, tid, definition_id)
    if int(row["current_version"]) != data.expected_version:
        raise DomainError("VERSION_CONFLICT", "A definição foi alterada por outro usuário.", 409)
    version = request.state.store.fetch_one("SELECT * FROM workflow_definition_versions WHERE tenant_id=? AND workflow_definition_id=? AND version=?", (tid, definition_id, data.expected_version))
    if not version:
        raise DomainError("WORKFLOW_VERSION_NOT_FOUND", "Versão do workflow não localizada.", 404)
    WorkflowGraph(steps=loads(version["steps_json"], []))
    now = iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE workflow_definition_versions SET state='superseded' WHERE tenant_id=? AND workflow_definition_id=? AND state='published'", (tid, definition_id))
        conn.execute("UPDATE workflow_definition_versions SET state='published' WHERE tenant_id=? AND workflow_definition_id=? AND version=?", (tid, definition_id, data.expected_version))
        conn.execute("UPDATE workflow_definitions SET state='published',updated_at=? WHERE tenant_id=? AND id=?", (now, tid, definition_id))
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="publish", aggregate_type="workflow_definition", aggregate_id=definition_id, correlation_id=request.state.correlation_id, after={"version": data.expected_version, "state": "published"}, reason=data.reason)
    return {"id": definition_id, "state": "published", "current_version": data.expected_version}


@router.get("/workflows/instances", operation_id="list_workflow_instances")
def list_instances(request: Request, state: str | None = None, aggregate_type: str | None = None, aggregate_id: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user); sql = "SELECT * FROM workflow_instances WHERE tenant_id=?"; params: list[Any] = [tid]
    if state: sql += " AND state=?"; params.append(state)
    if aggregate_type: sql += " AND aggregate_type=?"; params.append(aggregate_type)
    if aggregate_id: sql += " AND aggregate_id=?"; params.append(aggregate_id)
    rows = request.state.store.fetch_all(sql + " ORDER BY started_at DESC", params)
    for row in rows: row["context"] = loads(row.pop("context_json"), {})
    return {"items": rows}


@router.post("/workflows/instances", status_code=201, operation_id="start_workflow_instance")
def start_instance(data: WorkflowStartInput, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160), user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user); payload = data.model_dump(); scope = f"workflow:start:{tid}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, payload)
        if cached: return cached[1]
        result = start_workflow_in_connection(conn, tenant_id=tid, actor_user_id=user.id, correlation_id=request.state.correlation_id, aggregate_type=data.aggregate_type, aggregate_id=data.aggregate_id, context=data.context, definition_id=data.definition_id, definition_code=data.definition_code, definition_version=data.definition_version)
        save_idempotent(conn, scope, idempotency_key, payload, 201, result)
        add_audit(conn, tenant_id=tid, actor_id=user.id, action="start", aggregate_type="workflow_instance", aggregate_id=result["id"], correlation_id=request.state.correlation_id, after=result)
    return result


@router.get("/workflows/instances/{instance_id}", operation_id="get_workflow_instance")
def get_instance(instance_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid = tenant(user); row = _instance(request, tid, instance_id); row["context"] = loads(row.pop("context_json"), {})
    row["tasks"] = request.state.store.fetch_all("SELECT * FROM workflow_tasks WHERE tenant_id=? AND workflow_instance_id=? ORDER BY created_at", (tid, instance_id))
    for task in row["tasks"]: task["assignee_roles"] = loads(task.pop("assignee_roles_json"), [])
    row["events"] = request.state.store.fetch_all("SELECT * FROM workflow_events WHERE tenant_id=? AND workflow_instance_id=? ORDER BY occurred_at", (tid, instance_id))
    for event in row["events"]: event["payload"] = loads(event.pop("payload_json"), {})
    return row


@router.get("/workflows/tasks/me", operation_id="list_my_workflow_tasks")
def list_my_tasks(request: Request, state: Literal["open", "completed", "cancelled", "all"] = "open", user: CurrentUser = Depends(current_user)):
    tid = tenant(user); sql = "SELECT t.*,i.aggregate_type,i.aggregate_id,i.definition_version,i.version AS instance_version FROM workflow_tasks t JOIN workflow_instances i ON i.id=t.workflow_instance_id AND i.tenant_id=t.tenant_id WHERE t.tenant_id=?"; params: list[Any] = [tid]
    if state != "all": sql += " AND t.state=?"; params.append(state)
    rows = request.state.store.fetch_all(sql + " ORDER BY t.due_at IS NULL,t.due_at,t.created_at", params)
    result=[]
    for row in rows:
        roles=loads(row.pop("assignee_roles_json"),[])
        if row.get("assignee_user_id") == user.id or (not row.get("assignee_user_id") and set(roles).intersection(user.roles)):
            row["assignee_roles"] = roles
            row["sla_state"] = "breached" if row.get("sla_breached_at") else ("overdue" if row.get("due_at") and row["due_at"] < iso_now() else "on_time")
            result.append(row)
    return {"items": result}


@router.post("/workflows/tasks/{task_id}/reassign", operation_id="reassign_workflow_task")
def reassign_task(task_id: str, data: TaskReassignInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid=tenant(user);now=iso_now()
    if not data.assignee_user_id and not data.assignee_roles:
        raise DomainError("WORKFLOW_ASSIGNEE_REQUIRED","Informe usuário ou papel para reatribuição.",422)
    if data.assignee_user_id:
        target=request.state.store.fetch_one("SELECT id,active FROM users WHERE tenant_id=? AND id=?",(tid,data.assignee_user_id))
        if not target or not target["active"]:raise DomainError("WORKFLOW_ASSIGNEE_NOT_FOUND","Usuário destinatário não localizado.",404)
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM workflow_tasks WHERE tenant_id=? AND id=?",(tid,task_id)).fetchone();task=dict(row) if row else None
        if not task or task["state"]!="open":raise DomainError("WORKFLOW_TASK_NOT_FOUND","Tarefa aberta não localizada.",404)
        if int(task["version"])!=data.expected_task_version:raise DomainError("VERSION_CONFLICT","A tarefa foi alterada por outro usuário.",409)
        new_version=int(task["version"])+1
        conn.execute("UPDATE workflow_tasks SET assignee_roles_json=?,assignee_user_id=?,version=? WHERE tenant_id=? AND id=?",(dumps(data.assignee_roles),data.assignee_user_id,new_version,tid,task_id))
        conn.execute("INSERT INTO workflow_events(id,tenant_id,workflow_instance_id,event_type,from_state,to_state,from_step_key,to_step_key,actor_user_id,comment,payload_json,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,task["workflow_instance_id"],"task_reassigned","active","active",task["step_key"],task["step_key"],user.id,data.reason,dumps({"task_id":task_id,"assignee_roles":data.assignee_roles,"assignee_user_id":data.assignee_user_id,"task_version":new_version}),now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="reassign_task",aggregate_type="workflow_instance",aggregate_id=task["workflow_instance_id"],correlation_id=request.state.correlation_id,before={"assignee_roles":loads(task.get("assignee_roles_json"),[]),"assignee_user_id":task.get("assignee_user_id")},after={"assignee_roles":data.assignee_roles,"assignee_user_id":data.assignee_user_id,"task_version":new_version},reason=data.reason)
    return {"id":task_id,"state":"open","assignee_roles":data.assignee_roles,"assignee_user_id":data.assignee_user_id,"version":new_version}


@router.post("/workflows/tasks/{task_id}/complete", operation_id="complete_workflow_task")
def complete_task(task_id: str, data: TaskDecisionInput, request: Request, user: CurrentUser = Depends(current_user)):
    tid = tenant(user); now = iso_now()
    with request.state.store.transaction() as conn:
        task_row = conn.execute("SELECT * FROM workflow_tasks WHERE tenant_id=? AND id=?", (tid, task_id)).fetchone()
        task = dict(task_row) if task_row else None
        if not task or task["state"] != "open": raise DomainError("WORKFLOW_TASK_NOT_FOUND", "Tarefa aberta não localizada.", 404)
        if not user_can_act(task, user.id, user.roles): raise DomainError("WORKFLOW_TASK_FORBIDDEN", "Esta tarefa não está atribuída ao usuário.", 403)
        instance_row = conn.execute("SELECT * FROM workflow_instances WHERE tenant_id=? AND id=?", (tid, task["workflow_instance_id"])).fetchone(); instance = dict(instance_row) if instance_row else None
        if not instance or instance["state"] != "active": raise DomainError("WORKFLOW_INSTANCE_NOT_ACTIVE", "A instância não está ativa.", 409)
        if int(instance["version"]) != data.expected_instance_version: raise DomainError("VERSION_CONFLICT", "A instância foi alterada por outro usuário.", 409)
        version_row = conn.execute("SELECT * FROM workflow_definition_versions WHERE tenant_id=? AND workflow_definition_id=? AND version=?", (tid, instance["workflow_definition_id"], instance["definition_version"])).fetchone()
        if not version_row: raise DomainError("WORKFLOW_VERSION_NOT_FOUND", "Versão congelada do workflow não localizada.", 409)
        graph = WorkflowGraph(steps=loads(dict(version_row)["steps_json"], [])); step = graph.step(task["step_key"])
        # Valida a decisão antes de persistir.
        resolve_next_step(graph, task["step_key"], data.decision)
        conn.execute("UPDATE workflow_tasks SET state='completed',decision=?,comment=?,completed_by=?,completed_at=?,version=version+1 WHERE tenant_id=? AND id=? AND state='open'", (data.decision, data.comment, user.id, now, tid, task_id))
        next_version = int(instance["version"]) + 1; next_task_ids: list[str] = []
        pending_siblings = conn.execute("SELECT id FROM workflow_tasks WHERE tenant_id=? AND workflow_instance_id=? AND step_key=? AND state='open'", (tid, instance["id"], task["step_key"])).fetchall()
        if step.approval_mode == "all" and data.decision != "reject" and pending_siblings:
            next_state = "active"; next_step = step
            conn.execute("UPDATE workflow_instances SET version=? WHERE tenant_id=? AND id=?", (next_version, tid, instance["id"]))
        else:
            if pending_siblings:
                conn.execute("UPDATE workflow_tasks SET state='cancelled',version=version+1 WHERE tenant_id=? AND workflow_instance_id=? AND step_key=? AND state='open'", (tid, instance["id"], task["step_key"]))
            next_state, next_step = resolve_next_step(graph, task["step_key"], data.decision)
            if next_state == "active" and next_step:
                next_task_ids = create_tasks(conn, tenant_id=tid, instance_id=instance["id"], step=next_step, now=datetime.now(UTC))
                conn.execute("UPDATE workflow_instances SET current_step_key=?,version=? WHERE tenant_id=? AND id=?", (next_step.key, next_version, tid, instance["id"]))
            else:
                conn.execute("UPDATE workflow_instances SET state=?,current_step_key=NULL,completed_at=?,version=? WHERE tenant_id=? AND id=?", (next_state, now, next_version, tid, instance["id"]))
        conn.execute("INSERT INTO workflow_events(id,tenant_id,workflow_instance_id,event_type,from_state,to_state,from_step_key,to_step_key,actor_user_id,decision,comment,payload_json,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (uuid7(), tid, instance["id"], "task_completed", "active", next_state, task["step_key"], next_step.key if next_step else None, user.id, data.decision, data.comment, dumps({"task_id": task_id, "next_task_id": next_task_ids[0] if next_task_ids else None, "next_task_ids": next_task_ids}), now))
        payload={"instance_id":instance["id"],"task_id":task_id,"decision":data.decision,"state":next_state,"current_step_key":next_step.key if next_step else None,"version":next_version}
        add_outbox(conn,tenant_id=tid,event_type="WorkflowTaskCompleted",aggregate_type="workflow_instance",aggregate_id=instance["id"],payload=payload,correlation_id=request.state.correlation_id)
        if next_state in {"completed","rejected"}:
            add_outbox(conn,tenant_id=tid,event_type="WorkflowCompleted" if next_state=="completed" else "WorkflowRejected",aggregate_type="workflow_instance",aggregate_id=instance["id"],payload=payload,correlation_id=request.state.correlation_id)
            if instance["aggregate_type"] == "service_request":
                request_state = "resolved" if next_state == "completed" else "cancelled"
                existing = conn.execute("SELECT state,version FROM service_requests WHERE tenant_id=? AND id=?",(tid,instance["aggregate_id"])).fetchone()
                if existing:
                    old=dict(existing);conn.execute("UPDATE service_requests SET state=?,version=version+1,workflow_instance_id=?,updated_at=? WHERE tenant_id=? AND id=?",(request_state,instance["id"],now,tid,instance["aggregate_id"]));conn.execute("INSERT INTO service_request_events(id,tenant_id,service_request_id,event_type,from_state,to_state,reason,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,instance["aggregate_id"],"workflow_transition",old["state"],request_state,data.comment or data.decision,user.id,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="complete_task",aggregate_type="workflow_instance",aggregate_id=instance["id"],correlation_id=request.state.correlation_id,before={"state":"active","step":task["step_key"],"version":instance["version"]},after=payload,reason=data.comment)
    return payload


@router.post("/workflows/instances/{instance_id}/cancel", operation_id="cancel_workflow_instance")
def cancel_instance(instance_id: str, data: CancelInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, WORKFLOW_ADMIN_ROLES)
    tid=tenant(user);row=_instance(request,tid,instance_id)
    if row["state"]!="active": raise DomainError("WORKFLOW_INSTANCE_NOT_ACTIVE","A instância não está ativa.",409)
    if int(row["version"])!=data.expected_version: raise DomainError("VERSION_CONFLICT","A instância foi alterada por outro usuário.",409)
    now=iso_now();new_version=int(row["version"])+1
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE workflow_tasks SET state='cancelled',version=version+1 WHERE tenant_id=? AND workflow_instance_id=? AND state='open'",(tid,instance_id));conn.execute("UPDATE workflow_instances SET state='cancelled',current_step_key=NULL,cancelled_at=?,version=? WHERE tenant_id=? AND id=?",(now,new_version,tid,instance_id));conn.execute("INSERT INTO workflow_events(id,tenant_id,workflow_instance_id,event_type,from_state,to_state,from_step_key,actor_user_id,comment,payload_json,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,instance_id,"cancelled","active","cancelled",row["current_step_key"],user.id,data.reason,"{}",now))
        if row["aggregate_type"]=="service_request":
            existing=conn.execute("SELECT state FROM service_requests WHERE tenant_id=? AND id=?",(tid,row["aggregate_id"])).fetchone()
            if existing:
                previous=dict(existing)["state"];conn.execute("UPDATE service_requests SET state='cancelled',version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(now,tid,row["aggregate_id"]));conn.execute("INSERT INTO service_request_events(id,tenant_id,service_request_id,event_type,from_state,to_state,reason,actor_user_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,row["aggregate_id"],"workflow_cancelled",previous,"cancelled",data.reason,user.id,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="cancel",aggregate_type="workflow_instance",aggregate_id=instance_id,correlation_id=request.state.correlation_id,before={"state":"active","version":row["version"]},after={"state":"cancelled","version":new_version},reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="WorkflowCancelled",aggregate_type="workflow_instance",aggregate_id=instance_id,payload={"state":"cancelled","reason":data.reason},correlation_id=request.state.correlation_id)
    return {"id":instance_id,"state":"cancelled","version":new_version}
