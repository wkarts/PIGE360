import { computed, onMounted, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const templates = ref([]);
const notifications = ref([]);
const people = ref([]);
const preferences = ref([]);
const templateForm = reactive({
    template_key: "",
    name: "",
    channel: "internal",
    subject_template: "",
    body_template: "",
    variables: "",
});
const sendForm = reactive({
    recipient_person_id: "",
    channel: "internal",
    template_id: "",
    subject: "",
    body: "",
    scheduled_at: "",
});
const variables = reactive({});
const selectedTemplate = computed(() => templates.value.find((x) => x.id === sendForm.template_id));
const selectedVersion = computed(() => selectedTemplate.value?.versions?.find((x) => x.version === selectedTemplate.value?.current_version &&
    x.state === "published"));
const variableNames = computed(() => selectedVersion.value?.variables || []);
function msg(e) {
    return e instanceof Error ? e.message : "Falha na comunicação";
}
function dateBR(v) {
    if (!v)
        return "—";
    try {
        return new Intl.DateTimeFormat("pt-BR", {
            dateStyle: "short",
            timeStyle: "short",
        }).format(new Date(String(v)));
    }
    catch {
        return String(v);
    }
}
function idem(prefix) {
    return `${prefix}-${crypto.randomUUID()}`;
}
watch(() => sendForm.template_id, () => {
    for (const k of Object.keys(variables))
        delete variables[k];
    if (selectedTemplate.value)
        sendForm.channel = selectedTemplate.value.channel;
});
async function load() {
    loading.value = true;
    try {
        const [t, n, p, pr] = await Promise.all([
            props.api.request("/communication/templates"),
            props.api.request("/notifications?limit=100"),
            props.api.request("/people"),
            props.api
                .request("/communication/preferences/me")
                .catch(() => ({ items: [] })),
        ]);
        templates.value = t.items || [];
        notifications.value = n.items || [];
        people.value = p.items || [];
        preferences.value = pr.items || [];
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function createTemplate() {
    loading.value = true;
    try {
        await props.api.request("/communication/templates", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ...templateForm,
                subject_template: templateForm.subject_template || null,
                variables: templateForm.variables
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
            }),
        });
        Object.assign(templateForm, {
            template_key: "",
            name: "",
            channel: "internal",
            subject_template: "",
            body_template: "",
            variables: "",
        });
        await load();
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function publish(row) {
    loading.value = true;
    try {
        await props.api.request(`/communication/templates/${row.id}/publish`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                expected_version: row.current_version,
                reason: "Publicação pelo Branding/Comunicação administrativo",
            }),
        });
        await load();
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function send() {
    loading.value = true;
    try {
        const template = selectedTemplate.value;
        const body = {
            recipient_person_id: sendForm.recipient_person_id,
            channel: sendForm.channel,
            scheduled_at: sendForm.scheduled_at
                ? new Date(sendForm.scheduled_at).toISOString()
                : null,
        };
        if (template) {
            body.template_key = template.template_key;
            body.variables = { ...variables };
        }
        else {
            body.subject = sendForm.subject || null;
            body.body = sendForm.body;
        }
        await props.api.request("/notifications", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idem("notification"),
            },
            body: JSON.stringify(body),
        });
        Object.assign(sendForm, {
            recipient_person_id: "",
            channel: "internal",
            template_id: "",
            subject: "",
            body: "",
            scheduled_at: "",
        });
        await load();
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function retry(row) {
    loading.value = true;
    try {
        await props.api.request(`/notifications/${row.id}/retry`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason: "Retry solicitado pelo administrativo" }),
        });
        await load();
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function cancel(row) {
    loading.value = true;
    try {
        await props.api.request(`/notifications/${row.id}/cancel`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                reason: "Cancelamento solicitado pelo administrativo",
            }),
        });
        await load();
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['communication-grid', 'communication-grid',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("communication-grid") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.send) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.sendForm.recipient_person_id)),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [p] of __VLS_getVForSourceType((__VLS_ctx.people))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((p.id)),
            value: ((p.id)),
        });
        (p.full_name);
        (p.email || p.phone || "sem contato externo");
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.sendForm.template_id)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [t] of __VLS_getVForSourceType((__VLS_ctx.templates.filter((x) => x.state === 'published')))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((t.id)),
            value: ((t.id)),
        });
        (t.name);
        (t.channel);
    }
    if (!__VLS_ctx.selectedTemplate) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.sendForm.channel)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    }
    if (__VLS_ctx.selectedTemplate) {
        for (const [v] of __VLS_getVForSourceType((__VLS_ctx.variableNames))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
                key: ((v)),
            });
            (v);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.variables[v]);
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.sendForm.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.sendForm.body)),
            rows: ("5"),
            required: (true),
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("datetime-local"),
    });
    (__VLS_ctx.sendForm.scheduled_at);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        disabled: ((__VLS_ctx.loading)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createTemplate) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        pattern: ("[a-z0-9][a-z0-9._-]+"),
        placeholder: ("finance.due"),
        required: (true),
    });
    (__VLS_ctx.templateForm.template_key);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.templateForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.templateForm.channel)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        placeholder: ("Opcional"),
    });
    (__VLS_ctx.templateForm.subject_template);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.templateForm.body_template)),
        rows: ("5"),
        placeholder: ("Olá {{person.name}}"),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        placeholder: ("person.name, due_date"),
    });
    (__VLS_ctx.templateForm.variables);
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.templates.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [t] of __VLS_getVForSourceType((__VLS_ctx.templates))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((t.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (t.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (t.template_key);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.channel);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.current_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((t.state === 'published' ? 'ok' : 'warn')) },
        });
        (t.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        if (t.state !== 'published') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((t.state !== 'published')))
                            return;
                        __VLS_ctx.publish(t);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    if (!__VLS_ctx.templates.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            colspan: ("5"),
            ...{ class: ("empty") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        ...{ class: ("small") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [n] of __VLS_getVForSourceType((__VLS_ctx.notifications))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((n.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.dateBR(n.created_at));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.people.find((x) => x.id === n.recipient_person_id)
            ?.full_name ||
            n.recipient_person_id ||
            "—");
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (n.channel);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (n.subject || n.template_key || "Mensagem");
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((n.state === 'sent'
                    ? 'ok'
                    : n.state === 'failed'
                        ? 'danger'
                        : 'warn')) },
        });
        (n.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (n.attempts);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            ...{ class: ("row-actions") },
        });
        if (!['sent', 'cancelled', 'scheduled'].includes(n.state)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((!['sent', 'cancelled', 'scheduled'].includes(n.state))))
                            return;
                        __VLS_ctx.retry(n);
                    } },
                ...{ class: ("small") },
            });
        }
        if (!['sent', 'cancelled'].includes(n.state)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((!['sent', 'cancelled'].includes(n.state))))
                            return;
                        __VLS_ctx.cancel(n);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    if (!__VLS_ctx.notifications.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            colspan: ("7"),
            ...{ class: ("empty") },
        });
    }
    if (__VLS_ctx.preferences.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("preference-list") },
        });
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.preferences))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                key: ((p.channel)),
                ...{ class: ("pill") },
                ...{ class: ((p.enabled ? 'ok' : 'warn')) },
            });
            (p.channel);
            (p.enabled ? "ativo" : "desativado");
        }
    }
    ['communication-grid', 'panel', 'panel-title', 'primary', 'panel', 'panel-title', 'primary', 'panel', 'panel-title', 'pill', 'small', 'empty', 'panel', 'panel-title', 'small', 'pill', 'row-actions', 'small', 'small', 'empty', 'panel', 'panel-title', 'preference-list', 'pill',];
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
            templates: templates,
            notifications: notifications,
            people: people,
            preferences: preferences,
            templateForm: templateForm,
            sendForm: sendForm,
            variables: variables,
            selectedTemplate: selectedTemplate,
            variableNames: variableNames,
            dateBR: dateBR,
            load: load,
            createTemplate: createTemplate,
            publish: publish,
            send: send,
            retry: retry,
            cancel: cancel,
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
