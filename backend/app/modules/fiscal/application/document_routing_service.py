from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import Request
from lxml import etree

from app.modules.fiscal.application.context_service import fiscal_context_snapshot_by_version
from app.modules.fiscal.application.transparency_service import calculate_build_transparency, link_transparency_document
from app.modules.fiscal.presentation.document_routing_schemas import (
    FiscalDocumentAssemblyCreate, FiscalDocumentSchemaCreate, FiscalDocumentSchemaPublish,
    FiscalEmissionTriggerEvaluate, FiscalRoutingPolicyCreate, FiscalRoutingPolicyPublish,
)
from app.shared.application.idempotency import get_idempotent, save_idempotent
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_dump(value).encode()).hexdigest()


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)): return value
    if not value: return default
    try: return json.loads(value)
    except Exception: return default


def _row(store, sql: str, params: tuple[Any, ...], code: str, message: str):
    row = store.fetch_one(sql, params)
    if not row: raise DomainError(code, message, 404)
    return row


def _effective_context(conn, tenant_id: str, context_id: str, occurred_on: date) -> dict[str, Any]:
    target = occurred_on.isoformat()
    row = conn.execute(
        "SELECT id FROM fiscal_context_versions WHERE tenant_id=? AND fiscal_context_id=? AND state IN ('published','scheduled','superseded') AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY valid_from DESC,version_number DESC LIMIT 1",
        (tenant_id, context_id, target, target),
    ).fetchone()
    if not row: raise DomainError("FISCAL_CONTEXT_NOT_EFFECTIVE", "Nenhuma versão fiscal vigente para o contexto.", 409)
    return fiscal_context_snapshot_by_version(conn, tenant_id=tenant_id, version_id=row["id"], occurred_on=occurred_on)


def _decode_xsd(data: FiscalDocumentSchemaCreate) -> bytes:
    try:
        raw = data.xsd_text.encode("utf-8") if data.xsd_text is not None else base64.b64decode(data.xsd_base64 or "", validate=True)
        doc = etree.fromstring(raw)
        etree.XMLSchema(doc)
        return raw
    except Exception as exc:
        raise DomainError("FISCAL_XSD_INVALID", f"XSD inválido: {exc}", 422) from exc


def list_schemas(request: Request, tenant_id: str) -> dict[str, Any]:
    return {"items": request.state.store.fetch_all("SELECT id,document_type,schema_code,version_label,valid_from,valid_until,root_element,namespace_uri,source_reference,xsd_sha256,state,version,created_at,published_at FROM fiscal_document_schema_versions WHERE tenant_id=? ORDER BY document_type,valid_from DESC,version DESC", (tenant_id,))}


def create_schema(data: FiscalDocumentSchemaCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json", exclude={"xsd_text","xsd_base64"}); raw=_decode_xsd(data); digest=hashlib.sha256(raw).hexdigest(); scope=f"fiscal-xsd:{tenant_id}:{data.schema_code}:{data.version_label}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,{**body,"xsd_sha256":digest})
        if cached:return cached
        if conn.execute("SELECT 1 FROM fiscal_document_schema_versions WHERE tenant_id=? AND schema_code=? AND version_label=?",(tenant_id,data.schema_code,data.version_label)).fetchone(): raise DomainError("FISCAL_SCHEMA_EXISTS","Schema/versão já cadastrado.",409)
        sid=uuid7();now=iso_now();obj=request.app.state.data_router.object_storage(tenant_id).put_bytes(f"fiscal/schemas/{sid}/{data.schema_code}-{data.version_label}.xsd",raw,content_type="application/xml")
        conn.execute("INSERT INTO fiscal_document_schema_versions(id,tenant_id,document_type,schema_code,version_label,valid_from,valid_until,root_element,namespace_uri,source_reference,xsd_storage_key,xsd_sha256,metadata_json,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',1,?,?,?)",(sid,tenant_id,data.document_type,data.schema_code,data.version_label,str(data.valid_from),str(data.valid_until) if data.valid_until else None,data.root_element,data.namespace_uri,data.source_reference,obj.key,obj.sha256,_dump(data.metadata),user.id,now,now))
        result={"id":sid,"document_type":data.document_type,"schema_code":data.schema_code,"version_label":data.version_label,"xsd_sha256":obj.sha256,"state":"draft","version":1}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="create",aggregate_type="fiscal_document_schema",aggregate_id=sid,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentSchemaCreated",aggregate_type="fiscal_document_schema",aggregate_id=sid,payload=result,correlation_id=request.state.correlation_id);save_idempotent(conn,scope,idempotency_key,{**body,"xsd_sha256":digest},201,result)
    return 201,result


