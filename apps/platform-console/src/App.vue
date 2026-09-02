<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Pige360SessionClient, type ApiProblem } from "@pige360/auth";

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
const selected = ref<Row | null>(null);
const apps = ref<Row>({ entitlements: [], manifests: [], builds: [], releases: [] });
const branding = ref<Row>({});
const domains = ref<Row[]>([]);
const logs = ref<Row[]>([]);
const lastLogQuery = ref("");

const form = reactive({ code: "", legal_name: "", trade_name: "", owner_email: "", owner_password: "" });
const supportForm = reactive({ reason: "", ticket: "", minutes: 30 });
const domainForm = reactive({ hostname: "", surface: "admin" });
const logFilters = reactive({ correlation_id: "", service: "", plane: "", level: "", minutes: 60, limit: 200 });

function msg(e: unknown) {
  const p = (e as Error & { problem?: ApiProblem })?.problem;
  return p?.detail || (e instanceof Error ? e.message : "Erro inesperado");
}

function clearFeedback() {
  error.value = "";
  notice.value = "";
}

function canonicalDomainHost(): string {
  return String(domains.value.find((domain: Row) => Boolean(domain.is_canonical))?.hostname || "—");
}

async function load() {
  clearFeedback();
  const [t, s, a, ss] = await Promise.all([
    api.request<Row>("/platform/tenants"),
    api.request<Row>("/platform/status"),
    api.request<Row>("/platform/audit?limit=50"),
    api.request<Row>("/platform/support-sessions?active_only=true"),
  ]);
  tenants.value = t.items || [];
  status.value = s;
  audit.value = a.items || [];
  support.value = ss.items || [];
  if (selected.value) {
    const fresh = tenants.value.find((x) => x.id === selected.value?.id);
    if (fresh) selected.value = fresh;
    await loadTenant();
  }
}

