"""Compatibilidade temporária para os routers ainda em extração.

Novos domínios não devem importar este módulo. Ele será removido quando
academic_core.py e community_operations.py forem totalmente decompostos.
"""
from __future__ import annotations

from app.shared.application.sql import bool_int as boolint
from app.shared.application.sql import dumps, loads, row_or_404
from app.shared.domain.money import money as dec
from app.shared.security.authorization import (
    ADMIN_ROLES,
    FINANCE_ROLES,
    FISCAL_ROLES,
    HR_ROLES,
    INTEGRATION_ROLES,
    SALES_ROLES,
    require_roles as require,
    tenant_id as tenant,
)

__all__ = [
    "ADMIN_ROLES",
    "FINANCE_ROLES",
    "FISCAL_ROLES",
    "HR_ROLES",
    "INTEGRATION_ROLES",
    "SALES_ROLES",
    "boolint",
    "dec",
    "dumps",
    "loads",
    "require",
    "row_or_404",
    "tenant",
]
