from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.modules.operations.common import ADMIN_ROLES, HR_ROLES, require, tenant
from app.modules.portals.access import employee_for_user, guardian_for_user, student_for_user
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["tenant-portals"])


def _brand(store, tenant_id: str) -> dict[str, Any]:
    kit = store.fetch_one("SELECT state,active_version,payload_json FROM brand_kits WHERE tenant_id=?", (tenant_id,))
    payload: dict[str, Any] = {}
    if kit:
        try:
            payload = json.loads(kit["payload_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
    return {
        "state": kit["state"] if kit else "awaiting_assets",
        "active_version": kit["active_version"] if kit else None,
        "legal_name": payload.get("legal_name"),
        "trade_name": payload.get("trade_name"),
        "short_name": payload.get("short_name"),
        "primary_color": payload.get("primary_color", "#006D77"),
        "secondary_color": payload.get("secondary_color", "#0D1B2A"),
        "accent_color": payload.get("accent_color", "#F59E0B"),
        "light_theme": payload.get("light_theme", {}),
        "dark_theme": payload.get("dark_theme", {}),
        "logo_symbol": payload.get("logo_symbol"),
        "logo_horizontal_light": payload.get("logo_horizontal_light"),
        "logo_horizontal_dark": payload.get("logo_horizontal_dark"),
        "support_name": payload.get("support_name"),
        "support_email": payload.get("support_email"),
        "support_phone": payload.get("support_phone"),
        "website": payload.get("website"),
    }


def _visible_notices(store, tenant_id: str, *, roles: set[str], student_ids: set[str] | None = None) -> list[dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    rows = store.fetch_all(
        "SELECT * FROM notices WHERE tenant_id=? AND state='published' AND (expires_at IS NULL OR expires_at>?) ORDER BY created_at DESC LIMIT 100",
        (tenant_id, now),
    )
    visible: list[dict[str, Any]] = []
    for row in rows:
        try:
            audience = json.loads(row.get("audience_json") or "{}")
            channels = json.loads(row.get("channels_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        kind = audience.get("type", "all")
        allowed = kind == "all"
        if kind == "roles":
            allowed = bool(roles.intersection(set(audience.get("roles", []))))
        elif kind == "students" and student_ids is not None:
            allowed = bool(student_ids.intersection(set(audience.get("student_ids", []))))
        elif kind == "guardians":
            allowed = "guardian" in roles
        elif kind == "students_all":
            allowed = "student" in roles or bool(student_ids)
        if allowed:
            item = dict(row)
            item["audience"] = audience
            item["channels"] = channels
            item.pop("audience_json", None)
            item.pop("channels_json", None)
            visible.append(item)
    return visible


def _attendance_summary(store, tenant_id: str, student_id: str) -> dict[str, Any]:
    rows = store.fetch_all(
        """
        SELECT r.status_code,s.scheduled_start,s.component_id,cc.name AS component_name
          FROM attendance_records r
          JOIN class_sessions s ON s.id=r.class_session_id
          LEFT JOIN curriculum_components cc ON cc.id=s.component_id
         WHERE r.tenant_id=? AND r.student_id=? AND s.status NOT IN ('cancelled','rescheduled')
         ORDER BY s.scheduled_start DESC
        """,
        (tenant_id, student_id),
    )
    present = Decimal("0")
    counted = 0
    weights = {
        "present": Decimal("1"), "remote_present": Decimal("1"), "activity_present": Decimal("1"),
        "late": Decimal("0.75"), "late_justified": Decimal("0.75"), "early_departure": Decimal("0.75"),
        "early_departure_justified": Decimal("0.75"), "absent": Decimal("0"), "justified_absence": Decimal("0"),
        "excused_absence": Decimal("1"),
    }
    by_component: dict[str, dict[str, int]] = {}
    for row in rows:
        status = row["status_code"]
        if status in weights:
            present += weights[status]
            counted += 1
        key = row.get("component_name") or row.get("component_id") or "Componente"
        by_component.setdefault(key, {})[status] = by_component.setdefault(key, {}).get(status, 0) + 1
    pct = (present / counted * 100).quantize(Decimal("0.01")) if counted else Decimal("0")
    return {"percentage": str(pct), "counted_sessions": counted, "by_component": by_component, "recent": rows[:20]}


@router.get("/public/context", operation_id="get_public_tenant_context")
def public_context(request: Request):
    resolution = request.state.host_resolution
    if resolution.plane != "tenant" or not resolution.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Conteúdo público disponível somente no domínio da instituição.", 404)
    tid = resolution.tenant_id
    store = request.state.store
    institutions = store.fetch_all("SELECT id,legal_name,trade_name,education_system FROM institutions WHERE tenant_id=? AND state='active' ORDER BY trade_name", (tid,))
    programs = store.fetch_all("SELECT id,institution_id,code,name,education_level,modality FROM programs WHERE tenant_id=? AND state='active' ORDER BY name", (tid,))
    events = store.fetch_all("SELECT id,name,event_type,starts_at,ends_at,location,payload_json,state FROM events WHERE tenant_id=? AND state='published' ORDER BY starts_at LIMIT 50", (tid,))
    notices = _visible_notices(store, tid, roles=set())
    return {"branding": _brand(store, tid), "institutions": institutions, "programs": programs, "events": events, "notices": notices}


@router.get("/portal/family/me", operation_id="get_family_portal_context")
def family_me(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"guardian"})
    tid = tenant(user)
    guardian = guardian_for_user(request, user)
    person = request.state.store.fetch_one("SELECT id,full_name,social_name,email,phone FROM people WHERE tenant_id=? AND id=?", (tid, user.person_id))
    dependents = request.state.store.fetch_all(
        """
        SELECT s.id AS student_id,s.registration_number,p.full_name,p.social_name,gs.relationship,gs.is_legal,gs.is_financial,
               e.id AS enrollment_id,e.state AS enrollment_state,e.enrollment_number,cg.name AS class_group_name,pr.name AS program_name
          FROM guardian_students gs
          JOIN students s ON s.id=gs.student_id
          JOIN people p ON p.id=s.person_id
          LEFT JOIN enrollments e ON e.student_id=s.id AND e.tenant_id=gs.tenant_id AND e.state='active'
          LEFT JOIN class_groups cg ON cg.id=e.class_group_id
          LEFT JOIN programs pr ON pr.id=e.program_id
         WHERE gs.tenant_id=? AND gs.guardian_id=?
         ORDER BY p.full_name
        """,
        (tid, guardian["id"]),
    )
    student_ids = {item["student_id"] for item in dependents}
    installments = request.state.store.fetch_all(
        """
        SELECT DISTINCT i.id,i.sequence,i.competence,i.due_date,i.original_amount,i.discount_amount,i.penalty_amount,
               i.interest_amount,i.paid_amount,i.state,fc.description,e.student_id,p.full_name AS student_name
          FROM installments i
          JOIN financial_contracts fc ON fc.id=i.financial_contract_id
          LEFT JOIN enrollments e ON e.id=fc.enrollment_id
          LEFT JOIN students s ON s.id=e.student_id
          LEFT JOIN people p ON p.id=s.person_id
          LEFT JOIN guardian_students gs ON gs.tenant_id=i.tenant_id AND gs.guardian_id=? AND gs.student_id=e.student_id AND gs.is_financial=1
         WHERE i.tenant_id=? AND (fc.responsible_guardian_id=? OR e.financial_responsible_guardian_id=? OR gs.id IS NOT NULL)
         ORDER BY i.due_date
        """,
        (guardian["id"], tid, guardian["id"], guardian["id"]),
    )
    requests = request.state.store.fetch_all("SELECT * FROM service_requests WHERE tenant_id=? AND requester_person_id=? ORDER BY created_at DESC LIMIT 50", (tid, user.person_id))
    bank_accounts = request.state.store.fetch_all("SELECT id,name,bank_code,pix_key FROM bank_accounts WHERE tenant_id=? AND state='active' AND pix_key IS NOT NULL ORDER BY name", (tid,))
    return {
        "branding": _brand(request.state.store, tid), "person": person, "guardian_id": guardian["id"],
        "dependents": dependents, "installments": installments, "bank_accounts": bank_accounts,
        "notices": _visible_notices(request.state.store, tid, roles=set(user.roles), student_ids=student_ids),
        "requests": requests,
    }


@router.get("/portal/family/dependents/{student_id}", operation_id="get_family_dependent_context")
def family_dependent(student_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"guardian"})
    guardian = guardian_for_user(request, user)
    tid = tenant(user)
    link = request.state.store.fetch_one("SELECT * FROM guardian_students WHERE tenant_id=? AND guardian_id=? AND student_id=?", (tid, guardian["id"], student_id))
    if not link:
        raise DomainError("STUDENT_ACCESS_DENIED", "Dependente não pertence ao responsável autenticado.", 403)
    student = request.state.store.fetch_one("SELECT s.*,p.full_name,p.social_name,p.birth_date FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.id=?", (tid, student_id))
    enrollments = request.state.store.fetch_all("SELECT e.*,cg.name AS class_group_name,pr.name AS program_name FROM enrollments e LEFT JOIN class_groups cg ON cg.id=e.class_group_id JOIN programs pr ON pr.id=e.program_id WHERE e.tenant_id=? AND e.student_id=? ORDER BY e.created_at DESC", (tid, student_id))
    transport = request.state.store.fetch_all("SELECT tr.*,r.name AS route_name,r.vehicle FROM transport_riders tr JOIN transport_routes r ON r.id=tr.route_id WHERE tr.tenant_id=? AND tr.student_id=? AND tr.state='active'", (tid, student_id))
    loans = request.state.store.fetch_all("SELECT l.*,i.title,i.inventory_code FROM library_loans l JOIN library_items i ON i.id=l.library_item_id JOIN students s ON s.person_id=l.person_id WHERE l.tenant_id=? AND s.id=? ORDER BY l.loaned_at DESC", (tid, student_id))
    return {"student": student, "relationship": link, "enrollments": enrollments, "attendance": _attendance_summary(request.state.store, tid, student_id), "transport": transport, "library_loans": loans}


@router.get("/portal/student/me", operation_id="get_student_portal_context")
def student_me(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"student"})
    tid = tenant(user)
    student = student_for_user(request, user)
    person = request.state.store.fetch_one("SELECT id,full_name,social_name,email,phone,birth_date FROM people WHERE tenant_id=? AND id=?", (tid, user.person_id))
    enrollments = request.state.store.fetch_all("SELECT e.*,cg.name AS class_group_name,pr.name AS program_name,ay.name AS academic_year_name FROM enrollments e LEFT JOIN class_groups cg ON cg.id=e.class_group_id JOIN programs pr ON pr.id=e.program_id JOIN academic_years ay ON ay.id=e.academic_year_id WHERE e.tenant_id=? AND e.student_id=? ORDER BY e.created_at DESC", (tid, student["id"]))
    loans = request.state.store.fetch_all("SELECT l.*,i.title,i.inventory_code FROM library_loans l JOIN library_items i ON i.id=l.library_item_id WHERE l.tenant_id=? AND l.person_id=? ORDER BY l.loaned_at DESC", (tid, user.person_id))
    requests = request.state.store.fetch_all("SELECT * FROM service_requests WHERE tenant_id=? AND requester_person_id=? ORDER BY created_at DESC LIMIT 50", (tid, user.person_id))
    transport = request.state.store.fetch_all("SELECT tr.*,r.name AS route_name,r.vehicle,r.stops_json FROM transport_riders tr JOIN transport_routes r ON r.id=tr.route_id WHERE tr.tenant_id=? AND tr.student_id=? AND tr.state='active'", (tid, student["id"]))
    return {"branding": _brand(request.state.store, tid), "person": person, "student": student, "enrollments": enrollments, "attendance": _attendance_summary(request.state.store, tid, student["id"]), "library_loans": loans, "transport": transport, "requests":requests, "notices": _visible_notices(request.state.store, tid, roles=set(user.roles), student_ids={student["id"]})}


@router.get("/portal/teacher/me", operation_id="get_teacher_portal_context")
def teacher_me(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"teacher", "assistant_teacher"})
    tid = tenant(user)
    employee = employee_for_user(request, user)
    person = request.state.store.fetch_one("SELECT id,full_name,social_name,email,phone FROM people WHERE tenant_id=? AND id=?", (tid, user.person_id))
    assignments = request.state.store.fetch_all(
        """SELECT ta.*,
                  cg.name AS class_group_name,cg.unit_id,cg.academic_year_id,cg.program_id,cg.curriculum_id,
                  cc.name AS component_name,u.name AS unit_name,u.institution_id,
                  ay.name AS academic_year_name,pr.name AS program_name,pr.education_level,cu.name AS curriculum_name
             FROM teacher_assignments ta
             JOIN class_groups cg ON cg.id=ta.class_group_id AND cg.tenant_id=ta.tenant_id
             JOIN curriculum_components cc ON cc.id=ta.component_id AND cc.tenant_id=ta.tenant_id
             JOIN units u ON u.id=cg.unit_id AND u.tenant_id=ta.tenant_id
             JOIN academic_years ay ON ay.id=cg.academic_year_id AND ay.tenant_id=ta.tenant_id
             JOIN programs pr ON pr.id=cg.program_id AND pr.tenant_id=ta.tenant_id
             JOIN curricula cu ON cu.id=cg.curriculum_id AND cu.tenant_id=ta.tenant_id
            WHERE ta.tenant_id=? AND ta.employee_id=? AND ta.state='active'
              AND (ta.ends_on IS NULL OR ta.ends_on>=?)
            ORDER BY cg.name,cc.name""",
        (tid, employee["id"], date.today().isoformat()),
    )
    academic_year_ids=sorted({row["academic_year_id"] for row in assignments})
    periods=[]
    if academic_year_ids:
        placeholders=','.join('?' for _ in academic_year_ids)
        periods=request.state.store.fetch_all(
            f"SELECT id,academic_year_id,name,period_type,sequence,starts_on,ends_on,state FROM academic_periods WHERE tenant_id=? AND academic_year_id IN ({placeholders}) AND state='active' ORDER BY starts_on,sequence",
            [tid,*academic_year_ids],
        )
    sessions = request.state.store.fetch_all("SELECT * FROM class_sessions WHERE tenant_id=? ORDER BY scheduled_start DESC LIMIT 500", (tid,))
    sessions = [dict(row) for row in sessions if user.id in json.loads(row["teacher_ids_json"])][:100]
    for row in sessions:
        row["enrolled_student_ids"] = json.loads(row.pop("enrolled_students_json"))
        row["teacher_ids"] = json.loads(row.pop("teacher_ids_json"))
        row["payload"] = json.loads(row.pop("payload_json"))
    return {"branding": _brand(request.state.store, tid), "person": person, "employee": employee, "assignments": assignments, "academic_periods": periods, "sessions": sessions, "notices": _visible_notices(request.state.store, tid, roles=set(user.roles))}




@router.get("/portal/teacher/assignments/{assignment_id}/students", operation_id="get_teacher_assignment_students")
def teacher_assignment_students(assignment_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"teacher", "assistant_teacher"})
    tid=tenant(user);employee=employee_for_user(request,user)
    assignment=request.state.store.fetch_one(
        "SELECT ta.*,cg.academic_year_id,cg.program_id,cg.curriculum_id,pr.education_level "
        "FROM teacher_assignments ta JOIN class_groups cg ON cg.id=ta.class_group_id AND cg.tenant_id=ta.tenant_id "
        "JOIN programs pr ON pr.id=cg.program_id AND pr.tenant_id=ta.tenant_id "
        "WHERE ta.tenant_id=? AND ta.id=? AND ta.employee_id=? AND ta.state='active'",
        (tid,assignment_id,employee["id"]),
    )
    if not assignment:raise DomainError("TEACHER_ASSIGNMENT_NOT_FOUND","Atribuição docente não localizada no escopo da conta.",404)
    items=request.state.store.fetch_all(
        "SELECT s.id AS student_id,s.registration_number,p.full_name,p.social_name,e.id AS enrollment_id "
        "FROM enrollments e JOIN students s ON s.id=e.student_id AND s.tenant_id=e.tenant_id "
        "JOIN people p ON p.id=s.person_id AND p.tenant_id=e.tenant_id "
        "WHERE e.tenant_id=? AND e.class_group_id=? AND e.state='active' ORDER BY p.full_name",
        (tid,assignment["class_group_id"]),
    )
    return {"assignment":assignment,"items":items}


