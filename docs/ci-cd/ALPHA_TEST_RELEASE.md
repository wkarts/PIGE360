# Pré-lançamento `1.0.0-alpha.1`

## Finalidade

Esta versão é destinada a testes técnicos controlados do PIGE360. Ela não é uma
declaração de conclusão do contrato V8 e não deve ser tratada como produção.

O pré-lançamento reúne o código-fonte, as aplicações web, contratos de API,
migrations, documentação e imagens Docker construídas no runner do GitHub. As
integrações que exigem credenciais, certificados ou homologação externa seguem
desabilitadas até validação específica.

O workflow de pré-lançamento sempre anexa os relatórios de validação. Imagens
executáveis e ZIPs reproduzíveis só são gerados quando todos os gates passam;
em caso de falha, o job termina reprovado e preserva a evidência para correção.

## Fluxos no GitHub

| Workflow | Quando executa | Resultado |
| --- | --- | --- |
| `10 · Imagens base Docker` | alteração de bases/Docker ou execução manual | quatro imagens base exportadas em TAR, com inspeção e checksum. |
| `20 · Imagens Docker de aplicação` | alteração de backend, frontend, Docker, Compose ou pacote | bases + API, web, worker, migrations e reporting em TAR, seguidos de smoke test do Compose. |
| `50 · Pré-lançamento Alpha` | execução manual | testes, contratos, imagens Docker, smoke test do Compose e pacote ZIP reproduzível como artefatos. |

Os workflows somente constroem e disponibilizam artefatos do GitHub Actions.
Eles não publicam imagens em registro, não fazem deploy e não criam release
remota automaticamente.

## Estado do candidato neste checkpoint

Em validação local de 2026-08-13, `npm ci`, `npm run validate:ts` e
`npm run build:web` passaram. Os cinco aplicativos desta entrega
(`admin-app`, `desktop-admin`, `family-app`, `teacher-app` e
`tenant-admin-web`) e os 13 workspaces web produziram bundles Vite de produção.
Também passaram compilação estática Python, contrato visual, política dos
Dockerfiles, manifesto de aplicativos, validação estrutural, varredura de
segredos e SBOM.

Como ensaio adicional de compatibilidade, a suíte backend isolada em Python
3.12 concluiu 178 dos 179 nós na primeira rodada. O único nó reprovado dependia
de espaçamento literal no template Vue; a asserção foi reforçada para aceitar
formatação equivalente e todo o arquivo de validação frontend correspondente
passou na reexecução (5 testes). Esse ensaio não substitui a rodada integral e
limpa em Python 3.13 exigida pelo workflow.

O host local não possui Python 3.13 nem Docker/Compose. Por isso a suíte backend
no interpretador-alvo, as imagens OCI executáveis e o smoke test do Compose não
foram declarados aprovados localmente. Os workflows `20` e `50` executam esses
gates em runner Ubuntu com Docker, e só geram artefato de pré-lançamento após
todas as etapas passarem.

## Imagens construídas no workflow

```text
pige360-base-python:1.0.0-alpha.1
pige360-base-node:1.0.0-alpha.1
pige360-base-runtime:1.0.0-alpha.1
pige360-base-rust-tauri:1.0.0-alpha.1
pige360-api:1.0.0-alpha.1
pige360-web:1.0.0-alpha.1
pige360-worker:1.0.0-alpha.1
pige360-migrations:1.0.0-alpha.1
pige360-reporting:1.0.0-alpha.1
```

Cada imagem é exportada como arquivo TAR acompanhado de SHA-256 e metadados de
inspeção. O artefato pode ser importado em ambiente de teste com `docker load`.

### Encadeamento local de imagens

O script `scripts/oci/build-runtime-images.sh` constrói as imagens base com
`--load` e, em seguida, constrói API, web, workers e migrations usando o builder
Docker Engine padrão (`default`). Isso mantém as tags `pige360-base-*` e
`pige360-api` disponíveis para os estágios seguintes no mesmo runner, sem tentar
buscá-las no Docker Hub. O builder isolado criado pelo `setup-buildx-action`
continua disponível para workflows próprios, mas não é usado nessa cadeia local.

O lock de produção fixa `psycopg[binary]==3.2.13`. A versão `3.2.0` não é
utilizada porque seus metadados exigem `psycopg-binary==3.2.0.dev1`, pacote que
não está publicado no índice. O build da API instala os dois locks antes de
gerar a imagem, portanto essa validação ocorre no workflow de imagens.

Após a exportação, o workflow sobe somente o núcleo de homologação do Compose:
PostgreSQL de controle e tenants, Redis, RabbitMQ, MinIO, inicialização de
migrations, API e web. Os segredos são gerados em diretório temporário do
runner, não são impressos e são removidos ao final. A senha inicial do RabbitMQ
é lida do Docker Secret no boot (a imagem moderna não aceita a variante
`RABBITMQ_DEFAULT_PASS_FILE`) e o broker possui 45 segundos de período de
inicialização antes de o health check ser contabilizado. Se o startup falhar, o
workflow coleta o estado dos containers e os logs sanitizados de web e RabbitMQ
em `compose-startup-diagnostics.log`; o artefato do workflow 20 também é
enviado em caso de erro. A imagem web valida a configuração do Nginx no build e
inicia sem os scripts mutáveis da imagem base, compatível com UID não
privilegiado e root filesystem somente leitura. Os health checks de web e API,
logs e manifesto do smoke test ficam no artefato do job.

## Critérios antes de produção

- validar a suíte integral em GitHub Actions;
- executar o smoke test do Compose em ambiente isolado;
- validar upgrade/migrations sobre cópia de banco compatível;
- homologar providers fiscais, bancários, assinatura e comunicação conforme a
  configuração de cada tenant;
- realizar a matriz desktop/mobile nos runners e dispositivos correspondentes;
- revisar segurança, backups e o procedimento de rollback.
