<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { invokeCommand } from "../../services/tauri";
import BasePage from "../../components/base/BasePage.vue";

interface RuntimeStatus {
  running?: boolean;
  host?: string;
  port?: number;
  url?: string | null;
  path?: string;
  clients_count?: number;
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

const clients = ref<Record<string, unknown>[]>([]);
const testMessage = ref("Teste broadcast do WebSocket Service");
const socketTestResult = ref("");
let testSocket: WebSocket | null = null;
const wsUrl = computed(() => clientServiceUrl(status.value.url, "ws", status.value.port || 61004, status.value.path || "/ws"));
const healthUrl = computed(() => clientServiceUrl(status.value.url?.replace(/^ws/i, "http"), "http", status.value.port || 61004, "/health").replace(/\/ws$/, "/health"));

async function probeHealth() {
  try {
    await fetch(healthUrl.value, { method: "GET", mode: "no-cors", cache: "no-store" });
    status.value = { ...status.value, running: true, host: clientHost(status.value.host), message: "Serviço acessível via rede." };
  } catch {
    // Mantém o status retornado pelo runtime.
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    status.value = await invokeCommand<RuntimeStatus>("websocket_status");
    await probeHealth();
    const response = await invokeCommand<{ items: Record<string, unknown>[] }>("websocket_list_clients");
    clients.value = response.items || [];
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar status do serviço.";
  } finally {
    loading.value = false;
  }
}

async function start() {
  await runServiceAction("websocket_start", "WebSocket Service iniciado.");
}

async function stop() {
  await runServiceAction("websocket_stop", "WebSocket Service parado.");
}

async function restart() {
  await runServiceAction("websocket_restart", "WebSocket Service reiniciado.");
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
    error.value = err instanceof Error ? err.message : "Falha ao executar operação do WebSocket Service.";
  } finally {
    loading.value = false;
  }
}

function connectTestClient() {
  error.value = "";
  message.value = "";
  socketTestResult.value = "Conectando...";
  try {
    if (testSocket) {
      testSocket.close();
      testSocket = null;
    }
    const socket = new WebSocket(wsUrl.value);
    testSocket = socket;
    socket.onopen = () => {
      socketTestResult.value = "Cliente de teste conectado.";
      socket.send(testMessage.value || "ping");
    };
    socket.onmessage = (event) => {
      socketTestResult.value = `Mensagem recebida: ${event.data}`;
      load();
    };
    socket.onerror = () => {
      socketTestResult.value = "Falha ao conectar no WebSocket.";
    };
    socket.onclose = () => {
      if (socketTestResult.value === "Cliente de teste conectado.") {
        socketTestResult.value = "Cliente de teste desconectado.";
      }
      load();
    };
  } catch (err) {
    socketTestResult.value = err instanceof Error ? err.message : "Falha ao testar WebSocket.";
  }
}

async function broadcastTest() {
  error.value = "";
  message.value = "";
  try {
    await invokeCommand("websocket_broadcast_test", { message: testMessage.value });
    message.value = "Broadcast de teste enviado para clientes conectados.";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao enviar broadcast.";
  }
}

onMounted(load);
</script>

<template>
  <BasePage title="WebSocket Service" subtitle="Bridge genérica para canais, eventos, logs ao vivo, notificações e integração em tempo real." icon="websocket">
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
        <strong>{{ status.port || 61004 }}</strong>
        <p>{{ status.host || '0.0.0.0' }}</p>
      </article>
      <article class="info-card">
        <span>Clientes conectados</span>
        <strong>{{ status.clients_count ?? clients.length }}</strong>
        <p>{{ status.path || '/ws' }}</p>
      </article>
    </div>

    <div class="panel-card">
      <h2>Endpoint WebSocket</h2>
      <p class="muted">Apps derivados podem registrar canais e eventos sobre esta bridge sem duplicar infraestrutura.</p>
      <code class="code-line">{{ wsUrl }}</code>
    </div>

    <div class="panel-card form-grid two">
      <label>
        <span>Mensagem de broadcast</span>
        <input v-model="testMessage" />
      </label>
      <div class="toolbar-actions align-end">
        <button class="btn secondary" type="button" @click="connectTestClient">Conectar cliente teste</button>
        <button class="btn" type="button" @click="broadcastTest">Enviar broadcast</button>
      </div>
    </div>

    <div v-if="socketTestResult" class="alert info">{{ socketTestResult }}</div>

    <div class="panel-card">
      <h2>Clientes conectados</h2>
      <div v-if="!clients.length" class="empty-state">Nenhum cliente conectado.</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>User-Agent</th><th>Conectado em</th></tr></thead>
          <tbody>
            <tr v-for="item in clients" :key="String(item.id)">
              <td>{{ item.id }}</td>
              <td>{{ item.user_agent || '-' }}</td>
              <td>{{ item.connected_at }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </BasePage>
</template>
