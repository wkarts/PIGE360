from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def post(env, path: str, payload: dict, *, expected: int = 201):
    response = env.client.post(path, headers=env.alpha_headers(), json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def academic_context(env):
    institution = post(env, "/api/v1/institutions", {"legal_name": "Escola Captação Ltda", "trade_name": "Escola Captação"})
    unit = post(env, "/api/v1/units", {"institution_id": institution["id"], "code": "MATRIZ", "name": "Matriz"})
    year = post(env, "/api/v1/academic-years", {"institution_id": institution["id"], "name": "2026", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    program = post(env, "/api/v1/programs", {"institution_id": institution["id"], "code": "EF2", "name": "Fundamental II", "education_level": "fundamental", "modality": "presencial"})
    curriculum = post(env, "/api/v1/curricula", {"program_id": program["id"], "code": "CURR-EF2", "name": "Currículo EF2", "effective_from": "2026-01-01"})
    group = post(env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": year["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": "7A", "name": "7º A", "capacity": 1})
    return institution, unit, year, program, curriculum, group


def test_admissions_public_lead_ranking_reservation_and_conversion(local_env):
    institution, unit, year, program, curriculum, group = academic_context(local_env)
    today = date.today()
    campaign = post(
        local_env,
        "/api/v1/admissions/campaigns",
        {
            "code": "CAP-2026",
            "name": "Captação 2026",
            "program_id": program["id"],
            "academic_year_id": year["id"],
            "starts_on": str(today - timedelta(days=1)),
            "ends_on": str(today + timedelta(days=30)),
            "channels": ["portal", "crm"],
        },
    )
    assert campaign["state"] == "active"

    public_campaigns = local_env.client.get("/api/v1/public/admissions/campaigns", headers={"host": "admin.alpha.school.local"})
    assert public_campaigns.status_code == 200, public_campaigns.text
    assert [item["id"] for item in public_campaigns.json()["items"]] == [campaign["id"]]

    denied = local_env.client.post(
        "/api/v1/public/admissions/leads",
        headers={"host": "admin.alpha.school.local"},
        json={"campaign_id": campaign["id"], "full_name": "Sem Consentimento", "email": "sem.consentimento@example.com", "consent": False},
    )
    assert denied.status_code == 422 and denied.json()["code"] == "LEAD_CONSENT_REQUIRED"

    def public_lead(name: str, email: str):
        response = local_env.client.post(
            "/api/v1/public/admissions/leads",
            headers={"host": "admin.alpha.school.local"},
            json={"campaign_id": campaign["id"], "full_name": name, "email": email, "consent": True},
        )
        assert response.status_code == 201, response.text
        return response.json()

    lead1 = public_lead("Candidata Ana", "ana.captacao@example.com")
    lead2 = public_lead("Candidato Bruno", "bruno.captacao@example.com")
    assert lead1["source"] == "public_form"

    now = datetime.now(UTC)
    process = post(
        local_env,
        "/api/v1/admissions/processes",
        {
            "code": "PS-2026-EF2",
            "name": "Processo Seletivo EF2",
            "program_id": program["id"],
            "academic_year_id": year["id"],
            "applications_open_at": (now - timedelta(hours=1)).isoformat(),
            "applications_close_at": (now + timedelta(hours=1)).isoformat(),
            "seats": 2,
        },
    )
    exam = post(local_env, f"/api/v1/admissions/processes/{process['id']}/assessments", {"code": "PROVA", "name": "Prova", "assessment_type": "exam", "weight": 70, "max_score": 100})
    interview = post(local_env, f"/api/v1/admissions/processes/{process['id']}/assessments", {"code": "ENT", "name": "Entrevista", "assessment_type": "interview", "weight": 30, "max_score": 10})

    pre_open = local_env.client.post(
        f"/api/v1/admissions/leads/{lead1['id']}/convert",
        headers=local_env.alpha_headers(),
        json={"process_id": process["id"]},
    )
    assert pre_open.status_code == 409 and pre_open.json()["code"] == "ADMISSION_PROCESS_STATE_INVALID"

    post(local_env, f"/api/v1/admissions/processes/{process['id']}/state", {"state": "published", "reason": "Edital publicado"}, expected=200)
    post(local_env, f"/api/v1/admissions/processes/{process['id']}/state", {"state": "applications_open", "reason": "Inscrições iniciadas"}, expected=200)

    app1 = post(local_env, f"/api/v1/admissions/leads/{lead1['id']}/convert", {"process_id": process["id"]})
    app2 = post(local_env, f"/api/v1/admissions/leads/{lead2['id']}/convert", {"process_id": process["id"]})

    for app, exam_score, interview_score in ((app1, 80, 8), (app2, 70, 7)):
        post(local_env, f"/api/v1/admissions/applications/{app['application_id']}/results", {"assessment_id": exam["id"], "score": exam_score}, expected=200)
        post(local_env, f"/api/v1/admissions/applications/{app['application_id']}/results", {"assessment_id": interview["id"], "score": interview_score}, expected=200)

    before_close = local_env.client.post(f"/api/v1/admissions/processes/{process['id']}/ranking", headers=local_env.alpha_headers())
    assert before_close.status_code == 409 and before_close.json()["code"] == "ADMISSION_PROCESS_STATE_INVALID"

    post(local_env, f"/api/v1/admissions/processes/{process['id']}/state", {"state": "applications_closed", "reason": "Prazo encerrado"}, expected=200)
    post(local_env, f"/api/v1/admissions/processes/{process['id']}/state", {"state": "ranking", "reason": "Classificação iniciada"}, expected=200)
    ranking = post(local_env, f"/api/v1/admissions/processes/{process['id']}/ranking", {}, expected=200)
    assert [row["score"] for row in ranking["items"]] == ["80.00", "70.00"]
    assert [row["rank_position"] for row in ranking["items"]] == [1, 2]

    for app in (app1, app2):
        selected = post(local_env, f"/api/v1/admissions/applications/{app['application_id']}/state", {"state": "selected", "reason": "Classificação aprovada"}, expected=200)
        assert selected["state"] == "selected"

    expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    reservation = post(local_env, f"/api/v1/admissions/applications/{app1['application_id']}/reserve", {"class_group_id": group["id"], "expires_at": expires_at, "reason": "Reserva para matrícula"})
    assert reservation["state"] == "reserved"

    full = local_env.client.post(
        f"/api/v1/admissions/applications/{app2['application_id']}/reserve",
        headers=local_env.alpha_headers(),
        json={"class_group_id": group["id"], "expires_at": expires_at, "reason": "Segunda reserva"},
    )
    assert full.status_code == 409 and full.json()["code"] == "CLASS_CAPACITY_EXCEEDED"

    capacity = local_env.client.get(f"/api/v1/class-groups/{group['id']}/capacity", headers=local_env.alpha_headers())
    assert capacity.status_code == 200, capacity.text
    assert capacity.json()["occupied"] == 0
    assert capacity.json()["admission_reserved"] == 1
    assert capacity.json()["committed"] == 1
    assert capacity.json()["available"] == 0

    converted = post(
        local_env,
        f"/api/v1/admissions/candidates/{app1['candidate_id']}/convert",
        {
            "registration_number": "AL-CAP-001",
            "institution_id": institution["id"],
            "unit_id": unit["id"],
            "curriculum_id": curriculum["id"],
            "class_group_id": group["id"],
            "enrollment_number": "MAT-CAP-001",
        },
    )
    assert converted["state"] == "reserved"
    assert converted["reservation_id"] == reservation["id"]

    reservations = local_env.client.get("/api/v1/admissions/reservations", headers=local_env.alpha_headers())
    assert reservations.status_code == 200, reservations.text
    consumed = next(row for row in reservations.json()["items"] if row["id"] == reservation["id"])
    assert consumed["state"] == "consumed"
    assert consumed["consumed_enrollment_id"] == converted["enrollment_id"]

    capacity_after = local_env.client.get(f"/api/v1/class-groups/{group['id']}/capacity", headers=local_env.alpha_headers()).json()
    assert capacity_after["occupied"] == 1 and capacity_after["admission_reserved"] == 0 and capacity_after["available"] == 0


def test_admission_campaign_and_process_date_validation(local_env):
    _, _, year, program, _, _ = academic_context(local_env)
    response = local_env.client.post(
        "/api/v1/admissions/campaigns",
        headers=local_env.alpha_headers(),
        json={
            "code": "INVALID-DATE",
            "name": "Campanha inválida",
            "program_id": program["id"],
            "academic_year_id": year["id"],
            "starts_on": "2026-09-10",
            "ends_on": "2026-09-01",
        },
    )
    assert response.status_code == 422

    now = datetime.now(UTC)
    process = local_env.client.post(
        "/api/v1/admissions/processes",
        headers=local_env.alpha_headers(),
        json={
            "code": "INVALID-WINDOW",
            "name": "Processo inválido",
            "program_id": program["id"],
            "academic_year_id": year["id"],
            "applications_open_at": (now + timedelta(days=2)).isoformat(),
            "applications_close_at": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert process.status_code == 422
