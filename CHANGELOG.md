# Changelog

## [Unreleased] — checkpoint 0050 (2026-08-14)

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
