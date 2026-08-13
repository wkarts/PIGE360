<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient, type ApiProblem } from "@pige360/auth";
import MailPanel from "./components/MailPanel.vue";
import ReportingPanel from "./components/ReportingPanel.vue";
import AnalyticsPanel from "./components/AnalyticsPanel.vue";
import CommunicationPanel from "./components/CommunicationPanel.vue";
import WorkflowPanel from "./components/WorkflowPanel.vue";
import RequestsPanel from "./components/RequestsPanel.vue";
import StudentServicesPanel from "./components/StudentServicesPanel.vue";
import CanteenPanel from "./components/CanteenPanel.vue";
import EventsTravelPanel from "./components/EventsTravelPanel.vue";

type Row = Record<string, any>;
type Area =
  | "dashboard"
  | "analytics"
  | "students"
  | "planning"
  | "attendance"
  | "finance"
  | "sales"
  | "canteen"
  | "events"
  | "fiscal"
  | "hr"
  | "requests"
  | "workflows"
  | "communication"
  | "reports"
  | "mail"
  | "integrations"
  | "student_services"
  | "audit";

const api = new Pige360SessionClient();
const ready = ref(false);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const email = ref("");
const password = ref("");
const authenticated = ref(false);
const active = ref<Area>("dashboard");
const dashboard = ref<Row>({
  metrics: {},
  recent_audit: [],
  recent_outbox: [],
  branding: {},
});
const refs = ref<Row>({});
const rows = ref<Row[]>([]);
const secondary = ref<Row[]>([]);
const policies = ref<Row[]>([]);
const teacherAssignments = ref<Row[]>([]);
const allEnrollments = ref<Row[]>([]);
const brand = computed(() => dashboard.value.branding ?? {});
const schoolName = computed(
  () =>
    brand.value.short_name ||
    brand.value.trade_name ||
    brand.value.legal_name ||
    "Instituição",
);
const roleSet = computed(() => new Set(api.claims()?.roles ?? []));
const can = (...roles: string[]) => roles.some((r) => roleSet.value.has(r));
const nav = computed(
  () =>
    [
      ["dashboard", "Visão geral", "⌂", true],
      [
        "analytics",
        "Indicadores",
        "◫",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "secretary",
          "academic_coordinator",
          "finance_manager",
          "finance_operator",
          "hr_manager",
          "personnel_operator",
          "payroll_operator",
          "timekeeping_operator",
          "canteen_manager",
          "pos_operator",
          "inventory_manager",
          "auditor",
          "fiscal_manager",
        ),
      ],
      [
        "students",
        "Secretaria",
        "◎",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "secretary",
          "academic_coordinator",
        ),
      ],
      [
        "planning",
        "Planejamento",
        "▤",
        can(
          "tenant_owner",
          "institution_director",
          "academic_coordinator",
          "teacher",
          "assistant_teacher",
        ),
      ],
      [
        "attendance",
        "Frequência",
        "✓",
        can(
          "tenant_owner",
          "institution_director",
          "academic_coordinator",
          "teacher",
          "assistant_teacher",
        ),
      ],
      [
        "finance",
        "Financeiro",
        "$",
        can(
          "tenant_owner",
          "institution_director",
          "finance_manager",
          "finance_operator",
        ),
      ],
      [
        "sales",
        "Vendas e estoque",
        "▦",
        can(
          "tenant_owner",
          "institution_director",
          "canteen_manager",
          "pos_operator",
          "inventory_manager",
        ),
      ],
      [
        "canteen",
        "Cantina",
        "◈",
        can(
          "tenant_owner",
          "institution_director",
          "canteen_manager",
          "finance_manager",
          "finance_operator",
          "secretary",
        ),
      ],
      [
        "events",
        "Eventos e viagens",
        "☆",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "event_manager",
        ),
      ],
      [
        "fiscal",
        "Fiscal",
        "N",
        can(
          "tenant_owner",
          "institution_director",
          "fiscal_manager",
          "finance_manager",
        ),
      ],
      [
        "hr",
        "RH e Folha",
        "♙",
        can(
          "tenant_owner",
          "institution_director",
          "hr_manager",
          "personnel_operator",
          "payroll_operator",
          "timekeeping_operator",
        ),
      ],
      ["requests", "Solicitações", "☰", true],
      [
        "workflows",
        "Workflows",
        "◇",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "secretary",
          "academic_coordinator",
          "request_agent",
          "finance_manager",
          "hr_manager",
          "auditor",
          "support",
        ),
      ],
      [
        "communication",
        "Comunicação",
        "◌",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "secretary",
          "academic_coordinator",
          "event_manager",
          "finance_manager",
          "hr_manager",
          "request_agent",
          "support",
        ),
      ],
      [
        "reports",
        "Relatórios",
        "▥",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "secretary",
          "academic_coordinator",
          "finance_manager",
          "finance_operator",
          "hr_manager",
          "personnel_operator",
          "payroll_operator",
          "inventory_manager",
          "canteen_manager",
          "auditor",
        ),
      ],
      ["mail", "E-mail", "✉", true],
      [
        "integrations",
        "Integrações",
        "↔",
        can("tenant_owner", "institution_director", "support", "auditor"),
      ],
      [
        "student_services",
        "Serviços ao aluno",
        "♧",
        can(
          "tenant_owner",
          "institution_director",
          "unit_manager",
          "secretary",
          "library_manager",
          "transport_manager",
          "health_operator",
        ),
      ],
      [
        "audit",
        "Auditoria",
        "◉",
        can("tenant_owner", "institution_director", "auditor"),
      ],
    ].filter((x) => x[3]) as [Area, string, string, boolean][],
);

