from __future__ import annotations


def post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def make_person_student(env, name: str, cpf: str, registration: str):
    person = post(env, "/api/v1/people", {"full_name": name, "cpf": cpf}, key=f"person-{registration}")
    student = post(env, "/api/v1/students", {"person_id": person["id"], "registration_number": registration})
    return person, student


def school_context(env):
    inst = post(env, "/api/v1/institutions", {"legal_name": "Escola Secretaria Ltda", "trade_name": "Escola Secretaria"})
    unit = post(env, "/api/v1/units", {"institution_id": inst["id"], "code": "MATRIZ", "name": "Matriz"})
    y26 = post(env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": "2026", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    y27 = post(env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": "2027", "starts_on": "2027-01-20", "ends_on": "2027-12-17"})
    program = post(env, "/api/v1/programs", {"institution_id": inst["id"], "code": "EF2", "name": "Fundamental II", "education_level": "fundamental", "modality": "presencial"})
    curriculum = post(env, "/api/v1/curricula", {"program_id": program["id"], "code": "CURR-EF2", "name": "Currículo EF2", "effective_from": "2026-01-01"})
    a = post(env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": y26["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": "7A", "name": "7º A", "capacity": 1})
    b = post(env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": y26["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": "7B", "name": "7º B", "capacity": 2})
    next_group = post(env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": y27["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": "8A", "name": "8º A", "capacity": 2})
    return inst, unit, y26, y27, program, curriculum, a, b, next_group


def create_enrollment(env, student, inst, unit, year, program, curriculum, group, number):
    return post(
        env,
        "/api/v1/enrollments",
        {
            "student_id": student["id"],
            "institution_id": inst["id"],
            "unit_id": unit["id"],
            "program_id": program["id"],
            "curriculum_id": curriculum["id"],
            "academic_year_id": year["id"],
            "class_group_id": group["id"],
            "enrollment_number": number,
        },
        key=f"enroll-{number}",
    )


def test_secretary_enrollment_history_capacity_and_renewal(local_env):
    inst, unit, y26, y27, program, curriculum, group_a, group_b, group_27 = school_context(local_env)
    _, student1 = make_person_student(local_env, "Aluno Reserva Um", "11111111111", "AL-001")
    _, student2 = make_person_student(local_env, "Aluno Reserva Dois", "22222222222", "AL-002")
    e1 = create_enrollment(local_env, student1, inst, unit, y26, program, curriculum, group_a, "MAT-001")
    e2 = create_enrollment(local_env, student2, inst, unit, y26, program, curriculum, group_a, "MAT-002")

    reserved = post(local_env, f"/api/v1/enrollments/{e1['id']}/reserve", {"expected_version": 1, "reason": "Documentos iniciais conferidos", "effective_on": "2026-01-10"}, expected=200)
    assert reserved["state"] == "reserved" and reserved["version"] == 2
    capacity = local_env.client.get(f"/api/v1/class-groups/{group_a['id']}/capacity", headers=local_env.alpha_headers())
    assert capacity.status_code == 200, capacity.text
    assert capacity.json() == {"class_group_id": group_a["id"], "capacity": 1, "occupied": 1, "admission_reserved": 0, "committed": 1, "available": 0}

    denied = local_env.client.post(
        f"/api/v1/enrollments/{e2['id']}/reserve",
        headers=local_env.alpha_headers(),
        json={"expected_version": 1, "reason": "Tentativa com turma lotada", "effective_on": "2026-01-10"},
    )
    assert denied.status_code == 409 and denied.json()["code"] == "CLASS_CAPACITY_EXCEEDED"

    active = post(local_env, f"/api/v1/enrollments/{e1['id']}/activate", {"expected_version": 2, "reason": "Matrícula homologada"}, expected=200)
    changed = post(local_env, f"/api/v1/enrollments/{e1['id']}/change-class", {"expected_version": active["version"], "class_group_id": group_b["id"], "reason": "Ajuste pedagógico", "effective_on": "2026-02-01"}, expected=200)
    suspended = post(local_env, f"/api/v1/enrollments/{e1['id']}/suspend", {"expected_version": changed["version"], "reason": "Trancamento temporário", "effective_on": "2026-03-15"}, expected=200)
    reopened = post(local_env, f"/api/v1/enrollments/{e1['id']}/activate", {"expected_version": suspended["version"], "reason": "Retorno do trancamento"}, expected=200)
    completed = post(local_env, f"/api/v1/enrollments/{e1['id']}/complete", {"expected_version": reopened["version"], "reason": "Ano letivo integralizado"}, expected=200)
    renewed = post(
        local_env,
        f"/api/v1/enrollments/{e1['id']}/renew",
        {
            "enrollment_number": "MAT-001-2027",
            "academic_year_id": y27["id"],
            "class_group_id": group_27["id"],
            "reason": "Rematrícula para o período seguinte",
        },
    )
    assert completed["state"] == "completed"
    assert renewed["state"] == "pre_enrolled" and renewed["academic_year_id"] == y27["id"]

    history = local_env.client.get(f"/api/v1/enrollments/{e1['id']}/movements", headers=local_env.alpha_headers())
    assert history.status_code == 200, history.text
    movement_types = [row["movement_type"] for row in history.json()["items"]]
    assert movement_types == ["vacancy_reserved", "activation", "class_change", "suspension", "reopening", "completion", "renewal_created"]

    detail = local_env.client.get(f"/api/v1/enrollments/{e1['id']}", headers=local_env.alpha_headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["state"] == "completed"
    assert detail.json()["class_group_id"] == group_b["id"]


def test_admission_selection_history_and_conversion(local_env):
    inst, unit, y26, _, program, curriculum, _, group_b, _ = school_context(local_env)
    candidate_person = post(local_env, "/api/v1/people", {"full_name": "Candidato Selecionado", "cpf": "33333333333", "email": "candidato@example.com"}, key="candidate-person-001")
    candidate = post(local_env, "/api/v1/admissions/candidates", {"person_id": candidate_person["id"], "program_id": program["id"], "academic_year_id": y26["id"], "source": "site", "score": 91.5, "rank_position": 2})
    for state, reason in (("under_review", "Documentação em análise"), ("approved", "Critérios atendidos"), ("selected", "Vaga ofertada")):
        changed = post(local_env, f"/api/v1/admissions/candidates/{candidate['id']}/state", {"state": state, "reason": reason}, expected=200)
        assert changed["state"] == state

    converted = post(
        local_env,
        f"/api/v1/admissions/candidates/{candidate['id']}/convert",
        {
            "registration_number": "CAND-2026-01",
            "institution_id": inst["id"],
            "unit_id": unit["id"],
            "curriculum_id": curriculum["id"],
            "class_group_id": group_b["id"],
            "enrollment_number": "MAT-CAND-2026-01",
        },
    )
    assert converted["state"] == "pre_enrolled"
    detail = local_env.client.get(f"/api/v1/admissions/candidates/{candidate['id']}", headers=local_env.alpha_headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["state"] == "converted"
    assert [event["to_state"] for event in detail.json()["events"]] == ["under_review", "approved", "selected", "converted"]
