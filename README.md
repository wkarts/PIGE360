# PIGE360 — Plataforma Integrada de Gestão Educacional

**Versão de testes: 1.1.2**

PIGE360 é um ERP educacional brasileiro multi-tenant, SaaS/self-hosted e white-label. O monorepo reúne Control Plane, Tenant Plane, API FastAPI, workers Celery/RabbitMQ, aplicações Vue/PWA/Tauri, PostgreSQL por tenant, Redis, MinIO/S3, App Factory, contratos/assinaturas, módulos acadêmicos, financeiros, fiscais, RH, comunicação e serviços ao aluno.

## Estado validado desta árvore

- **599 paths / 742 operações OpenAPI / 403 schemas**, sem `operationId` duplicado;
- regressão backend executada por nós pytest isolados; a contagem e os comandos
  finais ficam em `release/reports/test-report.json`, evitando número histórico
  divergente do pacote;
- migrations separadas para Control Plane e Tenant Plane, com RLS no Tenant Plane;
- reconciliação de migrations para todos os bancos de tenants operacionais no
  `pige360-app-init`;
- tenant resolvido por hostname antes da abertura do store;
- PostgreSQL/SQLAlchemy 2 + `asyncpg` em `production/staging`; SQLite somente em desenvolvimento/testes;
- JWT, lockout persistente, refresh rotativo atômico, revogação/replay, Argon2,
  RBAC/ABAC contextual, auditoria, idempotência e transactional outbox/inbox;
- lifecycle de tenants, quotas, sessões de suporte, usuários globais,
  parceiros, planos, assinaturas manuais, uso/entitlements, agents, providers e
  jobs operacionais no Control Plane;
- planejamento pedagógico e frequência/chamada online/offline com vínculo acadêmico físico;
- financeiro, PIX, vendas, estoque, fiscal, RH/folha/ponto, contratos e assinaturas;
- ICP-Brasil/PAdES e GOV.BR condicionais, sem simular homologação externa;
- Mail/IMAP/SMTP, Cloudflare, Mailcow e Evolution por providers configuráveis;
- Reporting/Analytics, workflows humanos, avisos, solicitações, biblioteca, transporte e saúde;
- Branding Studio, `TenantBrandKit`, App Factory e Central de Downloads;
- **13 aplicações** Vue/PWA instaláveis e fontes Tauri preservadas;
- **49 serviços nomeados** no conjunto base/overlays Compose e **21 workflows
  GitHub Actions**, validados estruturalmente nesta máquina;
- matriz de release para Windows x64/x86, Linux x64/ARM64, macOS Intel/Apple
  Silicon, Web/PWA, CloudPanel x64/x86, Android APK/AAB ARM64 e iOS ARM64
  unsigned, além do agente e dos instaladores PIGE360 Deployer x64;
- OpenAPI + SDK TypeScript, backup/restore/update/rollback, secret scan, SBOM,
  provenance, relatório antes/depois e pacote de release local;
- nenhum container, provider externo ou binário nativo é apresentado como
  homologado sem execução no ambiente correspondente.

## Primeiro uso com Docker

Requisitos: Docker Engine/Compose atual, acesso aos registries/dependências durante o primeiro build e recursos compatíveis com os serviços habilitados.

```bash
git clone <SEU_REPOSITORIO_PIGE360>
cd pige360
cp .env.example .env
sh deploy/self-hosted/install.sh --mode source --target cloudpanel
```

O instalador gera apenas os segredos ausentes, valida o Compose, constrói as
imagens, executa as migrations do Control Plane e dos tenants e aguarda readiness
dentro do container da API. Também existem targets `base`, `edge`, `dockge` e
`portainer`, além do modo `registry`.

Depois, abra o hostname configurado para o Control Plane e execute o bootstrap do
primeiro administrador. O fluxo de provisionamento cria o tenant, domínio lógico,
banco/role PostgreSQL, migrations, storage e proprietário inicial.

Consulte [Instalação self-hosted](docs/deployment/SELF_HOSTED.md) e [Primeiro push no GitHub](docs/deployment/GITHUB_FIRST_RUN.md).

## Implantador integrado

O `tools/pige360-deployer` é o implantador oficial Tauri 2 + Rust + Vue do
monorepo. Ele instala, atualiza e reverte `deployments/develop` e
`deployments/production` nos targets Docker Compose, Dockge, CloudPanel e
Portainer, orquestrando os services operacionais `pige360-*` sem exigir scripts
no host. A cadeia própria do implantador gera somente Linux AMD64 e instaladores
Windows, Linux e macOS Intel x64.

Após a CI verde de `develop`, o workflow `36-develop-prerelease.yml` publica a
pré-release imutável `develop-<sha12>`. A release estável SemVer inclui os quatro
artefatos x64 do implantador na mesma política coordenada da plataforma.

## Desenvolvimento local sem containers

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.lock

npm ci

PYTHONPATH=backend pytest -q backend/tests
npm run validate:ts
python scripts/api/export_openapi.py
python scripts/api/generate_typescript_sdk.py
```

Para desenvolvimento/testes, `Settings.testing()` usa bancos SQLite fisicamente separados por tenant. Isso **não** é o adapter de produção.

## CI local

```bash
bash scripts/ci/run-all.sh --ci --network-used
```

O parâmetro `--network-used` registra explicitamente que a preparação resolveu
dependências pela rede. No GitHub Actions, o modo `--ci` instala pelo lockfile,
audita dependências e executa os 13 bundles Vite/PWA.

## Builds nativos e white-label

Os workflows estão preparados para runners compatíveis:

- Linux/Tauri: runner Linux com Rust/Tauri;
- Windows: runner Windows nativo;
- Android: runner com Android SDK/NDK/Gradle;
- macOS/iOS: runner macOS com Xcode;
- assinatura/publicação: somente quando os respectivos secrets estiverem configurados.

A App Factory mantém builds em `queued` até existir agente compatível. Ausência de toolchain **não** é convertida em sucesso artificial.

A release coordenada só publica quando todos os alvos obrigatórios registram
artefatos finais válidos. Uma falha mantém uma única GitHub Release em draft; a
retomada reconstrói a matriz a partir da mesma tag imutável, sem reaproveitar
silenciosamente artefatos antigos.

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

## Reprodutibilidade e rastreabilidade

O `package-lock.json` v3 é íntegro e o build usa `npm ci`. O ZIP fonte preserva
todos os arquivos JavaScript espelho já existentes, incluindo os 50 `*.vue.js`
recebidos, qualquer novo mirror gerado de componente Vue e os 13 `main.js`; ele
mantém o `mtime` UTC de cada fonte em vez de gravar uma data fixa.
Consulte `docs/operations/PROCESS_AUDIT_AND_CORRECTION.md` e
`docs/operations/BEFORE_AFTER_REPORT.md` para o histórico completo.

## Licença, segurança e operação

- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [Riscos operacionais](docs/operations/RISK_REGISTER.md)
- [Backup/restore](docs/operations/BACKUP_RESTORE.md)
- [Arquitetura](docs/architecture/README.md)
