from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.modules.fiscal.application.document_routing_service import _build_xml, process_emission_trigger
from app.modules.fiscal.presentation.document_routing_schemas import FiscalDocumentAssemblyCreate, FiscalAssemblyItem, FiscalRoutingRecipient
from app.shared.events.handlers import build_domain_event_handlers

ROOT=Path(__file__).resolve().parents[1]/"fixtures"/"fiscal-routing"


def _context(local_env):
    client=local_env.client
    c=client.post('/api/v1/fiscal/contexts',headers=local_env.alpha_headers(**{'Idempotency-Key':'routing-context-001'}),json={'code':'MATRIZ-BA','establishment_name':'Matriz BA','cnpj':'12.345.678/0001-95'})
    assert c.status_code==201,c.text
    v=client.post(f"/api/v1/fiscal/contexts/{c.json()['id']}/versions",headers=local_env.alpha_headers(**{'Idempotency-Key':'routing-context-version-001'}),json={'tax_regime':'simples_nacional','uf':'BA','municipality_code':'2927408','valid_from':'2026-01-01','environment':'homologation','rtc_mode':'optional_emit','layout_version':'fixture','schema_version':'routing-fixture','ruleset_version':'routing-v1','configuration':{},'scopes':[{'operation_type':'sale','item_kind':'any','recipient_scope':'any','document_type':'any'}],'expected_context_version':1})
    assert v.status_code==201,v.text
    p=client.post(f"/api/v1/fiscal/contexts/{c.json()['id']}/versions/{v.json()['id']}/publish",headers=local_env.alpha_headers(**{'Idempotency-Key':'routing-context-publish-001'}),json={'expected_context_version':2,'expected_version':1,'reason':'Publicação para roteamento fiscal local.'})
    assert p.status_code==200,p.text
    profile=client.post('/api/v1/fiscal/profiles',headers=local_env.alpha_headers(),json={'establishment_name':'Matriz BA','cnpj':'12.345.678/0001-95','tax_regime':'simples_nacional','uf':'BA','municipality_code':'2927408','environment':'homologation'})
    assert profile.status_code==201,profile.text
    return c.json(),profile.json()


def _xsd(root):
    return (ROOT/'generic.xsd.tpl').read_text().replace('__ROOT__',root)


def _schemas(local_env):
    out={}
    for document_type,root in [('NF-e','NFeDoc'),('NFC-e','NFCeDoc'),('NFS-e','NFSeDoc')]:
        r=local_env.client.post('/api/v1/fiscal/document-schemas',headers=local_env.alpha_headers(**{'Idempotency-Key':f'schema-{root}-001'}),json={'document_type':document_type,'schema_code':f'LOCAL-{root}','version_label':'1.0-test','valid_from':'2026-01-01','root_element':root,'xsd_text':_xsd(root),'source_reference':'fixture://local-xsd','metadata':{'fixture':True}})
        assert r.status_code==201,r.text
        pub=local_env.client.post(f"/api/v1/fiscal/document-schemas/{r.json()['id']}/publish",headers=local_env.alpha_headers(),json={'reason':'Publicação local para golden tests.','expected_version':1})
        assert pub.status_code==200,pub.text
        out[document_type]=r.json()['id']
    return out


def test_golden_xml_builders_are_deterministic():
    context={'context':{'cnpj':'12345678000195'},'version':{'uf':'BA'}}
    cases=[('NF-e','NFeDoc','company','Empresa Teste','12345678000195','product','P1','Produto','100.00','golden-nfe.xml'),('NFC-e','NFCeDoc','individual','Consumidor','12345678909','product','P1','Produto','100.00','golden-nfce.xml'),('NFS-e','NFSeDoc','individual','Aluno','12345678909','service','S1','Curso','200.00','golden-nfse.xml')]
    for doc,root,scope,name,document,kind,code,desc,amount,golden in cases:
        data=FiscalDocumentAssemblyCreate(fiscal_context_id='ctx',fiscal_profile_id='profile',source_type='manual',source_id='order-golden',occurred_on=date(2026,8,11),operation_type='sale',recipient_scope=scope,channel='web',recipient=FiscalRoutingRecipient(name=name,document=document),items=[])
        item={'line_id':'1','item_kind':kind,'item_id':None,'code':code,'description':desc,'quantity':Decimal('1'),'unit_price':Decimal(amount),'discount':Decimal('0'),'total_amount':Decimal(amount),'classification':{}}
        xml=_build_xml(doc,{'root_element':root,'namespace_uri':None},'assembly-golden',data,context,[item]).decode()
        assert xml.strip()==(ROOT/golden).read_text().strip()


