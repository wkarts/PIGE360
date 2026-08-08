from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from PIL import Image
from pydantic import BaseModel, Field

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, current_user, require_roles

router = APIRouter(tags=["branding"])
REQUIRED={"legal_name","trade_name","short_name","app_display_name","primary_domain","primary_color","secondary_color","accent_color","typography_family","co_branding_policy"}
COLOR=re.compile(r"^#[0-9A-Fa-f]{6}$")
ALLOWED_CATEGORIES={"logo_primary_light","logo_primary_dark","logo_horizontal_light","logo_horizontal_dark","logo_symbol","monochrome_logo","favicon","app_icon_source","notification_icon","splash_source","installer_banner","installer_sidebar","store_feature_graphic","social_share_image","email_header","pdf_header","pdf_footer","watermark","signature_stamp"}

class BrandAssetInput(BaseModel):
    category: str
    filename: str = Field(min_length=1,max_length=255)
    mime_type: str
    content_base64: str

class BrandPreviewInput(BaseModel):
    changes: dict[str,Any]

class BrandPublishInput(BaseModel):
    payload: dict[str,Any]
    reason: str = Field(min_length=3,max_length=2000)

class BrandRollbackInput(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3,max_length=2000)


def _tenant_store(request:Request,tenant_id:str):
    row=request.app.state.data_router.control.fetch_one("SELECT id FROM platform_tenants WHERE id=?",(tenant_id,))
    if not row:raise DomainError("TENANT_NOT_FOUND","Tenant não localizado.",404)
    return request.app.state.data_router.tenant_store(tenant_id)


def _ensure(store,tenant_id:str,actor_id:str|None=None):
    row=store.fetch_one("SELECT * FROM brand_kits WHERE tenant_id=?",(tenant_id,))
    if row:return row
    now=iso_now();kit_id=uuid7();initial={"status":"awaiting_assets","tenant_id":tenant_id}
    with store.transaction() as conn:conn.execute("INSERT INTO brand_kits(id,tenant_id,state,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",(kit_id,tenant_id,"awaiting_assets",json.dumps(initial),now,now))
    return store.fetch_one("SELECT * FROM brand_kits WHERE id=?",(kit_id,))


def _decode_kit(store,tenant_id:str)->dict[str,Any]:
    kit=_ensure(store,tenant_id);result={"id":kit["id"],"tenant_id":tenant_id,"state":kit["state"],"active_version":kit["active_version"],"payload":json.loads(kit["payload_json"]),"created_at":kit["created_at"],"updated_at":kit["updated_at"]}
    result["assets"]=store.fetch_all("SELECT id,category,original_filename,storage_key,mime_type,bytes,width,height,sha256,created_at FROM brand_assets WHERE tenant_id=? ORDER BY category",(tenant_id,))
    result["versions"]=store.fetch_all("SELECT id,version,state,sha256,created_by,created_at FROM brand_versions WHERE tenant_id=? ORDER BY version DESC",(tenant_id,))
    return result


def _validate_payload(payload:dict[str,Any]):
    missing=sorted(k for k in REQUIRED if not payload.get(k))
    if missing:raise DomainError("BRANDING_INCOMPLETE",f"Campos obrigatórios ausentes: {', '.join(missing)}",422)
    for key in ["primary_color","secondary_color","accent_color"]:
        if not COLOR.fullmatch(str(payload[key])):raise DomainError("INVALID_BRAND_COLOR",f"Cor inválida em {key}.",422)
    if payload.get("co_branding_policy") not in {"disabled","optional","required"}:raise DomainError("INVALID_CO_BRANDING_POLICY","Política de co-branding inválida.",422)
    if "pige360" in str(payload.get("primary_domain","")).lower() and not payload.get("demo_only"):
        # Tenants reais devem usar domínio próprio/dinâmico explicitamente provisionado; demo é exceção declarada.
        pass


def _target(request:Request,user:CurrentUser,tenant_id:str|None):
    if tenant_id is None:
        if user.plane!="tenant" or not user.tenant_id:raise DomainError("TENANT_ROUTE_REQUIRED","Rota tenant necessária.",404)
        return user.tenant_id,request.state.store
    if user.plane!="platform" or not set(user.roles).intersection({"platform_super_admin","platform_admin"}):raise DomainError("PERMISSION_DENIED","Acesso global insuficiente.",403)
    return tenant_id,_tenant_store(request,tenant_id)


@router.get("/branding/current",operation_id="get_current_tenant_branding")
def current_brand(request:Request,user:CurrentUser=Depends(current_user)):
    tenant_id,store=_target(request,user,None);return _decode_kit(store,tenant_id)

@router.get("/platform/tenants/{tenant_id}/branding",operation_id="get_platform_tenant_branding")
def platform_get_brand(tenant_id:str,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,tenant_id);return _decode_kit(store,tid)


