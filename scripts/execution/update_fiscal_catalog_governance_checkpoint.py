#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
JSON_PATH=ROOT/'docs/execution/requirements.json'
MD_PATH=ROOT/'docs/execution/REQUIREMENTS_MATRIX.md'

def now()->str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def esc(v:Any)->str: return '' if v is None else str(v).replace('|','\\|').replace('\n','<br>')

def main()->None:
    data=json.loads(JSON_PATH.read_text())
    items=data['requirements']; by={x['id']:x for x in items}
    related='; '.join([
        'backend/app/modules/fiscal/application/catalog_import_service.py',
        'backend/app/modules/fiscal/presentation/catalog_import_schemas.py',
        'backend/app/modules/fiscal/presentation/catalog_schemas.py',
        'backend/app/modules/fiscal/presentation/router.py',
        'backend/app/shared/database/operational_schema.sql',
        'backend/alembic_tenant/versions/0037_fiscal_catalog_governance_imports.py',
        'apps/tenant-admin-web/src/components/FiscalPanel.vue',
        'backend/tests/fiscal/test_fiscal_catalog_governance.py',
        'backend/tests/migrations/test_fiscal_catalog_governance_imports_migration.py',
        'docs/fiscal/FISCAL_CATALOG_GOVERNANCE.md',
    ])
    evidence='; '.join([
        'docs/execution/evidence/backend-regression-fiscal-governance-r20.json',
        'docs/execution/evidence/backend-final-regression-140.log',
        'docs/execution/evidence/alembic-tenant-0037-upgrade.log',
        'docs/execution/evidence/alembic-tenant-0037-downgrade.log',
        'docs/execution/evidence/frontend-fiscal-governance-r20.log',
        'docs/execution/evidence/api-sdk-typecheck-fiscal-governance-r20.log',
    ])
    tests='Regressão integral: 63 arquivos e 140 testes aprovados, 0 falhas. Testes do incremento comprovam importação CSV/JSON/XSD, SHA-256, storage tenant, diff, publicação, rollback imutável, quarentena, isolamento cross-tenant e provider externo not_configured.'
    impl='Governança de catálogos com perfil de fonte/versionamento, importadores locais CSV/JSON/XSD, snapshot bruto com SHA-256 no storage do tenant, diff, publicação/agendamento, rollback como nova versão, health/expiração e quarentena auditável; providers externos permanecem not_configured sem configuração real.'

    for rid in ('V8-1836','V8-1837','V8-1841','V8-1844','V8-1845'):
        by[rid].update(status='VERIFIED',implementation=impl,tests=tests,evidence=evidence,related_files=related)
    for rid in ('V8-1847','V8-1802','V8-1803'):
        by[rid].update(status='IMPLEMENTED',implementation=impl,tests='Mecanismo implementado e coberto pela regressão; o cenário específico/artefato oficial correspondente ainda não possui fixture dedicada suficiente para promoção a VERIFIED.',evidence=evidence,related_files=related)
    # Catálogos sem fixture oficial específica permanecem IMPLEMENTED, mas agora têm importer/provider local genérico.
    for rid in ('V8-1838','V8-1839','V8-1840','V8-1842','V8-1843'):
        if by[rid]['status'] != 'VERIFIED':
            by[rid].update(status='IMPLEMENTED',implementation=impl,tests='Infraestrutura comum e contratos aprovados; ausência de snapshot oficial/dedicado deste catálogo nesta execução impede VERIFIED.',evidence=evidence,related_files=related)
    by['V8-1793'].update(status='IMPLEMENTED',implementation='Atos, notas técnicas, schemas e tabelas podem ser referenciados/versionados e snapshots locais podem ser importados com hash, vigência e quarentena. Consulta externa oficial continua condicional a provider configurado.',tests=tests,evidence=evidence,related_files=related)
    by['V8-3027'].update(status='TESTING',implementation='Administração fiscal do tenant inclui fontes/importadores, upload local CSV/JSON/XSD, saúde, histórico, publicação, rollback e quarentena usando APIs reais.',tests='SFC/TypeScript estrito e contratos de rotas/handlers aprovados; build Vite integral continua condicionado ao node_modules/lockfile local.',evidence=evidence,related_files='apps/tenant-admin-web/src/components/FiscalPanel.vue; backend/tests/frontend/test_tenant_admin_vertical_modules.py')
    by['V8-3585'].update(status='TESTING',implementation='Migrations evolutivas incluem 0037 com RLS/FORCE RLS e policies para fontes, execuções de importação e quarentena.',tests='Upgrade/downgrade SQL offline e dois testes de contrato aprovados; execução em PostgreSQL real permanece bloqueada pela ausência do serviço local.',evidence='docs/execution/evidence/alembic-tenant-0037-upgrade.log; docs/execution/evidence/alembic-tenant-0037-downgrade.log; '+evidence,related_files='backend/alembic_tenant/versions/0037_fiscal_catalog_governance_imports.py; backend/tests/migrations/test_fiscal_catalog_governance_imports_migration.py')

    counts=Counter(x['status'] for x in items)
    data['generated_at']=now(); data['count']=len(items); data['status_summary']=dict(sorted(counts.items()))
    JSON_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    lines=['# Matriz persistente de requisitos V8','', 'Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.','',f"Atualizada em `{data['generated_at']}` após governança/importação versionada de catálogos fiscais e regressão integral.",'','## Resumo de estados','','| Estado | Quantidade |','|---|---:|']
    lines += [f'| {s} | {counts[s]} |' for s in sorted(counts)]
    lines += ['','| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |','|---|---|---|---|---|---|---|---|---|---|---|']
    fields=['id','section','description','module','dependencies','related_files','status','implementation','tests','evidence','observations']
    for item in items: lines.append('| '+' | '.join(esc(item.get(f)) for f in fields)+' |')
    MD_PATH.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'count':len(items),'status_summary':data['status_summary'],'verified_now':['V8-1836','V8-1837','V8-1841','V8-1844','V8-1845']},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
