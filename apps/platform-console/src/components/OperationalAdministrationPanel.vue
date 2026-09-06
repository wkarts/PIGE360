<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row = Record<string, any>;

const props = defineProps<{
  api: Pige360SessionClient;
  tenants: Row[];
}>();

const emit = defineEmits<{
  feedback: [value: { type: "success" | "error"; message: string }];
}>();

const loading = ref(false);
const agents = ref<Row[]>([]);
const providers = ref<Row[]>([]);
const jobs = ref<Row[]>([]);
const includeRevoked = ref(false);
const oneTimeCredential = ref<Row | null>(null);
const queueReceipt = ref<Row | null>(null);
const agentRevokeReason = ref("");
const jobCancelReason = ref("");
const canManageAgents = computed(() => Boolean(
  props.api.claims()?.roles?.includes("platform_super_admin"),
));
const operationalSummary = computed(() => ({
  activeAgents: agents.value.filter((agent: Row) => agent.state === "active").length,
  onlineAgents: agents.value.filter((agent: Row) => agent.connectivity === "online").length,
  configuredProviders: providers.value.filter((provider: Row) => provider.configured).length,
  queuedJobs: jobs.value.filter((job: Row) => job.state === "queued").length,
  runningJobs: jobs.value.filter((job: Row) => job.state === "running").length,
  attentionJobs: jobs.value.filter((job: Row) => job.attention_required).length,
}));

const agentForm = reactive({
  name: "",
  agent_type: "multi",
  capabilities: ["backup.execute", "restore.execute", "deploy.execute"] as string[],
  software_version: "",
  reason: "",
});
const jobForm = reactive({
  operation_type: "backup",
  resource_scope: "platform",
  tenant_id: "",
  deployment_target: "cloudpanel",
  image_mode: "registry",
  release_version: "",
  backup_reference: "",
  reason: "",
});
const jobFilters = reactive({ operation_type: "", state: "", tenant_id: "" });

const capabilityOptions = [
  ["backup.execute", "Executar backup"],
  ["restore.execute", "Executar restore"],
  ["deploy.execute", "Executar deploy"],
] as const;

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return candidate?.problem?.detail || candidate?.message || "Erro inesperado";
}

function idempotencyKey(scope: string): string {
  return `${scope}:${crypto.randomUUID()}`;
}

function tenantName(tenantId: string | null): string {
  if (!tenantId) return "Plataforma";
  const tenant = props.tenants.find((item: Row) => item.id === tenantId);
  return tenant ? `${tenant.trade_name} (${tenant.code})` : tenantId;
}

function providerState(state: string): string {
  return {
    configured_not_probed: "Configurado — não testado externamente",
    configuration_incomplete: "Configuração incompleta",
    local_fallback: "Fallback local",
    disabled: "Desabilitado",
  }[state] || state;
}

function connectivityLabel(state: string): string {
  return {
    registered: "Registrado — aguardando heartbeat",
    online: "Online",
    stale: "Sem heartbeat recente",
    revoked: "Revogado",
  }[state] || state;
}

async function loadAgents() {
  const data = await props.api.request<Row>(
    `/platform/operations/agents?include_revoked=${includeRevoked.value ? "true" : "false"}`,
  );
  agents.value = data.items || [];
}

async function loadProviders() {
  const data = await props.api.request<Row>("/platform/operations/providers");
  providers.value = data.items || [];
}

async function loadJobs() {
  const params = new URLSearchParams({ limit: "100" });
  if (jobFilters.operation_type) params.set("operation_type", jobFilters.operation_type);
  if (jobFilters.state) params.set("state", jobFilters.state);
  if (jobFilters.tenant_id) params.set("tenant_id", jobFilters.tenant_id);
  const data = await props.api.request<Row>(`/platform/operations/jobs?${params.toString()}`);
  jobs.value = data.items || [];
}

async function loadAll() {
  loading.value = true;
  try {
    await Promise.all([loadAgents(), loadProviders(), loadJobs()]);
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  } finally {
    loading.value = false;
  }
}

function registrationCapabilities(): string[] {
  const required = {
    backup: "backup.execute",
    restore: "restore.execute",
    deploy: "deploy.execute",
  }[agentForm.agent_type];
  return required ? [required] : [...new Set(agentForm.capabilities)].sort();
}

