<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";
type Row = Record<string, any>;
type Field = {
  name: string;
  label: string;
  type: "string" | "email" | "number" | "boolean" | "date";
  required: boolean;
};
const props = defineProps<{ api: Pige360SessionClient }>();
const emit = defineEmits<{ error: [message: string] }>();
const loading = ref(false);
const types = ref<Row[]>([]);
const requests = ref<Row[]>([]);
const notices = ref<Row[]>([]);
const workflows = ref<Row[]>([]);
const detail = ref<Row | null>(null);
const formValues = reactive<Record<string, any>>({});
const typeForm = reactive({
  code: "",
  name: "",
  department: "Secretaria",
  default_sla_hours: 72,
  workflow_definition_id: "",
});
const fields = ref<Field[]>([
  { name: "description", label: "Descrição", type: "string", required: true },
]);
const openForm = reactive({
  request_type: "",
  subject: "",
  priority: "normal",
  description: "",
});
const comment = reactive({ body: "", visibility: "requester" });
const selectedType = computed(() =>
  types.value.find((x) => x.code === openForm.request_type),
);
const selectedVersion = computed(() => {
  const type = selectedType.value;
  return type?.versions?.find(
    (v: Row) => v.version === type.current_version && v.state === "published",
  );
});
const selectedFields = computed<Field[]>(
  () => selectedVersion.value?.form_schema?.fields || [],
);
function msg(e: unknown) {
  return e instanceof Error ? e.message : "Falha nas solicitações";
}
function dateBR(v: any) {
  if (!v) return "—";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(String(v)));
  } catch {
    return String(v);
  }
}
watch(
  () => openForm.request_type,
  () => {
    for (const k of Object.keys(formValues)) delete formValues[k];
  },
);
async function load() {
  loading.value = true;
  try {
    const [t, r, n, w] = await Promise.all([
      props.api.request<Row>("/request-types"),
      props.api.request<Row>("/service-requests"),
      props.api.request<Row>("/notices"),
      props.api
        .request<Row>("/workflows/definitions")
        .catch(() => ({ items: [] })),
    ]);
    types.value = t.items || [];
    requests.value = r.items || [];
    notices.value = n.items || [];
    workflows.value = w.items || [];
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
function addField() {
  fields.value.push({
    name: `field_${fields.value.length + 1}`,
    label: `Campo ${fields.value.length + 1}`,
    type: "string",
    required: false,
  });
}
function removeField(i: number) {
  if (fields.value.length > 1) fields.value.splice(i, 1);
}
async function createType() {
  loading.value = true;
  try {
    await props.api.request("/request-types", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: typeForm.code,
        name: typeForm.name,
        department: typeForm.department,
        default_sla_hours: typeForm.default_sla_hours,
        form_schema: {
          fields: fields.value.map((f) => ({
            name: f.name,
            label: f.label,
            type: f.type,
            required: f.required,
          })),
        },
        workflow: typeForm.workflow_definition_id
          ? { definition_id: typeForm.workflow_definition_id }
          : {},
      }),
    });
    Object.assign(typeForm, {
      code: "",
      name: "",
      department: "Secretaria",
      default_sla_hours: 72,
      workflow_definition_id: "",
    });
    await load();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function publishType(row: Row) {
  try {
    await props.api.request(`/request-types/${row.id}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_version: row.current_version,
        reason: "Tipo publicado pelo administrativo",
      }),
    });
    await load();
  } catch (e) {
    emit("error", msg(e));
  }
}
async function openRequest() {
  loading.value = true;
  try {
    await props.api.request("/service-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...openForm, form_data: { ...formValues } }),
    });
    Object.assign(openForm, {
      request_type: "",
      subject: "",
      priority: "normal",
      description: "",
    });
    for (const k of Object.keys(formValues)) delete formValues[k];
    await load();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function show(row: Row) {
  try {
    detail.value = await props.api.request<Row>(`/service-requests/${row.id}`);
  } catch (e) {
    emit("error", msg(e));
  }
}
async function transition(state: string) {
  if (!detail.value) return;
  try {
    await props.api.request(`/service-requests/${detail.value.id}/transition`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state,
        reason: `Transição para ${state} pelo administrativo`,
      }),
    });
    await show(detail.value);
    await load();
  } catch (e) {
    emit("error", msg(e));
  }
}
async function addComment() {
  if (!detail.value || !comment.body) return;
  try {
    await props.api.request(`/service-requests/${detail.value.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(comment),
    });
    comment.body = "";
    await show(detail.value);
  } catch (e) {
    emit("error", msg(e));
  }
}
onMounted(load);
</script>
<template>
  <section class="req-grid">
    <form class="panel" @submit.prevent="openRequest">
      <div class="panel-title">
        <h2>Abrir solicitação</h2>
        <span>formulário versionado</span>
      </div>
      <label
        >Tipo<select v-model="openForm.request_type" required>
          <option value="">Selecione</option>
          <option
            v-for="t in types.filter((x: Row) => x.state === 'published')"
            :key="t.id"
            :value="t.code"
          >
            {{ t.name }}
          </option>
        </select></label
      ><label>Assunto<input v-model="openForm.subject" required /></label
      ><label
        >Prioridade<select v-model="openForm.priority">
          <option>low</option>
          <option>normal</option>
          <option>high</option>
          <option>urgent</option>
        </select></label
      ><label
        >Descrição<textarea
          v-model="openForm.description"
          rows="3"
        ></textarea></label
      ><label v-for="f in selectedFields" :key="f.name"
        >{{ f.label || f.name
        }}<input
          v-if="f.type !== 'boolean'"
          v-model="formValues[f.name]"
          :type="
            f.type === 'number'
              ? 'number'
              : f.type === 'date'
                ? 'date'
                : f.type === 'email'
                  ? 'email'
                  : 'text'
          "
          :required="f.required" /><input
          v-else
          v-model="formValues[f.name]"
          type="checkbox"
      /></label>
      <p v-if="selectedType?.workflow_instance_id" class="muted">
        Fluxo humano associado.
      </p>
      <button class="primary" :disabled="loading">Abrir protocolo</button>
    </form>
    <form class="panel" @submit.prevent="createType">
      <div class="panel-title">
        <h2>Tipo de solicitação</h2>
        <span>administração</span>
      </div>
      <label
        >Código<input
          v-model="typeForm.code"
          pattern="[a-z0-9][a-z0-9._-]+"
          required /></label
      ><label>Nome<input v-model="typeForm.name" required /></label>
      <div class="cols">
        <label>Departamento<input v-model="typeForm.department" /></label
        ><label
          >SLA (h)<input
            v-model.number="typeForm.default_sla_hours"
            type="number"
            min="1"
        /></label>
      </div>
      <label
        >Workflow<select v-model="typeForm.workflow_definition_id">
          <option value="">Sem workflow humano</option>
          <option
            v-for="w in workflows.filter((x: Row) => x.state === 'published')"
            :key="w.id"
            :value="w.id"
          >
            {{ w.name }} · v{{ w.current_version }}
          </option>
        </select></label
      >
      <div v-for="(f, i) in fields" :key="i" class="field-row">
        <input v-model="f.name" placeholder="nome" required /><input
          v-model="f.label"
          placeholder="Rótulo"
          required
        /><select v-model="f.type">
          <option>string</option>
          <option>email</option>
          <option>number</option>
          <option>boolean</option>
          <option>date</option></select
        ><label class="inline"
          ><input v-model="f.required" type="checkbox" /> obrigatório</label
        ><button type="button" class="small" @click="removeField(i)">×</button>
      </div>
      <div class="row-actions">
        <button type="button" class="small" @click="addField">
          Adicionar campo</button
        ><button class="primary" :disabled="loading">Criar tipo</button>
      </div>
    </form>
  </section>
  <section class="panel">
    <div class="panel-title">
      <h2>Tipos publicados e rascunhos</h2>
      <button class="small" @click="load">Atualizar</button>
    </div>
    <table>
      <thead>
        <tr>
          <th>Tipo</th>
          <th>Departamento</th>
          <th>SLA</th>
          <th>Versão</th>
          <th>Estado</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in types" :key="t.id">
          <td>
            <strong>{{ t.name }}</strong
            ><small>{{ t.code }}</small>
          </td>
          <td>{{ t.department || "—" }}</td>
          <td>{{ t.default_sla_hours }} h</td>
          <td>{{ t.current_version }}</td>
          <td>{{ t.state }}</td>
          <td>
            <button
              v-if="t.state !== 'published'"
              class="small"
              @click="publishType(t)"
            >
              Publicar
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
  <section class="panel">
    <div class="panel-title">
      <h2>Protocolos</h2>
      <span>{{ requests.length }}</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Protocolo</th>
          <th>Assunto</th>
          <th>Tipo</th>
          <th>SLA</th>
          <th>Workflow</th>
          <th>Estado</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in requests" :key="r.id">
          <td>{{ r.protocol }}</td>
          <td>{{ r.subject }}</td>
          <td>{{ r.request_type }} · v{{ r.request_type_version || "—" }}</td>
          <td>{{ dateBR(r.sla_due_at) }}</td>
          <td>{{ r.workflow_instance_id ? "ativo/vinculado" : "—" }}</td>
          <td>
            <span class="pill">{{ r.state }}</span>
          </td>
          <td><button class="small" @click="show(r)">Abrir</button></td>
        </tr>
      </tbody>
    </table>
  </section>
  <section v-if="detail" class="panel">
    <div class="panel-title">
      <h2>{{ detail.protocol }} · {{ detail.subject }}</h2>
      <button class="small" @click="detail = null">Fechar</button>
    </div>
    <p>{{ detail.description }}</p>
    <div class="row-actions">
      <button
        v-for="s in [
          'in_progress',
          'awaiting_requester',
          'resolved',
          'closed',
          'cancelled',
          'reopened',
        ]"
        :key="s"
        class="small"
        @click="transition(s)"
      >
        {{ s }}
      </button>
    </div>
    <div class="comments">
      <article v-for="c in detail.comments" :key="c.id">
        <strong>{{ c.visibility }}</strong>
        <p>{{ c.body }}</p>
        <small>{{ dateBR(c.created_at) }}</small>
      </article>
    </div>
    <form class="comment-form" @submit.prevent="addComment">
      <textarea
        v-model="comment.body"
        rows="2"
        placeholder="Comentário"
        required
      ></textarea
      ><select v-model="comment.visibility">
        <option value="requester">Visível ao solicitante</option>
        <option value="internal">Interno</option></select
      ><button class="primary">Comentar</button>
    </form>
  </section>
  <section class="panel">
    <div class="panel-title"><h2>Avisos visíveis</h2></div>
    <div class="notice-list">
      <article v-for="n in notices.slice(0, 12)" :key="n.id">
        <strong>{{ n.title }}</strong>
        <p>{{ n.body }}</p>
        <small>{{ dateBR(n.created_at) }}</small>
      </article>
    </div>
  </section>
</template>
<style scoped>
.req-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.req-grid form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr 110px auto 36px;
  gap: 6px;
  align-items: center;
}
.comments {
  display: grid;
  gap: 8px;
  margin: 14px 0;
}
.comments article {
  padding: 10px 12px;
  border-left: 3px solid var(--brand-primary);
  background: rgba(0, 109, 119, 0.05);
}
.comment-form {
  display: grid;
  grid-template-columns: 1fr 220px auto;
  gap: 8px;
  align-items: end;
}
@media (max-width: 900px) {
  .req-grid {
    grid-template-columns: 1fr;
  }
  .field-row,
  .comment-form {
    grid-template-columns: 1fr;
  }
}
</style>
