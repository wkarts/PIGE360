<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { invokeCommand } from "../../services/tauri";
import BasePage from "../../components/base/BasePage.vue";

interface RuntimeStatus {
  running?: boolean;
  host?: string;
  port?: number;
  url?: string | null;
  base_path?: string;
  events_count?: number;
  message?: string;
  simulated?: boolean;
}

const loading = ref(false);
const error = ref("");
const message = ref("");
const status = ref<RuntimeStatus>({ running: false });
function clientHost(host?: string): string {
  const value = (host || "127.0.0.1").trim();
  if (!value || value === "0.0.0.0" || value === "::" || value === "[::]" || value === "127.0.0.1" || value === "localhost") {
    return typeof window !== "undefined" ? window.location.hostname || "127.0.0.1" : "127.0.0.1";
  }
  return value;
}

function clientServiceUrl(rawUrl: string | null | undefined, protocol: "http" | "ws", port: number, path = "") {
  const fallback = `${protocol}://${clientHost(undefined)}:${port}${path}`;
  if (!rawUrl) return fallback;
  try {
    const parsed = new URL(rawUrl);
    parsed.hostname = clientHost(parsed.hostname);
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
}

const events = ref<Record<string, unknown>[]>([]);
const testPayload = reactive({ provider: "manual", event: "test", payload: '{"message":"Teste do Webhook Service"}' });

const serviceUrl = computed(() => clientServiceUrl(status.value.url, "http", status.value.port || 61003));
const endpointUrl = computed(() => `${serviceUrl.value}${status.value.base_path || "/webhooks"}/${testPayload.provider}/${testPayload.event}`);

async function probeHealth() {
  try {
    await fetch(`${serviceUrl.value}/health`, { method: "GET", mode: "no-cors", cache: "no-store" });
    status.value = { ...status.value, running: true, host: clientHost(status.value.host), url: serviceUrl.value, message: "Serviço acessível via rede." };
  } catch {
    // Mantém o status retornado pelo runtime.
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    status.value = await invokeCommand<RuntimeStatus>("webhook_status");
    await probeHealth();
    const response = await invokeCommand<{ items: Record<string, unknown>[] }>("webhook_list_events");
    events.value = response.items || [];
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar status do serviço.";
  } finally {
    loading.value = false;
  }
}

async function start() {
  await runServiceAction("webhook_start", "Webhook Service iniciado.");
}

async function stop() {
  await runServiceAction("webhook_stop", "Webhook Service parado.");
}

async function restart() {
  await runServiceAction("webhook_restart", "Webhook Service reiniciado.");
}

async function runServiceAction(command: string, successMessage: string) {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    status.value = await invokeCommand<RuntimeStatus>(command);
    message.value = successMessage;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao executar operação do Webhook Service.";
  } finally {
    loading.value = false;
  }
}

async function clearEvents() {
  error.value = "";
  message.value = "";
  try {
    await invokeCommand<boolean>("webhook_clear_events");
    message.value = "Eventos limpos.";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao limpar eventos.";
  }
}

async function sendTest() {
  let parsed: unknown;
  try {
    parsed = JSON.parse(testPayload.payload || "{}");
  } catch {
    parsed = { raw: testPayload.payload };
  }
  error.value = "";
  message.value = "";
  try {
    await invokeCommand("webhook_test_receive", { provider: testPayload.provider, event: testPayload.event, payload: parsed });
    message.value = "Webhook de teste registrado localmente.";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao registrar teste local.";
  }
}

onMounted(load);
</script>

<template>
  <BasePage title="Webhook Service" subtitle="Hub genérico para receber eventos HTTP externos por provedor, módulo ou integração." icon="webhook">
    <template #actions>
      <button class="secondary" type="button" @click="load" :disabled="loading">Atualizar</button>
      <button class="primary" type="button" @click="start">Iniciar</button>
      <button class="secondary" type="button" @click="restart">Reiniciar</button>
      <button class="danger" type="button" @click="stop">Parar</button>
    </template>

    <div v-if="message" class="alert success">{{ message }}</div>
    <div v-if="error" class="alert error">{{ error }}</div>

    <div class="cards-grid three">
      <article class="info-card">
        <span>Status</span>
        <strong>{{ status.running ? 'Rodando' : 'Parado' }}</strong>
        <p v-if="status.simulated || status.message">{{ status.message || 'Serviço simulado neste runtime.' }}</p>
      </article>
      <article class="info-card">
        <span>Porta</span>
        <strong>{{ status.port || 61003 }}</strong>
        <p>{{ status.host || '0.0.0.0' }}</p>
      </article>
      <article class="info-card">
        <span>Eventos recebidos</span>
        <strong>{{ status.events_count ?? events.length }}</strong>
        <p>{{ status.base_path || '/webhooks' }}</p>
      </article>
    </div>

    <div class="panel-card">
      <h2>Endpoint genérico</h2>
      <p class="muted">Use este padrão para apps derivados registrarem eventos sem recriar infraestrutura.</p>
      <code class="code-line">POST {{ endpointUrl }}</code>
    </div>

    <div class="panel-card form-grid two">
      <label>
        <span>Provider</span>
        <input v-model="testPayload.provider" />
      </label>
      <label>
        <span>Evento</span>
        <input v-model="testPayload.event" />
      </label>
      <label class="span-2">
        <span>Payload JSON de teste</span>
        <textarea v-model="testPayload.payload" rows="5"></textarea>
      </label>
      <div class="span-2 toolbar-actions">
        <button class="btn" type="button" @click="sendTest">Registrar teste local</button>
        <button class="btn secondary" type="button" @click="clearEvents">Limpar eventos</button>
      </div>
    </div>

    <div class="panel-card">
      <h2>Eventos recentes</h2>
      <div v-if="!events.length" class="empty-state">Nenhum webhook recebido.</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Provider</th><th>Evento</th><th>Status</th><th>Recebido em</th></tr></thead>
          <tbody>
            <tr v-for="item in events" :key="String(item.id)">
              <td>{{ item.id }}</td>
              <td>{{ item.provider }}</td>
              <td>{{ item.event }}</td>
              <td>{{ item.status }}</td>
              <td>{{ item.received_at }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </BasePage>
</template>
