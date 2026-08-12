from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from typing import Any, Iterable

from fastapi import Request

from app.modules.fiscal.presentation.context_schemas import (
    FISCAL_PROVIDER_CODES,
    FiscalContextCreate,
    FiscalContextPatch,
    FiscalContextResolveInput,
    FiscalContextVersionCreate,
    FiscalContextVersionPublish,
)
from app.modules.operations.common import dumps, loads
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

EFFECTIVE_VERSION_STATES = {"published", "scheduled", "superseded"}


def _one(
    conn: sqlite3.Connection,
    sql: str,
    params: Iterable[Any],
    code: str,
    detail: str,
) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, detail, 404)
    return dict(row)


def _context_payload(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["metadata"] = loads(result.pop("metadata_json", "{}"), {})
    result.setdefault("status", result.get("state"))
    return result


def _scope_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "operation_type": row["operation_type"],
        "item_kind": row["item_kind"],
        "recipient_scope": row["recipient_scope"],
        "document_type": row["document_type"],
    }


def _version_payload(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    include_scopes: bool = True,
) -> dict[str, Any]:
    result = dict(row)
    result["configuration"] = loads(result.pop("configuration_json", "{}"), {})
    result.setdefault("status", result.get("state"))
    if include_scopes:
        result["scopes"] = [
            _scope_payload(dict(scope))
            for scope in conn.execute(
                "SELECT * FROM fiscal_context_operation_scopes "
                "WHERE tenant_id=? AND fiscal_context_version_id=? "
                "ORDER BY operation_type,item_kind,recipient_scope,document_type,id",
                (row["tenant_id"], row["id"]),
            ).fetchall()
        ]
    return result


def _audit(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    user: CurrentUser,
    request: Request,
    action: str,
    aggregate_type: str,
    aggregate_id: str,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
) -> None:
    add_audit(
        conn,
        tenant_id=tenant_id,
        actor_id=user.id,
        action=action,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        correlation_id=request.state.correlation_id,
        before=before,
        after=after,
        reason=reason,
    )


def _event(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    request: Request,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: Any,
) -> None:
    add_outbox(
        conn,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )


def _validate_institutional_scope(
    conn: sqlite3.Connection,
    tenant_id: str,
    institution_id: str | None,
    unit_id: str | None,
) -> None:
    if institution_id:
        _one(
            conn,
            "SELECT id FROM institutions WHERE tenant_id=? AND id=? AND state='active'",
            (tenant_id, institution_id),
            "INSTITUTION_NOT_FOUND",
            "Instituição não localizada ou inativa.",
        )
    if unit_id:
        unit = _one(
            conn,
            "SELECT id,institution_id FROM units WHERE tenant_id=? AND id=? AND state='active'",
            (tenant_id, unit_id),
            "UNIT_NOT_FOUND",
            "Unidade não localizada ou inativa.",
        )
        if institution_id and unit["institution_id"] != institution_id:
            raise DomainError(
                "UNIT_SCOPE_MISMATCH",
                "A unidade não pertence à instituição informada.",
                409,
            )


