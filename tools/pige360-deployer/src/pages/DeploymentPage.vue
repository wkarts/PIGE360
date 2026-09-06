<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import AppPageTitleBar from "../components/base/AppPageTitleBar.vue";
import { appConfirm } from "../services/dialog";
import type {
  AgentEvent,
  AgentStatus,
  ConnectionInput,
  ConnectionTestResult,
  DeployRequest,
  DeploymentEnvironment,
  DeploymentPlatform,
  DesktopDeployRequest,
  DistributionChannel,
  DistributionDescriptor,
} from "../types/deployment";

const connection = reactive<ConnectionInput>({
  host: "",
  port: 22,
  user: "root",
  auth_method: "key",
  key_file: "",
  known_hosts_file: "",
  accept_new_host_key: false,
  sudo: false,
  connect_timeout_seconds: 20,
});

const deployment = reactive<DeployRequest>({
  protocol_version: 1,
  repository: "",
  channel: "develop",
  environment: "develop",
  requested_version: "develop",
  platform: "compose",
  directory: "/opt/stacks/pige360-develop",
  action: "plan",
  rollback_tag: "",
  github_token: "",
  registry_user: "",
  registry_token: "",
  env_input: null,
  env_overrides: {},
  secret_inputs: {},
  wait_seconds: 600,
});

const config = reactive({
  baseDomain: "pige360.argws.com.br",
  acmeEmail: "infra@pige360.com.br",
  cloudflareToken: "",
  cloudflareControlTunnelToken: "",
  cloudflareTenantTunnelToken: "",
  connectApiKey: "",
  cloudflareZoneId: "",
  envInputPath: "",
});

const testing = ref(false);
const loadingCatalog = ref(false);
const running = ref(false);
const testResult = ref<ConnectionTestResult | null>(null);
const distributions = ref<DistributionDescriptor[]>([]);
const result = ref<unknown>(null);
const errorMessage = ref("");
const progress = ref(0);
const logs = ref<AgentEvent[]>([]);
const agentStatus = ref<AgentStatus | null>(null);
let unlisten: UnlistenFn | null = null;

const targetLabel: Record<DeploymentPlatform, string> = {
  compose: "Docker Compose",
  dockge: "Dockge",
  cloudpanel: "CloudPanel",
  portainer: "Portainer",
};

const agentsReady = computed(() => Boolean(agentStatus.value?.amd64?.embedded));
const production = computed(() => deployment.environment === "production");
const immutableReference = computed(() => {
  if (deployment.channel === "develop") return "develop-<sha12>";
  if (deployment.channel === "prerelease") return deployment.requested_version || "develop-<sha12>";
  return deployment.requested_version || "latest";
});
const canRun = computed(() => {
  const auth = connection.auth_method === "agent" || Boolean(connection.key_file?.trim());
  const channelOk = !production.value || deployment.channel === "stable";
  return Boolean(
    connection.host.trim() &&
      connection.user.trim() &&
      auth &&
      deployment.repository.trim() &&
      deployment.requested_version.trim() &&
      deployment.directory.trim() &&
      channelOk &&
      agentsReady.value &&
      !running.value,
  );
});

watch(
  () => deployment.environment,
  (environment: DeploymentEnvironment) => {
    if (environment === "production") {
      deployment.channel = "stable";
      deployment.requested_version = "latest";
      deployment.directory = "/opt/stacks/pige360-production";
      config.baseDomain = "pige360.com.br";
    } else {
      deployment.channel = "develop";
      deployment.requested_version = "develop";
      deployment.directory = "/opt/stacks/pige360-develop";
      config.baseDomain = "pige360.argws.com.br";
    }
    deployment.rollback_tag = "";
    testResult.value = null;
  },
);

watch(
  () => deployment.channel,
  (channel: DistributionChannel) => {
    if (channel === "develop") deployment.requested_version = "develop";
    if (channel === "prerelease" && !/^develop-[0-9a-f]{12}$/.test(deployment.requested_version)) {
      deployment.requested_version = "";
    }
    if (channel === "stable" && deployment.requested_version === "develop") deployment.requested_version = "latest";
  },
);

