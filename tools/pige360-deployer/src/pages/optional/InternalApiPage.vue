<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import BasePage from "../../components/base/BasePage.vue";
import BaseSectionCard from "../../components/base/BaseSectionCard.vue";
import AppSwitch from "../../components/AppSwitch.vue";
import {
  getInternalApiStatus,
  restartInternalApi,
  saveRuntimeSettings,
  startInternalApi,
  stopInternalApi,
  testInternalApi,
  testInternalApiPort,
  type RuntimeSettings,
} from "../../services/crud";

const loading = ref(false);
const message = ref("");
const error = ref("");
const status = ref<Record<string, any>>({});
const portResult = ref<Record<string, unknown> | null>(null);
const apiResult = ref<Record<string, unknown> | null>(null);

const defaults: RuntimeSettings = {
  internal_api_host: "127.0.0.1",
  internal_api_port: 61001,
  internal_api_base_url: "http://127.0.0.1:61001",
  internal_api_docs_url: "http://127.0.0.1:61001/docs",
  internal_api_auto_start: false,
  internal_api_restart_on_config_change: true,
  internal_api_require_token: false,
  internal_api_token: "",
  internal_api_allow_public_network: false,
  internal_api_cors_enabled: false,
  internal_api_token_header: "X-App-Token",
  internal_api_docs_public_local: true,
  internal_api_open_scalar_after_start: false,
  internal_api_timeout_ms: 8000,
  internal_api_log_mode: "normal",
  internal_api_docs_enabled: true,
  internal_api_docs_path: "/docs",
  local_web_enabled: true,
  local_web_auto_start: true,
  local_web_host: "0.0.0.0",
  local_web_port: 61002,
  auxiliary_host: "0.0.0.0",
  auxiliary_port: 61003,
  bridge_core_host: "0.0.0.0",
  bridge_core_port: 61004,
  webhook_enabled: false,
  webhook_auto_start: false,
  webhook_host: "0.0.0.0",
  webhook_port: 61003,
  webhook_base_path: "/webhooks",
  webhook_token_required: true,
  webhook_token_header: "X-Webhook-Token",
  webhook_token: "",
  webhook_allow_lan: true,
  webhook_allow_external: false,
  websocket_enabled: false,
  websocket_auto_start: false,
  websocket_host: "0.0.0.0",
  websocket_port: 61004,
  websocket_path: "/ws",
  websocket_token_required: true,
  websocket_token_query: "token",
  websocket_token_header: "X-WebSocket-Token",
  websocket_token: "",
  websocket_allow_lan: true,
  websocket_allow_external: false,
  websocket_heartbeat_seconds: 30,
  tray_enabled: true,
  minimize_to_tray: true,
  close_to_tray: false,
  start_with_windows: false,
  services_auto_start: false,
  app_service_name: "Pige360DeployerServer",
};

const form = reactive<RuntimeSettings>({ ...defaults });

function browserHostForPublishedService(): string {
  if (typeof window === "undefined") return "127.0.0.1";
  const host = window.location.hostname || "127.0.0.1";
  return host === "localhost" ? "127.0.0.1" : host;
}

function normalizeClientHost(host: string): string {
  const trimmed = String(host || "").trim();
  if (["0.0.0.0", "::", "[::]", "", "127.0.0.1", "localhost"].includes(trimmed)) {
    return browserHostForPublishedService();
  }
  return trimmed;
}

