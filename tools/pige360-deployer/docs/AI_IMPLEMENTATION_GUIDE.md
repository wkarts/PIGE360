# Guia para IA/agente de desenvolvimento

Este documento orienta qualquer IA/agente que adapte este template para um novo projeto.

## Regras obrigatórias

1. Identifique primeiro a stack e a estrutura do projeto.
2. Preserve a arquitetura atual.
3. Não remova recursos existentes sem autorização explícita.
4. Não quebre splash, login e sessão.
5. Preserve o bootstrap aleatório em runtime, a troca obrigatória no primeiro acesso e a remoção do arquivo temporário.
6. Não altere nomes de arquivos centrais sem necessidade.
7. Não quebre commands Rust existentes.
8. Não quebre Vue Router.
9. Não quebre permissões existentes.
10. Não introduza modo escuro na documentação Scalar.
11. Não acople regra de negócio específica ao core do template.
12. Mantenha módulos opcionais ativáveis/desativáveis por configuração.

## Arquivos centrais

```text
src/config/projectConfig.ts
src/config/navigation.ts
src/router/index.ts
src/layouts/AppLayout.vue
src/App.vue
src/services/startup.ts
src/stores/session.ts
src-tauri/src/lib.rs
src-tauri/src/app_state.rs
src-tauri/src/migrations.rs
src-tauri/src/commands/*
```

## Como adicionar um módulo específico do projeto

1. Crie páginas em `src/pages` ou subdiretório específico.
2. Crie serviços em `src/services`.
3. Crie commands Rust em `src-tauri/src/commands`.
4. Registre o command em `src-tauri/src/lib.rs`.
5. Adicione rota em `src/router/index.ts`.
6. Adicione item no menu em `src/config/navigation.ts`.
7. Adicione feature flag em `src/config/projectConfig.ts`, se for opcional.
8. Respeite permissões.

## O que não fazer

- Não mover regra de negócio crítica para Vue se ela pertence ao Rust/core.
- Não salvar tokens e senhas em texto puro sem proteção.
- Não criar dashboard com dados falsos fixos.
- Não remover validações para passar build.
- Não substituir o fluxo de sessão por lógica local improvisada.
- Não misturar API interna com integrações externas.

## Validações obrigatórias

```bash
npm run typecheck
npm run build:web
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings
```

Quando possível, também executar:

```bash
npm run tauri:build
cargo test --manifest-path src-tauri/Cargo.toml --all-targets --all-features
```

## Direção correta

O core deve ser reaproveitável. O projeto específico deve ser plugável.

```text
Core do template: autenticação, sessão, empresas, usuários, perfis, permissões, logs, branding, splash, layout, features.
Projeto específico: telas próprias, endpoints próprios, integrações próprias, relatórios próprios, regras próprias.
```


## Validação Rust obrigatória

Antes de entregar alterações, execute os scripts de validação descritos em `docs/RUST_FORMATTING_AND_CI.md`. Não remova `cargo fmt --check`, não mascare warnings do Clippy e não substitua validações por comandos que sempre passam.

A transição multi-banco deve respeitar `docs/DATABASE_PROVIDER.md`: CRUD antigo preservado, provider iniciado e Firebird fora do escopo funcional.


## Validação local obrigatória da Etapa 2.4.1

Antes de abrir PR ou pedir revisão, execute:

```bash
npm install --no-audit --no-fund
npm run ci:version
npm run typecheck
npm run build:web
npm run fmt:rust
npm run fmt:rust:check
npm run lint:rust
npm run test:rust
npm run validate:all
```

Para corrigir formatação Rust automaticamente:

```bash
./scripts/fix-rust-format.sh
```

No Windows/PowerShell:

```powershell
./scripts/fix-rust-format.ps1
```

Para ativar o hook local de pré-commit:

```bash
git config core.hooksPath .githooks
```

O hook não substitui o CI. Ele apenas evita commits com TypeScript quebrado ou Rust fora do `rustfmt`.


## Validação rápida e CI

A validação de PR foi otimizada para separar `cargo fmt --check` das etapas mais pesadas de Rust/Tauri. Use também `docs/CI_PERFORMANCE.md`.

Comandos principais:

```bash
npm run fmt:rust
npm run fmt:rust:check
npm run validate:all
```

Para corrigir formatação Rust automaticamente:

```bash
./scripts/fix-rust-format.sh
```

No Windows PowerShell:

```powershell
./scripts/fix-rust-format.ps1
```

Hook local recomendado:

```bash
git config core.hooksPath .githooks
```

## Regras obrigatórias de CI para agentes

Antes de entregar alterações neste template, o agente deve executar ou orientar explicitamente a execução de:

```bash
npm run fmt:rust
npm run fmt:rust:check
npm run validate:web
```

Quando houver Cargo disponível:

```bash
npm run validate:all
```

Nunca substitua `cargo fmt --check` por comando que sempre passa. O correto é formatar com `npm run fmt:rust` e depois validar com `npm run fmt:rust:check`.

O hook local deve ser preservado:

```bash
git config core.hooksPath .githooks
```

Firebird permanece fora do escopo funcional neste template.