def test_mixed_order_routes_two_documents_with_snapshots_and_idempotency(local_env):
    context,profile=_context(local_env);_schemas(local_env)
    policy=local_env.client.post('/api/v1/fiscal/routing-policies',headers=local_env.alpha_headers(**{'Idempotency-Key':'routing-policy-001'}),json={'fiscal_context_id':context['id'],'code':'VENDA-MISTA','name':'Venda mista local','operation_type':'sale','recipient_scope':'any','channel_scope':'any','service_document_type':'NFS-e','trigger_types':['manual','sale_completed'],'valid_from':'2026-01-01','priority':100,'settings':{}})
    assert policy.status_code==201,policy.text
    pub=local_env.client.post(f"/api/v1/fiscal/routing-policies/{policy.json()['id']}/publish",headers=local_env.alpha_headers(),json={'reason':'Ativação da política local.','expected_version':1});assert pub.status_code==200,pub.text
    body={'fiscal_context_id':context['id'],'fiscal_profile_id':profile['id'],'source_type':'manual','source_id':'pedido-misto-001','occurred_on':'2026-08-11','operation_type':'sale','recipient_scope':'individual','channel':'pos','destination_uf':'BA','trigger_type':'manual','recipient':{'name':'Responsável Teste','document':'12345678909','uf':'BA'},'request_emission':True,'items':[{'line_id':'p1','item_kind':'product','code':'UNIFORME','description':'Uniforme','quantity':'1','unit_price':'100.00','discount':'0','total_amount':'100.00','classification':{'ncm':'61091000'}},{'line_id':'s1','item_kind':'service','code':'CURSO','description':'Curso extracurricular','quantity':'1','unit_price':'200.00','discount':'0','total_amount':'200.00','classification':{'nbs':'1.0901'}}]}
    headers=local_env.alpha_headers(**{'Idempotency-Key':'assembly-mixed-001'})
    result=local_env.client.post('/api/v1/fiscal/document-assemblies',headers=headers,json=body);assert result.status_code==201,result.text
    payload=result.json();assert payload['state']=='emission_requested';assert payload['routing']['mixed'] is True;assert {x['document_type'] for x in payload['builds']}=={'NFC-e','NFS-e'};assert {x['relationship'] for x in payload['documents']}=={'product_part','service_part'};assert len(payload['input_sha256'])==64 and len(payload['output_sha256'])==64
    for build in payload['builds']:
        assert build['validation_state']=='valid' and len(build['xml_sha256'])==64
    replay=local_env.client.post('/api/v1/fiscal/document-assemblies',headers=headers,json=body);assert replay.status_code==201 and replay.json()['assembly_id']==payload['assembly_id']
    detail=local_env.client.get(f"/api/v1/fiscal/document-assemblies/{payload['assembly_id']}",headers=local_env.alpha_headers());assert detail.status_code==200;assert len(detail.json()['links'])==2
    beta=local_env.client.get(f"/api/v1/fiscal/document-assemblies/{payload['assembly_id']}",headers=local_env.beta_headers());assert beta.status_code==404


