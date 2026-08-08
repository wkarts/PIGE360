from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Header, Request, Response, UploadFile
from pydantic import BaseModel, Field

from app.modules.operations.common import ADMIN_ROLES, require, tenant
from app.shared.application.idempotency import canonical_hash
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user

router=APIRouter(tags=["government-education"])
ROLES=ADMIN_ROLES|{"auditor"}

class ValidationInput(BaseModel):
    layout_id:str
    reference_period:str=Field(min_length=4,max_length=40)
    direction:Literal["import","export"]="export"
    records:list[dict[str,Any]]=Field(max_length=100000)

class TransmissionInput(BaseModel):
    connection_id:str|None=None

class RetryInput(BaseModel):
    reason:str=Field(min_length=3,max_length=2000)


def _layout(request:Request,tid:str,layout_id:str)->dict[str,Any]:
    row=request.state.store.fetch_one("SELECT * FROM government_export_layouts WHERE tenant_id=? AND id=? AND state='active'",(tid,layout_id))
    if not row:raise DomainError("GOV_LAYOUT_NOT_FOUND","Layout governamental ativo não localizado.",404)
    try:row["schema"]=json.loads(row.get("schema_json") or "{}")
    except (TypeError,json.JSONDecodeError):raise DomainError("GOV_LAYOUT_INVALID","Schema do layout está inválido.",409)
    return row


def _validate(layout:dict[str,Any],records:list[dict[str,Any]])->list[dict[str,Any]]:
    issues:list[dict[str,Any]]=[];fields=layout.get("schema",{}).get("fields",[])
    for idx,record in enumerate(records,1):
        for raw in fields:
            rule=raw if isinstance(raw,dict) else {"name":str(raw),"required":True}
            name=str(rule.get("name") or "").strip()
            if not name:continue
            value=record.get(name)
            empty=value is None or value==""
            if rule.get("required",True) and empty:
                issues.append({"row_number":idx,"field_code":name,"severity":"error","code":"REQUIRED","message":f"Campo obrigatório '{name}' não informado."});continue
            if empty:continue
            text=str(value)
            kind=str(rule.get("type") or "string")
            if kind=="integer":
                try:int(text)
                except ValueError:issues.append({"row_number":idx,"field_code":name,"severity":"error","code":"INVALID_INTEGER","message":f"'{name}' deve ser inteiro."})
            elif kind in {"decimal","number"}:
                try:float(text.replace(",","."))
                except ValueError:issues.append({"row_number":idx,"field_code":name,"severity":"error","code":"INVALID_NUMBER","message":f"'{name}' deve ser numérico."})
            if rule.get("max_length") and len(text)>int(rule["max_length"]):issues.append({"row_number":idx,"field_code":name,"severity":"error","code":"MAX_LENGTH","message":f"'{name}' excede {rule['max_length']} caracteres."})
            allowed=rule.get("enum") or []
            if allowed and value not in allowed and text not in {str(x) for x in allowed}:issues.append({"row_number":idx,"field_code":name,"severity":"error","code":"INVALID_ENUM","message":f"'{name}' possui valor fora do catálogo do layout."})
            pattern=rule.get("pattern")
            if pattern:
                try:matched=re.fullmatch(str(pattern),text) is not None
                except re.error:raise DomainError("GOV_LAYOUT_INVALID_PATTERN",f"Regex inválida no campo '{name}'.",409)
                if not matched:issues.append({"row_number":idx,"field_code":name,"severity":"error","code":"PATTERN_MISMATCH","message":f"'{name}' não atende ao formato do layout."})
    return issues


def _store_validation(request:Request,tid:str,layout_id:str,reference_period:str,direction:str,records:list[dict[str,Any]],issues:list[dict[str,Any]],actor:str,source_sha256:str|None=None)->dict[str,Any]:
    rid=uuid7();now=iso_now();errors=sum(1 for x in issues if x["severity"]=="error");warnings=sum(1 for x in issues if x["severity"]=="warning");state="invalid" if errors else "valid"
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO government_validation_runs(id,tenant_id,layout_id,reference_period,direction,state,record_count,error_count,warning_count,source_sha256,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,layout_id,reference_period,direction,state,len(records),errors,warnings,source_sha256,actor,now))
        for issue in issues:
            conn.execute("INSERT INTO government_validation_issues(id,tenant_id,run_id,row_number,field_code,severity,code,message,source_ref,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uuid7(),tid,rid,issue.get("row_number"),issue.get("field_code"),issue["severity"],issue["code"],issue["message"],issue.get("source_ref"),"open",now))
        add_audit(conn,tenant_id=tid,actor_id=actor,action="validate",aggregate_type="government_validation",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"state":state,"record_count":len(records),"error_count":errors,"warning_count":warnings})
    return {"id":rid,"state":state,"record_count":len(records),"error_count":errors,"warning_count":warnings}


