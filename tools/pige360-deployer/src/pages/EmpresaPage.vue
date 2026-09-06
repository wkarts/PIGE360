<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import AppModal from "../components/AppModal.vue";
import BasePage from "../components/base/BasePage.vue";
import AppSwitch from "../components/AppSwitch.vue";
import {
  deleteCompany,
  getCompany,
  listCompanies,
  lookupCompanyCnpj,
  lookupCompanyIe,
  saveCompany,
  type GenericRecord,
} from "../services/crud";
import { booleanLabel, formatCpfCnpj, formatPhone } from "../services/format";
import { showSplashError, showSplashInfo, showSplashSuccess, showSplashWarning } from "../services/splash";
import { appConfirm } from "../services/dialog";

const rows = ref<GenericRecord[]>([]);
const loading = ref(false);
const saving = ref(false);
const lookupCnpjLoading = ref(false);
const lookupIeLoading = ref(false);
const error = ref("");
const search = ref("");
const onlyActive = ref(false);
const modalOpen = ref(false);

function onlyDigits(value: string) {
  return String(value || "").replace(/\D/g, "");
}

function defaultForm() {
  return {
    id: undefined as number | undefined,
    nome: "",
    nome_fantasia: "",
    documento: "",
    inscricao_estadual: "",
    inscricao_municipal: "",
    telefone: "",
    email: "",
    responsavel_nome: "",
    responsavel_telefone: "",
    cep: "",
    endereco: "",
    numero: "",
    complemento: "",
    bairro: "",
    cidade: "",
    estado: "",
    observacoes: "",
    ativo: true
  };
}

const form = reactive(defaultForm());

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

function assignIfPresent(key: keyof typeof form, value: unknown) {
  if (value == null) return;
  const text = String(value).trim();
  if (!text) return;
  (form[key] as unknown as string) = text;
}

function applyLookupResult(payload: GenericRecord) {
  const documentoAtual = String(form.documento || "").trim();
  assignIfPresent("nome", payload.nome);
  assignIfPresent("nome_fantasia", payload.nome_fantasia || payload.fantasia);
  if (!documentoAtual) {
    assignIfPresent("documento", payload.documento);
  }
  assignIfPresent("inscricao_estadual", payload.inscricao_estadual || payload.ie);
  assignIfPresent("inscricao_municipal", payload.inscricao_municipal);
  assignIfPresent("telefone", payload.telefone);
  assignIfPresent("email", payload.email);
  assignIfPresent("cep", payload.cep);
  assignIfPresent("endereco", payload.endereco || payload.logradouro);
  assignIfPresent("numero", payload.numero);
  assignIfPresent("complemento", payload.complemento);
  assignIfPresent("bairro", payload.bairro);
  assignIfPresent("cidade", payload.cidade || payload.municipio);
  assignIfPresent("estado", payload.estado || payload.uf);
}