def test_sale_completed_trigger_is_idempotent_and_routes_existing_sale(local_env):
    context,profile=_context(local_env);_schemas(local_env)
    policy=local_env.client.post('/api/v1/fiscal/routing-policies',headers=local_env.alpha_headers(**{'Idempotency-Key':'routing-policy-trigger-001'}),json={'fiscal_context_id':context['id'],'code':'SALE-EVENT','name':'Evento venda concluída','operation_type':'sale','recipient_scope':'any','channel_scope':'any','trigger_types':['sale_completed'],'valid_from':'2026-01-01','priority':10,'settings':{}});assert policy.status_code==201
    local_env.client.post(f"/api/v1/fiscal/routing-policies/{policy.json()['id']}/publish",headers=local_env.alpha_headers(),json={'reason':'Ativação para evento de venda.','expected_version':1})
    store=local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant['id']);now='2026-08-11T00:00:00+00:00'
    with store.transaction() as conn:
        product_id='prod-route-trigger';sale_id='sale-route-trigger';conn.execute("INSERT INTO products(id,tenant_id,sku,name,unit,cost,sale_price,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(product_id,local_env.alpha_tenant['id'],'ROUTE-1','Produto Trigger','UN','50','100','active',now,now));conn.execute("INSERT INTO sales(id,tenant_id,channel,subtotal,discount,total_amount,state,fiscal_status,idempotency_key,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(sale_id,local_env.alpha_tenant['id'],'pos','100','0','100','completed','pending','sale-route-trigger-key','test',now));conn.execute("INSERT INTO sale_items(id,tenant_id,sale_id,product_id,quantity,unit_price,discount,total_amount,created_at) VALUES(?,?,?,?,?,?,?,?,?)",('sale-item-route-trigger',local_env.alpha_tenant['id'],sale_id,product_id,'1','100','0','100',now))
    router=local_env.client.app.state.data_router
    first=process_emission_trigger(router,local_env.alpha_tenant['id'],'SaleCompleted','sale-route-trigger',{'id':'sale-route-trigger'},'corr-route-trigger');assert first['state']=='emission_requested' and first['documents']
    second=process_emission_trigger(router,local_env.alpha_tenant['id'],'SaleCompleted','sale-route-trigger',{'id':'sale-route-trigger'},'corr-route-trigger');assert second['idempotent'] is True and second['id']==first['id']


def _financial_service_order(local_env, *, suffix: str, paid: bool = False):
    context, profile = _context(local_env)
    _schemas(local_env)
    policy = local_env.client.post(
        '/api/v1/fiscal/routing-policies',
        headers=local_env.alpha_headers(**{'Idempotency-Key': f'routing-policy-fin-{suffix}'}),
        json={
            'fiscal_context_id': context['id'],
            'code': f'FIN-CANCEL-{suffix}',
            'name': f'Cancelamento fiscal financeiro {suffix}',
            'operation_type': 'service',
            'recipient_scope': 'any',
            'channel_scope': 'any',
            'service_document_type': 'NFS-e',
            'trigger_types': ['manual', 'payment', 'competence', 'billing', 'service_order_confirmed'],
            'valid_from': '2026-01-01',
            'priority': 50,
            'settings': {'financial_cancel_mode': 'cancel_unpaid_charge', 'tax_regimes': ['simples_nacional'], 'municipality_codes': ['2927408'], 'require_financial_contract': True},
        },
    )
    assert policy.status_code == 201, policy.text
    published = local_env.client.post(
        f"/api/v1/fiscal/routing-policies/{policy.json()['id']}/publish",
        headers=local_env.alpha_headers(),
        json={'reason': 'Política fiscal financeira para teste.', 'expected_version': 1},
    )
    assert published.status_code == 200, published.text

    tenant_id = local_env.alpha_tenant['id']
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    now = '2026-08-11T03:30:00+00:00'
    ids = {
        'contract': f'contract-fin-{suffix}',
        'installment': f'installment-fin-{suffix}',
        'charge': f'charge-fin-{suffix}',
        'receivable': f'receivable-fin-{suffix}',
        'service': f'service-fin-{suffix}',
        'order': f'order-fin-{suffix}',
        'item': f'order-item-fin-{suffix}',
        'ledger': f'ledger-fin-{suffix}',
        'payment': f'payment-fin-{suffix}',
        'allocation': f'allocation-fin-{suffix}',
    }
    paid_amount = '100.00' if paid else '0.00'
    outstanding = '0.00' if paid else '100.00'
    charge_state = 'paid' if paid else 'open'
    installment_state = 'paid' if paid else 'open'
    receivable_state = 'paid' if paid else 'open'
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO financial_contracts(id,tenant_id,description,total_amount,currency,competence_rule,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ids['contract'], tenant_id, 'Contrato de serviço fiscal', '100.00', 'BRL', 'billing', 'active', 1, now, now),
        )
        conn.execute(
            "INSERT INTO installments(id,tenant_id,financial_contract_id,sequence,competence,due_date,original_amount,discount_amount,penalty_amount,interest_amount,paid_amount,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ids['installment'], tenant_id, ids['contract'], 1, '2026-08', '2026-08-20', '100.00', '0', '0', '0', paid_amount, installment_state, now, now),
        )
        conn.execute(
            "INSERT INTO charges(id,tenant_id,charge_number,financial_contract_id,origin_type,origin_id,currency,total_amount,paid_amount,refunded_amount,outstanding_amount,due_date,state,generated_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ids['charge'], tenant_id, f'CH-{suffix}', ids['contract'], 'service_order', ids['order'], 'BRL', '100.00', paid_amount, '0', outstanding, '2026-08-20', charge_state, now, now, now),
        )
        conn.execute(
            "INSERT INTO accounts_receivable(id,tenant_id,receivable_number,installment_id,charge_id,amount,paid_amount,refunded_amount,outstanding_amount,due_date,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ids['receivable'], tenant_id, f'AR-{suffix}', ids['installment'], ids['charge'], '100.00', paid_amount, '0', outstanding, '2026-08-20', receivable_state, now, now),
        )
        conn.execute(
            "INSERT INTO services(id,tenant_id,code,name,price,state,taxable,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (ids['service'], tenant_id, f'SVC-{suffix}', 'Serviço fiscal', '100.00', 'active', 1, now, now),
        )
        conn.execute(
            "INSERT INTO service_orders(id,tenant_id,state,total_amount,financial_contract_id,order_number,subtotal,discount_amount,due_date,installment_count,charge_id,fiscal_status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ids['order'], tenant_id, 'confirmed', '100.00', ids['contract'], f'SO-{suffix}', '100.00', '0', '2026-08-20', 1, ids['charge'], 'pending', 1, now, now),
        )
        conn.execute(
            "INSERT INTO service_order_items(id,tenant_id,service_order_id,service_id,quantity,unit_price,total_amount,discount_amount,fiscal_profile_snapshot_json,execution_status,executed_quantity,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (ids['item'], tenant_id, ids['order'], ids['service'], '1', '100.00', '100.00', '0', '{}', 'pending', '0', now),
        )
        conn.execute(
            "INSERT INTO ledger_entries(id,tenant_id,entry_type,reference_type,reference_id,debit_account,credit_account,amount,occurred_at,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (ids['ledger'], tenant_id, 'charge', 'charge', ids['charge'], 'accounts_receivable', 'service_revenue', '100.00', now, 'Cobrança original', now),
        )
        if paid:
            conn.execute(
                "INSERT INTO payments(id,tenant_id,method,amount,paid_at,external_reference,state,idempotency_key,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (ids['payment'], tenant_id, 'pix', '100.00', now, f'E2E-{suffix}', 'confirmed', f'payment-key-{suffix}', '{}', now),
            )
            conn.execute(
                "INSERT INTO payment_allocations(id,tenant_id,payment_id,installment_id,amount,created_at) VALUES(?,?,?,?,?,?)",
                (ids['allocation'], tenant_id, ids['payment'], ids['installment'], '100.00', now),
            )
    return context, profile, policy.json(), ids


