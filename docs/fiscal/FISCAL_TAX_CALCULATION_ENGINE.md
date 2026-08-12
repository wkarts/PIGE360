# Motor de cálculo tributário versionado

## Objetivo

O motor fiscal calcula tributos a partir de **regras versionadas e vigentes**, sem embutir alíquotas legais permanentes no código. A resolução considera tenant, contexto fiscal, estabelecimento, operação, tipo de item, regime tributário, modo RTC, vigência e prioridade.

## Tributos suportados pelo motor

- ICMS;
- ICMS-ST;
- FCP;
- IPI;
- PIS;
- COFINS;
- ISS;
- IBS estadual;
- IBS municipal;
- CBS;
- Imposto Seletivo.

Os valores de alíquota, MVA, reduções e demais parâmetros pertencem à **versão da regra**, não ao código do motor.

## Incidências e tratamentos

Cada componente tributário pode usar:

- `taxable`;
- `exempt`;
- `deferred`;
- `suspended`;
- `immune`;
- `non_incident`;
- `zero_rate`;
- `monophase`.

São suportados base da operação, base customizada e base com MVA, redução de base, diferimento, suspensão, valor monofásico por unidade e dedução de tributos previamente calculados (por exemplo, ICMS próprio no cálculo configurado de ICMS-ST).

## Resolução de regra

A precedência é determinada por:

1. `fiscal_context_id`;
2. vigência da versão do contexto;
3. estabelecimento exato ou regra geral;
4. operação exata ou `any`;
5. tipo de item exato ou `any`;
6. regime tributário exato ou `any`;
7. modo RTC exato ou `any`;
8. prioridade;
9. versão e vigência.

Empate real entre conjuntos distintos com a mesma precedência é rejeitado como ambiguidade.

## Snapshot e explicabilidade

Cada simulação persiste:

- entrada completa;
- contexto fiscal e versão;
- conjunto e versão da regra;
- classificação fiscal localizada, quando houver `item_id`;
- passos de cálculo por tributo;
- base, alíquota, valor bruto, diferido, suspenso e devido;
- fonte, SHA-256 e fundamentação informada na versão;
- divergências contra valores esperados opcionais;
- SHA-256 do snapshot do cálculo.

A tabela `fiscal_tax_calculations` é uma trilha de simulação/auditoria. Ela não representa, por si só, autorização de documento fiscal.

## APIs

```text
GET    /api/v1/fiscal/tax-rule-sets
POST   /api/v1/fiscal/tax-rule-sets
GET    /api/v1/fiscal/tax-rule-sets/{rule_set_id}
POST   /api/v1/fiscal/tax-rule-sets/{rule_set_id}/versions
POST   /api/v1/fiscal/tax-rule-sets/{rule_set_id}/versions/{version_id}/publish
POST   /api/v1/fiscal/tax-calculations/simulate
GET    /api/v1/fiscal/tax-calculations/{calculation_id}
```

## Idempotência e consistência

Criação de conjunto, criação/publicação de versão e simulação aceitam chave de idempotência. Alterações usam versão esperada. Versões publicadas com vigência sobreposta no mesmo conjunto são rejeitadas. Auditoria e transactional outbox são gravadas na mesma transação.

Eventos principais:

- `FiscalTaxRuleSetCreated`;
- `FiscalTaxRuleVersionCreated`;
- `FiscalTaxRuleVersionPublished`;
- `FiscalTaxRuleVersionScheduled`;
- `FiscalTaxCalculationCompleted`;
- `FiscalTaxDivergenceDetected`.

## Golden tests

Os testes usam somente fixtures técnicas locais, explicitamente não legais. Eles comprovam a matemática e a seleção versionada do motor, não certificam alíquotas oficiais.

O cenário de produto comprova ICMS, ICMS-ST com MVA e dedução do ICMS próprio, FCP, IPI, PIS, COFINS, IBS estadual, IBS municipal, CBS e Imposto Seletivo com alíquota zero. Outro cenário comprova ISS com redução de base, diferimento, suspensão, monofásico, imunidade, não incidência e detecção de divergência.

## Limites

Ainda não estão incluídos neste incremento:

- retenções;
- DIFAL específico;
- crédito presumido;
- regimes especiais específicos;
- devolução/transferência/importação/exportação como estratégias tributárias dedicadas;
- sincronização online de legislação ou tabelas oficiais;
- homologação fiscal externa.

Esses itens devem ser implementados em incrementos próprios e não são inferidos como concluídos pelo motor genérico.
