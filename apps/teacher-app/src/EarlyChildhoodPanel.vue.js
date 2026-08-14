import { computed, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const infantLevels = new Set([
    "infantil",
    "educacao_infantil",
    "educação_infantil",
    "early_childhood",
]);
const infantAssignments = computed(() => props.assignments.filter((a) => infantLevels.has(String(a.education_level || "")
    .toLowerCase()
    .replace(/ /g, "_"))));
const assignmentId = ref("");
const students = ref([]);
const selectedStudent = ref("");
const history = ref([]);
const guardians = ref([]);
const busy = ref(false);
const form = reactive({
    record_date: new Date().toISOString().slice(0, 10),
    mood: "",
    meal: "",
    consumption: "completo",
    sleep_start: "",
    sleep_end: "",
    hygiene: "",
    diaper_change: "",
    development_notes: "",
});
const pickup = reactive({
    guardian_id: "",
    released_at: "",
    identity_document_masked: "",
    notes: "",
});
function message(e) {
    return e instanceof Error ? e.message : "Erro ao operar agenda infantil";
}
async function loadStudents() {
    students.value = [];
    selectedStudent.value = "";
    history.value = [];
    guardians.value = [];
    if (!assignmentId.value)
        return;
    busy.value = true;
    try {
        const r = await props.api.request(`/portal/teacher/assignments/${assignmentId.value}/students`);
        students.value = r.items || [];
    }
    catch (e) {
        emit("error", message(e));
    }
    finally {
        busy.value = false;
    }
}
async function loadStudent() {
    history.value = [];
    guardians.value = [];
    if (!selectedStudent.value)
        return;
    busy.value = true;
    try {
        const [d, g] = await Promise.all([
            props.api.request(`/academic/early-childhood/students/${selectedStudent.value}/daily-records`),
            props.api.request(`/academic/early-childhood/students/${selectedStudent.value}/authorized-pickups`),
        ]);
        history.value = d.items || [];
        guardians.value = g.items || [];
    }
    catch (e) {
        emit("error", message(e));
    }
    finally {
        busy.value = false;
    }
}
async function save() {
    if (!selectedStudent.value)
        return;
    busy.value = true;
    try {
        const body = {
            student_id: selectedStudent.value,
            record_date: form.record_date,
            meals: form.meal
                ? [{ meal: form.meal, consumption: form.consumption }]
                : [],
            sleep: form.sleep_start
                ? { started_at: form.sleep_start, ended_at: form.sleep_end || null }
                : {},
            hygiene: form.hygiene ? [{ type: form.hygiene }] : [],
            diaper_changes: form.diaper_change ? [{ type: form.diaper_change }] : [],
            mood: form.mood || null,
            development_notes: form.development_notes || null,
            authorized_photos: [],
        };
        await props.api.request("/academic/early-childhood/daily-records", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        emit("notice", "Agenda diária registrada.");
        await loadStudent();
    }
    catch (e) {
        emit("error", message(e));
    }
    finally {
        busy.value = false;
    }
}
async function release() {
    if (!selectedStudent.value || !pickup.guardian_id || !pickup.released_at)
        return;
    busy.value = true;
    try {
        await props.api.request("/academic/early-childhood/pickups", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                student_id: selectedStudent.value,
                guardian_id: pickup.guardian_id,
                released_at: new Date(pickup.released_at).toISOString(),
                identity_document_masked: pickup.identity_document_masked || null,
                notes: pickup.notes || null,
            }),
        });
        emit("notice", "Retirada registrada com responsável autorizado.");
        Object.assign(pickup, {
            guardian_id: "",
            released_at: "",
            identity_document_masked: "",
            notes: "",
        });
        await loadStudent();
    }
    catch (e) {
        emit("error", message(e));
    }
    finally {
        busy.value = false;
    }
}
watch(assignmentId, () => void loadStudents());
watch(selectedStudent, () => void loadStudent());
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    if (__VLS_ctx.infantAssignments.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel early-childhood") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
        });
        (__VLS_ctx.infantAssignments.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.assignmentId)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [a] of __VLS_getVForSourceType((__VLS_ctx.infantAssignments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((a.id)),
                value: ((a.id)),
            });
            (a.class_group_name);
            (a.component_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.selectedStudent)),
            disabled: ((!__VLS_ctx.assignmentId)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [s] of __VLS_getVForSourceType((__VLS_ctx.students))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((s.student_id)),
                value: ((s.student_id)),
            });
            (s.social_name || s.full_name);
            (s.registration_number);
        }
        if (__VLS_ctx.selectedStudent) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("grid") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.save) },
                ...{ class: ("form subpanel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.form.record_date);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("alegre, tranquilo…"),
            });
            (__VLS_ctx.form.mood);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("almoço"),
            });
            (__VLS_ctx.form.meal);
            if (__VLS_ctx.form.meal) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((__VLS_ctx.form.consumption)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("completo"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("parcial"),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    value: ("recusado"),
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("time"),
            });
            (__VLS_ctx.form.sleep_start);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("time"),
            });
            (__VLS_ctx.form.sleep_end);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("lavagem das mãos"),
            });
            (__VLS_ctx.form.hygiene);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("troca de fralda/roupa"),
            });
            (__VLS_ctx.form.diaper_change);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.form.development_notes)),
                rows: ("4"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                disabled: ((__VLS_ctx.busy)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.release) },
                ...{ class: ("form subpanel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.pickup.guardian_id)),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [g] of __VLS_getVForSourceType((__VLS_ctx.guardians))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((g.guardian_id)),
                    value: ((g.guardian_id)),
                });
                (g.social_name || g.full_name);
                (g.relationship);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("datetime-local"),
                required: (true),
            });
            (__VLS_ctx.pickup.released_at);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                placeholder: ("CPF ***.***.***-00"),
            });
            (__VLS_ctx.pickup.identity_document_masked);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.pickup.notes)),
                rows: ("3"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                disabled: ((__VLS_ctx.busy || !__VLS_ctx.guardians.length)),
            });
            if (!__VLS_ctx.guardians.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            }
        }
        if (__VLS_ctx.history.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows history") },
            });
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.history.slice(0, 10)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (r.record_date);
                (r.mood || "Rotina registrada");
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (r.development_notes || "Sem observação de desenvolvimento.");
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (r.version);
            }
        }
    }
    ['panel', 'early-childhood', 'section-title', 'pill', 'cols', 'grid', 'form', 'subpanel', 'cols', 'cols', 'cols', 'form', 'subpanel', 'rows', 'history', 'pill',];
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
            infantAssignments: infantAssignments,
            assignmentId: assignmentId,
            students: students,
            selectedStudent: selectedStudent,
            history: history,
            guardians: guardians,
            busy: busy,
            form: form,
            pickup: pickup,
            save: save,
            release: release,
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
