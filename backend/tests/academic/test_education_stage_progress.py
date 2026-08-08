from __future__ import annotations

from datetime import date

from conftest import ALPHA_HOST


def post(env, path: str, payload: dict, *, headers=None, key: str | None = None, expected: int = 201):
    request_headers = headers or env.alpha_headers()
    if key:
        request_headers = {**request_headers, "Idempotency-Key": key}
    response = env.client.post(path, headers=request_headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def create_school_context(env, *, suffix: str, level: str, component_count: int = 1):
    inst = post(env, "/api/v1/institutions", {"legal_name": f"Instituição {suffix} Ltda", "trade_name": f"Instituição {suffix}"})
    unit = post(env, "/api/v1/units", {"institution_id": inst["id"], "code": f"U-{suffix}", "name": f"Unidade {suffix}", "timezone": "America/Bahia"})
    year = post(env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": f"2026-{suffix}", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    program = post(env, "/api/v1/programs", {"institution_id": inst["id"], "code": f"P-{suffix}", "name": f"Programa {suffix}", "education_level": level})
    curriculum = post(env, "/api/v1/curricula", {"program_id": program["id"], "code": f"C-{suffix}", "name": f"Currículo {suffix}", "effective_from": "2026-01-01"})
    components = []
    for index in range(component_count):
        components.append(post(env, "/api/v1/curriculum-components", {
            "curriculum_id": curriculum["id"],
            "code": f"CMP-{suffix}-{index+1}",
            "name": f"Componente {suffix} {index+1}",
            "workload_hours": 80 + (index * 20),
            "credits": 4 + index,
        }))
    group = post(env, "/api/v1/class-groups", {
        "unit_id": unit["id"], "academic_year_id": year["id"], "program_id": program["id"],
        "curriculum_id": curriculum["id"], "code": f"T-{suffix}", "name": f"Turma {suffix}", "capacity": 30,
    })
    return inst, unit, year, program, curriculum, components, group


def create_active_student(env, *, suffix: str, context):
    inst, unit, year, program, curriculum, _, group = context
    person = post(env, "/api/v1/people", {"full_name": f"Aluno {suffix}", "cpf": f"900000000{len(suffix):02d}"}, key=f"person-{suffix}")
    student = post(env, "/api/v1/students", {"person_id": person["id"], "registration_number": f"RA-{suffix}"})
    enrollment = post(env, "/api/v1/enrollments", {
        "student_id": student["id"], "institution_id": inst["id"], "unit_id": unit["id"],
        "program_id": program["id"], "curriculum_id": curriculum["id"], "academic_year_id": year["id"],
        "class_group_id": group["id"], "enrollment_number": f"MAT-{suffix}",
    }, key=f"enroll-{suffix}")
    activated = post(env, f"/api/v1/enrollments/{enrollment['id']}/activate", {"expected_version": 1, "reason": "Matrícula ativa para teste acadêmico"}, expected=200)
    assert activated["state"] == "active"
    return person, student, enrollment


def create_teacher(env, *, suffix: str, group_id: str, component_id: str):
    person = post(env, "/api/v1/people", {"full_name": f"Professor {suffix}", "email": f"prof.{suffix.lower()}@example.com"}, key=f"teacher-person-{suffix}")
    employee = post(env, "/api/v1/employees", {"person_id": person["id"], "employee_number": f"PROF-{suffix}", "department": "Pedagógico", "position": "Professor", "admission_date": "2026-01-10"})
    _, token = env.create_alpha_user(f"prof.{suffix.lower()}@alpha.example.com", ["teacher"], person_id=person["id"])
    post(env, "/api/v1/teacher-assignments", {"employee_id": employee["id"], "class_group_id": group_id, "component_id": component_id, "starts_on": "2026-01-20", "ends_on": "2026-12-18", "role": "teacher"})
    return person, employee, token


def test_early_childhood_daily_agenda_guardian_access_and_pickup(local_env):
    context = create_school_context(local_env, suffix="INF", level="educacao_infantil")
    _, student, _ = create_active_student(local_env, suffix="INFANTIL", context=context)
    _, _, _, _, _, components, group = context
    _, _, teacher_token = create_teacher(local_env, suffix="Infantil", group_id=group["id"], component_id=components[0]["id"])
    teacher_headers = local_env.headers(ALPHA_HOST, teacher_token)
    teacher_ctx=local_env.client.get("/api/v1/portal/teacher/me",headers=teacher_headers)
    assert teacher_ctx.status_code==200,teacher_ctx.text
    assignment=teacher_ctx.json()["assignments"][0]
    assert assignment["education_level"]=="educacao_infantil"
    assignment_students=local_env.client.get(f"/api/v1/portal/teacher/assignments/{assignment['id']}/students",headers=teacher_headers)
    assert assignment_students.status_code==200,assignment_students.text
    assert [row["student_id"] for row in assignment_students.json()["items"]]==[student["id"]]

    guardian_person = post(local_env, "/api/v1/people", {"full_name": "Responsável Autorizado", "cpf": "91111111111", "email": "responsavel.inf@example.com"}, key="guardian-person-inf")
    guardian = post(local_env, "/api/v1/guardians", {"person_id": guardian_person["id"]})
    post(local_env, "/api/v1/guardian-students", {"guardian_id": guardian["id"], "student_id": student["id"], "relationship": "mãe", "is_legal": True, "is_financial": True, "pickup_authorized": True})
    _, guardian_token = local_env.create_alpha_user("responsavel.inf@alpha.example.com", ["guardian"], person_id=guardian_person["id"])
    guardian_headers = local_env.headers(ALPHA_HOST, guardian_token)

    daily = post(local_env, "/api/v1/academic/early-childhood/daily-records", {
        "student_id": student["id"], "record_date": "2026-08-08",
        "meals": [{"time": "11:30", "meal": "almoço", "consumption": "completo"}],
        "sleep": {"started_at": "13:00", "ended_at": "14:10", "quality": "tranquilo"},
        "hygiene": [{"time": "10:00", "type": "lavagem_mãos"}],
        "diaper_changes": [{"time": "09:40", "type": "troca"}],
        "mood": "alegre", "development_notes": "Participou das atividades de coordenação motora.",
        "authorized_photos": ["asset-photo-authorized-001"],
    }, headers=teacher_headers)
    assert daily["version"] == 1 and daily["mood"] == "alegre"

    updated = post(local_env, "/api/v1/academic/early-childhood/daily-records", {
        "student_id": student["id"], "record_date": "2026-08-08",
        "meals": [{"time": "11:30", "meal": "almoço", "consumption": "parcial"}],
        "sleep": {"started_at": "13:00", "ended_at": "14:10", "quality": "tranquilo"},
        "mood": "tranquilo", "development_notes": "Registro ajustado pela professora.",
    }, headers=teacher_headers)
    assert updated["id"] == daily["id"] and updated["version"] == 2

    family_view = local_env.client.get(f"/api/v1/academic/early-childhood/students/{student['id']}/daily-records", headers=guardian_headers)
    assert family_view.status_code == 200, family_view.text
    assert family_view.json()["items"][0]["meals"][0]["consumption"] == "parcial"

    pickup = post(local_env, "/api/v1/academic/early-childhood/pickups", {
        "student_id": student["id"], "guardian_id": guardian["id"], "released_at": "2026-08-08T17:05:00-03:00",
        "identity_document_masked": "CPF ***.***.***-11", "notes": "Retirada regular após conferência.",
    }, headers=teacher_headers)
    assert pickup["guardian_id"] == guardian["id"] and pickup["pickup_person_name"] == "Responsável Autorizado"

    unauthorized_person = post(local_env, "/api/v1/people", {"full_name": "Responsável Sem Retirada", "cpf": "92222222222"}, key="guardian-person-no-pickup")
    unauthorized = post(local_env, "/api/v1/guardians", {"person_id": unauthorized_person["id"]})
    post(local_env, "/api/v1/guardian-students", {"guardian_id": unauthorized["id"], "student_id": student["id"], "relationship": "tio", "pickup_authorized": False})
    denied = local_env.client.post("/api/v1/academic/early-childhood/pickups", headers=teacher_headers, json={
        "student_id": student["id"], "guardian_id": unauthorized["id"], "released_at": "2026-08-08T17:10:00-03:00", "notes": "Tentativa sem autorização",
    })
    assert denied.status_code == 403 and denied.json()["code"] == "PICKUP_NOT_AUTHORIZED"
    active_enrollment=local_env.client.get("/api/v1/enrollments",headers=local_env.alpha_headers()).json()["items"][0]
    no_tcc=local_env.client.post("/api/v1/academic/theses",headers=local_env.alpha_headers(),json={"enrollment_id":active_enrollment["id"],"title":"TCC indevido na educação infantil"})
    assert no_tcc.status_code==409 and no_tcc.json()["code"]=="ADVANCED_EDUCATION_PROGRAM_REQUIRED"


def test_higher_education_prerequisites_internship_activity_thesis_and_integralization(local_env):
    context = create_school_context(local_env, suffix="SUP", level="superior", component_count=2)
    _, student, enrollment = create_active_student(local_env, suffix="SUPERIOR", context=context)
    _, _, _, _, _, components, _ = context
    component_a, component_b = components
    _, student_token = local_env.create_alpha_user("student.superior@alpha.example.com", ["student"], person_id=local_env.client.get(f"/api/v1/students/{student['id']}", headers=local_env.alpha_headers()).json()["person_id"])
    student_headers = local_env.headers(ALPHA_HOST, student_token)

    prereq = post(local_env, "/api/v1/academic/component-prerequisites", {
        "component_id": component_b["id"], "prerequisite_component_id": component_a["id"], "minimum_final_score": "6",
    })
    assert prereq["state"] == "active"

    denied_before = local_env.client.post("/api/v1/academic/component-completions", headers=local_env.alpha_headers(), json={
        "enrollment_id": enrollment["id"], "component_id": component_b["id"], "source_type": "grade", "final_score": "8", "completed_on": "2026-07-15", "reason": "Conclusão ordinária sem pré-requisito",
    })
    assert denied_before.status_code == 409 and denied_before.json()["code"] == "COMPONENT_PREREQUISITES_NOT_MET"

    comp_a_low = post(local_env, "/api/v1/academic/component-completions", {
        "enrollment_id": enrollment["id"], "component_id": component_a["id"], "source_type": "grade", "final_score": "5", "completed_on": "2026-06-30", "reason": "Resultado final do primeiro componente",
    })
    assert comp_a_low["state"] == "approved"
    denied_score = local_env.client.post("/api/v1/academic/component-completions", headers=local_env.alpha_headers(), json={
        "enrollment_id": enrollment["id"], "component_id": component_b["id"], "source_type": "grade", "final_score": "8", "completed_on": "2026-07-15", "reason": "Tentativa com nota mínima não atendida",
    })
    assert denied_score.status_code == 409 and denied_score.json()["code"] == "COMPONENT_PREREQUISITES_NOT_MET"

    # Reconhecimento formal por equivalência pode superar o pré-requisito, deixando o ato explícito e auditável.
    comp_b = post(local_env, "/api/v1/academic/component-completions", {
        "enrollment_id": enrollment["id"], "component_id": component_b["id"], "source_type": "equivalence", "source_reference_id": "processo-equivalencia-2026-001", "final_score": "8", "completed_on": "2026-07-20", "reason": "Equivalência deferida pela coordenação acadêmica",
    })
    assert comp_b["state"] == "approved"

    internship = post(local_env, "/api/v1/academic/internships", {
        "enrollment_id": enrollment["id"], "organization_name": "Empresa Estágio Ltda", "supervisor_name": "Supervisor Externo",
        "starts_on": "2026-08-01", "ends_on": "2026-12-10", "required_hours": "100", "notes": "Estágio curricular obrigatório",
    })
    approved = post(local_env, f"/api/v1/academic/internships/{internship['id']}/state", {"state": "approved", "expected_version": 1, "reason": "Plano de estágio aprovado"}, expected=200)
    in_progress = post(local_env, f"/api/v1/academic/internships/{internship['id']}/state", {"state": "in_progress", "expected_version": approved["version"], "reason": "Início confirmado pela concedente"}, expected=200)
    hours_plan=[("2026-08-10","24"),("2026-08-11","24"),("2026-08-12","12")]
    last=None
    for activity_date,hours in hours_plan:
        last=post(local_env,f"/api/v1/academic/internships/{internship['id']}/hours",{"activity_date":activity_date,"hours":hours,"description":"Atividades supervisionadas do primeiro ciclo"},headers=student_headers)
    assert last["completed_hours"] == "60"
    # draft v1 -> approved v2 -> in_progress v3 -> 3 apontamentos => v6
    premature = local_env.client.post(f"/api/v1/academic/internships/{internship['id']}/state", headers=local_env.alpha_headers(), json={"state": "completed", "expected_version": 6, "reason": "Tentativa antes da carga completa"})
    assert premature.status_code == 409 and premature.json()["code"] == "INTERNSHIP_HOURS_INCOMPLETE"
    for activity_date,hours in (("2026-09-10","24"),("2026-09-11","16")):
        last=post(local_env,f"/api/v1/academic/internships/{internship['id']}/hours",{"activity_date":activity_date,"hours":hours,"description":"Atividades supervisionadas do segundo ciclo"},headers=student_headers)
    completed = post(local_env, f"/api/v1/academic/internships/{internship['id']}/state", {"state": "completed", "expected_version": 8, "reason": "Carga horária integral comprovada"}, expected=200)
    assert last["completed_hours"] == "100" and completed["state"] == "completed"

    activity = post(local_env, "/api/v1/academic/complementary-activities", {
        "enrollment_id": enrollment["id"], "category": "extensão", "title": "Projeto de extensão comunitária", "requested_hours": "20",
    }, headers=student_headers)
    decision = post(local_env, f"/api/v1/academic/complementary-activities/{activity['id']}/decision", {"state": "approved", "approved_hours": "15", "notes": "Quinze horas validadas conforme regulamento"}, expected=200)
    assert decision["approved_hours"] == "15"

    thesis = post(local_env, "/api/v1/academic/theses", {
        "enrollment_id": enrollment["id"], "title": "Arquitetura de Sistemas Educacionais Multi-tenant", "abstract": "Trabalho de conclusão aplicado à gestão educacional.",
    }, headers=student_headers)
    transitions = [
        ("approved", "Projeto aprovado pelo colegiado", None),
        ("in_progress", "Orientação e desenvolvimento iniciados", None),
        ("submitted", "Versão final submetida à banca", None),
        ("defended", "Defesa realizada perante banca examinadora", "2026-11-20T14:00:00-03:00"),
        ("passed", "TCC aprovado pela banca", None),
    ]
    version = 1
    for state, reason, defense_at in transitions:
        payload = {"state": state, "expected_version": version, "reason": reason}
        if defense_at:
            payload["defense_at"] = defense_at
            payload["grade"] = "9.2"
        elif state == "passed":
            payload["grade"] = "9.2"
        changed = post(local_env, f"/api/v1/academic/theses/{thesis['id']}/state", payload, expected=200)
        version = changed["version"]
    assert changed["state"] == "passed"

    own_integralization = local_env.client.get(f"/api/v1/academic/students/{student['id']}/integralization", headers=student_headers)
    assert own_integralization.status_code == 200, own_integralization.text
    info = own_integralization.json()["enrollments"][0]
    assert info["curriculum"]["components_total"] == 2
    assert info["curriculum"]["components_completed"] == 2
    assert info["curriculum"]["completion_percentage"] == "100.00"
    assert info["complementary_hours_approved"] == "15"
    assert info["internships"][0]["state"] == "completed"
    assert info["theses"][0]["state"] == "passed"

    other_context = create_school_context(local_env, suffix="SUP2", level="superior")
    _, other_student, _ = create_active_student(local_env, suffix="OUTRO", context=other_context)
    denied_other = local_env.client.get(f"/api/v1/academic/students/{other_student['id']}/integralization", headers=student_headers)
    assert denied_other.status_code == 403 and denied_other.json()["code"] == "STUDENT_ACCESS_DENIED"
