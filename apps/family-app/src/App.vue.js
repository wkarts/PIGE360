import { computed, onMounted, reactive, ref } from "vue";
import { Pige360SessionClient } from "@pige360/auth";
const api = new Pige360SessionClient();
const ready = ref(false), auth = ref(false), busy = ref(false), error = ref(""), notice = ref("");
const privacyNotice = ref(null);
const email = ref(""), password = ref("");
const ctx = ref({ branding: {}, dependents: [], installments: [], bank_accounts: [], notices: [], requests: [], health: { people: [], records: [], incidents: [], medications: [] }, canteen_wallets: [], events: [], event_registrations: [], trips: [], consent_purposes: [], privacy_requests: [] });
const selected = ref(null);
const pix = ref(null);
const pendingAuthorization = ref(null);
const consentText = ref("Autorizo a participação do meu dependente no evento e declaro ciência das informações apresentadas.");
const policyForm = reactive({ blocked_allergens: "", blocked_product_ids: "", daily_limit: "", weekly_limit: "", notes: "" });
const requestForm = reactive({ request_type: "administrative", subject: "", description: "", priority: "normal", department: "Secretaria", sla_hours: 72 });
const privacyForm = reactive({ request_type: "access", description: "" });
const brand = computed(() => ctx.value.branding || {});
const school = computed(() => brand.value.short_name || brand.value.trade_name || brand.value.legal_name || "Instituição");
function msg(e) { const p = e?.problem; return p?.detail || (e instanceof Error ? e.message : "Erro inesperado"); }
function applyBrand() { document.documentElement.style.setProperty("--brand-primary", brand.value.primary_color || "#006D77"); document.documentElement.style.setProperty("--brand-secondary", brand.value.secondary_color || "#0D1B2A"); document.documentElement.style.setProperty("--brand-accent", brand.value.accent_color || "#F59E0B"); document.title = `${school.value} — Família`; }
async function load() { const [portal, health, wallets, events, registrations, trips, purposes, privacyRequests] = await Promise.all([api.request("/portal/family/me"), api.request("/health/me").catch(() => ({ people: [], records: [], incidents: [], medications: [] })), api.request("/canteen/wallets/me").catch(() => ({ items: [] })), api.request("/events").catch(() => ({ items: [] })), api.request("/events/me/registrations").catch(() => ({ items: [] })), api.request("/trips/me").catch(() => ({ items: [] })), api.request("/compliance/consent-purposes").catch(() => ({ items: [] })), api.request("/compliance/data-subject-requests").catch(() => ({ items: [] }))]); ctx.value = { ...portal, health, canteen_wallets: wallets.items || [], events: events.items || [], event_registrations: registrations.items || [], trips: trips.items || [], consent_purposes: purposes.items || [], privacy_requests: privacyRequests.items || [] }; applyBrand(); if (ctx.value.dependents?.length && !selected.value)
    await openDependent(ctx.value.dependents[0]); }
