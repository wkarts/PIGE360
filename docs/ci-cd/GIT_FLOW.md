# Git Flow canônico — PIGE360

## Branches permanentes

- `develop`: integração, desenvolvimento e homologação contínua.
- `main`: produção e origem exclusiva das releases oficiais.

## Branches temporárias

Toda alteração comum nasce de `develop`:

- `feature/*` — funcionalidades;
- `fix/*` — correções;
- `chore/*` — manutenção;
- `refactor/*` — refatorações controladas;
- `docs/*` — documentação;
- `ci/*` — automação/CI;
- `test/*` — testes;
- `perf/*` — desempenho.

Essas branches abrem Pull Request para `develop`.

## Promoção para produção

Quando `develop` estiver homologada, abre-se Pull Request direto `develop -> main`.

O merge em `main` aciona o release automático SemVer. Não existe canal Alpha, Beta, RC ou Draft para o produto PIGE360.

## Versionamento SemVer

Formato oficial: `MAJOR.MINOR.PATCH`.

- `version:patch` ou alteração comum: `1.0.1 -> 1.0.2`;
- `version:minor` ou PR com título `feat:`: `1.0.2 -> 1.1.0`;
- `version:major`, `!` em Conventional Commit ou `BREAKING CHANGE`: `1.1.0 -> 2.0.0`.

A primeira distribuição estável deste novo fluxo parte da base interna `1.0.0` e publica `v1.0.1`.

O workflow manual da release também aceita override `auto`, `patch`, `minor` ou `major`.

## Release automática

A `main` publica somente após gates de qualidade concluídos com sucesso.

A distribuição canônica contém:

- 13 PWAs;
- pacotes self-hosted e fontes;
- imagens/runtime e evidências de Compose;
- evidências, SBOM/proveniência quando presentes no bundle;
- checksums;
- tag imutável `vX.Y.Z`;
- GitHub Release oficial.

Binários nativos permanecem fora da distribuição automática. APK, AAB, IPA e instaladores desktop não são gerados nem anexados pelo workflow oficial.

Os workflows nativos continuam disponíveis exclusivamente por execução manual para desenvolvimento/homologação.

## Sincronização pós-release

Depois que a `main` persiste o número final da release, o workflow sincroniza esse commit de versão de volta para `develop`, mantendo as duas branches preparadas para o próximo ciclo.

## Hotfix

Hotfixes críticos podem nascer de `main` em `hotfix/*`, retornar por Pull Request para `main` e ser sincronizados de volta para `develop` após a publicação.

## Topologia validada por CI

O workflow `03 · Git Flow` valida:

- `main` aceita promoção de `develop` ou `hotfix/*`;
- `develop` aceita branches de trabalho padronizadas e sincronização da `main`;
- PRs para outras bases são rejeitados pela política de CI.
