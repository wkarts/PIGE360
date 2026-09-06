<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { clearAppLogs, listAppLogs, type GenericRecord } from "../services/crud";
import BasePage from "../components/base/BasePage.vue";
import { useSessionStore } from "../stores/session";
import { logAppError, logAppInfo } from "../services/logger";
import { appConfirm } from "../services/dialog";

const session = useSessionStore();
const rows = ref<GenericRecord[]>([]);
const loading = ref(false);
const clearing = ref(false);
const error = ref("");
const filters = reactive({ level: "", category: "", search: "", limit: 200 });

async function ensureSession() {
  if (!session.sessionToken) {
    await session.restore();
  }
  if (!session.sessionToken) {
    throw new Error("Sessão inválida para consultar logs da aplicação.");
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    await ensureSession();
    rows.value = await listAppLogs(session.sessionToken!, filters);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar logs.";
    logAppError("logs", "Falha ao carregar página de logs.", { error: error.value });
  } finally {
    loading.value = false;
  }
}

async function clearLogs() {
  if (!(await appConfirm({ title: "Limpar logs", message: "Deseja limpar os logs da aplicação?", danger: true, confirmText: "Limpar" }))) return;
  clearing.value = true;
  try {
    await ensureSession();
    await clearAppLogs(session.sessionToken!);
    logAppInfo("logs", "Logs da aplicação limpos manualmente.", { user: session.user?.login ?? null });
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao limpar logs.";
  } finally {
    clearing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <BasePage title="Logs da aplicação" subtitle="Diagnóstico de inicialização, sessão, navegação, páginas e falhas administrativas." icon="clipboard">
    <template #actions>
      <button class="secondary" :disabled="loading" @click="load">Atualizar</button>
      <button class="danger" :disabled="clearing" @click="clearLogs">Limpar logs</button>
    </template>

    <div v-if="error" class="alert error">{{ error }}</div>

    <div class="card grid page-gap">
      <div class="grid columns-4 mobile-columns-1">
        <div class="field">
          <label>Nível</label>
          <select v-model="filters.level">
            <option value="">Todos</option>
            <option value="debug">Debug</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
          </select>
        </div>
        <div class="field">
          <label>Categoria</label>
          <input v-model="filters.category" type="text" placeholder="auth, router, session..." />
        </div>
        <div class="field span-2">
          <label>Buscar</label>
          <input v-model="filters.search" type="text" placeholder="mensagem, rota ou detalhes" @keyup.enter="load" />
        </div>
      </div>
    </div>

    <div class="card table-wrap">
      <table>
        <thead>
          <tr>
            <th>Quando</th>
            <th>Nível</th>
            <th>Categoria</th>
            <th>Mensagem</th>
            <th>Origem</th>
            <th>Rota</th>
            <th>Detalhes</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="Number(row.id)">
            <td>{{ row.created_at }}</td>
            <td>{{ row.level }}</td>
            <td>{{ row.category }}</td>
            <td>{{ row.message }}</td>
            <td>{{ row.source || '-' }}</td>
            <td>{{ row.route || '-' }}</td>
            <td><pre class="logs-pre">{{ row.details_json || '-' }}</pre></td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="7" class="empty-cell">Nenhum log encontrado.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </BasePage>
</template>