def _validate_provider(
    conn: sqlite3.Connection,
    tenant_id: str,
    provider_connection_id: str | None,
) -> None:
    if not provider_connection_id:
        return
    row = conn.execute(
        "SELECT provider FROM integration_connections WHERE tenant_id=? AND id=?",
        (tenant_id, provider_connection_id),
    ).fetchone()
    if not row:
        raise DomainError("FISCAL_PROVIDER_NOT_FOUND", "Conexão fiscal não localizada.", 404)
    if row["provider"] not in FISCAL_PROVIDER_CODES:
        raise DomainError(
            "FISCAL_PROVIDER_INVALID",
            "A conexão selecionada não implementa um provider fiscal.",
            422,
        )


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def list_contexts(
    request: Request,
    tenant_id: str,
    *,
    status: str | None = None,
    q: str | None = None,
    institution_id: str | None = None,
    unit_id: str | None = None,
) -> dict[str, Any]:
    sql = "SELECT * FROM fiscal_contexts WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if status:
        sql += " AND state=?"
        params.append(status)
    if q:
        sql += " AND (code LIKE ? OR establishment_name LIKE ? OR legal_name LIKE ? OR cnpj LIKE ?)"
        term = f"%{q}%"
        params.extend((term, term, term, term))
    if institution_id:
        sql += " AND institution_id=?"
        params.append(institution_id)
    if unit_id:
        sql += " AND unit_id=?"
        params.append(unit_id)
    sql += " ORDER BY establishment_name,code,id"
    items = [_context_payload(row) for row in request.state.store.fetch_all(sql, params)]
    for item in items:
        active_version_id = item.get("active_version_id")
        item["active_version"] = (
            request.state.store.fetch_one(
                "SELECT id,version_number,tax_regime,uf,municipality_code,valid_from,valid_until,"
                "environment,rtc_mode,state FROM fiscal_context_versions WHERE tenant_id=? AND id=?",
                (tenant_id, active_version_id),
            )
            if active_version_id
            else None
        )
    return {"items": items}


def context_detail(request: Request, tenant_id: str, context_id: str) -> dict[str, Any]:
    context = request.state.store.fetch_one(
        "SELECT * FROM fiscal_contexts WHERE tenant_id=? AND id=?",
        (tenant_id, context_id),
    )
    if not context:
        raise DomainError("FISCAL_CONTEXT_NOT_FOUND", "Contexto fiscal não localizado.", 404)
    result = _context_payload(context)
    with request.state.store.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND fiscal_context_id=? "
            "ORDER BY version_number DESC,id DESC",
            (tenant_id, context_id),
        ).fetchall()
        result["versions"] = [_version_payload(conn, dict(row)) for row in rows]
    return result


def create_context(
    data: FiscalContextCreate,
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    idempotency_key: str,
) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-context:create:{tenant_id}"
    now = iso_now()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        _validate_institutional_scope(conn, tenant_id, data.institution_id, data.unit_id)
        _validate_provider(conn, tenant_id, data.provider_connection_id)
        duplicate = conn.execute(
            "SELECT id,code,cnpj FROM fiscal_contexts WHERE tenant_id=? AND (code=? OR cnpj=?)",
            (tenant_id, data.code, data.cnpj),
        ).fetchone()
        if duplicate:
            raise DomainError(
                "FISCAL_CONTEXT_EXISTS",
                "Já existe contexto fiscal com o mesmo código ou CNPJ.",
                409,
            )
        context_id = uuid7()
        conn.execute(
            "INSERT INTO fiscal_contexts("
            "id,tenant_id,code,establishment_name,legal_name,cnpj,institution_id,unit_id,"
            "state_registration,municipal_registration,provider_connection_id,metadata_json,state,"
            "active_version_id,latest_version_number,version,created_by,created_at,updated_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                context_id,
                tenant_id,
                data.code,
                data.establishment_name,
                data.legal_name,
                data.cnpj,
                data.institution_id,
                data.unit_id,
                data.state_registration,
                data.municipal_registration,
                data.provider_connection_id,
                dumps(data.metadata),
                "active",
                None,
                0,
                1,
                user.id,
                now,
                now,
            ),
        )
        result = {
            "id": context_id,
            **body,
            "status": "active",
            "active_version_id": None,
            "latest_version_number": 0,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create",
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="FiscalContextCreated",
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            payload=result,
        )
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return 201, result


