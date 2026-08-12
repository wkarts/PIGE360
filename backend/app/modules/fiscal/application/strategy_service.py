from __future__ import annotations
import hashlib, json, sqlite3
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from fastapi import Request
from app.modules.fiscal.presentation.strategy_schemas import FiscalLegalSourceCreate,FiscalStrategyRuleCreate,FiscalRtcScheduleCreate
from app.shared.application.idempotency import get_idempotent,save_idempotent
from app.shared.domain.ids import iso_now,uuid7
from app.shared.events.records import add_audit,add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser
from app.modules.operations.common import dumps,loads

CENT=Decimal("0.01")
def _money(v): return Decimal(str(v or 0)).quantize(CENT,rounding=ROUND_HALF_UP)
def _audit(conn,tenant_id,user,request,action,atype,aid,after): add_audit(conn,tenant_id=tenant_id,actor_id=user.id,action=action,aggregate_type=atype,aggregate_id=aid,correlation_id=request.state.correlation_id,after=after)
def _event(conn,tenant_id,request,etype,atype,aid,payload): add_outbox(conn,tenant_id=tenant_id,event_type=etype,aggregate_type=atype,aggregate_id=aid,payload=payload,correlation_id=request.state.correlation_id)
def _context(conn,tenant_id,cid):
    row=conn.execute("SELECT id FROM fiscal_contexts WHERE tenant_id=? AND id=? AND state='active'",(tenant_id,cid)).fetchone()
    if not row: raise DomainError("FISCAL_CONTEXT_NOT_FOUND","Contexto fiscal não localizado.",404)
def _source(conn,tenant_id,sid):
    if sid and not conn.execute("SELECT id FROM fiscal_legal_source_artifacts WHERE tenant_id=? AND id=? AND state='published'",(tenant_id,sid)).fetchone(): raise DomainError("FISCAL_LEGAL_SOURCE_NOT_FOUND","Fonte normativa não localizada ou não publicada.",404)

