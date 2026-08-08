from __future__ import annotations

from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

ADMIN_ROLES = {"tenant_owner", "institution_director", "unit_manager", "secretary", "academic_coordinator"}
FINANCE_ROLES = {"tenant_owner", "institution_director", "finance_manager", "finance_operator"}
HR_ROLES = {"tenant_owner", "institution_director", "hr_manager", "personnel_operator", "payroll_operator", "timekeeping_operator"}
SALES_ROLES = {"tenant_owner", "institution_director", "canteen_manager", "pos_operator", "inventory_manager"}
INTEGRATION_ROLES = {"tenant_owner", "institution_director", "support", "auditor"}
FISCAL_ROLES = {"tenant_owner", "institution_director", "fiscal_manager", "finance_manager"}


def tenant_id(user: CurrentUser) -> str:
    if user.plane != "tenant" or not user.tenant_id:
        raise DomainError(
            "TENANT_ROUTE_REQUIRED",
            "Rota disponível somente no domínio da instituição.",
            404,
        )
    return user.tenant_id


def require_roles(user: CurrentUser, roles: set[str]) -> None:
    tenant_id(user)
    if not set(user.roles).intersection(roles):
        raise DomainError(
            "PERMISSION_DENIED",
            "Permissão insuficiente para esta operação.",
            403,
            "Acesso negado",
        )
