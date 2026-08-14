import { onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const definitions = ref([]);
const instances = ref([]);
const tasks = ref([]);
const selected = ref(null);
const definitionForm = reactive({
    code: "",
    name: "",
    aggregate_type: "service_request",
});
const steps = ref([
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
function msg(e) {
    return e instanceof Error ? e.message : "Falha no workflow";
}
function idem() {
    return `workflow-${crypto.randomUUID()}`;
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
            props.api.request("/workflows/definitions"),
            props.api.request("/workflows/instances"),
            props.api.request("/workflows/tasks/me?state=open"),
        ]);
        definitions.value = d.items || [];
        instances.value = i.items || [];
        tasks.value = t.items || [];
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
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
function removeStep(index) {
    if (steps.value.length > 1)
        steps.value.splice(index, 1);
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
        await props.api.request(`/workflows/definitions/${row.id}/publish`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                expected_version: row.current_version,
                reason: "Publicação pelo administrativo",
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
async function start() {
    loading.value = true;
    try {
        let context = {};
        try {
            context = JSON.parse(startForm.context || "{}");
        }
        catch {
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
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function decide(task, decision) {
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
    }
    catch (e) {
        emit("error", msg(e));
    }
    finally {
        loading.value = false;
    }
}
async function detail(row) {
    loading.value = true;
    try {
        selected.value = await props.api.request(`/workflows/instances/${row.id}`);
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
    ['workflow-grid', 'step-head', 'cols', 'timeline', 'workflow-grid', 'cols',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("workflow-grid") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createDefinition) },
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
        placeholder: ("request.scholarship"),
        required: (true),
    });
    (__VLS_ctx.definitionForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.definitionForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.definitionForm.aggregate_type);
    for (const [s, index] of __VLS_getVForSourceType((__VLS_ctx.steps))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: ((s.key)),
            ...{ class: ("step") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("step-head") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (index + 1);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.removeStep(index);
                } },
            type: ("button"),
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (s.key);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (s.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((s.type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("approval"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("task"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("1"),
        });
        (s.due_hours);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("academic_coordinator, finance_manager"),
            required: (true),
        });
        (s.assignee_roles);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("completed ou chave"),
        });
        (s.approve_to);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("rejected ou chave"),
        });
        (s.reject_to);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("row-actions") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.addStep) },
        type: ("button"),
        ...{ class: ("small") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        disabled: ((__VLS_ctx.loading)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.start) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.startForm.definition_id)),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [d] of __VLS_getVForSourceType((__VLS_ctx.definitions.filter((x) => x.state === 'published')))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((d.id)),
            value: ((d.id)),
        });
        (d.name);
        (d.current_version);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.startForm.aggregate_type);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.startForm.aggregate_id);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.startForm.context)),
        rows: ("5"),
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [d] of __VLS_getVForSourceType((__VLS_ctx.definitions))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((d.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (d.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (d.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (d.aggregate_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (d.current_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((d.state === 'published' ? 'ok' : 'warn')) },
        });
        (d.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        if (d.state !== 'published') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((d.state !== 'published')))
                            return;
                        __VLS_ctx.publish(d);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    if (!__VLS_ctx.definitions.length) {
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.tasks.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [t] of __VLS_getVForSourceType((__VLS_ctx.tasks))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((t.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (t.step_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (t.step_key);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.aggregate_type);
        (t.aggregate_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.dateBR(t.due_at));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((t.sla_state === 'breached'
                    ? 'danger'
                    : t.sla_state === 'overdue'
                        ? 'warn'
                        : 'ok')) },
        });
        (t.sla_state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            ...{ class: ("row-actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.decide(t, t.task_type === 'task' ? 'complete' : 'approve');
                } },
            ...{ class: ("small") },
        });
        (t.task_type === "task" ? "Concluir" : "Aprovar");
        if (t.task_type === 'approval') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((t.task_type === 'approval')))
                            return;
                        __VLS_ctx.decide(t, 'reject');
                    } },
                ...{ class: ("small danger") },
            });
        }
    }
    if (!__VLS_ctx.tasks.length) {
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.instances.length);
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
    for (const [i] of __VLS_getVForSourceType((__VLS_ctx.instances))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((i.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.dateBR(i.started_at));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.aggregate_type);
        (i.aggregate_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.definition_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.current_step_key || "—");
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((i.state === 'completed'
                    ? 'ok'
                    : i.state === 'rejected' || i.state === 'cancelled'
                        ? 'danger'
                        : 'warn')) },
        });
        (i.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.detail(i);
                } },
            ...{ class: ("small") },
        });
    }
    if (__VLS_ctx.selected) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!((__VLS_ctx.selected)))
                        return;
                    __VLS_ctx.selected = null;
                } },
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("timeline") },
        });
        for (const [e] of __VLS_getVForSourceType((__VLS_ctx.selected.events))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((e.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (e.event_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.dateBR(e.occurred_at));
            (e.from_step_key || "início");
            (e.to_step_key || e.to_state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (e.comment || "");
        }
    }
    ['workflow-grid', 'panel', 'panel-title', 'step', 'step-head', 'small', 'cols', 'cols', 'row-actions', 'small', 'primary', 'panel', 'panel-title', 'primary', 'panel', 'panel-title', 'small', 'pill', 'small', 'empty', 'panel', 'panel-title', 'pill', 'row-actions', 'small', 'small', 'danger', 'empty', 'panel', 'panel-title', 'pill', 'small', 'panel', 'panel-title', 'small', 'timeline',];
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
            definitions: definitions,
            instances: instances,
            tasks: tasks,
            selected: selected,
            definitionForm: definitionForm,
            steps: steps,
            startForm: startForm,
            dateBR: dateBR,
            load: load,
            addStep: addStep,
            removeStep: removeStep,
            createDefinition: createDefinition,
            publish: publish,
            start: start,
            decide: decide,
            detail: detail,
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
