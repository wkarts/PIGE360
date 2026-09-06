<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row = Record<string, any>;

const props = defineProps<{
  api: Pige360SessionClient;
  tenants: Row[];
}>();

const emit = defineEmits<{
  feedback: [value: { type: "success" | "error"; message: string }];
}>();

const loading = ref(false);
const tenantLoading = ref(false);
const partners = ref<Row[]>([]);
const plans = ref<Row[]>([]);
const entitlements = ref<Row | null>(null);
const selectedTenantId = ref("");
const selectedPartnerId = ref("");
const currentSubscriptionPlanId = ref("");
const partnerReason = ref("");
const planReason = ref("");
const linkedPartnerId = computed(() => String(entitlements.value?.partner?.id || ""));
const selectablePartners = computed(() => partners.value.filter((item: Row) => (
  item.status === "active" || item.id === linkedPartnerId.value
)));
const selectableSubscriptionPlans = computed(() => plans.value.filter((item: Row) => (
  item.status === "active" || item.id === currentSubscriptionPlanId.value
)));
const selectedPartnerIsActive = computed(() => Boolean(
  partners.value.find((partner: Row) => partner.id === selectedPartnerId.value)?.status === "active",
));
const currentSubscriptionPlanUnavailable = computed(() => Boolean(
  currentSubscriptionPlanId.value
  && plans.value.find((plan: Row) => plan.id === currentSubscriptionPlanId.value)?.status !== "active",
));

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

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return candidate?.problem?.detail || candidate?.message || "Erro inesperado";
}

function idempotencyKey(scope: string): string {
  return `${scope}:${crypto.randomUUID()}`;
}

