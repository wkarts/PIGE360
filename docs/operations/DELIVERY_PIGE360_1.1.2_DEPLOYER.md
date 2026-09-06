# Entrega PIGE360 1.1.2 com Deployer service-native x64

Data: 2026-09-06

## Fonte canônica

- arquivo recebido: `PIGE360-1.1.2-source.zip`;
- SHA-256: `5f4a5ec73692a3adef084c37598e4a2a288f316d988e027aec02fe5d8684dfc6`;
- versão preservada: `1.1.2`;
- os diretórios `deployments/` e `infra/` foram preservados byte a byte.

## Integração entregue

- PIGE360 Deployer integrado em `tools/pige360-deployer`;
- agente remoto Rust para Linux AMD64;
- instaladores Tauri para Windows x64, Linux x64 e macOS Intel x64;
- Compose, Dockge, CloudPanel e Portainer;
- execução service-native por `pige360-secrets-init`, `pige360-secret-set`,
  validação, migrations, readiness, bootstrap, backup, restore e diagnóstico;
- rollback transacional que restaura os arquivos e reaplica a stack anterior se
  uma atualização falhar;
- pré-release imutável `develop-<sha12>` após CI verde da revisão exata;
- release estável coordenada com 16 alvos, incluindo os quatro do Deployer.

## Evidências locais

- 371/371 testes backend isolados aprovados;
- 12/12 testes de release aprovados;
- 21 workflows canônicos e 21 espelhos locais;
- validação do projeto, deployments standalone, versão e Deployer aprovadas;
- varredura de segredos e integridade do ZIP executadas antes da entrega.

## Limites honestos

Este executor não possui Docker nem Rust/Cargo e não conseguiu resolver o
`vue-tsc` ausente no cache npm offline. Portanto, não houve build nativo local,
pull de imagens, publicação no GitHub/GHCR ou homologação em VPS/DNS/TLS real.
Essas provas são executadas pelos workflows incluídos quando a branch for
enviada ao repositório e pelos testes no servidor de homologação.
