import { computed, onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const tab = ref("catalog");
const catalogs = ref([]);
const services = ref([]);
const subscriptions = ref([]);
const orders = ref([]);
const executions = ref([]);
const fiscalEvents = ref([]);
const people = ref([]);
const dashboard = ref({});
const selectedService = ref(null);
const selectedSubscription = ref(null);
const selectedOrder = ref(null);
const today = new Date().toISOString().slice(0, 10);
const month = new Date().toISOString().slice(0, 7);
const catalogForm = reactive({ code: "", name: "", description: "", valid_from: today, status: "active" });
const serviceForm = reactive({ catalog_id: "", code: "", name: "", description: "", service_type: "administrative", recurrence_type: "one_time", unit_of_measure: "unit", taxable: true, status: "active" });
const variantForm = reactive({ code: "PADRAO", name: "Padrão", duration_minutes: 60, capacity: null, status: "active" });
const priceForm = reactive({ variant_id: "", name: "Tabela vigente", valid_from: today, amount: "", billing_frequency: "one_time", status: "active" });
const fiscalForm = reactive({ variant_id: "", valid_from: today, nbs_code: "", lc116_code: "", municipal_service_code: "", cnae_code: "", iss_rate: "0", ibs_rate: "0", cbs_rate: "0", cclass_trib: "", fiscal_trigger: "billing" });
const billingForm = reactive({ variant_id: "", code: "PADRAO", name: "Cobrança padrão", billing_trigger: "competence", due_day: 10, installment_count: 1, interval_months: 1, recognition_policy: "competence", fiscal_trigger: "competence", proration_policy: "none", status: "active" });
const subscriptionForm = reactive({ subscription_number: "", service_id: "", variant_id: "", subscriber_person_id: "", billing_rule_id: "", starts_on: today, ends_on: "", quantity: "1", unit_price: "", discount_amount: "0", auto_renew: false });
const competenceForm = reactive({ competence_key: month, due_date: `${month}-10` });
const orderForm = reactive({ order_number: "", subscriber_person_id: "", service_id: "", variant_id: "", quantity: "1", unit_price: "", discount_amount: "0", due_date: today, notes: "" });
const executionForm = reactive({ order_item_id: "", scheduled_at: "", quantity: "1", performer_person_id: "", notes: "" });
const currentVariants = computed(() => selectedService.value?.variants ?? []);
const currentPrices = computed(() => selectedService.value?.price_tables ?? []);
const currentFiscalProfiles = computed(() => selectedService.value?.fiscal_profiles ?? []);
const currentBillingRules = computed(() => selectedService.value?.billing_rules ?? []);
function message(error) {
    const candidate = error;
    return candidate.problem?.detail || (error instanceof Error ? error.message : "Erro inesperado");
}
function idempotency(prefix) { return `${prefix}-${crypto.randomUUID()}`; }
async function request(path, init = {}) { return props.api.request(path, init); }
async function post(path, body, key) {
    const headers = { "Content-Type": "application/json" };
    if (key)
        headers["Idempotency-Key"] = key;
    return request(path, { method: "POST", headers, body: JSON.stringify(body) });
}
async function patch(path, body) {
    return request(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function numeric(value) { return value.trim() === "" ? null : value; }
function clearServiceSelection() {
    selectedService.value = null;
    Object.assign(variantForm, { code: "PADRAO", name: "Padrão", duration_minutes: 60, capacity: null, status: "active" });
    Object.assign(priceForm, { variant_id: "", name: "Tabela vigente", valid_from: today, amount: "", billing_frequency: "one_time", status: "active" });
    Object.assign(fiscalForm, { variant_id: "", valid_from: today, nbs_code: "", lc116_code: "", municipal_service_code: "", cnae_code: "", iss_rate: "0", ibs_rate: "0", cbs_rate: "0", cclass_trib: "", fiscal_trigger: "billing" });
    Object.assign(billingForm, { variant_id: "", code: "PADRAO", name: "Cobrança padrão", billing_trigger: "competence", due_day: 10, installment_count: 1, interval_months: 1, recognition_policy: "competence", fiscal_trigger: "competence", proration_policy: "none", status: "active" });
}
async function load() {
    loading.value = true;
    try {
        const [catalogResult, serviceResult, subscriptionResult, orderResult, executionResult, fiscalResult, peopleResult, dashboardResult] = await Promise.all([
            request("/service-catalogs"), request("/services"), request("/service-subscriptions"), request("/service-orders"),
            request("/service-executions"), request("/service-fiscal-events"), request("/people?limit=200"), request("/services-dashboard"),
        ]);
        catalogs.value = catalogResult.items ?? [];
        services.value = serviceResult.items ?? [];
        subscriptions.value = subscriptionResult.items ?? [];
        orders.value = orderResult.items ?? [];
        executions.value = executionResult.items ?? [];
        fiscalEvents.value = fiscalResult.items ?? [];
        people.value = peopleResult.items ?? [];
        dashboard.value = dashboardResult;
        if (!serviceForm.catalog_id && catalogs.value[0])
            serviceForm.catalog_id = catalogs.value[0].id;
        if (!subscriptionForm.service_id && services.value[0])
            subscriptionForm.service_id = services.value[0].id;
        if (!orderForm.service_id && services.value[0])
            orderForm.service_id = services.value[0].id;
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        loading.value = false;
    }
}
async function createCatalog() {
    try {
        await post("/service-catalogs", { ...catalogForm, description: catalogForm.description || null }, idempotency("service-catalog"));
        Object.assign(catalogForm, { code: "", name: "", description: "", valid_from: today, status: "active" });
        emit("notice", "Catálogo de serviços cadastrado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createService() {
    try {
        const created = await post("/services", { ...serviceForm, catalog_id: serviceForm.catalog_id || null, description: serviceForm.description || null }, idempotency("service"));
        Object.assign(serviceForm, { catalog_id: serviceForm.catalog_id, code: "", name: "", description: "", service_type: "administrative", recurrence_type: "one_time", unit_of_measure: "unit", taxable: true, status: "active" });
        emit("notice", "Serviço cadastrado.");
        await load();
        await showService(created);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showService(service) {
    try {
        selectedService.value = await request(`/services/${service.id}`);
        const firstVariant = currentVariants.value[0];
        priceForm.variant_id = firstVariant?.id ?? "";
        fiscalForm.variant_id = firstVariant?.id ?? "";
        billingForm.variant_id = firstVariant?.id ?? "";
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function updateServiceStatus(status) {
    if (!selectedService.value)
        return;
    try {
        selectedService.value = await patch(`/services/${selectedService.value.id}`, { status, expected_version: selectedService.value.version });
        emit("notice", `Serviço atualizado para ${status}.`);
        await load();
        await showService(selectedService.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createVariant() {
    if (!selectedService.value)
        return;
    try {
        await post(`/services/${selectedService.value.id}/variants`, { ...variantForm, duration_minutes: variantForm.duration_minutes || null, capacity: variantForm.capacity || null }, idempotency("service-variant"));
        emit("notice", "Variação cadastrada.");
        await showService(selectedService.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createPrice() {
    if (!selectedService.value)
        return;
    try {
        await post(`/services/${selectedService.value.id}/price-tables`, { ...priceForm, variant_id: priceForm.variant_id || null }, idempotency("service-price"));
        emit("notice", "Preço e vigência registrados.");
        await showService(selectedService.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createFiscalProfile() {
    if (!selectedService.value)
        return;
    try {
        await post(`/services/${selectedService.value.id}/fiscal-profiles`, { ...fiscalForm, variant_id: fiscalForm.variant_id || null, nbs_code: fiscalForm.nbs_code || null, lc116_code: fiscalForm.lc116_code || null, municipal_service_code: fiscalForm.municipal_service_code || null, cnae_code: fiscalForm.cnae_code || null, cclass_trib: fiscalForm.cclass_trib || null }, idempotency("service-fiscal"));
        emit("notice", "Perfil fiscal versionado.");
        await showService(selectedService.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function publishFiscal(profile) {
    try {
        await post(`/service-fiscal-profiles/${profile.id}/publish`, { notes: "Classificação revisada na administração do tenant." });
        emit("notice", "Perfil fiscal publicado.");
        if (selectedService.value)
            await showService(selectedService.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createBillingRule() {
    if (!selectedService.value)
        return;
    try {
        await post(`/services/${selectedService.value.id}/billing-rules`, { ...billingForm, variant_id: billingForm.variant_id || null }, idempotency("service-billing"));
        emit("notice", "Regra de cobrança registrada.");
        await showService(selectedService.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createSubscription() {
    try {
        const created = await post("/service-subscriptions", { ...subscriptionForm, variant_id: subscriptionForm.variant_id || null, ends_on: subscriptionForm.ends_on || null, unit_price: numeric(subscriptionForm.unit_price) }, idempotency("service-subscription"));
        selectedSubscription.value = created;
        emit("notice", "Assinatura criada em rascunho.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function subscriptionAction(row, action) {
    try {
        await post(`/service-subscriptions/${row.id}/${action}`, { reason: `Ação ${action} registrada pela administração.` });
        emit("notice", "Estado da assinatura atualizado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function generateCompetence(row) {
    try {
        await post(`/service-subscriptions/${row.id}/competencies`, competenceForm, idempotency(`service-competence-${competenceForm.competence_key}`));
        emit("notice", "Competência gerada com pedido, cobrança, execução e evento fiscal.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createOrder() {
    try {
        await post("/service-orders", { order_number: orderForm.order_number || null, subscriber_person_id: orderForm.subscriber_person_id || null, due_date: orderForm.due_date || null, installment_count: 1, discount_amount: "0", notes: orderForm.notes || null, items: [{ service_id: orderForm.service_id, variant_id: orderForm.variant_id || null, quantity: orderForm.quantity, unit_price: numeric(orderForm.unit_price), discount_amount: orderForm.discount_amount }] }, idempotency("service-order"));
        emit("notice", "Pedido de serviço criado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function orderAction(row, action) {
    try {
        await post(`/service-orders/${row.id}/${action}`, action === "cancel" ? { reason: "Cancelamento registrado pela administração." } : { notes: `Ação ${action} registrada pela administração.` });
        emit("notice", "Pedido atualizado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showOrder(row) {
    try {
        selectedOrder.value = await request(`/service-orders/${row.id}`);
        executionForm.order_item_id = selectedOrder.value?.items?.[0]?.id ?? "";
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function scheduleExecution() {
    if (!selectedOrder.value)
        return;
    try {
        await post(`/service-orders/${selectedOrder.value.id}/executions`, { ...executionForm, scheduled_at: executionForm.scheduled_at ? new Date(executionForm.scheduled_at).toISOString() : null, performer_person_id: executionForm.performer_person_id || null, notes: executionForm.notes || null }, idempotency("service-execution"));
        emit("notice", "Execução agendada.");
        await load();
        await showOrder(selectedOrder.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function executionAction(row, action) {
    try {
        const body = action === "complete" ? { completed_quantity: row.quantity, notes: "Execução concluída.", evidence: { source: "tenant-admin-web" } } : action === "cancel" ? { reason: "Execução cancelada pela administração." } : { notes: "Execução iniciada pela administração." };
        await post(`/service-executions/${row.id}/${action}`, body);
        emit("notice", "Execução atualizada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
function money(value) { return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value ?? 0)); }
function dateTime(value) { return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—"; }
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['service-tabs', 'service-tabs', 'service-tabs', 'rows', 'rows', 'rows', 'service-tabs', 'refresh', 'rows',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("service-module") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("metrics") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.services ?? __VLS_ctx.services.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.active_subscriptions ?? 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.open_orders ?? 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.dashboard.not_configured_fiscal_events ?? 0);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.money(__VLS_ctx.dashboard.billed_total));
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("service-tabs") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'catalog';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'catalog' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'subscriptions';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'subscriptions' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'orders';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'orders' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'fiscal';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'fiscal' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        ...{ class: ("small refresh") },
        disabled: ((__VLS_ctx.loading)),
    });
    (__VLS_ctx.loading ? 'Atualizando…' : 'Atualizar');
    if (__VLS_ctx.tab === 'catalog') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createCatalog) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.catalogForm.valid_from);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.catalogForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.catalogForm.description)),
            rows: ("3"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createService) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.serviceForm.catalog_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.catalogs))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.serviceForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.serviceForm.service_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("tuition"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("course"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("transportation"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("extracurricular"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("event"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("document"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("administrative"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("other"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.serviceForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.serviceForm.recurrence_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("one_time"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("monthly"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("quarterly"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("annual"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("custom"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.serviceForm.taxable);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.services.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.services))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.service_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.recurrence_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((row.status === 'active' ? 'ok' : 'warn')) },
            });
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((__VLS_ctx.tab === 'catalog')))
                            return;
                        __VLS_ctx.showService(row);
                    } },
                ...{ class: ("small") },
            });
        }
        if (!__VLS_ctx.services.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.selectedService) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.selectedService.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (__VLS_ctx.selectedService.code);
            (__VLS_ctx.selectedService.version);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            if (__VLS_ctx.selectedService.status !== 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'catalog')))
                                return;
                            if (!((__VLS_ctx.selectedService)))
                                return;
                            if (!((__VLS_ctx.selectedService.status !== 'active')))
                                return;
                            __VLS_ctx.updateServiceStatus('active');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (__VLS_ctx.selectedService.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.tab === 'catalog')))
                                return;
                            if (!((__VLS_ctx.selectedService)))
                                return;
                            if (!((__VLS_ctx.selectedService.status === 'active')))
                                return;
                            __VLS_ctx.updateServiceStatus('inactive');
                        } },
                    ...{ class: ("small") },
                });
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.clearServiceSelection) },
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createVariant) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.variantForm.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.variantForm.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
            });
            (__VLS_ctx.variantForm.duration_minutes);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
            });
            (__VLS_ctx.variantForm.capacity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createPrice) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.priceForm.variant_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentVariants))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.id)),
                    value: ((row.id)),
                });
                (row.name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.priceForm.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0.01"),
                step: ("0.01"),
                required: (true),
            });
            (__VLS_ctx.priceForm.amount);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
                required: (true),
            });
            (__VLS_ctx.priceForm.valid_from);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.priceForm.billing_frequency)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("one_time"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("monthly"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("annual"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createFiscalProfile) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.fiscalForm.variant_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentVariants))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.id)),
                    value: ((row.id)),
                });
                (row.name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.fiscalForm.nbs_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.fiscalForm.lc116_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.fiscalForm.municipal_service_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.fiscalForm.cnae_code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.fiscalForm.cclass_trib);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.fiscalForm.fiscal_trigger)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("competence"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("billing"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("payment"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("execution"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("manual"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.createBillingRule) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.billingForm.variant_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentVariants))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.id)),
                    value: ((row.id)),
                });
                (row.name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.billingForm.code);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.billingForm.name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("1"),
                max: ("31"),
            });
            (__VLS_ctx.billingForm.due_day);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.billingForm.billing_trigger)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("competence"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("billing"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("payment"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("execution"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: ("manual"),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows") },
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentVariants))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((row.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (row.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (row.code);
                (row.capacity ?? 'livre');
            }
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentPrices))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((row.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (row.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (__VLS_ctx.money(row.amount));
                (row.valid_from);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows") },
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentFiscalProfiles))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((row.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (row.nbs_code || 'NBS pendente');
                (row.lc116_code || 'LC 116 pendente');
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (row.classification_status);
                (row.status);
                if (row.status !== 'published') {
                    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                        ...{ onClick: (...[$event]) => {
                                if (!((__VLS_ctx.tab === 'catalog')))
                                    return;
                                if (!((__VLS_ctx.selectedService)))
                                    return;
                                if (!((row.status !== 'published')))
                                    return;
                                __VLS_ctx.publishFiscal(row);
                            } },
                        ...{ class: ("small") },
                    });
                }
            }
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.currentBillingRules))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((row.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (row.name);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (row.due_day);
                (row.billing_trigger);
            }
        }
    }
    else if (__VLS_ctx.tab === 'subscriptions') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createSubscription) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.subscriptionForm.subscription_number);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.subscriptionForm.starts_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.subscriptionForm.service_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.services))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.subscriptionForm.subscriber_person_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.people))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.full_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("UUID da regra publicada"),
            required: (true),
        });
        (__VLS_ctx.subscriptionForm.billing_rule_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.01"),
            step: ("0.01"),
        });
        (__VLS_ctx.subscriptionForm.unit_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.subscriptionForm.discount_amount);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.subscriptionForm.auto_renew);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (...[$event]) => {
                    if (!(!((__VLS_ctx.tab === 'catalog'))))
                        return;
                    if (!((__VLS_ctx.tab === 'subscriptions')))
                        return;
                    __VLS_ctx.selectedSubscription && __VLS_ctx.generateCompetence(__VLS_ctx.selectedSubscription);
                } },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.selectedSubscription)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ((null)),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.subscriptions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row)),
            });
            (row.subscription_number);
            (row.service_name || row.service_id);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("month"),
            required: (true),
        });
        (__VLS_ctx.competenceForm.competence_key);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
            required: (true),
        });
        (__VLS_ctx.competenceForm.due_date);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((!__VLS_ctx.selectedSubscription)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.subscriptions.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.subscriptions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.subscription_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.service_name || row.service_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.subscriber_name || row.subscriber_person_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.cycle_amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((row.status === 'active' ? 'ok' : 'warn')) },
            });
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.status === 'draft') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!((__VLS_ctx.tab === 'subscriptions')))
                                return;
                            if (!((row.status === 'draft')))
                                return;
                            __VLS_ctx.subscriptionAction(row, 'activate');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!((__VLS_ctx.tab === 'subscriptions')))
                                return;
                            if (!((row.status === 'active')))
                                return;
                            __VLS_ctx.subscriptionAction(row, 'suspend');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'suspended') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!((__VLS_ctx.tab === 'subscriptions')))
                                return;
                            if (!((row.status === 'suspended')))
                                return;
                            __VLS_ctx.subscriptionAction(row, 'resume');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (!['cancelled', 'ended'].includes(row.status)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!((__VLS_ctx.tab === 'subscriptions')))
                                return;
                            if (!((!['cancelled', 'ended'].includes(row.status))))
                                return;
                            __VLS_ctx.subscriptionAction(row, 'cancel');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!((__VLS_ctx.tab === 'subscriptions')))
                                return;
                            if (!((row.status === 'active')))
                                return;
                            __VLS_ctx.selectedSubscription = row;
                            __VLS_ctx.generateCompetence(row);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.subscriptions.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
    }
    else if (__VLS_ctx.tab === 'orders') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createOrder) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.orderForm.service_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.services))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.orderForm.subscriber_person_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.people))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.full_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.0001"),
            step: ("0.0001"),
            required: (true),
        });
        (__VLS_ctx.orderForm.quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.01"),
            step: ("0.01"),
        });
        (__VLS_ctx.orderForm.unit_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.orderForm.due_date);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.orderForm.discount_amount);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.scheduleExecution) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            ...{ onChange: (...[$event]) => {
                    if (!(!((__VLS_ctx.tab === 'catalog'))))
                        return;
                    if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                        return;
                    if (!((__VLS_ctx.tab === 'orders')))
                        return;
                    __VLS_ctx.selectedOrder && __VLS_ctx.showOrder(__VLS_ctx.selectedOrder);
                } },
            value: ((__VLS_ctx.selectedOrder)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ((null)),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.orders))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row)),
            });
            (row.order_number);
            (__VLS_ctx.money(row.total_amount));
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.executionForm.order_item_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.selectedOrder?.items || []))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.description);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.0001"),
            step: ("0.0001"),
            required: (true),
        });
        (__VLS_ctx.executionForm.quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("datetime-local"),
        });
        (__VLS_ctx.executionForm.scheduled_at);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((!__VLS_ctx.selectedOrder)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.orders.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.orders))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.order_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.subscriber_name || row.subscriber_person_id || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.total_amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.charge_state || row.charge?.state || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.fiscal_status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
            });
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'catalog'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                            return;
                        if (!((__VLS_ctx.tab === 'orders')))
                            return;
                        __VLS_ctx.showOrder(row);
                    } },
                ...{ class: ("small") },
            });
            if (row.status === 'draft') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((row.status === 'draft')))
                                return;
                            __VLS_ctx.orderAction(row, 'confirm');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'confirmed') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((row.status === 'confirmed')))
                                return;
                            __VLS_ctx.orderAction(row, 'start');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'in_progress') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((row.status === 'in_progress')))
                                return;
                            __VLS_ctx.orderAction(row, 'complete');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (!['cancelled', 'completed'].includes(row.status)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((!['cancelled', 'completed'].includes(row.status))))
                                return;
                            __VLS_ctx.orderAction(row, 'cancel');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.executions.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.executions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.order_number || row.order_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.dateTime(row.scheduled_at));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.completed_quantity || row.quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.status === 'scheduled') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((row.status === 'scheduled')))
                                return;
                            __VLS_ctx.executionAction(row, 'start');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'in_progress') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((row.status === 'in_progress')))
                                return;
                            __VLS_ctx.executionAction(row, 'complete');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (!['completed', 'cancelled'].includes(row.status)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'catalog'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'subscriptions'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((!['completed', 'cancelled'].includes(row.status))))
                                return;
                            __VLS_ctx.executionAction(row, 'cancel');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.fiscalEvents.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.fiscalEvents))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.source_type);
            (row.source_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.trigger_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.classification_status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: ("pill") },
                ...{ class: ((row.status === 'not_configured' ? 'warn' : row.status === 'blocked_validation' ? 'danger' : 'ok')) },
            });
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.failure_code || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.dateTime(row.updated_at));
        }
        if (!__VLS_ctx.fiscalEvents.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
    }
    ['service-module', 'metrics', 'service-tabs', 'selected', 'selected', 'selected', 'selected', 'small', 'refresh', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'cols', 'cols', 'inline', 'primary', 'panel', 'panel-title', 'pill', 'small', 'empty', 'panel', 'panel-title', 'small', 'small', 'small', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'cols', 'primary', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'primary', 'panel', 'cols', 'cols', 'primary', 'grid-2', 'panel', 'rows', 'panel', 'rows', 'small', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'inline', 'primary', 'panel', 'cols', 'primary', 'panel', 'panel-title', 'pill', 'small', 'small', 'small', 'small', 'small', 'empty', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'primary', 'panel', 'panel-title', 'pill', 'small', 'small', 'small', 'small', 'small', 'panel', 'panel-title', 'small', 'small', 'small', 'panel', 'panel-title', 'pill', 'empty',];
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
            tab: tab,
            catalogs: catalogs,
            services: services,
            subscriptions: subscriptions,
            orders: orders,
            executions: executions,
            fiscalEvents: fiscalEvents,
            people: people,
            dashboard: dashboard,
            selectedService: selectedService,
            selectedSubscription: selectedSubscription,
            selectedOrder: selectedOrder,
            catalogForm: catalogForm,
            serviceForm: serviceForm,
            variantForm: variantForm,
            priceForm: priceForm,
            fiscalForm: fiscalForm,
            billingForm: billingForm,
            subscriptionForm: subscriptionForm,
            competenceForm: competenceForm,
            orderForm: orderForm,
            executionForm: executionForm,
            currentVariants: currentVariants,
            currentPrices: currentPrices,
            currentFiscalProfiles: currentFiscalProfiles,
            currentBillingRules: currentBillingRules,
            clearServiceSelection: clearServiceSelection,
            load: load,
            createCatalog: createCatalog,
            createService: createService,
            showService: showService,
            updateServiceStatus: updateServiceStatus,
            createVariant: createVariant,
            createPrice: createPrice,
            createFiscalProfile: createFiscalProfile,
            publishFiscal: publishFiscal,
            createBillingRule: createBillingRule,
            createSubscription: createSubscription,
            subscriptionAction: subscriptionAction,
            generateCompetence: generateCompetence,
            createOrder: createOrder,
            orderAction: orderAction,
            showOrder: showOrder,
            scheduleExecution: scheduleExecution,
            executionAction: executionAction,
            money: money,
            dateTime: dateTime,
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
