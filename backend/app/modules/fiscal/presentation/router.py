from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from app.modules.fiscal.application.ibpt import UFS, normalize_uf, queue_ibpt_sync
from app.modules.operations.common import FISCAL_ROLES, SALES_ROLES, dec, dumps, loads, require, row_or_404, tenant
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router = APIRouter(tags=["fiscal"])
CENT = Decimal("0.01")
def money(v: Any) -> Decimal: return dec(v)
def m(v: Decimal) -> str: return format(v.quantize(CENT), ".2f")

class FiscalProfileInput(BaseModel):
    establishment_name:str;cnpj:str;tax_regime:str;uf:str=Field(min_length=2,max_length=2);municipality_code:str|None=None;environment:Literal["homologation","production"]="homologation";provider_connection_id:str|None=None
class FiscalRuleInput(BaseModel):
    fiscal_profile_id:str;operation_type:str;item_kind:Literal["product","service","mixed"];classification_key:str|None=None;effective_from:date;effective_until:date|None=None;rules:dict[str,Any]
class FiscalSimulationInput(BaseModel):
    fiscal_profile_id:str;operation_type:str;item_kind:Literal["product","service"];classification_key:str|None=None;total_amount:Decimal=Field(ge=0);context:dict[str,Any]=Field(default_factory=dict)
class FiscalRequestInput(BaseModel):
    fiscal_profile_id:str;source_type:Literal["sale","service_order","manual"];source_id:str;document_type:Literal["NF-e","NFC-e","NFS-e"];totals:dict[str,Any]=Field(default_factory=dict);payload:dict[str,Any]=Field(default_factory=dict)
class FiscalStateInput(BaseModel):reason:str=Field(min_length=3,max_length=2000)

