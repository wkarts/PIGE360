import { computed, onMounted, reactive, ref } from "vue";
import GradingPanel from "./GradingPanel.vue";
import EarlyChildhoodPanel from "./EarlyChildhoodPanel.vue";
import { Pige360SessionClient } from "@pige360/auth";
import { TransactionalOutbox, createOfflineStore } from "@pige360/offline-sync";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref(""), online = ref(navigator.onLine);
const email = ref(""), password = ref("");
const ctx = ref({ branding: {}, assignments: [], sessions: [] });
const roster = ref(null);
const attendance = reactive({});
const webOutbox = new TransactionalOutbox();
let nativeStore = null;
const plan = reactive({ assignment_id: "", title: "", start_date: "", end_date: "", content: "" });
const b = computed(() => ctx.value.branding || {}), school = computed(() => b.value.short_name || b.value.trade_name || b.value.legal_name || "Instituição");
function m(e) { const p = e.problem; return p?.detail || (e instanceof Error ? e.message : "Erro"); }
function theme() { document.documentElement.style.setProperty("--brand-primary", b.value.primary_color || "#006D77"); document.documentElement.style.setProperty("--brand-secondary", b.value.secondary_color || "#0D1B2A"); document.title = `${school.value} — Professor`; }
async function load() { ctx.value = await api.request("/portal/teacher/me"); theme(); const c = api.claims(); if (c?.tid && c.sub) {
    nativeStore = createOfflineStore(c.tid, c.sub);
    if (nativeStore)
        await nativeStore.initialize();
} if (online.value)
    await sync(); }
