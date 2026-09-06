<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import AppModal from "../components/AppModal.vue";
import BasePage from "../components/base/BasePage.vue";
import AppSwitch from "../components/AppSwitch.vue";
import { entityConfigs, type EntityField } from "../config/entities";
import { comboList, deleteEntity, listEntity, saveEntity, type ComboOption } from "../services/crud";
import { booleanLabel } from "../services/format";
import { appConfirm } from "../services/dialog";

const props = defineProps<{
  entityKey: string;
}>();

const config = computed(() => entityConfigs[props.entityKey]);
const rows = ref<Record<string, unknown>[]>([]);
const search = ref("");
const saving = ref(false);
const loading = ref(false);
const error = ref("");
const modalOpen = ref(false);
type FormFieldValue = string | number | boolean | undefined;
type TextBindableValue = string | number | readonly string[] | null | undefined;
const form = reactive<Record<string, FormFieldValue>>({ id: undefined });
const optionsMap = ref<Record<string, ComboOption[]>>({});

function inputValue(value: unknown): TextBindableValue {
  if (typeof value === "string" || typeof value === "number") return value;
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  return value == null ? undefined : String(value);
}

function switchValue(value: FormFieldValue): boolean | number | string | undefined {
  if (typeof value === "boolean" || typeof value === "number" || typeof value === "string") return value;
  return undefined;
}

function normalizeFormValue(value: unknown, fallback: FormFieldValue): FormFieldValue {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  return value == null ? fallback : String(value);
}

function onTextareaInput(key: string, event: Event) {
  form[key] = (event.target as HTMLTextAreaElement).value;
}

function defaultFieldValue(field: EntityField): FormFieldValue {
  if (field.type === "checkbox") return true;
  return "";
}

function closeModal() {
  modalOpen.value = false;
}

function openNewModal() {
  resetForm();
  modalOpen.value = true;
}

function resetForm() {
  Object.keys(form).forEach((key) => delete form[key]);
  form.id = undefined;
  for (const field of config.value.fields) {
    form[field.key] = defaultFieldValue(field);
  }
}

async function loadOptions() {
  const relationFields = config.value.fields.filter((field) => field.type === "select" && field.relationEntity);
  const entries = await Promise.all(
    relationFields.map(async (field) => ({
      key: field.key,
      items: await comboList(field.relationEntity as string)
    }))
  );

  const next: Record<string, ComboOption[]> = {};
  for (const entry of entries) {
    next[entry.key] = entry.items;
  }
  optionsMap.value = next;
}

function getOptionLabel(fieldKey: string, value: unknown): string {
  const options = optionsMap.value[fieldKey] || [];
  const matched = options.find((item) => String(item.id) === String(value));
  return matched?.label || String(value ?? "");
}

function displayValue(column: string, row: Record<string, unknown>): string {
  const value = row[column];
  const field = config.value.fields.find((item) => item.key === column);

  if (field?.type === "checkbox") {
    return booleanLabel(value);
  }

  if (field?.type === "select") {
    return getOptionLabel(field.key, value);
  }

  return String(value ?? "");
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listEntity(config.value.key, search.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar registros.";
  } finally {
    loading.value = false;
  }
}

function editRow(row: Record<string, unknown>) {
  Object.keys(form).forEach((key) => delete form[key]);
  for (const field of config.value.fields) {
    const fallback = defaultFieldValue(field);
    form[field.key] = normalizeFormValue(row[field.key], fallback);
  }
  form.id = normalizeFormValue(row.id, undefined);
  modalOpen.value = true;
}

async function persist() {
  saving.value = true;
  error.value = "";
  try {
    await saveEntity(config.value.key, { ...form });
    await load();
    closeModal();
    resetForm();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao salvar registro.";
  } finally {
    saving.value = false;
  }
}

async function removeRow(id: number) {
  if (!(await appConfirm({ title: "Remover registro", message: "Deseja remover este registro?", danger: true, confirmText: "Remover" }))) return;
  try {
    await deleteEntity(config.value.key, id);
    await load();
    if (Number(form.id) === id) {
      resetForm();
      closeModal();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao remover registro.";
  }
}

onMounted(async () => {
  resetForm();
  await loadOptions();
  await load();
});

watch(
  () => props.entityKey,
  async () => {
    closeModal();
    resetForm();
    await loadOptions();
    await load();
  }
);
</script>

<template>
  <BasePage :title="config.title" subtitle="Cadastro local padronizado com edição e inclusão em modal.">
    <template #actions>
      <input v-model="search" class="titlebar-search" placeholder="Pesquisar..." @keyup.enter="load" />
      <button class="secondary" @click="load">Buscar</button>
      <button class="primary" @click="openNewModal">Novo</button>
    </template>

    <div v-if="error" class="alert error">{{ error }}</div>

    <div class="card">
      <h3 style="margin-top: 0;">Listagem</h3>
      <div v-if="loading" class="muted">Carregando...</div>

      <div class="table-wrap" v-else>
        <table>
          <thead>
            <tr>
              <th v-for="column in config.columns" :key="column">{{ column }}</th>
              <th>ações</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="String(row.id)">
              <td v-for="column in config.columns" :key="column">
                {{ displayValue(column, row) }}
              </td>
              <td>
                <div class="actions compact-actions">
                  <button class="secondary" @click="editRow(row)">Editar</button>
                  <button class="danger" @click="removeRow(Number(row.id))">Excluir</button>
                </div>
              </td>
            </tr>
            <tr v-if="rows.length === 0">
              <td :colspan="config.columns.length + 1" class="muted">Nenhum registro encontrado.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <AppModal
      :open="modalOpen"
      :title="form.id ? `Editar ${config.title}` : `Novo registro de ${config.title}`"
      subtitle="Fluxo ajustado para manutenção em modal, preservando a listagem principal."
      width="lg"
      @close="closeModal"
    >
      <form class="grid" @submit.prevent="persist">
        <div v-for="field in config.fields" :key="field.key" class="field">
          <label v-if="field.type !== 'checkbox'" :for="field.key">
            {{ field.label }}
            <span v-if="field.required" class="required">*</span>
          </label>

          <textarea
            v-if="field.type === 'textarea'"
            :id="field.key"
            :value="inputValue(form[field.key])"
            rows="3"
            :placeholder="field.placeholder"
            @input="onTextareaInput(field.key, $event)"
          />

          <AppSwitch
            v-else-if="field.type === 'checkbox'"
            :model-value="switchValue(form[field.key])"
            :label="field.label"
            @update:model-value="form[field.key] = $event"
          />

          <select
            v-else-if="field.type === 'select'"
            :id="field.key"
            v-model="form[field.key]"
          >
            <option value="">Selecione</option>
            <option v-for="item in optionsMap[field.key] || []" :key="item.id" :value="item.id">
              {{ item.label }}
            </option>
          </select>

          <input
            v-else
            :id="field.key"
            v-model="form[field.key]"
            :placeholder="field.placeholder"
            :type="field.type === 'number'
              ? 'number'
              : field.type === 'date'
                ? 'date'
                : field.type === 'time'
                  ? 'time'
                  : field.type === 'email'
                    ? 'email'
                    : field.type === 'tel'
                      ? 'tel'
                      : field.type === 'password'
                        ? 'password'
                        : 'text'"
          />
        </div>

        <div class="actions">
          <button class="primary" type="submit" :disabled="saving">
            {{ saving ? 'Salvando...' : 'Salvar' }}
          </button>
          <button class="secondary" type="button" @click="resetForm">Limpar</button>
        </div>
      </form>
    </AppModal>
  </BasePage>
</template>