@router.get("/fiscal/profiles",operation_id="list_fiscal_profiles")
def list_profiles(request:Request,user:CurrentUser=Depends(current_user)):require(user,FISCAL_ROLES);return {"items":request.state.store.fetch_all("SELECT * FROM fiscal_profiles WHERE tenant_id=? ORDER BY establishment_name",(tenant(user),))}
@router.post("/fiscal/profiles",status_code=201,operation_id="create_fiscal_profile")
def create_profile(data:FiscalProfileInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);tid=tenant(user);pid=uuid7();now=iso_now()
    if data.provider_connection_id:
        connection=request.state.store.fetch_one("SELECT provider FROM integration_connections WHERE id=? AND tenant_id=?",(data.provider_connection_id,tid))
        allowed={"SefazNfeProvider","SefazNfceProvider","NationalNfseProvider","MunicipalNfseProvider","ThirdPartyFiscalProvider"}
        if not connection:raise DomainError("FISCAL_PROVIDER_NOT_FOUND","Conexão fiscal não localizada.",404)
        if connection["provider"] not in allowed:raise DomainError("FISCAL_PROVIDER_INVALID","A conexão selecionada não é um provider fiscal.",422)
    result={"id":pid,"establishment_name":data.establishment_name,"cnpj":data.cnpj,"tax_regime":data.tax_regime,"uf":data.uf.upper(),"environment":data.environment,"provider_connection_id":data.provider_connection_id,"state":"active"}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO fiscal_profiles(id,tenant_id,establishment_name,cnpj,tax_regime,uf,municipality_code,environment,provider_connection_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(pid,tid,data.establishment_name,data.cnpj,data.tax_regime,data.uf.upper(),data.municipality_code,data.environment,data.provider_connection_id,"active",now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="create",aggregate_type="fiscal_profile",aggregate_id=pid,correlation_id=request.state.correlation_id,after=result)
    return result

@router.get("/fiscal/rules",operation_id="list_fiscal_rules")
def list_rules(request:Request,fiscal_profile_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);tid=tenant(user);sql="SELECT * FROM fiscal_rules WHERE tenant_id=?";params:[Any]=[tid]
    if fiscal_profile_id:sql+=" AND fiscal_profile_id=?";params.append(fiscal_profile_id)
    sql+=" ORDER BY effective_from DESC,version DESC";items=request.state.store.fetch_all(sql,params)
    for item in items:item["rules"]=loads(item.pop("rules_json"),{})
    return {"items":items}
@router.post("/fiscal/rules",status_code=201,operation_id="create_fiscal_rule")
def create_rule(data:FiscalRuleInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);tid=tenant(user);row_or_404(request,"SELECT id FROM fiscal_profiles WHERE id=? AND tenant_id=?",(data.fiscal_profile_id,tid),"FISCAL_PROFILE_NOT_FOUND","Perfil fiscal não localizado.");rid=uuid7();now=iso_now();version=(request.state.store.scalar("SELECT COALESCE(MAX(version),0) AS n FROM fiscal_rules WHERE tenant_id=? AND fiscal_profile_id=? AND operation_type=? AND item_kind=? AND classification_key IS ?",(tid,data.fiscal_profile_id,data.operation_type,data.item_kind,data.classification_key)) or 0)+1;result={"id":rid,"version":int(version),**data.model_dump(mode="json"),"state":"active"}
    with request.state.store.transaction() as conn:conn.execute("INSERT INTO fiscal_rules(id,tenant_id,fiscal_profile_id,operation_type,item_kind,classification_key,effective_from,effective_until,rules_json,state,version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,data.fiscal_profile_id,data.operation_type,data.item_kind,data.classification_key,str(data.effective_from),str(data.effective_until) if data.effective_until else None,dumps(data.rules),"active",int(version),now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="publish",aggregate_type="fiscal_rule",aggregate_id=rid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="FiscalRulePublished",aggregate_type="fiscal_rule",aggregate_id=rid,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/fiscal/simulate",operation_id="simulate_fiscal_operation")
def simulate(data:FiscalSimulationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES|SALES_ROLES);tid=tenant(user);today=date.today().isoformat();row=request.state.store.fetch_one("""SELECT * FROM fiscal_rules WHERE tenant_id=? AND fiscal_profile_id=? AND operation_type=? AND item_kind=? AND state='active' AND effective_from<=? AND (effective_until IS NULL OR effective_until>=?) AND (classification_key=? OR classification_key IS NULL) ORDER BY CASE WHEN classification_key=? THEN 0 ELSE 1 END,version DESC LIMIT 1""",(tid,data.fiscal_profile_id,data.operation_type,data.item_kind,today,today,data.classification_key,data.classification_key));total=money(data.total_amount)
    if not row:return {"classified":False,"total_amount":m(total),"taxes":{},"warnings":["Nenhuma regra fiscal vigente corresponde à operação."],"rule_id":None}
    rules=loads(row["rules_json"],{});rates=rules.get("rates",{});taxes={};tax_total=Decimal("0")
    for tax,rate in rates.items():
        r=Decimal(str(rate));amount=(total*r/Decimal("100")).quantize(CENT);taxes[tax]={"rate":str(r),"base":m(total),"amount":m(amount)};tax_total+=amount
    return {"classified":True,"rule_id":row["id"],"rule_version":row["version"],"total_amount":m(total),"taxes":taxes,"tax_total":m(tax_total),"classification_key":data.classification_key,"rules":rules,"context":data.context}

@router.get("/fiscal/documents",operation_id="list_fiscal_documents_relational")
def list_documents(request:Request,state:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES|{"finance_operator"});tid=tenant(user);sql="SELECT * FROM fiscal_documents WHERE tenant_id=?";params:[Any]=[tid]
    if state:sql+=" AND state=?";params.append(state)
    sql+=" ORDER BY created_at DESC";return {"items":request.state.store.fetch_all(sql,params)}
@router.post("/fiscal/documents",status_code=201,operation_id="request_fiscal_document_relational")
def request_document(data:FiscalRequestInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES|SALES_ROLES);tid=tenant(user);body=data.model_dump(mode="json");scope=f"fiscal-request:{tid}:{data.document_type}:{data.source_type}:{data.source_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        profile=conn.execute("SELECT * FROM fiscal_profiles WHERE id=? AND tenant_id=? AND state='active'",(data.fiscal_profile_id,tid)).fetchone()
        if not profile:raise DomainError("FISCAL_PROFILE_NOT_FOUND","Perfil fiscal não localizado.",404)
        profile=dict(profile)
        provider_connection_id=profile.get("provider_connection_id")
        provider_status="not_configured"
        if provider_connection_id:
            connection=conn.execute("SELECT state FROM integration_connections WHERE id=? AND tenant_id=?",(provider_connection_id,tid)).fetchone()
            provider_status="queued" if connection and connection["state"] in {"configured","degraded"} else "not_configured"
        fid=uuid7();now=iso_now();result={"id":fid,"document_type":data.document_type,"source_type":data.source_type,"source_id":data.source_id,"environment":profile["environment"],"state":"requested","provider_connection_id":provider_connection_id,"provider_status":provider_status}
        conn.execute("INSERT INTO fiscal_documents(id,tenant_id,fiscal_profile_id,document_type,source_type,source_id,environment,state,provider_connection_id,provider_status,totals_json,request_json,response_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fid,tid,data.fiscal_profile_id,data.document_type,data.source_type,data.source_id,profile["environment"],"requested",provider_connection_id,provider_status,dumps(data.totals),dumps(data.payload),"{}",now,now))
        conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,fid,"requested","requested",provider_connection_id,dumps(result),now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="request",aggregate_type="fiscal_document",aggregate_id=fid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tid,event_type="FiscalDocumentRequested",aggregate_type="fiscal_document",aggregate_id=fid,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return result
@router.post("/fiscal/documents/{document_id}/cancel",operation_id="cancel_fiscal_document_local")
def cancel_document(document_id:str,data:FiscalStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM fiscal_documents WHERE id=? AND tenant_id=?",(document_id,tid)).fetchone()
        if not row:raise DomainError("FISCAL_DOCUMENT_NOT_FOUND","Documento fiscal não localizado.",404)
        row=dict(row)
        if row["state"] in {"cancelled","rejected"}:return {"id":document_id,"state":row["state"],"idempotent":True}
        if row["state"]=="authorized":
            if not row.get("provider_connection_id"):raise DomainError("FISCAL_PROVIDER_REQUIRED","Documento autorizado não possui provider configurado para cancelamento.",409)
            result={"id":document_id,"state":"cancellation_requested","reason":data.reason}
            conn.execute("UPDATE fiscal_documents SET state='cancellation_requested',provider_status='queued',updated_at=? WHERE id=?",(now,document_id))
            conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,document_id,"cancellation_requested","cancellation_requested",row.get("provider_connection_id"),dumps(result),now))
            add_audit(conn,tenant_id=tid,actor_id=user.id,action="request_cancel",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.reason)
            add_outbox(conn,tenant_id=tid,event_type="FiscalDocumentCancellationRequested",aggregate_type="fiscal_document",aggregate_id=document_id,payload=result,correlation_id=request.state.correlation_id)
            return result
        conn.execute("UPDATE fiscal_documents SET state='cancelled',updated_at=? WHERE id=?",(now,document_id));result={"id":document_id,"state":"cancelled","reason":data.reason};conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,document_id,"cancelled_locally","cancelled",row.get("provider_connection_id"),dumps(result),now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="cancel",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="FiscalDocumentCancelledLocally",aggregate_type="fiscal_document",aggregate_id=document_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/fiscal/documents/{document_id}/events",operation_id="list_fiscal_document_events")
def list_fiscal_document_events(document_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES|{"finance_operator"});tid=tenant(user);row_or_404(request,"SELECT id FROM fiscal_documents WHERE id=? AND tenant_id=?",(document_id,tid),"FISCAL_DOCUMENT_NOT_FOUND","Documento fiscal não localizado.")
    items=request.state.store.fetch_all("SELECT * FROM fiscal_document_events WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at,id",(tid,document_id))
    for item in items:item["payload"]=loads(item.pop("payload_json"),{})
    return {"items":items}

@router.post("/fiscal/documents/{document_id}/retry",operation_id="retry_fiscal_document")
def retry_fiscal_document(document_id:str,data:FiscalStateInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);tid=tenant(user);now=iso_now()
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM fiscal_documents WHERE id=? AND tenant_id=?",(document_id,tid)).fetchone()
        if not row:raise DomainError("FISCAL_DOCUMENT_NOT_FOUND","Documento fiscal não localizado.",404)
        row=dict(row)
        if row["state"] in {"authorized","cancelled"}:raise DomainError("FISCAL_DOCUMENT_FINAL","Documento fiscal já está em estado final.",409)
        if not row.get("provider_connection_id"):raise DomainError("FISCAL_PROVIDER_REQUIRED","Configure um provider fiscal antes de reprocessar.",409)
        result={"id":document_id,"state":"requested","provider_status":"queued","reason":data.reason}
        conn.execute("UPDATE fiscal_documents SET state='requested',provider_status='queued',error_code=NULL,error_message=NULL,updated_at=? WHERE id=?",(now,document_id))
        conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,document_id,"retry_requested","requested",row.get("provider_connection_id"),dumps(result),now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="retry",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tid,event_type="FiscalDocumentRequested",aggregate_type="fiscal_document",aggregate_id=document_id,payload=result,correlation_id=request.state.correlation_id)
    return result