@router.get("/portal/teacher/sessions/{session_id}/roster", operation_id="get_teacher_session_roster")
def teacher_session_roster(session_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"teacher", "assistant_teacher"})
    tid=tenant(user)
    session=request.state.store.fetch_one("SELECT * FROM class_sessions WHERE tenant_id=? AND id=?",(tid,session_id))
    if not session:raise DomainError("CLASS_SESSION_NOT_FOUND","Sessão de aula não localizada.",404)
    teacher_ids=json.loads(session["teacher_ids_json"])
    if user.id not in teacher_ids:raise DomainError("TEACHER_NOT_ASSIGNED","Professor não atribuído a esta sessão.",403)
    student_ids=json.loads(session["enrolled_students_json"])
    if not student_ids:return {"session_id":session_id,"items":[]}
    placeholders=','.join('?' for _ in student_ids)
    rows=request.state.store.fetch_all(f"SELECT s.id AS student_id,s.registration_number,p.full_name,p.social_name FROM students s JOIN people p ON p.id=s.person_id WHERE s.tenant_id=? AND s.id IN ({placeholders}) ORDER BY p.full_name",[tid,*student_ids])
    records=request.state.store.fetch_all("SELECT student_id,status_code,minutes_present,observation,version FROM attendance_records WHERE tenant_id=? AND class_session_id=?",(tid,session_id))
    by_id={r["student_id"]:r for r in records}
    for row in rows:row["attendance"]=by_id.get(row["student_id"])
    call=request.state.store.fetch_one("SELECT id,status,current_version,mode,submitted_at FROM attendance_calls WHERE tenant_id=? AND class_session_id=?",(tid,session_id))
    return {"session_id":session_id,"session_status":session["status"],"session_version":session["version"],"call":call,"items":rows}


