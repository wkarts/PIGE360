<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  getAppServiceStatus,
  getSystemInfo,
  loadRuntimeSettings,
  saveRuntimeSettings,
  setStartupWithWindows,
  setSystemDataDir,
  type RuntimeSettings,
} from "../services/crud";
import { appFeatures, databaseConfig, internalApiConfig, projectConfig, sidebarConfig } from "../config/projectConfig";
import { storageKey } from "../config/appBranding";
import BasePage from "../components/base/BasePage.vue";
import BaseSectionCard from "../components/base/BaseSectionCard.vue";
import AppSwitch from "../components/AppSwitch.vue";

type ServiceKey = "internal_api" | "local_web" | "auxiliary" | "bridge_core";

type PortInfo = {
  key?: unknown;
  label?: unknown;
  host?: unknown;
  configured_port?: unknown;
  effective_port?: unknown;
  default_port?: unknown;
  available?: unknown;
  description?: unknown;
};

const WORKSPACE_TABS_ENABLED_KEY = storageKey("workspace-tabs-enabled");

const info = ref<Record<string, unknown>>({});
const serviceStatus = ref<Record<string, unknown>>({});
const ports = ref<PortInfo[]>([]);
const warnings = ref<string[]>([]);
const envPath = ref("");
const form = reactive({ dataDir: "" });
const runtimeForm = reactive<RuntimeSettings>({
  internal_api_host: "127.0.0.1",
  internal_api_port: 61001,
  internal_api_base_url: "http://127.0.0.1:61001",
  internal_api_docs_url: "http://127.0.0.1:61001/docs",
  internal_api_auto_start: true,
  internal_api_restart_on_config_change: true,
  internal_api_require_token: false,
  internal_api_allow_public_network: false,
  internal_api_cors_enabled: false,
  internal_api_token_header: "X-App-Token",
  internal_api_token: "",
  internal_api_docs_public_local: true,
  internal_api_open_scalar_after_start: false,
  internal_api_timeout_ms: 8000,
  internal_api_log_mode: "normal",
  internal_api_docs_enabled: true,
  internal_api_docs_path: "/docs",
  local_web_enabled: true,
  local_web_auto_start: true,
  local_web_host: "127.0.0.1",
  local_web_port: 61002,
  auxiliary_host: "127.0.0.1",
  auxiliary_port: 61003,
  bridge_core_host: "127.0.0.1",
  bridge_core_port: 61004,
  webhook_enabled: false,
  webhook_auto_start: false,
  webhook_host: "127.0.0.1",
  webhook_port: 61003,
  webhook_base_path: "/webhooks",
  webhook_token_required: true,
  webhook_token_header: "X-Webhook-Token",
  webhook_token: "",
  webhook_allow_lan: false,
  webhook_allow_external: false,
  websocket_enabled: false,
  websocket_auto_start: false,
  websocket_host: "127.0.0.1",
  websocket_port: 61004,
  websocket_path: "/ws",
  websocket_token_required: true,
  websocket_token_query: "token",
  websocket_token_header: "X-WebSocket-Token",
  websocket_token: "",
  websocket_allow_lan: false,
  websocket_allow_external: false,
  websocket_heartbeat_seconds: 30,
  tray_enabled: true,
  minimize_to_tray: true,
  close_to_tray: false,
  start_with_windows: false,
  services_auto_start: false,
  app_service_name: "Pige360DeployerServer",
});
const loading = ref(false);
const message = ref("");
const error = ref("");
const workspaceTabsEnabled = ref(true);

function applyRuntime(settings: RuntimeSettings) {
  Object.assign(runtimeForm, settings);
}

function readWorkspaceTabsPreference(): boolean {
  const stored = window.localStorage.getItem(WORKSPACE_TABS_ENABLED_KEY);
  if (stored === "enabled") return true;
  if (stored === "disabled") return false;
  return true;
}