const personForm = reactive({
  full_name: "",
  cpf: "",
  email: "",
  registration_number: "",
});
const enrollmentForm = reactive({
  student_id: "",
  institution_id: "",
  unit_id: "",
  program_id: "",
  curriculum_id: "",
  academic_year_id: "",
  class_group_id: "",
  enrollment_number: "",
  financial_responsible_guardian_id: "",
});
const planForm = reactive({
  institution_id: "",
  unit_id: "",
  academic_period_id: "",
  program_id: "",
  curriculum_id: "",
  class_group_id: "",
  component_id: "",
  teacher_id: "",
  title: "",
  start_date: "",
  end_date: "",
  content: "",
});
const sessionForm = reactive({
  institution_id: "",
  unit_id: "",
  class_group_id: "",
  component_id: "",
  attendance_policy_id: "",
  teacher_id: "",
  scheduled_start: "",
  scheduled_end: "",
});
const financeForm = reactive({
  enrollment_id: "",
  responsible_guardian_id: "",
  description: "Mensalidade escolar",
  total_amount: "",
  count: 12,
  first_due_date: "",
});
const productForm = reactive({
  sku: "",
  barcode: "",
  name: "",
  product_type: "book",
  ncm: "",
  unit: "UN",
  cost: "0.00",
  sale_price: "0.00",
});
const requestForm = reactive({
  request_type: "administrative",
  subject: "",
  description: "",
  priority: "normal",
  department: "Secretaria",
  sla_hours: 72,
});
const integrationForm = reactive({
  provider: "cloudflare",
  name: "Cloudflare",
  base_url: "",
  secret_reference: "",
  allow_private_network: false,
});

