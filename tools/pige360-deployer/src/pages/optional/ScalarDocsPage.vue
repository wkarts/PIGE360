<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BasePage from "../../components/base/BasePage.vue";
import BaseSectionCard from "../../components/base/BaseSectionCard.vue";
import { getInternalApiStatus, startInternalApi } from "../../services/crud";

const loading = ref(false);
const error = ref("");
const message = ref("");
const status = ref<Record<string, any>>({});
const frameKey = ref(0);

declare global {
  interface Window { __TAURI_INTERNALS__?: unknown }
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

function isWebProxyRuntime(): boolean {
  if (typeof window === "undefined") return false;
  const win = window as Window & { PIGE360_DEPLOYER_COMMAND_PROXY_BASE?: string; PIGE360_DEPLOYER_WEB_RUNTIME?: boolean; PIGE360_DEPLOYER_INTERNAL_API_WEB_RUNTIME?: boolean };
  return !isTauriRuntime() && Boolean(win.PIGE360_DEPLOYER_COMMAND_PROXY_BASE || win.PIGE360_DEPLOYER_WEB_RUNTIME || win.PIGE360_DEPLOYER_INTERNAL_API_WEB_RUNTIME || window.location.port === "61002");
}

function sameOriginInternalApiUrl(path = ""): string {
  if (typeof window === "undefined") return path || "/__internal_api";
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${window.location.origin}/__internal_api${normalizedPath === "/" ? "" : normalizedPath}`;
}

function browserHostForPublishedService(): string {
  if (typeof window === "undefined") return "127.0.0.1";
  const host = window.location.hostname || "127.0.0.1";
  return host === "localhost" ? "127.0.0.1" : host;
}


function internalApiPortFromStatus(): number {
  const raw = status.value.port || status.value.effective_port || settings.value.internal_api_port || 61001;
  const port = Number(raw);
  return Number.isFinite(port) && port > 0 ? port : 61001;
}

function normalizeInternalApiDirectUrl(rawUrl: string, fallbackPath = "") : string {
  const fallbackHost = browserHostForPublishedService();
  const fallbackPort = internalApiPortFromStatus();
  const fallback = `http://${fallbackHost}:${fallbackPort}${fallbackPath}`;
  const raw = String(rawUrl || "").trim();
  if (!raw) return fallback;
  try {
    const parsed = new URL(raw, typeof window !== "undefined" ? window.location.href : fallback);
    const isProxyPath = parsed.pathname.startsWith("/__internal_api");
    if (isProxyPath) {
      const nextPath = parsed.pathname.replace(/^\/__internal_api/, "") || fallbackPath || "/";
      parsed.protocol = "http:";
      parsed.hostname = fallbackHost;
      parsed.port = String(fallbackPort);
      parsed.pathname = nextPath;
    } else if (["0.0.0.0", "::", "[::]", "127.0.0.1", "localhost", ""].includes(parsed.hostname)) {
      parsed.hostname = fallbackHost;
      if (!parsed.port) parsed.port = String(fallbackPort);
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
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

function withScalarParams(rawUrl: string): string {
  const url = new URL(rawUrl, window.location.href);
  const token = String(settings.value.internal_api_token || "").trim();
  if (tokenRequired.value && token) url.searchParams.set("token", token);
  url.searchParams.set("embed", "1");
  url.searchParams.set("theme", "light");
  return url.toString();
}

const running = computed(() => Boolean(status.value.running));
const settings = computed(() => status.value.settings || {});
const docsUrl = computed(() => {
  const docsPath = settings.value.internal_api_docs_path || "/docs";
  return isWebProxyRuntime()
    ? sameOriginInternalApiUrl(docsPath)
    : normalizeInternalApiDirectUrl(String(status.value.docs_url || settings.value.internal_api_docs_url || ""), docsPath);
});
const baseUrl = computed(() => isWebProxyRuntime()
  ? sameOriginInternalApiUrl("")
  : normalizeInternalApiDirectUrl(String(status.value.url || settings.value.internal_api_base_url || ""), ""));
const tokenRequired = computed(() => Boolean(status.value.token_required || settings.value.internal_api_require_token));
const tokenConfigured = computed(() => Boolean(status.value.token_configured || settings.value.internal_api_token));
const scalarInternalUrl = computed(() => {
  return withScalarParams(docsUrl.value);
});
const tokenInfo = computed(() => tokenRequired.value ? (tokenConfigured.value ? "Token obrigatório aplicado ao carregamento interno" : "Token obrigatório não configurado") : "Token desativado para ambiente local controlado");

async function load() {
  loading.value = true;
  error.value = "";
  try { status.value = await getInternalApiStatus(); } catch (err) { error.value = err instanceof Error ? err.message : "Falha ao carregar status da API interna."; }
  finally { loading.value = false; }
}
async function startApi() {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    await startInternalApi(settings.value.internal_api_host, settings.value.internal_api_port);
    message.value = "API iniciada. A documentação Scalar será carregada dentro da aplicação.";
    await load(); reloadDocs();
  } catch (err) { error.value = err instanceof Error ? err.message : "Falha ao iniciar API interna."; }
  finally { loading.value = false; }
}
function reloadDocs() { frameKey.value += 1; }
function openExternal() { window.open(scalarInternalUrl.value, "_blank", "noopener,noreferrer"); }
onMounted(load);
</script>

<template>
  <BasePage title="Documentação Scalar" subtitle="Scalar interno em tema claro, com suporte a API protegida por token.">
    <template #actions>
      <button class="secondary" :disabled="loading" @click="load">Atualizar status</button>
      <button class="secondary" :disabled="loading || !running" @click="reloadDocs">Recarregar documentação</button>
      <button class="primary" :disabled="!docsUrl" @click="openExternal">Abrir fora</button>
    </template>
    <div v-if="message" class="alert success">{{ message }}</div>
    <div v-if="error" class="alert error">{{ error }}</div>
    <BaseSectionCard title="Scalar da API interna" :subtitle="`${baseUrl} · ${tokenInfo}`">
      <div class="scalar-toolbar">
        <div><strong>URL interna:</strong> <code>{{ scalarInternalUrl }}</code></div>
        <span class="module-chip" :class="running ? 'enabled' : 'disabled'">{{ running ? 'API rodando' : 'API parada' }}</span>
      </div>
      <div v-if="!running" class="scalar-empty light-only-panel">
        <h2>API interna parada</h2>
        <p>A documentação Scalar depende da API local. Inicie a API para abrir a documentação dentro da aplicação.</p>
        <button class="primary" :disabled="loading" @click="startApi">Iniciar API</button>
      </div>
      <div v-else class="scalar-dedicated-shell light-only-panel">
        <iframe :key="frameKey" class="scalar-frame dedicated" :src="scalarInternalUrl" title="Documentação Scalar da API interna"></iframe>
      </div>
    </BaseSectionCard>
  </BasePage>
</template>
