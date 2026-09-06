<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { invokeCommand } from "../../services/tauri";
import BasePage from "../../components/base/BasePage.vue";
import BaseSectionCard from "../../components/base/BaseSectionCard.vue";
import AppModal from "../../components/AppModal.vue";
import { appConfirm } from "../../services/dialog";

type Integration = {
  id?: number;
  nome: string;
  tipo: string;
  base_url: string;
  metodo_padrao: string;
  headers_json?: string;
  ambiente: string;
  status: string;
  timeout_seconds: number;
  retry_attempts: number;
  ativo: number | boolean;
  ultimo_erro?: string | null;
  ultima_execucao_em?: string | null;
};

const items = ref<Integration[]>([]);
const logs = ref<any[]>([]);
const loading = ref(false);
const testingId = ref<number | null>(null);
const error = ref("");
const modalOpen = ref(false);
const form = ref<any>({});

const activeCount = computed(() => items.value.filter((item) => item.ativo && item.status === "active").length);
const errorCount = computed(() => items.value.filter((item) => item.status === "error").length);

function newForm() {
  form.value = {
    nome: "",
    tipo: "rest",
    base_url: "",
    metodo_padrao: "GET",
    headers: {},
    token: "",
    ambiente: "production",
    status: "inactive",
    timeout_seconds: 30,
    retry_attempts: 0,
    ativo: true,
  };
  modalOpen.value = true;
}

function edit(item: Integration) {
  form.value = {
    ...item,
    headers: item.headers_json ? JSON.parse(item.headers_json) : {},
    token: "",
    ativo: Boolean(item.ativo),
  };
  modalOpen.value = true;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    items.value = await invokeCommand<Integration[]>("integration_list");
    logs.value = await invokeCommand<any[]>("integration_logs", { integrationId: null });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar integrações.";
  } finally {
    loading.value = false;
  }
}

async function save() {
  error.value = "";
  try {
    await invokeCommand("integration_save", { payload: form.value });
    modalOpen.value = false;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao salvar integração.";
  }
}

async function test(item: Integration) {
  if (!item.id) return;
  testingId.value = item.id;
  error.value = "";
  try {
    await invokeCommand("integration_test", { id: item.id });
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao testar integração.";
  } finally {
    testingId.value = null;
  }
}

async function remove(item: Integration) {
  if (!item.id) return;
  if (!(await appConfirm({ title: "Excluir integração", message: `Excluir integração ${item.nome}?`, danger: true, confirmText: "Excluir" }))) return;
  await invokeCommand("integration_delete", { id: item.id });
  await load();
}

onMounted(load);
</script>

<template>
  <BasePage title="Integrações externas" subtitle="Cadastro funcional para APIs REST, tokens protegidos, teste de conexão e logs de requisição.">
    <div class="page-actions-row">
      <button class="primary" @click="newForm">Nova integração</button>
      <button class="secondary" :disabled="loading" @click="load">Atualizar</button>
    </div>

    <div v-if="error" class="alert error">{{ error }}</div>

    <div class="grid columns-4 mobile-columns-1">
      <div class="kpi"><strong>Total</strong><span>{{ items.length }}</span></div>
      <div class="kpi"><strong>Ativas</strong><span>{{ activeCount }}</span></div>
      <div class="kpi"><strong>Com erro</strong><span>{{ errorCount }}</span></div>
      <div class="kpi"><strong>Logs</strong><span>{{ logs.length }}</span></div>
    </div>

    <BaseSectionCard title="Integrações cadastradas">
      <div v-if="!items.length" class="empty-state"><strong>Nenhuma integração cadastrada.</strong><p>Cadastre uma API externa para testar conexão e monitorar logs.</p></div>
      <div v-else class="table-wrap">
        <table class="data-table compact-table">
          <thead><tr><th>Nome</th><th>URL</th><th>Ambiente</th><th>Status</th><th>Ativo</th><th>Ações</th></tr></thead>
          <tbody>
            <tr v-for="item in items" :key="item.id">
              <td><strong>{{ item.nome }}</strong><small>{{ item.tipo }} / {{ item.metodo_padrao }}</small></td>
              <td class="mono-text">{{ item.base_url }}</td>
              <td>{{ item.ambiente }}</td>
              <td><span class="status-pill" :class="item.status">{{ item.status }}</span></td>
              <td>{{ item.ativo ? 'Sim' : 'Não' }}</td>
              <td class="row-actions">
                <button class="secondary tiny" @click="edit(item)">Editar</button>
                <button class="secondary tiny" :disabled="testingId === item.id" @click="test(item)">Testar</button>
                <button class="danger tiny" @click="remove(item)">Excluir</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseSectionCard>

    <BaseSectionCard title="Últimos logs de integração">
      <div v-if="!logs.length" class="empty-state"><strong>Nenhum log registrado.</strong><p>Use o botão testar para gerar o primeiro log.</p></div>
      <div v-else class="table-wrap">
        <table class="data-table compact-table">
          <thead><tr><th>Data</th><th>URL</th><th>Status</th><th>Duração</th><th>Erro</th></tr></thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>{{ log.created_at }}</td>
              <td class="mono-text">{{ log.url }}</td>
              <td>{{ log.status_code || (log.success ? 'OK' : 'Falha') }}</td>
              <td>{{ log.duration_ms }}ms</td>
              <td>{{ log.error_message || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseSectionCard>

    <AppModal :open="modalOpen" title="Integração externa" width="xl" @close="modalOpen=false">
      <div class="form-grid columns-2">
        <label>Nome<input v-model="form.nome" /></label>
        <label>Tipo<select v-model="form.tipo"><option value="rest">REST</option><option value="webhook">Webhook</option></select></label>
        <label class="span-2">URL base<input v-model="form.base_url" placeholder="https://api.exemplo.com/health" /></label>
        <label>Método<select v-model="form.metodo_padrao"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label>
        <label>Ambiente<input v-model="form.ambiente" /></label>
        <label>Timeout<input v-model.number="form.timeout_seconds" type="number" min="1" /></label>
        <label>Tentativas<input v-model.number="form.retry_attempts" type="number" min="0" /></label>
        <label class="span-2">Token/Bearer<input v-model="form.token" type="password" placeholder="Preencha apenas para alterar" /></label>
        <label class="checkbox-line"><input v-model="form.ativo" type="checkbox" /> Ativo</label>
      </div>
      <div class="modal-actions-row">
        <button class="secondary" @click="modalOpen=false">Cancelar</button>
        <button class="primary" @click="save">Salvar</button>
      </div>
    </AppModal>
  </BasePage>
</template>
