<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row = Record<string, any>;
type Step = {
  key: string;
  name: string;
  type: "approval" | "task";
  assignee_roles: string;
  due_hours: number;
  approve_to: string;
  reject_to: string;
};
const props = defineProps<{ api: Pige360SessionClient }>();
const emit = defineEmits<{ error: [message: string] }>();
const loading = ref(false);
const definitions = ref<Row[]>([]);
const instances = ref<Row[]>([]);
const tasks = ref<Row[]>([]);
const selected = ref<Row | null>(null);
const definitionForm = reactive({
  code: "",
  name: "",
  aggregate_type: "service_request",
});
const steps = ref<Step[]>([
  {
    key: "approval",
    name: "Aprovação",
    type: "approval",
    assignee_roles: "academic_coordinator",
    due_hours: 24,
    approve_to: "completed",
    reject_to: "rejected",
  },
]);
const startForm = reactive({
  definition_id: "",
  aggregate_type: "service_request",
  aggregate_id: "",
  context: "{}",
});
function msg(e: unknown) {
  return e instanceof Error ? e.message : "Falha no workflow";
}
function idem() {
  return `workflow-${crypto.randomUUID()}`;
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
function payloadSteps() {
  return steps.value.map((s) => ({
    ...s,
    assignee_roles: s.assignee_roles
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    due_hours: Number(s.due_hours) || null,
  }));
}
async function load() {
  loading.value = true;
  try {
    const [d, i, t] = await Promise.all([
      props.api.request<Row>("/workflows/definitions"),
      props.api.request<Row>("/workflows/instances"),
      props.api.request<Row>("/workflows/tasks/me?state=open"),
    ]);
    definitions.value = d.items || [];
    instances.value = i.items || [];
    tasks.value = t.items || [];
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
function addStep() {
  const index = steps.value.length + 1;
  steps.value.push({
    key: `step_${index}`,
    name: `Etapa ${index}`,
    type: "approval",
    assignee_roles: "tenant_owner",
    due_hours: 24,
    approve_to: "completed",
    reject_to: "rejected",
  });
}
function removeStep(index: number) {
  if (steps.value.length > 1) steps.value.splice(index, 1);
}
async function createDefinition() {
  loading.value = true;
  try {
    await props.api.request("/workflows/definitions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...definitionForm, steps: payloadSteps() }),
    });
    Object.assign(definitionForm, {
      code: "",
      name: "",
      aggregate_type: "service_request",
    });
    steps.value = [
      {
        key: "approval",
        name: "Aprovação",
        type: "approval",
        assignee_roles: "academic_coordinator",
        due_hours: 24,
        approve_to: "completed",
        reject_to: "rejected",
      },
    ];
    await load();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function publish(row: Row) {
  loading.value = true;
  try {
    await props.api.request(`/workflows/definitions/${row.id}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_version: row.current_version,
        reason: "Publicação pelo administrativo",
      }),
    });
    await load();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function start() {
  loading.value = true;
  try {
    let context: Record<string, unknown> = {};
    try {
      context = JSON.parse(startForm.context || "{}");
    } catch {
      throw new Error("Contexto deve ser JSON válido.");
    }
    await props.api.request("/workflows/instances", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idem(),
      },
      body: JSON.stringify({ ...startForm, context }),
    });
    Object.assign(startForm, {
      definition_id: "",
      aggregate_type: "service_request",
      aggregate_id: "",
      context: "{}",
    });
    await load();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function decide(task: Row, decision: "approve" | "reject" | "complete") {
  loading.value = true;
  try {
    await props.api.request(`/workflows/tasks/${task.id}/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_instance_version: task.instance_version,
        decision,
        comment: `Decisão ${decision} pelo administrativo`,
      }),
    });
    await load();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function detail(row: Row) {
  loading.value = true;
  try {
    selected.value = await props.api.request<Row>(
      `/workflows/instances/${row.id}`,
    );
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section class="workflow-grid">
    <form class="panel" @submit.prevent="createDefinition">
      <div class="panel-title">
        <h2>Definição de workflow</h2>
        <span>versionada</span>
      </div>
      <label
        >Código<input
          v-model="definitionForm.code"
          pattern="[a-z0-9][a-z0-9._-]+"
          placeholder="request.scholarship"
          required /></label
      ><label>Nome<input v-model="definitionForm.name" required /></label
      ><label
        >Agregado<input v-model="definitionForm.aggregate_type" required
      /></label>
      <div v-for="(s, index) in steps" :key="s.key" class="step">
        <div class="step-head">
          <strong>Etapa {{ index + 1 }}</strong
          ><button type="button" class="small" @click="removeStep(index)">
            Remover
          </button>
        </div>
        <label>Chave<input v-model="s.key" required /></label
        ><label>Nome<input v-model="s.name" required /></label>
        <div class="cols">
          <label
            >Tipo<select v-model="s.type">
              <option value="approval">Aprovação</option>
              <option value="task">Tarefa</option>
            </select></label
          ><label
            >SLA (h)<input v-model.number="s.due_hours" type="number" min="1"
          /></label>
        </div>
        <label
          >Papéis responsáveis<input
            v-model="s.assignee_roles"
            placeholder="academic_coordinator, finance_manager"
            required
        /></label>
        <div class="cols">
          <label
            >Ao aprovar<input
              v-model="s.approve_to"
              placeholder="completed ou chave" /></label
          ><label
            >Ao rejeitar<input
              v-model="s.reject_to"
              placeholder="rejected ou chave"
          /></label>
        </div>
      </div>
      <div class="row-actions">
        <button type="button" class="small" @click="addStep">
          Adicionar etapa</button
        ><button class="primary" :disabled="loading">Criar definição</button>
      </div>
    </form>
    <form class="panel" @submit.prevent="start">
      <div class="panel-title">
        <h2>Iniciar processo</h2>
        <span>idempotente</span>
      </div>
      <label
        >Workflow<select v-model="startForm.definition_id" required>
          <option value="">Selecione</option>
          <option
            v-for="d in definitions.filter((x: Row) => x.state === 'published')"
            :key="d.id"
            :value="d.id"
          >
            {{ d.name }} · v{{ d.current_version }}
          </option>
        </select></label
      ><label
        >Tipo do agregado<input
          v-model="startForm.aggregate_type"
          required /></label
      ><label
        >ID do agregado<input
          v-model="startForm.aggregate_id"
          required /></label
      ><label
        >Contexto JSON<textarea
          v-model="startForm.context"
          rows="5"
        ></textarea></label
      ><button class="primary" :disabled="loading">Iniciar workflow</button>
    </form>
  </section>
  <section class="panel">
    <div class="panel-title">
      <h2>Definições</h2>
      <button class="small" @click="load">Atualizar</button>
    </div>
    <table>
      <thead>
        <tr>
          <th>Nome</th>
          <th>Agregado</th>
          <th>Versão</th>
          <th>Estado</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in definitions" :key="d.id">
          <td>
            <strong>{{ d.name }}</strong
            ><small>{{ d.code }}</small>
          </td>
          <td>{{ d.aggregate_type }}</td>
          <td>{{ d.current_version }}</td>
          <td>
            <span
              class="pill"
              :class="d.state === 'published' ? 'ok' : 'warn'"
              >{{ d.state }}</span
            >
          </td>
          <td>
            <button
              v-if="d.state !== 'published'"
              class="small"
              @click="publish(d)"
            >
              Publicar
            </button>
          </td>
        </tr>
        <tr v-if="!definitions.length">
          <td colspan="5" class="empty">Nenhuma definição cadastrada.</td>
        </tr>
      </tbody>
    </table>
  </section>
  <section class="panel">
    <div class="panel-title">
      <h2>Minhas tarefas</h2>
      <span>{{ tasks.length }}</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Etapa</th>
          <th>Agregado</th>
          <th>Prazo</th>
          <th>SLA</th>
          <th>Ações</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in tasks" :key="t.id">
          <td>
            <strong>{{ t.step_name }}</strong
            ><small>{{ t.step_key }}</small>
          </td>
          <td>{{ t.aggregate_type }} · {{ t.aggregate_id }}</td>
          <td>{{ dateBR(t.due_at) }}</td>
          <td>
            <span
              class="pill"
              :class="
                t.sla_state === 'breached'
                  ? 'danger'
                  : t.sla_state === 'overdue'
                    ? 'warn'
                    : 'ok'
              "
              >{{ t.sla_state }}</span
            >
          </td>
          <td class="row-actions">
            <button
              class="small"
              @click="
                decide(t, t.task_type === 'task' ? 'complete' : 'approve')
              "
            >
              {{ t.task_type === "task" ? "Concluir" : "Aprovar" }}</button
            ><button
              v-if="t.task_type === 'approval'"
              class="small danger"
              @click="decide(t, 'reject')"
            >
              Rejeitar
            </button>
          </td>
        </tr>
        <tr v-if="!tasks.length">
          <td colspan="5" class="empty">
            Nenhuma tarefa pendente para seu perfil.
          </td>
        </tr>
      </tbody>
    </table>
  </section>
  <section class="panel">
    <div class="panel-title">
      <h2>Instâncias</h2>
      <span>{{ instances.length }}</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Início</th>
          <th>Agregado</th>
          <th>Versão congelada</th>
          <th>Etapa</th>
          <th>Estado</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in instances" :key="i.id">
          <td>{{ dateBR(i.started_at) }}</td>
          <td>{{ i.aggregate_type }} · {{ i.aggregate_id }}</td>
          <td>v{{ i.definition_version }}</td>
          <td>{{ i.current_step_key || "—" }}</td>
          <td>
            <span
              class="pill"
              :class="
                i.state === 'completed'
                  ? 'ok'
                  : i.state === 'rejected' || i.state === 'cancelled'
                    ? 'danger'
                    : 'warn'
              "
              >{{ i.state }}</span
            >
          </td>
          <td><button class="small" @click="detail(i)">Histórico</button></td>
        </tr>
      </tbody>
    </table>
  </section>
  <section v-if="selected" class="panel">
    <div class="panel-title">
      <h2>Histórico da instância</h2>
      <button class="small" @click="selected = null">Fechar</button>
    </div>
    <div class="timeline">
      <div v-for="e in selected.events" :key="e.id">
        <strong>{{ e.event_type }}</strong
        ><span
          >{{ dateBR(e.occurred_at) }} · {{ e.from_step_key || "início" }} →
          {{ e.to_step_key || e.to_state }}</span
        ><small>{{ e.comment || "" }}</small>
      </div>
    </div>
  </section>
</template>
<style scoped>
.workflow-grid {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 16px;
  margin-bottom: 16px;
}
.workflow-grid form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.step {
  border: 1px solid var(--border, #d8dee8);
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.step-head,
.cols,
.row-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.step-head {
  justify-content: space-between;
}
.cols > * {
  flex: 1;
}
.timeline {
  display: grid;
  gap: 10px;
}
.timeline > div {
  display: grid;
  gap: 3px;
  padding: 10px 12px;
  border-left: 3px solid var(--brand-primary);
  background: rgba(0, 109, 119, 0.05);
}
@media (max-width: 900px) {
  .workflow-grid {
    grid-template-columns: 1fr;
  }
  .cols {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
