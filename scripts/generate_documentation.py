#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION=(ROOT/'VERSION').read_text().strip()

def write(path:str,text:str)->None:
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text.rstrip()+"\n",encoding='utf-8')

write('README.md',f'''# PIGE360 — Plataforma Integrada de Gestão Educacional

Versão local: **{VERSION}**

Monorepo educacional brasileiro multi-tenant, SaaS/self-hosted e white-label, construído exclusivamente com os anexos locais desta execução. O projeto adota monólito modular orientado a domínios, API FastAPI, clientes Vue/Tauri, banco por tenant, outbox, cache offline e infraestrutura declarativa.

## Evidência disponível

- 328 rotas FastAPI e 221 paths OpenAPI, sem `operationId` duplicado;
- 15 testes automatizados do núcleo aprovados;
- isolamento de tenant por hostname e banco físico local comprovado;
- planejamento anual/periódico/semanal/por aula, versões, aprovação, execução e relatórios contratados na API;
- frequência por sessão, política versionada, chamada offline idempotente, justificativa, correção, reabertura e risco;
- Branding Studio, `BrandProvider`, `TenantBrandKit` e App Factory local;
- contratos com snapshot, PDF, SHA-256, envelopes e assinatura eletrônica interna;
- 13 aplicações web/PWA e fontes Tauri;
- 40 superfícies canônicas e 132 screenshots de regressão visual;
- 46 serviços Compose e 15 workflows inertes;
- backup/restore isolado testado;
- OpenAPI, SDK TypeScript, SBOM e provenance locais.

## Limites comprovados do ambiente

O workspace não possui Docker/Podman, Rust/Cargo, Android SDK/Gradle nem Xcode. Por isso, os binários nativos e as imagens executáveis não são apresentados como compilados. O pacote contém fontes, manifests, Dockerfiles, Compose e workflows prontos para runners adequados, além de layouts OCI estruturais marcados explicitamente como não executáveis. Nenhum serviço remoto foi acessado.

## Desenvolvimento local do núcleo

```bash
cd backend
PYTHONPATH=. pytest -q
cd ..
npx --no-install tsc -p tsconfig.validation.json --noEmit
python scripts/api/export_openapi.py
python scripts/api/generate_typescript_sdk.py
python scripts/visual/validate_visual_contract.py
python scripts/backup/test_backup_restore.py
```

## Validação completa sem rede

```bash
bash scripts/ci/run-all.sh
```

## Instalação self-hosted futura

```bash
bash scripts/local/init-secrets.sh runtime-secrets
docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml up -d
```

A inicialização por containers exige engine disponível e resolução das imagens declaradas. Consulte `docs/deployment/SELF_HOSTED.md` e `docs/operations/RISK_REGISTER.md` antes de produção.
''')

