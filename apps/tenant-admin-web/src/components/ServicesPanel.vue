<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

type Row = Record<string, any>;
const props = defineProps<{ api: any }>();
const emit = defineEmits<{ error: [message: string]; notice: [message: string] }>();

const loading = ref(false);
const tab = ref<"catalog" | "subscriptions" | "orders" | "fiscal">("catalog");
const catalogs = ref<Row[]>([]);
const services = ref<Row[]>([]);
const subscriptions = ref<Row[]>([]);
const orders = ref<Row[]>([]);
const executions = ref<Row[]>([]);
const fiscalEvents = ref<Row[]>([]);
const people = ref<Row[]>([]);
const dashboard = ref<Row>({});
const selectedService = ref<Row | null>(null);
const selectedSubscription = ref<Row | null>(null);
const selectedOrder = ref<Row | null>(null);

const today = new Date().toISOString().slice(0, 10);
const month = new Date().toISOString().slice(0, 7);
const catalogForm = reactive({ code: "", name: "", description: "", valid_from: today, status: "active" });
const serviceForm = reactive({ catalog_id: "", code: "", name: "", description: "", service_type: "administrative", recurrence_type: "one_time", unit_of_measure: "unit", taxable: true, status: "active" });
const variantForm = reactive({ code: "PADRAO", name: "Padrão", duration_minutes: 60 as number | null, capacity: null as number | null, status: "active" });
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

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return candidate.problem?.detail || (error instanceof Error ? error.message : "Erro inesperado");
}
function idempotency(prefix: string): string { return `${prefix}-${crypto.randomUUID()}`; }
async function request<T = Row>(path: string, init: RequestInit = {}): Promise<T> { return props.api.request(path, init) as Promise<T>; }
async function post<T = Row>(path: string, body: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["Idempotency-Key"] = key;
  return request<T>(path, { method: "POST", headers, body: JSON.stringify(body) });
}
async function patch<T = Row>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function numeric(value: string): string | null { return value.trim() === "" ? null : value; }
function clearServiceSelection(): void {
  selectedService.value = null;
  Object.assign(variantForm, { code: "PADRAO", name: "Padrão", duration_minutes: 60, capacity: null, status: "active" });
  Object.assign(priceForm, { variant_id: "", name: "Tabela vigente", valid_from: today, amount: "", billing_frequency: "one_time", status: "active" });
  Object.assign(fiscalForm, { variant_id: "", valid_from: today, nbs_code: "", lc116_code: "", municipal_service_code: "", cnae_code: "", iss_rate: "0", ibs_rate: "0", cbs_rate: "0", cclass_trib: "", fiscal_trigger: "billing" });
  Object.assign(billingForm, { variant_id: "", code: "PADRAO", name: "Cobrança padrão", billing_trigger: "competence", due_day: 10, installment_count: 1, interval_months: 1, recognition_policy: "competence", fiscal_trigger: "competence", proration_policy: "none", status: "active" });
}
async function load(): Promise<void> {
  loading.value = true;
  try {
    const [catalogResult, serviceResult, subscriptionResult, orderResult, executionResult, fiscalResult, peopleResult, dashboardResult] = await Promise.all([
      request<Row>("/service-catalogs"), request<Row>("/services"), request<Row>("/service-subscriptions"), request<Row>("/service-orders"),
      request<Row>("/service-executions"), request<Row>("/service-fiscal-events"), request<Row>("/people?limit=200"), request<Row>("/services-dashboard"),
    ]);
    catalogs.value = catalogResult.items ?? [];
    services.value = serviceResult.items ?? [];
    subscriptions.value = subscriptionResult.items ?? [];
    orders.value = orderResult.items ?? [];
    executions.value = executionResult.items ?? [];
    fiscalEvents.value = fiscalResult.items ?? [];
    people.value = peopleResult.items ?? [];
    dashboard.value = dashboardResult;
    if (!serviceForm.catalog_id && catalogs.value[0]) serviceForm.catalog_id = catalogs.value[0].id;
    if (!subscriptionForm.service_id && services.value[0]) subscriptionForm.service_id = services.value[0].id;
    if (!orderForm.service_id && services.value[0]) orderForm.service_id = services.value[0].id;
  } catch (error) { emit("error", message(error)); }
  finally { loading.value = false; }
}
async function createCatalog(): Promise<void> {
  try {
    await post("/service-catalogs", { ...catalogForm, description: catalogForm.description || null }, idempotency("service-catalog"));
    Object.assign(catalogForm, { code: "", name: "", description: "", valid_from: today, status: "active" });
    emit("notice", "Catálogo de serviços cadastrado."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function createService(): Promise<void> {
  try {
    const created = await post<Row>("/services", { ...serviceForm, catalog_id: serviceForm.catalog_id || null, description: serviceForm.description || null }, idempotency("service"));
    Object.assign(serviceForm, { catalog_id: serviceForm.catalog_id, code: "", name: "", description: "", service_type: "administrative", recurrence_type: "one_time", unit_of_measure: "unit", taxable: true, status: "active" });
    emit("notice", "Serviço cadastrado."); await load(); await showService(created);
  } catch (error) { emit("error", message(error)); }
}
async function showService(service: Row): Promise<void> {
  try {
    selectedService.value = await request<Row>(`/services/${service.id}`);
    const firstVariant = currentVariants.value[0];
    priceForm.variant_id = firstVariant?.id ?? ""; fiscalForm.variant_id = firstVariant?.id ?? ""; billingForm.variant_id = firstVariant?.id ?? "";
  } catch (error) { emit("error", message(error)); }
}
async function updateServiceStatus(status: string): Promise<void> {
  if (!selectedService.value) return;
  try {
    selectedService.value = await patch<Row>(`/services/${selectedService.value.id}`, { status, expected_version: selectedService.value.version });
    emit("notice", `Serviço atualizado para ${status}.`); await load(); await showService(selectedService.value);
  } catch (error) { emit("error", message(error)); }
}
async function createVariant(): Promise<void> {
  if (!selectedService.value) return;
  try {
    await post(`/services/${selectedService.value.id}/variants`, { ...variantForm, duration_minutes: variantForm.duration_minutes || null, capacity: variantForm.capacity || null }, idempotency("service-variant"));
    emit("notice", "Variação cadastrada."); await showService(selectedService.value);
  } catch (error) { emit("error", message(error)); }
}
async function createPrice(): Promise<void> {
  if (!selectedService.value) return;
  try {
    await post(`/services/${selectedService.value.id}/price-tables`, { ...priceForm, variant_id: priceForm.variant_id || null }, idempotency("service-price"));
    emit("notice", "Preço e vigência registrados."); await showService(selectedService.value);
  } catch (error) { emit("error", message(error)); }
}
async function createFiscalProfile(): Promise<void> {
  if (!selectedService.value) return;
  try {
    await post(`/services/${selectedService.value.id}/fiscal-profiles`, { ...fiscalForm, variant_id: fiscalForm.variant_id || null, nbs_code: fiscalForm.nbs_code || null, lc116_code: fiscalForm.lc116_code || null, municipal_service_code: fiscalForm.municipal_service_code || null, cnae_code: fiscalForm.cnae_code || null, cclass_trib: fiscalForm.cclass_trib || null }, idempotency("service-fiscal"));
    emit("notice", "Perfil fiscal versionado."); await showService(selectedService.value);
  } catch (error) { emit("error", message(error)); }
}
async function publishFiscal(profile: Row): Promise<void> {
  try { await post(`/service-fiscal-profiles/${profile.id}/publish`, { notes: "Classificação revisada na administração do tenant." }); emit("notice", "Perfil fiscal publicado."); if (selectedService.value) await showService(selectedService.value); }
  catch (error) { emit("error", message(error)); }
}
async function createBillingRule(): Promise<void> {
  if (!selectedService.value) return;
  try { await post(`/services/${selectedService.value.id}/billing-rules`, { ...billingForm, variant_id: billingForm.variant_id || null }, idempotency("service-billing")); emit("notice", "Regra de cobrança registrada."); await showService(selectedService.value); }
  catch (error) { emit("error", message(error)); }
}
async function createSubscription(): Promise<void> {
  try {
    const created = await post<Row>("/service-subscriptions", { ...subscriptionForm, variant_id: subscriptionForm.variant_id || null, ends_on: subscriptionForm.ends_on || null, unit_price: numeric(subscriptionForm.unit_price) }, idempotency("service-subscription"));
    selectedSubscription.value = created; emit("notice", "Assinatura criada em rascunho."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function subscriptionAction(row: Row, action: "activate" | "suspend" | "resume" | "cancel"): Promise<void> {
  try { await post(`/service-subscriptions/${row.id}/${action}`, { reason: `Ação ${action} registrada pela administração.` }); emit("notice", "Estado da assinatura atualizado."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function generateCompetence(row: Row): Promise<void> {
  try { await post(`/service-subscriptions/${row.id}/competencies`, competenceForm, idempotency(`service-competence-${competenceForm.competence_key}`)); emit("notice", "Competência gerada com pedido, cobrança, execução e evento fiscal."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createOrder(): Promise<void> {
  try {
    await post("/service-orders", { order_number: orderForm.order_number || null, subscriber_person_id: orderForm.subscriber_person_id || null, due_date: orderForm.due_date || null, installment_count: 1, discount_amount: "0", notes: orderForm.notes || null, items: [{ service_id: orderForm.service_id, variant_id: orderForm.variant_id || null, quantity: orderForm.quantity, unit_price: numeric(orderForm.unit_price), discount_amount: orderForm.discount_amount }] }, idempotency("service-order"));
    emit("notice", "Pedido de serviço criado."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function orderAction(row: Row, action: "confirm" | "start" | "complete" | "cancel"): Promise<void> {
  try { await post(`/service-orders/${row.id}/${action}`, action === "cancel" ? { reason: "Cancelamento registrado pela administração." } : { notes: `Ação ${action} registrada pela administração.` }); emit("notice", "Pedido atualizado."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function showOrder(row: Row): Promise<void> {
  try { selectedOrder.value = await request<Row>(`/service-orders/${row.id}`); executionForm.order_item_id = selectedOrder.value?.items?.[0]?.id ?? ""; }
  catch (error) { emit("error", message(error)); }
}
async function scheduleExecution(): Promise<void> {
  if (!selectedOrder.value) return;
  try { await post(`/service-orders/${selectedOrder.value.id}/executions`, { ...executionForm, scheduled_at: executionForm.scheduled_at ? new Date(executionForm.scheduled_at).toISOString() : null, performer_person_id: executionForm.performer_person_id || null, notes: executionForm.notes || null }, idempotency("service-execution")); emit("notice", "Execução agendada."); await load(); await showOrder(selectedOrder.value); }
  catch (error) { emit("error", message(error)); }
}
async function executionAction(row: Row, action: "start" | "complete" | "cancel"): Promise<void> {
  try {
    const body = action === "complete" ? { completed_quantity: row.quantity, notes: "Execução concluída.", evidence: { source: "tenant-admin-web" } } : action === "cancel" ? { reason: "Execução cancelada pela administração." } : { notes: "Execução iniciada pela administração." };
    await post(`/service-executions/${row.id}/${action}`, body); emit("notice", "Execução atualizada."); await load();
  } catch (error) { emit("error", message(error)); }
}
function money(value: any): string { return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value ?? 0)); }
function dateTime(value: string | null | undefined): string { return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—"; }

onMounted(load);
</script>

<template>
  <div class="service-module">
    <section class="metrics">
      <article><span>Serviços</span><strong>{{ dashboard.services ?? services.length }}</strong><small>catálogo operacional</small></article>
      <article><span>Assinaturas ativas</span><strong>{{ dashboard.active_subscriptions ?? 0 }}</strong><small>recorrência vigente</small></article>
      <article><span>Pedidos em aberto</span><strong>{{ dashboard.open_orders ?? 0 }}</strong><small>execução ou cobrança</small></article>
      <article><span>Fiscal não configurado</span><strong>{{ dashboard.not_configured_fiscal_events ?? 0 }}</strong><small>sem simular emissão real</small></article>
      <article><span>Faturado</span><strong>{{ money(dashboard.billed_total) }}</strong><small>pedidos confirmados</small></article>
    </section>
    <section class="service-tabs">
      <button :class="{selected:tab==='catalog'}" @click="tab='catalog'">Catálogo e preços</button>
      <button :class="{selected:tab==='subscriptions'}" @click="tab='subscriptions'">Assinaturas</button>
      <button :class="{selected:tab==='orders'}" @click="tab='orders'">Pedidos e execuções</button>
      <button :class="{selected:tab==='fiscal'}" @click="tab='fiscal'">Fiscal</button>
      <button class="small refresh" :disabled="loading" @click="load">{{ loading ? 'Atualizando…' : 'Atualizar' }}</button>
    </section>

    <template v-if="tab==='catalog'">
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createCatalog"><h2>Novo catálogo</h2><div class="cols"><label>Código<input v-model="catalogForm.code" required /></label><label>Vigência<input v-model="catalogForm.valid_from" type="date" /></label></div><label>Nome<input v-model="catalogForm.name" required /></label><label>Descrição<textarea v-model="catalogForm.description" rows="3"></textarea></label><button class="primary">Cadastrar catálogo</button></form>
        <form class="panel" @submit.prevent="createService"><h2>Novo serviço</h2><label>Catálogo<select v-model="serviceForm.catalog_id"><option value="">Sem catálogo</option><option v-for="row in catalogs" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>Código<input v-model="serviceForm.code" required /></label><label>Tipo<select v-model="serviceForm.service_type"><option value="tuition">Mensalidade</option><option value="course">Curso</option><option value="transportation">Transporte</option><option value="extracurricular">Extracurricular</option><option value="event">Evento</option><option value="document">Documento</option><option value="administrative">Administrativo</option><option value="other">Outro</option></select></label></div><label>Nome<input v-model="serviceForm.name" required /></label><div class="cols"><label>Recorrência<select v-model="serviceForm.recurrence_type"><option value="one_time">Avulso</option><option value="monthly">Mensal</option><option value="quarterly">Trimestral</option><option value="annual">Anual</option><option value="custom">Personalizada</option></select></label><label class="inline"><input v-model="serviceForm.taxable" type="checkbox" /> Tributável</label></div><button class="primary">Cadastrar serviço</button></form>
      </section>
      <section class="panel"><div class="panel-title"><h2>Serviços cadastrados</h2><span>{{ services.length }}</span></div><table><thead><tr><th>Código</th><th>Serviço</th><th>Tipo</th><th>Recorrência</th><th>Estado</th><th></th></tr></thead><tbody><tr v-for="row in services" :key="row.id"><td>{{ row.code }}</td><td>{{ row.name }}</td><td>{{ row.service_type }}</td><td>{{ row.recurrence_type }}</td><td><span class="pill" :class="row.status==='active'?'ok':'warn'">{{ row.status }}</span></td><td><button class="small" @click="showService(row)">Detalhes</button></td></tr><tr v-if="!services.length"><td colspan="6" class="empty">Nenhum serviço cadastrado.</td></tr></tbody></table></section>
      <template v-if="selectedService">
        <section class="panel"><div class="panel-title"><div><h2>{{ selectedService.name }}</h2><small>{{ selectedService.code }} · versão {{ selectedService.version }}</small></div><div><button v-if="selectedService.status!=='active'" class="small" @click="updateServiceStatus('active')">Ativar</button><button v-if="selectedService.status==='active'" class="small" @click="updateServiceStatus('inactive')">Inativar</button><button class="small" @click="clearServiceSelection">Fechar</button></div></div></section>
        <section class="grid-2 forms"><form class="panel" @submit.prevent="createVariant"><h2>Variação</h2><div class="cols"><label>Código<input v-model="variantForm.code" required /></label><label>Nome<input v-model="variantForm.name" required /></label></div><div class="cols"><label>Duração (min)<input v-model.number="variantForm.duration_minutes" type="number" min="1" /></label><label>Capacidade<input v-model.number="variantForm.capacity" type="number" min="1" /></label></div><button class="primary">Adicionar variação</button></form><form class="panel" @submit.prevent="createPrice"><h2>Preço e vigência</h2><label>Variação<select v-model="priceForm.variant_id"><option value="">Serviço principal</option><option v-for="row in currentVariants" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>Nome<input v-model="priceForm.name" required /></label><label>Valor<input v-model="priceForm.amount" type="number" min="0.01" step="0.01" required /></label></div><div class="cols"><label>Vigência<input v-model="priceForm.valid_from" type="date" required /></label><label>Frequência<select v-model="priceForm.billing_frequency"><option value="one_time">Avulsa</option><option value="monthly">Mensal</option><option value="annual">Anual</option></select></label></div><button class="primary">Registrar preço</button></form></section>
        <section class="grid-2 forms"><form class="panel" @submit.prevent="createFiscalProfile"><h2>Perfil fiscal</h2><label>Variação<select v-model="fiscalForm.variant_id"><option value="">Serviço principal</option><option v-for="row in currentVariants" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>NBS<input v-model="fiscalForm.nbs_code" /></label><label>LC 116<input v-model="fiscalForm.lc116_code" /></label></div><div class="cols"><label>Código municipal<input v-model="fiscalForm.municipal_service_code" /></label><label>CNAE<input v-model="fiscalForm.cnae_code" /></label></div><div class="cols"><label>cClassTrib<input v-model="fiscalForm.cclass_trib" /></label><label>Gatilho<select v-model="fiscalForm.fiscal_trigger"><option value="competence">Competência</option><option value="billing">Faturamento</option><option value="payment">Pagamento</option><option value="execution">Execução</option><option value="manual">Manual</option></select></label></div><button class="primary">Versionar perfil</button></form><form class="panel" @submit.prevent="createBillingRule"><h2>Regra de cobrança</h2><label>Variação<select v-model="billingForm.variant_id"><option value="">Serviço principal</option><option v-for="row in currentVariants" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><div class="cols"><label>Código<input v-model="billingForm.code" required /></label><label>Nome<input v-model="billingForm.name" required /></label></div><div class="cols"><label>Dia de vencimento<input v-model.number="billingForm.due_day" type="number" min="1" max="31" /></label><label>Gatilho<select v-model="billingForm.billing_trigger"><option value="competence">Competência</option><option value="billing">Faturamento</option><option value="payment">Pagamento</option><option value="execution">Execução</option><option value="manual">Manual</option></select></label></div><button class="primary">Registrar regra</button></form></section>
        <section class="grid-2"><div class="panel"><h2>Variações e preços</h2><div class="rows"><div v-for="row in currentVariants" :key="row.id"><div><strong>{{ row.name }}</strong><small>{{ row.code }} · capacidade {{ row.capacity ?? 'livre' }}</small></div></div><div v-for="row in currentPrices" :key="row.id"><div><strong>{{ row.name }}</strong><small>{{ money(row.amount) }} · desde {{ row.valid_from }}</small></div></div></div></div><div class="panel"><h2>Fiscal e cobrança</h2><div class="rows"><div v-for="row in currentFiscalProfiles" :key="row.id"><div><strong>{{ row.nbs_code || 'NBS pendente' }} / {{ row.lc116_code || 'LC 116 pendente' }}</strong><small>{{ row.classification_status }} · {{ row.status }}</small></div><button v-if="row.status!=='published'" class="small" @click="publishFiscal(row)">Publicar</button></div><div v-for="row in currentBillingRules" :key="row.id"><div><strong>{{ row.name }}</strong><small>dia {{ row.due_day }} · {{ row.billing_trigger }}</small></div></div></div></div></section>
      </template>
    </template>

    <template v-else-if="tab==='subscriptions'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createSubscription"><h2>Nova assinatura</h2><div class="cols"><label>Número<input v-model="subscriptionForm.subscription_number" required /></label><label>Início<input v-model="subscriptionForm.starts_on" type="date" required /></label></div><label>Serviço<select v-model="subscriptionForm.service_id" required><option v-for="row in services" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label>Assinante<select v-model="subscriptionForm.subscriber_person_id" required><option value="">Selecione</option><option v-for="row in people" :key="row.id" :value="row.id">{{ row.full_name }}</option></select></label><label>Regra de cobrança<input v-model="subscriptionForm.billing_rule_id" placeholder="UUID da regra publicada" required /></label><div class="cols"><label>Preço opcional<input v-model="subscriptionForm.unit_price" type="number" min="0.01" step="0.01" /></label><label>Desconto<input v-model="subscriptionForm.discount_amount" type="number" min="0" step="0.01" /></label></div><label class="inline"><input v-model="subscriptionForm.auto_renew" type="checkbox" /> Renovação automática</label><button class="primary">Criar assinatura</button></form><form class="panel" @submit.prevent="selectedSubscription && generateCompetence(selectedSubscription)"><h2>Gerar competência</h2><label>Assinatura<select v-model="selectedSubscription"><option :value="null">Selecione</option><option v-for="row in subscriptions" :key="row.id" :value="row">{{ row.subscription_number }} · {{ row.service_name || row.service_id }}</option></select></label><div class="cols"><label>Competência<input v-model="competenceForm.competence_key" type="month" required /></label><label>Vencimento<input v-model="competenceForm.due_date" type="date" required /></label></div><button class="primary" :disabled="!selectedSubscription">Gerar pedido e cobrança</button></form></section>
      <section class="panel"><div class="panel-title"><h2>Assinaturas</h2><span>{{ subscriptions.length }}</span></div><table><thead><tr><th>Número</th><th>Serviço</th><th>Assinante</th><th>Valor do ciclo</th><th>Estado</th><th>Ações</th></tr></thead><tbody><tr v-for="row in subscriptions" :key="row.id"><td>{{ row.subscription_number }}</td><td>{{ row.service_name || row.service_id }}</td><td>{{ row.subscriber_name || row.subscriber_person_id }}</td><td>{{ money(row.cycle_amount) }}</td><td><span class="pill" :class="row.status==='active'?'ok':'warn'">{{ row.status }}</span></td><td><button v-if="row.status==='draft'" class="small" @click="subscriptionAction(row,'activate')">Ativar</button><button v-if="row.status==='active'" class="small" @click="subscriptionAction(row,'suspend')">Suspender</button><button v-if="row.status==='suspended'" class="small" @click="subscriptionAction(row,'resume')">Retomar</button><button v-if="!['cancelled','ended'].includes(row.status)" class="small" @click="subscriptionAction(row,'cancel')">Cancelar</button><button v-if="row.status==='active'" class="small" @click="selectedSubscription=row;generateCompetence(row)">Gerar competência</button></td></tr><tr v-if="!subscriptions.length"><td colspan="6" class="empty">Nenhuma assinatura cadastrada.</td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab==='orders'">
      <section class="grid-2 forms"><form class="panel" @submit.prevent="createOrder"><h2>Novo pedido avulso</h2><label>Serviço<select v-model="orderForm.service_id" required><option v-for="row in services" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label>Assinante<select v-model="orderForm.subscriber_person_id"><option value="">Sem vínculo</option><option v-for="row in people" :key="row.id" :value="row.id">{{ row.full_name }}</option></select></label><div class="cols"><label>Quantidade<input v-model="orderForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Preço unitário<input v-model="orderForm.unit_price" type="number" min="0.01" step="0.01" /></label></div><div class="cols"><label>Vencimento<input v-model="orderForm.due_date" type="date" /></label><label>Desconto<input v-model="orderForm.discount_amount" type="number" min="0" step="0.01" /></label></div><button class="primary">Criar pedido</button></form><form class="panel" @submit.prevent="scheduleExecution"><h2>Agendar execução</h2><label>Pedido<select v-model="selectedOrder" @change="selectedOrder && showOrder(selectedOrder)"><option :value="null">Selecione</option><option v-for="row in orders" :key="row.id" :value="row">{{ row.order_number }} · {{ money(row.total_amount) }}</option></select></label><label>Item<select v-model="executionForm.order_item_id" required><option v-for="row in selectedOrder?.items || []" :key="row.id" :value="row.id">{{ row.description }}</option></select></label><div class="cols"><label>Quantidade<input v-model="executionForm.quantity" type="number" min="0.0001" step="0.0001" required /></label><label>Data/hora<input v-model="executionForm.scheduled_at" type="datetime-local" /></label></div><button class="primary" :disabled="!selectedOrder">Agendar</button></form></section>
      <section class="panel"><div class="panel-title"><h2>Pedidos</h2><span>{{ orders.length }}</span></div><table><thead><tr><th>Número</th><th>Assinante</th><th>Total</th><th>Financeiro</th><th>Fiscal</th><th>Estado</th><th>Ações</th></tr></thead><tbody><tr v-for="row in orders" :key="row.id"><td>{{ row.order_number }}</td><td>{{ row.subscriber_name || row.subscriber_person_id || '—' }}</td><td>{{ money(row.total_amount) }}</td><td>{{ row.charge_state || row.charge?.state || '—' }}</td><td>{{ row.fiscal_status }}</td><td><span class="pill">{{ row.status }}</span></td><td><button class="small" @click="showOrder(row)">Detalhes</button><button v-if="row.status==='draft'" class="small" @click="orderAction(row,'confirm')">Confirmar</button><button v-if="row.status==='confirmed'" class="small" @click="orderAction(row,'start')">Iniciar</button><button v-if="row.status==='in_progress'" class="small" @click="orderAction(row,'complete')">Concluir</button><button v-if="!['cancelled','completed'].includes(row.status)" class="small" @click="orderAction(row,'cancel')">Cancelar</button></td></tr></tbody></table></section>
      <section class="panel"><div class="panel-title"><h2>Execuções</h2><span>{{ executions.length }}</span></div><table><thead><tr><th>Pedido</th><th>Programação</th><th>Quantidade</th><th>Estado</th><th>Ações</th></tr></thead><tbody><tr v-for="row in executions" :key="row.id"><td>{{ row.order_number || row.order_id }}</td><td>{{ dateTime(row.scheduled_at) }}</td><td>{{ row.completed_quantity || row.quantity }}</td><td>{{ row.status }}</td><td><button v-if="row.status==='scheduled'" class="small" @click="executionAction(row,'start')">Iniciar</button><button v-if="row.status==='in_progress'" class="small" @click="executionAction(row,'complete')">Concluir</button><button v-if="!['completed','cancelled'].includes(row.status)" class="small" @click="executionAction(row,'cancel')">Cancelar</button></td></tr></tbody></table></section>
    </template>

    <template v-else>
      <section class="panel"><div class="panel-title"><h2>Eventos fiscais de serviços</h2><span>{{ fiscalEvents.length }}</span></div><table><thead><tr><th>Origem</th><th>Gatilho</th><th>Classificação</th><th>Provider</th><th>Falha</th><th>Atualização</th></tr></thead><tbody><tr v-for="row in fiscalEvents" :key="row.id"><td>{{ row.source_type }} / {{ row.source_id }}</td><td>{{ row.trigger_type }}</td><td>{{ row.classification_status }}</td><td><span class="pill" :class="row.status==='not_configured'?'warn':row.status==='blocked_validation'?'danger':'ok'">{{ row.status }}</span></td><td>{{ row.failure_code || '—' }}</td><td>{{ dateTime(row.updated_at) }}</td></tr><tr v-if="!fiscalEvents.length"><td colspan="6" class="empty">Nenhum evento fiscal de serviço.</td></tr></tbody></table></section>
    </template>
  </div>
</template>

<style scoped>
.service-tabs{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}.service-tabs button{border:1px solid var(--line,#d9e0e7);background:var(--surface,#fff);padding:10px 14px;border-radius:10px;cursor:pointer}.service-tabs button.selected{border-color:var(--brand-primary);box-shadow:0 0 0 1px var(--brand-primary)}.service-tabs .refresh{margin-left:auto}.rows>div{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line,#e5e7eb)}.rows>div:last-child{border-bottom:0}.rows>div>div{display:flex;flex-direction:column}.rows small{opacity:.7}textarea{resize:vertical}@media(max-width:800px){.service-tabs .refresh{margin-left:0}.rows>div{align-items:flex-start;flex-direction:column}}
</style>