def publish_schema(schema_id: str, data: FiscalDocumentSchemaPublish, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM fiscal_document_schema_versions WHERE tenant_id=? AND id=?",(tenant_id,schema_id)).fetchone()
        if not row:raise DomainError("FISCAL_SCHEMA_NOT_FOUND","Schema fiscal não localizado.",404)
        row=dict(row)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        if row["state"]=="published":return {"id":schema_id,"state":"published","version":row["version"]}
        overlap=conn.execute("SELECT id FROM fiscal_document_schema_versions WHERE tenant_id=? AND document_type=? AND state='published' AND id<>? AND valid_from<=COALESCE(?, '9999-12-31') AND (valid_until IS NULL OR valid_until>=?) LIMIT 1",(tenant_id,row["document_type"],schema_id,row["valid_until"],row["valid_from"])).fetchone()
        if overlap:raise DomainError("FISCAL_SCHEMA_PERIOD_OVERLAP","Já existe schema publicado vigente no período para este documento.",409)
        now=iso_now();version=int(row["version"])+1;conn.execute("UPDATE fiscal_document_schema_versions SET state='published',published_by=?,published_at=?,version=?,updated_at=? WHERE tenant_id=? AND id=?",(user.id,now,version,now,tenant_id,schema_id));result={"id":schema_id,"state":"published","version":version,"reason":data.reason}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="publish",aggregate_type="fiscal_document_schema",aggregate_id=schema_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after=result);add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentSchemaPublished",aggregate_type="fiscal_document_schema",aggregate_id=schema_id,payload=result,correlation_id=request.state.correlation_id)
        return result


def list_policies(request: Request, tenant_id: str) -> dict[str, Any]:
    items=request.state.store.fetch_all("SELECT * FROM fiscal_document_routing_policies WHERE tenant_id=? ORDER BY priority,valid_from DESC,version DESC",(tenant_id,))
    for i in items:i["trigger_types"]=_loads(i.pop("trigger_types_json","[]"),[]);i["settings"]=_loads(i.pop("settings_json","{}"),{})
    return {"items":items}


def create_policy(data: FiscalRoutingPolicyCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int, dict[str, Any]]:
    body=data.model_dump(mode="json");scope=f"fiscal-routing-policy:{tenant_id}:{data.fiscal_context_id}:{data.code}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:return cached
        if not conn.execute("SELECT 1 FROM fiscal_contexts WHERE tenant_id=? AND id=?",(tenant_id,data.fiscal_context_id)).fetchone():raise DomainError("FISCAL_CONTEXT_NOT_FOUND","Contexto fiscal não localizado.",404)
        version=int((conn.execute("SELECT COALESCE(MAX(version),0) AS n FROM fiscal_document_routing_policies WHERE tenant_id=? AND fiscal_context_id=? AND code=?",(tenant_id,data.fiscal_context_id,data.code)).fetchone() or {"n":0})["n"])+1
        pid=uuid7();now=iso_now();conn.execute("INSERT INTO fiscal_document_routing_policies(id,tenant_id,fiscal_context_id,code,name,operation_type,recipient_scope,channel_scope,product_document_type,service_document_type,trigger_types_json,valid_from,valid_until,priority,settings_json,state,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,tenant_id,data.fiscal_context_id,data.code,data.name,data.operation_type,data.recipient_scope,data.channel_scope,data.product_document_type,data.service_document_type,_dump(data.trigger_types),str(data.valid_from),str(data.valid_until) if data.valid_until else None,data.priority,_dump(data.settings),"draft",version,user.id,now,now));result={"id":pid,"code":data.code,"state":"draft","version":version}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="create",aggregate_type="fiscal_routing_policy",aggregate_id=pid,correlation_id=request.state.correlation_id,after=result);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return 201,result


def publish_policy(policy_id: str, data: FiscalRoutingPolicyPublish, request: Request, tenant_id: str, user: CurrentUser) -> dict[str, Any]:
    with request.state.store.transaction() as conn:
        row=conn.execute("SELECT * FROM fiscal_document_routing_policies WHERE tenant_id=? AND id=?",(tenant_id,policy_id)).fetchone()
        if not row:raise DomainError("FISCAL_ROUTING_POLICY_NOT_FOUND","Política de roteamento não localizada.",404)
        row=dict(row)
        if int(row["version"])!=data.expected_version:raise DomainError("VERSION_CONFLICT","Versão divergente.",409)
        now=iso_now();conn.execute("UPDATE fiscal_document_routing_policies SET state='published',published_by=?,published_at=?,updated_at=? WHERE tenant_id=? AND id=?",(user.id,now,now,tenant_id,policy_id));result={"id":policy_id,"state":"published","version":row["version"],"reason":data.reason};add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="publish",aggregate_type="fiscal_routing_policy",aggregate_id=policy_id,correlation_id=request.state.correlation_id,after=result);add_outbox(conn,tenant_id=tenant_id,event_type="FiscalRoutingPolicyPublished",aggregate_type="fiscal_routing_policy",aggregate_id=policy_id,payload=result,correlation_id=request.state.correlation_id);return result


