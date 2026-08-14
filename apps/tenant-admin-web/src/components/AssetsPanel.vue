<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

type Row = Record<string, any>;
const props = defineProps<{ api: any }>();
const emit = defineEmits<{
  error: [message: string];
  notice: [message: string];
}>();

const loading = ref(false);
const locations = ref<Row[]>([]);
const assets = ref<Row[]>([]);
const people = ref<Row[]>([]);
const products = ref<Row[]>([]);
const suppliers = ref<Row[]>([]);
const selectedAsset = ref<Row | null>(null);
const selectedMaintenance = ref<Row | null>(null);
const selectedLoan = ref<Row | null>(null);
const today = new Date().toISOString().slice(0, 10);
const month = new Date().toISOString().slice(0, 7);

const locationForm = reactive({ code: "", name: "", parent_id: "" });
const assetForm = reactive({
  tag: "",
  name: "",
  location_id: "",
  product_id: "",
  receipt_item_id: "",
  description: "",
  serial_number: "",
  responsible_person_id: "",
  acquisition_date: today,
  acquisition_cost: "0",
  useful_life_months: 60 as number | null,
  residual_value: "0",
  warranty_until: "",
});
const transferForm = reactive({
  location_id: "",
  responsible_person_id: "",
  reason: "Transferência patrimonial autorizada.",
});
const maintenanceForm = reactive({
  maintenance_type: "preventive",
  scheduled_on: today,
  supplier_id: "",
  estimated_cost: "0",
  description: "",
});
const maintenanceCompleteForm = reactive({
  result_notes: "Serviço concluído e bem liberado.",
  actual_cost: "0",
});
const loanForm = reactive({
  borrower_person_id: "",
  expected_return_at: "",
  condition_out: "Bem entregue em condições regulares de uso.",
});
const loanReturnForm = reactive({ condition_in: "Bem devolvido e conferido." });
const depreciationForm = reactive({ competence: month });

