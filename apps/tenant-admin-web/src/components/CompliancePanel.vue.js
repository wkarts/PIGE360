import { onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const dashboard = ref({}), notices = ref([]), processing = ref([]), requests = ref([]), retention = ref([]), holds = ref([]), busy = ref(false);
const noticeForm = reactive({ code: "PRIVACY-GENERAL", title: "Aviso de Privacidade", content: "", effective_from: new Date().toISOString().slice(0, 10), effective_until: "" });
const processingForm = reactive({ code: "", name: "", purpose: "", legal_basis: "", privacy_notice_code: "", data_categories: "", data_subjects: "", recipients: "", retention_rule: "", security_measures: "tenant_isolation, encryption, audit", owner_department: "" });
const retentionForm = reactive({ data_category: "", purpose_code: "", retention_days: 1825, disposition: "anonymize", legal_basis: "", starts_on: new Date().toISOString().slice(0, 10) });
const holdForm = reactive({ person_id: "", aggregate_type: "", aggregate_id: "", reason: "" });
function msg(e) { return e instanceof Error ? e.message : "Erro de compliance"; }
function list(v) { return v.split(",").map(x => x.trim()).filter(Boolean); }
async function load() { busy.value = true; try {
    const [d, n, p, r, ret, h] = await Promise.all([props.api.request("/compliance/dashboard"), props.api.request("/compliance/privacy-notices"), props.api.request("/compliance/processing-activities"), props.api.request("/compliance/data-subject-requests"), props.api.request("/compliance/retention-policies"), props.api.request("/compliance/legal-holds")]);
    dashboard.value = d;
    notices.value = n.items || [];
    processing.value = p.items || [];
    requests.value = r.items || [];
    retention.value = ret.items || [];
    holds.value = h.items || [];
}
catch (e) {
    emit("error", msg(e));
}
finally {
    busy.value = false;
} }
async function createNotice() { try {
    await props.api.request("/compliance/privacy-notices", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...noticeForm, effective_until: noticeForm.effective_until || null }) });
    emit("notice", "Nova versão do aviso criada.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function publish(n) { try {
    await props.api.request(`/compliance/privacy-notices/${n.id}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Publicação aprovada no painel de compliance" }) });
    emit("notice", "Aviso de privacidade publicado.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function createProcessing() { try {
    await props.api.request("/compliance/processing-activities", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: processingForm.code, name: processingForm.name, purpose: processingForm.purpose, legal_basis: processingForm.legal_basis, privacy_notice_code: processingForm.privacy_notice_code || null, data_categories: list(processingForm.data_categories), data_subjects: list(processingForm.data_subjects), recipients: list(processingForm.recipients), retention_rule: processingForm.retention_rule || null, security_measures: list(processingForm.security_measures), owner_department: processingForm.owner_department || null, international_transfer: false }) });
    emit("notice", "Atividade de tratamento registrada.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function stateRequest(row, state) { try {
    await props.api.request(`/compliance/data-subject-requests/${row.id}/state`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state, reason: `Tratamento administrativo: ${state}` }) });
    emit("notice", "Solicitação LGPD atualizada.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function exportRequest(row) { try {
    const result = await props.api.request(`/compliance/data-subject-requests/${row.id}/export`, { method: "POST" });
    emit("notice", `Exportação gerada · SHA-256 ${result.sha256.slice(0, 16)}…`);
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function anonymize(row) { if (!confirm("Confirmar anonimização controlada? A operação preserva fatos históricos e pseudonimiza o cadastro pessoal."))
    return; try {
    await props.api.request(`/compliance/data-subject-requests/${row.id}/anonymize`, { method: "POST" });
    emit("notice", "Anonimização executada e auditada.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function createRetention() { try {
    await props.api.request("/compliance/retention-policies", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...retentionForm, purpose_code: retentionForm.purpose_code || null }) });
    emit("notice", "Política de retenção criada.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function createHold() { try {
    await props.api.request("/compliance/legal-holds", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ person_id: holdForm.person_id || null, aggregate_type: holdForm.aggregate_type || null, aggregate_id: holdForm.aggregate_id || null, reason: holdForm.reason }) });
    emit("notice", "Legal hold criado.");
    await load();
}
catch (e) {
    emit("error", msg(e));
} }
async function releaseHold(row) { try {
    await props.api.request(`/compliance/legal-holds/${row.id}/release`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Motivo de preservação encerrado" }) });
    emit("notice", "Legal hold liberado.");
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
        ...{ class: ("compliance-panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("metrics") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.open_data_subject_requests || 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.active_consents || 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.active_legal_holds || 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.processing_activities || 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createNotice) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.noticeForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.noticeForm.title);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.noticeForm.content)),
        rows: ("8"),
        minlength: ("20"),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
        required: (true),
    });
    (__VLS_ctx.noticeForm.effective_from);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
    });
    (__VLS_ctx.noticeForm.effective_until);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("notice-list") },
    });
    for (const [n] of __VLS_getVForSourceType((__VLS_ctx.notices))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((n.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (n.title);
        (n.version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (n.code);
        (n.effective_from);
        (n.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (n.sha256);
        if (n.state === 'draft') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((n.state === 'draft')))
                            return;
                        __VLS_ctx.publish(n);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createProcessing) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.processingForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.processingForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.processingForm.purpose)),
        rows: ("3"),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.processingForm.legal_basis);
    if (__VLS_ctx.processingForm.legal_basis.toLowerCase() === 'consent') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            placeholder: ("PRIVACY-GENERAL"),
            required: (true),
        });
        (__VLS_ctx.processingForm.privacy_notice_code);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        placeholder: ("identificação, acadêmico, financeiro"),
    });
    (__VLS_ctx.processingForm.data_categories);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        placeholder: ("aluno, responsável, colaborador"),
    });
    (__VLS_ctx.processingForm.data_subjects);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.processingForm.recipients);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.processingForm.retention_rule);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.processingForm.security_measures);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("notice-list") },
    });
    for (const [p] of __VLS_getVForSourceType((__VLS_ctx.processing))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((p.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (p.name);
        (p.version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (p.purpose);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (p.legal_basis);
        ((p.data_categories || []).join(', '));
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
    for (const [r] of __VLS_getVForSourceType((__VLS_ctx.requests))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((r.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.protocol);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.request_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
        (r.subject_person_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
        });
        (r.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (r.due_at);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            ...{ class: ("row-actions") },
        });
        if (r.state === 'submitted') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((r.state === 'submitted')))
                            return;
                        __VLS_ctx.stateRequest(r, 'under_review');
                    } },
                ...{ class: ("small") },
            });
        }
        if (r.state === 'under_review') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((r.state === 'under_review')))
                            return;
                        __VLS_ctx.stateRequest(r, 'approved');
                    } },
                ...{ class: ("small") },
            });
        }
        if (['under_review', 'approved'].includes(r.state) && ['access', 'export'].includes(r.request_type)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((['under_review', 'approved'].includes(r.state) && ['access', 'export'].includes(r.request_type))))
                            return;
                        __VLS_ctx.exportRequest(r);
                    } },
                ...{ class: ("small") },
            });
        }
        if (r.request_type === 'anonymization' && r.state === 'approved') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((r.request_type === 'anonymization' && r.state === 'approved')))
                            return;
                        __VLS_ctx.anonymize(r);
                    } },
                ...{ class: ("small danger") },
            });
        }
        if (r.state === 'approved' && r.request_type !== 'anonymization') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((r.state === 'approved' && r.request_type !== 'anonymization')))
                            return;
                        __VLS_ctx.stateRequest(r, 'fulfilled');
                    } },
                ...{ class: ("small") },
            });
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createRetention) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.retentionForm.data_category);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.retentionForm.purpose_code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("1"),
        required: (true),
    });
    (__VLS_ctx.retentionForm.retention_days);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.retentionForm.disposition)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("archive"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("anonymize"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("delete"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.retentionForm.legal_basis);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("date"),
        required: (true),
    });
    (__VLS_ctx.retentionForm.starts_on);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("notice-list") },
    });
    for (const [r] of __VLS_getVForSourceType((__VLS_ctx.retention))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((r.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (r.data_category);
        (r.version);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (r.retention_days);
        (r.disposition);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (r.legal_basis);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createHold) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        placeholder: ("Titular"),
    });
    (__VLS_ctx.holdForm.person_id);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        placeholder: ("contract, fiscal_document…"),
    });
    (__VLS_ctx.holdForm.aggregate_type);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
    (__VLS_ctx.holdForm.aggregate_id);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.holdForm.reason)),
        rows: ("3"),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("notice-list") },
    });
    for (const [h] of __VLS_getVForSourceType((__VLS_ctx.holds))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((h.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (h.person_id || `${h.aggregate_type}/${h.aggregate_id}`);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (h.reason);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (h.state);
        (h.starts_at);
        if (h.state === 'active') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((h.state === 'active')))
                            return;
                        __VLS_ctx.releaseHold(h);
                    } },
                ...{ class: ("small") },
            });
        }
    }
    ['compliance-panel', 'metrics', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'notice-list', 'small', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'notice-list', 'panel', 'panel-title', 'pill', 'row-actions', 'small', 'small', 'small', 'small', 'danger', 'small', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'notice-list', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'notice-list', 'small',];
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
            dashboard: dashboard,
            notices: notices,
            processing: processing,
            requests: requests,
            retention: retention,
            holds: holds,
            noticeForm: noticeForm,
            processingForm: processingForm,
            retentionForm: retentionForm,
            holdForm: holdForm,
            createNotice: createNotice,
            publish: publish,
            createProcessing: createProcessing,
            stateRequest: stateRequest,
            exportRequest: exportRequest,
            anonymize: anonymize,
            createRetention: createRetention,
            createHold: createHold,
            releaseHold: releaseHold,
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
