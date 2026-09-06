<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Pige360SessionClient, type ApiProblem } from "@pige360/auth";
import CommercialAdministrationPanel from "./components/CommercialAdministrationPanel.vue";
import OperationalAdministrationPanel from "./components/OperationalAdministrationPanel.vue";

type Row = Record<string, any>;
const api = new Pige360SessionClient();
const ready = ref(false);
const auth = ref(false);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const email = ref("");
const password = ref("");
const tenants = ref<Row[]>([]);
const status = ref<Row>({});
const audit = ref<Row[]>([]);
const support = ref<Row[]>([]);
const inventory = ref<Row>({});
const platformUsers = ref<Row[]>([]);
const selected = ref<Row | null>(null);
const apps = ref<Row>({ entitlements: [], manifests: [], builds: [], releases: [] });
const branding = ref<Row>({});
const domains = ref<Row[]>([]);
const quotas = ref<Row>({ configured: {}, effective: {}, enforcement: {} });
const logs = ref<Row[]>([]);
const lastLogQuery = ref("");

const form = reactive({ code: "", legal_name: "", trade_name: "", owner_email: "", owner_password: "" });
const supportForm = reactive({ reason: "", ticket: "", minutes: 30 });
const supportEndReason = ref("");
const lifecycleReason = ref("");
const quotaReason = ref("");
const domainForm = reactive({ hostname: "", surface: "admin" });
const logFilters = reactive({ correlation_id: "", service: "", plane: "", level: "", minutes: 60, limit: 200 });
const quotaForm = reactive({
  max_users: 500,
  max_students: 5000,
  storage_bytes: 107374182400,
  api_requests_per_minute: 6000,
  max_integrations: 20,
  max_concurrent_builds: 2,
  max_custom_domains: 10,
});
const selectedProducts = ref<string[]>(["pwa"]);
const selectedPlatforms = ref<string[]>(["pwa"]);
const productOptions = [
  ["pwa", "Web / PWA"],
  ["family-mobile", "Família mobile"],
  ["teacher-mobile", "Professor mobile"],
  ["student-mobile", "Aluno mobile"],
  ["admin-mobile", "Admin mobile"],
  ["pos-mobile", "PDV mobile"],
  ["kiosk", "Quiosque"],
  ["timeclock", "Ponto"],
  ["desktop-admin", "Admin desktop"],
  ["pos-desktop", "PDV desktop"],
] as const;
const platformOptions = [
  ["pwa", "PWA"],
  ["android-apk", "Android APK"],
  ["android-aab", "Android AAB"],
  ["ios-app", "iOS App"],
  ["ios-xcarchive", "iOS Archive"],
  ["ios-ipa-unsigned", "iOS IPA sem assinatura"],
  ["windows-x64", "Windows x64"],
  ["windows-x86", "Windows x86"],
  ["linux-x64", "Linux x64"],
  ["linux-arm64", "Linux ARM64"],
  ["macos-intel", "macOS Intel"],
  ["macos-apple", "macOS Apple"],
] as const;

function msg(e: unknown) {
  const p = (e as Error & { problem?: ApiProblem })?.problem;
  return p?.detail || (e instanceof Error ? e.message : "Erro inesperado");
}

function clearFeedback() {
  error.value = "";
  notice.value = "";
}

function handlePanelFeedback(value: { type: "success" | "error"; message: string }) {
  clearFeedback();
  if (value.type === "success") notice.value = value.message;
  else error.value = value.message;
}

function canonicalDomainHost(): string {
  return String(domains.value.find((domain: Row) => Boolean(domain.is_canonical) && domain.status === "active")?.hostname || "—");
}

function selectedSupportSessions(): Row[] {
  return support.value.filter((session: Row) => session.tenant_id === selected.value?.id);
}

function canManagePlatformUsers(): boolean {
  return Boolean(api.claims()?.roles?.includes("platform_super_admin"));
}

