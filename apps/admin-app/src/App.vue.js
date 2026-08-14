import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
import MailPanel from "./components/MailPanel.vue";
import ReportingPanel from "./components/ReportingPanel.vue";
import AnalyticsPanel from "./components/AnalyticsPanel.vue";
import CommunicationPanel from "./components/CommunicationPanel.vue";
import WorkflowPanel from "./components/WorkflowPanel.vue";
import RequestsPanel from "./components/RequestsPanel.vue";
import StudentServicesPanel from "./components/StudentServicesPanel.vue";
import CanteenPanel from "./components/CanteenPanel.vue";
import EventsTravelPanel from "./components/EventsTravelPanel.vue";
const api = new Pige360SessionClient();
const ready = ref(false);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const email = ref("");
const password = ref("");
const authenticated = ref(false);
const active = ref("dashboard");
const dashboard = ref({
    metrics: {},
    recent_audit: [],
    recent_outbox: [],
    branding: {},
});
const refs = ref({});
const rows = ref([]);
const secondary = ref([]);
const policies = ref([]);
const teacherAssignments = ref([]);
const allEnrollments = ref([]);
const brand = computed(() => dashboard.value.branding ?? {});
const schoolName = computed(() => brand.value.short_name ||
    brand.value.trade_name ||
    brand.value.legal_name ||
    "Instituição");