function clearSensitiveFields() {
  deployment.github_token = "";
  deployment.registry_token = "";
  config.cloudflareToken = "";
  config.cloudflareControlTunnelToken = "";
  config.cloudflareTenantTunnelToken = "";
  config.connectApiKey = "";
}

function formatBytes(value?: number | null): string {
  if (!value) return "—";
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

async function loadDistributions() {
  loadingCatalog.value = true;
  errorMessage.value = "";
  try {
    distributions.value = await invoke<DistributionDescriptor[]>("pige360_distribution_list", {
      repository: deployment.repository,
      githubToken: deployment.github_token || null,
    });
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    loadingCatalog.value = false;
  }
}

function selectDistribution(item: DistributionDescriptor) {
  deployment.channel = item.channel;
  deployment.environment = item.channel === "stable" ? "production" : "develop";
  deployment.requested_version = item.reference;
}

async function testServer() {
  testing.value = true;
  errorMessage.value = "";
  testResult.value = null;
  try {
    testResult.value = await invoke<ConnectionTestResult>("pige360_test_connection", { input: { ...connection } });
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    testing.value = false;
  }
}

function buildInput(): DesktopDeployRequest {
  const domain = config.baseDomain.trim();
  const envOverrides: Record<string, string> = {};
  if (domain) {
    envOverrides.PIGE360_BASE_DOMAIN = domain;
    envOverrides.PLATFORM_CONTROL_BASE_DOMAIN = domain;
    envOverrides.PLATFORM_CONSOLE_HOST = `console.${domain}`;
    envOverrides.PLATFORM_API_HOST = `api.${domain}`;
    envOverrides.PLATFORM_OPS_HOST = `ops.${domain}`;
    envOverrides.PLATFORM_BRANDING_HOST = `branding.${domain}`;
    envOverrides.PLATFORM_DOWNLOADS_HOST = `downloads.${domain}`;
    envOverrides.TENANT_DEFAULT_BASE_DOMAIN = domain;
    envOverrides.TENANT_WILDCARD_HOST = `*.${domain}`;
    envOverrides.TENANT_CANONICAL_HOST_TEMPLATE = `{tenant}.${domain}`;
    envOverrides.TENANT_CUSTOM_DOMAIN_CNAME_TARGET = `edge.${domain}`;
  }
  if (config.acmeEmail.trim()) envOverrides.ACME_EMAIL = config.acmeEmail.trim();
  if (config.cloudflareZoneId.trim()) {
    envOverrides.CLOUDFLARE_CONTROL_ZONE_ID = config.cloudflareZoneId.trim();
    envOverrides.CLOUDFLARE_TENANT_ZONE_ID = config.cloudflareZoneId.trim();
  }
  const secretInputs: Record<string, string> = {};
  if (config.cloudflareToken) secretInputs.cloudflare_api_token = config.cloudflareToken;
  if (config.cloudflareControlTunnelToken) secretInputs.cloudflare_control_tunnel_token = config.cloudflareControlTunnelToken;
  if (config.cloudflareTenantTunnelToken) secretInputs.cloudflare_tenant_tunnel_token = config.cloudflareTenantTunnelToken;
  if (config.connectApiKey) secretInputs.connect_api_key = config.connectApiKey;
  return {
    connection: { ...connection },
    deploy: { ...deployment, env_input: null, env_overrides: envOverrides, secret_inputs: secretInputs },
    env_input_path: config.envInputPath.trim() || null,
  };
}

async function execute() {
  if (deployment.action === "apply" || deployment.action === "rollback") {
    const accepted = await appConfirm({
      title: deployment.action === "rollback" ? "Confirmar rollback" : "Confirmar implantação",
      message: `${deployment.action === "rollback" ? "Reverter" : "Implantar"} ${targetLabel[deployment.platform]} ${deployment.environment} em ${connection.host}?`,
      confirmText: deployment.action === "rollback" ? "Executar rollback" : "Implantar",
      cancelText: "Cancelar",
      danger: deployment.action === "rollback",
    });
    if (!accepted) return;
  }
  running.value = true;
  errorMessage.value = "";
  logs.value = [];
  result.value = null;
  progress.value = 0;
  try {
    result.value = await invoke("pige360_deploy", { input: buildInput() });
    progress.value = 100;
  } catch (error) {
    errorMessage.value = String(error);
  } finally {
    running.value = false;
    clearSensitiveFields();
  }
}

onMounted(async () => {
  try {
    unlisten = await listen<AgentEvent>("pige360-deploy-event", (event) => {
      logs.value.push(event.payload);
      if (typeof event.payload.progress === "number") progress.value = event.payload.progress;
      if (event.payload.kind === "result") result.value = event.payload.data;
    });
    agentStatus.value = await invoke<AgentStatus>("pige360_embedded_agent_status");
  } catch {
    agentStatus.value = null;
  }
});

onBeforeUnmount(() => unlisten?.());
</script>

<template>
  <div class="page-content-scroll deployer-page">
    <AppPageTitleBar
      title="Implantação PIGE360"
      subtitle="Instale, atualize ou reverta qualquer distribuição homologada em Compose, Dockge, CloudPanel ou Portainer."
      eyebrow="Develop prerelease • Stable SemVer"
      icon="sync"
    >
      <template #actions>
        <button class="secondary" :disabled="loadingCatalog" @click="loadDistributions">{{ loadingCatalog ? "Consultando…" : "Consultar distribuições" }}</button>
        <button class="primary" :disabled="testing || running" @click="testServer">{{ testing ? "Testando…" : "Testar servidor" }}</button>
      </template>
    </AppPageTitleBar>

    <section class="channel-strip" aria-label="Política de canais">
      <div><strong>Develop</strong><span>revisão atual da branch</span><code>develop → SHA</code></div>
      <div><strong>Prerelease</strong><span>snapshot homologável publicado</span><code>develop-&lt;sha12&gt;</code></div>
      <div><strong>Stable</strong><span>produção</span><code>vX.Y.Z</code></div>
    </section>

    <div v-if="errorMessage" class="deploy-alert error"><strong>Operação bloqueada</strong><span>{{ errorMessage }}</span></div>

    <section v-if="distributions.length" class="card catalog-card">
      <div class="section-heading"><div><span class="eyebrow">CATÁLOGO</span><h2>Distribuições encontradas</h2></div><small>Selecione uma revisão para preencher o plano</small></div>
      <div class="distribution-list">
        <button v-for="item in distributions" :key="`${item.channel}-${item.commit}`" class="distribution-item" @click="selectDistribution(item)">
          <span class="channel-pill" :class="item.channel">{{ item.channel }}</span><strong>{{ item.version }}</strong><code>{{ item.commit.slice(0, 12) }}</code><small>{{ item.published_at ? new Date(item.published_at).toLocaleString("pt-BR") : "branch atual" }}</small>
        </button>
      </div>
    </section>

    <div class="deployment-grid">
      <div class="form-column">
        <section class="card">
          <div class="section-heading"><div><span class="eyebrow">01</span><h2>Servidor SSH</h2></div><span class="secure-label">chave validada</span></div>
          <div class="form-grid cols-3">
            <label class="field span-2"><span>Host / IP</span><input v-model.trim="connection.host" placeholder="203.0.113.10" autocomplete="off" /></label>
            <label class="field"><span>Porta</span><input v-model.number="connection.port" type="number" min="1" max="65535" /></label>
            <label class="field"><span>Usuário</span><input v-model.trim="connection.user" autocomplete="username" /></label>
            <label class="field"><span>Autenticação</span><select v-model="connection.auth_method"><option value="key">Chave SSH</option><option value="agent">SSH Agent</option></select></label>
            <label class="check-field"><input v-model="connection.sudo" type="checkbox" /><span>Usar <code>sudo -n</code></span></label>
            <label v-if="connection.auth_method === 'key'" class="field span-2"><span>Caminho da chave privada</span><input v-model.trim="connection.key_file" placeholder="~/.ssh/id_ed25519" autocomplete="off" /></label>
            <label class="field"><span>known_hosts alternativo</span><input v-model.trim="connection.known_hosts_file" placeholder="padrão do sistema" /></label>
          </div>
          <label class="check-field host-check"><input v-model="connection.accept_new_host_key" type="checkbox" /><span>Aceitar host novo somente após comparar o fingerprint abaixo com o servidor. Mudança de chave permanece bloqueada.</span></label>
          <div v-if="testResult" class="preflight-grid">
            <div><span>Sistema</span><strong>{{ testResult.server.os }} / {{ testResult.server.architecture }}</strong></div>
            <div><span>Docker</span><strong>{{ testResult.server.docker_available ? testResult.server.docker_version : "ausente" }}</strong></div>
            <div><span>Compose</span><strong>{{ testResult.server.compose_available ? testResult.server.compose_version : "ausente" }}</strong></div>
            <div><span>CloudPanel</span><strong>{{ testResult.server.cloudpanel_available ? "detectado" : "não detectado" }}</strong></div>
            <div><span>Disco /opt</span><strong>{{ formatBytes(testResult.server.disk_available_bytes) }}</strong></div>
            <div><span>Host key</span><strong>{{ testResult.known_host_status }}</strong></div>
            <div><span>Fingerprint</span><strong>{{ testResult.fingerprint_sha256 || "confira com ssh-keygen" }}</strong></div>
          </div>
        </section>

        <section class="card">
          <div class="section-heading"><div><span class="eyebrow">02</span><h2>Distribuição e target</h2></div><span class="environment-pill" :class="deployment.environment">{{ deployment.environment }}</span></div>
          <div class="environment-switch"><button :class="{ active: deployment.environment === 'develop' }" @click="deployment.environment = 'develop'">Homologação / develop</button><button :class="{ active: deployment.environment === 'production' }" @click="deployment.environment = 'production'">Produção</button></div>
          <div class="form-grid cols-2">
            <label class="field span-2"><span>Repositório PIGE360</span><input v-model.trim="deployment.repository" placeholder="owner/PIGE360" /></label>
            <label class="field"><span>Canal</span><select v-model="deployment.channel" :disabled="production"><option value="develop">develop</option><option value="prerelease">prerelease</option><option value="stable">stable</option></select></label>
            <label class="field"><span>Versão / referência</span><input v-model.trim="deployment.requested_version" :placeholder="immutableReference" /></label>
            <label class="field"><span>Plataforma</span><select v-model="deployment.platform"><option v-for="(label, key) in targetLabel" :key="key" :value="key">{{ label }}</option></select></label>
            <label class="field"><span>Ação</span><select v-model="deployment.action"><option value="plan">Plano — não grava</option><option value="prepare">Preparar — configura</option><option value="apply">Aplicar — instala/atualiza</option><option value="rollback">Rollback — tag imutável</option></select></label>
            <label class="field span-2"><span>Diretório da stack</span><input v-model.trim="deployment.directory" /></label>
            <label v-if="deployment.action === 'rollback'" class="field"><span>Tag de rollback</span><input v-model.trim="deployment.rollback_tag" placeholder="develop-abc123def456 ou 1.2.3" /></label>
            <label class="field"><span>Timeout readiness</span><input v-model.number="deployment.wait_seconds" type="number" min="1" max="3600" /></label>
          </div>
        </section>

        <section class="card">
          <div class="section-heading"><div><span class="eyebrow">03</span><h2>Domínio, ambiente e credenciais</h2></div><button class="ghost" @click="clearSensitiveFields">Limpar segredos</button></div>
          <div class="form-grid cols-2">
            <label class="field"><span>Domínio base</span><input v-model.trim="config.baseDomain" /></label>
            <label class="field"><span>E-mail ACME</span><input v-model.trim="config.acmeEmail" type="email" /></label>
            <label class="field"><span>Caminho de .env inicial</span><input v-model.trim="config.envInputPath" placeholder="opcional; apenas instalação nova" /></label>
            <label class="field"><span>Cloudflare Zone ID</span><input v-model.trim="config.cloudflareZoneId" placeholder="opcional" /></label>
            <label class="field"><span>Token GitHub</span><input v-model="deployment.github_token" type="password" autocomplete="new-password" placeholder="repo privado" /></label>
            <label class="field"><span>Token Cloudflare</span><input v-model="config.cloudflareToken" type="password" autocomplete="new-password" placeholder="opcional" /></label>
            <label class="field"><span>Túnel Cloudflare Control Plane</span><input v-model="config.cloudflareControlTunnelToken" type="password" autocomplete="new-password" placeholder="opcional" /></label>
            <label class="field"><span>Túnel Cloudflare tenants</span><input v-model="config.cloudflareTenantTunnelToken" type="password" autocomplete="new-password" placeholder="opcional" /></label>
            <label class="field"><span>Chave Connect API</span><input v-model="config.connectApiKey" type="password" autocomplete="new-password" placeholder="opcional" /></label>
            <label class="field"><span>Usuário GHCR</span><input v-model.trim="deployment.registry_user" placeholder="opcional" /></label>
            <label class="field"><span>Token GHCR read:packages</span><input v-model="deployment.registry_token" type="password" autocomplete="new-password" placeholder="opcional" /></label>
          </div>
        </section>
      </div>

      <aside class="status-column">
        <section class="card sticky-status">
          <div class="section-heading"><div><span class="eyebrow">EXECUÇÃO</span><h2>{{ targetLabel[deployment.platform] }}</h2></div><code>{{ immutableReference }}</code></div>
          <div class="progress-meta"><span>Progresso</span><strong>{{ progress }}%</strong></div><div class="progress"><div :style="{ width: `${progress}%` }"></div></div>
          <div class="agent-status"><span>Agente Linux embutido</span><code>{{ agentsReady ? "amd64/x86_64 ✓" : "aguardando build" }}</code></div>
          <div class="terminal" aria-live="polite">
            <p v-if="!logs.length">Os eventos auditáveis do agente Rust aparecerão aqui.</p>
            <div v-for="(entry, index) in logs" :key="`${index}-${entry.step}`" :class="`terminal-${entry.kind}`"><code>{{ entry.step }}</code><span>{{ entry.message }}</span></div>
          </div>
          <button class="run-button" :disabled="!canRun" @click="execute">{{ running ? "Executando…" : deployment.action === "apply" ? "IMPLANTAR" : deployment.action === "rollback" ? "REVERTER" : deployment.action === "prepare" ? "PREPARAR" : "VALIDAR PLANO" }}</button>
          <small class="operation-note">O VPS recebe um agente Rust temporário, valida a distribuição e remove o binário ao terminar. Dados persistentes não são empacotados nem enviados.</small>
          <details v-if="result" class="receipt"><summary>Recibo da operação</summary><pre>{{ JSON.stringify(result, null, 2) }}</pre></details>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.deployer-page{display:grid;gap:14px}.channel-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.channel-strip>div{display:grid;gap:3px;padding:13px;border:1px solid var(--border-color);border-radius:12px;background:var(--surface-bg)}.channel-strip strong{color:#006d77}.channel-strip span{color:var(--text-muted);font-size:12px}.channel-strip code{font-size:11px}.deployment-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(330px,390px);gap:14px;align-items:start}.form-column{display:grid;gap:14px}.card{padding:16px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.section-heading h2{margin:2px 0 0;font-size:17px}.section-heading small{color:var(--text-muted)}.eyebrow{font-size:10px;letter-spacing:.14em;font-weight:800;color:#006d77}.secure-label,.environment-pill,.channel-pill{font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:800;border-radius:999px;padding:6px 9px;background:#e5f5f3;color:#006d77}.environment-pill.production,.channel-pill.stable{background:#eaf1ff;color:#1d4ed8}.environment-pill.develop,.channel-pill.develop{background:#f2eafd;color:#6d28d9}.channel-pill.prerelease{background:#fff2cc;color:#92400e}.form-grid{display:grid;gap:12px}.cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.span-2{grid-column:span 2}.field{display:grid;gap:6px}.field>span,.check-field>span{font-size:12px;font-weight:650;color:var(--text-muted)}.field input,.field select{width:100%;min-height:40px;border:1px solid var(--border-color);border-radius:9px;padding:9px 10px;background:var(--surface-bg);color:var(--text-color)}.check-field{display:flex;align-items:center;gap:8px;min-height:40px}.check-field input{width:16px;height:16px}.host-check{margin-top:12px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px}.preflight-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.preflight-grid>div{display:grid;gap:3px;padding:9px;border-radius:8px;background:var(--surface-muted-bg)}.preflight-grid span{font-size:10px;color:var(--text-muted)}.preflight-grid strong{font-size:11px;overflow-wrap:anywhere}.environment-switch{display:flex;gap:5px;background:var(--surface-muted-bg);padding:4px;border-radius:10px;margin-bottom:12px}.environment-switch button{flex:1;border:0;border-radius:8px;padding:9px;background:transparent;color:var(--text-muted)}.environment-switch button.active{background:#fff;color:#006d77;box-shadow:0 1px 5px #0d1b2a1a}.ghost{border:0;border-radius:8px;padding:8px 10px;background:var(--surface-muted-bg);color:var(--text-color)}.sticky-status{position:sticky;top:calc(var(--topbar-height) + 12px)}.progress-meta{display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted)}.progress{height:8px;border-radius:99px;overflow:hidden;background:#e5e7eb;margin:7px 0 12px}.progress>div{height:100%;background:linear-gradient(90deg,#006d77,#f59e0b);transition:width .2s}.agent-status{display:flex;justify-content:space-between;gap:8px;padding:10px;border-radius:9px;background:var(--surface-muted-bg);font-size:11px}.terminal{height:330px;overflow:auto;background:#0d1b2a;color:#cbd5e1;border-radius:10px;padding:10px;margin:12px 0;font-size:11px}.terminal p{color:#718096}.terminal>div{display:grid;grid-template-columns:84px minmax(0,1fr);gap:7px;padding:5px 2px;border-bottom:1px solid #ffffff0d}.terminal>div code{color:#67e8f9;overflow:hidden;text-overflow:ellipsis}.terminal-warning span{color:#fde68a}.terminal-error span{color:#fca5a5}.terminal-result span{color:#86efac}.run-button{width:100%;min-height:48px;border:0;border-radius:10px;background:#006d77;color:#fff;font-weight:850;letter-spacing:.05em}.run-button:disabled{opacity:.5}.operation-note{display:block;text-align:center;color:var(--text-muted);line-height:1.45;margin-top:9px}.receipt{margin-top:12px}.receipt pre{max-height:230px;overflow:auto;white-space:pre-wrap;background:var(--surface-muted-bg);padding:9px;border-radius:8px;font-size:10px}.deploy-alert{display:grid;gap:3px;padding:11px 13px;border-radius:10px}.deploy-alert.error{background:#fff0ef;color:#8e342c;border:1px solid #f1c8c4}.distribution-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}.distribution-item{display:grid;grid-template-columns:auto 1fr auto;gap:7px;align-items:center;text-align:left;border:1px solid var(--border-color);border-radius:10px;padding:10px;background:var(--surface-bg);color:var(--text-color)}.distribution-item small{grid-column:2/4;color:var(--text-muted)}@media(max-width:1100px){.deployment-grid{grid-template-columns:1fr}.sticky-status{position:static}.channel-strip{grid-template-columns:1fr}.cols-3{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:720px){.cols-2,.cols-3,.preflight-grid{grid-template-columns:1fr}.span-2{grid-column:auto}}
</style>
