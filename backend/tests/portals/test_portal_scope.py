from __future__ import annotations

from conftest import ALPHA_HOST, PASSWORD


def _post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def _user(env, email: str, roles: list[str], person_id: str):
    created = env.client.post(
        "/api/v1/auth/users",
        headers=env.alpha_headers(),
        json={"email": email, "password": PASSWORD, "roles": roles, "person_id": person_id},
    )
    assert created.status_code == 201, created.text
    login = env.client.post("/api/v1/auth/login", headers={"host": ALPHA_HOST}, json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return created.json(), login.json()["access_token"]


def _academic_base(env):
    inst = _post(env, "/api/v1/institutions", {"legal_name": "Escola Escopo Ltda", "trade_name": "Escola Escopo", "education_system": "private"})
    unit = _post(env, "/api/v1/units", {"institution_id": inst["id"], "code": "U1", "name": "Unidade 1", "timezone": "America/Bahia", "address": {}})
    year = _post(env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": "2026", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    program = _post(env, "/api/v1/programs", {"institution_id": inst["id"], "code": "EF", "name": "Fundamental", "education_level": "fundamental"})
    curriculum = _post(env, "/api/v1/curricula", {"program_id": program["id"], "code": "C26", "name": "Currículo 2026", "effective_from": "2026-01-01"})
    component = _post(env, "/api/v1/curriculum-components", {"curriculum_id": curriculum["id"], "code": "MAT", "name": "Matemática", "workload_hours": 100})
    group = _post(env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": year["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": "7A", "name": "7º A", "capacity": 30})
    return inst, unit, year, program, curriculum, component, group


def _student(env, suffix: str):
    person = _post(env, "/api/v1/people", {"full_name": f"Aluno {suffix}", "email": f"aluno.{suffix.lower()}@example.com"}, key=f"person-{suffix}-scope")
    student = _post(env, "/api/v1/students", {"person_id": person["id"], "registration_number": f"MAT-{suffix}"})
    return person, student


def test_guardian_portal_and_pix_are_limited_to_linked_financial_dependent(local_env):
    inst, unit, year, program, curriculum, _component, group = _academic_base(local_env)
    person_a, student_a = _student(local_env, "A")
    person_b, student_b = _student(local_env, "B")
    guardian_person = _post(local_env, "/api/v1/people", {"full_name": "Responsável A", "email": "responsavel.a@example.com"}, key="guardian-person-scope")
    guardian = _post(local_env, "/api/v1/guardians", {"person_id": guardian_person["id"]})
    _post(local_env, "/api/v1/guardian-students", {"guardian_id": guardian["id"], "student_id": student_a["id"], "relationship": "mãe", "is_legal": True, "is_financial": True})
    _, guardian_token = _user(local_env, "guardiao@alpha.example.com", ["guardian"], guardian_person["id"])
    gh = local_env.headers(ALPHA_HOST, guardian_token)

    def enrollment(student, number, responsible=None):
        return _post(local_env, "/api/v1/enrollments", {"student_id": student["id"], "institution_id": inst["id"], "unit_id": unit["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "academic_year_id": year["id"], "class_group_id": group["id"], "enrollment_number": number, "financial_responsible_guardian_id": responsible}, key=f"enrollment-{number}")

    e_a = enrollment(student_a, "EA", guardian["id"])
    e_b = enrollment(student_b, "EB")
    c_a = _post(local_env, "/api/v1/finance/contracts", {"enrollment_id": e_a["id"], "responsible_guardian_id": guardian["id"], "description": "Mensalidade A", "total_amount": "100.00"})
    c_b = _post(local_env, "/api/v1/finance/contracts", {"enrollment_id": e_b["id"], "description": "Mensalidade B", "total_amount": "100.00"})
    i_a = _post(local_env, f"/api/v1/finance/contracts/{c_a['id']}/installments", {"count": 1, "first_due_date": "2026-08-10"})["installments"][0]
    i_b = _post(local_env, f"/api/v1/finance/contracts/{c_b['id']}/installments", {"count": 1, "first_due_date": "2026-08-10"})["installments"][0]
    account = _post(local_env, "/api/v1/banking/accounts", {"name": "Conta Escola", "pix_key": "financeiro@example.com", "pix_receiver_name": "ESCOLA ESCOPO", "pix_receiver_city": "SALVADOR"})

    context = local_env.client.get("/api/v1/portal/family/me", headers=gh)
    assert context.status_code == 200, context.text
    assert {d["student_id"] for d in context.json()["dependents"]} == {student_a["id"]}
    assert {i["id"] for i in context.json()["installments"]} == {i_a["id"]}

    own_pix = local_env.client.post(f"/api/v1/banking/accounts/{account['id']}/pix-charges", headers=gh, json={"installment_id": i_a["id"]})
    assert own_pix.status_code == 201, own_pix.text
    denied = local_env.client.post(f"/api/v1/banking/accounts/{account['id']}/pix-charges", headers=gh, json={"installment_id": i_b["id"]})
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "INSTALLMENT_ACCESS_DENIED"

    other = local_env.client.get(f"/api/v1/portal/family/dependents/{student_b['id']}", headers=gh)
    assert other.status_code == 403


def test_student_attendance_scope_blocks_other_student(local_env):
    _inst, _unit, _year, _program, _curriculum, _component, _group = _academic_base(local_env)
    person_a, student_a = _student(local_env, "OWN")
    _person_b, student_b = _student(local_env, "OTHER")
    _, token = _user(local_env, "student.scope@alpha.example.com", ["student"], person_a["id"])
    headers = local_env.headers(ALPHA_HOST, token)

    own = local_env.client.get(f"/api/v1/attendance/students/{student_a['id']}", headers=headers)
    assert own.status_code == 200, own.text
    denied = local_env.client.get(f"/api/v1/attendance/students/{student_b['id']}", headers=headers)
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "STUDENT_ACCESS_DENIED"

    portal = local_env.client.get("/api/v1/portal/student/me", headers=headers)
    assert portal.status_code == 200, portal.text
    assert portal.json()["student"]["id"] == student_a["id"]


def test_public_context_is_tenant_scoped_and_contains_no_platform_wordmark(local_env):
    _academic_base(local_env)
    alpha = local_env.client.get("/api/v1/public/context", headers={"host": ALPHA_HOST})
    assert alpha.status_code == 200, alpha.text
    text = alpha.text.lower()
    assert "pige360" not in text
    beta = local_env.client.get("/api/v1/public/context", headers={"host": "admin.beta.school.local"})
    assert beta.status_code == 200
    assert beta.json()["institutions"] == []


def test_student_cannot_access_admin_documents_or_trip_emergency_and_only_sees_published_events(local_env):
    _academic_base(local_env)
    person, _student_row = _student(local_env, "SEC")
    _, token = _user(local_env, "student.security@alpha.example.com", ["student"], person["id"])
    headers = local_env.headers(ALPHA_HOST, token)

    draft = _post(local_env, "/api/v1/events", {"event_type":"meeting","name":"Reunião interna","starts_at":"2026-09-01T12:00:00Z","ends_at":"2026-09-01T13:00:00Z"})
    published = _post(local_env, "/api/v1/events", {"event_type":"fair","name":"Feira escolar","starts_at":"2026-09-02T12:00:00Z","ends_at":"2026-09-02T13:00:00Z"})
    pub = local_env.client.post(f"/api/v1/events/{published['id']}/publish", headers=local_env.alpha_headers())
    assert pub.status_code == 200, pub.text
    trip = _post(local_env, "/api/v1/trips", {"name":"Excursão privada","destination":"Museu","starts_at":"2026-10-01T08:00:00Z","ends_at":"2026-10-01T18:00:00Z","emergency":{"contact":"sigiloso"}})

    visible = local_env.client.get("/api/v1/events", headers=headers)
    assert visible.status_code == 200, visible.text
    assert {x["id"] for x in visible.json()["items"]} == {published["id"]}
    assert draft["id"] not in {x["id"] for x in visible.json()["items"]}

    trips = local_env.client.get("/api/v1/trips", headers=headers)
    assert trips.status_code == 403, trips.text

    uploaded = local_env.client.post(
        "/api/v1/documents?owner_type=student&category=academic",
        headers=local_env.alpha_headers(),
        files={"file": ("secret.pdf", b"%PDF-1.4\nPRIVATE\n%%EOF", "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert local_env.client.get("/api/v1/documents", headers=headers).status_code == 403
    assert local_env.client.get(f"/api/v1/documents/{uploaded.json()['id']}/download", headers=headers).status_code == 403
    assert trip["id"]