const roleSet = computed(() => new Set(api.claims()?.roles ?? []));
const can = (...roles) => roles.some((r) => roleSet.value.has(r));
const nav = computed(() => [
    ["dashboard", "Visão geral", "⌂", true],
    [
        "analytics",
        "Indicadores",
        "◫",
        can("tenant_owner", "institution_director", "unit_manager", "secretary", "academic_coordinator", "finance_manager", "finance_operator", "hr_manager", "personnel_operator", "payroll_operator", "timekeeping_operator", "canteen_manager", "pos_operator", "inventory_manager", "auditor", "fiscal_manager"),
    ],
    [
        "students",
        "Secretaria",
        "◎",
        can("tenant_owner", "institution_director", "unit_manager", "secretary", "academic_coordinator"),
    ],
    [
        "planning",
        "Planejamento",
        "▤",
        can("tenant_owner", "institution_director", "academic_coordinator", "teacher", "assistant_teacher"),
    ],
    [
        "attendance",
        "Frequência",
        "✓",
        can("tenant_owner", "institution_director", "academic_coordinator", "teacher", "assistant_teacher"),
    ],
    [
        "finance",
        "Financeiro",
        "$",
        can("tenant_owner", "institution_director", "finance_manager", "finance_operator"),
    ],
    [
        "sales",
        "Vendas e estoque",
        "▦",
        can("tenant_owner", "institution_director", "canteen_manager", "pos_operator", "inventory_manager"),
    ],
    [
        "canteen",
        "Cantina",
        "◈",
        can("tenant_owner", "institution_director", "canteen_manager", "finance_manager", "finance_operator", "secretary"),
    ],
    [
        "events",
        "Eventos e viagens",
        "☆",
        can("tenant_owner", "institution_director", "unit_manager", "event_manager"),
    ],
    [
        "fiscal",
        "Fiscal",
        "N",
        can("tenant_owner", "institution_director", "fiscal_manager", "finance_manager"),
    ],
    [
        "hr",
        "RH e Folha",
        "♙",
        can("tenant_owner", "institution_director", "hr_manager", "personnel_operator", "payroll_operator", "timekeeping_operator"),
    ],
    ["requests", "Solicitações", "☰", true],
    [
        "workflows",
        "Workflows",
        "◇",
        can("tenant_owner", "institution_director", "unit_manager", "secretary", "academic_coordinator", "request_agent", "finance_manager", "hr_manager", "auditor", "support"),
    ],
    [
        "communication",
        "Comunicação",
        "◌",
        can("tenant_owner", "institution_director", "unit_manager", "secretary", "academic_coordinator", "event_manager", "finance_manager", "hr_manager", "request_agent", "support"),
    ],
    [
        "reports",
        "Relatórios",
        "▥",
        can("tenant_owner", "institution_director", "unit_manager", "secretary", "academic_coordinator", "finance_manager", "finance_operator", "hr_manager", "personnel_operator", "payroll_operator", "inventory_manager", "canteen_manager", "auditor"),
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
        can("tenant_owner", "institution_director", "unit_manager", "secretary", "library_manager", "transport_manager", "health_operator"),
    ],
    [
        "audit",
        "Auditoria",
        "◉",
        can("tenant_owner", "institution_director", "auditor"),
    ],
].filter((x) => x[3]));
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
function problemMessage(e) {
    const p = e?.problem;
    return p?.detail || (e instanceof Error ? e.message : "Erro inesperado");
}
function idem(prefix) {
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
async function request(path, init = {}) {
    return api.request(path, init);
}
async function jsonPost(path, body, key) {
    const headers = {
        "Content-Type": "application/json",
    };
    if (key)
        headers["Idempotency-Key"] = key;
    return request(path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
    });
}
async function boot() {
    try {
        await api.initialize();
        authenticated.value = !!api.tokens;
        if (authenticated.value)
            await loadBase();
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
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
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
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
    dashboard.value = await request("/dashboard/operations");
    setBrand();
    try {
        refs.value = await request("/references/catalog");
    }
    catch {
        refs.value = {};
    }
    try {
        teacherAssignments.value =
            (await request("/teacher-assignments")).items || [];
    }
    catch {
        teacherAssignments.value = [];
    }
    try {
        allEnrollments.value = (await request("/enrollments")).items || [];
    }
    catch {
        allEnrollments.value = [];
    }
    await selectArea(active.value);
}
async function selectArea(area) {
    active.value = area;
    error.value = "";
    notice.value = "";
    busy.value = true;
    try {
        if (area === "dashboard") {
            dashboard.value = await request("/dashboard/operations");
            setBrand();
            rows.value = dashboard.value.recent_audit || [];
            secondary.value = dashboard.value.recent_outbox || [];
        }
        if (area === "analytics" ||
            area === "reports" ||
            area === "communication" ||
            area === "workflows" ||
            area === "canteen" ||
            area === "events") {
            rows.value = [];
            secondary.value = [];
        }
        if (area === "students") {
            rows.value = (await request("/students")).items || [];
            secondary.value = (await request("/enrollments")).items || [];
        }
        if (area === "planning") {
            rows.value = (await request("/teaching-plans")).items || [];
            secondary.value =
                (await request("/teacher-assignments")).items || [];
        }
        if (area === "attendance") {
            rows.value =
                (await request("/class-sessions?limit=100")).items || [];
            policies.value = (await request("/attendance/policies")).items || [];
            secondary.value = (await request("/attendance/risks")).items || [];
        }
        if (area === "finance") {
            rows.value = (await request("/finance/contracts")).items || [];
            secondary.value =
                (await request("/finance/installments")).items || [];
        }
        if (area === "sales") {
            rows.value = (await request("/products")).items || [];
            secondary.value = (await request("/sales")).items || [];
        }
        if (area === "fiscal") {
            rows.value = (await request("/fiscal/documents")).items || [];
            secondary.value = (await request("/fiscal/rules")).items || [];
        }
        if (area === "hr") {
            rows.value = (await request("/hr/employment-contracts")).items || [];
            secondary.value = (await request("/payroll/runs")).items || [];
        }
        if (area === "requests") {
            rows.value = (await request("/service-requests")).items || [];
            secondary.value = (await request("/notices")).items || [];
        }
        if (area === "mail" || area === "student_services") {
            rows.value = [];
            secondary.value = [];
        }
        if (area === "integrations") {
            rows.value = (await request("/integration-connections")).items || [];
            secondary.value =
                (await request("/integrations/providers/status")).items || [];
        }
        if (area === "audit") {
            const d = await request("/dashboard/operations");
            rows.value = d.recent_audit || [];
            secondary.value = d.recent_outbox || [];
        }
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function createStudent() {
    busy.value = true;
    try {
        const person = await jsonPost("/people", {
            full_name: personForm.full_name,
            cpf: personForm.cpf || null,
            email: personForm.email || null,
        }, idem("person"));
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
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function createEnrollment() {
    busy.value = true;
    try {
        const body = {
            ...enrollmentForm,
            class_group_id: enrollmentForm.class_group_id || null,
            financial_responsible_guardian_id: enrollmentForm.financial_responsible_guardian_id || null,
        };
        await jsonPost("/enrollments", body, idem("enrollment"));
        notice.value = "Pré-matrícula criada.";
        await selectArea("students");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function activateEnrollment(row) {
    try {
        await jsonPost(`/enrollments/${row.id}/activate`, {
            expected_version: row.version,
            reason: "Ativação pelo administrativo",
        });
        await selectArea("students");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
}
async function createPlan() {
    busy.value = true;
    try {
        await jsonPost("/teaching-plans", {
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
        }, idem("teaching-plan"));
        notice.value = "Planejamento criado.";
        await selectArea("planning");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function planAction(row, action) {
    try {
        await jsonPost(`/teaching-plans/${row.id}/${action}`, {
            reason: action === "approve"
                ? "Planejamento aprovado"
                : "Atualização de fluxo pedagógico",
            expected_version: row.current_version,
            comments: null,
        });
        await selectArea("planning");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
}
async function createSession() {
    busy.value = true;
    try {
        await jsonPost("/class-sessions", {
            institution_id: sessionForm.institution_id,
            unit_id: sessionForm.unit_id,
            class_group_id: sessionForm.class_group_id,
            component_id: sessionForm.component_id,
            attendance_policy_id: sessionForm.attendance_policy_id,
            scheduled_start: sessionForm.scheduled_start,
            scheduled_end: sessionForm.scheduled_end,
            modality: "regular",
            enrolled_student_ids: ((await request(`/enrollments?state=active`)).items || [])
                .filter((x) => x.class_group_id === sessionForm.class_group_id)
                .map((x) => x.student_id),
            teacher_ids: [sessionForm.teacher_id],
        }, idem("class-session"));
        notice.value = "Sessão de aula criada.";
        await selectArea("attendance");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function sessionAction(row, action) {
    try {
        await jsonPost(`/class-sessions/${row.id}/${action}`, {
            reason: "Operação administrativa registrada",
            expected_version: row.version,
        });
        await selectArea("attendance");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
}
async function createFinancial() {
    busy.value = true;
    try {
        const contract = await jsonPost("/finance/contracts", {
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
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function createProduct() {
    busy.value = true;
    try {
        await jsonPost("/products", productForm);
        notice.value = "Produto cadastrado.";
        await selectArea("sales");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function createRequest() {
    busy.value = true;
    try {
        await jsonPost("/service-requests", requestForm);
        notice.value = "Solicitação criada.";
        await selectArea("requests");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
function label(items, id) {
    return items?.find((x) => x.id === id)?.label || id;
}
function money(v) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    }).format(Number(v || 0));
}
function dateBR(v) {
    if (!v)
        return "—";
    try {
        return new Intl.DateTimeFormat("pt-BR", {
            dateStyle: "short",
            timeStyle: String(v).includes("T") ? "short" : undefined,
        }).format(new Date(v));
    }
    catch {
        return String(v);
    }
}
function integrationCapabilities(provider) {
    if (provider === "cloudflare")
        return ["dns", "custom_hostnames"];
    if (provider === "mailcow")
        return ["mailboxes"];
    if (provider === "evolution")
        return ["send_text"];
    return [];
}
async function createIntegration() {
    busy.value = true;
    error.value = "";
    try {
        const config = {};
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
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
async function testIntegration(row) {
    busy.value = true;
    error.value = "";
    try {
        const result = await jsonPost(`/integration-connections/${row.id}/test`, {});
        notice.value = `${row.name}: ${result.status} (${result.latency_ms} ms)`;
        await selectArea("integrations");
    }
    catch (e) {
        error.value = problemMessage(e);
    }
    finally {
        busy.value = false;
    }
}
onMounted(boot);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    if (!__VLS_ctx.ready) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("center") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("spinner") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    }
    else if (!__VLS_ctx.authenticated) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("login-page") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.login) },
            ...{ class: ("login-card") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("school-mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("email"),
            autocomplete: ("username"),
            required: (true),
        });
        (__VLS_ctx.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("password"),
            autocomplete: ("current-password"),
            required: (true),
        });
        (__VLS_ctx.password);
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.busy)),
        });
        (__VLS_ctx.busy ? "Entrando…" : "Entrar");
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("app-shell") },
            'data-surface': ("tenant"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("brand") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.schoolName);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({});
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.nav))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.authenticated))))
                            return;
                        __VLS_ctx.selectArea(item[0]);
                    } },
                key: ((item[0])),
                ...{ class: (({ active: __VLS_ctx.active === item[0] })) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (item[2]);
            (item[1]);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("aside-footer") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.api.claims()?.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
        (__VLS_ctx.schoolName);
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        (__VLS_ctx.nav.find((n) => n[0] === __VLS_ctx.active)?.[1]);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("header-actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("connection") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    __VLS_ctx.selectArea(__VLS_ctx.active);
                } },
        });
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.authenticated))))
                            return;
                        if (!((__VLS_ctx.error)))
                            return;
                        __VLS_ctx.error = '';
                    } },
            });
        }
        if (__VLS_ctx.notice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash success") },
            });
            (__VLS_ctx.notice);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.authenticated))))
                            return;
                        if (!((__VLS_ctx.notice)))
                            return;
                        __VLS_ctx.notice = '';
                    } },
            });
        }
        if (__VLS_ctx.busy) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("loading-line") },
            });
        }
        if (__VLS_ctx.active === 'dashboard') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("metrics") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dashboard.metrics?.active_students ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dashboard.metrics?.active_enrollments ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dashboard.metrics?.open_installments ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dashboard.metrics?.pending_attendance_sessions ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dashboard.metrics?.open_requests ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dashboard.metrics?.unpublished_outbox ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.dashboard.recent_audit))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.action);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.aggregate_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.dateBR(r.created_at));
            }
            if (!__VLS_ctx.dashboard.recent_audit?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                    colspan: ("3"),
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.dashboard.recent_outbox))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.event_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.attempts);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((r.published_at ? 'ok' : 'warn')) },
                });
                (r.published_at ? "Publicado" : "Pendente");
            }
        }
        else if (__VLS_ctx.active === 'students') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createStudent) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.personForm.full_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.personForm.cpf);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("email"),
            });
            (__VLS_ctx.personForm.email);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.personForm.registration_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createEnrollment) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.student_id)),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.students))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.institution_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.institutions))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.unit_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.units))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.program_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.programs))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.curriculum_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.curricula))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.academic_year_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.academic_years))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.enrollmentForm.class_group_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.class_groups))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.enrollmentForm.enrollment_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.rows.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.full_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.registration_number);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.cpf || "—");
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill ok") },
                });
                (r.state);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.secondary))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.student_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.program_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.class_group_name || "—");
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.state);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                if (r.state !== 'active') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!((__VLS_ctx.active === 'students')))
                                    return;
                                if (!((r.state !== 'active')))
                                    return;
                                __VLS_ctx.activateEnrollment(r);
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
        }
        else if (__VLS_ctx.active === 'planning') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createPlan) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.institution_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.institutions))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.unit_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.units))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.academic_period_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.academic_periods))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.program_id)),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.programs))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.curriculum_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.curricula))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.class_group_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.class_groups))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.component_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.components))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.id)),
                });
                (x.label);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.planForm.teacher_id)),
                required: (true),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.secondary))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ((x.user_id)),
                });
                (x.teacher_name);
                (x.class_group_name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.planForm.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.planForm.start_date);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.planForm.end_date);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.planForm.content)),
                rows: ("4"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.ul, __VLS_intrinsicElements.ul)({
                ...{ class: ("checklist") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (r.title);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.label(__VLS_ctx.refs.class_groups, r.class_group_id));
                (__VLS_ctx.label(__VLS_ctx.refs.components, r.component_id));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.start_date);
                (r.end_date);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (r.status);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.current_version);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                    ...{ class: ("row-actions") },
                });
                if (r.status === 'draft' || r.status === 'changes_requested') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'students'))))
                                    return;
                                if (!((__VLS_ctx.active === 'planning')))
                                    return;
                                if (!((r.status === 'draft' || r.status === 'changes_requested')))
                                    return;
                                __VLS_ctx.planAction(r, 'submit');
                            } },
                        ...{ class: ("small") },
                    });
                }
                if (r.status === 'submitted_for_review' &&
                    __VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator')) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'students'))))
                                    return;
                                if (!((__VLS_ctx.active === 'planning')))
                                    return;
                                if (!((r.status === 'submitted_for_review' &&
                                    __VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator'))))
                                    return;
                                __VLS_ctx.planAction(r, 'approve');
                            } },
                        ...{ class: ("small ok-btn") },
                    });
                }
                if (r.status === 'submitted_for_review' &&
                    __VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator')) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'students'))))
                                    return;
                                if (!((__VLS_ctx.active === 'planning')))
                                    return;
                                if (!((r.status === 'submitted_for_review' &&
                                    __VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator'))))
                                    return;
                                __VLS_ctx.planAction(r, 'request-changes');
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
        }
        else if (__VLS_ctx.active === 'attendance') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            if (__VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator')) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                    ...{ onSubmit: (__VLS_ctx.createSession) },
                    ...{ class: ("panel") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("cols") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.sessionForm.institution_id)),
                    required: (true),
                });
                for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.institutions))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        value: ((x.id)),
                    });
                    (x.label);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.sessionForm.unit_id)),
                    required: (true),
                });
                for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.units))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        value: ((x.id)),
                    });
                    (x.label);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("cols") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.sessionForm.class_group_id)),
                    required: (true),
                });
                for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.class_groups))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        value: ((x.id)),
                    });
                    (x.label);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.sessionForm.component_id)),
                    required: (true),
                });
                for (const [x] of __VLS_getVForSourceType((__VLS_ctx.refs.components))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        value: ((x.id)),
                    });
                    (x.label);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.sessionForm.attendance_policy_id)),
                    required: (true),
                });
                for (const [x] of __VLS_getVForSourceType((__VLS_ctx.policies))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        value: ((x.id)),
                    });
                    (x.name);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.sessionForm.teacher_id)),
                    required: (true),
                });
                for (const [x] of __VLS_getVForSourceType((__VLS_ctx.teacherAssignments))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        value: ((x.user_id)),
                    });
                    (x.label);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("cols") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    type: ("datetime-local"),
                    required: (true),
                });
                (__VLS_ctx.sessionForm.scheduled_start);
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    type: ("datetime-local"),
                    required: (true),
                });
                (__VLS_ctx.sessionForm.scheduled_end);
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ class: ("primary") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            if (__VLS_ctx.secondary.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("risk-list") },
                });
                for (const [r] of __VLS_getVForSourceType((__VLS_ctx.secondary))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((r.student_id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (__VLS_ctx.label(__VLS_ctx.refs.students, r.student_id));
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (r.percentage);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: ("pill") },
                        ...{ class: ((r.level === 'critical' ? 'danger' : 'warn')) },
                    });
                    (r.level);
                }
            }
            else {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.dateBR(r.scheduled_start));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.label(__VLS_ctx.refs.class_groups, r.class_group_id));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.label(__VLS_ctx.refs.components, r.component_id));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (r.status);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                    ...{ class: ("row-actions") },
                });
                if (['scheduled', 'ready'].includes(r.status)) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'students'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'planning'))))
                                    return;
                                if (!((__VLS_ctx.active === 'attendance')))
                                    return;
                                if (!((['scheduled', 'ready'].includes(r.status))))
                                    return;
                                __VLS_ctx.sessionAction(r, 'start');
                            } },
                        ...{ class: ("small") },
                    });
                }
                if ([
                    'attendance_submitted',
                    'completed',
                    'started',
                    'attendance_open',
                ].includes(r.status)) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'students'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'planning'))))
                                    return;
                                if (!((__VLS_ctx.active === 'attendance')))
                                    return;
                                if (!(([
                                    'attendance_submitted',
                                    'completed',
                                    'started',
                                    'attendance_open',
                                ].includes(r.status))))
                                    return;
                                __VLS_ctx.sessionAction(r, 'close');
                            } },
                        ...{ class: ("small") },
                    });
                }
                if (r.status === 'closed' &&
                    __VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator')) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.authenticated))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'dashboard'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'students'))))
                                    return;
                                if (!(!((__VLS_ctx.active === 'planning'))))
                                    return;
                                if (!((__VLS_ctx.active === 'attendance')))
                                    return;
                                if (!((r.status === 'closed' &&
                                    __VLS_ctx.can('tenant_owner', 'institution_director', 'academic_coordinator'))))
                                    return;
                                __VLS_ctx.sessionAction(r, 'reopen');
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
        }
        else if (__VLS_ctx.active === 'finance') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createFinancial) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.financeForm.enrollment_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [x] of __VLS_getVForSourceType((__VLS_ctx.allEnrollments))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((x.id)),
                    value: ((x.id)),
                });
                (x.student_name);
                (x.enrollment_number);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.financeForm.description);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.01"),
                min: ("0.01"),
                required: (true),
            });
            (__VLS_ctx.financeForm.total_amount);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
                max: ("120"),
                required: (true),
            });
            (__VLS_ctx.financeForm.count);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.financeForm.first_due_date);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("big-number") },
            });
            (__VLS_ctx.secondary.filter((x) => ["open", "partial"].includes(x.state)).length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.description);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.enrollment_id || "—");
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.money(r.total_amount));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (r.state);
            }
        }
        else if (__VLS_ctx.active === 'sales') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createProduct) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.productForm.sku);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.productForm.barcode);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.productForm.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.productForm.ncm);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.productForm.unit);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.01"),
            });
            (__VLS_ctx.productForm.cost);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.01"),
                required: (true),
            });
            (__VLS_ctx.productForm.sale_price);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("big-number") },
            });
            (__VLS_ctx.secondary.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.sku);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.money(r.sale_price));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.stock_quantity ?? 0);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.state);
            }
        }
        else if (__VLS_ctx.active === 'canteen') {
            // @ts-ignore
            /** @type { [typeof CanteenPanel, ] } */ ;
            // @ts-ignore
            const __VLS_0 = __VLS_asFunctionalComponent(CanteenPanel, new CanteenPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_1 = __VLS_0({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_0));
            let __VLS_5;
            const __VLS_6 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!((__VLS_ctx.active === 'canteen')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_2;
            let __VLS_3;
            var __VLS_4;
        }
        else if (__VLS_ctx.active === 'events') {
            // @ts-ignore
            /** @type { [typeof EventsTravelPanel, ] } */ ;
            // @ts-ignore
            const __VLS_7 = __VLS_asFunctionalComponent(EventsTravelPanel, new EventsTravelPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_8 = __VLS_7({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_7));
            let __VLS_12;
            const __VLS_13 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!((__VLS_ctx.active === 'events')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_9;
            let __VLS_10;
            var __VLS_11;
        }
        else if (__VLS_ctx.active === 'fiscal') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("metrics") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.rows.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.secondary.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.document_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.source_type);
                (r.source_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.environment);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (r.state);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.dateBR(r.updated_at));
            }
        }
        else if (__VLS_ctx.active === 'hr') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("metrics") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.rows.filter((x) => x.state === "active").length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.secondary.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.secondary[0]?.competence || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.secondary[0]?.state || "sem processamento");
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.employee_name || r.employee_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.contract_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.starts_on);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.money(r.salary));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.state);
            }
        }
        else if (__VLS_ctx.active === 'requests') {
            // @ts-ignore
            /** @type { [typeof RequestsPanel, ] } */ ;
            // @ts-ignore
            const __VLS_14 = __VLS_asFunctionalComponent(RequestsPanel, new RequestsPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_15 = __VLS_14({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_14));
            let __VLS_19;
            const __VLS_20 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!((__VLS_ctx.active === 'requests')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_16;
            let __VLS_17;
            var __VLS_18;
        }
        else if (__VLS_ctx.active === 'integrations') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createIntegration) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                ...{ onChange: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.authenticated))))
                            return;
                        if (!(!((__VLS_ctx.active === 'dashboard'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'students'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'planning'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'attendance'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'finance'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'sales'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'canteen'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'events'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'fiscal'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'hr'))))
                            return;
                        if (!(!((__VLS_ctx.active === 'requests'))))
                            return;
                        if (!((__VLS_ctx.active === 'integrations')))
                            return;
                        __VLS_ctx.integrationForm.name =
                            __VLS_ctx.integrationForm.provider === 'cloudflare'
                                ? 'Cloudflare'
                                : __VLS_ctx.integrationForm.provider === 'mailcow'
                                    ? 'Mail institucional'
                                    : 'WhatsApp Evolution';
                    } },
                value: ((__VLS_ctx.integrationForm.provider)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("cloudflare"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("mailcow"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("evolution"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.integrationForm.name);
            if (__VLS_ctx.integrationForm.provider !== 'cloudflare') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    type: ("url"),
                    placeholder: ("https://servico.exemplo.com"),
                    required: (true),
                });
                (__VLS_ctx.integrationForm.base_url);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("ex.: tenant-alpha-evolution-api-key"),
            });
            (__VLS_ctx.integrationForm.secret_reference);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            if (__VLS_ctx.integrationForm.provider !== 'cloudflare') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                    ...{ class: ("inline") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    type: ("checkbox"),
                });
                (__VLS_ctx.integrationForm.allow_private_network);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.ul, __VLS_intrinsicElements.ul)({
                ...{ class: ("checklist") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.rows.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.provider);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                ((r.capabilities || []).join(", ") || "—");
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((r.secret_configured ? 'ok' : 'warn')) },
                });
                (r.secret_configured ? "Referenciado" : "Não configurado");
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((r.last_health_state === 'healthy'
                            ? 'ok'
                            : r.last_health_state === 'failed'
                                ? 'danger'
                                : 'warn')) },
                });
                (r.last_health_state || r.state);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.authenticated))))
                                return;
                            if (!(!((__VLS_ctx.active === 'dashboard'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'students'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'planning'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'attendance'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'finance'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'sales'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'canteen'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'events'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'fiscal'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'hr'))))
                                return;
                            if (!(!((__VLS_ctx.active === 'requests'))))
                                return;
                            if (!((__VLS_ctx.active === 'integrations')))
                                return;
                            __VLS_ctx.testIntegration(r);
                        } },
                    ...{ class: ("small") },
                });
            }
            if (!__VLS_ctx.rows.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                    colspan: ("6"),
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("notice-list") },
            });
            for (const [p] of __VLS_getVForSourceType((__VLS_ctx.secondary))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    key: ((p.provider)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (p.provider);
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
                (p.domain);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (p.status);
                (p.connections);
            }
        }
        else if (__VLS_ctx.active === 'analytics') {
            // @ts-ignore
            /** @type { [typeof AnalyticsPanel, ] } */ ;
            // @ts-ignore
            const __VLS_21 = __VLS_asFunctionalComponent(AnalyticsPanel, new AnalyticsPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_22 = __VLS_21({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_21));
            let __VLS_26;
            const __VLS_27 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'requests'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'integrations'))))
                        return;
                    if (!((__VLS_ctx.active === 'analytics')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_23;
            let __VLS_24;
            var __VLS_25;
        }
        else if (__VLS_ctx.active === 'workflows') {
            // @ts-ignore
            /** @type { [typeof WorkflowPanel, ] } */ ;
            // @ts-ignore
            const __VLS_28 = __VLS_asFunctionalComponent(WorkflowPanel, new WorkflowPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_29 = __VLS_28({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_28));
            let __VLS_33;
            const __VLS_34 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'requests'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'integrations'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'analytics'))))
                        return;
                    if (!((__VLS_ctx.active === 'workflows')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_30;
            let __VLS_31;
            var __VLS_32;
        }
        else if (__VLS_ctx.active === 'communication') {
            // @ts-ignore
            /** @type { [typeof CommunicationPanel, ] } */ ;
            // @ts-ignore
            const __VLS_35 = __VLS_asFunctionalComponent(CommunicationPanel, new CommunicationPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_36 = __VLS_35({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_35));
            let __VLS_40;
            const __VLS_41 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'requests'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'integrations'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'analytics'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'workflows'))))
                        return;
                    if (!((__VLS_ctx.active === 'communication')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_37;
            let __VLS_38;
            var __VLS_39;
        }
        else if (__VLS_ctx.active === 'reports') {
            // @ts-ignore
            /** @type { [typeof ReportingPanel, ] } */ ;
            // @ts-ignore
            const __VLS_42 = __VLS_asFunctionalComponent(ReportingPanel, new ReportingPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_43 = __VLS_42({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_42));
            let __VLS_47;
            const __VLS_48 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'requests'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'integrations'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'analytics'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'workflows'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'communication'))))
                        return;
                    if (!((__VLS_ctx.active === 'reports')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_44;
            let __VLS_45;
            var __VLS_46;
        }
        else if (__VLS_ctx.active === 'mail') {
            // @ts-ignore
            /** @type { [typeof MailPanel, ] } */ ;
            // @ts-ignore
            const __VLS_49 = __VLS_asFunctionalComponent(MailPanel, new MailPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_50 = __VLS_49({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_49));
            let __VLS_54;
            const __VLS_55 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'requests'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'integrations'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'analytics'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'workflows'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'communication'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'reports'))))
                        return;
                    if (!((__VLS_ctx.active === 'mail')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_51;
            let __VLS_52;
            var __VLS_53;
        }
        else if (__VLS_ctx.active === 'student_services') {
            // @ts-ignore
            /** @type { [typeof StudentServicesPanel, ] } */ ;
            // @ts-ignore
            const __VLS_56 = __VLS_asFunctionalComponent(StudentServicesPanel, new StudentServicesPanel({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }));
            const __VLS_57 = __VLS_56({
                ...{ 'onError': {} },
                api: ((__VLS_ctx.api)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_56));
            let __VLS_61;
            const __VLS_62 = {
                onError: (...[$event]) => {
                    if (!(!((!__VLS_ctx.ready))))
                        return;
                    if (!(!((!__VLS_ctx.authenticated))))
                        return;
                    if (!(!((__VLS_ctx.active === 'dashboard'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'students'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'planning'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'attendance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'finance'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'sales'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'canteen'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'events'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'fiscal'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'hr'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'requests'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'integrations'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'analytics'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'workflows'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'communication'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'reports'))))
                        return;
                    if (!(!((__VLS_ctx.active === 'mail'))))
                        return;
                    if (!((__VLS_ctx.active === 'student_services')))
                        return;
                    __VLS_ctx.error = $event;
                }
            };
            let __VLS_58;
            let __VLS_59;
            var __VLS_60;
        }
        else if (__VLS_ctx.active === 'audit') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.rows))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (__VLS_ctx.dateBR(r.created_at));
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.action);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.aggregate_type);
                (r.aggregate_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
                (r.correlation_id);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.secondary))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.event_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.attempts);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.published_at ? __VLS_ctx.dateBR(r.published_at) : "Pendente");
            }
        }
    }
    ['center', 'spinner', 'login-page', 'login-card', 'school-mark', 'eyebrow', 'error', 'primary', 'app-shell', 'brand', 'mark', 'active', 'aside-footer', 'eyebrow', 'header-actions', 'connection', 'flash', 'error', 'flash', 'success', 'loading-line', 'metrics', 'grid-2', 'panel', 'panel-title', 'empty', 'panel', 'panel-title', 'pill', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'cols', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'pill', 'ok', 'panel', 'panel-title', 'small', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'cols', 'cols', 'primary', 'panel', 'checklist', 'panel', 'pill', 'row-actions', 'small', 'small', 'ok-btn', 'small', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'primary', 'panel', 'risk-list', 'pill', 'empty', 'panel', 'pill', 'row-actions', 'small', 'small', 'small', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'big-number', 'panel', 'pill', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'primary', 'panel', 'big-number', 'panel', 'metrics', 'panel', 'pill', 'metrics', 'panel', 'grid-2', 'forms', 'panel', 'inline', 'primary', 'panel', 'checklist', 'panel', 'panel-title', 'pill', 'pill', 'small', 'empty', 'panel', 'notice-list', 'grid-2', 'panel', 'panel',];
    var __VLS_slots;
    var $slots;
    let __VLS_inheritedAttrs;
    var $attrs;
    const __VLS_refs = {};
    var $refs;
    var $el;
    return {
        attrs: {},
        slots: __VLS_slots,
        refs: $refs,
        rootEl: $el,
    };
}
;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            MailPanel: MailPanel,
            ReportingPanel: ReportingPanel,
            AnalyticsPanel: AnalyticsPanel,
            CommunicationPanel: CommunicationPanel,
            WorkflowPanel: WorkflowPanel,
            RequestsPanel: RequestsPanel,
            StudentServicesPanel: StudentServicesPanel,
            CanteenPanel: CanteenPanel,
            EventsTravelPanel: EventsTravelPanel,
            api: api,
            ready: ready,
            busy: busy,
            error: error,
            notice: notice,
            email: email,
            password: password,
            authenticated: authenticated,
            active: active,
            dashboard: dashboard,
            refs: refs,
            rows: rows,
            secondary: secondary,
            policies: policies,
            teacherAssignments: teacherAssignments,
            allEnrollments: allEnrollments,
            schoolName: schoolName,
            can: can,
            nav: nav,
            personForm: personForm,
            enrollmentForm: enrollmentForm,
            planForm: planForm,
            sessionForm: sessionForm,
            financeForm: financeForm,
            productForm: productForm,
            integrationForm: integrationForm,
            login: login,
            logout: logout,
            selectArea: selectArea,
            createStudent: createStudent,
            createEnrollment: createEnrollment,
            activateEnrollment: activateEnrollment,
            createPlan: createPlan,
            planAction: planAction,
            createSession: createSession,
            sessionAction: sessionAction,
            createFinancial: createFinancial,
            createProduct: createProduct,
            label: label,
            money: money,
            dateBR: dateBR,
            createIntegration: createIntegration,
            testIntegration: testIntegration,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
