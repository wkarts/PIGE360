from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.modules.analytics.application.queries.dashboard import academic_snapshot, finance_snapshot, operations_snapshot, overview
from app.modules.analytics.domain.value_objects.period import AnalyticsPeriod
from app.shared.security.auth import CurrentUser, current_user
from app.shared.security.authorization import ADMIN_ROLES, FINANCE_ROLES, HR_ROLES, SALES_ROLES, require_roles, tenant_id

router = APIRouter(tags=["analytics"])
ANALYTICS_ROLES = ADMIN_ROLES | FINANCE_ROLES | HR_ROLES | SALES_ROLES | {"auditor", "fiscal_manager"}


def _context(user: CurrentUser, start: str | None, end: str | None) -> tuple[str, AnalyticsPeriod]:
    require_roles(user, ANALYTICS_ROLES)
    return tenant_id(user), AnalyticsPeriod.parse(start, end)


@router.get("/analytics/overview", operation_id="get_analytics_overview")
def get_overview(
    request: Request,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    user: CurrentUser = Depends(current_user),
):
    tid, period = _context(user, from_date, to_date)
    return overview(request.state.store, tid, period)


@router.get("/analytics/academic", operation_id="get_academic_analytics")
def get_academic(
    request: Request,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    user: CurrentUser = Depends(current_user),
):
    tid, period = _context(user, from_date, to_date)
    return {"period": {"from": period.start_text, "to": period.end_text}, **academic_snapshot(request.state.store, tid, period)}


@router.get("/analytics/finance", operation_id="get_finance_analytics")
def get_finance(
    request: Request,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    user: CurrentUser = Depends(current_user),
):
    tid, period = _context(user, from_date, to_date)
    return {"period": {"from": period.start_text, "to": period.end_text}, **finance_snapshot(request.state.store, tid, period)}


@router.get("/analytics/operations", operation_id="get_operations_analytics")
def get_operations(
    request: Request,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    user: CurrentUser = Depends(current_user),
):
    tid, period = _context(user, from_date, to_date)
    return {"period": {"from": period.start_text, "to": period.end_text}, **operations_snapshot(request.state.store, tid, period)}
