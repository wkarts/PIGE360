from __future__ import annotations


def post(env, path, payload, headers=None, expected=201):
    response = env.client.post(path, headers=headers or env.alpha_headers(), json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def user_headers(env, email, roles):
    _, token = env.create_alpha_user(email, roles)
    return env.headers("admin.alpha.school.local", token)


def workflow_steps(second_role="finance_manager"):
    return [
        {
            "key": "coordination",
            "name": "Aprovação da coordenação",
            "type": "approval",
            "assignee_roles": ["academic_coordinator"],
            "due_hours": 24,
            "approve_to": "finance",
            "reject_to": "rejected",
        },
        {
            "key": "finance",
            "name": "Aprovação financeira",
            "type": "approval",
            "assignee_roles": [second_role],
            "due_hours": 48,
            "approve_to": "completed",
            "reject_to": "rejected",
        },
    ]


def create_published(env, code="request.scholarship"):
    definition = post(env, "/api/v1/workflows/definitions", {
        "code": code,
        "name": "Aprovação de bolsa",
        "aggregate_type": "service_request",
        "steps": workflow_steps(),
    })
    published = post(env, f"/api/v1/workflows/definitions/{definition['id']}/publish", {
        "expected_version": 1,
        "reason": "Fluxo institucional aprovado",
    }, expected=200)
    assert published["state"] == "published"
    return definition


def test_versioned_human_workflow_roles_concurrency_and_tenant_isolation(local_env):
    definition = create_published(local_env)
    coord = user_headers(local_env, "coord@alpha.example.com", ["academic_coordinator"])
    finance = user_headers(local_env, "finance@alpha.example.com", ["finance_manager"])
    outsider = user_headers(local_env, "teacher.workflow@alpha.example.com", ["teacher"])

    payload = {
        "definition_id": definition["id"],
        "aggregate_type": "service_request",
        "aggregate_id": "REQ-TEST-001",
        "context": {"amount": "1500.00"},
    }
    headers = local_env.alpha_headers(**{"Idempotency-Key": "workflow-start-001"})
    instance = post(local_env, "/api/v1/workflows/instances", payload, headers)
    replay = post(local_env, "/api/v1/workflows/instances", payload, headers)
    assert replay == instance
    assert instance["definition_version"] == 1 and instance["current_step_key"] == "coordination"

    coord_tasks = local_env.client.get("/api/v1/workflows/tasks/me", headers=coord)
    finance_tasks = local_env.client.get("/api/v1/workflows/tasks/me", headers=finance)
    outsider_tasks = local_env.client.get("/api/v1/workflows/tasks/me", headers=outsider)
    assert coord_tasks.status_code == 200 and len(coord_tasks.json()["items"]) == 1
    assert finance_tasks.status_code == 200 and finance_tasks.json()["items"] == []
    assert outsider_tasks.status_code == 200 and outsider_tasks.json()["items"] == []

    task1 = coord_tasks.json()["items"][0]
    forbidden = local_env.client.post(
        f"/api/v1/workflows/tasks/{task1['id']}/complete",
        headers=finance,
        json={"expected_instance_version": 1, "decision": "approve", "comment": "Tentativa indevida"},
    )
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "WORKFLOW_TASK_FORBIDDEN"

    first = post(local_env, f"/api/v1/workflows/tasks/{task1['id']}/complete", {
        "expected_instance_version": 1,
        "decision": "approve",
        "comment": "Coordenação aprovou",
    }, coord, 200)
    assert first["state"] == "active" and first["current_step_key"] == "finance" and first["version"] == 2

    stale = local_env.client.post(
        f"/api/v1/workflows/tasks/{local_env.client.get('/api/v1/workflows/tasks/me', headers=finance).json()['items'][0]['id']}/complete",
        headers=finance,
        json={"expected_instance_version": 1, "decision": "approve", "comment": "Versão antiga"},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"

    # Publicar a versão 2 não altera a versão congelada da instância já iniciada.
    version2 = post(local_env, f"/api/v1/workflows/definitions/{definition['id']}/versions", {
        "steps": workflow_steps("tenant_owner"),
        "reason": "Nova política para futuras instâncias",
    })
    assert version2["current_version"] == 2
    post(local_env, f"/api/v1/workflows/definitions/{definition['id']}/publish", {
        "expected_version": 2,
        "reason": "Nova versão publicada",
    }, expected=200)

    finance_task = local_env.client.get("/api/v1/workflows/tasks/me", headers=finance).json()["items"][0]
    completed = post(local_env, f"/api/v1/workflows/tasks/{finance_task['id']}/complete", {
        "expected_instance_version": 2,
        "decision": "approve",
        "comment": "Financeiro aprovou",
    }, finance, 200)
    assert completed["state"] == "completed" and completed["version"] == 3

    detail = local_env.client.get(f"/api/v1/workflows/instances/{instance['id']}", headers=local_env.alpha_headers())
    assert detail.status_code == 200
    assert detail.json()["definition_version"] == 1
    assert detail.json()["state"] == "completed"
    assert len(detail.json()["events"]) == 3

    beta = local_env.client.get(f"/api/v1/workflows/instances/{instance['id']}", headers=local_env.beta_headers())
    assert beta.status_code == 404


def test_request_type_starts_frozen_workflow_and_completion_resolves_request(local_env):
    definition = create_published(local_env, "request.document.approval")
    secretary = user_headers(local_env, "secretary.workflow@alpha.example.com", ["academic_coordinator"])
    finance = user_headers(local_env, "finance2@alpha.example.com", ["finance_manager"])

    kind = post(local_env, "/api/v1/request-types", {
        "code": "document.with-approval",
        "name": "Documento com aprovação",
        "department": "Secretaria",
        "default_sla_hours": 24,
        "form_schema": {"fields": [{"name": "document", "type": "string", "required": True}]},
        "workflow": {"definition_id": definition["id"]},
    })
    post(local_env, f"/api/v1/request-types/{kind['id']}/publish", {
        "expected_version": 1,
        "reason": "Fluxo do protocolo aprovado",
    }, expected=200)

    person = post(local_env, "/api/v1/people", {
        "full_name": "Solicitante Workflow",
        "cpf": "44444444444",
        "email": "request.workflow@alpha.example.com",
    }, local_env.alpha_headers(**{"Idempotency-Key": "person-workflow-request"}))
    _, token = local_env.create_alpha_user("request.workflow@alpha.example.com", ["guardian"], person_id=person["id"])
    requester = local_env.headers("admin.alpha.school.local", token)

    service_request = post(local_env, "/api/v1/service-requests", {
        "request_type": "document.with-approval",
        "subject": "Emitir declaração",
        "form_data": {"document": "Declaração de matrícula"},
    }, requester)
    assert service_request["workflow_instance_id"]

    detail = local_env.client.get(f"/api/v1/service-requests/{service_request['id']}", headers=requester)
    assert detail.status_code == 200 and detail.json()["workflow_instance_id"] == service_request["workflow_instance_id"]

    task1 = local_env.client.get("/api/v1/workflows/tasks/me", headers=secretary).json()["items"][0]
    post(local_env, f"/api/v1/workflows/tasks/{task1['id']}/complete", {
        "expected_instance_version": 1,
        "decision": "approve",
        "comment": "Documentação conferida",
    }, secretary, 200)
    task2 = local_env.client.get("/api/v1/workflows/tasks/me", headers=finance).json()["items"][0]
    post(local_env, f"/api/v1/workflows/tasks/{task2['id']}/complete", {
        "expected_instance_version": 2,
        "decision": "approve",
        "comment": "Sem pendência financeira",
    }, finance, 200)

    final = local_env.client.get(f"/api/v1/service-requests/{service_request['id']}", headers=requester).json()
    assert final["state"] == "resolved"
    assert final["events"][-1]["event_type"] == "workflow_transition"


def test_workflow_reassignment_and_sla_breach_once(local_env):
    from app.worker import mark_overdue_workflow_tasks

    definition = create_published(local_env, "request.sla")
    coord = user_headers(local_env, "coord.sla@alpha.example.com", ["academic_coordinator"])
    owner = local_env.alpha_headers()
    instance = post(
        local_env,
        "/api/v1/workflows/instances",
        {"definition_id": definition["id"], "aggregate_type": "service_request", "aggregate_id": "REQ-SLA-001", "context": {}},
        local_env.alpha_headers(**{"Idempotency-Key": "workflow-sla-start"}),
    )
    task = local_env.client.get("/api/v1/workflows/tasks/me", headers=coord).json()["items"][0]

    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    store.execute("UPDATE workflow_tasks SET due_at='2000-01-01T00:00:00+00:00' WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], task["id"]))
    first = mark_overdue_workflow_tasks(router=local_env.client.app.state.data_router)
    second = mark_overdue_workflow_tasks(router=local_env.client.app.state.data_router)
    assert first["breached"] == 1 and second["breached"] == 0
    persisted = store.fetch_one("SELECT sla_breached_at,escalation_count FROM workflow_tasks WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], task["id"]))
    assert persisted["sla_breached_at"] and persisted["escalation_count"] == 1
    events = store.fetch_all("SELECT event_type FROM workflow_events WHERE tenant_id=? AND workflow_instance_id=? ORDER BY occurred_at", (local_env.alpha_tenant["id"], instance["id"]))
    assert [e["event_type"] for e in events].count("sla_breached") == 1

    reassigned = post(local_env, f"/api/v1/workflows/tasks/{task['id']}/reassign", {
        "expected_task_version": 2,
        "assignee_roles": ["tenant_owner"],
        "reason": "Escalonamento após vencimento de SLA",
    }, owner, 200)
    assert reassigned["version"] == 3 and reassigned["assignee_roles"] == ["tenant_owner"]
    assert local_env.client.get("/api/v1/workflows/tasks/me", headers=coord).json()["items"] == []
    owner_task = local_env.client.get("/api/v1/workflows/tasks/me", headers=owner).json()["items"][0]
    assert owner_task["id"] == task["id"] and owner_task["sla_state"] == "breached"


def test_parallel_all_approval_requires_every_role(local_env):
    definition = post(local_env, "/api/v1/workflows/definitions", {
        "code": "request.parallel",
        "name": "Aprovação paralela",
        "aggregate_type": "service_request",
        "steps": [{
            "key": "joint",
            "name": "Aprovação conjunta",
            "type": "approval",
            "approval_mode": "all",
            "assignee_roles": ["academic_coordinator", "finance_manager"],
            "due_hours": 24,
            "approve_to": "completed",
            "reject_to": "rejected",
        }],
    })
    post(local_env, f"/api/v1/workflows/definitions/{definition['id']}/publish", {"expected_version":1,"reason":"Fluxo paralelo aprovado"}, expected=200)
    coord = user_headers(local_env, "coord.parallel@alpha.example.com", ["academic_coordinator"])
    finance = user_headers(local_env, "finance.parallel@alpha.example.com", ["finance_manager"])
    instance = post(local_env, "/api/v1/workflows/instances", {
        "definition_id":definition["id"],"aggregate_type":"service_request","aggregate_id":"REQ-PAR-001","context":{}
    }, local_env.alpha_headers(**{"Idempotency-Key":"workflow-parallel-start"}))
    assert len(instance["task_ids"]) == 2
    coord_task = local_env.client.get("/api/v1/workflows/tasks/me", headers=coord).json()["items"][0]
    finance_task = local_env.client.get("/api/v1/workflows/tasks/me", headers=finance).json()["items"][0]
    first = post(local_env, f"/api/v1/workflows/tasks/{coord_task['id']}/complete", {
        "expected_instance_version":1,"decision":"approve","comment":"Coordenação de acordo"
    }, coord, 200)
    assert first["state"] == "active" and first["current_step_key"] == "joint" and first["version"] == 2
    assert local_env.client.get("/api/v1/workflows/tasks/me", headers=coord).json()["items"] == []
    remaining = local_env.client.get("/api/v1/workflows/tasks/me", headers=finance).json()["items"]
    assert len(remaining) == 1 and remaining[0]["id"] == finance_task["id"]
    final = post(local_env, f"/api/v1/workflows/tasks/{finance_task['id']}/complete", {
        "expected_instance_version":2,"decision":"approve","comment":"Financeiro de acordo"
    }, finance, 200)
    assert final["state"] == "completed" and final["version"] == 3
