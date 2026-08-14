<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row = Record<string, any>;

const props = defineProps<{
  api: Pige360SessionClient;
  sessions: Row[];
  references: Row;
}>();
const emit = defineEmits<{
  error: [message: string];
  notice: [message: string];
  refresh: [];
}>();

const selectedSessionId = ref("");
const records = ref<Row[]>([]);
const call = ref<Row | null>(null);
const loading = ref(false);
const saving = ref(false);
const statusOptions = [
  ["present", "Presente"],
  ["absent", "Ausente"],
  ["late", "Atrasado"],
  ["justified_absence", "Falta justificada"],
  ["excused_absence", "Dispensado"],
  ["remote_present", "Presente remoto"],
  ["activity_present", "Atividade externa"],
  ["attendance_pending", "Pendente"],
] as const;

const selectedSession = computed(
  () =>
    props.sessions.find((row: Row) => row.id === selectedSessionId.value) ??
    null,
);
const isReadOnly = computed(() =>
  ["closed", "cancelled", "rescheduled"].includes(
    selectedSession.value?.status,
  ),
);
const pendingCount = computed(
  () =>
    records.value.filter((row) => row.status_code === "attendance_pending")
      .length,
);
const callVersion = computed(() => Number(call.value?.current_version ?? 0));

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return (
    candidate.problem?.detail ||
    (error instanceof Error ? error.message : "Erro inesperado na chamada.")
  );
}
function idempotency(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
function studentLabel(studentId: string): string {
  const student = (props.references?.students ?? []).find(
    (row: Row) => row.id === studentId,
  );
  return student?.label || student?.full_name || studentId;
}
function syncRecords(session: Row, response: Row): void {
  const existing = new Map<string, Row>(
    (response.records ?? []).map((row: Row) => [row.student_id, row]),
  );
  records.value = (session.enrolled_student_ids ?? []).map(
    (studentId: string) => ({
      ...existing.get(studentId),
      student_id: studentId,
      status_code: existing.get(studentId)?.status_code ?? "attendance_pending",
      minutes_present: existing.get(studentId)?.minutes_present ?? null,
      observation: existing.get(studentId)?.observation ?? "",
    }),
  );
}
async function loadAttendance(): Promise<void> {
  if (!selectedSession.value) {
    records.value = [];
    call.value = null;
    return;
  }
  loading.value = true;
  try {
    const response = await props.api.request<Row>(
      `/class-sessions/${selectedSession.value.id}/attendance`,
    );
    call.value = response.call ?? null;
    syncRecords(selectedSession.value, response);
  } catch (error) {
    emit("error", message(error));
  } finally {
    loading.value = false;
  }
}
function selectFirstSession(): void {
  if (!selectedSessionId.value && props.sessions.length)
    selectedSessionId.value = props.sessions[0].id;
  if (selectedSessionId.value && !selectedSession.value)
    selectedSessionId.value = props.sessions[0]?.id ?? "";
}
async function saveDraft(): Promise<void> {
  if (!selectedSession.value || isReadOnly.value) return;
  saving.value = true;
  try {
    await props.api.request<Row>(
      `/class-sessions/${selectedSession.value.id}/attendance`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotency("attendance-draft"),
        },
        body: JSON.stringify({
          records: records.value.map((row) => ({
            student_id: row.student_id,
            status_code: row.status_code,
            minutes_present:
              row.minutes_present === "" ? null : row.minutes_present,
            observation: row.observation || null,
          })),
          mode: "full_list",
          origin: "online",
        }),
      },
    );
    emit("notice", "Rascunho da chamada salvo com auditoria.");
    emit("refresh");
    await loadAttendance();
  } catch (error) {
    emit("error", message(error));
  } finally {
    saving.value = false;
  }
}
async function submit(): Promise<void> {
  if (
    !selectedSession.value ||
    !callVersion.value ||
    pendingCount.value ||
    isReadOnly.value
  )
    return;
  saving.value = true;
  try {
    await props.api.request<Row>(
      `/class-sessions/${selectedSession.value.id}/attendance/submit`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_call_version: callVersion.value,
          origin: "online",
        }),
      },
    );
    emit("notice", "Chamada enviada. A sessão já pode ser fechada.");
    emit("refresh");
    await loadAttendance();
  } catch (error) {
    emit("error", message(error));
  } finally {
    saving.value = false;
  }
}
async function sessionAction(
  action: "start" | "close" | "reopen",
): Promise<void> {
  if (!selectedSession.value) return;
  saving.value = true;
  try {
    await props.api.request<Row>(
      `/class-sessions/${selectedSession.value.id}/${action}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: selectedSession.value.version,
          reason: `Ação ${action} registrada na chamada.`,
        }),
      },
    );
    emit(
      "notice",
      `Sessão ${action === "start" ? "iniciada" : action === "close" ? "fechada" : "reaberta"}.`,
    );
    emit("refresh");
    await loadAttendance();
  } catch (error) {
    emit("error", message(error));
  } finally {
    saving.value = false;
  }
}
function markAllPresent(): void {
  if (isReadOnly.value) return;
  records.value.forEach((row) => {
    row.status_code = "present";
    row.minutes_present = null;
  });
}

watch(() => props.sessions, selectFirstSession, { immediate: true });
watch(selectedSessionId, () => void loadAttendance());
</script>

<template>
  <section class="panel attendance-editor">
    <div class="panel-title attendance-heading">
      <div>
        <h2>Chamada digital</h2>
        <p>
          Registre presença, faltas e atrasos com rascunho versionado e envio
          auditado.
        </p>
      </div>
      <label class="attendance-session-select"
        >Sessão<select
          v-model="selectedSessionId"
          :disabled="loading || !sessions.length"
        >
          <option value="">Selecione uma sessão</option>
          <option
            v-for="session in sessions"
            :key="session.id"
            :value="session.id"
          >
            {{ session.scheduled_start }} · {{ session.status }}
          </option>
        </select></label
      >
    </div>
    <p v-if="!sessions.length" class="empty">
      Agende uma sessão para iniciar a chamada.
    </p>
    <template v-else-if="selectedSession">
      <div class="attendance-toolbar">
        <div>
          <strong>{{ selectedSession.class_group_id }}</strong
          ><span
            class="pill"
            :class="selectedSession.status === 'closed' ? 'ok' : 'warn'"
            >{{ selectedSession.status }}</span
          ><small
            >{{ records.length }} alunos · {{ pendingCount }} pendentes ·
            chamada v{{ callVersion }}</small
          >
        </div>
        <div class="row-actions">
          <button
            v-if="['scheduled', 'ready'].includes(selectedSession.status)"
            class="small"
            :disabled="saving"
            @click="sessionAction('start')"
          >
            Iniciar sessão</button
          ><button
            v-if="
              call?.status === 'submitted' &&
              [
                'attendance_submitted',
                'completed',
                'started',
                'attendance_open',
              ].includes(selectedSession.status)
            "
            class="small ok-btn"
            :disabled="saving"
            @click="sessionAction('close')"
          >
            Fechar sessão</button
          ><button
            v-if="selectedSession.status === 'closed'"
            class="small"
            :disabled="saving"
            @click="sessionAction('reopen')"
          >
            Reabrir
          </button>
        </div>
      </div>
      <div v-if="loading" class="empty">Carregando registros da chamada…</div>
      <template v-else>
        <div class="attendance-actions">
          <button
            class="small"
            :disabled="isReadOnly || saving"
            @click="markAllPresent"
          >
            Marcar todos presentes</button
          ><span v-if="pendingCount" class="attendance-warning"
            >Preencha os {{ pendingCount }} registros pendentes antes de
            enviar.</span
          ><span
            v-else-if="call?.status === 'submitted'"
            class="attendance-success"
            >Chamada enviada e pronta para fechamento.</span
          >
        </div>
        <table class="attendance-table">
          <thead>
            <tr>
              <th>Aluno</th>
              <th>Situação</th>
              <th>Minutos presentes</th>
              <th>Observação</th>
              <th>Versão</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in records" :key="record.student_id">
              <td>
                <strong>{{ studentLabel(record.student_id) }}</strong
                ><small>{{ record.student_id }}</small>
              </td>
              <td>
                <select
                  v-model="record.status_code"
                  :disabled="isReadOnly || saving"
                >
                  <option
                    v-for="option in statusOptions"
                    :key="option[0]"
                    :value="option[0]"
                  >
                    {{ option[1] }}
                  </option>
                </select>
              </td>
              <td>
                <input
                  v-model.number="record.minutes_present"
                  type="number"
                  min="0"
                  max="1440"
                  placeholder="—"
                  :disabled="isReadOnly || saving"
                />
              </td>
              <td>
                <input
                  v-model="record.observation"
                  maxlength="2000"
                  placeholder="Opcional"
                  :disabled="isReadOnly || saving"
                />
              </td>
              <td>v{{ record.version || 0 }}</td>
            </tr>
            <tr v-if="!records.length">
              <td colspan="5" class="empty">
                Esta sessão não possui alunos vinculados.
              </td>
            </tr>
          </tbody>
        </table>
        <div class="attendance-footer">
          <button
            class="small"
            :disabled="isReadOnly || saving || !records.length"
            @click="saveDraft"
          >
            {{ saving ? "Salvando…" : "Salvar rascunho" }}</button
          ><button
            class="primary"
            :disabled="isReadOnly || saving || !callVersion || !!pendingCount"
            @click="submit"
          >
            Enviar chamada
          </button>
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.attendance-heading {
  align-items: flex-end;
}
.attendance-heading p {
  margin: 5px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.attendance-session-select {
  width: min(360px, 100%);
}
.attendance-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
  background: #f7fafb;
  border: 1px solid var(--border);
  border-radius: 12px;
}
.attendance-toolbar strong {
  margin-right: 10px;
}
.attendance-toolbar small {
  display: block;
  color: var(--muted);
  margin-top: 5px;
}
.attendance-actions,
.attendance-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 0;
}
.attendance-warning {
  color: #99650b;
  font-size: 12px;
}
.attendance-success {
  color: #116c50;
  font-size: 12px;
}
.attendance-table {
  min-width: 840px;
}
.attendance-table input,
.attendance-table select {
  padding: 8px 9px;
  border-radius: 8px;
  font-size: 12px;
}
.attendance-footer {
  justify-content: flex-end;
  margin-bottom: 0;
}
@media (max-width: 760px) {
  .attendance-heading,
  .attendance-toolbar,
  .attendance-actions,
  .attendance-footer {
    align-items: stretch;
    flex-direction: column;
  }
  .attendance-session-select {
    width: 100%;
  }
}
</style>