write('docs/architecture/OVERVIEW.md','''# Arquitetura

## Estilo

O PIGE360 usa **monólito modular orientado a domínios**. A API, os workers e o scheduler são processos diferentes do mesmo contrato de aplicação. Isso reduz transações distribuídas prematuras e mantém portas claras para extração futura.

```text
clientes web/PWA/Tauri
        ↓ HTTPS / REST / eventos autorizados
API FastAPI + resolução de Host
        ↓
Control Plane ── Tenant Plane dedicado
        ↓                ↓
PostgreSQL control    banco por tenant + RLS interno
        ↓                ↓
outbox → RabbitMQ → inbox/handlers idempotentes
        ↓
MinIO por tenant · Redis efêmero · observabilidade
```

## Fronteiras

- **Control Plane:** tenants, domínios, licenças, branding global, App Factory, suporte e auditoria global.
- **Tenant Plane:** dados acadêmicos, administrativos, financeiros, fiscais, trabalhistas e documentos da escola.
- **Clientes:** não acessam banco, fila, Redis ou storage diretamente.
- **Offline:** SQLite por tenant/usuário, outbox transacional, checkpoint e conflito explícito.

## Fonte de verdade

PostgreSQL é a fonte transacional; MinIO é a fonte de objetos; Mailcow permanece fonte das caixas; Redis não guarda informação definitiva; RabbitMQ transporta eventos, mas o estado é conciliado pela outbox/inbox.

## Estado desta revisão

O adapter local SQLite é usado para executar a suíte sem serviços externos. As migrations PostgreSQL e policies RLS estão em `backend/alembic_*` e `infra/migrations`. O adapter assíncrono SQLAlchemy está presente, porém a execução PostgreSQL não ocorreu por ausência de runtime de containers/servidor local.
''')
write('docs/architecture/TENANCY.md','''# Multi-tenancy

## Resolução obrigatória

O tenant é resolvido pelo hostname antes da autenticação. `X-Tenant-ID`, `tenant_id` em query string e seleção pública pelo frontend são rejeitados. Domínio desconhecido retorna 404.

## Separação física e lógica

- banco de controle separado;
- banco e usuário previstos por tenant em PostgreSQL;
- adapter local cria arquivo SQLite separado por tenant para comprovação sem infraestrutura externa;
- storage em `/var/lib/pige360/tenants/<uuid>`;
- buckets e chaves são derivados do UUID, nunca do nome comercial;
- RLS interno limita instituição, unidade, campus e departamento.

## Suporte global

O contrato exige sessão temporária com motivo, step-up, ator real e banner permanente. A rota genérica de dados nunca aceita token da plataforma dentro de um hostname tenant.

## Testes

A suíte prova que registros, tokens, arquivos, hostnames e backups não cruzam entre dois tenants locais. O relatório de backup/restore restaura somente Alpha e verifica ausência de Beta.
''')
write('docs/architecture/EVENTS.md','''# Eventos, outbox e consistência

Cada alteração consolidada grava estado e evento na mesma transação. O publisher seleciona eventos sem `published_at`, adiciona contexto assinado do tenant e publica na fila. O consumidor registra inbox/idempotência antes de executar o handler.

## Garantias

- entrega ao menos uma vez;
- handlers idempotentes;
- correlation ID e versão do evento;
- retries com backoff/jitter;
- DLQ e reprocessamento explícito;
- nenhum `tenant_id` confiado diretamente do payload externo;
- fechamento acadêmico/financeiro impede mutação retroativa.

O arquivo `backend/app/worker.py` valida contexto HMAC antes do handler. Celery é dependência de produção preparada, mas não foi baixada no ambiente offline.
''')
write('docs/architecture/ERD.md','''# Modelo de dados — visão condensada

```mermaid
erDiagram
  PLATFORM_TENANT ||--o{ TENANT_DOMAIN : owns
  PLATFORM_TENANT ||--|| TENANT_DATABASE : isolates
  TENANT_DATABASE ||--o{ USER : contains
  TENANT_DATABASE ||--o{ TEACHING_PLAN : contains
  TEACHING_PLAN ||--o{ TEACHING_PLAN_VERSION : versions
  TEACHING_PLAN ||--o{ LESSON_PLAN : schedules
  LESSON_PLAN ||--o{ LESSON_EXECUTION : records
  CLASS_SESSION ||--o{ ATTENDANCE_CALL : opens
  ATTENDANCE_CALL ||--o{ ATTENDANCE_RECORD : records
  ATTENDANCE_POLICY ||--o{ ATTENDANCE_POLICY_VERSION : versions
  BRAND_KIT ||--o{ BRAND_VERSION : versions
  BRAND_KIT ||--o{ BRAND_ASSET : owns
  TENANT_APP_MANIFEST ||--o{ APP_BUILD_REQUEST : requests
  CONTRACT ||--o{ CONTRACT_SNAPSHOT : freezes
  CONTRACT ||--o{ SIGNATURE_ENVELOPE : signs
  OUTBOX_EVENT }o--|| AUDIT_LOG : correlates
```

As migrations completas são a fonte normativa; este diagrama é somente uma visão de relacionamento.
''')

