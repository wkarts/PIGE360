# Git Flow canônico — PIGE360

## Branches permanentes

- `main`: código promovido e apto a gerar release canônica.
- `dev`: integração contínua das próximas mudanças.

## Branches temporárias

Toda alteração comum nasce de `dev`:

- `feature/*` — funcionalidades;
- `fix/*` — correções;
- `chore/*` — manutenção;
- `refactor/*` — refatorações controladas;
- `docs/*` — documentação;
- `ci/*` — automação/CI;
- `test/*` — testes;
- `perf/*` — desempenho.

Essas branches abrem Pull Request para `dev`.

## Promoção de release

1. Crie `release/<versao>` a partir de `dev`.
2. Atualize somente o arquivo `VERSION` para a versão Alpha desejada.
3. O workflow `04 · Sincronizar versão de release` sincroniza automaticamente os manifests versionados e valida a consistência.
4. Abra Pull Request de `release/<versao>` para `main`.
5. Após merge na `main`, a alteração de `VERSION` aciona `50 · Pré-lançamento Alpha Web/Server`.
6. Faça o back-merge de `main` para `dev`.

## Hotfix

Hotfixes críticos nascem de `main` em `hotfix/*`, retornam por Pull Request para `main` e depois são sincronizados de `main` para `dev`.

## Release automática

A release canônica automática publica somente a distribuição Web/Server:

- 13 PWAs;
- pacotes self-hosted e fontes;
- imagens/runtime e evidências de Compose;
- evidências, SBOM/proveniência quando presentes no bundle;
- checksums.

Binários nativos estão fora da release automática. APK, AAB, IPA e instaladores desktop não são gerados nem anexados pelo workflow `50`.

Os workflows nativos permanecem disponíveis exclusivamente por execução manual para desenvolvimento/homologação. Isso preserva a capacidade técnica sem transformar binários mobile/desktop em artefatos da release canônica.

## Topologia protegida por CI

O workflow `03 · Git Flow` valida:

- `main` aceita PR apenas de `release/*` ou `hotfix/*`;
- `dev` aceita branches de trabalho padronizadas e o back-merge de `main`;
- PRs para outras bases são rejeitados pela política de CI.