def _decode_capabilities(row:dict[str,Any])->set[str]:
    try:return set(json.loads(row.get("capabilities_json") or "[]"))
    except (TypeError,json.JSONDecodeError):return set()


def _eligible_connection(request:Request,tid:str,requested:str|None)->dict[str,Any]|None:
    rows=request.state.store.fetch_all("SELECT id,provider,name,environment,capabilities_json,state,secret_reference FROM integration_connections WHERE tenant_id=? ORDER BY created_at",(tid,))
    for row in rows:
        if requested and row["id"]!=requested:continue
        if row["state"]!="configured" or not row.get("secret_reference"):continue
        caps=_decode_capabilities(row)
        if "government_submission" in caps or "*" in caps:return row
    if requested:
        exists=request.state.store.fetch_one("SELECT id FROM integration_connections WHERE tenant_id=? AND id=?",(tid,requested))
        if not exists:raise DomainError("INTEGRATION_CONNECTION_NOT_FOUND","Conexão de integração não localizada.",404)
    return None


def _transmission_event(conn,tid:str,transmission_id:str,event_type:str,actor:str,from_state:str|None,to_state:str|None,details:dict[str,Any]|None=None)->None:
    conn.execute("INSERT INTO government_transmission_events(id,tenant_id,transmission_id,event_type,from_state,to_state,details_json,actor_id,occurred_at) VALUES(?,?,?,?,?,?,?,?,?)",(uuid7(),tid,transmission_id,event_type,from_state,to_state,json.dumps(details or {},ensure_ascii=False),actor,iso_now()))


@router.post("/government-education/validations",status_code=201,operation_id="validate_government_records")
def validate_records(data:ValidationInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);tid=tenant(user);layout=_layout(request,tid,data.layout_id);issues=_validate(layout,data.records);result=_store_validation(request,tid,data.layout_id,data.reference_period,data.direction,data.records,issues,user.id)
    result["issues"]=issues[:500];return result

@router.get("/government-education/validations",operation_id="list_government_validations")
def list_validations(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);return {"items":request.state.store.fetch_all("SELECT * FROM government_validation_runs WHERE tenant_id=? ORDER BY created_at DESC",(tenant(user),))}

@router.get("/government-education/validations/{run_id}/issues",operation_id="list_government_validation_issues")
def list_validation_issues(run_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);tid=tenant(user);run=request.state.store.fetch_one("SELECT id FROM government_validation_runs WHERE tenant_id=? AND id=?",(tid,run_id))
    if not run:raise DomainError("GOV_VALIDATION_NOT_FOUND","Validação governamental não localizada.",404)
    return {"items":request.state.store.fetch_all("SELECT * FROM government_validation_issues WHERE tenant_id=? AND run_id=? ORDER BY row_number,field_code",(tid,run_id))}

