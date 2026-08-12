# Roteamento fiscal e montagem documental versionada — incremento 0039

## Objetivo

Este incremento separa a decisão **qual documento emitir** da integração de transporte com SEFAZ/NFS-e já existente. A decisão é persistida, versionada, auditável e reproduzível; a emissão real continua condicionada a provider, certificado, ambiente e credenciais configurados.

O módulo não contém XSD oficial embutido como verdade legal permanente. Os schemas são importados, versionados por vigência, armazenados no storage do tenant e identificados por SHA-256. Os golden XML desta suíte são fixtures técnicas locais e não representam homologação oficial.

## Persistência

- `fiscal_document_schema_versions`: XSD importado, versão, vigência, storage e SHA-256.
- `fiscal_document_routing_policies`: política publicada por contexto fiscal, operação, destinatário, canal, gatilho e vigência.
- `fiscal_document_assemblies`: snapshot imutável da entrada e decisão de roteamento.
- `fiscal_document_builds`: payload/XML construído, XSD aplicado, resultado da validação e total.
- `fiscal_document_links`: vínculo entre pedido/origem, montagem, build e documento fiscal.
- `fiscal_document_financial_links`: contrato/cobrança vinculados ao documento e estado de eventual ajuste financeiro.
- `fiscal_emission_trigger_runs`: inbox idempotente dos gatilhos automáticos.

Todas as tabelas novas da migration `0039_fiscal_document_routing_assembly` possuem `tenant_id`, RLS habilitada e `FORCE ROW LEVEL SECURITY`.

## Decisão documental

A política é resolvida pela vigência do contexto e pode ser restringida por:

- natureza/operação (`operation_type`);
- perfil do destinatário;
- canal;
- modo de gatilho;
- regime tributário opcional (`settings.tax_regimes`);
- município opcional (`settings.municipality_codes`);
- existência ou ID do contrato financeiro.

Sem override de política, o roteador aplica decisões estruturais:

- serviço → NFS-e;
- consumidor em PDV/cantina/kiosk/varejo → NFC-e;
- pessoa jurídica, governo, exterior ou operação interestadual de produto → NF-e;
- produto fora desses casos → NF-e.

A decisão persistida contém as dimensões efetivamente utilizadas, rotas escolhidas, motivos e SHA-256 do contexto fiscal.

## Venda mista

Uma única origem comercial pode gerar duas partes fiscais sem perder o vínculo:

```text
pedido comercial
├── product_part → NF-e ou NFC-e
└── service_part → NFS-e
```

As duas partes permanecem ligadas ao mesmo `source_id` e à mesma montagem por `fiscal_document_links`.

## Montagem e validação XML

Cada build:

1. carrega o XSD publicado vigente;
2. monta XML determinístico para o schema/importador configurado;
3. grava o XML no storage exclusivo do tenant;
4. calcula SHA-256;
5. executa validação local via `lxml.etree.XMLSchema`;
6. persiste erros de validação;
7. bloqueia solicitação de emissão quando o XML não for válido.

A ausência de XSD publicado gera `schema_not_configured`/`blocked_validation`, nunca emissão fictícia.

## Gatilhos de emissão

Gatilhos persistidos e idempotentes:

- `SaleCompleted` → `sale_completed`;
- `ServiceOrderConfirmed` → `service_order_confirmed`;
- `ServiceCompetenceBilled` → `competence`;
- `PaymentConfirmed` → `payment`;
- `ChargeCreated` → `billing`.

`PaymentConfirmed` resolve a cadeia `payment_allocations → installments → financial_contract → service_order`.
`ChargeCreated` usa a origem da cobrança ou o contrato financeiro para localizar o pedido correspondente.

Gatilhos distintos que apontem para o mesmo pedido e mesmo tipo documental **convergem no mesmo documento fiscal**, evitando dupla emissão.

## Cancelamento fiscal e financeiro

A integração financeira não assume globalmente que cancelar documento fiscal significa cancelar cobrança.

`settings.financial_cancel_mode`:

- `link_only` (padrão): registra vínculo e não altera financeiro automaticamente;
- `cancel_unpaid_charge`: se a cobrança não possui pagamento, cancela cobrança/recebível/parcelas abertas e cria lançamento contábil compensatório `fiscal_charge_reversal` referenciando o lançamento original;
- se já existe pagamento confirmado, não apaga nem altera o pagamento: marca `refund_required` e publica `FiscalFinancialRefundRequired` para tratamento de devolução/reembolso.

Repetir o cancelamento não cria segundo lançamento compensatório.

## API

- `GET/POST /api/v1/fiscal/document-schemas`
- `POST /api/v1/fiscal/document-schemas/{schema_id}/publish`
- `GET/POST /api/v1/fiscal/routing-policies`
- `POST /api/v1/fiscal/routing-policies/{policy_id}/publish`
- `GET/POST /api/v1/fiscal/document-assemblies`
- `GET /api/v1/fiscal/document-assemblies/{assembly_id}`
- `GET /api/v1/fiscal/emission-trigger-runs`
- `POST /api/v1/fiscal/emission-trigger-runs/evaluate`

O ciclo de vida posterior de emissão/consulta/cancelamento/substituição/inutilização continua no módulo 0038.

## Interface administrativa

A aba **Roteamento e XML** permite:

- importar/publicar XSD versionado;
- configurar política documental;
- selecionar gatilho;
- filtrar regime e município;
- exigir contrato financeiro;
- definir política financeira de cancelamento;
- montar/splitar documento;
- visualizar SHA-256 e decisão explicável;
- acompanhar/reavaliar gatilhos.

A interface informa explicitamente que pagamento confirmado nunca é apagado por cancelamento fiscal.

## Limites de comprovação

Comprovado localmente:

- roteamento e split;
- snapshots e SHA-256;
- XSD importado/versionado e validação local;
- golden XML técnico;
- gatilhos competência, pagamento e faturamento;
- idempotência entre múltiplos gatilhos;
- vínculo contrato/cobrança;
- estorno compensatório de cobrança não paga;
- pendência de reembolso para cobrança paga;
- isolamento por tenant;
- migration/RLS.

Não comprovado por este incremento:

- homologação oficial SEFAZ/NFS-e;
- validade legal de fixtures XSD/golden;
- produção real;
- certificado/credenciais externos.

Esses itens permanecem dependentes dos providers reais e dos ambientes externos correspondentes.
