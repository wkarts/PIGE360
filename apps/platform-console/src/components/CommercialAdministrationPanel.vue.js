import { computed, onMounted, reactive, ref, watch } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const tenantLoading = ref(false);
const partners = ref([]);
const plans = ref([]);
const entitlements = ref(null);
const selectedTenantId = ref("");
const selectedPartnerId = ref("");
const currentSubscriptionPlanId = ref("");
const partnerReason = ref("");
const planReason = ref("");
const linkedPartnerId = computed(() => String(entitlements.value?.partner?.id || ""));
const selectablePartners = computed(() => partners.value.filter((item) => (item.status === "active" || item.id === linkedPartnerId.value)));
const selectableSubscriptionPlans = computed(() => plans.value.filter((item) => (item.status === "active" || item.id === currentSubscriptionPlanId.value)));
const selectedPartnerIsActive = computed(() => Boolean(partners.value.find((partner) => partner.id === selectedPartnerId.value)?.status === "active"));
const currentSubscriptionPlanUnavailable = computed(() => Boolean(currentSubscriptionPlanId.value
    && plans.value.find((plan) => plan.id === currentSubscriptionPlanId.value)?.status !== "active"));
const partnerForm = reactive({
    code: "",
    legal_name: "",
    trade_name: "",
    contact_email: "",
    notes: "",
});
const planForm = reactive({
    code: "",
    name: "",
    description: "",
    currency: "BRL",
    billing_interval: "monthly",
    price_minor: 0,
    features_json: "{}",
    limits_json: "{}",
});
const subscriptionForm = reactive({
    plan_id: "",
    status: "active",
    version: 0,
    starts_at: "",
    current_period_end: "",
    trial_ends_at: "",
    cancel_at_period_end: false,
    reason: "",
});
const usageForm = reactive({
    period: new Date().toISOString().slice(0, 7),
    source: "manual",
    version: 0,
    metrics_json: "{}",
    reason: "",
});
let tenantLoadSequence = 0;
function message(error) {
    const candidate = error;
    return candidate?.problem?.detail || candidate?.message || "Erro inesperado";
}
function idempotencyKey(scope) {
    return `${scope}:${crypto.randomUUID()}`;
}
function parseMap(value, label) {
    const parsed = JSON.parse(value);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error(`${label} deve ser um objeto JSON.`);
    }
    return parsed;
}
async function mutate(path, method, body, scope) {
    return props.api.request(path, {
        method,
        headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey(scope) },
        body: JSON.stringify(body),
    });
}
async function loadCatalog() {
    loading.value = true;
    try {
        const [partnerData, planData] = await Promise.all([
            props.api.request("/platform/commercial/partners?limit=200"),
            props.api.request("/platform/commercial/plans?include_archived=true"),
        ]);
        partners.value = partnerData.items || [];
        plans.value = planData.items || [];
        if (!subscriptionForm.plan_id) {
            subscriptionForm.plan_id = plans.value.find((plan) => plan.status === "active")?.id || "";
        }
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
    finally {
        loading.value = false;
    }
}
async function loadTenantCommercial() {
    const sequence = ++tenantLoadSequence;
    const tenantId = selectedTenantId.value;
    const period = usageForm.period;
    const source = usageForm.source;
    tenantLoading.value = true;
    entitlements.value = null;
    selectedPartnerId.value = "";
    currentSubscriptionPlanId.value = "";
    subscriptionForm.version = 0;
    subscriptionForm.plan_id = "";
    subscriptionForm.status = "active";
    subscriptionForm.starts_at = "";
    subscriptionForm.current_period_end = "";
    subscriptionForm.trial_ends_at = "";
    subscriptionForm.cancel_at_period_end = false;
    usageForm.version = 0;
    usageForm.metrics_json = "{}";
    if (!tenantId) {
        tenantLoading.value = false;
        return;
    }
    try {
        const [subscriptionData, entitlementData, usageData] = await Promise.all([
            props.api.request(`/platform/commercial/tenants/${tenantId}/subscription`),
            props.api.request(`/platform/commercial/tenants/${tenantId}/entitlements?period=${period}`),
            props.api.request(`/platform/commercial/tenants/${tenantId}/usage?period=${period}`),
        ]);
        if (sequence !== tenantLoadSequence
            || tenantId !== selectedTenantId.value
            || period !== usageForm.period
            || source !== usageForm.source)
            return;
        const subscription = subscriptionData.subscription;
        if (subscription) {
            currentSubscriptionPlanId.value = subscription.plan_id;
            subscriptionForm.plan_id = subscription.plan_id;
            subscriptionForm.status = subscription.status;
            subscriptionForm.version = subscription.version;
            subscriptionForm.starts_at = subscription.starts_at;
            subscriptionForm.current_period_end = subscription.current_period_end || "";
            subscriptionForm.trial_ends_at = subscription.trial_ends_at || "";
            subscriptionForm.cancel_at_period_end = Boolean(subscription.cancel_at_period_end);
        }
        const snapshot = (usageData.items || []).find((item) => item.source === source);
        if (snapshot) {
            usageForm.version = snapshot.version;
            usageForm.metrics_json = JSON.stringify(snapshot.metrics, null, 2);
        }
        entitlements.value = entitlementData;
        selectedPartnerId.value = entitlementData.partner?.id || "";
    }
    catch (error) {
        if (sequence === tenantLoadSequence)
            emit("feedback", { type: "error", message: message(error) });
    }
    finally {
        if (sequence === tenantLoadSequence)
            tenantLoading.value = false;
    }
}
async function createPartner() {
    try {
        await mutate("/platform/commercial/partners", "POST", {
            ...partnerForm,
            contact_email: partnerForm.contact_email || null,
            notes: partnerForm.notes || null,
        }, "partner-create");
        Object.assign(partnerForm, { code: "", legal_name: "", trade_name: "", contact_email: "", notes: "" });
        emit("feedback", { type: "success", message: "Parceiro comercial cadastrado." });
        await loadCatalog();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function changePartner(target, partner) {
    if (partnerReason.value.trim().length < 10) {
        emit("feedback", { type: "error", message: "Informe um motivo auditável com ao menos 10 caracteres." });
        return;
    }
    const method = target === "archive" ? "DELETE" : "POST";
    const path = target === "archive"
        ? `/platform/commercial/partners/${partner.id}`
        : `/platform/commercial/partners/${partner.id}/${target}`;
    try {
        await mutate(path, method, { expected_version: partner.version, reason: partnerReason.value }, `partner-${target}`);
        partnerReason.value = "";
        emit("feedback", { type: "success", message: "Ciclo de vida do parceiro atualizado." });
        await loadCatalog();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function linkTenant(unlink = false) {
    const partner = partners.value.find((item) => item.id === selectedPartnerId.value);
    if (!partner || !selectedTenantId.value || partnerReason.value.trim().length < 10) {
        emit("feedback", { type: "error", message: "Selecione parceiro e tenant e informe o motivo do vínculo." });
        return;
    }
    if (!unlink && partner.status !== "active") {
        emit("feedback", { type: "error", message: "Somente parceiro ativo pode receber um novo vínculo." });
        return;
    }
    try {
        const result = await mutate(`/platform/commercial/partners/${partner.id}/tenants/${selectedTenantId.value}`, unlink ? "DELETE" : "PUT", { reason: partnerReason.value }, unlink ? "partner-unlink" : "partner-link");
        partnerReason.value = "";
        const successMessage = unlink ? "Tenant desvinculado." : "Tenant vinculado ao parceiro.";
        const noChangeMessage = unlink
            ? "Nenhuma alteração: o tenant já estava desvinculado deste parceiro."
            : "Nenhuma alteração: o tenant já estava vinculado a este parceiro.";
        emit("feedback", { type: "success", message: result.changed ? successMessage : noChangeMessage });
        await Promise.all([loadCatalog(), loadTenantCommercial()]);
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function createPlan() {
    try {
        await mutate("/platform/commercial/plans", "POST", {
            code: planForm.code,
            name: planForm.name,
            description: planForm.description || null,
            currency: planForm.currency,
            billing_interval: planForm.billing_interval,
            price_minor: planForm.price_minor,
            features: parseMap(planForm.features_json, "Features"),
            limits: parseMap(planForm.limits_json, "Limites"),
        }, "plan-create");
        Object.assign(planForm, {
            code: "", name: "", description: "", currency: "BRL", billing_interval: "monthly",
            price_minor: 0, features_json: "{}", limits_json: "{}",
        });
        emit("feedback", { type: "success", message: "Plano comercial cadastrado." });
        await loadCatalog();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function togglePlan(plan) {
    if (planReason.value.trim().length < 10) {
        emit("feedback", { type: "error", message: "Informe um motivo auditável para alterar o plano." });
        return;
    }
    try {
        await mutate(`/platform/commercial/plans/${plan.id}`, "PATCH", {
            expected_version: plan.version,
            reason: planReason.value,
            status: plan.status === "active" ? "inactive" : "active",
        }, "plan-status");
        planReason.value = "";
        emit("feedback", { type: "success", message: "Disponibilidade do plano atualizada." });
        await loadCatalog();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function archivePlan(plan) {
    if (planReason.value.trim().length < 10) {
        emit("feedback", { type: "error", message: "Informe um motivo auditável para arquivar o plano." });
        return;
    }
    try {
        await mutate(`/platform/commercial/plans/${plan.id}`, "DELETE", {
            expected_version: plan.version,
            reason: planReason.value,
        }, "plan-archive");
        planReason.value = "";
        emit("feedback", { type: "success", message: "Plano arquivado." });
        await loadCatalog();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function saveSubscription() {
    if (!selectedTenantId.value || !subscriptionForm.plan_id || subscriptionForm.reason.trim().length < 10) {
        emit("feedback", { type: "error", message: "Selecione tenant/plano e informe o motivo da assinatura." });
        return;
    }
    const selectedPlan = plans.value.find((plan) => plan.id === subscriptionForm.plan_id);
    const isCurrentPlan = subscriptionForm.plan_id === currentSubscriptionPlanId.value;
    if (!selectedPlan || (!isCurrentPlan && selectedPlan.status !== "active")) {
        emit("feedback", { type: "error", message: "Uma nova assinatura ou migração exige um plano ativo." });
        return;
    }
    if (selectedPlan.status !== "active" && ["active", "trialing"].includes(subscriptionForm.status)) {
        emit("feedback", {
            type: "error",
            message: "O plano atual está indisponível para venda; cancele a assinatura ou migre para um plano ativo.",
        });
        return;
    }
    try {
        const result = await mutate(`/platform/commercial/tenants/${selectedTenantId.value}/subscription`, "PUT", {
            expected_version: subscriptionForm.version,
            plan_id: subscriptionForm.plan_id,
            status: subscriptionForm.status,
            starts_at: subscriptionForm.starts_at || new Date().toISOString(),
            current_period_end: subscriptionForm.current_period_end || null,
            trial_ends_at: subscriptionForm.trial_ends_at || null,
            cancel_at_period_end: subscriptionForm.cancel_at_period_end,
            reason: subscriptionForm.reason,
        }, "subscription-set");
        subscriptionForm.version = result.version;
        subscriptionForm.reason = "";
        emit("feedback", { type: "success", message: "Assinatura manual atualizada." });
        await loadTenantCommercial();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
async function saveUsage() {
    if (!selectedTenantId.value || usageForm.reason.trim().length < 10) {
        emit("feedback", { type: "error", message: "Selecione o tenant e informe o motivo do snapshot." });
        return;
    }
    try {
        const result = await mutate(`/platform/commercial/tenants/${selectedTenantId.value}/usage/${usageForm.period}`, "PUT", {
            expected_version: usageForm.version,
            source: usageForm.source,
            metrics: parseMap(usageForm.metrics_json, "Métricas"),
            reason: usageForm.reason,
        }, "usage-set");
        usageForm.version = result.version;
        usageForm.reason = "";
        emit("feedback", { type: "success", message: "Snapshot de uso registrado." });
        await loadTenantCommercial();
    }
    catch (error) {
        emit("feedback", { type: "error", message: message(error) });
    }
}
watch(() => props.tenants, (value) => {
    if (!selectedTenantId.value)
        selectedTenantId.value = value[0]?.id || "";
}, { immediate: true });
watch(selectedTenantId, loadTenantCommercial);
watch(() => usageForm.period, loadTenantCommercial);
watch(() => usageForm.source, loadTenantCommercial);
onMounted(async () => {
    await loadCatalog();
    await loadTenantCommercial();
});
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['commercial-panel', 'commercial-panel', 'commercial-panel', 'commercial-panel', 'commercial-panel', 'commercial-grid', 'commercial-grid', 'commercial-panel', 'wide', 'row', 'row', 'row', 'secondary', 'danger', 'entitlement-summary', 'entitlement-summary', 'commercial-grid', 'selectors', 'row',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("commercial-panel") },
        'aria-labelledby': ("commercial-title"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: ("eyebrow") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        id: ("commercial-title"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.loadCatalog) },
        ...{ class: ("secondary") },
        disabled: ((__VLS_ctx.loading)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("commercial-grid") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createPartner) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
        minlength: ("2"),
    });
    (__VLS_ctx.partnerForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.partnerForm.legal_name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.partnerForm.trade_name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("email"),
    });
    (__VLS_ctx.partnerForm.contact_email);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.partnerForm.notes)),
        rows: ("2"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        type: ("submit"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createPlan) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
        minlength: ("2"),
    });
    (__VLS_ctx.planForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.planForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("0"),
    });
    (__VLS_ctx.planForm.price_minor);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.planForm.billing_interval)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("monthly"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("annual"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("custom"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.planForm.features_json)),
        rows: ("2"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.planForm.limits_json)),
        rows: ("2"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        type: ("submit"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: ("wide") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        placeholder: ("Obrigatório para lifecycle e vínculos"),
    });
    (__VLS_ctx.partnerReason);
    if (__VLS_ctx.partners.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [partner] of __VLS_getVForSourceType((__VLS_ctx.partners))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((partner.id)),
                ...{ class: ("row") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (partner.trade_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (partner.code);
            (partner.status);
            (partner.tenant_count);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("actions") },
            });
            if (partner.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.partners.length)))
                                return;
                            if (!((partner.status === 'active')))
                                return;
                            __VLS_ctx.changePartner('suspend', partner);
                        } },
                    ...{ class: ("secondary") },
                });
            }
            if (partner.status === 'suspended') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.partners.length)))
                                return;
                            if (!((partner.status === 'suspended')))
                                return;
                            __VLS_ctx.changePartner('reactivate', partner);
                        } },
                    ...{ class: ("secondary") },
                });
            }
            if (partner.status !== 'archived') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.partners.length)))
                                return;
                            if (!((partner.status !== 'archived')))
                                return;
                            __VLS_ctx.changePartner('archive', partner);
                        } },
                    ...{ class: ("danger") },
                });
            }
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: ("empty") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: ("wide") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        placeholder: ("Obrigatório para disponibilidade e arquivo"),
    });
    (__VLS_ctx.planReason);
    if (__VLS_ctx.plans.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [plan] of __VLS_getVForSourceType((__VLS_ctx.plans))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((plan.id)),
                ...{ class: ("row") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (plan.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (plan.code);
            (plan.status);
            (plan.currency);
            ((plan.price_minor / 100).toFixed(2));
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("actions") },
            });
            if (plan.status !== 'archived') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.plans.length)))
                                return;
                            if (!((plan.status !== 'archived')))
                                return;
                            __VLS_ctx.togglePlan(plan);
                        } },
                    ...{ class: ("secondary") },
                });
                (plan.status === "active" ? "Desativar venda" : "Ativar venda");
            }
            if (plan.status !== 'archived') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.plans.length)))
                                return;
                            if (!((plan.status !== 'archived')))
                                return;
                            __VLS_ctx.archivePlan(plan);
                        } },
                    ...{ class: ("danger") },
                });
            }
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({
        ...{ class: ("wide tenant-admin") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h3, __VLS_intrinsicElements.h3)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("selectors") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.selectedTenantId)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [tenant] of __VLS_getVForSourceType((__VLS_ctx.tenants))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((tenant.id)),
            value: ((tenant.id)),
        });
        (tenant.trade_name);
        (tenant.code);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.selectedPartnerId)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [partner] of __VLS_getVForSourceType((__VLS_ctx.selectablePartners))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((partner.id)),
            value: ((partner.id)),
        });
        (partner.trade_name);
        if (partner.status !== 'active') {
            (partner.status);
        }
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("actions align-end") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.linkTenant(false);
            } },
        ...{ class: ("secondary") },
        disabled: ((!__VLS_ctx.selectedPartnerId || !__VLS_ctx.selectedPartnerIsActive)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.linkTenant(true);
            } },
        ...{ class: ("secondary") },
        disabled: ((!__VLS_ctx.linkedPartnerId || __VLS_ctx.selectedPartnerId !== __VLS_ctx.linkedPartnerId)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("commercial-grid") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.saveSubscription) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h4, __VLS_intrinsicElements.h4)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.subscriptionForm.plan_id)),
        required: (true),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [plan] of __VLS_getVForSourceType((__VLS_ctx.selectableSubscriptionPlans))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((plan.id)),
            value: ((plan.id)),
        });
        (plan.name);
        if (plan.status !== 'active') {
            (plan.status);
        }
    }
    if (__VLS_ctx.currentSubscriptionPlanUnavailable) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({
            ...{ class: ("commercial-warning") },
        });
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.subscriptionForm.status)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("active"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("trialing"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("suspended"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: ("canceled"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
        minlength: ("10"),
    });
    (__VLS_ctx.subscriptionForm.reason);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        type: ("submit"),
        disabled: ((__VLS_ctx.tenantLoading)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.saveUsage) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.h4, __VLS_intrinsicElements.h4)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("month"),
        required: (true),
    });
    (__VLS_ctx.usageForm.period);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.usageForm.source);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.textarea)({
        value: ((__VLS_ctx.usageForm.metrics_json)),
        rows: ("3"),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
        minlength: ("10"),
    });
    (__VLS_ctx.usageForm.reason);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
        type: ("submit"),
        disabled: ((__VLS_ctx.tenantLoading)),
    });
    if (__VLS_ctx.entitlements) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("entitlement-summary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.entitlements.entitlements?.enabled ? "habilitados" : "indisponíveis");
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.entitlements.plan?.name || "não configurado");
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (JSON.stringify(__VLS_ctx.entitlements.entitlements?.usage || {}));
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (JSON.stringify(__VLS_ctx.entitlements.entitlements?.remaining || {}));
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    }
    ['commercial-panel', 'eyebrow', 'secondary', 'commercial-grid', 'primary', 'primary', 'wide', 'rows', 'row', 'actions', 'secondary', 'secondary', 'danger', 'empty', 'wide', 'rows', 'row', 'actions', 'secondary', 'danger', 'wide', 'tenant-admin', 'selectors', 'actions', 'align-end', 'secondary', 'secondary', 'commercial-grid', 'commercial-warning', 'primary', 'primary', 'entitlement-summary',];
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
            tenantLoading: tenantLoading,
            partners: partners,
            plans: plans,
            entitlements: entitlements,
            selectedTenantId: selectedTenantId,
            selectedPartnerId: selectedPartnerId,
            partnerReason: partnerReason,
            planReason: planReason,
            linkedPartnerId: linkedPartnerId,
            selectablePartners: selectablePartners,
            selectableSubscriptionPlans: selectableSubscriptionPlans,
            selectedPartnerIsActive: selectedPartnerIsActive,
            currentSubscriptionPlanUnavailable: currentSubscriptionPlanUnavailable,
            partnerForm: partnerForm,
            planForm: planForm,
            subscriptionForm: subscriptionForm,
            usageForm: usageForm,
            loadCatalog: loadCatalog,
            createPartner: createPartner,
            changePartner: changePartner,
            linkTenant: linkTenant,
            createPlan: createPlan,
            togglePlan: togglePlan,
            archivePlan: archivePlan,
            saveSubscription: saveSubscription,
            saveUsage: saveUsage,
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