@router.post("/government-education/imports",status_code=201,operation_id="import_government_file")
async def import_file(request:Request,layout_id:str,reference_period:str,file:UploadFile=File(...),user:CurrentUser=Depends(current_user)):
    require(user,ROLES);tid=tenant(user);layout=_layout(request,tid,layout_id);content=await file.read()
    if len(content)>25*1024*1024:raise DomainError("GOV_IMPORT_TOO_LARGE","Arquivo governamental excede 25 MB.",413)
    try:text=content.decode("utf-8-sig")
    except UnicodeDecodeError:raise DomainError("GOV_IMPORT_ENCODING_INVALID","Arquivo deve utilizar UTF-8.",422)
    try:records=[dict(row) for row in csv.DictReader(io.StringIO(text))]
    except csv.Error as exc:raise DomainError("GOV_IMPORT_CSV_INVALID",f"CSV inválido: {exc}",422)
    digest=hashlib.sha256(content).hexdigest();issues=_validate(layout,records);validation=_store_validation(request,tid,layout_id,reference_period,"import",records,issues,user.id,digest);iid=uuid7();key=f"imports/government/{layout['authority']}/{iid}.csv";stored=request.app.state.data_router.object_storage(tid).put_bytes(key,content,content_type="text/csv")
    if stored.sha256!=digest:raise DomainError("GOV_IMPORT_STORAGE_INTEGRITY_FAILED","Falha de integridade ao armazenar importação.",500)
    rejected=len({x.get("row_number") for x in issues if x["severity"]=="error" and x.get("row_number")});accepted=max(0,len(records)-rejected);state="rejected" if validation["error_count"] else "validated";now=iso_now();filename=Path(file.filename or "government-import.csv").name
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO government_imports(id,tenant_id,layout_id,validation_run_id,reference_period,original_filename,state,row_count,accepted_count,rejected_count,sha256,storage_key,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,tid,layout_id,validation["id"],reference_period,filename,state,len(records),accepted,rejected,digest,key,user.id,now,now))
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="import",aggregate_type="government_import",aggregate_id=iid,correlation_id=request.state.correlation_id,after={"state":state,"row_count":len(records),"accepted_count":accepted,"rejected_count":rejected,"sha256":digest})
    return {"id":iid,"state":state,"row_count":len(records),"accepted_count":accepted,"rejected_count":rejected,"sha256":digest,"validation_run_id":validation["id"]}

@router.get("/government-education/imports",operation_id="list_government_imports")
def list_imports(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);return {"items":request.state.store.fetch_all("SELECT id,layout_id,validation_run_id,reference_period,original_filename,state,row_count,accepted_count,rejected_count,sha256,created_at FROM government_imports WHERE tenant_id=? ORDER BY created_at DESC",(tenant(user),))}

