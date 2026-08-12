from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from typing import Any, Iterable

from fastapi import Request

from app.modules.fiscal.presentation.catalog_schemas import (
    FiscalCatalogCreate,
    FiscalCatalogVersionCreate,
    FiscalCatalogVersionPublish,
    FiscalClassificationRuleCreate,
    FiscalClassificationRulePatch,
    FiscalClassificationRulePublish,
)
from app.modules.operations.common import dumps, loads
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser

CATALOG_FIELD_MAP = {
    "NCM": "ncm", "NBS": "nbs", "LC116": "lc116", "CFOP": "cfop", "CEST": "cest",
    "CST": "cst", "CSOSN": "csosn", "CST_IBS_CBS": "cst_ibs_cbs", "CCLASSTRIB": "cclasstrib", "CBENEF": "cbenef",
}
EFFECTIVE_STATES = {"published", "scheduled", "superseded"}


def _one(conn: sqlite3.Connection, sql: str, params: Iterable[Any], code: str, detail: str) -> dict[str, Any]:
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        raise DomainError(code, detail, 404)
    return dict(row)


def _audit(conn, *, tenant_id: str, user: CurrentUser, request: Request, action: str, aggregate_type: str, aggregate_id: str, before=None, after=None, reason=None):
    add_audit(conn, tenant_id=tenant_id, actor_id=user.id, action=action, aggregate_type=aggregate_type,
              aggregate_id=aggregate_id, correlation_id=request.state.correlation_id, before=before, after=after, reason=reason)


def _event(conn, *, tenant_id: str, request: Request, event_type: str, aggregate_type: str, aggregate_id: str, payload: Any):
    add_outbox(conn, tenant_id=tenant_id, event_type=event_type, aggregate_type=aggregate_type,
               aggregate_id=aggregate_id, payload=payload, correlation_id=request.state.correlation_id)


def _catalog_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row); out["metadata"] = loads(out.pop("metadata_json", "{}"), {}); out["status"] = out.get("state")
    return out


def _version_payload(conn: sqlite3.Connection, row: dict[str, Any], include_entries: bool = False) -> dict[str, Any]:
    out = dict(row); out["status"] = out.get("state")
    if include_entries:
        entries = conn.execute("SELECT id,code,description,parent_code,metadata_json FROM fiscal_catalog_entries WHERE tenant_id=? AND fiscal_catalog_version_id=? ORDER BY code", (row["tenant_id"], row["id"])).fetchall()
        out["entries"] = [{**dict(e), "metadata": loads(e["metadata_json"], {})} for e in entries]
        for e in out["entries"]: e.pop("metadata_json", None)
    return out


def _rule_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row); out["tax_configuration"] = loads(out.pop("tax_configuration_json", "{}"), {}); out["status"] = out.get("state")
    return out


def _normalize_entry(normalization: str, value: str) -> str:
    value = value.strip().upper()
    if normalization == "digits": return "".join(c for c in value if c.isdigit())
    if normalization == "upper_alnum": return "".join(c for c in value if c.isalnum())
    return value


def _entries_digest(entries: list[dict[str, Any]]) -> str:
    body = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def list_catalogs(request: Request, tenant_id: str, kind: str | None = None) -> dict[str, Any]:
    sql = "SELECT * FROM fiscal_catalogs WHERE tenant_id=?"; params: list[Any] = [tenant_id]
    if kind: sql += " AND kind=?"; params.append(kind)
    sql += " ORDER BY kind,name,id"
    items = [_catalog_payload(x) for x in request.state.store.fetch_all(sql, params)]
    for item in items:
        if item.get("active_version_id"):
            item["active_version"] = request.state.store.fetch_one("SELECT id,version_number,version_label,valid_from,valid_until,state,entries_count,source_sha256 FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?", (tenant_id, item["active_version_id"]))
        else: item["active_version"] = None
    return {"items": items}


