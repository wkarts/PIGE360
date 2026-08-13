<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row = Record<string, any>;
const props = defineProps<{ api: Pige360SessionClient }>();
const emit = defineEmits<{ error: [message: string] }>();
const loading = ref(false);
const tab = ref<"library" | "transport" | "health">("library");
const refs = ref<Row>({ people: [], students: [] });
const items = ref<Row[]>([]),
  loans = ref<Row[]>([]),
  reservations = ref<Row[]>([]),
  fines = ref<Row[]>([]),
  policies = ref<Row[]>([]);
const routes = ref<Row[]>([]),
  riders = ref<Row[]>([]),
  schedules = ref<Row[]>([]),
  occurrences = ref<Row[]>([]);
const healthRecords = ref<Row[]>([]),
  incidents = ref<Row[]>([]),
  medications = ref<Row[]>([]),
  accessLog = ref<Row[]>([]);
const itemForm = reactive({
  inventory_code: "",
  title: "",
  authors: "",
  isbn: "",
  category: "",
  item_type: "book",
});
const loanForm = reactive({ library_item_id: "", person_id: "" });
const policyForm = reactive({
  code: "default",
  effective_from: new Date().toISOString().slice(0, 10),
  max_loan_days: 14,
  max_renewals: 2,
  grace_days: 0,
  daily_fine: "0.00",
  reservation_hold_hours: 48,
});
const routeForm = reactive({
  code: "",
  name: "",
  vehicle: "",
  driver_person_id: "",
  monitor_person_id: "",
  stops_text: "",
});
const riderForm = reactive({
  route_id: "",
  student_id: "",
  boarding_stop: "",
  dropoff_stop: "",
});
const scheduleForm = reactive({
  route_id: "",
  weekdays: [0, 1, 2, 3, 4],
  outbound_time: "07:00",
  return_time: "17:00",
  valid_from: new Date().toISOString().slice(0, 10),
  valid_until: "",
});
const occurrenceForm = reactive({
  route_id: "",
  student_id: "",
  occurrence_type: "delay",
  description: "",
  severity: "normal",
});
const recordForm = reactive({
  person_id: "",
  record_type: "allergy",
  summary: "",
  sensitivity: "restricted",
  valid_from: "",
  valid_until: "",
});
const incidentForm = reactive({
  person_id: "",
  incident_type: "first_aid",
  occurred_at: new Date().toISOString().slice(0, 16),
  location: "",
  summary: "",
  referred_to: "",
  guardian_notified: false,
});
const medicationForm = reactive({
  person_id: "",
  medication_name: "",
  dosage: "",
  instructions: "",
  starts_on: new Date().toISOString().slice(0, 10),
  ends_on: "",
  prescriber: "",
  guardian_person_id: "",
});
const administrationForm = reactive({
  authorization_id: "",
  administered_at: new Date().toISOString().slice(0, 16),
  dosage: "",
  notes: "",
});
function msg(e: unknown) {
  return e instanceof Error ? e.message : "Falha na operação";
}
function dateBR(v: any) {
  if (!v) return "—";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: String(v).includes("T") ? "short" : undefined,
    }).format(new Date(String(v)));
  } catch {
    return String(v);
  }
}
function money(v: any) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(v || 0));
}
function label(list: Row[] | undefined, id: any) {
  return list?.find((x) => x.id === id)?.label || id || "—";
}
function idem(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}
async function post(path: string, body: unknown, key?: string) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (key) headers["Idempotency-Key"] = key;
  return props.api.request(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}
