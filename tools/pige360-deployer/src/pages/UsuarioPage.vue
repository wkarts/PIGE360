<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import AppModal from "../components/AppModal.vue";
import BasePage from "../components/base/BasePage.vue";
import AppSwitch from "../components/AppSwitch.vue";
import {
  comboList,
  deleteUser,
  getUser,
  getUserPolicy,
  listProfiles,
  listUsers,
  saveUserPolicy,
  saveUser,
  type ComboOption
} from "../services/crud";
import { booleanLabel, formatPhone } from "../services/format";
import { useSessionStore } from "../stores/session";
import { logAppError, logAppInfo } from "../services/logger";
import { showSplashSuccess } from "../services/splash";
import { appConfirm } from "../services/dialog";

const session = useSessionStore();
const rows = ref<Record<string, unknown>[]>([]);
const loading = ref(false);
const saving = ref(false);
const policyLoading = ref(false);
const policySaving = ref(false);
const error = ref("");
const policyError = ref("");
const search = ref("");
const filterEmpresaId = ref<number | null>(null);
const onlyActive = ref(true);
const modalOpen = ref(false);

const companyOptions = ref<ComboOption[]>([]);
const profileOptions = ref<ComboOption[]>([]);
const loginMinLength = ref(2);
const loginMinAllowed = ref(1);
const loginMaxAllowed = ref(64);

function defaultForm() {
  return {
    id: undefined as number | undefined,
    nome: "",
    login: "",
    email: "",
    telefone: "",
    cargo: "",
    observacoes: "",
    senha: "",
    master_user: false,
    administrador: false,
    senha_provisoria: false,
    ativo: true,
    photo_url: "",
    empresa_ids: [] as string[],
    profile_ids: [] as string[]
  };
}

const form = reactive(defaultForm());
const canManage = computed(() => session.can("usuarios:manage"));

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

function readPhotoFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    form.photo_url = String(reader.result || "");
  };
  reader.readAsDataURL(file);
}

function clearPhoto() {
  form.photo_url = "";
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item));
}

async function loadOptions() {
  await ensureSession();
  companyOptions.value = await comboList("empresas");
  const profileRows = await listProfiles(session.sessionToken!, { onlyActive: true });
  profileOptions.value = profileRows.map((row) => ({
    id: Number(row.id),
    label: String(row.nome || `Perfil ${row.id}`)
  }));
}