def update_context(
    context_id: str,
    data: FiscalContextPatch,
    request: Request,
    tenant_id: str,
    user: CurrentUser,
) -> dict[str, Any]:
    values = data.model_dump(exclude={"expected_version"}, exclude_unset=True, mode="json")
    if not values:
        raise DomainError("NO_CHANGES", "Nenhuma alteração foi informada.", 422)
    now = iso_now()
    with request.state.store.transaction() as conn:
        before = _one(
            conn,
            "SELECT * FROM fiscal_contexts WHERE tenant_id=? AND id=?",
            (tenant_id, context_id),
            "FISCAL_CONTEXT_NOT_FOUND",
            "Contexto fiscal não localizado.",
        )
        if int(before["version"]) != data.expected_version:
            raise DomainError("VERSION_CONFLICT", "O contexto fiscal foi alterado por outro usuário.", 409)
        if "provider_connection_id" in values:
            _validate_provider(conn, tenant_id, values["provider_connection_id"])

        assignments: list[str] = []
        params: list[Any] = []
        for field, value in values.items():
            column = {"status": "state", "metadata": "metadata_json"}.get(field, field)
            assignments.append(f"{column}=?")
            params.append(dumps(value) if field == "metadata" else value)
        next_version = data.expected_version + 1
        assignments.extend(("version=?", "updated_at=?"))
        params.extend((next_version, now, tenant_id, context_id))
        conn.execute(
            f"UPDATE fiscal_contexts SET {','.join(assignments)} WHERE tenant_id=? AND id=?",
            params,
        )
        after_row = _one(
            conn,
            "SELECT * FROM fiscal_contexts WHERE tenant_id=? AND id=?",
            (tenant_id, context_id),
            "FISCAL_CONTEXT_NOT_FOUND",
            "Contexto fiscal não localizado.",
        )
        result = _context_payload(after_row)
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="update",
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            before=_context_payload(before),
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="FiscalContextUpdated",
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            payload=result,
        )
    return result


def create_version(
    context_id: str,
    data: FiscalContextVersionCreate,
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    idempotency_key: str,
) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-context-version:create:{tenant_id}:{context_id}"
    now = iso_now()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        context = _one(
            conn,
            "SELECT * FROM fiscal_contexts WHERE tenant_id=? AND id=?",
            (tenant_id, context_id),
            "FISCAL_CONTEXT_NOT_FOUND",
            "Contexto fiscal não localizado.",
        )
        if context["state"] != "active":
            raise DomainError("FISCAL_CONTEXT_INACTIVE", "Contexto fiscal inativo não aceita nova versão.", 409)
        if int(context["version"]) != data.expected_context_version:
            raise DomainError("VERSION_CONFLICT", "O contexto fiscal foi alterado por outro usuário.", 409)
        version_number = int(context["latest_version_number"] or 0) + 1
        version_id = uuid7()
        conn.execute(
            "INSERT INTO fiscal_context_versions("
            "id,tenant_id,fiscal_context_id,version_number,tax_regime,uf,municipality_code,"
            "valid_from,valid_until,environment,rtc_mode,layout_version,schema_version,"
            "technical_note_version,ruleset_version,configuration_json,notes,state,published_at,"
            "published_by,superseded_by_version_id,version,created_by,created_at,updated_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                version_id,
                tenant_id,
                context_id,
                version_number,
                data.tax_regime,
                data.uf,
                data.municipality_code,
                data.valid_from.isoformat(),
                data.valid_until.isoformat() if data.valid_until else None,
                data.environment,
                data.rtc_mode,
                data.layout_version,
                data.schema_version,
                data.technical_note_version,
                data.ruleset_version,
                dumps(data.configuration),
                data.notes,
                "draft",
                None,
                None,
                None,
                1,
                user.id,
                now,
                now,
            ),
        )
        for operation_scope in data.scopes:
            conn.execute(
                "INSERT INTO fiscal_context_operation_scopes("
                "id,tenant_id,fiscal_context_version_id,operation_type,item_kind,recipient_scope,document_type,created_at"
                ") VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid7(),
                    tenant_id,
                    version_id,
                    operation_scope.operation_type,
                    operation_scope.item_kind,
                    operation_scope.recipient_scope,
                    operation_scope.document_type,
                    now,
                ),
            )
        next_context_version = data.expected_context_version + 1
        conn.execute(
            "UPDATE fiscal_contexts SET latest_version_number=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",
            (version_number, next_context_version, now, tenant_id, context_id),
        )
        row = _one(
            conn,
            "SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND id=?",
            (tenant_id, version_id),
            "FISCAL_CONTEXT_VERSION_NOT_FOUND",
            "Versão do contexto fiscal não localizada.",
        )
        result = _version_payload(conn, row)
        result["context_version"] = next_context_version
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="create_version",
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            before={"latest_version_number": context["latest_version_number"], "version": context["version"]},
            after=result,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type="FiscalContextVersionCreated",
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            payload=result,
        )
        save_idempotent(conn, scope, idempotency_key, body, 201, result)
    return 201, result


