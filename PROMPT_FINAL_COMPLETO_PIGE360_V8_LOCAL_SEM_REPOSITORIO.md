> **Cópia operacional normalizada:** por instrução posterior do proprietário, toda referência nominal histórica foi removida; os requisitos funcionais, técnicos, visuais e de aceite permanecem inalterados. Hash SHA-256 do contrato original lido integralmente: `33d177211b3cfd4b80a19a61f351d5bd02950003bf2cda1d448a369e6686bc27`.

# PROMPT FINAL — CONSTRUÇÃO INTEGRAL DO PIGE360

## 0. COMANDO PRINCIPAL

Atue como Arquiteto de Software Principal, Engenheiro de Plataforma, Engenheiro Backend, Engenheiro Frontend, Engenheiro Mobile, Engenheiro DevOps, Especialista em Segurança, Especialista Fiscal Brasileiro, Especialista em Folha/Departamento Pessoal e QA Lead.

Construa de ponta a ponta uma plataforma educacional brasileira completa, multi-tenant, SaaS e self-hosted, denominada oficialmente **PIGE360 — Plataforma Integrada de Gestão Educacional**.

Não entregue MVP, protótipo, prova de conceito, telas estáticas, módulos isolados, roadmap substituindo implementação, endpoints fictícios, botões sem ação, dados simulados misturados à produção, fluxos incompletos ou código apenas “preparado para o futuro”. Organize a execução internamente na ordem técnica necessária, mas continue trabalhando até que todo o escopo deste documento esteja implementado, integrado, testado, documentado e com builds aprovados.

Não interrompa a construção para pedir autorização entre módulos. Quando uma integração externa depender de credenciais, certificados, contas ou contratos ainda não fornecidos:

1. implemente integralmente o contrato, provider, telas, banco, filas, webhooks, idempotência, retries, health checks, mocks exclusivos de teste/homologação e documentação;
2. deixe a integração desabilitada por configuração;
3. não bloqueie os demais builds;
4. não apresente o provider mock como integração real validada;
5. ative automaticamente o job correspondente quando todos os segredos obrigatórios forem configurados.

A construção deve ocorrer **exclusivamente no workspace local disponibilizado pela ferramenta**, utilizando apenas os arquivos, anexos, templates e pacotes fornecidos nesta execução.

Regras obrigatórias:

- não conectar a serviços de hospedagem de código;
- não clonar, buscar, sincronizar ou atualizar conteúdo remoto;
- não autenticar em plataformas externas de versionamento;
- não executar comandos de envio ou publicação remota;
- não criar Pull Request;
- não criar release remota;
- não publicar imagens em registro remoto;
- não alterar nenhum projeto remoto;
- não depender de acesso de rede para concluir a construção;
- não pedir credenciais para publicação;
- gerar toda a aplicação, os workflows e os artefatos dentro do workspace local;
- entregar um pacote `.zip` integral, reproduzível e validado.

Antes de alterar arquivos:

- leia toda a documentação disponível localmente;
- inspecione Dockerfiles, Compose, scripts, migrations, manifests, lockfiles, infraestrutura e arquivos existentes no workspace;
- registre o estado inicial;
- preserve os recursos, padrões de segurança, matrizes e contratos já validados;
- identifique referências herdadas de outros produtos e corrija-as de forma controlada;
- não faça refatoração destrutiva ou reorganização abrupta;
- execute todas as validações localmente;
- não interrompa a construção por ausência de autenticação externa.

Os arquivos de CI/CD devem ser gerados como parte do pacote, completos e prontos para instalação futura, mas **não devem ser executados contra nenhum serviço remoto durante esta construção**.

A interface, documentação operacional e mensagens para o usuário devem usar **Português do Brasil** como idioma padrão, com infraestrutura de internacionalização para outros idiomas.

## 0.1. EXECUÇÃO LOCAL, ENTREGA ZIP E CI/CD PREPARADO

### Regra de execução

O trabalho deve permanecer no workspace local do início ao fim.

É proibido durante esta execução:

```text
acessar hospedagem remota de código
sincronizar histórico remoto
enviar código
publicar tags
criar releases remotas
publicar imagens em registro remoto
executar deploy remoto
abrir Pull Request
solicitar autenticação para essas operações
```

### Fluxo obrigatório

```text
arquivos e anexos locais
    ↓
inventário e validação inicial
    ↓
implementação integral
    ↓
testes e builds locais
    ↓
geração dos workflows CI/CD
    ↓
geração de imagens OCI locais
    ↓
geração dos pacotes de release
    ↓
checksums, SBOM e manifests
    ↓
pacote ZIP final
```

### CI/CD como arquivos inertes

Gerar os arquivos:

```text
.github/workflows/
scripts/ci/
scripts/release/
infra/docker/base/
docs/ci-cd/
```

Esses arquivos devem:

- ser sintaticamente válidos;
- suportar builds completos;
- possuir publicação remota desabilitada por padrão;
- exigir habilitação manual futura para qualquer upload;
- não conter credenciais;
- não ser executados pela ferramenta contra serviços externos;
- permitir substituição do provedor de CI/CD e do registro de imagens;
- gerar localmente os mesmos manifests, checksums e pacotes.

### Imagens e registro

Construir e validar imagens OCI localmente.

A configuração pode prever um registro remoto opcional para uso futuro, porém:

```dotenv
REMOTE_CI_ENABLED=false
REMOTE_REGISTRY_ENABLED=false
REMOTE_RELEASE_ENABLED=false
REMOTE_DEPLOY_ENABLED=false
```

Nenhuma dessas capacidades deve ser ativada nesta execução.

### Versionamento local

Use Semantic Versioning nos manifests e nomes dos pacotes, sem publicar tags remotas.

Exemplos:

```text
1.0.0-alpha.1
1.0.0-beta.1
1.0.0-rc.1
1.0.0
```

### Pacotes obrigatórios

```text
PIGE360-<version>-source.zip
PIGE360-<version>-release-bundle.zip
PIGE360-<version>-self-hosted.zip
PIGE360-<version>-workflows-ci-cd.zip
```

### Evidências obrigatórias

Ao concluir, apresentar:

```text
workspace utilizado
árvore final
versão
pacote ZIP completo
SHA-256
release manifest
relatório de testes
relatório de builds
artifacts locais
SBOM
provenance
imagens OCI locais e digests
workflows gerados
status das integrações
```

---

## 0.2. NOME OFICIAL PIGE360 E MIGRAÇÃO SEM REFATORAÇÃO ABRUPTA

A partir desta revisão, o nome oficial e visível da plataforma é:

```text
PIGE360
Plataforma Integrada de Gestão Educacional
```

Regras de identidade:

```dotenv
PRODUCT_NAME=PIGE360
PRODUCT_FULL_NAME=PIGE360 — Plataforma Integrada de Gestão Educacional
PRODUCT_SLUG=pige360
PRODUCT_PUBLISHER=ARGWS / WWSoftwares
PRODUCT_IDENTIFIER_PREFIX=br.com.argws.pige360
```
- novas telas;
- novos documentos;
- novos aplicativos;
- instaladores;
- splash screens;
- ícones com wordmark;
- metadados de loja;
- e-mails;
- relatórios;
- contratos;
- títulos de página;
- notificações;
- imagens de release;
- documentação nova.

As imagens e o pacote de branding antigos continuam válidos como referência para:

- símbolo do livro conectado;
- geometria visual;
- paleta;
- gradientes;
- tipografia;
- patterns;
- composição;
- diretrizes de interface.

Todo texto, wordmark e assinatura nominal devem ser regenerados como **PIGE360**, sem deformar o símbolo nem alterar abruptamente a identidade já aprovada.

### Migração técnica controlada

Antes de renomear qualquer identificador técnico, inventarie:

- serviços Docker;
- nomes de containers;
- volumes;
- networks;
- bancos;
- schemas;
- buckets;
- object keys;
- variáveis de ambiente;
- bundle IDs;
- package IDs;
- manifests;
- update URLs;
- imagens OCI;
- workflows CI/CD;
- scripts;
- backups;
- integrações externas;
- instalações existentes.

A migração deve aplicar:

1. novo nome visível imediatamente;
2. aliases temporários para variáveis legadas quando existirem consumidores;
3. volumes e bancos preservados por nome explícito, sem recriação destrutiva;
4. migrations de dados idempotentes;
5. compatibilidade de leitura durante a janela de transição;
6. novos nomes `pige360-*` para recursos recém-criados;
7. backup antes de qualquer renomeação estrutural;
8. rollback documentado;
9. testes de upgrade a partir da instalação anterior;
10. remoção do legado apenas após comprovar ausência de consumidores.

### Canais de distribuição preparados

A construção deve preparar, sem executar remotamente:

```text
workflows CI/CD
artifacts locais
pacotes ZIP
imagens OCI locais
central privada de downloads dos tenants
integrações opcionais com lojas, quando configuradas futuramente
```

Durante esta execução, nenhum canal remoto deve ser acessado, autenticado ou publicado.


O usuário anexará imagens de referência, screenshots, mockups, fluxos, documentos, relatórios, ícones, logos e kits de branding. Esses anexos devem ser inspecionados integralmente e tratados como requisitos obrigatórios de UX/UI e identidade visual. O branding oficial anexado posteriormente substitui qualquer ativo provisório sem exigir refatoração das regras de negócio.

A marca do proprietário da plataforma deve aparecer somente no Control Plane e nas superfícies globais da operadora. Cada tenant deve possuir domínio, branding, documentos, portais e aplicações próprios. Quando o contrato comercial da escola habilitar aplicativos dedicados, a plataforma deve gerar, testar, assinar quando houver segredos e disponibilizar os aplicativos mobile e desktop personalizados do tenant em sua central privada de downloads.

---

# 1. OBJETIVO DO PRODUTO

Criar um ERP educacional integral e modular que atenda, por parametrização:

- escolas privadas;
- escolas públicas municipais, estaduais ou redes conveniadas;
- educação infantil;
- ensino fundamental;
- ensino médio;
- educação técnica e profissionalizante;
- ensino superior;
- cursos livres;
- grupos educacionais;
- mantenedoras;
- secretarias de educação;
- instituições com múltiplas unidades, campi ou polos;
- operação SaaS;
- operação self-hosted;
- operação white-label;
- instalações compartilhadas, dedicadas e enterprise.

A plataforma deve centralizar:

- gestão institucional;
- multi-tenancy;
- pessoas;
- alunos;
- responsáveis;
- colaboradores;
- professores;
- captação;
- inscrição;
- processo seletivo;
- secretaria;
- matrícula;
- acadêmico;
- pedagógico;
- financeiro;
- bancário;
- fiscal;
- vendas;
- PDV;
- cantina;
- estoque;
- compras;
- patrimônio;
- eventos;
- viagens;
- avisos;
- solicitações e protocolos;
- comunicação;
- WhatsApp;
- e-mail institucional;
- Mailcow;
- RH;
- setor pessoal;
- folha de pagamento;
- controle de ponto;
- biblioteca;
- transporte;
- saúde e ocorrências;
- documentos;
- assinaturas;
- portais;
- aplicativos;
- relatórios;
- auditoria;
- integrações;
- observabilidade;
- administração da plataforma.

---

# 2. DIRETRIZES INEGOCIÁVEIS

## 2.1. Produto completo

Não considerar a aplicação concluída enquanto houver:

- telas sem persistência real;
- rotas sem autorização;
- ações sem auditoria;
- integrações sem idempotência;
- filas sem reprocessamento;
- jobs sem tenant;
- arquivos sem hash;
- módulos sem testes;
- aplicativos sem build;
- workflows quebrados;
- migrations não testadas;
- TODOs em fluxos críticos;
- mocks ativos em produção;
- dados de demonstração fora do modo demo;
- isolamento de tenant não comprovado;
- emissão fiscal sem armazenamento de XML/eventos;
- lançamentos financeiros mutáveis sem trilha;
- baixa de estoque sem vínculo transacional;
- permissões genéricas que exponham dados;
- credenciais em código, banco aberto, logs ou frontend.

## 2.2. Arquitetura inicial

Use **monólito modular orientado a domínios**, com processos separados para workers, scheduler, gateway e aplicações cliente. Não fragmente prematuramente em dezenas de microserviços. Mantenha contratos claros para permitir extração futura de domínios sem reescrever as regras de negócio.

## 2.3. Fonte de verdade

- PostgreSQL: dados transacionais e metadados.
- S3/MinIO: arquivos e objetos.
- Mailcow: conteúdo oficial das caixas de e-mail.
- Redis: cache, locks, sessões técnicas e coordenação efêmera.
- RabbitMQ: eventos e tarefas.
- SQLite criptografado nos aplicativos: cache offline e outbox local.
- Nenhum aplicativo cliente acessa PostgreSQL, RabbitMQ, Redis ou MinIO diretamente.

## 2.4. Histórico e imutabilidade

Não sobrescrever silenciosamente informações acadêmicas, financeiras, fiscais, trabalhistas ou administrativas consolidadas. Aplicar:

- versionamento;
- vigência;
- eventos;
- lançamentos compensatórios;
- histórico de estados;
- justificativa;
- usuário responsável;
- data/hora;
- antes/depois;
- correlação;
- trilha de auditoria.

---


# 2.5. IDENTIDADE E PARÂMETROS CENTRALIZADOS

Use uma identidade provisória centralizada, nunca espalhada pelo código:

```dotenv
PRODUCT_NAME=PIGE360
PRODUCT_FULL_NAME=PIGE360 — Plataforma Integrada de Gestão Educacional
PRODUCT_SLUG=pige360
PRODUCT_PUBLISHER=ARGWS / WWSoftwares
PRODUCT_IDENTIFIER_PREFIX=br.com.argws.pige360
PLATFORM_CONTROL_BASE_DOMAIN=platform.wws.app
TENANT_DEFAULT_BASE_DOMAIN=school.argws.com.br
```

Identificadores iniciais, substituíveis por configuração antes da primeira publicação:

```text
br.com.argws.pige360.family
br.com.argws.pige360.teacher
br.com.argws.pige360.student
br.com.argws.pige360.admin
br.com.argws.pige360.pos
br.com.argws.pige360.kiosk
br.com.argws.pige360.timeclock
br.com.argws.pige360.desktop
```

Centralize nome, marca, ícones, cores, publisher, bundle IDs, package IDs, URLs, política de privacidade, termos, contatos e metadados de loja. O branding de cada tenant deve ser configurável sem recompilar o backend.

---

# 2.6. IMAGENS DE REFERÊNCIA, UX E BRANDING OBRIGATÓRIO

## 2.6.1. Uso obrigatório dos anexos visuais

O usuário anexará ao projeto imagens de referência, screenshots, wireframes, mockups, exemplos de relatórios, impressões, layouts desktop/mobile, ícones, logotipos e um kit de branding. Esses anexos são requisitos normativos de interface e não materiais meramente ilustrativos.

Antes de implementar ou alterar qualquer frontend, a ferramenta deve:

1. localizar e inspecionar integralmente todos os anexos visuais disponíveis;
2. preservar os arquivos originais sem sobrescrevê-los;
3. calcular SHA-256 de cada anexo;
4. criar um inventário em `docs/design/reference-assets/manifest.json`;
5. criar `docs/design/reference-map/REFERENCE_MAP.md`;
6. mapear cada imagem para aplicação, rota, módulo, breakpoint e componente correspondente;
7. registrar o que deve ser reproduzido exatamente e o que pode ser estendido por consistência;
8. identificar versões concorrentes da mesma tela;
9. selecionar como referência canônica a versão mais recente explicitamente indicada pelo usuário;
10. extrair tokens visuais para o design system;
11. implementar testes de regressão visual baseados nas referências;
12. gerar screenshots reais das telas implementadas para comparação;
13. não solicitar novamente arquivos ou informações já presentes nos anexos.

Estrutura mínima do mapa:

```text
arquivo de referência
hash SHA-256
aplicação alvo
rota/tela
plataforma: web | desktop | android | ios | kiosk
breakpoint
componentes visíveis
hierarquia
navegação
cores
espaçamentos
proporções
estados
interações
texto obrigatório
observações do usuário
prioridade
status de implementação
screenshot de validação
```

Não substituir telas explicitamente referenciadas por dashboards ou templates genéricos. Não misturar elementos de versões antigas e novas sem justificativa. Não ignorar imagens por já existir uma implementação funcional.

## 2.6.2. Precedência de requisitos

Em caso de conflito, aplicar a seguinte ordem:

1. segurança, isolamento, legislação e integridade de dados;
2. instrução explícita mais recente do usuário;
3. branding final anexado e aprovado;
4. imagem de referência marcada como canônica;
5. especificação funcional deste prompt;
6. design system derivado;
7. extensão visual coerente para telas sem referência.

Quando uma referência visual omitir um comportamento necessário, preservar o visual e completar a funcionalidade de forma coerente. Não remover função obrigatória apenas porque ela não aparece no screenshot.

## 2.6.3. Extração e centralização do design system

A partir do branding e das referências, gerar:

```text
packages/design-tokens/
packages/ui/
packages/tenant-branding/
docs/design/brand-guides/
docs/design/screen-catalog/
```

Extrair e versionar:

- paleta principal, secundária e semântica;
- contraste e acessibilidade;
- tipografia;
- escalas de fonte;
- espaçamento;
- grid;
- breakpoints;
- radius;
- bordas;
- elevação;
- sombras;
- ícones;
- densidade;
- motion;
- duração e easing;
- tamanhos de toque;
- estados hover, focus, active, disabled, loading, error e success;
- tabelas;
- formulários;
- filtros;
- sidebars;
- titlebars;
- cards;
- gráficos;
- modais;
- toast;
- relatórios;
- documentos;
- impressões;
- splash screens;
- instaladores.

Não espalhar cores, logos, fontes, nomes, domínios ou ícones diretamente nos componentes. Todos devem vir de tokens, configuração ou manifesto de branding.

## 2.6.4. Branding da plataforma e branding do tenant

Existem dois contextos completamente distintos.

### Branding da plataforma

Usar a marca do proprietário da plataforma — branding que será anexado pelo usuário, como ARGWS/WWSoftwares ou a marca final escolhida — somente em:

- Console global do Control Plane;
- login da equipe da plataforma;
- administração global de tenants;
- infraestrutura, releases, licenciamento e suporte global;
- páginas institucionais da plataforma;
- documentos próprios da operadora da plataforma;
- download center global, quando não estiver no contexto de uma escola.

### Branding do tenant

