#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
JP=ROOT/'docs/execution/requirements.json'
MP=ROOT/'docs/execution/REQUIREMENTS_MATRIX.md'

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def esc(v:Any)->str: return '' if v is None else str(v).replace('|','\\|').replace('\n','<br>')

def main():
    data=json.loads(JP.read_text(encoding='utf-8')); items=data['requirements']; by={r['id']:r for r in items}
    related='; '.join([
        'backend/app/modules/fiscal/application/document_delivery_service.py',
        'backend/app/modules/fiscal/presentation/document_delivery_schemas.py',
        'backend/app/modules/fiscal/presentation/router.py',
        'backend/app/shared/events/handlers.py',
        'backend/app/worker.py',
        'backend/app/shared/database/operational_schema.sql',
        'backend/app/shared/database/store.py',
        'backend/alembic_tenant/versions/0041_fiscal_delivery_resilience_rendering.py',
        'apps/tenant-admin-web/src/components/FiscalPanel.vue',
        'backend/tests/fiscal/test_fiscal_delivery_resilience_rendering.py',
        'backend/tests/migrations/test_fiscal_delivery_resilience_rendering_migration.py',
        'backend/tests/frontend/test_fiscal_delivery_admin_0041.py',
        'docs/fiscal/FISCAL_DELIVERY_RESILIENCE_RENDERING_0041.md',
    ])
    evidence='; '.join([
        'docs/execution/evidence/backend-regression-fiscal-delivery-0041.json',
        'docs/execution/evidence/backend-final-regression-0041.log',
        'docs/execution/evidence/fiscal-delivery-0041-targeted.log',
        'docs/execution/evidence/frontend-fiscal-delivery-0041-validation.log',
        'docs/execution/evidence/alembic-tenant-0041-upgrade.log',
        'docs/execution/evidence/alembic-tenant-0041-downgrade.log',
    ])
    tests=('Regressão integral 0041: 72 arquivos e 167 testes aprovados, 0 falhas, com processos pytest isolados. '
           'Testes direcionados comprovam rejeição persistida/explicável, resolução, retry manual e automático com backoff/jitter determinístico, '
           'limite de tentativas, ativação de contingência por limiar, idempotência, isolamento tenant, renderer local determinístico e SHA-256. '
           'Migration 0041 upgrade/downgrade SQL offline e contratos frontend/OpenAPI também aprovados.')

    by['V8-1862'].update(
        status='VERIFIED',
        implementation='Rejeições fiscais são persistidas por documento/tentativa com código, mensagem, classificação retryable/não-retryable, payload técnico controlado, estado resolvido e vínculo com auditoria/outbox.',
        tests=tests,evidence=evidence,related_files=related)
    by['V8-1863'].update(
        status='VERIFIED',
        implementation='Retry fiscal usa política versionada por documento/provider/ambiente, backoff exponencial, jitter determinístico, limite de tentativas, reprocessamento manual idempotente e countdown dinâmico no worker Celery.',
        tests=tests,evidence=evidence,related_files=related)

    # Implementado e exercitado localmente, mas sem afirmar equivalência às modalidades/protocolos oficiais de contingência externos.
    by['V8-1861'].update(
        status='IMPLEMENTED',
        implementation='Política versionada de entrega define limiar e modo de contingência por documento/provider; ativação é persistida, auditada e integrada ao retry. Modalidades oficiais específicas (ex.: SVC/EPEC) continuam dependentes do schema/provider aplicável.',
        tests=tests,evidence=evidence,related_files=related)
    # Renderer local existe para os três tipos, mas o golden test integral ainda cobre explicitamente apenas o fluxo NF-e; manter conservador.
    by['V8-1866'].update(
        status='IMPLEMENTED',
        implementation='Renderizador local determinístico produz artefatos DANFE/DANFC-e/DANFSe a partir do snapshot/XML, com storage tenant e SHA-256; golden coverage integral por todos os três tipos ainda será ampliada antes de VERIFIED.',
        tests=tests,evidence=evidence,related_files=related)

    if 'V8-3027' in by:
        by['V8-3027'].update(
            status='TESTING',
            implementation='Administração fiscal inclui políticas de entrega, diagnóstico de rejeição, retry/reprocessamento e renderização local, além das superfícies fiscais anteriores.',
            tests='Contrato frontend/OpenAPI e validação SFC/TypeScript estrito aprovados; build Vite integral segue condicionado ao tooling Node local.',
            evidence=evidence,
            related_files='apps/tenant-admin-web/src/components/FiscalPanel.vue; backend/tests/frontend/test_fiscal_delivery_admin_0041.py')
    if 'V8-3585' in by:
        by['V8-3585'].update(
            status='TESTING',
            implementation='Migrations fiscais evolutivas chegam a 0041, incluindo políticas de entrega/rejeições, RLS/FORCE RLS e colunas monotônicas de retry/contingência.',
            tests='Migration 0041 possui testes de contrato e SQL offline upgrade/downgrade; PostgreSQL real continua indisponível neste ambiente.',
            evidence='docs/execution/evidence/alembic-tenant-0041-upgrade.log; docs/execution/evidence/alembic-tenant-0041-downgrade.log; '+evidence,
            related_files='backend/alembic_tenant/versions/0041_fiscal_delivery_resilience_rendering.py; backend/tests/migrations/test_fiscal_delivery_resilience_rendering_migration.py')

    counts=Counter(r['status'] for r in items)
    data['generated_at']=now(); data['count']=len(items); data['status_summary']=dict(sorted(counts.items()))
    JP.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[
        '# Matriz persistente de requisitos V8','',
        'Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.','',
        f"Atualizada em `{data['generated_at']}` após o incremento 0041 de resiliência de entrega fiscal e regressão integral 167/167.",'',
        '## Resumo de estados','', '| Estado | Quantidade |','|---|---:|'
    ]
    lines += [f'| {s} | {counts[s]} |' for s in sorted(counts)]
    lines += ['', '| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |','|---|---|---|---|---|---|---|---|---|---|---|']
    fields=['id','section','description','module','dependencies','related_files','status','implementation','tests','evidence','observations']
    for r in items: lines.append('| '+' | '.join(esc(r.get(f)) for f in fields)+' |')
    MP.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'count':len(items),'status_summary':data['status_summary'],'promoted_verified':['V8-1862','V8-1863'],'kept_implemented':['V8-1861','V8-1866']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
