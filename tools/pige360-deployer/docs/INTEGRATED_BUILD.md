# Build integrado ao PIGE360

O PIGE360 Deployer faz parte do mesmo código-fonte e da mesma versão SemVer da
plataforma. Ele não substitui os arquivos de deployment: consome e valida os
`compose.yaml`, `.env.example`, manifestos e scripts versionados em
`deployments/`.

## Alvos do implantador

| Componente | Sistema | Arquitetura |
| --- | --- | --- |
| Agente remoto temporário | Linux | AMD64/x86_64 |
| Instalador | Windows | x64 |
| Instalador | Linux | x64 |
| Instalador | macOS | Intel/x64 |

ARM64 não é compilado nem publicado pela cadeia do implantador integrado. Essa
decisão é isolada do restante da plataforma e não remove alvos já existentes de
aplicações PIGE360.

## Canais

- Pull Request: valida contrato, TypeScript, Rust, agente e instaladores x64.
- `develop`: depois da CI verde, publica a prerelease imutável
  `develop-<sha12>` com fonte, deployments, agente e instaladores.
- `main`: a release SemVer coordenada inclui os quatro artefatos do implantador
  e só deixa o draft quando a matriz obrigatória está completa.

## Build local

```bash
cd tools/pige360-deployer
npm ci
npm run validate:deployer
npm run typecheck
cargo test --manifest-path src-tauri/Cargo.toml --locked --no-default-features --lib
cargo build --manifest-path src-tauri/Cargo.toml --locked --release \
  --no-default-features --bin pige360-deploy-agent \
  --target x86_64-unknown-linux-gnu
```

O instalador desktop precisa do agente em
`src-tauri/embedded/pige360-deploy-agent-linux-amd64` antes de executar o build
Tauri.

## Rollback

Reverter a alteração que adiciona `tools/pige360-deployer` e os workflows 35/36
remove apenas o implantador integrado. Os deployments, imagens, bancos e dados
da plataforma não são modificados por esse rollback de código.
