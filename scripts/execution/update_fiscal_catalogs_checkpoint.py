#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[2]
JSON_PATH=ROOT/'docs/execution/requirements.json'; MD_PATH=ROOT/'docs/execution/REQUIREMENTS_MATRIX.md'
def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def esc(v:Any)->str: return '' if v is None else str(v).replace('|','\\|').replace('\n','<br>')

def main():
    data=json.loads(JSON_PATH.read_text()); items=data['requirements']; by={x['id']:x for x in items}
    related='; '.join([
      'backend/app/modules/fiscal/application/catalog_service.py','backend/app/modules/fiscal/presentation/catalog_schemas.py',
      'backend/app/modules/fiscal/presentation/router.py','backend/app/shared/database/operational_schema.sql',
      'backend/alembic_tenant/versions/0033_fiscal_catalogs_classifications.py','apps/tenant-admin-web/src/components/FiscalPanel.vue',
      'backend/tests/fiscal/test_fiscal_catalog_classifications.py','backend/tests/migrations/test_fiscal_catalogs_classifications_migration.py',
      'docs/fiscal/FISCAL_CATALOGS_CLASSIFICATION.md'])
    evidence='; '.join(['docs/execution/evidence/fiscal-catalogs-vertical-validation-r000013.log','docs/execution/evidence/backend-final-regression-r000013.json','docs/execution/evidence/alembic-tenant-0033-upgrade-r000013.log','docs/execution/evidence/alembic-tenant-0033-downgrade-r000013.log'])
    impl='Catálogo/classificação fiscal independente e versionado por tenant, fonte, SHA-256 e vigência, com validação de código vigente, regras por estabelecimento/item/operação, auditoria, outbox e RLS.'
    tests='Testes comprovam os dez tipos de catálogo, replay idempotente, publicação, resolução por vigência, validação de códigos, isolamento cross-tenant, classificação de produto/serviço e prontidão; regressão integral 123/123.'
    verified=[1756,1757,1758,1759,1760,1761,1762,1766,1767,1768,1792,1794,1795,1796,1797,1798,1799,1800,1801,1806,3751,3753,3754]
    for n in verified:
        by[f'V8-{n:04d}'].update(status='VERIFIED',implementation=impl,tests=tests,evidence=evidence,related_files=related)
    for n in range(1836,1844):
        by[f'V8-{n:04d}'].update(status='IMPLEMENTED',implementation='Estrutura versionada, histórica e publicável do catálogo disponível com fonte, hash, vigência e API; sincronizador específico da fonte oficial ainda não implementado.',tests='Contratos de catálogo, migration 0033 e regressão comprovam persistência e resolução; integração de download oficial permanece pendente.',evidence=evidence,related_files=related)
    by['V8-1789'].update(status='IMPLEMENTED',implementation='Classificação e prontidão RTC versionadas foram implementadas; simulação fiscal pré-existente permanece integrada ao domínio.',tests=tests,evidence=evidence,related_files=related)
    by['V8-3027'].update(status='TESTING',implementation='Administração fiscal do tenant cobre contextos, vigências, catálogos, classificações e prontidão usando APIs reais.',tests='SFC TypeScript/estrutura e contratos de rotas/handlers aprovados; build Vite integral continua condicionado ao tooling Node local.',evidence='docs/execution/evidence/frontend-fiscal-catalogs-validation-r000013.log; '+evidence,related_files='apps/tenant-admin-web/src/components/FiscalPanel.vue; backend/tests/frontend/test_tenant_admin_vertical_modules.py')
    by['V8-3585'].update(status='TESTING',implementation='Migrations evolutivas incluem 0033 com RLS, upgrade/downgrade adjacente e SQL PostgreSQL renderizável.',tests='Migration 0033 possui dois testes de contrato e SQL offline de upgrade/downgrade; PostgreSQL real não está disponível neste host.',evidence='docs/execution/evidence/alembic-tenant-0033-upgrade-r000013.log; docs/execution/evidence/alembic-tenant-0033-downgrade-r000013.log',related_files='backend/alembic_tenant/versions/0033_fiscal_catalogs_classifications.py; backend/tests/migrations/test_fiscal_catalogs_classifications_migration.py')
    counts=Counter(x['status'] for x in items); data['generated_at']=now(); data['count']=len(items); data['status_summary']=dict(sorted(counts.items())); JSON_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    lines=['# Matriz persistente de requisitos V8','', 'Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.','',f"Atualizada em `{data['generated_at']}` após o incremento fiscal versionado e regressão integral.",'','## Resumo de estados','','| Estado | Quantidade |','|---|---:|']
    lines += [f'| {s} | {counts[s]} |' for s in sorted(counts)]
    lines += ['','| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |','|---|---|---|---|---|---|---|---|---|---|---|']
    fields=['id','section','description','module','dependencies','related_files','status','implementation','tests','evidence','observations']
    for item in items: lines.append('| '+' | '.join(esc(item.get(f)) for f in fields)+' |')
    MD_PATH.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'count':len(items),'status_summary':data['status_summary']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
