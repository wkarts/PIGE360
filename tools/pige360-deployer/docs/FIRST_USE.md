# Primeiro uso do PIGE360 Deployer Tauri

Este template é uma base corporativa genérica para novas aplicações desktop com Tauri 2, Rust, Vue 3, TypeScript, SQLite, Pinia e Vue Router.

## 1. Criar um novo projeto a partir do template

1. Copie o diretório do template para o novo repositório.
2. Remova o histórico antigo, se necessário.
3. Atualize `README.md`, `VERSION`, `package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json` e `release.config.mjs`.
4. Revise `src/config/projectConfig.ts` para ativar somente os módulos necessários.
5. Execute validações antes do primeiro commit.

## 2. Renomear a aplicação

Atualize:

- `package.json`: `name`, `version` e scripts se necessário.
- `src-tauri/Cargo.toml`: `package.name`, `version`, `description` e `authors`.
- `src-tauri/tauri.conf.json`: `productName`, `identifier`, `version`, `app.windows[].title`.
- `src/config/projectConfig.ts`: `projectConfig.app.name`, `shortName`, `identifier`, `developer` e `version`.
- `README.md` e `VERSION`.
- `release.config.mjs`: prefixos e nomes de release.

## 3. Substituir branding e assets

Substitua mantendo os mesmos nomes quando possível:

```text
src/assets/branding/logo.svg
src/assets/branding/logo-mark.svg
src/assets/branding/logo-light.png
src/assets/branding/logo-dark.png
src/assets/branding/logo-mark.png
src/assets/branding/splash-logo.png
src/assets/branding/favicon.png
src/assets/branding/favicon.ico
src/assets/branding/tray-icon.png
src/assets/branding/tray-icon.ico
src/assets/branding/app-icon-*.png
src/assets/branding/brand.json
src-tauri/icons/*
```

Depois revise:

```text
index.html
package.json
src-tauri/tauri.conf.json
README.md
VERSION
release.config.mjs
```

## 4. Credencial inicial obrigatória

O primeiro startup cria o usuário `admin` e uma senha aleatória de 32 caracteres. A credencial
temporária é registrada apenas em `.bootstrap-admin.local`, dentro do diretório canônico de dados,
com permissão privada quando suportada pelo sistema. A interface não exibe credenciais padrão.

O acesso fica restrito à rota de primeiro acesso até a definição de uma senha forte. Após a troca,
o arquivo temporário é removido. Em migrações, usuários e hashes de senha existentes são
preservados e a credencial bootstrap obsoleta é descartada.

## 5. Módulos opcionais

A ativação/ocultação de módulos fica em:

```text
src/config/projectConfig.ts
```

Principais flags:

- `licensing`
- `about`
- `userGuide`
- `logs`
- `systemSettings`
- `genericEntities`
- `technicalSheet`
- `sync`
- `internalApi`
- `scalarDocs`
- `databaseSettings`
- `integrations`
- `tray`
- `windowsService`
- `linuxService`
- `autoStartWithWindows`
- `headlessMode`

Quando um módulo está desativado, o menu não aparece e a rota é bloqueada pelo router.

## 6. Menus e módulos ativos

O menu é configurado em:

```text
src/config/navigation.ts
```

A separação padrão é:

- Core
- Aplicação
- Ferramentas
- Documentação

Cadastros genéricos permanecem como herança opcional e só aparecem se `genericEntities` estiver ativo.

## 7. API interna

A API interna é opcional. Configure em:

```text
src/config/projectConfig.ts
```

Configuração padrão segura:

```ts
host: "127.0.0.1"
port: 61001
requireToken: true
allowPublicNetwork: false
```

Nunca exponha em `0.0.0.0` sem decisão explícita do projeto.

## 8. Execução automática com Windows

A estrutura fica preparada em `projectConfig.startup`. O template não força autostart por padrão.

Modos previstos:

- `disabled`
- `user-login`
- `machine-startup`

## 9. Tray icon

O comportamento do tray fica em `projectConfig.tray`. O tray deve mostrar apenas recursos ativos do projeto.

## 10. Serviço Windows e serviço Linux

A Etapa 2.2 implementa instalação/controle básico real por `sc.exe` no Windows e `systemd` no Linux; o projeto final pode ajustar nome, usuário e permissões.

Serviço não deve abrir splash nem janela gráfica.

## 11. Banco de dados

SQLite é o padrão. A documentação de bancos está em `docs/DATABASES.md`.

Drivers disponíveis/configuráveis:

- SQLite
- MySQL/MariaDB
- PostgreSQL
- Firebird: ignorado nesta etapa por compatibilidade

## 12. Desenvolvimento

```bash
npm install
npm run tauri:dev
```

## 13. Build

```bash
npm run typecheck
npm run build:web
npm run tauri:build
```

## 14. Validação Rust

```bash
cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml --all-targets --all-features
```

## 15. Distribuição

Antes de distribuir:

1. Atualize versão.
2. Atualize ícones.
3. Revise identificador Tauri.
4. Revise assinatura/certificados conforme plataforma.
5. Revise CI/CD.
6. Gere build local de validação.
7. Gere release pelo pipeline.


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

## Validação rápida antes de PR

Para evitar falhas de `cargo fmt --check` no GitHub Actions, execute:

```bash
npm run fmt:rust
npm run fmt:rust:check
npm run validate:web
```

Para validação completa em ambiente com Rust/Cargo:

```bash
npm run validate:all
```

Também é recomendado ativar os hooks locais:

```bash
git config core.hooksPath .githooks
```

Correção automática de formatação Rust:

```bash
bash scripts/fix-rust-format.sh
```

No Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fix-rust-format.ps1
```
