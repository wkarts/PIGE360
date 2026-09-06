# PIGE360 Deployer

Implantador oficial do PIGE360 para VPS Linux. O aplicativo desktop é feito em
Tauri 2, Rust, Vue 3 e TypeScript e opera o servidor por SSH usando um agente
Rust temporário. O VPS precisa de Linux, Docker e Docker Compose v2; não precisa
de Node.js, Rust ou Python para executar o instalador.

O computador que executa o desktop precisa do OpenSSH Client (`ssh`, `scp`,
`ssh-keyscan` e `ssh-keygen`), disponível como recurso nativo nos sistemas
suportados.

## O que ele instala

O Deployer não mantém cópias paralelas dos YAMLs. Ele lê os deployments que
fazem parte da revisão escolhida do próprio repositório PIGE360, verifica o
commit, os blobs Git e o `GENERATED-MANIFEST.json`, e então executa o contrato
versionado daquela distribuição.

| Ambiente | Canal aceito | Imagem | Uso |
| --- | --- | --- | --- |
| Homologação | `develop` | `develop-<sha12>` | revisão atual da branch `develop` |
| Homologação | `prerelease` | `develop-<sha12>` | snapshot imutável publicado |
| Homologação | `stable` | `X.Y.Z` | reprodução de release estável |
| Produção | `stable` | `X.Y.Z` | única política permitida |

Targets disponíveis:

- Docker Compose genérico;
- Dockge;
- CloudPanel;
- Portainer.

Para cada target o instalador oferece `plan`, `prepare`, `apply` e `rollback`.
Atualizações preservam `.env`, `secrets`, `volumes` e `.state`, criam backup dos
arquivos gerenciados, executam a validação e deixam um recibo em
`.pige360-deployer.json`.

As operações são realizadas pelos services `pige360-*` do Compose; o VPS não
depende de `install.sh`, `update.sh`, `validate.sh` ou `rollback.sh`.

## Uso

1. Instale o artefato desktop correspondente ao seu sistema.
2. Informe host, porta, usuário e chave SSH ou use o SSH Agent.
3. Teste a conexão; o preflight confirma Linux, arquitetura, Docker, Compose,
   espaço e acesso `sudo -n` quando solicitado.
4. Escolha repositório, ambiente, canal, versão e target.
5. Execute primeiro `plan`; depois `prepare` ou `apply`.
6. Confira o progresso estruturado e o recibo final.

Por padrão a homologação usa `/opt/stacks/pige360-develop` e a produção usa
`/opt/stacks/pige360-production`.

## Segurança operacional

- autenticação somente por chave SSH ou SSH Agent, sem senha armazenada;
- `known_hosts` estrito; host novo só é aceito com autorização explícita;
- argumentos SSH validados e sem shell local;
- tokens enviados somente em memória/stdin e removidos após a operação;
- login GHCR isolado em diretório temporário com limpeza automática;
- allowlist para overrides de ambiente e secrets;
- recusa de path traversal, links simbólicos e diretórios amplos;
- lock por stack, escrita atômica, backup e tag imutável para rollback;
- licenciamento desativado.

## Desenvolvimento e validação

```bash
npm ci
npm run validate:deployer
npm run typecheck
npm run build:web

cargo fmt --manifest-path src-tauri/Cargo.toml --all --check
cargo test --manifest-path src-tauri/Cargo.toml --locked --no-default-features
cargo test --manifest-path src-tauri/Cargo.toml --locked --all-targets --all-features
```

Build desktop local:

```bash
npm run tauri:build
```

O build desktop distribuível precisa conter o agente x64 gerado pela CI:

```text
src-tauri/embedded/pige360-deploy-agent-linux-amd64
```

## Ciclo de distribuição

- todo push em `develop` aprovado pela CI gera o agente Linux AMD64, a interface
  e instaladores x64 para Windows, Linux e macOS Intel, e publica a pré-release imutável
  `develop-<sha12>`;
- a release estável nasce do workflow da `main`, usa tag SemVer e só publica
  depois da matriz coordenada;
- produção nunca aceita `develop` nem prerelease.

Os workflows integrados estão na raiz do monorepo PIGE360. ARM64 não faz parte
da cadeia do implantador.

## Documentação

- contrato: [`CONTRATO.md`](CONTRATO.md);
- arquitetura: [`docs/DEPLOYER_ARCHITECTURE.md`](docs/DEPLOYER_ARCHITECTURE.md);
- migração da tecnologia: [`docs/MIGRATION_CONNECT_TO_PIGE360.md`](docs/MIGRATION_CONNECT_TO_PIGE360.md);
- integração ao monorepo: [`docs/INTEGRATED_BUILD.md`](docs/INTEGRATED_BUILD.md);
- branding: [`docs/BRANDING.md`](docs/BRANDING.md);
- build e release: [`docs/RELEASE_REPOSITORY.md`](docs/RELEASE_REPOSITORY.md).

## Limite de uma instalação local

O programa automatiza o deployment, mas não transforma credenciais, DNS, TLS
ou um VPS inexistente em homologação aprovada. O primeiro go-live deve validar
DNS/TLS, migrations, persistência após restart, backup/restore e smoke externo
no servidor definitivo.
