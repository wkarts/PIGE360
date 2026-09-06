# Instalação self-hosted

O instalador preserva o `compose.yaml` canônico e aplica overlays explícitos. Ele
gera somente segredos ausentes, valida a configuração, prepara as imagens, sobe o
grafo de dependências e espera o readiness **dentro dos containers**. A aprovação
exige API, quatro UIs, worker consolidado e Celery Beat; assim, o teste não depende
de uma porta host que só existe no overlay CloudPanel.

Pré-requisitos: Linux, Docker Engine, Docker Compose v2 e espaço para os volumes e
para um backup pré-update. `python3` ou `openssl` é necessário apenas para gerar os
segredos iniciais; `python3` é necessário para backup, restore e update.

## Primeira instalação a partir do fonte

```bash
cp deploy/env/pige360.develop.env.example .env.develop
sh deploy/self-hosted/install.sh --environment develop --mode source --target cloudpanel
```

O modo `source` constrói as bases locais, API, migrations, worker e quatro imagens
web distintas. Usa `npm ci`; `APP_VERSION` nasce do arquivo `VERSION`, enquanto
`PIGE360_IMAGE_TAG` respeita a precedência CLI/variável exportada, `.env` e padrão.
Os exemplos entregues já mantêm os dois valores coerentes.

Targets disponíveis:

- `base`: Compose de produção sem proxy adicional;
- `cloudpanel`: binds em loopback para Nginx/CloudPanel e coleta Alloy;
- `edge`, `dockge` e `portainer`: Traefik/ACME + Alloy. Dockge e Portainer são
  interfaces diferentes sobre o mesmo contrato Compose; não mudam os nomes dos
  volumes.

## Imagens em registry

O registro precisa conter sete imagens da mesma versão: `pige360-api`,
`pige360-migrations`, `pige360-worker`, `pige360-web`,
`pige360-platform-console`, `pige360-branding-studio` e
`pige360-tenant-download-center`.

```bash
export PIGE360_IMAGE_MODE=registry
export PIGE360_IMAGE_REGISTRY=ghcr.io/ORGANIZACAO
sh deploy/self-hosted/build-images.sh --push
sh deploy/self-hosted/install.sh --mode registry --target dockge
```

O App Factory reutiliza a imagem da API com `APP_PROCESS_ROLE` próprio. O install
falha antes de subir serviços se qualquer imagem first-party não puder ser baixada.

`BUILD_FARM_ENABLED=false` é o padrão e o profile Compose `build-farm` não é
ativado pela instalação principal. Isso evita anunciar builds nativos sem agentes.
Linux/Android e os runners Windows/macOS/iOS devem ser provisionados e testados
separadamente antes de habilitar esse profile; eles não bloqueiam a homologação da
plataforma administrativa.

Para homologação pelo canal publicado da branch `develop`:

```bash
cp deploy/env/pige360.develop.env.example .env.develop
sh deploy/self-hosted/install.sh --environment develop --mode registry --target dockge
```

Produção aceita somente imagens `X.Y.Z` estáveis ou referências explícitas
`PIGE360_*_IMAGE=...@sha256:...`. Tags mutáveis como `latest`, `main` e `develop`
são recusadas antes de qualquer pull no ambiente `production`.

## Administrador inicial

Depois que o stack atingir readiness, execute o bootstrap idempotente. Em terminal
interativo, a senha é solicitada sem eco e nunca entra no histórico do shell:

```bash
PIGE360_ENV_FILE=.env.develop \
  sh deploy/self-hosted/bootstrap-admin.sh admin@pige360.argws.com.br
```

Para CI ou provisionamento não interativo, forneça um arquivo temporário protegido
ou stdin; não use variável de ambiente nem argumento de linha de comando para a
senha:

```bash
PIGE360_ENV_FILE=.env.production \
  sh deploy/self-hosted/bootstrap-admin.sh admin@pige360.com.br \
    --password-file /run/secrets/pige360_admin_password
```

## Backup, restore, update e rollback

```bash
sh deploy/self-hosted/backup.sh /srv/backups/pige360/2026-09-04

# Destrutivo: exige confirmação literal e a mesma DATABASE_SECRET_KEY do backup.
sh deploy/self-hosted/restore.sh /srv/backups/pige360/2026-09-04 \
  --confirm RESTORE-PIGE360

sh deploy/self-hosted/update.sh /srv/pige360/releases/NOVA_VERSAO

# Rollback só da aplicação; permitido apenas se o schema for retrocompatível.
sh deploy/self-hosted/rollback.sh /caminho/update-estado.json \
  --application-only --confirm APP-ONLY-COMPATIBLE

# Rollback completo para o backup pré-update.
sh deploy/self-hosted/rollback.sh /caminho/update-estado.json \
  --with-data --confirm RESTORE-PIGE360
```

O backup inclui Control Plane, cada banco PostgreSQL operacional, o volume local
autoritativo dos tenants e o estado atual dos buckets MinIO. Dumps são validados por `pg_restore --list`; manifesto,
inventário exato, tamanhos, SHA-256, catálogo de tenants e fingerprint (não a chave)
da `DATABASE_SECRET_KEY` são verificados antes da promoção. O catálogo é conferido
antes e depois da cópia para detectar provisionamento concorrente.

Limites deliberados do formato v1:

- consistência é por recurso online, não uma transação global entre bancos e S3;
- o snapshot MinIO contém os objetos atuais, não o histórico de versões;
- cache Redis, filas RabbitMQ, métricas, logs e artefatos temporários de build não
  são fontes autoritativas e não integram o formato v1;
- restauração exige a mesma chave de cifragem dos tenants;
- rollback não executa downgrade automático de schema;
- homologação final ainda exige Docker/PostgreSQL/MinIO reais, DNS/TLS, restart,
  restore de ensaio e smoke externo no host de destino.

Não altere ou renomeie volumes entre releases. Migrations são executadas pelo
serviço canônico `pige360-app-init`, incluindo todos os bancos de tenants nos
estados `active`, `degraded` ou `suspended`.