function normalizeClientUrl(url: string): string {
  const raw = String(url || "").trim();
  if (!raw) return `http://${browserHostForPublishedService()}:61001`;
  try {
    const parsed = new URL(raw, typeof window !== "undefined" ? window.location.href : "http://127.0.0.1");
    if (["0.0.0.0", "::", "[::]", "127.0.0.1", "localhost", ""].includes(parsed.hostname)) {
      parsed.hostname = browserHostForPublishedService();
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return raw
      .replace("http://0.0.0.0:", `http://${browserHostForPublishedService()}:`)
      .replace("https://0.0.0.0:", `https://${browserHostForPublishedService()}:`)
      .replace("http://127.0.0.1:", `http://${browserHostForPublishedService()}:`)
      .replace("http://localhost:", `http://${browserHostForPublishedService()}:`);
  }
}

const baseUrl = computed(() => normalizeClientUrl(form.internal_api_base_url || `http://${normalizeClientHost(form.internal_api_host)}:${form.internal_api_port}`));
const docsUrl = computed(() => normalizeClientUrl(form.internal_api_docs_url || `${baseUrl.value}${form.internal_api_docs_path || "/docs"}`));
const recentLogs = computed(() => Array.isArray(status.value.recent_logs) ? status.value.recent_logs : []);

function syncDerivedUrls() {
  form.internal_api_base_url = `http://${normalizeClientHost(form.internal_api_host)}:${Number(form.internal_api_port || 61001)}`;
  const docsPath = form.internal_api_docs_path?.startsWith("/") ? form.internal_api_docs_path : `/${form.internal_api_docs_path || "docs"}`;
  form.internal_api_docs_path = docsPath;
  form.internal_api_docs_url = `${form.internal_api_base_url}${docsPath}`;
}

function applyStatus(payload: Record<string, any>) {
  status.value = payload;
  if (payload.settings) Object.assign(form, payload.settings);
  syncDerivedUrls();
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    applyStatus(await getInternalApiStatus());
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao consultar API interna.";
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    syncDerivedUrls();
    const saved = await saveRuntimeSettings({ ...form });
    if (saved.settings) Object.assign(form, saved.settings);
    message.value = saved.restarted
      ? "Configuração salva e API reiniciada com sucesso."
      : "Configuração salva no banco local e no .env.";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Configuração inválida ou falha ao salvar.";
  } finally {
    loading.value = false;
  }
}

async function run(action: "start" | "stop" | "restart") {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    syncDerivedUrls();
    if (action === "start") status.value = await startInternalApi(form.internal_api_host, Number(form.internal_api_port));
    if (action === "stop") status.value = await stopInternalApi();
    if (action === "restart") status.value = await restartInternalApi(form.internal_api_host, Number(form.internal_api_port));
    message.value = action === "stop" ? "API parada." : "API iniciada/atualizada com sucesso.";
    await load();
    if (action !== "stop" && form.internal_api_open_scalar_after_start && form.internal_api_docs_enabled) openScalar();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao executar operação da API interna.";
  } finally {
    loading.value = false;
  }
}

async function testPort() {
  portResult.value = await testInternalApiPort(form.internal_api_host, Number(form.internal_api_port));
}

async function testApi() {
  apiResult.value = await testInternalApi(baseUrl.value, Number(form.internal_api_timeout_ms));
}

function openScalar() {
  window.location.hash = "#/documentacao/scalar";
}

function openExternal() {
  window.open(docsUrl.value, "_blank", "noopener,noreferrer");
}

function restoreDefaults() {
  Object.assign(form, defaults);
  syncDerivedUrls();
  message.value = "Padrões restaurados no formulário. Clique em Salvar configurações para persistir.";
}

onMounted(load);
</script>