function parseMap(value: string, label: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} deve ser um objeto JSON.`);
  }
  return parsed as Record<string, unknown>;
}

async function mutate<T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body: Row, scope: string): Promise<T> {
  return props.api.request<T>(path, {
    method,
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey(scope) },
    body: JSON.stringify(body),
  });
}

async function loadCatalog() {
  loading.value = true;
  try {
    const [partnerData, planData] = await Promise.all([
      props.api.request<Row>("/platform/commercial/partners?limit=200"),
      props.api.request<Row>("/platform/commercial/plans?include_archived=true"),
    ]);
    partners.value = partnerData.items || [];
    plans.value = planData.items || [];
    if (!subscriptionForm.plan_id) {
      subscriptionForm.plan_id = plans.value.find((plan: Row) => plan.status === "active")?.id || "";
    }
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  } finally {
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
      props.api.request<Row>(`/platform/commercial/tenants/${tenantId}/subscription`),
      props.api.request<Row>(`/platform/commercial/tenants/${tenantId}/entitlements?period=${period}`),
      props.api.request<Row>(`/platform/commercial/tenants/${tenantId}/usage?period=${period}`),
    ]);
    if (
      sequence !== tenantLoadSequence
      || tenantId !== selectedTenantId.value
      || period !== usageForm.period
      || source !== usageForm.source
    ) return;
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
    const snapshot = (usageData.items || []).find((item: Row) => item.source === source);
    if (snapshot) {
      usageForm.version = snapshot.version;
      usageForm.metrics_json = JSON.stringify(snapshot.metrics, null, 2);
    }
    entitlements.value = entitlementData;
    selectedPartnerId.value = entitlementData.partner?.id || "";
  } catch (error) {
    if (sequence === tenantLoadSequence) emit("feedback", { type: "error", message: message(error) });
  } finally {
    if (sequence === tenantLoadSequence) tenantLoading.value = false;
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
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function changePartner(target: "suspend" | "reactivate" | "archive", partner: Row) {
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
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function linkTenant(unlink = false) {
  const partner = partners.value.find((item: Row) => item.id === selectedPartnerId.value);
  if (!partner || !selectedTenantId.value || partnerReason.value.trim().length < 10) {
    emit("feedback", { type: "error", message: "Selecione parceiro e tenant e informe o motivo do vínculo." });
    return;
  }
  if (!unlink && partner.status !== "active") {
    emit("feedback", { type: "error", message: "Somente parceiro ativo pode receber um novo vínculo." });
    return;
  }
  try {
    const result = await mutate<Row>(
      `/platform/commercial/partners/${partner.id}/tenants/${selectedTenantId.value}`,
      unlink ? "DELETE" : "PUT",
      { reason: partnerReason.value },
      unlink ? "partner-unlink" : "partner-link",
    );
    partnerReason.value = "";
    const successMessage = unlink ? "Tenant desvinculado." : "Tenant vinculado ao parceiro.";
    const noChangeMessage = unlink
      ? "Nenhuma alteração: o tenant já estava desvinculado deste parceiro."
      : "Nenhuma alteração: o tenant já estava vinculado a este parceiro.";
    emit("feedback", { type: "success", message: result.changed ? successMessage : noChangeMessage });
    await Promise.all([loadCatalog(), loadTenantCommercial()]);
  } catch (error) {
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
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function togglePlan(plan: Row) {
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
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function archivePlan(plan: Row) {
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
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function saveSubscription() {
  if (!selectedTenantId.value || !subscriptionForm.plan_id || subscriptionForm.reason.trim().length < 10) {
    emit("feedback", { type: "error", message: "Selecione tenant/plano e informe o motivo da assinatura." });
    return;
  }
  const selectedPlan = plans.value.find((plan: Row) => plan.id === subscriptionForm.plan_id);
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
    const result = await mutate<Row>(`/platform/commercial/tenants/${selectedTenantId.value}/subscription`, "PUT", {
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
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

async function saveUsage() {
  if (!selectedTenantId.value || usageForm.reason.trim().length < 10) {
    emit("feedback", { type: "error", message: "Selecione o tenant e informe o motivo do snapshot." });
    return;
  }
  try {
    const result = await mutate<Row>(
      `/platform/commercial/tenants/${selectedTenantId.value}/usage/${usageForm.period}`,
      "PUT",
      {
        expected_version: usageForm.version,
        source: usageForm.source,
        metrics: parseMap(usageForm.metrics_json, "Métricas"),
        reason: usageForm.reason,
      },
      "usage-set",
    );
    usageForm.version = result.version;
    usageForm.reason = "";
    emit("feedback", { type: "success", message: "Snapshot de uso registrado." });
    await loadTenantCommercial();
  } catch (error) {
    emit("feedback", { type: "error", message: message(error) });
  }
}

watch(() => props.tenants, (value: Row[]) => {
  if (!selectedTenantId.value) selectedTenantId.value = value[0]?.id || "";
}, { immediate: true });
watch(selectedTenantId, loadTenantCommercial);
watch(() => usageForm.period, loadTenantCommercial);
watch(() => usageForm.source, loadTenantCommercial);
onMounted(async () => {
  await loadCatalog();
  await loadTenantCommercial();
});
</script>

<template>
  <section class="commercial-panel" aria-labelledby="commercial-title">
    <header>
      <div>
        <span class="eyebrow">Control Plane</span>
        <h2 id="commercial-title">Administração comercial</h2>
        <p>Parceiros, catálogo, assinaturas manuais e uso por tenant.</p>
      </div>
      <button class="secondary" :disabled="loading" @click="loadCatalog">Atualizar</button>
    </header>

    <div class="commercial-grid">
      <article>
        <h3>Novo parceiro</h3>
        <form @submit.prevent="createPartner">
          <label>Código<input v-model="partnerForm.code" required minlength="2" /></label>
          <label>Razão social<input v-model="partnerForm.legal_name" required /></label>
          <label>Nome comercial<input v-model="partnerForm.trade_name" required /></label>
          <label>E-mail<input v-model="partnerForm.contact_email" type="email" /></label>
          <label>Observações<textarea v-model="partnerForm.notes" rows="2" /></label>
          <button class="primary" type="submit">Cadastrar parceiro</button>
        </form>
      </article>

      <article>
        <h3>Novo plano</h3>
        <form @submit.prevent="createPlan">
          <label>Código<input v-model="planForm.code" required minlength="2" /></label>
          <label>Nome<input v-model="planForm.name" required /></label>
          <label>Preço em centavos<input v-model.number="planForm.price_minor" type="number" min="0" /></label>
          <label>Periodicidade
            <select v-model="planForm.billing_interval"><option value="monthly">Mensal</option><option value="annual">Anual</option><option value="custom">Personalizada</option></select>
          </label>
          <label>Features JSON<textarea v-model="planForm.features_json" rows="2" /></label>
          <label>Limites JSON<textarea v-model="planForm.limits_json" rows="2" /></label>
          <button class="primary" type="submit">Cadastrar plano</button>
        </form>
      </article>
    </div>

    <article class="wide">
      <h3>Parceiros cadastrados</h3>
      <label>Motivo das ações<input v-model="partnerReason" placeholder="Obrigatório para lifecycle e vínculos" /></label>
      <div v-if="partners.length" class="rows">
        <div v-for="partner in partners" :key="partner.id" class="row">
          <div><strong>{{ partner.trade_name }}</strong><small>{{ partner.code }} · {{ partner.status }} · {{ partner.tenant_count }} tenant(s)</small></div>
          <div class="actions">
            <button v-if="partner.status === 'active'" class="secondary" @click="changePartner('suspend', partner)">Suspender</button>
            <button v-if="partner.status === 'suspended'" class="secondary" @click="changePartner('reactivate', partner)">Reativar</button>
            <button v-if="partner.status !== 'archived'" class="danger" @click="changePartner('archive', partner)">Arquivar</button>
          </div>
        </div>
      </div>
      <p v-else class="empty">Nenhum parceiro cadastrado.</p>
    </article>

    <article class="wide">
      <h3>Catálogo de planos</h3>
      <label>Motivo das ações<input v-model="planReason" placeholder="Obrigatório para disponibilidade e arquivo" /></label>
      <div v-if="plans.length" class="rows">
        <div v-for="plan in plans" :key="plan.id" class="row">
          <div><strong>{{ plan.name }}</strong><small>{{ plan.code }} · {{ plan.status }} · {{ plan.currency }} {{ (plan.price_minor / 100).toFixed(2) }}</small></div>
          <div class="actions">
            <button v-if="plan.status !== 'archived'" class="secondary" @click="togglePlan(plan)">{{ plan.status === "active" ? "Desativar venda" : "Ativar venda" }}</button>
            <button v-if="plan.status !== 'archived'" class="danger" @click="archivePlan(plan)">Arquivar</button>
          </div>
        </div>
      </div>
    </article>

    <article class="wide tenant-admin">
      <h3>Tenant, assinatura e uso</h3>
      <div class="selectors">
        <label>Tenant<select v-model="selectedTenantId"><option value="">Selecione</option><option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{ tenant.trade_name }} ({{ tenant.code }})</option></select></label>
        <label>Parceiro<select v-model="selectedPartnerId"><option value="">Selecione</option><option v-for="partner in selectablePartners" :key="partner.id" :value="partner.id">{{ partner.trade_name }}<template v-if="partner.status !== 'active'"> · {{ partner.status }} (vínculo atual)</template></option></select></label>
        <div class="actions align-end"><button class="secondary" :disabled="!selectedPartnerId || !selectedPartnerIsActive" @click="linkTenant(false)">Vincular</button><button class="secondary" :disabled="!linkedPartnerId || selectedPartnerId !== linkedPartnerId" @click="linkTenant(true)">Desvincular</button></div>
      </div>

      <div class="commercial-grid">
        <form @submit.prevent="saveSubscription">
          <h4>Assinatura manual</h4>
          <label>Plano<select v-model="subscriptionForm.plan_id" required><option value="">Selecione</option><option v-for="plan in selectableSubscriptionPlans" :key="plan.id" :value="plan.id">{{ plan.name }}<template v-if="plan.status !== 'active'"> · {{ plan.status }} (plano atual)</template></option></select></label>
          <small v-if="currentSubscriptionPlanUnavailable" class="commercial-warning">O plano atual não aceita nova ativação. Cancele esta assinatura ou migre para um plano ativo.</small>
          <label>Status<select v-model="subscriptionForm.status"><option value="active">Ativa</option><option value="trialing">Teste</option><option value="suspended">Suspensa</option><option value="canceled">Cancelada</option></select></label>
          <label>Motivo<input v-model="subscriptionForm.reason" required minlength="10" /></label>
          <button class="primary" type="submit" :disabled="tenantLoading">Salvar assinatura</button>
        </form>

        <form @submit.prevent="saveUsage">
          <h4>Snapshot de uso</h4>
          <label>Período<input v-model="usageForm.period" type="month" required /></label>
          <label>Origem<input v-model="usageForm.source" required /></label>
          <label>Métricas JSON<textarea v-model="usageForm.metrics_json" rows="3" /></label>
          <label>Motivo<input v-model="usageForm.reason" required minlength="10" /></label>
          <button class="primary" type="submit" :disabled="tenantLoading">Registrar uso</button>
        </form>
      </div>

      <div v-if="entitlements" class="entitlement-summary">
        <strong>Entitlements: {{ entitlements.entitlements?.enabled ? "habilitados" : "indisponíveis" }}</strong>
        <span>Plano: {{ entitlements.plan?.name || "não configurado" }}</span>
        <span>Uso: {{ JSON.stringify(entitlements.entitlements?.usage || {}) }}</span>
        <span>Saldo: {{ JSON.stringify(entitlements.entitlements?.remaining || {}) }}</span>
        <small>Cobrança automática externa: não habilitada.</small>
      </div>
    </article>
  </section>
</template>

<style scoped>
.commercial-panel{display:grid;gap:16px;margin:20px 0}.commercial-panel>header{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.commercial-panel h2,.commercial-panel h3,.commercial-panel h4{margin:0}.commercial-panel p{color:#687780;margin:5px 0}.commercial-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.commercial-grid>article,.commercial-grid>form,.wide{background:#fff;border:1px solid #dfe7ea;border-radius:16px;padding:18px}.commercial-panel form{display:grid;gap:10px;margin-top:12px}.wide{display:grid;gap:12px}.rows{display:grid}.row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid #edf1f3}.row:first-child{border-top:0}.row>div:first-child{display:grid;gap:4px}.row small,.entitlement-summary small{color:#687780}.actions{display:flex;gap:8px;flex-wrap:wrap}.secondary,.danger{border:1px solid #cbd8dc;border-radius:9px;background:#fff;padding:8px 10px;cursor:pointer}.secondary:disabled{cursor:not-allowed;opacity:.55}.danger{border-color:#e2b0b0;color:#8f2c2c}.selectors{display:grid;grid-template-columns:1fr 1fr auto;gap:10px}.align-end{align-items:end}.tenant-admin{gap:16px}.commercial-warning{background:#fff0dd;border-radius:9px;color:#85500a;padding:9px}.entitlement-summary{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:#f2f7f7;border-radius:12px;padding:12px}.entitlement-summary strong{color:#006d77}.empty{font-size:13px}@media(max-width:800px){.commercial-grid,.selectors{grid-template-columns:1fr}.row{align-items:flex-start;display:grid}}
</style>
