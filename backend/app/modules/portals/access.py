from __future__ import annotations

from typing import Any

from fastapi import Request

from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

ADMIN_ATTENDANCE_ROLES = {"tenant_owner", "institution_director", "academic_coordinator", "secretary", "auditor"}


def tenant_id(user: CurrentUser) -> str:
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError("TENANT_ROUTE_REQUIRED", "Rota disponível somente no domínio da instituição.", 404)
    return user.tenant_id


def require_person(user: CurrentUser) -> str:
    if not user.person_id:
        raise DomainError(
            "PERSON_LINK_REQUIRED",
            "A conta precisa estar vinculada ao cadastro único de pessoa para acessar este recurso.",
            403,
            "Vínculo cadastral necessário",
        )
    return user.person_id


def guardian_for_user(request: Request, user: CurrentUser) -> dict[str, Any]:
    tid = tenant_id(user)
    person_id = require_person(user)
    row = request.state.store.fetch_one(
        "SELECT * FROM guardians WHERE tenant_id=? AND person_id=? AND state='active'",
        (tid, person_id),
    )
    if not row:
        raise DomainError("GUARDIAN_LINK_REQUIRED", "A conta não está vinculada a um responsável ativo.", 403)
    return row


def student_for_user(request: Request, user: CurrentUser) -> dict[str, Any]:
    tid = tenant_id(user)
    person_id = require_person(user)
    row = request.state.store.fetch_one(
        "SELECT * FROM students WHERE tenant_id=? AND person_id=? AND state='active'",
        (tid, person_id),
    )
    if not row:
        raise DomainError("STUDENT_LINK_REQUIRED", "A conta não está vinculada a um aluno ativo.", 403)
    return row


def employee_for_user(request: Request, user: CurrentUser) -> dict[str, Any]:
    tid = tenant_id(user)
    person_id = require_person(user)
    row = request.state.store.fetch_one(
        "SELECT * FROM employees WHERE tenant_id=? AND person_id=? AND state='active'",
        (tid, person_id),
    )
    if not row:
        raise DomainError("EMPLOYEE_LINK_REQUIRED", "A conta não está vinculada a um colaborador ativo.", 403)
    return row


def guardian_can_access_student(request: Request, user: CurrentUser, student_id: str, *, financial_only: bool = False) -> bool:
    guardian = guardian_for_user(request, user)
    tid = tenant_id(user)
    sql = "SELECT id FROM guardian_students WHERE tenant_id=? AND guardian_id=? AND student_id=?"
    params: list[Any] = [tid, guardian["id"], student_id]
    if financial_only:
        sql += " AND is_financial=1"
    return bool(request.state.store.fetch_one(sql, params))


def teacher_can_access_student(request: Request, user: CurrentUser, student_id: str) -> bool:
    employee = employee_for_user(request, user)
    tid = tenant_id(user)
    today = __import__("datetime").date.today().isoformat()
    row = request.state.store.fetch_one(
        """
        SELECT 1 AS allowed
          FROM teacher_assignments ta
          JOIN enrollments e ON e.class_group_id=ta.class_group_id
         WHERE ta.tenant_id=? AND ta.employee_id=? AND ta.state='active'
           AND ta.starts_on<=? AND (ta.ends_on IS NULL OR ta.ends_on>=?)
           AND e.tenant_id=? AND e.student_id=? AND e.state='active'
         LIMIT 1
        """,
        (tid, employee["id"], today, today, tid, student_id),
    )
    return bool(row)


def assert_student_access(request: Request, user: CurrentUser, student_id: str) -> None:
    tid = tenant_id(user)
    if request.state.store.fetch_one("SELECT id FROM students WHERE tenant_id=? AND id=?", (tid, student_id)) is None:
        raise DomainError("STUDENT_NOT_FOUND", "Aluno não localizado.", 404)
    roles = set(user.roles)
    if roles.intersection(ADMIN_ATTENDANCE_ROLES):
        return
    if "student" in roles:
        student = student_for_user(request, user)
        if student["id"] == student_id:
            return
    if "guardian" in roles and guardian_can_access_student(request, user, student_id):
        return
    if roles.intersection({"teacher", "assistant_teacher"}) and teacher_can_access_student(request, user, student_id):
        return
    raise DomainError("STUDENT_ACCESS_DENIED", "O aluno informado não pertence ao escopo desta conta.", 403)


def assert_financial_installment_access(request: Request, user: CurrentUser, installment_id: str) -> dict[str, Any]:
    tid = tenant_id(user)
    row = request.state.store.fetch_one(
        """
        SELECT i.*, fc.enrollment_id, fc.responsible_guardian_id,
               e.student_id, e.financial_responsible_guardian_id
          FROM installments i
          JOIN financial_contracts fc ON fc.id=i.financial_contract_id
          LEFT JOIN enrollments e ON e.id=fc.enrollment_id
         WHERE i.tenant_id=? AND i.id=?
        """,
        (tid, installment_id),
    )
    if not row:
        raise DomainError("INSTALLMENT_NOT_FOUND", "Parcela não localizada.", 404)
    if "guardian" not in user.roles:
        return row
    guardian = guardian_for_user(request, user)
    direct = row.get("responsible_guardian_id") == guardian["id"] or row.get("financial_responsible_guardian_id") == guardian["id"]
    linked = bool(row.get("student_id")) and guardian_can_access_student(request, user, row["student_id"], financial_only=True)
    if not (direct or linked):
        raise DomainError("INSTALLMENT_ACCESS_DENIED", "A parcela não pertence ao responsável financeiro autenticado.", 403)
    return row


def assert_class_access(request: Request, user: CurrentUser, class_group_id: str) -> None:
    tid = tenant_id(user)
    roles = set(user.roles)
    if roles.intersection(ADMIN_ATTENDANCE_ROLES):
        return
    if roles.intersection({"teacher", "assistant_teacher"}):
        employee = employee_for_user(request, user)
        row = request.state.store.fetch_one(
            "SELECT id FROM teacher_assignments WHERE tenant_id=? AND employee_id=? AND class_group_id=? AND state='active' LIMIT 1",
            (tid, employee["id"], class_group_id),
        )
        if row:
            return
    raise DomainError("CLASS_ACCESS_DENIED", "A turma informada não pertence ao escopo desta conta.", 403)
