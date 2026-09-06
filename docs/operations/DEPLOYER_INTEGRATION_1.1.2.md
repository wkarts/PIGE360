# Integração do PIGE360 Deployer x64

Data da integração: 2026-09-06  
Versão-base da árvore: 1.1.2  
Branch: `feat/pige360-1.1.2-service-native-deployer-x64`

## Resultado

O implantador deixou de ser uma entrega externa e passou a integrar o projeto
PIGE360 em `tools/pige360-deployer`. Ele não duplica nem elimina os contratos
operacionais existentes: seleciona e executa as distribuições versionadas em
`deployments/develop` (homologação) e `deployments/production` (produção).

Os arquivos Compose, `.env.example`, manifesto e checksums continuam sendo a
definição operacional auditável. Instalação, validação, migrations, readiness,
bootstrap, backup, restore e diagnóstico são executados pelos services
operacionais do Compose. O Deployer atua como interface e agente de
orquestração sobre essa definição, sem exigir scripts no host.

## Arquiteturas do Deployer

| Artefato | Arquitetura | Canal |
| --- | --- | --- |
| Agente remoto Linux | AMD64/x86_64 | develop e SemVer |
| Instalador Windows | x64 | develop e SemVer |
| Instalador Linux | x64 | develop e SemVer |
| Instalador macOS | Intel/x64 | develop e SemVer |

ARM64 não é compilado nem publicado pela cadeia do Deployer. Esta decisão não
remove alvos ARM64 legados das demais aplicações PIGE360.

## Automação integrada

- `35-build-deployer.yml`: valida pull requests e builds manuais sem publicar;
- `36-develop-prerelease.yml`: cria `develop-<sha12>` somente após a CI da
  revisão exata do commit terminar com sucesso;
- `50-release.yml`: inclui os quatro artefatos x64 na release estável e mantém a
  publicação bloqueada se qualquer resultado estiver ausente;
- `51-recover-release.yml`: recuperação coerente com a matriz de 16 alvos;
- `CI_CD_KIT_LOCAL/workflows`: espelho exato dos workflows canônicos.

## Verificações executadas localmente

| Verificação | Resultado |
| --- | --- |
| Contrato do Deployer integrado | aprovado |
| Consistência de versão | aprovado em 1.1.2 |
| Readiness da release | aprovado |
| Validação estrutural do projeto | aprovado |
| YAML dos 21 workflows e seus 21 espelhos | válido, sem chaves duplicadas |
| Regressão backend isolada | 371/371 aprovados |
| Testes do publicador e integração de release | 12/12 aprovados |
| Simulação do coletor de release | 16/16 alvos reconhecidos |
| Sintaxe dos scripts Node do Deployer | aprovada |
| Contrato e versionamento internos do Deployer | aprovados |

## Limites desta execução

O ambiente local não possui o toolchain Rust/Cargo nem acesso ao pacote npm
`vue-tsc` que faltava no cache offline. Por isso, os binários Tauri e o agente
nativo não foram materializados localmente nesta execução. Os workflows de CI
contêm os runners e comandos nativos para esses builds, mas o primeiro run no
GitHub deve ser tratado como a evidência definitiva de compilação x64.

Também não foram realizados deploy real, acesso ao GHCR, publicação GitHub,
DNS/TLS, migração em PostgreSQL real ou homologação em servidor. Essas ações
dependem dos runners, secrets e hosts do ambiente definitivo.

## Fluxo de promoção

1. abrir PR desta branch para `develop`;
2. executar CI e `35-build-deployer.yml`;
3. após o merge, `36-develop-prerelease.yml` publica `develop-<sha12>`;
4. instalar essa pré-release em homologação e executar smoke operacional;
5. promover a revisão homologada para a release SemVer estável;
6. `50-release.yml` publica a plataforma e os quatro artefatos do Deployer.

## Rollback

- a pré-release é imutável por SHA e não sobrescreve uma revisão anterior;
- para homologação, reinstalar o `develop-<sha12>` anterior;
- para produção, selecionar a SemVer anterior no Deployer; ele troca a tag
  imutável, executa backup e reaplica a stack service-native;
- migrations e dados devem seguir os procedimentos de backup/restore já
  existentes nos pacotes de deployment.
