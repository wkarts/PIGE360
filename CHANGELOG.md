# Changelog

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