async function registerAgent() {
  if (!canManageAgents.value) return;
  const capabilities = registrationCapabilities();
  if (!capabilities.length) {
    emit("feedback", { type: "error", message: "Selecione ao menos uma capability para o agente." });
    return;
  }
  try {
    const result = await props.api.request<Row>("/platform/operations/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: agentForm.name,
        agent_type: agentForm.agent_type,
        capabilities,
        software_version: agentForm.software_version || null,
        reason: agentForm.reason,
      }),
    });
    oneTimeCredential.value = result.credential;
    Object.assign(agentForm, {
      name: "",
      agent_type: "multi",
      capabilities: ["backup.execute", "restore.execute", "deploy.execute"],
      software_version: "",
      reason: "",
    });
    emit("feedback", { type: "success", message: "Agente registrado. Guarde agora a credencial exibida uma única vez." });
    await loadAgents();
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function copyCredential() {
  if (!oneTimeCredential.value?.token) return;
  try {
    await navigator.clipboard.writeText(String(oneTimeCredential.value.token));
    emit("feedback", { type: "success", message: "Credencial copiada. Armazene-a em um secret manager." });
  } catch {
    emit("feedback", { type: "error", message: "Não foi possível copiar automaticamente a credencial." });
  }
}

async function revokeAgent(agent: Row) {
  if (!canManageAgents.value) return;
  if (agentRevokeReason.value.trim().length < 10) {
    emit("feedback", { type: "error", message: "Informe um motivo auditável para revogar o agente." });
    return;
  }
  try {
    await props.api.request(`/platform/operations/agents/${agent.id}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: agent.version, reason: agentRevokeReason.value }),
    });
    agentRevokeReason.value = "";
    emit("feedback", { type: "success", message: "Agente revogado. Jobs ativos continuam marcados para atenção manual." });
    await Promise.all([loadAgents(), loadJobs()]);
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

function operationalJobPayload(): Row {
  const payload: Row = {
    operation_type: jobForm.operation_type,
    resource_scope: jobForm.operation_type === "deploy" ? "platform" : jobForm.resource_scope,
    reason: jobForm.reason,
  };
  if (payload.resource_scope === "tenant") payload.tenant_id = jobForm.tenant_id;
  if (jobForm.operation_type === "restore") payload.backup_reference = jobForm.backup_reference;
  if (jobForm.operation_type === "deploy") {
    payload.deployment_target = jobForm.deployment_target;
    payload.image_mode = jobForm.image_mode;
    payload.release_version = jobForm.release_version;
  }
  return payload;
}

async function queueJob() {
  try {
    const result = await props.api.request<Row>("/platform/operations/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey(`ops-${jobForm.operation_type}`),
      },
      body: JSON.stringify(operationalJobPayload()),
    });
    queueReceipt.value = {
      id: result.job?.id,
      execution_started: Boolean(result.execution_started),
      replayed: Boolean(result.replayed),
    };
    jobForm.reason = "";
    emit("feedback", {
      type: "success",
      message: result.execution_started
        ? "Job aceito e execução iniciada."
        : "Job registrado na fila; a execução ainda não começou.",
    });
    await loadJobs();
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function cancelJob(job: Row) {
  if (jobCancelReason.value.trim().length < 10) {
    emit("feedback", { type: "error", message: "Informe um motivo auditável para cancelar o job." });
    return;
  }
  try {
    await props.api.request(`/platform/operations/jobs/${job.id}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: job.version, reason: jobCancelReason.value }),
    });
    jobCancelReason.value = "";
    emit("feedback", { type: "success", message: "Job ainda não reivindicado foi cancelado." });
    await loadJobs();
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

