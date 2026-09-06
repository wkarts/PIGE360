# Etapa 2 funcional — PIGE360 Deployer Tauri 0.1.8

Esta etapa converteu os principais placeholders da versão professional em implementação funcional mínima e extensível, preservando o desktop Tauri atual.

## Implementado

- Versão sincronizada para `0.1.8` em `VERSION`, `package.json`, `Cargo.toml`, `tauri.conf.json`, `projectConfig.ts`, `brand.json`, `README.md` e `CHANGELOG.md`.
- API interna real com Axum:
  - `GET /health`
  - `GET /version`
  - `GET /status`
  - `GET /app/meta`
  - `GET /features`
  - `GET /logs`
  - `GET /openapi.json`
  - `GET /docs`
- Scalar em tema claro fixo.
- Runtime modes:
  - `desktop`
  - `headless-api`
  - `cli`
  - `worker`
- Parsing de argumentos:
  - `--mode=desktop`
  - `--mode=headless-api`
  - `--mode=cli`
  - `--mode=worker`
  - `--host=127.0.0.1`
  - `--port=61001`
  - `--database-driver=sqlite`
  - `--data-dir=/caminho/dados`
- Scripts auxiliares:
  - `npm run tauri:server`
  - `npm run tauri:cli`
  - `npm run tauri:worker`
- Banco multi-driver:
  - SQLite funcional preservado.
  - MySQL e PostgreSQL com configuração, health check e migrations iniciais por feature Rust; Firebird ignorado nesta etapa.
- Migrations ampliadas:
  - `feature_flags`
  - `integration_configs`
  - `integration_logs`
  - `api_tokens`
- Integrações externas funcionais:
  - cadastro
  - URL base
  - headers
  - token protegido com criptografia local
  - teste de conexão
  - logs de requisição
  - status ativo/inativo
- Tray Tauri 2:
  - restaurar janela
  - sair definitivamente
  - status da API interna no menu
- Comandos preparados de serviço Windows:
  - install
  - uninstall
  - start
  - stop
  - restart
  - status
- Impressão/preview em janela própria via `WebviewWindow`.
- Dashboard com dados reais adicionais:
  - logs de erro hoje
  - status do banco
  - status API interna
  - integrações totais/ativas

## Limitações honestas

- MySQL e PostgreSQL possuem conexão real por features Rust. Firebird foi ignorado nesta etapa por compatibilidade.
- Serviço Windows implementado via `sc.exe` na Etapa 2.2.
- A validação completa depende de ambiente com Node/npm dependências instaladas e toolchain Rust/Cargo.

## Validação neste ambiente

- `npm run typecheck`: não executou porque `vue-tsc` não está instalado no ambiente atual.
- `cargo fmt`, `cargo clippy`, `cargo test`: não executaram porque `cargo` não existe no ambiente atual.
- Arquivos compactados foram gerados e testados com `unzip -t` e `tar -tzf`.
