import { computed, onMounted, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const types = ref([]);
const requests = ref([]);
const notices = ref([]);
const workflows = ref([]);
const detail = ref(null);
const formValues = reactive({});
const typeForm = reactive({ code: "", name: "", department: "Secretaria", default_sla_hours: 72, workflow_definition_id: "" });
const fields = ref([{ name: "description", label: "Descrição", type: "string", required: true }]);
const openForm = reactive({ request_type: "", subject: "", priority: "normal", description: "" });
const comment = reactive({ body: "", visibility: "requester" });
const selectedType = computed(() => types.value.find(x => x.code === openForm.request_type));
const selectedVersion = computed(() => selectedType.value?.versions?.find((v) => v.version === selectedType.value.current_version && v.state === "published"));
const selectedFields = computed(() => selectedVersion.value?.form_schema?.fields || []);
function msg(e) { return e instanceof Error ? e.message : "Falha nas solicitações"; }
function dateBR(v) { if (!v)
    return "—"; try {
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(String(v)));
}
catch {
    return String(v);
} }
watch(() => openForm.request_type, () => { for (const k of Object.keys(formValues))
    delete formValues[k]; });
async function load() { loading.value = true; try {
    const [t, r, n, w] = await Promise.all([props.api.request("/request-types"), props.api.request("/service-requests"), props.api.request("/notices"), props.api.request("/workflows/definitions").catch(() => ({ items: [] }))]);
    types.value = t.items || [];
    requests.value = r.items || [];
    notices.value = n.items || [];
    workflows.value = w.items || [];
}
catch (e) {
    emit("error", msg(e));
}
finally {
    loading.value = false;
} }
function addField() { fields.value.push({ name: `field_${fields.value.length + 1}`, label: `Campo ${fields.value.length + 1}`, type: "string", required: false }); }
function removeField(i) { if (fields.value.length > 1)
    fields.value.splice(i, 1); }
