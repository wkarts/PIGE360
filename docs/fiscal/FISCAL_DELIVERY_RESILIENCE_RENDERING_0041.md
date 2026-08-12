# Fiscal 0041 — Resiliência de entrega, rejeição e renderização local

## Objetivo

O incremento 0041 fecha capacidades locais que permaneciam incompletas no ciclo de documentos fiscais: política de retry/backoff por provider, limite de tentativas, contingência auditável, persistência explicável das rejeições e geração local determinística de DANFE/DANFC-e/DANFSe a partir do snapshot persistido do documento.

Este incremento **não declara homologação externa** e não substitui provider fiscal oficial. Autorização continua existindo somente quando o provider configurado devolve estado/protocolo válidos.

## Política versionada de entrega

A tabela `fiscal_document_delivery_policies` possui vigência e versão por tenant. A resolução considera:

- tipo de documento;
- provider;
- ambiente;
- data do documento;
- prioridade e especificidade.

Configura:

- `max_attempts`;
- `base_delay_seconds`;
- `max_delay_seconds`;
- `backoff_multiplier`;
- `jitter_seconds` determinístico;
- `auto_retry`;
- `contingency_after_attempts`;
- `contingency_mode` (`offline`, `svc`, `epec`).

Quando a política está publicada, o worker recebe `FiscalRetryScheduled` e usa o `countdown` calculado pela política. Na ausência de política publicada, permanece o comportamento genérico anterior do worker.

## Rejeição explicável

`fiscal_document_rejections` preserva cada falha/rejeição sem sobrescrever histórico:

- tentativa relacionada;
- política selecionada;
- código e mensagem técnica;
- categoria (`transport`, `provider_error`, `provider_rejection`);
- retryable;
- próxima tentativa;
- limite atingido;
- explicação JSON;
- resolução posterior.

A autorização posterior resolve as rejeições anteriores, sem excluí-las.

## Contingência

Contingência não equivale a autorização. Quando o limiar da política é alcançado, o documento registra `contingency_mode`, evento `contingency_activated`, auditoria e `FiscalDocumentContingencyActivated`. O provider continua necessário para autorização quando a legislação/documento o exigir.

## Renderização local determinística

`POST /api/v1/fiscal/documents/{id}/render` cria PDF local determinístico:

- NF-e → `danfe_local`;
- NFC-e → `danfce_local`;
- NFS-e → `danfse_local`.

O conteúdo deriva exclusivamente do documento/snapshot persistido. O artefato é gravado no storage exclusivo do tenant, possui SHA-256 e registro em `fiscal_document_artifacts`, auditoria e outbox `FiscalDocumentRendered`.

O PDF local contém aviso explícito de que o artefato não representa autorização fiscal por si só. A superfície white-label não injeta marca global automaticamente.

## APIs

```text
GET  /api/v1/fiscal/delivery-policies
POST /api/v1/fiscal/delivery-policies
POST /api/v1/fiscal/delivery-policies/{id}/publish

GET  /api/v1/fiscal/documents/{id}/rejection
POST /api/v1/fiscal/documents/{id}/retry
POST /api/v1/fiscal/documents/{id}/render
```

## Persistência e isolamento

Migration: `0041_fiscal_delivery_resilience_rendering`.

As novas tabelas possuem RLS e `FORCE ROW LEVEL SECURITY` no PostgreSQL. O adapter SQLite local replica as estruturas necessárias para testes determinísticos e desenvolvimento offline.

## Limites explícitos

- fixtures de provider não são homologação;
- renderer local não assina nem autoriza documento;
- SVC/EPEC/offline são estados/políticas auditáveis; sua transmissão real continua condicionada ao provider e ambiente configurados;
- contas, regras legais e tempos de retry não são hardcoded como legislação: a política é versionada pelo tenant.
