# Changelog

## [1.1.2] — deployment service-native (2026-09-05)

- Substitui scripts obrigatórios do host por serviços Compose idempotentes.
- Adiciona a imagem `pige360-ops` ao catálogo, build e publicação GHCR.
- Separa inicialização de secrets, configuração, dados, validação e migrations.
- Adiciona services sob profile `operations` para readiness, bootstrap, secrets externos, diagnóstico, backup e restore.
- Elimina bind mounts relativos e pastas auxiliares dos pacotes standalone.
- Preserva update/rollback sob Dockge, Portainer ou CI/CD sem conceder Docker socket aos serviços administrativos.

## [1.1.1] — deployments de homologação e produção (2026-09-04)

### Deploy operacional

- deployments independentes e autocontidos foram adicionados para `develop`
  (homologação) e `production`, com variantes Docker Compose, Dockge,
  CloudPanel e Portainer;
- cada pacote inclui `.env.example`, Compose image-only, instalação, validação,
  health check, logs, stop, atualização, rollback, bootstrap administrativo,
  backup e restore;
- o instalador self-hosted passou a selecionar de fato ambiente, modo
  `source|registry` e target, com precedência explícita de configuração e
  isolamento de projetos, redes, portas, volumes e logs;
- produção recusa tags móveis (`latest`, `main`, `develop`); homologação aceita
  `develop`, `develop-<sha>` ou uma SemVer deliberadamente informada;
- apenas o gateway é publicado em loopback. PostgreSQL, Redis, RabbitMQ, MinIO,
  Prometheus, Grafana e Loki permanecem privados nas redes Docker.

### Imagens, runtime e segurança

- API, migrations, worker e as quatro superfícies administrativas possuem
  referências GHCR coerentes; os workflows constroem, publicam primeiro a tag
  imutável por commit, promovem o canal e executam smoke da imagem publicada;
- `/api` passou a funcionar em same-origin nas imagens web, enquanto métricas
  Prometheus continuam acessíveis somente pela rede interna;
- secrets são criados atomicamente, com diretório `0700`, arquivos `0444` para
  containers non-root e recusa de links simbólicos;
- storage bind usa ownership por serviço e nunca `chmod 777`; Alloy filtra pelo
  projeto Compose e Loki usa WAL e retenção operacional de 30 dias;
- o manifesto alpha histórico da raiz permanece no repositório como evidência,
  mas não entra nos novos ZIPs nem é apresentado como manifesto da release.

### Limites explícitos

- `BUILD_FARM_ENABLED=false` permanece como padrão; builders e runners nativos
  são perfis opcionais e não fazem parte da subida administrativa principal;
- push/pull GHCR, `docker compose up`, DNS/TLS e restore de ensaio dependem de
  runner ou servidor com Docker e credenciais reais e não são simulados como
  homologação produtiva local.

## [1.1.0] — evolução conservadora auditada (2026-09-04)

### Administração e segurança

- lifecycle versionado de tenants, quotas, revogação de suporte, usuários da
  plataforma e inventário operacional sanitizado foram adicionados sem remover
  telas ou rotas existentes;
- parceiros, catálogo de planos, assinatura manual, snapshots de uso e
  entitlements passaram a ser administráveis no Control Plane com
  idempotência, versão otimista, auditoria e Outbox;
- agents operacionais passaram a ter credencial one-time, capabilities,
  heartbeat, stale/revoke e fila auditável de backup, restore e deploy; sem
  agent compatível o job permanece `queued` e nunca é apresentado como executado;
- autenticação recebeu lockout persistente, sessão identificada, rotação atômica
  de refresh token, detecção de replay e logout com revogação no servidor;
- readiness passou a falhar fechado em produção, cobrindo Control Plane,
  migrations, tenants ativos, storage, Redis, RabbitMQ e MinIO;
- eventos ainda sem handler deixaram de ser marcados como concluídos: agora
  seguem retry e dead letter persistida.
