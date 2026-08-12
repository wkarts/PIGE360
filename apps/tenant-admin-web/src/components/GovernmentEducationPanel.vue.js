import { onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const busy = ref(false), layouts = ref([]), validations = ref([]), imports = ref([]), exports = ref([]), transmissions = ref([]), connections = ref([]), issues = ref([]);
const importFile = ref(null);
const today = new Date().toISOString().slice(0, 10);
const layoutForm = reactive({ authority: "INEP", layout_code: "EDUCACENSO-MATRICULA", version: "2026.1", effective_from: today, fields_json: '[{"name":"student_code","required":true,"max_length":20},{"name":"enrollment_state","required":true,"enum":["ACTIVE","TRANSFERRED"]}]' });
const runForm = reactive({ layout_id: "", reference_period: "2026", records_json: '[{"student_code":"ABC123","enrollment_state":"ACTIVE"}]' });
const importForm = reactive({ layout_id: "", reference_period: "2026" });
function msg(e) { return e instanceof Error ? e.message : "Erro na integração educacional"; }
function parseRecords(v) { const x = JSON.parse(v); if (!Array.isArray(x))
    throw new Error("Informe uma lista JSON de registros."); return x; }
function parseFields(v) { const x = JSON.parse(v); if (!Array.isArray(x) || !x.length)
    throw new Error("Informe ao menos um campo no layout."); return x; }
async function load() { busy.value = true; try {
    const [l, v, i, e, t, c] = await Promise.all([props.api.request("/government-education/layouts"), props.api.request("/government-education/validations"), props.api.request("/government-education/imports"), props.api.request("/government-education/exports"), props.api.request("/government-education/transmissions"), props.api.request("/integration-connections")]);
    layouts.value = l.items || [];
    validations.value = v.items || [];
    imports.value = i.items || [];
    exports.value = e.items || [];
    transmissions.value = t.items || [];
    connections.value = (c.items || []).filter((x) => (x.capabilities || []).includes("government_submission"));
    if (!runForm.layout_id && layouts.value[0])
        runForm.layout_id = layouts.value[0].id;
    if (!importForm.layout_id && layouts.value[0])
        importForm.layout_id = layouts.value[0].id;
}
catch (e) {
    emit("error", msg(e));
}
finally {
    busy.value = false;
} }
async function createLayout() { try {
    await props.api.request("/government-education/layouts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ authority: layoutForm.authority, layout_code: layoutForm.layout_code, version: layoutForm.version, effective_from: layoutForm.effective_from, layout_schema: { format: "csv", fields: parseFields(layoutForm.fields_json) } }) });
    emit("notice", "Layout governamental versionado registrado.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function validate() { try {
    const r = await props.api.request("/government-education/validations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layout_id: runForm.layout_id, reference_period: runForm.reference_period, direction: "export", records: parseRecords(runForm.records_json) }) });
    issues.value = r.issues || [];
    emit("notice", r.state === "valid" ? "Validação concluída sem inconsistências." : `Validação encontrou ${r.error_count} erro(s).`);
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function generateExport() { try {
    const r = await props.api.request("/government-education/exports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layout_id: runForm.layout_id, reference_period: runForm.reference_period, records: parseRecords(runForm.records_json) }) });
    emit("notice", `Exportação gerada · SHA-256 ${String(r.sha256).slice(0, 16)}…`);
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function uploadImport() { if (!importFile.value)
    return; try {
    const body = new FormData();
    body.append("file", importFile.value);
    const q = new URLSearchParams({ layout_id: importForm.layout_id, reference_period: importForm.reference_period });
    const r = await props.api.request(`/government-education/imports?${q}`, { method: "POST", body });
    emit("notice", `Importação ${r.state}: ${r.accepted_count} aceitos / ${r.rejected_count} rejeitados.`);
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function showIssues(run) { try {
    const r = await props.api.request(`/government-education/validations/${run.id}/issues`);
    issues.value = r.items || [];
}
catch (e) {
    emit("error", msg(e));
} }
async function download(path, filename) { try {
    const response = await props.api.response(path);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}
catch (e) {
    emit("error", msg(e));
} }
async function transmit(row) { try {
    const connection = connections.value[0]?.id || null;
    const r = await props.api.request(`/government-education/exports/${row.id}/transmissions`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": `gov-${row.id}-${crypto.randomUUID()}` }, body: JSON.stringify({ connection_id: connection }) });
    emit("notice", r.state === "queued" ? "Transmissão enviada para a fila do provider configurado." : "Exportação aguardando configuração de provider governamental.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function retry(row) { try {
    await props.api.request(`/government-education/transmissions/${row.id}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Reprocessamento solicitado pelo operador autorizado" }) });
    emit("notice", "Transmissão governamental reavaliada/reprocessada.");
    await load();
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("government-panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createLayout) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.layoutForm.authority)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.layoutForm.layout_code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.layoutForm.version);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
        required: (true),
    });
    (__VLS_ctx.layoutForm.effective_from);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.layoutForm.fields_json)),
        rows: ("7"),
        spellcheck: ("false"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.validate) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.runForm.layout_id)),
        required: (true),
    });
    for (const [l] of __VLS_getVForSourceType((__VLS_ctx.layouts))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((l.id)),
            value: ((l.id)),
        });
        (l.authority);
        (l.layout_code);
        (l.version);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.runForm.reference_period);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.runForm.records_json)),
        rows: ("8"),
        spellcheck: ("false"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("row-actions") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.generateExport) },
        type: ("button"),
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.uploadImport) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.importForm.layout_id)),
        required: (true),
    });
    for (const [l] of __VLS_getVForSourceType((__VLS_ctx.layouts))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((l.id)),
            value: ((l.id)),
        });
        (l.authority);
        (l.layout_code);
        (l.version);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.importForm.reference_period);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        ...{ onChange: (...[$event]) => {
                __VLS_ctx.importFile = $event.target.files?.[0] || null;
            } },
        type: ("file"),
        accept: (".csv,text/csv"),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
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
    for (const [i] of __VLS_getVForSourceType((__VLS_ctx.issues))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((i.id || `${i.row_number}-${i.field_code}-${i.code}`)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.row_number || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.field_code || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (i.message);
    }
    if (!__VLS_ctx.issues.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            colspan: ("4"),
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
    (__VLS_ctx.validations.length);
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
    for (const [v] of __VLS_getVForSourceType((__VLS_ctx.validations))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((v.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (v.reference_period);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (v.direction);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((v.state === 'valid' ? 'ok' : 'danger')) },
        });
        (v.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (v.record_count);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (v.error_count);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.showIssues(v);
                } },
            ...{ class: ("small") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("notice-list") },
    });
    for (const [i] of __VLS_getVForSourceType((__VLS_ctx.imports.slice(0, 8)))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((i.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (i.original_filename);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (i.reference_period);
        (i.state);
        (i.accepted_count);
        (i.rejected_count);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (i.sha256);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.download(`/government-education/imports/${i.id}/download`, i.original_filename);
                } },
            ...{ class: ("small") },
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
    (__VLS_ctx.exports.length);
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
    for (const [e] of __VLS_getVForSourceType((__VLS_ctx.exports))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((e.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (e.authority);
        (e.layout_code);
        (e.layout_version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (e.reference_period);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
        });
        (e.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (String(e.sha256).slice(0, 16));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (e.protocol || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            ...{ class: ("row-actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.download(`/government-education/exports/${e.id}/download`, `government-${e.id}.csv`);
                } },
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.transmit(e);
                } },
            ...{ class: ("small") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
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
    for (const [t] of __VLS_getVForSourceType((__VLS_ctx.transmissions))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((t.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (String(t.export_id).slice(0, 8));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.environment);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((t.state === 'accepted' ? 'ok' : t.state === 'rejected' || t.state === 'failed' ? 'danger' : 'warn')) },
        });
        (t.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.attempts);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (t.protocol || 'Aguardando retorno real');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        if (!['accepted', 'transmitting'].includes(t.state)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((!['accepted', 'transmitting'].includes(t.state))))
                            return;
                        __VLS_ctx.retry(t);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: ("empty") },
    });
    ['government-panel', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'row-actions', 'primary', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'empty', 'panel', 'panel-title', 'pill', 'small', 'notice-list', 'small', 'panel', 'panel-title', 'pill', 'row-actions', 'small', 'small', 'pill', 'small', 'empty',];
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
            layouts: layouts,
            validations: validations,
            imports: imports,
            exports: exports,
            transmissions: transmissions,
            issues: issues,
            importFile: importFile,
            layoutForm: layoutForm,
            runForm: runForm,
            importForm: importForm,
            createLayout: createLayout,
            validate: validate,
            generateExport: generateExport,
            uploadImport: uploadImport,
            showIssues: showIssues,
            download: download,
            transmit: transmit,
            retry: retry,
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
    __typeEl: {},
});
; /* PartiallyEnd: #4569/main.vue */
