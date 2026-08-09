# Primeiro push e primeira execução no GitHub

O repositório é entregue sem executar operações remotas. Os passos abaixo são para o mantenedor executar posteriormente.

## 1. Inicializar e publicar o repositório

```bash
git init
git add .
git commit -m "release: PIGE360 1.0.0"
git branch -M main
git remote add origin <URL_DO_REPOSITORIO>
git push -u origin main
```

Nenhum desses comandos é executado pelos scripts de construção local.

## 2. Primeira CI

O workflow `00-ci.yml` instala Python/Node, instala as dependências frontend e executa `scripts/ci/run-all.sh --ci`. Os demais workflows fazem os builds por plataforma.

Como esta construção offline não pôde gerar um lock npm raiz com `integrity` verificável, o primeiro runner autorizado com rede usará `npm install` com versões diretas fixadas. Depois de validar o resultado, gere e versione o lock raiz:

```bash
rm -rf node_modules
npm install --workspaces --include-workspace-root
npm ci --workspaces --include-workspace-root
npm run validate:ts
npm run build:web
```

## 3. Secrets do GitHub

Somente configure secrets das capacidades que realmente serão usadas. Publicação/deploy continuam bloqueados enquanto `REMOTE_*` permanecer `false`.

Nunca copie `runtime-secrets/`, certificados, keystores, chaves Apple, service accounts ou tokens para o repositório.

## 4. Self-hosted

```bash
cp .env.example .env
bash scripts/local/init-secrets.sh runtime-secrets
docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml build
docker compose -f compose.yaml -f compose.production.yaml up -d
```

Execute backup/restore e healthchecks antes de dados reais.
