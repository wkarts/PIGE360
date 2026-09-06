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
cp deploy/env/pige360.production.env.example .env.production
sh deploy/self-hosted/install.sh --environment production --mode registry --target dockge
```

O Traefik atende `80/443`, solicita o certificado wildcard por DNS-01/Cloudflare e encaminha `/api` para a API e o restante para os frontends corretos.

### CloudPanel

```bash
cp deploy/env/pige360.production.env.example .env.production
sh deploy/self-hosted/install.sh --environment production --mode registry --target cloudpanel
```

Neste modo os serviços publicam somente em `127.0.0.1`. O CloudPanel/Nginx termina TLS e usa `deploy/cloudpanel/pige360-vhost.nginx.conf.example` como referência de roteamento.

## Provisionamento de tenant

O Control Plane já cria banco PostgreSQL isolado, role/senha própria, bucket MinIO/S3, migrações e registro em `tenant_domains`. Para tenant canônico, o hostname deve seguir `{tenant}.pige360.com.br`; graças ao wildcard, nenhuma alteração de DNS é necessária a cada escola.

`deploy/provisioning/tenant-contract.yaml` define o fluxo operacional completo e as regras para domínios personalizados.

## Logs e observabilidade

- stdout/stderr dos containers -> Grafana Alloy -> Loki.
- métricas HTTP reais da API -> Prometheus -> Grafana.
- logs de edge em JSON incluem host, rota, status e latência, permitindo recorte por tenant canônico.
- logs estruturados de aplicação devem carregar `tenant_id`, `tenant_code`, `correlation_id`, `service`, `environment` e `request_host` quando disponíveis.

O collector OpenTelemetry permanece opt-in no profile `otel`. O backend atual não
é anunciado como instrumentado para exportação OTLP; `OTEL_ENABLED=false` é o
padrão até que essa emissão seja implementada e homologada.

A Build Farm também permanece opt-in: `BUILD_FARM_ENABLED=false` e nenhum
`COMPOSE_PROFILES` é definido por padrão. O Control Plane, os quatro frontends,
API, workers, bancos e observabilidade não dependem dos builders. Ative o profile
`build-farm` somente depois de publicar os agentes Linux/Android e provisionar os
runners nativos/toolchains correspondentes.

O Alloy filtra exatamente o label Docker Compose indicado por
`PIGE360_PROJECT_NAME`; cada ambiente deve injetar seu próprio nome no container
para nunca misturar logs de homologação e produção. O Loki local mantém WAL e
retenção operacional de 30 dias (`720h`); backups autoritativos continuam fora
do volume de logs.

O Docker socket montado no Alloy/Traefik é somente leitura. Em ambientes de maior criticidade, substitua o acesso direto por um socket proxy com allowlist.

## Segredos obrigatórios

Nunca grave tokens reais em YAML ou `.env`. Gere os arquivos em `runtime-secrets/` (ou aponte `PIGE360_SECRETS_DIR`) para JWT, bancos, Redis, RabbitMQ, MinIO, Grafana, Cloudflare, Connect API e demais integrações.

`scripts/local/init-secrets.sh` mantém o diretório-fonte em modo `0700` e os
arquivos em `0444`. O modo dos arquivos é deliberado: Docker Compose local monta
secrets baseados em arquivo preservando permissão suficiente para os processos
non-root (`UID 10001`); no host, outros usuários continuam sem atravessar o
diretório `0700`. Para instalar ou rotacionar um token externo sem janela
gravável, crie-o fora da árvore e substitua-o atomicamente:

```bash
temporary="$(mktemp runtime-secrets/.cloudflare_api_token.XXXXXX)"
chmod 0600 "$temporary"
printf '%s' "$TOKEN_EXTERNO" > "$temporary"
chmod 0444 "$temporary"
mv "$temporary" runtime-secrets/cloudflare_api_token.txt
```

Não use `chmod -R 777`, não monte o diretório inteiro no container e nunca
adicione `runtime-secrets/`, `backups/` ou estado operacional ao Git.

O arquivo `deploy/env/pige360.production.env.example` é copiável, mas não contém credenciais.

## Operação e recuperação

Use somente os entrypoints em `deploy/self-hosted/` para install, healthcheck,
backup, restore, update e rollback. Eles preservam o conjunto exato de overlays,
as imagens da versão, o serviço `pige360-app-init`, o catálogo de tenants e os
volumes nomeados. Consulte `docs/deployment/SELF_HOSTED.md` para confirmações
destrutivas, limites de consistência e modos `source`/`registry`.

Depois do primeiro readiness, crie o administrador inicial de forma idempotente:

```bash
PIGE360_ENV_FILE=.env.production \
  sh deploy/self-hosted/bootstrap-admin.sh admin@pige360.com.br
```

Em automação, use `--password-file ARQUIVO` (ou `--password-file -` para stdin);
a senha nunca deve ser gravada no `.env` nem passada como argumento de processo.