<template>
  <BasePage title="API Interna" subtitle="Configuração persistente, ciclo de vida, segurança local e diagnóstico da API interna.">
    <template #actions>
      <button class="secondary" :disabled="loading" @click="load">Atualizar</button>
      <button class="primary" type="button" @click="openScalar">Abrir Scalar</button>
      <button class="secondary" type="button" @click="openExternal">Abrir no navegador</button>
    </template>

    <div v-if="message" class="alert success">{{ message }}</div>
    <div v-if="error" class="alert error">{{ error }}</div>
    <div v-for="warning in status.warnings || []" :key="warning" class="alert warning">{{ warning }}</div>

    <div class="grid columns-4 mobile-columns-1">
      <div class="kpi"><strong>Status</strong><span>{{ status.running ? 'Rodando' : 'Parada' }}</span></div>
      <div class="kpi"><strong>Host/porta</strong><span>{{ form.internal_api_host }}:{{ form.internal_api_port }}</span></div>
      <div class="kpi"><strong>Token</strong><span>{{ form.internal_api_require_token ? 'Obrigatório' : 'Desativado' }}</span></div>
      <div class="kpi"><strong>Auto start</strong><span>{{ form.internal_api_auto_start ? 'Ativo' : 'Inativo' }}</span></div>
    </div>

    <BaseSectionCard title="Controles" subtitle="No Tauri/headless estes botões controlam o servidor local real; no navegador dependem do provider disponível.">
      <div class="runtime-actions-grid">
        <button class="primary" :disabled="loading" @click="run('start')">Iniciar API</button>
        <button class="secondary" :disabled="loading" @click="run('restart')">Reiniciar API</button>
        <button class="danger" :disabled="loading" @click="run('stop')">Parar API</button>
        <button class="secondary" :disabled="loading" @click="testPort">Testar porta</button>
        <button class="secondary" :disabled="loading" @click="testApi">Testar API</button>
        <button class="primary" type="button" @click="openScalar">Abrir Scalar</button>
      </div>
      <div class="info-grid compact-info">
        <div class="info-item"><strong>URL base</strong><code>{{ baseUrl }}</code></div>
        <div class="info-item"><strong>URL Scalar</strong><code>{{ docsUrl }}</code></div>
        <div v-if="portResult" class="info-item"><strong>Teste de porta</strong><code>{{ portResult }}</code></div>
        <div v-if="apiResult" class="info-item"><strong>Teste da API</strong><code>{{ apiResult }}</code></div>
      </div>
    </BaseSectionCard>

    <BaseSectionCard title="Configuração persistente da API" subtitle="Prioridade: interface/banco local > .env > valores padrão do template.">
      <div class="grid columns-4 mobile-columns-1">
        <label class="field"><span>Host da API</span><input v-model="form.internal_api_host" type="text" @change="syncDerivedUrls" /></label>
        <label class="field"><span>Porta da API</span><input v-model.number="form.internal_api_port" type="number" min="1" max="65535" @change="syncDerivedUrls" /></label>
        <label class="field"><span>URL base</span><input v-model="form.internal_api_base_url" type="text" /></label>
        <label class="field"><span>URL da documentação Scalar</span><input v-model="form.internal_api_docs_url" type="text" /></label>
        <label class="field"><span>Caminho docs</span><input v-model="form.internal_api_docs_path" type="text" @change="syncDerivedUrls" /></label>
        <label class="field"><span>Timeout inicialização (ms)</span><input v-model.number="form.internal_api_timeout_ms" type="number" min="1000" step="500" /></label>
        <label class="field"><span>Modo de log</span><select v-model="form.internal_api_log_mode"><option value="normal">normal</option><option value="verbose">verbose</option><option value="silent">silent</option></select></label>
        <label class="field"><span>Token da API</span><input v-model="form.internal_api_token" type="password" autocomplete="off" placeholder="Defina apenas quando token obrigatório" /></label>
      </div>
      <div class="switch-grid">
        <AppSwitch v-model="form.internal_api_auto_start" label="Iniciar API automaticamente" />
        <AppSwitch v-model="form.internal_api_restart_on_config_change" label="Reiniciar ao mudar configuração" />
        <AppSwitch v-model="form.internal_api_require_token" label="Exigir token de autenticação" />
        <AppSwitch v-model="form.internal_api_docs_public_local" label="Permitir Scalar sem token local" />
        <AppSwitch v-model="form.internal_api_open_scalar_after_start" label="Abrir Scalar após iniciar" />
        <AppSwitch v-model="form.internal_api_docs_enabled" label="Scalar habilitado" />
      </div>
      <div class="actions align-end">
        <button class="primary" :disabled="loading" @click="saveSettings">Salvar configurações</button>
        <button class="secondary" type="button" @click="restoreDefaults">Restaurar padrão</button>
      </div>
    </BaseSectionCard>

    <BaseSectionCard title="Logs recentes da API" subtitle="Eventos gravados no banco local e no arquivo de logs da aplicação.">
      <div v-if="!recentLogs.length" class="empty-state compact">Nenhum log recente da API interna.</div>
      <div v-else class="logs-list">
        <div v-for="(log, index) in recentLogs" :key="index" class="info-item">
          <strong>{{ log.created_at }} · {{ log.level }}</strong>
          <code>{{ log.message }} {{ log.details_json || '' }}</code>
        </div>
      </div>
    </BaseSectionCard>
  </BasePage>
</template>
