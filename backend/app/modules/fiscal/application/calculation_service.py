from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from fastapi import Request

from app.modules.fiscal.application.context_service import fiscal_context_snapshot_by_version
from app.modules.fiscal.application.strategy_service import resolve_strategies, apply_strategies
from app.modules.fiscal.presentation.calculation_schemas import (
    FiscalTaxRuleSetCreate,
    FiscalTaxRuleVersionCreate,
    FiscalTaxRuleVersionPublish,
    FiscalTaxSimulationInput,
)
from app.modules.operations.common import dumps, loads
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

CENT = Decimal("0.01")
ZERO = Decimal("0")
EFFECTIVE_STATES = {"published", "scheduled", "superseded"}
NON_TAXING = {"exempt", "immune", "non_incident", "zero_rate"}


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _one(conn: sqlite3.Connection, sql: str, params: Iterable[Any], code: str, detail: str) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, detail, 404)
    return dict(row)


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _audit(conn, *, tenant_id: str, user: CurrentUser, request: Request, action: str, aggregate_type: str, aggregate_id: str, before=None, after=None, reason=None):
    add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action=action, aggregate_type=aggregate_type,
              aggregate_id=aggregate_id, correlation_id=request.state.correlation_id, before=before, after=after, reason=reason)


def _event(conn, *, tenant_id: str, request: Request, event_type: str, aggregate_type: str, aggregate_id: str, payload: Any):
    add_outbox(conn, tenant_id=tenant_id, event_type=event_type, aggregate_type=aggregate_type,
               aggregate_id=aggregate_id, payload=payload, correlation_id=request.state.correlation_id)


def _ruleset_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status"] = out.get("state")
    return out


def _version_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["components"] = loads(out.pop("components_json", "[]"), [])
    out["legal_basis"] = loads(out.pop("legal_basis_json", "[]"), [])
    out["status"] = out.get("state")
    return out


def list_tax_rule_sets(request: Request, tenant_id: str, *, fiscal_context_id: str | None = None, status: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM fiscal_tax_rule_sets WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if fiscal_context_id:
        sql += " AND fiscal_context_id=?"; params.append(fiscal_context_id)
    if status:
        sql += " AND state=?"; params.append(status)
    sql += " ORDER BY priority DESC,code,id"
    items = [_ruleset_payload(row) for row in request.state.store.fetch_all(sql, params)]
    for item in items:
        item["active_version"] = request.state.store.fetch_one(
            "SELECT id,version_number,version_label,valid_from,valid_until,state,source_sha256 FROM fiscal_tax_rule_versions WHERE tenant_id=? AND id=?",
            (tenant_id, item["active_version_id"]),
        ) if item.get("active_version_id") else None
    return {"items": items}


def create_tax_rule_set(data: FiscalTaxRuleSetCreate, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json"); scope = f"fiscal-tax-ruleset:create:{tenant_id}"; now = iso_now()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
        if cached: return cached
        _one(conn, "SELECT id FROM fiscal_contexts WHERE tenant_id=? AND id=? AND state='active'", (tenant_id, data.fiscal_context_id), "FISCAL_CONTEXT_NOT_FOUND", "Contexto fiscal não localizado.")
        exists = conn.execute("SELECT id FROM fiscal_tax_rule_sets WHERE tenant_id=? AND code=?", (tenant_id, data.code)).fetchone()
        if exists: raise DomainError("FISCAL_TAX_RULE_SET_EXISTS", "Já existe conjunto tributário com este código.", 409)
        rid = uuid7()
        conn.execute(
            "INSERT INTO fiscal_tax_rule_sets(id,tenant_id,fiscal_context_id,code,name,description,establishment_code,operation_type,item_kind,tax_regime,rtc_mode,priority,state,active_version_id,latest_version_number,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, tenant_id, data.fiscal_context_id, data.code, data.name, data.description, data.establishment_code,
             data.operation_type, data.item_kind, data.tax_regime, data.rtc_mode, data.priority, "active", None, 0, 1, user.id, now, now),
        )
        result = {"id": rid, **body, "status": "active", "active_version_id": None, "latest_version_number": 0, "version": 1, "created_at": now, "updated_at": now}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create", aggregate_type="fiscal_tax_rule_set", aggregate_id=rid, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalTaxRuleSetCreated", aggregate_type="fiscal_tax_rule_set", aggregate_id=rid, payload=result)
        save_idempotent(conn, scope, key, body, 201, result)
        return 201, result