def _source_items(conn, tenant_id: str, source_type: str, source_id: str) -> list[dict[str, Any]]:
    if source_type=="sale":
        sale=conn.execute("SELECT * FROM sales WHERE tenant_id=? AND id=?",(tenant_id,source_id)).fetchone()
        if not sale:raise DomainError("FISCAL_SOURCE_NOT_FOUND","Venda não localizada.",404)
        return [dict(x) for x in conn.execute("SELECT si.id AS line_id,'product' AS item_kind,p.id AS item_id,p.sku AS code,p.name AS description,si.quantity,si.unit_price,si.discount,si.total_amount,p.ncm,p.cest FROM sale_items si JOIN products p ON p.id=si.product_id AND p.tenant_id=si.tenant_id WHERE si.tenant_id=? AND si.sale_id=? ORDER BY si.id",(tenant_id,source_id)).fetchall()]
    if source_type=="service_order":
        order=conn.execute("SELECT * FROM service_orders WHERE tenant_id=? AND id=?",(tenant_id,source_id)).fetchone()
        if not order:raise DomainError("FISCAL_SOURCE_NOT_FOUND","Pedido de serviço não localizado.",404)
        return [dict(x) for x in conn.execute("SELECT oi.id AS line_id,'service' AS item_kind,s.id AS item_id,s.code,s.name AS description,oi.quantity,oi.unit_price,oi.discount_amount AS discount,oi.total_amount,s.nbs,s.lc116_code,s.municipal_code,s.cnae FROM service_order_items oi JOIN services s ON s.id=oi.service_id AND s.tenant_id=oi.tenant_id WHERE oi.tenant_id=? AND oi.service_order_id=? ORDER BY oi.id",(tenant_id,source_id)).fetchall()]
    return []


def _policy(conn, tenant_id: str, data: FiscalDocumentAssemblyCreate, context: dict[str, Any]) -> dict[str, Any] | None:
    target=data.occurred_on.isoformat()
    rows=conn.execute("SELECT * FROM fiscal_document_routing_policies WHERE tenant_id=? AND fiscal_context_id=? AND state='published' AND operation_type IN (?, 'any') AND recipient_scope IN (?, 'any') AND channel_scope IN (?, 'any') AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY priority ASC,version DESC",(tenant_id,data.fiscal_context_id,data.operation_type,data.recipient_scope,data.channel,target,target)).fetchall()
    contract_id=None
    if data.source_type=="service_order":
        source=conn.execute("SELECT financial_contract_id FROM service_orders WHERE tenant_id=? AND id=?",(tenant_id,data.source_id)).fetchone()
        contract_id=source["financial_contract_id"] if source else None
    version=context["version"]
    for raw in rows:
        row=dict(raw);triggers=_loads(row["trigger_types_json"],[]);settings=_loads(row["settings_json"],{})
        if not (data.trigger_type in triggers or ("manual" in triggers and data.trigger_type=="manual")):
            continue
        regimes={str(x) for x in settings.get("tax_regimes",[]) if x}
        municipalities={str(x) for x in settings.get("municipality_codes",[]) if x}
        contract_ids={str(x) for x in settings.get("financial_contract_ids",[]) if x}
        if regimes and str(version.get("tax_regime") or "") not in regimes:
            continue
        if municipalities and str(version.get("municipality_code") or "") not in municipalities:
            continue
        if settings.get("require_financial_contract") and not contract_id:
            continue
        if contract_ids and str(contract_id or "") not in contract_ids:
            continue
        row["trigger_types"]=triggers;row["settings"]=settings;row["financial_contract_id"]=contract_id
        return row
    return None


def _product_document(context: dict[str, Any], data: FiscalDocumentAssemblyCreate, policy: dict[str, Any] | None) -> tuple[str,list[str]]:
    if policy and policy.get("product_document_type"):return str(policy["product_document_type"]),["routing_policy_product_override"]
    reasons=[]; origin=context["version"]["uf"]
    if data.recipient_scope in {"company","government","foreign"}:return "NF-e",["recipient_requires_nfe"]
    if data.destination_uf and data.destination_uf != origin:return "NF-e",["interstate_operation_requires_nfe"]
    if data.channel.lower() in {"pos","canteen","kiosk","retail","counter"}:return "NFC-e",["consumer_retail_channel"]
    return "NF-e",["default_product_document"]


def _effective_schema(conn, tenant_id: str, document_type: str, occurred_on: date) -> dict[str, Any] | None:
    row=conn.execute("SELECT * FROM fiscal_document_schema_versions WHERE tenant_id=? AND document_type=? AND state='published' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY valid_from DESC,version DESC LIMIT 1",(tenant_id,document_type,occurred_on.isoformat(),occurred_on.isoformat())).fetchone();return dict(row) if row else None


def _build_xml(document_type: str, schema: dict[str, Any], assembly_id: str, data: FiscalDocumentAssemblyCreate, context: dict[str, Any], items: list[dict[str, Any]]) -> bytes:
    ns=schema.get("namespace_uri") or None; root=etree.Element(f"{{{ns}}}{schema['root_element']}" if ns else schema["root_element"], nsmap={None:ns} if ns else None)
    def child(parent,name,text):
        element=etree.SubElement(parent,f"{{{ns}}}{name}" if ns else name);element.text=str(text);return element
    child(root,"DocumentType",document_type);child(root,"AssemblyId",assembly_id);child(root,"SourceType",data.source_type);child(root,"SourceId",data.source_id);child(root,"OccurredOn",data.occurred_on.isoformat());issuer=etree.SubElement(root,f"{{{ns}}}Issuer" if ns else "Issuer");child(issuer,"CNPJ",context["context"]["cnpj"]);child(issuer,"UF",context["version"]["uf"]);recipient=etree.SubElement(root,f"{{{ns}}}Recipient" if ns else "Recipient");child(recipient,"Scope",data.recipient_scope);child(recipient,"Name",data.recipient.name or "");child(recipient,"Document",data.recipient.document or "");items_el=etree.SubElement(root,f"{{{ns}}}Items" if ns else "Items");total=Decimal("0")
    for item in items:
        line=etree.SubElement(items_el,f"{{{ns}}}Item" if ns else "Item");child(line,"LineId",item["line_id"]);child(line,"Kind",item["item_kind"]);child(line,"Code",item.get("code") or "");child(line,"Description",item["description"]);child(line,"Quantity",item["quantity"]);child(line,"UnitPrice",item["unit_price"]);child(line,"Discount",item.get("discount") or 0);child(line,"TotalAmount",item["total_amount"]);total+=Decimal(str(item["total_amount"]))
    totals=etree.SubElement(root,f"{{{ns}}}Totals" if ns else "Totals");child(totals,"TotalAmount",f"{total:.2f}")
    return etree.tostring(root,encoding="utf-8",xml_declaration=True,pretty_print=False)