async function load() {
  await ensureSession();
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listUsers(session.sessionToken!, {
      search: search.value,
      empresaId: filterEmpresaId.value,
      onlyActive: onlyActive.value
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar usuários.";
    logAppError("usuarios", "Falha ao carregar usuários.", { error: error.value });
  } finally {
    loading.value = false;
  }
}

async function loadPolicy() {
  if (!session.isMaster) return;
  await ensureSession();
  policyLoading.value = true;
  policyError.value = "";
  try {
    const payload = await getUserPolicy(session.sessionToken!);
    loginMinLength.value = Number(payload.login_min_length || 2);
    loginMinAllowed.value = Number(payload.login_min_allowed || 1);
    loginMaxAllowed.value = Number(payload.login_max_allowed || 64);
  } catch (err) {
    policyError.value = err instanceof Error ? err.message : "Falha ao carregar política de login.";
    logAppError("usuarios", "Falha ao carregar política de login.", { error: policyError.value });
  } finally {
    policyLoading.value = false;
  }
}

async function persistPolicy() {
  if (!canManage.value || !session.isMaster) return;
  await ensureSession();
  policySaving.value = true;
  policyError.value = "";
  try {
    const payload = await saveUserPolicy(session.sessionToken!, { login_min_length: Number(loginMinLength.value) });
    loginMinLength.value = Number(payload.login_min_length || loginMinLength.value);
    loginMinAllowed.value = Number(payload.login_min_allowed || loginMinAllowed.value);
    loginMaxAllowed.value = Number(payload.login_max_allowed || loginMaxAllowed.value);
    logAppInfo("usuarios", "Política de login atualizada com sucesso.", { login_min_length: loginMinLength.value });
  } catch (err) {
    policyError.value = err instanceof Error ? err.message : "Falha ao salvar política de login.";
    logAppError("usuarios", "Falha ao salvar política de login.", {
      error: policyError.value,
      login_min_length: loginMinLength.value
    });
  } finally {
    policySaving.value = false;
  }
}

async function editRow(id: number) {
  error.value = "";
  try {
    await ensureSession();
    const record = await getUser(session.sessionToken!, id);
    Object.assign(form, defaultForm(), record, {
      master_user: Number(record.master_user) === 1 || record.master_user === true,
      administrador: Number(record.administrador) === 1 || record.administrador === true,
      senha_provisoria: Number(record.senha_provisoria) === 1 || record.senha_provisoria === true,
      ativo: Number(record.ativo) === 1 || record.ativo === true,
      empresa_ids: toStringArray(record.empresa_ids),
      profile_ids: toStringArray(record.profile_ids),
      senha: ""
    });
    modalOpen.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar usuário.";
    logAppError("usuarios", "Falha ao carregar usuário para edição.", { id, error: error.value });
  }
}

async function persist() {
  if (!canManage.value) return;
  saving.value = true;
  error.value = "";
  try {
    await ensureSession();
    await saveUser(session.sessionToken!, {
      ...form,
      empresa_ids: form.empresa_ids.map((item) => Number(item)),
      profile_ids: form.profile_ids.map((item) => Number(item))
    });
    await load();
    closeModal();
    resetForm();
    logAppInfo("usuarios", "Usuário salvo com sucesso.");
    showSplashSuccess(form.id ? "Usuário atualizado com sucesso." : "Usuário criado com sucesso.");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao salvar usuário.";
    logAppError("usuarios", "Falha ao salvar usuário.", { error: error.value, payload: form });
  } finally {
    saving.value = false;
  }
}

async function removeRow(id: number) {
  if (!canManage.value) return;
  if (!(await appConfirm({ title: "Excluir usuário", message: "Deseja excluir este usuário?", danger: true, confirmText: "Excluir" }))) return;
  try {
    await ensureSession();
    await deleteUser(session.sessionToken!, id);
    await load();
    if (Number(form.id) === id) {
      resetForm();
      closeModal();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao excluir usuário.";
    logAppError("usuarios", "Falha ao excluir usuário.", { id, error: error.value });
  }
}

onMounted(async () => {
  try {
    await loadOptions();
    await loadPolicy();
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao inicializar cadastro de usuários.";
    logAppError("usuarios", "Falha na inicialização da página de usuários.", { error: error.value });
  }
});
</script>

<template>
  <BasePage title="Cadastro de usuários" subtitle="Listagem fixa com manutenção do acesso em modal." icon="users">
    <template #actions>
      <button class="secondary" :disabled="!canManage" @click="openNewModal">Novo cadastro</button>
    </template>

    <div v-if="!session.can('usuarios:view')" class="alert error">Você não possui permissão para visualizar usuários.</div>
    <div v-else class="grid page-gap">
      <div v-if="error" class="alert error">{{ error }}</div>
      <div v-if="policyError" class="alert error">{{ policyError }}</div>

      <div v-if="session.isMaster" class="card grid page-gap">
        <div class="toolbar">
          <div>
            <h3>Políticas de login</h3>
            <div class="muted-text">Parâmetro global aplicado na criação e atualização de usuários.</div>
          </div>
          <div class="actions align-end">
            <div class="field min-field">
              <label>Mínimo de caracteres no login</label>
              <input
                v-model.number="loginMinLength"
                type="number"
                :min="loginMinAllowed"
                :max="loginMaxAllowed"
                :disabled="policyLoading || policySaving || !canManage"
              />
            </div>
            <button class="secondary" :disabled="policyLoading || policySaving || !canManage" @click="persistPolicy">
              {{ policySaving ? "Salvando..." : "Salvar política" }}
            </button>
          </div>
        </div>
      </div>

      <div class="card grid page-gap">
        <div class="toolbar">
          <div>
            <h3>Usuários cadastrados</h3>
            <div class="muted-text">Controle de login, sessão e vínculo de perfis por empresa.</div>
          </div>
          <div class="actions align-end">
            <div class="field min-field">
              <label>Empresa</label>
              <select v-model="filterEmpresaId">
                <option :value="null">Todas</option>
                <option v-for="item in companyOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
              </select>
            </div>
            <div class="field min-field">
              <label>Buscar</label>
              <input v-model="search" type="text" placeholder="Nome, login ou e-mail" @keyup.enter="load" />
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
                <th>Usuário</th>
                <th>Contato</th>
                <th>Perfis</th>
                <th>Empresas</th>
                <th>Status</th>
                <th>Último login</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="Number(row.id)">
                <td>{{ row.id }}</td>
                <td>
                  <div class="avatar-preview-row avatar-editor-card"><img v-if="row.photo_url" :src="String(row.photo_url)" class="user-avatar-img" alt="Foto" /><div v-else class="user-avatar">{{ String(row.nome || row.login || 'U').slice(0, 1).toUpperCase() }}</div><div><strong>{{ row.nome }}</strong><div class="muted-row">{{ row.login }}</div></div></div>
                  <div class="pill-box top-gap-6">
                    <span v-if="Number(row.master_user) === 1 || row.master_user === true" class="status-pill pill-master">MASTER</span>
                    <span v-if="Number(row.administrador) === 1 || row.administrador === true" class="status-pill pill-secondary">ADMIN</span>
                    <span v-if="Number(row.senha_provisoria) === 1 || row.senha_provisoria === true" class="status-pill pill-warning">SENHA PROVISÓRIA</span>
                  </div>
                </td>
                <td>
                  <div>{{ row.email || '-' }}</div>
                  <div class="muted-row">{{ formatPhone(row.telefone) || '-' }}</div>
                </td>
                <td>{{ row.perfis || '-' }}</td>
                <td>{{ row.empresas || '-' }}</td>
                <td>{{ booleanLabel(row.ativo) }}</td>
                <td>{{ row.ultimo_login_em || '-' }}</td>
                <td>
                  <div class="table-actions">
                    <button class="secondary small" @click="editRow(Number(row.id))">Editar</button>
                    <button class="danger small" :disabled="!canManage" @click="removeRow(Number(row.id))">Excluir</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!rows.length">
                <td colspan="8" class="empty-cell">Nenhum usuário encontrado.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <AppModal
      :open="modalOpen"
      :title="form.id ? 'Editar usuário' : 'Novo usuário'"
      subtitle="Fluxo convertido para modal, preservando as regras atuais de sessão, perfis e empresas."
      width="xl"
      @close="closeModal"
    >
      <div class="grid page-gap user-modal-shell">
        <section class="modal-section-card">
        <div class="section-title">Dados do acesso</div>
        <div class="avatar-preview-row">
          <img v-if="form.photo_url" :src="form.photo_url" class="avatar-preview" alt="Foto do usuário" />
          <div v-else class="avatar-placeholder">{{ (form.nome || form.login || 'U').slice(0, 1).toUpperCase() }}</div>
          <div class="field">
            <label>Foto do usuário</label>
            <input type="file" accept="image/*" :disabled="!canManage" @change="readPhotoFile" />
            <button class="secondary small top-gap-6" type="button" :disabled="!canManage || !form.photo_url" @click="clearPhoto">Remover foto</button>
          </div>
        </div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field">
            <label>Nome *</label>
            <input v-model="form.nome" type="text" :disabled="!canManage" placeholder="Nome completo do usuário" />
          </div>
          <div class="field">
            <label>Login *</label>
            <input v-model="form.login" type="text" :disabled="!canManage" placeholder="login" />
          </div>
          <div class="field">
            <label>E-mail</label>
            <input v-model="form.email" type="email" :disabled="!canManage" placeholder="usuario@empresa.com" />
          </div>
          <div class="field">
            <label>Telefone</label>
            <input v-model="form.telefone" type="text" :disabled="!canManage" placeholder="(00) 00000-0000" />
          </div>
          <div class="field">
            <label>Cargo</label>
            <input v-model="form.cargo" type="text" :disabled="!canManage" placeholder="Cargo / função" />
          </div>
          <div class="field">
            <label>{{ form.id ? 'Nova senha (opcional)' : 'Senha *' }}</label>
            <input v-model="form.senha" type="password" :disabled="!canManage" placeholder="mínimo 6 caracteres" />
          </div>
        </div>
        </section>

        <section class="modal-section-card">
          <div class="section-title">Perfis e empresas</div>
          <div class="selection-summary-row">
            <span class="selection-summary-pill">{{ form.profile_ids.length }} perfil(is) selecionado(s)</span>
            <span class="selection-summary-pill">{{ form.empresa_ids.length }} empresa(s) vinculada(s)</span>
            <span v-if="form.master_user" class="selection-summary-pill">Master: vínculo específico opcional</span>
          </div>
          <div class="grid columns-2 mobile-columns-1">
            <div class="field">
              <label>Perfis de acesso</label>
              <div class="selection-card-grid">
                <label v-for="item in profileOptions" :key="item.id" class="selection-card">
                  <input v-model="form.profile_ids" type="checkbox" :value="String(item.id)" :disabled="!canManage || form.master_user" />
                  <span class="selection-switch-ui"></span>
                  <span class="selection-card-copy"><strong>{{ item.label }}</strong><small>Perfil #{{ item.id }}</small></span>
                </label>
              </div>
            </div>
            <div class="field">
              <label>Empresas vinculadas</label>
              <div class="selection-card-grid">
                <label v-for="item in companyOptions" :key="item.id" class="selection-card">
                  <input v-model="form.empresa_ids" type="checkbox" :value="String(item.id)" :disabled="!canManage || form.master_user" />
                  <span class="selection-switch-ui"></span>
                  <span class="selection-card-copy"><strong>{{ item.label }}</strong><small>Acesso permitido para esta empresa</small></span>
                </label>
              </div>
              <div class="muted-row">Ative as empresas onde este usuário poderá operar. Usuário master pode operar sem vínculo específico.</div>
            </div>
          </div>
        </section>

        <section class="modal-section-card">
        <div class="section-title">Status e observações</div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field span-2">
            <label>Observações</label>
            <textarea v-model="form.observacoes" rows="4" :disabled="!canManage" placeholder="Observações internas sobre o usuário"></textarea>
          </div>
          <AppSwitch v-model="form.master_user" label="Usuário master" :disabled="!canManage" />
          <AppSwitch v-model="form.administrador" label="Administrador" :disabled="!canManage" />
          <AppSwitch v-model="form.senha_provisoria" label="Senha provisória / exigir troca" :disabled="!canManage" />
          <AppSwitch v-model="form.ativo" label="Usuário ativo" :disabled="!canManage" />
        </div>
        </section>

        <div class="actions modal-actions-footer">
          <button class="primary" :disabled="saving || !canManage" @click="persist">
            {{ saving ? "Salvando..." : form.id ? "Atualizar usuário" : "Salvar usuário" }}
          </button>
          <button class="secondary" @click="resetForm">Limpar</button>
        </div>
      </div>
    </AppModal>
  </BasePage>
</template>