@router.get("/portal/kiosk/me", operation_id="get_kiosk_portal_context")
def kiosk_me(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, {"student", "guardian", "employee", "teacher", "assistant_teacher"})
    tid = tenant(user)
    person_id = user.person_id
    if not person_id:
        raise DomainError("PERSON_LINK_REQUIRED", "A conta precisa estar vinculada a uma pessoa.", 403)
    person = request.state.store.fetch_one("SELECT id,full_name,social_name FROM people WHERE tenant_id=? AND id=?", (tid, person_id))
    requests = request.state.store.fetch_all("SELECT id,protocol,request_type,subject,priority,sla_due_at,state,created_at,updated_at FROM service_requests WHERE tenant_id=? AND requester_person_id=? ORDER BY created_at DESC LIMIT 50", (tid, person_id))
    loans = request.state.store.fetch_all("SELECT l.*,i.title FROM library_loans l JOIN library_items i ON i.id=l.library_item_id WHERE l.tenant_id=? AND l.person_id=? ORDER BY l.loaned_at DESC LIMIT 50", (tid, person_id))
    return {"branding": _brand(request.state.store, tid), "person": person, "requests": requests, "library_loans": loans}


@router.get("/portal/timeclock/me", operation_id="get_timeclock_portal_context")
def timeclock_me(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, HR_ROLES | {"employee", "teacher", "assistant_teacher"})
    tid = tenant(user)
    employee = employee_for_user(request, user)
    person = request.state.store.fetch_one("SELECT id,full_name,social_name FROM people WHERE tenant_id=? AND id=?", (tid, user.person_id))
    entries = request.state.store.fetch_all("SELECT * FROM time_entries WHERE tenant_id=? AND employee_id=? ORDER BY occurred_at DESC LIMIT 50", (tid, employee["id"]))
    return {"branding": _brand(request.state.store, tid), "person": person, "employee": employee, "entries": entries}