write('docs/adr/ADR-001-modular-monolith.md','''# ADR-001 — Monólito modular

**Status:** aceito.

Foi escolhido um monólito modular porque os domínios educacionais compartilham transações e regras fortes. Processos de worker, scheduler, gateway e clientes são separados, mas não há fragmentação prematura em dezenas de serviços. Extração futura exige porta, evento e ownership claro, não repository genérico obrigatório.
''')
write('docs/adr/ADR-002-host-tenancy.md','''# ADR-002 — Tenant somente por hostname

**Status:** aceito.

O hostname é validado antes da autenticação e abertura de recursos. Cabeçalhos públicos ou parâmetros de tenant são proibidos para evitar confused-deputy e troca de contexto induzida pelo cliente. Domínios personalizados mapeiam para um único UUID imutável.
''')
write('docs/adr/ADR-003-local-only-delivery.md','''# ADR-003 — Construção exclusivamente local

**Status:** aceito para esta revisão.

Nenhum repositório, registro, loja, provedor de deploy ou serviço externo foi acessado. Workflows são arquivos inertes. A ausência de toolchain nativa gera `skipped_not_configured`; não gera binário falso. A provenance registra essa restrição.
''')

catalog=json.loads((ROOT/'docs/domains/RESOURCE_CATALOG.json').read_text())
rows=['# Catálogo de domínios','', '| Recurso | Rota | Estado inicial | Papéis principais | Evento |','|---|---|---|---|---|']
for r in catalog:rows.append(f"| `{r['name']}` | `/api/v1/{r['path']}` | `{r['initial_state']}` | {', '.join(r['roles'])} | `{r['event_prefix']}*` |")
rows.extend(['','Os 47 recursos usam persistência real, autorização, optimistic concurrency, auditoria e outbox no kernel genérico. Isso não significa que todas as particularidades legais de cada domínio estejam homologadas com provedores externos. Planejamento, frequência, branding, App Factory e contratos possuem implementações especializadas além do kernel.'])
write('docs/domains/MODULE_CATALOG.md','\n'.join(rows))

write('docs/security/SECURITY_MODEL.md','''# Segurança e LGPD

## Controles implementados

- Argon2id para senha e JWT curto com refresh rotativo;
- hostname confiável como fronteira do tenant;
- RBAC granular e pontos de ABAC contextual;
- correlation/request ID, auditoria antes/depois e motivo;
- idempotency key em mutações críticas;
- sanitização SVG e upload com hash;
- CSP no frontend servido por Nginx;
- containers não root, filesystem read-only e redes internas;
- secrets somente por arquivo/secret manager;
- logs sem payload sensível por padrão;
- backup isolado e verificação de hash;
- scanner local de padrões de segredo.

## Controles preparados

2FA/passkeys, HSM/KMS, antivírus ClamAV, certificate pinning, WAF, rate limit de borda, PAdES/ICP-Brasil e providers governamentais possuem contratos/configuração, mas exigem infraestrutura e homologação.

## Dados de menores

Acesso a saúde, localização, biometria, fotos e medicação deve depender de finalidade, base legal, consentimento quando aplicável, escopo de papel e auditoria de visualização. Nenhum desses providers fica habilitado por padrão.
''')

write('docs/deployment/LOCAL.md','''# Execução local

## Núcleo sem containers

```bash
cd backend
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Defina `APP_DEMO_MODE=true` somente em ambiente isolado. Hosts de exemplo precisam ser enviados no cabeçalho `Host`; o domínio desconhecido é rejeitado.

## Frontends

Os diretórios `apps/*/dist` são builds PWA estáticos determinísticos. O código Vue 3/TypeScript está em `apps/*/src`. Como as dependências npm não estavam em cache e a rede foi proibida, a compilação Vite real não foi executada nesta revisão.
''')
write('docs/deployment/SELF_HOSTED.md','''# Instalação self-hosted

1. Revise capacidade de CPU, RAM, storage e política de backup.
2. Gere secrets locais com `scripts/local/init-secrets.sh`.
3. Preencha `.env` sem copiar valores sensíveis para logs.
4. Execute `docker compose config` e scans das imagens.
5. Suba primeiro dados/init, depois aplicação e observabilidade.
6. Provisione tenant por domínio; não edite banco diretamente.
7. Teste restore antes da entrada em produção.

```bash
cp .env.example .env
bash scripts/local/init-secrets.sh runtime-secrets
docker compose -f compose.yaml -f compose.production.yaml config
docker compose -f compose.yaml -f compose.production.yaml up -d
```

O runtime de containers não estava disponível na construção; esses comandos são instruções futuras, não evidência de execução.
''')
write('docs/deployment/CLOUDPANEL.md','''# CloudPanel

Use um site reverse proxy para a porta publicada somente em loopback. TLS de origem deve permanecer válido e o acesso direto deve ser bloqueado. Não exponha PostgreSQL, Redis, RabbitMQ, MinIO ou Grafana. O Cloudflare Tunnel, quando contratado, deve terminar em gateway interno separado para Control Plane e Tenant Plane.
''')
write('docs/deployment/DOCKGE.md','''# Dockge

Importe `compose.yaml` e `compose.production.yaml`, preserve o nome do projeto `pige360`, configure `PIGE360_SECRETS_DIR` fora do diretório público e não altere nomes de volumes existentes durante atualização. Aplique migrations por `pige360-app-init` antes de trocar a imagem ativa.
''')
write('docs/deployment/PORTAINER.md','''# Portainer

Crie stack com secrets externos ou bind protegido. Desabilite edição pública de `.env`, restrinja endpoints e use webhook de atualização somente depois de revisão. O pacote local não contém webhook nem credencial de Portainer.
''')

