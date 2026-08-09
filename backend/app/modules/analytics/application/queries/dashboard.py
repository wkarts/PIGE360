from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.analytics.domain.value_objects.period import AnalyticsPeriod


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _number(value: Decimal, digits: int = 2) -> float:
    return float(value.quantize(Decimal(1).scaleb(-digits)))


def _count(store: Any, sql: str, values: tuple[Any, ...]) -> int:
    return int(store.scalar(sql, values) or 0)


def _attendance(store: Any, tenant_id: str, period: AnalyticsPeriod) -> dict[str, Any]:
    rows = store.fetch_all(
        """SELECT ar.status_code,cs.attendance_policy_id,substr(cs.scheduled_start,1,10) AS session_date
           FROM attendance_records ar
           JOIN class_sessions cs ON cs.id=ar.class_session_id AND cs.tenant_id=ar.tenant_id
           WHERE ar.tenant_id=? AND cs.scheduled_start>=? AND cs.scheduled_start<?""",
        (tenant_id, period.start_timestamp, period.end_exclusive_timestamp),
    )
    distribution: dict[str, int] = defaultdict(int)
    policy_cache: dict[tuple[str, str], dict[str, Any]] = {}
    weighted = Decimal("0")
    counted = 0
    for row in rows:
        status = str(row["status_code"])
        distribution[status] += 1
        cache_key = (str(row["attendance_policy_id"]), str(row["session_date"]))
        if cache_key not in policy_cache:
            policy = store.fetch_one(
                """SELECT version,status_effects_json,minimum_percentage
                   FROM attendance_policy_versions
                   WHERE tenant_id=? AND policy_id=? AND effective_from<=?
                     AND (effective_until IS NULL OR effective_until>=?)
                   ORDER BY version DESC LIMIT 1""",
                (tenant_id, cache_key[0], cache_key[1], cache_key[1]),
            )
            if policy:
                policy_cache[cache_key] = {
                    "version": int(policy["version"]),
                    "minimum_percentage": str(policy["minimum_percentage"]),
                    "effects": json.loads(policy["status_effects_json"] or "{}"),
                }
            else:
                policy_cache[cache_key] = {"version": None, "minimum_percentage": None, "effects": {}}
        effect = policy_cache[cache_key]["effects"].get(status)
        if effect is not None:
            weighted += _decimal(effect)
            counted += 1
    percentage = (weighted / Decimal(counted) * Decimal("100")) if counted else Decimal("0")
    return {
        "records": len(rows),
        "counted_records": counted,
        "presence_percentage": _number(percentage),
        "by_status": [{"status": key, "count": distribution[key]} for key in sorted(distribution)],
        "policy_aware": True,
    }


def academic_snapshot(store: Any, tenant_id: str, period: AnalyticsPeriod) -> dict[str, Any]:
    attendance = _attendance(store, tenant_id, period)
    enrollments_by_class = store.fetch_all(
        """SELECT cg.name AS label,COUNT(e.id) AS value
           FROM enrollments e
           LEFT JOIN class_groups cg ON cg.id=e.class_group_id AND cg.tenant_id=e.tenant_id
           WHERE e.tenant_id=? AND e.state='active'
           GROUP BY cg.id,cg.name ORDER BY value DESC,label LIMIT 30""",
        (tenant_id,),
    )
    plans_by_status = store.fetch_all(
        """SELECT status AS label,COUNT(*) AS value FROM teaching_plans
           WHERE tenant_id=? AND start_date<=? AND end_date>=?
           GROUP BY status ORDER BY value DESC,label""",
        (tenant_id, period.end_text, period.start_text),
    )
    executions = store.fetch_one(
        """SELECT COUNT(*) AS total,
                  COALESCE(AVG(completion_percentage),0) AS average_completion
           FROM lesson_plan_execution_records
           WHERE tenant_id=? AND executed_at>=? AND executed_at<?""",
        (tenant_id, period.start_timestamp, period.end_exclusive_timestamp),
    ) or {"total": 0, "average_completion": 0}
    return {
        "active_students": _count(store, "SELECT COUNT(*) FROM students WHERE tenant_id=? AND state='active'", (tenant_id,)),
        "active_enrollments": _count(store, "SELECT COUNT(*) FROM enrollments WHERE tenant_id=? AND state='active'", (tenant_id,)),
        "attendance": attendance,
        "lesson_executions": {"count": int(executions["total"] or 0), "average_completion": _number(_decimal(executions["average_completion"]))},
        "enrollments_by_class": enrollments_by_class,
        "teaching_plans_by_status": plans_by_status,
    }