def list_versions(request: Request, tenant_id: str, context_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        _one(
            conn,
            "SELECT id FROM fiscal_contexts WHERE tenant_id=? AND id=?",
            (tenant_id, context_id),
            "FISCAL_CONTEXT_NOT_FOUND",
            "Contexto fiscal não localizado.",
        )
        rows = conn.execute(
            "SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND fiscal_context_id=? "
            "ORDER BY version_number DESC,id DESC",
            (tenant_id, context_id),
        ).fetchall()
        return {"items": [_version_payload(conn, dict(row)) for row in rows]}


def publish_version(
    context_id: str,
    version_id: str,
    data: FiscalContextVersionPublish,
    request: Request,
    tenant_id: str,
    user: CurrentUser,
    idempotency_key: str,
) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-context-version:publish:{tenant_id}:{context_id}:{version_id}"
    now = iso_now()
    today = date.today()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, idempotency_key, body)
        if cached:
            return cached
        context = _one(
            conn,
            "SELECT * FROM fiscal_contexts WHERE tenant_id=? AND id=?",
            (tenant_id, context_id),
            "FISCAL_CONTEXT_NOT_FOUND",
            "Contexto fiscal não localizado.",
        )
        if int(context["version"]) != data.expected_context_version:
            raise DomainError("VERSION_CONFLICT", "O contexto fiscal foi alterado por outro usuário.", 409)
        version = _one(
            conn,
            "SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND fiscal_context_id=? AND id=?",
            (tenant_id, context_id, version_id),
            "FISCAL_CONTEXT_VERSION_NOT_FOUND",
            "Versão do contexto fiscal não localizada.",
        )
        if int(version["version"]) != data.expected_version:
            raise DomainError("VERSION_CONFLICT", "A versão fiscal foi alterada por outro usuário.", 409)
        if version["state"] != "draft":
            raise DomainError("FISCAL_CONTEXT_VERSION_FINAL", "Somente versão em rascunho pode ser publicada.", 409)

        valid_from = date.fromisoformat(version["valid_from"])
        valid_until = date.fromisoformat(version["valid_until"]) if version.get("valid_until") else None
        overlaps = conn.execute(
            "SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND fiscal_context_id=? AND id<>? "
            "AND state IN ('published','scheduled','superseded') "
            "AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY valid_from,version_number",
            (
                tenant_id,
                context_id,
                version_id,
                valid_until.isoformat() if valid_until else "9999-12-31",
                valid_from.isoformat(),
            ),
        ).fetchall()
        superseded: list[dict[str, Any]] = []
        for raw in overlaps:
            previous = dict(raw)
            previous_from = date.fromisoformat(previous["valid_from"])
            if previous_from >= valid_from:
                raise DomainError(
                    "FISCAL_CONTEXT_PERIOD_OVERLAP",
                    "A vigência informada conflita com versão já publicada ou programada.",
                    409,
                )
            previous_until = valid_from - timedelta(days=1)
            if previous_until < previous_from:
                raise DomainError(
                    "FISCAL_CONTEXT_PERIOD_OVERLAP",
                    "Não é possível encerrar a versão anterior antes de seu início.",
                    409,
                )
            conn.execute(
                "UPDATE fiscal_context_versions SET valid_until=?,state='superseded',"
                "superseded_by_version_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                (previous_until.isoformat(), version_id, now, tenant_id, previous["id"]),
            )
            previous_after = {
                **_version_payload(conn, previous, include_scopes=False),
                "valid_until": previous_until.isoformat(),
                "status": "superseded",
                "superseded_by_version_id": version_id,
                "version": int(previous["version"]) + 1,
            }
            superseded.append(previous_after)
            _audit(
                conn,
                tenant_id=tenant_id,
                user=user,
                request=request,
                action="supersede",
                aggregate_type="fiscal_context_version",
                aggregate_id=previous["id"],
                before=_version_payload(conn, previous, include_scopes=False),
                after=previous_after,
                reason=data.reason,
            )
            _event(
                conn,
                tenant_id=tenant_id,
                request=request,
                event_type="FiscalContextVersionSuperseded",
                aggregate_type="fiscal_context",
                aggregate_id=context_id,
                payload=previous_after,
            )

        target_state = "published" if valid_from <= today else "scheduled"
        next_version = data.expected_version + 1
        conn.execute(
            "UPDATE fiscal_context_versions SET state=?,published_at=?,published_by=?,version=?,updated_at=? "
            "WHERE tenant_id=? AND id=?",
            (target_state, now, user.id, next_version, now, tenant_id, version_id),
        )
        active_version_id = context.get("active_version_id")
        if valid_from <= today and (valid_until is None or valid_until >= today):
            active_version_id = version_id
        next_context_version = data.expected_context_version + 1
        conn.execute(
            "UPDATE fiscal_contexts SET active_version_id=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",
            (active_version_id, next_context_version, now, tenant_id, context_id),
        )
        after_row = _one(
            conn,
            "SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND id=?",
            (tenant_id, version_id),
            "FISCAL_CONTEXT_VERSION_NOT_FOUND",
            "Versão do contexto fiscal não localizada.",
        )
        result = _version_payload(conn, after_row)
        result.update(
            {
                "context_id": context_id,
                "context_version": next_context_version,
                "active_version_id": active_version_id,
                "superseded_versions": [item["id"] for item in superseded],
            }
        )
        _audit(
            conn,
            tenant_id=tenant_id,
            user=user,
            request=request,
            action="publish" if target_state == "published" else "schedule",
            aggregate_type="fiscal_context_version",
            aggregate_id=version_id,
            before=_version_payload(conn, version, include_scopes=False),
            after=result,
            reason=data.reason,
        )
        _event(
            conn,
            tenant_id=tenant_id,
            request=request,
            event_type=("FiscalContextVersionPublished" if target_state == "published" else "FiscalContextVersionScheduled"),
            aggregate_type="fiscal_context",
            aggregate_id=context_id,
            payload=result,
        )
        save_idempotent(conn, scope, idempotency_key, body, 200, result)
    return 200, result