def tax_rule_set_detail(request: Request, tenant_id: str, rule_set_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        row = _one(conn, "SELECT * FROM fiscal_tax_rule_sets WHERE tenant_id=? AND id=?", (tenant_id, rule_set_id), "FISCAL_TAX_RULE_SET_NOT_FOUND", "Conjunto tributário não localizado.")
        out = _ruleset_payload(row)
        versions = conn.execute("SELECT * FROM fiscal_tax_rule_versions WHERE tenant_id=? AND fiscal_tax_rule_set_id=? ORDER BY version_number DESC", (tenant_id, rule_set_id)).fetchall()
        out["versions"] = [_version_payload(dict(v)) for v in versions]
        return out


def create_tax_rule_version(rule_set_id: str, data: FiscalTaxRuleVersionCreate, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json"); scope = f"fiscal-tax-rule-version:create:{tenant_id}:{rule_set_id}"; now = iso_now()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
        if cached: return cached
        rule_set = _one(conn, "SELECT * FROM fiscal_tax_rule_sets WHERE tenant_id=? AND id=?", (tenant_id, rule_set_id), "FISCAL_TAX_RULE_SET_NOT_FOUND", "Conjunto tributário não localizado.")
        if int(rule_set["version"]) != data.expected_rule_set_version:
            raise DomainError("FISCAL_TAX_RULE_SET_VERSION_CONFLICT", "O conjunto tributário foi alterado por outra operação.", 409)
        number = int(rule_set["latest_version_number"]) + 1
        components = [component.model_dump(mode="json") for component in data.components]
        source_sha = data.source_sha256 or _digest({"components": components, "legal_basis": data.legal_basis, "source": data.source_reference})
        vid = uuid7()
        conn.execute(
            "INSERT INTO fiscal_tax_rule_versions(id,tenant_id,fiscal_tax_rule_set_id,version_number,version_label,valid_from,valid_until,source_name,source_reference,source_sha256,legal_basis_json,components_json,notes,state,published_at,published_by,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, tenant_id, rule_set_id, number, data.version_label, data.valid_from.isoformat(), data.valid_until.isoformat() if data.valid_until else None,
             data.source_name, data.source_reference, source_sha, dumps(data.legal_basis), dumps(components), data.notes, "draft", None, None, 1, user.id, now, now),
        )
        conn.execute("UPDATE fiscal_tax_rule_sets SET latest_version_number=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (number, now, tenant_id, rule_set_id))
        result = _version_payload(_one(conn, "SELECT * FROM fiscal_tax_rule_versions WHERE tenant_id=? AND id=?", (tenant_id, vid), "X", "X"))
        result["rule_set_version"] = int(rule_set["version"]) + 1
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create_version", aggregate_type="fiscal_tax_rule_set", aggregate_id=rule_set_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalTaxRuleVersionCreated", aggregate_type="fiscal_tax_rule_set", aggregate_id=rule_set_id, payload={"version_id": vid, "version_number": number, "source_sha256": source_sha})
        save_idempotent(conn, scope, key, body, 201, result)
        return 201, result


def publish_tax_rule_version(rule_set_id: str, version_id: str, data: FiscalTaxRuleVersionPublish, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json"); scope = f"fiscal-tax-rule-version:publish:{tenant_id}:{version_id}"; now = iso_now(); today = date.today().isoformat()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
        if cached: return cached
        rule_set = _one(conn, "SELECT * FROM fiscal_tax_rule_sets WHERE tenant_id=? AND id=?", (tenant_id, rule_set_id), "FISCAL_TAX_RULE_SET_NOT_FOUND", "Conjunto tributário não localizado.")
        version = _one(conn, "SELECT * FROM fiscal_tax_rule_versions WHERE tenant_id=? AND id=? AND fiscal_tax_rule_set_id=?", (tenant_id, version_id, rule_set_id), "FISCAL_TAX_RULE_VERSION_NOT_FOUND", "Versão tributária não localizada.")
        if int(rule_set["version"]) != data.expected_rule_set_version or int(version["version"]) != data.expected_version:
            raise DomainError("FISCAL_TAX_RULE_VERSION_CONFLICT", "A versão tributária foi alterada por outra operação.", 409)
        if version["state"] not in {"draft", "scheduled"}:
            if version["state"] in EFFECTIVE_STATES:
                result = _version_payload(version); save_idempotent(conn, scope, key, body, 200, result); return 200, result
            raise DomainError("FISCAL_TAX_RULE_VERSION_STATE", "Somente versão em rascunho pode ser publicada.", 409)
        overlapping = conn.execute(
            "SELECT id FROM fiscal_tax_rule_versions WHERE tenant_id=? AND fiscal_tax_rule_set_id=? AND id<>? AND state IN ('published','scheduled') AND valid_from<=COALESCE(?, '9999-12-31') AND COALESCE(valid_until,'9999-12-31')>=? LIMIT 1",
            (tenant_id, rule_set_id, version_id, version.get("valid_until"), version["valid_from"]),
        ).fetchone()
        if overlapping:
            raise DomainError("FISCAL_TAX_RULE_PERIOD_OVERLAP", "Já existe versão tributária publicada com vigência sobreposta.", 409)
        target_state = "published" if version["valid_from"] <= today else "scheduled"
        conn.execute("UPDATE fiscal_tax_rule_versions SET state=?,published_at=?,published_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (target_state, now, user.id, now, tenant_id, version_id))
        if target_state == "published":
            conn.execute("UPDATE fiscal_tax_rule_sets SET active_version_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?", (version_id, now, tenant_id, rule_set_id))
        result = _version_payload(_one(conn, "SELECT * FROM fiscal_tax_rule_versions WHERE tenant_id=? AND id=?", (tenant_id, version_id), "X", "X"))
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="publish_version", aggregate_type="fiscal_tax_rule_set", aggregate_id=rule_set_id, before=_version_payload(version), after=result, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type=("FiscalTaxRuleVersionPublished" if target_state == "published" else "FiscalTaxRuleVersionScheduled"), aggregate_type="fiscal_tax_rule_set", aggregate_id=rule_set_id, payload={"version_id": version_id, "state": target_state})
        save_idempotent(conn, scope, key, body, 200, result)
        return 200, result


def _context_version(conn: sqlite3.Connection, tenant_id: str, context_id: str, occurred_on: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT v.*,c.code AS context_code,c.cnpj,c.establishment_name FROM fiscal_context_versions v JOIN fiscal_contexts c ON c.id=v.fiscal_context_id AND c.tenant_id=v.tenant_id WHERE v.tenant_id=? AND v.fiscal_context_id=? AND c.state='active' AND v.state IN ('published','scheduled','superseded') AND v.valid_from<=? AND (v.valid_until IS NULL OR v.valid_until>=?) ORDER BY v.valid_from DESC,v.version_number DESC LIMIT 1",
        (tenant_id, context_id, occurred_on, occurred_on),
    ).fetchone()
    if not row:
        raise DomainError("FISCAL_CONTEXT_NOT_EFFECTIVE", "Não existe versão de contexto fiscal vigente na data da operação.", 404)
    return dict(row)


def _resolve_rule_version(conn: sqlite3.Connection, tenant_id: str, data: FiscalTaxSimulationInput, context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    target = data.occurred_on.isoformat()
    rows = conn.execute(
        "SELECT rs.*,v.id AS rule_version_id,v.version_number AS rule_version_number,v.version_label,v.valid_from,v.valid_until,v.source_name,v.source_reference,v.source_sha256,v.legal_basis_json,v.components_json,v.state AS version_state "
        "FROM fiscal_tax_rule_sets rs JOIN fiscal_tax_rule_versions v ON v.fiscal_tax_rule_set_id=rs.id AND v.tenant_id=rs.tenant_id "
        "WHERE rs.tenant_id=? AND rs.fiscal_context_id=? AND rs.state='active' AND v.state IN ('published','scheduled','superseded') "
        "AND v.valid_from<=? AND (v.valid_until IS NULL OR v.valid_until>=?) "
        "AND (rs.establishment_code=? OR rs.establishment_code IS NULL) "
        "AND (rs.operation_type=? OR rs.operation_type='any') AND (rs.item_kind=? OR rs.item_kind='any') "
        "AND (rs.tax_regime=? OR rs.tax_regime='any') AND (rs.rtc_mode=? OR rs.rtc_mode='any')",
        (tenant_id, data.fiscal_context_id, target, target, data.establishment_code, data.operation_type, data.item_kind, context["tax_regime"], context["rtc_mode"]),
    ).fetchall()
    if not rows:
        raise DomainError("FISCAL_TAX_RULE_NOT_RESOLVED", "Nenhuma regra tributária versionada corresponde ao contexto da operação.", 404)
    def score(row: sqlite3.Row) -> tuple[int, int, str, int]:
        r = dict(row); points = int(r["priority"]) * 100
        points += 32 if r.get("establishment_code") == data.establishment_code and data.establishment_code else 0
        points += 16 if r["operation_type"] == data.operation_type else 0
        points += 8 if r["item_kind"] == data.item_kind else 0
        points += 4 if r["tax_regime"] == context["tax_regime"] else 0
        points += 2 if r["rtc_mode"] == context["rtc_mode"] else 0
        return points, int(r["rule_version_number"]), r["valid_from"], int(r["version"])
    ordered = sorted(rows, key=score, reverse=True)
    top_score = score(ordered[0])
    tied = [row for row in ordered if score(row) == top_score]
    if len({dict(row)["id"] for row in tied}) > 1:
        raise DomainError("FISCAL_TAX_RULE_AMBIGUOUS", "Mais de uma regra tributária possui a mesma precedência.", 409)
    selected = dict(ordered[0])
    version = {"id": selected.pop("rule_version_id"), "version_number": selected.pop("rule_version_number"), "version_label": selected.pop("version_label"), "valid_from": selected.pop("valid_from"), "valid_until": selected.pop("valid_until"), "source_name": selected.pop("source_name"), "source_reference": selected.pop("source_reference"), "source_sha256": selected.pop("source_sha256"), "legal_basis": loads(selected.pop("legal_basis_json"), []), "components": loads(selected.pop("components_json"), []), "status": selected.pop("version_state")}
    return selected, version


def _resolve_classification(conn: sqlite3.Connection, tenant_id: str, data: FiscalTaxSimulationInput) -> dict[str, Any] | None:
    if not data.item_id:
        return None
    target = data.occurred_on.isoformat()
    rows = conn.execute(
        "SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND fiscal_context_id=? AND state='published' AND item_kind=? AND (item_id=? OR item_id IS NULL) AND operation_type=? AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) AND (establishment_code=? OR establishment_code IS NULL) ORDER BY CASE WHEN item_id=? THEN 0 ELSE 1 END,CASE WHEN establishment_code=? THEN 0 ELSE 1 END,priority DESC,valid_from DESC LIMIT 1",
        (tenant_id, data.fiscal_context_id, data.item_kind, data.item_id, data.operation_type, target, target, data.establishment_code, data.item_id, data.establishment_code),
    ).fetchone()
    if not rows: return None
    result = dict(rows); result["tax_configuration"] = loads(result.pop("tax_configuration_json", "{}"), {})
    return result


def _base_for_component(component: dict[str, Any], data: FiscalTaxSimulationInput, taxes: dict[str, dict[str, Any]]) -> tuple[Decimal, list[dict[str, Any]]]:
    gross = _decimal(data.amount) + _decimal(data.freight) + _decimal(data.insurance) + _decimal(data.other_amount) - _decimal(data.discount)
    steps: list[dict[str, Any]] = [{"step": "operation_total", "value": str(_money(gross))}]
    if component["base_mode"] == "custom":
        key = component.get("custom_base_key")
        base = _decimal(data.custom_bases.get(key or "", ZERO)); steps.append({"step": "custom_base", "key": key, "value": str(_money(base))})
    elif component["base_mode"] == "mva":
        base = gross * (Decimal("1") + _decimal(component.get("mva_pct")) / Decimal("100")); steps.append({"step": "mva", "rate_pct": str(component.get("mva_pct", 0)), "value": str(_money(base))})
    else:
        base = gross
    for key in component.get("include_amount_keys", []):
        amount = _decimal(data.custom_amounts.get(key, ZERO)); base += amount; steps.append({"step": "include_amount", "key": key, "value": str(_money(amount))})
    for key in component.get("deduct_amount_keys", []):
        amount = _decimal(data.custom_amounts.get(key, ZERO)); base -= amount; steps.append({"step": "deduct_amount", "key": key, "value": str(_money(amount))})
    reduction = _decimal(component.get("base_reduction_pct"))
    if reduction:
        before = base; base = base * (Decimal("1") - reduction / Decimal("100")); steps.append({"step": "base_reduction", "rate_pct": str(reduction), "before": str(_money(before)), "value": str(_money(base))})
    return max(base, ZERO), steps


def _calculate_component(component: dict[str, Any], data: FiscalTaxSimulationInput, taxes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    incidence = component["incidence"]
    base, steps = _base_for_component(component, data, taxes)
    rate = _decimal(component.get("rate_pct"))
    gross_tax = ZERO
    if incidence in NON_TAXING or incidence == "suspended":
        gross_tax = ZERO
    elif incidence == "monophase" and component.get("monophase_amount_per_unit") is not None:
        gross_tax = _decimal(component["monophase_amount_per_unit"]) * _decimal(data.quantity)
        steps.append({"step": "monophase_per_unit", "quantity": str(data.quantity), "amount_per_unit": str(component["monophase_amount_per_unit"])})
    else:
        gross_tax = base * rate / Decimal("100")
        steps.append({"step": "rate", "rate_pct": str(rate), "value": str(_money(gross_tax))})
    deductions = ZERO
    for tax_code in component.get("deduct_tax_codes", []):
        deduction = _decimal(taxes.get(tax_code, {}).get("amount", ZERO)); deductions += deduction
        steps.append({"step": "deduct_tax", "tax": tax_code, "value": str(_money(deduction))})
    gross_tax = max(gross_tax - deductions, ZERO)
    deferred = ZERO; suspended = ZERO
    if incidence == "deferred":
        pct = _decimal(component.get("deferral_pct")); deferred = gross_tax * pct / Decimal("100")
        steps.append({"step": "deferral", "rate_pct": str(pct), "value": str(_money(deferred))})
    if incidence == "suspended":
        suspended = base * rate / Decimal("100") * _decimal(component.get("suspension_pct", 100)) / Decimal("100")
        steps.append({"step": "suspension", "value": str(_money(suspended))})
    payable = max(gross_tax - deferred, ZERO)
    return {
        "tax": component["tax"], "incidence": incidence, "base": str(_money(base)), "rate_pct": str(rate),
        "gross_amount": str(_money(gross_tax)), "deferred_amount": str(_money(deferred)), "suspended_amount": str(_money(suspended)),
        "amount": str(_money(payable)), "steps": steps, "metadata": component.get("metadata", {}),
    }


def simulate_tax_calculation(data: FiscalTaxSimulationInput, request: Request, tenant_id: str, user: CurrentUser, key: str | None = None) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json"); scope = f"fiscal-tax-simulation:{tenant_id}"; now = iso_now()
    with request.state.store.transaction() as conn:
        if key:
            cached = get_idempotent(conn, scope, key, body)
            if cached: return cached
        context = _context_version(conn, tenant_id, data.fiscal_context_id, data.occurred_on.isoformat())
        rule_set, version = _resolve_rule_version(conn, tenant_id, data, context)
        classification = _resolve_classification(conn, tenant_id, data)
        taxes: dict[str, dict[str, Any]] = {}
        for component in version["components"]:
            taxes[component["tax"]] = _calculate_component(component, data, taxes)
        tax_total = sum((_decimal(item["amount"]) for item in taxes.values()), ZERO)
        strategies = resolve_strategies(conn, tenant_id, data, context)
        # Estratégias recebem a base da operação explicitamente, sem esconder origem do cálculo.
        operation_base = _money(_decimal(data.amount) + _decimal(data.freight) + _decimal(data.insurance) + _decimal(data.other_amount) - _decimal(data.discount))
        for strategy in strategies:
            strategy.setdefault("parameters", {}).setdefault("operation_base", str(operation_base))
        strategy_adjustments, net_tax_total = apply_strategies(strategies, taxes, tax_total)
        divergences = []
        for tax, expected in data.expected_taxes.items():
            actual = _decimal(taxes.get(tax, {}).get("amount", ZERO)); delta = _money(actual - _decimal(expected))
            if delta != ZERO:
                divergences.append({"tax": tax, "expected": str(_money(_decimal(expected))), "actual": str(_money(actual)), "difference": str(delta)})
        input_snapshot = body
        result = {
            "calculation_id": uuid7(), "calculated_at": now, "occurred_on": data.occurred_on.isoformat(),
            "context": {"id": context["fiscal_context_id"], "version_id": context["id"], "tax_regime": context["tax_regime"], "uf": context["uf"], "municipality_code": context["municipality_code"], "rtc_mode": context["rtc_mode"], "ruleset_version": context["ruleset_version"]},
            "rule_set": {"id": rule_set["id"], "code": rule_set["code"], "name": rule_set["name"], "priority": rule_set["priority"], "version": version},
            "classification": classification,
            "operation": {"amount": str(_money(_decimal(data.amount))), "quantity": str(data.quantity), "freight": str(_money(_decimal(data.freight))), "insurance": str(_money(_decimal(data.insurance))), "other_amount": str(_money(_decimal(data.other_amount))), "discount": str(_money(_decimal(data.discount)))},
            "taxes": taxes, "tax_total": str(_money(tax_total)), "strategy_adjustments": strategy_adjustments, "net_tax_total": str(_money(net_tax_total)), "divergences": divergences,
            "explainability": {"rule_resolution": "vigência + contexto + estabelecimento + operação + item + regime + RTC + prioridade", "strategy_resolution": "vigência + estabelecimento + operação + regime + RTC + UF/DIFAL + prioridade", "source_sha256": version["source_sha256"], "legal_basis": version["legal_basis"]},
        }
        result["snapshot_sha256"] = _digest({"input": input_snapshot, "result": result})
        conn.execute(
            "INSERT INTO fiscal_tax_calculations(id,tenant_id,fiscal_context_id,fiscal_context_version_id,fiscal_tax_rule_set_id,fiscal_tax_rule_version_id,item_kind,item_id,operation_type,occurred_on,input_json,result_json,snapshot_sha256,tax_total,has_divergence,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (result["calculation_id"], tenant_id, data.fiscal_context_id, context["id"], rule_set["id"], version["id"], data.item_kind, data.item_id, data.operation_type, data.occurred_on.isoformat(), dumps(input_snapshot), dumps(result), result["snapshot_sha256"], str(_money(tax_total)), 1 if divergences else 0, user.id, now),
        )
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="simulate", aggregate_type="fiscal_tax_calculation", aggregate_id=result["calculation_id"], after={"snapshot_sha256": result["snapshot_sha256"], "tax_total": result["tax_total"], "has_divergence": bool(divergences)})
        _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalTaxCalculationCompleted", aggregate_type="fiscal_tax_calculation", aggregate_id=result["calculation_id"], payload={"snapshot_sha256": result["snapshot_sha256"], "tax_total": result["tax_total"], "has_divergence": bool(divergences)})
        if divergences:
            _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalTaxDivergenceDetected", aggregate_type="fiscal_tax_calculation", aggregate_id=result["calculation_id"], payload={"divergences": divergences})
        if key: save_idempotent(conn, scope, key, body, 201, result)
        return 201, result


def get_tax_calculation(request: Request, tenant_id: str, calculation_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM fiscal_tax_calculations WHERE tenant_id=? AND id=?", (tenant_id, calculation_id))
    if not row: raise DomainError("FISCAL_TAX_CALCULATION_NOT_FOUND", "Cálculo tributário não localizado.", 404)
    out = dict(row); out["input"] = loads(out.pop("input_json"), {}); out["result"] = loads(out.pop("result_json"), {})
    return out