def finance_snapshot(store: Any, tenant_id: str, period: AnalyticsPeriod) -> dict[str, Any]:
    open_row = store.fetch_one(
        """SELECT COUNT(*) AS count,
                  COALESCE(SUM(CAST(original_amount AS NUMERIC)+CAST(penalty_amount AS NUMERIC)+CAST(interest_amount AS NUMERIC)-CAST(discount_amount AS NUMERIC)-CAST(paid_amount AS NUMERIC)),0) AS balance
           FROM installments WHERE tenant_id=? AND state IN ('open','partial')""",
        (tenant_id,),
    ) or {"count": 0, "balance": 0}
    overdue = store.fetch_one(
        """SELECT COUNT(*) AS count,
                  COALESCE(SUM(CAST(original_amount AS NUMERIC)+CAST(penalty_amount AS NUMERIC)+CAST(interest_amount AS NUMERIC)-CAST(discount_amount AS NUMERIC)-CAST(paid_amount AS NUMERIC)),0) AS balance
           FROM installments WHERE tenant_id=? AND state IN ('open','partial') AND due_date<?""",
        (tenant_id, period.end_text),
    ) or {"count": 0, "balance": 0}
    payments = store.fetch_one(
        "SELECT COUNT(*) AS count,COALESCE(SUM(amount),0) AS total FROM payments WHERE tenant_id=? AND state='confirmed' AND paid_at>=? AND paid_at<?",
        (tenant_id, period.start_timestamp, period.end_exclusive_timestamp),
    ) or {"count": 0, "total": 0}
    sales = store.fetch_one(
        "SELECT COUNT(*) AS count,COALESCE(SUM(total_amount),0) AS total FROM sales WHERE tenant_id=? AND state='completed' AND created_at>=? AND created_at<?",
        (tenant_id, period.start_timestamp, period.end_exclusive_timestamp),
    ) or {"count": 0, "total": 0}
    receivables_by_month = store.fetch_all(
        """SELECT substr(due_date,1,7) AS label,
                  COUNT(*) AS count,
                  COALESCE(SUM(CAST(original_amount AS NUMERIC)-CAST(discount_amount AS NUMERIC)-CAST(paid_amount AS NUMERIC)),0) AS value
           FROM installments WHERE tenant_id=? AND due_date>=? AND due_date<=?
           GROUP BY substr(due_date,1,7) ORDER BY label""",
        (tenant_id, period.start_text, period.end_text),
    )
    sales_by_day = store.fetch_all(
        """SELECT substr(created_at,1,10) AS label,COUNT(*) AS count,COALESCE(SUM(total_amount),0) AS value
           FROM sales WHERE tenant_id=? AND state='completed' AND created_at>=? AND created_at<?
           GROUP BY substr(created_at,1,10) ORDER BY label""",
        (tenant_id, period.start_timestamp, period.end_exclusive_timestamp),
    )
    return {
        "open_receivables": {"count": int(open_row["count"] or 0), "balance": _number(_decimal(open_row["balance"]))},
        "overdue_receivables": {"count": int(overdue["count"] or 0), "balance": _number(_decimal(overdue["balance"]))},
        "confirmed_payments": {"count": int(payments["count"] or 0), "total": _number(_decimal(payments["total"]))},
        "sales": {"count": int(sales["count"] or 0), "total": _number(_decimal(sales["total"]))},
        "receivables_by_month": receivables_by_month,
        "sales_by_day": sales_by_day,
    }


def operations_snapshot(store: Any, tenant_id: str, period: AnalyticsPeriod) -> dict[str, Any]:
    requests_by_state = store.fetch_all(
        "SELECT state AS label,COUNT(*) AS value FROM service_requests WHERE tenant_id=? GROUP BY state ORDER BY value DESC,label",
        (tenant_id,),
    )
    open_requests = _count(store, "SELECT COUNT(*) FROM service_requests WHERE tenant_id=? AND state NOT IN ('resolved','closed','cancelled')", (tenant_id,))
    overdue_requests = _count(store, "SELECT COUNT(*) FROM service_requests WHERE tenant_id=? AND state NOT IN ('resolved','closed','cancelled') AND sla_due_at IS NOT NULL AND sla_due_at<?", (tenant_id, period.end_exclusive_timestamp))
    latest_payroll = store.fetch_one(
        "SELECT competence,state,gross_total,deductions_total,net_total FROM payroll_runs WHERE tenant_id=? ORDER BY competence DESC,created_at DESC LIMIT 1",
        (tenant_id,),
    )
    inventory = store.fetch_one(
        "SELECT COUNT(*) AS positions,COALESCE(SUM(quantity),0) AS quantity FROM stock_balances WHERE tenant_id=?",
        (tenant_id,),
    ) or {"positions": 0, "quantity": 0}
    outbox_pending = _count(store, "SELECT COUNT(*) FROM outbox_events WHERE tenant_id=? AND published_at IS NULL", (tenant_id,))
    return {
        "service_requests": {"open": open_requests, "sla_overdue": overdue_requests, "by_state": requests_by_state},
        "latest_payroll": latest_payroll,
        "inventory": {"positions": int(inventory["positions"] or 0), "quantity": _number(_decimal(inventory["quantity"]))},
        "outbox_pending": outbox_pending,
    }


def overview(store: Any, tenant_id: str, period: AnalyticsPeriod) -> dict[str, Any]:
    return {
        "period": {"from": period.start_text, "to": period.end_text},
        "academic": academic_snapshot(store, tenant_id, period),
        "finance": finance_snapshot(store, tenant_id, period),
        "operations": operations_snapshot(store, tenant_id, period),
    }