Todas as superfícies pertencentes à escola devem usar exclusivamente o branding do tenant, salvo co-branding explicitamente ativado pelo próprio tenant:

- administração web da escola;
- portal público;
- portal da família;
- portal do professor;
- portal do aluno;
- aplicativos móveis;
- aplicativos desktop;
- PDV;
- cantina;
- kiosk;
- controle de ponto;
- e-mails;
- avisos;
- contratos;
- documentos;
- PDFs;
- relatórios;
- recibos;
- telas de autenticação;
- páginas de domínio e erro;
- central de downloads da escola;
- notificações;
- splash screens;
- instaladores;
- atualizador.

Não deixar a marca da plataforma vazar para uma superfície white-label da escola. Uma atribuição discreta “Tecnologia por ...” somente pode aparecer quando a política comercial permitir.

## 2.6.5. Kit de branding por tenant

Criar um `TenantBrandKit` versionado contendo, no mínimo:

```text
legal_name
trade_name
short_name
slug técnico imutável
app_display_name
publisher_name
support_name
support_email
support_phone
website
privacy_policy_url
terms_url
primary_domain
secondary_domains
logo_primary_light
logo_primary_dark
logo_horizontal_light
logo_horizontal_dark
logo_symbol
monochrome_logo
favicon
app_icon_source
notification_icon
splash_source
installer_banner
installer_sidebar
store_feature_graphic
social_share_image
email_header
pdf_header
pdf_footer
watermark
signature_stamp
primary_color
secondary_color
accent_color
semantic_colors
typography_family
typography_fallbacks
border_radius_scale
icon_style
illustration_style
photography_style
light_theme
dark_theme
co_branding_policy
```

Os ativos devem ser armazenados no bucket do tenant com SHA-256, versionamento e metadados. Gerar derivados automaticamente em tamanhos e formatos necessários, sem alterar os originais.

O branding anexado pelo usuário para a plataforma e os brandings anexados para cada escola devem ser tratados como fonte oficial. Não inventar logotipo definitivo quando o arquivo oficial existir.

Estados do branding:

```text
draft
awaiting_assets
validating
ready
active
superseded
archived
failed
```

Não ativar um kit sem validar dimensões, transparência, contraste, legibilidade, licenças dos ativos e requisitos mínimos de cada plataforma.

## 2.6.6. Branding Studio

Criar uma interface de Branding Studio no Console global e, conforme permissão, no tenant para:

- upload de logos e fontes licenciadas;
- configuração de cores;
- preview claro/escuro;
- preview web, mobile, desktop, PDF, e-mail e instalador;
- validação de contraste;
- geração de ícones;
- geração de splash;
- favicon;
- cabeçalhos e rodapés;
- versão;
- aprovação;
- publicação;
- rollback;
- comparação entre versões;
- histórico;
- auditoria.

Não compartilhar ativos entre tenants sem autorização explícita.

## 2.6.7. Geração das imagens e ativos do projeto

Produzir e manter um catálogo visual completo. Quando a ferramenta possuir capacidade de geração de imagens, criar imagens idealizadas usando o branding anexado. Quando não possuir, implementar as telas reais e gerar screenshots automatizados com Playwright, Tauri, Android e iOS nos breakpoints definidos.

Entregáveis visuais mínimos:

```text
01-control-plane-dashboard
02-tenant-admin-dashboard
03-public-school-portal
04-family-mobile-home
05-family-finance-and-canteen
06-teacher-mobile-diary
07-teacher-attendance-offline
08-student-mobile-home
09-admin-mobile-dashboard
10-pos-canteen-sale
11-pos-products-and-nfce
12-kiosk-self-service
13-timeclock-terminal
14-academic-secretary
15-enrollment-workflow
16-pedagogical-dashboard
17-financial-dashboard
18-fiscal-nfe-nfce-nfse
19-tax-reform-ibs-cbs
20-contracts-and-signatures
21-govbr-signature-flow
22-mailcow-inbox
23-employee-and-hr
24-payroll
25-timekeeping
26-events-and-travel
27-notices
28-service-requests
29-inventory
30-library
31-transportation
32-cloudflare-domain-provisioning
33-tenant-branding-studio
34-tenant-app-factory
35-tenant-download-center
36-platform-health-and-observability
37-reports-and-print-preview
38-desktop-admin
39-mobile-app-suite
40-full-product-architecture-board
```

Para cada item, gerar variantes quando aplicável:

```text
desktop 1920x1080
desktop 1366x768
tablet landscape
tablet portrait
mobile Android
mobile iOS
light theme
dark theme
loading
empty
error
success
permission denied
offline
```

Salvar screenshots reais de validação em:

```text
docs/design/generated-previews/<tenant-or-platform>/<app>/<route>/<viewport>.png
```

Criar uma página de catálogo visual navegável e um relatório de diferenças.

Imagens idealizadas não substituem testes das interfaces reais. Após implementar as telas, gerar screenshots reais e usar estas como evidência de conclusão.

## 2.6.8. Regressão visual

Implementar:

- Playwright screenshot tests para web;
- screenshots Tauri para desktop;
- testes de screenshot para Android e iOS quando suportados;
- baseline versionada;
- tolerância mínima e justificada;
- comparação por rota e breakpoint;
- artefatos de diff no CI;
- aprovação explícita para atualizar baseline;
- proteção contra regressão de branding entre tenants;
- teste garantindo que a marca da plataforma não apareça em superfícies white-label.

O CI deve falhar quando uma tela canônica divergir além da tolerância aprovada.

---

# 2.7. APP FACTORY E WHITE-LABEL POR TENANT

## 2.7.1. Regra de produto

Cada escola contratante deve poder receber aplicativos móveis e desktop próprios, separados e personalizados, gerados pela plataforma quando o contrato comercial habilitar essa capacidade.

Não criar forks manuais permanentes por escola. Usar código-base compartilhado, manifesto imutável por tenant, feature flags, resource packs e builds isolados. Permitir repositório dedicado somente em modalidade enterprise expressamente configurada.

Cada app dedicado deve ser bloqueado ao tenant correto e não oferecer troca arbitrária de domínio ou tenant.

O gatilho comercial padrão deve ser:

```text
TenantContractActivated
ou
TenantAppPackagePurchased
```

A ativação deve gerar uma solicitação idempotente de aplicativos conforme os produtos contratados.

## 2.7.2. Aplicativos geráveis por tenant

Suportar, conforme o plano contratado:

```text
family-mobile
teacher-mobile
student-mobile
admin-mobile
pos-mobile
kiosk
timeclock
desktop-admin
pos-desktop
```

Plataformas:

```text
Android APK/AAB
iOS app/IPA
Windows x64/x86
Linux x64/ARM64
macOS Intel/Apple Silicon
PWA dedicada
```

Cada aplicativo deve possuir:

- nome próprio da escola;
- ícone próprio;
- splash própria;
- cores próprias;
- bundle/package ID próprio;
- domínio próprio;
- deep links próprios;
- configuração própria de push;
- update URL própria;
- assinatura própria quando contratada;
- políticas e módulos contratados;
- canal de release próprio;
- histórico próprio;
- central de download própria.

## 2.7.3. Manifesto do aplicativo do tenant

Criar `tenant-app-manifest.yaml` versionado:

```yaml
tenant_id: 019...
tenant_code: s-7km4q2x9d8
brand_version: 3
release_channel: stable
apps:
  family:
    enabled: true
    display_name: Colégio Exemplo Família
    identifier: br.com.colegioexemplo.family
    api_url: https://api.colegioexemplo.com.br
    web_url: https://familia.colegioexemplo.com.br
    update_url: https://apps.colegioexemplo.com.br/family
    icon_asset_id: 019...
    splash_asset_id: 019...
    features:
      canteen: true
      finance: true
      transport: true
    signing:
      android_secret_ref: secrets/tenants/<tenant>/android
      ios_secret_ref: secrets/tenants/<tenant>/ios
```

O manifesto deve controlar:

- nomes;
- identificadores;
- domínios;
- marca;
- temas;
- recursos;
- permissões;
- deep links;
- universal links;
- app links;
- push;
- update channels;
- store metadata;
- políticas;
- secrets por referência;
- assinatura;
- versões;
- compatibilidade mínima;
- entitlements;
- feature flags.

Bundle ID/package ID deve ser estável após a primeira distribuição. Mudança de branding não pode alterar o identificador sem processo de migração explícito.

## 2.7.4. Entidades da App Factory

Implementar, no mínimo:

```text
tenant_brand_kits
tenant_brand_assets
tenant_brand_versions
app_products
tenant_app_entitlements
tenant_app_manifests
tenant_app_manifest_versions
app_build_requests
app_build_jobs
app_builds
app_build_artifacts
app_signing_profiles
app_distribution_channels
app_releases
app_release_artifacts
app_update_manifests
app_download_events
app_store_connections
app_store_submissions
```

Todas as entidades devem possuir tenant, estado, idempotência, auditoria e versionamento quando aplicável.

## 2.7.5. Processo automático de geração

Ao ativar o recurso contratado:

```text
TenantActivated ou TenantAppPackagePurchased
    ↓
validar domínio e branding
    ↓
validar manifesto
    ↓
gerar resource pack
    ↓
gerar ícones, splash, favicons e instaladores
    ↓
gerar configurações de API, deep links e update
    ↓
reservar bundle/package IDs
    ↓
criar build request idempotente
    ↓
executar build isolado
    ↓
executar testes
    ↓
assinar quando os segredos existirem
    ↓
gerar checksums, SBOM e manifest
    ↓
publicar no download center do tenant
    ↓
opcionalmente publicar nas lojas
    ↓
notificar tenant
```

Estados:

```text
not_requested
awaiting_contract
awaiting_branding
awaiting_domains
ready
queued
building
testing
signing
publishing
available
failed
revoked
superseded
```

## 2.7.6. Build farm

Criar build farm com workers isolados por sistema operacional:

```text
linux-builder
windows-builder
macos-builder
android-builder
ios-builder
```

Requisitos:

- filas separadas;
- ambiente efêmero;
- cache seguro;
- sem segredo em logs;
- secret injection temporária;
- limpeza após build;
- provenance;
- build ID;
- tenant ID;
- brand version;
- source commit;
- lockfiles;
- toolchain versions;
- artefatos imutáveis;
- retenção;
- reprocessamento;
- concorrência controlada;
- auditoria;
- assinatura de manifest;
- isolamento contra vazamento de ativos e segredos entre tenants.

## 2.7.7. Central de downloads por escola

Disponibilizar em domínio do tenant, por exemplo:

```text
apps.colegioexemplo.com.br
downloads.colegioexemplo.com.br
apps.s-7km4q2x9d8.school.argws.com.br
```

Recursos:

- branding da escola;
- autenticação opcional;
- controle de público;
- aplicativos disponíveis;
- sistema operacional;
- arquitetura;
- canal estável/homologação/beta;
- versão;
- changelog;
- data;
- tamanho;
- SHA-256;
- assinatura;
- SBOM;
- requisitos mínimos;
- QR Code para download;
- release notes;
- histórico;
- versão revogada;
- atualização obrigatória;
- auditoria de download;
- limite e rate limit;
- instruções de instalação;
- status de loja;
- links de TestFlight/Play quando configurados.

O download center de uma escola não deve exibir aplicativos de outro tenant.

## 2.7.8. Atualizações

Desktop:

- updater assinado;
- canais;
- manifest;
- rollback controlado;
- atualização obrigatória opcional;
- delta quando suportado;
- revogação;
- integridade.

Android:

- APK direto assinado para instalação privada;
- AAB para Play Console;
- update check pelo download center;
- não instalar silenciosamente sem mecanismo permitido pelo sistema operacional ou MDM.

iOS:

- IPA assinada conforme método autorizado;
- App Store/TestFlight quando configurado;
- distribuição privada/MDM/Ad Hoc/Enterprise somente quando elegível;
- IPA unsigned apenas como artefato técnico, nunca descrita como instalável.

## 2.7.9. Branding de build e branding em runtime

Separar:

```text
build-time branding:
  app name
  bundle/package ID
  app icon
  splash
  installer
  publisher
  signing
  deep links

runtime branding:
  colors
  logos internos
  banners
  conteúdo
  temas
  módulos
  textos
  domínio
```

Mudanças somente de runtime podem ser publicadas sem recompilar quando seguras. Mudanças de ícone, identificador, splash nativo, assinatura ou metadados exigem novo build e incremento de versão.

## 2.7.10. Segurança dos apps dedicados

- pin do tenant no manifesto assinado;
- allowlist exata de hostnames;
- validação de issuer/audience;
- deep links assinados;
- certificate pinning configurável sem impedir rotação segura;
- banco SQLite separado;
- chaves por app/tenant;
- remoção segura no logout;
- nenhuma credencial administrativa embutida;
- segredo de loja apenas no CI;
- feature entitlements assinados;
- revogação remota de versão;
- integridade do update manifest;
- bloqueio de troca arbitrária para outro tenant;
- testes garantindo ausência de ativos de outro tenant.

## 2.7.11. Coexistência com app genérico

Permitir opcionalmente um app genérico da plataforma para tenants sem pacote white-label, mas:

- não substituir os apps dedicados contratados;
- exigir descoberta segura por QR/link/domínio;
- separar dados por tenant;
- usar branding do tenant após seleção;
- nunca compartilhar sessão entre escolas.

## 2.7.12. APIs da App Factory e Branding

Criar, no mínimo:

```text
GET    /api/v1/platform/tenants/{id}/branding
POST   /api/v1/platform/tenants/{id}/branding/assets
POST   /api/v1/platform/tenants/{id}/branding/preview
POST   /api/v1/platform/tenants/{id}/branding/publish
POST   /api/v1/platform/tenants/{id}/branding/rollback

GET    /api/v1/platform/tenants/{id}/apps
POST   /api/v1/platform/tenants/{id}/apps/manifests
POST   /api/v1/platform/tenants/{id}/apps/builds
GET    /api/v1/platform/tenants/{id}/apps/builds/{build_id}
POST   /api/v1/platform/tenants/{id}/apps/builds/{build_id}/retry
POST   /api/v1/platform/tenants/{id}/apps/releases/{release_id}/publish
POST   /api/v1/platform/tenants/{id}/apps/releases/{release_id}/revoke
GET    /api/v1/platform/tenants/{id}/apps/artifacts

GET    /api/v1/apps/catalog
GET    /api/v1/apps/releases/{id}
GET    /api/v1/apps/releases/{id}/download
GET    /api/v1/apps/update/{app}/{platform}/{arch}
```

Downloads devem utilizar autorização, URLs temporárias, rate limiting, auditoria e validação de tenant.

---

# 3. STACK OFICIAL

## 3.1. Backend e API

- Python 3.13;
- FastAPI;
- SQLAlchemy 2 assíncrono;
- Alembic;
- Pydantic;
- PostgreSQL;
- driver PostgreSQL assíncrono;
- OpenAPI;
- REST `/api/v1`;
- WebSocket e/ou Server-Sent Events somente onde agregarem valor;
- autenticação por access token curto e refresh token rotativo;
- OIDC/OAuth 2.1 compatível;
- tipagem rigorosa;
- lint, format, type-check e testes obrigatórios.

Adote gerenciamento de dependências reproduzível, lockfile versionado e builds determinísticos.

## 3.2. Frontend

- Vue 3;
- TypeScript em modo estrito;
- Vite;
- Pinia;
- Vue Router;
- ECharts;
- design system compartilhado;
- formulários tipados;
- validação coerente com os contratos da API;
- PWA;
- tema claro/escuro;
- branding por tenant;
- responsividade;
- WCAG 2.2 AA;
- i18n.

Não usar Blade, Livewire ou Inertia como camada principal. O frontend deve consumir a API FastAPI.

## 3.3. Processamento

- Celery;
- RabbitMQ;
- Redis;
- filas por domínio;
- retries com backoff e jitter;
- dead-letter queues;
- idempotência;
- transactional outbox;
- inbox do consumidor;
- locks distribuídos;
- monitoramento de tarefas;
- reprocessamento pelo painel.

## 3.4. Mobile e desktop

- Tauri 2;
- Vue 3;
- TypeScript;
- Rust;
- SQLite local;
- plugins oficiais quando disponíveis;
- código nativo Swift/Kotlin quando necessário;
- suporte Android e iOS;
- suporte desktop administrativo quando aplicável;
- biometria;
- deep links;
- QR Code;
- scanner de código de barras;
- NFC quando aplicável;
- notificações;
- armazenamento seguro;
- sincronização offline.

## 3.5. Documentos

- S3/MinIO;
- bucket exclusivo por tenant;
- SHA-256;
- metadados no PostgreSQL;
- versionamento;
- retenção;
- lifecycle;
- antivírus;
- quarentena;
- URLs temporárias assinadas;
- criptografia;
- auditoria de acesso.

## 3.6. Infraestrutura

- Docker Compose;
- imagens OCI locais e configuração de registro remoto opcional desabilitada;
- CloudPanel;
- Dockge;
- Portainer;
- workflows CI/CD gerados como arquivos;
- Cloudflare;
- Cloudflare Tunnel;
- Prometheus;
- Grafana;
- OpenTelemetry;
- logs estruturados;
- Loki ou backend compatível;
- alertas;
- backups automatizados;
- restauração testada;
- SBOM;
- checksums;
- provenance e assinatura de artefatos quando possível.

---

# 4. ESTRUTURA DO MONOREPO

Crie a seguinte estrutura, ajustando apenas quando houver justificativa técnica documentada:

```text
pige360/  #

├── backend/
│   ├── app/
│   │   ├── bootstrap/
│   │   ├── control_plane/
│   │   ├── modules/
│   │   │   ├── foundation/
│   │   │   ├── tenancy/
│   │   │   ├── branding/
│   │   │   ├── app_factory/
│   │   │   ├── app_distribution/
│   │   │   ├── identity/
│   │   │   ├── authorization/
│   │   │   ├── people/
│   │   │   ├── students/
│   │   │   ├── guardians/
│   │   │   ├── employees/
│   │   │   ├── admissions/
│   │   │   ├── secretary/
│   │   │   ├── enrollment/
│   │   │   ├── academic/
│   │   │   ├── pedagogy/
│   │   │   ├── lesson_planning/
│   │   │   ├── class_attendance/
│   │   │   ├── finance/
│   │   │   ├── services/
│   │   │   ├── banking/
│   │   │   ├── sales/
│   │   │   ├── pos/
│   │   │   ├── canteen/
│   │   │   ├── inventory/
│   │   │   ├── procurement/
│   │   │   ├── assets/
│   │   │   ├── fiscal/
│   │   │   ├── hr/
│   │   │   ├── personnel/
│   │   │   ├── payroll/
│   │   │   ├── timekeeping/
│   │   │   ├── events/
│   │   │   ├── travel/
│   │   │   ├── notices/
│   │   │   ├── requests/
│   │   │   ├── workflows/
│   │   │   ├── communication/
│   │   │   ├── mail/
│   │   │   ├── contracts/
│   │   │   ├── documents/
│   │   │   ├── signatures/
│   │   │   ├── library/
│   │   │   ├── transportation/
│   │   │   ├── health/
│   │   │   ├── compliance/
│   │   │   ├── government_education/
│   │   │   ├── reporting/
│   │   │   ├── analytics/
│   │   │   ├── integrations/
│   │   │   └── platform_operations/
│   │   ├── shared/
│   │   │   ├── application/
│   │   │   ├── domain/
│   │   │   ├── infrastructure/
│   │   │   ├── security/
│   │   │   ├── observability/
│   │   │   ├── events/
│   │   │   ├── storage/
│   │   │   ├── database/
│   │   │   └── testing/
│   │   └── main.py
│   ├── alembic_control/
│   ├── alembic_tenant/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── contract/
│   │   ├── tenancy/
│   │   ├── security/
│   │   ├── fiscal/
│   │   ├── contracts/
│   │   ├── pedagogy/
│   │   ├── attendance/
│   │   ├── branding/
│   │   ├── app_factory/
│   │   ├── visual/
│   │   ├── e2e/
│   │   └── performance/
│   ├── scripts/
│   └── pyproject.toml
├── apps/
│   ├── platform-console/
│   ├── branding-studio/
│   ├── tenant-download-center/
│   ├── tenant-admin-web/
│   ├── public-portal/
│   ├── family-app/
│   ├── teacher-app/
│   ├── student-app/
│   ├── admin-app/
│   ├── pos-app/
│   ├── kiosk-app/
│   ├── timeclock-app/
│   └── desktop-admin/
├── packages/
│   ├── ui/
│   ├── design-tokens/
│   ├── api-sdk/
│   ├── auth/
│   ├── domain-types/
│   ├── validation/
│   ├── permissions/
│   ├── offline-sync/
│   ├── observability/
│   ├── fiscal-types/
│   ├── mail-client/
│   ├── tenant-branding/
│   ├── app-manifest/
│   ├── visual-testing/
│   └── testing/
├── rust/
│   ├── crates/
│   │   ├── secure-storage/
│   │   ├── offline-database/
│   │   ├── sync-engine/
│   │   ├── device-identity/
│   │   ├── fiscal-snapshot/
│   │   ├── printing/
│   │   └── native-bridge/
│   └── Cargo.toml
├── infra/
│   ├── compose/
│   ├── docker/
│   ├── cloudpanel/
│   ├── dockge/
│   ├── portainer/
│   ├── cloudflare/
│   ├── mailcow/
│   ├── evolution/
│   ├── build-farm/
│   ├── app-distribution/
│   ├── visual-testing/
│   ├── monitoring/
│   ├── backup/
│   ├── restore/
│   ├── migrations/
│   └── scripts/
├── deploy/
│   ├── saas/
│   ├── self-hosted/
│   ├── enterprise/
│   └── local/
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── domains/
│   ├── api/
│   ├── database/
│   ├── security/
│   ├── deployment/
│   ├── operations/
│   ├── fiscal/
│   ├── banking/
│   ├── mail/
│   ├── design/
│   ├── branding/
│   ├── app-factory/
│   ├── mobile/
│   ├── testing/
│   └── user-guides/
├── scripts/
├── release/
├── .github/
│   └── workflows/
├── compose.yaml
├── compose.production.yaml
├── VERSION
├── CHANGELOG.md
├── SECURITY.md
├── CONTRIBUTING.md
└── README.md
```

Dentro de cada módulo backend, adote uma organização consistente:

```text
module/
├── domain/
│   ├── entities/
│   ├── value_objects/
│   ├── enums/
│   ├── events/
│   ├── policies/
│   ├── services/
│   └── exceptions/
├── application/
│   ├── commands/
│   ├── queries/
│   ├── handlers/
│   ├── dto/
│   ├── ports/
│   └── validators/
├── infrastructure/
│   ├── persistence/
│   ├── providers/
│   ├── messaging/
│   ├── storage/
│   └── clients/
├── presentation/
│   ├── api/
│   ├── schemas/
│   └── dependencies/
└── tests/
```

Evite abstrações sem propósito. Não crie repository genérico para cada Model apenas por padrão; use ports quando houver necessidade real de abstração, integração, substituição ou isolamento de domínio.

---

# 5. MULTI-TENANCY OBRIGATÓRIO

## 5.1. Regra central

Cada tenant deve possuir obrigatoriamente:

- domínio dinâmico próprio;
- suporte a domínio personalizado próprio;
- banco PostgreSQL lógico próprio;
- usuário de banco próprio;
- credencial própria;
- pool de conexão próprio;
- volume/diretório próprio;
- bucket S3/MinIO próprio;
- chave de criptografia própria;
- namespace Redis próprio;
- backups próprios;
- restauração isolada;
- quotas;
- auditoria;
- configurações;
- branding;
- políticas;
- integrações.

O tenant deve ser resolvido pelo hostname antes de autenticação e antes de abrir qualquer recurso de dados.

Não aceitar como seletor público de tenant:

```text
X-Tenant-ID
tenant_id em query string
tenant_id informado pelo formulário
tenant_id escolhido pelo frontend
rota /tenants/{id}/...
```

## 5.2. Control Plane e Tenant Plane

Use banco de controle separado:

```text
platform_control
```

Ele armazena:

- tenants;
- organizações;
- domínios;
- provisionamento;
- planos;
- licenças;
- referências de segredos;
- bancos;
- buckets;
- volumes;
- status;
- releases;
- distribuição de apps;
- administradores globais;
- sessões de suporte;
- auditoria global;
- métricas agregadas sem conteúdo sensível completo.

Cada tenant possui banco próprio:

```text
tenant_<uuid_normalizado>
```

O banco do tenant contém todos os módulos operacionais da escola.

## 5.3. Contexto institucional interno

Dentro do banco do tenant, diferencie:

```text
organization_id
institution_id
unit_id
campus_id
department_id
```

Use RLS e policies internas para restringir instituições, unidades, campi, departamentos e perfis, mesmo dentro do tenant.

## 5.4. Domínios dinâmicos

Suportar zonas-base configuráveis:

```text
school.argws.com.br
school.wwsoftwares.com.br
school.wws.app
```

Exemplo:

```text
s-7km4q2x9d8.school.argws.com.br
admin.s-7km4q2x9d8.school.argws.com.br
api.s-7km4q2x9d8.school.argws.com.br
familia.s-7km4q2x9d8.school.argws.com.br
professor.s-7km4q2x9d8.school.argws.com.br
aluno.s-7km4q2x9d8.school.argws.com.br
cantina.s-7km4q2x9d8.school.argws.com.br
portal.s-7km4q2x9d8.school.argws.com.br
eventos.s-7km4q2x9d8.school.argws.com.br
rh.s-7km4q2x9d8.school.argws.com.br
ponto.s-7km4q2x9d8.school.argws.com.br
pdv.s-7km4q2x9d8.school.argws.com.br
kiosk.s-7km4q2x9d8.school.argws.com.br
webhooks.s-7km4q2x9d8.school.argws.com.br
```

Todos os hosts devem ser associados exclusivamente a um tenant.

## 5.5. Storage por tenant

Diretório local:

```text
/var/lib/pige360/tenants/<tenant_uuid>/
├── documents/
├── academic/
├── finance/
├── fiscal/
├── sales/
├── canteen/
├── hr/
├── payroll/
├── timekeeping/
├── events/
├── mail-cache/
├── imports/
├── exports/
├── temporary/
├── quarantine/
├── backups/
└── audit/
```

Bucket:

```text
pe-tenant-<tenant_uuid>
```

Nunca usar slug ou nome comercial como fronteira de segurança.

## 5.6. Administrador global

O administrador da plataforma pode acessar qualquer tenant, mas somente por sessão explícita e auditada:

```text
console global
→ seleção do tenant
→ justificativa
→ 2FA/step-up
→ support session temporária assinada
→ redirecionamento ao domínio do tenant
→ banner permanente
→ auditoria do ator real
```

Registrar:

- platform_admin_id;
- tenant_id;
- usuário assumido, se houver;
- motivo;
- ticket;
- IP;
- dispositivo;
- início;
- expiração;
- ações;
- antes/depois;
- correlação.

Nunca mascarar o administrador real apenas como usuário assumido.

---

# 6. CLOUDFLARE, DOMÍNIOS, PROXY E SSL

## 6.1. Separação de zonas

O domínio administrativo deve ser separado dos domínios dinâmicos dos tenants.

Control Plane, exemplo:

```text
console.platform.wws.app
api.platform.wws.app
auth.platform.wws.app
status.platform.wws.app
downloads.platform.wws.app
```

Tenant Plane:

```text
*.school.argws.com.br
*.school.wwsoftwares.com.br
*.school.wws.app
```

Use tokens, zones, tunnels, rulesets e logs separados.

## 6.2. Provider Cloudflare

Implemente uma plataforma completa de integração Cloudflare por API Token:

- contas;
- zonas;
- DNS;
- tags/comentários;
- proxy;
- Cloudflare Tunnel;
- Custom Hostnames;
- Cloudflare for SaaS;
- Total TLS;
- certificados;
- regras;
- WAF;
- rate limiting;
- health checks;
- logs;
- reconciliação;
- rotação de tokens;
- least privilege;
- diagnóstico;
- reprocessamento.

Nunca usar Global API Key.

Crie contratos:

```text
DnsProvider
EdgeProvider
TunnelProvider
CustomHostnameProvider
CertificateProvider
RulesetProvider
HealthMonitorProvider
```

Implementações:

```text
CloudflareDnsProvider
CloudflareTunnelProvider
CloudflareForSaasProvider
CloudflareCertificateProvider
LetsEncryptAcmeProvider
CpanelDnsProvider
ManualDnsProvider
MockProviders apenas para teste
```

## 6.3. Origem sem IP público

Use Cloudflare Tunnel como entrada obrigatória para a plataforma SaaS:

```text
usuário
→ Cloudflare Edge
→ Cloudflare Tunnel
→ gateway interno
→ aplicação
```

Não criar A/AAAA público apontando para a origem da aplicação. Bloquear acesso direto por firewall. Manter conectores redundantes. Separar tunnel administrativo do tunnel de tenants.

## 6.4. Domínio personalizado do tenant

Quando o tenant informar:

```text
colegioexemplo.com.br
```

fornecer apontamentos como:

```dns
admin.colegioexemplo.com.br
CNAME
admin.s-7km4q2x9d8.school.argws.com.br

api.colegioexemplo.com.br
CNAME
api.s-7km4q2x9d8.school.argws.com.br
```

A plataforma deve:

1. validar formato;
2. impedir duplicidade;
3. provar propriedade;
4. criar Custom Hostname;
5. detectar propagação;
6. emitir certificado;
7. renovar automaticamente;
8. configurar proxy;
9. configurar rota;
10. executar health check;
11. marcar como canônico;
12. manter domínio dinâmico como fallback ou redirect 308;
13. auditar tudo.

Quando o DNS do cliente também for Cloudflare, orientar CNAME DNS-only no lado do cliente, salvo configuração explícita e validada de Orange-to-Orange. O proxy obrigatório permanece no lado da plataforma.

## 6.5. Let’s Encrypt

A plataforma deve se responsabilizar pela emissão e renovação automática.

Implemente políticas:

```text
lets_encrypt_strict
cloudflare_managed
acme_dns01_delegated
custom_certificate_upload
```

Requisitos:

- Total TLS com Let’s Encrypt para zonas dinâmicas quando suportado;
- seleção explícita de Let’s Encrypt em Custom Hostnames quando o plano permitir;
- alternativa ACME DNS-01 com delegação `_acme-challenge` e upload de certificate bundle quando necessário e suportado;
- nunca afirmar que o certificado é Let’s Encrypt se outra CA foi usada;
- no modo `lets_encrypt_strict`, não ativar o domínio enquanto a política não puder ser cumprida;
- TLS Full (strict);
- renovação antecipada;
- implantação atômica;
- rollback;
- CAA;
- health check;
- alerta de vencimento.

## 6.6. Provisionamento do tenant

Executar de forma idempotente:

```text
criar tenant
→ UUID imutável
→ reservar domínio
→ criar banco e usuário
→ aplicar migrations
→ criar bucket
→ criar diretório/volume
→ criar chaves
→ criar registros Cloudflare
→ criar tunnel/route
→ emitir SSL
→ criar admin inicial
→ testar todos os hosts
→ ativar tenant
```

Estados:

```text
draft
awaiting_domain
reserving_hostname
creating_database
creating_storage
creating_dns
waiting_dns
requesting_certificate
configuring_route
health_checking
active
degraded
suspended
failed
archived
```

---

# 7. IDENTIDADE, AUTENTICAÇÃO E AUTORIZAÇÃO

Implementar:

- cadastro único de pessoa;
- usuários;
- papéis múltiplos;
- RBAC;
- ABAC contextual;
- policies por tenant/instituição/unidade;
- 2FA TOTP;
- passkeys/WebAuthn quando possível;
- códigos de recuperação;
- sessão por dispositivo;
- refresh token rotativo;
- revogação;
- step-up authentication;
- bloqueio;
- política de senha parametrizável;
- login por domínio do tenant;
- OIDC;
- SSO opcional;
- biometria mobile;
- auditoria;
- impersonação controlada;
- acesso temporário;
- consentimento;
- LGPD.

Perfis mínimos:

```text
platform_super_admin
platform_admin
tenant_owner
institution_director
unit_manager
secretary
academic_coordinator
teacher
assistant_teacher
finance_manager
finance_operator
fiscal_manager
hr_manager
personnel_operator
payroll_operator
timekeeping_operator
canteen_manager
pos_operator
inventory_manager
event_manager
request_agent
mail_admin
employee
student
guardian
auditor
support
```

Permissões devem ser granulares, sem depender somente do nome do perfil.

---

# 8. CADASTRO ÚNICO DE PESSOAS

Modelar uma pessoa única com papéis especializados:

```text
Person
├── Student
├── Guardian
├── FinancialResponsible
├── Employee
├── Teacher
├── SupplierContact
├── Candidate
└── User
```

Recursos:

- dados civis;
- CPF e documentos;
- nome social;
- filiação;
- contatos;
- endereços;
- nacionalidade;
- necessidades especiais;
- informações médicas autorizadas;
- restrições alimentares;
- contatos de emergência;
- fotos;
- assinaturas;
- consentimentos;
- preferências de comunicação;
- vínculos familiares;
- responsáveis legais;
- responsáveis financeiros;
- pessoas autorizadas para retirada;
- deduplicação;
- histórico;
- validação.

---

# 9. ADMISSÕES, SECRETARIA E MATRÍCULA

## 9.1. Captação e admissões

- campanhas;
- leads;
- integração Perfex CRM;
- formulários públicos;
- inscrição;
- processo seletivo;
- provas;
- entrevistas;
- critérios;
- ranking;
- lista de espera;
- documentos;
- reserva de vaga;
- conversão em aluno;
- origem do lead;
- consentimentos.

## 9.2. Secretaria

- pré-matrícula;
- matrícula;
- rematrícula;
- enturmação;
- mudança de turma;
- mudança de turno;
- trancamento;
- cancelamento;
- desistência;
- suspensão;
- transferência;
- progressão;
- dependência;
- equivalência;
- aproveitamento de estudos;
- histórico de movimentações;
- controle de vagas;
- protocolos;
- documentos;
- declarações;
- históricos;
- certificados;
- livro de registros;
- assinatura;
- QR de validação.

A matrícula deve vincular:

- aluno;
- instituição;
- unidade;
- programa;
- currículo;
- ano/período;
- turma;
- situação;
- responsáveis;
- contrato;
- responsável financeiro;
- documentos;
- histórico.

---

# 10. NÚCLEO ACADÊMICO E PEDAGÓGICO

## 10.1. Modelo acadêmico genérico

Suportar:

```text
programas educacionais
currículos versionados
matrizes
períodos acadêmicos
anos letivos
semestres
bimestres
trimestres
etapas
séries
módulos
créditos
componentes curriculares
disciplinas
pré-requisitos
equivalências
ofertas
turmas
salas
laboratórios
horários
calendários
carga horária
professores
substituições
```

Não amarrar o domínio somente à educação básica.

## 10.2. Pedagógico

- plano de ensino;
- planejamento anual, periódico e semanal;
- plano de aula versionado;
- diário;
- conteúdo previsto;
- conteúdo ministrado;
- frequência por sessão;
- chamada em sala online e offline;
- atrasos;
- saídas antecipadas;
- justificativas;
- avaliações;
- provas;
- trabalhos;
- rubricas;
- competências;
- habilidades;
- notas;
- conceitos;
- pesos;
- médias;
- arredondamento;
- recuperação;
- parecer descritivo;
- conselho de classe;
- fechamento;
- reabertura auditada;
- boletim;
- histórico;
- acompanhamento;
- ocorrências;
- intervenção pedagógica;
- tarefas;
- anexos;
- relatórios.

Use strategies configuráveis para cálculo de notas, frequência, aprovação, recuperação e integralização curricular.

## 10.3. Educação infantil

Adicionar:

- alimentação;
- sono;
- higiene;
- troca;
- medicação autorizada;
- agenda;
- evolução;
- fotos autorizadas;
- retirada;
- ocorrências;
- comunicação diária.

## 10.4. Ensino técnico e superior

Adicionar:

- créditos;
- módulos;
- estágios;
- práticas;
- laboratórios;
- atividades complementares;
- extensão;
- TCC;
- colação;
- certificações;
- integralização;
- pré-requisitos;
- optativas;
- dependências;
- equivalências.

---

## 10.5. Módulo completo de planejamento de aulas

Criar um domínio próprio de planejamento pedagógico, separado do diário efetivamente executado, porém integrado a currículo, calendário, horários, turmas, professores, avaliações, recursos, frequência e relatórios.

### 10.5.1. Escopo

Suportar:

- planejamento anual;
- semestral;
- trimestral;
- bimestral;
- mensal;
- semanal;
- unidade didática;
- sequência didática;
- projeto interdisciplinar;
- plano de aula individual;
- plano recorrente;
- aula regular;
- prática;
- laboratório;
- remota;
- híbrida;
- reposição;
- substituição;
- atividade externa;
- educação infantil;
- ensino básico;
- técnico;
- superior;
- cursos livres.