@router.get("/government-education/imports/{import_id}/download",operation_id="download_government_import")
def download_import(import_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM government_imports WHERE tenant_id=? AND id=?",(tid,import_id))
    if not row:raise DomainError("GOV_IMPORT_NOT_FOUND","Importação governamental não localizada.",404)
    content=request.app.state.data_router.object_storage(tid).get_bytes(row["storage_key"])
    if hashlib.sha256(content).hexdigest()!=row["sha256"]:raise DomainError("GOV_IMPORT_INTEGRITY_FAILED","Integridade da importação falhou.",409)
    return Response(content=content,media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="{Path(row["original_filename"]).name}"',"X-Content-SHA256":row["sha256"]})

@router.get("/government-education/exports",operation_id="list_government_exports")
def list_exports(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);return {"items":request.state.store.fetch_all("SELECT ge.id,ge.layout_id,ge.reference_period,ge.state,ge.record_count,ge.sha256,ge.protocol,ge.created_at,gl.authority,gl.layout_code,gl.version AS layout_version FROM government_exports ge JOIN government_export_layouts gl ON gl.id=ge.layout_id WHERE ge.tenant_id=? ORDER BY ge.created_at DESC",(tenant(user),))}

@router.get("/government-education/exports/{export_id}/download",operation_id="download_government_export")
def download_export(export_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM government_exports WHERE tenant_id=? AND id=?",(tid,export_id))
    if not row:raise DomainError("GOV_EXPORT_NOT_FOUND","Exportação governamental não localizada.",404)
    content=request.app.state.data_router.object_storage(tid).get_bytes(row["storage_key"])
    if hashlib.sha256(content).hexdigest()!=row["sha256"]:raise DomainError("GOV_EXPORT_INTEGRITY_FAILED","Integridade da exportação falhou.",409)
    return Response(content=content,media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="government-{export_id}.csv"',"X-Content-SHA256":row["sha256"]})

@router.post("/government-education/exports/{export_id}/transmissions",status_code=201,operation_id="request_government_transmission")
def request_transmission(export_id:str,data:TransmissionInput,request:Request,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=160),user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);export=request.state.store.fetch_one("SELECT id,state,sha256 FROM government_exports WHERE tenant_id=? AND id=?",(tid,export_id))
    if not export:raise DomainError("GOV_EXPORT_NOT_FOUND","Exportação governamental não localizada.",404)
    existing=request.state.store.fetch_one("SELECT * FROM government_transmissions WHERE tenant_id=? AND idempotency_key=?",(tid,idempotency_key))
    fingerprint=canonical_hash({"export_id":export_id,"connection_id":data.connection_id})
    if existing:
        try:receipt=json.loads(existing.get("receipt_json") or "{}")
        except (TypeError,json.JSONDecodeError):receipt={}
        if receipt.get("request_hash") and receipt["request_hash"]!=fingerprint:raise DomainError("IDEMPOTENCY_CONFLICT","A mesma chave foi reutilizada para outra transmissão.",409)
        return {"id":existing["id"],"state":existing["state"],"connection_id":existing.get("connection_id"),"protocol":existing.get("protocol"),"replayed":True}
    connection=_eligible_connection(request,tid,data.connection_id);state="queued" if connection else "awaiting_configuration";environment=connection["environment"] if connection else "homologation";rid=uuid7();now=iso_now();receipt={"request_hash":fingerprint}
    with request.state.store.transaction() as conn:
        conn.execute("INSERT INTO government_transmissions(id,tenant_id,export_id,connection_id,environment,state,idempotency_key,attempts,receipt_json,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tid,export_id,connection["id"] if connection else None,environment,state,idempotency_key,0,json.dumps(receipt),user.id,now,now))
        _transmission_event(conn,tid,rid,"requested",user.id,None,state,{"export_sha256":export["sha256"],"connection_id":connection["id"] if connection else None})
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="request",aggregate_type="government_transmission",aggregate_id=rid,correlation_id=request.state.correlation_id,after={"state":state,"connection_id":connection["id"] if connection else None})
        if connection:add_outbox(conn,tenant_id=tid,event_type="GovernmentEducationTransmissionRequested",aggregate_type="government_transmission",aggregate_id=rid,payload={"export_id":export_id,"connection_id":connection["id"],"environment":environment},correlation_id=request.state.correlation_id)
    return {"id":rid,"state":state,"connection_id":connection["id"] if connection else None,"environment":environment,"protocol":None,"replayed":False}

@router.get("/government-education/transmissions",operation_id="list_government_transmissions")
def list_transmissions(request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ROLES);rows=request.state.store.fetch_all("SELECT id,export_id,connection_id,environment,state,attempts,protocol,provider_status,last_error,created_at,updated_at,submitted_at,completed_at FROM government_transmissions WHERE tenant_id=? ORDER BY created_at DESC",(tenant(user),));return {"items":rows}

@router.post("/government-education/transmissions/{transmission_id}/retry",operation_id="retry_government_transmission")
def retry_transmission(transmission_id:str,data:RetryInput,request:Request,user:CurrentUser=Depends(current_user)):
    require(user,ADMIN_ROLES);tid=tenant(user);row=request.state.store.fetch_one("SELECT * FROM government_transmissions WHERE tenant_id=? AND id=?",(tid,transmission_id))
    if not row:raise DomainError("GOV_TRANSMISSION_NOT_FOUND","Transmissão governamental não localizada.",404)
    if row["state"] in {"accepted","transmitting"}:raise DomainError("GOV_TRANSMISSION_NOT_RETRYABLE","Estado atual não permite reprocessamento.",409)
    connection=_eligible_connection(request,tid,row.get("connection_id"));state="queued" if connection else "awaiting_configuration";now=iso_now()
    with request.state.store.transaction() as conn:
        conn.execute("UPDATE government_transmissions SET connection_id=?,environment=?,state=?,attempts=attempts+1,last_error=NULL,updated_at=? WHERE tenant_id=? AND id=?",(connection["id"] if connection else None,connection["environment"] if connection else row["environment"],state,now,tid,transmission_id))
        _transmission_event(conn,tid,transmission_id,"retried",user.id,row["state"],state,{"reason":data.reason})
        add_audit(conn,tenant_id=tid,actor_id=user.id,action="retry",aggregate_type="government_transmission",aggregate_id=transmission_id,correlation_id=request.state.correlation_id,before={"state":row["state"]},after={"state":state},reason=data.reason)
        if connection:add_outbox(conn,tenant_id=tid,event_type="GovernmentEducationTransmissionRequested",aggregate_type="government_transmission",aggregate_id=transmission_id,payload={"export_id":row["export_id"],"connection_id":connection["id"],"environment":connection["environment"]},correlation_id=request.state.correlation_id)
    return {"id":transmission_id,"state":state,"connection_id":connection["id"] if connection else None,"protocol":row.get("protocol")}