async function loadTenant() {
  if (!selected.value) return;
  const [appData, brandData, domainData] = await Promise.all([
    api.request<Row>(`/platform/tenants/${selected.value.id}/apps`),
    api.request<Row>(`/platform/tenants/${selected.value.id}/branding`),
    api.request<Row>(`/platform/tenants/${selected.value.id}/domains`),
  ]);
  apps.value = appData;
  branding.value = brandData;
  domains.value = domainData.items || [];
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

async function entitlement() {
  if (!selected.value) return;
  clearFeedback();
  try {
    await api.request(`/platform/tenants/${selected.value.id}/apps/entitlements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app_product: "pwa", state: "active", contract_reference: "console" }),
    });
    notice.value = "Entitlement PWA atualizado.";
    await loadTenant();
  } catch (e) {
    error.value = msg(e);
  }
}

async function manifestAndBuild() {
  if (!selected.value) return;
  const brandVersion = branding.value.active_version;
  if (!brandVersion) {
    error.value = "Publique o branding do tenant antes de gerar a PWA.";
    return;
  }
  const domain = domains.value.find((d: Row) => d.is_canonical)?.hostname || domains.value.find((d: Row) => d.status === "active")?.hostname;
  if (!domain) {
    error.value = "Tenant sem domínio provisionado.";
    return;
  }
  const slug = selected.value.code.replace(/[^a-z0-9]/g, "");
  clearFeedback();
  try {
    const mf = await api.request<Row>(`/platform/tenants/${selected.value.id}/apps/manifests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": `manifest-${crypto.randomUUID()}` },
      body: JSON.stringify({
        tenant_code: selected.value.code,
        brand_version: brandVersion,
        release_channel: "stable",
        apps: {
          pwa: {
            enabled: true,
            display_name: `${selected.value.trade_name} PWA`,
            identifier: `br.com.${slug}.pwa`,
            api_url: `https://${domain}`,
            web_url: `https://${domain}`,
            update_url: `https://${domain}/apps`,
            features: { finance: true, attendance: true },
            signing: {},
          },
        },
        metadata: { created_from: "platform-console" },
      }),
    });
    const build = await api.request<Row>(`/platform/tenants/${selected.value.id}/apps/builds`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": `build-${crypto.randomUUID()}` },
      body: JSON.stringify({ manifest_id: mf.id, platforms: ["pwa"], products: ["pwa"] }),
    });
    notice.value = `Build PWA ${build.id} enfileirado.`;
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

      <section v-if="!selected" class="grid two">
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

      <template v-else>
        <section class="grid two">
          <div class="panel"><h2>Tenant</h2><dl class="facts"><div><dt>Código</dt><dd>{{selected.code}}</dd></div><div><dt>Status</dt><dd>{{selected.status}}</dd></div><div><dt>Branding</dt><dd>v{{branding.active_version||0}} · {{branding.state}}</dd></div><div><dt>Domínio canônico</dt><dd>{{canonicalDomainHost()}}</dd></div></dl></div>
          <form class="panel form" @submit.prevent="createSupport"><h2>Sessão de suporte</h2><label>Motivo<textarea v-model="supportForm.reason" minlength="10" required></textarea></label><label>Ticket<input v-model="supportForm.ticket"></label><label>Duração (min)<input v-model.number="supportForm.minutes" type="number" min="5" max="120"></label><button class="primary">Criar sessão auditada</button></form>
        </section>

        <section class="panel">
          <div class="section-title"><div><h2>Domínios</h2><small>Canônico + domínios próprios com prova de posse, roteamento e TLS</small></div><span>{{domains.length}} registrados</span></div>
          <form class="domain-form" @submit.prevent="createDomain"><input v-model="domainForm.hostname" placeholder="portal.escola.com.br" required><select v-model="domainForm.surface"><option value="admin">Admin</option><option value="public">Público</option><option value="family">Família</option><option value="student">Aluno</option><option value="teacher">Professor</option></select><button class="primary">Adicionar domínio</button></form>
          <article class="domain-card" v-for="d in domains" :key="d.id">
            <div class="domain-head"><div><strong>{{d.hostname}}</strong><span>{{d.surface}} · {{d.is_canonical?'canônico':'personalizado'}}</span></div><span class="status-pill">{{d.status}}</span></div>
            <div class="domain-meta"><span>TLS: {{d.certificate_status||'—'}}</span><span>Verificação: {{d.verification_status||'—'}}</span><span v-if="d.provider">Provider: {{d.provider}}</span></div>
            <div v-if="d.routing_record" class="dns-box"><strong>Roteie o domínio para o PIGE360</strong><code>{{d.routing_record.type}} {{d.routing_record.name}}</code><code>{{d.routing_record.value}}</code><small>{{d.routing_record.apex_note}}</small><div><button class="ghost-dark" @click="copy(d.routing_record.name)">Copiar host</button><button class="ghost-dark" @click="copy(d.routing_record.value)">Copiar destino</button></div></div>
            <div v-if="d.verification_record && d.verification_status!=='verified'" class="dns-box"><strong>Publique este TXT para provar a posse</strong><code>{{d.verification_record.name}}</code><code>{{d.verification_record.value}}</code><div><button class="ghost-dark" @click="copy(d.verification_record.name)">Copiar nome</button><button class="ghost-dark" @click="copy(d.verification_record.value)">Copiar valor</button></div></div>
            <div class="row-actions" v-if="!d.is_canonical"><button v-if="d.verification_status!=='verified'" class="ghost-dark" @click="verifyDomain(d)">Verificar DNS</button><button v-if="d.verification_status==='verified' && d.status!=='active'" class="ghost-dark" @click="refreshDomain(d)">Verificar TLS</button><button class="danger-outline" @click="disableDomain(d)">Desativar</button></div>
            <p v-if="d.last_error" class="inline-error">{{d.last_error}}</p>
          </article>
        </section>

        <section class="panel"><div class="section-title"><h2>App Factory Web/PWA</h2><span>{{apps.builds?.length||0}} builds</span></div><p class="helper">Builds nativos estão congelados. A distribuição canônica atual é Web/PWA.</p><div class="app-actions"><button class="ghost-dark" @click="entitlement">Ativar entitlement PWA</button><button class="primary" @click="manifestAndBuild">Gerar manifesto + build PWA</button></div><div class="list-row" v-for="b in apps.builds" :key="b.id"><div><strong>{{b.id}}</strong><span>{{b.status||b.state}} · {{b.created_at}}</span></div><small>{{b.jobs?.length||0}} jobs</small></div></section>
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
