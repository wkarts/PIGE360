# Recibos de pagamento de serviços

## Objetivo

O recibo comprova um pagamento já confirmado e rateado para a cobrança de um
pedido de serviço. Ele é um documento financeiro interno, persistente e
auditável; não substitui NF-e, NFC-e, NFS-e nem declara autorização fiscal.

## Emissão e vínculo

```text
Pagamento confirmado (financeiro ou PIX)
  → payment_allocations
  → accounts_receivable.charge_id
  → pedido de serviço
  → recibo em PDF, snapshot e SHA-256
```

O vínculo passa por `accounts_receivable.charge_id`, em vez de inferir o pedido
apenas pelo contrato financeiro. Assim, um rateio de pagamento de contrato
recorrente não é atribuído ao pedido de serviço errado.

Um recibo ativo é único por `tenant_id + service_order_id + payment_id`. A
emissão automática é idempotente e também ocorre quando um PIX é confirmado.
O endpoint manual permite recuperar um recibo de pagamento histórico já
confirmado; ele não aceita pagamentos sem rateio para a cobrança do pedido.

## Documento e segurança

- o PDF é gerado no servidor a partir de um snapshot congelado de emitente,
  destinatário, itens, pagamento e valor;
- o arquivo é salvo no object storage privado do tenant e o SHA-256 é
  persistido em `service_receipts.document_sha256`;
- o download autenticado recalcula o hash antes de entregar o PDF e retorna o
  cabeçalho `X-Content-SHA256` para verificação também no painel web;
- a tabela tem RLS por tenant na migration PostgreSQL, auditoria e eventos de
  outbox `ServiceReceiptIssued` e `ServiceReceiptVoided`.

## API

| Operação | Finalidade |
| --- | --- |
| `GET /service-orders/{order_id}/receipt-payments` | pagamentos confirmados elegíveis e recibos ativos. |
| `GET /service-orders/{order_id}/receipts` | recibos preservados, inclusive anulados. |
| `POST /service-orders/{order_id}/receipts` | emissão/reemissão idempotente para um `payment_id` vinculado. |
| `GET /service-receipts/{receipt_id}` | consulta autenticada do recibo. |
| `GET /service-receipts/{receipt_id}/document` | download do PDF com SHA-256. |
| `POST /service-receipts/{receipt_id}/void` | anulação auditável, com motivo obrigatório. |

## Anulação e limites

Anular o recibo não remove o PDF, o snapshot, o rateio, o pagamento nem os
eventos de auditoria. Uma nova emissão para o mesmo pagamento só é permitida
após a anulação do recibo anterior, preservando a trilha completa.

O fluxo não realiza estorno financeiro automaticamente. Estorno, devolução e
cancelamento de cobrança continuam sujeitos aos respectivos fluxos financeiros.
