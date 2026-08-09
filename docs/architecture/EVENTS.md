# Eventos, outbox e consistência

Cada alteração consolidada grava estado e evento na mesma transação. O publisher seleciona eventos sem `published_at`, adiciona contexto assinado do tenant e publica na fila. O consumidor registra inbox/idempotência antes de executar o handler.

## Garantias

- entrega ao menos uma vez;
- handlers idempotentes;
- correlation ID e versão do evento;
- retries com backoff/jitter;
- DLQ e reprocessamento explícito;
- nenhum `tenant_id` confiado diretamente do payload externo;
- fechamento acadêmico/financeiro impede mutação retroativa.

O arquivo `backend/app/worker.py` valida contexto HMAC antes do handler. Celery é dependência de produção preparada, mas não foi baixada no ambiente offline.