function persistWorkspaceTabsPreference() {
  window.localStorage.setItem(WORKSPACE_TABS_ENABLED_KEY, workspaceTabsEnabled.value ? "enabled" : "disabled");
  window.dispatchEvent(new CustomEvent("template:workspace-tabs-preference-changed", { detail: { enabled: workspaceTabsEnabled.value } }));
}

function isNetworkHost(host: string): boolean {
  const normalized = host.trim().toLowerCase();
  return normalized === "0.0.0.0" || normalized === "::" || normalized === "[::]";
}

function clientHost(host: string): string {
  return isNetworkHost(host) || host.trim() === "" ? "127.0.0.1" : host.trim();
}

function setNetworkAccess(service: "api" | "web" | "webhook" | "websocket", enabled: boolean) {
  const host = enabled ? "0.0.0.0" : "127.0.0.1";
  if (service === "api") {
    runtimeForm.internal_api_host = host;
    runtimeForm.internal_api_allow_public_network = enabled;
    if (enabled) runtimeForm.internal_api_cors_enabled = true;
    refreshInternalApiUrls();
  }
  if (service === "web") {
    runtimeForm.local_web_host = host;
  }
  if (service === "webhook") {
    runtimeForm.webhook_host = host;
    runtimeForm.auxiliary_host = host;
    runtimeForm.webhook_allow_lan = enabled;
  }
  if (service === "websocket") {
    runtimeForm.websocket_host = host;
    runtimeForm.bridge_core_host = host;
    runtimeForm.websocket_allow_lan = enabled;
  }
}

function refreshInternalApiUrls() {
  const base = `http://${clientHost(runtimeForm.internal_api_host)}:${runtimeForm.internal_api_port}`;
  runtimeForm.internal_api_base_url = base;
  runtimeForm.internal_api_docs_url = `${base}${runtimeForm.internal_api_docs_path || "/docs"}`;
}

function normalizeBeforeSave() {
  runtimeForm.auxiliary_host = runtimeForm.webhook_host;
  runtimeForm.auxiliary_port = runtimeForm.webhook_port;
  runtimeForm.bridge_core_host = runtimeForm.websocket_host;
  runtimeForm.bridge_core_port = runtimeForm.websocket_port;
  refreshInternalApiUrls();
}

function portByKey(key: ServiceKey): PortInfo | undefined {
  return ports.value.find((item) => String(item.key || "") === key);
}

function portNumber(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function serviceAddress(key: ServiceKey): string {
  if (key === "internal_api") return `${clientHost(runtimeForm.internal_api_host)}:${runtimeForm.internal_api_port}`;
  if (key === "local_web") return `${clientHost(runtimeForm.local_web_host)}:${runtimeForm.local_web_port}`;
  if (key === "auxiliary") return `${clientHost(runtimeForm.webhook_host)}:${runtimeForm.webhook_port}`;
  return `${clientHost(runtimeForm.websocket_host)}:${runtimeForm.websocket_port}`;
}

function serviceBind(key: ServiceKey): string {
  if (key === "internal_api") return `${runtimeForm.internal_api_host}:${runtimeForm.internal_api_port}`;
  if (key === "local_web") return `${runtimeForm.local_web_host}:${runtimeForm.local_web_port}`;
  if (key === "auxiliary") return `${runtimeForm.webhook_host}:${runtimeForm.webhook_port}`;
  return `${runtimeForm.websocket_host}:${runtimeForm.websocket_port}`;
}

function servicePortStatus(key: ServiceKey, defaultPort: number): string {
  const item = portByKey(key);
  const port = portNumber(item?.effective_port ?? item?.configured_port, defaultPort);
  const host = String(item?.host || serviceBind(key).split(":")[0]);
  const available = item?.available !== false;
  return `${host}:${port} · padrão ${String(item?.default_port || defaultPort)} · ${available ? "livre" : "em uso"}`;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    workspaceTabsEnabled.value = readWorkspaceTabsPreference();
    info.value = await getSystemInfo();
    form.dataDir = String(info.value.data_dir || "");
    const runtime = await loadRuntimeSettings();
    applyRuntime(runtime.settings);
    ports.value = runtime.ports || [];
    warnings.value = runtime.warnings || [];
    envPath.value = runtime.env_path || "";
    try { serviceStatus.value = await getAppServiceStatus(); } catch { serviceStatus.value = {}; }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar informações do sistema.";
  } finally {
    loading.value = false;
  }
}