async function load() {
  clearFeedback();
  const [t, s, a, ss, operations, users] = await Promise.all([
    api.request<Row>("/platform/tenants"),
    api.request<Row>("/platform/status"),
    api.request<Row>("/platform/audit?limit=50"),
    api.request<Row>("/platform/support-sessions?active_only=true"),
    api.request<Row>("/platform/operations/inventory"),
    api.request<Row>("/platform/users"),
  ]);
  tenants.value = t.items || [];
  status.value = s;
  audit.value = a.items || [];
  support.value = ss.items || [];
  inventory.value = operations;
  platformUsers.value = users.items || [];
  if (selected.value) {
    const fresh = tenants.value.find((x) => x.id === selected.value?.id);
    if (fresh) selected.value = fresh;
    await loadTenant();
  }
}

async function loadTenant() {
  if (!selected.value) return;
  const [appData, brandData, domainData, quotaData] = await Promise.all([
    api.request<Row>(`/platform/tenants/${selected.value.id}/apps`),
    api.request<Row>(`/platform/tenants/${selected.value.id}/branding`),
    api.request<Row>(`/platform/tenants/${selected.value.id}/domains`),
    api.request<Row>(`/platform/tenants/${selected.value.id}/quotas`),
  ]);
  apps.value = appData;
  branding.value = brandData;
  domains.value = domainData.items || [];
  quotas.value = quotaData;
  Object.assign(quotaForm, quotaData.effective || {});
}

async function boot() {
  try {
    await api.initialize();
    auth.value = !!api.tokens;
    if (auth.value) await load();
  } catch (e) {
    error.value = msg(e);
  } finally {
    ready.value = true;
  }
}

async function login() {
  clearFeedback();
  try {
    await api.login(email.value, password.value);
    if (api.claims()?.plane !== "platform") throw new Error("Use uma conta do Control Plane.");
    auth.value = true;
    await load();
  } catch (e) {
    error.value = msg(e);
  }
}

async function logout() {
  await api.logout();
  auth.value = false;
}

async function createTenant() {
  busy.value = true;
  clearFeedback();
  try {
    const created = await api.request<Row>("/platform/tenants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    notice.value = `Tenant provisionado em ${created.hostname}.`;
    Object.assign(form, { code: "", legal_name: "", trade_name: "", owner_email: "", owner_password: "" });
    await load();
  } catch (e) {
    error.value = msg(e);
  } finally {
    busy.value = false;
  }
}

async function choose(t: Row) {
  selected.value = t;
  logs.value = [];
  await loadTenant();
}

async function createSupport() {
  if (!selected.value) return;
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/support-sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(supportForm),
    });
    notice.value = "Sessão de suporte auditada criada.";
    await load();
  } catch (e) {
    error.value = msg(e);
  }
}

async function revokeSupport(session: Row) {
  if (!supportEndReason.value.trim()) {
    error.value = "Informe o motivo do encerramento da sessão de suporte.";
    return;
  }
  clearFeedback();
  try {
    await api.request(`/platform/support-sessions/${session.id}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: supportEndReason.value }),
    });
    supportEndReason.value = "";
    notice.value = "Sessão de suporte encerrada e revogada.";
    await load();
  } catch (e) {
    error.value = msg(e);
  }
}

async function changeTenantState(action: "suspend" | "reactivate") {
  if (!selected.value) return;
  if (!lifecycleReason.value.trim()) {
    error.value = "Informe um motivo auditável para alterar o status do tenant.";
    return;
  }
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: selected.value.version, reason: lifecycleReason.value }),
    });
    lifecycleReason.value = "";
    notice.value = action === "suspend" ? "Tenant suspenso." : "Tenant reativado.";
    await load();
  } catch (e) {
    error.value = msg(e);
  }
}

async function updateQuotas() {
  if (!selected.value) return;
  if (!quotaReason.value.trim()) {
    error.value = "Informe o motivo da alteração das quotas.";
    return;
  }
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/quotas`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: selected.value.version, reason: quotaReason.value, quotas: quotaForm }),
    });
    quotaReason.value = "";
    notice.value = "Quotas atualizadas com controle de versão.";
    await load();
  } catch (e) {
    error.value = msg(e);
  }
}

