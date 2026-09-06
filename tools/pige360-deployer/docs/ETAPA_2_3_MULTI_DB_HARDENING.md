# Etapa 2.3 — Multi-banco, Firebird fora do escopo e proteção da documentação da API

## Escopo aplicado

Esta etapa mantém o desktop Tauri atual intacto e reforça os recursos backend sem acoplar regra de negócio ao frontend.

## Bancos de dados

- **SQLite**: banco principal funcional do desktop e padrão para novos projetos. Todos os CRUDs atuais continuam usando SQLite.
- **MySQL/MariaDB**: possui health check e migrations equivalentes ao schema SQLite central quando o binário Rust é compilado com `--features mysql-db`.
- **PostgreSQL**: possui health check e migrations equivalentes ao schema SQLite central quando o binário Rust é compilado com `--features postgres-db`.
- **Firebird**: permanece fora do escopo funcional por compatibilidade nesta etapa.

## Importante sobre CRUDs

MySQL/MariaDB e PostgreSQL já têm conexão, health check e migrations por feature. Porém o desktop ainda mantém SQLite como banco principal operacional. Para transformar MySQL/PostgreSQL no banco principal de todos os CRUDs, a próxima etapa precisa implementar uma camada de repositórios/abstração de queries para substituir os acessos diretos atuais ao `rusqlite`.

## Segurança da API interna

Quando `requireToken=true`, os endpoints `/docs` e `/openapi.json` também são protegidos por token, exceto se `PIGE360_DEPLOYER_API_DOCS_PUBLIC=true` for configurado explicitamente.

Headers padrão:

```text
X-App-Token: <token>
```

Variáveis relevantes:

```text
PIGE360_DEPLOYER_API_REQUIRE_TOKEN=true
# PIGE360_DEPLOYER_API_TOKEN deve ser fornecido via secret/variável de ambiente segura.
PIGE360_DEPLOYER_API_TOKEN_HEADER=X-App-Token
PIGE360_DEPLOYER_API_EXPOSE_DOCS=true
PIGE360_DEPLOYER_API_DOCS_PUBLIC=false
PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK=false
```

## Validação esperada em ambiente com toolchain

```bash
npm run typecheck
npm run build:web
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml --all-targets --all-features
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db
cargo build --manifest-path src-tauri/Cargo.toml --features postgres-db
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db,postgres-db
```
