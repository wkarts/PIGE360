# Serviços e NFS-e — rastreabilidade operacional

## Objetivo

Cada item tributável de um pedido de serviço mantém sua intenção fiscal. Quando
uma política fiscal válida monta uma NFS-e para o pedido, o evento do serviço
passa a referenciar o documento e a montagem fiscal que o originaram.

O vínculo funciona para uma NFS-e consolidada: vários itens de serviço podem
apontar para o mesmo documento, sem perder o identificador de cada item de
origem.

## Fluxo local

```text
Pedido de serviço confirmado
  → evento fiscal por item tributável
  → gatilho/política fiscal publicada
  → montagem fiscal e NFS-e local
  → vínculo no evento de serviço
  → estado de entrega do provider refletido no pedido e no evento
```

Os campos `fiscal_document_id` e `fiscal_assembly_id` em
`service_fiscal_events` fornecem a ligação auditável. O painel de Serviços
exibe o identificador do documento quando ele já foi montado.

## Estados relevantes

| Estado | Significado |
| --- | --- |
| `blocked_validation` | classificação fiscal do serviço incompleta; nenhuma NFS-e é solicitada. |
| `emission_requested` | NFS-e montada e vinculada; aguarda o processamento do documento fiscal. |
| `awaiting_provider_configuration` | documento existente, mas provider/certificado ainda não está configurado. |
| `authorized`, `rejected`, `cancelled` | resultado efetivo refletido pelo lifecycle do documento fiscal, inclusive cancelamento local antes da transmissão. |

`not_configured` permanece compatível para eventos criados antes da montagem.
Após a montagem, o estado correto passa a ser acompanhado pelo documento fiscal
vinculado.

## Limites

O vínculo não executa transmissão externa, nem trata uma NFS-e local como
autorizada. Homologação e produção dependem de provider fiscal, credenciais,
certificado e resposta oficial válidos.