async function setPlatformUserState(platformUser: Row, active: boolean) {
  if (!canManagePlatformUsers()) return;
  const reason = window.prompt(active ? "Motivo para reativar este usuário:" : "Motivo para desativar este usuário:");
  if (!reason) return;
  clearFeedback();
  try {
    await api.request(`/platform/users/${platformUser.id}/active`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active, reason }),
    });
    notice.value = active ? "Usuário da plataforma reativado." : "Usuário da plataforma desativado e sessões revogadas.";
    await load();
  } catch (e) {
    error.value = msg(e);
  }
}

async function activateEntitlements() {
  if (!selected.value || busy.value) return;
  if (!selectedProducts.value.length) {
    error.value = "Selecione ao menos um produto.";
    return;
  }
  busy.value = true;
  clearFeedback();
  try {
    await Promise.all(selectedProducts.value.map((appProduct) => api.request(
      `/platform/tenants/${selected.value!.id}/apps/entitlements`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ app_product: appProduct, state: "active", contract_reference: "platform-console" }),
      },
    )));
    notice.value = "Entitlements selecionados foram ativados.";
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  } finally {
    busy.value = false;
  }
}

async function manifestAndBuild() {
  if (!selected.value || busy.value) return;
  if (!selectedProducts.value.length || !selectedPlatforms.value.length) {
    error.value = "Selecione ao menos um produto e uma plataforma.";
    return;
  }
  const brandVersion = branding.value.active_version;
  if (!brandVersion) {
    error.value = "Publique o branding do tenant antes de solicitar builds.";
    return;
  }
  const domain = domains.value.find((d: Row) => d.is_canonical && d.status === "active")?.hostname || domains.value.find((d: Row) => d.status === "active")?.hostname;
  if (!domain) {
    error.value = "Tenant sem domínio provisionado.";
    return;
  }
  const slug = selected.value.code.replace(/[^a-z0-9]/g, "");
  const manifestApps = Object.fromEntries(selectedProducts.value.map((product) => {
    const suffix = product.replace(/[^a-z0-9]/g, "");
    const label = productOptions.find(([value]) => value === product)?.[1] || product;
    const previous = apps.value.manifests?.[0]?.payload?.apps?.[product] || {};
    return [product, {
      enabled: true,
      display_name: `${selected.value!.trade_name} ${label}`,
      identifier: previous.identifier || `br.com.${slug}.${suffix}`,
      api_url: `https://${domain}`,
      web_url: `https://${domain}`,
      update_url: `https://${domain}/apps`,
      icon_asset_id: previous.icon_asset_id || null,
      splash_asset_id: previous.splash_asset_id || null,
      features: { finance: true, attendance: true },
      signing: previous.signing?.requires_reconfiguration ? {} : (previous.signing || {}),
    }];
  }));
  busy.value = true;
  clearFeedback();
  try {
    const mf = await api.request<Row>(`/platform/tenants/${selected.value.id}/apps/manifests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": `manifest-${crypto.randomUUID()}` },
      body: JSON.stringify({
        tenant_code: selected.value.code,
        brand_version: brandVersion,
        release_channel: "stable",
        apps: manifestApps,
        metadata: { created_from: "platform-console" },
      }),
    });
    const build = await api.request<Row>(`/platform/tenants/${selected.value.id}/apps/builds`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": `build-${crypto.randomUUID()}` },
      body: JSON.stringify({ manifest_id: mf.id, platforms: selectedPlatforms.value, products: selectedProducts.value }),
    });
    notice.value = `Build ${build.build_id} enfileirado com ${build.jobs?.length || 0} jobs compatíveis.`;
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  } finally {
    busy.value = false;
  }
}

async function retryBuild(build: Row) {
  if (!selected.value) return;
  const reason = window.prompt("Motivo para reenfileirar os jobs com falha:");
  if (!reason) return;
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/apps/builds/${build.build_id}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    notice.value = `Build ${build.build_id} reenfileirado.`;
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  }
}

async function createDomain() {
  if (!selected.value) return;
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/domains`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(domainForm),
    });
    Object.assign(domainForm, { hostname: "", surface: "admin" });
    notice.value = "Domínio cadastrado. Configure CNAME/flattening e TXT antes de verificar.";
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  }
}

