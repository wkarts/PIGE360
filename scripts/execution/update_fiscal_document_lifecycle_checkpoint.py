#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
JP=ROOT/'docs/execution/requirements.json'; MP=ROOT/'docs/execution/REQUIREMENTS_MATRIX.md'

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def esc(v:Any)->str: return '' if v is None else str(v).replace('|','\\|').replace('\n','<br>')

def main():
    data=json.loads(JP.read_text()); items=data['requirements']; by={r['id']:r for r in items}
    related='; '.join([
        'backend/app/modules/fiscal/application/document_lifecycle_service.py',
        'backend/app/modules/fiscal/presentation/document_lifecycle_schemas.py',
        'backend/app/modules/fiscal/presentation/router.py',
        'backend/app/shared/integrations/providers.py',
        'backend/app/shared/events/handlers.py',
        'backend/app/shared/database/operational_schema.sql',
        'backend/alembic_tenant/versions/0038_fiscal_document_lifecycle.py',
        'apps/tenant-admin-web/src/components/FiscalPanel.vue',
        'backend/tests/fiscal/test_fiscal_document_lifecycle.py',
        'backend/tests/fiscal/test_fiscal_delivery.py',
        'backend/tests/migrations/test_fiscal_document_lifecycle_migration.py',
        'docs/fiscal/FISCAL_DOCUMENT_LIFECYCLE.md',
    ])
    evidence='; '.join([
        'docs/execution/evidence/backend-regression-fiscal-doc-lifecycle-r000023.log',
        'docs/execution/evidence/fiscal-document-lifecycle-targeted-r000023.log',
        'docs/execution/evidence/alembic-tenant-0038-upgrade.log',
        'docs/execution/evidence/alembic-tenant-0038-downgrade.log',
        'docs/execution/evidence/frontend-fiscal-doc-lifecycle-r000023.log',
        'docs/execution/evidence/openapi-regeneration-r000023.log',
    ])
    tests='Regressão integral pós-0038: 65 arquivos e 144 testes aprovados, 0 falhas. Fixtures locais exercitam emissão, consulta, cancelamento, carta/evento, substituição, inutilização, storage tenant, XML/PDF, SHA-256, protocolo/chave, A1 apenas por referência segura, auditoria/outbox, isolamento cross-tenant e provider sem segredo em not_configured.'
    impl='Ciclo de vida fiscal versionado e auditável, com configuração especializada de provider/certificado por referência, tentativas persistidas, artefatos tenant-scoped com SHA-256, consulta, cancelamento, eventos, substituição, inutilização e estados condicionais sem simular autorização externa.'
    verified={
        'V8-1855':'Emissão via contrato comum e worker idempotente, com autorização fixture e persistência de artefatos.',
        'V8-1856':'Consulta ao provider enfileirada, conciliada e auditada.',
        'V8-1857':'Cancelamento enfileirado e estado final cancelado exercitado.',
        'V8-1858':'Substituição cria documento sucessor e preserva vínculo/estado do original.',
        'V8-1859':'Inutilização por faixa possui agregado, provider operation, protocolo, auditoria e outbox.',
        'V8-1860':'Eventos do provider (fixture de carta de correção) possuem inbox de estado, protocolo e artefato.',
        'V8-1865':'XML autorizado/evento é armazenado fora do banco no storage tenant e referenciado por hash.',
        'V8-1867':'Protocolo retornado pelo provider é persistido nos documentos/eventos/inutilizações.',
        'V8-1868':'Chave de acesso retornada pelo provider é persistida e consultável no detalhe do documento.',
        'V8-1872':'Artefatos fiscais são persistidos no storage exclusivo do tenant com chave controlada pelo backend.',
        'V8-1873':'SHA-256 de XML/PDF é calculado e conferido contra os bytes armazenados.',
        'V8-1874':'Operações do ciclo fiscal registram auditoria, tentativas e transactional outbox.',
    }
    for rid,desc in verified.items():
        by[rid].update(status='VERIFIED',implementation=desc,tests=tests,evidence=evidence,related_files=related)
    # Capacidades implementadas, mas sem prova de integração oficial externa/artefato gerado pelo próprio produto.
    implemented={
        'V8-1851':'NF-e possui provider especializado configurável e ciclo comum completo; homologação SEFAZ real ainda depende de credenciais/certificado/ambiente.',
        'V8-1852':'NFC-e possui provider especializado configurável e ciclo comum completo; homologação SEFAZ real ainda depende de credenciais/certificado/ambiente.',
        'V8-1853':'NFS-e nacional possui provider especializado configurável e estado not_configured sem segredo; homologação oficial não foi simulada.',
        'V8-1854':'NFS-e municipal possui provider especializado configurável; município/credenciais reais permanecem externos.',
        'V8-1861':'Modo de contingência é registrado no snapshot/documento e preservado no ciclo; regras oficiais específicas de cada modalidade ainda requerem payload/schema dedicado.',
        'V8-1866':'Artefato PDF fiscal derivado é armazenado e hash-validado quando retornado pelo provider; geração própria completa de DANFE/DANFC-e/DANFSe ainda não foi comprovada.',
        'V8-1869':'Certificado A1 possui metadados/versionamento e apenas secret_ref; chave/PFX e senha nunca entram no frontend/banco. Uso criptográfico real depende do secret configurado.',
        'V8-1875':'SefazNfeProvider implementa contrato issue/query/cancel/substitute/inutilize/event/health e configuração segura; autorização SEFAZ real não foi alegada.',
        'V8-1876':'SefazNfceProvider implementa o contrato comum e configuração segura; autorização SEFAZ real não foi alegada.',
        'V8-1877':'NationalNfseProvider implementa o contrato comum e not_configured seguro; autorização nacional real não foi alegada.',
        'V8-1878':'MunicipalNfseProvider implementa o contrato comum e not_configured seguro; integração municipal específica permanece condicionada.',
        'V8-1879':'ThirdPartyFiscalProvider implementa o contrato comum e configuração condicionada por segredo/provider.',
    }
    for rid,desc in implemented.items():
        if by[rid]['status']!='VERIFIED':
            by[rid].update(status='IMPLEMENTED',implementation=desc,tests=tests,evidence=evidence,related_files=related)
    for rid,label in [('V8-1870','homologação oficial'),('V8-1871','produção oficial')]:
        if by[rid]['status']!='VERIFIED':
            by[rid].update(status='BLOCKED_EXTERNAL',implementation=f'Código suporta ambientes separados e provider condicional; {label} exige endpoint, credenciais/certificado e protocolo externos reais.',tests='Fixtures locais e estados not_configured aprovados; nenhuma autorização externa foi simulada como real.',evidence=evidence,related_files=related)
    # Admin fiscal possui superfície funcional do ciclo 0038; build completo segue condicionado ao toolchain local.
    if 'V8-3027' in by:
        by['V8-3027'].update(status='TESTING',implementation='Administração fiscal inclui providers/certificados, health, documentos, consulta, cancelamento, substituição, eventos e inutilização consumindo APIs reais.',tests='Contrato frontend + SFC/TypeScript estrito aprovados; build Vite integral permanece condicionado aos node_modules/lockfile locais.',evidence=evidence,related_files='apps/tenant-admin-web/src/components/FiscalPanel.vue; backend/tests/frontend/test_tenant_admin_vertical_modules.py')
    if 'V8-3585' in by:
        by['V8-3585'].update(status='TESTING',implementation='Migrations fiscais evolutivas chegam a 0038 com RLS/FORCE RLS e preservação monotônica das colunas de cadeia documental.',tests='Upgrade/downgrade SQL offline e testes de contrato aprovados; PostgreSQL real continua indisponível neste ambiente.',evidence='docs/execution/evidence/alembic-tenant-0038-upgrade.log; docs/execution/evidence/alembic-tenant-0038-downgrade.log; '+evidence,related_files='backend/alembic_tenant/versions/0038_fiscal_document_lifecycle.py')
    counts=Counter(r['status'] for r in items)
    data['generated_at']=now(); data['count']=len(items); data['status_summary']=dict(sorted(counts.items()))
    JP.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    lines=['# Matriz persistente de requisitos V8','', 'Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.','',f"Atualizada em `{data['generated_at']}` após o ciclo de vida fiscal 0038 e regressão integral 144/144.",'','## Resumo de estados','','| Estado | Quantidade |','|---|---:|']
    lines += [f'| {s} | {counts[s]} |' for s in sorted(counts)]
    lines += ['','| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |','|---|---|---|---|---|---|---|---|---|---|---|']
    fields=['id','section','description','module','dependencies','related_files','status','implementation','tests','evidence','observations']
    for r in items: lines.append('| '+' | '.join(esc(r.get(f)) for f in fields)+' |')
    MP.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'count':len(items),'status_summary':data['status_summary'],'verified_now':list(verified),'implemented_or_external':list(implemented)+['V8-1870','V8-1871']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