write('docs/operations/BACKUP_RESTORE.md','''# Backup e restore

## Escopo por tenant

Backup contém banco lógico/dedicado, prefixo/bucket, manifest, hashes, configuração e chaves necessárias sob custódia separada. Não combine dois tenants em um archive sem catálogo explícito.

## Teste local executado

`scripts/backup/test_backup_restore.py` cria Alpha e Beta, grava dados/objeto em ambos, gera backup somente de Alpha, restaura em diretório limpo, verifica SHA-256 e confirma ausência de Beta. O relatório fica em `release/artifacts/backup-restore/report.json`.

## Produção

Use `pg_dump --format=custom`, snapshot/versionamento de objetos, criptografia, retenção, legal hold e restore em infraestrutura isolada. A restauração deve validar tenant UUID antes de ativar hostnames.
''')
write('docs/operations/OBSERVABILITY.md','''# Observabilidade

A stack inclui OpenTelemetry Collector, Prometheus, Grafana e Loki. Toda operação deve carregar correlation ID, tenant técnico, módulo, latência e resultado, sem conteúdo sensível.

Health checks:

- `/api/v1/health/live` — processo vivo;
- `/api/v1/health/ready` — storage do plano resolvido;
- Nginx `/healthz`;
- checks nativos de PostgreSQL, Redis, RabbitMQ e MinIO.

Alertas mínimos: erro por domínio, fila/DLQ, atraso de outbox, latência p95, certificado, backup, espaço, falha de login, vazamento de tenant e provider degradado.
''')
write('docs/operations/RUNBOOK.md','''# Runbook operacional

## API indisponível

1. Verifique readiness e dependências.
2. Correlacione por request ID.
3. Não reinicie banco antes de capturar evidência.
4. Se outbox acumulou, preserve a ordem e reprocese com idempotência.

## Tenant degradado

1. Confirme hostname e status no Control Plane.
2. Valide banco/bucket exclusivos.
3. Suspenda somente o tenant afetado.
4. Registre sessão de suporte com motivo.

## Build de app falhou

1. Preserve build ID, brand/manifest version e toolchain.
2. Nunca reutilize workspace com segredo de outro tenant.
3. Limpe ambiente efêmero.
4. Reprocessar mantém a mesma idempotency key quando a entrada não mudou.
''')
write('docs/operations/INTEGRATION_STATUS.md','''# Status das integrações

| Integração | Estado desta entrega | Execução real |
|---|---|---|
| PostgreSQL assíncrono | adapter e migrations preparados | não, servidor ausente |
| Redis/RabbitMQ/MinIO | contratos e Compose | não, runtime de containers ausente |
| Cloudflare/Tunnel/SaaS | providers/configuração desabilitados | não, sem rede/credenciais |
| Mailcow IMAP/SMTP/API | contrato desabilitado | não |
| Evolution API | adapter/configuração desabilitados | não |
| Bancos/PIX/CNAB | recursos, idempotência e contrato | não homologado |
| NF-e/NFC-e/NFS-e | domínio genérico, providers e storage contratados | não homologado com SEFAZ/município |
| IBPT | configuração e adapter previstos | nenhuma consulta realizada |
| GOV.BR | provider condicional e status `not_configured` | não homologado |
| ICP-Brasil | contrato/fixture e política | sem certificado real |
| Google Play/App Store | workflows condicionais | sem upload |

Mocks permanecem restritos a teste/homologação e não são apresentados como provider real.
''')
write('docs/operations/RISK_REGISTER.md','''# Riscos residuais reais

| Risco | Evidência | Impacto | Tratamento antes de produção |
|---|---|---|---|
| Imagens Docker não executadas | Docker/Podman ausentes | incompatibilidade pode passar despercebida | build, scan e smoke test em engine real |
| Apps Tauri não compilados | Rust/Cargo ausentes | erro nativo possível | matriz Windows/Linux/macOS |
| APK/AAB não compilados | Android SDK/Gradle ausentes | erro mobile possível | runner Android fixado e teste em dispositivo |
| iOS não compilado | Xcode/macOS ausentes | `.app/.xcarchive/IPA` não comprovados | runner macOS e assinatura condicional |
| Vue/Vite sem bundle de dependências | cache npm insuficiente e rede proibida | divergência do bundle estático | `npm ci` e build Vite em CI autorizado |
| Provedores externos não homologados | sem credenciais/rede | emissão/assinatura/envio não comprovados | homologação por provider e protocolo |
| Domínios amplos usam kernel genérico | 47 recursos persistidos | regras específicas ainda requerem aprofundamento | testes e regras por agregado prioritário |
| Pins opcionais não baixados | requirements de produção não resolvido localmente | incompatibilidade de dependência | gerar lock com hashes em CI controlado |
| ZIP de branding com quatro referências ausentes | checksum interno | rastreabilidade incompleta da fonte | obter arquivos originais ou atualizar manifesto oficial |
''')
write('docs/operations/LOCAL_EXECUTION_REPORT.md','''# Relatório de execução local

O relatório final gerado por `scripts/ci/run-all.sh` é a fonte de verdade para comandos e resultados. Esta construção não abriu conexão com hospedagem de código, registro, loja ou serviço de deploy.

Categorias:

- **passed:** comando executado e retorno zero;
- **skipped_not_configured:** toolchain/segredo ausente e nenhum artefato falso criado;
- **structural_only:** manifesto/OCI validado por estrutura, sem execução do runtime;
- **not_homologated:** integração implementada por contrato, sem protocolo real.
''')

