# Catálogos e classificações fiscais versionados

## Escopo implementado

O tenant mantém catálogos fiscais independentes para NCM, NBS, LC 116, CFOP, CEST, CST, CSOSN, CST IBS/CBS, cClassTrib e cBenef. O conteúdo legal não é hardcoded: cada versão registra fonte, referência, hash SHA-256, vigência, schema e entradas normalizadas.

A classificação relaciona contexto fiscal, estabelecimento, tipo e item opcional, operação, vigência e prioridade. Códigos de catálogo são aceitos apenas quando existem em versão publicada e vigente para a data inicial da regra.

## Estados

Catálogo: `active | inactive | archived`.

Versão: `draft | scheduled | published | superseded | archived`.

Regra: `draft | published | archived`. Regra publicada é imutável; alteração material exige nova regra temporal.

## Prontidão

`GET /api/v1/fiscal/readiness` calcula prontidão por contexto/estabelecimento/data/operação. Produtos exigem NCM e CST ou CSOSN conforme regime. Serviços exigem NBS, LC 116 e código municipal. Quando o modo RTC é `optional_emit` ou `required_emit`, CST IBS/CBS e cClassTrib também são exigidos.

## Limite honesto

Este incremento não implementa download/sincronização automática de cada fonte oficial. A infraestrutura versionada para receber e publicar snapshots está pronta, mas os sincronizadores específicos continuam pendentes e não são marcados `VERIFIED`.
