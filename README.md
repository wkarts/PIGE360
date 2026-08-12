# PIGE360 — Plataforma Integrada de Gestão Educacional

**Versão: 1.0.0**

PIGE360 é um ERP educacional brasileiro multi-tenant, SaaS/self-hosted e white-label. O monorepo reúne Control Plane, Tenant Plane, API FastAPI, workers Celery/RabbitMQ, aplicações Vue/PWA/Tauri, PostgreSQL por tenant, Redis, MinIO/S3, App Factory, contratos/assinaturas, módulos acadêmicos, financeiros, fiscais, RH, comunicação e serviços ao aluno.

## Estado validado desta árvore

- **559 paths / 689 operações OpenAPI / 375 schemas**, sem `operationId` duplicado;
- **98 testes backend aprovados** em três shards isolados (33/33, 33/33 e 32/32);
- migrations separadas para Control Plane e Tenant Plane, com RLS no Tenant Plane;
- tenant resolvido por hostname antes da abertura do store;
- PostgreSQL/SQLAlchemy 2 + `asyncpg` em `production/staging`; SQLite somente em desenvolvimento/testes;
- JWT, refresh rotativo, Argon2, RBAC/ABAC contextual, auditoria, idempotência, transactional outbox/inbox;
- planejamento pedagógico e frequência/chamada online/offline com vínculo acadêmico físico;
- financeiro, PIX, vendas, estoque, fiscal, RH/folha/ponto, contratos e assinaturas;
- ICP-Brasil/PAdES e GOV.BR condicionais, sem simular homologação externa;
- Mail/IMAP/SMTP, Cloudflare, Mailcow e Evolution por providers configuráveis;
- Reporting/Analytics, workflows humanos, avisos, solicitações, biblioteca, transporte e saúde;
- Branding Studio, `TenantBrandKit`, App Factory e Central de Downloads;
- **13 aplicações** Vue/PWA e fontes Tauri;
- **46 serviços Compose** e **15 workflows GitHub Actions**;
- OpenAPI + SDK TypeScript, backup/restore, secret scan, SBOM, provenance e pacote de release local.

## Primeiro uso com Docker

Requisitos: Docker Engine/Compose atual, acesso aos registries/dependências durante o primeiro build e recursos compatíveis com os serviços habilitados.

```bash
git clone <SEU_REPOSITORIO_PIGE360>
cd pige360
cp .env.example .env
bash scripts/local/init-secrets.sh runtime-secrets

docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml build
docker compose -f compose.yaml -f compose.production.yaml up -d
```

Depois, abra o hostname configurado para o Control Plane e execute o bootstrap do primeiro administrador. O fluxo de provisionamento cria o tenant, domínio lógico, banco/role PostgreSQL, migrations, storage e proprietário inicial.

Consulte [Instalação self-hosted](docs/deployment/SELF_HOSTED.md) e [Primeiro push no GitHub](docs/deployment/GITHUB_FIRST_RUN.md).

## Desenvolvimento local sem containers

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.lock

# Sem lockfile raiz válido, este script usa npm install com as versões diretas fixadas.
bash scripts/frontend/install-dependencies.sh

PYTHONPATH=backend pytest -q backend/tests
npm run validate:ts
python scripts/api/export_openapi.py
python scripts/api/generate_typescript_sdk.py
```

Para desenvolvimento/testes, `Settings.testing()` usa bancos SQLite fisicamente separados por tenant. Isso **não** é o adapter de produção.

## CI local

```bash
bash scripts/ci/run-all.sh
```

No GitHub Actions, `bash scripts/ci/run-all.sh --ci` também instala as dependências frontend e executa os bundles Vite.

## Builds nativos e white-label

Os workflows estão preparados para runners compatíveis:

- Linux/Tauri: runner Linux com Rust/Tauri;
- Windows: runner Windows nativo;
- Android: runner com Android SDK/NDK/Gradle;
- macOS/iOS: runner macOS com Xcode;
- assinatura/publicação: somente quando os respectivos secrets estiverem configurados.

A App Factory mantém builds em `queued` até existir agente compatível. Ausência de toolchain **não** é convertida em sucesso artificial.

## Segurança e publicação remota

Por padrão:

```dotenv
REMOTE_CI_ENABLED=false
REMOTE_REGISTRY_ENABLED=false
REMOTE_RELEASE_ENABLED=false
REMOTE_DEPLOY_ENABLED=false
INTEGRATION_REMOTE_ENABLED=false
```

Nenhum secret real deve ser versionado. Use Docker Secrets/secret manager do runner.

## Reprodutibilidade npm

Esta construção local foi produzida sem acesso de rede e o cache npm disponível não continha todos os tarballs Vue/Vite. Por isso, um `package-lock.json` raiz com `integrity` verificado **não foi fabricado**. O instalador usa `npm ci` quando um lock raiz íntegro existir; caso contrário usa `npm install` com versões diretas fixadas. Em um ambiente autorizado com rede, gere e versione o lock raiz antes de exigir builds herméticos.

## Licença, segurança e operação

- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [Riscos operacionais](docs/operations/RISK_REGISTER.md)
- [Backup/restore](docs/operations/BACKUP_RESTORE.md)
- [Arquitetura](docs/architecture/README.md)