def create_legal_source(data:FiscalLegalSourceCreate,request:Request,tenant_id:str,user:CurrentUser,key:str):
    body=data.model_dump(mode='json'); scope=f"fiscal-legal-source:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        sid=uuid7(); now=iso_now()
        conn.execute("INSERT INTO fiscal_legal_source_artifacts(id,tenant_id,kind,title,version_label,valid_from,valid_until,source_reference,source_sha256,metadata_json,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,tenant_id,data.kind,data.title,data.version_label,data.valid_from.isoformat(),data.valid_until.isoformat() if data.valid_until else None,data.source_reference,data.source_sha256,dumps(data.metadata),'published',user.id,now))
        result={'id':sid,**body,'status':'published','created_at':now}; _audit(conn,tenant_id,user,request,'create','fiscal_legal_source',sid,result); _event(conn,tenant_id,request,'FiscalLegalSourcePublished','fiscal_legal_source',sid,result); save_idempotent(conn,scope,key,body,201,result); return 201,result

def list_legal_sources(request,tenant_id):
    items=[]
    for r in request.state.store.fetch_all("SELECT * FROM fiscal_legal_source_artifacts WHERE tenant_id=? ORDER BY valid_from DESC,created_at DESC",(tenant_id,)):
        x=dict(r);x['metadata']=loads(x.pop('metadata_json','{}'),{});x['status']=x.get('state');items.append(x)
    return {'items':items}

def create_strategy_rule(data:FiscalStrategyRuleCreate,request:Request,tenant_id:str,user:CurrentUser,key:str):
    body=data.model_dump(mode='json');scope=f"fiscal-strategy:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        _context(conn,tenant_id,data.fiscal_context_id);_source(conn,tenant_id,data.legal_source_id)
        rid=uuid7();now=iso_now()
        conn.execute("INSERT INTO fiscal_strategy_rules(id,tenant_id,fiscal_context_id,establishment_code,strategy_type,operation_type,tax_regime,rtc_mode,origin_uf,destination_uf,valid_from,valid_until,priority,parameters_json,legal_source_id,state,version,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tenant_id,data.fiscal_context_id,data.establishment_code,data.strategy_type,data.operation_type,data.tax_regime,data.rtc_mode,data.origin_uf.upper() if data.origin_uf else None,data.destination_uf.upper() if data.destination_uf else None,data.valid_from.isoformat(),data.valid_until.isoformat() if data.valid_until else None,data.priority,dumps(data.parameters),data.legal_source_id,'published',1,user.id,now))
        result={'id':rid,**body,'status':'published','version':1};_audit(conn,tenant_id,user,request,'create','fiscal_strategy_rule',rid,result);_event(conn,tenant_id,request,'FiscalStrategyRulePublished','fiscal_strategy_rule',rid,result);save_idempotent(conn,scope,key,body,201,result);return 201,result

def list_strategy_rules(request,tenant_id,fiscal_context_id=None):
    sql="SELECT * FROM fiscal_strategy_rules WHERE tenant_id=?";p=[tenant_id]
    if fiscal_context_id:sql+=" AND fiscal_context_id=?";p.append(fiscal_context_id)
    sql+=" ORDER BY priority DESC,valid_from DESC"
    items=[]
    for r in request.state.store.fetch_all(sql,p):x=dict(r);x['parameters']=loads(x.pop('parameters_json','{}'),{});x['status']=x.get('state');items.append(x)
    return {'items':items}

def create_rtc_schedule(data:FiscalRtcScheduleCreate,request:Request,tenant_id:str,user:CurrentUser,key:str):
    body=data.model_dump(mode='json');scope=f"fiscal-rtc:create:{tenant_id}"
    with request.state.store.transaction() as conn:
        cached=get_idempotent(conn,scope,key,body)
        if cached:return cached
        _context(conn,tenant_id,data.fiscal_context_id);_source(conn,tenant_id,data.legal_source_id)
        overlap=conn.execute("SELECT id FROM fiscal_rtc_schedules WHERE tenant_id=? AND fiscal_context_id=? AND COALESCE(establishment_code,'')=COALESCE(?, '') AND tax_regime=? AND state='published' AND valid_from<=COALESCE(?, '9999-12-31') AND COALESCE(valid_until,'9999-12-31')>=? LIMIT 1",(tenant_id,data.fiscal_context_id,data.establishment_code,data.tax_regime,data.valid_until.isoformat() if data.valid_until else None,data.valid_from.isoformat())).fetchone()
        if overlap: raise DomainError('FISCAL_RTC_PERIOD_OVERLAP','Já existe cronograma RTC publicado sobreposto.',409)
        rid=uuid7();now=iso_now();conn.execute("INSERT INTO fiscal_rtc_schedules(id,tenant_id,fiscal_context_id,establishment_code,tax_regime,mode,valid_from,valid_until,legal_source_id,notes,state,version,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,tenant_id,data.fiscal_context_id,data.establishment_code,data.tax_regime,data.mode,data.valid_from.isoformat(),data.valid_until.isoformat() if data.valid_until else None,data.legal_source_id,data.notes,'published',1,user.id,now))
        result={'id':rid,**body,'status':'published','version':1};_audit(conn,tenant_id,user,request,'create','fiscal_rtc_schedule',rid,result);_event(conn,tenant_id,request,'FiscalRtcSchedulePublished','fiscal_rtc_schedule',rid,result);save_idempotent(conn,scope,key,body,201,result);return 201,result

def resolve_rtc(request,tenant_id,fiscal_context_id,occurred_on,establishment_code=None,tax_regime='any'):
    row=request.state.store.fetch_one("SELECT * FROM fiscal_rtc_schedules WHERE tenant_id=? AND fiscal_context_id=? AND state='published' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) AND (establishment_code=? OR establishment_code IS NULL) AND (tax_regime=? OR tax_regime='any') ORDER BY CASE WHEN establishment_code=? THEN 0 ELSE 1 END, CASE WHEN tax_regime=? THEN 0 ELSE 1 END, valid_from DESC LIMIT 1",(tenant_id,fiscal_context_id,occurred_on,occurred_on,establishment_code,tax_regime,establishment_code,tax_regime))
    if not row:return {'mode':'disabled','resolved':False}
    return {**dict(row),'status':row['state'],'resolved':True}

def resolve_strategies(conn,tenant_id,data,context):
    target=data.occurred_on.isoformat(); params=[tenant_id,data.fiscal_context_id,target,target,data.establishment_code,data.operation_type,context['tax_regime'],context['rtc_mode']]
    rows=conn.execute("SELECT * FROM fiscal_strategy_rules WHERE tenant_id=? AND fiscal_context_id=? AND state='published' AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) AND (establishment_code=? OR establishment_code IS NULL) AND (operation_type=? OR operation_type='any') AND (tax_regime=? OR tax_regime='any') AND (rtc_mode=? OR rtc_mode='any') ORDER BY priority DESC,valid_from DESC",params).fetchall()
    out=[]
    for row in rows:
        r=dict(row)
        if r['strategy_type']=='difal':
            if (getattr(data,'origin_uf',None) or '').upper()!=str(r.get('origin_uf') or '').upper() or (getattr(data,'destination_uf',None) or '').upper()!=str(r.get('destination_uf') or '').upper(): continue
            if not getattr(data,'final_consumer',False): continue
        r['parameters']=loads(r.pop('parameters_json','{}'),{});out.append(r)
    return out

def apply_strategies(strategies,taxes,tax_total):
    adjustments=[]; total=Decimal(str(tax_total))
    for r in strategies:
        p=r['parameters'];typ=r['strategy_type'];amount=Decimal('0');effect='informational'
        if typ in {'withholding','difal'}:
            base=Decimal(str(p.get('base',p.get('operation_base',0)) or 0));rate=Decimal(str(p.get('rate_pct',0) or 0));amount=_money(base*rate/Decimal('100'));total+=amount;effect='add'
        elif typ=='presumed_credit':
            base=Decimal(str(p.get('base',p.get('operation_base',0)) or 0));rate=Decimal(str(p.get('rate_pct',0) or 0));amount=_money(base*rate/Decimal('100'));total-=amount;effect='credit'
        elif typ in {'return','reversal'}:
            amount=_money(Decimal(str(p.get('amount',0) or 0)));total-=amount;effect='reverse'
        elif typ in {'adjustment','import','specific_regime'}:
            amount=_money(Decimal(str(p.get('amount',0) or 0)));total+=amount;effect='add'
        adjustments.append({'id':r['id'],'strategy_type':typ,'amount':str(amount),'effect':effect,'legal_source_id':r.get('legal_source_id')})
    return adjustments,max(total,Decimal('0'))
