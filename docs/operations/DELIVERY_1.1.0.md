# Entrega auditada PIGE360 1.1.0

## Classificação correta

Esta árvore é uma **source candidate para instalação e homologação**. Ela não é
uma release oficial publicável enquanto o runner coordenado não gerar os 14
`Cargo.lock`, os binários nativos, as imagens executáveis e as evidências dos
ambientes reais.

O modo local de empacotamento registra obrigatoriamente:

- `status: partial`;
- `distribution_channel: source-candidate`;
- `publishable_release: false`;
- `native_builds.status: not-built`.

## Fonte e preservação

- Base única: `PIGE360-develop(1).zip`.
- SHA-256: `dfc2950813fcb3ea239e9715b66527e55b914ee1241101fc8b986f44bf21a607`.
- Revisão declarada no comentário do ZIP:
  `9fa139bc20fc2f7173ffd2f07c78673e36e6090f`.
- Connect|API foi usado somente como referência arquitetural.
- O gate antes/depois recusa qualquer remoção de arquivo recebido.
- Os 50 `*.vue.js` e 13 `main.js` originais são preservados; componentes Vue
  novos também conservam seu mirror JavaScript.
- Os ZIPs usam o `mtime` UTC real de cada fonte, sem data fixa artificial.

## Incrementos entregues

### Administração global

- lifecycle versionado de tenants, quotas e revogação de suporte;
- usuários da plataforma com proteção da conta atual e do último superadmin;
- parceiros, planos, vínculo partner/tenant, assinatura manual, uso e
  entitlements;
- inventário interno sanitizado e status resiliente;
- agents com token one-time, capability, heartbeat, stale e revoke;
- catálogo de providers em estado `configured_not_probed`;
- jobs tipados de backup, restore e deploy, com idempotência, lease, auditoria,
  Outbox e transições reportadas por agent.

### Segurança e consistência

- lockout persistente, refresh rotativo atômico, replay protection e logout
  com revogação no servidor;
- quotas aplicadas em criação e reativação de usuários, alunos, integrações,
  builds e domínios;
- assinatura aceita apenas referências `secret://` tipadas; materiais privados,
  metadata sensível e URLs com `userinfo` são recusados;
- operações concorrentes críticas usam CAS/lock transacional;
- eventos sem handler seguem retry e DLQ, sem falso `completed`.

### Deploy e distribuição

- instalação self-hosted por fonte ou registry;
- targets `base`, `cloudpanel`, `edge`, `dockge` e `portainer`;
- migrations do Control Plane e de todos os tenants operacionais;
- backup/restore de Control, tenants e MinIO com manifesto/checksum;
- update com backup obrigatório e rollback explícito;
- matriz coordenada Windows, Linux, macOS, Web/PWA, CloudPanel, Android e iOS;
- release permanece draft se qualquer alvo obrigatório falhar.

### Web/PWA e supply chain

- 13 aplicações Vue/PWA instaláveis;
- IndexedDB isolado por tenant e usuário;
- dependências por `npm ci`, ECharts 6.1.0 e audit de produção;
- OpenAPI e SDK regenerados a partir da árvore final;
- secret scan, SBOM, manifesto, proveniência, checksums e verificação interna de
  cada ZIP.

## Evidência final

As contagens autoritativas são geradas somente após a última alteração:

- `release/reports/local-ci-report.json`;
- `release/reports/test-report.json`;
- `release/reports/build-report.json`;
- `docs/operations/BEFORE_AFTER_REPORT.json`;
- `release/secret-scan-report.json`;
- `release/source-tree-manifest.json`;
- `release/*provenance*.json`;
- `release/artifacts/reports/PIGE360-1.1.0-relatorio-evidencias.pdf`.

## Limites não mascarados

- Rust/Cargo, Android SDK/NDK, Xcode e Docker não estavam disponíveis neste host.
- PostgreSQL, Redis, RabbitMQ, MinIO, DNS/TLS, Cloudflare, CloudPanel, Dockge,
  Portainer e SSH remoto exigem acceptance test no ambiente definitivo.
- A assinatura comercial é manual; billing/gateway externo não foi homologado.
- Providers listados como configurados não foram probed.
- A quota `storage_bytes` ainda não é aplicada sem ledger Local/S3 unificado.
- Requisitos ainda `NOT_STARTED` no ledger continuam pendentes e não são
  promovidos por documentação ou inferência.

## Instalação para homologação

```bash
unzip PIGE360-1.1.0-source-candidate-bundle.zip
unzip packages/PIGE360-1.1.0-source-candidate-self-hosted.zip -d PIGE360
cd PIGE360
cp .env.example .env
sh deploy/self-hosted/install.sh --mode source --target cloudpanel
```

Antes do go-live, execute a matriz remota da release, smoke dos containers,
migrations em clone, restart/persistência, backup/restore, rollback, DNS/TLS,
tenant real, custom domain, providers e observabilidade.

