# Git Flow canônico — PIGE360

## Branches permanentes

- `develop`: integração, desenvolvimento e homologação contínua.
- `main`: produção e origem exclusiva das releases oficiais.

## Branches temporárias

Toda alteração comum nasce de `develop`:

- `feat/*` — funcionalidades; prefixo preferencial, alinhado ao Connect|API;
- `resource/*` — incrementos de recursos/ativos operacionais quando esse recorte fizer sentido;
- `fix/*` — correções;
- `hotfix/*` — correções urgentes, podendo promover diretamente para `main` quando necessário;
- `chore/*` — manutenção;
- `refactor/*` — refatorações controladas;
- `docs/*` — documentação;
- `ci/*` — automação/CI;
- `test/*` — testes;
- `perf/*` — desempenho.

`feature/*` continua aceito por compatibilidade, mas novos trabalhos devem preferir `feat/*`.

Essas branches abrem Pull Request para `develop`.

## Promoção para produção

Quando `develop` estiver homologada, abre-se Pull Request direto `develop -> main`.

O merge em `main` aciona o release automático SemVer. Não existe canal público
Alpha, Beta ou RC. Um draft técnico pode existir apenas para registrar uma
matriz incompleta e nunca é anunciado como versão pronta.

## Versionamento SemVer

Formato oficial: `MAJOR.MINOR.PATCH`.

- `version:patch` ou alteração comum: `1.0.1 -> 1.0.2`;
- `version:minor` ou PR com título `feat:`: `1.0.2 -> 1.1.0`;
- `version:major`, `!` em Conventional Commit ou `BREAKING CHANGE`: `1.1.0 -> 2.0.0`.

A primeira distribuição estável deste novo fluxo parte da base interna `1.0.0` e publica `v1.0.1`.

O workflow manual da release também aceita override `auto`, `patch`, `minor` ou `major`.
Tags SemVer prerelease existentes também podem ser retomadas manualmente e são
marcadas como prerelease no GitHub; elas não alteram o cálculo automático
estável executado pelos merges na `main`.

## Release automática

A `main` publica somente após gates de qualidade concluídos com sucesso.

A distribuição canônica contém:

- aplicações Web/PWA;
- pacotes self-hosted e fontes;
- imagens/runtime CloudPanel Linux x64/x86;
- instaladores Windows x64/x86, Linux x64/ARM64 e macOS Intel/Apple Silicon;
- APK/AAB Android ARM64 e IPA iOS ARM64 não assinado;
- evidências, SBOM/proveniência quando presentes no bundle;
- manifesto da matriz e checksums SHA-256;
- tag imutável `vX.Y.Z`;
- GitHub Release oficial.

Os doze alvos são tentados a partir da tag exata. Uma matriz incompleta cria ou
atualiza somente um draft auditável e não é apresentada como release concluída.
A publicação parcial exige `allow_partial_release=true` em disparo manual.

Os workflows nativos permanecem disponíveis manualmente e também validam Pull
Requests pertinentes. Assinaturas e lojas são condicionais a secrets e a uma
solicitação explícita; builds unsigned continuam sendo executados sem esses
segredos.

Uma retomada pelo workflow 51 valida a tag e todos os lockfiles persistidos e
redispara a matriz completa do workflow 50. Ela nunca promove nem reaproveita
assets de um run anterior; uma nova falha preserva a release como draft.

## Sincronização pós-release

Depois que a `main` persiste o número final da release, o workflow sincroniza esse commit de versão de volta para `develop`, mantendo as duas branches preparadas para o próximo ciclo.

## Hotfix

Hotfixes críticos podem nascer de `main` em `hotfix/*`, retornar por Pull Request para `main` e ser sincronizados de volta para `develop` após a publicação.

## Topologia validada por CI

O workflow `03 · Git Flow` valida:

- `main` aceita promoção de `develop` ou `hotfix/*`;
- `develop` aceita `feat/*`, `resource/*`, `fix/*`, `hotfix/*`, `chore/*`, `refactor/*`, `docs/*`, `ci/*`, `test/*`, `perf/*` e sincronização da `main`;
- PRs para outras bases são rejeitados pela política de CI.
