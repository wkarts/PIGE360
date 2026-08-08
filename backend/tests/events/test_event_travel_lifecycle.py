from __future__ import annotations


def post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201, headers=None):
    h = headers or env.alpha_headers()
    if key:
        h = {**h, "Idempotency-Key": key}
    response = env.client.post(path, headers=h, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def student_and_guardian(env, suffix: str, student_cpf: str, guardian_cpf: str):
    sp = post(env, "/api/v1/people", {"full_name": f"Aluno Evento {suffix}", "cpf": student_cpf}, key=f"event-student-person-{suffix}")
    student = post(env, "/api/v1/students", {"person_id": sp["id"], "registration_number": f"EV-{suffix}"})
    gp = post(env, "/api/v1/people", {"full_name": f"Responsável Evento {suffix}", "cpf": guardian_cpf, "email": f"guardian{suffix}@example.com"}, key=f"event-guardian-person-{suffix}")
    guardian = post(env, "/api/v1/guardians", {"person_id": gp["id"]})
    post(env, "/api/v1/guardian-students", {"guardian_id": guardian["id"], "student_id": student["id"], "relationship": "responsável legal", "is_legal": True, "is_financial": True, "pickup_authorized": True})
    return student, gp, guardian


def test_event_registration_authorization_finance_and_trip_operations(local_env):
    student, guardian_person, guardian = student_and_guardian(local_env, "01", "51515151515", "61616161616")
    second_student, _, _ = student_and_guardian(local_env, "02", "52525252525", "62626262626")
    _, guardian_token = local_env.create_alpha_user("guardian01@example.com", ["guardian"], person_id=guardian_person["id"])
    guardian_headers = local_env.headers("admin.alpha.school.local", guardian_token)

    event = post(
        local_env,
        "/api/v1/events",
        {
            "event_type": "excursao",
            "name": "Visita técnica ao museu",
            "starts_at": "2026-09-15T08:00:00-03:00",
            "ends_at": "2026-09-15T18:00:00-03:00",
            "location": "Museu de Ciência",
            "capacity": 1,
            "registration_fee": "100.00",
            "authorization_required": True,
            "payload": {"meeting_point": "Portão principal"},
        },
    )
    post(local_env, f"/api/v1/events/{event['id']}/schedule", {"sequence": 1, "title": "Credenciamento", "starts_at": "2026-09-15T08:00:00-03:00", "ends_at": "2026-09-15T08:30:00-03:00", "location": "Escola"})
    post(local_env, f"/api/v1/events/{event['id']}/publish", {}, expected=200)

    registration = post(
        local_env,
        f"/api/v1/events/{event['id']}/registrations",
        {"student_id": student["id"], "guardian_id": guardian["id"], "due_date": "2026-09-01"},
        key="event-registration-001",
    )
    assert registration["state"] == "awaiting_authorization"
    assert registration["fee_amount"] == "100.00"
    assert registration["financial_contract_id"]
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    installment = store.fetch_one("SELECT original_amount,due_date,state FROM installments WHERE tenant_id=? AND financial_contract_id=?", (tenant_id, registration["financial_contract_id"]))
    assert float(installment["original_amount"]) == 100.0 and installment["due_date"] == "2026-09-01" and installment["state"] == "open"

    capacity_denied = local_env.client.post(
        f"/api/v1/events/{event['id']}/registrations",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "event-registration-capacity"},
        json={"student_id": second_student["id"]},
    )
    assert capacity_denied.status_code == 409, capacity_denied.text
    assert capacity_denied.json()["code"] == "EVENT_CAPACITY_EXCEEDED"

    authorization = post(
        local_env,
        f"/api/v1/event-registrations/{registration['id']}/authorization",
        {"decision": "approved", "consent_text": "Autorizo expressamente a participação e a viagem."},
        expected=200,
        headers=guardian_headers,
    )
    assert authorization["state"] == "confirmed"
    auth_db = store.fetch_one("SELECT state,evidence_json FROM event_authorizations WHERE tenant_id=? AND event_registration_id=?", (tenant_id, registration["id"]))
    assert auth_db["state"] == "approved" and "authenticated_consent" in auth_db["evidence_json"]

    checkin = post(local_env, f"/api/v1/event-registrations/{registration['id']}/check-in", {}, expected=200)
    assert checkin["state"] == "checked_in"
    checkout = post(local_env, f"/api/v1/event-registrations/{registration['id']}/check-out", {}, expected=200)
    assert checkout["state"] == "completed"

    trip = post(
        local_env,
        "/api/v1/trips",
        {"event_id": event["id"], "name": "Ônibus Museu", "destination": "Museu de Ciência", "starts_at": "2026-09-15T07:30:00-03:00", "ends_at": "2026-09-15T18:30:00-03:00", "itinerary": [{"order": 1, "name": "Escola"}, {"order": 2, "name": "Museu"}], "vehicles": [{"plate": "ABC1D23", "capacity": 42}], "emergency": {"phone": "192"}},
    )
    passenger = post(local_env, f"/api/v1/trips/{trip['id']}/passengers", {"student_id": student["id"], "guardian_id": guardian["id"], "event_registration_id": registration["id"], "emergency_snapshot": {"contact": "Responsável Evento 01"}})
    checkpoint = post(local_env, f"/api/v1/trips/{trip['id']}/checkpoints", {"sequence": 1, "name": "Saída da escola", "planned_at": "2026-09-15T07:30:00-03:00"})
    post(local_env, f"/api/v1/trips/{trip['id']}/publish", {}, expected=200)
    boarded = post(local_env, f"/api/v1/trips/{trip['id']}/passengers/{passenger['id']}/board", {}, expected=200)
    assert boarded["state"] == "boarded"
    reached = post(local_env, f"/api/v1/trips/{trip['id']}/checkpoints/{checkpoint['id']}/reach", {}, expected=200)
    assert reached["state"] == "reached"
    incident = post(local_env, f"/api/v1/trips/{trip['id']}/incidents", {"passenger_id": passenger["id"], "incident_type": "motion_sickness", "severity": "low", "description": "Enjoo leve durante o trajeto."})
    assert incident["severity"] == "low"
    disembarked = post(local_env, f"/api/v1/trips/{trip['id']}/passengers/{passenger['id']}/disembark", {}, expected=200)
    assert disembarked["state"] == "completed"

    details = local_env.client.get(f"/api/v1/trips/{trip['id']}", headers=local_env.alpha_headers())
    assert details.status_code == 200, details.text
    body = details.json()
    assert body["state"] == "published"
    assert body["passengers"][0]["state"] == "completed"
    assert body["checkpoints"][0]["state"] == "reached"
    assert body["incidents"][0]["incident_type"] == "motion_sickness"