write('docs/branding/BRANDING.md','''# Branding e white-label

A marca PIGE360 pertence às superfícies globais. Tenant usa somente seu `TenantBrandKit`, salvo co-branding explicitamente habilitado.

## Camadas

- `packages/design-tokens`: paleta/tipografia/spacing;
- `packages/ui`: `BrandProvider` e componentes;
- `packages/tenant-branding`: ativos e manifestos versionados;
- Branding Studio: preview, contraste, publicação e rollback;
- App Factory: separa branding de build e branding de runtime.

Os 132 screenshots foram escaneados: HTML de contexto tenant não contém PIGE360, ARGWS, WWSoftwares nem nome histórico. O pacote oficial foi preservado e inventariado por hash. Quatro referências citadas no `SHA256SUMS.txt` original não estavam no ZIP.
''')
write('docs/app-factory/APP_FACTORY.md','''# App Factory

O manifesto do tenant fixa tenant, brand version, app, identifier, hosts, features e secret references. Build request é idempotente e registra toolchain, canal, artifact, SBOM e provenance.

Estados: `awaiting_branding`, `ready`, `queued`, `building`, `testing`, `signing`, `available`, `failed`, `revoked`, `superseded`.

A ausência de keystore/certificado gera `skipped_not_configured`; nunca cria arquivo assinado falso. Apps dedicados não permitem troca arbitrária de tenant. O exemplo validado está em `deploy/local/tenant-app-manifest.demo.yaml`.
''')
write('docs/mobile/OFFLINE_SYNC.md','''# Offline e sincronização

Cada usuário/tenant possui banco local e chave no secure storage. A transação local grava alteração e outbox. O servidor recebe idempotency key, valida revisão e responde com checkpoint. Conflitos não são sobrescritos silenciosamente.

Planejamento e chamada armazenam somente turmas/períodos autorizados. Período fechado rejeita atualização. Logout revoga token e limpa dados conforme política. Anexos temporários permanecem criptografados.
''')
write('docs/mobile/MOBILE_DESKTOP_BUILDS.md','''# Builds mobile e desktop

Fontes Tauri 2 estão em `apps/*/src-tauri`. Os scripts verificam toolchain antes de compilar e retornam `SKIPPED_NOT_CONFIGURED` quando ausente.

Artefatos previstos:

- Windows x64/x86;
- Linux x64/ARM64;
- macOS Intel/Apple Silicon;
- Android APK/AAB;
- iOS `.app`, `.xcarchive` e IPA unsigned técnica;
- assinatura somente com secrets temporários.

Nesta máquina não havia Rust, Android SDK nem Xcode. Portanto, nenhum instalador nativo está listado como build aprovado.
''')

