# CI e performance de validação

A validação foi separada em dois níveis para evitar PRs presas por muitos minutos instalando dependências gráficas do Tauri no Linux.

## PR rápida

Em `pull_request`, o CI executa:

- validação de título;
- frontend (`typecheck` e `build:web`);
- `cargo fmt --check`.

O job de `rust-format` não instala dependências Linux do Tauri.

## Validação Rust completa

A validação completa com:

- `cargo clippy --all-targets --all-features -- -D warnings`;
- `cargo test --all-targets --all-features`;
- build com `mysql-db`;
- build com `postgres-db`;
- build com `mysql-db,postgres-db`;

roda em:

- push para `main`, `develop` e `release/**`;
- execução manual `workflow_dispatch` com `full_rust_ci=true`.

## Por que não instalar dependências Tauri em toda PR?

No Linux, validar o app Tauri completo exige pacotes como WebKitGTK, AppIndicator e SVG. Esses pacotes são grandes e podem deixar uma PR parada vários minutos antes mesmo de chegar no `clippy`.

Para manter feedback rápido, a PR valida formatação Rust e frontend. A validação Rust completa continua existindo, mas roda nos pontos corretos de integração e release.

## Como corrigir rustfmt localmente

Linux/macOS:

```bash
./scripts/fix-rust-format.sh
```

Windows PowerShell:

```powershell
./scripts/fix-rust-format.ps1
```

Ou diretamente:

```bash
npm run fmt:rust
npm run fmt:rust:check
```
