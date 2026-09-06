# Bancos de dados

## Estado funcional atual

- **SQLite** é o banco principal funcional do desktop e segue como padrão para novos projetos.
- **MySQL/MariaDB** possui conexão real, health check e migrations centrais quando compilado com `--features mysql-db`.
- **PostgreSQL** possui conexão real, health check e migrations centrais quando compilado com `--features postgres-db`.
- **Firebird** está fora do escopo funcional por compatibilidade nesta etapa.

## Limite arquitetural atual

Os CRUDs atuais do desktop ainda usam a camada SQLite existente. MySQL/MariaDB e PostgreSQL estão preparados no backend para conexão, health check e criação do schema central, mas transformar esses drivers no banco principal de todos os CRUDs exige a próxima etapa: uma camada de repositórios/abstração de queries para substituir o uso direto de `rusqlite` nas regras atuais.

## Features Rust

```bash
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db
cargo build --manifest-path src-tauri/Cargo.toml --features postgres-db
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db,postgres-db
```

## Variáveis de ambiente

### SQLite

```text
PIGE360_DEPLOYER_DATABASE_DRIVER=sqlite
PIGE360_DEPLOYER_SQLITE_PATH=app.db
```

### MySQL/MariaDB

```text
PIGE360_DEPLOYER_DATABASE_DRIVER=mysql
PIGE360_DEPLOYER_MYSQL_HOST=127.0.0.1
PIGE360_DEPLOYER_MYSQL_PORT=3306
PIGE360_DEPLOYER_MYSQL_DATABASE=pige360_deployer
PIGE360_DEPLOYER_MYSQL_USERNAME=root
PIGE360_DEPLOYER_MYSQL_PASSWORD=
```

### PostgreSQL

```text
PIGE360_DEPLOYER_DATABASE_DRIVER=postgres
PIGE360_DEPLOYER_POSTGRES_HOST=127.0.0.1
PIGE360_DEPLOYER_POSTGRES_PORT=5432
PIGE360_DEPLOYER_POSTGRES_DATABASE=pige360_deployer
PIGE360_DEPLOYER_POSTGRES_USERNAME=postgres
PIGE360_DEPLOYER_POSTGRES_PASSWORD=
```

## Schema central migrado para MySQL/PostgreSQL

As migrations externas criam as tabelas centrais equivalentes ao SQLite:

- `empresas`
- `usuarios`
- `perfis_acesso`
- `perfis_permissoes`
- `usuarios_perfis`
- `usuarios_empresas`
- `user_sessions`
- `departamentos`
- `funcoes`
- `centro_custos`
- `clientes`
- `fornecedores`
- `produtos`
- `audit_logs`
- `sync_queue`
- `app_settings`
- `app_logs`
- `admin_guard`
- `admin_unlock_sessions`
- `local_licenses`
- `feature_flags`
- `integration_configs`
- `integration_logs`
- `api_tokens`
- `configuracoes`