async function persist() {
  message.value = "";
  error.value = "";
  try {
    info.value = await setSystemDataDir(form.dataDir);
    message.value = "Diretório de parâmetros/dados atualizado. Reinicie a aplicação se necessário.";
    await load();
  } catch (err) { error.value = err instanceof Error ? err.message : "Falha ao atualizar diretório de dados."; }
}

async function persistRuntime() {
  loading.value = true; message.value = ""; error.value = "";
  try {
    persistWorkspaceTabsPreference();
    normalizeBeforeSave();
    const saved = await saveRuntimeSettings({ ...runtimeForm });
    applyRuntime(saved.settings); ports.value = saved.ports || []; warnings.value = saved.warnings || []; envPath.value = saved.env_path || envPath.value;
    if (runtimeForm.start_with_windows) await setStartupWithWindows(true);
    message.value = "Configurações salvas. Serviços ativos serão preservados ou reiniciados de forma controlada quando aplicável.";
  } catch (err) { error.value = err instanceof Error ? err.message : "Falha ao salvar configurações runtime."; }
  finally { loading.value = false; }
}

onMounted(load);
</script>

<template>
  <BasePage title="Sistema e parâmetros" subtitle="Configuração organizada dos serviços, portas, acesso de rede, diretórios e execução.">
    <template #actions>
      <button class="secondary" :disabled="loading" @click="load">Recarregar</button>
      <button class="primary" :disabled="loading" @click="persistRuntime">Salvar runtime/.env</button>
    </template>

    <div v-if="message" class="alert success">{{ message }}</div>
    <div v-if="error" class="alert error">{{ error }}</div>
    <div v-for="warning in warnings" :key="warning" class="alert warning">{{ warning }}</div>

    <section class="settings-grid overview-grid">
      <BaseSectionCard title="Aplicação">
        <div class="info-grid compact-info">
          <div class="info-item"><strong>Produto</strong><code>{{ info.product_name || projectConfig.app.name }}</code></div>
          <div class="info-item"><strong>Versão</strong><code>{{ info.version || projectConfig.app.version }}</code></div>
          <div class="info-item"><strong>Build</strong><code>{{ info.build_hash || '-' }}</code></div>
          <div class="info-item"><strong>Identificador</strong><code>{{ projectConfig.app.identifier }}</code></div>
        </div>
      </BaseSectionCard>

      <BaseSectionCard title="Diretórios">
        <div class="info-grid compact-info">
          <div class="info-item"><strong>Banco local</strong><code>{{ info.db_path || '-' }}</code></div>
          <div class="info-item"><strong>Diretório de dados</strong><code>{{ info.data_dir || '-' }}</code></div>
          <div class="info-item"><strong>.env ativo</strong><code>{{ envPath || '-' }}</code></div>
        </div>
      </BaseSectionCard>
    </section>

    <BaseSectionCard title="Diretório de dados/parâmetros" subtitle="Use um diretório próprio no app derivado para não gravar dados em pige360_deployer.">
      <div class="inline-form-row">
        <label class="field data-dir-field"><span>Diretório de dados/parâmetros</span><input v-model="form.dataDir" type="text" placeholder="C:\\MinhaAplicacao\\dados" /></label>
        <button class="primary" :disabled="loading" @click="persist">Salvar diretório</button>
      </div>
    </BaseSectionCard>

    <BaseSectionCard title="Serviços publicados" subtitle="Use os botões Local/Rede para definir o bind. Não é necessário digitar 127.0.0.1 ou 0.0.0.0.">
      <div class="service-card-grid">
        <article class="service-card">
          <div class="service-card-header">
            <div><strong>API interna</strong><small>Docs, Scalar e comandos HTTP internos.</small></div>
            <span class="service-pill">{{ servicePortStatus('internal_api', 61001) }}</span>
          </div>
          <div class="service-body-grid">
            <label class="field"><span>Porta</span><input v-model.number="runtimeForm.internal_api_port" type="number" min="1" max="65535" @change="refreshInternalApiUrls" /></label>
            <div class="access-box"><span>Nível de acesso</span><div class="segmented"><button type="button" :class="{ active: !isNetworkHost(runtimeForm.internal_api_host) }" @click="setNetworkAccess('api', false)">Local</button><button type="button" :class="{ active: isNetworkHost(runtimeForm.internal_api_host) }" @click="setNetworkAccess('api', true)">Rede local/remoto</button></div></div>
          </div>
          <div class="switch-grid compact-switches"><AppSwitch v-model="runtimeForm.internal_api_auto_start" label="Iniciar com a aplicação" /><AppSwitch v-model="runtimeForm.internal_api_require_token" label="Exigir token" /><AppSwitch v-model="runtimeForm.internal_api_cors_enabled" label="CORS" /></div>
          <code class="bind-preview">Bind: {{ serviceBind('internal_api') }} · URL local: http://{{ serviceAddress('internal_api') }}</code>
        </article>

        <article class="service-card">
          <div class="service-card-header">
            <div><strong>Webport/Proxy</strong><small>Publica a mesma aplicação Tauri no navegador.</small></div>
            <span class="service-pill">{{ servicePortStatus('local_web', 61002) }}</span>
          </div>
          <div class="service-body-grid">
            <label class="field"><span>Porta</span><input v-model.number="runtimeForm.local_web_port" type="number" min="1" max="65535" /></label>
            <div class="access-box"><span>Nível de acesso</span><div class="segmented"><button type="button" :class="{ active: !isNetworkHost(runtimeForm.local_web_host) }" @click="setNetworkAccess('web', false)">Local</button><button type="button" :class="{ active: isNetworkHost(runtimeForm.local_web_host) }" @click="setNetworkAccess('web', true)">Rede local/remoto</button></div></div>
          </div>
          <div class="switch-grid compact-switches"><AppSwitch v-model="runtimeForm.local_web_enabled" label="Habilitar" /><AppSwitch v-model="runtimeForm.local_web_auto_start" label="Iniciar com a aplicação" /></div>
          <code class="bind-preview">Bind: {{ serviceBind('local_web') }} · URL local: http://{{ serviceAddress('local_web') }}</code>
        </article>

        <article class="service-card">
          <div class="service-card-header">
            <div><strong>Webhook Service</strong><small>Recepção HTTP de eventos externos.</small></div>
            <span class="service-pill">{{ servicePortStatus('auxiliary', 61003) }}</span>
          </div>
          <div class="service-body-grid">
            <label class="field"><span>Porta</span><input v-model.number="runtimeForm.webhook_port" type="number" min="1" max="65535" /></label>
            <div class="access-box"><span>Nível de acesso</span><div class="segmented"><button type="button" :class="{ active: !isNetworkHost(runtimeForm.webhook_host) }" @click="setNetworkAccess('webhook', false)">Local</button><button type="button" :class="{ active: isNetworkHost(runtimeForm.webhook_host) }" @click="setNetworkAccess('webhook', true)">Rede local/remoto</button></div></div>
          </div>
          <div class="switch-grid compact-switches"><AppSwitch v-model="runtimeForm.webhook_enabled" label="Habilitar" /><AppSwitch v-model="runtimeForm.webhook_auto_start" label="Iniciar automaticamente" /><AppSwitch v-model="runtimeForm.webhook_token_required" label="Exigir token" /></div>
          <code class="bind-preview">Bind: {{ serviceBind('auxiliary') }} · URL local: http://{{ serviceAddress('auxiliary') }}{{ runtimeForm.webhook_base_path }}</code>
        </article>

        <article class="service-card">
          <div class="service-card-header">
            <div><strong>WebSocket Service</strong><small>Canal de eventos em tempo real.</small></div>
            <span class="service-pill">{{ servicePortStatus('bridge_core', 61004) }}</span>
          </div>
          <div class="service-body-grid">
            <label class="field"><span>Porta</span><input v-model.number="runtimeForm.websocket_port" type="number" min="1" max="65535" /></label>
            <div class="access-box"><span>Nível de acesso</span><div class="segmented"><button type="button" :class="{ active: !isNetworkHost(runtimeForm.websocket_host) }" @click="setNetworkAccess('websocket', false)">Local</button><button type="button" :class="{ active: isNetworkHost(runtimeForm.websocket_host) }" @click="setNetworkAccess('websocket', true)">Rede local/remoto</button></div></div>
          </div>
          <div class="switch-grid compact-switches"><AppSwitch v-model="runtimeForm.websocket_enabled" label="Habilitar" /><AppSwitch v-model="runtimeForm.websocket_auto_start" label="Iniciar automaticamente" /><AppSwitch v-model="runtimeForm.websocket_token_required" label="Exigir token" /></div>
          <code class="bind-preview">Bind: {{ serviceBind('bridge_core') }} · URL local: http://{{ serviceAddress('bridge_core') }}{{ runtimeForm.websocket_path }}</code>
        </article>
      </div>
    </BaseSectionCard>

    <BaseSectionCard title="API, Scalar e segurança" subtitle="URLs de consumo usam 127.0.0.1 automaticamente quando o bind é 0.0.0.0; 0.0.0.0 é apenas endereço de escuta.">
      <div class="grid columns-3 mobile-columns-1">
        <label class="field"><span>URL base API</span><input v-model="runtimeForm.internal_api_base_url" type="text" /></label>
        <label class="field"><span>URL Scalar</span><input v-model="runtimeForm.internal_api_docs_url" type="text" /></label>
        <label class="field"><span>Path docs</span><input v-model="runtimeForm.internal_api_docs_path" type="text" @change="refreshInternalApiUrls" /></label>
        <label class="field"><span>Header do token</span><input v-model="runtimeForm.internal_api_token_header" type="text" /></label>
        <label class="field"><span>Token API</span><input v-model="runtimeForm.internal_api_token" type="text" placeholder="definido por ambiente/operador" /></label>
        <label class="field"><span>Timeout ms</span><input v-model.number="runtimeForm.internal_api_timeout_ms" type="number" min="1000" /></label>
      </div>
      <div class="switch-grid">
        <AppSwitch v-model="runtimeForm.internal_api_restart_on_config_change" label="Reiniciar API ao salvar" />
        <AppSwitch v-model="runtimeForm.internal_api_docs_public_local" label="Scalar público local" />
        <AppSwitch v-model="runtimeForm.internal_api_docs_enabled" label="Documentação Scalar habilitada" />
        <AppSwitch v-model="runtimeForm.internal_api_open_scalar_after_start" label="Abrir Scalar após iniciar" />
      </div>
    </BaseSectionCard>

    <BaseSectionCard title="Janela, tray e inicialização" subtitle="Comportamento visual e inicialização nativa da aplicação.">
      <div class="grid columns-3 mobile-columns-1">
        <label class="field"><span>Nome do serviço</span><input v-model="runtimeForm.app_service_name" type="text" /></label>
        <div class="info-item"><strong>Status serviço</strong><code>{{ serviceStatus.status === 'managed-by-installer' ? 'gerenciado pelo instalador/helper nativo' : (serviceStatus.status || serviceStatus.message || serviceStatus.action || 'não consultado') }}</code></div>
      </div>
      <div class="switch-grid">
        <AppSwitch v-model="runtimeForm.tray_enabled" label="Habilitar tray icon" />
        <AppSwitch v-model="runtimeForm.minimize_to_tray" label="Minimizar para bandeja" />
        <AppSwitch v-model="runtimeForm.close_to_tray" label="Fechar para bandeja" />
        <AppSwitch v-model="runtimeForm.start_with_windows" label="Iniciar com Windows" />
        <AppSwitch v-model="runtimeForm.services_auto_start" label="Iniciar serviços internos automaticamente" />
        <AppSwitch v-model="workspaceTabsEnabled" label="Abrir páginas em abas/guias" />
      </div>
    </BaseSectionCard>

    <section class="settings-grid overview-grid">
      <BaseSectionCard title="Módulos pré-ativados"><div class="switch-grid compact-switches"><AppSwitch v-for="(enabled, key) in appFeatures" :key="key" :model-value="enabled" :label="String(key)" disabled /></div></BaseSectionCard>
      <BaseSectionCard title="Execução"><div class="info-grid compact-info"><div class="info-item"><strong>Banco</strong><code>{{ databaseConfig.driver }}</code></div><div class="info-item"><strong>API</strong><code>{{ internalApiConfig.enabled ? serviceAddress('internal_api') : 'desativada' }}</code></div><div class="info-item"><strong>Sidebar</strong><code>{{ sidebarConfig.menuBehavior }}</code></div><div class="info-item"><strong>Webport</strong><code>{{ runtimeForm.local_web_enabled ? serviceAddress('local_web') : 'desativado' }}</code></div></div></BaseSectionCard>
    </section>
  </BasePage>
