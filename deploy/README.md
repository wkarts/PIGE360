# PIGE360 — Deploy canônico multitenant

Este diretório é o contrato operacional de implantação do PIGE360. Ele adapta o padrão de deploy estudado no Connect|API para a realidade do PIGE360 sem substituir o `compose.yaml` canônico nem duplicar serviços existentes.

## Domínios canônicos

- `console.pige360.com.br` — Control Plane Web.
- `api.pige360.com.br` — API global/Control Plane.
- `ops.pige360.com.br` — Grafana/observabilidade operacional.
- `<tenant>.pige360.com.br` — aplicação administrativa do tenant (`tenant-admin-web`).
- `*.pige360.com.br` — wildcard DNS/TLS que elimina criação de DNS por tenant canônico.
- Domínios próprios de clientes permanecem registrados no Control Plane e podem usar Cloudflare for SaaS ou ACME HTTP-01 no self-hosted.

O tenant é resolvido pelo `Host` no backend. Nunca use `X-Tenant-ID` como seletor público.

## Modos de implantação

### Dockge / Docker Compose com edge próprio

```bash
docker compose --env-file deploy/env/pige360.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  -f deploy/compose/compose.edge.yaml \
  -f deploy/compose/compose.logging.yaml \
  up -d
```

O Traefik atende `80/443`, solicita o certificado wildcard por DNS-01/Cloudflare e encaminha `/api` para a API e o restante para os frontends corretos.

### CloudPanel

```bash
docker compose --env-file deploy/env/pige360.production.env \
  -f compose.yaml \
  -f compose.production.yaml \
  -f deploy/compose/compose.cloudpanel.yaml \
  -f deploy/compose/compose.logging.yaml \
  up -d
```

Neste modo os serviços publicam somente em `127.0.0.1`. O CloudPanel/Nginx termina TLS e usa `deploy/cloudpanel/pige360-vhost.nginx.conf.example` como referência de roteamento.

## Provisionamento de tenant

O Control Plane já cria banco PostgreSQL isolado, role/senha própria, bucket MinIO/S3, migrações e registro em `tenant_domains`. Para tenant canônico, o hostname deve seguir `{tenant}.pige360.com.br`; graças ao wildcard, nenhuma alteração de DNS é necessária a cada escola.

`deploy/provisioning/tenant-contract.yaml` define o fluxo operacional completo e as regras para domínios personalizados.

## Logs e observabilidade

- Aplicações -> OpenTelemetry Collector -> Loki (OTLP nativo).
- stdout/stderr dos containers -> Grafana Alloy -> Loki.
- métricas -> OTel/Prometheus -> Grafana.
- logs de edge em JSON incluem host, rota, status e latência, permitindo recorte por tenant canônico.
- logs estruturados de aplicação devem carregar `tenant_id`, `tenant_code`, `correlation_id`, `service`, `environment` e `request_host` quando disponíveis.

O Docker socket montado no Alloy/Traefik é somente leitura. Em ambientes de maior criticidade, substitua o acesso direto por um socket proxy com allowlist.

## Segredos obrigatórios

Nunca grave tokens reais em YAML ou `.env`. Gere os arquivos em `runtime-secrets/` (ou aponte `PIGE360_SECRETS_DIR`) para JWT, bancos, Redis, RabbitMQ, MinIO, Grafana, Cloudflare, Connect API e demais integrações.

O arquivo `deploy/env/pige360.production.env.example` é copiável, mas não contém credenciais.
