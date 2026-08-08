# Observabilidade

A stack inclui OpenTelemetry Collector, Prometheus, Grafana e Loki. Toda operação deve carregar correlation ID, tenant técnico, módulo, latência e resultado, sem conteúdo sensível.

Health checks:

- `/api/v1/health/live` — processo vivo;
- `/api/v1/health/ready` — storage do plano resolvido;
- Nginx `/healthz`;
- checks nativos de PostgreSQL, Redis, RabbitMQ e MinIO.

Alertas mínimos: erro por domínio, fila/DLQ, atraso de outbox, latência p95, certificado, backup, espaço, falha de login, vazamento de tenant e provider degradado.
