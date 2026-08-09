from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.operations.common import dumps, loads
from app.modules.workflows.domain.models import TERMINALS, WorkflowGraph, WorkflowStep
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_outbox
from app.shared.presentation.errors import DomainError


def _as_row(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    return dict(row) if not isinstance(row, dict) else row


def load_definition_version(conn: Any, tenant_id: str, *, definition_id: str | None = None, definition_code: str | None = None, version_number: int | None = None, published_only: bool = True) -> tuple[dict[str, Any], dict[str, Any], WorkflowGraph]:
    if not definition_id and not definition_code:
        raise DomainError("WORKFLOW_DEFINITION_REQUIRED", "Informe a definição do workflow.", 422)
    if definition_id:
        definition = _as_row(conn.execute("SELECT * FROM workflow_definitions WHERE tenant_id=? AND id=?", (tenant_id, definition_id)).fetchone())
    else:
        definition = _as_row(conn.execute("SELECT * FROM workflow_definitions WHERE tenant_id=? AND code=?", (tenant_id, definition_code)).fetchone())
    if not definition or (published_only and definition["state"] != "published"):
        raise DomainError("WORKFLOW_DEFINITION_NOT_FOUND", "Workflow publicado não localizado.", 404)
    resolved_version = int(version_number or definition["current_version"])
    version = _as_row(conn.execute(
        "SELECT * FROM workflow_definition_versions WHERE tenant_id=? AND workflow_definition_id=? AND version=?",
        (tenant_id, definition["id"], resolved_version),
    ).fetchone())
    if not version:
        raise DomainError("WORKFLOW_VERSION_NOT_FOUND", "Versão do workflow não localizada.", 404)
    if published_only and version["state"] != "published":
        raise DomainError("WORKFLOW_VERSION_NOT_PUBLISHED", "A versão atual do workflow não está publicada.", 409)
    if version_number is not None and version["state"] not in {"published", "superseded"}:
        raise DomainError("WORKFLOW_VERSION_NOT_AVAILABLE", "A versão congelada do workflow nunca foi publicada.", 409)
    graph = WorkflowGraph(steps=loads(version["steps_json"], []))
    return definition, version, graph


def _task_due_at(step: WorkflowStep, now: datetime) -> str | None:
    return (now + timedelta(hours=step.due_hours)).isoformat() if step.due_hours else None


def create_tasks(conn: Any, *, tenant_id: str, instance_id: str, step: WorkflowStep, now: datetime) -> list[str]:
    assignments: list[tuple[list[str], str | None]] = []
    if step.approval_mode == "all":
        assignments.extend([([role], None) for role in step.assignee_roles])
        if step.assignee_user_id:
            assignments.append(([], step.assignee_user_id))
    else:
        assignments.append((list(step.assignee_roles), step.assignee_user_id))
    task_ids: list[str] = []
    for roles, user_id in assignments:
        task_id = uuid7(); task_ids.append(task_id)
        conn.execute(
            "INSERT INTO workflow_tasks(id,tenant_id,workflow_instance_id,step_key,step_name,task_type,assignee_roles_json,assignee_user_id,state,due_at,version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, tenant_id, instance_id, step.key, step.name, step.type, dumps(roles), user_id, "open", _task_due_at(step, now), 1, now.isoformat()),
        )
    return task_ids


def create_task(conn: Any, *, tenant_id: str, instance_id: str, step: WorkflowStep, now: datetime) -> str:
    """Compatibilidade interna: retorna a primeira tarefa criada."""
    return create_tasks(conn, tenant_id=tenant_id, instance_id=instance_id, step=step, now=now)[0]


def start_workflow_in_connection(
    conn: Any,
    *,
    tenant_id: str,
    actor_user_id: str,
    correlation_id: str,
    aggregate_type: str,
    aggregate_id: str,
    context: dict[str, Any] | None = None,
    definition_id: str | None = None,
    definition_code: str | None = None,
    definition_version: int | None = None,
) -> dict[str, Any]:
    definition, version, graph = load_definition_version(conn, tenant_id, definition_id=definition_id, definition_code=definition_code, version_number=definition_version, published_only=definition_version is None)
    now = datetime.now(UTC)
    instance_id = uuid7()
    first = graph.steps[0]
    conn.execute(
        "INSERT INTO workflow_instances(id,tenant_id,workflow_definition_id,definition_version,aggregate_type,aggregate_id,state,current_step_key,context_json,started_by,started_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (instance_id, tenant_id, definition["id"], version["version"], aggregate_type, aggregate_id, "active", first.key, dumps(context or {}), actor_user_id, now.isoformat(), 1),
    )
    task_ids = create_tasks(conn, tenant_id=tenant_id, instance_id=instance_id, step=first, now=now)
    task_id = task_ids[0]
    conn.execute(
        "INSERT INTO workflow_events(id,tenant_id,workflow_instance_id,event_type,to_state,to_step_key,actor_user_id,payload_json,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (uuid7(), tenant_id, instance_id, "started", "active", first.key, actor_user_id, dumps({"task_id": task_id, "task_ids": task_ids, "definition_version": version["version"]}), now.isoformat()),
    )
    add_outbox(conn, tenant_id=tenant_id, event_type="WorkflowStarted", aggregate_type="workflow_instance", aggregate_id=instance_id, payload={"aggregate_type": aggregate_type, "aggregate_id": aggregate_id, "definition_id": definition["id"], "definition_version": int(version["version"]), "current_step_key": first.key}, correlation_id=correlation_id)
    return {"id": instance_id, "definition_id": definition["id"], "definition_version": int(version["version"]), "state": "active", "current_step_key": first.key, "task_id": task_id, "task_ids": task_ids, "version": 1}


def resolve_next_step(graph: WorkflowGraph, current_step_key: str, decision: str) -> tuple[str, WorkflowStep | None]:
    step = graph.step(current_step_key)
    if step.type == "task" and decision not in {"complete", "approve"}:
        raise DomainError("WORKFLOW_DECISION_INVALID", "Tarefa operacional aceita somente conclusão.", 422)
    if step.type == "approval" and decision not in {"approve", "reject"}:
        raise DomainError("WORKFLOW_DECISION_INVALID", "Etapa de aprovação exige approve ou reject.", 422)
    target = step.reject_to if decision == "reject" else step.approve_to
    if target in TERMINALS:
        return target, None
    return "active", graph.step(target)


def user_can_act(task: dict[str, Any], user_id: str, roles: tuple[str, ...] | list[str]) -> bool:
    if task.get("assignee_user_id"):
        return task["assignee_user_id"] == user_id
    required = set(loads(task.get("assignee_roles_json"), []))
    return bool(required.intersection(roles))
