<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

type Row = Record<string, any>;
const props = defineProps<{ api: any }>();
const emit = defineEmits<{ error: [message: string]; notice: [message: string] }>();

const loading = ref(false);
const tab = ref<"suppliers" | "requisitions" | "quotations" | "orders" | "inventory" | "reorder">("suppliers");
const suppliers = ref<Row[]>([]);
const products = ref<Row[]>([]);
const requisitions = ref<Row[]>([]);
const quotations = ref<Row[]>([]);
const orders = ref<Row[]>([]);
const lots = ref<Row[]>([]);
const reservations = ref<Row[]>([]);
const reorderPolicies = ref<Row[]>([]);
const purchaseSuggestions = ref<Row[]>([]);
const selectedRequisition = ref<Row | null>(null);
const selectedQuotation = ref<Row | null>(null);
const selectedOrder = ref<Row | null>(null);
const activeCount = ref<Row | null>(null);
const editingPolicy = ref<Row | null>(null);
const selectedSuggestion = ref<Row | null>(null);

const today = new Date().toISOString().slice(0, 10);
const supplierForm = reactive({ code: "", legal_name: "", trade_name: "", cnpj: "", email: "", phone: "", rating: "", contact_name: "", contact_email: "" });
const variantForm = reactive({ product_id: "", sku: "", name: "", sale_price: "", cost_price: "" });
const barcodeForm = reactive({ product_id: "", variant_id: "", barcode: "", barcode_type: "ean13", primary: true });
const requisitionForm = reactive({ needed_by: today, justification: "", product_id: "", quantity: "1", estimated_unit_price: "0" });
const quotationForm = reactive({ requisition_id: "", response_deadline: "", supplier_id: "" });
const proposalForm = reactive({ supplier_id: "", delivery_days: 5, payment_days: "30", unit_price: "", quantity_available: "", brand: "", notes: "" });
const awardForm = reactive({ supplier_id: "", warehouse_id: "default", expected_on: today, reason: "Melhor combinação de preço, prazo e conformidade.", freight_amount: "0", discount_amount: "0" });
const orderForm = reactive({ supplier_id: "", warehouse_id: "default", product_id: "", quantity: "1", unit_price: "0", expected_on: today, freight_amount: "0", discount_amount: "0", notes: "" });
const receiptForm = reactive({ purchase_order_item_id: "", quantity: "1", unit_cost: "0", supplier_document_number: "", lot_number: "", manufactured_on: "", expires_on: "" });
const returnForm = reactive({ purchase_order_item_id: "", quantity: "1", lot_id: "", reason: "Devolução ao fornecedor após conferência." });
const reservationForm = reactive({ product_id: "", warehouse_id: "default", lot_id: "", source_type: "internal_request", source_id: "", quantity: "1", expires_at: "" });
const countForm = reactive({ warehouse_id: "default", product_id: "", include_zero_balance: true });
const countLines = reactive<Record<string, string>>({});
const reorderForm = reactive({ product_id: "", warehouse_id: "default", minimum_quantity: "1", target_quantity: "5", lead_time_days: 0, preferred_supplier_id: "" });
const suggestionActionForm = reactive({ needed_by: today, justification: "Reposição automática validada pela administração.", reason: "Sugestão descartada após revisão operacional e orçamentária." });

const quotationItems = computed(() => selectedQuotation.value?.items ?? []);
const quotationSuppliers = computed(() => selectedQuotation.value?.suppliers ?? []);
const selectedOrderItems = computed(() => selectedOrder.value?.items ?? []);

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return candidate.problem?.detail || (error instanceof Error ? error.message : "Erro inesperado");
}
function idempotency(prefix: string): string { return `${prefix}-${crypto.randomUUID()}`; }
async function request<T = Row>(path: string, init: RequestInit = {}): Promise<T> { return props.api.request<T>(path, init); }
async function post<T = Row>(path: string, body: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["Idempotency-Key"] = key;
  return request<T>(path, { method: "POST", headers, body: JSON.stringify(body) });
}
async function patch<T = Row>(path: string, body: unknown): Promise<T> { return request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
function nullable(value: string): string | null { return value.trim() ? value.trim() : null; }
function money(value: any): string { return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value ?? 0)); }