@router.get("/dashboard/operations", operation_id="get_tenant_operations_dashboard")
def tenant_dashboard(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, ADMIN_ROLES | {"finance_manager", "hr_manager", "inventory_manager", "auditor"})
    tid = tenant(user)
    scalar = request.state.store.scalar
    metrics = {
        "active_students": int(scalar("SELECT COUNT(*) AS n FROM students WHERE tenant_id=? AND state='active'", (tid,)) or 0),
        "active_enrollments": int(scalar("SELECT COUNT(*) AS n FROM enrollments WHERE tenant_id=? AND state='active'", (tid,)) or 0),
        "open_installments": int(scalar("SELECT COUNT(*) AS n FROM installments WHERE tenant_id=? AND state IN ('open','partial')", (tid,)) or 0),
        "open_requests": int(scalar("SELECT COUNT(*) AS n FROM service_requests WHERE tenant_id=? AND state NOT IN ('resolved','closed','cancelled')", (tid,)) or 0),
        "pending_attendance_sessions": int(scalar("SELECT COUNT(*) AS n FROM class_sessions WHERE tenant_id=? AND status IN ('scheduled','started','attendance_open')", (tid,)) or 0),
        "unpublished_outbox": int(scalar("SELECT COUNT(*) AS n FROM outbox_events WHERE tenant_id=? AND published_at IS NULL", (tid,)) or 0),
    }
    recent_audit = request.state.store.fetch_all("SELECT id,actor_id,action,aggregate_type,aggregate_id,reason,correlation_id,created_at FROM audit_log WHERE tenant_id=? ORDER BY created_at DESC LIMIT 20", (tid,))
    outbox = request.state.store.fetch_all("SELECT id,event_type,aggregate_type,aggregate_id,attempts,created_at,published_at FROM outbox_events WHERE tenant_id=? ORDER BY created_at DESC LIMIT 20", (tid,))
    return {"branding": _brand(request.state.store, tid), "metrics": metrics, "recent_audit": recent_audit, "recent_outbox": outbox}