async function loadRefs() {
  try {
    refs.value = await props.api.request<Row>("/references/catalog");
  } catch {
    refs.value = { people: [], students: [] };
  }
}
async function loadLibrary() {
  const [i, l, r, f, p] = await Promise.all([
    props.api.request<Row>("/library/items"),
    props.api.request<Row>("/library/loans"),
    props.api.request<Row>("/library/reservations"),
    props.api.request<Row>("/library/fines"),
    props.api.request<Row>("/library/policies"),
  ]);
  items.value = i.items || [];
  loans.value = l.items || [];
  reservations.value = r.items || [];
  fines.value = f.items || [];
  policies.value = p.items || [];
}
async function loadTransport() {
  const [r, ri, s, o] = await Promise.all([
    props.api.request<Row>("/transport/routes"),
    props.api.request<Row>("/transport/riders"),
    props.api.request<Row>("/transport/schedules"),
    props.api.request<Row>("/transport/occurrences"),
  ]);
  routes.value = r.items || [];
  riders.value = ri.items || [];
  schedules.value = s.items || [];
  occurrences.value = o.items || [];
}
async function loadHealth() {
  const [r, i, m, a] = await Promise.all([
    props.api.request<Row>("/health/records"),
    props.api.request<Row>("/health/incidents"),
    props.api.request<Row>("/health/medication-authorizations"),
    props.api.request<Row>("/health/access-log"),
  ]);
  healthRecords.value = r.items || [];
  incidents.value = i.items || [];
  medications.value = m.items || [];
  accessLog.value = a.items || [];
}
async function load() {
  loading.value = true;
  try {
    await loadRefs();
    await Promise.all([loadLibrary(), loadTransport(), loadHealth()]);
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function op(fn: () => Promise<any>, reload: () => Promise<void>) {
  loading.value = true;
  try {
    await fn();
    await reload();
  } catch (e) {
    emit("error", msg(e));
  } finally {
    loading.value = false;
  }
}
async function createItem() {
  await op(
    () =>
      post("/library/items", {
        ...itemForm,
        authors: itemForm.authors || null,
        isbn: itemForm.isbn || null,
        category: itemForm.category || null,
      }),
    loadLibrary,
  );
  Object.assign(itemForm, {
    inventory_code: "",
    title: "",
    authors: "",
    isbn: "",
    category: "",
    item_type: "book",
  });
}
async function createLoan() {
  await op(
    () => post("/library/loans", { ...loanForm, due_at: null }),
    loadLibrary,
  );
  Object.assign(loanForm, { library_item_id: "", person_id: "" });
}
async function returnLoan(id: string) {
  await op(() => post(`/library/loans/${id}/return`, {}), loadLibrary);
}
async function renewLoan(id: string) {
  await op(
    () =>
      post(`/library/loans/${id}/renew`, {
        reason: "Renovação administrativa",
      }),
    loadLibrary,
  );
}
async function settleFine(id: string, action: "paid" | "waived") {
  await op(
    () =>
      post(`/library/fines/${id}/settle`, {
        action,
        reason: action === "paid" ? "Pagamento registrado" : "Abono autorizado",
      }),
    loadLibrary,
  );
}
async function publishPolicy() {
  await op(() => post("/library/policies", policyForm), loadLibrary);
}
async function createRoute() {
  const stops = routeForm.stops_text
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((name, index) => ({ name, sequence: index + 1 }));
  await op(
    () =>
      post("/transport/routes", {
        ...routeForm,
        driver_person_id: routeForm.driver_person_id || null,
        monitor_person_id: routeForm.monitor_person_id || null,
        stops,
      }),
    loadTransport,
  );
  Object.assign(routeForm, {
    code: "",
    name: "",
    vehicle: "",
    driver_person_id: "",
    monitor_person_id: "",
    stops_text: "",
  });
}
async function assignRider() {
  await op(
    () =>
      post("/transport/riders", {
        ...riderForm,
        boarding_stop: riderForm.boarding_stop || null,
        dropoff_stop: riderForm.dropoff_stop || null,
      }),
    loadTransport,
  );
  Object.assign(riderForm, {
    route_id: "",
    student_id: "",
    boarding_stop: "",
    dropoff_stop: "",
  });
}
async function createSchedule() {
  await op(
    () =>
      post("/transport/schedules", {
        ...scheduleForm,
        outbound_time: scheduleForm.outbound_time || null,
        return_time: scheduleForm.return_time || null,
        valid_until: scheduleForm.valid_until || null,
      }),
    loadTransport,
  );
}
async function createOccurrence() {
  await op(
    () =>
      post("/transport/occurrences", {
        ...occurrenceForm,
        student_id: occurrenceForm.student_id || null,
      }),
    loadTransport,
  );
  Object.assign(occurrenceForm, {
    route_id: "",
    student_id: "",
    occurrence_type: "delay",
    description: "",
    severity: "normal",
  });
}
async function resolveOccurrence(id: string) {
  await op(
    () =>
      post(`/transport/occurrences/${id}/resolve`, {
        resolution: "Ocorrência tratada e encerrada.",
      }),
    loadTransport,
  );
}
async function createRecord() {
  await op(
    () =>
      post("/health/records", {
        ...recordForm,
        details: {},
        valid_from: recordForm.valid_from || null,
        valid_until: recordForm.valid_until || null,
      }),
    loadHealth,
  );
  Object.assign(recordForm, {
    person_id: "",
    record_type: "allergy",
    summary: "",
    sensitivity: "restricted",
    valid_from: "",
    valid_until: "",
  });
}
async function accessRecord(r: Row) {
  const reason = window.prompt(
    "Informe o motivo do acesso ao registro sensível:",
    "Atendimento autorizado",
  );
  if (!reason) return;
  await op(async () => {
    const detail = await post(`/health/records/${r.id}/access`, { reason });
    window.alert(
      `${detail.summary}\n\n${JSON.stringify(detail.details || {}, null, 2)}`,
    );
  }, loadHealth);
}
async function createIncident() {
  await op(
    () =>
      post("/health/incidents", {
        ...incidentForm,
        occurred_at: new Date(incidentForm.occurred_at).toISOString(),
        first_aid: [],
        referred_to: incidentForm.referred_to || null,
      }),
    loadHealth,
  );
}
async function closeIncident(id: string) {
  await op(
    () =>
      post(`/health/incidents/${id}/close`, {
        reason: "Atendimento concluído",
      }),
    loadHealth,
  );
}
async function createMedication() {
  await op(
    () =>
      post("/health/medication-authorizations", {
        ...medicationForm,
        ends_on: medicationForm.ends_on || null,
        prescriber: medicationForm.prescriber || null,
        guardian_person_id: medicationForm.guardian_person_id || null,
        consent_document_id: null,
      }),
    loadHealth,
  );
}
async function administer() {
  await op(
    () =>
      post(
        "/health/medication-administrations",
        {
          ...administrationForm,
          administered_at: new Date(
            administrationForm.administered_at,
          ).toISOString(),
          dosage: administrationForm.dosage || null,
          notes: administrationForm.notes || null,
        },
        idem("medication"),
      ),
    loadHealth,
  );
  Object.assign(administrationForm, {
    authorization_id: "",
    administered_at: new Date().toISOString().slice(0, 16),
    dosage: "",
    notes: "",
  });
}
const openLoans = computed(() => loans.value.filter((x) => x.state === "open"));
onMounted(load);
</script>
<template>
  <section class="service-tabs">
    <button :class="{ selected: tab === 'library' }" @click="tab = 'library'">
      Biblioteca</button
    ><button
      :class="{ selected: tab === 'transport' }"
      @click="tab = 'transport'"
    >
      Transporte</button
    ><button :class="{ selected: tab === 'health' }" @click="tab = 'health'">
      Saúde</button
    ><button class="small refresh" @click="load">Atualizar</button>
  </section>
  <template v-if="tab === 'library'">
    <section class="metrics">
      <article>
        <span>Acervo</span><strong>{{ items.length }}</strong
        ><small>exemplares</small>
      </article>
      <article>
        <span>Empréstimos</span><strong>{{ openLoans.length }}</strong
        ><small>abertos</small>
      </article>
      <article>
        <span>Reservas</span
        ><strong>{{
          reservations.filter((x: Row) => ["queued", "ready"].includes(x.state))
            .length
        }}</strong
        ><small>ativas</small>
      </article>
      <article>
        <span>Multas</span
        ><strong>{{
          fines.filter((x: Row) => x.state === "open").length
        }}</strong
        ><small>pendentes</small>
      </article>
    </section>
    <section class="grid-2 forms">
      <form class="panel" @submit.prevent="createItem">
        <h2>Novo exemplar</h2>
        <div class="cols">
          <label
            >Patrimônio<input
              v-model="itemForm.inventory_code"
              required /></label
          ><label
            >Tipo<select v-model="itemForm.item_type">
              <option value="book">Livro</option>
              <option value="magazine">Revista</option>
              <option value="digital">Digital</option>
              <option value="other">Outro</option>
            </select></label
          >
        </div>
        <label>Título<input v-model="itemForm.title" required /></label
        ><label>Autores<input v-model="itemForm.authors" /></label>
        <div class="cols">
          <label>ISBN<input v-model="itemForm.isbn" /></label
          ><label>Categoria<input v-model="itemForm.category" /></label>
        </div>
        <button class="primary" :disabled="loading">Cadastrar</button>
      </form>
      <form class="panel" @submit.prevent="createLoan">
        <h2>Novo empréstimo</h2>
        <label
          >Exemplar<select v-model="loanForm.library_item_id" required>
            <option value="">Selecione</option>
            <option
              v-for="i in items.filter((x: Row) =>
                ['available', 'reserved'].includes(x.state),
              )"
              :key="i.id"
              :value="i.id"
            >
              {{ i.title }} · {{ i.inventory_code }}
            </option>
          </select></label
        ><label
          >Pessoa<select v-model="loanForm.person_id" required>
            <option value="">Selecione</option>
            <option v-for="p in refs.people || []" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select></label
        ><button class="primary" :disabled="loading">Emprestar</button>
      </form>
    </section>
    <section class="panel">
      <div class="panel-title"><h2>Empréstimos</h2></div>
      <table>
        <thead>
          <tr>
            <th>Exemplar</th>
            <th>Pessoa</th>
            <th>Vencimento</th>
            <th>Renovações</th>
            <th>Multa</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in loans" :key="l.id">
            <td>{{ l.title }}</td>
            <td>{{ label(refs.people, l.person_id) }}</td>
            <td>{{ dateBR(l.due_at) }}</td>
            <td>{{ l.renewal_count || 0 }}</td>
            <td>{{ money(l.fine_amount) }}</td>
            <td class="row-actions">
              <button
                v-if="l.state === 'open'"
                class="small"
                @click="renewLoan(l.id)"
              >
                Renovar</button
              ><button
                v-if="l.state === 'open'"
                class="small"
                @click="returnLoan(l.id)"
              >
                Devolver
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
    <section class="grid-2">
      <div class="panel">
        <h2>Multas</h2>
        <div class="rows">
          <div v-for="f in fines" :key="f.id">
            <div>
              <strong>{{ label(refs.people, f.person_id) }}</strong
              ><small>{{ f.reason }}</small>
            </div>
            <div>
              <strong>{{ money(f.amount) }}</strong
              ><button
                v-if="f.state === 'open'"
                class="small"
                @click="settleFine(f.id, 'paid')"
              >
                Pagar</button
              ><button
                v-if="f.state === 'open'"
                class="small"
                @click="settleFine(f.id, 'waived')"
              >
                Abonar
              </button>
            </div>
          </div>
          <p v-if="!fines.length" class="empty">Sem multas.</p>
        </div>
      </div>
      <form class="panel" @submit.prevent="publishPolicy">
        <h2>Política de circulação</h2>
        <div class="cols">
          <label
            >Vigência<input
              v-model="policyForm.effective_from"
              type="date"
              required /></label
          ><label
            >Dias de empréstimo<input
              v-model.number="policyForm.max_loan_days"
              type="number"
              min="1"
          /></label>
        </div>
        <div class="cols">
          <label
            >Renovações<input
              v-model.number="policyForm.max_renewals"
              type="number"
              min="0" /></label
          ><label
            >Multa/dia<input
              v-model="policyForm.daily_fine"
              type="number"
              min="0"
              step="0.01"
          /></label>
        </div>
        <button class="primary">Publicar nova versão</button
        ><small v-if="policies[0]"
          >Atual: {{ policies[0].code }} v{{ policies[0].version }}</small
        >
      </form>
    </section>
  </template>
  <template v-else-if="tab === 'transport'">
    <section class="metrics">
      <article>
        <span>Rotas</span><strong>{{ routes.length }}</strong
        ><small>ativas</small>
      </article>
      <article>
        <span>Alunos</span><strong>{{ riders.length }}</strong
        ><small>vinculados</small>
      </article>
      <article>
        <span>Agendas</span><strong>{{ schedules.length }}</strong
        ><small>serviços</small>
      </article>
      <article>
        <span>Ocorrências</span
        ><strong>{{
          occurrences.filter((x: Row) => x.state !== "resolved").length
        }}</strong
        ><small>abertas</small>
      </article>
    </section>
    <section class="grid-2 forms">
      <form class="panel" @submit.prevent="createRoute">
        <h2>Nova rota</h2>
        <div class="cols">
          <label>Código<input v-model="routeForm.code" required /></label
          ><label>Veículo<input v-model="routeForm.vehicle" /></label>
        </div>
        <label>Nome<input v-model="routeForm.name" required /></label
        ><label
          >Motorista<select v-model="routeForm.driver_person_id">
            <option value="">Não definido</option>
            <option v-for="p in refs.people || []" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select></label
        ><label
          >Monitor<select v-model="routeForm.monitor_person_id">
            <option value="">Não definido</option>
            <option v-for="p in refs.people || []" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select></label
        ><label
          >Paradas (uma por linha)<textarea
            v-model="routeForm.stops_text"
            rows="4"
          ></textarea></label
        ><button class="primary">Criar rota</button>
      </form>
      <form class="panel" @submit.prevent="assignRider">
        <h2>Vincular aluno</h2>
        <label
          >Rota<select v-model="riderForm.route_id" required>
            <option value="">Selecione</option>
            <option v-for="r in routes" :key="r.id" :value="r.id">
              {{ r.name }}
            </option>
          </select></label
        ><label
          >Aluno<select v-model="riderForm.student_id" required>
            <option value="">Selecione</option>
            <option v-for="s in refs.students || []" :key="s.id" :value="s.id">
              {{ s.label }}
            </option>
          </select></label
        >
        <div class="cols">
          <label>Embarque<input v-model="riderForm.boarding_stop" /></label
          ><label>Desembarque<input v-model="riderForm.dropoff_stop" /></label>
        </div>
        <button class="primary">Vincular</button>
      </form>
    </section>
    <section class="grid-2 forms">
      <form class="panel" @submit.prevent="createSchedule">
        <h2>Agenda da rota</h2>
        <label
          >Rota<select v-model="scheduleForm.route_id" required>
            <option value="">Selecione</option>
            <option v-for="r in routes" :key="r.id" :value="r.id">
              {{ r.name }}
            </option>
          </select></label
        >
        <div class="cols">
          <label
            >Vigência inicial<input
              v-model="scheduleForm.valid_from"
              type="date"
              required /></label
          ><label
            >Vigência final<input
              v-model="scheduleForm.valid_until"
              type="date"
          /></label>
        </div>
        <div class="cols">
          <label
            >Saída<input
              v-model="scheduleForm.outbound_time"
              type="time" /></label
          ><label
            >Retorno<input v-model="scheduleForm.return_time" type="time"
          /></label>
        </div>
        <label
          >Dias da semana
          <div class="weekday-grid">
            <label
              v-for="d in [
                { n: 0, l: 'Seg' },
                { n: 1, l: 'Ter' },
                { n: 2, l: 'Qua' },
                { n: 3, l: 'Qui' },
                { n: 4, l: 'Sex' },
                { n: 5, l: 'Sáb' },
                { n: 6, l: 'Dom' },
              ]"
              :key="d.n"
              class="inline"
              ><input
                v-model="scheduleForm.weekdays"
                type="checkbox"
                :value="d.n"
              />{{ d.l }}</label
            >
          </div></label
        ><button class="primary">Agendar</button>
      </form>
      <form class="panel" @submit.prevent="createOccurrence">
        <h2>Registrar ocorrência</h2>
        <label
          >Rota<select v-model="occurrenceForm.route_id" required>
            <option value="">Selecione</option>
            <option v-for="r in routes" :key="r.id" :value="r.id">
              {{ r.name }}
            </option>
          </select></label
        ><label
          >Aluno<select v-model="occurrenceForm.student_id">
            <option value="">Ocorrência geral</option>
            <option v-for="s in refs.students || []" :key="s.id" :value="s.id">
              {{ s.label }}
            </option>
          </select></label
        >
        <div class="cols">
          <label
            >Tipo<select v-model="occurrenceForm.occurrence_type">
              <option value="delay">Atraso</option>
              <option value="absence">Ausência</option>
              <option value="incident">Incidente</option>
              <option value="vehicle">Veículo</option>
            </select></label
          ><label
            >Severidade<select v-model="occurrenceForm.severity">
              <option value="low">Baixa</option>
              <option value="normal">Normal</option>
              <option value="high">Alta</option>
              <option value="critical">Crítica</option>
            </select></label
          >
        </div>
        <label
          >Descrição<textarea
            v-model="occurrenceForm.description"
            rows="3"
            required
          ></textarea></label
        ><button class="primary">Registrar</button>
      </form>
    </section>
    <section class="panel">
      <h2>Ocorrências</h2>
      <table>
        <thead>
          <tr>
            <th>Data</th>
            <th>Rota</th>
            <th>Aluno</th>
            <th>Tipo</th>
            <th>Estado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in occurrences" :key="o.id">
            <td>{{ dateBR(o.created_at || o.occurred_at) }}</td>
            <td>{{ o.route_name || label(routes, o.route_id) }}</td>
            <td>{{ label(refs.students, o.student_id) }}</td>
            <td>{{ o.occurrence_type }}</td>
            <td>{{ o.state }}</td>
            <td>
              <button
                v-if="o.state !== 'resolved'"
                class="small"
                @click="resolveOccurrence(o.id)"
              >
                Resolver
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </template>
  <template v-else>
    <section class="metrics">
      <article>
        <span>Registros</span><strong>{{ healthRecords.length }}</strong
        ><small>metadados clínicos</small>
      </article>
      <article>
        <span>Ocorrências</span
        ><strong>{{
          incidents.filter((x: Row) => x.state === "open").length
        }}</strong
        ><small>abertas</small>
      </article>
      <article>
        <span>Medicações</span
        ><strong>{{
          medications.filter((x: Row) => x.state === "active").length
        }}</strong
        ><small>autorizações</small>
      </article>
      <article>
        <span>Acessos</span><strong>{{ accessLog.length }}</strong
        ><small>auditados</small>
      </article>
    </section>
    <section class="grid-2 forms">
      <form class="panel" @submit.prevent="createRecord">
        <h2>Registro de saúde</h2>
        <label
          >Pessoa<select v-model="recordForm.person_id" required>
            <option value="">Selecione</option>
            <option v-for="p in refs.people || []" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select></label
        >
        <div class="cols">
          <label>Tipo<input v-model="recordForm.record_type" required /></label
          ><label
            >Sensibilidade<select v-model="recordForm.sensitivity">
              <option value="restricted">Restrito</option>
              <option value="highly_restricted">Altamente restrito</option>
            </select></label
          >
        </div>
        <label
          >Resumo<textarea
            v-model="recordForm.summary"
            rows="3"
            required
          ></textarea></label
        ><button class="primary">Registrar</button>
      </form>
      <form class="panel" @submit.prevent="createIncident">
        <h2>Ocorrência / primeiros socorros</h2>
        <label
          >Pessoa<select v-model="incidentForm.person_id" required>
            <option value="">Selecione</option>
            <option v-for="p in refs.people || []" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select></label
        >
        <div class="cols">
          <label
            >Tipo<input v-model="incidentForm.incident_type" required /></label
          ><label
            >Data/hora<input
              v-model="incidentForm.occurred_at"
              type="datetime-local"
              required
          /></label>
        </div>
        <label>Local<input v-model="incidentForm.location" /></label
        ><label
          >Resumo<textarea
            v-model="incidentForm.summary"
            rows="3"
            required
          ></textarea></label
        ><label class="inline"
          ><input v-model="incidentForm.guardian_notified" type="checkbox" />
          Responsável já foi notificado</label
        ><button class="primary">Registrar ocorrência</button>
      </form>
    </section>
    <section class="grid-2 forms">
      <form class="panel" @submit.prevent="createMedication">
        <h2>Autorizar medicação</h2>
        <label
          >Pessoa<select v-model="medicationForm.person_id" required>
            <option value="">Selecione</option>
            <option v-for="p in refs.people || []" :key="p.id" :value="p.id">
              {{ p.label }}
            </option>
          </select></label
        >
        <div class="cols">
          <label
            >Medicamento<input
              v-model="medicationForm.medication_name"
              required /></label
          ><label
            >Dosagem<input v-model="medicationForm.dosage" required
          /></label>
        </div>
        <label
          >Instruções<textarea
            v-model="medicationForm.instructions"
            rows="3"
            required
          ></textarea>
        </label>
        <div class="cols">
          <label
            >Início<input
              v-model="medicationForm.starts_on"
              type="date"
              required /></label
          ><label
            >Fim<input v-model="medicationForm.ends_on" type="date"
          /></label>
        </div>
        <button class="primary">Criar autorização</button>
      </form>
      <form class="panel" @submit.prevent="administer">
        <h2>Administrar medicação</h2>
        <label
          >Autorização<select
            v-model="administrationForm.authorization_id"
            required
          >
            <option value="">Selecione</option>
            <option
              v-for="m in medications.filter((x: Row) => x.state === 'active')"
              :key="m.id"
              :value="m.id"
            >
              {{ label(refs.people, m.person_id) }} · {{ m.medication_name }} ·
              {{ m.dosage }}
            </option>
          </select></label
        ><label
          >Data/hora<input
            v-model="administrationForm.administered_at"
            type="datetime-local"
            required /></label
        ><label
          >Dosagem aplicada<input v-model="administrationForm.dosage" /></label
        ><label
          >Observações<textarea
            v-model="administrationForm.notes"
            rows="3"
          ></textarea></label
        ><button class="primary">Registrar administração</button>
      </form>
    </section>
    <section class="grid-2">
      <div class="panel">
        <h2>Registros</h2>
        <div class="rows">
          <div v-for="r in healthRecords" :key="r.id">
            <div>
              <strong
                >{{ label(refs.people, r.person_id) }} ·
                {{ r.record_type }}</strong
              ><small>{{ r.summary }} · {{ r.sensitivity }}</small>
            </div>
            <button class="small" @click="accessRecord(r)">Acessar</button>
          </div>
        </div>
      </div>
      <div class="panel">
        <h2>Ocorrências</h2>
        <div class="rows">
          <div v-for="i in incidents" :key="i.id">
            <div>
              <strong
                >{{ label(refs.people, i.person_id) }} ·
                {{ i.incident_type }}</strong
              ><small>{{ dateBR(i.occurred_at) }} · {{ i.summary }}</small>
            </div>
            <button
              v-if="i.state === 'open'"
              class="small"
              @click="closeIncident(i.id)"
            >
              Encerrar
            </button>
          </div>
        </div>
      </div>
    </section>
  </template>
</template>
<style scoped>
.service-tabs {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.service-tabs button {
  border: 1px solid var(--line, #d9e0e7);
  background: var(--surface, #fff);
  padding: 10px 14px;
  border-radius: 10px;
  cursor: pointer;
}
.service-tabs button.selected {
  border-color: var(--brand-primary);
  box-shadow: 0 0 0 1px var(--brand-primary);
}
.service-tabs .refresh {
  margin-left: auto;
}
.rows > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line, #e5e7eb);
}
.rows > div:last-child {
  border-bottom: 0;
}
.rows > div > div {
  display: flex;
  flex-direction: column;
}
.rows > div small {
  opacity: 0.7;
}
.rows button + button {
  margin-left: 6px;
}
.weekday-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
}
@media (max-width: 800px) {
  .service-tabs .refresh {
    margin-left: 0;
  }
  .rows > div {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