async function verifyDomain(domain: Row) {
  if (!selected.value) return;
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/domains/${domain.id}/verify`, { method: "POST" });
    notice.value = "Propriedade do domínio verificada. TLS foi solicitado.";
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  }
}

async function refreshDomain(domain: Row) {
  if (!selected.value) return;
  clearFeedback();
  try {
    const result = await api.request<Row>(`/platform/tenants/${selected.value.id}/domains/${domain.id}/refresh`, { method: "POST" });
    notice.value = result.status === "active" ? "Domínio e TLS ativos." : "TLS ainda em provisionamento.";
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  }
}

async function disableDomain(domain: Row) {
  if (!selected.value || domain.is_canonical) return;
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/domains/${domain.id}`, { method: "DELETE" });
    notice.value = "Domínio personalizado desativado.";
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  }
}

async function copy(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    notice.value = "Valor copiado.";
  } catch {
    error.value = "Não foi possível copiar automaticamente.";
  }
}

async function loadLogs() {
  clearFeedback();
  const params = new URLSearchParams();
  if (selected.value?.id) params.set("tenant_id", selected.value.id);
  if (logFilters.correlation_id) params.set("correlation_id", logFilters.correlation_id);
  if (logFilters.service) params.set("service", logFilters.service);
  if (logFilters.plane) params.set("plane", logFilters.plane);
  if (logFilters.level) params.set("level", logFilters.level);
  params.set("minutes", String(logFilters.minutes));
  params.set("limit", String(logFilters.limit));
  try {
    const result = await api.request<Row>(`/platform/logs?${params.toString()}`);
    logs.value = result.items || [];
    lastLogQuery.value = result.query || "";
  } catch (e) {
    error.value = msg(e);
  }
}

onMounted(boot);
</script>

