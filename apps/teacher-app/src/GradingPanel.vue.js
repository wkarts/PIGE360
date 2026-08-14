import { computed, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const selectedAssignment = ref(""), selectedPeriod = ref(""), assessments = ref([]), detail = ref(null), results = ref([]), busy = ref(false);
const form = reactive({
    title: "",
    assessment_type: "exam",
    weight: "1",
    max_score: "10",
    due_on: "",
});
const gradeForm = reactive({});
const assignment = computed(() => props.assignments.find((x) => x.id === selectedAssignment.value));
const periods = computed(() => props.periods.filter((x) => !assignment.value ||
    x.academic_year_id === assignment.value.academic_year_id));
async function loadAssessments() {
    detail.value = null;
    results.value = [];
    if (!assignment.value || !selectedPeriod.value) {
        assessments.value = [];
        return;
    }
    try {
        const a = assignment.value;
        const r = await props.api.request(`/pedagogy/assessments?academic_period_id=${selectedPeriod.value}&class_group_id=${a.class_group_id}&component_id=${a.component_id}`);
        assessments.value = r.items || [];
    }
    catch (e) {
        emit("error", e instanceof Error ? e.message : "Erro ao carregar avaliações");
    }
}
async function createAssessment() {
    if (!assignment.value || !selectedPeriod.value)
        return;
    busy.value = true;
    try {
        const a = assignment.value;
        const created = await props.api.request("/pedagogy/assessments", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                academic_period_id: selectedPeriod.value,
                class_group_id: a.class_group_id,
                component_id: a.component_id,
                title: form.title,
                assessment_type: form.assessment_type,
                weight: form.weight,
                max_score: form.max_score,
                due_on: form.due_on || null,
            }),
        });
        await props.api.request(`/pedagogy/assessments/${created.id}/publish`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                expected_version: created.version,
                reason: "Avaliação publicada pelo professor",
            }),
        });
        Object.assign(form, {
            title: "",
            assessment_type: "exam",
            weight: "1",
            max_score: "10",
            due_on: "",
        });
        emit("notice", "Avaliação criada e publicada.");
        await loadAssessments();
    }
    catch (e) {
        emit("error", e instanceof Error ? e.message : "Erro ao criar avaliação");
    }
    finally {
        busy.value = false;
    }
}
async function openAssessment(row) {
    busy.value = true;
    try {
        const assessmentDetail = await props.api.request(`/pedagogy/assessments/${row.id}`);
        detail.value = assessmentDetail;
        for (const student of assessmentDetail.roster || []) {
            const existing = (assessmentDetail.grades || []).find((g) => g.enrollment_id === student.enrollment_id);
            gradeForm[student.enrollment_id] = {
                score: existing?.score == null ? "" : String(existing.score),
                feedback: existing?.feedback || "",
                version: existing?.version ?? null,
            };
        }
    }
    catch (e) {
        emit("error", e instanceof Error ? e.message : "Erro ao abrir avaliação");
    }
    finally {
        busy.value = false;
    }
}
async function saveGrades() {
    if (!detail.value)
        return;
    busy.value = true;
    try {
        const grades = (detail.value.roster || []).map((student) => {
            const g = gradeForm[student.enrollment_id];
            return {
                enrollment_id: student.enrollment_id,
                score: g?.score === "" ? null : g?.score,
                status: g?.score === "" ? "missing" : "graded",
                feedback: g?.feedback || null,
                expected_version: g?.version ?? null,
            };
        });
        await props.api.request(`/pedagogy/assessments/${detail.value.id}/grades`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                reason: "Lançamento pelo diário do professor",
                grades,
            }),
        });
        emit("notice", "Notas salvas com versionamento.");
        await openAssessment(detail.value);
    }
    catch (e) {
        emit("error", e instanceof Error ? e.message : "Erro ao salvar notas");
    }
    finally {
        busy.value = false;
    }
}
async function calculate() {
    if (!assignment.value || !selectedPeriod.value)
        return;
    busy.value = true;
    try {
        const a = assignment.value;
        const r = await props.api.request("/pedagogy/period-results/calculate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                academic_period_id: selectedPeriod.value,
                class_group_id: a.class_group_id,
                component_id: a.component_id,
            }),
        });
        results.value = r.items || [];
        emit("notice", "Médias recalculadas pelas regras vigentes.");
    }
    catch (e) {
        emit("error", e instanceof Error ? e.message : "Erro ao calcular resultados");
    }
    finally {
        busy.value = false;
    }
}
watch([selectedAssignment, selectedPeriod], () => void loadAssessments());
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel grading") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("section-title") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.selectedAssignment)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [a] of __VLS_getVForSourceType((__VLS_ctx.assignments))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((a.id)),
            value: ((a.id)),
        });
        (a.class_group_name);
        (a.component_name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.selectedPeriod)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [p] of __VLS_getVForSourceType((__VLS_ctx.periods))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((p.id)),
            value: ((p.id)),
        });
        (p.name);
    }
    if (__VLS_ctx.selectedAssignment && __VLS_ctx.selectedPeriod) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createAssessment) },
            ...{ class: ("grade-create") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("Título da avaliação"),
            required: (true),
        });
        (__VLS_ctx.form.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.form.assessment_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("exam"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("work"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("project"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("formative"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0.01"),
            title: ("Peso"),
        });
        (__VLS_ctx.form.weight);
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            step: ("0.01"),
            min: ("0.01"),
            title: ("Nota máxima"),
        });
        (__VLS_ctx.form.max_score);
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.form.due_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            disabled: ((__VLS_ctx.busy)),
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("assessment-list") },
    });
    for (const [a] of __VLS_getVForSourceType((__VLS_ctx.assessments))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.openAssessment(a);
                } },
            key: ((a.id)),
            ...{ class: ("assessment-card") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (a.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (a.assessment_type);
        (a.weight);
        (a.max_score);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (a.state);
    }
    if (__VLS_ctx.selectedPeriod && !__VLS_ctx.assessments.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    if (__VLS_ctx.detail) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("grade-sheet") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
        (__VLS_ctx.detail.title);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.detail.state);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("grade-row head") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.detail.max_score);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        for (const [s] of __VLS_getVForSourceType((__VLS_ctx.detail.roster))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((s.enrollment_id)),
                ...{ class: ("grade-row") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (s.social_name || s.full_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (s.registration_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.01"),
                min: ("0"),
                max: ((__VLS_ctx.detail.max_score)),
            });
            (__VLS_ctx.gradeForm[s.enrollment_id].score);
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("Feedback"),
            });
            (__VLS_ctx.gradeForm[s.enrollment_id].feedback);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.calculate) },
            ...{ class: ("secondary") },
            disabled: ((__VLS_ctx.busy)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.saveGrades) },
            disabled: ((__VLS_ctx.busy)),
        });
    }
    if (__VLS_ctx.results.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("result-grid") },
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.results))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((r.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (r.final_score);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (r.outcome);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (r.attendance_percentage);
        }
    }
    ['panel', 'grading', 'section-title', 'cols', 'grade-create', 'assessment-list', 'assessment-card', 'empty', 'grade-sheet', 'section-title', 'grade-row', 'head', 'grade-row', 'actions', 'secondary', 'result-grid',];
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
            selectedAssignment: selectedAssignment,
            selectedPeriod: selectedPeriod,
            assessments: assessments,
            detail: detail,
            results: results,
            busy: busy,
            form: form,
            gradeForm: gradeForm,
            periods: periods,
            createAssessment: createAssessment,
            openAssessment: openAssessment,
            saveGrades: saveGrades,
            calculate: calculate,
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
