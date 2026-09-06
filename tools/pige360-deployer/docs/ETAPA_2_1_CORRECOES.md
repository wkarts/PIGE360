# Etapa 2.1 — Correções funcionais obrigatórias

Esta etapa corrige a versão 0.1.8 da base profissional do PIGE360 Deployer Tauri sem remover o fluxo desktop existente.

## Correções aplicadas

- Versão interna sincronizada para `0.1.8` em arquivos principais e branding.
- `getBootstrap()` exportado em `src/services/crud.ts` chamando o command `app_bootstrap`.
- `trayConfig`, `startupConfig` e `integrationsConfig` exportados em `projectConfig.ts`.
- `EntityFieldType` passou a aceitar `time`, preservando o tratamento existente em `EntityPage.vue`.
- API interna passou a validar:
  - `requireToken`;
  - `tokenHeader`;
  - token via `PIGE360_DEPLOYER_API_TOKEN`;
  - bloqueio de `0.0.0.0` quando `allowPublicNetwork=false`;
  - `corsEnabled`;
  - `exposeDocs`.
- `/docs` e `/openapi.json` só são registrados quando `exposeDocs=true`.
- Scalar usa tema claro fixo por CSS e não depende do tema visual da aplicação.
- Tray respeita desativação por variável/configuração de runtime e não é criado quando `PIGE360_DEPLOYER_TRAY_ENABLED=false`.
- Fechamento para tray é controlado por `PIGE360_DEPLOYER_TRAY_CLOSE_TO_TRAY=true`.
- Preview de impressão agora recebe e renderiza HTML real em janela independente.
- Comandos de serviço Windows executam `sc.exe`; em Linux, a Etapa 2.2 usa `systemd`.
- Mensagens sobre MySQL/PostgreSQL/Firebird foram ajustadas para não vender recurso externo como funcional completo.

## Configurações de ambiente relevantes

```bash
PIGE360_DEPLOYER_API_HOST=127.0.0.1
PIGE360_DEPLOYER_API_PORT=61001
PIGE360_DEPLOYER_API_REQUIRE_TOKEN=true
# PIGE360_DEPLOYER_API_TOKEN deve ser fornecido via secret/variável de ambiente segura.
PIGE360_DEPLOYER_API_TOKEN_HEADER=X-App-Token
PIGE360_DEPLOYER_API_ALLOW_PUBLIC_NETWORK=false
PIGE360_DEPLOYER_API_CORS=false
PIGE360_DEPLOYER_API_EXPOSE_DOCS=true
PIGE360_DEPLOYER_TRAY_ENABLED=true
PIGE360_DEPLOYER_TRAY_CLOSE_TO_TRAY=false
```

## Validação executada neste ambiente

Executado com sucesso:

```bash
npm install
npm run typecheck
npm run build:web
```

Não executado por ausência de `cargo` no ambiente:

```bash
npm run tauri:build
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml --all-targets --all-features
```

O erro observado foi ausência do binário `cargo`, não erro do código:

```text
failed to run command cargo metadata --no-deps --format-version 1: No such file or directory
bash: cargo: command not found
```
