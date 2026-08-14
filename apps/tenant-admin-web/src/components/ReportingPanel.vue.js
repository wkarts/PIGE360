import { computed, onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const catalog = ref([]);
const runs = ref([]);
const payrollRuns = ref([]);
const selected = ref("");
const format = ref("pdf");
const parameters = reactive({});
const current = computed(() => catalog.value.find((x) => x.code === selected.value));
const required = computed(() => current.value?.required_parameters || []);
function message(e) {
    return e instanceof Error ? e.message : "Falha ao processar relatório";
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
function select(code) {
    selected.value = code;
    const item = catalog.value.find((x) => x.code === code);
    format.value = item?.formats[0] || "pdf";
    for (const key of Object.keys(parameters))
        delete parameters[key];
}
async function load() {
    loading.value = true;
    try {
        const [c, r, p] = await Promise.all([
            props.api.request("/reports/catalog"),
            props.api.request("/reports/runs"),
            props.api.request("/payroll/runs").catch(() => ({ items: [] })),
        ]);
        catalog.value = c.items || [];
        runs.value = r.items || [];
        payrollRuns.value = p.items || [];
        if (!selected.value && catalog.value[0])
            select(catalog.value[0].code);
    }
    catch (e) {
        emit("error", message(e));
    }
    finally {
        loading.value = false;
    }
}
async function run() {
    if (!current.value)
        return;
    loading.value = true;
    try {
        const clean = {};
        for (const key of required.value) {
            if (parameters[key])
                clean[key] = parameters[key];
        }
        await props.api.request("/reports/runs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                report_code: selected.value,
                format: format.value,
                parameters: clean,
            }),
        });
        await load();
    }
    catch (e) {
        emit("error", message(e));
    }
    finally {
        loading.value = false;
    }
}
async function sha256(data) {
    const digest = await crypto.subtle.digest("SHA-256", data);
    return [...new Uint8Array(digest)]
        .map((x) => x.toString(16).padStart(2, "0"))
        .join("");
}
async function download(row) {
    loading.value = true;
    try {
        const response = await props.api.response(`/reports/runs/${row.id}/download`);
        const data = await response.arrayBuffer();
        const expected = (response.headers.get("x-content-sha256") || "").toLowerCase();
        const actual = await sha256(data);
        if (expected && actual !== expected)
            throw new Error("Integridade do relatório inválida: SHA-256 divergente.");
        const blob = new Blob([data], {
            type: response.headers.get("content-type") || "application/octet-stream",
        });
        const disposition = response.headers.get("content-disposition") || "";
        const name = /filename="?([^";]+)"?/i.exec(disposition)?.[1] ||
            `${row.report_code}.${row.format}`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
    }
    catch (e) {
        emit("error", message(e));
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
    ['report-choice', 'report-choice', 'report-layout',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("report-layout") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.aside, __VLS_intrinsicElements.aside)({
        ...{ class: ("panel report-catalog") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.catalog.length);
    for (const [item] of __VLS_getVForSourceType((__VLS_ctx.catalog))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.select(item.code);
                } },
            key: ((item.code)),
            ...{ class: ("report-choice") },
            ...{ class: (({ selected: __VLS_ctx.selected === item.code })) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (item.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (item.description);
    }
    if (!__VLS_ctx.catalog.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.run) },
        ...{ class: ("panel report-run") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    (__VLS_ctx.current?.title || "Relatório");
    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    (__VLS_ctx.current?.description);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.format)),
    });
    for (const [f] of __VLS_getVForSourceType((__VLS_ctx.current?.formats || []))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((f)),
            value: ((f)),
        });
        (f.toUpperCase());
    }
    for (const [field] of __VLS_getVForSourceType((__VLS_ctx.required))) {
        (field);
        if (field === 'run_id') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.parameters[field])),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.payrollRuns))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((r.id)),
                    value: ((r.id)),
                });
                (r.competence);
                (r.run_type);
                (r.state);
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            (field);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.parameters[field]);
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        disabled: ((__VLS_ctx.loading || !__VLS_ctx.current)),
    });
    (__VLS_ctx.loading ? "Processando…" : "Gerar relatório");
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
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
    for (const [r] of __VLS_getVForSourceType((__VLS_ctx.runs))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((r.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.catalog.find((x) => x.code === r.report_code)
            ?.title || r.report_code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (String(r.format).toUpperCase());
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.rows_count ?? "—");
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((r.state === 'completed'
                    ? 'ok'
                    : r.state === 'failed'
                        ? 'danger'
                        : 'warn')) },
        });
        (r.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.dateBR(r.requested_at));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        if (r.state === 'completed') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((r.state === 'completed')))
                            return;
                        __VLS_ctx.download(r);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    if (!__VLS_ctx.runs.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            colspan: ("6"),
            ...{ class: ("empty") },
        });
    }
    ['report-layout', 'panel', 'report-catalog', 'panel-title', 'report-choice', 'selected', 'empty', 'panel', 'report-run', 'panel-title', 'primary', 'panel', 'panel-title', 'small', 'pill', 'small', 'empty',];
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
            catalog: catalog,
            runs: runs,
            payrollRuns: payrollRuns,
            selected: selected,
            format: format,
            parameters: parameters,
            current: current,
            required: required,
            dateBR: dateBR,
            select: select,
            load: load,
            run: run,
            download: download,
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