async function boot() { try {
    await api.initialize();
    auth.value = !!api.tokens;
    if (auth.value)
        await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    ready.value = true;
} }
async function login() { busy.value = true; error.value = ""; try {
    await api.login(email.value, password.value);
    auth.value = true;
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function logout() { await api.logout(); auth.value = false; ctx.value = {}; selected.value = null; pix.value = null; }
async function openDependent(dep) { busy.value = true; try {
    const [base, events, policy, reportCard, daily, pickups, integralization] = await Promise.all([api.request(`/portal/family/dependents/${dep.student_id}`), api.request(`/transport/students/${dep.student_id}/events`).catch(() => ({ items: [] })), api.request(`/canteen/students/${dep.student_id}/policy`).catch(() => ({ blocked_allergens: [], blocked_product_ids: [], daily_limit: "", weekly_limit: "", notes: "" })), api.request(`/pedagogy/students/${dep.student_id}/report-card`).catch(() => ({ enrollments: [] })), api.request(`/academic/early-childhood/students/${dep.student_id}/daily-records`).catch(() => ({ items: [] })), api.request(`/academic/early-childhood/students/${dep.student_id}/pickups`).catch(() => ({ items: [] })), api.request(`/academic/students/${dep.student_id}/integralization`).catch(() => ({ enrollments: [] }))]);
    const consents = await api.request(`/compliance/persons/${base.student.person_id}/consents`).catch(() => ({ items: [] }));
    selected.value = { ...base, transport_events: events.items || [], canteen_policy: policy, report_card: reportCard, daily_records: daily.items || [], pickup_records: pickups.items || [], integralization, consents: consents.items || [] };
    Object.assign(policyForm, { blocked_allergens: (policy.blocked_allergens || []).join(", "), blocked_product_ids: (policy.blocked_product_ids || []).join(", "), daily_limit: policy.daily_limit ?? "", weekly_limit: policy.weekly_limit ?? "", notes: policy.notes ?? "" });
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function generatePix(inst) { const account = ctx.value.bank_accounts?.[0]; if (!account) {
    error.value = "A escola ainda não configurou uma conta PIX ativa.";
    return;
} busy.value = true; try {
    pix.value = await api.request(`/banking/accounts/${account.id}/pix-charges`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ installment_id: inst.id }) });
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function copyPix() { if (pix.value?.br_code) {
    await navigator.clipboard.writeText(pix.value.br_code);
    notice.value = "Código PIX copiado.";
} }
function walletForSelected() { return ctx.value.canteen_wallets?.find((x) => x.student?.id === selected.value?.student?.id)?.wallet || null; }
function registrationFor(eventId) { return ctx.value.event_registrations?.find((x) => x.event_id === eventId && x.student_id === selected.value?.student?.id) || null; }
async function saveFoodPolicy() { if (!selected.value?.student?.id)
    return; busy.value = true; try {
    await api.request(`/canteen/students/${selected.value.student.id}/policy`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ blocked_allergens: policyForm.blocked_allergens.split(",").map(x => x.trim()).filter(Boolean), blocked_product_ids: policyForm.blocked_product_ids.split(",").map(x => x.trim()).filter(Boolean), daily_limit: policyForm.daily_limit || null, weekly_limit: policyForm.weekly_limit || null, notes: policyForm.notes || null }) });
    notice.value = "Política alimentar atualizada.";
    await openDependent({ student_id: selected.value.student.id });
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function registerEvent(event) { if (!selected.value?.student?.id)
    return; busy.value = true; try {
    const r = await api.request(`/events/${event.id}/registrations`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": `event-${crypto.randomUUID()}` }, body: JSON.stringify({ student_id: selected.value.student.id }) });
    notice.value = r.state === "awaiting_authorization" ? "Inscrição reservada; confirme a autorização." : "Inscrição confirmada.";
    pendingAuthorization.value = r.state === "awaiting_authorization" ? r : null;
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function authorizeEvent(registration) { busy.value = true; try {
    await api.request(`/event-registrations/${registration.id}/authorization`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", consent_text: consentText.value }) });
    notice.value = "Participação autorizada.";
    pendingAuthorization.value = null;
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
function activeConsent(code) { return selected.value?.consents?.find((x) => x.purpose_code === code && x.state === "granted") || null; }
async function readPrivacyNotice(purpose) { if (!purpose.privacy_notice_id)
    return; busy.value = true; try {
    privacyNotice.value = await api.request(`/compliance/privacy-notices/${purpose.privacy_notice_id}`);
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function grantConsent(purpose) { if (!selected.value?.student?.person_id || !ctx.value.person?.id || !purpose.privacy_notice_id)
    return; busy.value = true; try {
    await api.request("/compliance/consents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ subject_person_id: selected.value.student.person_id, granted_by_person_id: ctx.value.person.id, purpose_code: purpose.code, privacy_notice_id: purpose.privacy_notice_id, channel: "mobile", evidence: { surface: "family-app", affirmative_action: true } }) });
    notice.value = "Consentimento registrado.";
    await openDependent({ student_id: selected.value.student.id });
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function revokeConsent(c) { busy.value = true; try {
    await api.request(`/compliance/consents/${c.id}/revoke`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "Revogação solicitada pelo responsável no Portal da Família" }) });
    notice.value = "Consentimento revogado.";
    await openDependent({ student_id: selected.value.student.id });
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function createPrivacyRequest() { if (!selected.value?.student?.person_id)
    return; busy.value = true; try {
    await api.request("/compliance/data-subject-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ subject_person_id: selected.value.student.person_id, request_type: privacyForm.request_type, description: privacyForm.description || null, priority: "normal" }) });
    notice.value = "Solicitação LGPD registrada.";
    privacyForm.description = "";
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
async function createRequest() { busy.value = true; try {
    await api.request("/service-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestForm) });
    notice.value = "Solicitação enviada.";
    Object.assign(requestForm, { request_type: "administrative", subject: "", description: "", priority: "normal", department: "Secretaria", sla_hours: 72 });
    await load();
}
catch (e) {
    error.value = msg(e);
}
finally {
    busy.value = false;
} }
function money(v) { return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(v || 0)); }
function date(v) { if (!v)
    return "—"; return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(v)); }
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
            ...{ class: ("login-page") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.login) },
            ...{ class: ("login-card") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("eyebrow") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("email"),
            required: (true),
            autocomplete: ("username"),
        });
        (__VLS_ctx.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            type: ("password"),
            required: (true),
            autocomplete: ("current-password"),
        });
        (__VLS_ctx.password);
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.busy)),
        });
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mobile-shell") },
            'data-surface': ("tenant"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("brand") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("mark") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.school);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.logout) },
            ...{ class: ("ghost") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({});
        if (__VLS_ctx.error) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash error") },
            });
            (__VLS_ctx.error);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        if (!((__VLS_ctx.error)))
                            return;
                        __VLS_ctx.error = '';
                    } },
            });
        }
        if (__VLS_ctx.notice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("flash success") },
            });
            (__VLS_ctx.notice);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        if (!((__VLS_ctx.notice)))
                            return;
                        __VLS_ctx.notice = '';
                    } },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("welcome") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({});
        (__VLS_ctx.ctx.person?.social_name || __VLS_ctx.ctx.person?.full_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.ctx.dependents?.length || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cards-scroll") },
        });
        for (const [d] of __VLS_getVForSourceType((__VLS_ctx.ctx.dependents))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        __VLS_ctx.openDependent(d);
                    } },
                key: ((d.student_id)),
                ...{ class: ("dependent") },
                ...{ class: (({ active: __VLS_ctx.selected?.student?.id === d.student_id })) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (d.social_name || d.full_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (d.program_name || 'Sem programa');
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (d.class_group_name || d.enrollment_state || 'Sem turma');
        }
        if (__VLS_ctx.selected) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ class: ("metric") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selected.attendance?.percentage || '0.00');
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.selected.attendance?.counted_sessions || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                ...{ class: ("metric") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selected.student?.registration_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.selected.enrollments?.[0]?.state || 'sem vínculo ativo');
        }
        if (__VLS_ctx.selected) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [en] of __VLS_getVForSourceType((__VLS_ctx.selected.report_card?.enrollments || []))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((en.enrollment.id)),
                    ...{ class: ("report-block") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
                (en.enrollment.academic_year_name || en.enrollment.enrollment_number);
                (en.enrollment.class_name || 'Turma');
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("list") },
                });
                for (const [r] of __VLS_getVForSourceType((en.results))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((r.id)),
                        ...{ class: ("list-row") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (r.component_name);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (r.period_name);
                    (r.outcome);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        ...{ class: ("right") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (Number(r.final_score).toFixed(2));
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (Number(r.attendance_percentage).toFixed(2));
                }
                if (!en.results?.length) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                        ...{ class: ("empty") },
                    });
                }
            }
            if (!__VLS_ctx.selected.report_card?.enrollments?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.ctx.installments?.filter((x) => x.state !== 'paid').length || 0);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("list") },
        });
        for (const [i] of __VLS_getVForSourceType((__VLS_ctx.ctx.installments))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((i.id)),
                ...{ class: ("list-row") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (i.student_name || i.description);
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.date(i.due_date));
            (i.state);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("right") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.money(Number(i.original_amount) + Number(i.penalty_amount || 0) + Number(i.interest_amount || 0) - Number(i.discount_amount || 0) - Number(i.paid_amount || 0)));
            if (i.state !== 'paid') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((!__VLS_ctx.ready))))
                                return;
                            if (!(!((!__VLS_ctx.auth))))
                                return;
                            if (!((i.state !== 'paid')))
                                return;
                            __VLS_ctx.generatePix(i);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.ctx.installments?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.pix) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel pix") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        if (!((__VLS_ctx.pix)))
                            return;
                        __VLS_ctx.pix = null;
                    } },
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.money(__VLS_ctx.pix.amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.code, __VLS_intrinsicElements.code)({});
            (__VLS_ctx.pix.br_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.copyPix) },
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.date(__VLS_ctx.pix.expires_at));
        }
        if (__VLS_ctx.selected?.daily_records?.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.selected.daily_records.length);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list") },
            });
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.selected.daily_records.slice(0, 14)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((r.id)),
                    ...{ class: ("list-row") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (__VLS_ctx.date(r.record_date));
                (r.mood || 'Rotina registrada');
                if (r.development_notes) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (r.development_notes);
                }
                if (r.meals?.length) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (r.meals.map((x) => `${x.meal || 'refeição'} (${x.consumption || 'registrada'})`).join(', '));
                }
                if (r.sleep?.started_at) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (r.sleep.started_at);
                    (r.sleep.ended_at || 'em andamento');
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: ("pill") },
                });
                (r.version);
            }
            if (__VLS_ctx.selected.pickup_records?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("section-title space") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list") },
            });
            for (const [p] of __VLS_getVForSourceType((__VLS_ctx.selected.pickup_records?.slice(0, 8)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((p.id)),
                    ...{ class: ("list-row") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (p.pickup_person_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (p.relationship || 'Responsável');
                (__VLS_ctx.date(p.released_at));
            }
        }
        if (__VLS_ctx.selected?.integralization?.enrollments?.some((x) => Number(x.curriculum?.components_total || 0) > 0)) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [en] of __VLS_getVForSourceType((__VLS_ctx.selected.integralization.enrollments))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((en.enrollment.id)),
                    ...{ class: ("report-block") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
                (en.enrollment.program_name);
                (en.enrollment.curriculum_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("grid") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    ...{ class: ("metric") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (en.curriculum.components_completed);
                (en.curriculum.components_total);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (en.curriculum.completion_percentage);
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    ...{ class: ("metric") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (en.complementary_hours_approved);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("list") },
                });
                for (const [i] of __VLS_getVForSourceType((en.internships))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((i.id)),
                        ...{ class: ("list-row") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (i.completed_hours);
                    (i.required_hours);
                    (i.state);
                }
                for (const [t] of __VLS_getVForSourceType((en.theses))) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                        key: ((t.id)),
                        ...{ class: ("list-row") },
                    });
                    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                    (t.title);
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                    (t.state);
                    if (t.grade) {
                        (t.grade);
                    }
                }
            }
        }
        if (__VLS_ctx.selected) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.selected.transport_events?.length || 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("list") },
            });
            for (const [t] of __VLS_getVForSourceType((__VLS_ctx.selected.transport_events?.slice(0, 8)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((t.id)),
                    ...{ class: ("list-row") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (t.event_type === 'boarded' ? 'Embarque' : t.event_type === 'disembarked' ? 'Desembarque' : t.event_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (t.route_name);
                (t.stop_name || 'sem parada informada');
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.date(t.occurred_at));
            }
            if (!__VLS_ctx.selected.transport_events?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            for (const [i] of __VLS_getVForSourceType(((__VLS_ctx.ctx.health?.incidents || []).filter((x) => x.person_id === __VLS_ctx.selected.student?.person_id).slice(0, 6)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    key: ((i.id)),
                    ...{ class: ("notice") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (i.incident_type);
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
                (i.summary);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.date(i.occurred_at));
                (i.state);
            }
            for (const [m] of __VLS_getVForSourceType(((__VLS_ctx.ctx.health?.medications || []).filter((x) => x.person_id === __VLS_ctx.selected.student?.person_id).slice(0, 6)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    key: ((m.id)),
                    ...{ class: ("notice") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (m.medication_name);
                (m.dosage);
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
                (m.instructions);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.date(m.starts_on));
                (__VLS_ctx.date(m.ends_on));
            }
            if (!(__VLS_ctx.ctx.health?.incidents || []).some((x) => x.person_id === __VLS_ctx.selected.student?.person_id) && !(__VLS_ctx.ctx.health?.medications || []).some((x) => x.person_id === __VLS_ctx.selected.student?.person_id)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
        }
        if (__VLS_ctx.selected) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            if (__VLS_ctx.walletForSelected()) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("metric-inline") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (__VLS_ctx.money(__VLS_ctx.walletForSelected().balance));
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.walletForSelected().daily_limit ? __VLS_ctx.money(__VLS_ctx.walletForSelected().daily_limit) : 'não definido');
            }
            else {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.saveFoodPolicy) },
                ...{ class: ("form compact") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                placeholder: ("amendoim, lactose"),
            });
            (__VLS_ctx.policyForm.blocked_allergens);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.01"),
            });
            (__VLS_ctx.policyForm.daily_limit);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
                type: ("number"),
                step: ("0.01"),
            });
            (__VLS_ctx.policyForm.weekly_limit);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.policyForm.notes)),
                rows: ("2"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.ctx.events?.length || 0);
            for (const [e] of __VLS_getVForSourceType((__VLS_ctx.ctx.events?.slice(0, 8)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    key: ((e.id)),
                    ...{ class: ("notice") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (e.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
                (e.location || 'Local a confirmar');
                (__VLS_ctx.date(e.starts_at));
                __VLS_elementAsFunction(__VLS_intrinsicElements.br, __VLS_intrinsicElements.br)({});
                (__VLS_ctx.money(e.registration_fee || 0));
                if (e.authorization_required) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("row-actions") },
                });
                if (__VLS_ctx.registrationFor(e.id)) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: ("pill") },
                    });
                    (__VLS_ctx.registrationFor(e.id).state);
                }
                else {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!((__VLS_ctx.selected)))
                                    return;
                                if (!(!((__VLS_ctx.registrationFor(e.id)))))
                                    return;
                                __VLS_ctx.registerEvent(e);
                            } },
                        ...{ class: ("small") },
                    });
                    (__VLS_ctx.selected.student?.social_name || __VLS_ctx.selected.student?.full_name);
                }
                if (__VLS_ctx.registrationFor(e.id)?.authorization_state === 'pending') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!((__VLS_ctx.selected)))
                                    return;
                                if (!((__VLS_ctx.registrationFor(e.id)?.authorization_state === 'pending')))
                                    return;
                                __VLS_ctx.authorizeEvent(__VLS_ctx.registrationFor(e.id));
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
            for (const [t] of __VLS_getVForSourceType((__VLS_ctx.ctx.trips?.filter((x) => x.student_id === __VLS_ctx.selected.student?.id).slice(0, 5)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((t.id)),
                    ...{ class: ("list-row") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (t.trip_name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (t.destination);
                (t.trip_state);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (t.state);
            }
        }
        if (__VLS_ctx.pendingAuthorization) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        if (!((__VLS_ctx.pendingAuthorization)))
                            return;
                        __VLS_ctx.pendingAuthorization = null;
                    } },
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.consentText)),
                rows: ("4"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((!__VLS_ctx.ready))))
                            return;
                        if (!(!((!__VLS_ctx.auth))))
                            return;
                        if (!((__VLS_ctx.pendingAuthorization)))
                            return;
                        __VLS_ctx.authorizeEvent(__VLS_ctx.pendingAuthorization);
                    } },
                ...{ class: ("primary") },
            });
        }
        if (__VLS_ctx.selected) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid two") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            for (const [p] of __VLS_getVForSourceType((__VLS_ctx.ctx.consent_purposes))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                    key: ((p.code)),
                    ...{ class: ("notice") },
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (p.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
                (p.purpose);
                if (p.privacy_notice_title) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                    (p.privacy_notice_title);
                    (p.privacy_notice_version);
                }
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: ("row-actions") },
                });
                if (p.privacy_notice_id) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!((__VLS_ctx.selected)))
                                    return;
                                if (!((p.privacy_notice_id)))
                                    return;
                                __VLS_ctx.readPrivacyNotice(p);
                            } },
                        ...{ class: ("small") },
                    });
                }
                if (!__VLS_ctx.activeConsent(p.code) && __VLS_ctx.selected.relationship?.is_legal) {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!(!((!__VLS_ctx.ready))))
                                    return;
                                if (!(!((!__VLS_ctx.auth))))
                                    return;
                                if (!((__VLS_ctx.selected)))
                                    return;
                                if (!((!__VLS_ctx.activeConsent(p.code) && __VLS_ctx.selected.relationship?.is_legal)))
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
                                if (!((__VLS_ctx.selected)))
                                    return;
                                if (!((__VLS_ctx.activeConsent(p.code))))
                                    return;
                                __VLS_ctx.revokeConsent(__VLS_ctx.activeConsent(p.code));
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
            if (!__VLS_ctx.ctx.consent_purposes?.length) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
                    ...{ class: ("empty") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createPrivacyRequest) },
                ...{ class: ("panel form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.privacyForm.request_type)),
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
                value: ((__VLS_ctx.privacyForm.description)),
                rows: ("4"),
                placeholder: ("Explique o pedido, quando necessário."),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            for (const [r] of __VLS_getVForSourceType((__VLS_ctx.ctx.privacy_requests?.filter((x) => x.subject_person_id === __VLS_ctx.selected.student.person_id).slice(0, 5)))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                    key: ((r.id)),
                });
                (r.protocol);
                (r.request_type);
                (r.state);
            }
        }
        if (__VLS_ctx.privacyNotice) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("section-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.privacyNotice.title);
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
            ...{ class: ("grid two") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("section-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        for (const [n] of __VLS_getVForSourceType((__VLS_ctx.ctx.notices?.slice(0, 8)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
                key: ((n.id)),
                ...{ class: ("notice") },
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRequest) },
            ...{ class: ("panel form") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.requestForm.subject);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input, __VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.requestForm.request_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.requestForm.description)),
            rows: ("4"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("protocols") },
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.ctx.requests?.slice(0, 5)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
                key: ((r.id)),
            });
            (r.protocol);
            (r.subject);
            (r.state);
        }
    }
    ['center', 'login-page', 'login-card', 'mark', 'eyebrow', 'flash', 'error', 'primary', 'mobile-shell', 'brand', 'mark', 'ghost', 'flash', 'error', 'flash', 'success', 'welcome', 'section-title', 'cards-scroll', 'dependent', 'active', 'grid', 'metric', 'metric', 'panel', 'section-title', 'report-block', 'list', 'list-row', 'right', 'empty', 'empty', 'panel', 'section-title', 'list', 'list-row', 'right', 'small', 'empty', 'panel', 'pix', 'section-title', 'small', 'primary', 'panel', 'section-title', 'list', 'list-row', 'pill', 'section-title', 'space', 'list', 'list-row', 'panel', 'section-title', 'report-block', 'grid', 'metric', 'metric', 'list', 'list-row', 'list-row', 'grid', 'two', 'panel', 'section-title', 'list', 'list-row', 'empty', 'panel', 'section-title', 'notice', 'notice', 'empty', 'grid', 'two', 'panel', 'section-title', 'metric-inline', 'empty', 'form', 'compact', 'cols', 'small', 'panel', 'section-title', 'notice', 'row-actions', 'pill', 'small', 'small', 'list-row', 'panel', 'section-title', 'small', 'primary', 'grid', 'two', 'panel', 'section-title', 'notice', 'row-actions', 'small', 'small', 'small', 'empty', 'panel', 'form', 'primary', 'panel', 'section-title', 'small', 'grid', 'two', 'panel', 'section-title', 'notice', 'empty', 'panel', 'form', 'primary', 'protocols',];
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
            busy: busy,
            error: error,
            notice: notice,
            privacyNotice: privacyNotice,
            email: email,
            password: password,
            ctx: ctx,
            selected: selected,
            pix: pix,
            pendingAuthorization: pendingAuthorization,
            consentText: consentText,
            policyForm: policyForm,
            requestForm: requestForm,
            privacyForm: privacyForm,
            school: school,
            login: login,
            logout: logout,
            openDependent: openDependent,
            generatePix: generatePix,
            copyPix: copyPix,
            walletForSelected: walletForSelected,
            registrationFor: registrationFor,
            saveFoodPolicy: saveFoodPolicy,
            registerEvent: registerEvent,
            authorizeEvent: authorizeEvent,
            activeConsent: activeConsent,
            readPrivacyNotice: readPrivacyNotice,
            grantConsent: grantConsent,
            revokeConsent: revokeConsent,
            createPrivacyRequest: createPrivacyRequest,
            createRequest: createRequest,
            money: money,
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
