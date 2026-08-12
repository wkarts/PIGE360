from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import Request

from app.modules.fiscal.presentation.transparency_schemas import (
    FiscalIbptProviderProfileCreate,
    FiscalIbptProviderProfilePublish,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

CENT = Decimal("0.01")
RATE = Decimal("0.0001")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def _rate(value: Any) -> Decimal:
    return _dec(value).quantize(RATE, rounding=ROUND_HALF_UP)

def _one(db, sql: str, params: tuple[Any, ...]):
    if hasattr(db, "fetch_one"):
        return db.fetch_one(sql, params)
    row = db.execute(sql, params).fetchone()
    return dict(row) if row else None


def _all(db, sql: str, params: tuple[Any, ...]):
    if hasattr(db, "fetch_all"):
        return db.fetch_all(sql, params)
    return [dict(row) for row in db.execute(sql, params).fetchall()]


def _exec(db, sql: str, params: tuple[Any, ...]):
    if hasattr(db, "execute") and not hasattr(db, "fetch_one"):
        return db.execute(sql, params)
    return db.execute(sql, params)


def _profile_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "provider_code": row["provider_code"],
        "mode": row["mode"],
        "valid_from": row["valid_from"],
        "valid_until": row.get("valid_until"),
        "sync_enabled": bool(row.get("sync_enabled")),
        "fallback_enabled": bool(row.get("fallback_enabled")),
        "fallback_max_age_days": int(row.get("fallback_max_age_days") or 0),
        "stale_after_days": int(row.get("stale_after_days") or 0),
        "base_url": row["base_url"],
        "uf_path": row["uf_path"],
        "notes": row.get("notes"),
        "state": row["state"],
        "version": int(row["version"]),
        "created_by": row["created_by"],
        "published_by": row.get("published_by"),
        "published_at": row.get("published_at"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_ibpt_profiles(request: Request, tenant_id: str) -> dict[str, Any]:
    rows = request.state.store.fetch_all(
        "SELECT * FROM fiscal_ibpt_provider_profiles WHERE tenant_id=? ORDER BY version DESC,created_at DESC",
        (tenant_id,),
    )
    return {"items": [_profile_row(row) for row in rows]}


def create_ibpt_profile(
    data: FiscalIbptProviderProfileCreate,
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    idempotency_key: str,
) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-ibpt-profile:{tenant_id}:{data.provider_code}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        version_row = conn.execute(
            "SELECT COALESCE(MAX(version),0) AS n FROM fiscal_ibpt_provider_profiles WHERE tenant_id=? AND provider_code=?",
            (tenant_id, data.provider_code),
        ).fetchone()
        version = int((version_row or {"n": 0})["n"] or 0) + 1
        profile_id = uuid7()
        now = iso_now()
        base_url = data.base_url or request.app.state.settings.ibpt_api_base_url
        uf_path = data.uf_path or request.app.state.settings.ibpt_api_uf_path
        conn.execute(
            "INSERT INTO fiscal_ibpt_provider_profiles("
            "id,tenant_id,provider_code,mode,valid_from,valid_until,sync_enabled,fallback_enabled,"
            "fallback_max_age_days,stale_after_days,base_url,uf_path,notes,state,version,created_by,created_at,updated_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?,?,?)",
            (
                profile_id, tenant_id, data.provider_code, data.mode, str(data.valid_from),
                str(data.valid_until) if data.valid_until else None, int(data.sync_enabled), int(data.fallback_enabled),
                data.fallback_max_age_days, data.stale_after_days, base_url, uf_path, data.notes,
                version, user.id, now, now,
            ),
        )
        result = {
            "id": profile_id,
            "provider_code": data.provider_code,
            "mode": data.mode,
            "state": "draft",
            "version": version,
            "sync_enabled": data.sync_enabled,
            "fallback_enabled": data.fallback_enabled,
            "valid_from": str(data.valid_from),
            "valid_until": str(data.valid_until) if data.valid_until else None,
        }
        add_audit(
            conn, tenant_id=tenant_id, actor_id=user.id, action="create",
            aggregate_type="fiscal_ibpt_provider_profile", aggregate_id=profile_id,
            correlation_id=request.state.correlation_id, after=result,
        )
        add_outbox(
            conn, tenant_id=tenant_id, event_type="FiscalIbptProviderProfileCreated",
            aggregate_type="fiscal_ibpt_provider_profile", aggregate_id=profile_id,
            payload=result, correlation_id=request.state.correlation_id,
        )
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
        return 201, result


def publish_ibpt_profile(
    profile_id: str,
    data: FiscalIbptProviderProfilePublish,
    request: Request,
    tenant_id: str,
    user: CurrentUser,
) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        raw = conn.execute(
            "SELECT * FROM fiscal_ibpt_provider_profiles WHERE tenant_id=? AND id=?",
            (tenant_id, profile_id),
        ).fetchone()
        if not raw:
            raise DomainError("FISCAL_IBPT_PROFILE_NOT_FOUND", "Perfil IBPT não localizado.", 404)
        row = dict(raw)
        if int(row["version"]) != data.expected_version:
            raise DomainError("VERSION_CONFLICT", "Versão divergente do perfil IBPT.", 409)
        if row["state"] == "published":
            return _profile_row(row)
        if row["state"] not in {"draft", "superseded"}:
            raise DomainError("FISCAL_IBPT_PROFILE_STATE", "Estado do perfil IBPT não permite publicação.", 409)
        # Perfis publicados podem coexistir quando as vigências não se sobrepõem. Em conflito,
        # a nova versão supersede somente versões do mesmo provider que interceptem seu período.
        overlaps = conn.execute(
            "SELECT id FROM fiscal_ibpt_provider_profiles WHERE tenant_id=? AND provider_code=? AND state='published' "
            "AND id<>? AND valid_from<=COALESCE(?, '9999-12-31') AND (valid_until IS NULL OR valid_until>=?)",
            (tenant_id, row["provider_code"], profile_id, row.get("valid_until"), row["valid_from"]),
        ).fetchall()
        superseded_ids = [item["id"] for item in overlaps]
        for old_id in superseded_ids:
            conn.execute(
                "UPDATE fiscal_ibpt_provider_profiles SET state='superseded',updated_at=? WHERE tenant_id=? AND id=?",
                (iso_now(), tenant_id, old_id),
            )
        now = iso_now()
        conn.execute(
            "UPDATE fiscal_ibpt_provider_profiles SET state='published',published_by=?,published_at=?,updated_at=? "
            "WHERE tenant_id=? AND id=?",
            (user.id, now, now, tenant_id, profile_id),
        )
        result = {**_profile_row({**row, "state": "published", "published_by": user.id, "published_at": now, "updated_at": now}), "reason": data.reason, "superseded_ids": superseded_ids}
        add_audit(
            conn, tenant_id=tenant_id, actor_id=user.id, action="publish",
            aggregate_type="fiscal_ibpt_provider_profile", aggregate_id=profile_id,
            correlation_id=request.state.correlation_id,
            before={"state": row["state"]}, after=result,
        )
        add_outbox(
            conn, tenant_id=tenant_id, event_type="FiscalIbptProviderProfilePublished",
            aggregate_type="fiscal_ibpt_provider_profile", aggregate_id=profile_id,
            payload={"id": profile_id, "mode": row["mode"], "version": row["version"], "superseded_ids": superseded_ids},
            correlation_id=request.state.correlation_id,
        )
        return result


def resolve_ibpt_profile(store, tenant_id: str, occurred_on: str | date | None = None) -> dict[str, Any] | None:
    if occurred_on is None:
        target = date.today().isoformat()
    elif isinstance(occurred_on, date):
        target = occurred_on.isoformat()
    else:
        target = str(occurred_on)[:10]
    row = _one(store,
        "SELECT * FROM fiscal_ibpt_provider_profiles WHERE tenant_id=? AND state='published' "
        "AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY valid_from DESC,version DESC LIMIT 1",
        (tenant_id, target, target),
    )
    return _profile_row(row) if row else None


def _snapshot_age_days(snapshot: dict[str, Any], reference: date) -> int:
    raw = str(snapshot.get("created_at") or "")
    try:
        created = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        try:
            created = date.fromisoformat(raw[:10])
        except Exception:
            return 999999
    return max(0, (reference - created).days)


def _find_rate(store, tenant_id: str, snapshot_id: str, code: str) -> dict[str, Any] | None:
    normalized = "".join(ch for ch in str(code or "") if ch.isalnum()).upper()
    if not normalized:
        return None
    return _one(store,
        "SELECT * FROM ibpt_rates WHERE tenant_id=? AND snapshot_id=? AND code=? ORDER BY CASE WHEN COALESCE(ex,'')='' THEN 0 ELSE 1 END,item_type LIMIT 1",
        (tenant_id, snapshot_id, normalized),
    )


def lookup_ibpt_rate(
    store,
    *,
    tenant_id: str,
    uf: str,
    code: str,
    occurred_on: date,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    profile = profile or resolve_ibpt_profile(store, tenant_id, occurred_on)
    if profile and profile["mode"] == "disabled":
        return None
    # Sem perfil publicado preserva compatibilidade do cache já existente, mas não habilita scheduler remoto.
    fallback_enabled = bool(profile["fallback_enabled"]) if profile else False
    fallback_days = int(profile["fallback_max_age_days"]) if profile else 0
    stale_days = int(profile["stale_after_days"]) if profile else 120
    active = _one(store,
        "SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND uf=? AND state='active' ORDER BY created_at DESC LIMIT 1",
        (tenant_id, uf.upper()),
    )
    selected = active
    source_state = "active_cache"
    rate = _find_rate(store, tenant_id, active["id"], code) if active else None
    if (not selected or not rate) and fallback_enabled:
        candidates = _all(store,
            "SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND uf=? AND state='superseded' ORDER BY created_at DESC",
            (tenant_id, uf.upper()),
        )
        for candidate in candidates:
            age = _snapshot_age_days(candidate, occurred_on)
            if age > fallback_days:
                continue
            candidate_rate = _find_rate(store, tenant_id, candidate["id"], code)
            if candidate_rate:
                selected = candidate
                rate = candidate_rate
                source_state = "fallback"
                break
    if not selected or not rate:
        return None
    age_days = _snapshot_age_days(selected, occurred_on)
    return {
        "profile_id": profile["id"] if profile else None,
        "profile_mode": profile["mode"] if profile else "legacy_local_cache",
        "source_state": source_state,
        "snapshot_id": selected["id"],
        "snapshot_sha256": selected["sha256"],
        "snapshot_source_version": selected.get("source_version"),
        "age_days": age_days,
        "stale": age_days > stale_days,
        "rate": rate,
        "purpose": "transparencia_vtottrib",
        "tax_calculation_source": False,
    }


def _item_code(item: dict[str, Any]) -> str | None:
    classification = item.get("classification") or {}
    return (
        item.get("ncm") or item.get("nbs") or classification.get("ncm") or classification.get("nbs") or item.get("code")
    )


def calculate_build_transparency(
    store,
    *,
    tenant_id: str,
    build_id: str,
    document_type: str,
    items: list[dict[str, Any]],
    uf: str,
    occurred_on: date,
    real_taxes: dict[str, Any] | None,
) -> dict[str, Any]:
    existing = _one(store,
        "SELECT * FROM fiscal_document_tax_transparency WHERE tenant_id=? AND build_id=?",
        (tenant_id, build_id),
    )
    if existing:
        return transparency_row(existing)
    profile = resolve_ibpt_profile(store, tenant_id, occurred_on)
    rows: list[dict[str, Any]] = []
    total_approx = Decimal("0")
    for item in items:
        code = _item_code(item)
        amount = _dec(item.get("total_amount"))
        found = lookup_ibpt_rate(store, tenant_id=tenant_id, uf=uf, code=code or "", occurred_on=occurred_on, profile=profile)
        if not found:
            rows.append({"line_id": item.get("line_id"), "code": code, "total_amount": _money(amount), "state": "rate_not_available"})
            continue
        rate = found["rate"]
        origin = str((item.get("classification") or {}).get("origin") or "national").lower()
        federal = _rate(rate.get("imported_federal")) if origin in {"imported", "foreign", "importacao"} else _rate(rate.get("national_federal"))
        state_rate = _rate(rate.get("state_rate"))
        municipal = _rate(rate.get("municipal_rate"))
        combined = federal + state_rate + municipal
        approx = (amount * combined / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        total_approx += approx
        rows.append({
            "line_id": item.get("line_id"), "code": code, "total_amount": _money(amount),
            "federal_rate": format(federal, "f"), "state_rate": format(state_rate, "f"),
            "municipal_rate": format(municipal, "f"), "combined_rate": format(combined, "f"),
            "approximate_amount": _money(approx), "source_state": found["source_state"],
            "snapshot_id": found["snapshot_id"], "snapshot_sha256": found["snapshot_sha256"],
            "age_days": found["age_days"], "stale": found["stale"],
        })
    approximate = {
        "document_type": document_type,
        "uf": uf,
        "profile_id": profile["id"] if profile else None,
        "profile_mode": profile["mode"] if profile else "legacy_local_cache",
        "items": rows,
        "vTotTrib": _money(total_approx),
        "purpose": "transparencia_vtottrib",
        "tax_calculation_source": False,
    }
    now = iso_now()
    transparency_id = uuid7()
    _exec(store,
        "INSERT INTO fiscal_document_tax_transparency("
        "id,tenant_id,build_id,fiscal_document_id,real_taxes_json,approximate_ibpt_json,vtottrib,ibpt_provider_profile_id,created_at"
        ") VALUES(?,?,?,?,?,?,?,?,?)",
        (
            transparency_id, tenant_id, build_id, None,
            _dump(real_taxes or {}), _dump(approximate), _money(total_approx),
            profile["id"] if profile else None, now,
        ),
    )
    return {
        "id": transparency_id, "build_id": build_id, "fiscal_document_id": None,
        "real_taxes": real_taxes or {}, "approximate_ibpt": approximate,
        "vTotTrib": _money(total_approx), "ibpt_provider_profile_id": profile["id"] if profile else None,
        "created_at": now,
    }


def link_transparency_document(store, *, tenant_id: str, build_id: str, fiscal_document_id: str) -> None:
    _exec(store,
        "UPDATE fiscal_document_tax_transparency SET fiscal_document_id=? WHERE tenant_id=? AND build_id=?",
        (fiscal_document_id, tenant_id, build_id),
    )


def transparency_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "build_id": row["build_id"],
        "fiscal_document_id": row.get("fiscal_document_id"),
        "real_taxes": _loads(row.get("real_taxes_json"), {}),
        "approximate_ibpt": _loads(row.get("approximate_ibpt_json"), {}),
        "vTotTrib": str(row.get("vtottrib") or "0.00"),
        "ibpt_provider_profile_id": row.get("ibpt_provider_profile_id"),
        "created_at": row["created_at"],
    }


def document_transparency(request: Request, tenant_id: str, document_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one(
        "SELECT * FROM fiscal_document_tax_transparency WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at DESC LIMIT 1",
        (tenant_id, document_id),
    )
    if not row:
        raise DomainError("FISCAL_TAX_TRANSPARENCY_NOT_FOUND", "Transparência tributária do documento não localizada.", 404)
    return transparency_row(row)
