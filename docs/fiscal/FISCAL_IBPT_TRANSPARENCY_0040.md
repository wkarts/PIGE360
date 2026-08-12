# IBPT versionado, fallback local e transparência tributária — 0040

O PIGE360 mantém `tributos_reais` e `tributos_aproximados_ibpt` como fontes distintas. O IBPT é usado somente para transparência (`vTotTrib`) e nunca como motor de cálculo tributário real.

## Perfil por tenant

`fiscal_ibpt_provider_profiles` versiona provider, modo (`disabled`, `local_snapshot`, `remote_sync`), vigência, habilitação de sincronização, obsolescência e fallback. O scheduler global desligado não agenda tenants sem perfil publicado `remote_sync + sync_enabled`.

## Venda sem acesso remoto

A montagem fiscal consulta exclusivamente `ibpt_snapshots` e `ibpt_rates` persistidos. Primeiro usa o snapshot ativo; quando permitido, pode usar o último snapshot superseded dentro da janela de fallback. Nenhuma chamada HTTP ocorre no fluxo de venda.

## Transparência

`fiscal_document_tax_transparency` congela por build/documento:
- `real_taxes_json`: resultado fornecido pelo motor tributário real;
- `approximate_ibpt_json`: percentuais e valores aproximados IBPT;
- `vTotTrib`: total informativo;
- snapshot e SHA-256 de origem no payload IBPT.

O XML genérico local não recebe elementos não previstos pelo XSD. O mapeamento de `vTotTrib` para XML só deve ocorrer quando o XSD oficial versionado declarar o campo aplicável.

## Orientação contábil

As contas de lançamento compensatório fiscal são parametrizadas na própria política versionada de roteamento (`fiscal_reversal_debit_account` e `fiscal_reversal_credit_account`). Não há mais conta contábil obrigatória hardcoded para esse ajuste.

## Manifestação e retry

A manifestação continua utilizando o lifecycle fiscal existente (`FiscalDocumentProviderEventRequested`, `event_type=manifestation`), com idempotência, provider condicional, tentativas, auditoria e outbox. O retry de documento continua usando o fluxo persistente existente; o 0040 não duplica esses agregados.