def _candidate_score(row: dict[str, Any], data: FiscalContextResolveInput) -> int:
    score = 0
    if data.context_id and row["context_id"] == data.context_id:
        score += 256
    if data.cnpj and row["cnpj"] == data.cnpj:
        score += 128
    if data.unit_id and row.get("unit_id") == data.unit_id:
        score += 64
    elif row.get("unit_id") is None:
        score += 1
    if data.institution_id and row.get("institution_id") == data.institution_id:
        score += 32
    elif row.get("institution_id") is None:
        score += 1
    if row["operation_type"] == data.operation_type:
        score += 16
    if row["item_kind"] == data.item_kind:
        score += 8
    if row["recipient_scope"] == data.recipient_scope:
        score += 4
    if row["document_type"] == data.document_type:
        score += 2
    return score


def _snapshot_from_candidate(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "context": {
            "id": row["context_id"],
            "code": row["context_code"],
            "establishment_name": row["establishment_name"],
            "legal_name": row["legal_name"],
            "cnpj": row["cnpj"],
            "institution_id": row["institution_id"],
            "unit_id": row["unit_id"],
            "state_registration": row["state_registration"],
            "municipal_registration": row["municipal_registration"],
            "provider_connection_id": row["provider_connection_id"],
        },
        "version": {
            "id": row["version_id"],
            "version_number": row["version_number"],
            "tax_regime": row["tax_regime"],
            "uf": row["uf"],
            "municipality_code": row["municipality_code"],
            "valid_from": row["valid_from"],
            "valid_until": row["valid_until"],
            "environment": row["environment"],
            "rtc_mode": row["rtc_mode"],
            "layout_version": row["layout_version"],
            "schema_version": row["schema_version"],
            "technical_note_version": row["technical_note_version"],
            "ruleset_version": row["ruleset_version"],
            "configuration": loads(row["configuration_json"], {}),
            "status": row["version_state"],
        },
        "scope": {
            "id": row["scope_id"],
            "operation_type": row["operation_type"],
            "item_kind": row["item_kind"],
            "recipient_scope": row["recipient_scope"],
            "document_type": row["document_type"],
        },
    }
    snapshot["sha256"] = _fingerprint(snapshot)
    return snapshot


