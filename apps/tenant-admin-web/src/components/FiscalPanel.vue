<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

type Row = Record<string, any>;
type ScopeForm = { operation_type: string; item_kind: string; recipient_scope: string; document_type: string };
type ApiSessionClient = { request<T = unknown>(path: string, init?: RequestInit): Promise<T>; response(path: string, init?: RequestInit): Promise<Response> };

const props = defineProps<{ api: ApiSessionClient }>();
const emit = defineEmits<{ error: [message: string]; notice: [message: string] }>();

const loading = ref(false);
const tab = ref<"contexts" | "catalogs" | "engine" | "strategies" | "routing" | "documents" | "rules">("contexts");
const contexts = ref<Row[]>([]);
const documents = ref<Row[]>([]);
const fiscalProviders = ref<Row[]>([]);
const fiscalCertificates = ref<Row[]>([]);
const fiscalInutilizations = ref<Row[]>([]);
const documentSchemas = ref<Row[]>([]);
const routingPolicies = ref<Row[]>([]);
const fiscalAssemblies = ref<Row[]>([]);
const emissionTriggerRuns = ref<Row[]>([]);
const rules = ref<Row[]>([]);
const catalogs = ref<Row[]>([]);
const catalogSources = ref<Row[]>([]);
const catalogImports = ref<Row[]>([]);
const catalogGovernance = ref<Row | null>(null);
const catalogQuarantine = ref<Row[]>([]);
const catalogImportFile = ref<File | null>(null);
const classificationRules = ref<Row[]>([]);
const taxRuleSets = ref<Row[]>([]);
const taxCalculation = ref<Row | null>(null);
const legalSources = ref<Row[]>([]);
const strategyRules = ref<Row[]>([]);
const ibptStatus = ref<Row | null>(null);
const ibptSnapshots = ref<Row[]>([]);
const ibptOffline = ref<Row | null>(null);
const ibptProfiles = ref<Row[]>([]);
const documentTransparency = ref<Row | null>(null);
const deliveryPolicies = ref<Row[]>([]);
const selectedRejection = ref<Row | null>(null);
const selectedArtifactDocument = ref<Row | null>(null);
const selectedArtifacts = ref<Row[]>([]);
const readiness = ref<Row | null>(null);
const connections = ref<Row[]>([]);
const institutions = ref<Row[]>([]);
const units = ref<Row[]>([]);
const selectedContext = ref<Row | null>(null);
const resolved = ref<Row | null>(null);
const today = new Date().toISOString().slice(0, 10);

const contextForm = reactive({
  code: "",
  establishment_name: "",
  legal_name: "",
  cnpj: "",
  institution_id: "",
  unit_id: "",
  state_registration: "",
  municipal_registration: "",
  provider_connection_id: "",
});
const versionForm = reactive({
  tax_regime: "simples_nacional",
  uf: "BA",
  municipality_code: "2927408",
  valid_from: today,
  valid_until: "",
  environment: "homologation",
  rtc_mode: "simulation_only",
  layout_version: "",
  schema_version: "",
  technical_note_version: "",
  ruleset_version: "",
  notes: "",
});
const scopes = ref<ScopeForm[]>([
  { operation_type: "sale", item_kind: "product", recipient_scope: "company", document_type: "NF-e" },
]);
const resolveForm = reactive({
  occurred_on: today,
  operation_type: "sale",
  item_kind: "product",
  recipient_scope: "company",
  document_type: "NF-e",
});
const catalogForm = reactive({ kind: "NCM", name: "NCM", normalization: "digits", code_pattern: "" });
const catalogVersionForm = reactive({ catalog_id: "", version_label: "2026.1", valid_from: today, valid_until: "", source_name: "Fonte oficial configurada", source_reference: "", code: "", description: "" });
const catalogSourceForm = reactive({ catalog_id: "", provider_type: "local_file", provider_key: "local-official", provider_version: "1", import_format: "csv", source_reference: "", encoding: "utf-8", delimiter: ";", max_age_days: 90 });
const catalogImportForm = reactive({ catalog_id: "", source_profile_id: "", version_label: "2026.1", valid_from: today, valid_until: "", auto_publish: false });
const classificationForm = reactive({ fiscal_context_id: "", establishment_code: "", item_kind: "product", item_id: "", operation_type: "sale", valid_from: today, valid_until: "", priority: 100, ncm: "", nbs: "", lc116: "", cfop: "", cest: "", cst: "", csosn: "", cst_ibs_cbs: "", cclasstrib: "", cbenef: "", municipal_code: "", cnae: "" });
const taxRuleForm = reactive({ fiscal_context_id: "", code: "VENDA-PADRAO", name: "Venda padrão", establishment_code: "", operation_type: "sale", item_kind: "product", tax_regime: "any", rtc_mode: "any", priority: 100 });
const taxVersionForm = reactive({ rule_set_id: "", version_label: "2026.1", valid_from: today, valid_until: "", source_name: "Regra tributária parametrizada", source_reference: "", legal_basis: "" });
const taxComponents = ref<Row[]>([
  { tax: "ICMS", incidence: "taxable", base_mode: "operation_total", rate_pct: "0", base_reduction_pct: "0", deferral_pct: "0", suspension_pct: "0", mva_pct: "0", monophase_amount_per_unit: "", deduct_tax_codes: [] },
]);
const taxSimulationForm = reactive({ fiscal_context_id: "", establishment_code: "", operation_type: "sale", item_kind: "product", occurred_on: today, amount: "0.00", quantity: "1", freight: "0.00", insurance: "0.00", other_amount: "0.00", discount: "0.00" });
const legalSourceForm = reactive({ kind: "technical_note", title: "", version_label: "2026.1", valid_from: today, valid_until: "", source_reference: "", source_sha256: "" });
const strategyForm = reactive({ fiscal_context_id: "", establishment_code: "", strategy_type: "withholding", operation_type: "sale", tax_regime: "any", rtc_mode: "any", origin_uf: "", destination_uf: "", valid_from: today, valid_until: "", priority: 100, rate_pct: "0", amount: "0", legal_source_id: "" });
const rtcForm = reactive({ fiscal_context_id: "", establishment_code: "", tax_regime: "any", mode: "optional_emit", valid_from: today, valid_until: "", legal_source_id: "", notes: "" });
const ibptUf = ref("BA");
const ibptProfileForm = reactive({ provider_code: "wwsoftwares", mode: "local_snapshot", valid_from: today, valid_until: "", sync_enabled: false, fallback_enabled: true, fallback_max_age_days: 90, stale_after_days: 120, base_url: "", uf_path: "", notes: "" });
const certificateForm = reactive({ subject_name: "", subject_document: "", serial_number: "", issuer_name: "", valid_from: `${today}T00:00:00Z`, valid_until: `${new Date(Date.now()+365*86400000).toISOString().slice(0,10)}T23:59:59Z`, fingerprint_sha256: "", secret_ref: "" });
const providerForm = reactive({ provider_code: "SefazNfeProvider", display_name: "", document_type: "NF-e", environment: "homologation", endpoint_url: "", secret_ref: "", certificate_metadata_id: "", enabled: false });
const deliveryPolicyForm = reactive({ code: "fiscal-default", name: "Entrega fiscal padrão", document_type: "any", provider_code: "", environment: "any", valid_from: today, valid_until: "", priority: 100, max_attempts: 3, base_delay_seconds: 30, max_delay_seconds: 1800, backoff_multiplier: "2", jitter_seconds: 0, auto_retry: true, contingency_after_attempts: 3, contingency_mode: "offline", notes: "" });
const inutilizationForm = reactive({ fiscal_profile_id: "", provider_configuration_id: "", document_type: "NF-e", year: new Date().getFullYear(), series: "1", start_number: 1, end_number: 1, reason: "" });
const documentSchemaForm = reactive({ document_type: "NF-e", schema_code: "LOCAL-NFE", version_label: "1.0-local", valid_from: today, valid_until: "", root_element: "NFeDoc", namespace_uri: "", source_reference: "fixture/local", xsd_text: "" });
const routingPolicyForm = reactive({ fiscal_context_id: "", code: "VENDA-PADRAO", name: "Roteamento padrão", operation_type: "sale", recipient_scope: "any", channel_scope: "any", product_document_type: "", service_document_type: "NFS-e", trigger_types: ["manual"] as string[], valid_from: today, valid_until: "", priority: 100, financial_cancel_mode: "link_only", fiscal_reversal_debit_account: "", fiscal_reversal_credit_account: "", tax_regime_filter: "", municipality_filter: "", require_financial_contract: false });
const assemblyForm = reactive({ fiscal_context_id: "", fiscal_profile_id: "", source_type: "manual", source_id: "", occurred_on: today, operation_type: "sale", recipient_scope: "individual", channel: "pos", destination_uf: "BA", trigger_type: "manual", recipient_name: "", recipient_document: "", request_emission: false, items_json: '[{"line_id":"1","item_kind":"product","code":"ITEM","description":"Item fiscal","quantity":"1","unit_price":"0.00","discount":"0","total_amount":"0.00","classification":{}}]' });
const assemblyResult = ref<Row | null>(null);


const fiscalConnections = computed(() => connections.value.filter((row) => [
  "SefazNfeProvider", "SefazNfceProvider", "NationalNfseProvider", "MunicipalNfseProvider", "ThirdPartyFiscalProvider",
].includes(row.provider)));
const publishedVersions = computed(() => contexts.value.reduce((total, context) => total + Number(context.active_version ? 1 : 0), 0));
const awaitingProvider = computed(() => documents.value.filter((row) => row.provider_status === "not_configured").length);
const filteredUnits = computed(() => contextForm.institution_id
  ? units.value.filter((unit) => unit.institution_id === contextForm.institution_id)
  : units.value);
const importSources = computed(() => catalogSources.value.filter((row) => !catalogImportForm.catalog_id || row.fiscal_catalog_id === catalogImportForm.catalog_id));

function message(error: unknown): string {
  const candidate = error as Error & { problem?: { detail?: string } };
  return candidate.problem?.detail || (error instanceof Error ? error.message : "Erro inesperado");
}
function idempotency(prefix: string): string { return `${prefix}-${crypto.randomUUID()}`; }
function nullable(value: string): string | null { return value.trim() ? value.trim() : null; }
async function request<T = Row>(path: string, init: RequestInit = {}): Promise<T> { return props.api.request<T>(path, init); }
async function post<T = Row>(path: string, body: unknown, key?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["Idempotency-Key"] = key;
  return request<T>(path, { method: "POST", headers, body: JSON.stringify(body) });
}
async function patch<T = Row>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function formatDate(value?: string): string { return value ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString("pt-BR") : "—"; }
function contextStatus(row: Row): string { return row.status ?? row.state ?? "—"; }
function sourceProfilesLabel(row: Row): string {
  const sources = Array.isArray(row.source_profiles) ? (row.source_profiles as Row[]) : [];
  return sources.map((source) => `${String(source.provider_key ?? source.provider_type ?? "fonte")}@${String(source.provider_version ?? "1")}`).join(", ") || "—";
}
async function fileToBase64(file: File): Promise<string> {
  const buffer = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < buffer.length; i += 0x8000) binary += String.fromCharCode(...buffer.subarray(i, i + 0x8000));
  return btoa(binary);
}
function selectCatalogImportFile(event: Event): void {
  catalogImportFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    const [contextResult, documentResult, ruleResult, connectionResult, catalogResult, classificationResult, taxRuleSetResult, legalSourceResult, strategyResult, ibptState, ibptSnapshotResult, ibptProfileResult, sourceResult, importResult, governanceResult, quarantineResult, providerResult, certificateResult, inutilizationResult, schemaResult, routingResult, assemblyListResult, triggerResult, deliveryPolicyResult] = await Promise.all([
      request<Row>("/fiscal/contexts"),
      request<Row>("/fiscal/documents"),
      request<Row>("/fiscal/rules"),
      request<Row>("/integration-connections"),
      request<Row>("/fiscal/catalogs"),
      request<Row>("/fiscal/classification-rules"),
      request<Row>("/fiscal/tax-rule-sets"),
      request<Row>("/fiscal/legal-sources"),
      request<Row>("/fiscal/strategy-rules"),
      request<Row>("/fiscal/ibpt/operational-status"),
      request<Row>("/fiscal/ibpt/snapshots"),
      request<Row>("/fiscal/ibpt/provider-profiles"),
      request<Row>("/fiscal/catalog-sources"),
      request<Row>("/fiscal/catalog-imports"),
      request<Row>("/fiscal/catalog-governance/health"),
      request<Row>("/fiscal/catalog-quarantine"),
      request<Row>("/fiscal/providers"),
      request<Row>("/fiscal/certificates"),
      request<Row>("/fiscal/inutilizations"),
      request<Row>("/fiscal/document-schemas"),
      request<Row>("/fiscal/routing-policies"),
      request<Row>("/fiscal/document-assemblies"),
      request<Row>("/fiscal/emission-trigger-runs"),
      request<Row>("/fiscal/delivery-policies"),
    ]);
    contexts.value = contextResult.items ?? [];
    documents.value = documentResult.items ?? [];
    rules.value = ruleResult.items ?? [];
    connections.value = connectionResult.items ?? [];
    catalogs.value = catalogResult.items ?? [];
    classificationRules.value = classificationResult.items ?? [];
    taxRuleSets.value = taxRuleSetResult.items ?? [];
    legalSources.value = legalSourceResult.items ?? [];
    strategyRules.value = strategyResult.items ?? [];
    ibptStatus.value = ibptState;
    ibptSnapshots.value = ibptSnapshotResult.items ?? [];
    ibptProfiles.value = ibptProfileResult.items ?? [];
    catalogSources.value = sourceResult.items ?? [];
    catalogImports.value = importResult.items ?? [];
    catalogGovernance.value = governanceResult;
    catalogQuarantine.value = quarantineResult.items ?? [];
    fiscalProviders.value = providerResult.items ?? [];
    fiscalCertificates.value = certificateResult.items ?? [];
    fiscalInutilizations.value = inutilizationResult.items ?? [];
    documentSchemas.value = schemaResult.items ?? [];
    routingPolicies.value = routingResult.items ?? [];
    fiscalAssemblies.value = assemblyListResult.items ?? [];
    emissionTriggerRuns.value = triggerResult.items ?? [];
    deliveryPolicies.value = deliveryPolicyResult.items ?? [];
    try {
      const references = await request<Row>("/references/catalog");
      institutions.value = references.institutions ?? [];
      units.value = references.units ?? [];
    } catch {
      institutions.value = [];
      units.value = [];
    }
    if (selectedContext.value) {
      const current = contexts.value.find((row) => row.id === selectedContext.value?.id);
      if (current) await showContext(current);
    }
  } catch (error) { emit("error", message(error)); }
  finally { loading.value = false; }
}

