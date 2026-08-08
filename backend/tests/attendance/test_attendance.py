from __future__ import annotations

from conftest import ALPHA_HOST


def _create_policy(local_env) -> dict:
    response = local_env.client.post(
        "/api/v1/attendance/policies",
        headers=local_env.alpha_headers(),
        json={
            "name": "Política anual 2026",
            "effective_from": "2026-01-01",
            "minimum_percentage": "75",
            "status_effects": {
                "present": "1",
                "remote_present": "1",
                "activity_present": "1",
                "late": "0.75",
                "late_justified": "0.75",
                "early_departure": "0.75",
                "early_departure_justified": "0.75",
                "absent": "0",
                "justified_absence": "0",
                "excused_absence": "1",
                "medical_leave": None,
                "institutional_leave": None,
                "attendance_pending": None,
                "not_expected": None,
                "not_enrolled": None,
                "transferred": None,
                "cancelled_session": None,
            },
            "tolerances": {"late_minutes": 10, "early_departure_minutes": 10, "rounding": 2},
            "rules": {"notification_wait_minutes": 20, "reopen_requires_reason": True},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _post(local_env, path: str, payload: dict, *, key: str | None = None, expected: int = 201) -> dict:
    headers = local_env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = local_env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def _class_context(local_env, suffix: str = "1", *, create_other_teacher: bool = False) -> dict:
    inst = _post(local_env, "/api/v1/institutions", {"legal_name": f"Escola Frequência {suffix} Ltda", "trade_name": f"Escola Frequência {suffix}", "education_system": "private"})
    unit = _post(local_env, "/api/v1/units", {"institution_id": inst["id"], "code": f"U{suffix}", "name": f"Unidade {suffix}", "timezone": "America/Bahia", "address": {}})
    year = _post(local_env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": "2026", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    program = _post(local_env, "/api/v1/programs", {"institution_id": inst["id"], "code": f"EF{suffix}", "name": "Ensino Fundamental", "education_level": "fundamental"})
    curriculum = _post(local_env, "/api/v1/curricula", {"program_id": program["id"], "code": f"CURR-{suffix}", "name": f"Currículo {suffix}", "effective_from": "2026-01-01"})
    component = _post(local_env, "/api/v1/curriculum-components", {"curriculum_id": curriculum["id"], "code": f"MAT{suffix}", "name": "Matemática", "workload_hours": 160})
    group = _post(local_env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": year["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": f"7A-{suffix}", "name": "7º A", "capacity": 30})

    students: list[dict] = []
    for index in range(1, 4):
        person = _post(local_env, "/api/v1/people", {"full_name": f"Aluno Frequência {suffix}-{index}", "email": f"freq.{suffix}.{index}@example.com"}, key=f"freq-person-{suffix}-{index}")
        student = _post(local_env, "/api/v1/students", {"person_id": person["id"], "registration_number": f"FREQ-{suffix}-{index}"})
        enrollment = _post(local_env, "/api/v1/enrollments", {"student_id": student["id"], "institution_id": inst["id"], "unit_id": unit["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "academic_year_id": year["id"], "class_group_id": group["id"], "enrollment_number": f"ENR-FREQ-{suffix}-{index}"}, key=f"freq-enrollment-{suffix}-{index}")
        _post(local_env, f"/api/v1/enrollments/{enrollment['id']}/activate", {"expected_version": 1, "reason": "Matrícula válida para chamada"}, expected=200)
        students.append(student)

    teacher_person = _post(local_env, "/api/v1/people", {"full_name": f"Professor Frequência {suffix}", "email": f"prof.freq.{suffix}@example.com"}, key=f"freq-teacher-person-{suffix}")
    employee = _post(local_env, "/api/v1/employees", {"person_id": teacher_person["id"], "employee_number": f"PROF-{suffix}", "department": "Pedagógico", "position": "Professor", "admission_date": "2026-01-05"})
    teacher, teacher_token = local_env.create_alpha_user(f"attendance.teacher.{suffix}@alpha.example.com", ["teacher"], person_id=teacher_person["id"])
    assignment = _post(local_env, "/api/v1/teacher-assignments", {"employee_id": employee["id"], "class_group_id": group["id"], "component_id": component["id"], "starts_on": "2026-01-20", "role": "teacher"})

    other_token = None
    if create_other_teacher:
        other_person = _post(local_env, "/api/v1/people", {"full_name": f"Professor Sem Atribuição {suffix}", "email": f"other.freq.{suffix}@example.com"}, key=f"freq-other-person-{suffix}")
        _post(local_env, "/api/v1/employees", {"person_id": other_person["id"], "employee_number": f"OTHER-{suffix}", "department": "Pedagógico", "position": "Professor", "admission_date": "2026-01-05"})
        _, other_token = local_env.create_alpha_user(f"other.{suffix}@alpha.example.com", ["teacher"], person_id=other_person["id"])

    return {"institution": inst, "unit": unit, "year": year, "program": program, "curriculum": curriculum, "component": component, "group": group, "students": students, "teacher": teacher, "teacher_token": teacher_token, "assignment": assignment, "other_token": other_token}


def _create_session(local_env, policy_id: str, context: dict, suffix: str = "1") -> dict:
    response = local_env.client.post(
        "/api/v1/class-sessions",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"session-create-{suffix}-0001"}),
        json={
            "institution_id": context["institution"]["id"],
            "unit_id": context["unit"]["id"],
            "class_group_id": context["group"]["id"],
            "component_id": context["component"]["id"],
            "attendance_policy_id": policy_id,
            "scheduled_start": "2026-08-10T10:00:00-03:00",
            "scheduled_end": "2026-08-10T11:40:00-03:00",
            "modality": "regular",
            "enrolled_student_ids": [student["id"] for student in context["students"]],
            "teacher_ids": [context["teacher"]["id"]],
            "room_id": "room-12",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_offline_call_submission_correction_reopen_justification_and_risk(local_env):
    context = _class_context(local_env, "1")
    policy = _create_policy(local_env)
    session = _create_session(local_env, policy["id"], context)
    teacher_headers = local_env.headers(ALPHA_HOST, context["teacher_token"])
    student_1, student_2, student_3 = [student["id"] for student in context["students"]]

    started = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/start",
        headers=teacher_headers,
        json={"reason": "Início da sessão", "expected_version": session["version"]},
    )
    assert started.status_code == 200, started.text

    call = local_env.client.put(
        f"/api/v1/class-sessions/{session['id']}/attendance",
        headers={**teacher_headers, "Idempotency-Key": "offline-call-alpha-0001"},
        json={
            "records": [
                {"student_id": student_1, "status_code": "present"},
                {"student_id": student_2, "status_code": "absent", "observation": "Sem justificativa"},
                {"student_id": student_3, "status_code": "late", "minutes_present": 85},
            ],
            "mode": "all_present_exceptions",
            "origin": "offline",
            "device_id": "teacher-device-001",
        },
    )
    assert call.status_code == 200, call.text
    assert call.json()["current_version"] == 1

    replay = local_env.client.put(
        f"/api/v1/class-sessions/{session['id']}/attendance",
        headers={**teacher_headers, "Idempotency-Key": "offline-call-alpha-0001"},
        json={
            "records": [
                {"student_id": student_1, "status_code": "present"},
                {"student_id": student_2, "status_code": "absent", "observation": "Sem justificativa"},
                {"student_id": student_3, "status_code": "late", "minutes_present": 85},
            ],
            "mode": "all_present_exceptions",
            "origin": "offline",
            "device_id": "teacher-device-001",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["attendance_call_id"] == call.json()["attendance_call_id"]

    submitted = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/attendance/submit",
        headers=teacher_headers,
        json={"expected_call_version": call.json()["current_version"], "origin": "offline", "device_id": "teacher-device-001"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    closed = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/close",
        headers=local_env.alpha_headers(),
        json={"reason": "Diário conferido", "expected_version": submitted.json()["session_version"]},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"

    reopened = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/reopen",
        headers=local_env.alpha_headers(),
        json={"reason": "Documento médico recebido", "expected_version": closed.json()["version"]},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "reopened"

    attendance = local_env.client.get(f"/api/v1/class-sessions/{session['id']}/attendance", headers=local_env.alpha_headers())
    absent = next(x for x in attendance.json()["records"] if x["student_id"] == student_2)
    corrected = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/attendance/corrections",
        headers=local_env.alpha_headers(),
        json={
            "student_id": student_2,
            "to_status": "justified_absence",
            "reason": "Atestado médico validado",
            "expected_record_version": absent["version"],
            "origin": "online",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["record"]["status_code"] == "justified_absence"

    justification = local_env.client.post(
        "/api/v1/attendance/justifications",
        headers=local_env.alpha_headers(),
        json={"student_id": student_2, "session_ids": [session["id"]], "reason": "Atestado médico", "attachments": [{"sha256": "0" * 64}]},
    )
    assert justification.status_code == 201
    approved = local_env.client.post(
        f"/api/v1/attendance/justifications/{justification.json()['id']}/approve",
        headers=local_env.alpha_headers(),
        json={"notes": "Documento conferido"},
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"

    risks = local_env.client.get("/api/v1/attendance/risks", headers=local_env.alpha_headers())
    assert risks.status_code == 200
    risk_student = next(x for x in risks.json()["items"] if x["student_id"] == student_2)
    assert risk_student["policy_versions"][0]["version"] == 1
    assert risk_student["percentage"] == "0.00"


def test_teacher_without_assignment_is_blocked_and_cancelled_session_has_no_absence(local_env):
    context = _class_context(local_env, "2", create_other_teacher=True)
    policy = _create_policy(local_env)
    session = _create_session(local_env, policy["id"], context, "2")
    other_token = context["other_token"]

    blocked = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/start",
        headers=local_env.headers(ALPHA_HOST, other_token),
        json={"reason": "Tentativa indevida", "expected_version": session["version"]},
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "TEACHER_NOT_ASSIGNED"

    cancelled = local_env.client.post(
        f"/api/v1/class-sessions/{session['id']}/cancel",
        headers=local_env.alpha_headers(),
        json={"reason": "Feriado municipal", "expected_version": session["version"]},
    )
    assert cancelled.status_code == 200
    call = local_env.client.get(f"/api/v1/class-sessions/{session['id']}/attendance", headers=local_env.alpha_headers())
    assert call.status_code == 200
    assert call.json()["records"] == []
    session_after = local_env.client.get(f"/api/v1/class-sessions/{session['id']}", headers=local_env.alpha_headers())
    assert session_after.json()["status"] == "cancelled"