### 10.5.2. Estrutura de dados

Implementar, no mínimo:

```text
teaching_plan_templates
teaching_plan_template_versions
teaching_plans
teaching_plan_versions
teaching_plan_periods
teaching_plan_components
teaching_plan_objectives
teaching_plan_curriculum_links
teaching_plan_skills
teaching_plan_competencies
teaching_plan_methodologies
teaching_plan_resources
teaching_plan_assessments
teaching_plan_accommodations
teaching_plan_homework
teaching_plan_references
teaching_plan_attachments
teaching_plan_approvals
teaching_plan_comments
lesson_plans
lesson_plan_versions
lesson_plan_schedules
lesson_plan_execution_records
lesson_plan_reschedules
lesson_plan_substitutions
lesson_plan_collaborators
lesson_plan_events
```

Cada plano deve registrar tenant, instituição, unidade, período, programa, currículo, turma, componente, professores, etapa, datas, duração, carga horária, objetivos, habilidades, competências, conteúdo, metodologia, recursos, acessibilidade, adaptações, avaliação, tarefa, referências, anexos, status, versão, aprovação, execução e justificativas.

### 10.5.3. Alinhamento curricular

Relacionar, sem hardcode, com:

- currículo e matriz;
- ementa;
- objetivos do curso;
- competências;
- habilidades;
- unidades temáticas;
- objetos de conhecimento;
- catálogos curriculares versionados;
- Plano Educacional Individualizado com acesso restrito;
- adaptações e recursos de acessibilidade.

### 10.5.4. Estados e fluxo

```text
draft
submitted_for_review
changes_requested
approved
scheduled
ready
in_progress
partially_executed
executed
rescheduled
cancelled
superseded
archived
```

Fluxo:

```text
professor cria ou duplica plano
    ↓
alinha ao currículo
    ↓
anexa recursos
    ↓
envia para revisão
    ↓
coordenação aprova ou devolve
    ↓
agenda sessões
    ↓
professor registra execução
    ↓
compara planejado e ministrado
    ↓
reagenda pendências
    ↓
atualiza diário e relatórios
```

A aprovação deve ser parametrizável. Nunca alterar retroativamente plano executado; gerar versão ou complemento.

### 10.5.5. Geração, colaboração e reaproveitamento

Permitir criar, duplicar, reutilizar período anterior, copiar entre turmas autorizadas, compartilhar, importar, exportar, gerar a partir da ementa, distribuir sequência em várias aulas e reorganizar pelo calendário.

Suportar autor, coautor, substituto, coordenador, revisor, aprovador, comentários, menções, comparação de versões, aprovação em lote e auditoria.

### 10.5.6. Calendário, recursos e diário

Integrar com horários, feriados, cancelamentos, mudança de sala, indisponibilidade, eventos, viagens, reposições e substituições.

Vincular documentos, apresentações, vídeos, links, livros, biblioteca, laboratório, equipamentos, salas, estoque, recursos de acessibilidade, formulários, avaliações e tarefas. Detectar conflito de reserva.

Separar:

```text
conteúdo planejado
conteúdo efetivamente ministrado
conteúdo não concluído
conteúdo reagendado
```

Na conclusão, registrar execução integral, parcial ou não executada, motivo, observações, conteúdo adicional, atividade, anexos e próxima ação.

### 10.5.7. Aplicativo do professor e offline

Permitir consultar, criar e editar rascunhos, duplicar, anexar, visualizar currículo, enviar para aprovação, receber devolução, iniciar aula, registrar execução, reagendar, trabalhar offline, sincronizar e resolver conflitos.

O cache offline deve conter apenas turmas e períodos autorizados, em SQLite criptografado, com outbox e idempotência.

### 10.5.8. APIs

```text
GET    /api/v1/teaching-plans
POST   /api/v1/teaching-plans
GET    /api/v1/teaching-plans/{id}
PATCH  /api/v1/teaching-plans/{id}
POST   /api/v1/teaching-plans/{id}/versions
POST   /api/v1/teaching-plans/{id}/submit
POST   /api/v1/teaching-plans/{id}/approve
POST   /api/v1/teaching-plans/{id}/request-changes
POST   /api/v1/teaching-plans/{id}/duplicate
POST   /api/v1/teaching-plans/{id}/schedule
POST   /api/v1/teaching-plans/{id}/archive

GET    /api/v1/lesson-plans
POST   /api/v1/lesson-plans
GET    /api/v1/lesson-plans/{id}
PATCH  /api/v1/lesson-plans/{id}
POST   /api/v1/lesson-plans/{id}/start
POST   /api/v1/lesson-plans/{id}/complete
POST   /api/v1/lesson-plans/{id}/reschedule
POST   /api/v1/lesson-plans/{id}/cancel
GET    /api/v1/lesson-plans/{id}/execution
```

### 10.5.9. Eventos e relatórios

Eventos:

```text
TeachingPlanCreated
TeachingPlanSubmitted
TeachingPlanApproved
TeachingPlanChangesRequested
LessonPlanScheduled
LessonStarted
LessonPartiallyExecuted
LessonCompleted
LessonRescheduled
LessonCancelled
CurriculumCoverageUpdated
```

Relatórios:

- cobertura curricular;
- planejado versus ministrado;
- planos pendentes;
- aprovações;
- carga planejada e executada;
- conteúdos atrasados;
- reposições;
- recursos;
- professor, turma e componente;
- competências;
- adaptações;
- PDF/XLSX.

### 10.5.10. Testes obrigatórios

Versionamento, aprovação, devolução, cópia, isolamento de tenant, professor sem atribuição, conflito, cancelamento, reposição, execução parcial, currículo, acessibilidade, offline, conflito de sincronização, fechamento e E2E completo.

## 10.6. Módulo completo de frequência escolar e chamada em sala

Criar um domínio próprio de frequência de alunos, distinto do controle de ponto de colaboradores. Registrar presença por sessão real e suportar frequência diária, por horário, componente, atividade, evento ou carga horária conforme a política da instituição.

### 10.6.1. Estrutura de dados

```text
class_sessions
class_session_schedules
class_session_occurrences
class_session_teachers
class_session_rooms
class_session_status_history
attendance_policies
attendance_policy_versions
attendance_status_catalog
attendance_calls
attendance_call_versions
attendance_records
attendance_record_events
attendance_justifications
attendance_justification_attachments
attendance_approvals
attendance_corrections
attendance_closures
attendance_notifications
attendance_summaries
attendance_risk_indicators
attendance_imports
attendance_exports
```

### 10.6.2. Status de frequência

Catálogo parametrizável com códigos internos estáveis:

```text
present
absent
justified_absence
excused_absence
late
late_justified
early_departure
early_departure_justified
remote_present
activity_present
medical_leave
institutional_leave
attendance_pending
not_expected
not_enrolled
transferred
cancelled_session
```

A política define quais estados contam como presença, falta, atraso, abono ou carga parcial.

### 10.6.3. Sessão de aula

Registrar tenant, instituição, unidade, turma, componente, oferta, datas, horários previstos e reais, duração, professor previsto e efetivo, substituto, sala, modalidade, plano, status, origem, versão e fechamento.

Estados:

```text
scheduled
ready
started
attendance_open
attendance_submitted
completed
cancelled
rescheduled
closed
reopened
```

### 10.6.4. Chamada em sala

Modos:

- lista completa;
- chamada rápida;
- marcar todos presentes e registrar exceções;
- grade;
- foto autorizada;
- QR Code rotativo;
- cartão/código de barras;
- NFC;
- kiosk;
- importação;
- integração autorizada com controle de acesso;
- biometria apenas como provider opcional, com consentimento, base legal e política de privacidade.

A chamada principal deve funcionar sem biometria.

Regras:

- um registro por aluno e sessão;
- idempotency key;
- considerar matrícula válida na data;
- tratar matrícula tardia e transferência;
- rascunho e autosave;
- chamada parcial;
- envio e fechamento;
- reabertura auditada;
- correção com motivo;
- aprovação quando exigida.

### 10.6.5. Tolerâncias e carga horária

Configurar atraso, presença parcial, saída antecipada, quantidade de tempos, aulas geminadas, frequência diária, por componente, por hora, atividade externa, remota, regras por etapa, percentual mínimo, arredondamento, abono, compensação e reposição.

Não usar percentual único hardcoded.

### 10.6.6. Justificativas

Responsável, aluno autorizado ou operador pode informar motivo, período, sessões e anexos.

```text
draft
submitted
under_review
additional_information_required
approved
partially_approved
rejected
cancelled
```

A aprovação não converte automaticamente falta em presença; a política define o efeito.

### 10.6.7. Alertas e automações

Falta ou atraso pode disparar notificação interna, push, e-mail, Evolution API, solicitação de justificativa, alerta à coordenação, tarefa de acompanhamento e intervenção pedagógica.

Aplicar janela de espera configurável depois do fechamento para evitar avisos prematuros.

### 10.6.8. Indicadores e risco

Calcular frequência total, por componente, período, faltas consecutivas, atrasos, saídas, tendência, risco de reprovação, turmas críticas, alunos sem chamada, sessões pendentes, divergências e justificativas pendentes. Vincular os resultados à versão da política.

### 10.6.9. Integração pedagógica

```text
plano de aula
→ sessão real
→ chamada
→ conteúdo ministrado
→ carga horária executada
→ diário
→ cobertura curricular
→ indicadores
→ notificações
```

Aula cancelada não pode gerar faltas. Reposição deve referenciar a sessão original.

### 10.6.10. Aplicativos

Professor:

- chamada offline;
- lista cacheada;
- marcação rápida;
- atraso e saída;
- observação;
- rascunho;
- envio;
- correção dentro da janela;
- solicitação de reabertura;
- sincronização e conflito.

Família e aluno:

- resumo;
- calendário;
- detalhes por componente;
- faltas e atrasos;
- justificativas;
- anexos;
- status;
- percentual;
- alertas.

### 10.6.11. APIs

```text
GET    /api/v1/class-sessions
POST   /api/v1/class-sessions
GET    /api/v1/class-sessions/{id}
PATCH  /api/v1/class-sessions/{id}
POST   /api/v1/class-sessions/{id}/start
POST   /api/v1/class-sessions/{id}/cancel
POST   /api/v1/class-sessions/{id}/reschedule
POST   /api/v1/class-sessions/{id}/close
POST   /api/v1/class-sessions/{id}/reopen

GET    /api/v1/class-sessions/{id}/attendance
PUT    /api/v1/class-sessions/{id}/attendance
POST   /api/v1/class-sessions/{id}/attendance/submit
POST   /api/v1/class-sessions/{id}/attendance/corrections

GET    /api/v1/attendance/students/{student_id}
GET    /api/v1/attendance/classes/{class_id}
GET    /api/v1/attendance/risks

POST   /api/v1/attendance/justifications
GET    /api/v1/attendance/justifications
POST   /api/v1/attendance/justifications/{id}/approve
POST   /api/v1/attendance/justifications/{id}/reject
```

### 10.6.12. Eventos e relatórios

```text
ClassSessionScheduled
ClassSessionStarted
AttendanceCallOpened
AttendanceDraftSaved
AttendanceSubmitted
AttendanceClosed
AttendanceReopened
StudentMarkedAbsent
StudentMarkedLate
AttendanceCorrectionRequested
AttendanceCorrected
AttendanceJustificationSubmitted
AttendanceJustificationApproved
AttendanceRiskDetected
GuardianAbsenceNotificationRequested
```

Relatórios de sessão, diário, aluno, turma, componente, professor, período, unidade, faltas consecutivas, atrasos, saídas, justificativas, risco, pendências, divergências e fechamento, com PDF/XLSX.

### 10.6.13. Segurança, auditoria e testes

Registrar ator, dispositivo, modo de chamada, data/hora, localização somente quando autorizada, antes/depois, motivo, aprovação, sessão, política, versão, correlação e origem offline.

Professor sem atribuição não pode lançar chamada. Administrador global somente por support session auditada.

Testar chamada online/offline, duplicidade, matrícula na data, transferência, atraso, saída, cancelamento, reposição, múltiplos tempos, substituição, correção, reabertura, justificativa, notificação, política, percentual, risco, isolamento, conflito, período fechado e E2E integrado.

---

# 11. FINANCEIRO E BANCÁRIO

## 11.1. Financeiro

Implementar:

```text
financial_contracts
contract_versions
contract_parties
financial_plans
charges
charge_items
installments
payments
payment_allocations
refunds
discounts
scholarships
penalties
renegotiations
agreements
bank_accounts
cash_registers
accounts_receivable
accounts_payable
cost_centers
ledger_entries
reconciliations
```

Regras:

- pagamento pode quitar várias parcelas;
- parcela pode receber pagamentos parciais;
- usar `payment_allocations`;
- subledger imutável;
- ajustes por lançamentos compensatórios;
- idempotência;
- vínculo com contrato, venda, serviço, evento, cantina e documento fiscal;
- reconhecimento por competência configurável;
- estornos;
- devoluções;
- inadimplência;
- cobrança;
- auditoria.

## 11.2. Bancário

Providers intercambiáveis para:

- PIX imediato;
- PIX com vencimento;
- boleto;
- boleto híbrido;
- consulta;
- baixa;
- cancelamento;
- devolução;
- webhook;
- extrato;
- conciliação;
- CNAB 240;
- CNAB 400;
- OFX;
- remessa;
- retorno;
- débito recorrente quando suportado;
- APIs bancárias;
- gateways.

Todo webhook deve:

- validar assinatura;
- armazenar payload mascarado;
- ser idempotente;
- ser reprocessável;
- identificar tenant;
- ter inbox;
- registrar tentativas;
- nunca duplicar baixa.

---


# 11.3. CATÁLOGO E EXECUÇÃO DE SERVIÇOS

Criar módulo próprio de serviços, integrado ao financeiro e ao fiscal, para:

- mensalidades;
- matrículas;
- rematrículas;
- cursos;
- módulos educacionais;
- transporte;
- atividades extracurriculares;
- eventos;
- viagens;
- documentos;
- segunda via;
- avaliações;
- treinamentos;
- locações;
- serviços administrativos;
- serviços recorrentes;
- serviços avulsos;
- pacotes de serviço.

Entidades mínimas:

```text
service_catalogs
services
service_variants
service_fiscal_profiles
service_price_tables
service_subscriptions
service_orders
service_order_items
service_executions
service_competencies
service_billing_rules
service_fiscal_events
```

Requisitos:

- catálogo por tenant/instituição/unidade;
- preço e vigência;
- recorrência;
- competência;
- contrato;
- plano;
- bolsa/desconto;
- centro de custo;
- responsável financeiro;
- consumo;
- execução;
- cancelamento;
- estorno;
- rateio;
- NBS;
- LC 116;
- código municipal;
- CNAE;
- ISS;
- IBS/CBS;
- cClassTrib;
- retenções;
- NFS-e;
- recibo;
- integração com contas a receber.

Mensalidades devem ser representadas como serviços educacionais vinculados ao contrato e à competência. A emissão da NFS-e deve ser configurável por competência, faturamento ou pagamento, nunca fixa globalmente.

Venda mista deve separar produtos e serviços e gerar os documentos fiscais corretos, preservando um único pedido comercial e vínculos entre NF-e/NFC-e/NFS-e.

---

# 12. VENDAS, PDV, CANTINA E ESTOQUE

## 12.1. Módulo de vendas

Vender:

- fardamento;
- uniformes;
- livros;
- apostilas;
- módulos;
- materiais;
- kits;
- ingressos;
- eventos;
- produtos diversos;
- serviços;
- mensalidades avulsas;
- transporte;
- cursos;
- taxas;
- alimentação.

Canais:

- painel web;
- aplicativo administrativo;
- aplicativo da família;
- aplicativo do aluno;
- PDV;
- cantina;
- kiosk;
- venda mobile;
- pedido antecipado;
- ecommerce institucional.

## 12.2. PDV

- múltiplos terminais;
- operadores;
- abertura/fechamento;
- sangria;
- suprimento;
- conferência;
- venda;
- orçamento;
- pedido;
- devolução;
- troca;
- desconto autorizado;
- comissão configurável;
- pagamentos mistos;
- PIX;
- dinheiro;
- cartão por terminal externo;
- carteira;
- crédito institucional;
- impressão;
- contingência;
- offline;
- sincronização;
- identificação do aluno;
- venda para público externo;
- NFC-e;
- NF-e quando aplicável.

## 12.3. Cantina

- cantinas;
- pontos de venda;
- cardápios;
- produtos;
- combos;
- receitas;
- ingredientes;
- adicionais;
- tamanhos;
- preços;
- alergênicos;
- informação nutricional;
- restrições alimentares;
- bloqueio por aluno;
- autorização;
- limite diário/semanal;
- horários;
- carteira pré-paga;
- recarga;
- estorno;
- subsídio;
- refeição gratuita;
- vale interno;
- saldo;
- alerta;
- extrato;
- venda offline;
- baixa de estoque;
- lote;
- validade;
- descarte;
- perda;
- custo de receita;
- sugestão de compra;
- NFC-e/NF-e;
- notificação ao responsável.

## 12.4. Estoque, compras e patrimônio

- produtos;
- variantes;
- códigos de barras;
- depósitos;
- lotes;
- validade;
- custo médio;
- entradas;
- saídas;
- transferências;
- inventários;
- perdas;
- reservas;
- estoque mínimo;
- fornecedores;
- cotações;
- pedidos;
- recebimentos;
- devoluções;
- requisições;
- patrimônio;
- localização;
- manutenção;
- empréstimos;
- depreciação informativa;
- auditoria.

Toda venda deve integrar, de forma transacional e idempotente:

```text
pedido
→ pagamento
→ estoque
→ financeiro
→ fiscal
→ recibo
→ notificação
→ auditoria
```

---

# 13. MOTOR FISCAL BRASILEIRO

## 13.1. Princípios

Criar domínio fiscal independente, versionado por:

- tenant;
- CNPJ;
- estabelecimento;
- regime;
- UF;
- município;
- data de vigência;
- tipo de operação;
- produto/serviço;
- destinatário;
- documento;
- ambiente;
- layout;
- schema;
- nota técnica;
- ruleset.

Não hardcode regras legais permanentes. Importar catálogos oficiais, versionar e aplicar por vigência.

## 13.2. Tributos e classificações

Suportar:

- ICMS;
- ICMS-ST;
- FCP;
- IPI;
- PIS;
- COFINS;
- ISS;
- IBS estadual;
- IBS municipal;
- CBS;
- Imposto Seletivo;
- retenções;
- DIFAL quando aplicável;
- CST;
- CSOSN;
- CFOP;
- NCM;
- CEST;
- NBS;
- LC 116;
- CNAE;
- código municipal;
- código nacional da NFS-e;
- CST IBS/CBS;
- cClassTrib;
- cBenef;
- crédito presumido;
- redução;
- diferimento;
- suspensão;
- imunidade;
- não incidência;
- alíquota zero;
- monofásico;
- devolução;
- transferência;
- ajuste;
- estorno;
- importação;
- exportação;
- regimes específicos.

## 13.3. Simples Nacional e Reforma Tributária

Manter modos:

```text
disabled
simulation_only
optional_emit
required_emit
```

Usar como baseline vigente em 2026:

- para optantes do Simples Nacional, não bloquear documentos em 2026 por ausência dos grupos IBS/CBS quando a regra oficial aplicável ainda não os exigir;
- preparar classificação, simulação e validação;
- suportar obrigatoriedade a partir de 2027 conforme regime e cronograma oficiais;
- suportar as alternativas de apuração do Simples e do regime regular;
- nunca aplicar uma flag global eterna;
- consultar e versionar atos, notas técnicas, schemas e tabelas oficiais.

O painel deve mostrar:

- produtos sem NCM;
- produtos sem CST/CSOSN;
- produtos sem CST IBS/CBS;
- produtos sem cClassTrib;
- serviços sem NBS;
- serviços sem LC 116;
- serviços sem código municipal;
- serviços sem classificação RTC;
- regras vencidas;
- tabelas desatualizadas;
- simulações;
- divergências;
- prontidão por estabelecimento.

## 13.4. IBPT WWSoftwares

Provider padrão:

```dotenv
IBPT_PROVIDER=wwsoftwares
IBPT_API_BASE_URL=https://ibpt.wwsoftwares.com.br
IBPT_API_UF_PATH=/tabela/ibpt/{uf}
```

Exemplos:

```text
https://ibpt.wwsoftwares.com.br/tabela/ibpt/ba
https://ibpt.wwsoftwares.com.br/tabela/ibpt/sp
```

O endpoint deve ser tratado como fonte CSV e o adapter deve suportar evolução de contrato sem contaminar o domínio.

Suportar todas as 27 UFs:

```text
AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO
```

Implementar:

- sincronização diária;
- sincronização manual;
- download por UF;
- parser CSV robusto;
- normalização;
- versão;
- vigência;
- hash SHA-256;
- snapshot original;
- diferenças;
- publicação atômica;
- rollback;
- cache;
- fallback;
- auditoria;
- quarentena;
- alerta;
- distribuição offline;
- nunca consultar a API por venda;
- nunca substituir cálculo tributário real pelo valor IBPT;
- usar IBPT para transparência e `vTotTrib`.

Separar:

```text
tributos_reais
tributos_aproximados_ibpt
```

## 13.5. Catálogos oficiais

Criar sincronizadores versionados para:

- NCM vigente;
- histórico NCM;
- NBS;
- LC 116;
- CFOP;
- CEST;
- CST/CSOSN;
- cClassTrib;
- crédito presumido;
- tabelas RTC;
- correlações NFS-e;
- schemas XSD;
- notas técnicas;
- códigos municipais;
- alíquotas e vigências.

Não tratar NCM, NBS, CNAE, LC 116, código municipal e cClassTrib como equivalentes.

## 13.6. Documentos fiscais

Implementar:

- NF-e;
- NFC-e;
- NFS-e padrão nacional;
- NFS-e municipal;
- emissão;
- consulta;
- cancelamento;
- substituição;
- inutilização quando aplicável;
- carta/eventos quando aplicável;
- contingência;
- rejeição;
- retry;
- manifestação quando aplicável;
- XML;
- DANFE/DANFC-e/DANFSe;
- protocolo;
- chave;
- certificado A1;
- homologação;
- produção;
- storage;
- SHA-256;
- auditoria.

Providers:

```text
SefazNfeProvider
SefazNfceProvider
NationalNfseProvider
MunicipalNfseProvider
ThirdPartyFiscalProvider
MockFiscalProvider somente para teste
```

O roteador fiscal deve escolher o documento pela natureza da operação.

Exemplos:

```text
cantina presencial → NFC-e quando aplicável
uniforme no balcão → NFC-e ou NF-e
venda para PJ → NF-e conforme regra
venda interestadual → NF-e
mensalidade → NFS-e
curso → NFS-e
venda mista → separar documentos de produto e serviço quando necessário
```

## 13.7. Integração fiscal e financeiro

Configurar evento de emissão por:

- competência;
- pagamento;
- faturamento;
- natureza;
- regime;
- município;
- orientação contábil;
- contrato;
- cancelamento;
- estorno.

Nunca assumir globalmente `pagou = emitir`.

---

# 14. RH, SETOR PESSOAL, FOLHA E PONTO

## 14.1. RH

- vagas;
- candidatos;
- seleção;
- admissão;
- onboarding;
- cargos;
- funções;
- departamentos;
- lotações;
- centros de custo;
- contratos;
- documentos;
- exames;
- treinamentos;
- competências;
- avaliações;
- plano de desenvolvimento;
- benefícios;
- férias;
- afastamentos;
- ocorrências;
- desligamento;
- histórico.

## 14.2. Setor pessoal

- dados trabalhistas;
- dependentes;
- contratos;
- jornada;
- salário;
- alterações;
- férias;
- rescisão;
- afastamentos;
- estabilidade;
- benefícios;
- empréstimos;
- pensão;
- sindicatos;
- documentos;
- obrigações;
- eventos versionados;
- integrações governamentais por adapters.

Preparar providers versionados para eSocial, FGTS Digital, DCTFWeb e obrigações legais aplicáveis, sem fixar layouts no domínio e sem alegar transmissão real sem credenciais/homologação.

## 14.3. Folha de pagamento

- competências;
- rubricas;
- incidências;
- bases;
- proventos;
- descontos;
- INSS;
- IRRF;
- FGTS;
- pensões;
- benefícios;
- horas;
- faltas;
- atrasos;
- adicionais;
- férias;
- 13º;
- rescisão;
- retroativos;
- rateios;
- centros de custo;
- provisões;
- holerites;
- arquivos;
- contabilização;
- auditoria;
- fechamento;
- reabertura controlada;
- simulação;
- processamento idempotente.

## 14.4. Controle de ponto

- escalas;
- jornadas;
- turnos;
- tolerâncias;
- feriados;
- banco de horas;
- horas extras;
- adicional noturno;
- faltas;
- atrasos;
- justificativas;
- ajustes;
- aprovação;
- espelho;
- fechamento;
- dispositivos;
- importações;
- REP/AFD por adapters;
- aplicativo de ponto;
- geolocalização opcional;
- selfie opcional;
- QR/NFC;
- modo offline;
- antifraude;
- auditoria;
- integração com folha.

Eventos de atraso e ausência devem alimentar o motor de automações.

---

# 15. EVENTOS E VIAGENS

Criar módulo genérico para qualquer evento:

- confraternização;
- celebração;
- festa;
- reunião;
- palestra;
- feira;
- campeonato;
- gincana;
- formatura;
- colação;
- cerimônia;
- passeio;
- excursão;
- viagem;
- visita técnica;
- evento acadêmico;
- curso;
- oficina;
- apresentação;
- reunião de pais;
- treinamento;
- evento online;
- evento híbrido.

Recursos:

- tipos configuráveis;
- calendário;
- local;
- salas;
- capacidade;
- programação;
- equipes;
- tarefas;
- orçamento;
- fornecedores;
- compras;
- contratos;
- patrocínios;
- ingressos;
- inscrições;
- lotes;
- pagamentos;
- PIX;
- venda de produtos;
- autorização de responsáveis;
- termos;
- documentos;
- saúde;
- restrições;
- transporte;
- hospedagem;
- roteiro;
- passageiros;
- responsáveis;
- check-in QR Code;
- check-out;
- presença;
- credenciais;
- gamificação;
- equipes de gincana;
- pontuação;
- ranking;
- certificados;
- fotos e consentimentos;
- ocorrências;
- notificações;
- relatórios;
- fiscal;
- auditoria.

Para viagens, adicionar:

- itinerário;
- pontos de encontro;
- veículos;
- motoristas;
- monitores;
- hospedagem;
- contatos;
- documentos;
- seguro;
- autorizações;
- medicações;
- emergência;
- localização opcional;
- confirmação de embarque/desembarque.

---

# 16. AVISOS, SOLICITAÇÕES E WORKFLOWS

## 16.1. Avisos

- institucionais;
- urgentes;
- emergenciais;
- acadêmicos;
- financeiros;
- RH;
- cantina;
- eventos;
- transporte;
- turma;
- curso;
- unidade;
- público dinâmico;
- anexos;
- agendamento;
- recorrência;
- expiração;
- aprovação;
- versionamento;
- leitura;
- confirmação;
- aceite;
- lembrete;
- canais múltiplos;
- auditoria.

## 16.2. Solicitações

Criar motor configurável para:

- declarações;
- histórico;
- segunda via;
- transferência;
- trancamento;
- mudança;
- justificativa;
- revisão de nota;
- equivalência;
- bolsa;
- desconto;
- renegociação;
- reembolso;
- devolução;
- retirada;
- atualização cadastral;
- atendimento;
- suporte;
- reserva;
- transporte;
- biblioteca;
- manutenção;
- TI;
- reclamação;
- sugestão;
- denúncia;
- viagem;
- evento;
- autorização;
- RH.

Cada tipo deve possuir:

- formulário versionado;
- campos;
- validações;
- anexos;
- assinatura;
- taxa;
- SLA;
- prioridade;
- departamento;
- fila;
- responsável;
- aprovação sequencial/paralela;
- estados;
- automações;
- comentários internos;
- comunicação;
- reabertura;
- satisfação;
- protocolo;
- histórico.

## 16.3. Motor de automações

Triggers:

```text
domain event
schedule
cron
webhook
state transition
threshold
deadline
incoming email
incoming WhatsApp
manual action
```

Ações:

```text
send_email
send_whatsapp
send_push
create_notice
create_request
assign_request
create_task
create_calendar_event
create_charge
provision_mailbox
suspend_mailbox
notify_manager
call_webhook
generate_document
start_workflow
```

Recursos:

- regras versionadas;
- condições;
- grupos AND/OR;
- templates;
- idempotência;
- rate limit;
- retries;
- aprovação;
- simulação;
- dry-run;
- logs;
- métricas;
- auditoria;
- DLQ;
- reprocessamento.

---

# 17. COMUNICAÇÃO E EVOLUTION API

Criar providers:

```text
EvolutionApiProvider
WhatsAppCloudProvider
EmailProvider
PushProvider
SmsProvider
WebhookProvider
MockProvider somente para teste
```

Evolution API deve ser adapter versionado e não acoplamento direto.

Suportar:

- instâncias;
- status;
- QR/conexão quando aplicável;
- envio texto;
- documento;
- mídia;
- template;
- grupos autorizados;
- webhook;
- eventos;
- mensagens recebidas;
- idempotência;
- deduplicação;
- retries;
- circuit breaker;
- rate limiting;
- health;
- logs;
- rastreio;
- consentimento.

Não confiar que webhooks chegarão uma única vez. Deduplicar por identificador do provider e hash de conteúdo.

Usos:

- atraso;
- ausência;
- pagamento;
- vencimento;
- nota publicada;
- boletim;
- evento;
- viagem;
- autorização;
- aviso;
- solicitação;
- e-mail provisionado;
- troca de senha;
- emergência.

Nunca enviar segredo, senha ou dado sensível completo por WhatsApp. Enviar resumo e link autenticado.

---

# 18. MÓDULO DE E-MAIL E MAILCOW

## 18.1. Regra

A integração de e-mail é opcional por tenant e totalmente parametrizável por Docker e painel.

Modos:

```text
disabled
mailcow_managed
generic_imap_smtp
dedicated_mailcow
```

Use:

- Mailcow REST API para domínio, mailbox, alias, quota, suspensão e remoção;
- IMAPS para leitura/sincronização;
- SMTP Submission/SMTPS para envio;
- OIDC quando aplicável;
- senha de aplicativo para clientes externos;
- Mailcow em stack separada.

## 18.2. Provisionamento automático

Ao ativar vínculo de colaborador:

```text
employee.employment_activated
→ política do tenant
→ reservar endereço
→ criar mailbox no Mailcow
→ aliases
→ quota
→ segredo
→ vínculo
→ notificação
```

Não criar mailbox apenas ao cadastrar uma pessoa incompleta.

Políticas de nomes:

```text
nome.sobrenome
nome.ultimo_sobrenome
inicial.sobrenome
matricula
personalizado
```

Tratar acentos, colisões e palavras reservadas.

## 18.3. Administração

Tenant pode:

- habilitar módulo;
- informar domínio;
- criar/remover/suspender mailbox;
- aliases;
- quotas;
- departamentos;
- políticas;
- retenção;
- acesso mobile;
- acesso por clientes externos;
- OIDC;
- delegação;
- caixas compartilhadas.

## 18.4. Caixa dentro da plataforma

Implementar cliente próprio:

- inbox;
- enviados;
- rascunhos;
- spam;
- lixeira;
- pastas;
- pesquisa;
- threads;
- resposta;
- encaminhamento;
- CC/CCO;
- anexos;
- assinatura;
- regras;
- delegação;
- ausência;
- push;
- mobile;
- offline criptografado.

Conteúdo oficial permanece no Mailcow. PostgreSQL armazena metadados e vínculos.

## 18.5. Segurança

- API key em secret manager;
- nenhuma senha no frontend;
- credenciais por mailbox criptografadas;
- logs mascarados;
- auditoria;
- acesso administrativo a mensagens somente com permissão específica e motivo;
- retenção no desligamento;
- revogação de app passwords;
- exportação controlada;
- backups incluindo chaves de criptografia.

## 18.6. DNS de e-mail

Não aplicar proxy HTTP padrão da Cloudflare a MX/SMTP/IMAP.

- registros de e-mail `DNS only`;
- Mailcow com IP dedicado;
- PTR correto;
- SPF;
- DKIM;
- DMARC;
- MTA-STS quando aplicável;
- TLS-RPT;
- MX;
- autodiscover;
- autoconfig;
- SSL automático;
- monitoramento de reputação.

O IP da aplicação escolar permanece oculto; o servidor de e-mail usa infraestrutura própria.

---

# 19. OUTROS MÓDULOS OBRIGATÓRIOS

## 19.1. Contratos, documentos e assinaturas digitais

Criar um domínio próprio de contratos, documentos e assinaturas, integrado a matrícula, rematrícula, financeiro, serviços, RH, eventos, viagens, cantina, transporte, compras, fornecedores e solicitações.

O módulo não deve ser apenas um gerador de PDF. Deve controlar:

- modelos;
- cláusulas;
- variáveis;
- versões;
- dados congelados;
- geração;
- revisão;
- partes;
- signatários;
- testemunhas;
- ordem de assinatura;
- assinatura eletrônica;
- assinatura digital com certificado;
- evidências;
- vigência;
- aditivos;
- renovações;
- rescisões;
- cancelamentos;
- arquivo;
- validação;
- auditoria.

### 19.1.1. Tipos de contrato

Suportar, no mínimo:

- contrato de prestação de serviços educacionais;
- contrato de matrícula;
- contrato de rematrícula;
- contrato de curso livre;
- contrato de ensino técnico;
- contrato de graduação ou pós-graduação;
- contrato de transporte escolar;
- contrato de material didático;
- contrato de venda parcelada de livros, módulos e fardamento;
- contrato de carteira ou plano de alimentação da cantina;
- contrato de atividade extracurricular;
- contrato de evento;
- contrato de viagem ou excursão;
- termos de autorização;
- autorização de imagem e voz;
- autorização de tratamento de dados;
- consentimentos LGPD;
- termos de saúde e medicação;
- contrato de trabalho;
- contrato de estágio;
- contrato de prestação de serviço por colaborador ou terceiro;
- termo de confidencialidade;
- contrato de fornecedor;
- contrato de compra;
- contrato de locação;
- convênios;
- acordos;
- aditivos;
- distratos;
- termos de quitação;
- termos de renegociação;
- outros tipos configuráveis pelo tenant.

### 19.1.2. Biblioteca de modelos e cláusulas

Implementar:

```text
contract_types
contract_template_families
contract_template_versions
contract_template_sections
contract_clause_library
contract_clause_versions
contract_variable_definitions
contract_conditional_rules
contract_numbering_sequences
contract_render_profiles
```

Cada modelo deve possuir:

- tenant;
- instituição;
- unidade;
- tipo;
- nome;
- descrição;
- versão;
- vigência inicial e final;
- status;
- idioma;
- jurisdição;
- foro;
- layout;
- cabeçalho;
- rodapé;
- marca;
- numeração;
- cláusulas;
- anexos;
- variáveis;
- condições;
- regras de assinatura;
- regra de aprovação;
- regra de geração;
- perfil de arquivamento;
- hash;
- autor;
- aprovador;
- data de publicação.

Estados do modelo:

```text
draft
under_review
approved
published
suspended
superseded
archived
```

Alterar um modelo publicado deve criar nova versão. Nunca modificar retroativamente contratos já gerados.

### 19.1.3. Variáveis e preenchimento automático

Criar engine de templates segura, sem permitir execução arbitrária de código.

Exemplos de variáveis:

```text
{{tenant.legal_name}}
{{tenant.trade_name}}
{{institution.legal_name}}
{{institution.cnpj}}
{{institution.address.full}}
{{unit.name}}
{{unit.address.full}}

{{contract.number}}
{{contract.generated_at}}
{{contract.start_date}}
{{contract.end_date}}

{{student.full_name}}
{{student.cpf}}
{{student.birth_date}}
{{student.registration_number}}

{{guardian.full_name}}
{{guardian.cpf}}
{{guardian.address.full}}
{{financial_responsible.full_name}}
{{financial_responsible.cpf}}

{{enrollment.academic_year}}
{{enrollment.program}}
{{enrollment.grade}}
{{enrollment.class_group}}
{{enrollment.shift}}

{{finance.total_amount}}
{{finance.installment_count}}
{{finance.installment_amount}}
{{finance.first_due_date}}
{{finance.discount_amount}}
{{finance.scholarship_percentage}}
{{finance.late_fee_rate}}
{{finance.interest_rate}}

{{employee.full_name}}
{{employee.cpf}}
{{employee.position}}
{{employee.salary}}
{{employee.work_schedule}}

{{event.name}}
{{event.start_at}}
{{event.end_at}}
{{travel.destination}}
{{travel.itinerary}}
```