</template>

<style scoped>
.settings-grid { display: grid; gap: 16px; }
.overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.inline-form-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: end; }
.data-dir-field { min-width: 0; }
.service-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.service-card { border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; padding: 16px; display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.service-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.service-card-header strong { display: block; color: #0f172a; font-size: 15px; }
.service-card-header small { display: block; color: #64748b; margin-top: 3px; line-height: 1.35; }
.service-pill { border-radius: 999px; background: #f1f5f9; color: #334155; font-size: 11px; padding: 6px 10px; white-space: nowrap; }
.service-body-grid { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 12px; align-items: end; }
.access-box > span { display: block; color: #475569; font-size: 12px; margin-bottom: 6px; font-weight: 700; }
.segmented { display: inline-flex; border: 1px solid #cbd5e1; border-radius: 12px; overflow: hidden; background: #f8fafc; }
.segmented button { border: 0; background: transparent; color: #475569; padding: 9px 12px; font-weight: 700; cursor: pointer; }
.segmented button + button { border-left: 1px solid #cbd5e1; }
.segmented button.active { background: #2563eb; color: #fff; }
.bind-preview { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 9px 10px; color: #334155; }
.compact-switches { gap: 10px 14px; }
@media (max-width: 980px) { .overview-grid, .service-card-grid { grid-template-columns: 1fr; } .service-body-grid, .inline-form-row { grid-template-columns: 1fr; } .service-card-header { flex-direction: column; } .service-pill { white-space: normal; } }

:global(.workspace-content-area .base-page.page-content-scroll) {
  height: auto;
  min-height: 100%;
  overflow: visible;
  padding-bottom: 72px;
}
:global(.workspace-content-area .base-page-body) {
  padding-bottom: 56px;
}
:global(.workspace-content-area) {
  overflow-y: auto;
  overflow-x: hidden;
}
.service-card-grid { align-items: stretch; }
.service-card { min-height: 0; }
.service-card .switch-grid { grid-template-columns: repeat(auto-fit, minmax(150px, max-content)); }
@media (max-width: 1280px) {
  .service-card-grid { grid-template-columns: 1fr; }
}

</style>
