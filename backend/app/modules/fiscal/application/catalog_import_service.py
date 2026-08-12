from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from fastapi import Request

from app.modules.fiscal.presentation.catalog_import_schemas import (
    FiscalCatalogImportCreate,
    FiscalCatalogImportPublish,
    FiscalCatalogQuarantineResolve,
    FiscalCatalogRollback,
    FiscalCatalogSourceCreate,
)
from app.modules.operations.common import dumps, loads
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_DIFF_CODES = 2000
SUPPORTED_KINDS = (
    "NCM", "NBS", "LC116", "CFOP", "CEST", "CST", "CSOSN", "CST_IBS_CBS",
    "CCLASSTRIB", "CBENEF", "CREDITO_PRESUMIDO", "RTC_TABLE",
)


def _one(conn: sqlite3.Connection, sql: str, params: Iterable[Any], code: str, detail: str) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, detail, 404)
    return dict(row)


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["mapping"] = loads(out.pop("mapping_json", "{}"), {})
    out["schema"] = loads(out.pop("schema_json", "{}"), {})
    out["status"] = out.get("state")
    return out


def _run_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["diff"] = loads(out.pop("diff_json", "{}"), {})
    out["status"] = out.get("state")
    return out


def _quarantine_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status"] = out.get("state")
    return out


def _audit(conn, *, tenant_id: str, user: CurrentUser, request: Request, action: str,
           aggregate_type: str, aggregate_id: str, before: Any = None, after: Any = None,
           reason: str | None = None) -> None:
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


def _event(conn, *, tenant_id: str, request: Request, event_type: str,
           aggregate_type: str, aggregate_id: str, payload: Any) -> None:
    add_outbox(
        conn,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    if not name or name in {".", ".."}:
        raise DomainError("FISCAL_CATALOG_FILENAME_INVALID", "Nome do arquivo de catálogo inválido.", 422)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:180]


def _decode_content(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DomainError("FISCAL_CATALOG_CONTENT_INVALID", "Conteúdo base64 inválido.", 422) from exc
    if not raw:
        raise DomainError("FISCAL_CATALOG_CONTENT_EMPTY", "Arquivo de catálogo vazio.", 422)
    if len(raw) > MAX_IMPORT_BYTES:
        raise DomainError("FISCAL_CATALOG_CONTENT_TOO_LARGE", "Arquivo de catálogo excede 25 MiB.", 413)
    return raw


def _lookup_path(value: Any, path: str | None) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"root_path não localizado: {path}")
    return current