Suportar:

- formatação de CPF/CNPJ;
- endereço;
- moeda;
- datas;
- números por extenso;
- listas;
- tabelas;
- parcelas;
- responsáveis múltiplos;
- dependentes;
- anexos;
- cláusulas condicionais;
- repetição de blocos;
- condições AND/OR;
- fallback;
- validação de variável obrigatória;
- preview com dados reais;
- relatório de variáveis ausentes.

Exemplos de condições:

```text
se tenant é privado → incluir cláusulas financeiras
se tenant é público → omitir cobrança e contrato financeiro
se aluno é menor → exigir responsável legal
se possui bolsa → incluir cláusula de bolsa
se possui transporte → anexar termo de transporte
se possui restrição de saúde → anexar termo específico autorizado
se evento possui viagem → exigir autorização de viagem
se pagamento é parcelado → renderizar tabela de parcelas
```

### 19.1.4. Geração automática na matrícula

Ao aprovar matrícula ou rematrícula, executar:

```text
EnrollmentApproved
    ↓
resolver tenant, instituição e unidade
    ↓
selecionar família e versão do modelo vigente
    ↓
resolver partes e signatários
    ↓
capturar snapshot imutável dos dados
    ↓
validar variáveis obrigatórias
    ↓
calcular condições e cláusulas
    ↓
gerar documento PDF
    ↓
calcular SHA-256
    ↓
armazenar PDF e snapshot no bucket do tenant
    ↓
criar envelope de assinatura
    ↓
notificar signatários
    ↓
acompanhar assinaturas
    ↓
ativar matrícula conforme política
```

Políticas configuráveis:

```text
generate_on_enrollment_draft
generate_on_enrollment_approval
generate_on_financial_plan_approval
require_signature_before_activation
allow_provisional_activation
block_classes_until_signed
block_portal_until_signed
expire_after_days
auto_regenerate_on_material_change
```

Mudança material após geração não pode alterar o PDF existente. Deve:

1. cancelar ou substituir o envelope anterior conforme a política;
2. gerar nova versão;
3. vincular a versão anterior;
4. registrar a justificativa;
5. solicitar novas assinaturas quando necessário.

### 19.1.5. Snapshot contratual

Quando um contrato for gerado, armazenar um snapshot completo e imutável dos dados utilizados:

```text
contract_data_snapshots
├── contract_id
├── template_version_id
├── schema_version
├── rendered_variables_json
├── source_references_json
├── generated_document_sha256
├── generated_at
└── generated_by
```

O contrato não deve depender de consultas futuras aos cadastros para provar seu conteúdo original.

### 19.1.6. Partes e signatários

Suportar:

- instituição;
- mantenedora;
- aluno;
- responsável legal;
- responsável financeiro;
- contratante;
- contratado;
- representante legal;
- testemunha;
- garantidor;
- colaborador;
- fornecedor;
- pessoa jurídica;
- procurador.

Estrutura mínima:

```text
contracts
contract_versions
contract_parties
contract_party_representatives
contract_signers
contract_witnesses
contract_guarantors
contract_relationships
contract_attachments
contract_amendments
contract_renewals
contract_terminations
contract_events
```

Cada signatário deve possuir:

- papel;
- nome;
- CPF/CNPJ;
- e-mail;
- telefone;
- forma de autenticação;
- forma de assinatura;
- ordem;
- assinatura obrigatória ou opcional;
- representante;
- procuração, quando aplicável;
- status;
- data de visualização;
- data de manifestação;
- data de assinatura;
- motivo de recusa.

Ordem:

```text
parallel
sequential
hybrid
```

### 19.1.7. Ciclo de vida do contrato

Estados mínimos:

```text
draft
generated
under_internal_review
approved
awaiting_signatures
partially_signed
signed
active
suspended
expired
terminated
rescinded
cancelled
superseded
archived
failed
```

Separar o status do contrato do status de cada envelope e de cada signatário.

Não excluir fisicamente contratos assinados. Aplicar retenção, bloqueio legal, arquivamento e trilha de custódia.

### 19.1.8. Formas de assinatura

Implementar providers substituíveis:

```text
InternalElectronicSignatureProvider
IcpBrasilPadesProvider
IcpBrasilRemoteSignatureProvider
GovBrAdvancedSignatureProvider
ExternalSignatureProvider
ManualSignedDocumentProvider
MockSignatureProvider somente para testes
```

Modos suportados:

```text
simple_electronic
advanced_electronic
qualified_icp_brasil
govbr_advanced
external_provider
manual_import
```

A política deve ser definida por:

- tipo de contrato;
- tenant;
- natureza pública ou privada;
- nível de risco;
- parte;
- data de vigência;
- exigência legal;
- valor;
- processo;
- disponibilidade do provider.

### 19.1.9. Assinatura eletrônica interna

Para contratos privados e documentos em que a política permitir, implementar assinatura eletrônica com pacote de evidências:

- autenticação do usuário;
- consentimento expresso;
- aceite do conteúdo;
- OTP por canal configurável;
- e-mail verificado;
- telefone verificado;
- 2FA;
- IP;
- user-agent;
- dispositivo;
- data/hora UTC;
- timezone;
- correlation ID;
- versão do documento;
- SHA-256;
- hash do pacote de evidências;
- histórico de visualização;
- registro da intenção;
- geolocalização somente mediante consentimento e política;
- selfie/prova de vida somente por provider autorizado e quando necessária;
- revogação ou recusa;
- trilha imutável.

O documento deve registrar que a parte aceitou o método de assinatura aplicável. Não usar caixa previamente marcada para consentimento.

### 19.1.10. Assinatura qualificada ICP-Brasil

Implementar assinatura digital de PDF no padrão PAdES e suporte a CAdES/XAdES quando o documento exigir.

Priorizar PAdES para contratos em PDF.

Suportar:

- certificado A1;
- certificado A3 por bridge local;
- assinatura remota por provider;
- e-CPF;
- e-CNPJ;
- certificado de representante;
- PKCS#11;
- PKCS#12;
- HSM/KMS compatível;
- cadeia de certificados;
- OCSP;
- LCR/CRL;
- carimbo do tempo por ACT/TSA;
- múltiplas assinaturas incrementais;
- validação de integridade;
- validação de revogação;
- evidências de longo prazo;
- perfis de assinatura configuráveis;
- verificação local e por serviço autorizado.

Regras de segurança:

- nunca expor chave privada ao frontend;
- nunca armazenar senha do certificado em texto aberto;
- A1 deve ficar em secret manager/HSM ou storage criptografado de alta proteção;
- PIN e certificado devem ser segregados;
- A3 deve ser operado no dispositivo do titular por bridge assinada e autenticada;
- registrar serial, emissor, titular, validade e política;
- impedir assinatura com certificado vencido ou revogado;
- permitir assinatura institucional por representante autorizado;
- validar poderes de representação.

### 19.1.11. Integração com Assinatura GOV.BR

Implementar `GovBrAdvancedSignatureProvider` de forma completa, porém condicional à elegibilidade e às credenciais oficiais.

A integração deve:

- depender do Login Único GOV.BR previamente autorizado;
- usar OAuth 2.0;
- solicitar consentimento explícito do signatário;
- validar o nível de confiabilidade exigido;
- suportar ambiente de homologação e produção;
- obter o certificado do usuário quando previsto;
- calcular o hash correto;
- solicitar assinatura PKCS#7;
- suportar assinatura detached `.p7s`;
- suportar incorporação da assinatura PKCS#7 no PDF;
- validar retorno;
- armazenar metadados técnicos;
- permitir validação;
- tratar cancelamento, expiração e erros;
- manter correlation ID;
- nunca registrar token nos logs;
- nunca reutilizar autorização além do permitido;
- possuir testes de contrato e fixtures de homologação.

Configurações:

```dotenv
GOVBR_SIGNATURE_ENABLED=false
GOVBR_SIGNATURE_ENVIRONMENT=homologation
GOVBR_SIGNATURE_CLIENT_ID=
GOVBR_SIGNATURE_CLIENT_SECRET_FILE=
GOVBR_SIGNATURE_REDIRECT_URI=
GOVBR_SIGNATURE_SCOPE=sign
GOVBR_SIGNATURE_VERIFY_TLS=true
GOVBR_SIGNATURE_TIMEOUT_SECONDS=30
```

Regras obrigatórias:

- não presumir que escolas privadas terão acesso à API GOV.BR;
- habilitar o provider somente para tenant público ou sistema formalmente autorizado;
- a ausência de credenciais deve marcar o provider como `not_configured`, sem quebrar builds;
- para tenant privado, oferecer ICP-Brasil, assinatura eletrônica interna e providers externos;
- permitir exportar o PDF para assinatura externa e importar o documento assinado;
- não apresentar `manual_import` como integração GOV.BR;
- não declarar homologação sem protocolo e evidência real.

### 19.1.12. Envelopes de assinatura

Estrutura:

```text
signature_envelopes
signature_envelope_documents
signature_envelope_signers
signature_requests
signature_attempts
signature_artifacts
signature_certificates
signature_timestamps
signature_validations
signature_evidence_packages
signature_provider_events
signature_webhook_inbox
```

Fluxo:

```text
documento congelado
→ envelope
→ signatários
→ autenticação
→ consentimento
→ assinatura
→ validação
→ assinatura seguinte
→ documento final
→ pacote de evidências
→ hash final
→ archive
→ notificação
```

O provider externo nunca deve ser considerado fonte única do estado. Webhooks devem ser armazenados, deduplicados e conciliados com consultas periódicas.

### 19.1.13. Assinatura pela instituição

A escola pode assinar:

- antes dos contratantes;
- depois dos contratantes;
- em paralelo;
- por representante;
- por certificado e-CNPJ;
- por e-CPF do representante;
- por assinatura eletrônica avançada conforme política.

A autorização do representante deve ser versionada:

```text
institution_signing_authorizations
├── institution_id
├── representative_person_id
├── signature_method
├── valid_from
├── valid_until
├── allowed_contract_types
├── authorization_document_id
└── status
```

### 19.1.14. Aditivos, renovações e distratos

Implementar:

- aditivo de valor;
- aditivo de prazo;
- alteração de responsável;
- alteração de serviço;
- bolsa/desconto;
- mudança de turma/curso;
- renegociação;
- renovação;
- rescisão;
- distrato;
- quitação;
- substituição.

Cada documento deve referenciar o contrato-base e preservar sua própria versão, partes, assinaturas e efeitos.

### 19.1.15. Integração financeira e acadêmica

Contrato educacional deve integrar:

```text
matrícula
programa
ano/período
serviços
plano financeiro
parcelas
bolsas
descontos
responsável financeiro
vigência
status
assinaturas
```

Políticas:

```text
não gerar parcelas até aprovação interna
gerar parcelas ao criar contrato
ativar parcelas após primeira assinatura
ativar matrícula após todas as assinaturas
permitir matrícula provisória
cancelar cobranças futuras em distrato
manter lançamentos já realizados
gerar termo de renegociação
```

Toda transição deve ser idempotente e auditada.

### 19.1.16. Geração e formatos

Suportar:

- HTML seguro;
- PDF;
- PDF/A quando configurado;
- DOCX somente como formato de modelo/importação quando necessário;
- anexos;
- tabela de parcelas;
- paginação;
- cabeçalho/rodapé;
- rubrica visual;
- bloco de assinaturas;
- QR Code;
- selo de validação;
- hash impresso;
- número do contrato;
- marca do tenant;
- acessibilidade;
- múltiplos idiomas.

O PDF assinado deve preservar assinaturas incrementais e não ser reprocessado de forma que invalide assinaturas.

### 19.1.17. Armazenamento, cadeia de custódia e retenção

Armazenar no bucket exclusivo do tenant:

```text
contracts/<year>/<contract_id>/
├── source-snapshot.json
├── generated-v1.pdf
├── signature-envelope.json
├── signed-final.pdf
├── detached-signatures/
├── evidence-package.json
├── validation-report.json
├── SHA256SUMS
└── audit-manifest.json
```

Aplicar:

- SHA-256;
- versionamento;
- Object Lock/WORM opcional;
- retenção;
- legal hold;
- criptografia;
- manifest;
- assinatura do manifest;
- backup;
- restauração;
- auditoria de acesso;
- download por URL temporária;
- proibição de path fornecido pelo cliente.

### 19.1.18. Validação pública controlada

Cada documento final deve possuir QR Code ou código de validação.

A página pública deve apresentar somente:

- autenticidade;
- status;
- hash;
- número;
- instituição;
- data;
- quantidade de assinaturas;
- resultado da validação;
- revogação/cancelamento quando aplicável.

Não expor CPF completo, endereço, valores sensíveis ou conteúdo contratual sem autenticação.

Permitir:

- validar por código;
- validar por QR;
- enviar arquivo para comparar hash;
- baixar relatório de validação autorizado;
- consultar cadeia de certificados;
- verificar assinatura e integridade.

### 19.1.19. Notificações e lembretes

Integrar com:

- e-mail;
- Evolution API;
- push;
- aviso interno;
- calendário;
- solicitações.

Eventos:

```text
ContractGenerated
ContractApproved
ContractSentForSignature
ContractViewed
ContractSignatureCompleted
ContractPartiallySigned
ContractFullySigned
ContractDeclined
ContractExpired
ContractActivated
ContractSuspended
ContractTerminated
ContractSuperseded
SignatureValidationFailed
GovBrSignatureRequested
GovBrSignatureCompleted
IcpBrasilSignatureCompleted
```

Automatizar:

- convite;
- lembrete;
- vencimento;
- recusa;
- pendência;
- assinatura concluída;
- contrato ativado;
- aditivo necessário.

Não enviar documento integral ou dados sensíveis por WhatsApp sem política e consentimento. Preferir link autenticado e temporário.

### 19.1.20. API do módulo

Criar, no mínimo:

```text
GET    /api/v1/contracts
POST   /api/v1/contracts
GET    /api/v1/contracts/{id}
PATCH  /api/v1/contracts/{id}
POST   /api/v1/contracts/{id}/generate
POST   /api/v1/contracts/{id}/approve
POST   /api/v1/contracts/{id}/send-for-signature
POST   /api/v1/contracts/{id}/cancel
POST   /api/v1/contracts/{id}/terminate
POST   /api/v1/contracts/{id}/renew
POST   /api/v1/contracts/{id}/amendments
GET    /api/v1/contracts/{id}/versions
GET    /api/v1/contracts/{id}/document
GET    /api/v1/contracts/{id}/evidence
GET    /api/v1/contracts/{id}/audit

GET    /api/v1/contract-templates
POST   /api/v1/contract-templates
POST   /api/v1/contract-templates/{id}/versions
POST   /api/v1/contract-templates/{id}/publish
POST   /api/v1/contract-templates/{id}/preview
POST   /api/v1/contract-templates/{id}/validate

GET    /api/v1/signature-envelopes/{id}
POST   /api/v1/signature-envelopes/{id}/sign
POST   /api/v1/signature-envelopes/{id}/decline
POST   /api/v1/signature-envelopes/{id}/remind
POST   /api/v1/signature-envelopes/{id}/retry
POST   /api/v1/signature-envelopes/{id}/validate

GET    /api/v1/signatures/providers
POST   /api/v1/signatures/providers/{provider}/test

GET    /api/v1/public/contracts/validate/{code}
POST   /api/v1/public/contracts/validate-file
```

### 19.1.21. Telas

Administração:

- dashboard de contratos;
- modelos;
- biblioteca de cláusulas;
- editor;
- preview;
- variáveis;
- regras condicionais;
- contratos;
- versões;
- signatários;
- envelopes;
- pendências;
- assinaturas;
- providers;
- GOV.BR;
- ICP-Brasil;
- validações;
- auditoria;
- retenção;
- relatórios.

Família/aluno/contratante:

- contratos pendentes;
- visualização integral;
- consentimento;
- assinatura;
- recusa;
- download;
- histórico;
- validação;
- aditivos;
- comprovante.

Aplicativo administrativo:

- aprovações;
- acompanhamento;
- lembretes;
- assinatura institucional;
- validação.

### 19.1.22. Workers e filas

Filas:

```text
contracts.generate
contracts.render
contracts.notifications
signatures.request
signatures.govbr
signatures.icpbrasil
signatures.external
signatures.validate
signatures.webhooks
contracts.archive
```

Workers devem transportar contexto assinado do tenant, usar idempotência, retries e DLQ.

### 19.1.23. Testes obrigatórios do módulo

Testar:

- geração automática da matrícula;
- preenchimento de variáveis;
- condição de cláusulas;
- snapshot;
- versão de modelo;
- alteração material;
- múltiplos signatários;
- ordem sequencial e paralela;
- responsável de menor;
- contrato público sem cobrança;
- contrato privado com plano financeiro;
- assinatura interna;
- OTP;
- recusa;
- expiração;
- ICP-Brasil A1 em fixture segura;
- PAdES com múltiplas assinaturas;
- certificado vencido;
- certificado revogado;
- GOV.BR homologação por contrato mock oficial;
- ausência de credenciais GOV.BR;
- tenant privado sem elegibilidade GOV.BR;
- importação de PDF assinado;
- validação de hash;
- QR público sem exposição de dados;
- webhook duplicado;
- retry;
- storage por tenant;
- acesso cruzado;
- backup e restore;
- aditivo;
- distrato;
- integração financeira;
- ativação da matrícula;
- E2E completo.

### 19.1.24. Critérios específicos de conclusão

O módulo somente estará concluído quando:

1. modelos forem versionados;
2. contratos forem gerados automaticamente pela matrícula;
3. os dados utilizados forem congelados;
4. PDFs possuírem SHA-256;
5. houver assinatura eletrônica interna;
6. houver assinatura qualificada ICP-Brasil;
7. o provider GOV.BR estiver integralmente implementado e condicional;
8. escolas privadas não dependerem da API GOV.BR;
9. múltiplos signatários funcionarem;
10. evidências forem preservadas;
11. aditivos e distratos funcionarem;
12. financeiro e matrícula estiverem integrados;
13. contratos assinados não forem alterados;
14. validação pública controlada funcionar;
15. web e mobile permitirem assinatura;
16. storage e auditoria respeitarem o tenant;
17. workers forem idempotentes;
18. testes de segurança e E2E estiverem aprovados.