async function boot() { window.addEventListener("online", () => { online.value = true; void sync(); }); window.addEventListener("offline", () => online.value = false); try {
    await api.initialize();
    auth.value = !!api.tokens;
    if (auth.value)
        await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    ready.value = true;
} }
async function login() { busy.value = true; try {
    await api.login(email.value, password.value);
    auth.value = true;
    await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
async function logout() { await api.logout(); auth.value = false; ctx.value = {}; roster.value = null; }
async function openSession(s) { busy.value = true; try {
    roster.value = await api.request(`/portal/teacher/sessions/${s.id}/roster`);
    for (const st of roster.value.items || []) {
        attendance[st.student_id] = { status_code: st.attendance?.status_code || "present", minutes_present: st.attendance?.minutes_present ?? null, observation: st.attendance?.observation || "" };
    }
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
function operationForRoster() { if (!roster.value)
    throw new Error("Sessão não selecionada"); const records = (roster.value.items || []).map((s) => ({ student_id: s.student_id, ...attendance[s.student_id] })); return { idempotencyKey: `attendance-${roster.value.session_id}-${crypto.randomUUID()}`, aggregateType: "attendance_call", aggregateId: roster.value.session_id, baseRevision: Number(roster.value.call?.current_version || 0), localRevision: Number(roster.value.call?.current_version || 0) + 1, payload: { records, mode: "all_present_exceptions", origin: online.value ? "online" : "offline", device_id: "teacher-app" }, createdAt: new Date().toISOString() }; }
async function saveCall() { try {
    const op = operationForRoster();
    if (!online.value) {
        if (nativeStore)
            await nativeStore.enqueue(op);
        else
            webOutbox.enqueue(op);
        notice.value = "Chamada salva na outbox offline.";
        return;
    }
    await sendOp(op);
    notice.value = "Rascunho da chamada salvo.";
    await openSession(ctx.value.sessions.find((x) => x.id === roster.value?.session_id));
}
catch (e) {
    error.value = m(e);
} }
async function sendOp(op) { const result = await api.request(`/class-sessions/${op.aggregateId}/attendance`, { method: "PUT", headers: { "Content-Type": "application/json", "Idempotency-Key": op.idempotencyKey }, body: JSON.stringify(op.payload) }); if (nativeStore)
    await nativeStore.applyResult(op.idempotencyKey, result); return result; }
async function sync() { if (!online.value || !auth.value)
    return; try {
    if (nativeStore) {
        for (const op of await nativeStore.pending(100)) {
            await sendOp({ idempotencyKey: op.idempotency_key, aggregateType: op.aggregate_type, aggregateId: op.aggregate_id, baseRevision: op.base_revision, localRevision: op.base_revision + 1, payload: op.payload, createdAt: op.created_at });
        }
    }
    else {
        for (const op of webOutbox.pending(100)) {
            await sendOp(op);
            webOutbox.acknowledge(op.idempotencyKey);
        }
    }
}
catch (e) {
    error.value = `Sincronização pendente: ${m(e)}`;
} }
async function submitCall() { if (!roster.value)
    return; try {
    if (!online.value) {
        error.value = "Conecte-se à internet para enviar e fechar a chamada.";
        return;
    }
    const fresh = await api.request(`/portal/teacher/sessions/${roster.value.session_id}/roster`);
    if (!fresh.call) {
        error.value = "Salve o rascunho antes de enviar.";
        return;
    }
    await api.request(`/class-sessions/${roster.value.session_id}/attendance/submit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_call_version: fresh.call.current_version, origin: "online", device_id: "teacher-app" }) });
    notice.value = "Chamada enviada.";
    await load();
    await openSession(ctx.value.sessions.find((x) => x.id === roster.value?.session_id) || { id: roster.value.session_id });
}
catch (e) {
    error.value = m(e);
} }
async function createPlan() { const a = ctx.value.assignments.find((x) => x.id === plan.assignment_id); if (!a) {
    error.value = "Selecione uma atribuição.";
    return;
} const period = (ctx.value.academic_periods || []).filter((x) => x.academic_year_id === a.academic_year_id && x.starts_on <= plan.start_date && x.ends_on >= plan.end_date).sort((x, y) => (x.period_type === "annual" ? 1 : 0) - (y.period_type === "annual" ? 1 : 0))[0]; if (!period) {
    error.value = "Não existe período acadêmico ativo contendo as datas do planejamento.";
    return;
} try {
    await api.request("/teaching-plans", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": `plan-${crypto.randomUUID()}` }, body: JSON.stringify({ institution_id: a.institution_id, unit_id: a.unit_id, academic_period_id: period.id, program_id: a.program_id, curriculum_id: a.curriculum_id, class_group_id: a.class_group_id, component_id: a.component_id, teacher_ids: [api.claims()?.sub], plan_type: "weekly", title: plan.title, start_date: plan.start_date, end_date: plan.end_date, objectives: [], skills: [], competencies: [], curriculum_links: [], content: plan.content.split("\n").filter(Boolean), methodologies: [], resources: [], accommodations: [], assessments: [], homework: [], references: [], attachments: [], approval_required: true }) });
    notice.value = "Planejamento salvo.";
}
catch (e) {
    error.value = m(e);
} }
function dt(v) { return v ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—"; }
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
    }
    else if (!__VLS_ctx.auth) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("login") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.login) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("email"),
            required: (true),
        });
        (__VLS_ctx.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("password"),
            required: (true),
        });
        (__VLS_ctx.password);
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("shell") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.school);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.ctx.person?.full_name);
        (__VLS_ctx.online ? 'online' : 'offline');
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.sync) },
            ...{ class: ("sync") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({});
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        if (__VLS_ctx.notice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash success") },
            });
            (__VLS_ctx.notice);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("hero") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        (__VLS_ctx.ctx.person?.social_name || __VLS_ctx.ctx.person?.full_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (__VLS_ctx.ctx.assignments?.length || 0);
        (__VLS_ctx.ctx.sessions?.length || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [s] of __VLS_getVForSourceType((__VLS_ctx.ctx.sessions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        __VLS_ctx.openSession(s);
                    } },
                ...{ class: ("session") },
                key: ((s.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.dt(s.scheduled_start));
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (s.payload?.title || s.modality);
            (s.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        }
        if (!__VLS_ctx.ctx.sessions?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createPlan) },
            ...{ class: ("panel form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.plan.assignment_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.ctx.assignments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((a.id)),
                value: ((a.id)),
            });
            (a.class_group_name);
            (a.component_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.plan.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.plan.start_date);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.plan.end_date);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.plan.content)),
            rows: ("4"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
        if (__VLS_ctx.roster) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel attendance") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.roster.session_status);
            (__VLS_ctx.roster.call?.current_version || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((__VLS_ctx.online ? 'ok' : 'warn')) },
            });
            (__VLS_ctx.online ? 'Online' : 'Offline');
            for (const [s] of __VLS_getVForSourceType((__VLS_ctx.roster.items))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("student") },
                    key: ((s.student_id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (s.social_name || s.full_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (s.registration_number);
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.attendance[s.student_id].status_code)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("present"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("absent"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("late"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("justified_absence"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("early_departure"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("remote_present"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                    placeholder: ("Observação"),
                });
                (__VLS_ctx.attendance[s.student_id].observation);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("actions") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.saveCall) },
                ...{ class: ("secondary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.submitCall) },
            });
        }
        // @ts-ignore
        /** @type { [typeof EarlyChildhoodPanel, ] } */ ;
        // @ts-ignore
        const __VLS_0 = __VLS_asFunctionalComponent(EarlyChildhoodPanel, new EarlyChildhoodPanel({
            ...{ 'onNotice': {} },
            ...{ 'onError': {} },
            api: ((__VLS_ctx.api)),
            assignments: ((__VLS_ctx.ctx.assignments || [])),
        }));
        const __VLS_1 = __VLS_0({
            ...{ 'onNotice': {} },
            ...{ 'onError': {} },
            api: ((__VLS_ctx.api)),
            assignments: ((__VLS_ctx.ctx.assignments || [])),
        }, ...__VLS_functionalComponentArgsRest(__VLS_0));
        let __VLS_5;
        const __VLS_6 = {
            onNotice: (...[$event]) => {
                if (!(!((!__VLS_ctx.ready))))
                    return;
                if (!(!((!__VLS_ctx.auth))))
                    return;
                __VLS_ctx.notice = $event;
            }
        };
        const __VLS_7 = {
            onError: (...[$event]) => {
                if (!(!((!__VLS_ctx.ready))))
                    return;
                if (!(!((!__VLS_ctx.auth))))
                    return;
                __VLS_ctx.error = $event;
            }
        };
        let __VLS_2;
        let __VLS_3;
        var __VLS_4;
        // @ts-ignore
        /** @type { [typeof GradingPanel, ] } */ ;
        // @ts-ignore
        const __VLS_8 = __VLS_asFunctionalComponent(GradingPanel, new GradingPanel({
            ...{ 'onNotice': {} },
            ...{ 'onError': {} },
            api: ((__VLS_ctx.api)),
            assignments: ((__VLS_ctx.ctx.assignments || [])),
            periods: ((__VLS_ctx.ctx.academic_periods || [])),
        }));
        const __VLS_9 = __VLS_8({
            ...{ 'onNotice': {} },
            ...{ 'onError': {} },
            api: ((__VLS_ctx.api)),
            assignments: ((__VLS_ctx.ctx.assignments || [])),
            periods: ((__VLS_ctx.ctx.academic_periods || [])),
        }, ...__VLS_functionalComponentArgsRest(__VLS_8));
        let __VLS_13;
        const __VLS_14 = {
            onNotice: (...[$event]) => {
                if (!(!((!__VLS_ctx.ready))))
                    return;
                if (!(!((!__VLS_ctx.auth))))
                    return;
                __VLS_ctx.notice = $event;
            }
        };
        const __VLS_15 = {
            onError: (...[$event]) => {
                if (!(!((!__VLS_ctx.ready))))
                    return;
                if (!(!((!__VLS_ctx.auth))))
                    return;
                __VLS_ctx.error = $event;
            }
        };
        let __VLS_10;
        let __VLS_11;
        var __VLS_12;
    }
    ['center', 'login', 'mark', 'error', 'shell', 'sync', 'flash', 'error', 'flash', 'success', 'hero', 'grid', 'panel', 'session', 'empty', 'panel', 'form', 'cols', 'panel', 'attendance', 'section-title', 'pill', 'student', 'actions', 'secondary',];
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
            GradingPanel: GradingPanel,
            EarlyChildhoodPanel: EarlyChildhoodPanel,
            api: api,
            ready: ready,
            auth: auth,
            error: error,
            notice: notice,
            online: online,
            email: email,
            password: password,
            ctx: ctx,
            roster: roster,
            attendance: attendance,
            plan: plan,
            school: school,
            login: login,
            logout: logout,
            openSession: openSession,
            saveCall: saveCall,
            sync: sync,
            submitCall: submitCall,
            createPlan: createPlan,
            dt: dt,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
