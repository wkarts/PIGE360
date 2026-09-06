# Validação local final — PIGE360 1.1.2

Este documento separa tres classes de evidencia. Um resultado local ou estrutural nao e promovido a homologacao externa.

## Testes executados localmente

- Status da CI local: **passed**.
- Verificacoes registradas: **23**.
- Pytest: **371 aprovados**, conforme `release/reports/test-report.json`.
- Frontend de producao: **passed**, conforme o comando `frontend-build` do relatorio local.
- OpenAPI: **599 paths, 742 operacoes e 403 schemas**.
- Aplicacoes descobertas na arvore: **13**.

## Validacoes estruturais

- Compose principal: **46 servicos declarados**; isto nao prova que os containers iniciam.
- OCI: **13 descritores**, incluindo `pige360-ops`; status `structural_only`, `runtime_executable=false`.
- Deployments standalone: **8 variantes aprovadas**, com 59 services por ambiente e sem bind mounts relativos.
- Pacotes canônicos: **5 arquivos por ambiente**, sem scripts auxiliares obrigatórios.
- Visual: **40 superficies e 132 registros de baseline**; regressao pixel-a-pixel executada: **false**.
- Workflows descobertos na arvore: **19**.

## Teste sintetico de backup/restore

O resultado `passed` cobre tenants sinteticos em SQLite e filesystem local. Ele nao homologa restore de PostgreSQL nem de MinIO (`postgresql_restore_homologated=false`, `minio_restore_homologated=false`).

## Homologacao externa

Nao foi inferida de testes locais. Docker/Podman, PostgreSQL/Redis/RabbitMQ/MinIO reais, DNS/TLS, CloudPanel/Dockge, providers externos, lojas, assinatura e binarios nativos exigem seus ambientes e protocolos proprios.

## Ledger V8 recalculado

Foram recontados **4031** registros diretamente de `requirements`, sem confiar no resumo em cache.

| Estado | Quantidade |
|---|---:|
| BLOCKED_EXTERNAL | 2 |
| IMPLEMENTED | 262 |
| IMPLEMENTING | 2 |
| NOT_STARTED | 3206 |
| TESTING | 36 |
| VERIFIED | 523 |

Cache do ledger consistente com os registros: **true**.

## Preservação da base

- Fontes de aplicação removidos: **0**. As remoções desta entrega são cópias de scripts/configurações dos deployments 1.1.1, substituídas pelos services.
- `*.vue.js`: **52** presentes.
- `apps/*/src/main.js`: **13** presentes.
- Relatorio rastreavel: `docs/operations/BEFORE_AFTER_REPORT.json`.

## Rede e origem

Uso de rede registrado pelos relatórios desta execução. Isso não implica deploy, publicação ou homologação externa.

A revisao `9fa139bc20fc2f7173ffd2f07c78673e36e6090f` foi lida do comentario do ZIP-base e nao e apresentada como checkout Git verificado.