async function createContext(): Promise<void> {
  try {
    const created = await post<Row>("/fiscal/contexts", {
      code: contextForm.code,
      establishment_name: contextForm.establishment_name,
      legal_name: nullable(contextForm.legal_name),
      cnpj: contextForm.cnpj,
      institution_id: nullable(contextForm.institution_id),
      unit_id: nullable(contextForm.unit_id),
      state_registration: nullable(contextForm.state_registration),
      municipal_registration: nullable(contextForm.municipal_registration),
      provider_connection_id: nullable(contextForm.provider_connection_id),
      metadata: {},
    }, idempotency("fiscal-context"));
    Object.assign(contextForm, { code: "", establishment_name: "", legal_name: "", cnpj: "", institution_id: "", unit_id: "", state_registration: "", municipal_registration: "", provider_connection_id: "" });
    emit("notice", "Estabelecimento fiscal cadastrado com isolamento do tenant.");
    await load();
    await showContext(created);
  } catch (error) { emit("error", message(error)); }
}

async function showContext(row: Row): Promise<void> {
  try {
    selectedContext.value = await request<Row>(`/fiscal/contexts/${row.id}`);
    resolved.value = null;
  } catch (error) { emit("error", message(error)); }
}

async function updateContextStatus(status: "active" | "inactive" | "archived"): Promise<void> {
  if (!selectedContext.value) return;
  try {
    const updated = await patch<Row>(`/fiscal/contexts/${selectedContext.value.id}`, {
      status,
      expected_version: selectedContext.value.version,
    });
    emit("notice", `Contexto fiscal atualizado para ${status}.`);
    selectedContext.value = { ...selectedContext.value, ...updated };
    await load();
  } catch (error) { emit("error", message(error)); }
}

function addScope(): void {
  scopes.value.push({ operation_type: "service_billing", item_kind: "service", recipient_scope: "individual", document_type: "NFS-e" });
}
function removeScope(index: number): void {
  if (scopes.value.length > 1) scopes.value.splice(index, 1);
}

async function createVersion(): Promise<void> {
  if (!selectedContext.value) return;
  try {
    const created = await post<Row>(`/fiscal/contexts/${selectedContext.value.id}/versions`, {
      tax_regime: versionForm.tax_regime,
      uf: versionForm.uf,
      municipality_code: versionForm.municipality_code,
      valid_from: versionForm.valid_from,
      valid_until: nullable(versionForm.valid_until),
      environment: versionForm.environment,
      rtc_mode: versionForm.rtc_mode,
      layout_version: nullable(versionForm.layout_version),
      schema_version: nullable(versionForm.schema_version),
      technical_note_version: nullable(versionForm.technical_note_version),
      ruleset_version: nullable(versionForm.ruleset_version),
      configuration: {},
      notes: nullable(versionForm.notes),
      scopes: scopes.value,
      expected_context_version: selectedContext.value.version,
    }, idempotency("fiscal-context-version"));
    emit("notice", `Versão fiscal ${created.version_number} criada em rascunho.`);
    await showContext(selectedContext.value);
  } catch (error) { emit("error", message(error)); }
}

async function publishVersion(version: Row): Promise<void> {
  if (!selectedContext.value) return;
  try {
    await post(`/fiscal/contexts/${selectedContext.value.id}/versions/${version.id}/publish`, {
      expected_context_version: selectedContext.value.version,
      expected_version: version.version,
      reason: "Publicação revisada pela administração fiscal do tenant.",
    }, idempotency("fiscal-context-publish"));
    emit("notice", "Versão fiscal publicada ou programada conforme sua vigência.");
    await load();
  } catch (error) { emit("error", message(error)); }
}

async function resolveCurrent(): Promise<void> {
  if (!selectedContext.value) return;
  try {
    resolved.value = await post<Row>("/fiscal/contexts/resolve", {
      ...resolveForm,
      context_id: selectedContext.value.id,
    });
    emit("notice", "Contexto fiscal resolvido e fingerprint calculado.");
  } catch (error) { resolved.value = null; emit("error", message(error)); }
}


async function createCatalog(): Promise<void> {
  try {
    const created = await post<Row>("/fiscal/catalogs", { kind: catalogForm.kind, name: catalogForm.name, normalization: catalogForm.normalization, code_pattern: nullable(catalogForm.code_pattern), metadata: {} }, idempotency("fiscal-catalog"));
    catalogVersionForm.catalog_id = created.id;
    emit("notice", `Catálogo ${created.kind} criado.`);
    await load();
  } catch (error) { emit("error", message(error)); }
}

async function createCatalogVersion(): Promise<void> {
  if (!catalogVersionForm.catalog_id) return;
  try {
    const version = await post<Row>(`/fiscal/catalogs/${catalogVersionForm.catalog_id}/versions`, {
      version_label: catalogVersionForm.version_label, valid_from: catalogVersionForm.valid_from, valid_until: nullable(catalogVersionForm.valid_until),
      source_name: catalogVersionForm.source_name, source_reference: nullable(catalogVersionForm.source_reference), schema_version: "1", notes: null,
      entries: [{ code: catalogVersionForm.code, description: catalogVersionForm.description, metadata: {} }],
    }, idempotency("fiscal-catalog-version"));
    await post(`/fiscal/catalogs/${catalogVersionForm.catalog_id}/versions/${version.id}/publish`, { expected_version: version.version, reason: "Publicação revisada do catálogo fiscal." }, idempotency("fiscal-catalog-publish"));
    emit("notice", "Versão do catálogo publicada ou programada conforme vigência.");
    await load();
  } catch (error) { emit("error", message(error)); }
}

async function createCatalogSource(): Promise<void> {
  if (!catalogSourceForm.catalog_id) return;
  try {
    await post(`/fiscal/catalogs/${catalogSourceForm.catalog_id}/sources`, {
      provider_type: catalogSourceForm.provider_type, provider_key: catalogSourceForm.provider_key, provider_version: catalogSourceForm.provider_version,
      import_format: catalogSourceForm.import_format, source_reference: nullable(catalogSourceForm.source_reference), encoding: catalogSourceForm.encoding,
      delimiter: catalogSourceForm.delimiter, max_age_days: Number(catalogSourceForm.max_age_days), mapping: {}, schema: {}, notes: null,
    }, idempotency("fiscal-catalog-source"));
    emit("notice", "Fonte/importador fiscal configurado."); await load();
  } catch (error) { emit("error", message(error)); }
}

async function importCatalogFile(): Promise<void> {
  if (!catalogImportForm.catalog_id || !catalogImportForm.source_profile_id || !catalogImportFile.value) return;
  try {
    const result = await post<Row>(`/fiscal/catalogs/${catalogImportForm.catalog_id}/imports`, {
      source_profile_id: catalogImportForm.source_profile_id, filename: catalogImportFile.value.name,
      content_base64: await fileToBase64(catalogImportFile.value), version_label: catalogImportForm.version_label,
      valid_from: catalogImportForm.valid_from, valid_until: nullable(catalogImportForm.valid_until), schema_version: null, notes: null,
      auto_publish: catalogImportForm.auto_publish,
    }, idempotency("fiscal-catalog-import"));
    emit("notice", result.state === "quarantined" ? "Arquivo colocado em quarentena." : "Snapshot fiscal importado e validado.");
    catalogImportFile.value = null; await load();
  } catch (error) { emit("error", message(error)); await load(); }
}

async function publishCatalogImport(run: Row): Promise<void> {
  try {
    const detail = await request<Row>(`/fiscal/catalog-imports/${run.id}`);
    const version = detail.catalog_version as Row | undefined;
    if (!version) throw new Error("A importação não possui versão publicável.");
    await post(`/fiscal/catalog-imports/${run.id}/publish`, { expected_version: Number(version.version), reason: "Publicação do snapshot fiscal validado." }, idempotency("fiscal-catalog-import-publish"));
    emit("notice", "Snapshot fiscal publicado/agendado."); await load();
  } catch (error) { emit("error", message(error)); }
}

async function rollbackCatalogImport(run: Row): Promise<void> {
  if (!run.catalog_version_id) return;
  try {
    await post(`/fiscal/catalogs/${run.fiscal_catalog_id}/versions/${run.catalog_version_id}/rollback`, { effective_from: today, reason: "Rollback administrativo para snapshot fiscal validado." }, idempotency("fiscal-catalog-rollback"));
    emit("notice", "Rollback criado como nova versão imutável."); await load();
  } catch (error) { emit("error", message(error)); }
}

async function resolveCatalogQuarantine(row: Row): Promise<void> {
  try {
    await post(`/fiscal/catalog-quarantine/${row.id}/resolve`, { action: "discarded", reason: "Arquivo revisado e descartado pela administração fiscal." });
    emit("notice", "Quarentena resolvida."); await load();
  } catch (error) { emit("error", message(error)); }
}

async function createClassification(): Promise<void> {
  try {
    const payload: Row = { fiscal_context_id: classificationForm.fiscal_context_id, establishment_code: nullable(classificationForm.establishment_code), item_kind: classificationForm.item_kind, item_id: nullable(classificationForm.item_id), operation_type: classificationForm.operation_type, valid_from: classificationForm.valid_from, valid_until: nullable(classificationForm.valid_until), priority: Number(classificationForm.priority), tax_configuration: {}, notes: null };
    for (const field of ["ncm","nbs","lc116","cfop","cest","cst","csosn","cst_ibs_cbs","cclasstrib","cbenef","municipal_code","cnae"]) payload[field] = nullable(String((classificationForm as Row)[field]));
    const created = await post<Row>("/fiscal/classification-rules", payload, idempotency("fiscal-classification"));
    await post(`/fiscal/classification-rules/${created.id}/publish`, { expected_version: created.version, reason: "Classificação fiscal revisada pelo tenant." }, idempotency("fiscal-classification-publish"));
    emit("notice", "Regra de classificação publicada.");
    await load();
  } catch (error) { emit("error", message(error)); }
}

async function calculateReadiness(): Promise<void> {
  if (!classificationForm.fiscal_context_id) return;
  try {
    const params = new URLSearchParams({ fiscal_context_id: classificationForm.fiscal_context_id, occurred_on: classificationForm.valid_from, operation_type: classificationForm.operation_type });
    if (classificationForm.establishment_code) params.set("establishment_code", classificationForm.establishment_code);
    readiness.value = await request<Row>(`/fiscal/readiness?${params.toString()}`);
    emit("notice", "Prontidão fiscal recalculada.");
  } catch (error) { readiness.value = null; emit("error", message(error)); }
}

function addTaxComponent(): void {
  taxComponents.value.push({ tax: "CBS", incidence: "taxable", base_mode: "operation_total", rate_pct: "0", base_reduction_pct: "0", deferral_pct: "0", suspension_pct: "0", mva_pct: "0", monophase_amount_per_unit: "", deduct_tax_codes: [] });
}
function removeTaxComponent(index: number): void { if (taxComponents.value.length > 1) taxComponents.value.splice(index, 1); }

