# Rust formatting, Clippy e validação local

Esta etapa torna obrigatório formatar Rust antes do CI e impede que código fora do `rustfmt` seja aceito.

## Scripts locais

Execute sempre antes de abrir PR:

```bash
npm install --no-audit --no-fund
npm run ci:version
npm run typecheck
npm run build:web
npm run fmt:rust
npm run fmt:rust:check
npm run lint:rust
npm run test:rust
```

Quando usar drivers externos:

```bash
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db
cargo build --manifest-path src-tauri/Cargo.toml --features postgres-db
cargo build --manifest-path src-tauri/Cargo.toml --features mysql-db,postgres-db
```

## Regras

- Não substituir `cargo fmt --check` por comando que sempre passa.
- Não mascarar warnings do Clippy.
- Não remover `-D warnings`.
- Não remover validações do workflow.
- Corrigir a origem do problema em vez de relaxar o CI.
- Manter Firebird fora do escopo funcional.

## Ordem recomendada

1. `npm run fmt:rust`
2. `npm run fmt:rust:check`
3. `npm run lint:rust`
4. `npm run test:rust`
5. builds por feature, quando aplicável.

## Para IA/agente

Antes de entregar alterações Rust, a IA deve procurar diffs de formatação e garantir que o código esteja compatível com `rustfmt`. Quando não houver `cargo` no ambiente, a resposta deve informar isso claramente e não afirmar validação que não foi executada.
