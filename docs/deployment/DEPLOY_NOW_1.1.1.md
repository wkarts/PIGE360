# PIGE360 1.1.1 — subir agora

Esta entrega possui dois caminhos diferentes e intencionais. Use o modo
`source` para construir no próprio host sem depender do GHCR. Use os diretórios
`deployments/` somente depois que as imagens do canal correspondente tiverem
sido publicadas pelo workflow.

## 1. Homologação imediata a partir do fonte

Pré-requisitos: Linux, Docker Engine, Docker Compose v2, `python3` ou `openssl`,
8 GiB de RAM livres e espaço persistente para os volumes.

```bash
cp deploy/env/pige360.develop.env.example .env.develop
# ajuste domínio, e-mail ACME e integrações opcionais
sh deploy/self-hosted/install.sh \
  --environment develop --mode source --target cloudpanel

PIGE360_ENV_FILE=.env.develop \
  sh deploy/self-hosted/bootstrap-admin.sh admin@seu-dominio.com.br
```

Para Docker Compose sem CloudPanel, troque o target por `base`. Para edge TLS
próprio/Dockge, use `dockge` e preencha o token Cloudflare no arquivo de secret.

## 2. Homologação com imagens da branch `develop`

O workflow `.github/workflows/20-application-images.yml` precisa terminar verde
em um push da branch `develop`. Ele publica primeiro `develop-<sha12>`, promove a
tag `develop` e executa um smoke real do pacote publicado.

Depois, no servidor:

```bash
unzip PIGE360-1.1.1-develop-deployment.zip -d pige360-develop
cd pige360-develop
cp .env.example .env
# ajuste os domínios; se o pacote GHCR for privado, exporte GHCR_USERNAME/TOKEN
./install.sh
./bootstrap-admin.sh admin@seu-dominio.com.br
./healthcheck.sh
```

Para repetir um teste de forma imutável, substitua `PIGE360_IMAGE_TAG=develop`
por `PIGE360_IMAGE_TAG=develop-<sha12>` no `.env`.

## 3. Produção

Produção não aceita `latest`, `main` ou `develop`. O workflow de release deve
publicar as sete imagens da aplicação com a tag SemVer `1.1.1` e concluir seu
smoke antes do go-live.

```bash
unzip PIGE360-1.1.1-production-deployment.zip -d pige360-production
cd pige360-production
cp .env.example .env
# configure domínios/integrações e mantenha PIGE360_IMAGE_TAG=1.1.1
./validate.sh
./install.sh
./bootstrap-admin.sh admin@pige360.com.br
./healthcheck.sh
./backup.sh /srv/backups/pige360/primeiro-backup
```

O gateway é o único serviço publicado e escuta apenas em loopback:

| Ambiente | Projeto Compose | Gateway local | Canal de imagem |
|---|---|---:|---|
| Homologação | `pige360-develop` | `127.0.0.1:48080` | `develop` ou `develop-<sha12>` |
| Produção | `pige360-production` | `127.0.0.1:58080` | `1.1.1` ou digest SHA-256 |

PostgreSQL, Redis, RabbitMQ, MinIO, Prometheus, Grafana e Loki não publicam
portas no host. O proxy externo deve preservar `Host` e `X-Forwarded-Proto`.

## 4. Dockge, CloudPanel e Portainer

- Dockge: extraia `deployments/dockge/<ambiente>` no diretório de stacks, copie
  `.env.example` para `.env` e importe o `compose.yaml` dessa pasta.
- CloudPanel: execute o `install.sh` da pasta
  `deployments/cloudpanel/<ambiente>` e aponte o reverse proxy para o gateway
  loopback informado acima.
- Portainer: use o `stack.yaml` de `deployments/portainer/<ambiente>` mantendo
  junto dele as pastas `config/`, `tools/`, `secrets/` e `volumes/`; não cole
  somente o YAML sem os arquivos auxiliares.

Cada variante contém `validate.sh`, `healthcheck.sh`, `logs.sh`, `update.sh`,
`rollback.sh`, `backup.sh`, `restore.sh` e `GENERATED-MANIFEST.json` com hashes.

## 5. Critério de aceite no servidor

```bash
./validate.sh
./install.sh
./healthcheck.sh
curl -fsS -H 'Host: console.seu-dominio.com.br' http://127.0.0.1:48080/healthz
./backup.sh /srv/backups/pige360/ensaio
```

Depois faça restart do stack, repita o health check e restaure o backup em um
ambiente descartável. DNS, TLS, persistência, backup/restore e integrações reais
só podem ser homologados no host de destino.

## 6. Perfis opcionais

`BUILD_FARM_ENABLED=false` e `OTEL_ENABLED=false` são os padrões. A plataforma
administrativa, API, quatro frontends, workers, scheduler e observabilidade não
dependem deles. Não ative `build-farm` até provisionar os agentes Linux/Android,
as toolchains e os runners nativos Windows/macOS/iOS.
