<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import AppModal from "../components/AppModal.vue";
import BasePage from "../components/base/BasePage.vue";
import AppSwitch from "../components/AppSwitch.vue";
import {
  deleteProfile,
  getProfile,
  listPermissionCatalog,
  listProfiles,
  saveProfile,
  type GenericRecord
} from "../services/crud";
import { booleanLabel } from "../services/format";
import { useSessionStore } from "../stores/session";
import { logAppError, logAppInfo } from "../services/logger";
import { appConfirm } from "../services/dialog";

const session = useSessionStore();
const rows = ref<GenericRecord[]>([]);
const permissions = ref<GenericRecord[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const search = ref("");
const onlyActive = ref(true);
const modalOpen = ref(false);

function defaultForm() {
  return {
    id: undefined as number | undefined,
    nome: "",
    descricao: "",
    perfil_master: false,
    ativo: true,
    permission_keys: [] as string[]
  };
}

const form = reactive(defaultForm());
const canManage = computed(() => session.can("perfis:manage"));

async function ensureSession() {
  if (!session.sessionToken) {
    await session.restore();
  }
  if (!session.sessionToken) {
    throw new Error("Sessão inválida ou expirada. Faça login novamente.");
  }
}

function closeModal() {
  modalOpen.value = false;
}

function openNewModal() {
  resetForm();
  modalOpen.value = true;
}

function resetForm() {
  Object.assign(form, defaultForm());
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item));
}