write('docs/fiscal/FISCAL_ENGINE.md','''# Motor fiscal

O domínio separa operação comercial, perfil fiscal, ruleset versionado, documento, XML/protocolo e auditoria. O roteador decide NF-e, NFC-e ou NFS-e pela natureza da operação; pagamento não implica emissão globalmente.

Providers externos ficam desabilitados até certificado/credencial/homologação. XML autorizado deve ser imutável, armazenado por tenant e acompanhado de SHA-256. O kernel genérico e os contratos estão presentes, mas não houve emissão real nesta revisão local.
''')
write('docs/fiscal/IBPT.md','''# IBPT

O provider padrão declarado é `wwsoftwares`, com download CSV por UF, snapshot original, hash, vigência, diff e publicação atômica. Nunca deve ser consultado por venda e não substitui cálculo tributário real. `tributos_reais` e `tributos_aproximados_ibpt` são conceitos separados.

A sincronização ficou desabilitada e nenhuma URL foi acessada durante a construção.
''')
write('docs/fiscal/RTC_IBS_CBS.md','''# Reforma tributária IBS/CBS

Rulesets são versionados por regime, estabelecimento, operação e vigência. O modo pode ser `disabled`, `simulation_only`, `optional_emit` ou `required_emit`. NCM, NBS, LC 116, CNAE, código municipal e cClassTrib não são equivalentes.

A aplicação deve apresentar prontidão e divergências sem criar regra eterna por flag global. Homologação legal exige catálogos e schemas oficiais vigentes no momento do deploy.
''')
write('docs/banking/BANKING.md','''# Bancário

Providers suportam PIX, boleto, CNAB, OFX, extrato e conciliação. Todo webhook exige assinatura, replay protection, inbox e idempotência; uma parcela pode receber vários pagamentos e um pagamento pode alocar várias parcelas.

Não houve conexão bancária. Os recursos do domínio são persistidos e auditados, mas layouts de cada banco devem ser validados por contrato antes da produção.
''')
write('docs/mail/MAILCOW.md','''# Mailcow

Modos: `disabled`, `mailcow_managed`, `generic_imap_smtp`, `dedicated_mailcow`. API gerencia domínio/mailbox; IMAPS/SMTP tratam conteúdo; Mailcow permanece fonte oficial das caixas.

Provisionamento ocorre somente após `EmployeeEmploymentActivated`. Senhas nunca chegam ao frontend. DNS de e-mail é DNS-only e exige MX, PTR, SPF, DKIM e DMARC. A integração ficou desabilitada nesta execução.
''')
write('docs/contracts/SIGNATURES.md','''# Contratos e assinaturas

Contrato gerado congela snapshot e PDF, calcula SHA-256 e cria envelope. O ciclo de vida do contrato é independente do ciclo de cada signatário.

A assinatura eletrônica interna registra consentimento, ator, data UTC, documento/hash, IP/user-agent quando autorizado e pacote de evidências. ICP-Brasil e GOV.BR são providers condicionais; ausência de credencial não bloqueia o restante.

O teste local gera PDF, assina envelope e valida por código público sem expor conteúdo sensível.
''')