class IbptSyncInput(BaseModel):
    ufs: list[str] = Field(default_factory=lambda: list(UFS), min_length=1, max_length=27)


@router.post("/fiscal/ibpt/sync", status_code=202, operation_id="request_ibpt_sync")
def request_ibpt_sync(data: IbptSyncInput, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); tid = tenant(user)
    try:
        runs = queue_ibpt_sync(request.state.store, tenant_id=tid, ufs=data.ufs, actor_id=user.id, correlation_id=request.state.correlation_id)
    except ValueError as exc:
        raise DomainError("IBPT_UF_INVALID", str(exc), 422) from exc
    return {"state": "queued", "runs": runs}


@router.get("/fiscal/ibpt/sync-runs", operation_id="list_ibpt_sync_runs")
def list_ibpt_sync_runs(request: Request, state: str | None = None, uf: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); tid = tenant(user)
    sql = "SELECT * FROM ibpt_sync_runs WHERE tenant_id=?"; params: list[Any] = [tid]
    if state:
        sql += " AND state=?"; params.append(state)
    if uf:
        try: normalized = normalize_uf(uf)
        except ValueError as exc: raise DomainError("IBPT_UF_INVALID", str(exc), 422) from exc
        sql += " AND uf=?"; params.append(normalized)
    sql += " ORDER BY requested_at DESC LIMIT 500"
    return {"items": request.state.store.fetch_all(sql, params)}