- quotas de usuários, alunos, API, integrações, builds e domínios são aplicadas
  também nas reativações; storage permanece explicitamente sem enforcement até
  existir um ledger transacional comum a Local/S3.

### Deploy e distribuição

- instalação self-hosted ganhou modos fonte/registry e targets base,
  CloudPanel, Dockge, Portainer e edge;
- app-init passou a reconciliar migrations do Control Plane e de todos os
  tenants operacionais;
- backup/restore incluem Control, bancos de tenants e objetos atuais do MinIO,
  com manifesto, checksums, fingerprint da chave, confirmação destrutiva e
  rollback explícito;
- workflows nativos foram reativados com matriz coordenada para Windows,
  Linux, macOS, Android e iOS, além de Web/PWA e CloudPanel; publicação permanece
  bloqueada quando qualquer alvo obrigatório falha;
- a Build Farm passou a coletar somente artefatos finais, nunca diretórios
  `target` completos.

### Frontend, offline e supply chain

- as 13 aplicações receberam manifesto PWA, service worker instalável e base de
  assets relativa;
- a outbox offline passou a IndexedDB isolado por tenant e usuário;
- ECharts foi atualizado para 6.1.0 e o lockfile npm passou a ser a fonte
  reproduzível do build;
- SBOM passou a inventariar `package-lock.json` e dependências de produção;
- empacotamento preserva 50 `*.vue.js`, 13 `main.js` e os timestamps reais dos
  fontes, com gate antes/depois e zero remoção permitida;
- ZIPs são escritos em fluxo e publicados atomicamente; hashes imutáveis dos
  pacotes internos são reconferidos antes e depois da montagem do bundle, e um
  lock exclusivo impede duas execuções sobre o mesmo diretório de entrega;
- arquivos intermediários são isolados fora da pasta final e qualquer resíduo
  temporário faz o checksum e a entrega falharem de forma fechada.

### Limites de validação

- nenhuma evidência local é apresentada como homologação de Docker,
  PostgreSQL, MinIO, DNS/TLS, CloudPanel, Dockge, Portainer ou providers reais;
- os binários nativos dependem dos runners Windows/Linux/macOS/Android/iOS e não
  são declarados gerados quando a toolchain correspondente não foi executada.

## [1.0.0-alpha.2] — checkpoint 0051 (2026-08-14)

### Catálogo comercial escolar

- categorias explícitas para uniforme, livros, apostilas, módulos, materiais,
  kits, ingressos e eventos, mantendo compatibilidade com `product_type` legado;
- filtro por categoria com isolamento por tenant e índice operacional;
- formulário de cadastro no painel de Compras, OpenAPI e SDK TypeScript alinhados;
- migration tenant `0044_school_sales_catalog_categories`, documentação e
  cenários de regressão de venda/estoque incluídos.
- a cadeia de imagens Docker agora usa o builder Docker Engine padrão ao
  consumir bases locais, evitando busca indevida das imagens `pige360-base-*`
  no Docker Hub durante os workflows de aplicação e pré-lançamento.
- o lock de produção usa `psycopg[binary]` 3.2.13, substituindo a versão 3.2.0
  que referencia a distribuição inexistente `psycopg-binary==3.2.0.dev1`.
- o RabbitMQ lê a senha inicial a partir do Docker Secret em tempo de boot,
  substituindo a variável `_FILE` não suportada pela imagem atual; seu health
  check recebeu janela de inicialização de 45 segundos e diagnóstico persistente
  do smoke Compose para impedir falhas opacas no GitHub Actions.
- o container web inicia o Nginx diretamente em modo não privilegiado, sem os
  scripts da imagem base que tentavam alterar `default.conf`; a configuração é
  verificada no build e o diagnóstico do smoke agora inclui web e RabbitMQ.
- após limpar o `ENTRYPOINT` herdado, a imagem web declara explicitamente
  `CMD ["nginx", "-g", "daemon off;"]`, evitando que o Docker Compose tente
  criar o serviço sem comando.
