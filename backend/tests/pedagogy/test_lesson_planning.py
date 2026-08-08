from __future__ import annotations

from conftest import ALPHA_HOST


def _post(local_env, path: str, payload: dict, *, key: str | None = None, expected: int = 201) -> dict:
    headers = local_env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = local_env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def _planning_context(local_env, suffix: str = "1", *, assigned: bool = True) -> dict:
    inst = _post(local_env, "/api/v1/institutions", {"legal_name": f"Escola Planejamento {suffix} Ltda", "trade_name": f"Escola Planejamento {suffix}", "education_system": "private"})
    unit = _post(local_env, "/api/v1/units", {"institution_id": inst["id"], "code": f"UP{suffix}", "name": f"Unidade Planejamento {suffix}", "timezone": "America/Bahia", "address": {}})
    year = _post(local_env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": "2026", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    period = _post(local_env, "/api/v1/academic-periods", {"academic_year_id": year["id"], "name": "3º Bimestre", "period_type": "bimester", "sequence": 3, "starts_on": "2026-07-20", "ends_on": "2026-09-30"})
    program = _post(local_env, "/api/v1/programs", {"institution_id": inst["id"], "code": f"EFP{suffix}", "name": "Ensino Fundamental II", "education_level": "fundamental"})
    curriculum = _post(local_env, "/api/v1/curricula", {"program_id": program["id"], "code": f"CURRP-{suffix}", "name": f"Currículo Planejamento {suffix}", "effective_from": "2026-01-01"})
    component = _post(local_env, "/api/v1/curriculum-components", {"curriculum_id": curriculum["id"], "code": f"MATP{suffix}", "name": "Matemática", "workload_hours": 160})
    group = _post(local_env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": year["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": f"7P-{suffix}", "name": f"7º Planejamento {suffix}", "capacity": 30})
    person = _post(local_env, "/api/v1/people", {"full_name": f"Professor Planejamento {suffix}", "email": f"prof.plan.{suffix}@example.com"}, key=f"plan-person-{suffix}")
    employee = _post(local_env, "/api/v1/employees", {"person_id": person["id"], "employee_number": f"PLAN-{suffix}", "department": "Pedagógico", "position": "Professor", "admission_date": "2026-01-05"})
    teacher, token = local_env.create_alpha_user(f"teacher.plan.{suffix}@alpha.example.com", ["teacher"], person_id=person["id"] )
    assignment = None
    if assigned:
        assignment = _post(local_env, "/api/v1/teacher-assignments", {"employee_id": employee["id"], "class_group_id": group["id"], "component_id": component["id"], "starts_on": "2026-01-20", "role": "teacher"})
    return {"institution": inst, "unit": unit, "year": year, "period": period, "program": program, "curriculum": curriculum, "component": component, "group": group, "person": person, "employee": employee, "teacher": teacher, "token": token, "assignment": assignment}


def _plan_body(context: dict) -> dict:
    teacher_id = context["teacher"]["id"]
    return {
        "institution_id": context["institution"]["id"],
        "unit_id": context["unit"]["id"],
        "academic_period_id": context["period"]["id"],
        "program_id": context["program"]["id"],
        "curriculum_id": context["curriculum"]["id"],
        "class_group_id": context["group"]["id"],
        "component_id": context["component"]["id"],
        "teacher_ids": [teacher_id],
        "plan_type": "weekly",
        "title": "Sequência de frações e proporcionalidade",
        "start_date": "2026-08-10",
        "end_date": "2026-08-14",
        "duration_minutes": 200,
        "workload_hours": 3.33,
        "objectives": ["Resolver situações-problema com frações"],
        "skills": ["EF07MA08"],
        "competencies": ["Raciocínio lógico"],
        "curriculum_links": [{"catalog": "BNCC", "code": "EF07MA08", "version": "2026"}],
        "content": ["Frações equivalentes", "Proporcionalidade"],
        "methodologies": ["Sala de aula invertida", "Resolução colaborativa"],
        "resources": [{"type": "library_book", "id": "book-1"}],
        "accommodations": [{"type": "large_print", "student_scope": "restricted"}],
        "assessments": [{"type": "formative", "weight": 1}],
        "homework": [{"description": "Lista 3"}],
        "references": ["Currículo institucional v3"],
        "approval_required": True,
    }


def test_complete_planning_flow_with_versions_approval_and_execution(local_env):
    context = _planning_context(local_env, "1")
    teacher = context["teacher"]
    teacher_token = context["token"]
    teacher_headers = local_env.headers(ALPHA_HOST, teacher_token, **{"Idempotency-Key": "plan-create-0001"})
    created = local_env.client.post("/api/v1/teaching-plans", headers=teacher_headers, json=_plan_body(context))
    assert created.status_code == 201, created.text
    plan = created.json()

    patched = local_env.client.patch(
        f"/api/v1/teaching-plans/{plan['id']}",
        headers=local_env.headers(ALPHA_HOST, teacher_token),
        json={
            "expected_version": plan["current_version"],
            "changes": {"notes": "Adaptação pedagógica revisada"},
            "reason": "Ajuste após reunião pedagógica",
        },
    )
    assert patched.status_code == 200, patched.text

    stale = local_env.client.patch(
        f"/api/v1/teaching-plans/{plan['id']}",
        headers=local_env.headers(ALPHA_HOST, teacher_token),
        json={"expected_version": 1, "changes": {"notes": "stale"}, "reason": "Conflito proposital"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    submitted = local_env.client.post(
        f"/api/v1/teaching-plans/{plan['id']}/submit",
        headers=local_env.headers(ALPHA_HOST, teacher_token),
        json={"expected_version": patched.json()["current_version"], "reason": "Plano pronto para revisão"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted_for_review"

    approved = local_env.client.post(
        f"/api/v1/teaching-plans/{plan['id']}/approve",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": submitted.json()["current_version"],
            "reason": "Alinhamento curricular validado",
            "comments": "Aprovado pela coordenação",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    scheduled = local_env.client.post(
        f"/api/v1/teaching-plans/{plan['id']}/schedule",
        headers=local_env.alpha_headers(),
        json={
            "expected_version": approved.json()["current_version"],
            "sessions": [
                {
                    "scheduled_start": "2026-08-10T10:00:00-03:00",
                    "scheduled_end": "2026-08-10T11:40:00-03:00",
                    "modality": "regular",
                    "room_id": "room-12",
                    "teacher_ids": [teacher["id"]],
                    "title": "Frações equivalentes",
                }
            ],
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    lesson = scheduled.json()["lessons"][0]

    started = local_env.client.post(
        f"/api/v1/lesson-plans/{lesson['id']}/start",
        headers=local_env.headers(ALPHA_HOST, teacher_token),
        json={"expected_version": 1, "reason": "Aula iniciada no horário"},
    )
    assert started.status_code == 200
    completed = local_env.client.post(
        f"/api/v1/lesson-plans/{lesson['id']}/complete",
        headers=local_env.headers(ALPHA_HOST, teacher_token),
        json={
            "expected_version": started.json()["current_version"],
            "completion_percentage": 65,
            "delivered_content": ["Frações equivalentes"],
            "pending_content": ["Proporcionalidade"],
            "additional_content": ["Jogo pedagógico"],
            "notes": "Conteúdo pendente reagendável",
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "partially_executed"

    execution = local_env.client.get(
        f"/api/v1/lesson-plans/{lesson['id']}/execution",
        headers=local_env.headers(ALPHA_HOST, teacher_token),
    )
    assert execution.status_code == 200
    assert execution.json()["completion_percentage"] == 65

    coverage = local_env.client.get(
        f"/api/v1/teaching-plans/reports/coverage?class_group_id={context['group']['id']}&component_id={context['component']['id']}",
        headers=local_env.alpha_headers(),
    )
    assert coverage.status_code == 200
    assert coverage.json()["planned_lessons"] == 1
    assert coverage.json()["partially_executed_lessons"] == 1
    assert coverage.json()["coverage_percentage"] == 50.0

    details = local_env.client.get(f"/api/v1/teaching-plans/{plan['id']}", headers=local_env.alpha_headers())
    assert details.status_code == 200
    assert len(details.json()["versions"]) >= 4
    assert details.json()["approvals"][-1]["decision"] == "approved"


def test_teacher_cannot_access_or_duplicate_plan_from_another_assignment(local_env):
    owner = _planning_context(local_env, "A")
    outsider = _planning_context(local_env, "B")
    created = local_env.client.post(
        "/api/v1/teaching-plans",
        headers=local_env.headers(ALPHA_HOST, owner["token"], **{"Idempotency-Key": "plan-owner-a-0001"}),
        json=_plan_body(owner),
    )
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    outsider_headers = local_env.headers(ALPHA_HOST, outsider["token"])
    denied_get = local_env.client.get(f"/api/v1/teaching-plans/{plan_id}", headers=outsider_headers)
    assert denied_get.status_code == 403
    assert denied_get.json()["code"] == "TEACHER_NOT_ASSIGNED"
    denied_duplicate = local_env.client.post(f"/api/v1/teaching-plans/{plan_id}/duplicate", headers=outsider_headers, json={"title": "Cópia indevida"})
    assert denied_duplicate.status_code == 403
    listed = local_env.client.get("/api/v1/teaching-plans", headers=outsider_headers)
    assert listed.status_code == 200
    assert plan_id not in {item["id"] for item in listed.json()["items"]}