def _validate_xml(storage, schema: dict[str, Any], xml_bytes: bytes) -> tuple[str,list[str]]:
    try:
        xsd=storage.get_bytes(schema["xsd_storage_key"]);validator=etree.XMLSchema(etree.fromstring(xsd));doc=etree.fromstring(xml_bytes);ok=validator.validate(doc);return ("valid",[]) if ok else ("invalid",[str(e) for e in validator.error_log])
    except Exception as exc:return "invalid",[str(exc)]


def _create_document(conn, storage, tenant_id: str, actor_id: str, correlation_id: str, data: FiscalDocumentAssemblyCreate, context: dict[str, Any], profile: dict[str, Any], build_id: str, document_type: str, xml_key: str, xml_sha: str, total: str, contingency_mode: str | None) -> str:
    existing=conn.execute("SELECT fd.id FROM fiscal_document_links l JOIN fiscal_documents fd ON fd.id=l.fiscal_document_id AND fd.tenant_id=l.tenant_id WHERE l.tenant_id=? AND l.build_id=? LIMIT 1",(tenant_id,build_id)).fetchone()
    if existing:return existing["id"]
    existing=conn.execute("SELECT id FROM fiscal_documents WHERE tenant_id=? AND document_type=? AND source_type=? AND source_id=? ORDER BY created_at LIMIT 1",(tenant_id,document_type,data.source_type,data.source_id)).fetchone()
    if existing:
        return existing["id"]
    provider_id=context["context"].get("provider_connection_id") or profile.get("provider_connection_id");provider_status="not_configured"
    if provider_id:
        con=conn.execute("SELECT state FROM integration_connections WHERE tenant_id=? AND id=?",(tenant_id,provider_id)).fetchone();provider_status="queued" if con and con["state"] in {"configured","degraded"} else "not_configured"
    fid=uuid7();now=iso_now();request_payload={"assembly_build_id":build_id,"xml_storage_key":xml_key,"xml_sha256":xml_sha,"routing_source":data.source_type,"routing_source_id":data.source_id};conn.execute("INSERT INTO fiscal_documents(id,tenant_id,fiscal_profile_id,fiscal_context_id,fiscal_context_version_id,fiscal_context_snapshot_json,document_type,source_type,source_id,environment,state,provider_connection_id,provider_status,totals_json,request_json,response_json,contingency_mode,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fid,tenant_id,profile["id"],context["context"]["id"],context["version"]["id"],_dump(context),document_type,data.source_type,data.source_id,context["version"]["environment"],"requested",provider_id,provider_status,_dump({"total":total}),_dump(request_payload),"{}",contingency_mode,now,now));conn.execute("INSERT INTO fiscal_document_artifacts(id,tenant_id,fiscal_document_id,artifact_type,content_type,storage_key,sha256,bytes_count,provider_event_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,fid,"assembled_xml","application/xml",xml_key,xml_sha,len(storage.get_bytes(xml_key)),None,now));conn.execute("INSERT INTO fiscal_document_events(id,tenant_id,fiscal_document_id,event_type,state,provider_connection_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,fid,"assembly_ready","requested",provider_id,_dump(request_payload),now));add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentRequested",aggregate_type="fiscal_document",aggregate_id=fid,payload={"id":fid,"document_type":document_type,"assembly_build_id":build_id},correlation_id=correlation_id)
    if data.source_type == "service_order":
        financial = conn.execute("SELECT financial_contract_id,charge_id FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, data.source_id)).fetchone()
        if financial and (financial["financial_contract_id"] or financial["charge_id"]):
            conn.execute("INSERT OR IGNORE INTO fiscal_document_financial_links(id,tenant_id,fiscal_document_id,source_type,source_id,financial_contract_id,charge_id,payment_id,adjustment_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (uuid7(),tenant_id,fid,data.source_type,data.source_id,financial["financial_contract_id"],financial["charge_id"],None,"linked",now,now))
    return fid


def assemble_document(data: FiscalDocumentAssemblyCreate, request: Request, tenant_id: str, user: CurrentUser, idempotency_key: str) -> tuple[int,dict[str,Any]]:
    return _assemble(data, request.state.store, request.app.state.data_router.object_storage(tenant_id), tenant_id, user.id, request.state.correlation_id, idempotency_key)


def _assemble(data: FiscalDocumentAssemblyCreate, store, storage, tenant_id: str, actor_id: str, correlation_id: str, idempotency_key: str) -> tuple[int,dict[str,Any]]:
    body=data.model_dump(mode="json");scope=f"fiscal-assembly:{tenant_id}:{data.source_type}:{data.source_id}:{data.trigger_type}"
    with store.transaction() as conn:
        cached=get_idempotent(conn,scope,idempotency_key,body)
        if cached:return cached
        profile=conn.execute("SELECT * FROM fiscal_profiles WHERE tenant_id=? AND id=? AND state='active'",(tenant_id,data.fiscal_profile_id)).fetchone()
        if not profile:raise DomainError("FISCAL_PROFILE_NOT_FOUND","Perfil fiscal não localizado.",404)
        profile=dict(profile);context=_effective_context(conn,tenant_id,data.fiscal_context_id,data.occurred_on)
        if ''.join(c for c in profile['cnpj'] if c.isdigit()) != context['context']['cnpj']:raise DomainError("FISCAL_CONTEXT_PROFILE_MISMATCH","Perfil e contexto pertencem a CNPJs diferentes.",409)
        policy=_policy(conn,tenant_id,data,context);items=[i.model_dump(mode="json") for i in data.items] or _source_items(conn,tenant_id,data.source_type,data.source_id)
        if not items:raise DomainError("FISCAL_ASSEMBLY_ITEMS_EMPTY","Nenhum item fiscal para montar.",422)
        for i in items:
            i.setdefault("discount",0);i.setdefault("classification",{})
        product=[i for i in items if i["item_kind"]=="product"];services=[i for i in items if i["item_kind"]=="service"]
        routes=[]
        if product:
            doc,reasons=_product_document(context,data,policy);routes.append((doc,product,"product_part" if services else "primary",reasons))
        if services:
            routes.append(((policy or {}).get("service_document_type") or "NFS-e",services,"service_part" if product else "primary",["service_nature_requires_nfse"] if not policy else ["routing_policy_service_document"]))
        aid=uuid7();now=iso_now();input_snapshot={"request":body,"items":items,"context_sha256":context["sha256"]};input_sha=_sha(input_snapshot);decision={"policy_id":policy.get("id") if policy else None,"policy_code":policy.get("code") if policy else None,"dimensions":{"operation_type":data.operation_type,"recipient_scope":data.recipient_scope,"channel":data.channel,"trigger_type":data.trigger_type,"tax_regime":context["version"].get("tax_regime"),"municipality_code":context["version"].get("municipality_code"),"origin_uf":context["version"].get("uf"),"destination_uf":data.destination_uf,"financial_contract_id":policy.get("financial_contract_id") if policy else None},"routes":[{"document_type":r[0],"relationship":r[2],"reasons":r[3],"item_count":len(r[1])} for r in routes],"mixed":bool(product and services)}
        conn.execute("INSERT INTO fiscal_document_assemblies(id,tenant_id,source_type,source_id,fiscal_context_id,fiscal_context_version_id,routing_policy_id,fiscal_profile_id,occurred_on,operation_type,recipient_scope,channel,trigger_type,state,input_snapshot_json,input_sha256,routing_decision_json,output_snapshot_json,output_sha256,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'building',?,?,?,?,?,?,?,?)",(aid,tenant_id,data.source_type,data.source_id,context["context"]["id"],context["version"]["id"],policy.get("id") if policy else None,data.fiscal_profile_id,data.occurred_on.isoformat(),data.operation_type,data.recipient_scope,data.channel,data.trigger_type,_dump(input_snapshot),input_sha,_dump(decision),"{}",None,actor_id,now,now))
        builds=[];blocked=False
        for document_type,group,relationship,reasons in routes:
            schema=_effective_schema(conn,tenant_id,document_type,data.occurred_on);bid=uuid7();total=sum(Decimal(str(i["total_amount"])) for i in group)
            if schema:
                xml=_build_xml(document_type,schema,aid,data,context,group);obj=storage.put_bytes(f"fiscal/assemblies/{aid}/{bid}.xml",xml,content_type="application/xml");validation,errors=_validate_xml(storage,schema,xml)
            else:
                xml=b"";obj=None;validation="schema_not_configured";errors=["Nenhum XSD publicado vigente para o tipo documental."];blocked=True
            if validation!="valid":blocked=True
            conn.execute("INSERT INTO fiscal_document_builds(id,tenant_id,assembly_id,document_type,relationship,schema_version_id,payload_json,xml_storage_key,xml_sha256,validation_state,validation_errors_json,total_amount,item_count,fiscal_document_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(bid,tenant_id,aid,document_type,relationship,schema.get("id") if schema else None,_dump({"items":group,"context":context,"routing_reasons":reasons}),obj.key if obj else None,obj.sha256 if obj else None,validation,_dump(errors),str(total),len(group),None,now))
            real_by_document = data.metadata.get("real_taxes_by_document") if isinstance(data.metadata.get("real_taxes_by_document"), dict) else {}
            real_taxes = real_by_document.get(document_type, data.metadata.get("real_taxes", {})) if isinstance(real_by_document, dict) else data.metadata.get("real_taxes", {})
            transparency = calculate_build_transparency(
                conn, tenant_id=tenant_id, build_id=bid, document_type=document_type, items=group,
                uf=str(context["version"].get("uf") or ""), occurred_on=data.occurred_on,
                real_taxes=real_taxes if isinstance(real_taxes, dict) else {},
            )
            add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentTaxTransparencyCalculated",aggregate_type="fiscal_document_build",aggregate_id=bid,payload={"build_id":bid,"document_type":document_type,"vTotTrib":transparency["vTotTrib"],"tax_calculation_source":False},correlation_id=correlation_id)
            builds.append({"id":bid,"document_type":document_type,"relationship":relationship,"schema_version_id":schema.get("id") if schema else None,"xml_storage_key":obj.key if obj else None,"xml_sha256":obj.sha256 if obj else None,"validation_state":validation,"validation_errors":errors,"total_amount":f"{total:.2f}","item_count":len(group),"routing_reasons":reasons,"tax_transparency":transparency})
        docs=[]
        if data.request_emission and not blocked:
            for b in builds:
                fid=_create_document(conn,storage,tenant_id,actor_id,correlation_id,data,context,profile,b["id"],b["document_type"],b["xml_storage_key"],b["xml_sha256"],b["total_amount"],data.contingency_mode);conn.execute("UPDATE fiscal_document_builds SET fiscal_document_id=? WHERE tenant_id=? AND id=?",(fid,tenant_id,b["id"]));link_transparency_document(conn,tenant_id=tenant_id,build_id=b["id"],fiscal_document_id=fid);conn.execute("INSERT INTO fiscal_document_links(id,tenant_id,assembly_id,build_id,fiscal_document_id,source_type,source_id,relationship,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tenant_id,aid,b["id"],fid,data.source_type,data.source_id,b["relationship"],now));docs.append({"id":fid,"document_type":b["document_type"],"relationship":b["relationship"]})
        state="blocked_validation" if blocked else ("emission_requested" if docs else "assembled");output={"assembly_id":aid,"state":state,"input_sha256":input_sha,"routing":decision,"context_sha256":context["sha256"],"builds":builds,"documents":docs};out_sha=_sha(output);conn.execute("UPDATE fiscal_document_assemblies SET state=?,output_snapshot_json=?,output_sha256=?,updated_at=? WHERE tenant_id=? AND id=?",(state,_dump(output),out_sha,now,tenant_id,aid));result={**output,"output_sha256":out_sha};add_audit(conn,tenant_id=tenant_id,actor_id=actor_id,action="assemble",aggregate_type="fiscal_document_assembly",aggregate_id=aid,correlation_id=correlation_id,after=result);add_outbox(conn,tenant_id=tenant_id,event_type="FiscalDocumentAssemblyCompleted",aggregate_type="fiscal_document_assembly",aggregate_id=aid,payload={"id":aid,"state":state,"documents":docs,"mixed":decision["mixed"]},correlation_id=correlation_id);save_idempotent(conn,scope,idempotency_key,body,201,result)
    return 201,result


def list_assemblies(request: Request, tenant_id: str) -> dict[str,Any]:
    return {"items":request.state.store.fetch_all("SELECT id,source_type,source_id,occurred_on,operation_type,recipient_scope,channel,trigger_type,state,input_sha256,output_sha256,created_at FROM fiscal_document_assemblies WHERE tenant_id=? ORDER BY created_at DESC",(tenant_id,))}


def assembly_detail(request: Request, tenant_id: str, assembly_id: str) -> dict[str,Any]:
    row=_row(request.state.store,"SELECT * FROM fiscal_document_assemblies WHERE tenant_id=? AND id=?",(tenant_id,assembly_id),"FISCAL_ASSEMBLY_NOT_FOUND","Montagem fiscal não localizada.");row["input_snapshot"]=_loads(row.pop("input_snapshot_json"),{});row["routing_decision"]=_loads(row.pop("routing_decision_json"),{});row["output_snapshot"]=_loads(row.pop("output_snapshot_json"),{});row["builds"]=request.state.store.fetch_all("SELECT * FROM fiscal_document_builds WHERE tenant_id=? AND assembly_id=? ORDER BY created_at",(tenant_id,assembly_id));row["links"]=request.state.store.fetch_all("SELECT * FROM fiscal_document_links WHERE tenant_id=? AND assembly_id=? ORDER BY created_at",(tenant_id,assembly_id));return row


def list_trigger_runs(request: Request, tenant_id: str) -> dict[str,Any]:
    return {"items":request.state.store.fetch_all("SELECT * FROM fiscal_emission_trigger_runs WHERE tenant_id=? ORDER BY created_at DESC",(tenant_id,))}


def _profile_for_context(conn, tenant_id: str, context_id: str) -> tuple[str,str] | None:
    c=conn.execute("SELECT cnpj FROM fiscal_contexts WHERE tenant_id=? AND id=?",(tenant_id,context_id)).fetchone()
    if not c:return None
    row=conn.execute("SELECT id,cnpj FROM fiscal_profiles WHERE tenant_id=? AND state='active' ORDER BY created_at DESC",(tenant_id,)).fetchall()
    target=c["cnpj"]
    for p in row:
        if ''.join(x for x in p["cnpj"] if x.isdigit())==target:return p["id"],target
    return None


def process_emission_trigger(router, tenant_id: str, event_type: str, aggregate_id: str, payload: dict[str,Any], correlation_id: str) -> dict[str,Any]:
    store=router.tenant_store(tenant_id);storage=router.object_storage(tenant_id);now=iso_now()
    existing=store.fetch_one("SELECT * FROM fiscal_emission_trigger_runs WHERE tenant_id=? AND event_type=? AND aggregate_id=?",(tenant_id,event_type,aggregate_id))
    if existing:return {"state":existing["state"],"id":existing["id"],"idempotent":True}
    trigger={"SaleCompleted":"sale_completed","ServiceOrderConfirmed":"service_order_confirmed","ServiceCompetenceBilled":"competence","PaymentConfirmed":"payment","ChargeCreated":"billing"}.get(event_type)
    if not trigger:return {"state":"ignored","reason":"unsupported_event"}
    source_type="sale" if event_type=="SaleCompleted" else "service_order";source_id=str(payload.get("service_order_id") or payload.get("order_id") or payload.get("id") or aggregate_id)
    if event_type=="PaymentConfirmed":
        payment_id=str(payload.get("id") or aggregate_id);row=store.fetch_one("SELECT so.id FROM payment_allocations pa JOIN installments i ON i.id=pa.installment_id AND i.tenant_id=pa.tenant_id JOIN service_orders so ON so.financial_contract_id=i.financial_contract_id AND so.tenant_id=i.tenant_id WHERE pa.tenant_id=? AND pa.payment_id=? ORDER BY so.created_at DESC LIMIT 1",(tenant_id,payment_id))
        if not row:source_id="" 
        else:source_id=row["id"]
    if event_type=="ChargeCreated":
        charge_id=str(payload.get("id") or aggregate_id)
        row=store.fetch_one("SELECT origin_type,origin_id,financial_contract_id FROM charges WHERE tenant_id=? AND id=?",(tenant_id,charge_id))
        if not row:
            source_id=""
        elif row.get("origin_type") in {"service_order","sale"} and row.get("origin_id"):
            source_type=str(row["origin_type"]);source_id=str(row["origin_id"])
        elif row.get("financial_contract_id"):
            order=store.fetch_one("SELECT id FROM service_orders WHERE tenant_id=? AND financial_contract_id=? ORDER BY created_at DESC LIMIT 1",(tenant_id,row["financial_contract_id"]))
            source_type="service_order";source_id=str(order["id"]) if order else ""
        else:
            source_id=""
    with store.transaction() as conn:
        run_id=uuid7();policy=None
        if source_id:
            today=date.today()
            policies=conn.execute("SELECT * FROM fiscal_document_routing_policies WHERE tenant_id=? AND state='published' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY priority,version DESC",(tenant_id,today.isoformat(),today.isoformat())).fetchall()
            for raw_policy in policies:
                candidate=dict(raw_policy)
                if trigger not in _loads(candidate["trigger_types_json"],[]):
                    continue
                try:
                    candidate_context=_effective_context(conn,tenant_id,candidate["fiscal_context_id"],today)
                    probe=FiscalDocumentAssemblyCreate(
                        fiscal_context_id=candidate["fiscal_context_id"], fiscal_profile_id="policy-probe",
                        source_type=source_type, source_id=source_id, occurred_on=today,
                        operation_type=candidate["operation_type"], recipient_scope=str(payload.get("recipient_scope") or "individual"),
                        channel=str(payload.get("channel") or ("service" if source_type=="service_order" else "retail")),
                        trigger_type=trigger, request_emission=True,
                    )
                    matched=_policy(conn,tenant_id,probe,candidate_context)
                except DomainError:
                    matched=None
                if matched and matched.get("id")==candidate.get("id"):
                    policy=matched;break
        if not source_id:state="not_routable";detail="Nenhum pedido de serviço vinculado ao pagamento."
        elif not policy:state="no_policy";detail="Nenhuma política publicada habilita este gatilho."
        else:state="queued";detail="Gatilho apto para montagem."
        conn.execute("INSERT INTO fiscal_emission_trigger_runs(id,tenant_id,event_type,aggregate_id,source_type,source_id,trigger_type,routing_policy_id,state,payload_json,error_detail,assembly_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(run_id,tenant_id,event_type,aggregate_id,source_type,source_id or None,trigger,policy.get("id") if policy else None,state,_dump(payload),None if state=="queued" else detail,None,now,now))
    if state!="queued":return {"id":run_id,"state":state,"detail":detail}
    with store.transaction() as conn:
        pair=_profile_for_context(conn,tenant_id,policy["fiscal_context_id"])
    if not pair:
        store.execute("UPDATE fiscal_emission_trigger_runs SET state='not_configured',error_detail=?,updated_at=? WHERE tenant_id=? AND id=?",("Perfil fiscal correspondente ao contexto não configurado.",iso_now(),tenant_id,run_id));return {"id":run_id,"state":"not_configured"}
    try:
        input_data=FiscalDocumentAssemblyCreate(fiscal_context_id=policy["fiscal_context_id"],fiscal_profile_id=pair[0],source_type=source_type,source_id=source_id,occurred_on=date.today(),operation_type=policy["operation_type"],recipient_scope="individual",channel="service" if source_type=="service_order" else "retail",trigger_type=trigger,request_emission=True,metadata={"source_event":event_type,"aggregate_id":aggregate_id})
        _,assembled=_assemble(input_data,store,storage,tenant_id,"system-worker",correlation_id,f"trigger:{event_type}:{aggregate_id}");store.execute("UPDATE fiscal_emission_trigger_runs SET state=?,assembly_id=?,updated_at=? WHERE tenant_id=? AND id=?",(assembled["state"],assembled["assembly_id"],iso_now(),tenant_id,run_id));return {"id":run_id,"state":assembled["state"],"assembly_id":assembled["assembly_id"],"documents":assembled["documents"]}
    except Exception as exc:
        store.execute("UPDATE fiscal_emission_trigger_runs SET state='failed',error_detail=?,updated_at=? WHERE tenant_id=? AND id=?",(str(exc)[:2000],iso_now(),tenant_id,run_id));raise


def evaluate_trigger(data: FiscalEmissionTriggerEvaluate, request: Request, tenant_id: str) -> dict[str,Any]:
    return process_emission_trigger(request.app.state.data_router,tenant_id,data.event_type,data.aggregate_id,data.payload,request.state.correlation_id)



def apply_fiscal_financial_adjustment(conn, *, tenant_id: str, document_id: str, reason: str, now: str) -> dict[str, Any]:
    """Aplica a política financeira vinculada ao documento sem assumir cancelamento global."""
    links = conn.execute(
        "SELECT l.*,a.routing_policy_id FROM fiscal_document_financial_links l "
        "LEFT JOIN fiscal_document_links dl ON dl.tenant_id=l.tenant_id AND dl.fiscal_document_id=l.fiscal_document_id "
        "LEFT JOIN fiscal_document_assemblies a ON a.tenant_id=dl.tenant_id AND a.id=dl.assembly_id "
        "WHERE l.tenant_id=? AND l.fiscal_document_id=?",
        (tenant_id, document_id),
    ).fetchall()
    outcomes=[]
    for raw in links:
        link=dict(raw); mode="link_only"
        if link.get("routing_policy_id"):
            prow=conn.execute("SELECT settings_json FROM fiscal_document_routing_policies WHERE tenant_id=? AND id=?",(tenant_id,link["routing_policy_id"])).fetchone()
            if prow:
                routing_settings=_loads(prow["settings_json"],{})
                mode=str(routing_settings.get("financial_cancel_mode") or "link_only")
            else:
                routing_settings={}
        state="linked_no_automatic_adjustment"; ledger_id=None
        charge_id=link.get("charge_id")
        if mode=="cancel_unpaid_charge" and charge_id:
            charge=conn.execute("SELECT * FROM charges WHERE tenant_id=? AND id=?",(tenant_id,charge_id)).fetchone()
            if charge:
                charge=dict(charge)
                if Decimal(str(charge.get("paid_amount") or 0))>0:
                    state="refund_required"
                    add_outbox(conn,tenant_id=tenant_id,event_type="FiscalFinancialRefundRequired",aggregate_type="fiscal_document",aggregate_id=document_id,payload={"charge_id":charge_id,"reason":reason},correlation_id=f"fiscal-cancel:{document_id}")
                elif charge.get("state")!="cancelled":
                    conn.execute("UPDATE charges SET state='cancelled',outstanding_amount=0,cancelled_at=?,cancellation_reason=?,updated_at=? WHERE tenant_id=? AND id=?",(now,reason,now,tenant_id,charge_id))
                    conn.execute("UPDATE accounts_receivable SET state='cancelled',outstanding_amount=0,updated_at=? WHERE tenant_id=? AND charge_id=?",(now,tenant_id,charge_id))
                    if link.get("financial_contract_id"):
                        conn.execute("UPDATE installments SET state='cancelled',updated_at=? WHERE tenant_id=? AND financial_contract_id=? AND state IN ('open','partial')",(now,tenant_id,link["financial_contract_id"]))
                    original=conn.execute("SELECT id FROM ledger_entries WHERE tenant_id=? AND reference_type='charge' AND reference_id=? AND entry_type='charge' ORDER BY occurred_at LIMIT 1",(tenant_id,charge_id)).fetchone()
                    debit_account=str(routing_settings.get("fiscal_reversal_debit_account") or "service_revenue")
                    credit_account=str(routing_settings.get("fiscal_reversal_credit_account") or "accounts_receivable")
                    ledger_id=uuid7();conn.execute("INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,debit_account,credit_account,amount,occurred_at,reversal_of_id,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(ledger_id,tenant_id,"fiscal_charge_reversal","charge",charge_id,debit_account,credit_account,charge["total_amount"],now,original["id"] if original else None,"Ajuste compensatório vinculado ao cancelamento fiscal",now));state="reversed"
        conn.execute("UPDATE fiscal_document_financial_links SET adjustment_state=?,adjustment_ledger_entry_id=?,updated_at=? WHERE tenant_id=? AND id=?",(state,ledger_id,now,tenant_id,link["id"]))
        outcomes.append({"link_id":link["id"],"charge_id":charge_id,"mode":mode,"state":state,"ledger_entry_id":ledger_id})
    return {"document_id":document_id,"outcomes":outcomes}
