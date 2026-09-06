# Release SemVer oficial — PIGE360

## Política

O PIGE360 publica somente versões oficiais no formato `MAJOR.MINOR.PATCH`.

Não são usados sufixos de maturidade na versão do produto. A promoção para produção acontece por `develop -> main`, e a `main` é a única origem de tags e GitHub Releases oficiais.

## Incremento automático

A próxima versão é calculada a partir da tag estável mais recente:

- label `version:patch` ou alteração comum: incrementa PATCH;
- label `version:minor` ou título `feat:`: incrementa MINOR;
- label `version:major`, Conventional Commit com `!` ou `BREAKING CHANGE`: incrementa MAJOR.

O workflow manual permite override `auto`, `patch`, `minor` ou `major`, além
de retomar com `release_tag` uma tag imutável cuja release permaneceu em draft.
Uma retomada manual também aceita SemVer prerelease válido, por exemplo
`v1.2.0-rc.1`, mediante o gate explícito `--allow-prerelease`; esse canal é
identificado como prerelease no GitHub e permanece sujeito aos mesmos 12
builds, status e política de draft da versão estável. A geração automática e
o pacote canônico continuam stable-only. Assim, uma tag prerelease pode ser
reconstruída e auditada, mas permanece em draft quando o pacote central oficial
recusar a publicação estável.

Na ausência de uma tag estável anterior, o PIGE360 considera `1.0.0` como base
histórica. Uma alteração comum gera `1.0.1`; uma promoção identificada como
`feat:` ou `version:minor` gera `1.1.0`. Esta evolução administrativa e de
distribuição usa `1.1.0`.

## Gates

A publicação estável só acontece depois de:

1. validação de versão e metadados;
2. suíte integral de CI;
3. persistência da versão e dos `Cargo.lock` antes da tag imutável;
4. checkout dessa tag em cada runner da matriz;
5. build Windows x64/x86, Linux x64/ARM64 e macOS Intel/Apple Silicon;
6. empacotamento das 13 aplicações Web/PWA;
7. build CloudPanel Linux x64/x86;
8. build Android APK/AAB ARM64 e iOS ARM64 unsigned;
9. geração dos pacotes self-hosted/fontes/evidências;
10. coleta exclusiva dos artefatos finais, manifesto e checksums SHA-256.

## Reprodutibilidade Rust

A árvore de desenvolvimento pode ainda não conter os lockfiles dos 13
workspaces Tauri. Isso não é convertido em aprovação artificial: antes de
criar uma nova tag, o job de persistência instala Rust, gera o `Cargo.lock`
raiz e os 13 `Cargo.lock`, executa `cargo metadata --locked`, inclui esses
arquivos no commit de versão e somente então cria e envia a tag de forma
atômica. Se qualquer lock não puder ser gerado ou validado, a tag não é criada
e a release fica bloqueada.

Na retomada de uma tag, nenhum lock é regenerado: o workflow exige os 14
arquivos já persistidos na própria tag e repete `cargo metadata --locked`. O
workflow 51 também recusa redisparar uma tag sem esses arquivos. Portanto, a
reprodução exata dos builds nativos só é considerada fechada no commit/tag de
release, nunca a partir de dependências resolvidas silenciosamente no runner.

Cada alvo envia um status independente. Se algum build falhar, a tag continua
imutável e uma única GitHub Release permanece em draft, com o diagnóstico do
alvo ausente. A publicação parcial só ocorre quando
`allow_partial_release=true` for informado manualmente.

## Retomada segura

O workflow `51 · Retomar release coordenada` não baixa nem publica artefatos de
uma execução antiga. Ele valida a tag imutável, a versão, o `Cargo.lock` raiz e
os 13 `Cargo.lock` das aplicações Tauri, confirma que uma release existente
ainda está em draft e então redispara o workflow 50. Assim, os 12 alvos são
reconstruídos da mesma tag e voltam a passar pela coleta de artefatos finais,
checksums e política de publicação. O `source_run_id` opcional serve somente
para auditoria da origem e não autoriza reaproveitamento de binários.

## Distribuição

A release oficial reúne Web/Server/self-hosted, runtime CloudPanel e os
artefatos nativos efetivamente gerados, acompanhados por
`RELEASE-MANIFEST.json`, `RELEASE-STATUS.json` e `SHA256SUMS.txt`.

Os workflows nativos também validam Pull Requests e podem ser executados
manualmente. Assinatura Android/iOS e publicação em lojas dependem de opção
explícita e secrets; a ausência dessas credenciais não desativa os builds
unsigned/técnicos nem é mascarada como publicação concluída.

No fluxo manual iOS, o bundle ARM64 unsigned é construído primeiro. Uma
solicitação `store` só é considerada concluída quando `sign=true`, todos os
secrets Apple existem e a assinatura posterior é verificada; caso contrário,
o artefato técnico permanece disponível e o job falha explicitamente. Da mesma
forma, solicitar publicação white-label sem habilitação e conector de loja
homologado termina em erro auditável, sem declarar que a loja foi alterada.

## Sincronização

Após a publicação, o commit que materializa a versão final na `main` é sincronizado por fast-forward para `develop`, mantendo o próximo ciclo de desenvolvimento baseado na última versão oficial.