watch(() => agentForm.agent_type, (agentType: string) => {
  const capability = {
    backup: "backup.execute",
    restore: "restore.execute",
    deploy: "deploy.execute",
  }[agentType];
  if (capability) agentForm.capabilities = [capability];
});
watch(() => jobForm.operation_type, (operationType: string) => {
  queueReceipt.value = null;
  if (operationType === "deploy") {
    jobForm.resource_scope = "platform";
    jobForm.tenant_id = "";
  }
});
watch(includeRevoked, async () => {
  try {
    await loadAgents();
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
});
onMounted(loadAll);
</script>

<template>
  <section class="operational-panel" aria-labelledby="operational-title">
    <header>
      <div><span class="eyebrow">Control Plane</span><h2 id="operational-title">Operação administrada</h2><p>Agentes, providers e fila auditável de backup, restore e deploy.</p></div>
      <button class="secondary" :disabled="loading" @click="loadAll">Atualizar operação</button>
    </header>

    <div class="truth-banner">
      <strong>Estado observado, sem simulação</strong>
      <span>Providers mostram configuração, não homologação. Enfileirar um job não significa executar: um agente compatível ainda precisa reivindicá-lo.</span>
    </div>

    <div v-if="oneTimeCredential" class="credential" role="status" aria-live="polite">
      <div><strong>Credencial exibida uma única vez</strong><span>Header: <code>{{oneTimeCredential.header}}</code>. Copie agora e salve em um secret manager; ela não poderá ser recuperada pela listagem.</span></div>
      <code class="token">{{oneTimeCredential.token}}</code>
      <div class="actions"><button class="primary" @click="copyCredential">Copiar credencial</button><button class="secondary" @click="oneTimeCredential=null">Ocultar definitivamente</button></div>
    </div>

    <div class="summary">
      <article><span>Agentes ativos</span><strong>{{operationalSummary.activeAgents}}</strong><small>{{operationalSummary.onlineAgents}} online</small></article>
      <article><span>Providers configurados</span><strong>{{operationalSummary.configuredProviders}}</strong><small>sem probe externo</small></article>
      <article><span>Jobs na fila</span><strong>{{operationalSummary.queuedJobs}}</strong><small>{{operationalSummary.runningJobs}} executando</small></article>
      <article><span>Requerem atenção</span><strong>{{operationalSummary.attentionJobs}}</strong><small>lease expirado</small></article>
    </div>

    <div class="operational-grid">
      <form v-if="canManageAgents" class="card" @submit.prevent="registerAgent">
        <h3>Registrar agente</h3>
        <label>Nome técnico<input v-model="agentForm.name" pattern="[a-z0-9][a-z0-9._-]+" minlength="3" required placeholder="deploy-host-01"></label>
        <label>Tipo<select v-model="agentForm.agent_type"><option value="host">Host</option><option value="backup">Backup</option><option value="restore">Restore</option><option value="deploy">Deploy</option><option value="multi">Multi</option></select></label>
        <fieldset :disabled="['backup','restore','deploy'].includes(agentForm.agent_type)"><legend>Capabilities</legend><label v-for="option in capabilityOptions" :key="option[0]"><input v-model="agentForm.capabilities" type="checkbox" :value="option[0]">{{option[1]}}</label></fieldset>
        <label>Versão do agente<input v-model="agentForm.software_version" placeholder="1.0.0"></label>
        <label>Motivo<input v-model="agentForm.reason" minlength="10" maxlength="2000" required></label>
        <button class="primary" type="submit">Registrar e gerar credencial</button>
      </form>

      <article class="card agent-list">
        <div class="card-title"><div><h3>Agentes</h3><small>Heartbeat stale após o limite informado pela API</small></div><label class="inline"><input v-model="includeRevoked" type="checkbox">Incluir revogados</label></div>
        <label v-if="canManageAgents">Motivo de revogação<input v-model="agentRevokeReason" minlength="10" placeholder="Obrigatório para revogar"></label>
        <div v-if="agents.length" class="rows"><div v-for="agent in agents" :key="agent.id" class="row"><div><strong>{{agent.name}}</strong><span>{{agent.agent_type}} · {{agent.capabilities.join(', ')}}</span><small>{{connectivityLabel(agent.connectivity)}} · versão {{agent.software_version||'não informada'}}</small></div><button v-if="canManageAgents&&agent.state==='active'" class="danger" @click="revokeAgent(agent)">Revogar</button></div></div>
        <p v-else class="empty">Nenhum agente registrado.</p>
      </article>
    </div>

    <article class="card providers">
      <div class="card-title"><div><h3>Providers</h3><small>status_source=configuration_only · external_probe_performed=false</small></div><span>{{providers.length}} providers</span></div>
      <div class="provider-grid"><div v-for="provider in providers" :key="provider.code"><strong>{{provider.code}}</strong><span>{{provider.category}}</span><small :class="`provider-${provider.state}`">{{providerState(provider.state)}}</small></div></div>
    </article>

    <form class="card" @submit.prevent="queueJob">
      <div class="card-title"><div><h3>Novo job operacional</h3><small>O pedido nasce em queued; nenhum comando é executado por esta tela.</small></div></div>
      <div class="job-form">
        <label>Operação<select v-model="jobForm.operation_type"><option value="backup">Backup</option><option value="restore">Restore</option><option value="deploy">Deploy</option></select></label>
        <label>Escopo<select v-model="jobForm.resource_scope" :disabled="jobForm.operation_type==='deploy'"><option value="platform">Plataforma</option><option value="tenant">Tenant</option></select></label>
        <label v-if="jobForm.resource_scope==='tenant'&&jobForm.operation_type!=='deploy'">Tenant<select v-model="jobForm.tenant_id" required><option value="">Selecione</option><option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{tenant.trade_name}} ({{tenant.code}})</option></select></label>
        <label v-if="jobForm.operation_type==='restore'">Referência do backup<input v-model="jobForm.backup_reference" pattern="[A-Za-z0-9][A-Za-z0-9._:@-]*" required placeholder="backup:platform:20260904"></label>
        <label v-if="jobForm.operation_type==='deploy'">Destino<select v-model="jobForm.deployment_target"><option value="base">Base</option><option value="cloudpanel">CloudPanel</option><option value="edge">Edge</option><option value="dockge">Dockge</option><option value="portainer">Portainer</option></select></label>
        <label v-if="jobForm.operation_type==='deploy'">Imagem<select v-model="jobForm.image_mode"><option value="registry">Registry</option><option value="source">Source</option></select></label>
        <label v-if="jobForm.operation_type==='deploy'">Release<input v-model="jobForm.release_version" required placeholder="1.0.1"></label>
      </div>
      <label>Motivo operacional<input v-model="jobForm.reason" minlength="10" maxlength="2000" required></label>
      <button class="primary" type="submit">Registrar job na fila</button>
      <div v-if="queueReceipt" class="queue-receipt"><strong>Job {{queueReceipt.id}}</strong><span>execution_started={{queueReceipt.execution_started}}</span><small v-if="!queueReceipt.execution_started">Registro concluído; execução ainda não iniciada.</small></div>
    </form>

    <article class="card jobs">
      <div class="card-title"><div><h3>Fila operacional</h3><small>Estados, agente atribuído, lease e evidência retornados pela API</small></div><button class="secondary" @click="loadJobs">Atualizar fila</button></div>
      <div class="filters"><select v-model="jobFilters.operation_type"><option value="">Todas operações</option><option value="backup">Backup</option><option value="restore">Restore</option><option value="deploy">Deploy</option></select><select v-model="jobFilters.state"><option value="">Todos estados</option><option value="queued">Queued</option><option value="claimed">Claimed</option><option value="running">Running</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option></select><select v-model="jobFilters.tenant_id"><option value="">Todos escopos</option><option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{tenant.trade_name}}</option></select><button class="secondary" @click="loadJobs">Filtrar</button></div>
      <label>Motivo para cancelar job queued<input v-model="jobCancelReason" minlength="10" placeholder="Obrigatório para cancelamento"></label>
      <div v-if="jobs.length" class="rows"><div v-for="job in jobs" :key="job.id" class="job-row"><div class="job-head"><div><strong>{{job.operation_type}} · {{tenantName(job.tenant_id)}}</strong><span>{{job.id}} · v{{job.version}}</span></div><span :class="['state',`state-${job.state}`]">{{job.state}}</span></div><div class="job-meta"><span>Capability: {{job.required_capability}}</span><span>Agente: {{job.assigned_agent_id||'não atribuído'}}</span><span>Execução iniciada: {{job.started_at?'sim':'não'}}</span><span>Tentativas: {{job.attempts}}</span></div><div v-if="job.attention_required" class="attention">Lease expirado; requer intervenção manual. O sistema não afirma reatribuição automática.</div><div v-if="job.result_code||job.failure_code||job.evidence_reference" class="evidence"><span v-if="job.result_code">Resultado: {{job.result_code}}</span><span v-if="job.failure_code">Falha: {{job.failure_code}}</span><span v-if="job.evidence_reference">Evidência: {{job.evidence_reference}}</span><code v-if="job.evidence_sha256">sha256 {{job.evidence_sha256}}</code></div><button v-if="job.state==='queued'" class="danger" @click="cancelJob(job)">Cancelar job</button></div></div>
      <p v-else class="empty">Nenhum job para os filtros atuais.</p>
    </article>
  </section>