write('docs/testing/TEST_STRATEGY.md','''# Estratégia de testes

- unitários: ids, senha, estados, políticas e cálculos;
- integração local: FastAPI + bancos SQLite separados + storage;
- tenancy: hosts, tokens, registros e backup;
- planejamento: versão, aprovação, execução e conflito;
- frequência: offline, idempotência, correção, reabertura e risco;
- branding: sanitização SVG, contraste e vazamento de marca;
- App Factory: manifesto, build request e ausência de toolchain;
- contratos: snapshot, PDF, assinatura e validação pública;
- OpenAPI/SDK: operation IDs e tipos;
- visual: 40 telas, 132 arquivos, dimensões e hashes.

Testes PostgreSQL, containers, mobile/desktop e providers externos continuam obrigatórios em runners adequados.
''')
write('docs/api/SDK.md','''# OpenAPI e SDK TypeScript

`docs/api/openapi.json` e `.yaml` são exportados diretamente da aplicação. O SDK em `packages/api-sdk/src/generated` contém tipos e 324 métodos gerados. A validação impede `operationId` duplicado.

A autenticação envia Bearer token, mas o tenant continua sendo determinado pelo hostname da URL; o SDK não oferece parâmetro público de tenant.
''')

manuals={
'PLANEJAMENTO.md':('Planejamento de aulas','Crie plano anual/periódico/semanal ou por aula, associe currículo/habilidades, envie para revisão, agende e registre execução. Plano executado não é alterado retroativamente; crie versão/complemento. No offline, sincronize a outbox e resolva conflitos explicitamente.'),
'FREQUENCIA.md':('Chamada e frequência','Inicie a sessão, valide matrícula na data, marque presença/falta/atraso/saída, salve rascunho e envie. Aula cancelada não gera falta. Correção e reabertura exigem motivo e auditoria. Justificativa não vira presença automaticamente; a política versionada define o efeito.'),
'ADMINISTRADOR.md':('Administrador da plataforma','Gerencie tenants, domínios, licenças, branding e builds no Control Plane. Para entrar em escola, use sessão de suporte temporária com motivo; não use credencial do tenant nem acesse banco diretamente.'),
'ESCOLA.md':('Gestão da escola','Configure instituição, unidades, calendário, perfis, políticas, branding, módulos e integrações. Revise permissões e execute backup/restore antes de atualização.'),
'PROFESSOR.md':('Professor','Consulte turmas e currículo, prepare planos, faça chamada, registre conteúdo ministrado e finalize diário. O app restringe cache às atribuições autorizadas.'),
'FAMILIA.md':('Família','Acompanhe dependentes, frequência, notas, parcelas, cantina, contratos, eventos e solicitações. Documentos sensíveis usam link autenticado; mensagens não carregam segredo completo.'),
'PDV.md':('PDV e cantina','Abra caixa, identifique aluno, valide restrições/limites, finalize pagamento e aguarde sincronização fiscal/estoque. Venda offline fica na outbox e não deve ser duplicada.'),
'RH.md':('RH, folha e ponto','Mantenha vínculo, jornada e eventos com vigência. Fechamento de folha/ponto é auditado; correções geram eventos compensatórios.'),
'FISCAL.md':('Operação fiscal','Revise classificação e certificado, emita pelo documento adequado, acompanhe rejeição/retry e preserve XML/protocolo. Nunca altere XML autorizado.'),
}
for name,(title,body) in manuals.items():write('docs/user-guides/'+name,f'# {title}\n\n{body}\n\nToda ação crítica exige perfil autorizado e aparece na auditoria.')

write('docs/ci-cd/README.md','''# CI/CD preparado

Os 15 workflows em `.github/workflows` reproduzem validação, imagens, web, desktop, Android, iOS, white-label, segurança, release, self-hosted e restore. Publicação/deploy depende simultaneamente de input manual, variável `REMOTE_*_ENABLED` e environment protegido.

Nesta entrega, os workflows não foram enviados nem executados em provedor externo. O espelho está em `CI_CD_KIT_LOCAL`.
''')

print(json.dumps({'status':'generated','version':VERSION,'docs':len(list((ROOT/'docs').rglob('*.md')))},ensure_ascii=False))
