# Release SemVer oficial — PIGE360

## Política

O PIGE360 publica somente versões oficiais no formato `MAJOR.MINOR.PATCH`.

Não são usados sufixos de maturidade na versão do produto. A promoção para produção acontece por `develop -> main`, e a `main` é a única origem de tags e GitHub Releases oficiais.

## Incremento automático

A próxima versão é calculada a partir da tag estável mais recente:

- label `version:patch` ou alteração comum: incrementa PATCH;
- label `version:minor` ou título `feat:`: incrementa MINOR;
- label `version:major`, Conventional Commit com `!` ou `BREAKING CHANGE`: incrementa MAJOR.

O workflow manual permite override `auto`, `patch`, `minor` ou `major`.

Na ausência de uma tag estável anterior, o PIGE360 considera `1.0.0` como base histórica e publica `1.0.1` como primeira distribuição oficial deste fluxo.

## Gates

A tag e a GitHub Release só são criadas depois de:

1. validação de versão e metadados;
2. suíte integral de CI;
3. build dos runtimes Docker e smoke Compose;
4. empacotamento Web/PWA;
5. geração dos pacotes self-hosted/fontes/evidências;
6. bloqueio explícito de artefatos Android, iOS e Desktop na distribuição oficial;
7. persistência da versão final na `main`.

## Distribuição

A release oficial publica os artefatos Web/Server do PIGE360, acompanhados por checksums SHA-256 e evidências produzidas pelo pipeline.

Os builders Android, iOS e Desktop permanecem disponíveis somente por execução manual para homologação técnica e não participam da release oficial.

## Sincronização

Após a publicação, o commit que materializa a versão final na `main` é sincronizado por fast-forward para `develop`, mantendo o próximo ciclo de desenvolvimento baseado na última versão oficial.
