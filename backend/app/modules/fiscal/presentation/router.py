from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from app.modules.fiscal.application.calculation_service import (
    create_tax_rule_set, create_tax_rule_version, get_tax_calculation, list_tax_rule_sets,
    publish_tax_rule_version, simulate_tax_calculation, tax_rule_set_detail,
)
from app.modules.fiscal.presentation.calculation_schemas import (
    FiscalTaxRuleSetCreate, FiscalTaxRuleVersionCreate, FiscalTaxRuleVersionPublish, FiscalTaxSimulationInput,
)
from app.modules.fiscal.application.catalog_service import (
    catalog_detail,
    create_catalog,
    create_catalog_version,
    create_classification_rule,
    fiscal_readiness,
    list_catalogs,
    list_classification_rules,
    patch_classification_rule,
    publish_catalog_version,
    publish_classification_rule,
    resolve_catalog_code,
)
from app.modules.fiscal.application.catalog_import_service import (
    catalog_governance_health,
    catalog_import_detail,
    create_catalog_source,
    import_catalog_snapshot,
    list_catalog_imports,
    list_catalog_quarantine,
    list_catalog_sources,
    publish_catalog_import,
    resolve_catalog_quarantine,
    rollback_catalog_version,
)
from app.modules.fiscal.presentation.catalog_import_schemas import (
    FiscalCatalogImportCreate,
    FiscalCatalogImportPublish,
    FiscalCatalogQuarantineResolve,
    FiscalCatalogRollback,
    FiscalCatalogSourceCreate,
)
from app.modules.fiscal.presentation.catalog_schemas import (
    FiscalCatalogCreate,
    FiscalCatalogVersionCreate,
    FiscalCatalogVersionPublish,
    FiscalClassificationRuleCreate,
    FiscalClassificationRulePatch,
    FiscalClassificationRulePublish,
)
from app.modules.fiscal.application.context_service import (
    context_detail,
    create_context,
    create_version,
    fiscal_context_snapshot_by_version,
    list_contexts,
    list_versions,
    publish_version,
    resolve_context,
    update_context,
)
from app.modules.fiscal.application.document_lifecycle_service import (
    create_certificate as create_fiscal_certificate,
    create_inutilization as create_fiscal_inutilization,
    create_provider_configuration as create_fiscal_provider_configuration,
    document_detail as fiscal_document_detail,
    list_certificates as list_fiscal_certificates,
    list_inutilizations as list_fiscal_inutilizations,
    list_provider_configurations as list_fiscal_provider_configurations,
    patch_provider_configuration as patch_fiscal_provider_configuration,
    provider_health as fiscal_provider_health,
    queue_document_query as queue_fiscal_document_query,
    queue_provider_event as queue_fiscal_provider_event,
    substitute_document as substitute_fiscal_document,
)
from app.modules.fiscal.application.document_routing_service import (
    apply_fiscal_financial_adjustment,
    assembly_detail as fiscal_assembly_detail,
    assemble_document as assemble_fiscal_document,
    create_policy as create_fiscal_routing_policy,
    create_schema as create_fiscal_document_schema,
    evaluate_trigger as evaluate_fiscal_emission_trigger,
    list_assemblies as list_fiscal_assemblies,
    list_policies as list_fiscal_routing_policies,
    list_schemas as list_fiscal_document_schemas,
    list_trigger_runs as list_fiscal_emission_trigger_runs,
    publish_policy as publish_fiscal_routing_policy,
    publish_schema as publish_fiscal_document_schema,
)
from app.modules.fiscal.presentation.document_routing_schemas import (
    FiscalDocumentAssemblyCreate, FiscalDocumentSchemaCreate, FiscalDocumentSchemaPublish,
    FiscalEmissionTriggerEvaluate, FiscalRoutingPolicyCreate, FiscalRoutingPolicyPublish,
)
from app.modules.fiscal.presentation.document_lifecycle_schemas import (
    FiscalCertificateMetadataCreate,
    FiscalDocumentQueryRequest,
    FiscalDocumentSubstituteRequest,
    FiscalInutilizationCreate,
    FiscalProviderConfigurationCreate,
    FiscalProviderConfigurationPatch,
    FiscalProviderEventCreate,
)
from app.modules.fiscal.application.document_delivery_service import (
    create_delivery_policy,
    list_fiscal_document_artifacts,
    latest_rejection as fiscal_latest_rejection,
    list_delivery_policies,
    publish_delivery_policy,
    queue_document_retry,
    read_fiscal_document_artifact,
    render_fiscal_document,
)
from app.modules.fiscal.presentation.document_delivery_schemas import (
    FiscalDeliveryPolicyCreate,
    FiscalDeliveryPolicyPublish,
    FiscalDocumentRenderRequest,
    FiscalDocumentRetryRequest,
)
from app.modules.fiscal.application.ibpt import UFS, normalize_uf, queue_ibpt_sync, ibpt_rollback, ibpt_offline_package, ibpt_operational_status
from app.modules.fiscal.application.transparency_service import (
    create_ibpt_profile, document_transparency, list_ibpt_profiles, publish_ibpt_profile,
)
from app.modules.fiscal.presentation.transparency_schemas import (
    FiscalIbptProviderProfileCreate, FiscalIbptProviderProfilePublish,
)
from app.modules.fiscal.application.strategy_service import create_legal_source,list_legal_sources,create_strategy_rule,list_strategy_rules,create_rtc_schedule,resolve_rtc
from app.modules.fiscal.presentation.strategy_schemas import FiscalLegalSourceCreate,FiscalStrategyRuleCreate,FiscalRtcScheduleCreate
from app.modules.fiscal.presentation.context_schemas import (
    FiscalContextCreate,
    FiscalContextPatch,
    FiscalContextResolveInput,
    FiscalContextVersionCreate,
    FiscalContextVersionPublish,
)
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
    fiscal_profile_id:str;fiscal_context_version_id:str|None=None;source_type:Literal["sale","service_order","manual"];source_id:str;document_type:Literal["NF-e","NFC-e","NFS-e"];totals:dict[str,Any]=Field(default_factory=dict);payload:dict[str,Any]=Field(default_factory=dict);contingency_mode:Literal["offline","svc","ecpec"]|None=None
