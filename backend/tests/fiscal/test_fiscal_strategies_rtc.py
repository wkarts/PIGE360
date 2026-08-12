from __future__ import annotations

SHA = "a" * 64

def _context(local_env):
    c=local_env.client.post('/api/v1/fiscal/contexts',headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-context-001'}),json={'code':'MATRIZ-STRAT','establishment_name':'Matriz Estratégias','cnpj':'12.345.678/0001-95'})
    assert c.status_code==201,c.text; c=c.json()
    v=local_env.client.post(f"/api/v1/fiscal/contexts/{c['id']}/versions",headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-context-v1'}),json={'tax_regime':'simples_nacional','uf':'BA','municipality_code':'2927408','valid_from':'2026-01-01','environment':'homologation','rtc_mode':'optional_emit','ruleset_version':'STRAT-1','scopes':[{'operation_type':'sale','item_kind':'product','recipient_scope':'company','document_type':'NF-e'}],'expected_context_version':1})
    assert v.status_code==201,v.text
    p=local_env.client.post(f"/api/v1/fiscal/contexts/{c['id']}/versions/{v.json()['id']}/publish",headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-context-pub'}),json={'expected_context_version':2,'expected_version':1,'reason':'Publicação de teste'})
    assert p.status_code==200,p.text
    r=local_env.client.post('/api/v1/fiscal/tax-rule-sets',headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-base-rule'}),json={'fiscal_context_id':c['id'],'code':'BASE','name':'Base','establishment_code':'MATRIZ-STRAT','operation_type':'sale','item_kind':'product','tax_regime':'simples_nacional','rtc_mode':'optional_emit','priority':100})
    assert r.status_code==201,r.text
    rv=local_env.client.post(f"/api/v1/fiscal/tax-rule-sets/{r.json()['id']}/versions",headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-base-v1'}),json={'version_label':'1','valid_from':'2026-01-01','source_name':'fixture','components':[{'tax':'ICMS','rate_pct':'18'}],'expected_rule_set_version':1})
    assert rv.status_code==201,rv.text
    pub=local_env.client.post(f"/api/v1/fiscal/tax-rule-sets/{r.json()['id']}/versions/{rv.json()['id']}/publish",headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-base-pub'}),json={'expected_rule_set_version':2,'expected_version':1,'reason':'Publicação'})
    assert pub.status_code==200,pub.text
    return c

def test_strategies_and_rtc_are_versioned_resolved_and_applied(local_env):
    c=_context(local_env)
    src=local_env.client.post('/api/v1/fiscal/legal-sources',headers=local_env.alpha_headers(**{'Idempotency-Key':'legal-src-001'}),json={'kind':'technical_note','title':'Nota técnica fixture','version_label':'2026.1','valid_from':'2026-01-01','source_reference':'fixture://nota','source_sha256':SHA})
    assert src.status_code==201,src.text; sid=src.json()['id']
    for key,payload in [
        ('withhold',{'strategy_type':'withholding','parameters':{'rate_pct':'2'}}),
        ('credit',{'strategy_type':'presumed_credit','parameters':{'rate_pct':'1'}}),
        ('difal',{'strategy_type':'difal','origin_uf':'BA','destination_uf':'SP','parameters':{'rate_pct':'3'}}),
    ]:
        body={'fiscal_context_id':c['id'],'establishment_code':'MATRIZ-STRAT','operation_type':'sale','tax_regime':'simples_nacional','rtc_mode':'optional_emit','valid_from':'2026-01-01','priority':200,'legal_source_id':sid,**payload}
        resp=local_env.client.post('/api/v1/fiscal/strategy-rules',headers=local_env.alpha_headers(**{'Idempotency-Key':f'strategy-{key}-001'}),json=body)
        assert resp.status_code==201,resp.text
    for key,mode,start,end in [('rtc26','optional_emit','2026-01-01','2026-12-31'),('rtc27','required_emit','2027-01-01',None)]:
        body={'fiscal_context_id':c['id'],'establishment_code':'MATRIZ-STRAT','tax_regime':'simples_nacional','mode':mode,'valid_from':start,'valid_until':end,'legal_source_id':sid}
        resp=local_env.client.post('/api/v1/fiscal/rtc-schedules',headers=local_env.alpha_headers(**{'Idempotency-Key':key+'-001'}),json=body); assert resp.status_code==201,resp.text
    r26=local_env.client.get(f"/api/v1/fiscal/rtc/resolve?fiscal_context_id={c['id']}&occurred_on=2026-08-10&establishment_code=MATRIZ-STRAT&tax_regime=simples_nacional",headers=local_env.alpha_headers())
    r27=local_env.client.get(f"/api/v1/fiscal/rtc/resolve?fiscal_context_id={c['id']}&occurred_on=2027-02-01&establishment_code=MATRIZ-STRAT&tax_regime=simples_nacional",headers=local_env.alpha_headers())
    assert r26.status_code==200 and r26.json()['mode']=='optional_emit'; assert r27.status_code==200 and r27.json()['mode']=='required_emit'
    calc=local_env.client.post('/api/v1/fiscal/tax-calculations/simulate',headers=local_env.alpha_headers(**{'Idempotency-Key':'strat-calc-001'}),json={'fiscal_context_id':c['id'],'establishment_code':'MATRIZ-STRAT','operation_type':'sale','item_kind':'product','occurred_on':'2026-08-10','amount':'100.00','origin_uf':'BA','destination_uf':'SP','final_consumer':True,'recipient_scope':'company','document_type':'NF-e'})
    assert calc.status_code==201,calc.text; body=calc.json(); assert body['tax_total']=='18.00'; assert body['net_tax_total']=='22.00'; assert {x['strategy_type'] for x in body['strategy_adjustments']}=={'withholding','presumed_credit','difal'}
    store=local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant['id']); assert store.scalar("SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND aggregate_type='fiscal_strategy_rule'",(local_env.alpha_tenant['id'],))==3
    beta=local_env.client.get('/api/v1/fiscal/strategy-rules',headers=local_env.beta_headers()); assert beta.status_code==200 and beta.json()['items']==[]
