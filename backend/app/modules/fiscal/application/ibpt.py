from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.integrations.providers import DisabledTransport, IntegrationError, WWSoftwaresCsvProvider

UFS = tuple("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
_UF_SET = frozenset(UFS)


def normalize_uf(uf: str) -> str:
    value = str(uf or "").strip().upper()
    if value not in _UF_SET:
        raise ValueError("UF inválida")
    return value


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", normalized.lower())


def _decimal(value: Any) -> str:
    raw = str(value or "0").strip().replace("%", "").replace(" ", "")
    if not raw:
        return "0.0000"
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        return format(Decimal(raw).quantize(Decimal("0.0001")), "f")
    except InvalidOperation as exc:
        raise ValueError(f"percentual IBPT inválido: {value}") from exc


def _date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return raw[:32]


def parse_ibpt_csv(raw: bytes, *, uf: str) -> list[dict[str, Any]]:
    normalized_uf = normalize_uf(uf)
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV IBPT sem cabeçalho")
    rows: list[dict[str, Any]] = []
    for line_no, source in enumerate(reader, start=2):
        mapped = {_key(str(k)): (v or "").strip() for k, v in source.items() if k is not None}
        code = mapped.get("codigo") or mapped.get("ncm") or mapped.get("nbs") or ""
        if not code:
            continue
        rows.append({
            "uf": normalized_uf,
            "code": re.sub(r"[^0-9A-Za-z]", "", code),
            "ex": mapped.get("ex", ""),
            "item_type": mapped.get("tipo", ""),
            "description": mapped.get("descricao") or mapped.get("description") or code,
            "national_federal": _decimal(mapped.get("nacionalfederal") or mapped.get("federalnacional") or 0),
            "imported_federal": _decimal(mapped.get("importadosfederal") or mapped.get("federalimportado") or 0),
            "state_rate": _decimal(mapped.get("estadual") or 0),
            "municipal_rate": _decimal(mapped.get("municipal") or 0),
            "effective_from": _date(mapped.get("vigenciainicio") or mapped.get("iniciovigencia")),
            "effective_to": _date(mapped.get("vigenciafim") or mapped.get("fimvigencia")),
            "source_version": mapped.get("versao") or mapped.get("version") or None,
            "source_name": mapped.get("fonte") or "IBPT/WWSoftwares",
            "line_no": line_no,
        })
    if not rows:
        raise ValueError("CSV IBPT não contém registros classificáveis")
    return rows


def queue_ibpt_sync(store, *, tenant_id: str, ufs: list[str], actor_id: str | None, correlation_id: str | None) -> list[dict[str, Any]]:
    normalized = list(dict.fromkeys(normalize_uf(uf) for uf in ufs))
    now = iso_now(); created: list[dict[str, Any]] = []
    with store.transaction() as conn:
        for uf in normalized:
            existing = conn.execute(
                "SELECT * FROM ibpt_sync_runs WHERE tenant_id=? AND uf=? AND state IN ('queued','running','retry_pending') ORDER BY requested_at DESC LIMIT 1",
                (tenant_id, uf),
            ).fetchone()
            if existing:
                created.append(dict(existing)); continue
            run_id = uuid7()
            conn.execute(
                "INSERT INTO ibpt_sync_runs(id,tenant_id,uf,state,requested_by,requested_at) VALUES(?,?,?,?,?,?)",
                (run_id, tenant_id, uf, "queued", actor_id, now),
            )
            payload = {"run_id": run_id, "uf": uf}
            add_outbox(
                conn, tenant_id=tenant_id, event_type="IbptSyncRequested", aggregate_type="ibpt_sync_run",
                aggregate_id=run_id, payload=payload, correlation_id=correlation_id or uuid7(),
            )
            if actor_id:
                add_audit(
                    conn, tenant_id=tenant_id, actor_id=actor_id, action="request_sync",
                    aggregate_type="ibpt_sync_run", aggregate_id=run_id,
                    correlation_id=correlation_id, after=payload,
                )
            created.append({"id": run_id, "tenant_id": tenant_id, "uf": uf, "state": "queued", "requested_at": now})
    return created


def _active_rates(store, tenant_id: str, uf: str) -> tuple[dict[str, Any] | None, dict[tuple[str, str, str], tuple[str, ...]]]:
    snapshot = store.fetch_one(
        "SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND uf=? AND state='active' ORDER BY created_at DESC LIMIT 1",
        (tenant_id, uf),
    )
    if not snapshot:
        return None, {}
    rates = store.fetch_all(
        "SELECT code,ex,item_type,national_federal,imported_federal,state_rate,municipal_rate,effective_from,effective_to FROM ibpt_rates WHERE tenant_id=? AND snapshot_id=?",
        (tenant_id, snapshot["id"]),
    )
    current = {
        (str(r["code"]), str(r.get("ex") or ""), str(r.get("item_type") or "")): (
            _decimal(r["national_federal"]), _decimal(r["imported_federal"]), _decimal(r["state_rate"]), _decimal(r["municipal_rate"]),
            str(r.get("effective_from") or ""), str(r.get("effective_to") or ""),
        ) for r in rates
    }
    return snapshot, current


def execute_ibpt_sync(router, *, tenant_id: str, run_id: str, transport=None) -> dict[str, Any]:
    store = router.tenant_store(tenant_id)
    run = store.fetch_one("SELECT * FROM ibpt_sync_runs WHERE tenant_id=? AND id=?", (tenant_id, run_id))
    if not run:
        return {"state": "ignored", "reason": "sync_run_not_found"}
    if run["state"] in {"completed", "unchanged"}:
        return {"state": run["state"], "snapshot_id": run.get("snapshot_id"), "idempotent": True}
    uf = normalize_uf(str(run["uf"])); now = iso_now()
    store.execute(
        "UPDATE ibpt_sync_runs SET state='running',started_at=COALESCE(started_at,?),error_code=NULL,error_message=NULL WHERE tenant_id=? AND id=?",
        (now, tenant_id, run_id),
    )
    settings = router.settings
    provider = WWSoftwaresCsvProvider(
        config={"base_url": settings.ibpt_api_base_url, "uf_path": settings.ibpt_api_uf_path},
        secret="",
        transport=transport or (None if settings.integration_remote_enabled else DisabledTransport()),
    )
    try:
        source_url, raw = provider.fetch_uf(uf)
        rates = parse_ibpt_csv(raw, uf=uf)
    except (IntegrationError, ValueError) as exc:
        retryable = isinstance(exc, IntegrationError) and exc.retryable
        store.execute(
            "UPDATE ibpt_sync_runs SET state=?,error_code=?,error_message=?,finished_at=? WHERE tenant_id=? AND id=?",
            ("retry_pending" if retryable else "failed", getattr(exc, "code", "IBPT_PARSE_FAILED"), str(exc)[:2000], None if retryable else iso_now(), tenant_id, run_id),
        )
        if retryable:
            raise TimeoutError(str(exc)) from exc
        return {"state": "failed", "error_code": getattr(exc, "code", "IBPT_PARSE_FAILED")}

    digest = hashlib.sha256(raw).hexdigest()
    previous, previous_map = _active_rates(store, tenant_id, uf)
    if previous and previous["sha256"] == digest:
        store.execute(
            "UPDATE ibpt_sync_runs SET state='unchanged',snapshot_id=?,finished_at=? WHERE tenant_id=? AND id=?",
            (previous["id"], iso_now(), tenant_id, run_id),
        )
        return {"state": "unchanged", "snapshot_id": previous["id"], "uf": uf, "sha256": digest, "rows": len(rates), "diff": {"added": 0, "removed": 0, "changed": 0}}

    new_map = {
        (r["code"], r["ex"], r["item_type"]): (
            r["national_federal"], r["imported_federal"], r["state_rate"], r["municipal_rate"],
            r["effective_from"] or "", r["effective_to"] or "",
        ) for r in rates
    }
    prev_keys = set(previous_map); new_keys = set(new_map)
    diff = {
        "added": len(new_keys - prev_keys),
        "removed": len(prev_keys - new_keys),
        "changed": sum(1 for key in new_keys & prev_keys if new_map[key] != previous_map[key]),
    }
    snapshot_id = uuid7(); created_at = iso_now()
    storage_key = f"fiscal/ibpt/{uf}/{digest}.csv"
    stored = router.object_storage(tenant_id).put_bytes(storage_key, raw, content_type="text/csv")
    if stored.sha256 != digest:
        raise RuntimeError("hash do snapshot IBPT divergiu durante storage")
    effective_from = min((r["effective_from"] for r in rates if r["effective_from"]), default=None)
    effective_to = max((r["effective_to"] for r in rates if r["effective_to"]), default=None)
    source_versions = sorted({str(r["source_version"]) for r in rates if r["source_version"]})
    source_version = ",".join(source_versions)[:200] if source_versions else None
    with store.transaction() as conn:
        conn.execute("UPDATE ibpt_snapshots SET state='superseded' WHERE tenant_id=? AND uf=? AND state='active'", (tenant_id, uf))
        conn.execute(
            "INSERT INTO ibpt_snapshots(id,tenant_id,uf,source_url,sha256,storage_key,rows_count,source_version,effective_from,effective_to,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (snapshot_id, tenant_id, uf, source_url, digest, storage_key, len(rates), source_version, effective_from, effective_to, "active", created_at),
        )
        for rate in rates:
            conn.execute(
                "INSERT INTO ibpt_rates(id,tenant_id,snapshot_id,uf,code,ex,item_type,description,national_federal,imported_federal,state_rate,municipal_rate,effective_from,effective_to,source_version,source_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, snapshot_id, uf, rate["code"], rate["ex"], rate["item_type"], rate["description"], rate["national_federal"], rate["imported_federal"], rate["state_rate"], rate["municipal_rate"], rate["effective_from"], rate["effective_to"], rate["source_version"], rate["source_name"], created_at),
            )
        conn.execute(
            "UPDATE ibpt_sync_runs SET state='completed',snapshot_id=?,finished_at=? WHERE tenant_id=? AND id=?",
            (snapshot_id, iso_now(), tenant_id, run_id),
        )
        add_outbox(
            conn, tenant_id=tenant_id, event_type="IbptSnapshotPublished", aggregate_type="ibpt_snapshot",
            aggregate_id=snapshot_id, payload={"snapshot_id": snapshot_id, "uf": uf, "sha256": digest, "rows": len(rates), "diff": diff}, correlation_id=uuid7(),
        )
    return {"state": "completed", "snapshot_id": snapshot_id, "uf": uf, "sha256": digest, "rows": len(rates), "source_version": source_version, "effective_from": effective_from, "effective_to": effective_to, "diff": diff}