- todos os serviços web em Compose agora montam `/var/cache/nginx` e `/var/run`
  como `tmpfs` pertencentes ao UID/GID 10001; isso preserva o filesystem
  somente leitura sem impedir a criação de `client_temp` e do PID do Nginx.
- a promoção de versão na `main` agora cria uma GitHub Release imutável com
  tag, checksums, SBOM e proveniência, em vez de limitar-se a artefatos
  temporários do GitHub Actions;
- o pré-lançamento foi desenhado para montar os 13 PWAs, instaladores Tauri
  desktop, APK/AAB Android, IPAs iOS unsigned e pacotes self-hosted depois dos
  gates de validação, imagens Docker e smoke Compose; essa descrição é contrato
  de workflow, não comprovação de que os binários foram gerados naquele
  checkpoint;
- a versão canônica passou a ser verificada contra os metadados públicos de
  apps, pacotes, Docker e OpenAPI antes de qualquer publicação, evitando
  regressão silenciosa em promoções futuras.

## [1.0.0-alpha.1] - 2026-08-13

### Pré-lançamento de testes

- versão de testes preparada para execução controlada no GitHub Actions;
- imagens Docker base e de aplicação passaram a ser construídas por fluxo
  reutilizável, exportadas em TAR com SHA-256 e metadados de inspeção;
- Dockerfiles de API, web, worker, migrations e reporting agora recebem as
  imagens base por argumento, eliminando o acoplamento à tag estática `1.0.0`;
- workflow de pré-lançamento executa validações, constrói imagens e gera pacotes
  locais reproduzíveis como artefatos do GitHub Actions;
- publicação em registro, release remoto e deploy continuam deliberadamente
  fora do fluxo de testes.

## [1.0.0] - 2026-08-08

### Produto

- Control Plane e Tenant Plane multi-tenant por hostname, banco/role/storage por tenant e RLS;
- cadastro único de pessoas, alunos, responsáveis, colaboradores, currículo, turmas e matrícula;
- planejamento anual/periódico/semanal/aula, aprovação, execução, cobertura curricular e offline;
- sessões reais, chamada online/offline, políticas, justificativas, correções, reabertura e risco;
- financeiro, parcelas, pagamentos/rateios, PIX, conciliação, serviços, vendas, PDV, estoque, compras e patrimônio;
- motor fiscal versionado, simulação, IBPT, documentos fiscais por providers e storage de evidências;
- RH, contratos de trabalho, folha e ponto com sequência/idempotência;
- contratos jurídicos versionados, snapshot, PDF/hash, aditivos, renovação, envelopes, OTP, ICP-Brasil/PAdES e GOV.BR condicional;
- comunicação, e-mail IMAP/SMTP, Mailcow, Evolution, avisos, solicitações e workflows humanos;
- eventos/viagens, biblioteca, transporte, saúde, documentos, Reporting e Analytics;
- integrações externas por adapters tipados, secrets por referência e bloqueio de rede em testes;
- Branding Studio, white-label, App Factory, build jobs, releases e Central de Downloads;
- aplicações Web/PWA/Tauri para plataforma, administração, família, professor, aluno, PDV, kiosk e ponto.

### Plataforma e supply chain

- Compose self-hosted, workers, observabilidade, backup/restore e Docker Secrets;
- 15 workflows CI/CD com publicação/deploy desabilitados por padrão;
- OpenAPI e SDK TypeScript gerados;
- secret scan, SBOM CycloneDX, provenance, checksums e release local reproduzível;
- builders/agentes não transformam ausência de toolchain em build aprovado;
- frontend Docker multi-stage compila o source Vue atual, sem depender de `dist` histórico.

### Migração

- `generic_records` removido do runtime e de instalações novas;
- migration de compatibilidade preserva dados alpha como `legacy_generic_records` quando necessário;
- referências nominais migradas para PIGE360 1.0.0 sem alterar a fronteira white-label dos tenants.