async function consultCnpj() {
  lookupCnpjLoading.value = true;
  error.value = "";
  try {
    const payload = await lookupCompanyCnpj(form.documento, form.estado || null);
    applyLookupResult(payload);
    if (payload.cache_hit === true) {
      showSplashInfo("Consulta retornada do cache local para evitar consumo desnecessário dos provedores.");
    } else if (String(payload.source || "").length) {
      showSplashSuccess(`Consulta CNPJ concluída via ${String(payload.source)}.`);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao consultar CNPJ.";
    if (error.value.includes("limite") || error.value.includes("429")) {
      showSplashWarning("Serviços públicos atingiram limite temporário. Aguarde o cooldown e tente novamente.");
    } else {
      showSplashError(error.value);
    }
  } finally {
    lookupCnpjLoading.value = false;
  }
}

async function consultIe() {
  lookupIeLoading.value = true;
  error.value = "";
  try {
    const cnpj = onlyDigits(form.documento);
    if (cnpj.length !== 14) {
      throw new Error("Para consultar inscrição estadual, informe primeiro um CNPJ válido com 14 dígitos.");
    }
    const payload = await lookupCompanyIe(cnpj, form.estado || null);
    applyLookupResult(payload);
    if (payload.cache_hit === true) {
      showSplashInfo("Consulta IE retornada do cache local via CNPJ.");
    } else if (String(payload.source || "").length) {
      showSplashSuccess(`Consulta IE concluída via ${String(payload.source)}.`);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao consultar IE.";
    if (error.value.includes("limite") || error.value.includes("429")) {
      showSplashWarning("Serviços públicos em limite temporário para IE/CNPJ. Aguarde alguns segundos.");
    } else {
      showSplashError(error.value);
    }
  } finally {
    lookupIeLoading.value = false;
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listCompanies({
      search: search.value,
      onlyActive: onlyActive.value
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar empresas.";
  } finally {
    loading.value = false;
  }
}

async function editRow(id: number) {
  error.value = "";
  try {
    const record = await getCompany(id);
    Object.assign(form, defaultForm(), record, {
      ativo: Number(record.ativo) === 1 || record.ativo === true
    });
    modalOpen.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar empresa.";
  }
}

async function persist() {
  saving.value = true;
  error.value = "";
  try {
    await saveCompany({ ...form });
    await load();
    closeModal();
    resetForm();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao salvar empresa.";
  } finally {
    saving.value = false;
  }
}

async function removeRow(id: number) {
  if (!(await appConfirm({ title: "Excluir empresa", message: "Deseja excluir esta empresa usuária?", danger: true, confirmText: "Excluir" }))) return;

  try {
    await deleteCompany(id);
    await load();
    showSplashSuccess("Empresa excluída com sucesso.");
    if (Number(form.id) === id) {
      resetForm();
      closeModal();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao excluir empresa.";
  }
}

onMounted(load);
</script>

<template>
  <BasePage title="Cadastro de empresa usuária" subtitle="Gestão de empresas, identificação fiscal, contato e endereço." icon="building">
    <template #actions>
      <button class="primary" @click="openNewModal">Novo cadastro</button>
    </template>

    <div v-if="error" class="alert error">{{ error }}</div>

    <div class="card grid page-gap">
      <div class="toolbar">
        <div>
          <h3>Empresas cadastradas</h3>
        </div>
        <div class="actions align-end">
          <div class="field min-field">
            <label>Buscar</label>
            <input v-model="search" type="text" placeholder="Nome, documento ou cidade" @keyup.enter="load" />
          </div>
          <AppSwitch v-model="onlyActive" label="Somente ativas" />
          <button class="secondary" :disabled="loading" @click="load">
            {{ loading ? "Carregando..." : "Atualizar" }}
          </button>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Razão social</th>
              <th>Fantasia</th>
              <th>Documento</th>
              <th>Contato</th>
              <th>Cidade/UF</th>
              <th>Status</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="Number(row.id)">
              <td>{{ row.id }}</td>
              <td>{{ row.nome }}</td>
              <td>{{ row.nome_fantasia || '-' }}</td>
              <td>{{ formatCpfCnpj(row.documento) }}</td>
              <td>
                <div>{{ formatPhone(row.telefone) || '-' }}</div>
                <div class="muted-row">{{ row.email || '-' }}</div>
              </td>
              <td>{{ row.cidade || '-' }} / {{ row.estado || '-' }}</td>
              <td>{{ booleanLabel(row.ativo) }}</td>
              <td>
                <div class="compact-actions actions">
                  <button class="secondary" @click="editRow(Number(row.id))">Editar</button>
                  <button class="danger" @click="removeRow(Number(row.id))">Excluir</button>
                </div>
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="8" class="empty-cell">Nenhuma empresa encontrada.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <AppModal
      :open="modalOpen"
      :title="form.id ? 'Editar empresa usuária' : 'Nova empresa usuária'"
      width="xl"
      @close="closeModal"
    >
      <div class="grid page-gap">
        <div class="section-title">Dados principais</div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field">
            <label>Razão social *</label>
            <input v-model="form.nome" type="text" placeholder="Razão social da empresa" />
          </div>
          <div class="field">
            <label>Nome fantasia</label>
            <input v-model="form.nome_fantasia" type="text" placeholder="Nome fantasia" />
          </div>
          <div class="field span-2">
            <label>Documento da entidade *</label>
            <div class="actions stretch-on-mobile">
              <input v-model="form.documento" type="text" placeholder="CNPJ, CPF ou identificador interno" />
              <button class="secondary" type="button" :disabled="lookupCnpjLoading || saving" @click="consultCnpj">
                {{ lookupCnpjLoading ? "Consultando..." : "Consultar CNPJ" }}
              </button>
              <button class="secondary" type="button" :disabled="lookupIeLoading || saving" @click="consultIe">
                {{ lookupIeLoading ? "Consultando..." : "Consultar IE (via CNPJ)" }}
              </button>
            </div>
          </div>
          <div class="grid columns-2 nested-grid mobile-columns-1 span-2">
            <div class="field">
              <label>Inscrição estadual</label>
              <input v-model="form.inscricao_estadual" type="text" placeholder="Inscrição estadual" />
            </div>
            <div class="field">
              <label>Inscrição municipal</label>
              <input v-model="form.inscricao_municipal" type="text" placeholder="Inscrição municipal" />
            </div>
          </div>
          <div class="form-hint span-2">
            Para integrações fiscais, prefira CNPJ ou CPF válidos. Em cadastros internos/localizados, o sistema também aceita identificador simplificado quando a entidade não possui documento fiscal completo.
          </div>
        </div>

        <div class="section-title">Contato</div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field">
            <label>Telefone principal</label>
            <input v-model="form.telefone" type="text" placeholder="(00) 00000-0000" />
          </div>
          <div class="field">
            <label>E-mail</label>
            <input v-model="form.email" type="email" placeholder="contato@empresa.com" />
          </div>
          <div class="field">
            <label>Responsável</label>
            <input v-model="form.responsavel_nome" type="text" placeholder="Nome do responsável" />
          </div>
          <div class="field">
            <label>Telefone do responsável</label>
            <input v-model="form.responsavel_telefone" type="text" placeholder="(00) 00000-0000" />
          </div>
        </div>

        <div class="section-title">Endereço</div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field">
            <label>CEP</label>
            <input v-model="form.cep" type="text" placeholder="00000-000" />
          </div>
          <div class="grid columns-2 nested-grid mobile-columns-1">
            <div class="field">
              <label>UF</label>
              <input v-model="form.estado" type="text" maxlength="2" placeholder="BA" />
            </div>
            <div class="field">
              <label>Cidade</label>
              <input v-model="form.cidade" type="text" placeholder="Cidade" />
            </div>
          </div>
          <div class="field">
            <label>Endereço</label>
            <input v-model="form.endereco" type="text" placeholder="Rua / Avenida" />
          </div>
          <div class="grid columns-2 nested-grid mobile-columns-1">
            <div class="field">
              <label>Número</label>
              <input v-model="form.numero" type="text" placeholder="Número" />
            </div>
            <div class="field">
              <label>Complemento</label>
              <input v-model="form.complemento" type="text" placeholder="Complemento" />
            </div>
          </div>
          <div class="field">
            <label>Bairro</label>
            <input v-model="form.bairro" type="text" placeholder="Bairro" />
          </div>
        </div>

        <div class="section-title">Observações</div>
        <div class="grid columns-2 mobile-columns-1">
          <div class="field span-2">
            <label>Observações</label>
            <textarea v-model="form.observacoes" rows="4" placeholder="Informações adicionais da empresa"></textarea>
          </div>
          <div class="field span-2">
            <AppSwitch v-model="form.ativo" label="Empresa ativa" />
          </div>
        </div>

        <div class="actions">
          <button class="primary" :disabled="saving" @click="persist">
            {{ saving ? "Salvando..." : form.id ? "Atualizar empresa" : "Salvar empresa" }}
          </button>
          <button class="secondary" @click="resetForm">Limpar</button>
        </div>
      </div>
    </AppModal>
  </BasePage>
</template>
