import { computed, onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const tab = ref("library");
const refs = ref({ people: [], students: [] });
const items = ref([]), loans = ref([]), reservations = ref([]), fines = ref([]), policies = ref([]);
const routes = ref([]), riders = ref([]), schedules = ref([]), occurrences = ref([]);
const healthRecords = ref([]), incidents = ref([]), medications = ref([]), accessLog = ref([]);
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
function msg(e) {
    return e instanceof Error ? e.message : "Falha na operação";
}
function dateBR(v) {
    if (!v)
        return "—";
    try {
        return new Intl.DateTimeFormat("pt-BR", {
            dateStyle: "short",
            timeStyle: String(v).includes("T") ? "short" : undefined,
        }).format(new Date(String(v)));
    }
    catch {
        return String(v);
    }
}
function money(v) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    }).format(Number(v || 0));
}
function label(list, id) {
    return list?.find((x) => x.id === id)?.label || id || "—";
}
function idem(prefix) {
    return `${prefix}-${crypto.randomUUID()}`;
}
async function post(path, body, key) {
    const headers = {
        "Content-Type": "application/json",
    };
    if (key)
        headers["Idempotency-Key"] = key;
    return props.api.request(path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
    });
}
async function loadRefs() {
    try {
        refs.value = await props.api.request("/references/catalog");
    }
    catch {
        refs.value = { people: [], students: [] };
    }
}
async function loadLibrary() {
    const [i, l, r, f, p] = await Promise.all([
        props.api.request("/library/items"),
        props.api.request("/library/loans"),
        props.api.request("/library/reservations"),
        props.api.request("/library/fines"),
        props.api.request("/library/policies"),
    ]);
    items.value = i.items || [];
    loans.value = l.items || [];
    reservations.value = r.items || [];
    fines.value = f.items || [];
    policies.value = p.items || [];
}
async function loadTransport() {
    const [r, ri, s, o] = await Promise.all([
        props.api.request("/transport/routes"),
        props.api.request("/transport/riders"),
        props.api.request("/transport/schedules"),
        props.api.request("/transport/occurrences"),
    ]);
    routes.value = r.items || [];
    riders.value = ri.items || [];
    schedules.value = s.items || [];
    occurrences.value = o.items || [];
}
async function loadHealth() {
    const [r, i, m, a] = await Promise.all([
        props.api.request("/health/records"),
        props.api.request("/health/incidents"),
        props.api.request("/health/medication-authorizations"),
        props.api.request("/health/access-log"),
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
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function op(fn, reload) {
    loading.value = true;
    try {
        await fn();
        await reload();
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function createItem() {
    await op(() => post("/library/items", {
        ...itemForm,
        authors: itemForm.authors || null,
        isbn: itemForm.isbn || null,
        category: itemForm.category || null,
    }), loadLibrary);
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
    await op(() => post("/library/loans", { ...loanForm, due_at: null }), loadLibrary);
    Object.assign(loanForm, { library_item_id: "", person_id: "" });
}
async function returnLoan(id) {
    await op(() => post(`/library/loans/${id}/return`, {}), loadLibrary);
}
async function renewLoan(id) {
    await op(() => post(`/library/loans/${id}/renew`, {
        reason: "Renovação administrativa",
    }), loadLibrary);
}
async function settleFine(id, action) {
    await op(() => post(`/library/fines/${id}/settle`, {
        action,
        reason: action === "paid" ? "Pagamento registrado" : "Abono autorizado",
    }), loadLibrary);
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
    await op(() => post("/transport/routes", {
        ...routeForm,
        driver_person_id: routeForm.driver_person_id || null,
        monitor_person_id: routeForm.monitor_person_id || null,
        stops,
    }), loadTransport);
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
    await op(() => post("/transport/riders", {
        ...riderForm,
        boarding_stop: riderForm.boarding_stop || null,
        dropoff_stop: riderForm.dropoff_stop || null,
    }), loadTransport);
    Object.assign(riderForm, {
        route_id: "",
        student_id: "",
        boarding_stop: "",
        dropoff_stop: "",
    });
}
async function createSchedule() {
    await op(() => post("/transport/schedules", {
        ...scheduleForm,
        outbound_time: scheduleForm.outbound_time || null,
        return_time: scheduleForm.return_time || null,
        valid_until: scheduleForm.valid_until || null,
    }), loadTransport);
}
async function createOccurrence() {
    await op(() => post("/transport/occurrences", {
        ...occurrenceForm,
        student_id: occurrenceForm.student_id || null,
    }), loadTransport);
    Object.assign(occurrenceForm, {
        route_id: "",
        student_id: "",
        occurrence_type: "delay",
        description: "",
        severity: "normal",
    });
}
async function resolveOccurrence(id) {
    await op(() => post(`/transport/occurrences/${id}/resolve`, {
        resolution: "Ocorrência tratada e encerrada.",
    }), loadTransport);
}
async function createRecord() {
    await op(() => post("/health/records", {
        ...recordForm,
        details: {},
        valid_from: recordForm.valid_from || null,
        valid_until: recordForm.valid_until || null,
    }), loadHealth);
    Object.assign(recordForm, {
        person_id: "",
        record_type: "allergy",
        summary: "",
        sensitivity: "restricted",
        valid_from: "",
        valid_until: "",
    });
}
async function accessRecord(r) {
    const reason = window.prompt("Informe o motivo do acesso ao registro sensível:", "Atendimento autorizado");
    if (!reason)
        return;
    await op(async () => {
        const detail = await post(`/health/records/${r.id}/access`, { reason });
        window.alert(`${detail.summary}\n\n${JSON.stringify(detail.details || {}, null, 2)}`);
    }, loadHealth);
}
async function createIncident() {
    await op(() => post("/health/incidents", {
        ...incidentForm,
        occurred_at: new Date(incidentForm.occurred_at).toISOString(),
        first_aid: [],
        referred_to: incidentForm.referred_to || null,
    }), loadHealth);
}
async function closeIncident(id) {
    await op(() => post(`/health/incidents/${id}/close`, {
        reason: "Atendimento concluído",
    }), loadHealth);
}
async function createMedication() {
    await op(() => post("/health/medication-authorizations", {
        ...medicationForm,
        ends_on: medicationForm.ends_on || null,
        prescriber: medicationForm.prescriber || null,
        guardian_person_id: medicationForm.guardian_person_id || null,
        consent_document_id: null,
    }), loadHealth);
}
async function administer() {
    await op(() => post("/health/medication-administrations", {
        ...administrationForm,
        administered_at: new Date(administrationForm.administered_at).toISOString(),
        dosage: administrationForm.dosage || null,
        notes: administrationForm.notes || null,
    }, idem("medication")), loadHealth);
    Object.assign(administrationForm, {
        authorization_id: "",
        administered_at: new Date().toISOString().slice(0, 16),
        dosage: "",
        notes: "",
    });
}
const openLoans = computed(() => loans.value.filter((x) => x.state === "open"));
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['service-tabs', 'service-tabs', 'service-tabs', 'rows', 'rows', 'rows', 'rows', 'service-tabs', 'refresh', 'rows',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("service-tabs") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'library';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'library' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'transport';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'transport' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'health';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'health' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        ...{ class: ("small refresh") },
    });
    if (__VLS_ctx.tab === 'library') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("metrics") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.items.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.openLoans.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.reservations.filter((x) => ["queued", "ready"].includes(x.state))
            .length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.fines.filter((x) => x.state === "open").length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createItem) },
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
        (__VLS_ctx.itemForm.inventory_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.itemForm.item_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("book"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("magazine"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("digital"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("other"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.itemForm.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.itemForm.authors);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.itemForm.isbn);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.itemForm.category);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.loading)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createLoan) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.loanForm.library_item_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [i] of __VLS_getVForSourceType((__VLS_ctx.items.filter((x) => ['available', 'reserved'].includes(x.state))))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((i.id)),
                value: ((i.id)),
            });
            (i.title);
            (i.inventory_code);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.loanForm.person_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.refs.people || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((p.id)),
                value: ((p.id)),
            });
            (p.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.loading)),
        });
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [l] of __VLS_getVForSourceType((__VLS_ctx.loans))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((l.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (l.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.label(__VLS_ctx.refs.people, l.person_id));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.dateBR(l.due_at));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (l.renewal_count || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(l.fine_amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                ...{ class: ("row-actions") },
            });
            if (l.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'library')))
                                return;
                            if (!((l.state === 'open')))
                                return;
                            __VLS_ctx.renewLoan(l.id);
                        } },
                    ...{ class: ("small") },
                });
            }
            if (l.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'library')))
                                return;
                            if (!((l.state === 'open')))
                                return;
                            __VLS_ctx.returnLoan(l.id);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [f] of __VLS_getVForSourceType((__VLS_ctx.fines))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((f.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.label(__VLS_ctx.refs.people, f.person_id));
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (f.reason);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.money(f.amount));
            if (f.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'library')))
                                return;
                            if (!((f.state === 'open')))
                                return;
                            __VLS_ctx.settleFine(f.id, 'paid');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (f.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'library')))
                                return;
                            if (!((f.state === 'open')))
                                return;
                            __VLS_ctx.settleFine(f.id, 'waived');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.fines.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.publishPolicy) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.policyForm.effective_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
        });
        (__VLS_ctx.policyForm.max_loan_days);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.policyForm.max_renewals);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.policyForm.daily_fine);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        if (__VLS_ctx.policies[0]) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.policies[0].code);
            (__VLS_ctx.policies[0].version);
        }
    }
    else if (__VLS_ctx.tab === 'transport') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("metrics") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.routes.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.riders.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.schedules.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.occurrences.filter((x) => x.state !== "resolved").length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRoute) },
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
        (__VLS_ctx.routeForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.routeForm.vehicle);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.routeForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routeForm.driver_person_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.refs.people || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((p.id)),
                value: ((p.id)),
            });
            (p.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.routeForm.monitor_person_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.refs.people || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((p.id)),
                value: ((p.id)),
            });
            (p.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.routeForm.stops_text)),
            rows: ("4"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.assignRider) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.riderForm.route_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.routes))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((r.id)),
                value: ((r.id)),
            });
            (r.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.riderForm.student_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [s] of __VLS_getVForSourceType((__VLS_ctx.refs.students || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((s.id)),
                value: ((s.id)),
            });
            (s.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.riderForm.boarding_stop);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.riderForm.dropoff_stop);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createSchedule) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.scheduleForm.route_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.routes))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((r.id)),
                value: ((r.id)),
            });
            (r.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.scheduleForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.scheduleForm.valid_until);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("time"),
        });
        (__VLS_ctx.scheduleForm.outbound_time);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("time"),
        });
        (__VLS_ctx.scheduleForm.return_time);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("weekday-grid") },
        });
        for (const [d] of __VLS_getVForSourceType(([
            { n: 0, l: 'Seg' },
            { n: 1, l: 'Ter' },
            { n: 2, l: 'Qua' },
            { n: 3, l: 'Qui' },
            { n: 4, l: 'Sex' },
            { n: 5, l: 'Sáb' },
            { n: 6, l: 'Dom' },
        ]))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                key: ((d.n)),
                ...{ class: ("inline") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("checkbox"),
                value: ((d.n)),
            });
            (__VLS_ctx.scheduleForm.weekdays);
            (d.l);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createOccurrence) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.occurrenceForm.route_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.routes))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((r.id)),
                value: ((r.id)),
            });
            (r.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.occurrenceForm.student_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [s] of __VLS_getVForSourceType((__VLS_ctx.refs.students || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((s.id)),
                value: ((s.id)),
            });
            (s.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.occurrenceForm.occurrence_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("delay"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("absence"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("incident"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("vehicle"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.occurrenceForm.severity)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("low"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("normal"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("high"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("critical"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.occurrenceForm.description)),
            rows: ("3"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [o] of __VLS_getVForSourceType((__VLS_ctx.occurrences))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((o.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.dateBR(o.created_at || o.occurred_at));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (o.route_name || __VLS_ctx.label(__VLS_ctx.routes, o.route_id));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.label(__VLS_ctx.refs.students, o.student_id));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (o.occurrence_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (o.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (o.state !== 'resolved') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'library'))))
                                return;
                            if (!((__VLS_ctx.tab === 'transport')))
                                return;
                            if (!((o.state !== 'resolved')))
                                return;
                            __VLS_ctx.resolveOccurrence(o.id);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("metrics") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.healthRecords.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.incidents.filter((x) => x.state === "open").length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.medications.filter((x) => x.state === "active").length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.accessLog.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRecord) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.recordForm.person_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.refs.people || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((p.id)),
                value: ((p.id)),
            });
            (p.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.recordForm.record_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.recordForm.sensitivity)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("restricted"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("highly_restricted"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.recordForm.summary)),
            rows: ("3"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createIncident) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.incidentForm.person_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.refs.people || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((p.id)),
                value: ((p.id)),
            });
            (p.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.incidentForm.incident_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("datetime-local"),
            required: (true),
        });
        (__VLS_ctx.incidentForm.occurred_at);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.incidentForm.location);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.incidentForm.summary)),
            rows: ("3"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.incidentForm.guardian_notified);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createMedication) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.medicationForm.person_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.refs.people || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((p.id)),
                value: ((p.id)),
            });
            (p.label);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.medicationForm.medication_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.medicationForm.dosage);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.medicationForm.instructions)),
            rows: ("3"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.medicationForm.starts_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.medicationForm.ends_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.administer) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.administrationForm.authorization_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [m] of __VLS_getVForSourceType((__VLS_ctx.medications.filter((x) => x.state === 'active')))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((m.id)),
                value: ((m.id)),
            });
            (__VLS_ctx.label(__VLS_ctx.refs.people, m.person_id));
            (m.medication_name);
            (m.dosage);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("datetime-local"),
            required: (true),
        });
        (__VLS_ctx.administrationForm.administered_at);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.administrationForm.dosage);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.administrationForm.notes)),
            rows: ("3"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.healthRecords))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((r.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.label(__VLS_ctx.refs.people, r.person_id));
            (r.record_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (r.summary);
            (r.sensitivity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'library'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'transport'))))
                            return;
                        __VLS_ctx.accessRecord(r);
                    } },
                ...{ class: ("small") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [i] of __VLS_getVForSourceType((__VLS_ctx.incidents))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((i.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.label(__VLS_ctx.refs.people, i.person_id));
            (i.incident_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.dateBR(i.occurred_at));
            (i.summary);
            if (i.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'library'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'transport'))))
                                return;
                            if (!((i.state === 'open')))
                                return;
                            __VLS_ctx.closeIncident(i.id);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    ['service-tabs', 'selected', 'selected', 'selected', 'small', 'refresh', 'metrics', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'primary', 'panel', 'panel-title', 'row-actions', 'small', 'small', 'grid-2', 'panel', 'rows', 'small', 'small', 'empty', 'panel', 'cols', 'cols', 'primary', 'metrics', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'cols', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'weekday-grid', 'inline', 'primary', 'panel', 'cols', 'primary', 'panel', 'small', 'metrics', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'cols', 'inline', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'primary', 'grid-2', 'panel', 'rows', 'small', 'panel', 'rows', 'small',];
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
            loading: loading,
            tab: tab,
            refs: refs,
            items: items,
            loans: loans,
            reservations: reservations,
            fines: fines,
            policies: policies,
            routes: routes,
            riders: riders,
            schedules: schedules,
            occurrences: occurrences,
            healthRecords: healthRecords,
            incidents: incidents,
            medications: medications,
            accessLog: accessLog,
            itemForm: itemForm,
            loanForm: loanForm,
            policyForm: policyForm,
            routeForm: routeForm,
            riderForm: riderForm,
            scheduleForm: scheduleForm,
            occurrenceForm: occurrenceForm,
            recordForm: recordForm,
            incidentForm: incidentForm,
            medicationForm: medicationForm,
            administrationForm: administrationForm,
            dateBR: dateBR,
            money: money,
            label: label,
            load: load,
            createItem: createItem,
            createLoan: createLoan,
            returnLoan: returnLoan,
            renewLoan: renewLoan,
            settleFine: settleFine,
            publishPolicy: publishPolicy,
            createRoute: createRoute,
            assignRider: assignRider,
            createSchedule: createSchedule,
            createOccurrence: createOccurrence,
            resolveOccurrence: resolveOccurrence,
            createRecord: createRecord,
            accessRecord: accessRecord,
            createIncident: createIncident,
            closeIncident: closeIncident,
            createMedication: createMedication,
            administer: administer,
            openLoans: openLoans,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
    __typeProps: {},
});
; /* PartiallyEnd: #4569/main.vue */
