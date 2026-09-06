# Etapa 2.2 — Multi-banco, serviços e API controlável

Esta etapa transforma os recursos preparados da Etapa 2.1 em implementações reais mínimas e seguras.

## Banco de dados

SQLite continua sendo o padrão e permanece obrigatório para o desktop local.

MySQL/MariaDB e PostgreSQL foram adicionados como suporte real por feature Rust:

```bash
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db
cargo build --manifest-path src-tauri/Cargo.toml --features postgres-db
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db,postgres-db
```

Variáveis aceitas:

```bash
PIGE360_DEPLOYER_DB_HOST=127.0.0.1
PIGE360_DEPLOYER_DB_PORT=3306
PIGE360_DEPLOYER_DB_DATABASE=pige360_deployer
PIGE360_DEPLOYER_DB_USERNAME=root
PIGE360_DEPLOYER_DB_PASSWORD=senha
```

Ou prefixos específicos:

```bash
PIGE360_DEPLOYER_MYSQL_HOST=127.0.0.1
PIGE360_DEPLOYER_MYSQL_PORT=3306
PIGE360_DEPLOYER_MYSQL_DATABASE=pige360_deployer
PIGE360_DEPLOYER_MYSQL_USERNAME=root
PIGE360_DEPLOYER_MYSQL_PASSWORD=senha

PIGE360_DEPLOYER_POSTGRES_HOST=127.0.0.1
PIGE360_DEPLOYER_POSTGRES_PORT=5432
PIGE360_DEPLOYER_POSTGRES_DATABASE=pige360_deployer
PIGE360_DEPLOYER_POSTGRES_USERNAME=postgres
PIGE360_DEPLOYER_POSTGRES_PASSWORD=senha
```

Firebird foi intencionalmente ignorado nesta etapa por compatibilidade.

## Headless/API

Exemplo:

```bash
cargo run --manifest-path src-tauri/Cargo.toml -- --mode=headless-api --host 127.0.0.1 --port 61001
```

Com MySQL:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --features mysql-db -- --mode=headless-api --database-driver mysql
```

Com PostgreSQL:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --features postgres-db -- --mode=headless-api --database-driver postgres
```

## API controlável pelo desktop

Comandos Tauri adicionados:

```text
internal_api_status
internal_api_start
internal_api_stop
internal_api_restart
```

A API respeita segurança por token, bind host, CORS e exposição da documentação.

## Serviço Windows

Os comandos agora executam `sc.exe` em Windows:

```text
app_service_install
app_service_uninstall
app_service_start
app_service_stop
app_service_restart
app_service_status
```

O serviço instala o executável atual com `--mode=headless-api`.

## Serviço Linux/systemd

Em Linux, os comandos usam systemd e criam/removem uma unit em `/etc/systemd/system`.

Requer permissão administrativa.

## Impressão

`openReportPreview(html, title)` abre uma janela independente via `WebviewWindow` usando o HTML real recebido.