const movements = computed(
  () => selectedAsset.value?.movements ?? selectedAsset.value?.events ?? [],
);
const maintenances = computed(() => selectedAsset.value?.maintenances ?? []);
const loans = computed(() => selectedAsset.value?.loans ?? []);
const depreciations = computed(() => selectedAsset.value?.depreciations ?? []);

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return (
    candidate.problem?.detail ||
    (error instanceof Error ? error.message : "Erro inesperado")
  );
}
function idempotency(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
async function request<T = Row>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return props.api.request(path, init) as Promise<T>;
}
async function post<T = Row>(
  path: string,
  body: unknown,
  key?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (key) headers["Idempotency-Key"] = key;
  return request<T>(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}
function nullable(value: string): string | null {
  return value.trim() ? value.trim() : null;
}
function money(value: any): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value ?? 0));
}
function dateTime(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    const [
      locationResult,
      assetResult,
      peopleResult,
      productResult,
      supplierResult,
    ] = await Promise.all([
      request<Row>("/asset-locations?limit=300"),
      request<Row>("/assets?limit=300"),
      request<Row>("/people?limit=300"),
      request<Row>("/products?limit=300"),
      request<Row>("/suppliers?limit=300"),
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
  } catch (error) {
    emit("error", message(error));
  } finally {
    loading.value = false;
  }
}
async function createLocation(): Promise<void> {
  try {
    await post(
      "/asset-locations",
      {
        code: locationForm.code,
        name: locationForm.name,
        parent_id: nullable(locationForm.parent_id),
      },
      idempotency("asset-location"),
    );
    Object.assign(locationForm, { code: "", name: "", parent_id: "" });
    emit("notice", "Localização patrimonial cadastrada.");
    await load();
  } catch (error) {
    emit("error", message(error));
  }
}
async function createAsset(): Promise<void> {
  try {
    const created = await post<Row>(
      "/assets",
      {
        tag: assetForm.tag,
        name: assetForm.name,
        location_id: assetForm.location_id,
        product_id: nullable(assetForm.product_id),
        receipt_item_id: nullable(assetForm.receipt_item_id),
        description: nullable(assetForm.description),
        serial_number: nullable(assetForm.serial_number),
        responsible_person_id: nullable(assetForm.responsible_person_id),
        acquisition_date: assetForm.acquisition_date,
        acquisition_cost: assetForm.acquisition_cost,
        useful_life_months: assetForm.useful_life_months || null,
        residual_value: assetForm.residual_value,
        warranty_until: nullable(assetForm.warranty_until),
        metadata: {},
      },
      idempotency("asset"),
    );
    Object.assign(assetForm, {
      tag: "",
      name: "",
      location_id: assetForm.location_id,
      product_id: assetForm.product_id,
      receipt_item_id: "",
      description: "",
      serial_number: "",
      responsible_person_id: assetForm.responsible_person_id,
      acquisition_date: today,
      acquisition_cost: "0",
      useful_life_months: 60,
      residual_value: "0",
      warranty_until: "",
    });
    emit("notice", "Bem patrimonial incorporado.");
    await load();
    await showAsset(created);
  } catch (error) {
    emit("error", message(error));
  }
}
async function showAsset(row: Row): Promise<void> {
  try {
    selectedAsset.value = await request<Row>(`/assets/${row.id}`);
    transferForm.location_id =
      selectedAsset.value.location_id ?? locations.value[0]?.id ?? "";
    transferForm.responsible_person_id =
      selectedAsset.value.responsible_person_id ?? "";
    selectedMaintenance.value =
      maintenances.value.find((item: Row) =>
        ["scheduled", "in_progress"].includes(item.status),
      ) ?? null;
    selectedLoan.value =
      loans.value.find((item: Row) => item.status === "active") ?? null;
  } catch (error) {
    emit("error", message(error));
  }
}
async function transferAsset(): Promise<void> {
  if (!selectedAsset.value) return;
  try {
    selectedAsset.value = await post<Row>(
      `/assets/${selectedAsset.value.id}/transfers`,
      {
        ...transferForm,
        responsible_person_id: nullable(transferForm.responsible_person_id),
      },
    );
    emit("notice", "Transferência patrimonial registrada.");
    await load();
    await showAsset(selectedAsset.value.asset ?? selectedAsset.value);
  } catch (error) {
    emit("error", message(error));
  }
}
async function createMaintenance(): Promise<void> {
  if (!selectedAsset.value) return;
  try {
    selectedMaintenance.value = await post<Row>(
      `/assets/${selectedAsset.value.id}/maintenances`,
      {
        ...maintenanceForm,
        scheduled_on: nullable(maintenanceForm.scheduled_on),
        supplier_id: nullable(maintenanceForm.supplier_id),
      },
      idempotency("asset-maintenance"),
    );
    emit("notice", "Manutenção agendada.");
    await load();
    await showAsset(selectedAsset.value);
  } catch (error) {
    emit("error", message(error));
  }
}
async function startMaintenance(row: Row): Promise<void> {
  try {
    await post(`/asset-maintenances/${row.id}/start`, {});
    emit("notice", "Manutenção iniciada.");
    if (selectedAsset.value) await showAsset(selectedAsset.value);
    await load();
  } catch (error) {
    emit("error", message(error));
  }
}
async function completeMaintenance(row: Row): Promise<void> {
  try {
    await post(`/asset-maintenances/${row.id}/complete`, {
      result_notes: maintenanceCompleteForm.result_notes,
      actual_cost: maintenanceCompleteForm.actual_cost || null,
    });
    emit("notice", "Manutenção concluída.");
    if (selectedAsset.value) await showAsset(selectedAsset.value);
    await load();
  } catch (error) {
    emit("error", message(error));
  }
}
async function createLoan(): Promise<void> {
  if (!selectedAsset.value) return;
  try {
    selectedLoan.value = await post<Row>(
      `/assets/${selectedAsset.value.id}/loans`,
      {
        borrower_person_id: loanForm.borrower_person_id,
        expected_return_at: loanForm.expected_return_at
          ? new Date(loanForm.expected_return_at).toISOString()
          : null,
        condition_out: nullable(loanForm.condition_out),
      },
      idempotency("asset-loan"),
    );
    emit("notice", "Empréstimo patrimonial registrado.");
    await load();
    await showAsset(selectedAsset.value);
  } catch (error) {
    emit("error", message(error));
  }
}
async function returnLoan(row: Row): Promise<void> {
  try {
    await post(`/asset-loans/${row.id}/return`, loanReturnForm);
    emit("notice", "Bem devolvido e conferido.");
    if (selectedAsset.value) await showAsset(selectedAsset.value);
    await load();
  } catch (error) {
    emit("error", message(error));
  }
}
async function calculateDepreciation(): Promise<void> {
  if (!selectedAsset.value) return;
  try {
    await post(
      `/assets/${selectedAsset.value.id}/depreciations`,
      depreciationForm,
      idempotency(`asset-depreciation-${depreciationForm.competence}`),
    );
    emit("notice", "Depreciação informativa calculada para a competência.");
    await showAsset(selectedAsset.value);
    await load();
  } catch (error) {
    emit("error", message(error));
  }
}

onMounted(load);
</script>

<template>
  <div class="assets-module">
    <section class="metrics">
      <article>
        <span>Bens ativos</span
        ><strong>{{
          assets.filter(
            (row: Row) => !["disposed", "written_off"].includes(row.status),
          ).length
        }}</strong
        ><small>inventário patrimonial</small>
      </article>
      <article>
        <span>Em empréstimo</span
        ><strong>{{
          assets.filter((row: Row) => row.status === "loaned").length
        }}</strong
        ><small>retorno controlado</small>
      </article>
      <article>
        <span>Em manutenção</span
        ><strong>{{
          assets.filter((row: Row) => row.status === "maintenance").length
        }}</strong
        ><small>preventiva ou corretiva</small>
      </article>
      <article>
        <span>Localizações</span><strong>{{ locations.length }}</strong
        ><small>hierarquia física</small>
      </article>
      <article>
        <span>Valor de aquisição</span
        ><strong>{{
          money(
            assets.reduce(
              (sum: number, row: Row) =>
                sum + Number(row.acquisition_cost || 0),
              0,
            ),
          )
        }}</strong
        ><small>base informativa</small>
      </article>
    </section>
    <section class="grid-2 forms">
      <form class="panel" @submit.prevent="createLocation">
        <h2>Nova localização</h2>
        <div class="cols">
          <label>Código<input v-model="locationForm.code" required /></label
          ><label
            >Local superior<select v-model="locationForm.parent_id">
              <option value="">Raiz</option>
              <option v-for="row in locations" :key="row.id" :value="row.id">
                {{ row.name }}
              </option>
            </select></label
          >
        </div>
        <label>Nome<input v-model="locationForm.name" required /></label
        ><button class="primary">Cadastrar localização</button>
      </form>
      <form class="panel" @submit.prevent="createAsset">
        <h2>Incorporar bem</h2>
        <div class="cols">
          <label>Etiqueta<input v-model="assetForm.tag" required /></label
          ><label
            >Número de série<input v-model="assetForm.serial_number"
          /></label>
        </div>
        <label
          >Bem patrimonial<input v-model="assetForm.name" required
        /></label>
        <div class="cols">
          <label
            >Localização<select v-model="assetForm.location_id" required>
              <option v-for="row in locations" :key="row.id" :value="row.id">
                {{ row.name }}
              </option>
            </select></label
          ><label
            >Responsável<select v-model="assetForm.responsible_person_id">
              <option value="">Sem responsável</option>
              <option v-for="row in people" :key="row.id" :value="row.id">
                {{ row.full_name }}
              </option>
            </select></label
          >
        </div>
        <div class="cols">
          <label
            >Produto<select v-model="assetForm.product_id">
              <option value="">Sem vínculo</option>
              <option v-for="row in products" :key="row.id" :value="row.id">
                {{ row.name }}
              </option>
            </select></label
          ><label
            >Item do recebimento<input
              v-model="assetForm.receipt_item_id"
              placeholder="UUID opcional"
          /></label>
        </div>
        <div class="cols">
          <label
            >Aquisição<input
              v-model="assetForm.acquisition_date"
              type="date"
              required /></label
          ><label
            >Custo<input
              v-model="assetForm.acquisition_cost"
              type="number"
              min="0"
              step="0.01"
              required
          /></label>
        </div>
        <div class="cols">
          <label
            >Vida útil (meses)<input
              v-model.number="assetForm.useful_life_months"
              type="number"
              min="1" /></label
          ><label
            >Valor residual<input
              v-model="assetForm.residual_value"
              type="number"
              min="0"
              step="0.01"
          /></label>
        </div>
        <button class="primary">Incorporar patrimônio</button>
      </form>
    </section>
    <section class="panel">
      <div class="panel-title">
        <h2>Bens patrimoniais</h2>
        <div>
          <span>{{ assets.length }} registros</span
          ><button class="small" :disabled="loading" @click="load">
            {{ loading ? "Atualizando…" : "Atualizar" }}
          </button>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Etiqueta</th>
            <th>Bem</th>
            <th>Localização</th>
            <th>Responsável</th>
            <th>Valor líquido</th>
            <th>Estado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in assets" :key="row.id">
            <td>{{ row.tag }}</td>
            <td>{{ row.name }}</td>
            <td>{{ row.location_name || row.location_id }}</td>
            <td>{{ row.responsible_name || "—" }}</td>
            <td>{{ money(row.net_book_value ?? row.acquisition_cost) }}</td>
            <td>
              <span
                class="pill"
                :class="
                  row.status === 'active'
                    ? 'ok'
                    : row.status === 'maintenance'
                      ? 'warn'
                      : ''
                "
                >{{ row.status }}</span
              >
            </td>
            <td>
              <button class="small" @click="showAsset(row)">Detalhes</button>
            </td>
          </tr>
          <tr v-if="!assets.length">
            <td colspan="7" class="empty">Nenhum bem incorporado.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <template v-if="selectedAsset">
      <section class="panel">
        <div class="panel-title">
          <div>
            <h2>{{ selectedAsset.name }}</h2>
            <small
              >{{ selectedAsset.tag }} ·
              {{ selectedAsset.serial_number || "sem série" }} ·
              {{ selectedAsset.status }}</small
            >
          </div>
          <button class="small" @click="selectedAsset = null">
            Fechar detalhes
          </button>
        </div>
        <div class="metrics">
          <article>
            <span>Custo</span
            ><strong>{{ money(selectedAsset.acquisition_cost) }}</strong
            ><small>{{ selectedAsset.acquisition_date }}</small>
          </article>
          <article>
            <span>Depreciação</span
            ><strong>{{ money(selectedAsset.accumulated_depreciation) }}</strong
            ><small>informativa</small>
          </article>
          <article>
            <span>Valor líquido</span
            ><strong>{{ money(selectedAsset.net_book_value) }}</strong
            ><small>limitado ao residual</small>
          </article>
          <article>
            <span>Garantia</span
            ><strong>{{ selectedAsset.warranty_until || "—" }}</strong
            ><small>vigência cadastrada</small>
          </article>
        </div>
      </section>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="transferAsset">
          <h2>Transferir bem</h2>
          <label
            >Destino<select v-model="transferForm.location_id" required>
              <option v-for="row in locations" :key="row.id" :value="row.id">
                {{ row.name }}
              </option>
            </select></label
          ><label
            >Novo responsável<select
              v-model="transferForm.responsible_person_id"
            >
              <option value="">Sem responsável</option>
              <option v-for="row in people" :key="row.id" :value="row.id">
                {{ row.full_name }}
              </option>
            </select></label
          ><label
            >Motivo<textarea
              v-model="transferForm.reason"
              rows="3"
              required
            ></textarea></label
          ><button class="primary">Registrar transferência</button>
        </form>
        <form class="panel" @submit.prevent="calculateDepreciation">
          <h2>Depreciação informativa</h2>
          <label
            >Competência<input
              v-model="depreciationForm.competence"
              type="month"
              required
          /></label>
          <p>
            O cálculo é linear, cronológico, idempotente por competência e nunca
            reduz o bem abaixo do valor residual.
          </p>
          <button class="primary">Calcular competência</button>
        </form>
      </section>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createLoan">
          <h2>Novo empréstimo</h2>
          <label
            >Tomador<select v-model="loanForm.borrower_person_id" required>
              <option v-for="row in people" :key="row.id" :value="row.id">
                {{ row.full_name }}
              </option>
            </select></label
          ><label
            >Retorno esperado<input
              v-model="loanForm.expected_return_at"
              type="datetime-local" /></label
          ><label
            >Condição de saída<textarea
              v-model="loanForm.condition_out"
              rows="3"
            ></textarea></label
          ><button class="primary" :disabled="!!selectedLoan">
            Registrar empréstimo
          </button>
        </form>
        <form class="panel" @submit.prevent="createMaintenance">
          <h2>Agendar manutenção</h2>
          <div class="cols">
            <label
              >Tipo<select v-model="maintenanceForm.maintenance_type">
                <option value="preventive">Preventiva</option>
                <option value="corrective">Corretiva</option>
                <option value="inspection">Inspeção</option>
              </select></label
            ><label
              >Data<input v-model="maintenanceForm.scheduled_on" type="date"
            /></label>
          </div>
          <label
            >Fornecedor<select v-model="maintenanceForm.supplier_id">
              <option value="">Equipe interna</option>
              <option v-for="row in suppliers" :key="row.id" :value="row.id">
                {{ row.trade_name || row.legal_name }}
              </option>
            </select></label
          >
          <div class="cols">
            <label
              >Custo estimado<input
                v-model="maintenanceForm.estimated_cost"
                type="number"
                min="0"
                step="0.01" /></label
            ><label
              >Descrição<input v-model="maintenanceForm.description" required
            /></label>
          </div>
          <button class="primary" :disabled="!!selectedLoan">
            Agendar manutenção
          </button>
        </form>
      </section>
      <section class="grid-2">
        <div class="panel">
          <div class="panel-title">
            <h2>Empréstimos</h2>
            <span>{{ loans.length }}</span>
          </div>
          <div class="rows">
            <div v-for="row in loans" :key="row.id">
              <div>
                <strong>{{
                  row.borrower_name || row.borrower_person_id
                }}</strong
                ><small
                  >{{ row.status }} · retorno
                  {{ dateTime(row.expected_return_at) }}</small
                >
              </div>
              <button
                v-if="row.status === 'active'"
                class="small"
                @click="returnLoan(row)"
              >
                Registrar devolução
              </button>
            </div>
            <div v-if="!loans.length" class="empty">Nenhum empréstimo.</div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-title">
            <h2>Manutenções</h2>
            <span>{{ maintenances.length }}</span>
          </div>
          <div class="rows">
            <div v-for="row in maintenances" :key="row.id">
              <div>
                <strong>{{ row.maintenance_type }}</strong
                ><small
                  >{{ row.status }} · {{ row.scheduled_on || "sem data" }} ·
                  {{ money(row.actual_cost ?? row.estimated_cost) }}</small
                >
              </div>
              <div>
                <button
                  v-if="row.status === 'scheduled'"
                  class="small"
                  @click="startMaintenance(row)"
                >
                  Iniciar</button
                ><button
                  v-if="row.status === 'in_progress'"
                  class="small"
                  @click="completeMaintenance(row)"
                >
                  Concluir
                </button>
              </div>
            </div>
            <div v-if="!maintenances.length" class="empty">
              Nenhuma manutenção.
            </div>
          </div>
        </div>
      </section>
      <section class="grid-2">
        <div class="panel">
          <div class="panel-title">
            <h2>Movimentações</h2>
            <span>{{ movements.length }}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Origem</th>
                <th>Destino</th>
                <th>Responsável</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in movements" :key="row.id">
                <td>{{ row.movement_type || row.event_type }}</td>
                <td>
                  {{ row.from_location_name || row.from_location_id || "—" }}
                </td>
                <td>{{ row.to_location_name || row.to_location_id || "—" }}</td>
                <td>
                  {{ row.responsible_name || row.responsible_person_id || "—" }}
                </td>
                <td>{{ dateTime(row.created_at || row.occurred_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="panel">
          <div class="panel-title">
            <h2>Depreciações</h2>
            <span>{{ depreciations.length }}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Competência</th>
                <th>Valor</th>
                <th>Acumulada</th>
                <th>Valor líquido</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in depreciations" :key="row.id">
                <td>{{ row.competence }}</td>
                <td>{{ money(row.amount) }}</td>
                <td>{{ money(row.accumulated_amount) }}</td>
                <td>{{ money(row.net_book_value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.rows > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line, #e5e7eb);
}
.rows > div:last-child {
  border-bottom: 0;
}
.rows > div > div {
  display: flex;
  flex-direction: column;
}
.rows small {
  opacity: 0.7;
}
textarea {
  resize: vertical;
}
@media (max-width: 800px) {
  .rows > div {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