async function createTaxRuleSet(): Promise<void> {
  try {
    const created = await post<Row>("/fiscal/tax-rule-sets", {
      fiscal_context_id: taxRuleForm.fiscal_context_id, code: taxRuleForm.code, name: taxRuleForm.name, establishment_code: nullable(taxRuleForm.establishment_code),
      operation_type: taxRuleForm.operation_type, item_kind: taxRuleForm.item_kind, tax_regime: taxRuleForm.tax_regime, rtc_mode: taxRuleForm.rtc_mode, priority: Number(taxRuleForm.priority), description: null,
    }, idempotency("fiscal-tax-ruleset"));
    taxVersionForm.rule_set_id = created.id;
    emit("notice", "Conjunto tributário criado. Inclua uma versão para torná-lo aplicável.");
    await load();
  } catch (error) { emit("error", message(error)); }
}

async function createTaxRuleVersion(): Promise<void> {
  if (!taxVersionForm.rule_set_id) return;
  try {
    const ruleSet = taxRuleSets.value.find((row) => row.id === taxVersionForm.rule_set_id);
    if (!ruleSet) throw new Error("Selecione um conjunto tributário válido.");
    const components = taxComponents.value.map((component) => ({
      tax: component.tax, incidence: component.incidence, base_mode: component.base_mode, rate_pct: String(component.rate_pct || "0"),
      base_reduction_pct: String(component.base_reduction_pct || "0"), deferral_pct: String(component.deferral_pct || "0"), suspension_pct: String(component.suspension_pct || "0"),
      mva_pct: String(component.mva_pct || "0"), monophase_amount_per_unit: nullable(String(component.monophase_amount_per_unit || "")),
      custom_base_key: null, include_amount_keys: [], deduct_amount_keys: [], deduct_tax_codes: component.deduct_tax_codes ?? [], metadata: {},
    }));
    const created = await post<Row>(`/fiscal/tax-rule-sets/${ruleSet.id}/versions`, {
      version_label: taxVersionForm.version_label, valid_from: taxVersionForm.valid_from, valid_until: nullable(taxVersionForm.valid_until),
      source_name: taxVersionForm.source_name, source_reference: nullable(taxVersionForm.source_reference), legal_basis: taxVersionForm.legal_basis.split("\n").map((v) => v.trim()).filter(Boolean),
      notes: null, components, expected_rule_set_version: ruleSet.version,
    }, idempotency("fiscal-tax-ruleversion"));
    await post(`/fiscal/tax-rule-sets/${ruleSet.id}/versions/${created.id}/publish`, { expected_rule_set_version: created.rule_set_version, expected_version: created.version, reason: "Regra tributária revisada e publicada pelo tenant." }, idempotency("fiscal-tax-publish"));
    emit("notice", "Versão tributária publicada ou programada conforme vigência.");
    await load();
  } catch (error) { emit("error", message(error)); }
}

async function simulateTaxCalculation(): Promise<void> {
  try {
    taxCalculation.value = await post<Row>("/fiscal/tax-calculations/simulate", {
      fiscal_context_id: taxSimulationForm.fiscal_context_id, establishment_code: nullable(taxSimulationForm.establishment_code), operation_type: taxSimulationForm.operation_type,
      item_kind: taxSimulationForm.item_kind, occurred_on: taxSimulationForm.occurred_on, amount: taxSimulationForm.amount, quantity: taxSimulationForm.quantity,
      freight: taxSimulationForm.freight, insurance: taxSimulationForm.insurance, other_amount: taxSimulationForm.other_amount, discount: taxSimulationForm.discount,
      custom_bases: {}, custom_amounts: {}, expected_taxes: {}, recipient_scope: "any", document_type: "any", item_id: null,
    }, idempotency("fiscal-tax-simulation"));
    emit("notice", "Simulação tributária calculada com snapshot e explicabilidade.");
  } catch (error) { taxCalculation.value = null; emit("error", message(error)); }
}


