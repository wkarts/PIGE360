from __future__ import annotations
from app.shared.events.dispatcher import event_envelope
from app.worker import handle_event
SECRET='ibpt-resilience-secret-'+'x'*64
class Fake:
 def __init__(self,rate='20,00',invalid=False): self.rate=rate; self.invalid=invalid
 def request_bytes(self,method,url,*,headers,timeout=30.0,retries=2):
  if self.invalid:return 200,b'foo;bar\n;\n'
  txt='codigo;descricao;nacionalfederal;importadosfederal;estadual;municipal;vigenciainicio;vigenciafim;versao;fonte\n01012100;Item;10,00;12,00;'+self.rate+';0,00;01/01/2026;31/12/2026;26.1;IBPT\n'
  return 200,txt.encode()
def _queue(env):
 r=env.client.post('/api/v1/fiscal/ibpt/sync',headers=env.alpha_headers(),json={'ufs':['BA']});assert r.status_code==202,r.text;return r.json()['runs'][0]['id']
def _event(env,rid):
 store=env.client.app.state.data_router.tenant_store(env.alpha_tenant['id']);row=store.fetch_one("SELECT * FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type='IbptSyncRequested'",(env.alpha_tenant['id'],rid));return event_envelope(row,tenant_id=env.alpha_tenant['id'],secret=SECRET,plane='tenant')
def test_ibpt_offline_rollback_status_and_quarantine(local_env):
 router=local_env.client.app.state.data_router;tid=local_env.alpha_tenant['id'];store=router.tenant_store(tid)
 rid=_queue(local_env); a=handle_event(_event(local_env,rid),router=router,signing_secret=SECRET,transport=Fake('20,00')); first=a['result']['domain']['snapshot_id']
 rid=_queue(local_env); b=handle_event(_event(local_env,rid),router=router,signing_secret=SECRET,transport=Fake('21,00')); second=b['result']['domain']['snapshot_id'];assert first!=second
 offline=local_env.client.get('/api/v1/fiscal/ibpt/offline/BA',headers=local_env.alpha_headers());assert offline.status_code==200,offline.text; body=offline.json();assert body['snapshot']['id']==second and len(body['package_sha256'])==64 and body['tax_calculation_source'] is False
 rb=local_env.client.post(f'/api/v1/fiscal/ibpt/snapshots/{first}/rollback',headers=local_env.alpha_headers());assert rb.status_code==200,rb.text;assert store.fetch_one("SELECT state FROM ibpt_snapshots WHERE id=?",(first,))['state']=='active'
 bad=_queue(local_env); result=handle_event(_event(local_env,bad),router=router,signing_secret=SECRET,transport=Fake(invalid=True));assert result['result']['domain']['state']=='failed';assert store.scalar("SELECT COUNT(*) FROM ibpt_quarantine_items WHERE tenant_id=? AND state='open'",(tid,))==1
 status=local_env.client.get('/api/v1/fiscal/ibpt/operational-status',headers=local_env.alpha_headers());assert status.status_code==200,status.text;assert status.json()['quarantine_open']==1 and any(x['code']=='IBPT_QUARANTINE_OPEN' for x in status.json()['alerts'])
 assert store.scalar("SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND aggregate_type='ibpt_snapshot' AND action='rollback'",(tid,))==1