<template>
  <div v-if="!ready" class="center">Inicializando Control Plane…</div>
  <div v-else-if="!auth" class="login-page platform-login">
    <form class="login-card" @submit.prevent="login">
      <div class="mark">◈</div><span class="eyebrow">PIGE360</span><h1>Console Global</h1>
      <p>Administração da plataforma, tenants e distribuição.</p>
      <label>E-mail<input v-model="email" type="email" required></label>
      <label>Senha<input v-model="password" type="password" required></label>
      <p v-if="error" class="flash error">{{ error }}</p>
      <button class="primary">Entrar</button>
    </form>
  </div>

  <div v-else class="console">
    <aside>
      <div class="brand"><div class="mark">◈</div><div><strong>PIGE360</strong><small>Control Plane</small></div></div>
      <button :class="{ active: !selected }" @click="selected=null; logs=[]"><strong>Visão global</strong><small>Plataforma</small></button>
      <button v-for="t in tenants" :key="t.id" :class="{active:selected?.id===t.id}" @click="choose(t)"><strong>{{t.trade_name}}</strong><small>{{t.status}}</small></button>
      <button class="logout" @click="logout">Sair</button>
    </aside>

    <main>
      <div v-if="error" class="flash error">{{error}}</div>
      <div v-if="notice" class="flash success">{{notice}}</div>
      <header><div><span class="eyebrow">PIGE360</span><h1>{{selected?selected.trade_name:'Visão global'}}</h1></div><button class="ghost-dark" @click="load">Atualizar</button></header>

      <section class="metrics">
        <article><span>Tenants</span><strong>{{status.tenants?.total||0}}</strong><small>{{status.tenants?.active||0}} ativos</small></article>
        <article><span>Domínios</span><strong>{{status.domains||0}}</strong><small>hosts registrados</small></article>
        <article><span>Builds na fila</span><strong>{{status.builds?.queued||0}}</strong><small>{{status.builds?.building||0}} executando</small></article>
        <article><span>Suporte</span><strong>{{status.active_support_sessions||0}}</strong><small>sessões ativas</small></article>
      </section>

      <template v-if="!selected">
        <section class="grid two">
          <form class="panel form" @submit.prevent="createTenant">
            <h2>Provisionar tenant</h2>
            <p class="helper">O domínio canônico é criado automaticamente como <code>&lt;codigo&gt;.pige360.com.br</code>.</p>
            <label>Código<input v-model="form.code" pattern="[a-z0-9-]+" required placeholder="colegio-modelo"></label>
            <label>Razão social<input v-model="form.legal_name" required></label>
            <label>Nome comercial<input v-model="form.trade_name" required></label>
            <label>Administrador inicial<input v-model="form.owner_email" type="email" required></label>
            <label>Senha inicial<input v-model="form.owner_password" type="password" minlength="10" required></label>
            <button class="primary" :disabled="busy">Provisionar</button>
          </form>
          <div class="panel"><h2>Auditoria global</h2><div class="list-row" v-for="a in audit.slice(0,15)" :key="a.id"><div><strong>{{a.action}} · {{a.aggregate_type}}</strong><span>{{a.tenant_id||'platform'}} · {{a.correlation_id}}</span></div><small>{{a.created_at}}</small></div></div>
        </section>

        <section class="grid two">
          <div class="panel">
            <div class="section-title"><div><h2>Saúde e recursos</h2><small>Leitura interna; nenhum provider externo é consultado</small></div><span class="status-pill">{{inventory.status||'—'}}</span></div>
            <dl class="facts">
              <div><dt>Control DB</dt><dd>{{inventory.control_database?.provider}} · {{inventory.control_database?.state}}</dd></div>
              <div><dt>Bancos tenant</dt><dd>{{inventory.tenant_resources?.database_reachable||0}} acessíveis · {{inventory.tenant_resources?.database_unavailable||0}} indisponíveis</dd></div>
              <div><dt>Storage</dt><dd>{{inventory.tenant_resources?.storage_configured||0}} tenants configurados</dd></div>
              <div><dt>Outbox</dt><dd>{{inventory.workloads?.control_outbox_pending||0}} control · {{inventory.workloads?.tenant_outbox_pending||0}} tenants</dd></div>
              <div><dt>Integrações</dt><dd>{{inventory.workloads?.integration_connections||0}} conexões registradas</dd></div>
              <div><dt>Mail</dt><dd>{{inventory.configuration?.mail?.mode||'disabled'}} · {{inventory.workloads?.mail_accounts||0}} contas</dd></div>
              <div><dt>Deploy remoto</dt><dd>{{inventory.configuration?.remote_operations?.deploy_enabled?'habilitado':'desabilitado'}}</dd></div>
            </dl>
          </div>
          <div class="panel">
            <div class="section-title"><div><h2>Usuários da plataforma</h2><small>Senha, token e credenciais nunca são exibidos</small></div><span>{{platformUsers.length}} contas</span></div>
            <div class="list-row" v-for="platformUser in platformUsers" :key="platformUser.id">
              <div><strong>{{platformUser.email}}</strong><span>{{platformUser.roles.join(', ')}} · {{platformUser.active?'ativo':'inativo'}}<template v-if="platformUser.is_current_user"> · sua conta</template></span></div>
              <button v-if="canManagePlatformUsers() && !platformUser.is_current_user" :class="platformUser.active?'danger-outline':'ghost-dark'" @click="setPlatformUserState(platformUser,!platformUser.active)">{{platformUser.active?'Desativar':'Reativar'}}</button>
            </div>
          </div>
        </section>

        <section class="panel" v-if="support.length">
          <div class="section-title"><div><h2>Sessões de suporte ativas</h2><small>Acesse o tenant para encerrar uma sessão com motivo auditável</small></div><span>{{support.length}} ativas</span></div>
          <div class="list-row" v-for="session in support" :key="session.id"><div><strong>{{session.ticket||session.id}}</strong><span>{{session.tenant_id}} · expira {{session.expires_at}}</span></div><small>{{session.reason}}</small></div>
        </section>

        <OperationalAdministrationPanel :api="api" :tenants="tenants" @feedback="handlePanelFeedback" />
        <CommercialAdministrationPanel :api="api" :tenants="tenants" @feedback="handlePanelFeedback" />
      </template>

      <template v-else>
        <section class="grid two">
          <div class="panel form">
            <h2>Tenant</h2>
            <dl class="facts"><div><dt>Código</dt><dd>{{selected.code}}</dd></div><div><dt>Status</dt><dd>{{selected.status}}</dd></div><div><dt>Versão</dt><dd>{{selected.version}}</dd></div><div><dt>Branding</dt><dd>v{{branding.active_version||0}} · {{branding.state}}</dd></div><div><dt>Domínio canônico</dt><dd>{{canonicalDomainHost()}}</dd></div></dl>
            <label>Motivo da alteração de status<textarea v-model="lifecycleReason" minlength="10" maxlength="2000" placeholder="Motivo auditável"></textarea></label>
            <div class="row-actions"><button v-if="selected.status==='active'||selected.status==='degraded'" class="danger-outline" @click="changeTenantState('suspend')">Suspender tenant</button><button v-if="selected.status==='suspended'" class="primary" @click="changeTenantState('reactivate')">Reativar tenant</button></div>
          </div>
          <form class="panel form" @submit.prevent="createSupport">
            <h2>Sessão de suporte</h2><label>Motivo<textarea v-model="supportForm.reason" minlength="10" required></textarea></label><label>Ticket<input v-model="supportForm.ticket"></label><label>Duração (min)<input v-model.number="supportForm.minutes" type="number" min="5" max="120"></label><button class="primary" :disabled="selected.status!=='active'">Criar sessão auditada</button>
            <template v-if="selectedSupportSessions().length"><label>Motivo para encerrar<input v-model="supportEndReason" minlength="10" placeholder="Conclusão do atendimento"></label><div class="support-session" v-for="session in selectedSupportSessions()" :key="session.id"><div><strong>{{session.ticket||session.id}}</strong><small>Expira {{session.expires_at}}</small></div><button type="button" class="danger-outline" @click="revokeSupport(session)">Encerrar e revogar</button></div></template>
          </form>
        </section>

        <form class="panel form" @submit.prevent="updateQuotas">
          <div class="section-title"><div><h2>Quotas do tenant</h2><small>Atualização com versão otimista {{quotas.version}}</small></div><span>{{Object.keys(quotas.configured||{}).length}} configuradas</span></div>
          <div class="quota-grid"><label>Usuários<input v-model.number="quotaForm.max_users" type="number" min="1" max="1000000" required></label><label>Alunos<input v-model.number="quotaForm.max_students" type="number" min="0" max="10000000" required></label><label>Storage (bytes, informativo)<input v-model.number="quotaForm.storage_bytes" type="number" min="1048576" required></label><label>Requests/min<input v-model.number="quotaForm.api_requests_per_minute" type="number" min="1" max="1000000" required></label><label>Integrações<input v-model.number="quotaForm.max_integrations" type="number" min="0" max="10000" required></label><label>Builds simultâneos<input v-model.number="quotaForm.max_concurrent_builds" type="number" min="1" max="64" required></label><label>Domínios próprios<input v-model.number="quotaForm.max_custom_domains" type="number" min="0" max="1000" required></label></div>
          <div class="entitlements"><span v-for="(rule,key) in quotas.enforcement" :key="String(key)" class="status-pill">{{key}} · {{rule.status==='enforced'?'aplicada':'não aplicada'}}</span></div>
          <label>Motivo da alteração<input v-model="quotaReason" minlength="10" maxlength="2000" required></label><button class="primary">Salvar quotas</button>
        </form>

        <section class="panel">
          <div class="section-title"><div><h2>Domínios</h2><small>Canônico + domínios próprios com prova de posse, roteamento e TLS</small></div><span>{{domains.length}} registrados</span></div>
          <form class="domain-form" @submit.prevent="createDomain"><input v-model="domainForm.hostname" placeholder="portal.escola.com.br" required><select v-model="domainForm.surface"><option value="admin">Admin</option><option value="public">Público</option><option value="family">Família</option><option value="student">Aluno</option><option value="teacher">Professor</option></select><button class="primary">Adicionar domínio</button></form>
          <article class="domain-card" v-for="d in domains" :key="d.id">
            <div class="domain-head"><div><strong>{{d.hostname}}</strong><span>{{d.surface}} · {{d.is_canonical?'canônico':'personalizado'}}</span></div><span class="status-pill">{{d.status}}</span></div>
            <div class="domain-meta"><span>TLS: {{d.certificate_status||'—'}}</span><span>Verificação: {{d.verification_status||'—'}}</span><span v-if="d.provider">Provider: {{d.provider}}</span></div>
            <div v-if="d.routing_record" class="dns-box"><strong>Roteie o domínio para o PIGE360</strong><code>{{d.routing_record.type}} {{d.routing_record.name}}</code><code>{{d.routing_record.value}}</code><small>{{d.routing_record.apex_note}}</small><div><button class="ghost-dark" @click="copy(d.routing_record.name)">Copiar host</button><button class="ghost-dark" @click="copy(d.routing_record.value)">Copiar destino</button></div></div>
            <div v-if="d.verification_record && d.verification_status!=='verified'" class="dns-box"><strong>Publique este TXT para provar a posse</strong><code>{{d.verification_record.name}}</code><code>{{d.verification_record.value}}</code><div><button class="ghost-dark" @click="copy(d.verification_record.name)">Copiar nome</button><button class="ghost-dark" @click="copy(d.verification_record.value)">Copiar valor</button></div></div>
            <div v-if="d.provider_validation_records?.length" class="dns-box"><strong>Validação adicional exigida pelo provider</strong><div v-for="record in d.provider_validation_records" :key="`${record.purpose}-${record.type}-${record.name}`"><code>{{record.purpose}} · {{record.type}} · {{record.name}}</code><code>{{record.value}}</code><small v-if="record.status">Status: {{record.status}}</small><div><button class="ghost-dark" @click="copy(String(record.name))">Copiar nome</button><button class="ghost-dark" @click="copy(String(record.value))">Copiar valor</button></div></div></div>
            <div class="row-actions" v-if="!d.is_canonical"><button v-if="d.verification_status!=='verified'" class="ghost-dark" @click="verifyDomain(d)">Verificar DNS</button><button v-if="d.verification_status==='verified' && d.status!=='active'" class="ghost-dark" @click="refreshDomain(d)">Verificar TLS</button><button class="danger-outline" @click="disableDomain(d)">Desativar</button></div>
            <p v-if="d.last_error" class="inline-error">{{d.last_error}}</p>
          </article>
        </section>

        <section class="panel app-factory">
          <div class="section-title"><div><h2>App Factory multicanal</h2><small>Os jobs são executados somente por agentes compatíveis; assinatura depende de configuração externa</small></div><span>{{apps.builds?.length||0}} builds</span></div>
          <div class="build-selection"><fieldset><legend>Produtos</legend><label v-for="option in productOptions" :key="option[0]"><input v-model="selectedProducts" type="checkbox" :value="option[0]">{{option[1]}}</label></fieldset><fieldset><legend>Plataformas</legend><label v-for="option in platformOptions" :key="option[0]"><input v-model="selectedPlatforms" type="checkbox" :value="option[0]">{{option[1]}}</label></fieldset></div>
          <div class="entitlements"><span v-for="item in apps.entitlements" :key="item.id" class="status-pill">{{item.app_product}} · {{item.state}}</span></div>
          <div class="app-actions"><button class="ghost-dark" :disabled="busy" @click="activateEntitlements">Ativar entitlements selecionados</button><button class="primary" :disabled="busy" @click="manifestAndBuild">Gerar manifesto + solicitar build</button></div>
          <article class="build-card" v-for="build in apps.builds" :key="build.build_id">
            <div class="section-title"><div><strong>{{build.build_id}}</strong><small>{{build.created_at}} · {{build.requested_platforms?.join(', ')}}</small></div><span class="status-pill">{{build.status}}</span></div>
            <div class="job-grid"><div v-for="job in build.jobs" :key="job.id"><strong>{{job.app_product}} · {{job.platform}}</strong><span>{{job.status}} · {{job.required_os}}/{{job.architecture}}</span><small v-if="job.last_error" class="inline-error">{{job.last_error}}</small></div></div>
            <div class="artifact-list" v-if="build.artifacts?.length"><div v-for="artifact in build.artifacts" :key="artifact.id"><strong>{{artifact.filename}}</strong><span>{{artifact.artifact_kind}} · {{artifact.platform}}/{{artifact.architecture}} · {{artifact.signed_state}}</span><code>sha256 {{artifact.sha256}}</code></div></div>
            <button v-if="build.status==='failed'" class="ghost-dark" @click="retryBuild(build)">Reenfileirar falhas</button>
          </article>
          <p v-if="!apps.builds?.length" class="empty">Nenhum build solicitado para este tenant.</p>
        </section>
        <section class="panel"><h2>Releases</h2><div class="list-row" v-for="r in apps.releases" :key="r.id"><div><strong>{{r.version}} · {{r.channel}}</strong><span>{{r.state}}</span></div><small>{{r.created_at}}</small></div><p v-if="!apps.releases?.length" class="empty">Nenhuma release criada.</p></section>
      </template>

      <section class="panel logs-panel">
        <div class="section-title"><div><h2>Central de logs</h2><small>{{selected?`Filtrando por ${selected.trade_name}`:'Toda a plataforma'}}</small></div><span>{{logs.length}} eventos</span></div>
        <div class="log-filters"><input v-model="logFilters.correlation_id" placeholder="Correlation ID"><input v-model="logFilters.service" placeholder="Serviço, ex.: pige360-api"><select v-model="logFilters.plane"><option value="">Todos os planes</option><option value="platform">platform</option><option value="tenant">tenant</option></select><select v-model="logFilters.level"><option value="">Todos os níveis</option><option value="info">info</option><option value="warning">warning</option><option value="error">error</option></select><input v-model.number="logFilters.minutes" type="number" min="1" max="10080" title="Janela em minutos"><button class="primary" @click="loadLogs">Consultar</button></div>
        <code v-if="lastLogQuery" class="query-code">{{lastLogQuery}}</code>
        <div class="log-row" v-for="l in logs" :key="l.timestamp_ns + JSON.stringify(l.labels)"><div class="log-tags"><span>{{l.labels?.service||'serviço'}}</span><span v-if="l.labels?.tenant_code">{{l.labels.tenant_code}}</span><span v-if="l.event?.correlation_id">{{l.event.correlation_id}}</span></div><pre>{{l.event?JSON.stringify(l.event,null,2):l.message}}</pre></div>
        <p v-if="!logs.length" class="empty">Use os filtros acima para consultar o Loki pelo Control Plane.</p>
      </section>
    </main>
  </div>
</template>