class FiscalStateInput(BaseModel):reason:str=Field(min_length=3,max_length=2000)


@router.get("/fiscal/contexts", operation_id="list_fiscal_contexts")
def list_fiscal_contexts(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    institution_id: str | None = None,
    unit_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return list_contexts(
        request,
        tenant(user),
        status=status,
        q=q,
        institution_id=institution_id,
        unit_id=unit_id,
    )


@router.post("/fiscal/contexts", status_code=201, operation_id="create_fiscal_context")
def create_fiscal_context(
    data: FiscalContextCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_context(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/contexts/{context_id}", operation_id="get_fiscal_context")
def get_fiscal_context(
    context_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return context_detail(request, tenant(user), context_id)


@router.patch("/fiscal/contexts/{context_id}", operation_id="update_fiscal_context")
def update_fiscal_context(
    context_id: str,
    data: FiscalContextPatch,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return update_context(context_id, data, request, tenant(user), user)


@router.get("/fiscal/contexts/{context_id}/versions", operation_id="list_fiscal_context_versions")
def list_fiscal_context_versions(
    context_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return list_versions(request, tenant(user), context_id)


@router.post("/fiscal/contexts/{context_id}/versions", status_code=201, operation_id="create_fiscal_context_version")
def create_fiscal_context_version(
    context_id: str,
    data: FiscalContextVersionCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_version(context_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post(
    "/fiscal/contexts/{context_id}/versions/{version_id}/publish",
    operation_id="publish_fiscal_context_version",
)
def publish_fiscal_context_version(
    context_id: str,
    version_id: str,
    data: FiscalContextVersionPublish,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = publish_version(
        context_id,
        version_id,
        data,
        request,
        tenant(user),
        user,
        idempotency_key,
    )
    response.status_code = status_code
    return result


@router.post("/fiscal/contexts/resolve", operation_id="resolve_fiscal_context")
def resolve_fiscal_context(
    data: FiscalContextResolveInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES | SALES_ROLES)
    return resolve_context(data, request, tenant(user))

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
    require(user,FISCAL_ROLES|{"finance_operator"});tid=tenant(user);sql="SELECT * FROM fiscal_documents WHERE tenant_id=?";params:list[Any]=[tid]
    if state:sql+=" AND state=?";params.append(state)
    sql+=" ORDER BY created_at DESC";items=request.state.store.fetch_all(sql,params)
    for item in items:
        item["fiscal_context_snapshot"]=loads(item.pop("fiscal_context_snapshot_json", "{}"), {})
    return {"items":items}
@router.post("/fiscal/documents",status_code=201,operation_id="request_fiscal_document_relational")
def request_document(data:FiscalRequestInput,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES|SALES_ROLES);tid=tenant(user);body=data.model_dump(mode="json");scope=f"fiscal-request:{tid}:{data.document_type}:{data.source_type}:{data.source_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:response.status_code=cached[0];return cached[1]
        profile=conn.execute("SELECT * FROM fiscal_profiles WHERE id=? AND tenant_id=? AND state='active'",(data.fiscal_profile_id,tid)).fetchone()
        if not profile:raise DomainError("FISCAL_PROFILE_NOT_FOUND","Perfil fiscal não localizado.",404)
        profile=dict(profile)
        context_snapshot:dict[str,Any]={};fiscal_context_id=None;environment=profile["environment"]
        provider_connection_id=profile.get("provider_connection_id")
        if data.fiscal_context_version_id:
            context_snapshot=fiscal_context_snapshot_by_version(
                conn,
                tenant_id=tid,
                version_id=data.fiscal_context_version_id,
                occurred_on=date.today(),
            )
            fiscal_context_id=context_snapshot["context"]["id"]
            profile_cnpj="".join(character for character in profile["cnpj"] if character.isdigit())
            if profile_cnpj != context_snapshot["context"]["cnpj"]:
                raise DomainError("FISCAL_CONTEXT_PROFILE_MISMATCH","O perfil fiscal e o contexto versionado pertencem a CNPJs diferentes.",409)
            environment=context_snapshot["version"]["environment"]
            provider_connection_id=context_snapshot["context"].get("provider_connection_id") or provider_connection_id
        provider_status="not_configured"
        if provider_connection_id:
            connection=conn.execute("SELECT state FROM integration_connections WHERE id=? AND tenant_id=?",(provider_connection_id,tid)).fetchone()
            provider_status="queued" if connection and connection["state"] in {"configured","degraded"} else "not_configured"
        fid=uuid7();now=iso_now();result={"id":fid,"document_type":data.document_type,"source_type":data.source_type,"source_id":data.source_id,"environment":environment,"state":"requested","provider_connection_id":provider_connection_id,"provider_status":provider_status,"fiscal_context_id":fiscal_context_id,"fiscal_context_version_id":data.fiscal_context_version_id,"fiscal_context_sha256":context_snapshot.get("sha256"),"contingency_mode":data.contingency_mode}
        conn.execute("INSERT INTO fiscal_documents(id,tenant_id,fiscal_profile_id,fiscal_context_id,fiscal_context_version_id,fiscal_context_snapshot_json,document_type,source_type,source_id,environment,state,provider_connection_id,provider_status,totals_json,request_json,response_json,contingency_mode,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fid,tid,data.fiscal_profile_id,fiscal_context_id,data.fiscal_context_version_id,dumps(context_snapshot),data.document_type,data.source_type,data.source_id,environment,"requested",provider_connection_id,provider_status,dumps(data.totals),dumps(data.payload),"{}",data.contingency_mode,now,now))
        request_snapshot={"document_type":data.document_type,"source_type":data.source_type,"source_id":data.source_id,"environment":environment,"totals":data.totals,"payload":data.payload,"fiscal_context":context_snapshot,"contingency_mode":data.contingency_mode}
        snapshot_bytes=json.dumps(request_snapshot,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode("utf-8")
        stored_request=request.app.state.data_router.object_storage(tid).put_bytes(f"fiscal/{fid}/request-snapshot.json",snapshot_bytes,content_type="application/json")
        conn.execute("INSERT INTO fiscal_document_artifacts(id,tenant_id,fiscal_document_id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,fid,"request_snapshot","application/json",stored_request.key,stored_request.sha256,stored_request.bytes,None,now))
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
        conn.execute("UPDATE fiscal_documents SET state='cancelled',updated_at=? WHERE id=?",(now,document_id));financial_adjustment=apply_fiscal_financial_adjustment(conn,tenant_id=tid,document_id=document_id,reason=data.reason,now=now);result={"id":document_id,"state":"cancelled","reason":data.reason,"financial_adjustment":financial_adjustment};conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tid,document_id,"cancelled_locally","cancelled",row.get("provider_connection_id"),dumps(result),now));add_audit(conn,tenant_id=tid,actor_id=user.id,action="cancel",aggregate_type="fiscal_document",aggregate_id=document_id,correlation_id=request.state.correlation_id,before=dict(row),after=result,reason=data.reason);add_outbox(conn,tenant_id=tid,event_type="FiscalDocumentCancelledLocally",aggregate_type="fiscal_document",aggregate_id=document_id,payload=result,correlation_id=request.state.correlation_id)
    return result

@router.get("/fiscal/documents/{document_id}/events",operation_id="list_fiscal_document_events")
def list_fiscal_document_events(document_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES|{"finance_operator"});tid=tenant(user);row_or_404(request,"SELECT id FROM fiscal_documents WHERE id=? AND tenant_id=?",(document_id,tid),"FISCAL_DOCUMENT_NOT_FOUND","Documento fiscal não localizado.")
    items=request.state.store.fetch_all("SELECT * FROM fiscal_document_events WHERE tenant_id=? AND fiscal_document_id=? ORDER BY created_at,id",(tid,document_id))
    for item in items:item["payload"]=loads(item.pop("payload_json"),{})
    return {"items":items}

@router.post("/fiscal/documents/{document_id}/retry",operation_id="retry_fiscal_document")
def retry_fiscal_document(document_id:str,data:FiscalDocumentRetryRequest,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES)
    return queue_document_retry(document_id,data,request,tenant(user),user)


@router.get("/fiscal/documents/{document_id}/rejection", operation_id="get_fiscal_document_rejection")
def get_fiscal_document_rejection(document_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | {"finance_operator"})
    return fiscal_latest_rejection(request, tenant(user), document_id)


@router.post("/fiscal/documents/{document_id}/render", operation_id="render_fiscal_document_local")
def render_fiscal_document_local(document_id: str, data: FiscalDocumentRenderRequest, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | {"finance_operator"})
    return render_fiscal_document(document_id, data, request, tenant(user), user)


@router.get("/fiscal/documents/{document_id}/artifacts", operation_id="list_fiscal_document_artifacts")
def fiscal_document_artifacts_list(document_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | {"finance_operator"})
    return list_fiscal_document_artifacts(request, tenant(user), document_id)


@router.get("/fiscal/documents/{document_id}/artifacts/{artifact_id}/download", operation_id="download_fiscal_document_artifact")
def fiscal_document_artifact_download(document_id: str, artifact_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | {"finance_operator"})
    content, artifact = read_fiscal_document_artifact(request, tenant(user), document_id, artifact_id, user)
    return Response(
        content=content,
        media_type=artifact["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{artifact["filename"]}"',
            "X-Artifact-SHA256": artifact["sha256"],
            "X-Artifact-Bytes": str(artifact["bytes_count"]),
        },
    )

# Resiliência de entrega fiscal ------------------------------------------------

@router.get("/fiscal/delivery-policies", operation_id="list_fiscal_delivery_policies")
def fiscal_delivery_policies_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_delivery_policies(request, tenant(user))


@router.post("/fiscal/delivery-policies", status_code=201, operation_id="create_fiscal_delivery_policy")
def fiscal_delivery_policies_create(
    data: FiscalDeliveryPolicyCreate, request: Request, response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_delivery_policy(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post("/fiscal/delivery-policies/{policy_id}/publish", operation_id="publish_fiscal_delivery_policy")
def fiscal_delivery_policy_publish(policy_id: str, data: FiscalDeliveryPolicyPublish, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return publish_delivery_policy(policy_id, data, request, tenant(user), user)


# Ciclo de vida fiscal e providers condicionais --------------------------------

@router.get("/fiscal/certificates", operation_id="list_fiscal_certificates")
def fiscal_certificates_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_fiscal_certificates(request, tenant(user))


@router.post("/fiscal/certificates", status_code=201, operation_id="create_fiscal_certificate_metadata")
def fiscal_certificates_create(
    data: FiscalCertificateMetadataCreate, request: Request, response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_fiscal_certificate(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/providers", operation_id="list_fiscal_provider_configurations")
def fiscal_providers_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_fiscal_provider_configurations(request, tenant(user))


@router.post("/fiscal/providers", status_code=201, operation_id="create_fiscal_provider_configuration")
def fiscal_providers_create(
    data: FiscalProviderConfigurationCreate, request: Request, response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_fiscal_provider_configuration(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.patch("/fiscal/providers/{configuration_id}", operation_id="patch_fiscal_provider_configuration")
def fiscal_provider_patch(configuration_id: str, data: FiscalProviderConfigurationPatch, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return patch_fiscal_provider_configuration(configuration_id, data, request, tenant(user), user)


@router.post("/fiscal/providers/{configuration_id}/health", operation_id="check_fiscal_provider_health")
def fiscal_provider_check(configuration_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return fiscal_provider_health(configuration_id, request, tenant(user), user)


@router.get("/fiscal/documents/{document_id}", operation_id="get_fiscal_document_detail")
def get_fiscal_document_detail(document_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | {"finance_operator"})
    return fiscal_document_detail(document_id, request, tenant(user))


@router.post("/fiscal/documents/{document_id}/query", operation_id="query_fiscal_document_provider")
def query_fiscal_document(document_id: str, data: FiscalDocumentQueryRequest, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return queue_fiscal_document_query(document_id, data, request, tenant(user), user)


@router.post("/fiscal/documents/{document_id}/substitute", status_code=201, operation_id="substitute_fiscal_document_provider")
def substitute_fiscal_document_route(
    document_id: str, data: FiscalDocumentSubstituteRequest, request: Request, response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = substitute_fiscal_document(document_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post("/fiscal/documents/{document_id}/events", status_code=201, operation_id="request_fiscal_document_provider_event")
def request_fiscal_document_provider_event(
    document_id: str, data: FiscalProviderEventCreate, request: Request, response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = queue_fiscal_provider_event(document_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/inutilizations", operation_id="list_fiscal_inutilizations")
def fiscal_inutilizations_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_fiscal_inutilizations(request, tenant(user))


@router.post("/fiscal/inutilizations", status_code=201, operation_id="create_fiscal_inutilization")
def fiscal_inutilizations_create(
    data: FiscalInutilizationCreate, request: Request, response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_fiscal_inutilization(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


class IbptSyncInput(BaseModel):
    ufs: list[str] = Field(default_factory=lambda: list(UFS), min_length=1, max_length=27)


@router.get("/fiscal/ibpt/provider-profiles", operation_id="list_fiscal_ibpt_provider_profiles")
def api_list_ibpt_provider_profiles(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_ibpt_profiles(request, tenant(user))


@router.post("/fiscal/ibpt/provider-profiles", status_code=201, operation_id="create_fiscal_ibpt_provider_profile")
def api_create_ibpt_provider_profile(
    data: FiscalIbptProviderProfileCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_ibpt_profile(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post("/fiscal/ibpt/provider-profiles/{profile_id}/publish", operation_id="publish_fiscal_ibpt_provider_profile")
def api_publish_ibpt_provider_profile(
    profile_id: str,
    data: FiscalIbptProviderProfilePublish,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return publish_ibpt_profile(profile_id, data, request, tenant(user), user)


@router.get("/fiscal/documents/{document_id}/transparency", operation_id="get_fiscal_document_tax_transparency")
def api_document_tax_transparency(document_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | SALES_ROLES)
    return document_transparency(request, tenant(user), document_id)


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



@router.get("/fiscal/catalogs", operation_id="list_fiscal_catalogs")
def list_fiscal_catalogs(request: Request, kind: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_catalogs(request, tenant(user), kind=kind)


@router.post("/fiscal/catalogs", status_code=201, operation_id="create_fiscal_catalog")
def create_fiscal_catalog(data: FiscalCatalogCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = create_catalog(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/catalogs/{catalog_id}", operation_id="get_fiscal_catalog")
def get_fiscal_catalog(catalog_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return catalog_detail(request, tenant(user), catalog_id)


@router.post("/fiscal/catalogs/{catalog_id}/versions", status_code=201, operation_id="create_fiscal_catalog_version")
def create_fiscal_catalog_version(catalog_id: str, data: FiscalCatalogVersionCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = create_catalog_version(catalog_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post("/fiscal/catalogs/{catalog_id}/versions/{version_id}/publish", operation_id="publish_fiscal_catalog_version")
def publish_fiscal_catalog_version(catalog_id: str, version_id: str, data: FiscalCatalogVersionPublish, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = publish_catalog_version(catalog_id, version_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/catalogs/{catalog_id}/resolve/{code}", operation_id="resolve_fiscal_catalog_code")
def resolve_fiscal_catalog_entry(catalog_id: str, code: str, request: Request, occurred_on: date = date.today(), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | SALES_ROLES)
    return resolve_catalog_code(request, tenant(user), catalog_id, code, occurred_on)


@router.get("/fiscal/classification-rules", operation_id="list_fiscal_classification_rules")
def list_fiscal_classification_rule_items(request: Request, fiscal_context_id: str | None = None, status: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_classification_rules(request, tenant(user), fiscal_context_id=fiscal_context_id, status=status)


@router.post("/fiscal/classification-rules", status_code=201, operation_id="create_fiscal_classification_rule")
def create_fiscal_classification_rule(data: FiscalClassificationRuleCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = create_classification_rule(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.patch("/fiscal/classification-rules/{rule_id}", operation_id="update_fiscal_classification_rule")
def update_fiscal_classification_rule(rule_id: str, data: FiscalClassificationRulePatch, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return patch_classification_rule(rule_id, data, request, tenant(user), user)


@router.post("/fiscal/classification-rules/{rule_id}/publish", operation_id="publish_fiscal_classification_rule")
def publish_fiscal_classification_rule(rule_id: str, data: FiscalClassificationRulePublish, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = publish_classification_rule(rule_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/readiness", operation_id="get_fiscal_readiness")
def get_fiscal_readiness(request: Request, fiscal_context_id: str, occurred_on: date = date.today(), operation_type: str = "sale", establishment_code: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return fiscal_readiness(request, tenant(user), fiscal_context_id=fiscal_context_id, establishment_code=establishment_code, occurred_on=occurred_on, operation_type=operation_type)


@router.get("/fiscal/tax-rule-sets", operation_id="list_fiscal_tax_rule_sets")
def list_fiscal_tax_rule_set_items(request: Request, fiscal_context_id: str | None = None, status: str | None = None, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return list_tax_rule_sets(request, tenant(user), fiscal_context_id=fiscal_context_id, status=status)


@router.post("/fiscal/tax-rule-sets", status_code=201, operation_id="create_fiscal_tax_rule_set")
def create_fiscal_tax_rule_set(data: FiscalTaxRuleSetCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = create_tax_rule_set(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/tax-rule-sets/{rule_set_id}", operation_id="get_fiscal_tax_rule_set")
def get_fiscal_tax_rule_set(rule_set_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return tax_rule_set_detail(request, tenant(user), rule_set_id)


@router.post("/fiscal/tax-rule-sets/{rule_set_id}/versions", status_code=201, operation_id="create_fiscal_tax_rule_version")
def create_fiscal_tax_rule_version(rule_set_id: str, data: FiscalTaxRuleVersionCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = create_tax_rule_version(rule_set_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post("/fiscal/tax-rule-sets/{rule_set_id}/versions/{version_id}/publish", operation_id="publish_fiscal_tax_rule_version")
def publish_fiscal_tax_rule_version(rule_set_id: str, version_id: str, data: FiscalTaxRuleVersionPublish, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    status_code, result = publish_tax_rule_version(rule_set_id, version_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post("/fiscal/tax-calculations/simulate", status_code=201, operation_id="simulate_versioned_fiscal_tax_calculation")
def simulate_versioned_fiscal_tax_calculation(data: FiscalTaxSimulationInput, request: Request, response: Response, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | SALES_ROLES)
    status_code, result = simulate_tax_calculation(data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/tax-calculations/{calculation_id}", operation_id="get_versioned_fiscal_tax_calculation")
def get_versioned_fiscal_tax_calculation(calculation_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return get_tax_calculation(request, tenant(user), calculation_id)


@router.get("/fiscal/legal-sources", operation_id="list_fiscal_legal_sources")
def api_list_legal_sources(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES); return list_legal_sources(request,tenant(user))

@router.post("/fiscal/legal-sources",status_code=201,operation_id="create_fiscal_legal_source")
def api_create_legal_source(data:FiscalLegalSourceCreate,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES); status,result=create_legal_source(data,request,tenant(user),user,idempotency_key);response.status_code=status;return result

@router.get("/fiscal/strategy-rules",operation_id="list_fiscal_strategy_rules")
def api_list_strategy_rules(request:Request,fiscal_context_id:str|None=None,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);return list_strategy_rules(request,tenant(user),fiscal_context_id)

@router.post("/fiscal/strategy-rules",status_code=201,operation_id="create_fiscal_strategy_rule")
def api_create_strategy_rule(data:FiscalStrategyRuleCreate,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);status,result=create_strategy_rule(data,request,tenant(user),user,idempotency_key);response.status_code=status;return result

@router.post("/fiscal/rtc-schedules",status_code=201,operation_id="create_fiscal_rtc_schedule")
def api_create_rtc_schedule(data:FiscalRtcScheduleCreate,request:Request,response:Response,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=200),user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);status,result=create_rtc_schedule(data,request,tenant(user),user,idempotency_key);response.status_code=status;return result

@router.get("/fiscal/rtc/resolve",operation_id="resolve_fiscal_rtc_schedule")
def api_resolve_rtc(request:Request,fiscal_context_id:str,occurred_on:date=date.today(),establishment_code:str|None=None,tax_regime:str='any',user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);return resolve_rtc(request,tenant(user),fiscal_context_id,occurred_on.isoformat(),establishment_code,tax_regime)

@router.post("/fiscal/ibpt/snapshots/{snapshot_id}/rollback",operation_id="rollback_ibpt_snapshot")
def api_ibpt_rollback(snapshot_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES)
    try:return ibpt_rollback(request.app.state.data_router,tenant_id=tenant(user),snapshot_id=snapshot_id,actor_id=user.id,correlation_id=request.state.correlation_id)
    except ValueError as exc:raise DomainError('IBPT_SNAPSHOT_NOT_AVAILABLE',str(exc),404) from exc

@router.get("/fiscal/ibpt/offline/{uf}",operation_id="get_ibpt_offline_package")
def api_ibpt_offline(uf:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES)
    try:return ibpt_offline_package(request.app.state.data_router,tenant_id=tenant(user),uf=uf)
    except ValueError as exc:raise DomainError('IBPT_SNAPSHOT_NOT_AVAILABLE',str(exc),404) from exc

@router.get("/fiscal/ibpt/operational-status",operation_id="get_ibpt_operational_status")
def api_ibpt_operational_status(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,FISCAL_ROLES);return ibpt_operational_status(request.app.state.data_router,tenant_id=tenant(user))


# Governança e importação versionada de catálogos fiscais -------------------

@router.get("/fiscal/catalog-sources", operation_id="list_fiscal_catalog_sources")
def api_list_catalog_sources(
    request: Request,
    catalog_id: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return list_catalog_sources(request, tenant(user), catalog_id)


@router.post("/fiscal/catalogs/{catalog_id}/sources", status_code=201, operation_id="create_fiscal_catalog_source")
def api_create_catalog_source(
    catalog_id: str,
    data: FiscalCatalogSourceCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = create_catalog_source(catalog_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/catalog-imports", operation_id="list_fiscal_catalog_imports")
def api_list_catalog_imports(
    request: Request,
    catalog_id: str | None = None,
    state: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return list_catalog_imports(request, tenant(user), catalog_id, state)


@router.post("/fiscal/catalogs/{catalog_id}/imports", status_code=201, operation_id="import_fiscal_catalog_snapshot")
def api_import_catalog_snapshot(
    catalog_id: str,
    data: FiscalCatalogImportCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = import_catalog_snapshot(catalog_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/catalog-imports/{run_id}", operation_id="get_fiscal_catalog_import")
def api_get_catalog_import(run_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return catalog_import_detail(request, tenant(user), run_id)


@router.post("/fiscal/catalog-imports/{run_id}/publish", operation_id="publish_fiscal_catalog_import")
def api_publish_catalog_import(
    run_id: str,
    data: FiscalCatalogImportPublish,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = publish_catalog_import(run_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.post(
    "/fiscal/catalogs/{catalog_id}/versions/{version_id}/rollback",
    status_code=201,
    operation_id="rollback_fiscal_catalog_version",
)
def api_rollback_catalog_version(
    catalog_id: str,
    version_id: str,
    data: FiscalCatalogRollback,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    status_code, result = rollback_catalog_version(catalog_id, version_id, data, request, tenant(user), user, idempotency_key)
    response.status_code = status_code
    return result


@router.get("/fiscal/catalog-governance/health", operation_id="get_fiscal_catalog_governance_health")
def api_catalog_governance_health(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES)
    return catalog_governance_health(request, tenant(user))


@router.get("/fiscal/catalog-quarantine", operation_id="list_fiscal_catalog_quarantine")
def api_list_catalog_quarantine(
    request: Request,
    state: str | None = "open",
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return list_catalog_quarantine(request, tenant(user), state)


@router.post("/fiscal/catalog-quarantine/{quarantine_id}/resolve", operation_id="resolve_fiscal_catalog_quarantine")
def api_resolve_catalog_quarantine(
    quarantine_id: str,
    data: FiscalCatalogQuarantineResolve,
    request: Request,
    user: CurrentUser = Depends(current_user),
):
    require(user, FISCAL_ROLES)
    return resolve_catalog_quarantine(quarantine_id, data, request, tenant(user), user)


# Fiscal routing and versioned document assembly -----------------------------
@router.get("/fiscal/document-schemas", operation_id="list_fiscal_document_schemas")
def fiscal_document_schemas_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); return list_fiscal_document_schemas(request, tenant(user))

@router.post("/fiscal/document-schemas", status_code=201, operation_id="create_fiscal_document_schema")
def fiscal_document_schemas_create(data: FiscalDocumentSchemaCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); status, result = create_fiscal_document_schema(data, request, tenant(user), user, idempotency_key); response.status_code=status; return result

@router.post("/fiscal/document-schemas/{schema_id}/publish", operation_id="publish_fiscal_document_schema")
def fiscal_document_schemas_publish(schema_id: str, data: FiscalDocumentSchemaPublish, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); return publish_fiscal_document_schema(schema_id, data, request, tenant(user), user)

@router.get("/fiscal/routing-policies", operation_id="list_fiscal_routing_policies")
def fiscal_routing_policies_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); return list_fiscal_routing_policies(request, tenant(user))

@router.post("/fiscal/routing-policies", status_code=201, operation_id="create_fiscal_routing_policy")
def fiscal_routing_policies_create(data: FiscalRoutingPolicyCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); status, result = create_fiscal_routing_policy(data, request, tenant(user), user, idempotency_key); response.status_code=status; return result

@router.post("/fiscal/routing-policies/{policy_id}/publish", operation_id="publish_fiscal_routing_policy")
def fiscal_routing_policies_publish(policy_id: str, data: FiscalRoutingPolicyPublish, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); return publish_fiscal_routing_policy(policy_id, data, request, tenant(user), user)

@router.get("/fiscal/document-assemblies", operation_id="list_fiscal_document_assemblies")
def fiscal_document_assemblies_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | SALES_ROLES); return list_fiscal_assemblies(request, tenant(user))

@router.post("/fiscal/document-assemblies", status_code=201, operation_id="assemble_fiscal_documents")
def fiscal_document_assemblies_create(data: FiscalDocumentAssemblyCreate, request: Request, response: Response, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200), user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | SALES_ROLES); status, result = assemble_fiscal_document(data, request, tenant(user), user, idempotency_key); response.status_code=status; return result

@router.get("/fiscal/document-assemblies/{assembly_id}", operation_id="get_fiscal_document_assembly")
def fiscal_document_assemblies_get(assembly_id: str, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES | SALES_ROLES); return fiscal_assembly_detail(request, tenant(user), assembly_id)

@router.get("/fiscal/emission-trigger-runs", operation_id="list_fiscal_emission_trigger_runs")
def fiscal_emission_trigger_runs_list(request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); return list_fiscal_emission_trigger_runs(request, tenant(user))

@router.post("/fiscal/emission-trigger-runs/evaluate", operation_id="evaluate_fiscal_emission_trigger")
def fiscal_emission_trigger_evaluate(data: FiscalEmissionTriggerEvaluate, request: Request, user: CurrentUser = Depends(current_user)):
    require(user, FISCAL_ROLES); return evaluate_fiscal_emission_trigger(data, request, tenant(user))
