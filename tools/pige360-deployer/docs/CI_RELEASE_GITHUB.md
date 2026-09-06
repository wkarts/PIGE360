# CI/CD e release no GitHub

O PIGE360 Deployer integrado usa os workflows da raiz do monorepo PIGE360.

## CI

`35-build-deployer.yml` executa em Pull Requests e por acionamento manual. O
gate inclui:

- `actionlint` e validação de título de Pull Request;
- auditoria estrutural do projeto;
- sintaxe dos scripts Node.js, shell e PowerShell;
- `npm ci`, sincronização de versão, TypeScript e build Web/PWA;
- `cargo fmt`, `cargo check`, `cargo clippy` e testes com `--locked`;
- matriz das features MySQL, PostgreSQL e combinadas;
- build headless puro com `--no-default-features`;
- contrato AMD64 do agente e build dos instaladores desktop x64.

## Release coordenada

`50-release.yml` inicia somente depois de um CI aprovado em `main`, ou manualmente
para retomar uma tag já existente. O fluxo:

1. resolve a próxima versão com `semantic-release`;
2. gera e versiona `src-tauri/Cargo.lock` antes da tag;
3. faz checkout da tag exata em todos os builds;
4. gera o agente Linux AMD64 e o implantador Windows x64, Linux x64 e macOS Intel/x64 junto aos demais artefatos da plataforma;
5. reúne os artefatos em um único job publicador;
6. renomeia os arquivos e gera `SHA256SUMS.txt` e
   `RELEASE-MANIFEST.json`;
7. cria ou reutiliza um único draft; uma matriz completa é publicada e uma
   matriz parcial permanece retomável por padrão.

Uma publicação parcial exige acionamento manual com `allow_partial_release`.
Depois dessa autorização, alvos ausentes só podem ser acrescentados em uma nova
versão, pois a release publicada não é reaberta.

Uma nova tentativa aceita asset remoto existente somente quando o conteúdo é
idêntico. Release publicada não é reaberta, tag não é movida e asset divergente
não é sobrescrito.

## Escopo de arquitetura

O implantador integrado é exclusivamente x64. Ele não constrói Android, iOS,
Linux ARM64 nem macOS Apple Silicon. Os alvos próprios das demais aplicações
PIGE360 permanecem independentes e não são removidos por esta integração.

## CloudPanel manual

`cloudpanel-linux-release.yml` gera, sob demanda, pacotes x64, x86 ou ambos e os
mantém como artefatos da execução. A publicação oficial desses pacotes ocorre
no release coordenado, evitando duas rotas concorrentes gravando na mesma
release.

## Windows e caminhos longos

Os builds locais e o release Windows usam `CARGO_TARGET_DIR` curto fora do
projeto para evitar `LNK1104`, `MAX_PATH` e falhas em diretórios com espaços.
Use `npm run build:windows:project-target` apenas quando precisar
explicitamente do target dentro de `src-tauri`.

## Segredos opcionais

- `WINDOWS_CERTIFICATE`: certificado PFX codificado em Base64.
- `WINDOWS_CERTIFICATE_PASSWORD`: senha do PFX.

Sem esses secrets, os instaladores são gerados sem assinatura. O workflow
remove o arquivo temporário e o certificado importado ao concluir o job.
