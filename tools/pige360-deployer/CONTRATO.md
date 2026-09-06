# Contrato do PIGE360 Deployer

## Resultado

Entregar um implantador integrado ao monorepo PIGE360, baseado em Tauri 2, Vue 3 e Rust, capaz
de instalar e atualizar distribuições completas do PIGE360 em VPS Linux por
SSH, sem exigir Rust, Node.js ou Python no servidor de destino.

## Canais de distribuição

- `develop`: homologação contínua; resolve a branch `develop` e usa a imagem
  imutável `develop-<sha12>` quando disponível.
- `prerelease`: versões SemVer com sufixo, como `v1.2.0-rc.1`; somente em
  ambiente de homologação.
- `stable`: `latest` ou tag `vMAJOR.MINOR.PATCH`; única opção aceita para
  produção.

Builds originados da branch `develop` do PIGE360 devem ser publicados como
GitHub prerelease imutável `develop-<sha12>`. Releases estáveis somente podem
nascer da release SemVer coordenada da plataforma.

## Targets PIGE360

O instalador deve consumir os deployments versionados pelo próprio PIGE360:

- Docker Compose genérico;
- Dockge;
- CloudPanel;
- Portainer;
- ambientes `develop` e `production`.

## Operações

- descobrir distribuições e mostrar canal, tag, commit e data;
- testar SSH e executar preflight do servidor;
- planejar sem alterar a stack;
- preparar configuração e segredos sem iniciar serviços;
- instalar ou atualizar com backup transacional dos arquivos gerenciados;
- executar health/readiness e produzir recibo auditável;
- preservar `.env`, `secrets`, `volumes` e `.state` em atualizações;
- oferecer rollback por tag imutável usando o contrato do pacote PIGE360.

## Segurança

- validar chave de host SSH; host novo exige aceite explícito;
- aceitar autenticação por chave ou SSH Agent, sem armazenar senha SSH;
- transportar tokens somente em memória/stdin e omiti-los de logs/Debug;
- validar SHA Git e hashes de `GENERATED-MANIFEST.json`;
- rejeitar path traversal, links simbólicos e diretórios amplos do sistema;
- usar lock de operação, gravação atômica e recibos sem segredos;
- manter licenciamento desativado.

## Critérios de aceite

- identidade PIGE360 sem resíduos visuais ou executáveis do Connect Deployer;
- frontend TypeScript compila e o PWA é gerado;
- validação estrutural, identidade e versionamento aprovados;
- testes unitários cobrem política de canal, paths, env e redaction;
- workflows constroem agente Linux amd64/x86_64 e implantadores Windows x64,
  Linux x64 e macOS Intel/x64;
- a cadeia integrada do implantador não compila nem distribui ARM64;
- push em `develop` gera prerelease identificada pelo SHA;
- tag `vX.Y.Z` gera release estável e nunca é tratada como prerelease;
- pacote fonte inclui documentação, checksums e matriz de migração.

## Limites de homologação local

O workspace atual não possui Rust/Cargo nem Docker. Builds Rust/Tauri e um
deploy real precisam ser executados pelos runners e por um VPS de homologação;
essa limitação não pode ser apresentada como sucesso local.