async function load() {
  await ensureSession();
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listProfiles(session.sessionToken!, {
      search: search.value,
      onlyActive: onlyActive.value
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar perfis.";
    logAppError("perfis", "Falha ao carregar perfis.", { error: error.value });
  } finally {
    loading.value = false;
  }
}

async function loadPermissions() {
  await ensureSession();
  permissions.value = await listPermissionCatalog(session.sessionToken!);
}

async function editRow(id: number) {
  error.value = "";
  try {
    await ensureSession();
    const record = await getProfile(session.sessionToken!, id);
    Object.assign(form, defaultForm(), record, {
      perfil_master: Number(record.perfil_master) === 1 || record.perfil_master === true,
      ativo: Number(record.ativo) === 1 || record.ativo === true,
      permission_keys: toStringArray(record.permission_keys)
    });
    modalOpen.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar perfil.";
    logAppError("perfis", "Falha ao carregar perfil para edição.", { id, error: error.value });
  }
}

async function persist() {
  if (!canManage.value) return;
  saving.value = true;
  error.value = "";
  try {
    await ensureSession();
    await saveProfile(session.sessionToken!, { ...form });
    await load();
    closeModal();
    resetForm();
    logAppInfo("perfis", "Perfil salvo com sucesso.");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao salvar perfil.";
    logAppError("perfis", "Falha ao salvar perfil.", { error: error.value, payload: form });
  } finally {
    saving.value = false;
  }
}

async function removeRow(id: number) {
  if (!canManage.value) return;
  if (!(await appConfirm({ title: "Excluir perfil", message: "Deseja excluir este perfil de acesso?", danger: true, confirmText: "Excluir" }))) return;
  try {
    await ensureSession();
    await deleteProfile(session.sessionToken!, id);
    await load();
    if (Number(form.id) === id) {
      resetForm();
      closeModal();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao excluir perfil.";
    logAppError("perfis", "Falha ao excluir perfil.", { id, error: error.value });
  }
}

onMounted(async () => {
  try {
    await Promise.all([loadPermissions(), load()]);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao inicializar perfis de acesso.";
    logAppError("perfis", "Falha na inicialização da página de perfis.", { error: error.value });
  }
});
</script>

<template>
  <BasePage title="Perfis de acesso" subtitle="Listagem fixa com cadastro e edição padronizados em modal." icon="shield">
    <template #actions>
      <button class="secondary" :disabled="!canManage" @click="openNewModal">Novo perfil</button>
    </template>

    <div v-if="!session.can('perfis:view')" class="alert error">Você não possui permissão para visualizar perfis.</div>
    <div v-else class="grid page-gap">
      <div v-if="error" class="alert error">{{ error }}</div>

      <div class="card grid page-gap">
        <div class="toolbar">
          <div>
            <h3>Perfis cadastrados</h3>
            <div class="muted-text">Cada perfil pode ser reutilizado em vários usuários.</div>
          </div>
          <div class="actions align-end">
            <div class="field min-field">
              <label>Buscar</label>
              <input v-model="search" type="text" placeholder="Nome ou descrição" @keyup.enter="load" />
            </div>
            <AppSwitch v-model="onlyActive" label="Somente ativos" />
            <button class="secondary" :disabled="loading" @click="load">{{ loading ? "Carregando..." : "Atualizar" }}</button>
          </div>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Perfil</th>
                <th>Descrição</th>
                <th>Permissões</th>
                <th>Usuários</th>
                <th>Status</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="Number(row.id)">
                <td>{{ row.id }}</td>
                <td>
                  <strong>{{ row.nome }}</strong>
                  <div class="pill-box top-gap-6">
                    <span v-if="Number(row.perfil_master) === 1 || row.perfil_master === true" class="status-pill pill-master">MASTER</span>
                  </div>
                </td>
                <td>{{ row.descricao || '-' }}</td>
                <td>{{ row.total_permissoes || 0 }}</td>
                <td>{{ row.total_usuarios || 0 }}</td>
                <td>{{ booleanLabel(row.ativo) }}</td>
                <td>
                  <div class="table-actions">
                    <button class="secondary small" @click="editRow(Number(row.id))">Editar</button>
                    <button class="danger small" :disabled="!canManage" @click="removeRow(Number(row.id))">Excluir</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!rows.length">
                <td colspan="7" class="empty-cell">Nenhum perfil encontrado.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <AppModal
      :open="modalOpen"
      :title="form.id ? 'Editar perfil de acesso' : 'Novo perfil de acesso'"
      subtitle="A manutenção do perfil foi movida para modal sem alterar o fluxo da listagem."
      width="xl"
      @close="closeModal"
    >
      <div class="grid page-gap profile-modal-shell">
        <section class="modal-section-card">
          <div class="section-title">Dados do perfil</div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field">
            <label>Nome *</label>
            <input v-model="form.nome" type="text" :disabled="!canManage" placeholder="Ex.: Operação RH" />
          </div>
          <AppSwitch v-model="form.perfil_master" label="Perfil master" :disabled="!canManage" />
          <div class="field span-2">
            <label>Descrição</label>
            <textarea v-model="form.descricao" rows="3" :disabled="!canManage" placeholder="Escopo e finalidade do perfil"></textarea>
          </div>
          <AppSwitch v-model="form.ativo" label="Perfil ativo" :disabled="!canManage" />
        </div>
        </section>

        <section class="modal-section-card">
          <div class="section-title">Permissões</div>
        <div class="permissions-grid">
          <label v-for="permission in permissions" :key="String(permission.key)" class="permission-card">
            <input
              v-model="form.permission_keys"
              type="checkbox"
              :disabled="!canManage || form.perfil_master"
              :value="String(permission.key)"
            />
            <span class="permission-switch-ui"></span>
            <div>
              <strong>{{ permission.label }}</strong>
              <div class="muted-row">{{ permission.key }}</div>
            </div>
          </label>
        </div>
        </section>

        <div class="actions modal-actions-footer">
          <button class="primary" :disabled="saving || !canManage" @click="persist">
            {{ saving ? "Salvando..." : form.id ? "Atualizar perfil" : "Salvar perfil" }}
          </button>
          <button class="secondary" @click="resetForm">Limpar</button>
        </div>
      </div>
    </AppModal>
  </BasePage>
</template>
