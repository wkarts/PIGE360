import { computed, onMounted, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const students = ref([]), components = ref([]), selectedStudent = ref(""), integralization = ref({ enrollments: [] }), daily = ref([]), internships = ref([]), activities = ref([]), theses = ref([]), prerequisites = ref([]), busy = ref(false);
const internshipForm = reactive({ enrollment_id: "", organization_name: "", supervisor_name: "", starts_on: "", ends_on: "", required_hours: "0", notes: "" });
const activityForm = reactive({ enrollment_id: "", category: "extensão", title: "", requested_hours: "" });
const thesisForm = reactive({ enrollment_id: "", title: "", abstract: "" });
const prereqForm = reactive({ component_id: "", prerequisite_component_id: "", minimum_final_score: "" });
const enrollments = computed(() => integralization.value.enrollments || []);
function msg(e) { return e instanceof Error ? e.message : "Erro na progressão acadêmica"; }
async function boot() { try {
    const [s, c, p] = await Promise.all([props.api.request("/students?limit=500"), props.api.request("/curriculum-components"), props.api.request("/academic/component-prerequisites")]);
    students.value = s.items || [];
    components.value = c.items || [];
    prerequisites.value = p.items || [];
}
catch (e) {
    emit("error", msg(e));
} }
async function loadStudent() { integralization.value = { enrollments: [] }; daily.value = []; internships.value = []; activities.value = []; theses.value = []; if (!selectedStudent.value)
    return; busy.value = true; try {
    const [i, d, stages, acts, tcc] = await Promise.all([props.api.request(`/academic/students/${selectedStudent.value}/integralization`), props.api.request(`/academic/early-childhood/students/${selectedStudent.value}/daily-records`).catch(() => ({ items: [] })), props.api.request("/academic/internships"), props.api.request("/academic/complementary-activities"), props.api.request("/academic/theses")]);
    integralization.value = i;
    daily.value = d.items || [];
    const ids = new Set((i.enrollments || []).map((x) => x.enrollment.id));
    internships.value = (stages.items || []).filter((x) => ids.has(x.enrollment_id));
    activities.value = (acts.items || []).filter((x) => ids.has(x.enrollment_id));
    theses.value = (tcc.items || []).filter((x) => ids.has(x.enrollment_id));
    const first = i.enrollments?.[0]?.enrollment?.id || "";
    internshipForm.enrollment_id = first;
    activityForm.enrollment_id = first;
    thesisForm.enrollment_id = first;
}
catch (e) {
    emit("error", msg(e));
}
finally {
    busy.value = false;
} }
async function createPrerequisite() { try {
    await props.api.request("/academic/component-prerequisites", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ component_id: prereqForm.component_id, prerequisite_component_id: prereqForm.prerequisite_component_id, minimum_final_score: prereqForm.minimum_final_score || null }) });
    prerequisites.value = (await props.api.request("/academic/component-prerequisites")).items || [];
    emit("notice", "Pré-requisito curricular salvo.");
}
catch (e) {
    emit("error", msg(e));
} }
async function createInternship() { try {
    await props.api.request("/academic/internships", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...internshipForm, ends_on: internshipForm.ends_on || null, supervisor_name: internshipForm.supervisor_name || null, required_hours: internshipForm.required_hours || "0" }) });
    emit("notice", "Estágio cadastrado.");
    await loadStudent();
}
catch (e) {
    emit("error", msg(e));
} }
async function stageInternship(row, state) { try {
    await props.api.request(`/academic/internships/${row.id}/state`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state, expected_version: row.version, reason: `Alteração administrativa para ${state}` }) });
    emit("notice", "Estado do estágio atualizado.");
    await loadStudent();
}
catch (e) {
    emit("error", msg(e));
} }
async function createActivity() { try {
    await props.api.request("/academic/complementary-activities", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(activityForm) });
    emit("notice", "Atividade complementar registrada.");
    await loadStudent();
}
catch (e) {
    emit("error", msg(e));
} }
async function decideActivity(row, state) { try {
    const hours = state === "approved" ? String(row.requested_hours) : "0";
    await props.api.request(`/academic/complementary-activities/${row.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state, approved_hours: hours, notes: state === "approved" ? "Atividade homologada pela coordenação" : "Atividade não homologada pela coordenação" }) });
    emit("notice", "Atividade analisada.");
    await loadStudent();
}
catch (e) {
    emit("error", msg(e));
} }
async function createThesis() { try {
    await props.api.request("/academic/theses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...thesisForm, abstract: thesisForm.abstract || null }) });
    emit("notice", "TCC cadastrado.");
    await loadStudent();
}
catch (e) {
    emit("error", msg(e));
} }
async function stageThesis(row, state) { const payload = { state, expected_version: row.version, reason: `Alteração acadêmica para ${state}` }; if (state === "defended") {
    payload.defense_at = new Date().toISOString();
} try {
    await props.api.request(`/academic/theses/${row.id}/state`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    emit("notice", "Estado do TCC atualizado.");
    await loadStudent();
}
catch (e) {
    emit("error", msg(e));
} }
function componentName(id) { return components.value.find(x => x.id === id)?.name || id; }
watch(selectedStudent, () => void loadStudent());
onMounted(boot);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("academic-progress") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.selectedStudent)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [s] of __VLS_getVForSourceType((__VLS_ctx.students))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((s.id)),
            value: ((s.id)),
        });
        (s.full_name);
        (s.registration_number);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createPrerequisite) },
        ...{ class: ("panel") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.prereqForm.component_id)),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [c] of __VLS_getVForSourceType((__VLS_ctx.components))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((c.id)),
            value: ((c.id)),
        });
        (c.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.prereqForm.prerequisite_component_id)),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [c] of __VLS_getVForSourceType((__VLS_ctx.components))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((c.id)),
            value: ((c.id)),
        });
        (c.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("0"),
        step: ("0.01"),
    });
    (__VLS_ctx.prereqForm.minimum_final_score);
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
    for (const [p] of __VLS_getVForSourceType((__VLS_ctx.prerequisites.slice(0, 20)))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
            key: ((p.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.componentName(p.component_id));
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (p.prerequisite_name || __VLS_ctx.componentName(p.prerequisite_component_id));
        if (p.minimum_final_score) {
            (p.minimum_final_score);
        }
    }
    if (!__VLS_ctx.prerequisites.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    if (__VLS_ctx.selectedStudent) {
        if (__VLS_ctx.daily.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.daily.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.daily.slice(0, 30)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.record_date);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.mood || '—');
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.development_notes || '—');
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (r.version);
            }
        }
        for (const [en] of __VLS_getVForSourceType((__VLS_ctx.enrollments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                key: ((en.enrollment.id)),
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (en.enrollment.program_name);
            (en.enrollment.curriculum_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (en.curriculum.components_completed);
            (en.curriculum.components_total);
            (en.curriculum.workload_hours_completed);
            (en.curriculum.workload_hours_total);
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (en.curriculum.completion_percentage);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [c] of __VLS_getVForSourceType((en.components))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((c.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (c.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (c.workload_hours);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (c.credits || '—');
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                    ...{ class: ((c.completed ? 'ok' : 'warn')) },
                });
                (c.completed ? 'Sim' : 'Pendente');
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createInternship) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.internshipForm.enrollment_id)),
            required: (true),
        });
        for (const [e] of __VLS_getVForSourceType((__VLS_ctx.enrollments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((e.enrollment.id)),
                value: ((e.enrollment.id)),
            });
            (e.enrollment.program_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.internshipForm.organization_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({});
        (__VLS_ctx.internshipForm.supervisor_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.internshipForm.starts_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.internshipForm.ends_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.5"),
        });
        (__VLS_ctx.internshipForm.required_hours);
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
        for (const [i] of __VLS_getVForSourceType((__VLS_ctx.internships))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((i.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (i.organization_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (i.completed_hours);
            (i.required_hours);
            (i.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("row-actions") },
            });
            if (i.state === 'draft') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((i.state === 'draft')))
                                return;
                            __VLS_ctx.stageInternship(i, 'approved');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (i.state === 'approved') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((i.state === 'approved')))
                                return;
                            __VLS_ctx.stageInternship(i, 'in_progress');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (i.state === 'in_progress') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((i.state === 'in_progress')))
                                return;
                            __VLS_ctx.stageInternship(i, 'completed');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createActivity) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.activityForm.enrollment_id)),
            required: (true),
        });
        for (const [e] of __VLS_getVForSourceType((__VLS_ctx.enrollments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((e.enrollment.id)),
                value: ((e.enrollment.id)),
            });
            (e.enrollment.program_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.activityForm.category);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.activityForm.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.5"),
            step: ("0.5"),
            required: (true),
        });
        (__VLS_ctx.activityForm.requested_hours);
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
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.activities))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((a.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (a.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (a.category);
            (a.requested_hours);
            (a.state);
            if (a.state === 'submitted' || a.state === 'additional_information_required') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("row-actions") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((a.state === 'submitted' || a.state === 'additional_information_required')))
                                return;
                            __VLS_ctx.decideActivity(a, 'approved');
                        } },
                    ...{ class: ("small") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((a.state === 'submitted' || a.state === 'additional_information_required')))
                                return;
                            __VLS_ctx.decideActivity(a, 'rejected');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createThesis) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.thesisForm.enrollment_id)),
            required: (true),
        });
        for (const [e] of __VLS_getVForSourceType((__VLS_ctx.enrollments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((e.enrollment.id)),
                value: ((e.enrollment.id)),
            });
            (e.enrollment.program_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.thesisForm.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.thesisForm.abstract)),
            rows: ("4"),
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
        for (const [t] of __VLS_getVForSourceType((__VLS_ctx.theses))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((t.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (t.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (t.state);
            if (t.grade) {
                (t.grade);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("row-actions") },
            });
            if (t.state === 'proposal') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((t.state === 'proposal')))
                                return;
                            __VLS_ctx.stageThesis(t, 'approved');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (t.state === 'approved') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((t.state === 'approved')))
                                return;
                            __VLS_ctx.stageThesis(t, 'in_progress');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (t.state === 'in_progress') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((t.state === 'in_progress')))
                                return;
                            __VLS_ctx.stageThesis(t, 'submitted');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (t.state === 'submitted') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((t.state === 'submitted')))
                                return;
                            __VLS_ctx.stageThesis(t, 'defended');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (t.state === 'defended') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedStudent)))
                                return;
                            if (!((t.state === 'defended')))
                                return;
                            __VLS_ctx.stageThesis(t, 'passed');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    ['academic-progress', 'panel', 'panel-title', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'notice-list', 'empty', 'panel', 'panel-title', 'panel', 'panel-title', 'pill', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'notice-list', 'row-actions', 'small', 'small', 'small', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'notice-list', 'row-actions', 'small', 'small', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'notice-list', 'row-actions', 'small', 'small', 'small', 'small', 'small',];
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
            students: students,
            components: components,
            selectedStudent: selectedStudent,
            daily: daily,
            internships: internships,
            activities: activities,
            theses: theses,
            prerequisites: prerequisites,
            internshipForm: internshipForm,
            activityForm: activityForm,
            thesisForm: thesisForm,
            prereqForm: prereqForm,
            enrollments: enrollments,
            createPrerequisite: createPrerequisite,
            createInternship: createInternship,
            stageInternship: stageInternship,
            createActivity: createActivity,
            decideActivity: decideActivity,
            createThesis: createThesis,
            stageThesis: stageThesis,
            componentName: componentName,
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
