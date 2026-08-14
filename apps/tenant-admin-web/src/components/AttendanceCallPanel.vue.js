import { computed, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const selectedSessionId = ref("");
const records = ref([]);
const call = ref(null);
const loading = ref(false);
const saving = ref(false);
const statusOptions = [
    ["present", "Presente"],
    ["absent", "Ausente"],
    ["late", "Atrasado"],
    ["justified_absence", "Falta justificada"],
    ["excused_absence", "Dispensado"],
    ["remote_present", "Presente remoto"],
    ["activity_present", "Atividade externa"],
    ["attendance_pending", "Pendente"],
];
const selectedSession = computed(() => props.sessions.find((row) => row.id === selectedSessionId.value) ??
    null);
const isReadOnly = computed(() => ["closed", "cancelled", "rescheduled"].includes(selectedSession.value?.status));
const pendingCount = computed(() => records.value.filter((row) => row.status_code === "attendance_pending")
    .length);
const callVersion = computed(() => Number(call.value?.current_version ?? 0));
function message(error) {
    const candidate = error;
    return (candidate.problem?.detail ||
        (error instanceof Error ? error.message : "Erro inesperado na chamada."));
}
function idempotency(prefix) {
    return `${prefix}-${crypto.randomUUID()}`;
}
function studentLabel(studentId) {
    const student = (props.references?.students ?? []).find((row) => row.id === studentId);
    return student?.label || student?.full_name || studentId;
}
function syncRecords(session, response) {
    const existing = new Map((response.records ?? []).map((row) => [row.student_id, row]));
    records.value = (session.enrolled_student_ids ?? []).map((studentId) => ({
        ...existing.get(studentId),
        student_id: studentId,
        status_code: existing.get(studentId)?.status_code ?? "attendance_pending",
        minutes_present: existing.get(studentId)?.minutes_present ?? null,
        observation: existing.get(studentId)?.observation ?? "",
    }));
}
async function loadAttendance() {
    if (!selectedSession.value) {
        records.value = [];
        call.value = null;
        return;
    }
    loading.value = true;
    try {
        const response = await props.api.request(`/class-sessions/${selectedSession.value.id}/attendance`);
        call.value = response.call ?? null;
        syncRecords(selectedSession.value, response);
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        loading.value = false;
    }
}
function selectFirstSession() {
    if (!selectedSessionId.value && props.sessions.length)
        selectedSessionId.value = props.sessions[0].id;
    if (selectedSessionId.value && !selectedSession.value)
        selectedSessionId.value = props.sessions[0]?.id ?? "";
}
async function saveDraft() {
    if (!selectedSession.value || isReadOnly.value)
        return;
    saving.value = true;
    try {
        await props.api.request(`/class-sessions/${selectedSession.value.id}/attendance`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency("attendance-draft"),
            },
            body: JSON.stringify({
                records: records.value.map((row) => ({
                    student_id: row.student_id,
                    status_code: row.status_code,
                    minutes_present: row.minutes_present === "" ? null : row.minutes_present,
                    observation: row.observation || null,
                })),
                mode: "full_list",
                origin: "online",
            }),
        });
        emit("notice", "Rascunho da chamada salvo com auditoria.");
        emit("refresh");
        await loadAttendance();
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        saving.value = false;
    }
}
async function submit() {
    if (!selectedSession.value ||
        !callVersion.value ||
        pendingCount.value ||
        isReadOnly.value)
        return;
    saving.value = true;
    try {
        await props.api.request(`/class-sessions/${selectedSession.value.id}/attendance/submit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                expected_call_version: callVersion.value,
                origin: "online",
            }),
        });
        emit("notice", "Chamada enviada. A sessão já pode ser fechada.");
        emit("refresh");
        await loadAttendance();
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        saving.value = false;
    }
}
async function sessionAction(action) {
    if (!selectedSession.value)
        return;
    saving.value = true;
    try {
        await props.api.request(`/class-sessions/${selectedSession.value.id}/${action}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                expected_version: selectedSession.value.version,
                reason: `Ação ${action} registrada na chamada.`,
            }),
        });
        emit("notice", `Sessão ${action === "start" ? "iniciada" : action === "close" ? "fechada" : "reaberta"}.`);
        emit("refresh");
        await loadAttendance();
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        saving.value = false;
    }
}
function markAllPresent() {
    if (isReadOnly.value)
        return;
    records.value.forEach((row) => {
        row.status_code = "present";
        row.minutes_present = null;
    });
}
watch(() => props.sessions, selectFirstSession, { immediate: true });
watch(selectedSessionId, () => void loadAttendance());
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['attendance-heading', 'attendance-toolbar', 'attendance-toolbar', 'attendance-table', 'attendance-table', 'attendance-footer', 'attendance-heading', 'attendance-toolbar', 'attendance-actions', 'attendance-footer', 'attendance-session-select',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("panel attendance-editor") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("panel-title attendance-heading") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: ("attendance-session-select") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.selectedSessionId)),
        disabled: ((__VLS_ctx.loading || !__VLS_ctx.sessions.length)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [session] of __VLS_getVForSourceType((__VLS_ctx.sessions))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((session.id)),
            value: ((session.id)),
        });
        (session.scheduled_start);
        (session.status);
    }
    if (!__VLS_ctx.sessions.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    else if (__VLS_ctx.selectedSession) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("attendance-toolbar") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.selectedSession.class_group_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((__VLS_ctx.selectedSession.status === 'closed' ? 'ok' : 'warn')) },
        });
        (__VLS_ctx.selectedSession.status);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.records.length);
        (__VLS_ctx.pendingCount);
        (__VLS_ctx.callVersion);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("row-actions") },
        });
        if (['scheduled', 'ready'].includes(__VLS_ctx.selectedSession.status)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.sessions.length))))
                            return;
                        if (!((__VLS_ctx.selectedSession)))
                            return;
                        if (!((['scheduled', 'ready'].includes(__VLS_ctx.selectedSession.status))))
                            return;
                        __VLS_ctx.sessionAction('start');
                    } },
                ...{ class: ("small") },
                disabled: ((__VLS_ctx.saving)),
            });
        }
        if (__VLS_ctx.call?.status === 'submitted' &&
            [
                'attendance_submitted',
                'completed',
                'started',
                'attendance_open',
            ].includes(__VLS_ctx.selectedSession.status)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.sessions.length))))
                            return;
                        if (!((__VLS_ctx.selectedSession)))
                            return;
                        if (!((__VLS_ctx.call?.status === 'submitted' &&
                            [
                                'attendance_submitted',
                                'completed',
                                'started',
                                'attendance_open',
                            ].includes(__VLS_ctx.selectedSession.status))))
                            return;
                        __VLS_ctx.sessionAction('close');
                    } },
                ...{ class: ("small ok-btn") },
                disabled: ((__VLS_ctx.saving)),
            });
        }
        if (__VLS_ctx.selectedSession.status === 'closed') {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.sessions.length))))
                            return;
                        if (!((__VLS_ctx.selectedSession)))
                            return;
                        if (!((__VLS_ctx.selectedSession.status === 'closed')))
                            return;
                        __VLS_ctx.sessionAction('reopen');
                    } },
                ...{ class: ("small") },
                disabled: ((__VLS_ctx.saving)),
            });
        }
        if (__VLS_ctx.loading) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
            });
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("attendance-actions") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.markAllPresent) },
                ...{ class: ("small") },
                disabled: ((__VLS_ctx.isReadOnly || __VLS_ctx.saving)),
            });
            if (__VLS_ctx.pendingCount) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("attendance-warning") },
                });
                (__VLS_ctx.pendingCount);
            }
            else if (__VLS_ctx.call?.status === 'submitted') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("attendance-success") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({
                ...{ class: ("attendance-table") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [record] of __VLS_getVForSourceType((__VLS_ctx.records))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((record.student_id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (__VLS_ctx.studentLabel(record.student_id));
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (record.student_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                    value: ((record.status_code)),
                    disabled: ((__VLS_ctx.isReadOnly || __VLS_ctx.saving)),
                });
                for (const [option] of __VLS_getVForSourceType((__VLS_ctx.statusOptions))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                        key: ((option[0])),
                        value: ((option[0])),
                    });
                    (option[1]);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    type: ("number"),
                    min: ("0"),
                    max: ("1440"),
                    placeholder: ("—"),
                    disabled: ((__VLS_ctx.isReadOnly || __VLS_ctx.saving)),
                });
                (record.minutes_present);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    maxlength: ("2000"),
                    placeholder: ("Opcional"),
                    disabled: ((__VLS_ctx.isReadOnly || __VLS_ctx.saving)),
                });
                (record.observation);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (record.version || 0);
            }
            if (!__VLS_ctx.records.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                    colspan: ("5"),
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("attendance-footer") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.saveDraft) },
                ...{ class: ("small") },
                disabled: ((__VLS_ctx.isReadOnly || __VLS_ctx.saving || !__VLS_ctx.records.length)),
            });
            (__VLS_ctx.saving ? "Salvando…" : "Salvar rascunho");
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.submit) },
                ...{ class: ("primary") },
                disabled: ((__VLS_ctx.isReadOnly || __VLS_ctx.saving || !__VLS_ctx.callVersion || !!__VLS_ctx.pendingCount)),
            });
        }
    }
    ['panel', 'attendance-editor', 'panel-title', 'attendance-heading', 'attendance-session-select', 'empty', 'attendance-toolbar', 'pill', 'row-actions', 'small', 'small', 'ok-btn', 'small', 'empty', 'attendance-actions', 'small', 'attendance-warning', 'attendance-success', 'attendance-table', 'empty', 'attendance-footer', 'small', 'primary',];
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
            selectedSessionId: selectedSessionId,
            records: records,
            call: call,
            loading: loading,
            saving: saving,
            statusOptions: statusOptions,
            selectedSession: selectedSession,
            isReadOnly: isReadOnly,
            pendingCount: pendingCount,
            callVersion: callVersion,
            studentLabel: studentLabel,
            saveDraft: saveDraft,
            submit: submit,
            sessionAction: sessionAction,
            markAllPresent: markAllPresent,
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
