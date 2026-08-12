from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.integrations.providers import DisabledTransport, IntegrationError, WWSoftwaresCsvProvider
from app.modules.fiscal.application.transparency_service import resolve_ibpt_profile

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
    profile = resolve_ibpt_profile(store, tenant_id, date.today())
    if profile and profile["mode"] != "remote_sync":
        store.execute(
            "UPDATE ibpt_sync_runs SET state='failed',error_code='IBPT_PROFILE_REMOTE_SYNC_DISABLED',error_message=?,finished_at=? WHERE tenant_id=? AND id=?",
            (f"Perfil IBPT publicado em modo {profile['mode']} não permite download remoto.", iso_now(), tenant_id, run_id),
        )
        return {"state": "failed", "error_code": "IBPT_PROFILE_REMOTE_SYNC_DISABLED", "profile_id": profile["id"]}
    provider_config = {
        "base_url": profile["base_url"] if profile else settings.ibpt_api_base_url,
        "uf_path": profile["uf_path"] if profile else settings.ibpt_api_uf_path,
    }
    provider = WWSoftwaresCsvProvider(
        config=provider_config,
        secret="",
        transport=transport or (None if settings.integration_remote_enabled else DisabledTransport()),
    )
    raw = b""; source_url = None
    try:
        source_url, raw = provider.fetch_uf(uf)
        rates = parse_ibpt_csv(raw, uf=uf)
    except (IntegrationError, ValueError) as exc:
        if raw and isinstance(exc, ValueError):
            quarantine_ibpt_payload(router,tenant_id=tenant_id,run_id=run_id,uf=uf,source_url=source_url,raw=raw,reason_code="IBPT_PARSE_FAILED",reason_message=str(exc))
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


def quarantine_ibpt_payload(router, *, tenant_id: str, run_id: str, uf: str, source_url: str | None, raw: bytes, reason_code: str, reason_message: str) -> dict[str, Any]:
    store=router.tenant_store(tenant_id); digest=hashlib.sha256(raw).hexdigest(); qid=uuid7(); now=iso_now(); key=f"fiscal/ibpt/quarantine/{uf}/{digest}.csv"
    stored=router.object_storage(tenant_id).put_bytes(key,raw,content_type="text/csv")
    with store.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO ibpt_quarantine_items(id,tenant_id,sync_run_id,uf,source_url,sha256,storage_key,bytes_count,reason_code,reason_message,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(qid,tenant_id,run_id,uf,source_url,digest,key,len(raw),reason_code,reason_message[:2000],'open',now))
        add_outbox(conn,tenant_id=tenant_id,event_type='IbptPayloadQuarantined',aggregate_type='ibpt_quarantine',aggregate_id=qid,payload={'uf':uf,'sha256':digest,'reason_code':reason_code},correlation_id=uuid7())
    return {'id':qid,'uf':uf,'sha256':stored.sha256,'state':'open'}

def ibpt_rollback(router, *, tenant_id: str, snapshot_id: str, actor_id: str, correlation_id: str) -> dict[str, Any]:
    store=router.tenant_store(tenant_id); now=iso_now()
    with store.transaction() as conn:
        target=conn.execute("SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND id=?",(tenant_id,snapshot_id)).fetchone()
        if not target: raise ValueError('snapshot IBPT não localizado')
        target=dict(target); current=conn.execute("SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND uf=? AND state='active'",(tenant_id,target['uf'])).fetchone()
        conn.execute("UPDATE ibpt_snapshots SET state='superseded' WHERE tenant_id=? AND uf=? AND state='active'",(tenant_id,target['uf']))
        conn.execute("UPDATE ibpt_snapshots SET state='active' WHERE tenant_id=? AND id=?",(tenant_id,snapshot_id))
        add_audit(conn,tenant_id=tenant_id,actor_id=actor_id,action='rollback',aggregate_type='ibpt_snapshot',aggregate_id=snapshot_id,correlation_id=correlation_id,before=dict(current) if current else None,after={'id':snapshot_id,'state':'active'})
        add_outbox(conn,tenant_id=tenant_id,event_type='IbptSnapshotRolledBack',aggregate_type='ibpt_snapshot',aggregate_id=snapshot_id,payload={'snapshot_id':snapshot_id,'uf':target['uf']},correlation_id=correlation_id)
    return {'snapshot_id':snapshot_id,'uf':target['uf'],'state':'active','rolled_back_at':now}

def ibpt_offline_package(router, *, tenant_id: str, uf: str) -> dict[str, Any]:
    store=router.tenant_store(tenant_id); uf=normalize_uf(uf); snap=store.fetch_one("SELECT * FROM ibpt_snapshots WHERE tenant_id=? AND uf=? AND state='active' ORDER BY created_at DESC LIMIT 1",(tenant_id,uf))
    if not snap: raise ValueError('snapshot IBPT ativo não localizado')
    rates=store.fetch_all("SELECT code,ex,item_type,description,national_federal,imported_federal,state_rate,municipal_rate,effective_from,effective_to,source_version,source_name FROM ibpt_rates WHERE tenant_id=? AND snapshot_id=? ORDER BY code,ex,item_type",(tenant_id,snap['id']))
    payload={'format':'pige360-ibpt-offline-v1','uf':uf,'snapshot':{'id':snap['id'],'sha256':snap['sha256'],'source_version':snap.get('source_version'),'effective_from':snap.get('effective_from'),'effective_to':snap.get('effective_to')},'rates':rates,'purpose':'transparencia_vtottrib','tax_calculation_source':False}
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode(); payload['package_sha256']=hashlib.sha256(encoded).hexdigest(); return payload

def ibpt_operational_status(router, *, tenant_id: str) -> dict[str, Any]:
    store=router.tenant_store(tenant_id); active=store.fetch_all("SELECT uf,id,sha256,source_version,effective_to,created_at FROM ibpt_snapshots WHERE tenant_id=? AND state='active' ORDER BY uf",(tenant_id,)); by={r['uf']:r for r in active}; failed=store.scalar("SELECT COUNT(*) FROM ibpt_sync_runs WHERE tenant_id=? AND state IN ('failed','retry_pending')",(tenant_id,)) or 0; quarantine=store.scalar("SELECT COUNT(*) FROM ibpt_quarantine_items WHERE tenant_id=? AND state='open'",(tenant_id,)) or 0
    alerts=[]
    if len(by)<27: alerts.append({'code':'IBPT_UF_MISSING','count':27-len(by)})
    if failed: alerts.append({'code':'IBPT_SYNC_FAILURES','count':int(failed)})
    if quarantine: alerts.append({'code':'IBPT_QUARANTINE_OPEN','count':int(quarantine)})
    return {'provider':router.settings.ibpt_provider,'active':list(by.values()),'missing_ufs':[u for u in UFS if u not in by],'all_ufs_ready':len(by)==27,'failed_or_retry':int(failed),'quarantine_open':int(quarantine),'alerts':alerts}