### 19.1.25. Documentos gerais

Além dos contratos, o domínio deve continuar suportando:

- documentos acadêmicos;
- declarações;
- históricos;
- certificados;
- autorizações;
- holerites;
- documentos fiscais;
- relatórios;
- PDF;
- XLSX;
- templates;
- QR Code;
- hashes;
- cadeia de custódia;
- validação pública controlada.

## 19.2. Biblioteca

- acervo;
- exemplares;
- autores;
- editoras;
- categorias;
- empréstimo;
- reserva;
- renovação;
- multa;
- perda;
- inventário;
- acervo digital;
- acesso por perfil.

## 19.3. Transporte

- veículos;
- motoristas;
- monitores;
- rotas;
- pontos;
- alunos;
- presença;
- embarque;
- desembarque;
- ocorrências;
- comunicação;
- rastreamento opcional;
- autorização.

## 19.4. Saúde e ocorrências

- alergias;
- condições;
- medicamentos;
- contatos;
- incidentes;
- primeiros socorros;
- encaminhamentos;
- autorizações;
- acesso restrito;
- auditoria de visualização.

---


## 19.5. Integrações educacionais governamentais

Criar módulo versionado e desacoplado para:

- MEC;
- INEP;
- Censo Escolar/Educacenso;
- cadastros educacionais;
- exportações;
- importações;
- validações;
- relatórios de inconsistência;
- layouts por vigência;
- filas;
- reprocessamento;
- auditoria;
- homologação;
- protocolos.

Não codificar layouts diretamente nos controllers. Use catalogs, schemas, DTOs, validators, exporters e adapters versionados. Não declarar transmissão oficial concluída sem credenciais, ambiente e protocolo real.

## 19.6. Integrações externas

Criar plataforma de integrações com:

- Perfex CRM;
- ERPs;
- contabilidade;
- bancos;
- gateways;
- plataformas acadêmicas;
- APIs públicas e privadas;
- SFTP;
- CSV;
- XLSX;
- JSON;
- XML;
- webhooks de entrada e saída;
- filas;
- mapeamentos;
- transformações;
- reconciliação;
- reprocessamento.

Entidades:

```text
integration_connections
integration_credentials
integration_capabilities
integration_mappings
integration_sync_runs
integration_events
integration_failures
external_record_links
webhook_endpoints
webhook_deliveries
```

Definir fonte oficial por tipo de dado. Exemplo:

```text
lead/oportunidade → Perfex CRM
pessoa/matrícula → PIGE360
contrato/parcela/pagamento → PIGE360
documento fiscal → PIGE360
```

Não manter dois sistemas como fonte oficial concorrente para o mesmo agregado.

Cada integração deve possuir:

- credencial criptografada;
- ambiente;
- capability discovery;
- teste de conexão;
- timeout;
- retry;
- circuit breaker;
- idempotência;
- rate limit;
- health;
- logs;
- auditoria;
- mapeamento;
- reprocessamento;
- dead-letter queue.

---

# 20. APLICAÇÕES FRONTEND E MOBILE

## 20.1. Console da plataforma

Para administração global:

- tenants;
- domínios;
- Cloudflare;
- bancos;
- storage;
- licenças;
- planos;
- releases;
- apps;
- Mailcow;
- Evolution;
- integrações;
- filas;
- saúde;
- logs;
- suporte;
- sessões;
- auditoria;
- backup;
- restore;
- quotas;
- cobrança SaaS;
- planos e assinaturas da plataforma;
- faturamento do tenant;
- limites e consumo;
- licenças self-hosted;
- suspensão e reativação controladas.

## 20.2. Administração do tenant

- dashboard;
- secretaria;
- acadêmico;
- pedagógico;
- financeiro;
- fiscal;
- bancário;
- vendas;
- PDV;
- cantina;
- estoque;
- compras;
- RH;
- folha;
- ponto;
- eventos;
- avisos;
- solicitações;
- e-mail;
- documentos;
- relatórios;
- integrações;
- configurações;
- usuários;
- permissões;
- auditoria.

## 20.3. Família

- dependentes;
- agenda;
- frequência;
- notas;
- boletim;
- calendário;
- avisos;
- confirmações;
- ocorrências;
- contratos;
- parcelas;
- PIX;
- boleto;
- recibo;
- nota fiscal;
- cantina;
- carteira;
- restrições;
- pedidos;
- eventos;
- viagens;
- autorizações;
- solicitações;
- documentos;
- transporte;
- biblioteca;
- e-mail/mensagens quando permitido;
- push;
- biometria.

## 20.4. Professor

- turmas;
- disciplinas;
- horários;
- chamada offline;
- diário;
- planos;
- conteúdo;
- avaliação;
- notas;
- parecer;
- competências;
- ocorrências;
- avisos;
- solicitações;
- eventos;
- e-mail;
- calendário;
- substituições;
- relatórios;
- sincronização.

## 20.5. Aluno

- vida acadêmica;
- calendário;
- tarefas;
- materiais;
- notas;
- frequência;
- biblioteca;
- eventos;
- cantina;
- carteira;
- documentos;
- solicitações;
- avisos;
- e-mail institucional quando permitido.

## 20.6. Administrativo mobile

- dashboards;
- aprovações;
- alunos;
- matrículas;
- solicitações;
- financeiro;
- fiscal;
- RH;
- ponto;
- cantina;
- estoque;
- eventos;
- avisos;
- e-mail;
- integrações;
- alertas.

## 20.7. PDV/Cantina mobile

- catálogo;
- leitor;
- aluno;
- carteira;
- restrições;
- venda;
- pagamento;
- NFC-e;
- impressão;
- estoque;
- caixa;
- offline;
- sincronização.

## 20.8. Kiosk e ponto

- identificação;
- QR;
- NFC;
- consulta;
- check-in;
- pedido;
- protocolo;
- registro de ponto;
- modo restrito;
- offline;
- gestão remota.


## 20.9. Branding Studio do tenant

- logos e variantes;
- cores;
- tipografia;
- temas;
- ícones;
- splash;
- documentos;
- e-mails;
- instaladores;
- preview web/mobile/desktop/PDF;
- validação de contraste;
- aprovação;
- publicação;
- versionamento;
- rollback;
- auditoria.

O tenant somente pode administrar sua própria marca. O administrador global pode atuar em qualquer tenant por sessão auditada.

## 20.10. App Factory administrativa

- catálogo de produtos de app;
- contrato/entitlements;
- manifestos;
- brand version;
- domínios;
- bundle/package IDs;
- builds;
- filas;
- assinaturas;
- artefatos;
- lojas;
- canais;
- erros;
- retry;
- revogação;
- auditoria.

## 20.11. Central de downloads do tenant

- aplicativos mobile e desktop próprios da escola;
- branding exclusivo;
- Windows, Linux, macOS, Android e iOS;
- arquitetura;
- versão;
- canal;
- changelog;
- hash;
- assinatura;
- SBOM;
- QR Code;
- instruções;
- histórico;
- revogação;
- atualização;
- links de lojas quando configurados;
- autenticação e auditoria.


---

# 21. OFFLINE E SINCRONIZAÇÃO

Implementar engine compartilhado:

```text
server revision
local revision
outbox
inbox
idempotency key
conflict
merge policy
tombstone
checkpoint
```

Regras:

- banco SQLite por tenant e usuário;
- criptografia local;
- chave no secure storage;
- dados mínimos;
- cache com validade;
- outbox transacional;
- envio em lote;
- retry;
- deduplicação;
- conflito explícito;
- períodos fechados não aceitam alteração;
- logout limpa/revoga conforme política;
- anexos temporários criptografados;
- snapshots fiscais assinados;
- PDV e professor com suporte offline;
- auditoria de sincronização.

---

# 22. DISTRIBUIÇÃO, PLAY CONSOLE E APP STORE CONNECT

## 22.1. Artefatos

Android:

- APK debug;
- APK release unsigned;
- APK release signed;
- APK universal;
- APK split por ABI;
- AAB release;
- mapping/symbols;
- checksums;
- SBOM;
- manifest.

iOS:

- `.app` ARM64;
- `.xcarchive`;
- IPA unsigned técnica;
- IPA assinada;
- dSYM;
- checksums;
- SBOM;
- manifest.

## 22.2. Lojas e publicação

Implementar integração com:

- Google Play;
- Play Console;
- Google Play Developer API;
- tracks internos, fechados, abertos e produção;
- upload AAB;
- release notes;
- rollout;
- status;
- App Store Connect;
- App Store Connect API;
- TestFlight;
- grupos;
- testers;
- upload IPA;
- metadados;
- submissão;
- acompanhamento de revisão;
- versionamento;
- changelog.

## 22.3. Condicional por segredos

Os workflows sempre devem compilar e validar os aplicativos.

Jobs de assinatura/publicação somente executam quando todos os segredos necessários existirem.

Exemplo conceitual:

```yaml
env:
  PLAY_SERVICE_ACCOUNT_JSON: ${{ secrets.PLAY_SERVICE_ACCOUNT_JSON }}

steps:
  - name: Publicar no Play Console
    if: ${{ env.PLAY_SERVICE_ACCOUNT_JSON != '' }}
    run: ./scripts/mobile/publish-play.sh
```

Aplicar o mesmo princípio a Apple.

Ausência de segredo:

- job de publicação marcado como skipped;
- build continua aprovado;
- artefatos locais continuam gerados;
- nenhuma falha falsa;
- resumo informa “distribuição não configurada”.

## 22.4. Distribuição privada

Também criar servidor privado:

- canais;
- versões;
- manifest assinado;
- download;
- autenticação;
- auditoria;
- revogação;
- atualização;
- APK direto;
- desktop updater;
- contingência.


## 22.5. Builds white-label por tenant

Todo workflow de aplicativo deve aceitar um manifesto de tenant e gerar artefatos independentes. Não usar um único APK, IPA ou desktop com logos da plataforma quando o tenant contratou white-label.

Cada build deve registrar:

```text
tenant_id
app_product
brand_version
manifest_version
source_commit
version
build_number
platform
architecture
signing_profile
release_channel
build_started_at
build_finished_at
status
artifacts
checksums
sbom
provenance
```

A ausência de credenciais de assinatura deve gerar artefatos unsigned tecnicamente válidos e marcar a etapa de assinatura como `skipped_not_configured`, sem falhar os demais builds.

## 22.6. Gatilho por contratação do tenant

Quando o contrato comercial habilitar o pacote de aplicativos:

```text
contrato ativado
→ entitlements registrados
→ branding validado
→ domínios validados
→ manifestos gerados
→ builds solicitados
→ testes executados
→ artefatos publicados
→ escola notificada
```

O processo deve ser idempotente e reprocessável.


---

# 23. API E CONTRATOS

Padrões obrigatórios:

- `/api/v1`;
- OpenAPI;
- SDK TypeScript gerado e validado;
- IDs UUIDv7;
- datas ISO 8601;
- timezone explícito;
- moeda decimal;
- paginação cursor onde necessário;
- filtros tipados;
- ordenação allowlist;
- idempotency key;
- correlation ID;
- request ID;
- ETag/version;
- optimistic concurrency;
- formato único de erro;
- validação;
- rate limit;
- versionamento;
- depreciação documentada.

Formato de erro:

```json
{
  "type": "https://errors.pige360.local/validation-error",
  "title": "Erro de validação",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "Existem campos inválidos.",
  "correlation_id": "019...",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_EMAIL",
      "message": "Informe um e-mail válido."
    }
  ]
}
```

---

# 24. EVENTOS E CONSISTÊNCIA

Use Transactional Outbox:

```text
transação PostgreSQL
├── altera agregado
└── grava outbox
    ↓
publisher
    ↓
RabbitMQ
    ↓
consumer inbox
    ↓
handler idempotente
```

Eventos mínimos:

```text
TenantProvisioned
TenantBrandingPublished
TenantAppPackagePurchased
TenantAppBuildRequested
TenantAppBuildCompleted
TenantAppReleasePublished
DomainActivated
PersonRegistered
EmployeeEmploymentActivated
MailboxProvisionRequested
MailboxProvisioned
StudentRegistered
EnrollmentActivated
EnrollmentCancelled
TeachingPlanCreated
TeachingPlanSubmitted
TeachingPlanApproved
LessonPlanScheduled
LessonStarted
LessonCompleted
ClassSessionScheduled
ClassSessionStarted
AttendanceCallOpened
AttendanceSubmitted
AttendanceClosed
AttendanceJustificationSubmitted
AttendanceJustificationApproved
AttendanceRiskDetected
GuardianAbsenceNotificationRequested
EmployeeLate
EmployeeAbsent
GradePublished
ContractCreated
InstallmentGenerated
ChargeCreated
PaymentConfirmed
PaymentRefunded
SaleCompleted
StockDebited
FiscalDocumentRequested
FiscalDocumentAuthorized
FiscalDocumentRejected
EventCreated
TripAuthorizationPending
NoticePublished
ServiceRequestCreated
ServiceRequestSlaBreached
ContractGenerated
ContractSentForSignature
ContractFullySigned
ContractTerminated
SignatureValidationFailed
DocumentSigned
NotificationRequested
```

Versionar schemas de eventos.

---

# 25. SEGURANÇA E LGPD

Implementar:

- secure by default;
- least privilege;
- tenant isolation;
- RLS;
- RBAC/ABAC;
- 2FA;
- passkeys;
- refresh rotation;
- device revocation;
- TLS;
- HSTS;
- CSP;
- CORS por hostname exato;
- Trusted Host;
- validação de `Host`;
- validação de proxy confiável;
- CSRF onde aplicável;
- XSS;
- SQL injection;
- SSRF;
- path traversal;
- upload seguro;
- antivírus;
- MIME real;
- quotas;
- criptografia de campos;
- envelope encryption;
- secrets manager;
- chaves por tenant;
- logs sem dados sensíveis;
- assinatura de webhook;
- replay protection;
- rate limiting;
- WAF;
- backups criptografados;
- auditoria;
- retenção;
- anonimização;
- exportação do titular;
- consentimento;
- finalidade;
- dados de menores;
- acesso a saúde;
- segregação;
- testes de segurança;
- dependency scanning;
- container scanning;
- secret scanning;
- SBOM.

---

# 26. OBSERVABILIDADE

Implementar:

- logs JSON;
- correlation ID;
- tenant ID técnico;
- módulo;
- operação;
- latência;
- status;
- erro;
- OpenTelemetry;
- traces;
- metrics;
- Prometheus;
- Grafana;
- filas;
- Celery;
- RabbitMQ;
- Redis;
- PostgreSQL;
- MinIO;
- Cloudflare;
- Mailcow;
- Evolution;
- fiscal;
- bancos;
- apps;
- crash reporting configurável;
- alertas;
- SLO;
- health live/readiness/startup;
- painel operacional;
- reprocessamento.

Não incluir conteúdo sensível em logs.

---

# 27. DOCKER E SERVIÇOS

Criar, no mínimo:

```text
pige360-api
pige360-web
pige360-platform-console
pige360-branding-studio
pige360-tenant-download-center
pige360-app-factory-api
pige360-worker-app-builds
pige360-worker-app-distribution
pige360-worker-visual-regression
pige360-worker-default
pige360-worker-high-priority
pige360-worker-academic
pige360-worker-pedagogy
pige360-worker-attendance
pige360-worker-finance
pige360-worker-banking
pige360-worker-fiscal
pige360-worker-sales
pige360-worker-hr
pige360-worker-mail
pige360-worker-notifications
pige360-worker-documents
pige360-worker-contracts
pige360-worker-signatures
pige360-worker-reports
pige360-worker-integrations
pige360-builder-linux
pige360-builder-windows
pige360-builder-macos
pige360-builder-android
pige360-builder-ios
pige360-beat
pige360-postgres-control
pige360-postgres-tenants
pige360-redis
pige360-rabbitmq
pige360-minio
pige360-minio-init
pige360-app-init
pige360-clamav
pige360-cloudflared-control
pige360-cloudflared-tenants
pige360-otel-collector
pige360-prometheus
pige360-grafana
pige360-loki
```

Mailcow deve ser stack separada, integrável por rede segura e API.

Evolution API pode ser stack separada e opcional.

Init services devem ser idempotentes:

- storage;
- buckets;
- bancos;
- usuários;
- migrations;
- filas;
- secrets;
- APP keys;
- tenant bootstrap;
- health.

---

# 28. CONFIGURAÇÕES E SEGREDOS

Crie `.env.example` completo, sem segredo real.

Categorias:

```text
APP
PLATFORM_BRANDING
TENANT_BRANDING
APP_FACTORY
APP_DISTRIBUTION
BUILD_FARM
DATABASE_CONTROL
DATABASE_TENANT
REDIS
RABBITMQ
MINIO
CLOUDFLARE_CONTROL
CLOUDFLARE_TENANT
CLOUDFLARE_SAAS
CLOUDFLARE_TUNNELS
ACME
MAILCOW
IMAP
SMTP
CONTRACTS
SIGNATURES
GOVBR_SIGNATURE
ICP_BRASIL
EVOLUTION
BANKING
FISCAL
IBPT
LESSON_PLANNING
CLASS_ATTENDANCE
MOBILE
PLAY_CONSOLE
APP_STORE_CONNECT
OBSERVABILITY
BACKUP
SECURITY
```

Segredos devem vir de:

- Docker Secrets;
- secret manager do provedor CI/CD;
- Vault/KMS opcional;
- arquivo protegido no self-hosted.

Não armazenar segredos em texto aberto no PostgreSQL.

---

# 29. CI/CD LOCAL, IMAGENS BASE, BUILDS E PACOTES DE RELEASE

Os workflows e scripts devem ser gerados integralmente, mas não devem acessar serviços remotos nesta execução.

## 29.1. Arquivos obrigatórios

```text
00-ci.yml
05-pedagogy-attendance.yml
10-base-images.yml
20-application-images.yml
30-build-web.yml
31-build-desktop.yml
32-build-android.yml
33-build-ios.yml
34-build-tenant-apps.yml
40-security.yml
50-release.yml
60-deploy-saas.yml
61-self-hosted-bundle.yml
70-backup-restore-test.yml
80-dependency-maintenance.yml
```

Os workflows devem ser entregues como arquivos prontos para uso futuro. Qualquer job de upload, publicação ou deploy deve permanecer desabilitado por padrão.

## 29.2. Validação local

Executar localmente:

- format;
- lint;
- type-check;
- backend;
- frontend;
- Rust;
- migrations;
- tenancy;
- segurança;
- contratos;
- fiscal;
- branding;
- regressão visual;
- planejamento de aulas;
- frequência e chamada;
- offline;
- OpenAPI;
- SDK;
- Compose;
- Dockerfiles;
- E2E.

## 29.3. Imagens base OCI

Criar e validar localmente:

```text
pige360-base-python
pige360-base-node
pige360-base-rust-tauri
pige360-base-runtime
```

Requisitos:

- multi-stage;
- usuário não root;
- labels OCI;
- BuildKit;
- cache;
- `linux/amd64`;
- `linux/arm64`, quando compatível;
- SBOM;
- provenance;
- scan;
- digest;
- lock de digests;
- rollback.

A configuração de registro remoto deve usar variável genérica e permanecer desabilitada:

```dotenv
OCI_REGISTRY=registry.invalid
REMOTE_REGISTRY_ENABLED=false
```

## 29.4. Imagens de aplicação

Criar localmente:

```text
pige360
pige360-api
pige360-web
pige360-worker
pige360-platform-console
pige360-app-factory
pige360-migrations
pige360-reporting
```

Gerar tarballs OCI quando necessário:

```text
PIGE360-<version>-images-oci.tar
PIGE360-<version>-images-digests.json
```

## 29.5. Build completo

Gerar:

- web;
- PWA;
- documentação;
- OpenAPI;
- SDK;
- containers;
- Windows;
- Linux x64/ARM64;
- macOS Intel/Apple Silicon;
- Android APK/AAB;
- iOS `.app`;
- `.xcarchive`;
- IPA unsigned;
- IPA assinada somente quando os segredos locais estiverem disponíveis;
- apps white-label;
- símbolos;
- manifests;
- changelog;
- checksums;
- SBOM;
- provenance.

## 29.6. Release local idempotente

O processo de release deve:

1. validar `VERSION`;
2. executar CI local;
3. construir artifacts;
4. verificar digests;
5. gerar manifest;
6. gerar checksums;
7. gerar SBOM;
8. gerar provenance;
9. evitar colisões de arquivos;
10. montar os pacotes ZIP;
11. produzir resumo final.

Não criar release remota durante esta execução.

## 29.7. Pacotes ZIP obrigatórios

```text
PIGE360-<version>-source.zip
PIGE360-<version>-release-bundle.zip
PIGE360-<version>-self-hosted.zip
PIGE360-<version>-workflows-ci-cd.zip
```

Incluir:

- código;
- workflows;
- Dockerfiles;
- Compose;
- scripts;
- migrations;
- documentação;
- OpenAPI;
- SDK;
- branding;
- manifests;
- checksums;
- SBOM;
- deploy;
- `.env.example`;
- instaladores;
- relatórios.

Excluir:

- metadados de versionamento;
- segredos;
- caches;
- `node_modules`;
- ambientes virtuais;
- certificados privados;
- dados reais;
- arquivos temporários.

## 29.8. Scripts locais

Criar:

```text
scripts/ci/run-all.sh
scripts/release/build-source-zip.sh
scripts/release/assemble-release.sh
scripts/release/build-oci-bundle.sh
scripts/release/checksums.sh
scripts/release/generate-manifest.py
scripts/release/package-local.sh
```

Nenhum script deve executar upload ou autenticação remota.

## 29.9. Ausência de segredos

A ausência de segredo afeta somente assinatura ou integração correspondente.

Exemplos:

```text
Apple sem certificado → gerar .app/.xcarchive/IPA unsigned
Android sem keystore → gerar artefatos unsigned
lojas sem credenciais → gerar pacote, sem upload
deploy sem credencial → gerar bundle, sem deploy
```

## 29.10. Supply chain

- inventariar ferramentas;
- fixar versões;
- preferir checksums;
- registrar origem;
- aplicar permissões mínimas;
- gerar SBOM;
- gerar provenance;
- assinar artifacts quando houver chave local;
- não baixar executáveis sem validação.

## 29.11. Critérios

- YAML válido;
- scripts válidos;
- nenhuma conexão remota necessária;
- nenhuma publicação remota executada;
- ZIP reproduzível;
- imagens OCI locais;
- digests registrados;
- builds mobile/desktop;
- jobs opcionais corretamente ignorados;
- backup/restore testado;
- documentação operacional completa.

---

# 30. TESTES OBRIGATÓRIOS

## 30.1. Unitários

Regras de domínio, cálculos, estados, estratégias, políticas, planejamento de aulas, sessões e frequência.

## 30.2. Integração

PostgreSQL, Redis, RabbitMQ, MinIO, Mailcow adapter, Cloudflare adapter, Evolution adapter, bancos e fiscal em ambientes controlados.

## 30.3. Contrato

- providers;
- webhooks;
- OpenAPI;
- SDK;
- IBPT CSV;
- Mailcow;
- Cloudflare;
- Evolution;
- fiscal;
- bancário;
- lojas.

## 30.4. Multi-tenant

Provar:

- tenant A não consulta B;
- token A não funciona em B;
- arquivo A não abre em B;
- job A não executa em B;
- cache A não vaza;
- relatório A não mistura;
- backup A não restaura B;
- domínio desconhecido retorna 404;
- rota platform não funciona no tenant;
- rota tenant não funciona no platform;
- suporte global exige sessão.

## 30.5. Fiscal

- golden XML;
- schemas;
- homologação;
- rejeição;
- contingência;
- Simples;
- regime normal;
- vigências;
- cClassTrib;
- IBPT;
- NCM;
- NBS;
- venda mista;
- cancelamento;
- estorno;
- idempotência.

## 30.6. Offline

- queda de conexão;
- duplicidade;
- conflito;
- outbox;
- retomada;
- fiscal snapshot;
- PDV;
- planejamento offline;
- chamada offline;
- conflitos de frequência;
- logout;
- revogação.

## 30.7. Segurança

- auth;
- RBAC;
- ABAC;
- RLS;
- CSRF;
- XSS;
- SSRF;
- path traversal;
- upload;
- webhook replay;
- brute force;
- Host header;
- proxy headers;
- secrets;
- permissions.

## 30.8. E2E

Fluxos completos:

```text
tenant → escola → aluno → matrícula → turma → professor
→ planejamento anual → plano de aula → sessão → chamada
→ frequência → diário → avaliação → boletim
→ contrato → parcela → PIX → pagamento → NFS-e
→ produto → estoque → venda → NFC-e/NF-e
→ cantina → carteira → restrição → venda
→ colaborador → mailbox → ponto → folha
→ evento → inscrição → autorização → pagamento
→ aviso → WhatsApp/e-mail/push
→ solicitação → aprovação → documento
→ matrícula → contrato automático → responsável → assinatura
→ assinatura institucional → validação → ativação da matrícula
→ aditivo/distrato → financeiro → auditoria
```


## 30.9. Planejamento de aulas e frequência

- planejamento anual, periódico, semanal e por aula;
- templates, versões, alinhamento curricular, aprovação e devolução;
- execução parcial, reposição, substituição e integração ao diário;
- sessão real e chamada online/offline;
- justificativa, correção e reabertura;
- política versionada;
- alertas e risco;
- professor sem atribuição;
- aluno transferido;
- aula cancelada sem falta;
- isolamento entre tenants;
- relatórios;
- E2E completo.

## 30.10. Branding, referências visuais e App Factory


- inventário dos anexos;
- SHA-256 dos ativos;
- mapa de referências;
- tokens;
- contraste;
- marca global somente no Control Plane;
- marca do tenant em todas as superfícies da escola;
- ausência de vazamento de branding entre tenants;
- screenshots canônicos;
- regressão visual;
- manifesto válido;
- bundle/package ID estável;
- geração de resource pack;
- build Android, iOS e desktop por tenant;
- assinatura condicional;
- ausência de segredo;
- download center isolado;
- revogação;
- update manifest;
- lojas condicionais;
- build idempotente;
- limpeza de ambiente e segredo;
- E2E de contratação até download.

## 30.11. Backup e restore

Restaurar tenant isolado, banco, bucket, Mailcow dedicado quando aplicável, manifest e checksums.

---

# 31. DADOS DEMONSTRATIVOS

Criar modo demo explícito:

```text
APP_DEMO_MODE=true
```

- separado da produção;
- seed reproduzível;
- tenant de demonstração;
- dados marcados;
- reset;
- sem misturar mocks;
- sem usar credenciais reais;
- banner visível;
- nunca habilitado automaticamente em produção.

---

# 32. DOCUMENTAÇÃO

Entregar:

- visão;
- arquitetura;
- ADRs;
- mapa de domínios;
- modelo de tenancy;
- modelo de dados;
- ERDs;
- OpenAPI;
- SDK;
- permissões;
- instalação local;
- Docker;
- CloudPanel;
- Dockge;
- Portainer;
- SaaS;
- self-hosted;
- Cloudflare;
- domínios;
- SSL;
- Mailcow;
- Evolution;
- fiscal;
- IBPT;
- design system;
- inventário de imagens de referência;
- mapa de telas;
- branding da plataforma;
- branding por tenant;
- App Factory;
- central de downloads;
- contratos;
- modelos e cláusulas;
- assinaturas ICP-Brasil;
- integração GOV.BR;
- bancos;
- mobile;
- lojas;
- backup;
- restore;
- observabilidade;
- troubleshooting;
- runbooks;
- manual do administrador;
- manual da escola;
- manual do professor;
- manual de planejamento de aulas;
- manual de chamada e frequência;
- manual da família;
- manual do PDV;
- manual de RH;
- manual fiscal.

---

# 33. CRITÉRIOS DE CONCLUSÃO

A aplicação somente estará concluída quando:

1. todos os módulos deste prompt estiverem implementados;
2. backend, frontend e persistência forem reais;
3. todos os clientes estiverem funcionais;
4. Docker Compose subir de forma reproduzível;
5. migrations funcionarem em banco vazio e atualização;
6. provisionamento de tenant for idempotente;
7. domínio, Cloudflare, proxy e SSL funcionarem;
8. banco, bucket e volume forem separados por tenant;
9. isolamento cruzado estiver testado;
10. administrador global usar sessão auditada;
11. matrícula, acadêmico e pedagógico funcionarem;
12. contratos, parcelas e pagamentos forem consistentes;
13. PDV, vendas, estoque e cantina estiverem integrados;
14. NF-e, NFC-e e NFS-e tiverem providers, armazenamento e auditoria;
15. regras RTC forem versionadas;
16. IBPT por UF estiver sincronizado;
17. RH, folha e ponto estiverem integrados;
18. eventos e viagens estiverem completos;
19. avisos e solicitações tiverem workflows;
20. contratos de matrícula serem gerados automaticamente por modelos versionados;
21. assinatura eletrônica interna, ICP-Brasil e provider GOV.BR condicional funcionarem;
22. envelopes, evidências, aditivos, distratos e validação pública funcionarem;
23. Mailcow provisionar mailbox automaticamente;
24. inbox e envio funcionarem na web e apps;
25. Evolution, e-mail e push estiverem no motor de automação;
26. offline funcionar nos fluxos previstos;
27. APK/AAB/IPA e artefatos forem gerados;
28. Play/App Store jobs forem condicionais por segredos;
29. relatórios PDF/XLSX funcionarem;
30. backups e restore forem testados;
31. observabilidade estiver ativa;
32. CI/CD estiver verde;
33. não houver TODO crítico;
34. não houver mock ativo em produção;
35. não houver segredo exposto;
36. documentação estiver completa;
37. todas as imagens anexadas estiverem inventariadas e mapeadas;
38. o branding final anexado for aplicado por tokens e manifestos;
39. a marca global aparecer somente no Control Plane;
40. cada tenant tiver domínio e branding próprios em todas as suas superfícies;
41. aplicativos mobile e desktop do tenant forem gerados automaticamente quando contratados;
42. artefatos white-label estiverem isolados, testados e assinados quando configurados;
43. a central de downloads do tenant estiver funcional e isolada;
44. os workflows de lojas forem opcionais por segredos;
45. regressão visual e testes contra vazamento de branding estiverem aprovados.

---

46. planejamento anual, periódico, semanal e por aula estiver completo;
47. planos estiverem integrados a currículo, calendário, diário e recursos;
48. chamada em sala online e offline estiver funcional;
49. justificativas, correções, reaberturas e alertas estiverem funcionais;
50. imagens base OCI locais estiverem construídas e validadas;
51. release e pacote ZIP reproduzível estiverem gerados;
52. nenhum serviço remoto tiver sido acessado durante a entrega.

# 34. ORDEM TÉCNICA INTERNA, SEM ENTREGA PARCIAL

Você pode internamente organizar a construção por dependências técnicas, mas não apresente isso como MVP ou produto parcial e não encerre o trabalho após qualquer subconjunto.

Ordem interna recomendada:

```text
fundação do monorepo
→ control plane
→ tenancy e segurança
→ dados compartilhados
→ módulos de negócio
→ integrações
→ aplicativos
→ infraestrutura
→ testes
→ documentação
→ validação total
```

Continue até a entrega integral.

---

# 35. SAÍDA ESPERADA DA FERRAMENTA

Ao finalizar, entregar:

1. resumo técnico;
2. árvore final;
3. decisões arquiteturais;
4. comandos de desenvolvimento e produção;
5. serviços e variáveis;
6. migrations;
7. testes e resultados;
8. builds e artifacts locais;
9. checksums;
10. SBOM;
11. provenance;
12. workflows CI/CD;
13. imagens base OCI e digests;
14. imagens de aplicação OCI e digests;
15. status das integrações;
16. documentação;
17. versão local;
18. pacote source;
19. pacote release;
20. pacote self-hosted;
21. pacote de workflows;
22. release manifest;
23. inventário visual;
24. screenshots e regressão visual;
25. apps por tenant;
26. planejamento de aulas;
27. frequência e chamada;
28. relatórios pedagógicos;
29. relatório de execução local;
30. riscos residuais reais.

Durante esta construção:

- não conectar a serviços remotos;
- não sincronizar código;
- não publicar;
- não fazer upload;
- não executar deploy remoto;
- não criar Pull Request.

Não declarar sucesso sem evidências. Comprovar ZIP íntegro, workflows válidos, imagens OCI locais, ausência de segredos, builds executados e ausência de referências operacionais indevidas.

---

# 36. INSTRUÇÃO ESPECÍFICA PARA OS ANEXOS QUE SERÃO FORNECIDOS

O usuário informará e anexará posteriormente:

- branding oficial da plataforma;
- logos e variantes;
- ícones;
- paleta;
- tipografia, quando licenciada;
- imagens de referência das interfaces;
- referências desktop e mobile;
- branding de tenants reais;
- materiais para apps dedicados;
- modelos de documentos, relatórios, contratos e impressões.

Assim que esses arquivos existirem no contexto da ferramenta:

1. reler todos os anexos antes de continuar o frontend;
2. calcular e registrar hashes;
3. substituir somente os ativos provisórios correspondentes;
4. preservar IDs, dados, contratos e regras já implementadas;
5. atualizar tokens e resource packs;
6. gerar previews reais novamente;
7. executar regressão visual;
8. gerar os aplicativos dedicados dos tenants habilitados;
9. publicar no download center;
10. não reutilizar branding de um tenant em outro;
11. não solicitar novamente informações já presentes nos anexos;
12. documentar qualquer arquivo inválido, incompleto ou incompatível sem inventar substituto definitivo.

Se o branding final ainda não estiver anexado, usar uma identidade visual neutra e explicitamente marcada como provisória apenas para permitir validação técnica. Não declarar o visual final como aprovado e não inventar logos definitivas.

---

# ADENDO OBRIGATÓRIO — BRANDING OFICIAL DO PIGE360


## Referências canônicas e conversão nominal

Considere todos os arquivos presentes em `01_REFERENCIAS_ORIGINAIS/` e o pacote de ativos desta revisão como referências visuais obrigatórias.

Os arquivos históricos de composição permanecem apenas como referência visual e devem usar exclusivamente a identidade PIGE360 em qualquer saída operacional.

- preserve o símbolo oficial;
- preserve proporções, cores e gradientes;
- remova o wordmark antigo;
- componha o novo wordmark **PIGE360**;
- use a descrição “Plataforma Integrada de Gestão Educacional” quando houver espaço;
- regenere PNG, SVG, favicon, ícones, splash, documentos, templates, installers e metadados;
- não publique ativos finais com o nome anterior;
- mantenha um mapa de origem e SHA-256 dos arquivos transformados.
 Antes de alterar qualquer interface:

1. inventarie as imagens e calcule SHA-256;
2. associe cada referência às aplicações e rotas correspondentes;
3. registre screenshots do estado atual;
4. derive ou carregue os design tokens oficiais;
5. preserve regras de negócio, contratos de API, estados, rotas e funcionalidades;
6. aplique o branding de forma incremental, sem refatoração abrupta;
7. valide contraste, responsividade, acessibilidade e regressão visual.

## Escopo da marca global

A marca **PIGE360** deve ser utilizada somente em:

- Control Plane administrativo global;
- site e materiais institucionais da plataforma;
- gestão de tenants, infraestrutura, licenciamento, suporte e releases;
- central global de downloads e documentação corporativa.

Ela não deve aparecer automaticamente em superfícies white-label dos tenants.

## Branding do tenant

Cada escola deve possuir `TenantBrandKit` próprio e versionado contendo logos, ícones, paleta, tipografia, domínios, e-mails, documentos, instaladores e metadados de aplicativos. A App Factory deve gerar builds mobile e desktop separados para cada tenant.

A marca global PIGE360 somente poderá aparecer em uma superfície do tenant quando uma política explícita de co-branding estiver habilitada no contrato e na configuração do tenant.

## Integração sem refatoração abrupta

- adicionar o pacote de branding como camada nova;
- não substituir cores por busca global;
- não alterar módulos de domínio para aplicar identidade visual;
- usar tokens e provider de branding;
- ativar por feature flag e rollout controlado;
- manter compatibilidade com os estilos existentes durante a migração;
- remover legado somente depois que nenhum consumidor permanecer;
- executar testes funcionais e visuais a cada grupo de telas.

## Paleta oficial

```text
Azul Profundo    #0D1B2A
Azul Petróleo    #006D77
Teal Claro       #14B8A6
Azul Claro       #3B82F6
Laranja Energia  #F59E0B
Dourado Suave    #FFD166
Cinza Claro      #F2F4F7
```

## Tipografia

```text
Títulos e destaques: Poppins SemiBold
Interface e textos:  Inter Regular
```

Não versionar arquivos de fonte sem verificar licença e autorização. Configure as famílias por dependência ou serviço aprovado.
