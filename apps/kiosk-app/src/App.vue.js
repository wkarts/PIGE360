import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref(""), email = ref(""), password = ref("");
const ctx = ref({ branding: {}, requests: [], library_loans: [] });
const form = reactive({ request_type: "administrative", subject: "", description: "", priority: "normal", department: "Secretaria", sla_hours: 72 });
const school = computed(() => ctx.value.branding?.short_name || ctx.value.branding?.trade_name || ctx.value.branding?.legal_name || "Instituição");
function msg(e) { const p = e?.problem; return p?.detail || (e instanceof Error ? e.message : "Erro inesperado"); }
function apply() { document.documentElement.style.setProperty("--brand-primary", ctx.value.branding?.primary_color || "#006D77"); document.documentElement.style.setProperty("--brand-secondary", ctx.value.branding?.secondary_color || "#0D1B2A"); document.title = `${school.value} — Autoatendimento`; }
async function load() { ctx.value = await api.request("/portal/kiosk/me"); const b = await api.request("/branding/current"); ctx.value.branding = b.payload || b; apply(); }
async function boot() { try {
    await api.initialize();
    auth.value = !!api.tokens;
    if (auth.value)
        await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    ready.value = true;
} }
async function login() { try {
    await api.login(email.value, password.value);
    auth.value = true;
    await load();
}
catch (e) {
    error.value = msg(e);
} }
async function logout() { await api.logout(); auth.value = false; }
async function createRequest() { busy.value = true; try {
    await api.request("/service-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    notice.value = "Protocolo criado.";
    Object.assign(form, { request_type: "administrative", subject: "", description: "", priority: "normal", department: "Secretaria", sla_hours: 72 });
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
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
            ...{ class: ("login-page") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.login) },
            ...{ class: ("login-card") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
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
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mobile-shell") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("brand") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.school);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
            ...{ class: ("ghost") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({});
        if (__VLS_ctx.notice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash success") },
            });
            (__VLS_ctx.notice);
        }
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("welcome") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        (__VLS_ctx.ctx.person?.social_name || __VLS_ctx.ctx.person?.full_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid two") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRequest) },
            ...{ class: ("panel form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.form.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.form.description)),
            rows: ("5"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.busy)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [l] of __VLS_getVForSourceType((__VLS_ctx.ctx.library_loans))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list-row") },
                key: ((l.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (l.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (l.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (l.due_at || l.due_date);
        }
        if (!__VLS_ctx.ctx.library_loans?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.ctx.requests?.length || 0);
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.ctx.requests))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list-row") },
                key: ((r.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (r.protocol);
            (r.subject);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (r.request_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (r.state);
        }
        if (!__VLS_ctx.ctx.requests?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
    }
    ['center', 'login-page', 'login-card', 'mark', 'eyebrow', 'flash', 'error', 'primary', 'mobile-shell', 'brand', 'mark', 'ghost', 'flash', 'success', 'flash', 'error', 'welcome', 'grid', 'two', 'panel', 'form', 'primary', 'panel', 'list-row', 'empty', 'panel', 'section-title', 'list-row', 'empty',];
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
            ready: ready,
            auth: auth,
            busy: busy,
            error: error,
            notice: notice,
            email: email,
            password: password,
            ctx: ctx,
            form: form,
            school: school,
            login: login,
            logout: logout,
            createRequest: createRequest,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
