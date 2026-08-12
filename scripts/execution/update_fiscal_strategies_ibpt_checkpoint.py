#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
JP=ROOT/'docs/execution/requirements.json'; MP=ROOT/'docs/execution/REQUIREMENTS_MATRIX.md'
data=json.loads(JP.read_text(encoding='utf-8')); reqs=data['requirements']; by={r['id']:r for r in reqs}
E='docs/execution/evidence/fiscal-strategies-ibpt-r000017.log; docs/execution/evidence/backend-regression-post-ibpt-current.json'
F='backend/app/modules/fiscal/application/strategy_service.py; backend/app/modules/fiscal/application/calculation_service.py; backend/app/modules/fiscal/application/ibpt.py; backend/app/modules/fiscal/presentation/router.py; backend/alembic_tenant/versions/0035_fiscal_strategies_rtc_schedule.py; backend/alembic_tenant/versions/0036_ibpt_operational_resilience.py; apps/tenant-admin-web/src/components/FiscalPanel.vue'
def patch(rid,status,impl,tests,evidence=E,files=F):
 r=by[rid]; r['status']=status; r['implementation']=impl; r['tests']=tests; r['evidence']=evidence; r['related_files']=files
# estratégias diretamente exercitadas
for rid,name in [('V8-1754','retenções'),('V8-1755','DIFAL'),('V8-1769','crédito presumido')]:
 patch(rid,'VERIFIED',f'Estratégia versionada de {name}, resolvida por contexto/estabelecimento/regime/operação/vigência e integrada ao cálculo tributário com explicabilidade.','Cenário fiscal direcionado e regressão integral aprovados.')
for rid,name in [('V8-1777','devolução'),('V8-1778','transferência'),('V8-1779','ajuste'),('V8-1780','estorno'),('V8-1781','importação'),('V8-1782','exportação'),('V8-1783','regimes específicos')]:
 patch(rid,'IMPLEMENTED',f'Estratégia {name} modelada no catálogo de tipos, persistência versionada, resolução e motor de ajustes.','Motor e contratos passam na regressão; falta golden test isolado específico deste tipo antes de VERIFIED.')
patch('V8-1784','IMPLEMENTED','Modo RTC disabled aceito pelo schema e cronograma versionado.','Infraestrutura coberta; falta resolução dedicada deste modo no golden test.')
patch('V8-1785','IMPLEMENTED','Modo RTC simulation_only aceito pelo schema e cronograma versionado.','Infraestrutura coberta; falta resolução dedicada deste modo no golden test.')
patch('V8-1786','VERIFIED','Modo RTC optional_emit resolvido por contexto/regime/estabelecimento e vigência.','Golden test resolve optional_emit em 2026.')
patch('V8-1787','VERIFIED','Modo RTC required_emit resolvido por contexto/regime/estabelecimento e vigência.','Golden test resolve required_emit em 2027.')
patch('V8-1788','VERIFIED','Contexto Simples Nacional 2026 com RTC optional_emit calcula documento sem exigir grupos IBS/CBS ausentes no cenário exercitado.','Golden test Simples 2026 aprovado.')
patch('V8-1790','VERIFIED','Obrigatoriedade RTC é cronograma versionado e o cenário 2027 resolve required_emit.','Golden test 2027 aprovado.')
patch('V8-1791','IMPLEMENTED','Regras e cronogramas são discriminados por tax_regime e suportam Simples/regular sem flag global.','Arquitetura/regressão aprovadas; falta golden comparativo dedicado entre as duas alternativas.')
patch('V8-1793','IMPLEMENTED','Fontes normativas versionadas suportam ato, nota técnica, schema, tabela oficial e outros tipos, com vigência, referência e SHA-256.','Nota técnica fixture exercitada; demais tipos aguardam fonte local real/dedicada.')
# IBPT
ibpt_verified={
 'V8-1812':'As 27 UFs são suportadas e o enfileiramento manual sem UF gera 27 execuções únicas.',
 'V8-1814':'Sincronização manual por UF implementada e exercitada.',
 'V8-1815':'Download/adapter por UF exercitado com URL BA no transport de teste.',
 'V8-1816':'Parser CSV robusto exercitado com formato IBPT separado por ponto e vírgula.',
 'V8-1817':'Normalização numérica e de códigos exercitada.',
 'V8-1818':'Snapshots possuem source_version e histórico.',
 'V8-1819':'Snapshots/rates preservam vigência da fonte.',
 'V8-1820':'CSV original e pacote offline possuem SHA-256.',
 'V8-1821':'Snapshot original é armazenado no object storage do tenant e relido no teste.',
 'V8-1822':'Diff added/removed/changed entre snapshots é exercitado.',
 'V8-1823':'Publicação ativa/superseded é transacional e exercitada.',
 'V8-1824':'Rollback de snapshot é exercitado e auditado.',
 'V8-1827':'Solicitações e rollback possuem auditoria.',
 'V8-1828':'CSV inválido é persistido em quarentena sem substituir snapshot ativo.',
 'V8-1829':'Status operacional gera alerta de quarentena.',
 'V8-1830':'Pacote offline determinístico por UF é gerado com SHA-256.',
 'V8-1831':'Consulta de taxa usa snapshot/rates locais; o transport externo aparece apenas na sincronização.',
 'V8-1832':'Resposta IBPT declara tax_calculation_source=false e permanece separada do motor tributário real.',
 'V8-1833':'Lookup IBPT declara propósito transparencia_vtottrib.'}
for rid,impl in ibpt_verified.items(): patch(rid,'VERIFIED',impl,'Testes IBPT existentes + resiliência IBPT incluídos na regressão integral.')
patch('V8-1825','IMPLEMENTED','Consulta utiliza snapshot e rates persistidos localmente, funcionando como cache materializado por UF/versão.','Lookup local exercitado; política formal de expiração/cache distribuído ainda não possui teste dedicado.')
# fallback fica NOT_STARTED por honestidade
# UI fiscal: mantém TESTING e atualiza evidência nos requisitos que já estão TESTING relacionados à fiscal se houver descrição exata
for r in reqs:
 if r.get('status')=='TESTING' and r.get('description','').strip(';').lower()=='fiscal':
  r['implementation']='Superfície fiscal administrativa conectada às APIs reais de contextos, catálogos, cálculo, estratégias/RTC e IBPT.'
  r['tests']='Contrato frontend direcionado 4/4 e estrutura SFC aprovados; build Vite integral bloqueado por tooling local ausente.'
  r['evidence']='docs/execution/evidence/frontend-fiscal-post-ibpt-targeted.log; '+E
counts=Counter(r['status'] for r in reqs); data['generated_at']=datetime.now(timezone.utc).replace(microsecond=0).isoformat(); data['count']=len(reqs); data['status_summary']=dict(sorted(counts.items()))
JP.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def esc(v): return str(v or '').replace('|','\\|').replace('\n','<br>')
lines=['# Matriz persistente de requisitos V8','', 'Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.','',f"Atualizada em `{data['generated_at']}` após regressão integral pós-IBPT e reconciliação física.",'','## Resumo de estados','', '| Estado | Quantidade |','|---|---:|']
for s in sorted(counts): lines.append(f'| {s} | {counts[s]} |')
lines += ['', '| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |','|---|---|---|---|---|---|---|---|---|---|---|']
fields=['id','section','description','module','dependencies','related_files','status','implementation','tests','evidence','observations']
for r in reqs: lines.append('| '+' | '.join(esc(r.get(f)) for f in fields)+' |')
MP.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'count':len(reqs),'status_summary':data['status_summary']},ensure_ascii=False,indent=2))