async function load(): Promise<void> {
  loading.value = true;
  try {
    const [supplierResult, productResult, requisitionResult, quotationResult, orderResult, lotResult, reservationResult, reorderResult, suggestionResult] = await Promise.all([
      request<Row>("/suppliers?limit=200"), request<Row>("/products?limit=300"), request<Row>("/procurement/requisitions?limit=200"),
      request<Row>("/procurement/quotations?limit=200"), request<Row>("/procurement/orders?limit=200"), request<Row>("/inventory/lots?limit=300"), request<Row>("/inventory/reservations?limit=300"),
      request<Row>("/inventory/reorder-policies"), request<Row>("/inventory/purchase-suggestions"),
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
    const firstProduct = products.value[0]; const firstSupplier = suppliers.value[0];
    if (firstProduct) {
      if (!variantForm.product_id) variantForm.product_id = firstProduct.id;
      if (!barcodeForm.product_id) barcodeForm.product_id = firstProduct.id;
      if (!requisitionForm.product_id) requisitionForm.product_id = firstProduct.id;
      if (!orderForm.product_id) orderForm.product_id = firstProduct.id;
      if (!reservationForm.product_id) reservationForm.product_id = firstProduct.id;
      if (!countForm.product_id) countForm.product_id = firstProduct.id;
      if (!reorderForm.product_id) reorderForm.product_id = firstProduct.id;
    }
    if (firstSupplier) {
      if (!quotationForm.supplier_id) quotationForm.supplier_id = firstSupplier.id;
      if (!proposalForm.supplier_id) proposalForm.supplier_id = firstSupplier.id;
      if (!awardForm.supplier_id) awardForm.supplier_id = firstSupplier.id;
      if (!orderForm.supplier_id) orderForm.supplier_id = firstSupplier.id;
      if (!reorderForm.preferred_supplier_id) reorderForm.preferred_supplier_id = firstSupplier.id;
    }
  } catch (error) { emit("error", message(error)); }
  finally { loading.value = false; }
}

async function createSupplier(): Promise<void> {
  try {
    const contacts = supplierForm.contact_name ? [{ name: supplierForm.contact_name, email: nullable(supplierForm.contact_email), role: "commercial", primary: true }] : [];
    await post("/suppliers", { code: nullable(supplierForm.code), legal_name: supplierForm.legal_name, trade_name: nullable(supplierForm.trade_name), cnpj: nullable(supplierForm.cnpj), email: nullable(supplierForm.email), phone: nullable(supplierForm.phone), rating: nullable(supplierForm.rating), contacts }, idempotency("supplier"));
    Object.assign(supplierForm, { code: "", legal_name: "", trade_name: "", cnpj: "", email: "", phone: "", rating: "", contact_name: "", contact_email: "" });
    emit("notice", "Fornecedor e contato cadastrados."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function toggleSupplier(row: Row): Promise<void> {
  try { await patch(`/suppliers/${row.id}`, { status: row.status === "active" ? "inactive" : "active", expected_version: row.version }); emit("notice", "Estado do fornecedor atualizado."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createVariant(): Promise<void> {
  try { await post("/inventory/product-variants", { ...variantForm, sale_price: nullable(variantForm.sale_price), cost_price: nullable(variantForm.cost_price), attributes: {} }, idempotency("product-variant")); emit("notice", "Variação de produto cadastrada."); Object.assign(variantForm, { product_id: variantForm.product_id, sku: "", name: "", sale_price: "", cost_price: "" }); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createBarcode(): Promise<void> {
  try { await post("/inventory/product-barcodes", { ...barcodeForm, variant_id: nullable(barcodeForm.variant_id) }, idempotency("product-barcode")); emit("notice", "Código de barras cadastrado."); barcodeForm.barcode = ""; await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createRequisition(): Promise<void> {
  try {
    await post("/procurement/requisitions", { needed_by: nullable(requisitionForm.needed_by), justification: requisitionForm.justification, items: [{ product_id: requisitionForm.product_id, quantity: requisitionForm.quantity, estimated_unit_price: requisitionForm.estimated_unit_price }] }, idempotency("purchase-requisition"));
    requisitionForm.justification = ""; emit("notice", "Requisição de compra criada."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function showRequisition(row: Row): Promise<void> {
  try { selectedRequisition.value = await request<Row>(`/procurement/requisitions/${row.id}`); quotationForm.requisition_id = row.id; }
  catch (error) { emit("error", message(error)); }
}
async function requisitionAction(row: Row, action: "submit" | "approve" | "reject" | "cancel"): Promise<void> {
  try {
    const detail = await request<Row>(`/procurement/requisitions/${row.id}`);
    const body = action === "approve" ? { approved_quantities: Object.fromEntries((detail.items ?? []).map((item: Row) => [item.id, item.requested_quantity ?? item.quantity])), reason: "Necessidade e disponibilidade orçamentária validadas." } : action === "submit" ? {} : { reason: `${action === "reject" ? "Rejeição" : "Cancelamento"} registrado pela administração.` };
    await post(`/procurement/requisitions/${row.id}/${action}`, body); emit("notice", "Requisição atualizada."); await load(); if (selectedRequisition.value?.requisition?.id === row.id || selectedRequisition.value?.id === row.id) await showRequisition(row);
  } catch (error) { emit("error", message(error)); }
}
async function createQuotation(): Promise<void> {
  try {
    const created = await post<Row>("/procurement/quotations", { requisition_id: quotationForm.requisition_id || null, response_deadline: quotationForm.response_deadline ? new Date(quotationForm.response_deadline).toISOString() : null, currency: "BRL", supplier_ids: [quotationForm.supplier_id], items: [] }, idempotency("quotation"));
    emit("notice", "Cotação criada e fornecedor convidado."); await load(); await showQuotation(created.quotation ?? created);
  } catch (error) { emit("error", message(error)); }
}
async function showQuotation(row: Row): Promise<void> {
  try {
    selectedQuotation.value = await request<Row>(`/procurement/quotations/${row.id}`);
    proposalForm.supplier_id = quotationSuppliers.value[0]?.supplier_id ?? proposalForm.supplier_id;
    proposalForm.quantity_available = quotationItems.value[0]?.quantity ?? quotationItems.value[0]?.requested_quantity ?? "1";
    awardForm.supplier_id = proposalForm.supplier_id;
  } catch (error) { emit("error", message(error)); }
}
async function submitProposal(): Promise<void> {
  if (!selectedQuotation.value || !quotationItems.value.length) return;
  try {
    await post(`/procurement/quotations/${selectedQuotation.value.quotation?.id ?? selectedQuotation.value.id}/suppliers/${proposalForm.supplier_id}/proposal`, { delivery_days: proposalForm.delivery_days, payment_terms: { days: proposalForm.payment_days.split(",").map(value => Number(value.trim())).filter(Number.isFinite) }, notes: nullable(proposalForm.notes), items: quotationItems.value.map((item: Row) => ({ quotation_item_id: item.id, unit_price: proposalForm.unit_price, quantity_available: proposalForm.quantity_available || item.quantity, brand: nullable(proposalForm.brand) })) }, idempotency("supplier-proposal"));
    emit("notice", "Proposta do fornecedor registrada."); await showQuotation(selectedQuotation.value.quotation ?? selectedQuotation.value); await load();
  } catch (error) { emit("error", message(error)); }
}
async function awardQuotation(): Promise<void> {
  if (!selectedQuotation.value) return;
  try {
    const result = await post<Row>(`/procurement/quotations/${selectedQuotation.value.quotation?.id ?? selectedQuotation.value.id}/award`, awardForm, idempotency("quotation-award"));
    emit("notice", "Cotação adjudicada e pedido de compra criado."); await load(); await showOrder(result.order ?? result);
  } catch (error) { emit("error", message(error)); }
}
async function createOrder(): Promise<void> {
  try {
    const created = await post<Row>("/procurement/orders", { supplier_id: orderForm.supplier_id, warehouse_id: orderForm.warehouse_id, expected_on: nullable(orderForm.expected_on), freight_amount: orderForm.freight_amount, discount_amount: orderForm.discount_amount, notes: nullable(orderForm.notes), items: [{ product_id: orderForm.product_id, quantity: orderForm.quantity, unit_price: orderForm.unit_price, discount_amount: "0" }] }, idempotency("purchase-order"));
    emit("notice", "Pedido de compra criado em rascunho."); await load(); await showOrder(created.order ?? created);
  } catch (error) { emit("error", message(error)); }
}
async function showOrder(row: Row): Promise<void> {
  try {
    selectedOrder.value = await request<Row>(`/procurement/orders/${row.id}`);
    const item = selectedOrderItems.value[0];
    if (item) { receiptForm.purchase_order_item_id = item.id; receiptForm.unit_cost = String(item.unit_price ?? 0); returnForm.purchase_order_item_id = item.id; }
  } catch (error) { emit("error", message(error)); }
}
async function approveOrder(row: Row): Promise<void> {
  try { await post(`/procurement/orders/${row.id}/approve`, { reason: "Pedido aprovado pela administração." }); emit("notice", "Pedido aprovado."); await load(); await showOrder(row); }
  catch (error) { emit("error", message(error)); }
}
async function receiveOrder(): Promise<void> {
  if (!selectedOrder.value) return;
  try {
    await post(`/procurement/orders/${selectedOrder.value.order?.id ?? selectedOrder.value.id}/receipts`, { supplier_document_number: nullable(receiptForm.supplier_document_number), items: [{ purchase_order_item_id: receiptForm.purchase_order_item_id, quantity: receiptForm.quantity, unit_cost: receiptForm.unit_cost, lot_number: nullable(receiptForm.lot_number), manufactured_on: nullable(receiptForm.manufactured_on), expires_on: nullable(receiptForm.expires_on) }] }, idempotency("goods-receipt"));
    emit("notice", "Recebimento registrado com estoque e custo médio atualizados."); await load(); await showOrder(selectedOrder.value.order ?? selectedOrder.value);
  } catch (error) { emit("error", message(error)); }
}
async function returnOrderItem(): Promise<void> {
  if (!selectedOrder.value) return;
  try { await post(`/procurement/orders/${selectedOrder.value.order?.id ?? selectedOrder.value.id}/returns`, { reason: returnForm.reason, items: [{ purchase_order_item_id: returnForm.purchase_order_item_id, quantity: returnForm.quantity, lot_id: nullable(returnForm.lot_id) }] }, idempotency("purchase-return")); emit("notice", "Devolução registrada e estoque compensado."); await load(); await showOrder(selectedOrder.value.order ?? selectedOrder.value); }
  catch (error) { emit("error", message(error)); }
}
async function createReservation(): Promise<void> {
  try { await post("/inventory/reservations", { ...reservationForm, lot_id: nullable(reservationForm.lot_id), expires_at: reservationForm.expires_at ? new Date(reservationForm.expires_at).toISOString() : null }, idempotency("inventory-reservation")); emit("notice", "Reserva de estoque registrada."); reservationForm.source_id = ""; await load(); }
  catch (error) { emit("error", message(error)); }
}
async function reservationAction(row: Row, action: "release" | "consume"): Promise<void> {
  try { await post(`/inventory/reservations/${row.id}/${action}`, {}); emit("notice", action === "consume" ? "Reserva consumida e estoque baixado." : "Reserva liberada."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createCount(): Promise<void> {
  try {
    activeCount.value = await post<Row>("/inventory/counts", { warehouse_id: countForm.warehouse_id, product_ids: countForm.product_id ? [countForm.product_id] : [], include_zero_balance: countForm.include_zero_balance }, idempotency("inventory-count"));
    for (const item of activeCount.value.items ?? []) countLines[item.id] = String(item.expected_quantity ?? "0");
    emit("notice", "Inventário aberto para contagem física.");
  } catch (error) { emit("error", message(error)); }
}
async function completeCount(): Promise<void> {
  if (!activeCount.value) return;
  try {
    const countId = activeCount.value.count?.id ?? activeCount.value.id;
    activeCount.value = await post<Row>(`/inventory/counts/${countId}/complete`, { reason: "Contagem física conferida pela administração.", items: (activeCount.value.items ?? []).map((item: Row) => ({ item_id: item.id, counted_quantity: countLines[item.id] ?? item.expected_quantity, notes: null })) });
    emit("notice", "Inventário concluído e divergências ajustadas."); await load();
  } catch (error) { emit("error", message(error)); }
}

function clearPolicyEditor(): void {
  editingPolicy.value = null;
  Object.assign(reorderForm, { product_id: products.value[0]?.id ?? "", warehouse_id: "default", minimum_quantity: "1", target_quantity: "5", lead_time_days: 0, preferred_supplier_id: suppliers.value[0]?.id ?? "" });
}
function editReorderPolicy(row: Row): void {
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
async function saveReorderPolicy(): Promise<void> {
  try {
    const body = {
      minimum_quantity: reorderForm.minimum_quantity,
      target_quantity: reorderForm.target_quantity,
      lead_time_days: reorderForm.lead_time_days,
      preferred_supplier_id: nullable(reorderForm.preferred_supplier_id),
    };
    if (editingPolicy.value) {
      await patch(`/inventory/reorder-policies/${editingPolicy.value.id}`, { ...body, expected_version: editingPolicy.value.version });
      emit("notice", "Política de estoque mínimo atualizada.");
    } else {
      await post("/inventory/reorder-policies", { product_id: reorderForm.product_id, warehouse_id: reorderForm.warehouse_id, ...body }, idempotency("reorder-policy"));
      emit("notice", "Política de estoque mínimo cadastrada.");
    }
    clearPolicyEditor(); await load();
  } catch (error) { emit("error", message(error)); }
}
async function toggleReorderPolicy(row: Row): Promise<void> {
  try {
    await patch(`/inventory/reorder-policies/${row.id}`, { state: row.status === "active" ? "inactive" : "active", expected_version: row.version });
    emit("notice", row.status === "active" ? "Política inativada e sugestões abertas encerradas." : "Política reativada.");
    await load();
  } catch (error) { emit("error", message(error)); }
}
async function generatePurchaseSuggestions(): Promise<void> {
  try {
    const result = await post<Row>("/inventory/purchase-suggestions/generate", {}, idempotency("purchase-suggestions"));
    const summary = result.summary ?? {};
    emit("notice", `Sugestões processadas: ${summary.created ?? 0} novas, ${summary.refreshed ?? 0} atualizadas e ${summary.superseded ?? 0} encerradas.`);
    selectedSuggestion.value = null; await load();
  } catch (error) { emit("error", message(error)); }
}
function selectSuggestion(row: Row): void {
  selectedSuggestion.value = row;
  suggestionActionForm.needed_by = today;
  suggestionActionForm.justification = `Reposição automática de ${row.product_name} validada pela administração.`;
  suggestionActionForm.reason = "Sugestão descartada após revisão operacional e orçamentária.";
}
async function convertSelectedSuggestion(): Promise<void> {
  if (!selectedSuggestion.value) return;
  try {
    const result = await post<Row>(`/inventory/purchase-suggestions/${selectedSuggestion.value.id}/convert`, { expected_version: selectedSuggestion.value.version, needed_by: nullable(suggestionActionForm.needed_by), justification: suggestionActionForm.justification }, idempotency("purchase-suggestion-convert"));
    emit("notice", `Sugestão convertida na requisição ${result.requisition?.requisition_number ?? result.requisition?.id}.`);
    selectedSuggestion.value = null; await load();
  } catch (error) { emit("error", message(error)); }
}
async function dismissSelectedSuggestion(): Promise<void> {
  if (!selectedSuggestion.value) return;
  try {
    await post(`/inventory/purchase-suggestions/${selectedSuggestion.value.id}/dismiss`, { expected_version: selectedSuggestion.value.version, reason: suggestionActionForm.reason }, idempotency("purchase-suggestion-dismiss"));
    emit("notice", "Sugestão descartada com justificativa e trilha de auditoria.");
    selectedSuggestion.value = null; await load();
  } catch (error) { emit("error", message(error)); }
}

onMounted(load);
</script>

<template>
  <div class="procurement-module">
    <section class="metrics">
      <article><span>Fornecedores ativos</span><strong>{{ suppliers.filter(row=>row.status==='active').length }}</strong><small>cadastro homologado</small></article>
      <article><span>Requisições abertas</span><strong>{{ requisitions.filter(row=>!['cancelled','rejected','converted'].includes(row.status)).length }}</strong><small>fluxo de aprovação</small></article>
      <article><span>Cotações</span><strong>{{ quotations.length }}</strong><small>propostas e adjudicação</small></article>
      <article><span>Pedidos pendentes</span><strong>{{ orders.filter(row=>!['received','cancelled'].includes(row.status)).length }}</strong><small>recebimento parcial ou integral</small></article>
      <article><span>Lotes ativos</span><strong>{{ lots.filter(row=>Number(row.quantity)>0).length }}</strong><small>validade e rastreabilidade</small></article>
      <article><span>Sugestões abertas</span><strong>{{ purchaseSuggestions.filter(row=>row.status==='open').length }}</strong><small>reposição por estoque mínimo</small></article>
    </section>
    <section class="procurement-tabs"><button :class="{selected:tab==='suppliers'}" @click="tab='suppliers'">Fornecedores e produtos</button><button :class="{selected:tab==='requisitions'}" @click="tab='requisitions'">Requisições</button><button :class="{selected:tab==='quotations'}" @click="tab='quotations'">Cotações</button><button :class="{selected:tab==='orders'}" @click="tab='orders'">Pedidos e recebimentos</button><button :class="{selected:tab==='inventory'}" @click="tab='inventory'">Lotes, reservas e inventário</button><button :class="{selected:tab==='reorder'}" @click="tab='reorder'">Estoque mínimo e reposição</button><button class="small refresh" :disabled="loading" @click="load">{{ loading?'Atualizando…':'Atualizar' }}</button></section>

    <template v-if="tab==='suppliers'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createSupplier"><h2>Novo fornecedor</h2><div class="cols"><label>Código<input v-model="supplierForm.code" /></label><label>CNPJ<input v-model="supplierForm.cnpj" inputmode="numeric" /></label></div><label>Razão social<input v-model="supplierForm.legal_name" required /></label><label>Nome fantasia<input v-model="supplierForm.trade_name" /></label><div class="cols"><label>E-mail<input v-model="supplierForm.email" type="email" /></label><label>Telefone<input v-model="supplierForm.phone" /></label></div><div class="cols"><label>Contato principal<input v-model="supplierForm.contact_name" /></label><label>E-mail do contato<input v-model="supplierForm.contact_email" type="email" /></label></div><button class="primary">Cadastrar fornecedor</button></form><div class="panel"><h2>Garantias do fluxo</h2><ul class="checklist"><li>Idempotência em cadastros, requisições, pedidos e recebimentos.</li><li>Recebimento parcial com bloqueio de quantidade excedente.</li><li>Lote obrigatório quando definido no perfil do produto.</li><li>Entrada, custo médio, devolução e reserva na mesma transação.</li><li>Auditoria e outbox em todas as transições.</li></ul></div></section>
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createVariant"><h2>Variação de produto</h2><label>Produto<select v-model="variantForm.product_id" required><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>SKU<input v-model="variantForm.sku" required /></label><label>Nome<input v-model="variantForm.name" required /></label></div><div class="cols"><label>Custo<input v-model="variantForm.cost_price" type="number" min="0" step="0.01" /></label><label>Venda<input v-model="variantForm.sale_price" type="number" min="0" step="0.01" /></label></div><button class="primary">Cadastrar variação</button></form><form class="panel" @submit.prevent="createBarcode"><h2>Código de barras</h2><label>Produto<select v-model="barcodeForm.product_id" required><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>Código<input v-model="barcodeForm.barcode" required /></label><label>Tipo<select v-model="barcodeForm.barcode_type"><option value="ean13">EAN-13</option><option value="ean8">EAN-8</option><option value="code128">Code 128</option><option value="internal">Interno</option></select></label></div><label class="inline"><input v-model="barcodeForm.primary" type="checkbox" /> Código principal</label><button class="primary">Cadastrar código</button></form></section>
      <section class="panel"><div class="panel-title"><h2>Fornecedores</h2><span>{{ suppliers.length }}</span></div><table><thead><tr><th>Código</th><th>Fornecedor</th><th>CNPJ</th><th>Contato</th><th>Avaliação</th><th>Estado</th><th></th></tr></thead><tbody><tr v-for="row in suppliers" :key="row.id"><td>{{ row.code||'—' }}</td><td>{{ row.trade_name||row.legal_name }}</td><td>{{ row.cnpj||'—' }}</td><td>{{ row.email||row.contacts?.[0]?.email||'—' }}</td><td>{{ row.rating??'—' }}</td><td>{{ row.status }}</td><td><button class="small" @click="toggleSupplier(row)">{{ row.status==='active'?'Inativar':'Ativar' }}</button></td></tr><tr v-if="!suppliers.length"><td colspan="7" class="empty">Nenhum fornecedor cadastrado.</td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab==='requisitions'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createRequisition"><h2>Nova requisição</h2><label>Produto<select v-model="requisitionForm.product_id" required><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>Quantidade<input v-model="requisitionForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Preço estimado<input v-model="requisitionForm.estimated_unit_price" type="number" min="0" step="0.01" /></label></div><label>Necessário até<input v-model="requisitionForm.needed_by" type="date" /></label><label>Justificativa<textarea v-model="requisitionForm.justification" rows="4" required></textarea></label><button class="primary">Criar requisição</button></form><div class="panel" v-if="selectedRequisition"><h2>Detalhes da requisição</h2><p><strong>{{ selectedRequisition.requisition?.number || selectedRequisition.number }}</strong> · {{ selectedRequisition.requisition?.status || selectedRequisition.status }}</p><div class="rows"><div v-for="item in selectedRequisition.items||[]" :key="item.id"><div><strong>{{ item.product_name||item.product_id }}</strong><small>solicitado {{ item.requested_quantity||item.quantity }} · aprovado {{ item.approved_quantity||0 }}</small></div></div></div></div><div v-else class="panel"><h2>Fluxo de aprovação</h2><p>Selecione uma requisição para consultar itens, quantidades aprovadas e histórico de transições.</p></div></section>
      <section class="panel"><div class="panel-title"><h2>Requisições</h2><span>{{ requisitions.length }}</span></div><table><thead><tr><th>Número</th><th>Data necessária</th><th>Justificativa</th><th>Total estimado</th><th>Estado</th><th>Ações</th></tr></thead><tbody><tr v-for="row in requisitions" :key="row.id"><td>{{ row.number }}</td><td>{{ row.needed_by||'—' }}</td><td>{{ row.justification }}</td><td>{{ money(row.estimated_total) }}</td><td>{{ row.status }}</td><td><button class="small" @click="showRequisition(row)">Detalhes</button><button v-if="row.status==='draft'" class="small" @click="requisitionAction(row,'submit')">Enviar</button><button v-if="row.status==='submitted'" class="small" @click="requisitionAction(row,'approve')">Aprovar</button><button v-if="row.status==='submitted'" class="small" @click="requisitionAction(row,'reject')">Rejeitar</button><button v-if="!['cancelled','rejected','converted'].includes(row.status)" class="small" @click="requisitionAction(row,'cancel')">Cancelar</button></td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab==='quotations'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createQuotation"><h2>Nova cotação</h2><label>Requisição aprovada<select v-model="quotationForm.requisition_id" required><option value="">Selecione</option><option v-for="row in requisitions.filter(item=>item.status==='approved')" :key="row.id" :value="row.id">{{ row.number }} · {{ row.justification }}</option></select></label><label>Fornecedor convidado<select v-model="quotationForm.supplier_id" required><option v-for="row in suppliers.filter(item=>item.status==='active')" :key="row.id" :value="row.id">{{ row.trade_name||row.legal_name }}</option></select></label><label>Prazo de resposta<input v-model="quotationForm.response_deadline" type="datetime-local" /></label><button class="primary">Criar cotação</button></form><form class="panel" @submit.prevent="submitProposal"><h2>Registrar proposta</h2><label>Fornecedor<select v-model="proposalForm.supplier_id" required><option v-for="row in quotationSuppliers" :key="row.supplier_id" :value="row.supplier_id">{{ row.supplier_name||row.supplier_id }}</option></select></label><div class="cols"><label>Preço unitário<input v-model="proposalForm.unit_price" type="number" min="0" step="0.01" required /></label><label>Quantidade disponível<input v-model="proposalForm.quantity_available" type="number" min="0.0001" step="0.0001" required /></label></div><div class="cols"><label>Prazo (dias)<input v-model.number="proposalForm.delivery_days" type="number" min="0" /></label><label>Pagamento (dias)<input v-model="proposalForm.payment_days" placeholder="30,60" /></label></div><label>Marca<input v-model="proposalForm.brand" /></label><button class="primary" :disabled="!selectedQuotation">Registrar proposta</button></form></section>
      <section v-if="selectedQuotation" class="grid-2 forms"><div class="panel"><h2>Itens da cotação</h2><div class="rows"><div v-for="row in quotationItems" :key="row.id"><div><strong>{{ row.product_name||row.product_id }}</strong><small>quantidade {{ row.quantity }}</small></div></div></div></div><form class="panel" @submit.prevent="awardQuotation"><h2>Adjudicar</h2><label>Fornecedor vencedor<select v-model="awardForm.supplier_id" required><option v-for="row in quotationSuppliers.filter(item=>item.status==='responded')" :key="row.supplier_id" :value="row.supplier_id">{{ row.supplier_name||row.supplier_id }}</option></select></label><div class="cols"><label>Depósito<input v-model="awardForm.warehouse_id" required /></label><label>Entrega esperada<input v-model="awardForm.expected_on" type="date" /></label></div><div class="cols"><label>Frete<input v-model="awardForm.freight_amount" type="number" min="0" step="0.01" /></label><label>Desconto<input v-model="awardForm.discount_amount" type="number" min="0" step="0.01" /></label></div><label>Justificativa<textarea v-model="awardForm.reason" rows="3" required></textarea></label><button class="primary">Adjudicar e criar pedido</button></form></section>
      <section class="panel"><div class="panel-title"><h2>Cotações</h2><span>{{ quotations.length }}</span></div><table><thead><tr><th>Número</th><th>Requisição</th><th>Prazo</th><th>Fornecedores</th><th>Estado</th><th></th></tr></thead><tbody><tr v-for="row in quotations" :key="row.id"><td>{{ row.number }}</td><td>{{ row.requisition_number||row.requisition_id||'—' }}</td><td>{{ row.response_deadline||'—' }}</td><td>{{ row.supplier_count??row.suppliers?.length??0 }}</td><td>{{ row.status }}</td><td><button class="small" @click="showQuotation(row)">Detalhes</button></td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab==='orders'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createOrder"><h2>Novo pedido direto</h2><label>Fornecedor<select v-model="orderForm.supplier_id" required><option v-for="row in suppliers.filter(item=>item.status==='active')" :key="row.id" :value="row.id">{{ row.trade_name||row.legal_name }}</option></select></label><label>Produto<select v-model="orderForm.product_id" required><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>Quantidade<input v-model="orderForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Preço unitário<input v-model="orderForm.unit_price" type="number" min="0" step="0.01" required /></label></div><div class="cols"><label>Depósito<input v-model="orderForm.warehouse_id" required /></label><label>Entrega esperada<input v-model="orderForm.expected_on" type="date" /></label></div><button class="primary">Criar pedido</button></form><div class="panel" v-if="selectedOrder"><h2>Pedido {{ selectedOrder.order?.number||selectedOrder.number }}</h2><p>Estado: <strong>{{ selectedOrder.order?.status||selectedOrder.status }}</strong></p><div class="rows"><div v-for="item in selectedOrderItems" :key="item.id"><div><strong>{{ item.product_name||item.product_id }}</strong><small>pedido {{ item.quantity }} · recebido {{ item.received_quantity||0 }} · devolvido {{ item.returned_quantity||0 }}</small></div></div></div></div><div v-else class="panel"><h2>Recebimento e devolução</h2><p>Selecione um pedido para registrar notas, lotes, quantidades recebidas e devoluções.</p></div></section>
      <section v-if="selectedOrder" class="grid-2 forms"><form class="panel" @submit.prevent="receiveOrder"><h2>Registrar recebimento</h2><label>Item<select v-model="receiptForm.purchase_order_item_id" required><option v-for="row in selectedOrderItems" :key="row.id" :value="row.id">{{ row.product_name||row.product_id }}</option></select></label><div class="cols"><label>Quantidade<input v-model="receiptForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Custo unitário<input v-model="receiptForm.unit_cost" type="number" min="0" step="0.0001" required /></label></div><label>Documento do fornecedor<input v-model="receiptForm.supplier_document_number" /></label><div class="cols"><label>Lote<input v-model="receiptForm.lot_number" /></label><label>Validade<input v-model="receiptForm.expires_on" type="date" /></label></div><button class="primary">Confirmar recebimento</button></form><form class="panel" @submit.prevent="returnOrderItem"><h2>Devolução ao fornecedor</h2><label>Item<select v-model="returnForm.purchase_order_item_id" required><option v-for="row in selectedOrderItems" :key="row.id" :value="row.id">{{ row.product_name||row.product_id }}</option></select></label><div class="cols"><label>Quantidade<input v-model="returnForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Lote<select v-model="returnForm.lot_id"><option value="">Sem lote</option><option v-for="row in lots" :key="row.id" :value="row.id">{{ row.lot_number }} · {{ row.product_name }}</option></select></label></div><label>Motivo<textarea v-model="returnForm.reason" rows="3" required></textarea></label><button class="primary">Registrar devolução</button></form></section>
      <section class="panel"><div class="panel-title"><h2>Pedidos de compra</h2><span>{{ orders.length }}</span></div><table><thead><tr><th>Número</th><th>Fornecedor</th><th>Total</th><th>Recebido</th><th>Estado</th><th>Ações</th></tr></thead><tbody><tr v-for="row in orders" :key="row.id"><td>{{ row.number }}</td><td>{{ row.supplier_name||row.supplier_id }}</td><td>{{ money(row.total_amount) }}</td><td>{{ row.received_percentage??0 }}%</td><td>{{ row.status }}</td><td><button class="small" @click="showOrder(row)">Detalhes</button><button v-if="row.status==='draft'" class="small" @click="approveOrder(row)">Aprovar</button></td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab==='inventory'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createReservation"><h2>Reserva de estoque</h2><label>Produto<select v-model="reservationForm.product_id" required><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label>Lote<select v-model="reservationForm.lot_id"><option value="">Sem lote específico</option><option v-for="row in lots.filter(item=>item.product_id===reservationForm.product_id)" :key="row.id" :value="row.id">{{ row.lot_number }} · saldo {{ row.quantity }}</option></select></label><div class="cols"><label>Quantidade<input v-model="reservationForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Depósito<input v-model="reservationForm.warehouse_id" required /></label></div><div class="cols"><label>Origem<input v-model="reservationForm.source_type" required /></label><label>Identificador<input v-model="reservationForm.source_id" required /></label></div><button class="primary">Reservar</button></form><form class="panel" @submit.prevent="createCount"><h2>Novo inventário</h2><label>Depósito<input v-model="countForm.warehouse_id" required /></label><label>Produto<select v-model="countForm.product_id"><option value="">Todos os produtos</option><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label class="inline"><input v-model="countForm.include_zero_balance" type="checkbox" /> Incluir saldo zero</label><button class="primary">Abrir inventário</button></form></section>
      <section v-if="activeCount" class="panel"><div class="panel-title"><h2>Contagem em andamento</h2><span>{{ activeCount.count?.number||activeCount.number }}</span></div><table><thead><tr><th>Produto</th><th>Esperado</th><th>Contado</th></tr></thead><tbody><tr v-for="row in activeCount.items||[]" :key="row.id"><td>{{ row.product_name||row.product_id }}</td><td>{{ row.expected_quantity }}</td><td><input v-model="countLines[row.id]" type="number" min="0" step="0.0001" /></td></tr></tbody></table><button v-if="(activeCount.count?.status||activeCount.status)!=='completed'" class="primary" @click="completeCount">Concluir inventário e ajustar</button></section>
      <section class="grid-2"><div class="panel"><div class="panel-title"><h2>Lotes</h2><span>{{ lots.length }}</span></div><table><thead><tr><th>Produto</th><th>Lote</th><th>Validade</th><th>Quantidade</th></tr></thead><tbody><tr v-for="row in lots" :key="row.id"><td>{{ row.product_name||row.product_id }}</td><td>{{ row.lot_number }}</td><td>{{ row.expires_on||'—' }}</td><td>{{ row.quantity }}</td></tr></tbody></table></div><div class="panel"><div class="panel-title"><h2>Reservas</h2><span>{{ reservations.length }}</span></div><table><thead><tr><th>Produto</th><th>Origem</th><th>Quantidade</th><th>Estado</th><th></th></tr></thead><tbody><tr v-for="row in reservations" :key="row.id"><td>{{ row.product_name||row.product_id }}</td><td>{{ row.source_type }} / {{ row.source_id }}</td><td>{{ row.quantity }}</td><td>{{ row.status }}</td><td><button v-if="row.status==='active'" class="small" @click="reservationAction(row,'consume')">Consumir</button><button v-if="row.status==='active'" class="small" @click="reservationAction(row,'release')">Liberar</button></td></tr></tbody></table></div></section>
    </template>

    <template v-else>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="saveReorderPolicy">
          <div class="panel-title"><h2>{{ editingPolicy?'Editar política':'Nova política de estoque mínimo' }}</h2><span v-if="editingPolicy">v{{ editingPolicy.version }}</span></div>
          <label>Produto<select v-model="reorderForm.product_id" :disabled="!!editingPolicy" required><option v-for="row in products" :key="row.id" :value="row.id">{{ row.name }} · {{ row.sku }}</option></select></label>
          <label>Depósito<input v-model="reorderForm.warehouse_id" :disabled="!!editingPolicy" required /></label>
          <div class="cols"><label>Estoque mínimo<input v-model="reorderForm.minimum_quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Estoque alvo<input v-model="reorderForm.target_quantity" type="number" min="0.0001" step="0.0001" required /></label></div>
          <div class="cols"><label>Prazo de reposição (dias)<input v-model.number="reorderForm.lead_time_days" type="number" min="0" max="3650" /></label><label>Fornecedor preferencial<select v-model="reorderForm.preferred_supplier_id"><option value="">Sem preferência</option><option v-for="row in suppliers.filter(item=>item.status==='active')" :key="row.id" :value="row.id">{{ row.trade_name||row.legal_name }}</option></select></label></div>
          <div class="actions"><button class="primary">{{ editingPolicy?'Salvar alterações':'Cadastrar política' }}</button><button v-if="editingPolicy" type="button" class="small" @click="clearPolicyEditor">Cancelar edição</button></div>
        </form>
        <div class="panel">
          <h2>Motor de reposição</h2>
          <p>O cálculo considera saldo físico, reservas ativas e quantidades ainda pendentes em pedidos aprovados. Sugestões abertas são atualizadas sem duplicidade e encerradas quando a necessidade deixa de existir.</p>
          <ul class="checklist"><li>Limites por produto e depósito.</li><li>Fornecedor preferencial e prazo de reposição.</li><li>Conversão transacional em requisição de compra.</li><li>Idempotência, concorrência otimista, auditoria e outbox.</li><li>Aplicável à cantina, materiais, uniformes, livros e demais estoques.</li></ul>
          <button class="primary" :disabled="loading||!reorderPolicies.some(row=>row.status==='active')" @click="generatePurchaseSuggestions">Recalcular sugestões de compra</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title"><h2>Políticas de estoque mínimo</h2><span>{{ reorderPolicies.length }}</span></div>
        <table><thead><tr><th>Produto</th><th>Depósito</th><th>Disponível</th><th>Em compra</th><th>Projetado</th><th>Mínimo / alvo</th><th>Fornecedor</th><th>Estado</th><th>Ações</th></tr></thead><tbody>
          <tr v-for="row in reorderPolicies" :key="row.id"><td><strong>{{ row.product_name }}</strong><small>{{ row.product_sku }}</small></td><td>{{ row.warehouse_id||row.warehouse }}</td><td>{{ row.stock?.available_quantity??0 }}</td><td>{{ row.stock?.open_purchase_quantity??0 }}</td><td>{{ row.stock?.projected_quantity??0 }}</td><td>{{ row.minimum_quantity }} / {{ row.target_quantity }}</td><td>{{ row.preferred_supplier_name||'—' }}</td><td>{{ row.status }}</td><td><button class="small" @click="editReorderPolicy(row)">Editar</button><button class="small" @click="toggleReorderPolicy(row)">{{ row.status==='active'?'Inativar':'Ativar' }}</button></td></tr>
          <tr v-if="!reorderPolicies.length"><td colspan="9" class="empty">Nenhuma política cadastrada.</td></tr>
        </tbody></table>
      </section>

      <section class="grid-2">
        <div class="panel">
          <div class="panel-title"><h2>Sugestões de compra</h2><span>{{ purchaseSuggestions.length }}</span></div>
          <table><thead><tr><th>Produto</th><th>Disponível + compra</th><th>Sugerido</th><th>Estimativa</th><th>Estado</th><th></th></tr></thead><tbody>
            <tr v-for="row in purchaseSuggestions" :key="row.id"><td><strong>{{ row.product_name }}</strong><small>{{ row.warehouse_id }}</small></td><td>{{ row.available_quantity }} + {{ row.open_purchase_quantity }}</td><td>{{ row.suggested_quantity }}</td><td>{{ money(row.estimated_total) }}</td><td>{{ row.status }}</td><td><button v-if="row.status==='open'" class="small" @click="selectSuggestion(row)">Analisar</button><span v-else-if="row.requisition_id">Req. {{ row.requisition_id.slice(-8) }}</span><span v-else>{{ row.closure_reason||'—' }}</span></td></tr>
            <tr v-if="!purchaseSuggestions.length"><td colspan="6" class="empty">Nenhuma sugestão calculada.</td></tr>
          </tbody></table>
        </div>
        <div v-if="selectedSuggestion" class="panel">
          <h2>Analisar reposição</h2>
          <p><strong>{{ selectedSuggestion.product_name }}</strong></p>
          <div class="rows"><div><div><span>Saldo projetado</span><small>disponível + compras aprovadas</small></div><strong>{{ selectedSuggestion.projected_quantity }}</strong></div><div><div><span>Limite mínimo</span><small>gatilho configurado</small></div><strong>{{ selectedSuggestion.minimum_quantity }}</strong></div><div><div><span>Quantidade sugerida</span><small>até o estoque alvo</small></div><strong>{{ selectedSuggestion.suggested_quantity }}</strong></div></div>
          <form @submit.prevent="convertSelectedSuggestion"><label>Necessário até<input v-model="suggestionActionForm.needed_by" type="date" /></label><label>Justificativa<textarea v-model="suggestionActionForm.justification" rows="3" required></textarea></label><button class="primary">Converter em requisição</button></form>
          <form class="dismiss-form" @submit.prevent="dismissSelectedSuggestion"><label>Motivo do descarte<textarea v-model="suggestionActionForm.reason" rows="3" required></textarea></label><button class="small">Descartar sugestão</button></form>
        </div>
        <div v-else class="panel"><h2>Análise da sugestão</h2><p>Selecione uma sugestão aberta para convertê-la em requisição de compra ou descartá-la com justificativa auditada.</p></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.procurement-tabs{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}.procurement-tabs button{border:1px solid var(--line,#d9e0e7);background:var(--surface,#fff);padding:10px 14px;border-radius:10px;cursor:pointer}.procurement-tabs button.selected{border-color:var(--brand-primary);box-shadow:0 0 0 1px var(--brand-primary)}.procurement-tabs .refresh{margin-left:auto}.rows>div{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line,#e5e7eb)}.rows>div:last-child{border-bottom:0}.rows>div>div{display:flex;flex-direction:column}.rows small{opacity:.7}textarea{resize:vertical}.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.dismiss-form{margin-top:18px;padding-top:18px;border-top:1px solid var(--line,#e5e7eb)}td strong+small{display:block;opacity:.7;margin-top:2px}@media(max-width:800px){.procurement-tabs .refresh{margin-left:0}.rows>div{align-items:flex-start;flex-direction:column}}
</style>