</template>

<style scoped>
.operational-panel{display:grid;gap:16px;margin:20px 0}.operational-panel>header{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.operational-panel h2,.operational-panel h3{margin:0}.operational-panel p{color:#687780;margin:5px 0}.truth-banner,.credential,.queue-receipt,.attention{border-radius:13px;padding:13px;display:grid;gap:5px}.truth-banner{background:#edf5f5;border:1px solid #c9dfdf}.credential{background:#fff7df;border:1px solid #ead08b}.credential>div:first-child{display:grid;gap:4px}.credential .token{display:block;overflow:auto;white-space:nowrap;background:#332b1d;color:#fff7df;padding:10px;border-radius:8px}.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.summary article,.card{background:#fff;border:1px solid #dfe7ea;border-radius:16px;padding:17px}.summary article{display:grid;gap:4px}.summary article span,.summary article small{color:#687780}.summary article strong{font-size:24px;color:#006d77}.operational-grid{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(420px,1.2fr);gap:14px}.card{display:grid;gap:12px}.card form,.card label,.operational-panel form{display:grid;gap:6px}.card fieldset{border:1px solid #dfe7ea;border-radius:11px;display:grid;gap:7px}.card fieldset label,.inline{display:flex;align-items:center;gap:7px}.card input[type=checkbox]{padding:0}.card-title,.row,.job-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.card-title>div,.row>div:first-child,.job-head>div{display:grid;gap:4px}.card-title small,.row span,.row small,.job-head span,.job-meta,.evidence{font-size:12px;color:#687780}.rows{display:grid}.row,.job-row{padding:12px 0;border-top:1px solid #edf1f3}.row:first-child,.job-row:first-child{border-top:0}.actions,.filters{display:flex;gap:8px;flex-wrap:wrap}.primary,.secondary,.danger{border-radius:9px;padding:9px 11px;cursor:pointer}.primary{border:0;background:#006d77;color:#fff}.secondary{border:1px solid #cbd8dc;background:#fff}.danger{border:1px solid #e2b0b0;background:#fff;color:#8f2c2c}.provider-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:9px}.provider-grid>div{display:grid;gap:4px;padding:11px;background:#f4f7f9;border-radius:10px}.provider-grid span,.provider-grid small{font-size:12px;color:#687780}.provider-configured_not_probed{color:#8a6400!important}.provider-configuration_incomplete{color:#9b3030!important}.provider-local_fallback{color:#176147!important}.job-form{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:10px}.queue-receipt{background:#edf5f5}.job-row{display:grid;gap:9px}.job-meta,.evidence{display:flex;gap:10px;flex-wrap:wrap}.evidence code{word-break:break-all}.state{font-size:12px;border-radius:999px;padding:5px 9px;background:#eef2f3}.state-succeeded{background:#e8f7ef;color:#176147}.state-failed,.state-cancelled{background:#ffeded;color:#952d2d}.state-running,.state-claimed{background:#e8f4f3;color:#116b65}.attention{background:#fff0dd;color:#85500a}.empty{font-size:13px}@media(max-width:950px){.summary{grid-template-columns:repeat(2,1fr)}.operational-grid{grid-template-columns:1fr}.provider-grid{grid-template-columns:repeat(2,1fr)}.job-form{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.operational-panel>header,.card-title,.row,.job-head{align-items:flex-start;display:grid}.summary,.provider-grid,.job-form{grid-template-columns:1fr}.filters{display:grid}.filters>*{width:100%}}
</style>