def _parse_csv(raw: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    encoding = source.get("encoding") or "utf-8"
    try:
        text = raw.decode(encoding + "-sig" if encoding.lower() == "utf-8" else encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError(f"Falha ao decodificar CSV em {encoding}: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter=source.get("delimiter") or ";")
    if not reader.fieldnames:
        raise ValueError("CSV sem cabeçalho")
    return [dict(row) for row in reader]


def _parse_json(raw: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    encoding = source.get("encoding") or "utf-8"
    try:
        value = json.loads(raw.decode(encoding))
    except (LookupError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON inválido: {exc}") from exc
    schema = loads(source.get("schema_json", "{}"), {})
    value = _lookup_path(value, schema.get("root_path"))
    if not isinstance(value, list):
        raise ValueError("JSON deve resultar em uma lista de registros")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError("Todos os itens JSON devem ser objetos")
    return [dict(item) for item in value]


def _parse_xsd(raw: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/ENTITY não é permitido em importação XSD")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"XSD/XML inválido: {exc}") from exc
    xsd_ns = "http://www.w3.org/2001/XMLSchema"
    rows: list[dict[str, Any]] = []
    for node in root.iter(f"{{{xsd_ns}}}enumeration"):
        code = (node.attrib.get("value") or "").strip()
        if not code:
            continue
        description = code
        documentation = node.find(f".//{{{xsd_ns}}}documentation")
        if documentation is not None and "".join(documentation.itertext()).strip():
            description = " ".join("".join(documentation.itertext()).split())
        rows.append({"code": code, "description": description})
    if not rows:
        raise ValueError("XSD não contém xs:enumeration importável")
    return rows


PARSERS = {"csv": _parse_csv, "json": _parse_json, "xsd": _parse_xsd}


def _mapped_entries(records: list[dict[str, Any]], source: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = loads(source.get("mapping_json", "{}"), {})
    schema = loads(source.get("schema_json", "{}"), {})
    code_field = str(mapping.get("code") or "code")
    description_field = str(mapping.get("description") or "description")
    parent_field = str(mapping.get("parent_code") or "parent_code")
    metadata_fields = mapping.get("metadata_fields") or []
    required_fields = set(schema.get("required_fields") or [code_field, description_field])
    allow_code_description = bool(schema.get("description_optional", False))
    min_entries = int(schema.get("min_entries", 1))
    normalization = catalog.get("normalization") or "upper_alnum"
    pattern = re.compile(catalog["code_pattern"]) if catalog.get("code_pattern") else None
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def norm(value: Any) -> str:
        text = str(value or "").strip().upper()
        if normalization == "digits":
            return "".join(c for c in text if c.isdigit())
        if normalization == "upper_alnum":
            return "".join(c for c in text if c.isalnum())
        return text

    for index, row in enumerate(records, start=1):
        missing = [field for field in required_fields if row.get(field) in (None, "")]
        if missing:
            raise ValueError(f"registro {index}: campos obrigatórios ausentes: {', '.join(sorted(missing))}")
        code = norm(row.get(code_field))
        if not code:
            raise ValueError(f"registro {index}: código vazio após normalização")
        if pattern and not pattern.fullmatch(code):
            raise ValueError(f"registro {index}: código {code} não atende ao padrão do catálogo")
        if code in seen:
            raise ValueError(f"registro {index}: código duplicado {code}")
        seen.add(code)
        description = str(row.get(description_field) or (code if allow_code_description else "")).strip()
        if not description:
            raise ValueError(f"registro {index}: descrição obrigatória")
        parent = norm(row.get(parent_field)) if row.get(parent_field) not in (None, "") else None
        metadata = {field: row.get(field) for field in metadata_fields if field in row}
        if isinstance(row.get("metadata"), dict):
            metadata.update(row["metadata"])
        entries.append({"code": code, "description": description[:1000], "parent_code": parent, "metadata": metadata})
    if len(entries) < min_entries:
        raise ValueError(f"catálogo possui {len(entries)} entradas; mínimo configurado é {min_entries}")
    return entries


def _calculate_diff(conn: sqlite3.Connection, tenant_id: str, catalog: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    active_id = catalog.get("active_version_id")
    previous: dict[str, tuple[str, str | None, str]] = {}
    if active_id:
        rows = conn.execute(
            "SELECT code,description,parent_code,metadata_json FROM fiscal_catalog_entries WHERE tenant_id=? AND fiscal_catalog_version_id=?",
            (tenant_id, active_id),
        ).fetchall()
        for row in rows:
            previous[row["code"]] = (row["description"], row["parent_code"], dumps(loads(row["metadata_json"], {})))
    current = {item["code"]: (item["description"], item["parent_code"], dumps(item["metadata"])) for item in entries}
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    changed = sorted(code for code in set(current) & set(previous) if current[code] != previous[code])
    return {
        "base_version_id": active_id,
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added_codes": added[:MAX_DIFF_CODES],
        "removed_codes": removed[:MAX_DIFF_CODES],
        "changed_codes": changed[:MAX_DIFF_CODES],
        "truncated": any(len(values) > MAX_DIFF_CODES for values in (added, removed, changed)),
    }


def list_catalog_sources(request: Request, tenant_id: str, catalog_id: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM fiscal_catalog_source_profiles WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if catalog_id:
        sql += " AND fiscal_catalog_id=?"
        params.append(catalog_id)
    sql += " ORDER BY created_at DESC,id"
    return {"items": [_source_payload(row) for row in request.state.store.fetch_all(sql, params)]}


def create_catalog_source(catalog_id: str, data: FiscalCatalogSourceCreate, request: Request, tenant_id: str,
                          user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-catalog-source:create:{tenant_id}:{catalog_id}"
    now = iso_now()
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
        if cached:
            return cached
        _one(conn, "SELECT id FROM fiscal_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id),
             "FISCAL_CATALOG_NOT_FOUND", "Catálogo fiscal não localizado.")
        duplicate = conn.execute(
            "SELECT id FROM fiscal_catalog_source_profiles WHERE tenant_id=? AND fiscal_catalog_id=? AND provider_key=? AND provider_version=?",
            (tenant_id, catalog_id, data.provider_key, data.provider_version),
        ).fetchone()
        if duplicate:
            raise DomainError("FISCAL_CATALOG_SOURCE_EXISTS", "Provider/importador já cadastrado nesta versão.", 409)
        source_id = uuid7()
        state = "not_configured" if data.provider_type == "external_http" else "ready"
        conn.execute(
            """INSERT INTO fiscal_catalog_source_profiles(
                id,tenant_id,fiscal_catalog_id,provider_type,provider_key,provider_version,import_format,source_reference,
                encoding,delimiter,max_age_days,mapping_json,schema_json,state,last_import_at,last_success_at,last_error,
                version,notes,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (source_id, tenant_id, catalog_id, data.provider_type, data.provider_key, data.provider_version,
             data.import_format, data.source_reference, data.encoding, data.delimiter, data.max_age_days,
             dumps(data.mapping), dumps(data.validation_schema), state, None, None, None, 1, data.notes, user.id, now, now),
        )
        result = _source_payload(_one(conn, "SELECT * FROM fiscal_catalog_source_profiles WHERE tenant_id=? AND id=?",
                                      (tenant_id, source_id), "X", "X"))
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="create",
               aggregate_type="fiscal_catalog_source", aggregate_id=source_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalCatalogSourceConfigured",
               aggregate_type="fiscal_catalog_source", aggregate_id=source_id,
               payload={"catalog_id": catalog_id, "provider_key": data.provider_key, "state": state})
        save_idempotent(conn, scope, key, body, 201, result)
        return 201, result


def _insert_import_run(conn: sqlite3.Connection, *, run_id: str, tenant_id: str, catalog_id: str, source: dict[str, Any],
                       filename: str, digest: str, storage_key: str, bytes_count: int, data: FiscalCatalogImportCreate,
                       user: CurrentUser, state: str, error_code: str | None = None, error_detail: str | None = None,
                       diff: dict[str, Any] | None = None, entries_count: int = 0, version_id: str | None = None) -> None:
    now = iso_now()
    conn.execute(
        """INSERT INTO fiscal_catalog_import_runs(
          id,tenant_id,fiscal_catalog_id,source_profile_id,provider_key,provider_version,import_format,original_filename,
          source_sha256,storage_key,bytes_count,state,version_label,valid_from,valid_until,schema_version,entries_count,
          diff_json,catalog_version_id,error_code,error_detail,idempotency_key,requested_by,created_at,updated_at,completed_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, tenant_id, catalog_id, source["id"], source["provider_key"], source["provider_version"],
         source["import_format"], filename, digest, storage_key, bytes_count, state, data.version_label,
         data.valid_from.isoformat(), data.valid_until.isoformat() if data.valid_until else None,
         data.schema_version, entries_count, dumps(diff or {}), version_id, error_code, error_detail,
         None, user.id, now, now, now if state in {"quarantined", "failed"} else None),
    )


def _create_draft_version(conn: sqlite3.Connection, *, tenant_id: str, catalog: dict[str, Any], data: FiscalCatalogImportCreate,
                          entries: list[dict[str, Any]], source: dict[str, Any], digest: str, user: CurrentUser) -> dict[str, Any]:
    number = int(catalog["latest_version_number"]) + 1
    version_id = uuid7()
    now = iso_now()
    conn.execute(
        """INSERT INTO fiscal_catalog_versions(
          id,tenant_id,fiscal_catalog_id,version_number,version_label,valid_from,valid_until,source_name,source_reference,
          source_sha256,schema_version,notes,state,published_at,published_by,entries_count,version,created_by,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (version_id, tenant_id, catalog["id"], number, data.version_label, data.valid_from.isoformat(),
         data.valid_until.isoformat() if data.valid_until else None,
         f"{source['provider_key']}@{source['provider_version']}", source.get("source_reference"), digest,
         data.schema_version or source.get("provider_version"), data.notes, "draft", None, None,
         len(entries), 1, user.id, now, now),
    )
    for item in entries:
        conn.execute(
            "INSERT INTO fiscal_catalog_entries(id,tenant_id,fiscal_catalog_version_id,code,description,parent_code,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (uuid7(), tenant_id, version_id, item["code"], item["description"], item["parent_code"], dumps(item["metadata"]), now),
        )
    conn.execute(
        "UPDATE fiscal_catalogs SET latest_version_number=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
        (number, now, tenant_id, catalog["id"]),
    )
    return {
        "id": version_id,
        "version_number": number,
        "version_label": data.version_label,
        "valid_from": data.valid_from.isoformat(),
        "valid_until": data.valid_until.isoformat() if data.valid_until else None,
        "source_sha256": digest,
        "entries_count": len(entries),
        "state": "draft",
        "version": 1,
    }


def _publish_version_in_tx(conn: sqlite3.Connection, *, tenant_id: str, catalog: dict[str, Any], version_id: str,
                           user: CurrentUser, request: Request, reason: str) -> dict[str, Any]:
    version = _one(conn, "SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=? AND fiscal_catalog_id=?",
                   (tenant_id, version_id, catalog["id"]), "FISCAL_CATALOG_VERSION_NOT_FOUND", "Versão fiscal não localizada.")
    if version["state"] not in {"draft", "scheduled"}:
        if version["state"] == "published":
            return version
        raise DomainError("FISCAL_CATALOG_VERSION_NOT_PUBLISHABLE", "Versão não pode ser publicada neste estado.", 409)
    today = date.today()
    valid_from = date.fromisoformat(version["valid_from"])
    now = iso_now()
    if valid_from > today:
        conn.execute(
            "UPDATE fiscal_catalog_versions SET state='scheduled',published_at=?,published_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (now, user.id, now, tenant_id, version_id),
        )
        state = "scheduled"
    else:
        active_id = catalog.get("active_version_id")
        if active_id and active_id != version_id:
            active = _one(conn, "SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?",
                          (tenant_id, active_id), "FISCAL_CATALOG_VERSION_NOT_FOUND", "Versão ativa não localizada.")
            active_from = date.fromisoformat(active["valid_from"])
            if valid_from < active_from:
                raise DomainError(
                    "FISCAL_CATALOG_BACKDATED_PUBLICATION",
                    "Nova versão não pode retroceder a vigência da versão ativa; use rollback explícito.",
                    409,
                )
            close_on = valid_from - timedelta(days=1)
            new_until = active.get("valid_until")
            if active_from < valid_from and (not new_until or date.fromisoformat(new_until) >= valid_from):
                new_until = close_on.isoformat()
            conn.execute(
                "UPDATE fiscal_catalog_versions SET state='superseded',valid_until=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
                (new_until, now, tenant_id, active_id),
            )
        conn.execute(
            "UPDATE fiscal_catalog_versions SET state='published',published_at=?,published_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (now, user.id, now, tenant_id, version_id),
        )
        conn.execute(
            "UPDATE fiscal_catalogs SET active_version_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (version_id, now, tenant_id, catalog["id"]),
        )
        state = "published"
    result = dict(_one(conn, "SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?",
                       (tenant_id, version_id), "X", "X"))
    _audit(conn, tenant_id=tenant_id, user=user, request=request, action="publish_imported_version",
           aggregate_type="fiscal_catalog", aggregate_id=catalog["id"], after=result, reason=reason)
    _event(conn, tenant_id=tenant_id, request=request,
           event_type="FiscalCatalogImportPublished" if state == "published" else "FiscalCatalogImportScheduled",
           aggregate_type="fiscal_catalog", aggregate_id=catalog["id"],
           payload={"version_id": version_id, "state": state, "valid_from": version["valid_from"]})
    return result


def import_catalog_snapshot(catalog_id: str, data: FiscalCatalogImportCreate, request: Request, tenant_id: str,
                            user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-catalog-import:create:{tenant_id}:{catalog_id}"
    cached = None
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
    if cached:
        return cached

    catalog = request.state.store.fetch_one("SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id))
    if not catalog:
        raise DomainError("FISCAL_CATALOG_NOT_FOUND", "Catálogo fiscal não localizado.", 404)
    source = request.state.store.fetch_one(
        "SELECT * FROM fiscal_catalog_source_profiles WHERE tenant_id=? AND id=? AND fiscal_catalog_id=?",
        (tenant_id, data.source_profile_id, catalog_id),
    )
    if not source:
        raise DomainError("FISCAL_CATALOG_SOURCE_NOT_FOUND", "Provider/importador fiscal não localizado.", 404)
    raw = _decode_content(data.content_base64)
    digest = hashlib.sha256(raw).hexdigest()
    run_id = uuid7()
    filename = _safe_filename(data.filename)
    storage = request.app.state.data_router.object_storage(tenant_id)
    storage_key = f"fiscal/catalogs/{catalog_id}/imports/{run_id}/{filename}"
    stored = storage.put_bytes(storage_key, raw, content_type={"csv": "text/csv", "json": "application/json", "xsd": "application/xml"}[source["import_format"]])

    try:
        parser = PARSERS[source["import_format"]]
        records = parser(raw, source)
        entries = _mapped_entries(records, source, catalog)
    except Exception as exc:
        reason = str(exc)[:4000]
        quarantine_id = uuid7()
        quarantine_key = f"quarantine/fiscal-catalogs/{catalog_id}/{run_id}/{filename}"
        quarantined = storage.put_bytes(quarantine_key, raw, content_type="application/octet-stream")
        with request.state.store.transaction() as conn:
            _insert_import_run(
                conn, run_id=run_id, tenant_id=tenant_id, catalog_id=catalog_id, source=source, filename=filename,
                digest=digest, storage_key=storage_key, bytes_count=stored.bytes, data=data, user=user,
                state="quarantined", error_code="FISCAL_CATALOG_IMPORT_INVALID", error_detail=reason,
            )
            conn.execute(
                """INSERT INTO fiscal_catalog_quarantine(
                   id,tenant_id,import_run_id,source_profile_id,fiscal_catalog_id,reason_code,reason_detail,storage_key,
                   source_sha256,bytes_count,state,created_at,resolved_at,resolved_by,resolution_reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (quarantine_id, tenant_id, run_id, source["id"], catalog_id, "FISCAL_CATALOG_IMPORT_INVALID",
                 reason, quarantine_key, quarantined.sha256, quarantined.bytes, "open", iso_now(), None, None, None),
            )
            conn.execute(
                "UPDATE fiscal_catalog_source_profiles SET last_import_at=?,last_error=?,updated_at=? WHERE tenant_id=? AND id=?",
                (iso_now(), reason, iso_now(), tenant_id, source["id"]),
            )
            result = {
                "id": run_id,
                "status": "quarantined",
                "catalog_id": catalog_id,
                "source_profile_id": source["id"],
                "source_sha256": digest,
                "storage_key": storage_key,
                "quarantine_id": quarantine_id,
                "error_code": "FISCAL_CATALOG_IMPORT_INVALID",
                "error_detail": reason,
            }
            _audit(conn, tenant_id=tenant_id, user=user, request=request, action="quarantine_import",
                   aggregate_type="fiscal_catalog_import", aggregate_id=run_id, after=result, reason=reason)
            _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalCatalogImportQuarantined",
                   aggregate_type="fiscal_catalog_import", aggregate_id=run_id,
                   payload={"catalog_id": catalog_id, "source_sha256": digest, "reason": reason})
            save_idempotent(conn, scope, key, body, 422, result)
        return 422, result

    with request.state.store.transaction() as conn:
        catalog = _one(conn, "SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id),
                       "FISCAL_CATALOG_NOT_FOUND", "Catálogo fiscal não localizado.")
        diff = _calculate_diff(conn, tenant_id, catalog, entries)
        version = _create_draft_version(
            conn, tenant_id=tenant_id, catalog=catalog, data=data, entries=entries, source=source,
            digest=digest, user=user,
        )
        state = "draft_created"
        if data.auto_publish:
            published = _publish_version_in_tx(
                conn, tenant_id=tenant_id, catalog=catalog, version_id=version["id"], user=user,
                request=request, reason="Publicação automática após importação local validada.",
            )
            state = published["state"]
        _insert_import_run(
            conn, run_id=run_id, tenant_id=tenant_id, catalog_id=catalog_id, source=source, filename=filename,
            digest=digest, storage_key=storage_key, bytes_count=stored.bytes, data=data, user=user, state=state,
            diff=diff, entries_count=len(entries), version_id=version["id"],
        )
        conn.execute(
            "UPDATE fiscal_catalog_source_profiles SET last_import_at=?,last_success_at=?,last_error=NULL,updated_at=? WHERE tenant_id=? AND id=?",
            (iso_now(), iso_now(), iso_now(), tenant_id, source["id"]),
        )
        result = _run_payload(_one(conn, "SELECT * FROM fiscal_catalog_import_runs WHERE tenant_id=? AND id=?",
                                   (tenant_id, run_id), "X", "X"))
        result["catalog_version"] = version
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="import",
               aggregate_type="fiscal_catalog_import", aggregate_id=run_id, after=result)
        _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalCatalogSnapshotImported",
               aggregate_type="fiscal_catalog_import", aggregate_id=run_id,
               payload={"catalog_id": catalog_id, "version_id": version["id"], "entries_count": len(entries), "diff": diff})
        save_idempotent(conn, scope, key, body, 201, result)
        return 201, result


def list_catalog_imports(request: Request, tenant_id: str, catalog_id: str | None = None,
                         state: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM fiscal_catalog_import_runs WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if catalog_id:
        sql += " AND fiscal_catalog_id=?"; params.append(catalog_id)
    if state:
        sql += " AND state=?"; params.append(state)
    sql += " ORDER BY created_at DESC,id LIMIT 500"
    return {"items": [_run_payload(row) for row in request.state.store.fetch_all(sql, params)]}


def catalog_import_detail(request: Request, tenant_id: str, run_id: str) -> dict[str, Any]:
    row = request.state.store.fetch_one("SELECT * FROM fiscal_catalog_import_runs WHERE tenant_id=? AND id=?", (tenant_id, run_id))
    if not row:
        raise DomainError("FISCAL_CATALOG_IMPORT_NOT_FOUND", "Importação fiscal não localizada.", 404)
    result = _run_payload(row)
    if row.get("catalog_version_id"):
        result["catalog_version"] = request.state.store.fetch_one(
            """SELECT id,version_number,version_label,state,version,valid_from,valid_until,source_sha256,entries_count
               FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?""",
            (tenant_id, row["catalog_version_id"]),
        )
    else:
        result["catalog_version"] = None
    return result


def publish_catalog_import(run_id: str, data: FiscalCatalogImportPublish, request: Request, tenant_id: str,
                           user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-catalog-import:publish:{tenant_id}:{run_id}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
        if cached:
            return cached
        run = _one(conn, "SELECT * FROM fiscal_catalog_import_runs WHERE tenant_id=? AND id=?", (tenant_id, run_id),
                   "FISCAL_CATALOG_IMPORT_NOT_FOUND", "Importação fiscal não localizada.")
        if run["state"] in {"published", "scheduled"}:
            result = _run_payload(run); save_idempotent(conn, scope, key, body, 200, result); return 200, result
        if run["state"] != "draft_created" or not run.get("catalog_version_id"):
            raise DomainError("FISCAL_CATALOG_IMPORT_NOT_PUBLISHABLE", "Importação não possui versão validada publicável.", 409)
        version = _one(conn, "SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?",
                       (tenant_id, run["catalog_version_id"]), "FISCAL_CATALOG_VERSION_NOT_FOUND", "Versão fiscal não localizada.")
        if int(version["version"]) != data.expected_version:
            raise DomainError("VERSION_CONFLICT", "A versão fiscal foi alterada por outro processo.", 409)
        catalog = _one(conn, "SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?",
                       (tenant_id, run["fiscal_catalog_id"]), "FISCAL_CATALOG_NOT_FOUND", "Catálogo fiscal não localizado.")
        published = _publish_version_in_tx(
            conn, tenant_id=tenant_id, catalog=catalog, version_id=version["id"], user=user,
            request=request, reason=data.reason,
        )
        conn.execute(
            "UPDATE fiscal_catalog_import_runs SET state=?,updated_at=?,completed_at=? WHERE tenant_id=? AND id=?",
            (published["state"], iso_now(), iso_now(), tenant_id, run_id),
        )
        result = _run_payload(_one(conn, "SELECT * FROM fiscal_catalog_import_runs WHERE tenant_id=? AND id=?",
                                   (tenant_id, run_id), "X", "X"))
        result["catalog_version"] = published
        save_idempotent(conn, scope, key, body, 200, result)
        return 200, result


def rollback_catalog_version(catalog_id: str, target_version_id: str, data: FiscalCatalogRollback, request: Request,
                             tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json")
    scope = f"fiscal-catalog:rollback:{tenant_id}:{catalog_id}:{target_version_id}"
    with request.state.store.transaction() as conn:
        cached = get_idempotent(conn, scope, key, body)
        if cached:
            return cached
        catalog = _one(conn, "SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id),
                       "FISCAL_CATALOG_NOT_FOUND", "Catálogo fiscal não localizado.")
        target = _one(conn, "SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=? AND fiscal_catalog_id=?",
                      (tenant_id, target_version_id, catalog_id), "FISCAL_CATALOG_VERSION_NOT_FOUND", "Versão alvo não localizada.")
        if target["state"] == "draft":
            raise DomainError("FISCAL_CATALOG_ROLLBACK_DRAFT", "Não é possível rollback para versão nunca publicada.", 409)
        rows = conn.execute(
            "SELECT code,description,parent_code,metadata_json FROM fiscal_catalog_entries WHERE tenant_id=? AND fiscal_catalog_version_id=? ORDER BY code",
            (tenant_id, target_version_id),
        ).fetchall()
        number = int(catalog["latest_version_number"]) + 1
        version_id = uuid7(); now = iso_now()
        conn.execute(
            """INSERT INTO fiscal_catalog_versions(
              id,tenant_id,fiscal_catalog_id,version_number,version_label,valid_from,valid_until,source_name,source_reference,
              source_sha256,schema_version,notes,state,published_at,published_by,entries_count,version,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (version_id, tenant_id, catalog_id, number, f"rollback-v{target['version_number']}", data.effective_from.isoformat(), None,
             target["source_name"], f"rollback:{target_version_id}", target["source_sha256"], target.get("schema_version"),
             f"Rollback imutável da versão {target['version_number']}: {data.reason}", "draft", None, None,
             len(rows), 1, user.id, now, now),
        )
        for row in rows:
            conn.execute(
                "INSERT INTO fiscal_catalog_entries(id,tenant_id,fiscal_catalog_version_id,code,description,parent_code,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, version_id, row["code"], row["description"], row["parent_code"], row["metadata_json"], now),
            )
        conn.execute(
            "UPDATE fiscal_catalogs SET latest_version_number=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",
            (number, now, tenant_id, catalog_id),
        )
        catalog = _one(conn, "SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?", (tenant_id, catalog_id), "X", "X")
        published = _publish_version_in_tx(
            conn, tenant_id=tenant_id, catalog=catalog, version_id=version_id, user=user, request=request, reason=data.reason,
        )
        result = {"catalog_id": catalog_id, "target_version_id": target_version_id, "rollback_version": published}
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="rollback",
               aggregate_type="fiscal_catalog", aggregate_id=catalog_id, before=target, after=published, reason=data.reason)
        _event(conn, tenant_id=tenant_id, request=request, event_type="FiscalCatalogRolledBack",
               aggregate_type="fiscal_catalog", aggregate_id=catalog_id,
               payload={"target_version_id": target_version_id, "rollback_version_id": version_id})
        save_idempotent(conn, scope, key, body, 201, result)
        return 201, result


def list_catalog_quarantine(request: Request, tenant_id: str, state: str | None = "open") -> dict[str, Any]:
    sql = "SELECT * FROM fiscal_catalog_quarantine WHERE tenant_id=?"
    params: list[Any] = [tenant_id]
    if state:
        sql += " AND state=?"; params.append(state)
    sql += " ORDER BY created_at DESC,id LIMIT 500"
    return {"items": [_quarantine_payload(row) for row in request.state.store.fetch_all(sql, params)]}


def resolve_catalog_quarantine(quarantine_id: str, data: FiscalCatalogQuarantineResolve, request: Request,
                               tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before = _one(conn, "SELECT * FROM fiscal_catalog_quarantine WHERE tenant_id=? AND id=?", (tenant_id, quarantine_id),
                      "FISCAL_CATALOG_QUARANTINE_NOT_FOUND", "Item de quarentena não localizado.")
        if before["state"] != "open":
            return _quarantine_payload(before)
        conn.execute(
            "UPDATE fiscal_catalog_quarantine SET state=?,resolved_at=?,resolved_by=?,resolution_reason=? WHERE tenant_id=? AND id=?",
            (data.action, iso_now(), user.id, data.reason, tenant_id, quarantine_id),
        )
        after = _quarantine_payload(_one(conn, "SELECT * FROM fiscal_catalog_quarantine WHERE tenant_id=? AND id=?",
                                         (tenant_id, quarantine_id), "X", "X"))
        _audit(conn, tenant_id=tenant_id, user=user, request=request, action="resolve_quarantine",
               aggregate_type="fiscal_catalog_quarantine", aggregate_id=quarantine_id,
               before=_quarantine_payload(before), after=after, reason=data.reason)
        return after


def catalog_governance_health(request: Request, tenant_id: str) -> dict[str, Any]:
    today = date.today()
    catalogs = request.state.store.fetch_all("SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND state='active' ORDER BY kind", (tenant_id,))
    open_quarantine = request.state.store.fetch_all(
        "SELECT fiscal_catalog_id,COUNT(*) AS n FROM fiscal_catalog_quarantine WHERE tenant_id=? AND state='open' GROUP BY fiscal_catalog_id",
        (tenant_id,),
    )
    quarantine_by_catalog = {row["fiscal_catalog_id"]: int(row["n"]) for row in open_quarantine}
    items: list[dict[str, Any]] = []
    for catalog in catalogs:
        active = None
        if catalog.get("active_version_id"):
            active = request.state.store.fetch_one(
                "SELECT id,version_number,version_label,valid_from,valid_until,source_sha256,state FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?",
                (tenant_id, catalog["active_version_id"]),
            )
        sources = request.state.store.fetch_all(
            "SELECT id,provider_type,provider_key,provider_version,state,max_age_days,last_success_at,last_error FROM fiscal_catalog_source_profiles WHERE tenant_id=? AND fiscal_catalog_id=? ORDER BY created_at DESC",
            (tenant_id, catalog["id"]),
        )
        reasons: list[str] = []
        if not active:
            reasons.append("no_active_version")
        elif active.get("valid_until") and date.fromisoformat(active["valid_until"]) < today:
            reasons.append("expired")
        ready_sources = [source for source in sources if source["state"] == "ready"]
        if not sources:
            reasons.append("source_profile_missing")
        elif not ready_sources:
            reasons.append("source_not_configured")
        else:
            fresh = False
            now = datetime.now(timezone.utc)
            for source in ready_sources:
                if source.get("last_success_at"):
                    stamp = datetime.fromisoformat(str(source["last_success_at"]).replace("Z", "+00:00"))
                    if now - stamp <= timedelta(days=int(source["max_age_days"])):
                        fresh = True
                        break
            if not fresh:
                reasons.append("source_stale")
        if quarantine_by_catalog.get(catalog["id"], 0):
            reasons.append("quarantine_open")
        items.append({
            "catalog_id": catalog["id"], "kind": catalog["kind"], "name": catalog["name"],
            "healthy": not reasons, "reasons": reasons, "active_version": active,
            "source_profiles": sources, "open_quarantine": quarantine_by_catalog.get(catalog["id"], 0),
        })
    configured_kinds = {item["kind"] for item in items}
    missing_kinds = [kind for kind in SUPPORTED_KINDS if kind not in configured_kinds]
    return {
        "healthy": bool(items) and all(item["healthy"] for item in items) and not missing_kinds,
        "catalogs": items,
        "configured_count": len(items),
        "missing_kinds": missing_kinds,
        "outdated_kinds": [item["kind"] for item in items if not item["healthy"]],
        "open_quarantine": sum(quarantine_by_catalog.values()),
        "checked_on": today.isoformat(),
    }