async function createType() { loading.value = true; try {
    await props.api.request("/request-types", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: typeForm.code, name: typeForm.name, department: typeForm.department, default_sla_hours: typeForm.default_sla_hours, form_schema: { fields: fields.value.map(f => ({ name: f.name, label: f.label, type: f.type, required: f.required })) }, workflow: typeForm.workflow_definition_id ? { definition_id: typeForm.workflow_definition_id } : {} }) });
    Object.assign(typeForm, { code: "", name: "", department: "Secretaria", default_sla_hours: 72, workflow_definition_id: "" });
    await load();
}
catch (e) {
    emit("error", msg(e));
}
finally {
    loading.value = false;
} }
async function publishType(row) { try {
    await props.api.request(`/request-types/${row.id}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_version: row.current_version, reason: "Tipo publicado pelo administrativo" }) });
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function openRequest() { loading.value = true; try {
    await props.api.request("/service-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...openForm, form_data: { ...formValues } }) });
    Object.assign(openForm, { request_type: "", subject: "", priority: "normal", description: "" });
    for (const k of Object.keys(formValues))
        delete formValues[k];
    await load();
}
catch (e) {
    emit("error", msg(e));
}
finally {
    loading.value = false;
} }
async function show(row) { try {
    detail.value = await props.api.request(`/service-requests/${row.id}`);
}
catch (e) {
    emit("error", msg(e));
} }
async function transition(state) { if (!detail.value)
    return; try {
    await props.api.request(`/service-requests/${detail.value.id}/transition`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state, reason: `Transição para ${state} pelo administrativo` }) });
    await show(detail.value);
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function addComment() { if (!detail.value || !comment.body)
    return; try {
    await props.api.request(`/service-requests/${detail.value.id}/comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(comment) });
    comment.body = "";
    await show(detail.value);
}
catch (e) {
    emit("error", msg(e));
} }
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['req-grid', 'comments', 'req-grid', 'field-row', 'comment-form',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("req-grid") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.openRequest) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.openForm.request_type)),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [t] of __VLS_getVForSourceType((__VLS_ctx.types.filter(x => x.state === 'published')))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((t.id)),
            value: ((t.code)),
        });
        (t.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.openForm.subject);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.openForm.priority)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.openForm.description)),
        rows: ("3"),
    });
    for (const [f] of __VLS_getVForSourceType((__VLS_ctx.selectedFields))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            key: ((f.name)),
        });
        (f.label || f.name);
        if (f.type !== 'boolean') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ((f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : f.type === 'email' ? 'email' : 'text')),
                required: ((f.required)),
            });
            (__VLS_ctx.formValues[f.name]);
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("checkbox"),
            });
            (__VLS_ctx.formValues[f.name]);
        }
    }
    if (__VLS_ctx.selectedType?.workflow_instance_id) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("muted") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        disabled: ((__VLS_ctx.loading)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createType) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        pattern: ("[a-z0-9][a-z0-9._-]+"),
        required: (true),
    });
    (__VLS_ctx.typeForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.typeForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.typeForm.department);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("1"),
    });
    (__VLS_ctx.typeForm.default_sla_hours);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.typeForm.workflow_definition_id)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [w] of __VLS_getVForSourceType((__VLS_ctx.workflows.filter(x => x.state === 'published')))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((w.id)),
            value: ((w.id)),
        });
        (w.name);
        (w.current_version);
    }
    for (const [f, i] of __VLS_getVForSourceType((__VLS_ctx.fields))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: ((i)),
            ...{ class: ("field-row") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("nome"),
            required: (true),
        });
        (f.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("Rótulo"),
            required: (true),
        });
        (f.label);
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((f.type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (f.required);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.removeField(i);
                } },
            type: ("button"),
            ...{ class: ("small") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("row-actions") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.addField) },
        type: ("button"),
        ...{ class: ("small") },
    });
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [t] of __VLS_getVForSourceType((__VLS_ctx.types))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((t.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (t.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (t.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.department || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.default_sla_hours);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.current_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        if (t.state !== 'published') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((t.state !== 'published')))
                            return;
                        __VLS_ctx.publishType(t);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.requests.length);
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
    for (const [r] of __VLS_getVForSourceType((__VLS_ctx.requests))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((r.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.protocol);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.request_type);
        (r.request_type_version || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.dateBR(r.sla_due_at));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.workflow_instance_id ? 'ativo/vinculado' : '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
        });
        (r.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.show(r);
                } },
            ...{ class: ("small") },
        });
    }
    if (__VLS_ctx.detail) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        (__VLS_ctx.detail.protocol);
        (__VLS_ctx.detail.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!((__VLS_ctx.detail)))
                        return;
                    __VLS_ctx.detail = null;
                } },
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (__VLS_ctx.detail.description);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("row-actions") },
        });
        for (const [s] of __VLS_getVForSourceType((['in_progress', 'awaiting_requester', 'resolved', 'closed', 'cancelled', 'reopened']))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((__VLS_ctx.detail)))
                            return;
                        __VLS_ctx.transition(s);
                    } },
                key: ((s)),
                ...{ class: ("small") },
            });
            (s);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("comments") },
        });
        for (const [c] of __VLS_getVForSourceType((__VLS_ctx.detail.comments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((c.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (c.visibility);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (c.body);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.dateBR(c.created_at));
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.addComment) },
            ...{ class: ("comment-form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.comment.body)),
            rows: ("2"),
            placeholder: ("Comentário"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.comment.visibility)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("requester"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("internal"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("notice-list") },
    });
    for (const [n] of __VLS_getVForSourceType((__VLS_ctx.notices.slice(0, 12)))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((n.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (n.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (n.body);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.dateBR(n.created_at));
    }
    ['req-grid', 'panel', 'panel-title', 'muted', 'primary', 'panel', 'panel-title', 'cols', 'field-row', 'inline', 'small', 'row-actions', 'small', 'primary', 'panel', 'panel-title', 'small', 'small', 'panel', 'panel-title', 'pill', 'small', 'panel', 'panel-title', 'small', 'row-actions', 'small', 'comments', 'comment-form', 'primary', 'panel', 'panel-title', 'notice-list',];
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
            types: types,
            requests: requests,
            notices: notices,
            workflows: workflows,
            detail: detail,
            formValues: formValues,
            typeForm: typeForm,
            fields: fields,
            openForm: openForm,
            comment: comment,
            selectedType: selectedType,
            selectedFields: selectedFields,
            dateBR: dateBR,
            load: load,
            addField: addField,
            removeField: removeField,
            createType: createType,
            publishType: publishType,
            openRequest: openRequest,
            show: show,
            transition: transition,
            addComment: addComment,
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
