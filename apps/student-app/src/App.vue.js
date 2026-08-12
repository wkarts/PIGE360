import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref("");
const privacyNotice = ref(null);
const email = ref(""), password = ref("");
const ctx = ref({ branding: {}, enrollments: [], attendance: {}, library_loans: [], transport: [], notices: [], requests: [], health: { people: [], records: [], incidents: [], medications: [] }, transport_events: [], consent_purposes: [], consents: [], privacy_requests: [] });
const req = reactive({ request_type: "academic", subject: "", description: "", priority: "normal", department: "Secretaria", sla_hours: 72 });
const privacy = reactive({ request_type: "access", description: "" });
const b = computed(() => ctx.value.branding || {}), school = computed(() => b.value.short_name || b.value.trade_name || b.value.legal_name || "Instituição");
function m(e) { const p = e.problem; return p?.detail || (e instanceof Error ? e.message : "Erro"); }
function theme() { document.documentElement.style.setProperty("--brand-primary", b.value.primary_color || "#006D77"); document.documentElement.style.setProperty("--brand-secondary", b.value.secondary_color || "#0D1B2A"); document.title = `${school.value} — Aluno`; }
async function load() { const portal = await api.request("/portal/student/me"); const sid = portal.student?.id; const pid = portal.person?.id; const [health, events, reportCard, integralization, purposes, consents, privacyRequests] = await Promise.all([api.request("/health/me").catch(() => ({ people: [], records: [], incidents: [], medications: [] })), sid ? api.request(`/transport/students/${sid}/events`).catch(() => ({ items: [] })) : Promise.resolve({ items: [] }), sid ? api.request(`/pedagogy/students/${sid}/report-card`).catch(() => ({ enrollments: [] })) : Promise.resolve({ enrollments: [] }), sid ? api.request(`/academic/students/${sid}/integralization`).catch(() => ({ enrollments: [] })) : Promise.resolve({ enrollments: [] }), api.request("/compliance/consent-purposes").catch(() => ({ items: [] })), pid ? api.request(`/compliance/persons/${pid}/consents`).catch(() => ({ items: [] })) : Promise.resolve({ items: [] }), api.request("/compliance/data-subject-requests").catch(() => ({ items: [] }))]); ctx.value = { ...portal, health, transport_events: events.items || [], report_card: reportCard, integralization, consent_purposes: purposes.items || [], consents: consents.items || [], privacy_requests: privacyRequests.items || [] }; theme(); }
async function boot() { try {
    await api.initialize();
    auth.value = !!api.tokens;
    if (auth.value)
        await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    ready.value = true;
} }
async function login() { busy.value = true; try {
    await api.login(email.value, password.value);
    auth.value = true;
    await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
async function logout() { await api.logout(); auth.value = false; }
async function renewLoan(id) { busy.value = true; try {
    await api.request(`/library/loans/${id}/renew`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Renovação solicitada pelo aluno" }) });
    await load();
    notice.value = "Empréstimo renovado.";
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
function activeConsent(code) { return ctx.value.consents?.find((x) => x.purpose_code === code && x.state === "granted") || null; }
function adult() { const b = ctx.value.person?.birth_date; if (!b)
    return false; const born = new Date(`${b}T00:00:00`), now = new Date(); let age = now.getFullYear() - born.getFullYear(); if (now.getMonth() < born.getMonth() || (now.getMonth() === born.getMonth() && now.getDate() < born.getDate()))
    age--; return age >= 18; }
async function readPrivacyNotice(p) { if (!p.privacy_notice_id)
    return; busy.value = true; try {
    privacyNotice.value = await api.request(`/compliance/privacy-notices/${p.privacy_notice_id}`);
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
async function grantConsent(p) { if (!ctx.value.person?.id || !p.privacy_notice_id)
    return; busy.value = true; try {
    await api.request("/compliance/consents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ subject_person_id: ctx.value.person.id, granted_by_person_id: ctx.value.person.id, purpose_code: p.code, privacy_notice_id: p.privacy_notice_id, channel: "mobile", evidence: { surface: "student-app", affirmative_action: true } }) });
    notice.value = "Consentimento registrado.";
    await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
async function revokeConsent(c) { busy.value = true; try {
    await api.request(`/compliance/consents/${c.id}/revoke`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Revogação solicitada pelo titular no Portal do Aluno" }) });
    notice.value = "Consentimento revogado.";
    await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
async function privacyRequest() { if (!ctx.value.person?.id)
    return; busy.value = true; try {
    await api.request("/compliance/data-subject-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ subject_person_id: ctx.value.person.id, request_type: privacy.request_type, description: privacy.description || null, priority: "normal" }) });
    notice.value = "Solicitação LGPD registrada.";
    privacy.description = "";
    await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
async function send() { busy.value = true; try {
    await api.request("/service-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    notice.value = "Solicitação enviada.";
    Object.assign(req, { request_type: "academic", subject: "", description: "", priority: "normal", department: "Secretaria", sla_hours: 72 });
    await load();
}
catch (e) {
    error.value = m(e);
}
finally {
    busy.value = false;
} }
function date(v) { return v ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(v)) : "—"; }
onMounted(boot);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    if (!__VLS_ctx.ready) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("center") },
        });
    }
    else if (!__VLS_ctx.auth) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("login") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.login) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("email"),
            required: (true),
        });
        (__VLS_ctx.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("password"),
            required: (true),
        });
        (__VLS_ctx.password);
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("shell") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.school);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({});
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        if (__VLS_ctx.notice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash success") },
            });
            (__VLS_ctx.notice);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("hero") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        (__VLS_ctx.ctx.person?.social_name || __VLS_ctx.ctx.person?.full_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        (__VLS_ctx.ctx.enrollments?.[0]?.program_name || 'Vida acadêmica');
        (__VLS_ctx.ctx.enrollments?.[0]?.class_group_name || 'Sem turma ativa');
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("metrics") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.ctx.attendance?.percentage || '0.00');
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.ctx.attendance?.counted_sessions || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.ctx.student?.registration_number);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.ctx.enrollments?.[0]?.academic_year_name || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.ctx.library_loans?.filter((x) => x.state === 'open').length || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [en] of __VLS_getVForSourceType((__VLS_ctx.ctx.report_card?.enrollments || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((en.enrollment.id)),
                ...{ class: ("rows") },
            });
            for (const [r] of __VLS_getVForSourceType((en.results))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((r.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (r.component_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (r.period_name);
                (r.outcome);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (Number(r.final_score).toFixed(2));
                (Number(r.attendance_percentage).toFixed(2));
            }
            if (!en.results?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
        }
        if (!__VLS_ctx.ctx.report_card?.enrollments?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.ctx.integralization?.enrollments?.some((x) => Number(x.curriculum?.components_total || 0) > 0)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            for (const [en] of __VLS_getVForSourceType((__VLS_ctx.ctx.integralization.enrollments))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((en.enrollment.id)),
                    ...{ class: ("rows") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (en.enrollment.program_name);
                (en.enrollment.curriculum_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (en.curriculum.components_completed);
                (en.curriculum.components_total);
                (en.curriculum.workload_hours_completed);
                (en.curriculum.workload_hours_total);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (en.curriculum.completion_percentage);
                for (const [i] of __VLS_getVForSourceType((en.internships))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((i.id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (i.completed_hours);
                    (i.required_hours);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: ("pill") },
                    });
                    (i.state);
                }
                for (const [a] of __VLS_getVForSourceType((en.complementary_activities))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((a.id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (a.title);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (a.category);
                    (a.approved_hours);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: ("pill") },
                    });
                    (a.state);
                }
                for (const [t] of __VLS_getVForSourceType((en.theses))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((t.id)),
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (t.title);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: ("pill") },
                    });
                    (t.state);
                    if (t.grade) {
                        (t.grade);
                    }
                }
                if (en.pending_prerequisites?.length) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (en.pending_prerequisites.map((x) => x.prerequisite_name).join(', '));
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: ("pill") },
                    });
                    (en.pending_prerequisites.length);
                }
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.ctx.attendance?.recent))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((r.class_session_id + r.scheduled_start)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (r.component_name || 'Componente');
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.date(r.scheduled_start));
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
            });
            (r.status_code);
        }
        if (!__VLS_ctx.ctx.attendance?.recent?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [n] of __VLS_getVForSourceType((__VLS_ctx.ctx.notices?.slice(0, 8)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ class: ("notice") },
                key: ((n.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (n.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (n.body);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.date(n.created_at));
        }
        if (!__VLS_ctx.ctx.notices?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [t] of __VLS_getVForSourceType((__VLS_ctx.ctx.transport_events?.slice(0, 10)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((t.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (t.event_type === 'boarded' ? 'Embarque' : t.event_type === 'disembarked' ? 'Desembarque' : t.event_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (t.route_name);
            (t.stop_name || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.date(t.occurred_at));
        }
        if (!__VLS_ctx.ctx.transport_events?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [i] of __VLS_getVForSourceType((__VLS_ctx.ctx.health?.incidents?.slice(0, 6)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ class: ("notice") },
                key: ((i.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (i.incident_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (i.summary);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.date(i.occurred_at));
            (i.state);
        }
        for (const [med] of __VLS_getVForSourceType((__VLS_ctx.ctx.health?.medications?.slice(0, 6)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ class: ("notice") },
                key: ((med.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (med.medication_name);
            (med.dosage);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (med.instructions);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.date(med.starts_on));
            (__VLS_ctx.date(med.ends_on));
        }
        if (!__VLS_ctx.ctx.health?.incidents?.length && !__VLS_ctx.ctx.health?.medications?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [p] of __VLS_getVForSourceType((__VLS_ctx.ctx.consent_purposes))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ class: ("notice") },
                key: ((p.code)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (p.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            (p.purpose);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (p.privacy_notice_title || 'Aviso de privacidade');
            if (p.privacy_notice_version) {
                (p.privacy_notice_version);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("right") },
            });
            if (p.privacy_notice_id) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!((p.privacy_notice_id)))
                                return;
                            __VLS_ctx.readPrivacyNotice(p);
                        } },
                    ...{ class: ("small") },
                });
            }
            if (__VLS_ctx.adult() && !__VLS_ctx.activeConsent(p.code)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!((__VLS_ctx.adult() && !__VLS_ctx.activeConsent(p.code))))
                                return;
                            __VLS_ctx.grantConsent(p);
                        } },
                    ...{ class: ("small") },
                    disabled: ((!p.privacy_notice_id)),
                });
            }
            if (__VLS_ctx.activeConsent(p.code)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!((__VLS_ctx.activeConsent(p.code))))
                                return;
                            __VLS_ctx.revokeConsent(__VLS_ctx.activeConsent(p.code));
                        } },
                    ...{ class: ("small") },
                });
            }
            if (!__VLS_ctx.adult() && !__VLS_ctx.activeConsent(p.code)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            }
        }
        if (!__VLS_ctx.ctx.consent_purposes?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.privacyRequest) },
            ...{ class: ("panel form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.privacy.request_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("access"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("export"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("rectification"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("restriction"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("objection"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("anonymization"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.privacy.description)),
            rows: ("4"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.ctx.privacy_requests?.slice(0, 5)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                key: ((r.id)),
            });
            (r.protocol);
            (r.request_type);
            (r.state);
        }
        if (__VLS_ctx.privacyNotice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("right") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        if (!((__VLS_ctx.privacyNotice)))
                            return;
                        __VLS_ctx.privacyNotice = null;
                    } },
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.privacyNotice.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.privacyNotice.code);
            (__VLS_ctx.privacyNotice.version);
            (__VLS_ctx.privacyNotice.sha256);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ style: ({}) },
            });
            (__VLS_ctx.privacyNotice.content);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [l] of __VLS_getVForSourceType((__VLS_ctx.ctx.library_loans))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((l.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (l.title);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.date(l.due_at));
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("right") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (l.state);
            if (l.state === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!((l.state === 'open')))
                                return;
                            __VLS_ctx.renewLoan(l.id);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.ctx.library_loans?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
            ...{ class: ("space") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [t] of __VLS_getVForSourceType((__VLS_ctx.ctx.transport))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((t.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (t.route_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (t.vehicle || 'Veículo não informado');
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (t.state);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.send) },
            ...{ class: ("panel form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.req.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.req.request_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.req.description)),
            rows: ("5"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({});
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.ctx.requests?.slice(0, 5)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                key: ((r.id)),
            });
            (r.protocol);
            (r.subject);
            (r.state);
        }
    }
    ['center', 'login', 'mark', 'error', 'shell', 'flash', 'error', 'flash', 'success', 'hero', 'metrics', 'panel', 'rows', 'pill', 'empty', 'empty', 'panel', 'rows', 'pill', 'pill', 'pill', 'pill', 'pill', 'grid', 'panel', 'rows', 'pill', 'empty', 'panel', 'notice', 'empty', 'grid', 'panel', 'rows', 'empty', 'panel', 'notice', 'notice', 'empty', 'grid', 'panel', 'notice', 'right', 'small', 'small', 'small', 'empty', 'panel', 'form', 'panel', 'right', 'small', 'grid', 'panel', 'rows', 'right', 'small', 'empty', 'space', 'rows', 'panel', 'form',];
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
            ready: ready,
            auth: auth,
            error: error,
            notice: notice,
            privacyNotice: privacyNotice,
            email: email,
            password: password,
            ctx: ctx,
            req: req,
            privacy: privacy,
            school: school,
            login: login,
            logout: logout,
            renewLoan: renewLoan,
            activeConsent: activeConsent,
            adult: adult,
            readPrivacyNotice: readPrivacyNotice,
            grantConsent: grantConsent,
            revokeConsent: revokeConsent,
            privacyRequest: privacyRequest,
            send: send,
            date: date,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