async function createLegalSource(): Promise<void> {
  try { await post("/fiscal/legal-sources", { ...legalSourceForm, valid_until: nullable(legalSourceForm.valid_until), source_reference: nullable(legalSourceForm.source_reference), metadata: {} }, idempotency("fiscal-legal-source")); emit("notice", "Fonte normativa versionada publicada."); await load(); } catch (error) { emit("error", message(error)); }
}
async function createStrategy(): Promise<void> {
  try { const parameters: Row = {}; if (Number(strategyForm.rate_pct)) parameters.rate_pct = strategyForm.rate_pct; if (Number(strategyForm.amount)) parameters.amount = strategyForm.amount; await post("/fiscal/strategy-rules", { ...strategyForm, establishment_code: nullable(strategyForm.establishment_code), origin_uf: nullable(strategyForm.origin_uf), destination_uf: nullable(strategyForm.destination_uf), valid_until: nullable(strategyForm.valid_until), legal_source_id: nullable(strategyForm.legal_source_id), parameters }, idempotency("fiscal-strategy")); emit("notice", "Estratégia tributária publicada."); await load(); } catch (error) { emit("error", message(error)); }
}
async function createRtcSchedule(): Promise<void> {
  try { await post("/fiscal/rtc-schedules", { ...rtcForm, establishment_code: nullable(rtcForm.establishment_code), valid_until: nullable(rtcForm.valid_until), legal_source_id: nullable(rtcForm.legal_source_id), notes: nullable(rtcForm.notes) }, idempotency("fiscal-rtc")); emit("notice", "Cronograma RTC publicado."); await load(); } catch (error) { emit("error", message(error)); }
}
async function syncIbpt(): Promise<void> { try { await post("/fiscal/ibpt/sync", { ufs: [ibptUf.value] }); emit("notice", `Sincronização IBPT ${ibptUf.value} enfileirada.`); await load(); } catch (error) { emit("error", message(error)); } }
async function loadIbptOffline(): Promise<void> { try { ibptOffline.value = await request(`/fiscal/ibpt/offline/${ibptUf.value}`); } catch (error) { emit("error", message(error)); } }
async function rollbackIbpt(snapshot: Row): Promise<void> { try { await post(`/fiscal/ibpt/snapshots/${snapshot.id}/rollback`, {}); emit("notice", `Snapshot IBPT ${snapshot.uf} reativado.`); await load(); } catch (error) { emit("error", message(error)); } }
async function createIbptProfile(): Promise<void> {
  try {
    const result = await post<Row>("/fiscal/ibpt/provider-profiles", {
      provider_code: ibptProfileForm.provider_code, mode: ibptProfileForm.mode, valid_from: ibptProfileForm.valid_from,
      valid_until: nullable(ibptProfileForm.valid_until), sync_enabled: ibptProfileForm.sync_enabled,
      fallback_enabled: ibptProfileForm.fallback_enabled, fallback_max_age_days: ibptProfileForm.fallback_max_age_days,
      stale_after_days: ibptProfileForm.stale_after_days, base_url: nullable(ibptProfileForm.base_url),
      uf_path: nullable(ibptProfileForm.uf_path), notes: nullable(ibptProfileForm.notes),
    }, idempotency("fiscal-ibpt-profile"));
    await post(`/fiscal/ibpt/provider-profiles/${result.id}/publish`, { expected_version: Number(result.version ?? 1), reason: "Publicação administrativa do perfil IBPT versionado." });
    emit("notice", "Perfil IBPT versionado publicado."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function loadDocumentTransparency(row: Row): Promise<void> {
  try { documentTransparency.value = await request<Row>(`/fiscal/documents/${row.id}/transparency`); }
  catch (error) { documentTransparency.value = null; emit("error", message(error)); }
}


async function createFiscalCertificate(): Promise<void> {
  try {
    await post("/fiscal/certificates", {
      certificate_type: "a1", subject_name: certificateForm.subject_name, subject_document: nullable(certificateForm.subject_document),
      serial_number: certificateForm.serial_number, issuer_name: certificateForm.issuer_name, valid_from: certificateForm.valid_from,
      valid_until: certificateForm.valid_until, fingerprint_sha256: certificateForm.fingerprint_sha256, secret_ref: certificateForm.secret_ref,
      metadata: { source: "tenant-admin-web" },
    }, idempotency("fiscal-certificate"));
    emit("notice", "Metadados do certificado registrados; a chave privada permanece apenas no secret store."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function createFiscalProvider(): Promise<void> {
  try {
    await post("/fiscal/providers", {
      provider_code: providerForm.provider_code, display_name: providerForm.display_name, document_type: providerForm.document_type,
      environment: providerForm.environment, endpoint_url: nullable(providerForm.endpoint_url), secret_ref: nullable(providerForm.secret_ref),
      certificate_metadata_id: nullable(providerForm.certificate_metadata_id), capabilities: ["issue","query","cancel","substitute","inutilize","event","health"],
      settings: {}, enabled: providerForm.enabled,
    }, idempotency("fiscal-provider"));
    emit("notice", "Provider fiscal salvo. Estado real depende das referências de credenciais/certificado."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function checkFiscalProvider(row: Row): Promise<void> {
  try { const result=await post<Row>(`/fiscal/providers/${row.id}/health`,{}); emit("notice", `Health fiscal: ${result.health}`); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createDeliveryPolicy(): Promise<void> {
  try {
    const result = await post<Row>("/fiscal/delivery-policies", {
      ...deliveryPolicyForm, provider_code: nullable(deliveryPolicyForm.provider_code), valid_until: nullable(deliveryPolicyForm.valid_until),
      contingency_after_attempts: deliveryPolicyForm.contingency_after_attempts || null, contingency_mode: deliveryPolicyForm.contingency_after_attempts ? deliveryPolicyForm.contingency_mode : null, notes: nullable(deliveryPolicyForm.notes),
    }, idempotency("fiscal-delivery-policy"));
    await post(`/fiscal/delivery-policies/${result.id}/publish`, { expected_version: Number(result.version ?? 1), reason: "Publicação administrativa da política de entrega fiscal." });
    emit("notice", "Política versionada de retry/contingência publicada."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function retryFiscalDocument(row: Row): Promise<void> {
  const reason = window.prompt("Motivo do reprocessamento fiscal:", "Reprocessamento manual após análise operacional."); if (!reason) return;
  try { await post(`/fiscal/documents/${row.id}/retry`, { reason, force: false }); emit("notice", "Reprocessamento fiscal enfileirado conforme a política vigente."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function renderFiscalDocument(row: Row): Promise<void> {
  try { const result = await post<Row>(`/fiscal/documents/${row.id}/render`, { force: false }); emit("notice", `Artefato ${String(result.artifact_type)} gerado · ${String(result.sha256).slice(0,12)}…`); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function loadDocumentArtifacts(row: Row): Promise<void> {
  try {
    const result = await request<Row>(`/fiscal/documents/${row.id}/artifacts`);
    selectedArtifactDocument.value = row;
    selectedArtifacts.value = result.items ?? [];
  } catch (error) { emit("error", message(error)); }
}
async function downloadFiscalArtifact(row: Row | null, artifact: Row): Promise<void> {
  if (!row) return;
  try {
    const response = await props.api.response(`/fiscal/documents/${row.id}/artifacts/${artifact.id}/download`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${String(artifact.artifact_type ?? "artefato-fiscal")}-${row.id}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
    emit("notice", `Download validado por SHA-256: ${String(artifact.sha256).slice(0, 12)}…`);
  } catch (error) { emit("error", message(error)); }
}
async function loadFiscalRejection(row: Row): Promise<void> {
  try { selectedRejection.value = await request<Row>(`/fiscal/documents/${row.id}/rejection`); }
  catch (error) { selectedRejection.value = null; emit("error", message(error)); }
}

async function queryFiscalDocument(row: Row): Promise<void> {
  try { await post(`/fiscal/documents/${row.id}/query`,{reason:"Consulta manual solicitada pela administração."}); emit("notice","Consulta fiscal enfileirada."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function cancelFiscalDocument(row: Row): Promise<void> {
  const reason=window.prompt("Motivo do cancelamento fiscal:","Cancelamento solicitado pela administração."); if(!reason) return;
  try { await post(`/fiscal/documents/${row.id}/cancel`,{reason}); emit("notice","Cancelamento registrado/enfileirado conforme o estado do documento."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function substituteFiscalDocument(row: Row): Promise<void> {
  const reason=window.prompt("Motivo da substituição:","Substituição fiscal solicitada pela administração."); if(!reason) return;
  try { await post(`/fiscal/documents/${row.id}/substitute`,{source_type:"manual",source_id:`${String(row.source_id)}-sub-${Date.now()}`,totals:{},payload:{replacement_of:row.id},reason},idempotency("fiscal-substitute")); emit("notice","Substituição fiscal enfileirada."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function requestCorrectionEvent(row: Row): Promise<void> {
  const text=window.prompt("Texto do evento/carta de correção:",""); if(!text) return;
  try { await post(`/fiscal/documents/${row.id}/events`,{event_type:"correction_letter",payload:{text},reason:"Evento solicitado pela administração."},idempotency("fiscal-event")); emit("notice","Evento fiscal enfileirado."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createFiscalInutilization(): Promise<void> {
  try { await post("/fiscal/inutilizations",{...inutilizationForm},idempotency("fiscal-inutilization")); emit("notice","Inutilização registrada conforme o provider configurado."); await load(); }
  catch (error) { emit("error", message(error)); }
}


async function createDocumentSchema(): Promise<void> {
  try {
    const result = await post<Row>("/fiscal/document-schemas", { document_type: documentSchemaForm.document_type, schema_code: documentSchemaForm.schema_code, version_label: documentSchemaForm.version_label, valid_from: documentSchemaForm.valid_from, valid_until: nullable(documentSchemaForm.valid_until), root_element: documentSchemaForm.root_element, namespace_uri: nullable(documentSchemaForm.namespace_uri), xsd_text: documentSchemaForm.xsd_text, source_reference: nullable(documentSchemaForm.source_reference), metadata: { imported_from: "tenant_admin" } }, idempotency("fiscal-schema"));
    emit("notice", "Schema fiscal versionado criado em rascunho."); await publishDocumentSchema(result); await load();
  } catch (error) { emit("error", message(error)); }
}
async function publishDocumentSchema(row: Row): Promise<void> {
  try { await post(`/fiscal/document-schemas/${row.id}/publish`, { reason: "Publicação administrativa do schema validado localmente.", expected_version: Number(row.version ?? 1) }); emit("notice", "Schema fiscal publicado."); await load(); }
  catch (error) { emit("error", message(error)); }
}
async function createRoutingPolicy(): Promise<void> {
  try {
    const settings = {
      financial_cancel_mode: routingPolicyForm.financial_cancel_mode,
      tax_regimes: routingPolicyForm.tax_regime_filter ? [routingPolicyForm.tax_regime_filter] : [],
      municipality_codes: routingPolicyForm.municipality_filter ? [routingPolicyForm.municipality_filter] : [],
      require_financial_contract: routingPolicyForm.require_financial_contract,
      fiscal_reversal_debit_account: nullable(routingPolicyForm.fiscal_reversal_debit_account),
      fiscal_reversal_credit_account: nullable(routingPolicyForm.fiscal_reversal_credit_account),
    };
    const result=await post<Row>("/fiscal/routing-policies", {
      fiscal_context_id: routingPolicyForm.fiscal_context_id, code: routingPolicyForm.code, name: routingPolicyForm.name,
      operation_type: routingPolicyForm.operation_type, recipient_scope: routingPolicyForm.recipient_scope, channel_scope: routingPolicyForm.channel_scope,
      product_document_type: nullable(routingPolicyForm.product_document_type), service_document_type: routingPolicyForm.service_document_type,
      trigger_types: routingPolicyForm.trigger_types, valid_from: routingPolicyForm.valid_from, valid_until: nullable(routingPolicyForm.valid_until),
      priority: routingPolicyForm.priority, settings,
    }, idempotency("fiscal-routing"));
    await post(`/fiscal/routing-policies/${result.id}/publish`, { reason: "Publicação administrativa da política de roteamento.", expected_version: Number(result.version ?? 1) });
    emit("notice", "Política de roteamento publicada."); await load();
  } catch (error) { emit("error", message(error)); }
}
async function assembleFiscalDocument(): Promise<void> {
  try {
    const items=JSON.parse(assemblyForm.items_json) as Row[];
    assemblyResult.value=await post<Row>("/fiscal/document-assemblies", { fiscal_context_id: assemblyForm.fiscal_context_id, fiscal_profile_id: assemblyForm.fiscal_profile_id, source_type: assemblyForm.source_type, source_id: assemblyForm.source_id, occurred_on: assemblyForm.occurred_on, operation_type: assemblyForm.operation_type, recipient_scope: assemblyForm.recipient_scope, channel: assemblyForm.channel, destination_uf: nullable(assemblyForm.destination_uf), trigger_type: assemblyForm.trigger_type, recipient: { name: nullable(assemblyForm.recipient_name), document: nullable(assemblyForm.recipient_document), uf: nullable(assemblyForm.destination_uf) }, items, request_emission: assemblyForm.request_emission, metadata: { requested_from: "tenant_admin" } }, idempotency("fiscal-assembly"));
    emit("notice", assemblyResult.value.state === "blocked_validation" ? "Montagem bloqueada pela validação local." : "Montagem fiscal concluída."); await load();
  } catch (error) { emit("error", message(error)); }
}

async function evaluateEmissionTrigger(row: Row): Promise<void> {
  try { await post("/fiscal/emission-trigger-runs/evaluate", { event_type: row.event_type ?? "SaleCompleted", aggregate_id: row.aggregate_id ?? row.source_id, payload: {} }); emit("notice", "Gatilho fiscal reavaliado."); await load(); }
  catch (error) { emit("error", message(error)); }
}

onMounted(load);
</script>

<template>
  <div class="fiscal-panel">
    <section class="metrics">
      <article><span>Estabelecimentos</span><strong>{{ contexts.length }}</strong><small>contextos fiscais isolados</small></article>
      <article><span>Versões vigentes</span><strong>{{ publishedVersions }}</strong><small>seleção por data e operação</small></article>
      <article><span>Documentos fiscais</span><strong>{{ documents.length }}</strong><small>solicitações persistidas</small></article>
      <article><span>Aguardando provider</span><strong>{{ awaitingProvider }}</strong><small>não configurado, sem simulação</small></article>
    </section>

    <section class="tabs panel">
      <button :class="{ active: tab === 'contexts' }" @click="tab = 'contexts'">Contextos e vigências</button>
      <button :class="{ active: tab === 'catalogs' }" @click="tab = 'catalogs'">Catálogos e prontidão</button>
      <button :class="{ active: tab === 'engine' }" @click="tab = 'engine'">Motor tributário</button>
      <button :class="{ active: tab === 'strategies' }" @click="tab = 'strategies'">Estratégias, RTC e IBPT</button>
      <button :class="{ active: tab === 'routing' }" @click="tab = 'routing'">Roteamento e XML</button>
      <button :class="{ active: tab === 'documents' }" @click="tab = 'documents'">Documentos</button>
      <button :class="{ active: tab === 'rules' }" @click="tab = 'rules'">Regras tributárias</button>
      <button class="small refresh" :disabled="loading" @click="load">{{ loading ? "Atualizando…" : "Atualizar" }}</button>
    </section>

    <template v-if="tab === 'contexts'">
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createContext">
          <h2>Novo estabelecimento fiscal</h2>
          <div class="cols"><label>Código<input v-model="contextForm.code" required maxlength="80" /></label><label>CNPJ<input v-model="contextForm.cnpj" required placeholder="00.000.000/0000-00" /></label></div>
          <label>Nome do estabelecimento<input v-model="contextForm.establishment_name" required /></label>
          <label>Razão social<input v-model="contextForm.legal_name" /></label>
          <div class="cols"><label>Instituição<select v-model="contextForm.institution_id"><option value="">Escopo geral</option><option v-for="row in institutions" :key="row.id" :value="row.id">{{ row.label ?? row.trade_name ?? row.legal_name }}</option></select></label><label>Unidade<select v-model="contextForm.unit_id"><option value="">Todas as unidades</option><option v-for="row in filteredUnits" :key="row.id" :value="row.id">{{ row.label ?? row.name }}</option></select></label></div>
          <div class="cols"><label>Inscrição estadual<input v-model="contextForm.state_registration" /></label><label>Inscrição municipal<input v-model="contextForm.municipal_registration" /></label></div>
          <label>Provider fiscal<select v-model="contextForm.provider_connection_id"><option value="">Não configurado</option><option v-for="row in fiscalConnections" :key="row.id" :value="row.id">{{ row.name }} · {{ row.provider }}</option></select><small>A ausência de provider não bloqueia cadastro, simulação e validação.</small></label>
          <button class="primary">Cadastrar contexto</button>
        </form>
        <div class="panel">
          <div class="panel-title"><h2>Estabelecimentos</h2><span>{{ contexts.length }} registros</span></div>
          <div class="context-list">
            <button v-for="row in contexts" :key="row.id" :class="{ selected: selectedContext?.id === row.id }" @click="showContext(row)">
              <span><strong>{{ row.establishment_name }}</strong><small>{{ row.code }} · {{ row.cnpj }} · {{ row.active_version?.tax_regime ?? "sem versão publicada" }}</small></span>
              <span class="pill" :class="contextStatus(row) === 'active' ? 'ok' : 'warn'">{{ contextStatus(row) }}</span>
            </button>
            <div v-if="!contexts.length" class="empty">Nenhum contexto fiscal cadastrado.</div>
          </div>
        </div>
      </section>

      <template v-if="selectedContext">
        <section class="panel">
          <div class="panel-title"><div><h2>{{ selectedContext.establishment_name }}</h2><small>{{ selectedContext.code }} · {{ selectedContext.cnpj }} · versão cadastral {{ selectedContext.version }}</small></div><div class="actions"><button v-if="contextStatus(selectedContext) !== 'active'" class="small" @click="updateContextStatus('active')">Ativar</button><button v-if="contextStatus(selectedContext) === 'active'" class="small" @click="updateContextStatus('inactive')">Inativar</button><button v-if="contextStatus(selectedContext) !== 'archived'" class="small danger" @click="updateContextStatus('archived')">Arquivar</button><button class="small" @click="selectedContext = null">Fechar</button></div></div>
          <div class="details"><span><b>Inscrição estadual:</b> {{ selectedContext.state_registration ?? "—" }}</span><span><b>Inscrição municipal:</b> {{ selectedContext.municipal_registration ?? "—" }}</span><span><b>Provider:</b> {{ selectedContext.provider_connection_id ?? "not_configured" }}</span><span><b>Versão ativa:</b> {{ selectedContext.active_version_id ?? "—" }}</span></div>
        </section>

        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="createVersion">
            <h2>Nova versão por vigência</h2>
            <div class="cols"><label>Regime<select v-model="versionForm.tax_regime"><option value="simples_nacional">Simples Nacional</option><option value="lucro_presumido">Lucro Presumido</option><option value="lucro_real">Lucro Real</option><option value="normal">Regime normal</option><option value="mei">MEI</option><option value="imune">Imune</option><option value="isenta">Isenta</option><option value="public_entity">Entidade pública</option><option value="other">Outro</option></select></label><label>Ambiente<select v-model="versionForm.environment"><option value="homologation">Homologação</option><option value="production">Produção</option></select></label></div>
            <div class="cols"><label>UF<input v-model="versionForm.uf" maxlength="2" required /></label><label>Código IBGE do município<input v-model="versionForm.municipality_code" maxlength="7" required /></label></div>
            <div class="cols"><label>Vigência inicial<input v-model="versionForm.valid_from" type="date" required /></label><label>Vigência final<input v-model="versionForm.valid_until" type="date" /></label></div>
            <label>Modo RTC<select v-model="versionForm.rtc_mode"><option value="disabled">Desabilitado</option><option value="simulation_only">Somente simulação</option><option value="optional_emit">Emissão opcional</option><option value="required_emit">Emissão obrigatória</option></select></label>
            <div class="cols"><label>Layout<input v-model="versionForm.layout_version" placeholder="NF-e 4.00" /></label><label>Schema<input v-model="versionForm.schema_version" placeholder="PL_010_V120" /></label></div>
            <div class="cols"><label>Nota técnica<input v-model="versionForm.technical_note_version" /></label><label>Ruleset<input v-model="versionForm.ruleset_version" /></label></div>
            <label>Observações<textarea v-model="versionForm.notes" rows="3"></textarea></label>
            <div class="scope-title"><h3>Tipos de operação</h3><button class="small" type="button" @click="addScope">Adicionar escopo</button></div>
            <div v-for="(scope, index) in scopes" :key="index" class="scope-row">
              <input v-model="scope.operation_type" required placeholder="sale" />
              <select v-model="scope.item_kind"><option value="any">Qualquer item</option><option value="product">Produto</option><option value="service">Serviço</option><option value="mixed">Misto</option></select>
              <select v-model="scope.recipient_scope"><option value="any">Qualquer destinatário</option><option value="individual">Pessoa física</option><option value="company">Pessoa jurídica</option><option value="government">Governo</option><option value="foreign">Exterior</option></select>
              <select v-model="scope.document_type"><option value="any">Qualquer documento</option><option value="NF-e">NF-e</option><option value="NFC-e">NFC-e</option><option value="NFS-e">NFS-e</option></select>
              <button class="small danger" type="button" :disabled="scopes.length === 1" @click="removeScope(index)">Remover</button>
            </div>
            <button class="primary">Criar versão em rascunho</button>
          </form>

          <div class="panel">
            <div class="panel-title"><h2>Histórico de versões</h2><span>{{ selectedContext.versions?.length ?? 0 }}</span></div>
            <div class="version-list">
              <article v-for="version in selectedContext.versions ?? []" :key="version.id">
                <div><strong>v{{ version.version_number }} · {{ version.tax_regime }}</strong><small>{{ version.uf }}/{{ version.municipality_code }} · {{ formatDate(version.valid_from) }} até {{ formatDate(version.valid_until) }}</small><small>{{ version.environment }} · RTC {{ version.rtc_mode }} · {{ version.scopes?.length ?? 0 }} escopos</small></div>
                <div><span class="pill" :class="version.status === 'published' ? 'ok' : version.status === 'draft' ? 'warn' : ''">{{ version.status }}</span><button v-if="version.status === 'draft'" class="small" @click="publishVersion(version)">Publicar</button></div>
              </article>
              <div v-if="!selectedContext.versions?.length" class="empty">Nenhuma versão cadastrada.</div>
            </div>
          </div>
        </section>

        <section class="grid-2 forms">
          <form class="panel" @submit.prevent="resolveCurrent">
            <h2>Testar resolução fiscal</h2>
            <div class="cols"><label>Data da operação<input v-model="resolveForm.occurred_on" type="date" required /></label><label>Operação<input v-model="resolveForm.operation_type" required /></label></div>
            <div class="cols"><label>Item<select v-model="resolveForm.item_kind"><option value="product">Produto</option><option value="service">Serviço</option><option value="mixed">Misto</option></select></label><label>Destinatário<select v-model="resolveForm.recipient_scope"><option value="individual">Pessoa física</option><option value="company">Pessoa jurídica</option><option value="government">Governo</option><option value="foreign">Exterior</option></select></label></div>
            <label>Documento<select v-model="resolveForm.document_type"><option value="NF-e">NF-e</option><option value="NFC-e">NFC-e</option><option value="NFS-e">NFS-e</option></select></label>
            <button class="primary">Resolver versão aplicável</button>
          </form>
          <div class="panel"><h2>Snapshot resolvido</h2><template v-if="resolved"><dl><dt>Versão</dt><dd>{{ resolved.version?.version_number }} · {{ resolved.version?.tax_regime }}</dd><dt>Vigência</dt><dd>{{ resolved.version?.valid_from }} até {{ resolved.version?.valid_until ?? "sem término" }}</dd><dt>Escopo</dt><dd>{{ resolved.scope?.operation_type }} / {{ resolved.scope?.item_kind }} / {{ resolved.scope?.document_type }}</dd><dt>SHA-256</dt><dd><code>{{ resolved.sha256 }}</code></dd></dl></template><div v-else class="empty">Execute a resolução para comprovar a regra aplicável sem alterar documentos existentes.</div></div>
        </section>
      </template>
    </template>

    <template v-else-if="tab === 'catalogs'">
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createCatalog">
          <h2>Novo catálogo fiscal versionado</h2>
          <div class="cols"><label>Tipo<select v-model="catalogForm.kind"><option v-for="kind in ['NCM','NBS','LC116','CFOP','CEST','CST','CSOSN','CST_IBS_CBS','CCLASSTRIB','CBENEF','CREDITO_PRESUMIDO','RTC_TABLE','NFSE_CORRELATION','MUNICIPAL_CODE','TAX_RATE','TECHNICAL_NOTE']" :key="kind" :value="kind">{{ kind }}</option></select></label><label>Nome<input v-model="catalogForm.name" required /></label></div>
          <div class="cols"><label>Normalização<select v-model="catalogForm.normalization"><option value="digits">Somente dígitos</option><option value="upper_alnum">Alfanumérico maiúsculo</option><option value="preserve">Preservar formato</option></select></label><label>Padrão regex opcional<input v-model="catalogForm.code_pattern" placeholder="^[0-9]{8}$" /></label></div>
          <button class="primary">Criar catálogo</button>
        </form>
        <form class="panel" @submit.prevent="createCatalogVersion">
          <h2>Publicar versão e entrada</h2>
          <label>Catálogo<select v-model="catalogVersionForm.catalog_id" required><option value="">Selecione</option><option v-for="row in catalogs" :key="row.id" :value="row.id">{{ row.kind }} · {{ row.name }}</option></select></label>
          <div class="cols"><label>Versão<input v-model="catalogVersionForm.version_label" required /></label><label>Vigência<input v-model="catalogVersionForm.valid_from" type="date" required /></label></div>
          <label>Fonte<input v-model="catalogVersionForm.source_name" required /></label><label>Referência da fonte<input v-model="catalogVersionForm.source_reference" /></label>
          <div class="cols"><label>Código<input v-model="catalogVersionForm.code" required /></label><label>Descrição<input v-model="catalogVersionForm.description" required /></label></div>
          <button class="primary">Criar e publicar versão</button>
        </form>
      </section>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createClassification">
          <h2>Regra por estabelecimento e vigência</h2>
          <label>Contexto<select v-model="classificationForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }} · {{ row.establishment_name }}</option></select></label>
          <div class="cols"><label>Estabelecimento<input v-model="classificationForm.establishment_code" placeholder="MATRIZ-BA" /></label><label>Operação<input v-model="classificationForm.operation_type" required /></label></div>
          <div class="cols"><label>Tipo<select v-model="classificationForm.item_kind"><option value="product">Produto</option><option value="service">Serviço</option><option value="mixed">Misto</option></select></label><label>ID do item opcional<input v-model="classificationForm.item_id" /></label></div>
          <div class="cols"><label>Início<input v-model="classificationForm.valid_from" type="date" required /></label><label>Fim<input v-model="classificationForm.valid_until" type="date" /></label></div>
          <div class="classification-grid"><label>NCM<input v-model="classificationForm.ncm" /></label><label>NBS<input v-model="classificationForm.nbs" /></label><label>LC 116<input v-model="classificationForm.lc116" /></label><label>CFOP<input v-model="classificationForm.cfop" /></label><label>CEST<input v-model="classificationForm.cest" /></label><label>CST<input v-model="classificationForm.cst" /></label><label>CSOSN<input v-model="classificationForm.csosn" /></label><label>CST IBS/CBS<input v-model="classificationForm.cst_ibs_cbs" /></label><label>cClassTrib<input v-model="classificationForm.cclasstrib" /></label><label>cBenef<input v-model="classificationForm.cbenef" /></label><label>Cód. municipal<input v-model="classificationForm.municipal_code" /></label><label>CNAE<input v-model="classificationForm.cnae" /></label></div>
          <div class="actions"><button class="primary">Publicar regra</button><button type="button" class="small" @click="calculateReadiness">Calcular prontidão</button></div>
        </form>
        <div class="panel"><div class="panel-title"><h2>Prontidão fiscal</h2><strong v-if="readiness">{{ readiness.readiness_percentage }}%</strong></div><template v-if="readiness"><div class="details"><span><b>Itens:</b> {{ readiness.total_items }}</span><span><b>Prontos:</b> {{ readiness.ready_items }}</span><span><b>Pendentes:</b> {{ readiness.pending_items }}</span><span><b>RTC:</b> {{ readiness.rtc_mode }}</span></div><table><thead><tr><th>Item</th><th>Tipo</th><th>Estado</th><th>Pendências</th></tr></thead><tbody><tr v-for="item in readiness.items" :key="item.item_id"><td>{{ item.code }} · {{ item.name }}</td><td>{{ item.item_kind }}</td><td><span class="pill" :class="item.ready ? 'ok' : 'warn'">{{ item.ready ? 'pronto' : 'pendente' }}</span></td><td>{{ item.missing?.join(', ') || '—' }}</td></tr></tbody></table></template><div v-else class="empty">Selecione o contexto e calcule a prontidão para produtos e serviços.</div></div>
      </section>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createCatalogSource">
          <h2>Fonte/importador versionado</h2>
          <label>Catálogo<select v-model="catalogSourceForm.catalog_id" required><option value="">Selecione</option><option v-for="row in catalogs" :key="row.id" :value="row.id">{{ row.kind }} · {{ row.name }}</option></select></label>
          <div class="cols"><label>Provider<input v-model="catalogSourceForm.provider_key" required /></label><label>Versão<input v-model="catalogSourceForm.provider_version" required /></label></div>
          <div class="cols"><label>Tipo<select v-model="catalogSourceForm.provider_type"><option value="local_file">Arquivo local</option><option value="manual_snapshot">Snapshot manual</option><option value="external_http">HTTP externo (condicional)</option></select></label><label>Formato<select v-model="catalogSourceForm.import_format"><option value="csv">CSV</option><option value="json">JSON</option><option value="xsd">XSD</option></select></label></div>
          <label>Referência<input v-model="catalogSourceForm.source_reference" placeholder="Origem/ato/arquivo oficial" /></label>
          <button class="primary">Configurar fonte</button>
        </form>
        <form class="panel" @submit.prevent="importCatalogFile">
          <h2>Importar snapshot local</h2>
          <label>Catálogo<select v-model="catalogImportForm.catalog_id" required><option value="">Selecione</option><option v-for="row in catalogs" :key="row.id" :value="row.id">{{ row.kind }} · {{ row.name }}</option></select></label>
          <label>Fonte<select v-model="catalogImportForm.source_profile_id" required><option value="">Selecione</option><option v-for="row in importSources" :key="row.id" :value="row.id">{{ row.provider_key }}@{{ row.provider_version }} · {{ row.import_format }} · {{ row.state }}</option></select></label>
          <div class="cols"><label>Versão<input v-model="catalogImportForm.version_label" required /></label><label>Vigência<input v-model="catalogImportForm.valid_from" type="date" required /></label></div>
          <label>Arquivo CSV/JSON/XSD<input type="file" accept=".csv,.json,.xsd,text/csv,application/json,application/xml,text/xml" required @change="selectCatalogImportFile" /></label>
          <label class="inline-check"><input v-model="catalogImportForm.auto_publish" type="checkbox" /> Publicar automaticamente após validação</label>
          <button class="primary" :disabled="!catalogImportFile">Importar e validar</button>
        </form>
      </section>
      <section class="panel"><div class="panel-title"><h2>Saúde dos catálogos</h2><span>{{ catalogGovernance?.missing_kinds?.length ?? 0 }} tipo(s) ausente(s)</span></div><table><thead><tr><th>Catálogo</th><th>Versão ativa</th><th>Fontes</th><th>Estado</th></tr></thead><tbody><tr v-for="row in catalogGovernance?.catalogs ?? []" :key="row.catalog_id"><td>{{ row.kind }}</td><td>{{ row.active_version?.version_label ?? '—' }}</td><td>{{ sourceProfilesLabel(row) }}</td><td><span class="pill" :class="row.healthy ? 'ok' : 'warn'">{{ row.healthy ? 'saudável' : row.reasons.join(', ') }}</span></td></tr></tbody></table><p v-if="catalogGovernance?.missing_kinds?.length" class="warn-text">Não configurados: {{ catalogGovernance.missing_kinds.join(', ') }}</p></section>
      <section class="grid-2">
        <div class="panel"><div class="panel-title"><h2>Importações</h2><span>{{ catalogImports.length }}</span></div><table><thead><tr><th>Versão</th><th>Estado</th><th>Entradas</th><th>SHA-256</th><th>Ações</th></tr></thead><tbody><tr v-for="row in catalogImports" :key="row.id"><td>{{ row.version_label }}</td><td>{{ row.state }}</td><td>{{ row.entries_count }}</td><td><code>{{ row.source_sha256 }}</code></td><td><button v-if="row.state === 'draft_created'" class="small" @click="publishCatalogImport(row)">Publicar</button><button v-if="row.catalog_version_id && ['published','scheduled'].includes(row.state)" class="small" @click="rollbackCatalogImport(row)">Rollback</button></td></tr><tr v-if="!catalogImports.length"><td colspan="5" class="empty">Nenhuma importação registrada.</td></tr></tbody></table></div>
        <div class="panel"><div class="panel-title"><h2>Quarentena</h2><span>{{ catalogQuarantine.length }}</span></div><table><thead><tr><th>Motivo</th><th>SHA-256</th><th>Estado</th><th>Ação</th></tr></thead><tbody><tr v-for="row in catalogQuarantine" :key="row.id"><td>{{ row.reason_code }} · {{ row.reason_detail }}</td><td><code>{{ row.source_sha256 }}</code></td><td>{{ row.state }}</td><td><button v-if="row.state === 'open'" class="small danger" @click="resolveCatalogQuarantine(row)">Descartar</button></td></tr><tr v-if="!catalogQuarantine.length"><td colspan="4" class="empty">Nenhum arquivo em quarentena.</td></tr></tbody></table></div>
      </section>
      <section class="panel"><div class="panel-title"><h2>Catálogos publicados</h2><span>{{ catalogs.length }}</span></div><table><thead><tr><th>Tipo</th><th>Nome</th><th>Versão ativa</th><th>Vigência</th><th>SHA-256</th></tr></thead><tbody><tr v-for="row in catalogs" :key="row.id"><td>{{ row.kind }}</td><td>{{ row.name }}</td><td>{{ row.active_version?.version_label ?? '—' }}</td><td>{{ row.active_version ? formatDate(row.active_version.valid_from) : '—' }}</td><td><code>{{ row.active_version?.source_sha256 ?? '—' }}</code></td></tr><tr v-if="!catalogs.length"><td colspan="5" class="empty">Nenhum catálogo fiscal configurado.</td></tr></tbody></table></section>
      <section class="panel"><div class="panel-title"><h2>Classificações publicadas</h2><span>{{ classificationRules.length }}</span></div><table><thead><tr><th>Contexto</th><th>Item</th><th>Operação</th><th>Vigência</th><th>Classificação</th></tr></thead><tbody><tr v-for="row in classificationRules" :key="row.id"><td><code>{{ row.fiscal_context_id }}</code></td><td>{{ row.item_kind }} · {{ row.item_id ?? 'geral' }}</td><td>{{ row.operation_type }}</td><td>{{ formatDate(row.valid_from) }} — {{ formatDate(row.valid_until) }}</td><td>{{ [row.ncm,row.nbs,row.lc116,row.cfop,row.cest,row.cst,row.csosn,row.cst_ibs_cbs,row.cclasstrib,row.cbenef].filter(Boolean).join(' · ') || '—' }}</td></tr></tbody></table></section>
    </template>


    <template v-else-if="tab === 'engine'">
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createTaxRuleSet">
          <h2>Conjunto tributário versionado</h2>
          <label>Contexto<select v-model="taxRuleForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }} · {{ row.establishment_name }}</option></select></label>
          <div class="cols"><label>Código<input v-model="taxRuleForm.code" required /></label><label>Nome<input v-model="taxRuleForm.name" required /></label></div>
          <div class="cols"><label>Estabelecimento<input v-model="taxRuleForm.establishment_code" placeholder="MATRIZ-BA" /></label><label>Operação<input v-model="taxRuleForm.operation_type" required /></label></div>
          <div class="cols"><label>Tipo<select v-model="taxRuleForm.item_kind"><option value="any">Qualquer</option><option value="product">Produto</option><option value="service">Serviço</option><option value="mixed">Misto</option></select></label><label>Regime<input v-model="taxRuleForm.tax_regime" placeholder="any" /></label></div>
          <div class="cols"><label>RTC<select v-model="taxRuleForm.rtc_mode"><option value="any">Qualquer</option><option value="disabled">Desabilitado</option><option value="simulation_only">Simulação</option><option value="optional_emit">Opcional</option><option value="required_emit">Obrigatório</option></select></label><label>Prioridade<input v-model.number="taxRuleForm.priority" type="number" min="0" /></label></div>
          <button class="primary">Criar conjunto</button>
        </form>
        <form class="panel" @submit.prevent="createTaxRuleVersion">
          <div class="panel-title"><h2>Versão e componentes</h2><button type="button" class="small" @click="addTaxComponent">Adicionar tributo</button></div>
          <label>Conjunto<select v-model="taxVersionForm.rule_set_id" required><option value="">Selecione</option><option v-for="row in taxRuleSets" :key="row.id" :value="row.id">{{ row.code }} · {{ row.name }}</option></select></label>
          <div class="cols"><label>Versão<input v-model="taxVersionForm.version_label" required /></label><label>Vigência<input v-model="taxVersionForm.valid_from" type="date" required /></label></div>
          <label>Fonte<input v-model="taxVersionForm.source_name" required /></label><label>Referência<input v-model="taxVersionForm.source_reference" /></label><label>Fundamentação, uma por linha<textarea v-model="taxVersionForm.legal_basis" rows="2"></textarea></label>
          <div v-for="(component, index) in taxComponents" :key="index" class="tax-component">
            <select v-model="component.tax"><option v-for="tax in ['ICMS','ICMS_ST','FCP','IPI','PIS','COFINS','ISS','IBS_ESTADUAL','IBS_MUNICIPAL','CBS','IS']" :key="tax" :value="tax">{{ tax }}</option></select>
            <select v-model="component.incidence"><option v-for="incidence in ['taxable','exempt','deferred','suspended','immune','non_incident','zero_rate','monophase']" :key="incidence" :value="incidence">{{ incidence }}</option></select>
            <select v-model="component.base_mode"><option value="operation_total">Base da operação</option><option value="mva">MVA</option></select>
            <input v-model="component.rate_pct" type="number" step="0.0001" min="0" placeholder="Alíquota %" />
            <input v-model="component.base_reduction_pct" type="number" step="0.0001" min="0" placeholder="Redução %" />
            <input v-model="component.deferral_pct" type="number" step="0.0001" min="0" placeholder="Diferimento %" />
            <input v-model="component.suspension_pct" type="number" step="0.0001" min="0" placeholder="Suspensão %" />
            <input v-model="component.mva_pct" type="number" step="0.0001" min="0" placeholder="MVA %" />
            <input v-model="component.monophase_amount_per_unit" type="number" step="0.0001" min="0" placeholder="Monofásico/unidade" />
            <button type="button" class="small danger" :disabled="taxComponents.length === 1" @click="removeTaxComponent(index)">Remover</button>
          </div>
          <button class="primary">Criar e publicar versão</button>
        </form>
      </section>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="simulateTaxCalculation">
          <h2>Simulação explicável</h2>
          <label>Contexto<select v-model="taxSimulationForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }} · {{ row.establishment_name }}</option></select></label>
          <div class="cols"><label>Estabelecimento<input v-model="taxSimulationForm.establishment_code" /></label><label>Operação<input v-model="taxSimulationForm.operation_type" /></label></div>
          <div class="cols"><label>Tipo<select v-model="taxSimulationForm.item_kind"><option value="product">Produto</option><option value="service">Serviço</option><option value="mixed">Misto</option></select></label><label>Data<input v-model="taxSimulationForm.occurred_on" type="date" /></label></div>
          <div class="cols"><label>Valor<input v-model="taxSimulationForm.amount" type="number" step="0.01" min="0" /></label><label>Quantidade<input v-model="taxSimulationForm.quantity" type="number" step="0.0001" min="0.0001" /></label></div>
          <div class="cols"><label>Frete<input v-model="taxSimulationForm.freight" type="number" step="0.01" min="0" /></label><label>Seguro<input v-model="taxSimulationForm.insurance" type="number" step="0.01" min="0" /></label></div>
          <div class="cols"><label>Outros<input v-model="taxSimulationForm.other_amount" type="number" step="0.01" min="0" /></label><label>Desconto<input v-model="taxSimulationForm.discount" type="number" step="0.01" min="0" /></label></div>
          <button class="primary">Simular cálculo</button>
        </form>
        <div class="panel"><div class="panel-title"><h2>Resultado do motor</h2><strong v-if="taxCalculation">{{ taxCalculation.tax_total }}</strong></div><template v-if="taxCalculation"><div class="details"><span><b>Regra:</b> {{ taxCalculation.rule_set?.code }}</span><span><b>Versão:</b> {{ taxCalculation.rule_set?.version?.version_label }}</span><span><b>Regime:</b> {{ taxCalculation.context?.tax_regime }}</span><span><b>RTC:</b> {{ taxCalculation.context?.rtc_mode }}</span></div><table><thead><tr><th>Tributo</th><th>Incidência</th><th>Base</th><th>Alíquota</th><th>Valor</th></tr></thead><tbody><tr v-for="row in Object.values(taxCalculation.taxes ?? {})" :key="row.tax"><td>{{ row.tax }}</td><td>{{ row.incidence }}</td><td>{{ row.base }}</td><td>{{ row.rate_pct }}%</td><td>{{ row.amount }}</td></tr></tbody></table><p><b>Snapshot:</b> <code>{{ taxCalculation.snapshot_sha256 }}</code></p><p v-if="taxCalculation.divergences?.length" class="warn-text">{{ taxCalculation.divergences.length }} divergência(s) encontrada(s).</p></template><div v-else class="empty">Configure uma regra e execute uma simulação. Nenhuma alíquota é assumida globalmente.</div></div>
      </section>
      <section class="panel"><div class="panel-title"><h2>Conjuntos tributários</h2><span>{{ taxRuleSets.length }}</span></div><table><thead><tr><th>Código</th><th>Escopo</th><th>Regime</th><th>RTC</th><th>Versão ativa</th></tr></thead><tbody><tr v-for="row in taxRuleSets" :key="row.id"><td>{{ row.code }}</td><td>{{ row.operation_type }} · {{ row.item_kind }} · {{ row.establishment_code ?? 'geral' }}</td><td>{{ row.tax_regime }}</td><td>{{ row.rtc_mode }}</td><td>{{ row.active_version?.version_label ?? '—' }}</td></tr><tr v-if="!taxRuleSets.length"><td colspan="5" class="empty">Nenhum conjunto tributário configurado.</td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab === 'strategies'">
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createLegalSource"><h2>Fonte normativa versionada</h2><div class="cols"><label>Tipo<input v-model="legalSourceForm.kind" /></label><label>Versão<input v-model="legalSourceForm.version_label" required /></label></div><label>Título<input v-model="legalSourceForm.title" required /></label><div class="cols"><label>Vigência<input v-model="legalSourceForm.valid_from" type="date" /></label><label>Até<input v-model="legalSourceForm.valid_until" type="date" /></label></div><label>Referência<input v-model="legalSourceForm.source_reference" /></label><label>SHA-256<input v-model="legalSourceForm.source_sha256" /></label><button class="primary">Publicar fonte</button></form>
        <form class="panel" @submit.prevent="createRtcSchedule"><h2>Cronograma RTC</h2><label>Contexto<select v-model="rtcForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }}</option></select></label><div class="cols"><label>Regime<input v-model="rtcForm.tax_regime" /></label><label>Modo<select v-model="rtcForm.mode"><option value="disabled">Desabilitado</option><option value="simulation_only">Simulação</option><option value="optional_emit">Emissão opcional</option><option value="required_emit">Emissão obrigatória</option></select></label></div><div class="cols"><label>Vigência<input v-model="rtcForm.valid_from" type="date" /></label><label>Até<input v-model="rtcForm.valid_until" type="date" /></label></div><button class="primary">Publicar cronograma</button></form>
      </section>
      <section class="grid-2 forms">
        <form class="panel" @submit.prevent="createStrategy"><h2>Estratégia tributária</h2><label>Contexto<select v-model="strategyForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }}</option></select></label><div class="cols"><label>Estratégia<select v-model="strategyForm.strategy_type"><option value="withholding">Retenção</option><option value="difal">DIFAL</option><option value="presumed_credit">Crédito presumido</option><option value="return">Devolução</option><option value="transfer">Transferência</option><option value="adjustment">Ajuste</option><option value="reversal">Estorno</option><option value="import">Importação</option><option value="export">Exportação</option><option value="specific_regime">Regime específico</option></select></label><label>Operação<input v-model="strategyForm.operation_type" /></label></div><div class="cols"><label>Alíquota %<input v-model="strategyForm.rate_pct" type="number" step="0.0001" /></label><label>Valor<input v-model="strategyForm.amount" type="number" step="0.01" /></label></div><button class="primary">Publicar estratégia</button></form>
        <form class="panel" @submit.prevent="createIbptProfile"><h2>Perfil IBPT por tenant</h2><div class="cols"><label>Modo<select v-model="ibptProfileForm.mode"><option value="disabled">Desabilitado</option><option value="local_snapshot">Snapshot local</option><option value="remote_sync">Sincronização remota</option></select></label><label>Provider<input v-model="ibptProfileForm.provider_code" /></label></div><div class="cols"><label>Vigência<input v-model="ibptProfileForm.valid_from" type="date" /></label><label>Até<input v-model="ibptProfileForm.valid_until" type="date" /></label></div><div class="cols"><label><input v-model="ibptProfileForm.sync_enabled" type="checkbox" /> Sincronização diária</label><label><input v-model="ibptProfileForm.fallback_enabled" type="checkbox" /> Fallback local</label></div><div class="cols"><label>Fallback máximo (dias)<input v-model.number="ibptProfileForm.fallback_max_age_days" type="number" min="0" /></label><label>Obsoleto após (dias)<input v-model.number="ibptProfileForm.stale_after_days" type="number" min="0" /></label></div><label>Base URL opcional<input v-model="ibptProfileForm.base_url" placeholder="configuração local/secret" /></label><label>Path por UF<input v-model="ibptProfileForm.uf_path" placeholder="/tabela/ibpt/{uf}" /></label><button class="primary">Criar e publicar perfil</button></form>
      </section>
      <section class="panel"><div class="panel-title"><h2>Perfis IBPT</h2><span>{{ ibptProfiles.length }}</span></div><table><thead><tr><th>Versão</th><th>Modo</th><th>Sync</th><th>Fallback</th><th>Vigência</th><th>Estado</th></tr></thead><tbody><tr v-for="row in ibptProfiles" :key="row.id"><td>v{{ row.version }} · {{ row.provider_code }}</td><td>{{ row.mode }}</td><td>{{ row.sync_enabled ? 'ativo' : 'não' }}</td><td>{{ row.fallback_enabled ? row.fallback_max_age_days + ' dias' : 'desabilitado' }}</td><td>{{ formatDate(row.valid_from) }} — {{ formatDate(row.valid_until) }}</td><td>{{ row.state }}</td></tr><tr v-if="!ibptProfiles.length"><td colspan="6" class="empty">Nenhum perfil IBPT versionado.</td></tr></tbody></table></section>
      <section class="grid-2">
        <div class="panel"><div class="panel-title"><h2>Saúde IBPT</h2><span>{{ ibptStatus?.status ?? '—' }}</span></div><div class="details"><span><b>UF:</b> {{ ibptUf }}</span><span><b>Snapshots:</b> {{ ibptSnapshots.length }}</span><span><b>Ausentes:</b> {{ ibptStatus?.missing_ufs?.length ?? 0 }}</span><span><b>Quarentena:</b> {{ ibptStatus?.quarantine_count ?? 0 }}</span></div><div class="actions"><select v-model="ibptUf"><option v-for="uf in ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']" :key="uf">{{ uf }}</option></select><button type="button" @click="syncIbpt">Sincronizar</button><button type="button" @click="loadIbptOffline">Pacote offline</button></div><p v-if="ibptOffline"><b>Pacote:</b> <code>{{ ibptOffline.package_sha256 }}</code></p></div>
        <div class="panel"><h2>Snapshots IBPT</h2><table><thead><tr><th>UF</th><th>Versão</th><th>Estado</th><th>SHA</th><th>Ação</th></tr></thead><tbody><tr v-for="row in ibptSnapshots.filter(s => !ibptUf || s.uf === ibptUf)" :key="row.id"><td>{{ row.uf }}</td><td>{{ row.source_version }}</td><td>{{ row.state }}</td><td><code>{{ row.sha256 }}</code></td><td><button v-if="row.state !== 'active'" type="button" class="small" @click="rollbackIbpt(row)">Reativar</button></td></tr></tbody></table></div>
      </section>
      <section class="panel"><div class="panel-title"><h2>Estratégias publicadas</h2><span>{{ strategyRules.length }}</span></div><table><thead><tr><th>Tipo</th><th>Operação</th><th>Regime</th><th>RTC</th><th>Vigência</th></tr></thead><tbody><tr v-for="row in strategyRules" :key="row.id"><td>{{ row.strategy_type }}</td><td>{{ row.operation_type }}</td><td>{{ row.tax_regime }}</td><td>{{ row.rtc_mode }}</td><td>{{ formatDate(row.valid_from) }}</td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab === 'routing'">
      <section class="grid-2 forms">
        <form class="panel grid-form" @submit.prevent="createDocumentSchema"><h2>Schema/XSD versionado</h2><div class="cols"><label>Documento<select v-model="documentSchemaForm.document_type"><option>NF-e</option><option>NFC-e</option><option>NFS-e</option></select></label><label>Código<input v-model="documentSchemaForm.schema_code" required /></label></div><div class="cols"><label>Versão<input v-model="documentSchemaForm.version_label" required /></label><label>Vigência<input v-model="documentSchemaForm.valid_from" type="date" /></label></div><label>Elemento raiz<input v-model="documentSchemaForm.root_element" required /></label><label>Namespace<input v-model="documentSchemaForm.namespace_uri" /></label><label>Fonte<input v-model="documentSchemaForm.source_reference" /></label><label>XSD<textarea v-model="documentSchemaForm.xsd_text" rows="8" required placeholder="Cole o XSD local/versionado"></textarea></label><button class="primary">Validar, armazenar e publicar</button></form>
        <form class="panel grid-form" @submit.prevent="createRoutingPolicy"><h2>Política de roteamento</h2><label>Contexto<select v-model="routingPolicyForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }} · {{ row.establishment_name }}</option></select></label><div class="cols"><label>Código<input v-model="routingPolicyForm.code" required /></label><label>Nome<input v-model="routingPolicyForm.name" required /></label></div><div class="cols"><label>Operação<input v-model="routingPolicyForm.operation_type" /></label><label>Destinatário<select v-model="routingPolicyForm.recipient_scope"><option value="any">Qualquer</option><option value="individual">Pessoa física</option><option value="company">Pessoa jurídica</option><option value="government">Governo</option><option value="foreign">Exterior</option></select></label></div><div class="cols"><label>Canal<input v-model="routingPolicyForm.channel_scope" /></label><label>Produto<select v-model="routingPolicyForm.product_document_type"><option value="">Automático</option><option>NF-e</option><option>NFC-e</option></select></label></div><label>Gatilho<select v-model="routingPolicyForm.trigger_types[0]"><option value="manual">Manual</option><option value="sale_completed">Venda concluída</option><option value="service_order_confirmed">Serviço confirmado</option><option value="competence">Competência</option><option value="payment">Pagamento</option><option value="billing">Faturamento</option></select></label><div class="cols"><label>Regime fiscal opcional<input v-model="routingPolicyForm.tax_regime_filter" placeholder="simples_nacional" /></label><label>Município opcional<input v-model="routingPolicyForm.municipality_filter" placeholder="2927408" /></label></div><div class="cols"><label>Ajuste financeiro no cancelamento<select v-model="routingPolicyForm.financial_cancel_mode"><option value="link_only">Somente vincular</option><option value="cancel_unpaid_charge">Cancelar cobrança não paga / exigir reembolso se paga</option></select></label><label class="check"><input v-model="routingPolicyForm.require_financial_contract" type="checkbox" /> Exigir contrato financeiro</label></div><div class="cols"><label>Conta débito do estorno<input v-model="routingPolicyForm.fiscal_reversal_debit_account" placeholder="configurável pela contabilidade" /></label><label>Conta crédito do estorno<input v-model="routingPolicyForm.fiscal_reversal_credit_account" placeholder="configurável pela contabilidade" /></label></div><small>A política nunca apaga pagamento confirmado. Quando configurada para ajustar cobrança, documentos pagos geram pendência de reembolso; documentos não pagos usam lançamento compensatório.</small><button class="primary">Criar e publicar política</button></form>
      </section>
      <section class="panel"><div class="panel-title"><h2>Schemas publicados</h2><span>{{ documentSchemas.length }}</span></div><table><thead><tr><th>Documento</th><th>Schema</th><th>Versão</th><th>Vigência</th><th>SHA-256</th><th>Estado</th></tr></thead><tbody><tr v-for="row in documentSchemas" :key="row.id"><td>{{ row.document_type }}</td><td>{{ row.schema_code }}</td><td>{{ row.version_label }}</td><td>{{ formatDate(row.valid_from) }}</td><td><code>{{ row.xsd_sha256 }}</code></td><td>{{ row.state }} <button v-if="row.state==='draft'" type="button" class="small" @click="publishDocumentSchema(row)">Publicar</button></td></tr><tr v-if="!documentSchemas.length"><td colspan="6" class="empty">Nenhum XSD versionado.</td></tr></tbody></table></section>
      <section class="grid-2 forms"><form class="panel grid-form" @submit.prevent="assembleFiscalDocument"><h2>Montagem e explicabilidade</h2><div class="cols"><label>Contexto<select v-model="assemblyForm.fiscal_context_id" required><option value="">Selecione</option><option v-for="row in contexts" :key="row.id" :value="row.id">{{ row.code }}</option></select></label><label>Perfil fiscal<input v-model="assemblyForm.fiscal_profile_id" required /></label></div><div class="cols"><label>Origem<select v-model="assemblyForm.source_type"><option value="manual">Manual/mista</option><option value="sale">Venda</option><option value="service_order">Pedido de serviço</option></select></label><label>ID origem<input v-model="assemblyForm.source_id" required /></label></div><div class="cols"><label>Destinatário<select v-model="assemblyForm.recipient_scope"><option value="individual">Pessoa física</option><option value="company">Pessoa jurídica</option><option value="government">Governo</option><option value="foreign">Exterior</option></select></label><label>Canal<input v-model="assemblyForm.channel" /></label></div><div class="cols"><label>Nome destinatário<input v-model="assemblyForm.recipient_name" /></label><label>Documento<input v-model="assemblyForm.recipient_document" /></label></div><label>Itens JSON<textarea v-model="assemblyForm.items_json" rows="9"></textarea></label><label><input v-model="assemblyForm.request_emission" type="checkbox" /> Solicitar emissão somente após XSD válido</label><button class="primary">Montar documentos</button></form><div class="panel"><h2>Última decisão</h2><template v-if="assemblyResult"><p><b>Estado:</b> {{ assemblyResult.state }}</p><p><b>Input:</b> <code>{{ assemblyResult.input_sha256 }}</code></p><p><b>Output:</b> <code>{{ assemblyResult.output_sha256 }}</code></p><div v-for="build in assemblyResult.builds ?? []" :key="build.id" class="version-list"><article><div><strong>{{ build.document_type }} · {{ build.relationship }}</strong><small>{{ build.validation_state }} · {{ build.item_count }} item(ns)</small><small>{{ build.routing_reasons?.join(', ') }}</small></div></article></div></template><div v-else class="empty">Nenhuma montagem executada nesta sessão.</div></div></section>
      <section class="panel"><div class="panel-title"><h2>Montagens persistidas</h2><span>{{ fiscalAssemblies.length }}</span></div><table><thead><tr><th>Origem</th><th>Operação</th><th>Gatilho</th><th>Estado</th><th>Input SHA</th><th>Output SHA</th></tr></thead><tbody><tr v-for="row in fiscalAssemblies" :key="row.id"><td>{{ row.source_type }} / {{ row.source_id }}</td><td>{{ row.operation_type }} · {{ row.channel }}</td><td>{{ row.trigger_type }}</td><td>{{ row.state }}</td><td><code>{{ row.input_sha256 }}</code></td><td><code>{{ row.output_sha256 ?? '—' }}</code></td></tr><tr v-if="!fiscalAssemblies.length"><td colspan="6" class="empty">Nenhuma montagem fiscal registrada.</td></tr></tbody></table></section>
      <section class="panel"><div class="panel-title"><h2>Gatilhos de emissão</h2><span>{{ emissionTriggerRuns.length }}</span></div><table><thead><tr><th>Evento</th><th>Origem</th><th>Estado</th><th>Ação</th></tr></thead><tbody><tr v-for="row in emissionTriggerRuns" :key="row.id"><td>{{ row.event_type }}</td><td>{{ row.source_type }} / {{ row.source_id }}</td><td>{{ row.state }}</td><td><button type="button" class="small" @click="evaluateEmissionTrigger(row)">Reavaliar</button></td></tr><tr v-if="!emissionTriggerRuns.length"><td colspan="4" class="empty">Nenhum gatilho processado.</td></tr></tbody></table></section>
    </template>

    <template v-else-if="tab === 'documents'">
      <section class="panel"><div class="panel-title"><h2>Providers fiscais condicionais</h2><span>{{ fiscalProviders.length }}</span></div>
        <form class="grid-form" @submit.prevent="createFiscalProvider"><div class="cols"><label>Provider<select v-model="providerForm.provider_code"><option>SefazNfeProvider</option><option>SefazNfceProvider</option><option>NationalNfseProvider</option><option>MunicipalNfseProvider</option><option>ThirdPartyFiscalProvider</option></select></label><label>Documento<select v-model="providerForm.document_type"><option>NF-e</option><option>NFC-e</option><option>NFS-e</option></select></label></div><label>Nome<input v-model="providerForm.display_name" required /></label><div class="cols"><label>Endpoint HTTPS<input v-model="providerForm.endpoint_url" placeholder="https://..." /></label><label>Referência do segredo<input v-model="providerForm.secret_ref" placeholder="nome-no-secret-store" /></label></div><div class="cols"><label>Certificado A1<select v-model="providerForm.certificate_metadata_id"><option value="">Não aplicável / não configurado</option><option v-for="row in fiscalCertificates" :key="row.id" :value="row.id">{{ row.subject_name }} · {{ row.valid_until }}</option></select></label><label>Ambiente<select v-model="providerForm.environment"><option value="homologation">Homologação</option><option value="production">Produção</option></select></label></div><label><input v-model="providerForm.enabled" type="checkbox" /> Habilitado</label><button class="primary">Salvar provider</button></form>
        <table><thead><tr><th>Provider</th><th>Documento</th><th>Ambiente</th><th>Status</th><th>Health</th><th>Ações</th></tr></thead><tbody><tr v-for="row in fiscalProviders" :key="row.id"><td>{{ row.display_name }}<small>{{ row.provider_code }}</small></td><td>{{ row.document_type }}</td><td>{{ row.environment }}</td><td>{{ row.status }}</td><td>{{ row.last_health_status }}</td><td><button type="button" @click="checkFiscalProvider(row)">Verificar</button></td></tr><tr v-if="!fiscalProviders.length"><td colspan="6" class="empty">Nenhum provider fiscal especializado configurado.</td></tr></tbody></table>
      </section>
      <section class="split"><form class="panel grid-form" @submit.prevent="createFiscalCertificate"><h2>Metadados de certificado A1</h2><label>Titular<input v-model="certificateForm.subject_name" required /></label><div class="cols"><label>CPF/CNPJ<input v-model="certificateForm.subject_document" /></label><label>Serial<input v-model="certificateForm.serial_number" required /></label></div><label>Emissor<input v-model="certificateForm.issuer_name" required /></label><div class="cols"><label>Válido desde<input v-model="certificateForm.valid_from" /></label><label>Válido até<input v-model="certificateForm.valid_until" /></label></div><label>Fingerprint SHA-256<input v-model="certificateForm.fingerprint_sha256" minlength="64" maxlength="64" required /></label><label>Referência segura do PFX<input v-model="certificateForm.secret_ref" required /><small>O PFX e sua senha não são armazenados no frontend nem no PostgreSQL.</small></label><button class="primary">Registrar metadados</button></form>
        <form class="panel grid-form" @submit.prevent="createFiscalInutilization"><h2>Inutilização de numeração</h2><label>Perfil fiscal<input v-model="inutilizationForm.fiscal_profile_id" required /></label><label>Provider<select v-model="inutilizationForm.provider_configuration_id" required><option value="">Selecione</option><option v-for="row in fiscalProviders.filter(p=>p.document_type===inutilizationForm.document_type)" :key="row.id" :value="row.id">{{ row.display_name }}</option></select></label><div class="cols"><label>Documento<select v-model="inutilizationForm.document_type"><option>NF-e</option><option>NFC-e</option></select></label><label>Ano<input v-model.number="inutilizationForm.year" type="number" /></label></div><div class="cols"><label>Série<input v-model="inutilizationForm.series" /></label><label>Inicial<input v-model.number="inutilizationForm.start_number" type="number" min="1" /></label><label>Final<input v-model.number="inutilizationForm.end_number" type="number" min="1" /></label></div><label>Justificativa<textarea v-model="inutilizationForm.reason" minlength="15" required /></label><button class="primary">Solicitar inutilização</button></form>
      </section>
      <section class="panel"><div class="panel-title"><h2>Política de entrega, retry e contingência</h2><span>{{ deliveryPolicies.length }} versões</span></div>
        <form class="grid-form" @submit.prevent="createDeliveryPolicy"><div class="cols"><label>Código<input v-model="deliveryPolicyForm.code" required /></label><label>Nome<input v-model="deliveryPolicyForm.name" required /></label></div><div class="cols"><label>Documento<select v-model="deliveryPolicyForm.document_type"><option value="any">Qualquer</option><option>NF-e</option><option>NFC-e</option><option>NFS-e</option></select></label><label>Provider<select v-model="deliveryPolicyForm.provider_code"><option value="">Qualquer provider</option><option>ThirdPartyFiscalProvider</option><option>SefazNfeProvider</option><option>SefazNfceProvider</option><option>NationalNfseProvider</option><option>MunicipalNfseProvider</option></select></label><label>Ambiente<select v-model="deliveryPolicyForm.environment"><option value="any">Qualquer</option><option value="homologation">Homologação</option><option value="production">Produção</option></select></label></div><div class="cols"><label>Máx. tentativas<input v-model.number="deliveryPolicyForm.max_attempts" type="number" min="1" max="30" /></label><label>Delay inicial (s)<input v-model.number="deliveryPolicyForm.base_delay_seconds" type="number" min="0" /></label><label>Delay máximo (s)<input v-model.number="deliveryPolicyForm.max_delay_seconds" type="number" min="0" /></label></div><div class="cols"><label>Backoff<input v-model="deliveryPolicyForm.backoff_multiplier" /></label><label>Contingência após<input v-model.number="deliveryPolicyForm.contingency_after_attempts" type="number" min="1" /></label><label>Modo<select v-model="deliveryPolicyForm.contingency_mode"><option value="offline">Offline</option><option value="svc">SVC</option><option value="epec">EPEC</option></select></label></div><label><input v-model="deliveryPolicyForm.auto_retry" type="checkbox" /> Retry automático pelo worker conforme countdown versionado</label><button class="primary">Publicar política</button></form>
        <table><thead><tr><th>Código</th><th>Documento</th><th>Provider</th><th>Tentativas</th><th>Backoff</th><th>Contingência</th><th>Estado</th></tr></thead><tbody><tr v-for="row in deliveryPolicies" :key="row.id"><td>{{ row.code }}<small>v{{ row.version }}</small></td><td>{{ row.document_type }}</td><td>{{ row.provider_code ?? 'qualquer' }}</td><td>{{ row.max_attempts }}</td><td>{{ row.base_delay_seconds }}s → {{ row.max_delay_seconds }}s</td><td>{{ row.contingency_after_attempts ? `${row.contingency_after_attempts} · ${row.contingency_mode}` : '—' }}</td><td>{{ row.state }}</td></tr><tr v-if="!deliveryPolicies.length"><td colspan="7" class="empty">Nenhuma política versionada publicada.</td></tr></tbody></table>
      </section>
      <section class="panel"><div class="panel-title"><h2>Documentos fiscais</h2><span>{{ documents.length }} registros</span></div><table><thead><tr><th>Documento</th><th>Origem</th><th>Provider</th><th>Estado</th><th>Contingência</th><th>Ações</th></tr></thead><tbody><tr v-for="row in documents" :key="row.id"><td>{{ row.document_type }}</td><td>{{ row.source_type }} / {{ row.source_id }}</td><td>{{ row.provider_status }}</td><td><span class="pill" :class="row.state === 'authorized' ? 'ok' : row.state.includes('awaiting') ? 'warn' : ''">{{ row.state }}</span></td><td>{{ row.contingency_mode ?? '—' }}</td><td class="actions"><button type="button" @click="queryFiscalDocument(row)">Consultar</button><button v-if="row.state==='authorized'" type="button" @click="requestCorrectionEvent(row)">Evento</button><button v-if="row.state==='authorized'" type="button" @click="substituteFiscalDocument(row)">Substituir</button><button type="button" @click="renderFiscalDocument(row)">Renderizar</button><button type="button" @click="loadDocumentArtifacts(row)">Artefatos</button><button v-if="['rejected','requested'].includes(String(row.state))" type="button" @click="retryFiscalDocument(row)">Retry</button><button v-if="row.error_code || row.state==='rejected'" type="button" @click="loadFiscalRejection(row)">Rejeição</button><button type="button" @click="loadDocumentTransparency(row)">Transparência</button><button v-if="row.state==='authorized'" type="button" class="danger" @click="cancelFiscalDocument(row)">Cancelar</button></td></tr><tr v-if="!documents.length"><td colspan="6" class="empty">Nenhum documento fiscal solicitado.</td></tr></tbody></table></section>
      <section v-if="selectedArtifactDocument" class="panel"><div class="panel-title"><div><h2>Artefatos de {{ selectedArtifactDocument.document_type }}</h2><small>{{ selectedArtifactDocument.id }}</small></div><button type="button" class="small" @click="selectedArtifactDocument=null;selectedArtifacts=[]">Fechar</button></div><table><thead><tr><th>Tipo</th><th>SHA-256</th><th>Tamanho</th><th>Disponível</th><th></th></tr></thead><tbody><tr v-for="artifact in selectedArtifacts" :key="artifact.id"><td>{{ artifact.artifact_type }}</td><td><code>{{ artifact.sha256 }}</code></td><td>{{ artifact.bytes_count }} bytes</td><td><span class="pill" :class="artifact.available ? 'ok' : 'warn'">{{ artifact.available ? 'sim' : 'não' }}</span></td><td><button v-if="artifact.available" type="button" class="small" @click="downloadFiscalArtifact(selectedArtifactDocument, artifact)">Baixar PDF</button></td></tr><tr v-if="!selectedArtifacts.length"><td colspan="5" class="empty">Nenhum artefato renderizado para este documento.</td></tr></tbody></table></section>
      <section v-if="selectedRejection" class="panel"><div class="panel-title"><h2>Diagnóstico da rejeição</h2><span>{{ selectedRejection.state }}</span></div><div v-if="selectedRejection.rejection" class="details"><span><b>Código:</b> {{ selectedRejection.rejection.error_code ?? '—' }}</span><span><b>Categoria:</b> {{ selectedRejection.rejection.category }}</span><span><b>Retryable:</b> {{ selectedRejection.rejection.retryable ? 'sim' : 'não' }}</span><span><b>Próxima tentativa:</b> {{ selectedRejection.rejection.next_retry_at ?? '—' }}</span></div><pre v-if="selectedRejection.rejection">{{ JSON.stringify(selectedRejection.rejection.explanation, null, 2) }}</pre><p v-else>Nenhuma rejeição persistida para este documento.</p></section>
      <section v-if="documentTransparency" class="panel"><div class="panel-title"><h2>Transparência tributária</h2><strong>vTotTrib {{ documentTransparency.vtottrib ?? '0.00' }}</strong></div><div class="details"><span><b>Documento:</b> {{ documentTransparency.fiscal_document_id }}</span><span><b>Perfil IBPT:</b> {{ documentTransparency.ibpt_provider_profile_id ?? 'cache local legado' }}</span><span><b>Fonte de cálculo:</b> tributos reais</span><span><b>IBPT:</b> somente transparência</span></div><div class="grid-2"><div><h3>Tributos reais</h3><pre>{{ JSON.stringify(documentTransparency.real_taxes, null, 2) }}</pre></div><div><h3>Aproximados IBPT</h3><pre>{{ JSON.stringify(documentTransparency.approximate_ibpt, null, 2) }}</pre></div></div><p><b>tax_calculation_source:</b> false para IBPT.</p></section>
      <section class="panel"><div class="panel-title"><h2>Inutilizações</h2><span>{{ fiscalInutilizations.length }}</span></div><table><thead><tr><th>Documento</th><th>Faixa</th><th>Ano</th><th>Estado</th><th>Protocolo</th></tr></thead><tbody><tr v-for="row in fiscalInutilizations" :key="row.id"><td>{{ row.document_type }}</td><td>{{ row.series }} / {{ row.start_number }}–{{ row.end_number }}</td><td>{{ row.year }}</td><td>{{ row.state }}</td><td>{{ row.protocol ?? '—' }}</td></tr><tr v-if="!fiscalInutilizations.length"><td colspan="5" class="empty">Nenhuma inutilização registrada.</td></tr></tbody></table></section>
    </template>

    <section v-else class="panel">
      <div class="panel-title"><h2>Regras tributárias versionadas</h2><span>{{ rules.length }} registros</span></div>
      <table><thead><tr><th>Perfil</th><th>Operação</th><th>Item</th><th>Classificação</th><th>Vigência</th><th>Versão</th></tr></thead><tbody><tr v-for="row in rules" :key="row.id"><td><code>{{ row.fiscal_profile_id }}</code></td><td>{{ row.operation_type }}</td><td>{{ row.item_kind }}</td><td>{{ row.classification_key ?? "geral" }}</td><td>{{ formatDate(row.effective_from) }} — {{ formatDate(row.effective_until) }}</td><td>{{ row.version }}</td></tr><tr v-if="!rules.length"><td colspan="6" class="empty">Nenhuma regra tributária cadastrada.</td></tr></tbody></table>
    </section>
  </div>
</template>

<style scoped>
.tabs{display:flex;gap:8px;align-items:center;margin-bottom:16px}.tabs button.active{background:var(--brand-primary);color:#fff}.tabs .refresh{margin-left:auto}.context-list,.version-list{display:flex;flex-direction:column;gap:8px}.context-list>button,.version-list article{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px;border:1px solid var(--line,#e5e7eb);border-radius:10px;background:transparent;text-align:left}.context-list>button.selected{border-color:var(--brand-primary);box-shadow:0 0 0 1px var(--brand-primary)}.context-list span:first-child,.version-list article>div:first-child{display:flex;flex-direction:column}.context-list small,.version-list small{opacity:.72}.details{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.actions{display:flex;gap:8px;flex-wrap:wrap}.scope-title{display:flex;align-items:center;justify-content:space-between}.scope-row{display:grid;grid-template-columns:1.2fr repeat(3,1fr) auto;gap:8px;margin-bottom:8px}.version-list article>div:last-child{display:flex;align-items:center;gap:8px}dl{display:grid;grid-template-columns:100px 1fr;gap:8px}dt{font-weight:700}dd{margin:0;min-width:0}code{overflow-wrap:anywhere}.danger{border-color:#b91c1c;color:#b91c1c}.classification-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.tax-component{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:10px 0;border-bottom:1px solid var(--line,#e5e7eb)}.warn-text{color:#b45309;font-weight:600}@media(max-width:1000px){.details{grid-template-columns:1fr 1fr}.scope-row{grid-template-columns:1fr 1fr}.classification-grid{grid-template-columns:1fr 1fr}}@media(max-width:700px){.tabs{flex-wrap:wrap}.tabs .refresh{margin-left:0}.details,.scope-row,.classification-grid{grid-template-columns:1fr}.context-list>button,.version-list article{align-items:flex-start;flex-direction:column}}
</style>