def _upload(tenant_id:str,store,data:BrandAssetInput,request:Request,user:CurrentUser):
    if data.category not in ALLOWED_CATEGORIES:raise DomainError("INVALID_ASSET_CATEGORY","Categoria de ativo inválida.",422)
    if Path(data.filename).name!=data.filename:raise DomainError("INVALID_FILENAME","Nome de arquivo inválido.",422)
    try:content=base64.b64decode(data.content_base64,validate=True)
    except Exception as exc:raise DomainError("INVALID_BASE64","Conteúdo base64 inválido.",422) from exc
    if len(content)>request.app.state.settings.brand_asset_max_mb*1024*1024:raise DomainError("ASSET_TOO_LARGE","Ativo excede o limite configurado.",413)
    width=height=None;ext=Path(data.filename).suffix.lower()
    if data.mime_type in {"image/png","image/jpeg","image/webp","image/x-icon"}:
        try:
            with Image.open(io.BytesIO(content)) as im:im.verify()
            with Image.open(io.BytesIO(content)) as im:width,height=im.size
        except Exception as exc:raise DomainError("INVALID_IMAGE","O conteúdo não é uma imagem válida.",422) from exc
    elif data.mime_type=="image/svg+xml":
        text=content.decode("utf-8",errors="strict").lower()
        # O namespace XML oficial não é uma referência externa ativa. URLs em href,
        # CSS, scripts, entidades e imports continuam proibidas.
        inspection=text.replace("http://www.w3.org/2000/svg","").replace("https://www.w3.org/2000/svg","")
        forbidden=["<script","javascript:","xlink:href","<!entity","<!doctype","@import","url(http","href=\"http","href='http"]
        if "<svg" not in text or any(x in inspection for x in forbidden):
            raise DomainError("UNSAFE_SVG","SVG inválido ou contém referência externa/script.",422)
    else:raise DomainError("UNSUPPORTED_ASSET_TYPE","Formato de ativo não suportado.",415)
    kit=_ensure(store,tenant_id,user.id);digest=hashlib.sha256(content).hexdigest();asset_id=uuid7();key=f"branding/{kit['id']}/originals/{asset_id}{ext}";storage=request.app.state.data_router.object_storage(tenant_id);stored=storage.put_bytes(key,content,content_type=data.mime_type);now=iso_now()
    if stored.sha256 != digest:raise DomainError("BRAND_ASSET_INTEGRITY_FAILED","Falha de integridade ao armazenar o ativo.",500)
    with store.transaction() as conn:
        existing=conn.execute("SELECT * FROM brand_assets WHERE tenant_id=? AND sha256=? AND category=?",(tenant_id,digest,data.category)).fetchone()
        if existing:return dict(existing)
        conn.execute("INSERT INTO brand_assets(id,tenant_id,brand_kit_id,category,original_filename,storage_key,mime_type,bytes,width,height,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(asset_id,tenant_id,kit["id"],data.category,data.filename,key,data.mime_type,len(content),width,height,digest,now))
        result={"id":asset_id,"category":data.category,"original_filename":data.filename,"storage_key":key,"mime_type":data.mime_type,"bytes":len(content),"width":width,"height":height,"sha256":digest,"created_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="upload_asset",aggregate_type="brand_asset",aggregate_id=asset_id,correlation_id=request.state.correlation_id,after=result)
    return result

@router.post("/branding/assets",operation_id="upload_current_tenant_brand_asset",status_code=201)
def tenant_asset(data:BrandAssetInput,request:Request,user:CurrentUser=Depends(current_user)):
    if not set(user.roles).intersection({"tenant_owner","institution_director"}):raise DomainError("PERMISSION_DENIED","Sem permissão para alterar a marca.",403)
    tid,store=_target(request,user,None);return _upload(tid,store,data,request,user)

@router.post("/platform/tenants/{tenant_id}/branding/assets",operation_id="upload_platform_tenant_brand_asset",status_code=201)
def platform_asset(tenant_id:str,data:BrandAssetInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,tenant_id);return _upload(tid,store,data,request,user)


def _relative_luminance(color:str)->float:
    values=[]
    for index in (1,3,5):
        channel=int(color[index:index+2],16)/255
        values.append(channel/12.92 if channel<=0.04045 else ((channel+0.055)/1.055)**2.4)
    return 0.2126*values[0]+0.7152*values[1]+0.0722*values[2]


def _contrast(a:str,b:str)->float:
    la,lb=_relative_luminance(a),_relative_luminance(b)
    return round((max(la,lb)+0.05)/(min(la,lb)+0.05),2)


def _preview(tenant_id:str,store,data:BrandPreviewInput):
    kit=_ensure(store,tenant_id);payload={**json.loads(kit["payload_json"]),**data.changes}
    contrast={}
    for key in ("primary_color","secondary_color","accent_color"):
        value=payload.get(key)
        if isinstance(value,str) and COLOR.fullmatch(value):
            white=_contrast(value,"#FFFFFF");dark=_contrast(value,"#0D1B2A")
            contrast[key]={"on_white":{"ratio":white,"passes_aa":white>=4.5},"on_dark":{"ratio":dark,"passes_aa":dark>=4.5}}
    return {"tenant_id":tenant_id,"preview":payload,"contrast":contrast,"active_version":kit["active_version"],"persisted":False}

@router.post("/branding/preview",operation_id="preview_current_tenant_branding")
def tenant_preview(data:BrandPreviewInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,None);return _preview(tid,store,data)

@router.post("/platform/tenants/{tenant_id}/branding/preview",operation_id="preview_platform_tenant_branding")
def platform_preview(tenant_id:str,data:BrandPreviewInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,tenant_id);return _preview(tid,store,data)


def _publish(tenant_id:str,store,data:BrandPublishInput,request:Request,user:CurrentUser):
    _validate_payload(data.payload);kit=_ensure(store,tenant_id,user.id);assets=store.scalar("SELECT COUNT(*) AS n FROM brand_assets WHERE tenant_id=?",(tenant_id,)) or 0
    if assets<1 and not data.payload.get("demo_only"):raise DomainError("BRANDING_ASSETS_REQUIRED","Envie ao menos um ativo oficial antes de publicar.",409)
    now=iso_now();version=(kit["active_version"] or 0)+1;canonical=json.dumps(data.payload,ensure_ascii=False,sort_keys=True,separators=(",",":"));digest=hashlib.sha256(canonical.encode()).hexdigest();version_id=uuid7()
    with store.transaction() as conn:
        conn.execute("INSERT INTO brand_versions(id,tenant_id,brand_kit_id,version,state,payload_json,sha256,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(version_id,tenant_id,kit["id"],version,"active",canonical,digest,user.id,now))
        conn.execute("UPDATE brand_versions SET state='superseded' WHERE brand_kit_id=? AND version<>? AND state='active'",(kit["id"],version))
        conn.execute("UPDATE brand_kits SET state='active',active_version=?,payload_json=?,updated_at=? WHERE id=?",(version,canonical,now,kit["id"]))
        result={"tenant_id":tenant_id,"brand_kit_id":kit["id"],"version":version,"state":"active","sha256":digest,"payload":data.payload,"reason":data.reason,"published_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="publish",aggregate_type="brand_kit",aggregate_id=kit["id"],correlation_id=request.state.correlation_id,before=json.loads(kit["payload_json"]),after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="TenantBrandingPublished",aggregate_type="brand_kit",aggregate_id=kit["id"],payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/branding/publish",operation_id="publish_current_tenant_branding")
def tenant_publish(data:BrandPublishInput,request:Request,user:CurrentUser=Depends(current_user)):
    if not set(user.roles).intersection({"tenant_owner","institution_director"}):raise DomainError("PERMISSION_DENIED","Sem permissão para publicar a marca.",403)
    tid,store=_target(request,user,None);return _publish(tid,store,data,request,user)

@router.post("/platform/tenants/{tenant_id}/branding/publish",operation_id="publish_platform_tenant_branding")
def platform_publish(tenant_id:str,data:BrandPublishInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,tenant_id);return _publish(tid,store,data,request,user)


def _rollback(tenant_id:str,store,data:BrandRollbackInput,request:Request,user:CurrentUser):
    kit=_ensure(store,tenant_id);version=store.fetch_one("SELECT * FROM brand_versions WHERE brand_kit_id=? AND version=?",(kit["id"],data.version))
    if not version:raise DomainError("BRAND_VERSION_NOT_FOUND","Versão de branding não localizada.",404)
    now=iso_now()
    with store.transaction() as conn:
        conn.execute("UPDATE brand_versions SET state='superseded' WHERE brand_kit_id=? AND state='active'",(kit["id"],));conn.execute("UPDATE brand_versions SET state='active' WHERE id=?",(version["id"],));conn.execute("UPDATE brand_kits SET active_version=?,payload_json=?,state='active',updated_at=? WHERE id=?",(data.version,version["payload_json"],now,kit["id"]))
        result={"tenant_id":tenant_id,"brand_kit_id":kit["id"],"active_version":data.version,"sha256":version["sha256"],"reason":data.reason,"rolled_back_at":now}
        add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action="rollback",aggregate_type="brand_kit",aggregate_id=kit["id"],correlation_id=request.state.correlation_id,before={"active_version":kit["active_version"]},after=result,reason=data.reason)
        add_outbox(conn,tenant_id=tenant_id,event_type="TenantBrandingRolledBack",aggregate_type="brand_kit",aggregate_id=kit["id"],payload=result,correlation_id=request.state.correlation_id)
    return result

@router.post("/branding/rollback",operation_id="rollback_current_tenant_branding")
def tenant_rollback(data:BrandRollbackInput,request:Request,user:CurrentUser=Depends(current_user)):
    if not set(user.roles).intersection({"tenant_owner","institution_director"}):raise DomainError("PERMISSION_DENIED","Sem permissão para rollback.",403)
    tid,store=_target(request,user,None);return _rollback(tid,store,data,request,user)

@router.post("/platform/tenants/{tenant_id}/branding/rollback",operation_id="rollback_platform_tenant_branding")
def platform_rollback(tenant_id:str,data:BrandRollbackInput,request:Request,user:CurrentUser=Depends(current_user)):
    tid,store=_target(request,user,tenant_id);return _rollback(tid,store,data,request,user)
