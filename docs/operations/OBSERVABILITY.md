# Observabilidade

A stack inclui OpenTelemetry Collector, Prometheus, Grafana e Loki. Toda operação deve carregar correlation ID, tenant técnico, módulo, latência e resultado, sem conteúdo sensível.

Health checks:

- `/api/v1/health/live` — processo vivo;
- `/api/v1/health/ready` — readiness global, com retorno `503` quando um requisito crítico não é comprovado;
- `/api/v1/metrics` — métricas Prometheus do processo e das requisições HTTP;
- Nginx `/healthz`;
- checks nativos de PostgreSQL, Redis, RabbitMQ e MinIO.

## Contrato Prometheus

O endpoint `/api/v1/metrics` usa o formato de exposição Prometheus `0.0.4`, não
exige autenticação e continua sujeito à validação de hostname do PIGE360. O scraper
deve enviar um hostname permitido do Control Plane; o endpoint não deve ser
publicado diretamente na internet.

As séries atuais são locais a cada processo da API:

- `pige360_build_info`, com versão e ambiente;
- `pige360_process_start_time_seconds` e `pige360_process_uptime_seconds`;
- `pige360_http_requests_total`, por método e status HTTP;
- `pige360_http_request_duration_seconds`, com contagem e soma por método.

Não são usados labels de caminho, hostname, tenant, usuário ou correlation ID. Isso
mantém a cardinalidade limitada e evita levar identificadores operacionais para o
Prometheus. O endpoint envia `Cache-Control: no-store` e fica fora do OpenAPI
público por ser uma superfície operacional.

## Contrato de readiness

O handler de `/health/live` não executa probes de banco, fila ou storage; os monitores devem
chamá-lo pelo host do Control Plane para medir apenas o processo. `/health/ready` verifica, com timeout e sem
retornar DSN, endpoint, credencial ou texto bruto de driver:

- banco e migration `head` do Control Plane;
- catálogo de tenants ativos;
- banco, migration `head` e storage de cada tenant ativo;
- Redis, RabbitMQ e MinIO/S3 quando habilitados;
- em `production` e `staging`, Redis, RabbitMQ, MinIO/S3, bancos e migrations são sempre críticos.

Em `development` e `testing`, o schema SQLite canônico substitui o Alembic PostgreSQL e as
dependências externas não configuradas não bloqueiam o processo. O timeout é configurado por
`READINESS_TIMEOUT_SECONDS` (de `0.1` a `30`, padrão `3`). Dependências externas podem ser
exigidas localmente com `READINESS_REQUIRE_REDIS`, `READINESS_REQUIRE_RABBITMQ` e
`READINESS_REQUIRE_OBJECT_STORAGE`.

Os probes aceitam substituição em `app.state.readiness_probes`, por nome (`redis`, `rabbitmq`,
`minio`, `tenant_database`, `tenant_storage`) e recebem somente um contexto interno com timeout.
Esse ponto existe para testes determinísticos e adapters futuros; resultado `False`, exceção ou
timeout de um probe crítico produz `not_ready` e HTTP `503`.

## Estados de entrega de eventos deferred

Eventos com efeito externo ou mutação explícita não podem ser encerrados como apenas
`observed`. `WorkflowStartRequested` possui handler local transacional e idempotente. Os eventos
abaixo permanecem sem integração inventada e, enquanto não houver handler/provider real,
seguem `processing -> failed` com retry exponencial do Celery; na oitava entrega vão para o
estado persistido `dead_lettered` no inbox:

- `MailboxProvisionRequested` e `MailboxSuspendRequested`;
- `IntegrationWebhookRequested`;
- `DocumentGenerationRequested`;
- `ChargeCreationRequested`;
- `CalendarEventCreationRequested`;
- `TaskCreationRequested`.

Um evento `dead_lettered` nunca recebe `completed`. Após a instalação de um handler válido, o
mesmo envelope pode ser reapresentado e concluir de forma idempotente. Eventos informativos não
deferred preservam o comportamento legado `observed`, pois não prometem executar efeito colateral.

Alertas mínimos: erro por domínio, fila/DLQ, atraso de outbox, latência p95, certificado, backup, espaço, falha de login, vazamento de tenant e provider degradado.
