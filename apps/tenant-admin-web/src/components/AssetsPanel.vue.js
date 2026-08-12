import { computed, onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const locations = ref([]);
const assets = ref([]);
const people = ref([]);
const products = ref([]);
const suppliers = ref([]);
const selectedAsset = ref(null);
const selectedMaintenance = ref(null);
const selectedLoan = ref(null);
const today = new Date().toISOString().slice(0, 10);
const month = new Date().toISOString().slice(0, 7);
const locationForm = reactive({ code: "", name: "", parent_id: "" });
const assetForm = reactive({ tag: "", name: "", location_id: "", product_id: "", receipt_item_id: "", description: "", serial_number: "", responsible_person_id: "", acquisition_date: today, acquisition_cost: "0", useful_life_months: 60, residual_value: "0", warranty_until: "" });
const transferForm = reactive({ location_id: "", responsible_person_id: "", reason: "Transferência patrimonial autorizada." });
const maintenanceForm = reactive({ maintenance_type: "preventive", scheduled_on: today, supplier_id: "", estimated_cost: "0", description: "" });
const maintenanceCompleteForm = reactive({ result_notes: "Serviço concluído e bem liberado.", actual_cost: "0" });
const loanForm = reactive({ borrower_person_id: "", expected_return_at: "", condition_out: "Bem entregue em condições regulares de uso." });
const loanReturnForm = reactive({ condition_in: "Bem devolvido e conferido." });
const depreciationForm = reactive({ competence: month });
const movements = computed(() => selectedAsset.value?.movements ?? selectedAsset.value?.events ?? []);
const maintenances = computed(() => selectedAsset.value?.maintenances ?? []);
const loans = computed(() => selectedAsset.value?.loans ?? []);
const depreciations = computed(() => selectedAsset.value?.depreciations ?? []);
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
function nullable(value) { return value.trim() ? value.trim() : null; }
function money(value) { return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value ?? 0)); }
function dateTime(value) { return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—"; }
async function load() {
    loading.value = true;
    try {
        const [locationResult, assetResult, peopleResult, productResult, supplierResult] = await Promise.all([
            request("/asset-locations?limit=300"), request("/assets?limit=300"), request("/people?limit=300"), request("/products?limit=300"), request("/suppliers?limit=300"),
        ]);
        locations.value = locationResult.items ?? [];
        assets.value = assetResult.items ?? [];
        people.value = peopleResult.items ?? [];
        products.value = productResult.items ?? [];
        suppliers.value = supplierResult.items ?? [];
        if (!assetForm.location_id && locations.value[0])
            assetForm.location_id = locations.value[0].id;
        if (!transferForm.location_id && locations.value[0])
            transferForm.location_id = locations.value[0].id;
        if (!assetForm.product_id && products.value[0])
            assetForm.product_id = products.value[0].id;
        if (!assetForm.responsible_person_id && people.value[0])
            assetForm.responsible_person_id = people.value[0].id;
        if (!loanForm.borrower_person_id && people.value[0])
            loanForm.borrower_person_id = people.value[0].id;
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        loading.value = false;
    }
}
async function createLocation() {
    try {
        await post("/asset-locations", { code: locationForm.code, name: locationForm.name, parent_id: nullable(locationForm.parent_id) }, idempotency("asset-location"));
        Object.assign(locationForm, { code: "", name: "", parent_id: "" });
        emit("notice", "Localização patrimonial cadastrada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createAsset() {
    try {
        const created = await post("/assets", { tag: assetForm.tag, name: assetForm.name, location_id: assetForm.location_id, product_id: nullable(assetForm.product_id), receipt_item_id: nullable(assetForm.receipt_item_id), description: nullable(assetForm.description), serial_number: nullable(assetForm.serial_number), responsible_person_id: nullable(assetForm.responsible_person_id), acquisition_date: assetForm.acquisition_date, acquisition_cost: assetForm.acquisition_cost, useful_life_months: assetForm.useful_life_months || null, residual_value: assetForm.residual_value, warranty_until: nullable(assetForm.warranty_until), metadata: {} }, idempotency("asset"));
        Object.assign(assetForm, { tag: "", name: "", location_id: assetForm.location_id, product_id: assetForm.product_id, receipt_item_id: "", description: "", serial_number: "", responsible_person_id: assetForm.responsible_person_id, acquisition_date: today, acquisition_cost: "0", useful_life_months: 60, residual_value: "0", warranty_until: "" });
        emit("notice", "Bem patrimonial incorporado.");
        await load();
        await showAsset(created);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showAsset(row) {
    try {
        selectedAsset.value = await request(`/assets/${row.id}`);
        transferForm.location_id = selectedAsset.value.location_id ?? locations.value[0]?.id ?? "";
        transferForm.responsible_person_id = selectedAsset.value.responsible_person_id ?? "";
        selectedMaintenance.value = maintenances.value.find((item) => ["scheduled", "in_progress"].includes(item.status)) ?? null;
        selectedLoan.value = loans.value.find((item) => item.status === "active") ?? null;
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function transferAsset() {
    if (!selectedAsset.value)
        return;
    try {
        selectedAsset.value = await post(`/assets/${selectedAsset.value.id}/transfers`, { ...transferForm, responsible_person_id: nullable(transferForm.responsible_person_id) });
        emit("notice", "Transferência patrimonial registrada.");
        await load();
        await showAsset(selectedAsset.value.asset ?? selectedAsset.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createMaintenance() {
    if (!selectedAsset.value)
        return;
    try {
        selectedMaintenance.value = await post(`/assets/${selectedAsset.value.id}/maintenances`, { ...maintenanceForm, scheduled_on: nullable(maintenanceForm.scheduled_on), supplier_id: nullable(maintenanceForm.supplier_id) }, idempotency("asset-maintenance"));
        emit("notice", "Manutenção agendada.");
        await load();
        await showAsset(selectedAsset.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function startMaintenance(row) {
    try {
        await post(`/asset-maintenances/${row.id}/start`, {});
        emit("notice", "Manutenção iniciada.");
        if (selectedAsset.value)
            await showAsset(selectedAsset.value);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function completeMaintenance(row) {
    try {
        await post(`/asset-maintenances/${row.id}/complete`, { result_notes: maintenanceCompleteForm.result_notes, actual_cost: maintenanceCompleteForm.actual_cost || null });
        emit("notice", "Manutenção concluída.");
        if (selectedAsset.value)
            await showAsset(selectedAsset.value);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createLoan() {
    if (!selectedAsset.value)
        return;
    try {
        selectedLoan.value = await post(`/assets/${selectedAsset.value.id}/loans`, { borrower_person_id: loanForm.borrower_person_id, expected_return_at: loanForm.expected_return_at ? new Date(loanForm.expected_return_at).toISOString() : null, condition_out: nullable(loanForm.condition_out) }, idempotency("asset-loan"));
        emit("notice", "Empréstimo patrimonial registrado.");
        await load();
        await showAsset(selectedAsset.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function returnLoan(row) {
    try {
        await post(`/asset-loans/${row.id}/return`, loanReturnForm);
        emit("notice", "Bem devolvido e conferido.");
        if (selectedAsset.value)
            await showAsset(selectedAsset.value);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function calculateDepreciation() {
    if (!selectedAsset.value)
        return;
    try {
        await post(`/assets/${selectedAsset.value.id}/depreciations`, depreciationForm, idempotency(`asset-depreciation-${depreciationForm.competence}`));
        emit("notice", "Depreciação informativa calculada para a competência.");
        await showAsset(selectedAsset.value);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
onMounted(load);
; /* PartiallyEnd: #3632/scriptSetup.vue */
function __VLS_template() {
    const __VLS_ctx = {};
    let __VLS_components;
    let __VLS_directives;
    ['rows', 'rows', 'rows', 'rows',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("assets-module") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("metrics") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.assets.filter(row => !['disposed', 'written_off'].includes(row.status)).length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.assets.filter(row => row.status === 'loaned').length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.assets.filter(row => row.status === 'maintenance').length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.locations.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.money(__VLS_ctx.assets.reduce((sum, row) => sum + Number(row.acquisition_cost || 0), 0)));
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("grid-2 forms") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createLocation) },
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
    (__VLS_ctx.locationForm.code);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.locationForm.parent_id)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [row] of __VLS_getVForSourceType((__VLS_ctx.locations))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((row.id)),
            value: ((row.id)),
        });
        (row.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.locationForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ class: ("primary") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
        ...{ onSubmit: (__VLS_ctx.createAsset) },
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
    (__VLS_ctx.assetForm.tag);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
    (__VLS_ctx.assetForm.serial_number);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        required: (true),
    });
    (__VLS_ctx.assetForm.name);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.assetForm.location_id)),
        required: (true),
    });
    for (const [row] of __VLS_getVForSourceType((__VLS_ctx.locations))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((row.id)),
            value: ((row.id)),
        });
        (row.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.assetForm.responsible_person_id)),
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
        value: ((__VLS_ctx.assetForm.product_id)),
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
        value: (""),
    });
    for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            key: ((row.id)),
            value: ((row.id)),
        });
        (row.name);
    }
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        placeholder: ("UUID opcional"),
    });
    (__VLS_ctx.assetForm.receipt_item_id);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("date"),
        required: (true),
    });
    (__VLS_ctx.assetForm.acquisition_date);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("0"),
        step: ("0.01"),
        required: (true),
    });
    (__VLS_ctx.assetForm.acquisition_cost);
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("cols") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("1"),
    });
    (__VLS_ctx.assetForm.useful_life_months);
    __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
        type: ("number"),
        min: ("0"),
        step: ("0.01"),
    });
    (__VLS_ctx.assetForm.residual_value);
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
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.assets.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        ...{ class: ("small") },
        disabled: ((__VLS_ctx.loading)),
    });
    (__VLS_ctx.loading ? 'Atualizando…' : 'Atualizar');
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
    for (const [row] of __VLS_getVForSourceType((__VLS_ctx.assets))) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
            key: ((row.id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (row.tag);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (row.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (row.location_name || row.location_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (row.responsible_name || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        (__VLS_ctx.money(row.net_book_value ?? row.acquisition_cost));
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: ("pill") },
            ...{ class: ((row.status === 'active' ? 'ok' : row.status === 'maintenance' ? 'warn' : '')) },
        });
        (row.status);
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    __VLS_ctx.showAsset(row);
                } },
            ...{ class: ("small") },
        });
    }
    if (!__VLS_ctx.assets.length) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
            colspan: ("7"),
            ...{ class: ("empty") },
        });
    }
    if (__VLS_ctx.selectedAsset) {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        (__VLS_ctx.selectedAsset.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.selectedAsset.tag);
        (__VLS_ctx.selectedAsset.serial_number || 'sem série');
        (__VLS_ctx.selectedAsset.status);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!((__VLS_ctx.selectedAsset)))
                        return;
                    __VLS_ctx.selectedAsset = null;
                } },
            ...{ class: ("small") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("metrics") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.money(__VLS_ctx.selectedAsset.acquisition_cost));
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        (__VLS_ctx.selectedAsset.acquisition_date);
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.money(__VLS_ctx.selectedAsset.accumulated_depreciation));
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.money(__VLS_ctx.selectedAsset.net_book_value));
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
        (__VLS_ctx.selectedAsset.warranty_until || '—');
        __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.transferAsset) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.transferForm.location_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.locations))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.transferForm.responsible_person_id)),
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.transferForm.reason)),
            rows: ("3"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.calculateDepreciation) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("month"),
            required: (true),
        });
        (__VLS_ctx.depreciationForm.competence);
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createLoan) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.loanForm.borrower_person_id)),
            required: (true),
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
            type: ("datetime-local"),
        });
        (__VLS_ctx.loanForm.expected_return_at);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.loanForm.condition_out)),
            rows: ("3"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((!!__VLS_ctx.selectedLoan)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createMaintenance) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.maintenanceForm.maintenance_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("preventive"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("corrective"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("inspection"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.maintenanceForm.scheduled_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.maintenanceForm.supplier_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.suppliers))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.trade_name || row.legal_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.maintenanceForm.estimated_cost);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.maintenanceForm.description);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((!!__VLS_ctx.selectedLoan)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.loans.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.loans))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (row.borrower_name || row.borrower_person_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.status);
            (__VLS_ctx.dateTime(row.expected_return_at));
            if (row.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedAsset)))
                                return;
                            if (!((row.status === 'active')))
                                return;
                            __VLS_ctx.returnLoan(row);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.loans.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.maintenances.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("rows") },
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.maintenances))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (row.maintenance_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.status);
            (row.scheduled_on || 'sem data');
            (__VLS_ctx.money(row.actual_cost ?? row.estimated_cost));
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            if (row.status === 'scheduled') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedAsset)))
                                return;
                            if (!((row.status === 'scheduled')))
                                return;
                            __VLS_ctx.startMaintenance(row);
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'in_progress') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!((__VLS_ctx.selectedAsset)))
                                return;
                            if (!((row.status === 'in_progress')))
                                return;
                            __VLS_ctx.completeMaintenance(row);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
        if (!__VLS_ctx.maintenances.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("empty") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.movements.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.movements))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.movement_type || row.event_type);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.from_location_name || row.from_location_id || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.to_location_name || row.to_location_id || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.responsible_name || row.responsible_person_id || '—');
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.dateTime(row.created_at || row.occurred_at));
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.depreciations.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.depreciations))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.competence);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.accumulated_amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.net_book_value));
        }
    }
    ['assets-module', 'metrics', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'cols', 'cols', 'cols', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'small', 'pill', 'small', 'empty', 'panel', 'panel-title', 'small', 'metrics', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'primary', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'cols', 'cols', 'primary', 'grid-2', 'panel', 'panel-title', 'rows', 'small', 'empty', 'panel', 'panel-title', 'rows', 'small', 'small', 'empty', 'grid-2', 'panel', 'panel-title', 'panel', 'panel-title',];
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
            locations: locations,
            assets: assets,
            people: people,
            products: products,
            suppliers: suppliers,
            selectedAsset: selectedAsset,
            selectedLoan: selectedLoan,
            locationForm: locationForm,
            assetForm: assetForm,
            transferForm: transferForm,
            maintenanceForm: maintenanceForm,
            loanForm: loanForm,
            depreciationForm: depreciationForm,
            movements: movements,
            maintenances: maintenances,
            loans: loans,
            depreciations: depreciations,
            money: money,
            dateTime: dateTime,
            load: load,
            createLocation: createLocation,
            createAsset: createAsset,
            showAsset: showAsset,
            transferAsset: transferAsset,
            createMaintenance: createMaintenance,
            startMaintenance: startMaintenance,
            completeMaintenance: completeMaintenance,
            createLoan: createLoan,
            returnLoan: returnLoan,
            calculateDepreciation: calculateDepreciation,
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
