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
      'backend/app/modules/fiscal/application/calculation_service.py','backend/app/modules/fiscal/presentation/calculation_schemas.py',
      'backend/app/modules/fiscal/presentation/router.py','backend/app/shared/database/operational_schema.sql',
      'backend/alembic_tenant/versions/0034_fiscal_tax_calculation_engine.py','apps/tenant-admin-web/src/components/FiscalPanel.vue',
      'backend/tests/fiscal/test_fiscal_tax_calculation_engine.py','backend/tests/migrations/test_fiscal_tax_calculation_engine_migration.py',
      'backend/tests/frontend/test_tenant_admin_vertical_modules.py','docs/fiscal/FISCAL_TAX_CALCULATION_ENGINE.md'])
    evidence='; '.join([
      'docs/execution/evidence/fiscal-tax-engine-targeted-r000015.log',
      'docs/execution/evidence/backend-final-regression-r000015.json',
      'docs/execution/evidence/backend-final-regression-r000015.log',
      'docs/execution/evidence/alembic-tenant-0034-upgrade.log',
      'docs/execution/evidence/alembic-tenant-0034-downgrade.log',
      'docs/execution/evidence/frontend-fiscal-tax-engine-validation-r000015.log',
      'docs/execution/evidence/typescript-tax-engine-r000015.log'])
    impl=('Motor tributário parametrizado e versionado por contexto, estabelecimento, operação, item, regime, RTC e vigência; '
          'componentes suportam base, alíquota, MVA, redução, diferimento, suspensão, imunidade, não incidência, alíquota zero, '
          'monofásico, explicabilidade, snapshot SHA-256, divergência, auditoria, outbox e isolamento por tenant.')
    tests=('Golden tests locais comprovam ICMS, ICMS-ST/MVA, FCP, IPI, PIS, COFINS, ISS, IBS estadual/municipal, CBS, IS, redução de base, '
           'diferimento, suspensão, monofásico, imunidade, não incidência, divergência, idempotência e isolamento; regressão integral 128/128.')
    verified=list(range(1743,1754))+list(range(1770,1777))+[1789,1804,1805]
    for n in verified:
        by[f'V8-{n:04d}'].update(status='VERIFIED',implementation=impl,tests=tests,evidence=evidence,related_files=related)
    by['V8-3027'].update(status='TESTING',implementation='Administração fiscal do tenant cobre contextos, catálogos, classificações, prontidão e motor tributário versionado com simulação explicável.',tests='SFC validado com TypeScript estrito e contratos de rotas/handlers aprovados; build Vite integral continua condicionado ao tooling Node local.',evidence=evidence,related_files='apps/tenant-admin-web/src/components/FiscalPanel.vue; backend/tests/frontend/test_tenant_admin_vertical_modules.py')
    by['V8-3585'].update(status='TESTING',implementation='Migrations evolutivas incluem 0034 com RLS e snapshot de cálculos tributários.',tests='Migration 0034 possui testes de contrato e SQL offline de upgrade/downgrade; PostgreSQL real não está disponível neste host.',evidence='docs/execution/evidence/alembic-tenant-0034-upgrade.log; docs/execution/evidence/alembic-tenant-0034-downgrade.log',related_files='backend/alembic_tenant/versions/0034_fiscal_tax_calculation_engine.py; backend/tests/migrations/test_fiscal_tax_calculation_engine_migration.py')
    counts=Counter(x['status'] for x in items); data['generated_at']=now(); data['count']=len(items); data['status_summary']=dict(sorted(counts.items())); JSON_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    lines=['# Matriz persistente de requisitos V8','', 'Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.','',f"Atualizada em `{data['generated_at']}` após o motor tributário versionado e regressão integral 128/128.",'','## Resumo de estados','','| Estado | Quantidade |','|---|---:|']
    lines += [f'| {s} | {counts[s]} |' for s in sorted(counts)]
    lines += ['','| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |','|---|---|---|---|---|---|---|---|---|---|---|']
    fields=['id','section','description','module','dependencies','related_files','status','implementation','tests','evidence','observations']
    for item in items: lines.append('| '+' | '.join(esc(item.get(f)) for f in fields)+' |')
    MD_PATH.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'count':len(items),'status_summary':data['status_summary'],'promoted':[f'V8-{n:04d}' for n in verified]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