def resolve_context(
    data: FiscalContextResolveInput,
    request: Request,
    tenant_id: str,
) -> dict[str, Any]:
    target_date = data.occurred_on.isoformat()
    sql = (
        "SELECT c.id AS context_id,c.code AS context_code,c.establishment_name,c.legal_name,c.cnpj,"
        "c.institution_id,c.unit_id,c.state_registration,c.municipal_registration,c.provider_connection_id,"
        "v.id AS version_id,v.version_number,v.tax_regime,v.uf,v.municipality_code,v.valid_from,v.valid_until,"
        "v.environment,v.rtc_mode,v.layout_version,v.schema_version,v.technical_note_version,v.ruleset_version,"
        "v.configuration_json,v.state AS version_state,"
        "s.id AS scope_id,s.operation_type,s.item_kind,s.recipient_scope,s.document_type "
        "FROM fiscal_contexts c "
        "JOIN fiscal_context_versions v ON v.fiscal_context_id=c.id AND v.tenant_id=c.tenant_id "
        "JOIN fiscal_context_operation_scopes s ON s.fiscal_context_version_id=v.id AND s.tenant_id=v.tenant_id "
        "WHERE c.tenant_id=? AND c.state='active' "
        "AND v.state IN ('published','scheduled','superseded') "
        "AND v.valid_from<=? AND (v.valid_until IS NULL OR v.valid_until>=?) "
        "AND (s.operation_type=? OR s.operation_type='any') "
        "AND (s.item_kind=? OR s.item_kind='any') "
        "AND (s.recipient_scope=? OR s.recipient_scope='any') "
        "AND (s.document_type=? OR s.document_type='any')"
    )
    params: list[Any] = [
        tenant_id,
        target_date,
        target_date,
        data.operation_type,
        data.item_kind,
        data.recipient_scope,
        data.document_type,
    ]
    if data.context_id:
        sql += " AND c.id=?"
        params.append(data.context_id)
    if data.cnpj:
        sql += " AND c.cnpj=?"
        params.append(data.cnpj)
    if data.institution_id:
        sql += " AND (c.institution_id=? OR c.institution_id IS NULL)"
        params.append(data.institution_id)
    if data.unit_id:
        sql += " AND (c.unit_id=? OR c.unit_id IS NULL)"
        params.append(data.unit_id)
    rows = request.state.store.fetch_all(sql, params)
    if not rows:
        raise DomainError(
            "FISCAL_CONTEXT_NOT_RESOLVED",
            "Nenhum contexto fiscal vigente corresponde à operação informada.",
            404,
        )
    ranked = sorted(
        (( _candidate_score(row, data), row["valid_from"], int(row["version_number"]), row) for row in rows),
        key=lambda item: (item[0], item[1], item[2]),
        reverse=True,
    )
    top = ranked[0]
    tied = [item for item in ranked if item[:3] == top[:3]]
    unique_targets = {(item[3]["context_id"], item[3]["version_id"], item[3]["scope_id"]) for item in tied}
    if len(unique_targets) > 1:
        raise DomainError(
            "FISCAL_CONTEXT_AMBIGUOUS",
            "Mais de um contexto fiscal possui a mesma precedência para a operação.",
            409,
        )
    result = _snapshot_from_candidate(top[3])
    result["resolved_for"] = data.model_dump(mode="json")
    return result