def _assemble_financial_service_order(local_env, *, suffix: str, paid: bool = False):
    context, profile, policy, ids = _financial_service_order(local_env, suffix=suffix, paid=paid)
    response = local_env.client.post(
        '/api/v1/fiscal/document-assemblies',
        headers=local_env.alpha_headers(**{'Idempotency-Key': f'assembly-fin-{suffix}'}),
        json={
            'fiscal_context_id': context['id'],
            'fiscal_profile_id': profile['id'],
            'source_type': 'service_order',
            'source_id': ids['order'],
            'occurred_on': '2026-08-11',
            'operation_type': 'service',
            'recipient_scope': 'individual',
            'channel': 'service',
            'trigger_type': 'manual',
            'recipient': {'name': 'Responsável Teste', 'document': '12345678909', 'uf': 'BA'},
            'request_emission': True,
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload['state'] == 'emission_requested'
    assert len(payload['documents']) == 1
    return payload['documents'][0]['id'], ids, policy


def test_fiscal_cancel_reverses_only_unpaid_charge_with_compensating_ledger(local_env):
    document_id, ids, _ = _assemble_financial_service_order(local_env, suffix='unpaid', paid=False)
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant['id'])
    link = store.fetch_one(
        "SELECT * FROM fiscal_document_financial_links WHERE tenant_id=? AND fiscal_document_id=?",
        (local_env.alpha_tenant['id'], document_id),
    )
    assert link and link['charge_id'] == ids['charge'] and link['financial_contract_id'] == ids['contract']

    cancelled = local_env.client.post(
        f'/api/v1/fiscal/documents/{document_id}/cancel',
        headers=local_env.alpha_headers(),
        json={'reason': 'Cancelamento fiscal com ajuste financeiro controlado.'},
    )
    assert cancelled.status_code == 200, cancelled.text
    outcome = cancelled.json()['financial_adjustment']['outcomes'][0]
    assert outcome['mode'] == 'cancel_unpaid_charge'
    assert outcome['state'] == 'reversed'
    assert outcome['ledger_entry_id']

    charge = store.fetch_one("SELECT state,outstanding_amount FROM charges WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], ids['charge']))
    receivable = store.fetch_one("SELECT state,outstanding_amount FROM accounts_receivable WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], ids['receivable']))
    installment = store.fetch_one("SELECT state FROM installments WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], ids['installment']))
    reversal = store.fetch_one("SELECT * FROM ledger_entries WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], outcome['ledger_entry_id']))
    link = store.fetch_one("SELECT adjustment_state,adjustment_ledger_entry_id FROM fiscal_document_financial_links WHERE tenant_id=? AND fiscal_document_id=?", (local_env.alpha_tenant['id'], document_id))
    assert charge['state'] == 'cancelled' and Decimal(str(charge['outstanding_amount'])) == Decimal('0')
    assert receivable['state'] == 'cancelled' and Decimal(str(receivable['outstanding_amount'])) == Decimal('0')
    assert installment['state'] == 'cancelled'
    assert reversal['entry_type'] == 'fiscal_charge_reversal'
    assert reversal['reversal_of_id'] == ids['ledger']
    assert link['adjustment_state'] == 'reversed' and link['adjustment_ledger_entry_id'] == outcome['ledger_entry_id']
    decision_row = store.fetch_one(
        "SELECT a.routing_decision_json FROM fiscal_document_links dl JOIN fiscal_document_assemblies a ON a.tenant_id=dl.tenant_id AND a.id=dl.assembly_id WHERE dl.tenant_id=? AND dl.fiscal_document_id=?",
        (local_env.alpha_tenant['id'], document_id),
    )
    dimensions = __import__('json').loads(decision_row['routing_decision_json'])['dimensions']
    assert dimensions['tax_regime'] == 'simples_nacional'
    assert dimensions['municipality_code'] == '2927408'
    assert dimensions['financial_contract_id'] == ids['contract']

    replay = local_env.client.post(
        f'/api/v1/fiscal/documents/{document_id}/cancel',
        headers=local_env.alpha_headers(),
        json={'reason': 'Repetição idempotente do cancelamento.'},
    )
    assert replay.status_code == 200 and replay.json()['idempotent'] is True
    reversals = store.fetch_all("SELECT id FROM ledger_entries WHERE tenant_id=? AND entry_type='fiscal_charge_reversal' AND reference_id=?", (local_env.alpha_tenant['id'], ids['charge']))
    assert len(reversals) == 1


def test_fiscal_cancel_paid_charge_requires_refund_without_erasing_payment(local_env):
    document_id, ids, _ = _assemble_financial_service_order(local_env, suffix='paid', paid=True)
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant['id'])
    cancelled = local_env.client.post(
        f'/api/v1/fiscal/documents/{document_id}/cancel',
        headers=local_env.alpha_headers(),
        json={'reason': 'Cancelamento fiscal após pagamento confirmado.'},
    )
    assert cancelled.status_code == 200, cancelled.text
    outcome = cancelled.json()['financial_adjustment']['outcomes'][0]
    assert outcome['state'] == 'refund_required'
    assert outcome['ledger_entry_id'] is None
    charge = store.fetch_one("SELECT state,paid_amount FROM charges WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], ids['charge']))
    payment = store.fetch_one("SELECT state,amount FROM payments WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], ids['payment']))
    link = store.fetch_one("SELECT adjustment_state FROM fiscal_document_financial_links WHERE tenant_id=? AND fiscal_document_id=?", (local_env.alpha_tenant['id'], document_id))
    refund_event = store.fetch_one("SELECT event_type FROM outbox_events WHERE tenant_id=? AND event_type='FiscalFinancialRefundRequired' AND aggregate_id=?", (local_env.alpha_tenant['id'], document_id))
    assert charge['state'] == 'paid' and Decimal(str(charge['paid_amount'])) == Decimal('100.00')
    assert payment['state'] == 'confirmed' and Decimal(str(payment['amount'])) == Decimal('100.00')
    assert link['adjustment_state'] == 'refund_required'
    assert refund_event is not None
    assert store.fetch_one("SELECT id FROM ledger_entries WHERE tenant_id=? AND entry_type='fiscal_charge_reversal' AND reference_id=?", (local_env.alpha_tenant['id'], ids['charge'])) is None


def test_payment_trigger_resolves_contract_service_order_and_is_idempotent(local_env):
    context, profile, policy, ids = _financial_service_order(local_env, suffix='payment-trigger', paid=True)
    # A política já contém o gatilho payment. O resolver deve seguir payment -> allocation -> installment -> contract -> service order.
    router = local_env.client.app.state.data_router
    first = process_emission_trigger(
        router,
        local_env.alpha_tenant['id'],
        'PaymentConfirmed',
        ids['payment'],
        {'id': ids['payment']},
        'corr-payment-trigger',
    )
    assert first['state'] == 'emission_requested'
    assert first['documents'] and first['documents'][0]['document_type'] == 'NFS-e'
    second = process_emission_trigger(
        router,
        local_env.alpha_tenant['id'],
        'PaymentConfirmed',
        ids['payment'],
        {'id': ids['payment']},
        'corr-payment-trigger',
    )
    assert second['idempotent'] is True and second['id'] == first['id']
    run = router.tenant_store(local_env.alpha_tenant['id']).fetch_one(
        "SELECT source_type,source_id,trigger_type,state FROM fiscal_emission_trigger_runs WHERE tenant_id=? AND id=?",
        (local_env.alpha_tenant['id'], first['id']),
    )
    assert run['source_type'] == 'service_order'
    assert run['source_id'] == ids['order']
    assert run['trigger_type'] == 'payment'
    assert run['state'] == 'emission_requested'


def test_competence_and_billing_triggers_route_service_order(local_env):
    context, profile, policy, ids = _financial_service_order(local_env, suffix='billing-triggers', paid=False)
    router = local_env.client.app.state.data_router
    competence = process_emission_trigger(
        router, local_env.alpha_tenant['id'], 'ServiceCompetenceBilled', 'competence-billing-triggers',
        {'service_order_id': ids['order']}, 'corr-competence-trigger',
    )
    assert competence['state'] == 'emission_requested'
    assert competence['documents'][0]['document_type'] == 'NFS-e'
    billing = process_emission_trigger(
        router, local_env.alpha_tenant['id'], 'ChargeCreated', ids['charge'],
        {'id': ids['charge']}, 'corr-billing-trigger',
    )
    assert billing['state'] == 'emission_requested'
    assert billing['documents'][0]['document_type'] == 'NFS-e'
    assert billing['documents'][0]['id'] == competence['documents'][0]['id']
    store = router.tenant_store(local_env.alpha_tenant['id'])
    competence_run = store.fetch_one("SELECT trigger_type,source_id FROM fiscal_emission_trigger_runs WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], competence['id']))
    billing_run = store.fetch_one("SELECT trigger_type,source_id FROM fiscal_emission_trigger_runs WHERE tenant_id=? AND id=?", (local_env.alpha_tenant['id'], billing['id']))
    assert competence_run['trigger_type'] == 'competence' and competence_run['source_id'] == ids['order']
    assert billing_run['trigger_type'] == 'billing' and billing_run['source_id'] == ids['order']


def test_service_fiscal_event_tracks_nfse_document_and_provider_state(local_env):
    _, _, _, ids = _financial_service_order(local_env, suffix='service-event-link', paid=False)
    tenant_id = local_env.alpha_tenant['id']
    router = local_env.client.app.state.data_router
    store = router.tenant_store(tenant_id)
    now = '2026-08-11T04:00:00+00:00'
    fiscal_event_id = 'service-fiscal-event-link'
    with store.transaction() as conn:
        conn.execute(
            """INSERT INTO service_fiscal_events(
                   id,tenant_id,event_key,service_order_id,service_order_item_id,competence_id,
                   trigger_type,document_type,state,payload_snapshot_json,requested_at,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fiscal_event_id, tenant_id, 'service-order-link:billing', ids['order'], ids['item'], None,
                'service_order_confirmed', 'nfse', 'queued', '{}', now, now, now,
            ),
        )

    first = process_emission_trigger(
        router,
        tenant_id,
        'ServiceOrderConfirmed',
        ids['order'],
        {'id': ids['order'], 'charge_id': ids['charge']},
        'corr-service-fiscal-event-link',
    )
    assert first['state'] == 'emission_requested'
    assert first['documents'] and first['documents'][0]['document_type'] == 'NFS-e'
    document_id = first['documents'][0]['id']

    linked = store.fetch_one(
        """SELECT fiscal_document_id,fiscal_assembly_id,state,failure_code
           FROM service_fiscal_events WHERE tenant_id=? AND id=?""",
        (tenant_id, fiscal_event_id),
    )
    assert linked == {
        'fiscal_document_id': document_id,
        'fiscal_assembly_id': first['assembly_id'],
        'state': 'emission_requested',
        'failure_code': None,
    }
    order = store.fetch_one("SELECT fiscal_status FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, ids['order']))
    assert order == {'fiscal_status': 'emission_requested'}

    handler = build_domain_event_handlers(router, tenant_id=tenant_id)['FiscalDocumentRequested']
    handled = handler(store, {'aggregate_id': document_id, 'event_id': 'evt-service-fiscal-link', 'correlation_id': 'corr-service-fiscal-link'})
    assert handled == {'state': 'awaiting_provider_configuration', 'provider_status': 'not_configured'}
    synced = store.fetch_one(
        """SELECT fiscal_document_id,state,failure_code
           FROM service_fiscal_events WHERE tenant_id=? AND id=?""",
        (tenant_id, fiscal_event_id),
    )
    assert synced == {
        'fiscal_document_id': document_id,
        'state': 'awaiting_provider_configuration',
        'failure_code': 'FISCAL_PROVIDER_NOT_CONFIGURED',
    }
    order = store.fetch_one("SELECT fiscal_status FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, ids['order']))
    assert order == {'fiscal_status': 'awaiting_provider_configuration'}

    cancelled = local_env.client.post(
        f'/api/v1/fiscal/documents/{document_id}/cancel',
        headers=local_env.alpha_headers(),
        json={'reason': 'Cancelamento local antes da transmissão ao provider.'},
    )
    assert cancelled.status_code == 200, cancelled.text
    cancelled_event = store.fetch_one(
        "SELECT state,completed_at FROM service_fiscal_events WHERE tenant_id=? AND id=?",
        (tenant_id, fiscal_event_id),
    )
    assert cancelled_event['state'] == 'cancelled' and cancelled_event['completed_at']
    order = store.fetch_one("SELECT fiscal_status FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, ids['order']))
    assert order == {'fiscal_status': 'cancelled'}

    replay = process_emission_trigger(
        router,
        tenant_id,
        'ServiceOrderConfirmed',
        ids['order'],
        {'id': ids['order'], 'charge_id': ids['charge']},
        'corr-service-fiscal-event-link',
    )
    assert replay['idempotent'] is True and replay['id'] == first['id']
    order = store.fetch_one("SELECT fiscal_status FROM service_orders WHERE tenant_id=? AND id=?", (tenant_id, ids['order']))
    assert order == {'fiscal_status': 'cancelled'}