def create_catalog(data: FiscalCatalogCreate, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body = data.model_dump(mode="json"); scope=f"fiscal-catalog:create:{tenant_id}"; now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached: return cached
        if conn.execute("SELECT 1 FROM fiscal_catalogs WHERE tenant_id=? AND kind=?",(tenant_id,data.kind)).fetchone():
            raise DomainError("FISCAL_CATALOG_EXISTS","Já existe catálogo deste tipo para o tenant.",409)
        cid=uuid7()
        conn.execute("INSERT INTO fiscal_catalogs(id,tenant_id,kind,name,description,normalization,code_pattern,metadata_json,state,active_version_id,latest_version_number,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid,tenant_id,data.kind,data.name,data.description,data.normalization,data.code_pattern,dumps(data.metadata),"active",None,0,1,user.id,now,now))
        result={"id":cid,**body,"status":"active","active_version_id":None,"latest_version_number":0,"version":1,"created_at":now,"updated_at":now}
        _audit(conn,tenant_id=tenant_id,user=user,request=request,action="create",aggregate_type="fiscal_catalog",aggregate_id=cid,after=result)
        _event(conn,tenant_id=tenant_id,request=request,event_type="FiscalCatalogCreated",aggregate_type="fiscal_catalog",aggregate_id=cid,payload={"kind":data.kind})
        save_idempotent(conn,scope,key,body,201,result)
        return 201,result


def catalog_detail(request: Request, tenant_id: str, catalog_id: str) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        row=_one(conn,"SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?",(tenant_id,catalog_id),"FISCAL_CATALOG_NOT_FOUND","Catálogo fiscal não localizado.")
        out=_catalog_payload(row)
        versions=conn.execute("SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND fiscal_catalog_id=? ORDER BY version_number DESC",(tenant_id,catalog_id)).fetchall()
        out["versions"]=[_version_payload(conn,dict(v),False) for v in versions]
        return out


def create_catalog_version(catalog_id: str, data: FiscalCatalogVersionCreate, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json"); scope=f"fiscal-catalog-version:create:{tenant_id}:{catalog_id}"; now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        catalog=_one(conn,"SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?",(tenant_id,catalog_id),"FISCAL_CATALOG_NOT_FOUND","Catálogo fiscal não localizado.")
        normalized=[]
        pattern=re.compile(catalog["code_pattern"]) if catalog.get("code_pattern") else None
        for entry in data.entries:
            code=_normalize_entry(catalog["normalization"],entry.code)
            if not code: raise DomainError("FISCAL_CATALOG_CODE_EMPTY","Código vazio após normalização.",422)
            if pattern and not pattern.fullmatch(code): raise DomainError("FISCAL_CATALOG_CODE_INVALID",f"Código {code} não atende ao padrão do catálogo.",422)
            normalized.append({"code":code,"description":entry.description,"parent_code":_normalize_entry(catalog["normalization"],entry.parent_code) if entry.parent_code else None,"metadata":entry.metadata})
        codes=[e["code"] for e in normalized]
        if len(codes)!=len(set(codes)): raise DomainError("FISCAL_CATALOG_CODE_DUPLICATE","Códigos duplicados após normalização.",422)
        vid=uuid7(); number=int(catalog["latest_version_number"])+1; digest=data.source_sha256 or _entries_digest(normalized)
        conn.execute("INSERT INTO fiscal_catalog_versions(id,tenant_id,fiscal_catalog_id,version_number,version_label,valid_from,valid_until,source_name,source_reference,source_sha256,schema_version,notes,state,published_at,published_by,entries_count,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (vid,tenant_id,catalog_id,number,data.version_label,data.valid_from.isoformat(),data.valid_until.isoformat() if data.valid_until else None,data.source_name,data.source_reference,digest,data.schema_version,data.notes,"draft",None,None,len(normalized),1,user.id,now,now))
        for entry in normalized:
            conn.execute("INSERT INTO fiscal_catalog_entries(id,tenant_id,fiscal_catalog_version_id,code,description,parent_code,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,vid,entry["code"],entry["description"],entry["parent_code"],dumps(entry["metadata"]),now))
        conn.execute("UPDATE fiscal_catalogs SET latest_version_number=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(number,now,tenant_id,catalog_id))
        result=_version_payload(conn,_one(conn,"SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?",(tenant_id,vid),"X","X"),True)
        _audit(conn,tenant_id=tenant_id,user=user,request=request,action="create_version",aggregate_type="fiscal_catalog",aggregate_id=catalog_id,after=result)
        _event(conn,tenant_id=tenant_id,request=request,event_type="FiscalCatalogVersionCreated",aggregate_type="fiscal_catalog",aggregate_id=catalog_id,payload={"version_id":vid,"version_number":number,"entries_count":len(normalized),"source_sha256":digest})
        save_idempotent(conn,scope,key,body,201,result)
        return 201,result


def publish_catalog_version(catalog_id: str, version_id: str, data: FiscalCatalogVersionPublish, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json"); scope=f"fiscal-catalog-version:publish:{tenant_id}:{version_id}"; now=iso_now(); today=date.today().isoformat()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        catalog=_one(conn,"SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?",(tenant_id,catalog_id),"FISCAL_CATALOG_NOT_FOUND","Catálogo fiscal não localizado.")
        version=_one(conn,"SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=? AND fiscal_catalog_id=?",(tenant_id,version_id,catalog_id),"FISCAL_CATALOG_VERSION_NOT_FOUND","Versão fiscal não localizada.")
        if int(version["version"])!=data.expected_version: raise DomainError("VERSION_CONFLICT","A versão do catálogo foi alterada por outro processo.",409)
        if version["state"]!="draft":
            result=_version_payload(conn,version,False); save_idempotent(conn,scope,key,body,200,result); return 200,result
        overlap=conn.execute("SELECT id FROM fiscal_catalog_versions WHERE tenant_id=? AND fiscal_catalog_id=? AND id<>? AND state IN ('published','scheduled','superseded') AND valid_from<=COALESCE(?, '9999-12-31') AND COALESCE(valid_until,'9999-12-31')>=? LIMIT 1",(tenant_id,catalog_id,version_id,version["valid_until"],version["valid_from"])).fetchone()
        if overlap: raise DomainError("FISCAL_CATALOG_PERIOD_OVERLAP","Já existe versão publicada com vigência sobreposta.",409)
        state="published" if version["valid_from"]<=today else "scheduled"
        conn.execute("UPDATE fiscal_catalog_versions SET state=?,published_at=?,published_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(state,now,user.id,now,tenant_id,version_id))
        if state=="published": conn.execute("UPDATE fiscal_catalogs SET active_version_id=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(version_id,now,tenant_id,catalog_id))
        result=_version_payload(conn,_one(conn,"SELECT * FROM fiscal_catalog_versions WHERE tenant_id=? AND id=?",(tenant_id,version_id),"X","X"),False)
        _audit(conn,tenant_id=tenant_id,user=user,request=request,action="publish",aggregate_type="fiscal_catalog",aggregate_id=catalog_id,before=_version_payload(conn,version,False),after=result,reason=data.reason)
        _event(conn,tenant_id=tenant_id,request=request,event_type="FiscalCatalogVersionPublished" if state=="published" else "FiscalCatalogVersionScheduled",aggregate_type="fiscal_catalog",aggregate_id=catalog_id,payload={"version_id":version_id,"state":state,"valid_from":version["valid_from"]})
        save_idempotent(conn,scope,key,body,200,result); return 200,result


def resolve_catalog_code(request: Request, tenant_id: str, catalog_id: str, code: str, occurred_on: date) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        catalog=_one(conn,"SELECT * FROM fiscal_catalogs WHERE tenant_id=? AND id=?",(tenant_id,catalog_id),"FISCAL_CATALOG_NOT_FOUND","Catálogo fiscal não localizado.")
        normalized=_normalize_entry(catalog["normalization"],code); when=occurred_on.isoformat()
        rows=conn.execute("SELECT v.*,e.id AS entry_id,e.code,e.description AS entry_description,e.parent_code,e.metadata_json AS entry_metadata_json FROM fiscal_catalog_versions v JOIN fiscal_catalog_entries e ON e.fiscal_catalog_version_id=v.id AND e.tenant_id=v.tenant_id WHERE v.tenant_id=? AND v.fiscal_catalog_id=? AND v.state IN ('published','scheduled','superseded') AND v.valid_from<=? AND (v.valid_until IS NULL OR v.valid_until>=?) AND e.code=? ORDER BY v.valid_from DESC,v.version_number DESC",(tenant_id,catalog_id,when,when,normalized)).fetchall()
        if not rows: raise DomainError("FISCAL_CATALOG_ENTRY_NOT_FOUND","Código não localizado em versão vigente do catálogo.",404)
        row=dict(rows[0])
        return {"catalog":{"id":catalog_id,"kind":catalog["kind"],"name":catalog["name"]},"version":{"id":row["id"],"version_number":row["version_number"],"version_label":row["version_label"],"valid_from":row["valid_from"],"valid_until":row["valid_until"],"source_sha256":row["source_sha256"]},"entry":{"id":row["entry_id"],"code":row["code"],"description":row["entry_description"],"parent_code":row["parent_code"],"metadata":loads(row["entry_metadata_json"],{})}}


def _validate_rule_codes(conn: sqlite3.Connection, tenant_id: str, data: FiscalClassificationRuleCreate) -> None:
    when=data.valid_from.isoformat()
    for kind,field in CATALOG_FIELD_MAP.items():
        code=getattr(data,field)
        if not code: continue
        row=conn.execute("SELECT c.id,c.normalization,c.kind FROM fiscal_catalogs c WHERE c.tenant_id=? AND c.kind=? AND c.state='active'",(tenant_id,kind)).fetchone()
        if not row: raise DomainError("FISCAL_CATALOG_REQUIRED",f"Catálogo {kind} ainda não foi configurado.",422)
        normalized=_normalize_entry(row["normalization"],code)
        exists=conn.execute("SELECT 1 FROM fiscal_catalog_versions v JOIN fiscal_catalog_entries e ON e.fiscal_catalog_version_id=v.id AND e.tenant_id=v.tenant_id WHERE v.tenant_id=? AND v.fiscal_catalog_id=? AND v.state IN ('published','scheduled','superseded') AND v.valid_from<=? AND (v.valid_until IS NULL OR v.valid_until>=?) AND e.code=? LIMIT 1",(tenant_id,row["id"],when,when,normalized)).fetchone()
        if not exists: raise DomainError("FISCAL_CLASSIFICATION_CODE_NOT_EFFECTIVE",f"Código {code} de {kind} não existe em versão vigente para {when}.",422)
        setattr(data,field,normalized)


def list_classification_rules(request: Request, tenant_id: str, fiscal_context_id: str | None = None, status: str | None = None) -> dict[str, Any]:
    sql="SELECT * FROM fiscal_classification_rules WHERE tenant_id=?"; params:[Any]=[tenant_id]
    if fiscal_context_id: sql+=" AND fiscal_context_id=?"; params.append(fiscal_context_id)
    if status: sql+=" AND state=?"; params.append(status)
    sql+=" ORDER BY priority DESC,valid_from DESC,id"
    return {"items":[_rule_payload(x) for x in request.state.store.fetch_all(sql,params)]}


def create_classification_rule(data: FiscalClassificationRuleCreate, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json"); scope=f"fiscal-classification:create:{tenant_id}"; now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        _one(conn,"SELECT id FROM fiscal_contexts WHERE tenant_id=? AND id=? AND state='active'",(tenant_id,data.fiscal_context_id),"FISCAL_CONTEXT_NOT_FOUND","Contexto fiscal não localizado.")
        if data.item_id:
            table="products" if data.item_kind=="product" else "services" if data.item_kind=="service" else None
            if not table: raise DomainError("FISCAL_ITEM_KIND_INVALID","item_id exige product ou service.",422)
            _one(conn,f"SELECT id FROM {table} WHERE tenant_id=? AND id=?",(tenant_id,data.item_id),"FISCAL_ITEM_NOT_FOUND","Item não localizado no tenant.")
        _validate_rule_codes(conn,tenant_id,data)
        rid=uuid7(); values=data.model_dump(mode="json")
        conn.execute("INSERT INTO fiscal_classification_rules(id,tenant_id,fiscal_context_id,establishment_code,item_kind,item_id,operation_type,valid_from,valid_until,priority,ncm,nbs,lc116,cfop,cest,cst,csosn,cst_ibs_cbs,cclasstrib,cbenef,municipal_code,cnae,tax_configuration_json,notes,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid,tenant_id,data.fiscal_context_id,data.establishment_code,data.item_kind,data.item_id,data.operation_type,data.valid_from.isoformat(),data.valid_until.isoformat() if data.valid_until else None,data.priority,data.ncm,data.nbs,data.lc116,data.cfop,data.cest,data.cst,data.csosn,data.cst_ibs_cbs,data.cclasstrib,data.cbenef,data.municipal_code,data.cnae,dumps(data.tax_configuration),data.notes,"draft",1,user.id,now,now))
        result=_rule_payload(_one(conn,"SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND id=?",(tenant_id,rid),"X","X"))
        _audit(conn,tenant_id=tenant_id,user=user,request=request,action="create",aggregate_type="fiscal_classification_rule",aggregate_id=rid,after=result)
        _event(conn,tenant_id=tenant_id,request=request,event_type="FiscalClassificationRuleCreated",aggregate_type="fiscal_classification_rule",aggregate_id=rid,payload={"context_id":data.fiscal_context_id,"item_kind":data.item_kind})
        save_idempotent(conn,scope,key,body,201,result); return 201,result


def patch_classification_rule(rule_id: str, data: FiscalClassificationRulePatch, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        before=_one(conn,"SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND id=?",(tenant_id,rule_id),"FISCAL_CLASSIFICATION_RULE_NOT_FOUND","Regra fiscal não localizada.")
        if before["state"]!="draft": raise DomainError("FISCAL_CLASSIFICATION_IMMUTABLE","Regra publicada é imutável; crie nova regra por vigência.",409)
        if int(before["version"])!=data.expected_version: raise DomainError("VERSION_CONFLICT","A regra foi alterada por outro processo.",409)
        changes=[]; params=[]
        for field,column,transform in (("valid_until","valid_until",lambda x:x.isoformat() if x else None),("priority","priority",lambda x:x),("tax_configuration","tax_configuration_json",dumps),("notes","notes",lambda x:x),("status","state",lambda x:x)):
            value=getattr(data,field)
            if value is not None: changes.append(f"{column}=?"); params.append(transform(value))
        if not changes:return _rule_payload(before)
        changes += ["version=version+1","updated_at=?"]; params += [iso_now(),tenant_id,rule_id]
        conn.execute(f"UPDATE fiscal_classification_rules SET {','.join(changes)} WHERE tenant_id=? AND id=?",params)
        after=_rule_payload(_one(conn,"SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND id=?",(tenant_id,rule_id),"X","X"))
        _audit(conn,tenant_id=tenant_id,user=user,request=request,action="update",aggregate_type="fiscal_classification_rule",aggregate_id=rule_id,before=_rule_payload(before),after=after)
        _event(conn,tenant_id=tenant_id,request=request,event_type="FiscalClassificationRuleUpdated",aggregate_type="fiscal_classification_rule",aggregate_id=rule_id,payload={"version":after["version"]})
        return after


def publish_classification_rule(rule_id: str, data: FiscalClassificationRulePublish, request: Request, tenant_id: str, user: CurrentUser, key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json"); scope=f"fiscal-classification:publish:{tenant_id}:{rule_id}"; now=iso_now()
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        before=_one(conn,"SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND id=?",(tenant_id,rule_id),"FISCAL_CLASSIFICATION_RULE_NOT_FOUND","Regra fiscal não localizada.")
        if before["state"]=="published": result=_rule_payload(before); save_idempotent(conn,scope,key,body,200,result); return 200,result
        if before["state"]!="draft": raise DomainError("FISCAL_CLASSIFICATION_NOT_PUBLISHABLE","A regra não está em rascunho.",409)
        if int(before["version"])!=data.expected_version: raise DomainError("VERSION_CONFLICT","A regra foi alterada por outro processo.",409)
        # same-specificity overlap is forbidden; different priorities/specificities are deterministic.
        overlap=conn.execute("SELECT id FROM fiscal_classification_rules WHERE tenant_id=? AND fiscal_context_id=? AND id<>? AND state='published' AND item_kind=? AND COALESCE(item_id,'')=COALESCE(?, '') AND operation_type=? AND COALESCE(establishment_code,'')=COALESCE(?, '') AND valid_from<=COALESCE(?, '9999-12-31') AND COALESCE(valid_until,'9999-12-31')>=? LIMIT 1",(tenant_id,before["fiscal_context_id"],rule_id,before["item_kind"],before["item_id"],before["operation_type"],before["establishment_code"],before["valid_until"],before["valid_from"])).fetchone()
        if overlap: raise DomainError("FISCAL_CLASSIFICATION_PERIOD_OVERLAP","Existe regra publicada com o mesmo escopo e vigência sobreposta.",409)
        conn.execute("UPDATE fiscal_classification_rules SET state='published',published_at=?,published_by=?,version=version+1,updated_at=? WHERE tenant_id=? AND id=?",(now,user.id,now,tenant_id,rule_id))
        result=_rule_payload(_one(conn,"SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND id=?",(tenant_id,rule_id),"X","X"))
        _audit(conn,tenant_id=tenant_id,user=user,request=request,action="publish",aggregate_type="fiscal_classification_rule",aggregate_id=rule_id,before=_rule_payload(before),after=result,reason=data.reason)
        _event(conn,tenant_id=tenant_id,request=request,event_type="FiscalClassificationRulePublished",aggregate_type="fiscal_classification_rule",aggregate_id=rule_id,payload={"context_id":before["fiscal_context_id"],"valid_from":before["valid_from"]})
        save_idempotent(conn,scope,key,body,200,result); return 200,result


def _resolve_rule(conn: sqlite3.Connection, tenant_id: str, *, fiscal_context_id: str, item_kind: str, item_id: str, operation_type: str, occurred_on: str, establishment_code: str | None) -> dict[str, Any] | None:
    rows=conn.execute("SELECT * FROM fiscal_classification_rules WHERE tenant_id=? AND fiscal_context_id=? AND state='published' AND item_kind=? AND operation_type=? AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) AND (item_id IS NULL OR item_id=?) AND (establishment_code IS NULL OR establishment_code=?) ORDER BY CASE WHEN item_id=? THEN 1 ELSE 0 END DESC, CASE WHEN establishment_code=? THEN 1 ELSE 0 END DESC, priority DESC, valid_from DESC,id DESC",(tenant_id,fiscal_context_id,item_kind,operation_type,occurred_on,occurred_on,item_id,establishment_code,item_id,establishment_code)).fetchall()
    return _rule_payload(dict(rows[0])) if rows else None


def fiscal_readiness(request: Request, tenant_id: str, *, fiscal_context_id: str, establishment_code: str | None, occurred_on: date, operation_type: str) -> dict[str, Any]:
    when=occurred_on.isoformat()
    with request.state.store.transaction() as conn:
        context=_one(conn,"SELECT id,code,cnpj,active_version_id FROM fiscal_contexts WHERE tenant_id=? AND id=? AND state='active'",(tenant_id,fiscal_context_id),"FISCAL_CONTEXT_NOT_FOUND","Contexto fiscal não localizado.")
        version=conn.execute("SELECT * FROM fiscal_context_versions WHERE tenant_id=? AND fiscal_context_id=? AND state IN ('published','scheduled','superseded') AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY valid_from DESC,version_number DESC LIMIT 1",(tenant_id,fiscal_context_id,when,when)).fetchone()
        if not version: raise DomainError("FISCAL_CONTEXT_NOT_EFFECTIVE","Não existe versão fiscal vigente para a data informada.",422)
        version=dict(version); rtc_required=version["rtc_mode"] in {"optional_emit","required_emit"}; tax_regime=version["tax_regime"]
        details=[]
        for table,item_kind,name_col in (("products","product","name"),("services","service","name")):
            rows=conn.execute(f"SELECT * FROM {table} WHERE tenant_id=? AND state='active' ORDER BY {name_col},id",(tenant_id,)).fetchall()
            for raw in rows:
                item=dict(raw); rule=_resolve_rule(conn,tenant_id,fiscal_context_id=fiscal_context_id,item_kind=item_kind,item_id=item["id"],operation_type=operation_type,occurred_on=when,establishment_code=establishment_code)
                missing=[]
                if item_kind=="product":
                    ncm=(rule or {}).get("ncm") or item.get("ncm")
                    if not ncm: missing.append("NCM")
                    if tax_regime=="simples_nacional":
                        if not (rule or {}).get("csosn"): missing.append("CSOSN")
                    elif not (rule or {}).get("cst"): missing.append("CST")
                else:
                    if not ((rule or {}).get("nbs") or item.get("nbs")): missing.append("NBS")
                    if not ((rule or {}).get("lc116") or item.get("lc116_code")): missing.append("LC116")
                    if not ((rule or {}).get("municipal_code") or item.get("municipal_code")): missing.append("MUNICIPAL_CODE")
                if rtc_required:
                    if not (rule or {}).get("cst_ibs_cbs"): missing.append("CST_IBS_CBS")
                    if not (rule or {}).get("cclasstrib"): missing.append("CCLASSTRIB")
                details.append({"item_id":item["id"],"item_kind":item_kind,"code":item.get("sku") or item.get("code"),"name":item.get(name_col),"ready":not missing,"missing":missing,"rule_id":(rule or {}).get("id")})
        ready=sum(1 for x in details if x["ready"]); total=len(details)
        missing_counts={}
        for item in details:
            for field in item["missing"]: missing_counts[field]=missing_counts.get(field,0)+1
        return {"fiscal_context_id":fiscal_context_id,"fiscal_context_version_id":version["id"],"establishment_code":establishment_code or context["code"],"occurred_on":when,"operation_type":operation_type,"tax_regime":tax_regime,"rtc_mode":version["rtc_mode"],"total_items":total,"ready_items":ready,"pending_items":total-ready,"readiness_percentage":100.0 if total==0 else round((ready/total)*100,2),"missing_counts":missing_counts,"items":details}