@router.get("/fiscal/ibpt/snapshots", operation_id="list_ibpt_snapshots")
def list_ibpt_snapshots(request: Request, uf: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); tid = tenant(user)
    sql = "SELECT * FROM ibpt_snapshots WHERE tenant_id=?"; params: list[Any] = [tid]
    if uf:
        try: normalized = normalize_uf(uf)
        except ValueError as exc: raise DomainError("IBPT_UF_INVALID", str(exc), 422) from exc
        sql += " AND uf=?"; params.append(normalized)
    sql += " ORDER BY created_at DESC LIMIT 500"
    return {"items": request.state.store.fetch_all(sql, params)}


@router.get("/fiscal/ibpt/status", operation_id="get_ibpt_status")
def get_ibpt_status(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); tid = tenant(user)
    rows = request.state.store.fetch_all("SELECT uf,sha256,rows_count,source_version,effective_from,effective_to,created_at FROM ibpt_snapshots WHERE tenant_id=? AND state='active' ORDER BY uf", (tid,))
    by_uf = {row["uf"]: row for row in rows}
    return {"provider": request.app.state.settings.ibpt_provider, "active": list(by_uf.values()), "missing_ufs": [uf for uf in UFS if uf not in by_uf], "all_ufs_ready": len(by_uf) == len(UFS)}


@router.get("/fiscal/ibpt/rates/{code}", operation_id="get_ibpt_rate")
def get_ibpt_rate(code: str, request: Request, uf: str, ex: str = "", item_type: str = "", user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); tid = tenant(user)
    try: normalized = normalize_uf(uf)
    except ValueError as exc: raise DomainError("IBPT_UF_INVALID", str(exc), 422) from exc
    clean_code = "".join(ch for ch in code if ch.isalnum())
    snapshot = request.state.store.fetch_one("SELECT id,sha256,source_version,effective_from,effective_to FROM ibpt_snapshots WHERE tenant_id=? AND uf=? AND state='active' ORDER BY created_at DESC LIMIT 1", (tid, normalized))
    if not snapshot: raise DomainError("IBPT_SNAPSHOT_NOT_AVAILABLE", "Não existe snapshot IBPT ativo para a UF informada.", 404)
    row = request.state.store.fetch_one("SELECT * FROM ibpt_rates WHERE tenant_id=? AND snapshot_id=? AND code=? AND ex=? AND item_type=?", (tid, snapshot["id"], clean_code, ex, item_type))
    if not row and not ex and not item_type:
        row = request.state.store.fetch_one("SELECT * FROM ibpt_rates WHERE tenant_id=? AND snapshot_id=? AND code=? ORDER BY ex,item_type LIMIT 1", (tid, snapshot["id"], clean_code))
    if not row: raise DomainError("IBPT_RATE_NOT_FOUND", "Classificação não localizada no snapshot IBPT ativo.", 404)
    return {**row, "snapshot": snapshot, "purpose": "transparencia_vtottrib", "tax_calculation_source": False}