function problemMessage(e: unknown) {
  const p = (e as Error & { problem?: ApiProblem })?.problem;
  return p?.detail || (e instanceof Error ? e.message : "Erro inesperado");
}
function idem(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}
function setBrand() {
  const b = brand.value;
  const root = document.documentElement;
  root.style.setProperty("--brand-primary", b.primary_color || "#006D77");
  root.style.setProperty("--brand-secondary", b.secondary_color || "#0D1B2A");
  root.style.setProperty("--brand-accent", b.accent_color || "#F59E0B");
  document.title = `${schoolName.value} — Administração`;
}
async function request<T>(path: string, init: RequestInit = {}) {
  return api.request<T>(path, init);
}
async function jsonPost<T>(path: string, body: unknown, key?: string) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (key) headers["Idempotency-Key"] = key;
  return request<T>(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

async function boot() {
  try {
    await api.initialize();
    authenticated.value = !!api.tokens;
    if (authenticated.value) await loadBase();
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    ready.value = true;
  }
}
async function login() {
  busy.value = true;
  error.value = "";
  try {
    await api.login(email.value, password.value);
    authenticated.value = true;
    await loadBase();
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function logout() {
  await api.logout();
  authenticated.value = false;
  rows.value = [];
  secondary.value = [];
}
async function loadBase() {
  dashboard.value = await request<Row>("/dashboard/operations");
  setBrand();
  try {
    refs.value = await request<Row>("/references/catalog");
  } catch {
    refs.value = {};
  }
  try {
    teacherAssignments.value =
      (await request<Row>("/teacher-assignments")).items || [];
  } catch {
    teacherAssignments.value = [];
  }
  try {
    allEnrollments.value = (await request<Row>("/enrollments")).items || [];
  } catch {
    allEnrollments.value = [];
  }
  await selectArea(active.value);
}
async function selectArea(area: Area) {
  active.value = area;
  error.value = "";
  notice.value = "";
  busy.value = true;
  try {
    if (area === "dashboard") {
      dashboard.value = await request<Row>("/dashboard/operations");
      setBrand();
      rows.value = dashboard.value.recent_audit || [];
      secondary.value = dashboard.value.recent_outbox || [];
    }
    if (
      area === "analytics" ||
      area === "reports" ||
      area === "communication" ||
      area === "workflows" ||
      area === "canteen" ||
      area === "events"
    ) {
      rows.value = [];
      secondary.value = [];
    }
    if (area === "students") {
      rows.value = (await request<Row>("/students")).items || [];
      secondary.value = (await request<Row>("/enrollments")).items || [];
    }
    if (area === "planning") {
      rows.value = (await request<Row>("/teaching-plans")).items || [];
      secondary.value =
        (await request<Row>("/teacher-assignments")).items || [];
    }
    if (area === "attendance") {
      rows.value =
        (await request<Row>("/class-sessions?limit=100")).items || [];
      policies.value = (await request<Row>("/attendance/policies")).items || [];
      secondary.value = (await request<Row>("/attendance/risks")).items || [];
    }
    if (area === "finance") {
      rows.value = (await request<Row>("/finance/contracts")).items || [];
      secondary.value =
        (await request<Row>("/finance/installments")).items || [];
    }
    if (area === "sales") {
      rows.value = (await request<Row>("/products")).items || [];
      secondary.value = (await request<Row>("/sales")).items || [];
    }
    if (area === "fiscal") {
      rows.value = (await request<Row>("/fiscal/documents")).items || [];
      secondary.value = (await request<Row>("/fiscal/rules")).items || [];
    }
    if (area === "hr") {
      rows.value = (await request<Row>("/hr/employment-contracts")).items || [];
      secondary.value = (await request<Row>("/payroll/runs")).items || [];
    }
    if (area === "requests") {
      rows.value = (await request<Row>("/service-requests")).items || [];
      secondary.value = (await request<Row>("/notices")).items || [];
    }
    if (area === "mail" || area === "student_services") {
      rows.value = [];
      secondary.value = [];
    }
    if (area === "integrations") {
      rows.value = (await request<Row>("/integration-connections")).items || [];
      secondary.value =
        (await request<Row>("/integrations/providers/status")).items || [];
    }
    if (area === "audit") {
      const d = await request<Row>("/dashboard/operations");
      rows.value = d.recent_audit || [];
      secondary.value = d.recent_outbox || [];
    }
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}

async function createStudent() {
  busy.value = true;
  try {
    const person = await jsonPost<Row>(
      "/people",
      {
        full_name: personForm.full_name,
        cpf: personForm.cpf || null,
        email: personForm.email || null,
      },
      idem("person"),
    );
    await jsonPost("/students", {
      person_id: person.id,
      registration_number: personForm.registration_number,
    });
    notice.value = "Aluno cadastrado com sucesso.";
    Object.assign(personForm, {
      full_name: "",
      cpf: "",
      email: "",
      registration_number: "",
    });
    await selectArea("students");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function createEnrollment() {
  busy.value = true;
  try {
    const body = {
      ...enrollmentForm,
      class_group_id: enrollmentForm.class_group_id || null,
      financial_responsible_guardian_id:
        enrollmentForm.financial_responsible_guardian_id || null,
    };
    await jsonPost("/enrollments", body, idem("enrollment"));
    notice.value = "Pré-matrícula criada.";
    await selectArea("students");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function activateEnrollment(row: Row) {
  try {
    await jsonPost(`/enrollments/${row.id}/activate`, {
      expected_version: row.version,
      reason: "Ativação pelo administrativo",
    });
    await selectArea("students");
  } catch (e) {
    error.value = problemMessage(e);
  }
}
async function createPlan() {
  busy.value = true;
  try {
    await jsonPost(
      "/teaching-plans",
      {
        institution_id: planForm.institution_id,
        unit_id: planForm.unit_id,
        academic_period_id: planForm.academic_period_id,
        program_id: planForm.program_id || null,
        curriculum_id: planForm.curriculum_id,
        class_group_id: planForm.class_group_id,
        component_id: planForm.component_id,
        teacher_ids: [planForm.teacher_id],
        plan_type: "weekly",
        title: planForm.title,
        start_date: planForm.start_date,
        end_date: planForm.end_date,
        objectives: [],
        skills: [],
        competencies: [],
        curriculum_links: [],
        content: planForm.content.split("\n").filter(Boolean),
        methodologies: [],
        resources: [],
        accommodations: [],
        assessments: [],
        homework: [],
        references: [],
        attachments: [],
        approval_required: true,
      },
      idem("teaching-plan"),
    );
    notice.value = "Planejamento criado.";
    await selectArea("planning");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function planAction(
  row: Row,
  action: "submit" | "approve" | "request-changes",
) {
  try {
    await jsonPost(`/teaching-plans/${row.id}/${action}`, {
      reason:
        action === "approve"
          ? "Planejamento aprovado"
          : "Atualização de fluxo pedagógico",
      expected_version: row.current_version,
      comments: null,
    });
    await selectArea("planning");
  } catch (e) {
    error.value = problemMessage(e);
  }
}
async function createSession() {
  busy.value = true;
  try {
    await jsonPost(
      "/class-sessions",
      {
        institution_id: sessionForm.institution_id,
        unit_id: sessionForm.unit_id,
        class_group_id: sessionForm.class_group_id,
        component_id: sessionForm.component_id,
        attendance_policy_id: sessionForm.attendance_policy_id,
        scheduled_start: sessionForm.scheduled_start,
        scheduled_end: sessionForm.scheduled_end,
        modality: "regular",
        enrolled_student_ids: (
          (await request<Row>(`/enrollments?state=active`)).items || []
        )
          .filter((x: Row) => x.class_group_id === sessionForm.class_group_id)
          .map((x: Row) => x.student_id),
        teacher_ids: [sessionForm.teacher_id],
      },
      idem("class-session"),
    );
    notice.value = "Sessão de aula criada.";
    await selectArea("attendance");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function sessionAction(row: Row, action: "start" | "close" | "reopen") {
  try {
    await jsonPost(`/class-sessions/${row.id}/${action}`, {
      reason: "Operação administrativa registrada",
      expected_version: row.version,
    });
    await selectArea("attendance");
  } catch (e) {
    error.value = problemMessage(e);
  }
}
async function createFinancial() {
  busy.value = true;
  try {
    const contract = await jsonPost<Row>("/finance/contracts", {
      enrollment_id: financeForm.enrollment_id || null,
      responsible_guardian_id: financeForm.responsible_guardian_id || null,
      description: financeForm.description,
      total_amount: financeForm.total_amount,
      competence_rule: "billing",
    });
    await jsonPost(`/finance/contracts/${contract.id}/installments`, {
      count: Number(financeForm.count),
      first_due_date: financeForm.first_due_date,
      interval_months: 1,
    });
    notice.value = "Contrato e parcelas gerados.";
    await selectArea("finance");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function createProduct() {
  busy.value = true;
  try {
    await jsonPost("/products", productForm);
    notice.value = "Produto cadastrado.";
    await selectArea("sales");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function createRequest() {
  busy.value = true;
  try {
    await jsonPost("/service-requests", requestForm);
    notice.value = "Solicitação criada.";
    await selectArea("requests");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
function label(items: Row[] | undefined, id: string) {
  return items?.find((x) => x.id === id)?.label || id;
}
function money(v: any) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(v || 0));
}
function dateBR(v: any) {
  if (!v) return "—";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: String(v).includes("T") ? "short" : undefined,
    }).format(new Date(v));
  } catch {
    return String(v);
  }
}

function integrationCapabilities(provider: string) {
  if (provider === "cloudflare") return ["dns", "custom_hostnames"];
  if (provider === "mailcow") return ["mailboxes"];
  if (provider === "evolution") return ["send_text"];
  return [];
}
async function createIntegration() {
  busy.value = true;
  error.value = "";
  try {
    const config: Row = {};
    if (integrationForm.base_url.trim())
      config.base_url = integrationForm.base_url.trim();
    if (integrationForm.allow_private_network)
      config.allow_private_network = true;
    await jsonPost("/integration-connections", {
      provider: integrationForm.provider,
      name: integrationForm.name,
      environment: "production",
      capabilities: integrationCapabilities(integrationForm.provider),
      secret_reference: integrationForm.secret_reference || null,
      config,
    });
    notice.value =
      "Conexão registrada. O segredo permanece fora do banco e do frontend.";
    await selectArea("integrations");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}
async function testIntegration(row: Row) {
  busy.value = true;
  error.value = "";
  try {
    const result = await jsonPost<Row>(
      `/integration-connections/${row.id}/test`,
      {},
    );
    notice.value = `${row.name}: ${result.status} (${result.latency_ms} ms)`;
    await selectArea("integrations");
  } catch (e) {
    error.value = problemMessage(e);
  } finally {
    busy.value = false;
  }
}

onMounted(boot);
</script>

<template>
  <div v-if="!ready" class="center">
    <div class="spinner"></div>
    <p>Inicializando ambiente da instituição…</p>
  </div>
  <div v-else-if="!authenticated" class="login-page">
    <form class="login-card" @submit.prevent="login">
      <div class="school-mark">◆</div>
      <span class="eyebrow">Acesso institucional</span>
      <h1>Administração Escolar</h1>
      <p>Entre com sua conta autorizada neste domínio.</p>
      <label
        >E-mail<input
          v-model="email"
          type="email"
          autocomplete="username"
          required /></label
      ><label
        >Senha<input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
      /></label>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="primary" :disabled="busy">
        {{ busy ? "Entrando…" : "Entrar" }}
      </button>
    </form>
  </div>
  <div v-else class="app-shell" data-surface="tenant">
    <aside>
      <div class="brand">
        <div class="mark">◆</div>
        <div>
          <strong>{{ schoolName }}</strong
          ><small>Administração</small>
        </div>
      </div>
      <nav>
        <button
          v-for="item in nav"
          :key="item[0]"
          :class="{ active: active === item[0] }"
          @click="selectArea(item[0])"
        >
          <span>{{ item[2] }}</span
          >{{ item[1] }}
        </button>
      </nav>
      <div class="aside-footer">
        <small>{{ api.claims()?.email }}</small
        ><button @click="logout">Sair</button>
      </div>
    </aside>
    <main>
      <header>
        <div>
          <span class="eyebrow">{{ schoolName }}</span>
          <h1>
            {{
              nav.find(
                (n: [Area, string, string, boolean]) => n[0] === active,
              )?.[1]
            }}
          </h1>
        </div>
        <div class="header-actions">
          <span class="connection">● Online</span
          ><button @click="selectArea(active)">Atualizar</button>
        </div>
      </header>
      <div v-if="error" class="flash error">
        {{ error }}<button @click="error = ''">×</button>
      </div>
      <div v-if="notice" class="flash success">
        {{ notice }}<button @click="notice = ''">×</button>
      </div>
      <div v-if="busy" class="loading-line"></div>

      <template v-if="active === 'dashboard'">
        <section class="metrics">
          <article>
            <span>Alunos ativos</span
            ><strong>{{ dashboard.metrics?.active_students ?? 0 }}</strong
            ><small>cadastros ativos</small>
          </article>
          <article>
            <span>Matrículas</span
            ><strong>{{ dashboard.metrics?.active_enrollments ?? 0 }}</strong
            ><small>matrículas ativas</small>
          </article>
          <article>
            <span>Parcelas abertas</span
            ><strong>{{ dashboard.metrics?.open_installments ?? 0 }}</strong
            ><small>financeiro</small>
          </article>
          <article>
            <span>Chamadas pendentes</span
            ><strong>{{
              dashboard.metrics?.pending_attendance_sessions ?? 0
            }}</strong
            ><small>sessões a concluir</small>
          </article>
          <article>
            <span>Solicitações</span
            ><strong>{{ dashboard.metrics?.open_requests ?? 0 }}</strong
            ><small>em andamento</small>
          </article>
          <article>
            <span>Eventos pendentes</span
            ><strong>{{ dashboard.metrics?.unpublished_outbox ?? 0 }}</strong
            ><small>outbox transacional</small>
          </article>
        </section>
        <section class="grid-2">
          <div class="panel">
            <div class="panel-title"><h2>Auditoria recente</h2></div>
            <table>
              <thead>
                <tr>
                  <th>Ação</th>
                  <th>Entidade</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in dashboard.recent_audit" :key="r.id">
                  <td>{{ r.action }}</td>
                  <td>{{ r.aggregate_type }}</td>
                  <td>{{ dateBR(r.created_at) }}</td>
                </tr>
                <tr v-if="!dashboard.recent_audit?.length">
                  <td colspan="3" class="empty">
                    Nenhuma atividade registrada.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="panel">
            <div class="panel-title"><h2>Eventos de domínio</h2></div>
            <table>
              <thead>
                <tr>
                  <th>Evento</th>
                  <th>Tentativas</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in dashboard.recent_outbox" :key="r.id">
                  <td>{{ r.event_type }}</td>
                  <td>{{ r.attempts }}</td>
                  <td>
                    <span
                      class="pill"
                      :class="r.published_at ? 'ok' : 'warn'"
                      >{{ r.published_at ? "Publicado" : "Pendente" }}</span
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <template v-else-if="active === 'students'">
        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="createStudent">
            <h2>Novo aluno</h2>
            <label
              >Nome completo<input v-model="personForm.full_name" required
            /></label>
            <div class="cols">
              <label>CPF<input v-model="personForm.cpf" /></label
              ><label
                >E-mail<input v-model="personForm.email" type="email"
              /></label>
            </div>
            <label
              >Matrícula interna<input
                v-model="personForm.registration_number"
                required /></label
            ><button class="primary">Cadastrar pessoa e aluno</button>
          </form>
          <form class="panel" @submit.prevent="createEnrollment">
            <h2>Nova matrícula</h2>
            <label
              >Aluno<select v-model="enrollmentForm.student_id" required>
                <option value="">Selecione</option>
                <option v-for="x in refs.students" :key="x.id" :value="x.id">
                  {{ x.label }}
                </option>
              </select></label
            >
            <div class="cols">
              <label
                >Instituição<select
                  v-model="enrollmentForm.institution_id"
                  required
                >
                  <option
                    v-for="x in refs.institutions"
                    :key="x.id"
                    :value="x.id"
                  >
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Unidade<select v-model="enrollmentForm.unit_id" required>
                  <option v-for="x in refs.units" :key="x.id" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <div class="cols">
              <label
                >Programa<select v-model="enrollmentForm.program_id" required>
                  <option v-for="x in refs.programs" :key="x.id" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Currículo<select
                  v-model="enrollmentForm.curriculum_id"
                  required
                >
                  <option v-for="x in refs.curricula" :key="x.id" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <div class="cols">
              <label
                >Ano letivo<select
                  v-model="enrollmentForm.academic_year_id"
                  required
                >
                  <option
                    v-for="x in refs.academic_years"
                    :key="x.id"
                    :value="x.id"
                  >
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Turma<select v-model="enrollmentForm.class_group_id">
                  <option value="">Sem turma</option>
                  <option
                    v-for="x in refs.class_groups"
                    :key="x.id"
                    :value="x.id"
                  >
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <label
              >Número da matrícula<input
                v-model="enrollmentForm.enrollment_number"
                required /></label
            ><button class="primary">Criar pré-matrícula</button>
          </form>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>Alunos</h2>
            <span>{{ rows.length }} registros</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Aluno</th>
                <th>Matrícula</th>
                <th>CPF</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ r.full_name }}</td>
                <td>{{ r.registration_number }}</td>
                <td>{{ r.cpf || "—" }}</td>
                <td>
                  <span class="pill ok">{{ r.state }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
        <section class="panel">
          <div class="panel-title"><h2>Matrículas</h2></div>
          <table>
            <thead>
              <tr>
                <th>Aluno</th>
                <th>Programa</th>
                <th>Turma</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in secondary" :key="r.id">
                <td>{{ r.student_name }}</td>
                <td>{{ r.program_name }}</td>
                <td>{{ r.class_group_name || "—" }}</td>
                <td>{{ r.state }}</td>
                <td>
                  <button
                    v-if="r.state !== 'active'"
                    class="small"
                    @click="activateEnrollment(r)"
                  >
                    Ativar
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'planning'">
        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="createPlan">
            <h2>Novo planejamento semanal</h2>
            <div class="cols">
              <label
                >Instituição<select v-model="planForm.institution_id" required>
                  <option v-for="x in refs.institutions" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Unidade<select v-model="planForm.unit_id" required>
                  <option v-for="x in refs.units" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <div class="cols">
              <label
                >Período acadêmico<select
                  v-model="planForm.academic_period_id"
                  required
                >
                  <option v-for="x in refs.academic_periods" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Programa<select v-model="planForm.program_id">
                  <option v-for="x in refs.programs" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <div class="cols">
              <label
                >Currículo<select v-model="planForm.curriculum_id" required>
                  <option v-for="x in refs.curricula" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Turma<select v-model="planForm.class_group_id" required>
                  <option v-for="x in refs.class_groups" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <div class="cols">
              <label
                >Componente<select v-model="planForm.component_id" required>
                  <option v-for="x in refs.components" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Professor<select v-model="planForm.teacher_id" required>
                  <option v-for="x in secondary" :value="x.user_id">
                    {{ x.teacher_name }} — {{ x.class_group_name }}
                  </option>
                </select></label
              >
            </div>
            <label>Título<input v-model="planForm.title" required /></label>
            <div class="cols">
              <label
                >Início<input
                  v-model="planForm.start_date"
                  type="date"
                  required /></label
              ><label
                >Fim<input v-model="planForm.end_date" type="date" required
              /></label>
            </div>
            <label
              >Conteúdos, um por linha<textarea
                v-model="planForm.content"
                rows="4"
              ></textarea></label
            ><button class="primary">Criar planejamento</button>
          </form>
          <div class="panel">
            <h2>Fluxo pedagógico</h2>
            <p>
              Os planos permanecem versionados. Aprovação e devolução não
              alteram versões executadas retroativamente.
            </p>
            <ul class="checklist">
              <li>Alinhamento curricular</li>
              <li>Revisão pela coordenação</li>
              <li>Planejado versus ministrado</li>
              <li>Reposição e execução parcial auditadas</li>
            </ul>
          </div>
        </section>
        <section class="panel">
          <table>
            <thead>
              <tr>
                <th>Plano</th>
                <th>Período</th>
                <th>Estado</th>
                <th>Versão</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>
                  <strong>{{ r.title }}</strong
                  ><small
                    >{{ label(refs.class_groups, r.class_group_id) }} ·
                    {{ label(refs.components, r.component_id) }}</small
                  >
                </td>
                <td>{{ r.start_date }} → {{ r.end_date }}</td>
                <td>
                  <span class="pill">{{ r.status }}</span>
                </td>
                <td>{{ r.current_version }}</td>
                <td class="row-actions">
                  <button
                    v-if="
                      r.status === 'draft' || r.status === 'changes_requested'
                    "
                    class="small"
                    @click="planAction(r, 'submit')"
                  >
                    Enviar</button
                  ><button
                    v-if="
                      r.status === 'submitted_for_review' &&
                      can(
                        'tenant_owner',
                        'institution_director',
                        'academic_coordinator',
                      )
                    "
                    class="small ok-btn"
                    @click="planAction(r, 'approve')"
                  >
                    Aprovar</button
                  ><button
                    v-if="
                      r.status === 'submitted_for_review' &&
                      can(
                        'tenant_owner',
                        'institution_director',
                        'academic_coordinator',
                      )
                    "
                    class="small"
                    @click="planAction(r, 'request-changes')"
                  >
                    Devolver
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'attendance'">
        <section class="grid-2 forms">
          <form
            v-if="
              can(
                'tenant_owner',
                'institution_director',
                'academic_coordinator',
              )
            "
            class="panel"
            @submit.prevent="createSession"
          >
            <h2>Nova sessão de aula</h2>
            <div class="cols">
              <label
                >Instituição<select
                  v-model="sessionForm.institution_id"
                  required
                >
                  <option v-for="x in refs.institutions" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Unidade<select v-model="sessionForm.unit_id" required>
                  <option v-for="x in refs.units" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <div class="cols">
              <label
                >Turma<select v-model="sessionForm.class_group_id" required>
                  <option v-for="x in refs.class_groups" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              ><label
                >Componente<select v-model="sessionForm.component_id" required>
                  <option v-for="x in refs.components" :value="x.id">
                    {{ x.label }}
                  </option>
                </select></label
              >
            </div>
            <label
              >Política<select
                v-model="sessionForm.attendance_policy_id"
                required
              >
                <option v-for="x in policies" :value="x.id">
                  {{ x.name }}
                </option>
              </select></label
            ><label
              >Professor<select v-model="sessionForm.teacher_id" required>
                <option v-for="x in teacherAssignments" :value="x.user_id">
                  {{ x.label }}
                </option></select
              ><small>Use atribuição docente cadastrada.</small></label
            >
            <div class="cols">
              <label
                >Início<input
                  v-model="sessionForm.scheduled_start"
                  type="datetime-local"
                  required /></label
              ><label
                >Fim<input
                  v-model="sessionForm.scheduled_end"
                  type="datetime-local"
                  required
              /></label>
            </div>
            <button class="primary">Agendar sessão</button>
          </form>
          <div class="panel">
            <h2>Risco de frequência</h2>
            <div v-if="secondary.length" class="risk-list">
              <div v-for="r in secondary" :key="r.student_id">
                <strong>{{ label(refs.students, r.student_id) }}</strong
                ><span>{{ r.percentage }}%</span
                ><span
                  class="pill"
                  :class="r.level === 'critical' ? 'danger' : 'warn'"
                  >{{ r.level }}</span
                >
              </div>
            </div>
            <p v-else class="empty">Nenhum risco calculado no momento.</p>
          </div>
        </section>
        <section class="panel">
          <table>
            <thead>
              <tr>
                <th>Data</th>
                <th>Turma</th>
                <th>Componente</th>
                <th>Estado</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ dateBR(r.scheduled_start) }}</td>
                <td>{{ label(refs.class_groups, r.class_group_id) }}</td>
                <td>{{ label(refs.components, r.component_id) }}</td>
                <td>
                  <span class="pill">{{ r.status }}</span>
                </td>
                <td class="row-actions">
                  <button
                    v-if="['scheduled', 'ready'].includes(r.status)"
                    class="small"
                    @click="sessionAction(r, 'start')"
                  >
                    Iniciar</button
                  ><button
                    v-if="
                      [
                        'attendance_submitted',
                        'completed',
                        'started',
                        'attendance_open',
                      ].includes(r.status)
                    "
                    class="small"
                    @click="sessionAction(r, 'close')"
                  >
                    Fechar</button
                  ><button
                    v-if="
                      r.status === 'closed' &&
                      can(
                        'tenant_owner',
                        'institution_director',
                        'academic_coordinator',
                      )
                    "
                    class="small"
                    @click="sessionAction(r, 'reopen')"
                  >
                    Reabrir
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'finance'">
        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="createFinancial">
            <h2>Novo contrato financeiro</h2>
            <label
              >Matrícula<select v-model="financeForm.enrollment_id">
                <option value="">Sem vínculo</option>
                <option v-for="x in allEnrollments" :key="x.id" :value="x.id">
                  {{ x.student_name }} — {{ x.enrollment_number }}
                </option>
              </select></label
            ><label
              >Descrição<input v-model="financeForm.description" required
            /></label>
            <div class="cols">
              <label
                >Valor total<input
                  v-model="financeForm.total_amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  required /></label
              ><label
                >Parcelas<input
                  v-model.number="financeForm.count"
                  type="number"
                  min="1"
                  max="120"
                  required
              /></label>
            </div>
            <label
              >Primeiro vencimento<input
                v-model="financeForm.first_due_date"
                type="date"
                required /></label
            ><button class="primary">Gerar contrato e parcelas</button>
          </form>
          <div class="panel">
            <h2>Parcelas abertas</h2>
            <div class="big-number">
              {{
                secondary.filter((x: Row) =>
                  ["open", "partial"].includes(x.state),
                ).length
              }}
            </div>
            <p>Todos os pagamentos são rateados e o subledger é preservado.</p>
          </div>
        </section>
        <section class="panel">
          <table>
            <thead>
              <tr>
                <th>Contrato</th>
                <th>Aluno/Matrícula</th>
                <th>Valor</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ r.description }}</td>
                <td>{{ r.enrollment_id || "—" }}</td>
                <td>{{ money(r.total_amount) }}</td>
                <td>
                  <span class="pill">{{ r.state }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'sales'">
        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="createProduct">
            <h2>Novo produto</h2>
            <div class="cols">
              <label>SKU<input v-model="productForm.sku" required /></label
              ><label
                >Código de barras<input v-model="productForm.barcode"
              /></label>
            </div>
            <label>Produto<input v-model="productForm.name" required /></label>
            <div class="cols">
              <label>NCM<input v-model="productForm.ncm" /></label
              ><label>Unidade<input v-model="productForm.unit" /></label>
            </div>
            <div class="cols">
              <label
                >Custo<input
                  v-model="productForm.cost"
                  type="number"
                  step="0.01" /></label
              ><label
                >Venda<input
                  v-model="productForm.sale_price"
                  type="number"
                  step="0.01"
                  required
              /></label>
            </div>
            <button class="primary">Cadastrar produto</button>
          </form>
          <div class="panel">
            <h2>Vendas recentes</h2>
            <div class="big-number">{{ secondary.length }}</div>
            <p>
              Venda integra pagamento, estoque, solicitação fiscal e auditoria.
            </p>
          </div>
        </section>
        <section class="panel">
          <table>
            <thead>
              <tr>
                <th>Produto</th>
                <th>SKU</th>
                <th>Preço</th>
                <th>Estoque</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ r.name }}</td>
                <td>{{ r.sku }}</td>
                <td>{{ money(r.sale_price) }}</td>
                <td>{{ r.stock_quantity ?? 0 }}</td>
                <td>{{ r.state }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'canteen'"
        ><CanteenPanel :api="api" @error="error = $event"
      /></template>
      <template v-else-if="active === 'events'"
        ><EventsTravelPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'fiscal'">
        <section class="metrics">
          <article>
            <span>Documentos</span><strong>{{ rows.length }}</strong
            ><small>eventos fiscais persistidos</small>
          </article>
          <article>
            <span>Regras vigentes</span><strong>{{ secondary.length }}</strong
            ><small>rulesets versionados</small>
          </article>
          <article>
            <span>Ambiente</span><strong>Por perfil</strong
            ><small>homologação/produção</small>
          </article>
        </section>
        <section class="panel">
          <table>
            <thead>
              <tr>
                <th>Documento</th>
                <th>Origem</th>
                <th>Ambiente</th>
                <th>Estado</th>
                <th>Atualização</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ r.document_type }}</td>
                <td>{{ r.source_type }} / {{ r.source_id }}</td>
                <td>{{ r.environment }}</td>
                <td>
                  <span class="pill">{{ r.state }}</span>
                </td>
                <td>{{ dateBR(r.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'hr'">
        <section class="metrics">
          <article>
            <span>Contratos ativos</span
            ><strong>{{
              rows.filter((x: Row) => x.state === "active").length
            }}</strong
            ><small>vínculos de trabalho</small>
          </article>
          <article>
            <span>Folhas</span><strong>{{ secondary.length }}</strong
            ><small>competências processadas</small>
          </article>
          <article>
            <span>Última competência</span
            ><strong>{{ secondary[0]?.competence || "—" }}</strong
            ><small>{{ secondary[0]?.state || "sem processamento" }}</small>
          </article>
        </section>
        <section class="panel">
          <table>
            <thead>
              <tr>
                <th>Colaborador</th>
                <th>Tipo</th>
                <th>Início</th>
                <th>Salário</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ r.employee_name || r.employee_id }}</td>
                <td>{{ r.contract_type }}</td>
                <td>{{ r.starts_on }}</td>
                <td>{{ money(r.salary) }}</td>
                <td>{{ r.state }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <template v-else-if="active === 'requests'"
        ><RequestsPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'integrations'">
        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="createIntegration">
            <h2>Nova integração</h2>
            <label
              >Provider<select
                v-model="integrationForm.provider"
                @change="
                  integrationForm.name =
                    integrationForm.provider === 'cloudflare'
                      ? 'Cloudflare'
                      : integrationForm.provider === 'mailcow'
                        ? 'Mail institucional'
                        : 'WhatsApp Evolution'
                "
              >
                <option value="cloudflare">Cloudflare</option>
                <option value="mailcow">Mailcow</option>
                <option value="evolution">Evolution API</option>
              </select></label
            >
            <label>Nome<input v-model="integrationForm.name" required /></label>
            <label v-if="integrationForm.provider !== 'cloudflare'"
              >URL HTTPS do provider<input
                v-model="integrationForm.base_url"
                type="url"
                placeholder="https://servico.exemplo.com"
                required
            /></label>
            <label
              >Referência do segredo<input
                v-model="integrationForm.secret_reference"
                placeholder="ex.: tenant-alpha-evolution-api-key"
              /><small
                >Informe somente o nome lógico do Docker Secret/secret manager.
                O valor nunca é enviado por esta tela.</small
              ></label
            >
            <label
              v-if="integrationForm.provider !== 'cloudflare'"
              class="inline"
              ><input
                v-model="integrationForm.allow_private_network"
                type="checkbox"
              />
              Permitir rede privada explicitamente</label
            >
            <button class="primary">Registrar integração</button>
          </form>
          <div class="panel">
            <h2>Política de segurança</h2>
            <ul class="checklist">
              <li>Credenciais permanecem em Docker Secrets/secret manager.</li>
              <li>URLs externas exigem HTTPS e têm proteção SSRF.</li>
              <li>Operações com efeito externo usam Idempotency-Key.</li>
              <li>Health, falhas e ações são auditados.</li>
              <li>
                Rede externa permanece desligada por padrão na construção local.
              </li>
            </ul>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>Conexões configuradas</h2>
            <span>{{ rows.length }} conexões</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>Provider</th>
                <th>Capabilities</th>
                <th>Segredo</th>
                <th>Health</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.id">
                <td>{{ r.name }}</td>
                <td>{{ r.provider }}</td>
                <td>{{ (r.capabilities || []).join(", ") || "—" }}</td>
                <td>
                  <span
                    class="pill"
                    :class="r.secret_configured ? 'ok' : 'warn'"
                    >{{
                      r.secret_configured ? "Referenciado" : "Não configurado"
                    }}</span
                  >
                </td>
                <td>
                  <span
                    class="pill"
                    :class="
                      r.last_health_state === 'healthy'
                        ? 'ok'
                        : r.last_health_state === 'failed'
                          ? 'danger'
                          : 'warn'
                    "
                    >{{ r.last_health_state || r.state }}</span
                  >
                </td>
                <td>
                  <button class="small" @click="testIntegration(r)">
                    Testar conexão
                  </button>
                </td>
              </tr>
              <tr v-if="!rows.length">
                <td colspan="6" class="empty">
                  Nenhuma integração configurada.
                </td>
              </tr>
            </tbody>
          </table>
        </section>
        <section class="panel">
          <h2>Providers previstos no tenant</h2>
          <div class="notice-list">
            <article v-for="p in secondary" :key="p.provider">
              <strong>{{ p.provider }}</strong>
              <p>{{ p.domain }}</p>
              <small
                >Status: {{ p.status }} · conexões: {{ p.connections }}</small
              >
            </article>
          </div>
        </section>
      </template>

      <template v-else-if="active === 'analytics'"
        ><AnalyticsPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'workflows'"
        ><WorkflowPanel :api="api" @error="error = $event"
      /></template>
      <template v-else-if="active === 'communication'"
        ><CommunicationPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'reports'"
        ><ReportingPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'mail'"
        ><MailPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'student_services'"
        ><StudentServicesPanel :api="api" @error="error = $event"
      /></template>

      <template v-else-if="active === 'audit'"
        ><section class="grid-2">
          <div class="panel">
            <h2>Trilha de auditoria</h2>
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Ação</th>
                  <th>Agregado</th>
                  <th>Correlação</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="r.id">
                  <td>{{ dateBR(r.created_at) }}</td>
                  <td>{{ r.action }}</td>
                  <td>{{ r.aggregate_type }} / {{ r.aggregate_id }}</td>
                  <td>
                    <code>{{ r.correlation_id }}</code>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="panel">
            <h2>Transactional Outbox</h2>
            <table>
              <thead>
                <tr>
                  <th>Evento</th>
                  <th>Tentativas</th>
                  <th>Publicação</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in secondary" :key="r.id">
                  <td>{{ r.event_type }}</td>
                  <td>{{ r.attempts }}</td>
                  <td>
                    {{ r.published_at ? dateBR(r.published_at) : "Pendente" }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section></template
      >
    </main>
  </div>
</template>
