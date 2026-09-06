import { computed, onMounted, reactive, ref } from "vue";
const props = defineProps();
const emit = defineEmits();
const loading = ref(false);
const tab = ref("suppliers");
const suppliers = ref([]);
const products = ref([]);
const requisitions = ref([]);
const quotations = ref([]);
const orders = ref([]);
const lots = ref([]);
const reservations = ref([]);
const reorderPolicies = ref([]);
const purchaseSuggestions = ref([]);
const selectedRequisition = ref(null);
const selectedQuotation = ref(null);
const selectedOrder = ref(null);
const activeCount = ref(null);
const editingPolicy = ref(null);
const selectedSuggestion = ref(null);
const today = new Date().toISOString().slice(0, 10);
const supplierForm = reactive({
    code: "",
    legal_name: "",
    trade_name: "",
    cnpj: "",
    email: "",
    phone: "",
    rating: "",
    contact_name: "",
    contact_email: "",
});
const productForm = reactive({
    sku: "",
    barcode: "",
    name: "",
    school_catalog_category: "general",
    cost: "0",
    sale_price: "0",
});
const variantForm = reactive({
    product_id: "",
    sku: "",
    name: "",
    sale_price: "",
    cost_price: "",
});
const barcodeForm = reactive({
    product_id: "",
    variant_id: "",
    barcode: "",
    barcode_type: "ean13",
    primary: true,
});
const requisitionForm = reactive({
    needed_by: today,
    justification: "",
    product_id: "",
    quantity: "1",
    estimated_unit_price: "0",
});
const quotationForm = reactive({
    requisition_id: "",
    response_deadline: "",
    supplier_id: "",
});
const proposalForm = reactive({
    supplier_id: "",
    delivery_days: 5,
    payment_days: "30",
    unit_price: "",
    quantity_available: "",
    brand: "",
    notes: "",
});
const awardForm = reactive({
    supplier_id: "",
    warehouse_id: "default",
    expected_on: today,
    reason: "Melhor combinação de preço, prazo e conformidade.",
    freight_amount: "0",
    discount_amount: "0",
});
const orderForm = reactive({
    supplier_id: "",
    warehouse_id: "default",
    product_id: "",
    quantity: "1",
    unit_price: "0",
    expected_on: today,
    freight_amount: "0",
    discount_amount: "0",
    notes: "",
});
const receiptForm = reactive({
    purchase_order_item_id: "",
    quantity: "1",
    unit_cost: "0",
    supplier_document_number: "",
    lot_number: "",
    manufactured_on: "",
    expires_on: "",
});
const returnForm = reactive({
    purchase_order_item_id: "",
    quantity: "1",
    lot_id: "",
    reason: "Devolução ao fornecedor após conferência.",
});
const reservationForm = reactive({
    product_id: "",
    warehouse_id: "default",
    lot_id: "",
    source_type: "internal_request",
    source_id: "",
    quantity: "1",
    expires_at: "",
});
const countForm = reactive({
    warehouse_id: "default",
    product_id: "",
    include_zero_balance: true,
});
const countLines = reactive({});
const reorderForm = reactive({
    product_id: "",
    warehouse_id: "default",
    minimum_quantity: "1",
    target_quantity: "5",
    lead_time_days: 0,
    preferred_supplier_id: "",
});
const suggestionActionForm = reactive({
    needed_by: today,
    justification: "Reposição automática validada pela administração.",
    reason: "Sugestão descartada após revisão operacional e orçamentária.",
});
const quotationItems = computed(() => selectedQuotation.value?.items ?? []);
const quotationSuppliers = computed(() => selectedQuotation.value?.suppliers ?? []);
const selectedOrderItems = computed(() => selectedOrder.value?.items ?? []);
function message(error) {
    const candidate = error;
    return (candidate.problem?.detail ||
        (error instanceof Error ? error.message : "Erro inesperado"));
}
function idempotency(prefix) {
    return `${prefix}-${crypto.randomUUID()}`;
}
async function request(path, init = {}) {
    return props.api.request(path, init);
}
async function post(path, body, key) {
    const headers = {
        "Content-Type": "application/json",
    };
    if (key)
        headers["Idempotency-Key"] = key;
    return request(path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
    });
}
async function patch(path, body) {
    return request(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
}
function nullable(value) {
    return value.trim() ? value.trim() : null;
}
function money(value) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    }).format(Number(value ?? 0));
}
async function load() {
    loading.value = true;
    try {
        const [supplierResult, productResult, requisitionResult, quotationResult, orderResult, lotResult, reservationResult, reorderResult, suggestionResult,] = await Promise.all([
            request("/suppliers?limit=200"),
            request("/products?limit=300"),
            request("/procurement/requisitions?limit=200"),
            request("/procurement/quotations?limit=200"),
            request("/procurement/orders?limit=200"),
            request("/inventory/lots?limit=300"),
            request("/inventory/reservations?limit=300"),
            request("/inventory/reorder-policies"),
            request("/inventory/purchase-suggestions"),
        ]);
        suppliers.value = supplierResult.items ?? [];
        products.value = productResult.items ?? [];
        requisitions.value = requisitionResult.items ?? [];
        quotations.value = quotationResult.items ?? [];
        orders.value = orderResult.items ?? [];
        lots.value = lotResult.items ?? [];
        reservations.value = reservationResult.items ?? [];
        reorderPolicies.value = reorderResult.items ?? [];
        purchaseSuggestions.value = suggestionResult.items ?? [];
        const firstProduct = products.value[0];
        const firstSupplier = suppliers.value[0];
        if (firstProduct) {
            if (!variantForm.product_id)
                variantForm.product_id = firstProduct.id;
            if (!barcodeForm.product_id)
                barcodeForm.product_id = firstProduct.id;
            if (!requisitionForm.product_id)
                requisitionForm.product_id = firstProduct.id;
            if (!orderForm.product_id)
                orderForm.product_id = firstProduct.id;
            if (!reservationForm.product_id)
                reservationForm.product_id = firstProduct.id;
            if (!countForm.product_id)
                countForm.product_id = firstProduct.id;
            if (!reorderForm.product_id)
                reorderForm.product_id = firstProduct.id;
        }
        if (firstSupplier) {
            if (!quotationForm.supplier_id)
                quotationForm.supplier_id = firstSupplier.id;
            if (!proposalForm.supplier_id)
                proposalForm.supplier_id = firstSupplier.id;
            if (!awardForm.supplier_id)
                awardForm.supplier_id = firstSupplier.id;
            if (!orderForm.supplier_id)
                orderForm.supplier_id = firstSupplier.id;
            if (!reorderForm.preferred_supplier_id)
                reorderForm.preferred_supplier_id = firstSupplier.id;
        }
    }
    catch (error) {
        emit("error", message(error));
    }
    finally {
        loading.value = false;
    }
}
async function createSupplier() {
    try {
        const contacts = supplierForm.contact_name
            ? [
                {
                    name: supplierForm.contact_name,
                    email: nullable(supplierForm.contact_email),
                    role: "commercial",
                    primary: true,
                },
            ]
            : [];
        await post("/suppliers", {
            code: nullable(supplierForm.code),
            legal_name: supplierForm.legal_name,
            trade_name: nullable(supplierForm.trade_name),
            cnpj: nullable(supplierForm.cnpj),
            email: nullable(supplierForm.email),
            phone: nullable(supplierForm.phone),
            rating: nullable(supplierForm.rating),
            contacts,
        }, idempotency("supplier"));
        Object.assign(supplierForm, {
            code: "",
            legal_name: "",
            trade_name: "",
            cnpj: "",
            email: "",
            phone: "",
            rating: "",
            contact_name: "",
            contact_email: "",
        });
        emit("notice", "Fornecedor e contato cadastrados.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createProduct() {
    try {
        await post("/products", {
            sku: productForm.sku,
            barcode: nullable(productForm.barcode),
            name: productForm.name,
            school_catalog_category: productForm.school_catalog_category,
            cost: productForm.cost,
            sale_price: productForm.sale_price,
        });
        Object.assign(productForm, {
            sku: "",
            barcode: "",
            name: "",
            school_catalog_category: "general",
            cost: "0",
            sale_price: "0",
        });
        emit("notice", "Produto escolar cadastrado e disponível para venda e estoque.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function toggleSupplier(row) {
    try {
        await patch(`/suppliers/${row.id}`, {
            status: row.status === "active" ? "inactive" : "active",
            expected_version: row.version,
        });
        emit("notice", "Estado do fornecedor atualizado.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createVariant() {
    try {
        await post("/inventory/product-variants", {
            ...variantForm,
            sale_price: nullable(variantForm.sale_price),
            cost_price: nullable(variantForm.cost_price),
            attributes: {},
        }, idempotency("product-variant"));
        emit("notice", "Variação de produto cadastrada.");
        Object.assign(variantForm, {
            product_id: variantForm.product_id,
            sku: "",
            name: "",
            sale_price: "",
            cost_price: "",
        });
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createBarcode() {
    try {
        await post("/inventory/product-barcodes", { ...barcodeForm, variant_id: nullable(barcodeForm.variant_id) }, idempotency("product-barcode"));
        emit("notice", "Código de barras cadastrado.");
        barcodeForm.barcode = "";
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createRequisition() {
    try {
        await post("/procurement/requisitions", {
            needed_by: nullable(requisitionForm.needed_by),
            justification: requisitionForm.justification,
            items: [
                {
                    product_id: requisitionForm.product_id,
                    quantity: requisitionForm.quantity,
                    estimated_unit_price: requisitionForm.estimated_unit_price,
                },
            ],
        }, idempotency("purchase-requisition"));
        requisitionForm.justification = "";
        emit("notice", "Requisição de compra criada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showRequisition(row) {
    try {
        selectedRequisition.value = await request(`/procurement/requisitions/${row.id}`);
        quotationForm.requisition_id = row.id;
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function requisitionAction(row, action) {
    try {
        const detail = await request(`/procurement/requisitions/${row.id}`);
        const body = action === "approve"
            ? {
                approved_quantities: Object.fromEntries((detail.items ?? []).map((item) => [
                    item.id,
                    item.requested_quantity ?? item.quantity,
                ])),
                reason: "Necessidade e disponibilidade orçamentária validadas.",
            }
            : action === "submit"
                ? {}
                : {
                    reason: `${action === "reject" ? "Rejeição" : "Cancelamento"} registrado pela administração.`,
                };
        await post(`/procurement/requisitions/${row.id}/${action}`, body);
        emit("notice", "Requisição atualizada.");
        await load();
        if (selectedRequisition.value?.requisition?.id === row.id ||
            selectedRequisition.value?.id === row.id)
            await showRequisition(row);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createQuotation() {
    try {
        const created = await post("/procurement/quotations", {
            requisition_id: quotationForm.requisition_id || null,
            response_deadline: quotationForm.response_deadline
                ? new Date(quotationForm.response_deadline).toISOString()
                : null,
            currency: "BRL",
            supplier_ids: [quotationForm.supplier_id],
            items: [],
        }, idempotency("quotation"));
        emit("notice", "Cotação criada e fornecedor convidado.");
        await load();
        await showQuotation(created.quotation ?? created);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showQuotation(row) {
    try {
        selectedQuotation.value = await request(`/procurement/quotations/${row.id}`);
        proposalForm.supplier_id =
            quotationSuppliers.value[0]?.supplier_id ?? proposalForm.supplier_id;
        proposalForm.quantity_available =
            quotationItems.value[0]?.quantity ??
                quotationItems.value[0]?.requested_quantity ??
                "1";
        awardForm.supplier_id = proposalForm.supplier_id;
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function submitProposal() {
    if (!selectedQuotation.value || !quotationItems.value.length)
        return;
    try {
        await post(`/procurement/quotations/${selectedQuotation.value.quotation?.id ?? selectedQuotation.value.id}/suppliers/${proposalForm.supplier_id}/proposal`, {
            delivery_days: proposalForm.delivery_days,
            payment_terms: {
                days: proposalForm.payment_days
                    .split(",")
                    .map((value) => Number(value.trim()))
                    .filter(Number.isFinite),
            },
            notes: nullable(proposalForm.notes),
            items: quotationItems.value.map((item) => ({
                quotation_item_id: item.id,
                unit_price: proposalForm.unit_price,
                quantity_available: proposalForm.quantity_available || item.quantity,
                brand: nullable(proposalForm.brand),
            })),
        }, idempotency("supplier-proposal"));
        emit("notice", "Proposta do fornecedor registrada.");
        await showQuotation(selectedQuotation.value.quotation ?? selectedQuotation.value);
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function awardQuotation() {
    if (!selectedQuotation.value)
        return;
    try {
        const result = await post(`/procurement/quotations/${selectedQuotation.value.quotation?.id ?? selectedQuotation.value.id}/award`, awardForm, idempotency("quotation-award"));
        emit("notice", "Cotação adjudicada e pedido de compra criado.");
        await load();
        await showOrder(result.order ?? result);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createOrder() {
    try {
        const created = await post("/procurement/orders", {
            supplier_id: orderForm.supplier_id,
            warehouse_id: orderForm.warehouse_id,
            expected_on: nullable(orderForm.expected_on),
            freight_amount: orderForm.freight_amount,
            discount_amount: orderForm.discount_amount,
            notes: nullable(orderForm.notes),
            items: [
                {
                    product_id: orderForm.product_id,
                    quantity: orderForm.quantity,
                    unit_price: orderForm.unit_price,
                    discount_amount: "0",
                },
            ],
        }, idempotency("purchase-order"));
        emit("notice", "Pedido de compra criado em rascunho.");
        await load();
        await showOrder(created.order ?? created);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function showOrder(row) {
    try {
        selectedOrder.value = await request(`/procurement/orders/${row.id}`);
        const item = selectedOrderItems.value[0];
        if (item) {
            receiptForm.purchase_order_item_id = item.id;
            receiptForm.unit_cost = String(item.unit_price ?? 0);
            returnForm.purchase_order_item_id = item.id;
        }
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function approveOrder(row) {
    try {
        await post(`/procurement/orders/${row.id}/approve`, {
            reason: "Pedido aprovado pela administração.",
        });
        emit("notice", "Pedido aprovado.");
        await load();
        await showOrder(row);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function receiveOrder() {
    if (!selectedOrder.value)
        return;
    try {
        await post(`/procurement/orders/${selectedOrder.value.order?.id ?? selectedOrder.value.id}/receipts`, {
            supplier_document_number: nullable(receiptForm.supplier_document_number),
            items: [
                {
                    purchase_order_item_id: receiptForm.purchase_order_item_id,
                    quantity: receiptForm.quantity,
                    unit_cost: receiptForm.unit_cost,
                    lot_number: nullable(receiptForm.lot_number),
                    manufactured_on: nullable(receiptForm.manufactured_on),
                    expires_on: nullable(receiptForm.expires_on),
                },
            ],
        }, idempotency("goods-receipt"));
        emit("notice", "Recebimento registrado com estoque e custo médio atualizados.");
        await load();
        await showOrder(selectedOrder.value.order ?? selectedOrder.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function returnOrderItem() {
    if (!selectedOrder.value)
        return;
    try {
        await post(`/procurement/orders/${selectedOrder.value.order?.id ?? selectedOrder.value.id}/returns`, {
            reason: returnForm.reason,
            items: [
                {
                    purchase_order_item_id: returnForm.purchase_order_item_id,
                    quantity: returnForm.quantity,
                    lot_id: nullable(returnForm.lot_id),
                },
            ],
        }, idempotency("purchase-return"));
        emit("notice", "Devolução registrada e estoque compensado.");
        await load();
        await showOrder(selectedOrder.value.order ?? selectedOrder.value);
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createReservation() {
    try {
        await post("/inventory/reservations", {
            ...reservationForm,
            lot_id: nullable(reservationForm.lot_id),
            expires_at: reservationForm.expires_at
                ? new Date(reservationForm.expires_at).toISOString()
                : null,
        }, idempotency("inventory-reservation"));
        emit("notice", "Reserva de estoque registrada.");
        reservationForm.source_id = "";
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function reservationAction(row, action) {
    try {
        await post(`/inventory/reservations/${row.id}/${action}`, {});
        emit("notice", action === "consume"
            ? "Reserva consumida e estoque baixado."
            : "Reserva liberada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function createCount() {
    try {
        activeCount.value = await post("/inventory/counts", {
            warehouse_id: countForm.warehouse_id,
            product_ids: countForm.product_id ? [countForm.product_id] : [],
            include_zero_balance: countForm.include_zero_balance,
        }, idempotency("inventory-count"));
        for (const item of activeCount.value.items ?? [])
            countLines[item.id] = String(item.expected_quantity ?? "0");
        emit("notice", "Inventário aberto para contagem física.");
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function completeCount() {
    if (!activeCount.value)
        return;
    try {
        const countId = activeCount.value.count?.id ?? activeCount.value.id;
        activeCount.value = await post(`/inventory/counts/${countId}/complete`, {
            reason: "Contagem física conferida pela administração.",
            items: (activeCount.value.items ?? []).map((item) => ({
                item_id: item.id,
                counted_quantity: countLines[item.id] ?? item.expected_quantity,
                notes: null,
            })),
        });
        emit("notice", "Inventário concluído e divergências ajustadas.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
function clearPolicyEditor() {
    editingPolicy.value = null;
    Object.assign(reorderForm, {
        product_id: products.value[0]?.id ?? "",
        warehouse_id: "default",
        minimum_quantity: "1",
        target_quantity: "5",
        lead_time_days: 0,
        preferred_supplier_id: suppliers.value[0]?.id ?? "",
    });
}
function editReorderPolicy(row) {
    editingPolicy.value = row;
    Object.assign(reorderForm, {
        product_id: row.product_id,
        warehouse_id: row.warehouse_id ?? row.warehouse ?? "default",
        minimum_quantity: String(row.minimum_quantity),
        target_quantity: String(row.target_quantity),
        lead_time_days: Number(row.lead_time_days ?? 0),
        preferred_supplier_id: row.preferred_supplier_id ?? "",
    });
}
async function saveReorderPolicy() {
    try {
        const body = {
            minimum_quantity: reorderForm.minimum_quantity,
            target_quantity: reorderForm.target_quantity,
            lead_time_days: reorderForm.lead_time_days,
            preferred_supplier_id: nullable(reorderForm.preferred_supplier_id),
        };
        if (editingPolicy.value) {
            await patch(`/inventory/reorder-policies/${editingPolicy.value.id}`, {
                ...body,
                expected_version: editingPolicy.value.version,
            });
            emit("notice", "Política de estoque mínimo atualizada.");
        }
        else {
            await post("/inventory/reorder-policies", {
                product_id: reorderForm.product_id,
                warehouse_id: reorderForm.warehouse_id,
                ...body,
            }, idempotency("reorder-policy"));
            emit("notice", "Política de estoque mínimo cadastrada.");
        }
        clearPolicyEditor();
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function toggleReorderPolicy(row) {
    try {
        await patch(`/inventory/reorder-policies/${row.id}`, {
            state: row.status === "active" ? "inactive" : "active",
            expected_version: row.version,
        });
        emit("notice", row.status === "active"
            ? "Política inativada e sugestões abertas encerradas."
            : "Política reativada.");
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function generatePurchaseSuggestions() {
    try {
        const result = await post("/inventory/purchase-suggestions/generate", {}, idempotency("purchase-suggestions"));
        const summary = result.summary ?? {};
        emit("notice", `Sugestões processadas: ${summary.created ?? 0} novas, ${summary.refreshed ?? 0} atualizadas e ${summary.superseded ?? 0} encerradas.`);
        selectedSuggestion.value = null;
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
function selectSuggestion(row) {
    selectedSuggestion.value = row;
    suggestionActionForm.needed_by = today;
    suggestionActionForm.justification = `Reposição automática de ${row.product_name} validada pela administração.`;
    suggestionActionForm.reason =
        "Sugestão descartada após revisão operacional e orçamentária.";
}
async function convertSelectedSuggestion() {
    if (!selectedSuggestion.value)
        return;
    try {
        const result = await post(`/inventory/purchase-suggestions/${selectedSuggestion.value.id}/convert`, {
            expected_version: selectedSuggestion.value.version,
            needed_by: nullable(suggestionActionForm.needed_by),
            justification: suggestionActionForm.justification,
        }, idempotency("purchase-suggestion-convert"));
        emit("notice", `Sugestão convertida na requisição ${result.requisition?.requisition_number ?? result.requisition?.id}.`);
        selectedSuggestion.value = null;
        await load();
    }
    catch (error) {
        emit("error", message(error));
    }
}
async function dismissSelectedSuggestion() {
    if (!selectedSuggestion.value)
        return;
    try {
        await post(`/inventory/purchase-suggestions/${selectedSuggestion.value.id}/dismiss`, {
            expected_version: selectedSuggestion.value.version,
            reason: suggestionActionForm.reason,
        }, idempotency("purchase-suggestion-dismiss"));
        emit("notice", "Sugestão descartada com justificativa e trilha de auditoria.");
        selectedSuggestion.value = null;
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
    ['procurement-tabs', 'procurement-tabs', 'procurement-tabs', 'rows', 'rows', 'rows', 'procurement-tabs', 'refresh', 'rows',];
    // CSS variable injection 
    // CSS variable injection end 
    __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: ("procurement-module") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("metrics") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.suppliers.filter((row) => row.status === "active").length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.requisitions.filter((row) => !["cancelled", "rejected", "converted"].includes(row.status)).length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.quotations.length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.orders.filter((row) => !["received", "cancelled"].includes(row.status)).length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.lots.filter((row) => Number(row.quantity) > 0).length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.article, __VLS_intrinsicElements.article)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
    (__VLS_ctx.purchaseSuggestions.filter((row) => row.status === "open").length);
    __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
    __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
        ...{ class: ("procurement-tabs") },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'suppliers';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'suppliers' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'requisitions';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'requisitions' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'quotations';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'quotations' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'orders';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'orders' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'inventory';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'inventory' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.tab = 'reorder';
            } },
        ...{ class: (({ selected: __VLS_ctx.tab === 'reorder' })) },
    });
    __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.load) },
        ...{ class: ("small refresh") },
        disabled: ((__VLS_ctx.loading)),
    });
    (__VLS_ctx.loading ? "Atualizando…" : "Atualizar");
    if (__VLS_ctx.tab === 'suppliers') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createSupplier) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.supplierForm.code);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            inputmode: ("numeric"),
        });
        (__VLS_ctx.supplierForm.cnpj);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.supplierForm.legal_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.supplierForm.trade_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("email"),
        });
        (__VLS_ctx.supplierForm.email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.supplierForm.phone);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.supplierForm.contact_name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("email"),
        });
        (__VLS_ctx.supplierForm.contact_email);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.ul, __VLS_intrinsicElements.ul)({
            ...{ class: ("checklist") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createProduct) },
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
        (__VLS_ctx.productForm.sku);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.productForm.barcode);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.productForm.name);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.productForm.school_catalog_category)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("general"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("school_uniform"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("textbook"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("handout"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("learning_module"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("educational_material"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("school_kit"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("event_ticket"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("event"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
            required: (true),
        });
        (__VLS_ctx.productForm.cost);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
            required: (true),
        });
        (__VLS_ctx.productForm.sale_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createVariant) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.variantForm.product_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
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
        (__VLS_ctx.variantForm.sku);
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
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.variantForm.cost_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.variantForm.sale_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createBarcode) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.barcodeForm.product_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
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
        (__VLS_ctx.barcodeForm.barcode);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.barcodeForm.barcode_type)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("ean13"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("ean8"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("code128"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: ("internal"),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.barcodeForm.primary);
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
        (__VLS_ctx.suppliers.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.suppliers))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.code || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.trade_name || row.legal_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.cnpj || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.email || row.contacts?.[0]?.email || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.rating ?? "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!((__VLS_ctx.tab === 'suppliers')))
                            return;
                        __VLS_ctx.toggleSupplier(row);
                    } },
                ...{ class: ("small") },
            });
            (row.status === "active" ? "Inativar" : "Ativar");
        }
        if (!__VLS_ctx.suppliers.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("7"),
                ...{ class: ("empty") },
            });
        }
    }
    else if (__VLS_ctx.tab === 'requisitions') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createRequisition) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.requisitionForm.product_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
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
            type: ("number"),
            min: ("0.0001"),
            step: ("0.0001"),
            required: (true),
        });
        (__VLS_ctx.requisitionForm.quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
        });
        (__VLS_ctx.requisitionForm.estimated_unit_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.requisitionForm.needed_by);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
            value: ((__VLS_ctx.requisitionForm.justification)),
            rows: ("4"),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        if (__VLS_ctx.selectedRequisition) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedRequisition.requisition?.number ||
                __VLS_ctx.selectedRequisition.number);
            (__VLS_ctx.selectedRequisition.requisition?.status ||
                __VLS_ctx.selectedRequisition.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows") },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.selectedRequisition.items || []))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((item.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (item.product_name || item.product_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (item.requested_quantity || item.quantity);
                (item.approved_quantity || 0);
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.requisitions.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.requisitions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.needed_by || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.justification);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.estimated_total));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'suppliers'))))
                            return;
                        if (!((__VLS_ctx.tab === 'requisitions')))
                            return;
                        __VLS_ctx.showRequisition(row);
                    } },
                ...{ class: ("small") },
            });
            if (row.status === 'draft') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!((__VLS_ctx.tab === 'requisitions')))
                                return;
                            if (!((row.status === 'draft')))
                                return;
                            __VLS_ctx.requisitionAction(row, 'submit');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'submitted') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!((__VLS_ctx.tab === 'requisitions')))
                                return;
                            if (!((row.status === 'submitted')))
                                return;
                            __VLS_ctx.requisitionAction(row, 'approve');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'submitted') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!((__VLS_ctx.tab === 'requisitions')))
                                return;
                            if (!((row.status === 'submitted')))
                                return;
                            __VLS_ctx.requisitionAction(row, 'reject');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (!['cancelled', 'rejected', 'converted'].includes(row.status)) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!((__VLS_ctx.tab === 'requisitions')))
                                return;
                            if (!((!['cancelled', 'rejected', 'converted'].includes(row.status))))
                                return;
                            __VLS_ctx.requisitionAction(row, 'cancel');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    else if (__VLS_ctx.tab === 'quotations') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createQuotation) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.quotationForm.requisition_id)),
            required: (true),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.requisitions.filter((item) => item.status === 'approved')))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.number);
            (row.justification);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.quotationForm.supplier_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.suppliers.filter((item) => item.status === 'active')))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.trade_name || row.legal_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("datetime-local"),
        });
        (__VLS_ctx.quotationForm.response_deadline);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.submitProposal) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.proposalForm.supplier_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.quotationSuppliers))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.supplier_id)),
                value: ((row.supplier_id)),
            });
            (row.supplier_name || row.supplier_id);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
            required: (true),
        });
        (__VLS_ctx.proposalForm.unit_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.0001"),
            step: ("0.0001"),
            required: (true),
        });
        (__VLS_ctx.proposalForm.quantity_available);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
        });
        (__VLS_ctx.proposalForm.delivery_days);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            placeholder: ("30,60"),
        });
        (__VLS_ctx.proposalForm.payment_days);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
        (__VLS_ctx.proposalForm.brand);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
            disabled: ((!__VLS_ctx.selectedQuotation)),
        });
        if (__VLS_ctx.selectedQuotation) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows") },
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.quotationItems))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((row.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (row.product_name || row.product_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (row.quantity);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.awardQuotation) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.awardForm.supplier_id)),
                required: (true),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.quotationSuppliers.filter((item) => item.status === 'responded')))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.supplier_id)),
                    value: ((row.supplier_id)),
                });
                (row.supplier_name || row.supplier_id);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                required: (true),
            });
            (__VLS_ctx.awardForm.warehouse_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
            });
            (__VLS_ctx.awardForm.expected_on);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0"),
                step: ("0.01"),
            });
            (__VLS_ctx.awardForm.freight_amount);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0"),
                step: ("0.01"),
            });
            (__VLS_ctx.awardForm.discount_amount);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.awardForm.reason)),
                rows: ("3"),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.quotations.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.quotations))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.requisition_number || row.requisition_id || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.response_deadline || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.supplier_count ?? row.suppliers?.length ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'suppliers'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'requisitions'))))
                            return;
                        if (!((__VLS_ctx.tab === 'quotations')))
                            return;
                        __VLS_ctx.showQuotation(row);
                    } },
                ...{ class: ("small") },
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
            value: ((__VLS_ctx.orderForm.supplier_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.suppliers.filter((item) => item.status === 'active')))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.trade_name || row.legal_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.orderForm.product_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
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
            type: ("number"),
            min: ("0.0001"),
            step: ("0.0001"),
            required: (true),
        });
        (__VLS_ctx.orderForm.quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            step: ("0.01"),
            required: (true),
        });
        (__VLS_ctx.orderForm.unit_price);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.orderForm.warehouse_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("date"),
        });
        (__VLS_ctx.orderForm.expected_on);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        if (__VLS_ctx.selectedOrder) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            (__VLS_ctx.selectedOrder.order?.number || __VLS_ctx.selectedOrder.number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedOrder.order?.status || __VLS_ctx.selectedOrder.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows") },
            });
            for (const [item] of __VLS_getVForSourceType((__VLS_ctx.selectedOrderItems))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: ((item.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
                (item.product_name || item.product_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
                (item.quantity);
                (item.received_quantity || 0);
                (item.returned_quantity || 0);
            }
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        }
        if (__VLS_ctx.selectedOrder) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("grid-2 forms") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.receiveOrder) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.receiptForm.purchase_order_item_id)),
                required: (true),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.selectedOrderItems))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.id)),
                    value: ((row.id)),
                });
                (row.product_name || row.product_id);
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
            (__VLS_ctx.receiptForm.quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("number"),
                min: ("0"),
                step: ("0.0001"),
                required: (true),
            });
            (__VLS_ctx.receiptForm.unit_cost);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.receiptForm.supplier_document_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("cols") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({});
            (__VLS_ctx.receiptForm.lot_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
            });
            (__VLS_ctx.receiptForm.expires_on);
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.returnOrderItem) },
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.returnForm.purchase_order_item_id)),
                required: (true),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.selectedOrderItems))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.id)),
                    value: ((row.id)),
                });
                (row.product_name || row.product_id);
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
            (__VLS_ctx.returnForm.quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
                value: ((__VLS_ctx.returnForm.lot_id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                value: (""),
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.lots))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                    key: ((row.id)),
                    value: ((row.id)),
                });
                (row.lot_number);
                (row.product_name);
            }
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.returnForm.reason)),
                rows: ("3"),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
        }
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.orders))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.supplier_name || row.supplier_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.total_amount));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.received_percentage ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'suppliers'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'requisitions'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'quotations'))))
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
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'requisitions'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'quotations'))))
                                return;
                            if (!((__VLS_ctx.tab === 'orders')))
                                return;
                            if (!((row.status === 'draft')))
                                return;
                            __VLS_ctx.approveOrder(row);
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    else if (__VLS_ctx.tab === 'inventory') {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createReservation) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.reservationForm.product_id)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.reservationForm.lot_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.lots.filter((item) => item.product_id === __VLS_ctx.reservationForm.product_id)))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.lot_number);
            (row.quantity);
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
        (__VLS_ctx.reservationForm.quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.reservationForm.warehouse_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.reservationForm.source_type);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.reservationForm.source_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.createCount) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            required: (true),
        });
        (__VLS_ctx.countForm.warehouse_id);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.countForm.product_id)),
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
            ...{ class: ("inline") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("checkbox"),
        });
        (__VLS_ctx.countForm.include_zero_balance);
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        if (__VLS_ctx.activeCount) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel-title") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.activeCount.count?.number || __VLS_ctx.activeCount.number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.activeCount.items || []))) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                    key: ((row.id)),
                });
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.product_name || row.product_id);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                (row.expected_quantity);
                __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
                __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                    type: ("number"),
                    min: ("0"),
                    step: ("0.0001"),
                });
                (__VLS_ctx.countLines[row.id]);
            }
            if ((__VLS_ctx.activeCount.count?.status || __VLS_ctx.activeCount.status) !== 'completed') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (__VLS_ctx.completeCount) },
                    ...{ class: ("primary") },
                });
            }
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
        (__VLS_ctx.lots.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.lots))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.product_name || row.product_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.lot_number);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.expires_on || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.quantity);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.reservations.length);
        __VLS_elementAsFunction(__VLS_intrinsicElements.table, __VLS_intrinsicElements.table)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.thead, __VLS_intrinsicElements.thead)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.reservations))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.product_name || row.product_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.source_type);
            (row.source_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'requisitions'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'quotations'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'orders'))))
                                return;
                            if (!((__VLS_ctx.tab === 'inventory')))
                                return;
                            if (!((row.status === 'active')))
                                return;
                            __VLS_ctx.reservationAction(row, 'consume');
                        } },
                    ...{ class: ("small") },
                });
            }
            if (row.status === 'active') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'requisitions'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'quotations'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'orders'))))
                                return;
                            if (!((__VLS_ctx.tab === 'inventory')))
                                return;
                            if (!((row.status === 'active')))
                                return;
                            __VLS_ctx.reservationAction(row, 'release');
                        } },
                    ...{ class: ("small") },
                });
            }
        }
    }
    else {
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("grid-2 forms") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
            ...{ onSubmit: (__VLS_ctx.saveReorderPolicy) },
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        (__VLS_ctx.editingPolicy
            ? "Editar política"
            : "Nova política de estoque mínimo");
        if (__VLS_ctx.editingPolicy) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            (__VLS_ctx.editingPolicy.version);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.reorderForm.product_id)),
            disabled: ((!!__VLS_ctx.editingPolicy)),
            required: (true),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.products))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.name);
            (row.sku);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            disabled: ((!!__VLS_ctx.editingPolicy)),
            required: (true),
        });
        (__VLS_ctx.reorderForm.warehouse_id);
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
        (__VLS_ctx.reorderForm.minimum_quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0.0001"),
            step: ("0.0001"),
            required: (true),
        });
        (__VLS_ctx.reorderForm.target_quantity);
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("cols") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
            type: ("number"),
            min: ("0"),
            max: ("3650"),
        });
        (__VLS_ctx.reorderForm.lead_time_days);
        __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.select, __VLS_intrinsicElements.select)({
            value: ((__VLS_ctx.reorderForm.preferred_supplier_id)),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
            value: (""),
        });
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.suppliers.filter((item) => item.status === 'active')))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.option, __VLS_intrinsicElements.option)({
                key: ((row.id)),
                value: ((row.id)),
            });
            (row.trade_name || row.legal_name);
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("actions") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ class: ("primary") },
        });
        (__VLS_ctx.editingPolicy ? "Salvar alterações" : "Cadastrar política");
        if (__VLS_ctx.editingPolicy) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (__VLS_ctx.clearPolicyEditor) },
                type: ("button"),
                ...{ class: ("small") },
            });
        }
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.ul, __VLS_intrinsicElements.ul)({
            ...{ class: ("checklist") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.li, __VLS_intrinsicElements.li)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (__VLS_ctx.generatePurchaseSuggestions) },
            ...{ class: ("primary") },
            disabled: ((__VLS_ctx.loading ||
                !__VLS_ctx.reorderPolicies.some((row) => row.status === 'active'))),
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.section, __VLS_intrinsicElements.section)({
            ...{ class: ("panel") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: ("panel-title") },
        });
        __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.reorderPolicies.length);
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
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.th, __VLS_intrinsicElements.th)({});
        __VLS_elementAsFunction(__VLS_intrinsicElements.tbody, __VLS_intrinsicElements.tbody)({});
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.reorderPolicies))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (row.product_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.product_sku);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.warehouse_id || row.warehouse);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.stock?.available_quantity ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.stock?.open_purchase_quantity ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.stock?.projected_quantity ?? 0);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.minimum_quantity);
            (row.target_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.preferred_supplier_name || "—");
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'suppliers'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'requisitions'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'quotations'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'orders'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'inventory'))))
                            return;
                        __VLS_ctx.editReorderPolicy(row);
                    } },
                ...{ class: ("small") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(!((__VLS_ctx.tab === 'suppliers'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'requisitions'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'quotations'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'orders'))))
                            return;
                        if (!(!((__VLS_ctx.tab === 'inventory'))))
                            return;
                        __VLS_ctx.toggleReorderPolicy(row);
                    } },
                ...{ class: ("small") },
            });
            (row.status === "active" ? "Inativar" : "Ativar");
        }
        if (!__VLS_ctx.reorderPolicies.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("9"),
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
        (__VLS_ctx.purchaseSuggestions.length);
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
        for (const [row] of __VLS_getVForSourceType((__VLS_ctx.purchaseSuggestions))) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({
                key: ((row.id)),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (row.product_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            (row.warehouse_id);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.available_quantity);
            (row.open_purchase_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.suggested_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (__VLS_ctx.money(row.estimated_total));
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            (row.status);
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({});
            if (row.status === 'open') {
                __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(!((__VLS_ctx.tab === 'suppliers'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'requisitions'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'quotations'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'orders'))))
                                return;
                            if (!(!((__VLS_ctx.tab === 'inventory'))))
                                return;
                            if (!((row.status === 'open')))
                                return;
                            __VLS_ctx.selectSuggestion(row);
                        } },
                    ...{ class: ("small") },
                });
            }
            else if (row.requisition_id) {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (row.requisition_id.slice(-8));
            }
            else {
                __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (row.closure_reason || "—");
            }
        }
        if (!__VLS_ctx.purchaseSuggestions.length) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.tr, __VLS_intrinsicElements.tr)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.td, __VLS_intrinsicElements.td)({
                colspan: ("6"),
                ...{ class: ("empty") },
            });
        }
        if (__VLS_ctx.selectedSuggestion) {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedSuggestion.product_name);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("rows") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedSuggestion.projected_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedSuggestion.minimum_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.small, __VLS_intrinsicElements.small)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.strong, __VLS_intrinsicElements.strong)({});
            (__VLS_ctx.selectedSuggestion.suggested_quantity);
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.convertSelectedSuggestion) },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.input)({
                type: ("date"),
            });
            (__VLS_ctx.suggestionActionForm.needed_by);
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.suggestionActionForm.justification)),
                rows: ("3"),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("primary") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.form, __VLS_intrinsicElements.form)({
                ...{ onSubmit: (__VLS_ctx.dismissSelectedSuggestion) },
                ...{ class: ("dismiss-form") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.textarea, __VLS_intrinsicElements.textarea)({
                value: ((__VLS_ctx.suggestionActionForm.reason)),
                rows: ("3"),
                required: (true),
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ class: ("small") },
            });
        }
        else {
            __VLS_elementAsFunction(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: ("panel") },
            });
            __VLS_elementAsFunction(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({});
            __VLS_elementAsFunction(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({});
        }
    }
    ['procurement-module', 'metrics', 'procurement-tabs', 'selected', 'selected', 'selected', 'selected', 'selected', 'selected', 'small', 'refresh', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'cols', 'primary', 'panel', 'checklist', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'inline', 'primary', 'panel', 'panel-title', 'small', 'empty', 'grid-2', 'forms', 'panel', 'cols', 'primary', 'panel', 'rows', 'panel', 'panel', 'panel-title', 'small', 'small', 'small', 'small', 'small', 'grid-2', 'forms', 'panel', 'primary', 'panel', 'cols', 'cols', 'primary', 'grid-2', 'forms', 'panel', 'rows', 'panel', 'cols', 'cols', 'primary', 'panel', 'panel-title', 'small', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'rows', 'panel', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'cols', 'primary', 'panel', 'panel-title', 'small', 'small', 'grid-2', 'forms', 'panel', 'cols', 'cols', 'primary', 'panel', 'inline', 'primary', 'panel', 'panel-title', 'primary', 'grid-2', 'panel', 'panel-title', 'panel', 'panel-title', 'small', 'small', 'grid-2', 'forms', 'panel', 'panel-title', 'cols', 'cols', 'actions', 'primary', 'small', 'panel', 'checklist', 'primary', 'panel', 'panel-title', 'small', 'small', 'empty', 'grid-2', 'panel', 'panel-title', 'small', 'empty', 'panel', 'rows', 'primary', 'dismiss-form', 'small', 'panel',];
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
            suppliers: suppliers,
            products: products,
            requisitions: requisitions,
            quotations: quotations,
            orders: orders,
            lots: lots,
            reservations: reservations,
            reorderPolicies: reorderPolicies,
            purchaseSuggestions: purchaseSuggestions,
            selectedRequisition: selectedRequisition,
            selectedQuotation: selectedQuotation,
            selectedOrder: selectedOrder,
            activeCount: activeCount,
            editingPolicy: editingPolicy,
            selectedSuggestion: selectedSuggestion,
            supplierForm: supplierForm,
            productForm: productForm,
            variantForm: variantForm,
            barcodeForm: barcodeForm,
            requisitionForm: requisitionForm,
            quotationForm: quotationForm,
            proposalForm: proposalForm,
            awardForm: awardForm,
            orderForm: orderForm,
            receiptForm: receiptForm,
            returnForm: returnForm,
            reservationForm: reservationForm,
            countForm: countForm,
            countLines: countLines,
            reorderForm: reorderForm,
            suggestionActionForm: suggestionActionForm,
            quotationItems: quotationItems,
            quotationSuppliers: quotationSuppliers,
            selectedOrderItems: selectedOrderItems,
            money: money,
            load: load,
            createSupplier: createSupplier,
            createProduct: createProduct,
            toggleSupplier: toggleSupplier,
            createVariant: createVariant,
            createBarcode: createBarcode,
            createRequisition: createRequisition,
            showRequisition: showRequisition,
            requisitionAction: requisitionAction,
            createQuotation: createQuotation,
            showQuotation: showQuotation,
            submitProposal: submitProposal,
            awardQuotation: awardQuotation,
            createOrder: createOrder,
            showOrder: showOrder,
            approveOrder: approveOrder,
            receiveOrder: receiveOrder,
            returnOrderItem: returnOrderItem,
            createReservation: createReservation,
            reservationAction: reservationAction,
            createCount: createCount,
            completeCount: completeCount,
            clearPolicyEditor: clearPolicyEditor,
            editReorderPolicy: editReorderPolicy,
            saveReorderPolicy: saveReorderPolicy,
            toggleReorderPolicy: toggleReorderPolicy,
            generatePurchaseSuggestions: generatePurchaseSuggestions,
            selectSuggestion: selectSuggestion,
            convertSelectedSuggestion: convertSelectedSuggestion,
            dismissSelectedSuggestion: dismissSelectedSuggestion,
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