def fiscal_context_snapshot_by_version(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    version_id: str,
    occurred_on: date,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT c.*,v.id AS version_id,v.version_number,v.tax_regime,v.uf,v.municipality_code,"
        "v.valid_from,v.valid_until,v.environment,v.rtc_mode,v.layout_version,v.schema_version,"
        "v.technical_note_version,v.ruleset_version,v.configuration_json,v.state AS version_state "
        "FROM fiscal_contexts c JOIN fiscal_context_versions v "
        "ON v.fiscal_context_id=c.id AND v.tenant_id=c.tenant_id "
        "WHERE c.tenant_id=? AND c.state='active' AND v.id=?",
        (tenant_id, version_id),
    ).fetchone()
    if not row:
        raise DomainError("FISCAL_CONTEXT_VERSION_NOT_FOUND", "Versão do contexto fiscal não localizada.", 404)
    item = dict(row)
    target = occurred_on.isoformat()
    if item["version_state"] not in EFFECTIVE_VERSION_STATES:
        raise DomainError("FISCAL_CONTEXT_VERSION_NOT_PUBLISHED", "Versão fiscal ainda não foi publicada.", 409)
    if item["valid_from"] > target or (item.get("valid_until") and item["valid_until"] < target):
        raise DomainError("FISCAL_CONTEXT_VERSION_NOT_EFFECTIVE", "Versão fiscal não está vigente na data da operação.", 409)
    scopes = [
        _scope_payload(dict(scope))
        for scope in conn.execute(
            "SELECT * FROM fiscal_context_operation_scopes WHERE tenant_id=? AND fiscal_context_version_id=? "
            "ORDER BY operation_type,item_kind,recipient_scope,document_type,id",
            (tenant_id, version_id),
        ).fetchall()
    ]
    snapshot = {
        "context": {
            "id": item["id"],
            "code": item["code"],
            "establishment_name": item["establishment_name"],
            "legal_name": item["legal_name"],
            "cnpj": item["cnpj"],
            "institution_id": item["institution_id"],
            "unit_id": item["unit_id"],
            "state_registration": item["state_registration"],
            "municipal_registration": item["municipal_registration"],
            "provider_connection_id": item["provider_connection_id"],
        },
        "version": {
            "id": item["version_id"],
            "version_number": item["version_number"],
            "tax_regime": item["tax_regime"],
            "uf": item["uf"],
            "municipality_code": item["municipality_code"],
            "valid_from": item["valid_from"],
            "valid_until": item["valid_until"],
            "environment": item["environment"],
            "rtc_mode": item["rtc_mode"],
            "layout_version": item["layout_version"],
            "schema_version": item["schema_version"],
            "technical_note_version": item["technical_note_version"],
            "ruleset_version": item["ruleset_version"],
            "configuration": loads(item["configuration_json"], {}),
            "status": item["version_state"],
        },
        "scopes": scopes,
        "occurred_on": target,
    }
    snapshot["sha256"] = _fingerprint(snapshot)
    return snapshot
